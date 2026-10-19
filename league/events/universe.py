"""Eligibility for an entry session (PREREG-EVL-1 section 2), computed lazily for the issuers that have events.

A stock is eligible for entry session D when, from data before D's open: its ticker maps to the issuer's CIK in SEC's
`company_tickers.json` (several tickers: the highest ADV); Alpaca lists it active, tradable, `us_equity`, on NYSE,
NASDAQ, AMEX, ARCA or BATS; its last SIP close >= $3; its ADV (mean close x volume over the 20 completed sessions
before D) >= $1,000,000 with a bar on each of them; and its issuer is an operating company (a 10-K, 10-Q, 20-F or 40-F
in the 15 months before D, SIC != 6221; EDGAR's company feed, cached 30 days). The benchmark is IWM when ADV <
$50,000,000, else SPY.

SIP daily bars on Alpaca's free Basic plan: `end` must be at least 15 minutes old, so a request's `end` is the day
after its last wanted session (a past instant) or now - 16 minutes, whichever is earlier.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, Callable, Iterable, Mapping

from . import calendar as C
from . import store as S

EXCHANGES = frozenset({"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"})
MIN_PRICE = 3.0
MIN_ADV = 1_000_000.0
ADV_SESSIONS = 20
BENCH_SPLIT = 50_000_000.0
PERIODIC = ("10-K", "10-Q", "20-F", "40-F", "10-K/A", "10-Q/A", "20-F/A", "40-F/A", "10-KT")
OPERATING_MONTHS = 15
CIK_TTL = dt.timedelta(days=30)
COMMODITY_SIC = "6221"
SIP_DELAY = dt.timedelta(minutes=16)
SYMBOLS_PER_REQUEST = 200
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def sip_end(last_day: dt.date, now: dt.datetime) -> str:
    """The `end` for SIP daily bars through `last_day` that Basic admits (RFC 3339, UTC)."""
    wanted = dt.datetime.combine(last_day + dt.timedelta(days=1), dt.time(0, 0), tzinfo=dt.timezone.utc)
    return S.iso(min(wanted, now - SIP_DELAY))


def fetch_daily_bars(store: S.Store, gw: Any, symbols: Iterable[str], first: dt.date, last: dt.date, *, adj: str = "raw",
                     now: dt.datetime | None = None) -> int:
    """Fetch SIP 1Day bars for `symbols` from `first` to `last` into `bars` (adj 'raw' or 'all'). Returns rows stored."""
    now = now or S.utc_now()
    names = sorted({s.upper() for s in symbols if s})
    stored = 0
    for i in range(0, len(names), SYMBOLS_PER_REQUEST):
        chunk = names[i:i + SYMBOLS_PER_REQUEST]
        token = None
        for _ in range(200):
            page = gw.get_json("/v1/alpaca/v2/stocks/bars", {
                "symbols": ",".join(chunk), "timeframe": "1Day", "start": first.isoformat(), "end": sip_end(last, now),
                "feed": "sip", "adjustment": adj, "limit": 10000, "page_token": token})
            with store.tx() as db:
                for sym, rows in ((page or {}).get("bars") or {}).items():
                    for b in rows or []:
                        day = S.parse_iso(str(b["t"])).astimezone(C.NY).date().isoformat()
                        db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, ?, ?, ?, ?, "
                                   "?, ?, ?) ON CONFLICT(symbol, day, adj) DO UPDATE SET o=excluded.o, h=excluded.h, "
                                   "l=excluded.l, c=excluded.c, v=excluded.v, fetched_at=excluded.fetched_at",
                                   (sym.upper(), day, adj, b.get("o"), b.get("h"), b.get("l"), b.get("c"), b.get("v"),
                                    S.iso(now)))
                        stored += 1
            token = (page or {}).get("next_page_token")
            if not token:
                break
    return stored


def bars(store: S.Store, symbol: str, days: Iterable[dt.date], adj: str = "raw") -> dict[str, Mapping[str, Any]]:
    want = [d.isoformat() for d in days]
    if not want:
        return {}
    marks = ",".join("?" * len(want))
    rows = store.db.execute(f"SELECT * FROM bars WHERE symbol=? AND adj=? AND day IN ({marks})", (symbol.upper(), adj, *want))
    return {r["day"]: dict(r) for r in rows}


def sec_tickers(get_sec: Callable[[str], bytes]) -> dict[str, list[tuple[str, str]]]:
    """CIK (10 digits) -> [(ticker, title)] from company_tickers.json."""
    payload = json.loads(get_sec(TICKERS_URL).decode("utf-8"))
    rows = payload.values() if isinstance(payload, dict) else payload
    out: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        try:
            cik = str(int(row["cik_str"])).zfill(10)
        except (KeyError, TypeError, ValueError):
            continue
        out.setdefault(cik, []).append((str(row.get("ticker", "")).upper(), str(row.get("title", ""))))
    return out


def alpaca_assets(gw: Any) -> dict[str, Mapping[str, Any]]:
    rows = gw.get_json("/v1/alpaca/v2/assets", {"status": "active", "asset_class": "us_equity"})
    return {str(a.get("symbol", "")).upper(): a for a in rows or []}


def _listed(asset: Mapping[str, Any] | None) -> bool:
    return bool(asset) and asset.get("status") == "active" and bool(asset.get("tradable")) \
        and asset.get("class") == "us_equity" and asset.get("exchange") in EXCHANGES


def company_feed_url(cik: str, form_prefix: str) -> str:
    return (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_prefix}&dateb="
            f"&owner=include&count=10&output=atom")


def operating(store: S.Store, get_sec: Callable[[str], bytes], cik: str, day: dt.date, *,
              now: dt.datetime | None = None) -> bool:
    """The operating-company test for `cik` as of entry session `day` (cached in cik_info for 30 days)."""
    now = now or S.utc_now()
    row = store.db.execute("SELECT * FROM cik_info WHERE cik=?", (cik,)).fetchone()
    if row is None or now - S.parse_iso(row["checked_at"]) > CIK_TTL:
        sic, best_form, best_date = None, None, None
        for prefix in ("10-", "20-F", "40-F"):
            body = get_sec(company_feed_url(cik, prefix)).decode("latin-1")
            m = re.search(r"<assigned-sic>(\d+)</assigned-sic>", body)
            sic = sic or (m.group(1) if m else None)
            for entry in body.split("<entry>")[1:]:
                ft = re.search(r"<filing-type>(.*?)</filing-type>", entry)
                fd = re.search(r"<filing-date>(\d{4}-\d{2}-\d{2})</filing-date>", entry)
                if ft and fd and ft.group(1).strip() in PERIODIC:
                    if best_date is None or fd.group(1) > best_date:
                        best_form, best_date = ft.group(1).strip(), fd.group(1)
                    break
            if best_date is not None:
                break
        store.db.execute("INSERT INTO cik_info(cik, sic, periodic_form, periodic_at, operating, checked_at) VALUES(?, ?, "
                         "?, ?, NULL, ?) ON CONFLICT(cik) DO UPDATE SET sic=excluded.sic, periodic_form=excluded."
                         "periodic_form, periodic_at=excluded.periodic_at, checked_at=excluded.checked_at",
                         (cik, sic, best_form, best_date, S.iso(now)))
        row = store.db.execute("SELECT * FROM cik_info WHERE cik=?", (cik,)).fetchone()
    if row["sic"] == COMMODITY_SIC or not row["periodic_at"]:
        return False
    periodic = dt.date.fromisoformat(row["periodic_at"])
    cutoff_month = day.month - OPERATING_MONTHS
    year, month = day.year + (cutoff_month - 1) // 12, (cutoff_month - 1) % 12 + 1
    cutoff = dt.date(year, month, min(day.day, 28))
    return cutoff <= periodic < day


def eligible(store: S.Store, cik: str, day: dt.date, *, tickers: Mapping[str, list[tuple[str, str]]],
             assets: Mapping[str, Mapping[str, Any]], operating_ok: bool, now: dt.datetime | None = None
             ) -> dict[str, Any] | None:
    """The universe row for (cik, entry session `day`), or None. Needs the 20 sessions' raw bars already fetched."""
    prior = C.previous(store, day, ADV_SESSIONS)
    if len(prior) < ADV_SESSIONS or not operating_ok:
        return None
    best = None
    for symbol, title in tickers.get(cik, []):
        if not _listed(assets.get(symbol)):
            continue
        got = bars(store, symbol, [s.day for s in prior], "raw")
        if len(got) < ADV_SESSIONS or any(got[s.day.isoformat()].get("c") is None for s in prior):
            continue
        closes = [float(got[s.day.isoformat()]["c"]) for s in prior]
        vols = [float(got[s.day.isoformat()]["v"] or 0) for s in prior]
        adv = sum(c * v for c, v in zip(closes, vols)) / ADV_SESSIONS
        prev_close = closes[-1]
        if prev_close < MIN_PRICE or adv < MIN_ADV:
            continue
        if best is None or adv > best["adv20"]:
            best = {"day": day.isoformat(), "symbol": symbol, "cik": cik, "name": title,
                    "exchange": assets[symbol].get("exchange"), "prev_close": prev_close, "adv20": adv,
                    "bench": "IWM" if adv < BENCH_SPLIT else "SPY"}
    if best is not None:
        store.db.execute("INSERT OR REPLACE INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, sigma60) "
                         "VALUES(?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                         (best["day"], best["symbol"], cik, best["name"], best["exchange"], best["prev_close"],
                          best["adv20"], best["bench"]))
    return best


__all__ = ["sip_end", "fetch_daily_bars", "bars", "sec_tickers", "alpaca_assets", "operating", "eligible", "EXCHANGES"]

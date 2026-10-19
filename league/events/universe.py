"""Eligibility for an entry session (PREREG-EVL-1 section 2), computed lazily for the issuers that have events.

A stock is eligible for entry session D when, from data before D's open: its ticker maps to the issuer's CIK in SEC's
`company_tickers.json` (several tickers: the highest ADV); Alpaca lists it active, tradable, `us_equity`, on NYSE,
NASDAQ, AMEX, ARCA or BATS; its last SIP close >= $3; its ADV (mean close x volume over the 20 completed sessions
before D) >= $1,000,000 with a bar on each of them; and its issuer is an operating company (a 10-K, 10-Q, 20-F or 40-F
in the 15 months before D, SIC != 6221; EDGAR's company feed, cached 30 days). The benchmark is IWM when ADV <
$50,000,000, else SPY.

SIP daily bars on Alpaca's free Basic plan: `end` must be at least 15 minutes old, so a request's `end` is the day
after its last wanted session (a past instant) or now - 16 minutes, whichever is earlier.

ONCE PER (ENTRY SESSION, CIK), BY THE RULE THAT MADE IT (release 1019b's second review; league/events/store.py
`eligibility`): every result, eligible or not, is kept with its rule (`record_result`), and a decision reads them
(league/events/run.py `eligibility`): a LIVE decision the live rule's result, checking under the live rule an issuer
that has none (one the backfill rule judged first included); a BACKFILL decision (the House's hourly re-decision of the
last sessions among them) any result there is, eligible only when none is ineligible (`combined`: the reading that
trades less), and checks under the backfill rule only an issuer no decision of the session has judged. The House's real
money reads the live rule's eligible results alone (league/events/book.py).
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
BLANK_CHECK_SIC = "6770"
EXCLUDED_SIC = frozenset({COMMODITY_SIC, BLANK_CHECK_SIC})
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


def alpaca_assets(gw: Any, status: str = "active") -> dict[str, Mapping[str, Any]]:
    """Alpaca's us_equity assets: `status` "active" for live decisions, "all" for backfilled ones (PREREG draft 2
    section 2: a name delisted since cannot drop out of a backfilled day)."""
    rows = gw.get_json("/v1/alpaca/v2/assets", {"status": status, "asset_class": "us_equity"})
    out: dict[str, Mapping[str, Any]] = {}
    for a in rows or []:
        sym = str(a.get("symbol", "")).upper()
        if sym not in out or a.get("status") == "active":   # a reused symbol: the active record wins
            out[sym] = a
    return out


def _listed(asset: Mapping[str, Any] | None, live: bool = True) -> bool:
    if not asset or asset.get("class") != "us_equity" or asset.get("exchange") not in EXCHANGES:
        return False
    return (asset.get("status") == "active" and bool(asset.get("tradable"))) if live else True


def company_feed_url(cik: str, form_prefix: str) -> str:
    return (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_prefix}&dateb="
            f"&owner=include&count=10&output=atom")


def operating(store: S.Store, get_sec: Callable[[str], bytes], cik: str, day: dt.date, *,
              now: dt.datetime | None = None) -> bool:
    """The operating-company test for `cik` as of entry session `day`: a 10-K, 10-Q, 20-F or 40-F (or amendment) filed
    in the 15 months before `day`, and an SIC that is neither 6221 nor 6770. EDGAR's company feed is read per form
    family (newest first, up to 10 each) and every periodic filing date is cached (cik_info.periodic_at, comma
    separated) for 30 days, so a backfilled `day` is judged on the filings before it, not on the newest one."""
    now = now or S.utc_now()
    row = store.db.execute("SELECT * FROM cik_info WHERE cik=?", (cik,)).fetchone()
    if row is None or now - S.parse_iso(row["checked_at"]) > CIK_TTL:
        sic, dates, forms = None, set(), set()
        for prefix in ("10-", "20-F", "40-F"):
            body = get_sec(company_feed_url(cik, prefix)).decode("latin-1")
            m = re.search(r"<assigned-sic>(\d+)</assigned-sic>", body)
            sic = sic or (m.group(1) if m else None)
            for entry in body.split("<entry>")[1:]:
                ft = re.search(r"<filing-type>(.*?)</filing-type>", entry)
                fd = re.search(r"<filing-date>(\d{4}-\d{2}-\d{2})</filing-date>", entry)
                if ft and fd and ft.group(1).strip() in PERIODIC:
                    dates.add(fd.group(1))
                    forms.add(ft.group(1).strip())
            if dates:
                break  # a domestic filer's 10-K/10-Q history (or a foreign one's): the other families add nothing
        store.db.execute("INSERT INTO cik_info(cik, sic, periodic_form, periodic_at, operating, checked_at) VALUES(?, ?, "
                         "?, ?, NULL, ?) ON CONFLICT(cik) DO UPDATE SET sic=excluded.sic, periodic_form=excluded."
                         "periodic_form, periodic_at=excluded.periodic_at, checked_at=excluded.checked_at",
                         (cik, sic, ",".join(sorted(forms)) or None, ",".join(sorted(dates)) or None, S.iso(now)))
        row = store.db.execute("SELECT * FROM cik_info WHERE cik=?", (cik,)).fetchone()
    if row["sic"] in EXCLUDED_SIC or not row["periodic_at"]:
        return False
    cutoff_month = day.month - OPERATING_MONTHS
    year, month = day.year + (cutoff_month - 1) // 12, (cutoff_month - 1) % 12 + 1
    cutoff = dt.date(year, month, min(day.day, 28))
    return any(cutoff <= dt.date.fromisoformat(d) < day for d in str(row["periodic_at"]).split(","))


#: SIP listing-exchange codes and Alpaca's exchange names (PREREG-EVL-1 section 5; verified on the Oct 16, 2026 tape).
EXCHANGE_CODES = {"NYSE": "N", "NASDAQ": "Q", "AMEX": "A", "ARCA": "P", "BATS": "Z"}
CODE_EXCHANGES = {v: k for k, v in EXCHANGE_CODES.items()}


def closing_print_exchange(gw: Any, symbol: str, session: Any) -> str | None:
    """The exchange name whose condition-`6` closing print `symbol` had on `session` (the first one), or None."""
    page = gw.get_json(f"/v1/alpaca/v2/stocks/{symbol}/trades", {
        "start": S.iso(session.close_at - dt.timedelta(seconds=5)), "end": S.iso(session.close_at + dt.timedelta(minutes=5)),
        "feed": "sip", "limit": 10000})
    for t in (page or {}).get("trades") or []:
        if "6" in (t.get("c") or []) and t.get("x") in CODE_EXCHANGES:
            return CODE_EXCHANGES[t["x"]]
    return None


def eligible(store: S.Store, cik: str, day: dt.date, *, tickers: Mapping[str, list[tuple[str, str]]],
             assets: Mapping[str, Mapping[str, Any]], operating_ok: bool, now: dt.datetime | None = None,
             live: bool = True, listing: Callable[[str], str | None] | None = None) -> dict[str, Any] | None:
    """`listing(symbol)` -> the listing exchange name for a BACKFILLED day (the previous session's closing-print
    exchange: PREREG section 2); a live day reads the Alpaca asset's exchange."""
    """The universe row for (cik, entry session `day`), or None. Needs the 20 sessions' raw bars already fetched."""
    prior = C.previous(store, day, ADV_SESSIONS)
    if len(prior) < ADV_SESSIONS or not operating_ok:
        return None
    best = None
    for symbol, title in tickers.get(cik, []):
        if not _listed(assets.get(symbol), live):
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
        if best is not None and adv <= best["adv20"]:
            continue
        exchange = assets[symbol].get("exchange") if live or listing is None else listing(symbol)
        if exchange not in EXCHANGES:
            continue  # a backfilled name with no closing print on a listed exchange the session before D
        best = {"day": day.isoformat(), "symbol": symbol, "cik": cik, "name": title, "exchange": exchange,
                "prev_close": prev_close, "adv20": adv, "bench": "IWM" if adv < BENCH_SPLIT else "SPY"}
    if best is not None:
        store.db.execute("INSERT OR REPLACE INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, sigma60) "
                         "VALUES(?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                         (best["day"], best["symbol"], cik, best["name"], best["exchange"], best["prev_close"],
                          best["adv20"], best["bench"]))
    return best


# ---------------------------------------------------------------------------------------------------- the results
def results(store: S.Store, day: dt.date) -> dict[str, dict[str, dict[str, Any] | None]]:
    """{cik: {rule: its universe row when eligible, None when not}} of entry session `day` (`eligibility`). An eligible
    result whose universe row is gone (its symbol's row since written for another issuer) reads as no result."""
    rows = {str(r["symbol"]): dict(r) for r in store.db.execute("SELECT * FROM universe WHERE day=?", (day.isoformat(),))}
    out: dict[str, dict[str, dict[str, Any] | None]] = {}
    for r in store.db.execute("SELECT cik, rule, eligible, symbol FROM eligibility WHERE day=?", (day.isoformat(),)):
        cik, rule = str(r["cik"]), str(r["rule"])
        if not r["eligible"]:
            out.setdefault(cik, {})[rule] = None
            continue
        row = rows.get(str(r["symbol"]))
        if row is not None and str(row["cik"]) == cik:
            out.setdefault(cik, {})[rule] = row
    return out


def record_result(store: S.Store, day: dt.date, cik: str, rule: str, row: Mapping[str, Any] | None, *,
                  now: dt.datetime | None = None) -> None:
    """Keep one result of the test (`eligible`'s row, or None), once: the first result of a (day, cik, rule) stands."""
    if rule not in (S.LIVE_RULE, S.BACKFILL_RULE):
        raise ValueError(rule)
    store.db.execute("INSERT OR IGNORE INTO eligibility(day, cik, rule, eligible, symbol, decided_at) VALUES(?, ?, ?, ?, ?, "
                     "?)", (day.isoformat(), str(cik), rule, 1 if row else 0, str(row["symbol"]) if row else None,
                            S.iso(now or S.utc_now())))


def combined(have: Mapping[str, Mapping[str, Any] | None]) -> Mapping[str, Any] | None:
    """A BACKFILL decision's reading of an issuer's results for one session: eligible only when no result is
    ineligible (the reading that trades less; two results exist when a live decision checked again an issuer the
    backfill rule judged first), with the live rule's row when there is one."""
    if not have or any(v is None for v in have.values()):
        return None
    return have.get(S.LIVE_RULE) or have.get(S.BACKFILL_RULE)


def seen_live(store: S.Store, day: dt.date, kind: str, stored: Mapping[str, str | None]) -> set[str]:
    """THE SESSIONS DECIDED BEFORE THE `eligibility` TABLE (`day` before meta `ELIGIBILITY_FROM`; league/events/store.py)
    kept no ineligible result. Of the issuers in `stored` ({cik: when this decision's first event of it was stored},
    none with a result), those whose event was stored BEFORE the session's first finished live `kind` decision (its
    receipt `ok` or `pending`, started within `LEGACY_LIVE_WITHIN` of its time) were judged by that decision under the
    live rule, which kept every eligible one: they were ineligible, and a re-decision does not judge them again."""
    since = store.meta(S.ELIGIBILITY_FROM)
    if not stored or since is None or day.isoformat() >= since:
        return set()
    session = C.session(store, day)
    if session is None:
        return set()
    scheduled = session.open_decide if kind == "open" else session.close_decide
    started = None
    for r in store.db.execute("SELECT started_at FROM receipts WHERE job=? AND status IN ('ok', 'pending') ORDER BY id",
                              (f"decide-{kind}:{day.isoformat()}",)):
        at = S.parse_iso(r["started_at"])
        if dt.timedelta(0) <= at - scheduled <= S.LEGACY_LIVE_WITHIN:
            started = at
            break
    if started is None:
        return set()
    return {cik for cik, when in stored.items() if when and S.parse_iso(when) < started}


__all__ = ["sip_end", "fetch_daily_bars", "bars", "sec_tickers", "alpaca_assets", "operating", "eligible", "EXCHANGES",
           "EXCHANGE_CODES", "CODE_EXCHANGES", "closing_print_exchange", "results", "record_result", "combined",
           "seen_live"]

"""The event lane's passes: record, backfill, decide at the open, decide at the close (shadow).

Each pass writes a receipt. Decisions are recorded at their SCHEDULED time (09:15 ET open, close - 14 min) whether
they ran live or as a backfill (`why` says which): a backfilled decision uses only data that was knowable at the
scheduled time (filings by knowable time, the universe from the sessions before D, C1's 15:30 minute bar and the
last daily close before the acceptance). Verdicts are asked only for eligible events of the reading programs.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Callable, Iterable, Mapping

from . import calendar as C
from . import edgar as E
from . import news as N
from . import programs as P
from . import store as S
from . import universe as U
from . import verdicts as V


class Context:
    """What a pass needs from the outside world, built once per pass."""

    def __init__(self, store: S.Store, gw: Any, sec: Callable[[str], bytes], *, now: Callable[[], dt.datetime] = S.utc_now):
        self.store, self.gw, self.sec, self.now = store, gw, sec, now
        self._tickers_by_sha: dict[str, dict[str, list[tuple[str, str]]]] = {}
        self._assets: dict[str, dict[str, Mapping[str, Any]]] = {}

    # SEC's company_tickers.json is snapshotted into the store with its fetch time (meta `tickers@<iso>` = document
    # sha); a decision for entry session D reads the latest snapshot fetched before 07:30 ET of D (PREREG draft 2
    # section 2), or, when the lane holds none that early, its earliest snapshot.
    def snapshot_tickers(self) -> str:
        raw = self.sec(U.TICKERS_URL)
        sha = self.store.put_document(raw, "company_tickers", now=self.now())
        self.store.set_meta(f"tickers@{S.iso(self.now())}", sha)
        return sha

    def _snapshots(self) -> list[tuple[dt.datetime, str]]:
        rows = self.store.db.execute("SELECT key, value FROM meta WHERE key LIKE 'tickers@%' ORDER BY key").fetchall()
        return [(S.parse_iso(k.split("@", 1)[1]), v) for k, v in rows]

    def _parsed(self, sha: str) -> dict[str, list[tuple[str, str]]]:
        if sha not in self._tickers_by_sha:
            data = self.store.get_document(sha)
            self._tickers_by_sha[sha] = U.sec_tickers(lambda url: data)
        return self._tickers_by_sha[sha]

    def tickers_for(self, day: dt.date | None = None) -> dict[str, list[tuple[str, str]]]:
        snaps = self._snapshots()
        if not snaps:
            self.snapshot_tickers()
            snaps = self._snapshots()
        if day is None:
            return self._parsed(snaps[-1][1])
        cutoff = dt.datetime.combine(day, dt.time(7, 30), tzinfo=C.NY).astimezone(dt.timezone.utc)
        before = [sha for at, sha in snaps if at < cutoff]
        return self._parsed(before[-1] if before else snaps[0][1])

    @property
    def tickers(self) -> dict[str, list[tuple[str, str]]]:
        return self.tickers_for(None)

    def cik_of_ticker(self, ticker: str, day: dt.date | None = None) -> str | None:
        for cik, rows in self.tickers_for(day).items():
            if any(t == ticker.upper() for t, _ in rows):
                return cik
        return None

    def assets(self, live: bool = True) -> dict[str, Mapping[str, Any]]:
        key = "active" if live else "all"
        if key not in self._assets:
            self._assets[key] = U.alpaca_assets(self.gw, key)
        return self._assets[key]


# ---------------------------------------------------------------------------------------------------- recording
def record_pass(ctx: Context) -> dict[str, Any]:
    """New filings from EDGAR's current feeds (8-K and 4; fetched when the issuer is a listed company) and new news."""
    st = ctx.store
    rid = st.start_receipt("record", now=ctx.now())
    out: dict[str, Any] = {}
    listed = set(ctx.tickers)
    for form in E.FORMS:
        known = [r[0] for r in st.db.execute("SELECT accession FROM filings WHERE form=? ORDER BY accepted_at DESC LIMIT 2000",
                                             (form,))]
        entries = E.poll_current(ctx.sec, form, known)
        counts = {"new": len(entries), "fetched": 0, "failed": 0, "unlisted": 0}
        for entry in entries:
            # a Form 4 is always fetched (its XML names the issuer); an 8-K only when its filer is a listed company
            fetch = form == "4" or entry["cik"] in listed
            status = E.record_filing(st, ctx.sec, entry, source="current", now=ctx.now(), fetch=fetch)
            if not fetch:
                counts["unlisted"] += 1
            elif status == "fetched":
                counts["fetched"] += 1
            elif status.startswith("failed"):
                counts["failed"] += 1
        out[form] = counts
    try:
        since = N.latest_created(st) or (ctx.now() - dt.timedelta(hours=2))
        out["news"] = N.record(st, ctx.gw, since - dt.timedelta(minutes=5), ctx.now(), now=ctx.now())
    except Exception as exc:  # noqa: BLE001 - news failing (no gateway path yet) never stops the filings
        out["news"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    st.finish_receipt(rid, "ok", out, now=ctx.now())
    return out


def backfill(ctx: Context, first: dt.date, last: dt.date, *, forms: Iterable[str] = E.FORMS, news: bool = True) -> dict[str, Any]:
    """Every 8-K and Form 4 of EDGAR's daily indexes from `first` to `last` (listed issuers fetched), and the news of
    the span. Days whose index is not published yet are left to the current-feed passes."""
    st = ctx.store
    rid = st.start_receipt("backfill", now=ctx.now())
    listed = set(ctx.tickers)
    out: dict[str, Any] = {"days": {}}
    day = first
    while day <= last:
        if day.weekday() < 5:
            try:
                rows = E.parse_daily_index(ctx.sec(E.daily_index_url(day)), forms)
            except Exception as exc:  # noqa: BLE001 - an unpublished index is a later pass's
                out["days"][day.isoformat()] = f"no index ({type(exc).__name__})"
                day += dt.timedelta(days=1)
                continue
            n = {"rows": len(rows), "fetched": 0, "failed": 0, "unlisted": 0}
            for row in rows:
                if row["form"] == "8-K" and row["cik"] not in listed:
                    n["unlisted"] += 1  # never stored: the index carries no acceptance time to store it with
                    continue
                status = E.record_filing(st, ctx.sec, row | {"accepted_at": None, "index_url": None, "items": []},
                                         source="daily-index", now=ctx.now(), fetch=True)
                if status == "fetched":
                    n["fetched"] += 1
                elif status.startswith("failed"):
                    n["failed"] += 1
            out["days"][day.isoformat()] = n
        day += dt.timedelta(days=1)
    try:
        if not news:
            raise LookupError("news not asked")
        lo = dt.datetime.combine(first, dt.time(0, 0), tzinfo=dt.timezone.utc)
        hi = dt.datetime.combine(last + dt.timedelta(days=1), dt.time(0, 0), tzinfo=dt.timezone.utc)
        out["news"] = N.record(st, ctx.gw, lo, hi, now=ctx.now())
    except Exception as exc:  # noqa: BLE001
        out["news"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    st.finish_receipt(rid, "ok", out, now=ctx.now())
    return out


# ---------------------------------------------------------------------------------------------------- eligibility
def eligibility(ctx: Context, day: dt.date, ciks: Iterable[str], *, live: bool = True) -> dict[str, Mapping[str, Any] | None]:
    """The universe row (or None) of each CIK for entry session `day`, fetching what it needs."""
    st = ctx.store
    want = sorted({c for c in ciks if c})
    out: dict[str, Mapping[str, Any] | None] = {}
    prior = C.previous(st, day, U.ADV_SESSIONS)
    if len(prior) < U.ADV_SESSIONS:
        return {c: None for c in want}
    cached = {r["cik"]: dict(r) for r in st.db.execute("SELECT * FROM universe WHERE day=?", (day.isoformat(),))}
    todo = [c for c in want if c not in cached]
    assets = ctx.assets(live)
    tickers = ctx.tickers_for(day)
    symbols = sorted({t for c in todo for t, _ in tickers.get(c, []) if U._listed(assets.get(t), live)})
    have = {r[0] for r in st.db.execute(
        "SELECT symbol FROM bars WHERE adj='raw' AND day=? GROUP BY symbol", (prior[-1].day.isoformat(),))}
    missing = [s for s in symbols if s not in have]
    if missing:
        U.fetch_daily_bars(st, ctx.gw, missing, prior[0].day, prior[-1].day, now=ctx.now())
    for cik in want:
        if cik in cached:
            out[cik] = cached[cik]
            continue
        ok = U.operating(st, ctx.sec, cik, day, now=ctx.now()) if tickers.get(cik) else False
        out[cik] = U.eligible(st, cik, day, tickers=tickers, assets=assets, operating_ok=ok, now=ctx.now(), live=live)
    return out


# ---------------------------------------------------------------------------------------------------- verdicts
def doc_verdict(ctx: Context, row: Mapping[str, Any], uni: Mapping[str, Any]) -> int | None:
    st = ctx.store
    if not row.get("text_sha") or (row.get("text_len") or 0) < 200:
        return None
    text = st.get_document(row["text_sha"]).decode("utf-8")
    user = V.render_doc(name=uni.get("name") or row.get("company") or "", ticker=uni["symbol"],
                        items=sorted(P.items_of(row)), accepted_at=S.parse_iso(row["accepted_at"]), text=text)
    got = V.ask(st, ctx.gw, f"8k:{row['accession']}", V.PROMPTS["doc"], user, now=ctx.now)
    return got["score"] if got and got["status"] == "ok" else None


def news_verdict(ctx: Context, row: Mapping[str, Any]) -> int | None:
    user = V.render_news(symbol=row["symbol"], created_at=S.parse_iso(row["created_at"]), source=row.get("source") or "",
                         headline=row.get("headline") or "", summary=row.get("summary") or "")
    got = V.ask(ctx.store, ctx.gw, f"news:{row['id']}", V.PROMPTS["news"], user, now=ctx.now)
    return got["score"] if got and got["status"] == "ok" else None


# ---------------------------------------------------------------------------------------------------- decisions
def decide_open(ctx: Context, day: dt.date, *, backfill_run: bool = False) -> dict[str, Any]:
    """Shadow intents for every open-entry program at session `day`'s open."""
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return {"skipped": "no session"}
    rid = st.start_receipt(f"decide-open:{day}", now=ctx.now())
    lo, hi = P.open_window(st, day)
    e8k = P.filings_in(st, "8-K", lo, hi)
    ins = P.ins_triggers(st, lo, hi)
    nlo, nhi = P.news_window(st, day)
    by_ticker = {t: cik for cik, rows in ctx.tickers_for(day).items() for t, _ in rows}
    articles = [a | {"cik": by_ticker.get(a["symbol"])} for a in P.news_in(st, nlo, nhi)]
    elig = eligibility(ctx, day, [r["cik"] for r in e8k] + [r["cik"] for r in ins] + [a["cik"] for a in articles if a["cik"]],
                       live=not backfill_run)
    scores: dict[str, int | None] = {}

    def verdict(row: Mapping[str, Any]) -> int | None:
        key = row.get("accession") or f"news:{row.get('id')}"
        if key not in scores:
            uni = elig.get(row.get("cik"))
            scores[key] = None if uni is None else (
                news_verdict(ctx, row) if "id" in row and "accession" not in row else doc_verdict(ctx, row, uni))
        return scores[key]

    def needs_verdict(prog: P.Program, row: Mapping[str, Any]) -> bool:
        """An eligible event of `prog`'s family that a verdict could exist for (an 8-K with TEXT >= 200 characters, or a
        news article whose symbol is the eligible one)."""
        uni = elig.get(row.get("cik"))
        if uni is None:
            return False
        if prog.family == "news":
            return uni["symbol"] == row.get("symbol")
        items = P.items_of(row)
        if prog.family == "ern" and not items & P.ERN_ITEMS:
            return False
        if prog.family == "8k" and (not items & P.OTHER_ITEMS or items & P.ERN_ITEMS):
            return False
        return bool(row.get("text_sha")) and (row.get("text_len") or 0) >= 200

    def pending(prog: P.Program, rows: list[Mapping[str, Any]]) -> int:
        """How many of `prog`'s eligible events still have no stored verdict (PREREG section 4: READ events wait)."""
        if not (prog.reads or prog.family == "news"):
            return 0
        prompt = V.PROMPTS["news" if prog.family == "news" else "doc"]
        missing = 0
        for row in rows:
            if not needs_verdict(prog, row):
                continue
            verdict(row)
            event = f"news:{row['id']}" if prog.family == "news" else f"8k:{row['accession']}"
            if V.stored(st, event, prompt) is None:
                missing += 1
        return missing

    out: dict[str, Any] = {"pending": {}}
    why = "backfill" if backfill_run else None
    for prog in P.PROGRAMS:
        if prog.entry_at != "open":
            continue
        rows = {"ern": e8k, "8k": e8k, "ins": ins, "news": articles}.get(prog.family, [])
        waiting = pending(prog, rows)
        if waiting:
            out["pending"][prog.id] = waiting   # decided by a later pass, once every verdict is stored
            continue
        cands = P.select(prog, rows, eligible=lambda c: elig.get(c), verdict=verdict)
        out[prog.id] = P.write_intents(st, prog, day, cands, decided_at=session.open_decide, why=why)
    out["events"] = {"8-K": len(e8k), "f4_triggers": len(ins), "news": len(articles),
                     "eligible": sum(1 for v in elig.values() if v)}
    st.finish_receipt(rid, "pending" if out["pending"] else "ok", out, now=ctx.now())
    return out


def _last_close_before(ctx: Context, symbol: str, accepted: dt.datetime) -> float | None:
    st = ctx.store
    rows = st.db.execute("SELECT day, close_at FROM sessions WHERE close_at<? ORDER BY day DESC LIMIT 1", (S.iso(accepted),))
    row = rows.fetchone()
    if row is None:
        return None
    day = dt.date.fromisoformat(row["day"])
    got = U.bars(st, symbol, [day], "raw")
    if day.isoformat() not in got:
        U.fetch_daily_bars(st, ctx.gw, [symbol], day, day, now=ctx.now())
        got = U.bars(st, symbol, [day], "raw")
    bar = got.get(day.isoformat())
    return float(bar["c"]) if bar and bar.get("c") else None


def _mark_1530(ctx: Context, symbol: str, day: dt.date) -> float | None:
    st = ctx.store
    have = st.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label='1530'", (symbol, day.isoformat())).fetchone()
    if have is not None:
        return have["px"]
    session = C.session(st, day)
    start = session.open_at
    end = session.at(dt.time(15, 30)) if not session.early else session.close_at - dt.timedelta(minutes=30)
    if ctx.now() < end + U.SIP_DELAY:
        return None
    page = ctx.gw.get_json("/v1/alpaca/v2/stocks/bars", {"symbols": symbol, "timeframe": "1Min", "start": S.iso(start),
                                                         "end": S.iso(end), "feed": "sip", "adjustment": "raw",
                                                         "limit": 10000})
    rows = [b for b in ((page or {}).get("bars") or {}).get(symbol, []) if S.parse_iso(b["t"]) + dt.timedelta(minutes=1) <= end]
    if not rows:
        return None
    last = rows[-1]
    st.db.execute("INSERT OR REPLACE INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, '1530', ?, ?, "
                  "'sip-1min', ?)", (symbol, day.isoformat(), float(last["c"]), last["t"], S.iso(ctx.now())))
    return float(last["c"])


def decide_close(ctx: Context, day: dt.date, *, backfill_run: bool = False) -> dict[str, Any]:
    """Shadow intents for C1 at session `day`'s close."""
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return {"skipped": "no session"}
    rid = st.start_receipt(f"decide-close:{day}", now=ctx.now())
    lo, hi = P.close_window(st, day)
    e8k = P.filings_in(st, "8-K", lo, hi)
    elig = eligibility(ctx, day, [r["cik"] for r in e8k if "2.02" in P.items_of(r)], live=not backfill_run)

    def reaction(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
        base = _last_close_before(ctx, uni["symbol"], S.parse_iso(row["accepted_at"]))
        mark = _mark_1530(ctx, uni["symbol"], day)
        return None if not base or mark is None else mark / base

    prog = P.BY_ID["EVL-ERN-REACT-C1"]
    cands = P.select(prog, e8k, eligible=lambda c: elig.get(c), verdict=lambda r: None, reaction=reaction)
    out = {prog.id: P.write_intents(st, prog, day, cands, decided_at=session.close_decide,
                                    why="backfill" if backfill_run else None),
           "events": {"8-K": len(e8k), "eligible": sum(1 for v in elig.values() if v)}}
    st.finish_receipt(rid, "ok", out, now=ctx.now())
    return out


__all__ = ["Context", "record_pass", "backfill", "eligibility", "decide_open", "decide_close"]

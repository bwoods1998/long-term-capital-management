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
from . import screen as SN
from . import store as S
from . import universe as U
from . import verdicts as V

#: A DECISION RUN THIS SOON AFTER ITS SCHEDULED TIME IS LIVE (PREREG-EVL-1 section 2's live rule: Alpaca's
#: `status=active` and `tradable: true`); later, it is a backfill (`status=all`, the previous session's closing-print
#: exchange). Each run's rule fixes its session's eligibility results for good, so the choice is the judge's, defined
#: once here, behind league/ci.py's wall (release 1019b's third review): the House's lane (league/events/house.py) and
#: the CLI's catchup take it from `live_run`.
LIVE_WITHIN = S.LEGACY_LIVE_WITHIN


def live_run(scheduled: dt.datetime, now: dt.datetime) -> bool:
    """Whether a decision of scheduled time `scheduled` run at `now` (or its verdicts asked ahead of it, `ask_only`,
    from 07:30 ET) is LIVE: at most `LIVE_WITHIN` after its time; else it is a backfill (`backfill_run`)."""
    return now <= scheduled + LIVE_WITHIN


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
def eligibility(ctx: Context, day: dt.date, ciks: Iterable[str], *, live: bool = True, kind: str | None = None,
                stored: Mapping[str, str | None] | None = None) -> dict[str, Mapping[str, Any] | None]:
    """The universe row (or None) of each CIK for entry session `day`, ONCE PER (ENTRY SESSION, CIK), BY THE RULE THAT
    MADE IT (release 1019b's second review; league/events/universe.py): a LIVE decision (`live`) reads the live rule's
    result and checks under the live rule (status=active, tradable) a CIK with none, a CIK the backfill rule judged
    first included; a BACKFILL decision reads any result of the session (eligible only when none is ineligible,
    `universe.combined`) and checks under the backfill rule (status=all, the previous session's closing-print exchange)
    only a CIK no decision has judged; on a session decided before the results were kept, the desktop's live refusals
    (A67's markers, kept by the migration) stand, and on such a session without them a CIK the session's first live run
    of either kind already judged (`stored` {cik: when its first event here was fetched}, `universe.seen_live`; `kind`
    the asking decision's, "open" | "close") is ineligible as it found. Every check's result is kept, eligible or not
    (`universe.record_result`), as it is made. It fetches what it needs; an empty asset list is unreadable (raised, so
    no result is kept from it)."""
    st = ctx.store
    want = sorted({c for c in ciks if c})
    out: dict[str, Mapping[str, Any] | None] = {}
    prior = C.previous(st, day, U.ADV_SESSIONS)
    if len(prior) < U.ADV_SESSIONS:
        return {c: None for c in want}
    rule = S.LIVE_RULE if live else S.BACKFILL_RULE
    known = U.results(st, day)
    todo = []
    for cik in want:
        have = known.get(cik) or {}
        if live and S.LIVE_RULE in have:
            out[cik] = have[S.LIVE_RULE]
        elif not live and have:
            out[cik] = U.combined(have)
        else:
            todo.append(cik)
    if not live and todo and kind is not None:
        judged = U.seen_live(st, day, kind, {c: (stored or {}).get(c) for c in todo})
        for cik in sorted(judged):
            U.record_result(st, day, cik, S.LIVE_RULE, None, now=ctx.now())
            out[cik] = None
        todo = [c for c in todo if c not in judged]
    if not todo:
        return out
    assets = ctx.assets(live)
    if not assets:
        raise RuntimeError("Alpaca's asset list came back empty: no eligibility is decided on it")
    tickers = ctx.tickers_for(day)
    symbols = sorted({t for c in todo for t, _ in tickers.get(c, []) if U._listed(assets.get(t), live)})
    # EVERY ONE OF THE 20 SESSIONS' BARS, NOT ONLY THE LAST (release 1019c's review): a symbol judged for a LATER entry
    # session first has the last of these sessions' bars and not the first, so a check of the last alone fetched
    # nothing and the issuer read as ineligible here (a re-decision of an older session, PREREG-EVL-4's rows decided
    # by themselves). A symbol with all of them stored is not fetched again, as before.
    window = [x.day for x in prior]
    missing = [s for s in symbols if len(U.bars(st, s, window, "raw")) < len(window)]
    if missing:
        U.fetch_daily_bars(st, ctx.gw, missing, prior[0].day, prior[-1].day, now=ctx.now())
    for cik in todo:
        ok = U.operating(st, ctx.sec, cik, day, now=ctx.now()) if tickers.get(cik) else False
        listing = None if live else (lambda sym, before=prior[-1]: U.closing_print_exchange(ctx.gw, sym, before))
        row = U.eligible(st, cik, day, tickers=tickers, assets=assets, operating_ok=ok, now=ctx.now(), live=live,
                         listing=listing)
        U.record_result(st, day, cik, rule, row, now=ctx.now())
        out[cik] = row
    return out


def _first_fetched(st: S.Store, rows: Iterable[Mapping[str, Any]]) -> dict[str, str | None]:
    """{cik: the earliest time one of its rows was FETCHED} (`eligibility`'s `stored`, read by `universe.seen_live`):
    a news article's `received_at` (an article is stored whole when it is read); a filing's document's first store
    time (`documents.stored_at` of its `raw_sha`), never before the filing was first listed (`received_at`), and its
    `received_at` when no document time is kept. Release 1019b's third review: `received_at` is a filing's LISTING
    time, so a filing listed before a live run and fetched after it read as seen by that run."""
    out: dict[str, str | None] = {}
    for row in rows:
        cik, at = row.get("cik"), row.get("received_at")
        if not cik or not at:
            continue
        when = S.parse_iso(str(at))
        if row.get("accession") and row.get("raw_sha"):
            doc = st.db.execute("SELECT stored_at FROM documents WHERE sha=?", (str(row["raw_sha"]),)).fetchone()
            if doc is not None and doc["stored_at"]:
                when = max(when, S.parse_iso(str(doc["stored_at"])))
        if out.get(str(cik)) is None or when < S.parse_iso(str(out[str(cik)])):
            out[str(cik)] = S.iso(when)
    return out


def _key(prog: P.Program) -> str:
    """A decision summary's key: the id for version 1 (unchanged), `id@vN` for a later version (PREREG-EVL-3). The judge
    reads a receipt by the same key (league/events/screen.py `program_key`, `names`), defined there once."""
    return SN.program_key(prog.id, prog.version)


#: The families whose verdicts the OPEN decision of the same session asks, never their own close decision (PREREG-EVL-4:
#: EVL-NEWSPM-READ-ON and its control read the PROMPT-NEWS verdicts EVL-NEWS-READ-O1 asks for its open decision of D).
OPEN_ASKED = ("news-pm",)


def waits_on_open(out: Mapping[str, Any]) -> bool:
    """Whether a close decision's summary (`decide_close`'s, `ask_only` or not) is pending for a program that waits on
    verdicts only the OPEN decision of the same session asks (`OPEN_ASKED`): the House's lane then asks that open
    decision's own verdicts (`decide_open` with `ask_only`), so such a wait is never left to the hourly re-decision."""
    for key in (out.get("pending") or {}):
        pid, _, version = str(key).partition("@v")
        try:
            prog = P.BY_KEY.get((pid, int(version) if version else 1))
        except ValueError:
            continue
        if prog is not None and prog.family in OPEN_ASKED:
            return True
    return False


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
def decide_open(ctx: Context, day: dt.date, *, backfill_run: bool = False, ask_only: bool = False) -> dict[str, Any]:
    """Shadow intents for every open-entry program at session `day`'s open.

    `ask_only`: the decision's own windows, eligibility and verdict asks, and nothing else: no intent and no receipt is
    written, and `pending` counts each reading program's eligible events still without a stored verdict. The House's
    event lane (league/events/house.py) asks a session's verdicts this way from 07:30 ET, so the decision finds them
    stored; the verdicts and universe rows it stores are the very ones the decision reads."""
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return {"skipped": "no session"}
    rid = None if ask_only else st.start_receipt(f"decide-open:{day}", now=ctx.now())
    lo, hi = P.open_window(st, day)
    e8k = P.filings_in(st, "8-K", lo, hi)
    ins = P.ins_triggers(st, lo, hi)
    buys = P.ins_buys(st, lo, hi)
    nlo, nhi = P.news_window(st, day)
    by_ticker = {t: cik for cik, rows in ctx.tickers_for(day).items() for t, _ in rows}
    articles = [a | {"cik": by_ticker.get(a["symbol"])} for a in P.news_in(st, nlo, nhi)]
    elig = eligibility(ctx, day, [r["cik"] for r in e8k] + [r["cik"] for r in ins] + [r["cik"] for r in buys]
                       + [a["cik"] for a in articles if a["cik"]], live=not backfill_run, kind="open",
                       stored=_first_fetched(st, [*e8k, *ins, *buys, *articles]))
    scores: dict[str, int | None] = {}

    def verdict(row: Mapping[str, Any]) -> int | None:
        key = row.get("accession") or f"news:{row.get('id')}"
        if key not in scores:
            uni = elig.get(row.get("cik"))
            scores[key] = None if uni is None else (
                news_verdict(ctx, row) if "id" in row and "accession" not in row else doc_verdict(ctx, row, uni))
        return scores[key]

    def guidance(row: Mapping[str, Any]) -> str | None:
        got = V.stored(st, f"8k:{row['accession']}", V.PROMPTS["doc"]) if row.get("accession") else None
        return got["guidance"] if got and got["status"] == "ok" else None

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
        rows = {"ern": e8k, "8k": e8k, "ins": ins, "ins-buy": buys, "news": articles}.get(prog.family, [])
        rows = [r for r in rows if S.parse_iso(r["knowable_at"]) > prog.registered_at]
        waiting = pending(prog, rows)
        if ask_only:
            if waiting:
                out["pending"][_key(prog)] = waiting   # version 1 and version 2 of one id count apart
            continue
        if waiting:
            out["pending"][_key(prog)] = waiting   # decided by a later pass, once every verdict is stored
            continue
        cands = P.select(prog, rows, eligible=lambda c: elig.get(c), verdict=verdict, guidance=guidance)
        out[_key(prog)] = P.write_intents(st, prog, day, cands, decided_at=session.open_decide, why=why)
    out["events"] = {"8-K": len(e8k), "f4_triggers": len(ins), "f4_buys": len(buys), "news": len(articles),
                     "eligible": sum(1 for v in elig.values() if v)}
    if rid is not None:
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


#: THE T29 MINUTES OF PREREG-EVL-4's EVL-8K-REACT-ON, read together (its F8K(D) names run to about 50 a session, after
#: the earlier rows' own reads at 15:47 ET): this many names a request, page by page. Each name's mark is exactly the one
#: `_mark_1530` reads alone (the close of the last SIP minute bar ending by 15:30 ET, 30 minutes before an early close);
#: a name with no such bar in the answer gets no mark here and is read alone by `_mark_1530`, as every other row's is.
MARK_BATCH = 100
MARK_PAGES = 40


def _marks_1530(ctx: Context, symbols: Iterable[str], day: dt.date) -> int:
    """The 15:30 marks (label '1530') of `symbols` on session `day` that the store does not hold yet, read in batched
    SIP 1-minute requests (`MARK_BATCH` names each): the same rule and the same row `_mark_1530` writes. Returns how many
    marks were stored. Nothing is read before the bar is on the Basic plan's tape (`U.SIP_DELAY` after 15:30 ET)."""
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return 0
    end = session.at(dt.time(15, 30)) if not session.early else session.close_at - dt.timedelta(minutes=30)
    if ctx.now() < end + U.SIP_DELAY:
        return 0
    have = {str(r[0]) for r in st.db.execute("SELECT symbol FROM marks WHERE day=? AND label='1530'", (day.isoformat(),))}
    names = sorted({str(x) for x in symbols if x} - have)
    stored = 0
    for i in range(0, len(names), MARK_BATCH):
        chunk = names[i:i + MARK_BATCH]
        got: dict[str, list[Mapping[str, Any]]] = {}
        token = None
        for _ in range(MARK_PAGES):
            page = ctx.gw.get_json("/v1/alpaca/v2/stocks/bars", {"symbols": ",".join(chunk), "timeframe": "1Min",
                                                                 "start": S.iso(session.open_at), "end": S.iso(end),
                                                                 "feed": "sip", "adjustment": "raw", "limit": 10000,
                                                                 "page_token": token}) or {}
            for sym, bars in (page.get("bars") or {}).items():
                got.setdefault(str(sym), []).extend(bars or [])
            token = page.get("next_page_token")
            if not token:
                break
        for sym in chunk:
            rows = [b for b in got.get(sym, []) if S.parse_iso(b["t"]) + dt.timedelta(minutes=1) <= end]
            if not rows:
                continue
            last = rows[-1]
            st.db.execute("INSERT OR REPLACE INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, '1530', "
                          "?, ?, 'sip-1min', ?)", (sym, day.isoformat(), float(last["c"]), last["t"], S.iso(ctx.now())))
            stored += 1
    return stored


def _rows_4(ctx: Context, day: dt.date, window: tuple[dt.datetime, dt.datetime], by_ticker: Mapping[str, str],
            elig: Mapping[str, Mapping[str, Any] | None], *, live: bool) -> dict[str, Any]:
    """PREREG-EVL-4's rows of the close decision of D (its section 1): every fetched 8-K of D's close window, the
    day-news window's articles and PM(D)'s (each with its issuer's CIK by SEC's tickers), ALL READ WITH NO REGISTRATION
    FLOOR (the adversarial check's build note (i)); EXCLUDED on D and the F8K(D) skip (`programs.close_rows_4`); and the
    eligibility its rows read: the decision's own (`elig`, the earlier rows', untouched), with, judged here once per
    (entry session, CIK) by the decision's rule as every other result, the issuers of the day-news window not judged yet
    (DAY(D) reads each article's eligible ticker) and those of these rows' EVENTS (knowable after the registration time,
    not EXCLUDED, and for PM(D) with no F8K(D) filing) not judged yet. An issuer EXCLUDED or skipped is never judged for
    them. Returns {rows: {family: rows}, elig, excluded, filed, counts}."""
    st = ctx.store
    all8k = P.filings_window(st, "8-K", *window)

    def with_cik(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [dict(a) | {"cik": by_ticker.get(a["symbol"])} for a in rows]
    day_all = with_cik(P.news_rows(st, *P.day_news_window(st, day)))
    pm_all = with_cik(P.news_rows(st, *P.news_window(st, day)))
    table: dict[str, Mapping[str, Any] | None] = dict(elig)
    need = sorted({str(a["cik"]) for a in day_all if a.get("cik")} - set(table))
    if need:
        table.update(eligibility(ctx, day, need, live=live, kind="close",
                                 stored=_first_fetched(st, [a for a in day_all if a.get("cik") in need])))

    def symbol_of(cik: str) -> str | None:
        uni = table.get(cik)
        return None if uni is None else uni.get("symbol")
    rows = P.close_rows_4(all8k, day_all, pm_all, symbol_of)
    times = [p.registered_at for p in P.PROGRAMS if p.family in P.CLOSE_FAMILIES_4]
    events = [r for family in ("8k-day", "news-pm") for r in rows[family]
              if times and r.get("cik") and S.parse_iso(r["knowable_at"]) > min(times)]
    need = sorted({str(r["cik"]) for r in events} - set(table))
    if need:
        table.update(eligibility(ctx, day, need, live=live, kind="close",
                                 stored=_first_fetched(st, [r for r in events if str(r["cik"]) in need])))
    excluded = P.excluded(all8k, day_all, symbol_of)
    filed = P.f8k_ciks(all8k)
    counts = {"f8k": len(P.family_8k(all8k)), "pm": len(pm_all), "excluded": len(excluded),
              "eligible_4": sum(1 for c in {str(r["cik"]) for r in events} if table.get(c))}
    return {"rows": rows, "elig": table, "excluded": excluded, "filed": filed, "counts": counts}


def _skip_excluded(st: S.Store, day: dt.date, excluded: set[str], filed: set[str]) -> int:
    """THE ADVERSARIAL CHECK'S BUILD NOTE (ii) for PREREG-EVL-4's rows: a re-decision of D's close marks an intent of
    those rows for D that has not settled (planned or entered) `skipped:excluded` when a row stored after the intent was
    written now puts its issuer in EXCLUDED on D (for EVL-NEWSPM-READ-ON and its control, also in the F8K(D) skip): the
    shadow is the rule over every event knowable at the decision time, whenever the recorder stored it. A settled intent
    is never changed (its record is final; store.py's forward-only status); one skipped already stays as it is. Returns
    how many moved."""
    moves: list[tuple[P.Program, str, str]] = []
    for prog in P.PROGRAMS:
        if prog.family not in P.CLOSE_FAMILIES_4 or prog.entry_at != "close":
            continue
        drop = (excluded | filed) if prog.family == "news-pm" else excluded
        if not drop:
            continue
        for r in st.db.execute("SELECT event, cik FROM intents WHERE program=? AND version=? AND entry_day=? AND status IN "
                               "('planned', 'entered')", (prog.id, prog.version, day.isoformat())).fetchall():
            if r["cik"] and str(r["cik"]) in drop:
                why = ("EXCLUDED on D (ERN(D) or DAY(D)), by a row stored after the decision" if str(r["cik"]) in excluded
                       else "an F8K(D) filing of the issuer, stored after the decision")
                moves.append((prog, str(r["event"]), why))
    if not moves:
        return 0
    moved = 0
    with st.tx():
        for prog, event, why in moves:
            moved += bool(st.move_intent(prog.id, prog.version, event, "skipped:excluded", why))
    return moved


def decide_close(ctx: Context, day: dt.date, *, backfill_run: bool = False, ask_only: bool = False,
                 evl4_only: bool = False) -> dict[str, Any]:
    """Shadow intents for every close-entry program at session `day`'s close: C1 (PREREG-EVL-1) and PREREG-EVL-2's
    REACT-ON, REACT-READ-C1 and the day-news programs (NEWS-READ-ON, its control, NEWS-REACT-ON), then PREREG-EVL-4's
    (EVL-8K-REACT-ON, EVL-8K-READ-ON, EVL-NEWSPM-READ-ON and their two controls: `_rows_4`).

    The earlier rows read exactly what they read before PREREG-EVL-4 (their windows, their eligibility call, their
    verdicts, in the same order); PREREG-EVL-4's rows come after them, with their own reads: every 8-K of the close window
    (F8K(D) and ERN(D)), the day-news window (DAY(D)) and PM(D), with no registration floor for the sets that skip;
    their PROMPT-DOC verdicts asked as EVL-8K-READ-O1's own (one verdict an event, stored once: a filing knowable during
    D is asked during D's session by `ask_only`), their PROMPT-NEWS verdicts read only, never asked (EVL-NEWS-READ-O1
    asks them for its open decision of D: the adversarial check's build note (iii)); their READ events wait for their
    verdicts. A re-decision marks such a row's unsettled intent `skipped:excluded` when a row stored later puts its
    issuer in EXCLUDED or the F8K(D) skip (`_skip_excluded`, build note (ii)).

    `ask_only`: as decide_open's (the verdicts the close decision will read, asked during the session: no intent, no
    receipt, and no reaction, whose 15:29 bar is not on the tape before the decision).

    `evl4_only` (release 1019c's review): PREREG-EVL-4'S ROWS DECIDED BY THEMSELVES, for a close a release without them
    decided (league/events/screen.py `made_without`; the House's lane and the CLI's catchup run it once, as a backfill):
    the decision's reads and its eligibility call exactly as the whole decision makes them, then their rows as above
    (reads, verdicts, `_skip_excluded`, intents); NO EARLIER ROW'S verdict is asked or intent written, so a close final
    for an earlier program gains nothing. Its receipt is `decide-close-evl4:<day>` (screen.FOUR_KIND), which the judge
    reads for their programs only (`screen.final_until`): the session's `decide-close:<day>` receipts, which the House's
    lane, its book and the judge read for every earlier row, are left as they are."""
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return {"skipped": "no session"}
    job = f"decide-{SN.FOUR_KIND if evl4_only else 'close'}:{day}"
    rid = None if ask_only else st.start_receipt(job, now=ctx.now())
    lo, hi = P.close_window(st, day)
    e8k = [r for r in P.filings_in(st, "8-K", lo, hi) if "2.02" in P.items_of(r)]
    dlo, dhi = P.day_news_window(st, day)
    by_ticker = {t: cik for cik, rows in ctx.tickers_for(day).items() for t, _ in rows}
    articles = [a | {"cik": by_ticker.get(a["symbol"])} for a in P.news_in(st, dlo, dhi)
                if S.parse_iso(a["knowable_at"]) > S.parse_iso(P.REGISTERED_AT_2)]
    elig = eligibility(ctx, day, [r["cik"] for r in e8k] + [a["cik"] for a in articles if a["cik"]],
                       live=not backfill_run, kind="close", stored=_first_fetched(st, [*e8k, *articles]))
    four: dict[str, Any] = {}               # PREREG-EVL-4's reads, made once the earlier rows are decided (`_rows_4`)
    elig4: dict[str, Mapping[str, Any] | None] = {}
    scores: dict[str, int | None] = {}

    def verdict(row: Mapping[str, Any]) -> int | None:
        key = row.get("accession") or f"news:{row.get('id')}"
        if key not in scores:
            uni = elig.get(row.get("cik"))
            scores[key] = None if uni is None else (
                news_verdict(ctx, row) if "accession" not in row else doc_verdict(ctx, row, uni))
        return scores[key]

    scores4: dict[str, int | None] = {}

    def verdict4(row: Mapping[str, Any]) -> int | None:
        """PREREG-EVL-4's 8-K rows: the PROMPT-DOC verdict of `8k:<accession>`, EVL-8K-READ-O1's own (asked once, stored
        once, the first stored answer final), for an issuer eligible on D."""
        key = str(row["accession"])
        if key not in scores4:
            uni = elig4.get(row.get("cik"))
            scores4[key] = None if uni is None else doc_verdict(ctx, row, uni)
        return scores4[key]

    def stored_news(row: Mapping[str, Any]) -> int | None:
        """EVL-NEWSPM-READ-ON and its control: the STORED PROMPT-NEWS verdict of `news:<id>` (the one EVL-NEWS-READ-O1
        asks for its open decision of D), read only; this row asks none of its own."""
        got = V.stored(st, f"news:{row['id']}", V.PROMPTS["news"])
        return got["score"] if got and got["status"] == "ok" else None

    def reaction(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
        # an 8-K's base is C1's (the last close before the acceptance time); an article's, before its knowable time
        since = row["accepted_at"] if row.get("accession") else row["knowable_at"]
        base = _last_close_before(ctx, uni["symbol"], S.parse_iso(since))
        mark = _mark_1530(ctx, uni["symbol"], day)
        return None if not base or mark is None else mark / base

    def pending(prog: P.Program, rows: list[Mapping[str, Any]]) -> int:
        """How many of `prog`'s eligible events still have no stored verdict (PREREG-EVL-1 section 4: READ events
        wait), counted only for programs that read or rank by a verdict."""
        if not (prog.reads or prog.family == "news-day"):
            return 0
        news = prog.family == "news-day"
        prompt = V.PROMPTS["news" if news else "doc"]
        missing = 0
        for row in rows:
            uni = elig.get(row.get("cik"))
            if uni is None:
                continue
            if news and uni["symbol"] != row.get("symbol"):
                continue
            if not news and not (row.get("text_sha") and (row.get("text_len") or 0) >= 200):
                continue
            verdict(row)
            event = f"news:{row['id']}" if news else f"8k:{row['accession']}"
            if V.stored(st, event, prompt) is None:
                missing += 1
        return missing

    def pending4(prog: P.Program, rows: list[Mapping[str, Any]]) -> int:
        """PREREG-EVL-4's READ events wait for their verdicts (the shadow rule), and its news control for the stored
        scores it ranks by: how many of `prog`'s eligible events have none stored yet. The 8-K rows' PROMPT-DOC is asked
        here (TEXT >= 200 characters: a shorter TEXT has no verdict and is not taken); PM(D)'s PROMPT-NEWS is never
        asked here (it waits for EVL-NEWS-READ-O1's ask)."""
        news = prog.family == "news-pm"
        if not (prog.reads or news):
            return 0
        prompt = V.PROMPTS["news" if news else "doc"]
        missing = 0
        for row in rows:
            uni = elig4.get(row.get("cik"))
            if uni is None:
                continue
            if news and uni["symbol"] != row.get("symbol"):
                continue
            if not news and not (row.get("text_sha") and (row.get("text_len") or 0) >= 200):
                continue
            if not news:
                verdict4(row)
            event = f"news:{row['id']}" if news else f"8k:{row['accession']}"
            if V.stored(st, event, prompt) is None:
                missing += 1
        return missing

    out: dict[str, Any] = {"pending": {}}
    why = "backfill" if backfill_run else None
    # THE EARLIER ROWS FIRST, exactly as before PREREG-EVL-4 (their reads, verdicts and intents), then PREREG-EVL-4's,
    # whose own reads come after them: a failure or a time bound in those never holds an earlier row's decision.
    for mine in (False, True):
        if evl4_only and not mine:
            continue        # (PREREG-EVL-4's rows by themselves: no earlier row is decided again)
        if mine:
            four.update(_rows_4(ctx, day, (lo, hi), by_ticker, elig, live=not backfill_run))
            elig4.update(four["elig"])
            if not ask_only:
                late = _skip_excluded(st, day, four["excluded"], four["filed"])
                if late:
                    out["skipped_excluded"] = late
        for prog in P.PROGRAMS:
            if prog.entry_at != "close" or (prog.family in P.CLOSE_FAMILIES_4) != mine:
                continue
            if mine:
                rows, table, wait = four["rows"][prog.family], elig4, pending4
                read = stored_news if prog.family == "news-pm" else verdict4
            else:
                rows = {"ern-react": e8k, "news-day": articles, "news-react": articles}.get(prog.family, [])
                table, wait, read = elig, pending, verdict
            rows = [r for r in rows if S.parse_iso(r["knowable_at"]) > prog.registered_at]
            waiting = wait(prog, rows)
            if ask_only:
                if waiting:
                    out["pending"][_key(prog)] = waiting   # version 1 and version 2 of one id count apart
                continue
            if waiting:
                out["pending"][_key(prog)] = waiting   # decided by a later pass, once every verdict is stored
                continue
            if prog.family == "8k-react":
                _marks_1530(ctx, [str(table[r["cik"]]["symbol"]) for r in rows if table.get(r.get("cik"))], day)
            cands = P.select(prog, rows, eligible=lambda c, table=table: table.get(c), verdict=read, reaction=reaction)
            out[_key(prog)] = P.write_intents(st, prog, day, cands, decided_at=session.close_decide, why=why)
    out["events"] = {"8-K": len(e8k), "day_news": len(articles), "eligible": sum(1 for v in elig.values() if v),
                     **four["counts"]}
    if rid is not None:
        st.finish_receipt(rid, "pending" if out["pending"] else "ok", out, now=ctx.now())
    return out


__all__ = ["Context", "record_pass", "backfill", "eligibility", "decide_open", "decide_close", "LIVE_WITHIN", "live_run",
           "waits_on_open"]

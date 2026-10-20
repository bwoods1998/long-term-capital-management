"""The event lane's passes: record, backfill, decide at the open, decide at the close (shadow).

Each pass writes a receipt; a decision's carries THE VERDICT TALLY, `verdicts: {needed, answered}`: the distinct
(event, prompt) verdicts its reading programs need, open-entry and close-entry alike, and how many have a stored answer
(release 1019c: the House's stall job reads it, league/ops/evl_health.py `evl_verdicts`). Decisions are recorded at
their SCHEDULED time (09:15 ET open, close - 14 min) whether
they ran live or as a backfill (`why` says which): a backfilled decision uses only data that was knowable at the
scheduled time (filings by knowable time, the universe from the sessions before D, C1's 15:30 minute bar and the
last daily close before the acceptance). Verdicts are asked only for eligible events of the reading programs.
A decision made again (release 1019c, `_scope`), inside the House's re-decision window or outside it (a backfill after
an outage, a decision pending on verdicts, the CLI's catchup), writes intents for every program but those of a GROUP
over whose session a look of the group is written (the group: every version of a program's id, its control, and every
version of every READ program of that control; A66's owed purpose, A74 (5)); the summary's `kept` names each program it
left as it was, why, and the events it left out of that program's record (`_left_out`), which the daily report counts.
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
    have = {r[0] for r in st.db.execute(
        "SELECT symbol FROM bars WHERE adj='raw' AND day=? GROUP BY symbol", (prior[-1].day.isoformat(),))}
    missing = [s for s in symbols if s not in have]
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
    """A decision summary's key: the id for version 1 (unchanged), `id@vN` for a later version (PREREG-EVL-3)."""
    return prog.id if prog.version == 1 else f"{prog.id}@v{prog.version}"


# ---------------------------------------------------------------------------------------------------- re-decisions
def _group(program: str) -> frozenset[str]:
    """THE IDS A WRITTEN LOOK FREEZES TOGETHER (release 1019c's judges review): the look's id (every version: a
    version 2 takes its version 1's events word for word, PREREG-EVL-3 section 1), its control (the look read the
    control's record), and every READ program of that control (so each one's comparison with the control stays even);
    a control likewise, from its side. An id with no control and none of its own is its own group."""
    from . import screen as SN

    control = SN.CONTROLS.get(program) or (program if program in SN.CONTROLS.values() else None)
    if control is None:
        return frozenset({program})
    return frozenset({control, *(read for read, of in SN.CONTROLS.items() if of == control)})


def _scope(st: S.Store, kind: str, day: dt.date, now: dt.datetime) -> Callable[[P.Program], dict[str, Any] | None]:
    """WHAT A DECISION OF SESSION `day` MAY WRITE AGAIN (release 1019c): `kept(prog)` is why it writes (and asks)
    nothing for `prog` ({"why", "look"}), None when it decides it as before. A66's owed purpose, "a late-stored event
    can never land under a look already written", is kept by ONE rule:

    - A WRITTEN LOOK FREEZES ITS GROUP (A74 (5); A66's purpose, which A69's fast path reaches inside the window: it can
      make a close final while the House still decides it again every hour): once a look of any version of a program of
      the group (`_group`) is written as of the exit of this session's intents of that program or later, every program
      of the group is decided again for nothing, inside the window and out, pending or not (a kept run writes no
      `pending` for it, so its session is made, A66's second rule). The as-of date, the record a look read and the look
      stay the same; v1 and v2 keep the same events, and every READ program's control the same blocks.

    Every other program is decided whole, whichever session and whoever asks: the House's hourly re-decision, a
    decision pending on verdicts, the daily-index backfill's (league/events/house.py `_backfill`, which A66's third
    rule makes a look wait for, whatever the session's age) and the CLI's catchup. A74 (6), which wrote again OUTSIDE
    the re-decision window only the programs the last finished receipt was pending on, is WITHDRAWN (release 1019c's
    judges review, its major; for the captain to record before the release deploys, and never live): it threw
    away the events a backfill brings after an outage of three sessions or more (PREREG-EVL-1 section 3: "an outage
    removes nothing"; backfilled events "are read afterwards and count"), split a READ program that was pending from
    its control, and hid the shadow's holding from real money's one position per issuer (A70 (14)); the group freeze
    alone keeps every written look's record as the look read it. (`now` is not read: the callers' signature stays.)
    Every program a decision keeps is in its summary's `kept`, with why and the events left out of its record
    (`_left_out`, written by the decision: PREREG-EVL-1 section 3's late share, which league/events/report.py counts);
    the shadow's earlier intents stand."""
    from .programs import BY_KEY

    exits: dict[int, dt.date] = {}
    frozen: dict[str, str] = {}     # program id -> the written look that freezes its group over `day`
    for row in st.db.execute("SELECT program, version, k, at FROM looks ORDER BY program, version, k"):
        program, version = str(row["program"]), int(row["version"])
        try:
            as_of: dt.date | None = S.parse_iso(str(row["at"])).astimezone(C.NY).date()
        except (TypeError, ValueError):
            as_of = None     # (an unreadable as-of: read as over every session)
        looked = BY_KEY.get((program, version))
        if as_of is not None:
            if looked is None:
                continue     # (no registered program: no group to freeze)
            sessions = looked.hold if looked.entry_at == "open" else looked.hold + 1
            if sessions not in exits:
                out = C.nth(st, day, sessions)
                exits[sessions] = out.day if out is not None else day
            if exits[sessions] > as_of:
                continue     # this session's intents exit after the look's close: it does not cover them
        name = (f"{program if version == 1 else f'{program}@v{version}'} look {row['k']} as of "
                f"{as_of.isoformat() if as_of else 'an unreadable close'}")
        for member in _group(program):
            frozen.setdefault(member, name)

    def kept(prog: P.Program) -> dict[str, Any] | None:
        look = frozen.get(prog.id)
        if look is not None:
            return {"why": f"a look of its group is written over this session ({look})", "look": look}
        return None
    return kept


def _left_out(st: S.Store, prog: P.Program, rows: list[Mapping[str, Any]], *,
              eligible: Callable[[str], Mapping[str, Any] | None],
              guidance: Callable[[Mapping[str, Any]], str | None] | None = None,
              reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None
              ) -> dict[str, list[str]]:
    """WHAT A DECISION THAT KEEPS `prog` LEAVES OUT OF ITS RECORD (release 1019c's judges review; PREREG-EVL-1 section
    3: an outage removes nothing, the late share is reported): `events`, the events of the decision's windows its rule
    takes on the verdicts and prices already stored and its record does not hold (no intent, planned or skipped);
    `unjudged`, those it would take only on a verdict or a price no one has stored yet (a kept program is never asked a
    verdict and never fetched a price: `reaction` reads stored prices only). `rows` are the windows' rows after its
    registration; nothing is written. The daily report counts both (league/events/report.py `kept_out`)."""
    def answer(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
        news = "accession" not in row
        return V.stored(st, f"news:{row['id']}" if news else f"8k:{row['accession']}",
                        V.PROMPTS["news" if news else "doc"])

    def open_(row: Mapping[str, Any]) -> bool:
        """No verdict stored, and one can still come (a doc verdict is asked only of a TEXT of >= 200 characters)."""
        return answer(row) is None and ("accession" not in row or (bool(row.get("text_sha"))
                                                                 and (row.get("text_len") or 0) >= 200))

    def score(row: Mapping[str, Any]) -> int | None:
        got = answer(row)
        return got["score"] if got and got["status"] == "ok" else None

    def hoped(row: Mapping[str, Any]) -> int | None:
        return P.TOP_SCORE if open_(row) else score(row)

    def hoped_guidance(row: Mapping[str, Any]) -> str | None:
        return "raised" if open_(row) else (guidance(row) if guidance is not None else None)

    def hoped_reaction(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
        got = reaction(row, uni) if reaction is not None else None
        return P.REACT_RATIO if got is None else got

    def held(event: str) -> bool:
        return st.db.execute("SELECT 1 FROM intents WHERE program=? AND version=? AND event=?",
                             (prog.id, prog.version, event)).fetchone() is not None

    taken = {c.event for c in P.select(prog, rows, eligible=eligible, verdict=score, reaction=reaction,
                                       guidance=guidance)}
    maybe = {c.event for c in P.select(prog, rows, eligible=eligible, verdict=hoped, reaction=hoped_reaction,
                                       guidance=hoped_guidance)}
    return {"events": sorted(e for e in taken if not held(e)),
            "unjudged": sorted(e for e in maybe - taken if not held(e))}


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

    needed: set[tuple[str, str]] = set()      # THE VERDICT TALLY (release 1019c): (event, prompt) every program needs,
    unanswered: set[tuple[str, str]] = set()  # and those still without a stored answer (the stall job's evl_verdicts)

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
            needed.add((event, prompt.sha))
            if V.stored(st, event, prompt) is None:
                missing += 1
                unanswered.add((event, prompt.sha))
        return missing

    out: dict[str, Any] = {"pending": {}}
    why = "backfill" if backfill_run else None
    kept = _scope(st, "open", day, ctx.now())
    later: list[tuple[P.Program, list[Mapping[str, Any]]]] = []
    for prog in P.PROGRAMS:
        if prog.entry_at != "open":
            continue
        rows = {"ern": e8k, "8k": e8k, "ins": ins, "ins-buy": buys, "news": articles}.get(prog.family, [])
        rows = [r for r in rows if S.parse_iso(r["knowable_at"]) > prog.registered_at]
        frozen = kept(prog)
        if frozen is not None:     # (A66 owed, a look of its group: its earlier intents stand)
            out.setdefault("kept", {})[_key(prog)] = frozen
            later.append((prog, rows))
            continue
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
    for prog, rows in [] if ask_only else later:     # (what each kept program leaves out, once this run's asks are in)
        out["kept"][_key(prog)] |= _left_out(st, prog, rows, eligible=lambda c: elig.get(c), guidance=guidance)
    out["events"] = {"8-K": len(e8k), "f4_triggers": len(ins), "f4_buys": len(buys), "news": len(articles),
                     "eligible": sum(1 for v in elig.values() if v)}
    out["verdicts"] = {"needed": len(needed), "answered": len(needed - unanswered)}
    if rid is not None:
        st.finish_receipt(rid, "pending" if out["pending"] else "ok", out, now=ctx.now())
    return out


def _last_close_before(ctx: Context, symbol: str, accepted: dt.datetime, *, fetch: bool = True) -> float | None:
    """The raw SIP daily close of the last session closed before `accepted`; `fetch` False: only as stored."""
    st = ctx.store
    rows = st.db.execute("SELECT day, close_at FROM sessions WHERE close_at<? ORDER BY day DESC LIMIT 1", (S.iso(accepted),))
    row = rows.fetchone()
    if row is None:
        return None
    day = dt.date.fromisoformat(row["day"])
    got = U.bars(st, symbol, [day], "raw")
    if day.isoformat() not in got and fetch:
        U.fetch_daily_bars(st, ctx.gw, [symbol], day, day, now=ctx.now())
        got = U.bars(st, symbol, [day], "raw")
    bar = got.get(day.isoformat())
    return float(bar["c"]) if bar and bar.get("c") else None


def _mark_1530(ctx: Context, symbol: str, day: dt.date, *, fetch: bool = True) -> float | None:
    """C1's 15:30 mark of `symbol` on `day` (the close of the last SIP minute bar ending at or before 15:30 ET), stored
    once read; `fetch` False: only as stored."""
    st = ctx.store
    have = st.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label='1530'", (symbol, day.isoformat())).fetchone()
    if have is not None:
        return have["px"]
    if not fetch:
        return None
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


def decide_close(ctx: Context, day: dt.date, *, backfill_run: bool = False, ask_only: bool = False) -> dict[str, Any]:
    """Shadow intents for every close-entry program at session `day`'s close: C1 (PREREG-EVL-1) and PREREG-EVL-2's
    REACT-ON, REACT-READ-C1 and the day-news programs (NEWS-READ-ON, its control, NEWS-REACT-ON).

    `ask_only`: as decide_open's (the verdicts the close decision will read, asked during the session: no intent, no
    receipt, and no reaction, whose 15:29 bar is not on the tape before the decision)."""
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return {"skipped": "no session"}
    rid = None if ask_only else st.start_receipt(f"decide-close:{day}", now=ctx.now())
    lo, hi = P.close_window(st, day)
    e8k = [r for r in P.filings_in(st, "8-K", lo, hi) if "2.02" in P.items_of(r)]
    dlo, dhi = P.day_news_window(st, day)
    by_ticker = {t: cik for cik, rows in ctx.tickers_for(day).items() for t, _ in rows}
    articles = [a | {"cik": by_ticker.get(a["symbol"])} for a in P.news_in(st, dlo, dhi)
                if S.parse_iso(a["knowable_at"]) > S.parse_iso(P.REGISTERED_AT_2)]
    elig = eligibility(ctx, day, [r["cik"] for r in e8k] + [a["cik"] for a in articles if a["cik"]],
                       live=not backfill_run, kind="close", stored=_first_fetched(st, [*e8k, *articles]))
    scores: dict[str, int | None] = {}

    def verdict(row: Mapping[str, Any]) -> int | None:
        key = row.get("accession") or f"news:{row.get('id')}"
        if key not in scores:
            uni = elig.get(row.get("cik"))
            scores[key] = None if uni is None else (
                news_verdict(ctx, row) if "accession" not in row else doc_verdict(ctx, row, uni))
        return scores[key]

    def reaction(row: Mapping[str, Any], uni: Mapping[str, Any], fetch: bool = True) -> float | None:
        # an 8-K's base is C1's (the last close before the acceptance time); an article's, before its knowable time
        since = row["accepted_at"] if row.get("accession") else row["knowable_at"]
        base = _last_close_before(ctx, uni["symbol"], S.parse_iso(since), fetch=fetch)
        mark = _mark_1530(ctx, uni["symbol"], day, fetch=fetch)
        return None if not base or mark is None else mark / base

    needed: set[tuple[str, str]] = set()      # THE VERDICT TALLY (release 1019c), as decide_open's: the close-entry
    unanswered: set[tuple[str, str]] = set()  # READ programs' (NEWS-READ-ON, ERN-REACT-READ-C1) verdicts reach evl_verdicts

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
            needed.add((event, prompt.sha))
            if V.stored(st, event, prompt) is None:
                missing += 1
                unanswered.add((event, prompt.sha))
        return missing

    out: dict[str, Any] = {"pending": {}}
    why = "backfill" if backfill_run else None
    kept = _scope(st, "close", day, ctx.now())
    later: list[tuple[P.Program, list[Mapping[str, Any]]]] = []
    for prog in P.PROGRAMS:
        if prog.entry_at != "close":
            continue
        rows = {"ern-react": e8k, "news-day": articles, "news-react": articles}.get(prog.family, [])
        rows = [r for r in rows if S.parse_iso(r["knowable_at"]) > prog.registered_at]
        frozen = kept(prog)
        if frozen is not None:     # (A66 owed, a look of its group: its earlier intents stand)
            out.setdefault("kept", {})[_key(prog)] = frozen
            later.append((prog, rows))
            continue
        waiting = pending(prog, rows)
        if ask_only:
            if waiting:
                out["pending"][_key(prog)] = waiting   # version 1 and version 2 of one id count apart
            continue
        if waiting:
            out["pending"][_key(prog)] = waiting   # decided by a later pass, once every verdict is stored
            continue
        cands = P.select(prog, rows, eligible=lambda c: elig.get(c), verdict=verdict, reaction=reaction)
        out[_key(prog)] = P.write_intents(st, prog, day, cands, decided_at=session.close_decide, why=why)
    for prog, rows in [] if ask_only else later:     # (what each kept program leaves out, once this run's asks are in)
        out["kept"][_key(prog)] |= _left_out(st, prog, rows, eligible=lambda c: elig.get(c),
                                             reaction=lambda r, u: reaction(r, u, fetch=False))
    out["events"] = {"8-K": len(e8k), "day_news": len(articles), "eligible": sum(1 for v in elig.values() if v)}
    out["verdicts"] = {"needed": len(needed), "answered": len(needed - unanswered)}
    if rid is not None:
        st.finish_receipt(rid, "pending" if out["pending"] else "ok", out, now=ctx.now())
    return out


__all__ = ["Context", "record_pass", "backfill", "eligibility", "decide_open", "decide_close", "LIVE_WITHIN", "live_run"]

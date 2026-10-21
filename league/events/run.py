"""The event lane's passes: record, backfill, decide at the open, decide at the close (shadow).

Each pass writes a receipt; a decision's carries THE VERDICT TALLY, `verdicts: {needed, answered}`: the distinct
(event, prompt) verdicts its reading programs need, open-entry and close-entry alike, and how many have a stored answer
(release 1019c: the House's stall job reads it, league/ops/evl_health.py `evl_verdicts`). Decisions are recorded at
their SCHEDULED time (09:15 ET open, close - 14 min) whether
they ran live or as a backfill (`why` says which): a backfilled decision uses only data that was knowable at the
scheduled time (filings by knowable time, the universe from the sessions before D, C1's 15:30 minute bar and the
last daily close before the acceptance). Verdicts are asked only for eligible events of the reading programs.
A decision made again (release 1019c, `_scope`), inside the House's re-decision window or outside it (a backfill after
an outage, a decision pending on verdicts, the CLI's catchup, PREREG-EVL-4's rows' own `decide-close-evl4`: release
1019d), writes intents for every program but those of a GROUP
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


class Deadline(Exception):
    """A read past the bound of the task that runs a decision (the House's lane raises its `LaneDeadline`, a subclass):
    the task stops and its next turn goes on from what it stored. Never a failure of a decision's part
    (`decide_close`'s PREREG-EVL-4 part lets it through)."""


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
#: The program whose OPEN decision of D asks the PROMPT-NEWS verdicts PREREG-EVL-4's PM rows read (EVL-NEWS-READ-O1,
#: every version, with its group: its control and the READ programs of that control). Once a written look of that group
#: freezes it over D (A74 (5)), the open decision asks them nothing, so D's CLOSE decision asks the ones its PM rows need
#: itself (A83 (3)(ii): `decide_close`, the same stored prompt and its session-D rendering, stored once).
PM_ASKER = "EVL-NEWS-READ-O1"


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


# ---------------------------------------------------------------------------------------------------- re-decisions
def _group(program: str) -> frozenset[str]:
    """THE IDS A WRITTEN LOOK FREEZES TOGETHER (release 1019c's judges review): the look's id (every version: a
    version 2 takes its version 1's events word for word, PREREG-EVL-3 section 1), its control (the look read the
    control's record), and every READ program of that control (so each one's comparison with the control stays even);
    a control likewise, from its side. An id with no control and none of its own is its own group. A registered READ
    birth of R3 groups with its derived control (league/events/screen.py `control_of`, league/events/births.py
    `control_spec`: the control its looks read), as a PREREG READ program with its table's; every PREREG id's group is
    its table's alone (a birth is never in it)."""
    from . import screen as SN

    born: dict[str, str] = {}       # a READ birth's derived control -> the birth
    if P.BIRTHS:
        from .births import control_id

        born = {control_id(p.id): p.id for p in P.BIRTHS if p.reads and p.version == 1}
    control = SN.control_of(program) or (program if program in SN.CONTROLS.values() or program in born else None)
    if control is None:
        return frozenset({program})
    return frozenset({control, *(read for read, of in SN.CONTROLS.items() if of == control),
                      *((born[control],) if control in born else ())})


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


#: R3: the decision summary's map of the registered births whose own part of a decision raised ({key: why}).
BIRTHS_FAILED = "births_failed"


def _decide_one(prog: P.Program, one: Callable[[P.Program], None], out: dict[str, Any]) -> None:
    """One program's part of a decision. A PREREG program's failure fails the decision, as before; a registered
    birth's (R3, league/events/births.py) is its own: kept in the summary's `births_failed` (league/events/screen.py
    `final_until` then holds that birth's looks until a later pass decides it), never the PREREG programs' decision,
    whose receipt and finality stay as they were. The hourly re-decision tries it again."""
    if prog.spec is None:
        one(prog)
        return
    try:
        one(prog)
    except Exception as exc:  # noqa: BLE001 - a birth's failure is its own
        out.setdefault(BIRTHS_FAILED, {})[_key(prog)] = f"{type(exc).__name__}: {str(exc)[:160]}"


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
def decide_open(ctx: Context, day: dt.date, *, backfill_run: bool = False, ask_only: bool = False,
                births_only: bool = False) -> dict[str, Any]:
    """Shadow intents for every open-entry program at session `day`'s open.

    `ask_only`: the decision's own windows, eligibility and verdict asks, and nothing else: no intent and no receipt is
    written, and `pending` counts each reading program's eligible events still without a stored verdict. The House's
    event lane (league/events/house.py) asks a session's verdicts this way from 07:30 ET, so the decision finds them
    stored; the verdicts and universe rows it stores are the very ones the decision reads.

    `births_only` (release 1019e's review): R3'S REGISTERED BIRTHS DECIDED BY THEMSELVES, for a session a release, or a
    turn, without their rows decided (league/events/screen.py `births_made_without`; the House's lane and the CLI's
    catchup run it, as a backfill): the decision's reads and its eligibility call exactly as the whole decision makes
    them, then the births alone (their verdicts, their intents); NO PREREG PROGRAM's verdict is asked or intent
    written, so a session final for a PREREG program gains nothing. Its receipt is `decide-open-births:<day>`
    (screen.BIRTHS_KIND), which the judge reads for the births only (`screen.final_until`)."""
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return {"skipped": "no session"}
    job = f"decide-{SN.BIRTHS_KIND['open'] if births_only else 'open'}:{day}"
    rid = None if ask_only else st.start_receipt(job, now=ctx.now())
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

    def one(prog: P.Program) -> None:
        rows = {"ern": e8k, "8k": e8k, "ins": ins, "ins-buy": buys, "news": articles}.get(prog.family, [])
        rows = [r for r in rows if S.parse_iso(r["knowable_at"]) > prog.registered_at]
        frozen = kept(prog)
        if frozen is not None:     # (A66 owed, a look of its group: its earlier intents stand)
            out.setdefault("kept", {})[_key(prog)] = frozen
            later.append((prog, rows))
            return
        waiting = pending(prog, rows)
        if ask_only:
            if waiting:
                out["pending"][_key(prog)] = waiting   # version 1 and version 2 of one id count apart
            return
        if waiting:
            out["pending"][_key(prog)] = waiting   # decided by a later pass, once every verdict is stored
            return
        cands = P.select(prog, rows, eligible=lambda c: elig.get(c), verdict=verdict, guidance=guidance)
        out[_key(prog)] = P.write_intents(st, prog, day, cands, decided_at=session.open_decide, why=why)

    for prog in P.PROGRAMS:
        if prog.entry_at != "open" or (births_only and prog.spec is None):
            continue
        _decide_one(prog, one, out)
    for prog, rows in [] if ask_only else later:     # (what each kept program leaves out, once this run's asks are in)
        def left(prog: P.Program, rows: list[Mapping[str, Any]] = rows) -> None:
            out["kept"][_key(prog)] |= _left_out(st, prog, rows, eligible=lambda c: elig.get(c), guidance=guidance)
        _decide_one(prog, left, out)
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


def _skip_excluded(st: S.Store, day: dt.date, excluded: set[str], filed: set[str], *,
                   keep: Callable[[P.Program], bool] | None = None) -> int:
    """THE ADVERSARIAL CHECK'S BUILD NOTE (ii) for PREREG-EVL-4's rows: a re-decision of D's close marks an intent of
    those rows for D that has not settled (planned or entered) `skipped:excluded` when a row stored after the intent was
    written now puts its issuer in EXCLUDED on D (for EVL-NEWSPM-READ-ON and its control, also in the F8K(D) skip): the
    shadow is the rule over every event knowable at the decision time, whenever the recorder stored it. A settled intent
    is never changed (its record is final; store.py's forward-only status); one skipped already stays as it is; a
    program `keep` names (a written look of its group freezes it over D: run.py `_scope`, A74 (5)) is never touched
    (release 1019d). Returns how many moved."""
    moves: list[tuple[P.Program, str, str]] = []
    for prog in P.PROGRAMS:
        if prog.family not in P.CLOSE_FAMILIES_4 or prog.entry_at != "close":
            continue
        if keep is not None and keep(prog):
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
                 evl4_only: bool = False, births_only: bool = False) -> dict[str, Any]:
    """Shadow intents for every close-entry program at session `day`'s close: C1 (PREREG-EVL-1) and PREREG-EVL-2's
    REACT-ON, REACT-READ-C1 and the day-news programs (NEWS-READ-ON, its control, NEWS-REACT-ON), then PREREG-EVL-4's
    (EVL-8K-REACT-ON, EVL-8K-READ-ON, EVL-NEWSPM-READ-ON and their two controls: `_rows_4`).

    The earlier rows read exactly what they read before PREREG-EVL-4 (their windows, their eligibility call, their
    verdicts, in the same order); PREREG-EVL-4's rows come after them, with their own reads: every 8-K of the close window
    (F8K(D) and ERN(D)), the day-news window (DAY(D)) and PM(D), with no registration floor for the sets that skip;
    their PROMPT-DOC verdicts asked as EVL-8K-READ-O1's own (one verdict an event, stored once: a filing knowable during
    D is asked during D's session by `ask_only`), their PROMPT-NEWS verdicts read as stored (EVL-NEWS-READ-O1 asks them
    for its open decision of D: the adversarial check's build note (iii)), and asked here only when a written look of
    EVL-NEWS-READ-O1's group freezes that group over D, so its open decision asks nothing (A83 (3)(ii): the same stored
    prompt, the article as D's open decision renders it, one verdict an event, stored once; the frozen group itself is
    still asked nothing and written nothing); their READ events wait for their verdicts. A re-decision marks such a
    row's unsettled intent `skipped:excluded` when a row stored later puts its issuer in EXCLUDED or the F8K(D) skip
    (`_skip_excluded`, build note (ii)).

    PREREG-EVL-4'S PART IS ISOLATED (A83 (3)(i), release 1019e): its reads (`_rows_4`: every 8-K of the close window, the
    day-news window and PM(D), and their eligibility), `_skip_excluded`, the 15:30 marks of EVL-8K-REACT-ON's rows, its
    verdicts and its programs' intents run after every earlier row is decided. An exception in that part that is not
    the task's time bound (`Deadline`) is that part's alone: the decision finishes with the earlier rows' results (its
    receipt `ok`, or `pending` on THEIR verdicts), the error in the summary's `evl4_error`, and PREREG-EVL-4's programs
    NAMED NOWHERE in it (no counts, no `pending`, no `kept`), so the judge reads that close as made without their rows
    (league/events/screen.py `names`, `final_until`) and their own decision (`decide-close-evl4`, `made_without`) or the
    next whole re-decision decides them; the earlier rows' looks never wait on it. A time bound stops the whole task, as
    before (the next turn decides the close again). `ask_only` isolates it the same way (no receipt): the earlier rows'
    asks stand. With `evl4_only` (their own decision) the exception is the decision's own and propagates.

    `ask_only`: as decide_open's (the verdicts the close decision will read, asked during the session: no intent, no
    receipt, and no reaction, whose 15:29 bar is not on the tape before the decision).

    `evl4_only` (release 1019c's review): PREREG-EVL-4'S ROWS DECIDED BY THEMSELVES, for a close a release without them
    decided (league/events/screen.py `made_without`; the House's lane and the CLI's catchup run it once, as a backfill):
    the decision's reads and its eligibility call exactly as the whole decision makes them, then their rows as above
    (reads, verdicts, `_skip_excluded`, intents); NO EARLIER ROW'S verdict is asked or intent written, so a close final
    for an earlier program gains nothing. Its receipt is `decide-close-evl4:<day>` (screen.FOUR_KIND), which the judge
    reads for their programs only (`screen.final_until`): the session's `decide-close:<day>` receipts, which the House's
    lane, its book and the judge read for every earlier row, are left as they are.

    `births_only` (release 1019e's review): R3'S REGISTERED BIRTHS DECIDED BY THEMSELVES, as `decide_open`'s: the
    decision's reads and its eligibility call as the whole decision makes them, then the close-entry births alone (no
    PREREG row, PREREG-EVL-4's part not run); its receipt `decide-close-births:<day>` (screen.BIRTHS_KIND)."""
    if evl4_only and births_only:
        raise ValueError("a decision of PREREG-EVL-4's rows by themselves or of the births by themselves, not both")
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return {"skipped": "no session"}
    kind = SN.FOUR_KIND if evl4_only else SN.BIRTHS_KIND["close"] if births_only else "close"
    job = f"decide-{kind}:{day}"
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
        asks for its open decision of D), read only; their asks, when EVL-NEWS-READ-O1's group is frozen over D, are
        `pending4`'s (A83 (3)(ii))."""
        got = V.stored(st, f"news:{row['id']}", V.PROMPTS["news"])
        return got["score"] if got and got["status"] == "ok" else None

    asker: list[bool] = []

    def pm_asks() -> bool:
        """A83 (3)(ii): whether a written look of EVL-NEWS-READ-O1's group freezes that group over D (`_scope`, A74 (5);
        every version of the id, its control and the READ programs of that control are kept together), so D's open
        decision asks none of the PROMPT-NEWS verdicts PREREG-EVL-4's PM rows read: then this decision asks them."""
        if not asker:
            reader = P.BY_KEY.get((PM_ASKER, 1))
            asker.append(reader is not None and kept(reader) is not None)
        return asker[0]

    asked_news: dict[str, int | None] = {}

    def news4(row: Mapping[str, Any]) -> int | None:
        """A PM row's PROMPT-NEWS verdict asked by this decision (A83 (3)(ii)): `news_verdict`, the open decision's own
        ask (the same stored prompt, the article rendered from its stored fields as D's open decision renders it), once
        an article; `verdicts.ask` stores the first answer, which stays final."""
        key = str(row["id"])
        if key not in asked_news:
            asked_news[key] = news_verdict(ctx, row)
        return asked_news[key]

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

    def pending4(prog: P.Program, rows: list[Mapping[str, Any]]) -> int:
        """PREREG-EVL-4's READ events wait for their verdicts (the shadow rule), and its news control for the stored
        scores it ranks by: how many of `prog`'s eligible events have none stored yet. The 8-K rows' PROMPT-DOC is asked
        here (TEXT >= 200 characters: a shorter TEXT has no verdict and is not taken); PM(D)'s PROMPT-NEWS waits for
        EVL-NEWS-READ-O1's ask, and is asked here only while a written look of that program's group freezes it over D
        (`pm_asks`, A83 (3)(ii)). Each is in the decision's verdict tally as the earlier rows' are (release 1019d: a
        wait of these rows reaches the stall job's evl_verdicts, as their `pending` did before the tally)."""
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
            elif pm_asks():
                news4(row)
            event = f"news:{row['id']}" if news else f"8k:{row['accession']}"
            needed.add((event, prompt.sha))
            if V.stored(st, event, prompt) is None:
                missing += 1
                unanswered.add((event, prompt.sha))
        return missing

    out: dict[str, Any] = {"pending": {}}
    why = "backfill" if backfill_run else None
    kept = _scope(st, "close", day, ctx.now())
    later: list[tuple[P.Program, list[Mapping[str, Any]], Mapping[str, Mapping[str, Any] | None]]] = []

    def one(prog: P.Program, mine: bool) -> None:
        """One program's part of the close decision (a registered birth's failure is its own: `_decide_one`)."""
        if mine:
            rows, table, wait = four["rows"][prog.family], elig4, pending4
            read = stored_news if prog.family == "news-pm" else verdict4
        else:
            rows = {"ern-react": e8k, "news-day": articles, "news-react": articles}.get(prog.family, [])
            table, wait, read = elig, pending, verdict
        rows = [r for r in rows if S.parse_iso(r["knowable_at"]) > prog.registered_at]
        frozen = kept(prog)
        if frozen is not None:     # (A66 owed, a look of its group: its earlier intents stand)
            out.setdefault("kept", {})[_key(prog)] = frozen
            later.append((prog, rows, table))
            return
        waiting = wait(prog, rows)
        if ask_only:
            if waiting:
                out["pending"][_key(prog)] = waiting   # version 1 and version 2 of one id count apart
            return
        if waiting:
            out["pending"][_key(prog)] = waiting   # decided by a later pass, once every verdict is stored
            return
        if prog.family == "8k-react":
            _marks_1530(ctx, [str(table[r["cik"]]["symbol"]) for r in rows if table.get(r.get("cik"))], day)
        cands = P.select(prog, rows, eligible=lambda c, table=table: table.get(c), verdict=read, reaction=reaction)
        out[_key(prog)] = P.write_intents(st, prog, day, cands, decided_at=session.close_decide, why=why)

    def left(prog: P.Program, rows: list[Mapping[str, Any]], table: Mapping[str, Mapping[str, Any] | None]) -> None:
        out["kept"][_key(prog)] |= _left_out(st, prog, rows, eligible=lambda c: table.get(c),
                                             reaction=lambda r, u: reaction(r, u, fetch=False))

    def four_part() -> None:
        """PREREG-EVL-4's part of the decision (A83 (3)(i)): its reads, `_skip_excluded`, its programs (the 15:30 marks
        and the verdicts they read, their intents) and what each of its kept programs leaves out."""
        four.update(_rows_4(ctx, day, (lo, hi), by_ticker, elig, live=not backfill_run))
        elig4.update(four["elig"])
        if not ask_only:
            late = _skip_excluded(st, day, four["excluded"], four["filed"], keep=lambda prog: kept(prog) is not None)
            if late:
                out["skipped_excluded"] = late
        for prog in P.PROGRAMS:
            if prog.entry_at == "close" and prog.family in P.CLOSE_FAMILIES_4:
                _decide_one(prog, lambda prog: one(prog, True), out)
        for prog, rows, table in [] if ask_only else [x for x in later if x[0].family in P.CLOSE_FAMILIES_4]:
            _decide_one(prog, lambda prog, rows=rows, table=table: left(prog, rows, table), out)

    # THE EARLIER ROWS FIRST, exactly as before PREREG-EVL-4 (their reads, verdicts and intents), then PREREG-EVL-4's
    # part (`four_part`), whose own reads come after them; an exception in that part other than the task's time bound
    # finishes the decision with the earlier rows' results and leaves PREREG-EVL-4's programs unnamed (the docstring,
    # A83 (3)(i)). A program a written look of its group freezes (`_scope`, A74 (5)) is kept in either part: asked
    # nothing, fetched nothing, written nothing (no intent, no `skipped:excluded` move: `_skip_excluded` passes it
    # over). R3's registered births (close entry: ern-react, news-day, news-react) are decided in the earlier part,
    # after every PREREG row.
    if not evl4_only:       # (PREREG-EVL-4's rows by themselves: no earlier row is decided again)
        for prog in P.PROGRAMS:
            if prog.entry_at == "close" and prog.family not in P.CLOSE_FAMILIES_4 and \
                    not (births_only and prog.spec is None):
                _decide_one(prog, lambda prog: one(prog, False), out)
    try:
        if not births_only:     # (the births by themselves: no PREREG-EVL-4 row is decided again)
            four_part()
    except Deadline:
        raise
    except Exception as exc:  # noqa: BLE001 - PREREG-EVL-4's part fails alone (A83 (3)(i)); never with evl4_only
        if evl4_only:
            raise
        out["evl4_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        for prog in P.PROGRAMS:
            if prog.entry_at == "close" and prog.family in P.CLOSE_FAMILIES_4:
                for where in (out, out["pending"], out.get("kept") or {}):
                    where.pop(_key(prog), None)
        if "kept" in out and not out["kept"]:
            del out["kept"]
    for prog, rows, table in [] if ask_only else [x for x in later if x[0].family not in P.CLOSE_FAMILIES_4]:
        # (what each kept earlier program leaves out, once this run's asks are in)
        _decide_one(prog, lambda prog, rows=rows, table=table: left(prog, rows, table), out)
    out["events"] = {"8-K": len(e8k), "day_news": len(articles), "eligible": sum(1 for v in elig.values() if v),
                     **four.get("counts", {})}
    out["verdicts"] = {"needed": len(needed), "answered": len(needed - unanswered)}
    if rid is not None:
        st.finish_receipt(rid, "pending" if out["pending"] else "ok", out, now=ctx.now())
    return out


__all__ = ["Context", "record_pass", "backfill", "eligibility", "decide_open", "decide_close", "LIVE_WITHIN", "live_run",
           "waits_on_open", "Deadline", "PM_ASKER"]

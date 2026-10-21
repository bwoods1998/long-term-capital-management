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

import copy
import datetime as dt
import json
import time
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
    (`decide_close`'s PREREG-EVL-4 and PREREG-EVL-5 parts let it through)."""


class PartDeadline(Exception):
    """PREREG-EVL-5 section 1.3: THE PART OF A CLOSE DECISION THAT DECIDES ITS ROWS ran past ITS OWN time bound
    (`EVL5_BUDGET`, never past the task's own bound less `EVL5_FINISH`). NOT a `Deadline` (the task's): it is the part's
    failure alone, so the decision finishes with the earlier rows' results and names none of PREREG-EVL-5's rows
    (`decide_close`), which `decide-close-evl5` then decides by themselves as a backfill, never traded."""


#: PREREG-EVL-5 section 1.3, THE PART'S OWN TIME BOUND (the adversarial check's third major): the seconds the part that
#: decides PREREG-EVL-5's rows may run inside a close decision, and never past the task's own bound (the House's
#: `DECIDE_BUDGET`, league/events/house.py, which hands the decision its deadline: `Context.deadline`) less EVL5_FINISH,
#: the time the receipt's finish needs. The session's verdict pre-passes (`ask_only`) run the part's reads under
#: EVL5_PRE_BUDGET the same way. Behind league/ci.py's wall, as this module is.
EVL5_BUDGET = 45.0
EVL5_PRE_BUDGET = 60.0
EVL5_FINISH = 15.0
#: Inside this long before D's close decision, the pre-pass reads EVL-NEWS-NIGHT2-ON's rows only once the earlier rows'
#: verdicts of that decision are all stored (the code plan's schedule: the earlier rows' asks come first).
EVL5_PRE_URGENT = dt.timedelta(minutes=30)
#: meta `evl5:pre:<day>`: what the session's verdict pre-pass read for EVL-NEWS-NIGHT2-ON (JSON {cut, survivors, ...}),
#: written last, once its eligibility results and 09:30 marks are stored (league/events/house.py schedules the pass).
PRE_KEY = "evl5:pre:"
#: THE GAP'S MINUTE (PREREG-EVL-5 section 1.1): the regular-session SIP 1-minute bar starting at 09:30:00 ET of D, its
#: OPEN (raw), stored once read under this label (a row with no price when that minute had no trade: no gap).
GAP_LABEL = "0930"


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
        #: The bound of the task that runs this pass, on `mono`'s clock (the House's lane sets it: house.py `_do`), None
        #: when none (the CLI): PREREG-EVL-5's part of a close decision never runs past it less EVL5_FINISH.
        self.deadline: float | None = None
        self.mono: Callable[[], float] = time.monotonic

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
              reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None,
              gap: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None
              ) -> dict[str, list[str]]:
    """WHAT A DECISION THAT KEEPS `prog` LEAVES OUT OF ITS RECORD (release 1019c's judges review; PREREG-EVL-1 section
    3: an outage removes nothing, the late share is reported): `events`, the events of the decision's windows its rule
    takes on the verdicts and prices already stored and its record does not hold (no intent, planned or skipped);
    `unjudged`, those it would take only on a verdict or a price no one has stored yet (a kept program is never asked a
    verdict and never fetched a price: `reaction` reads stored prices only). `rows` are the windows' rows after its
    registration; nothing is written. The daily report counts both (league/events/report.py `kept_out`). PREREG-EVL-5's
    rows hope for the price their own rule takes (`HOPED`: a fall to 0.96, a muted 1.00) and EVL-NEWS-NIGHT2-ON for a
    gap of 1.02 (`gap`, stored marks only); every earlier row hopes for 1.04, as before."""
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
        return HOPED.get(prog.family, P.REACT_RATIO) if got is None else got

    def hoped_gap(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
        got = gap(row, uni) if gap is not None else None
        return P.GAP_RATIO if got is None else got

    def held(event: str) -> bool:
        return st.db.execute("SELECT 1 FROM intents WHERE program=? AND version=? AND event=?",
                             (prog.id, prog.version, event)).fetchone() is not None

    taken = {c.event for c in P.select(prog, rows, eligible=eligible, verdict=score, reaction=reaction,
                                       guidance=guidance, gap=gap)}
    maybe = {c.event for c in P.select(prog, rows, eligible=eligible, verdict=hoped, reaction=hoped_reaction,
                                       guidance=hoped_guidance, gap=hoped_gap)}
    return {"events": sorted(e for e in taken if not held(e)),
            "unjudged": sorted(e for e in maybe - taken if not held(e))}


#: The price a kept PREREG-EVL-5 earnings row hopes for when none is stored (`_left_out`): one its own rule takes.
HOPED = {"ern-drop": P.DROP_RATIO, "ern-under": 1.0}

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


# ---------------------------------------------------------------------------------------------------- PREREG-EVL-5
class _PartGateway:
    """The gateway of PREREG-EVL-5's part of a close decision (section 1.3): every read and call goes through the
    task's own gateway (its bound, its counts, the lane's line) and stops at the part's own bound first, with
    `PartDeadline` (the part's failure alone, never the task's `Deadline`)."""

    def __init__(self, inner: Any, until: float, mono: Callable[[], float]):
        self.__dict__.update(inner=inner, until=until, mono=mono)

    def _check(self, what: str) -> None:
        if self.mono() >= self.until:
            raise PartDeadline(f"PREREG-EVL-5's part ran past its own time bound before {str(what)[:80]}")

    @property
    def last_headers(self) -> Mapping[str, str]:
        return getattr(self.inner, "last_headers", {}) or {}

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        self._check(path)
        return self.inner.get_json(path, params)

    def post_json(self, path: str, body: Any, headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        self._check(path)
        return self.inner.post_json(path, body, headers)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__dict__["inner"], name)


def part_until(ctx: Context, budget: float) -> float:
    """The part's own bound on `ctx.mono`'s clock: `budget` seconds from now, and never past the task's own bound
    (`ctx.deadline`) less EVL5_FINISH (PREREG-EVL-5 section 1.3: the part never cuts the earlier rows' receipt)."""
    mono = getattr(ctx, "mono", None) or time.monotonic
    until = mono() + float(budget)
    deadline = getattr(ctx, "deadline", None)
    if deadline is not None:
        until = min(until, float(deadline) - EVL5_FINISH)
    return until


def bounded(ctx: Context, until: float) -> Context:
    """`ctx` with its gateway and SEC reads held to `until` (`_PartGateway`): a shallow copy sharing the store, the
    caches and the clock."""
    mono = getattr(ctx, "mono", None) or time.monotonic
    sub = copy.copy(ctx)
    sub.gw = _PartGateway(ctx.gw, until, mono)
    inner = ctx.sec

    def sec(url: str) -> bytes:
        if mono() >= until:
            raise PartDeadline(f"PREREG-EVL-5's part ran past its own time bound before {url[:80]}")
        return inner(url)
    sub.sec = sec
    return sub


def pre_from(session: C.Session) -> dt.datetime:
    """When D's 09:30 minute bar is on the Basic plan's tape (the bar's end plus `universe.SIP_DELAY`: 09:47 ET): from
    then on the session's verdict pre-passes read EVL-NEWS-NIGHT2-ON's rows (PREREG-EVL-5 section 1.3)."""
    return session.open_at + dt.timedelta(minutes=1) + U.SIP_DELAY


def _gap_mark(st: S.Store, symbol: str, day: dt.date) -> tuple[bool, float | None]:
    """(read, the open) of `symbol`'s stored 09:30 minute of `day` (`GAP_LABEL`): (False, None) when none is stored,
    (True, None) when the minute had no trade."""
    row = st.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label=?",
                        (symbol, day.isoformat(), GAP_LABEL)).fetchone()
    if row is None:
        return False, None
    return True, (float(row["px"]) if row["px"] is not None else None)


def _marks_0930(ctx: Context, symbols: Iterable[str], day: dt.date) -> int:
    """THE GAP'S MINUTE of `symbols` on session `day` (PREREG-EVL-5 section 1.1): the regular-session SIP 1-minute bar
    starting at 09:30:00 ET (raw), read in batched requests (`MARK_BATCH` names each, paged), stored once read under
    `GAP_LABEL` with its OPEN; a name the answer holds no such bar for (the minute had no trade) is stored with no price
    (no gap: the event is not taken). Names already stored are not read again; nothing is read before the bar is on the
    Basic plan's tape (`pre_from`). Returns how many rows were stored."""
    st = ctx.store
    session = C.session(st, day)
    if session is None or ctx.now() < pre_from(session):
        return 0
    start, end = session.open_at, session.open_at + dt.timedelta(minutes=1)
    have = {str(r[0]) for r in st.db.execute("SELECT symbol FROM marks WHERE day=? AND label=?",
                                              (day.isoformat(), GAP_LABEL))}
    names = sorted({str(x).upper() for x in symbols if x} - have)
    stored = 0
    for i in range(0, len(names), MARK_BATCH):
        chunk = names[i:i + MARK_BATCH]
        got: dict[str, list[Mapping[str, Any]]] = {}
        token = None
        for _ in range(MARK_PAGES):
            page = ctx.gw.get_json("/v1/alpaca/v2/stocks/bars", {"symbols": ",".join(chunk), "timeframe": "1Min",
                                                                 "start": S.iso(start), "end": S.iso(end), "feed": "sip",
                                                                 "adjustment": "raw", "limit": 10000,
                                                                 "page_token": token}) or {}
            for sym, bars in (page.get("bars") or {}).items():
                got.setdefault(str(sym).upper(), []).extend(bars or [])
            token = page.get("next_page_token")
            if not token:
                break
        with st.tx() as db:
            for sym in chunk:
                bar = next((b for b in got.get(sym, []) if S.parse_iso(str(b["t"])) == start), None)
                px = None
                if bar is not None and bar.get("o") is not None and float(bar["o"]) > 0:
                    px = float(bar["o"])
                db.execute("INSERT OR REPLACE INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, ?, ?, "
                           "?, ?, ?)", (sym, day.isoformat(), GAP_LABEL, px, S.iso(start),
                                        "sip-1min" if px is not None else "sip-1min:none", S.iso(ctx.now())))
                stored += 1
    return stored


def _stored_results(st: S.Store, day: dt.date, ciks: Iterable[str], *, live: bool) -> dict[str, Mapping[str, Any] | None]:
    """The eligibility results already kept for `ciks` (`universe.results`), read only: the live rule's for a live
    decision, every result's (`universe.combined`) for a backfill; None for a CIK with none. A kept program fetches
    nothing (A74 (5)), so what it leaves out is read on these."""
    known = U.results(st, day)
    out: dict[str, Mapping[str, Any] | None] = {}
    for cik in ciks:
        have = known.get(str(cik)) or {}
        out[str(cik)] = (have.get(S.LIVE_RULE) if live else U.combined(have)) if have else None
    return out


def _rows_5(ctx: Context, day: dt.date, by_ticker: Mapping[str, str], elig: Mapping[str, Mapping[str, Any] | None], *,
            live: bool, ask_only: bool, earnings: bool, night2: bool, fetch_earnings: bool, fetch_night2: bool,
            needed: set[tuple[str, str]], unanswered: set[tuple[str, str]], check: Callable[[str], None]
            ) -> dict[str, Any]:
    """PREREG-EVL-5's reads for the close decision of D = `day` (its section 1), ALL WITH NO REGISTRATION FLOOR for the
    sets that skip: ERN(D) (the item 2.02 8-Ks of D's close window), DAY(D) (PREREG-EVL-2's day-news window, each article
    with its issuer's CIK by D's tickers), the attention articles of P, and NO NEW INFORMATION's three windows (i)-(iii).

    `earnings` (DROP, UNDER and its control are read): the eligibility of ERN(D)'s event issuers (knowable after
    the registration time; most judged already by the earlier rows' call, `elig`, untouched), their reactions (C1's: the
    T29 close of D over the last close before the acceptance, the T29 minutes read together, `_marks_1530`), the
    day-news reactions of their DAY(D) issuers (the T29 close over the universe row's previous close), section 1.2's NO
    NEW PROMPT AND NO SECOND VERDICT (the PROMPT-NEWS verdict of a DAY(D) article, and the PROMPT-DOC verdict of an
    eligible ERN(D) filing, that these rows read and that no row has stored, asked here with the earlier row's event id,
    prompt and rendering), then TAKEN AT D'S CLOSE BY AN EARLIER ROW (`programs.taken_close_5`) and the <= 0.96 skip.
    `night2` (EVL-NEWS-NIGHT2-ON is read): the eligibility of the attention issuers with NO NEW INFORMATION
    whose attention article is an event, and the 09:30 minutes of the eligible ones (`_marks_0930`). With `ask_only` no
    reaction is read (the T29 bar is not on the tape before the decision): the asks are those of every eligible ERN(D)
    event. Only with `fetch_earnings` (an earnings row is decided or asked) and `fetch_night2` (EVL-NEWS-NIGHT2-ON is) is
    anything fetched or asked for that group; otherwise (every program of it kept: A74 (5)) the stored results, marks
    and verdicts only. `check(where)` raises `PartDeadline` once the part's bound has passed; every network read is held to
    it too (`bounded`). Every result is stored as it is read (eligibility, marks, verdicts), so a pre-pass's reads are
    the close decision's. Returns {rows: {family: rows}, elig, skips: {family: CIKs}, pending: {program id: n}, ...}."""
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        raise LookupError(f"no session {day}")
    times = [p.registered_at for p in P.PROGRAMS if p.prereg == 5 and p.family in P.CLOSE_FAMILIES_5]
    since = min(times) if times else None
    if since is None:
        return {"rows": {f: [] for f in P.CLOSE_FAMILIES_5}, "elig": dict(elig), "skips": {}, "pending": {},
                "reactions": {}, "gaps": {}, "counts": {}, "survivors": set()}

    def after(row: Mapping[str, Any]) -> bool:
        return S.parse_iso(str(row["knowable_at"])) > since

    def with_cik(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [dict(a) | {"cik": by_ticker.get(a["symbol"])} for a in rows]
    lo, hi = P.close_window(st, day)
    ern = [r for r in P.filings_window(st, "8-K", lo, hi) if P.items_of(r) & P.ERN_ITEMS and r.get("cik")]
    ern_events = [r for r in ern if after(r)]
    ern_issuers = {str(r["cik"]) for r in ern_events}
    day_all = with_cik(P.news_rows(st, *P.day_news_window(st, day)))
    attention = with_cik(P.news_rows(st, *P.attention_window(st, day)))
    windows = P.night2_windows(st, day)
    named = P.named_ciks(P.news_named(st, *windows["named"]), P.ciks_by_ticker(ctx.tickers_for(day)))
    filed = P.filed_ciks(P.filings_window(st, "8-K", *windows["filed"]))
    bought = P.bought_ciks(P.ins_buys_window(st, *windows["bought"]))
    quiet = named | filed | bought
    att_events = [a for a in attention if a.get("cik") and after(a) and str(a["cik"]) not in quiet]
    survivors = {str(a["cik"]) for a in att_events}
    check("the eligibility of PREREG-EVL-5's issuers")
    table: dict[str, Mapping[str, Any] | None] = dict(elig)
    fetched = ((ern_issuers if earnings and fetch_earnings else set())
               | (survivors if night2 and fetch_night2 else set())) - set(table)
    need = sorted(fetched)
    if need:
        rows_of = [r for r in ern_events if str(r["cik"]) in fetched] + [a for a in att_events if str(a["cik"]) in fetched]
        table.update(eligibility(ctx, day, need, live=live, kind="close", stored=_first_fetched(st, rows_of)))
    rest = sorted(((ern_issuers if earnings else set()) | (survivors if night2 else set())) - set(table))
    if rest:
        table.update(_stored_results(st, day, rest, live=live))

    def symbol_of(cik: str) -> str | None:
        uni = table.get(str(cik))
        return None if uni is None else uni.get("symbol")
    eligible_ern = {c for c in ern_issuers if table.get(c)} if earnings else set()
    day5 = [a for a in day_all if a.get("cik") and str(a["cik"]) in eligible_ern and symbol_of(a["cik"]) == a.get("symbol")]
    reactions: dict[str, float | None] = {}
    day_react: dict[str, float | None] = {}
    if earnings and not ask_only:
        check("the T29 minutes of ERN(D)")
        fetch = fetch_earnings
        if fetch:
            _marks_1530(ctx, [str(symbol_of(c)) for c in sorted(eligible_ern)], day)
        for r in ern:
            cik = str(r["cik"])
            if cik in eligible_ern:
                uni = table[cik]
                base = _last_close_before(ctx, uni["symbol"], S.parse_iso(r["accepted_at"]), fetch=fetch)
                mark = _mark_1530(ctx, uni["symbol"], day, fetch=fetch)
                reactions[str(r["accession"])] = None if not base or mark is None else mark / base
        for cik in sorted({str(a["cik"]) for a in day5}):
            uni = table[cik]
            mark = _mark_1530(ctx, uni["symbol"], day, fetch=fetch)
            prev = float(uni.get("prev_close") or 0.0)
            day_react[cik] = mark / prev if mark is not None and prev > 0 else None

    def react(row: Mapping[str, Any]) -> float | None:
        return reactions.get(str(row.get("accession")))
    news_prompt, doc_prompt = V.PROMPTS["news"], V.PROMPTS["doc"]

    def answer(a: Mapping[str, Any]) -> Mapping[str, Any] | None:
        return V.stored(st, f"news:{a['id']}", news_prompt)
    # (a) and (c) first (prices), so a PROMPT-NEWS verdict is asked only for an issuer they leave (section 1.2)
    first, _ = P.taken_close_5(ern, day5, symbol_of=symbol_of, reaction=react, day_reaction=day_react.get,
                               news_answer=lambda a: {"status": "unparsed"})
    for a in day5:
        if str(a["cik"]) in first:
            continue
        event = (f"news:{a['id']}", news_prompt.sha)
        needed.add(event)
        if answer(a) is None and fetch_earnings:
            check("a DAY(D) verdict")
            news_verdict(ctx, a)
        if answer(a) is None:
            unanswered.add(event)
    taken, waiting = P.taken_close_5(ern, day5, symbol_of=symbol_of, reaction=react, day_reaction=day_react.get,
                                     news_answer=answer)
    dropped = P.dropped_ciks([r for r in ern if str(r["cik"]) in eligible_ern], react)

    def band(r: Mapping[str, Any]) -> bool:
        ratio = react(r)
        return ask_only or (ratio is not None and P.DROP_RATIO < ratio < P.REACT_RATIO)
    under = [r for r in ern_events if str(r["cik"]) in eligible_ern and str(r["cik"]) not in taken | waiting | dropped
             and band(r) and r.get("text_sha") and (r.get("text_len") or 0) >= 200]
    for r in under:
        event = (f"8k:{r['accession']}", doc_prompt.sha)
        needed.add(event)
        if V.stored(st, event[0], doc_prompt) is None and fetch_earnings:
            check("an ERN(D) verdict")
            doc_verdict(ctx, r, table[str(r["cik"])])
        if V.stored(st, event[0], doc_prompt) is None:
            unanswered.add(event)
    unanswered_news = {cik: sum(1 for a in day5 if str(a["cik"]) == cik and answer(a) is None) for cik in waiting}
    falls = {str(r["cik"]) for r in ern_events if ask_only or (react(r) is not None and react(r) <= P.DROP_RATIO)}
    muted = {str(r["cik"]) for r in ern_events if band(r)} - dropped
    pending = {
        "EVL-ERN-DROP-ON": sum(n for cik, n in unanswered_news.items() if cik in falls),
        "EVL-ERN-UNDER-ON": sum(n for cik, n in unanswered_news.items() if cik in muted)
        + sum(1 for r in under if V.stored(st, f"8k:{r['accession']}", doc_prompt) is None),
    }
    pending["EVL-CTRL-ERN-UNDER-ON"] = pending["EVL-ERN-UNDER-ON"]
    gaps: dict[str, float | None] = {}
    marks = 0
    if night2:
        check("the 09:30 minutes of the attention issuers")
        live_symbols = sorted({str(symbol_of(c)) for c in survivors if symbol_of(c)})
        if fetch_night2:
            marks = _marks_0930(ctx, live_symbols, day)
        for cik in sorted(survivors):
            uni = table.get(cik)
            if uni is None:
                continue
            read, px = _gap_mark(st, str(uni["symbol"]), day)
            prev = float(uni.get("prev_close") or 0.0)
            gaps[cik] = px / prev if read and px is not None and prev > 0 else None
    rows = P.close_rows_5(ern, P.no_new_info(attention, named, filed, bought, symbol_of) if night2 else [],
                          taken=taken, waiting=waiting, dropped=dropped)
    attention_issuers = {str(a["cik"]) for a in attention if a.get("cik") and after(a)}
    counts = {"ern": len(ern), "ern_events": len(ern_events), "ern_issuers": len(ern_issuers),
              "ern_eligible": len(eligible_ern), "taken": len(taken & eligible_ern), "waiting": len(waiting),
              "dropped": len(dropped), "falls": len(falls & eligible_ern - taken), "muted": len(muted - taken - waiting),
              "attention": len(attention_issuers), "named": len(attention_issuers & named),
              "filed": len(attention_issuers & filed - named), "bought": len(attention_issuers & bought - named - filed),
              "survivors": len(survivors), "survivors_eligible": sum(1 for c in survivors if table.get(c)),
              "gaps_read": sum(1 for v in gaps.values() if v is not None),
              "gap_pass": sum(1 for v in gaps.values() if v is not None and v >= P.GAP_RATIO), "marks_0930": marks}
    return {"rows": rows, "elig": table, "skips": {"ern-drop": taken, "ern-under": taken | dropped, "news-night2": quiet},
            "pending": pending, "reactions": reactions, "gaps": gaps, "counts": counts, "survivors": survivors}


def _skip_taken_5(st: S.Store, day: dt.date, skips: Mapping[str, set[str]], *,
                  keep: Callable[[P.Program], bool] | None = None) -> int:
    """PREREG-EVL-5's re-decision (as PREREG-EVL-4's `_skip_excluded`, A75 (2)): a re-decision of D's close marks an
    intent of PREREG-EVL-5's rows for D that has not settled (planned or entered) `skipped:taken` when a row stored after
    the intent was written now puts its issuer in a set that skips it (`skips` by family: TAKEN AT D'S CLOSE BY AN
    EARLIER ROW for EVL-ERN-DROP-ON; that or the <= 0.96 skip for EVL-ERN-UNDER-ON and its control; NO NEW INFORMATION
    for EVL-NEWS-NIGHT2-ON): the shadow is the rule over every event knowable at the decision time, whenever the
    recorder stored it. A settled intent, or one skipped already, stays as it is; a program `keep` names (a written look
    of its group freezes it over D) is never touched. Returns how many moved."""
    whys = {"ern-drop": "TAKEN AT D'S CLOSE BY AN EARLIER ROW, by a row stored after the decision",
            "ern-under": "TAKEN AT D'S CLOSE BY AN EARLIER ROW or an ERN(D) reaction <= 0.96, by a row stored after the "
                         "decision",
            "news-night2": "NEW INFORMATION on D (an article naming the issuer, an 8-K or an insider buy), stored after "
                           "the decision"}
    moves: list[tuple[P.Program, str, str]] = []
    for prog in P.PROGRAMS:
        if prog.prereg != 5 or prog.family not in P.CLOSE_FAMILIES_5 or prog.entry_at != "close":
            continue
        if keep is not None and keep(prog):
            continue
        drop = skips.get(prog.family) or set()
        if not drop:
            continue
        for r in st.db.execute("SELECT event, cik FROM intents WHERE program=? AND version=? AND entry_day=? AND status IN "
                               "('planned', 'entered')", (prog.id, prog.version, day.isoformat())).fetchall():
            if r["cik"] and str(r["cik"]) in drop:
                moves.append((prog, str(r["event"]), whys[prog.family]))
    if not moves:
        return 0
    moved = 0
    with st.tx():
        for prog, event, why in moves:
            moved += bool(st.move_intent(prog.id, prog.version, event, "skipped:taken", why))
    return moved


def five_programs() -> list[P.Program]:
    """PREREG-EVL-5's programs, every one a close-entry program (`decide_close`'s last part decides them)."""
    return [p for p in P.PROGRAMS if p.prereg == 5 and p.entry_at == "close" and p.family in P.CLOSE_FAMILIES_5]


def _pre_tails(st: S.Store, day: dt.date, survivors: set[str]) -> dict[str, Any] | None:
    """What the close decision added to the session's pre-pass (meta `evl5:pre:<day>`): its cut, and the attention
    issuers that survive NO NEW INFORMATION now and did not then (`added`: an attention article stored after the cut)
    and those that did then and do not now (`removed`: the tails of (i)-(iii)). None with no pre-pass stored."""
    raw = st.meta(f"{PRE_KEY}{day.isoformat()}")
    if raw is None:
        return None
    try:
        pre = json.loads(raw)
        before = {str(c) for c in pre.get("survivors") or []}
    except (TypeError, ValueError, AttributeError):
        return {"unreadable": True}
    return {"cut": pre.get("cut"), "added": len(survivors - before), "removed": len(before - survivors)}


def decide_close(ctx: Context, day: dt.date, *, backfill_run: bool = False, ask_only: bool = False,
                 evl4_only: bool = False, births_only: bool = False, evl5_only: bool = False) -> dict[str, Any]:
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
    PREREG row, PREREG-EVL-4's part not run); its receipt `decide-close-births:<day>` (screen.BIRTHS_KIND).

    PREREG-EVL-5'S PART RUNS LAST, UNDER ITS OWN TIME BOUND, ISOLATED (its section 1.3, "the earlier rows' decision comes
    first"): after every earlier row and PREREG-EVL-4's part, its reads (`_rows_5`: ERN(D), DAY(D), the attention
    articles of P and NO NEW INFORMATION's windows, with no registration floor for the sets that skip; the eligibility of
    its own issuers, the T29 and 09:30 minutes, the verdicts section 1.2 says it asks), `_skip_taken_5` and its programs'
    intents run under `EVL5_BUDGET` seconds and never past the task's bound (`Context.deadline`) less `EVL5_FINISH`
    (`bounded`: `PartDeadline`). Its bound's expiry, or any other exception in it that is not the task's own `Deadline`,
    is its own: the decision finishes with the earlier rows' results (PREREG-EVL-1 to -4 and the births, whole), the
    error in the summary's `evl5_error`, and PREREG-EVL-5's programs NAMED NOWHERE in it, so the judge reads that close as
    made without their rows (league/events/screen.py `final_until`, `made_without(prereg=5)`), `decide-close-evl5`
    decides them by themselves, and real money never trades that close's events of them (league/events/book.py
    `part_hold`). With `ask_only` the part is the same reads under `EVL5_PRE_BUDGET`, and, for a live decision from
    D's 09:30 minute on the tape (`pre_from`), EVL-NEWS-NIGHT2-ON'S HEAVY READS made ahead (the eligibility of its
    surviving attention issuers and their 09:30 minutes, each stored as read; meta `evl5:pre:<day>` written last, the
    summary's `evl5_pre`); inside `EVL5_PRE_URGENT` of the decision only once the earlier rows' verdicts are all stored.
    What counts is the stored record at D's close decision time, wherever it is read: the close decision reads every
    window whole from the store (the pre-pass's reads and the rows stored after it), and the network reads the pre-pass
    made are read as stored.

    `evl5_only`: PREREG-EVL-5'S ROWS DECIDED BY THEMSELVES, for a close a release without them decided, or whose part
    failed (`screen.made_without(prereg=5)`; the House's lane and the CLI's catchup run it once, as a backfill): the
    decision's reads and its eligibility call as the whole decision makes them, then that part alone, under the task's
    bound only (no own bound: the part is the decision), NO EARLIER ROW's verdict asked or intent written; its receipt
    `decide-close-evl5:<day>` (screen.FIVE_KIND); its exception is the decision's own and propagates."""
    if sum((evl4_only, births_only, evl5_only)) > 1:
        raise ValueError("a decision of one file's rows by themselves, or of the births by themselves: one at a time")
    st = ctx.store
    session = C.session(st, day)
    if session is None:
        return {"skipped": "no session"}
    kind = (SN.FOUR_KIND if evl4_only else SN.FIVE_KIND if evl5_only else SN.BIRTHS_KIND["close"] if births_only
            else "close")
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

    def five_part() -> None:
        """PREREG-EVL-5's part of the decision (the docstring): its reads (`_rows_5`), `_skip_taken_5`, its programs'
        intents and what each of its kept programs leaves out, held to the part's own bound (`bounded`)."""
        progs = five_programs()
        if not progs:
            return
        if evl5_only:
            sub, until = ctx, None
        else:
            until = part_until(ctx, EVL5_PRE_BUDGET if ask_only else EVL5_BUDGET)
            sub = bounded(ctx, until)
        mono = getattr(ctx, "mono", None) or time.monotonic

        def check(where: str) -> None:
            if until is not None and mono() >= until:
                raise PartDeadline(f"PREREG-EVL-5's part ran past its own time bound before {where}")
        check("its reads")
        active = [p for p in progs if kept(p) is None]
        earnings = any(p.family in P.FAMILY_ERN_5 for p in active)
        night2 = any(p.family == "news-night2" for p in active)
        live = not backfill_run
        pre = False
        if ask_only and night2:
            pre = live and ctx.now() >= pre_from(session) and (
                ctx.now() < session.close_decide - EVL5_PRE_URGENT or not out["pending"])
            night2 = pre
        cut = ctx.now()
        f = _rows_5(sub, day, by_ticker, {**elig, **elig4}, live=live, ask_only=ask_only,
                    earnings=earnings or not ask_only, night2=night2 or not ask_only, fetch_earnings=earnings,
                    fetch_night2=night2, needed=needed, unanswered=unanswered, check=check)
        check("its intents")        # (reads that ended past the bound expire the part; its writes are never cut)
        if pre:
            out["evl5_pre"] = {"status": "stored", "cut": S.iso(cut), "survivors": len(f["survivors"]),
                               "eligible": f["counts"].get("survivors_eligible", 0),
                               "marks": f["counts"].get("marks_0930", 0)}
            st.set_meta(f"{PRE_KEY}{day.isoformat()}", json.dumps(
                {"cut": S.iso(cut), "survivors": sorted(f["survivors"]), "attention": f["counts"].get("attention", 0),
                 "eligible": f["counts"].get("survivors_eligible", 0), "marks": f["counts"].get("marks_0930", 0)},
                sort_keys=True))
        if not ask_only:
            late = _skip_taken_5(st, day, f["skips"], keep=lambda prog: kept(prog) is not None)
            if late:
                out["skipped_taken"] = late
        table = f["elig"]

        def read5(row: Mapping[str, Any]) -> int | None:
            got = V.stored(st, f"8k:{row['accession']}", V.PROMPTS["doc"]) if row.get("accession") else None
            return got["score"] if got and got["status"] == "ok" else None

        def guidance5(row: Mapping[str, Any]) -> str | None:
            got = V.stored(st, f"8k:{row['accession']}", V.PROMPTS["doc"]) if row.get("accession") else None
            return got["guidance"] if got and got["status"] == "ok" else None

        def react5(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
            return f["reactions"].get(str(row.get("accession")))

        def gap5(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
            return f["gaps"].get(str(row.get("cik")))
        for prog in progs:
            rows = [r for r in f["rows"][prog.family] if S.parse_iso(r["knowable_at"]) > prog.registered_at]
            frozen = kept(prog)
            if frozen is not None:     # (A66 owed, a look of its group: asked nothing, fetched nothing, written nothing)
                out.setdefault("kept", {})[_key(prog)] = frozen
                if not ask_only:
                    out["kept"][_key(prog)] |= _left_out(st, prog, rows, eligible=lambda c: table.get(c),
                                                         guidance=guidance5, reaction=react5, gap=gap5)
                continue
            waiting = int(f["pending"].get(prog.id) or 0)
            if waiting:
                out["pending"][_key(prog)] = waiting   # decided by a later pass, once every answer it waits for is stored
                continue
            if ask_only:
                continue
            cands = P.select(prog, rows, eligible=lambda c: table.get(c), verdict=read5, reaction=react5,
                             guidance=guidance5, gap=gap5)
            out[_key(prog)] = P.write_intents(st, prog, day, cands, decided_at=session.close_decide, why=why)
        out["evl5"] = f["counts"] | ({"pre": _pre_tails(st, day, f["survivors"])} if not ask_only else {})

    # THE EARLIER ROWS FIRST, exactly as before PREREG-EVL-4 (their reads, verdicts and intents), then PREREG-EVL-4's
    # part (`four_part`), whose own reads come after them; an exception in that part other than the task's time bound
    # finishes the decision with the earlier rows' results and leaves PREREG-EVL-4's programs unnamed (the docstring,
    # A83 (3)(i)). A program a written look of its group freezes (`_scope`, A74 (5)) is kept in either part: asked
    # nothing, fetched nothing, written nothing (no intent, no `skipped:excluded` move: `_skip_excluded` passes it
    # over). R3's registered births (close entry: ern-react, news-day, news-react) are decided in the earlier part,
    # after every PREREG row.
    if not evl4_only and not evl5_only:       # (one file's rows by themselves: no earlier row is decided again)
        for prog in P.PROGRAMS:
            if prog.entry_at == "close" and prog.family not in P.CLOSE_FAMILIES_4 and \
                    prog.family not in P.CLOSE_FAMILIES_5 and not (births_only and prog.spec is None):
                _decide_one(prog, lambda prog: one(prog, False), out)
    try:
        if not births_only and not evl5_only:     # (the births, or PREREG-EVL-5's rows, by themselves: no PREREG-EVL-4 row)
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
    # PREREG-EVL-5's part LAST (its section 1.3), under its own bound; its failure or expiry is its own (the docstring)
    try:
        if not births_only and not evl4_only:
            five_part()
    except Deadline:
        raise
    except Exception as exc:  # noqa: BLE001 - PREREG-EVL-5's part fails alone (section 1.3); never with evl5_only
        if evl5_only:
            raise
        out["evl5_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        if ask_only and "evl5_pre" not in out:
            out["evl5_pre"] = {"status": "cut" if isinstance(exc, PartDeadline) else "error", "why": out["evl5_error"]}
        for prog in five_programs():
            for where in (out, out["pending"], out.get("kept") or {}):
                where.pop(_key(prog), None)
        out.pop("evl5", None)
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
           "waits_on_open", "Deadline", "PM_ASKER", "PartDeadline", "EVL5_BUDGET", "EVL5_PRE_BUDGET", "EVL5_FINISH",
           "EVL5_PRE_URGENT", "PRE_KEY", "GAP_LABEL", "part_until", "bounded", "pre_from", "five_programs"]

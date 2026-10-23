"""THE DECISION SCHEDULER (release 1019i, A120): one pre-registered slot per file at each auction.

THE PROBLEM IT REMOVES. The House made ONE open decision (09:15 ET) and ONE close decision (its first tick at or after
15:47:00 ET; orders sent by 15:49:00 ET: league/events/house.py, run.py, league/equity/live.py's event book). Each new
pre-registration added its own isolated part INSIDE that one decision (PREREG-EVL-5: 45 s; PREREG-EVL-7's learners:
90 / 120 s; PREREG-EVL-8's PX 60 s and META 30 s; PREREG-EVL-9's warm part), and both PREREG-EVL-7's and -8's re-checks
found that the parts cannot all fit before the send line, that a part's bound is measured from its own start, and
that a late part delays or loses real money for the rows behind it.

THE DESIGN. A TIMING TABLE, one pinned constant per auction (`TABLE`, its sha256 `digest()`): each file's part runs in
ITS OWN DECISION RUN with a pre-registered start, its own bound measured from its own start, and the book's send window
for that file, so no part can delay or cut another:

- THE MAIN SLOT (file "main": every row of PREREG-EVL-1 to -6 and R3's births) keeps EXACTLY today's timing: the open
  decision at 09:15:00 ET with DECIDE_BUDGET, its buys sent 09:16:00-09:27:00; the close decision at the close - 13
  minutes (15:47:00 ET on a full day: the close - 14 minutes + CLOSE_GRACE), its buys sent to the close - 11 minutes.
  The main slot's row is read from the same constants the House and the book run on (`main_rows`), and a test pins the
  table's main rows to them, so its intents and picks are byte-identical to the path before this module (the
  simulation test, league/tests/test_events_scheduler.py).
- A FILE'S SLOT (`Slot`): starts at a wall time of the session (`Wall`: an offset from the session's own open or close,
  so an early close moves every close-side row with the session), or on the finish of the slots it names (`after`: the
  main receipt finished `ok` or `pending`, any other named slot's live receipt finished, whatever its status), never
  before `not_before` and NEVER PAST `never_past`: a slot whose start has not come by then is MISSED. Its bound
  (`bound`) is measured from its own start. The book sends the file's buys only inside [`send_from`, `send_until`)
  (`send_window`), each file its own window. A slot that starts before the main decision of its auction (PREREG-EVL-8's
  PX-ON at 15:46:00) runs as a task the House bounds to end DECISION_MARGIN before the main decision (house.py
  `_deadline`), so it never delays the main rows; one that starts after it never cuts them (they are decided and
  their receipt finished before it starts).
- ITS OWN RECEIPTS: the live run's `decide-<auction>-<file>:<day>` (`Slot.kind`; the frozen texts may pin another
  name: PREREG-EVL-7's `decide-open-lrnlive:<D>`), the catch-up's `Slot.catchup` (`decide-<auction>-<file>-cu:<day>`
  by default). A live run that failed, was cut at its bound or never started by `never_past` is FINAL for that auction:
  the House writes a `missed` receipt when the window closed with no run, warns (an alarm), and the file's rows of
  that auction are decided later by themselves as a CATCH-UP under their own receipt, shadow only, never traded
  (league/equity/live.py's event book plans a file's buys only from a live receipt finished `ok` or `pending`).
- THE PARTS (`Part`): a file's code registers its part (`register`): the live part, the catch-up, which program ids
  are its (`programs`; the book reads `file_of` to keep them out of the main pass), and from when its catch-ups are
  owed (`since`). A slot in the table with no registered part is inert: documented, never run, never alarmed. So the
  branches that add their files (feat/evl-6, feat/evl-7, feat/evl-8) adopt the scheduler with small diffs: a row in
  `TABLE` and one `register` call (docs/SCHEDULER.md).
- PRE-PASSES (`prepass` True): a file's reads made ahead of its decision on data knowable then (PREREG-EVL-8's
  `prepass-meta:open:<D>` from 09:00:00, `px-am:<D>` from 09:05:00; PREREG-EVL-9's `prepass-warm9`), run as the House's
  lowest-priority task between `start` and `never_past`, bounded to end before any decision, their receipt their own
  (`Slot.kind`), with no intent, no send window and no catch-up; a pre-pass not done by `never_past` is simply not
  done (its part computes what it needs itself, or trades nothing: the file's text says which).

Every time here is a wall-clock offset of the session (`Wall`), never a bound measured from another part's start.
`check(table)` holds the invariants (a test runs it on `TABLE`): one main slot an auction, every file once an auction,
`send_until` at or before the auction's own cut-off, a clock-started slot's `never_past` at or after its start, a
slot that starts before the main decision ending (`start + bound`) DECISION_MARGIN before it, `after` names only
earlier rows, no cycle. `worst_case(table, auction)` gives each slot's latest start and finish when every part before
it runs to its bound (the docs' timing table reads it): the honest statement of which files can miss their window
on a bad day. Python's standard library only.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping

from . import calendar as C

MAIN = "main"
AUCTIONS = ("open", "close")
#: A task never runs into a decision: a slot before the main decision ends this long before it (house.py's margin).
DECISION_MARGIN = 5.0
#: The receipt status the House writes for a slot whose window closed with no live run (`missed_receipt`).
MISSED = "missed"
#: The live receipt statuses that make a slot MADE at its auction: the book plans the file's buys from them.
MADE = ("ok", "pending")
#: The statuses of a live run that are FINAL for the auction without being made (decided later by the catch-up).
FINAL_UNMADE = ("failed", "cut", MISSED)


@dataclasses.dataclass(frozen=True)
class Wall:
    """A moment of a session: `seconds` after (negative: before) its `anchor` ("open" | "close"). Every close-side
    row of the table is anchored on the close, so an early close (13:00 ET) moves it by (close - 16:00)."""

    anchor: str
    seconds: int

    def at(self, session: C.Session) -> dt.datetime:
        base = session.open_at if self.anchor == "open" else session.close_at
        return base + dt.timedelta(seconds=int(self.seconds))

    def epoch(self, open_at: float, close_at: float) -> float:
        return (open_at if self.anchor == "open" else close_at) + float(self.seconds)

    def text(self, early: bool = False) -> str:
        """The New York wall time on a full day (or an early-close day), "HH:MM:SS"."""
        base = dt.datetime(2026, 1, 5, 9, 30) if self.anchor == "open" else dt.datetime(2026, 1, 5, 13 if early else 16, 0)
        return (base + dt.timedelta(seconds=int(self.seconds))).strftime("%H:%M:%S")


@dataclasses.dataclass(frozen=True)
class Slot:
    """One file's row of an auction (the module docstring)."""

    file: str
    auction: str
    bound: float
    kind: str                           # the live receipt kind: `decide-<kind>:<day>`
    start: Wall | None = None           # a clock start; None: on the finish of `after`'s receipts
    after: tuple[str, ...] = ()
    not_before: Wall | None = None
    never_past: Wall | None = None      # the latest start; past it the slot is missed
    send_from: Wall | None = None       # the book's send window of the file's buys (None: no buys, a pre-pass)
    send_until: Wall | None = None
    catchup: str | None = None          # the catch-up receipt kind; None: no catch-up (main has its own machinery)
    prepass: bool = False
    note: str = ""

    @property
    def job(self) -> str:
        """The receipt job of a live run: `decide-<kind>`; a pre-pass's receipt is its kind itself."""
        return self.kind if self.prepass else f"decide-{self.kind}"

    @property
    def catchup_job(self) -> str | None:
        return None if self.catchup is None else f"decide-{self.catchup}"

    def receipt(self, day: dt.date) -> str:
        return f"{self.job}:{day.isoformat()}"

    def catchup_receipt(self, day: dt.date) -> str | None:
        return None if self.catchup is None else f"{self.catchup_job}:{day.isoformat()}"

    def as_dict(self) -> dict[str, Any]:
        out = dataclasses.asdict(self)
        return {k: v for k, v in out.items() if v not in (None, (), "", False)}


@dataclasses.dataclass(frozen=True)
class Part:
    """A file's code, registered by its own module (`register`): `run(ctx, day, auction, slot, rid)` decides the
    file's rows of that auction LIVE under the slot's bound and returns the receipt's summary (it names the file's
    programs as the file's judge reads them); `catchup(ctx, day, auction, slot, rid)` decides them BY THEMSELVES later
    (shadow only; None: no catch-up); `programs()` the ids of its programs (the book keeps them out of the main pass);
    `since()` from when its catch-ups are owed (the file's registration time; None: not yet, nothing of it runs)."""

    file: str
    run: Callable[..., Mapping[str, Any]]
    catchup: Callable[..., Mapping[str, Any]] | None = None
    programs: Callable[[], Iterable[str]] = lambda: ()
    since: Callable[[], dt.datetime | None] = lambda: None
    prepass: Callable[..., Mapping[str, Any]] | None = None


#: The registered parts, by file (the main slot has none: the House's own decisions are its machinery).
PARTS: dict[str, Part] = {}
#: THE FILES' MODULES (release 1019n-r2): each registers its part and adds its row at its own import. Every reader of
#: the parts (`file_of`, `live_files`, `prepasses`) imports them first (`load_parts`), so no reader of the table, the
#: House's lane or the book's pass, ever sees a file's program as a main row because nothing had imported its module
#: yet (a later file's program in the main pass would be planned in ROOM's earlier place: the reading that trades MORE).
#: PREREG-EVL-10's READER-2 (league/events/reader2.py) is the first.
PART_MODULES: tuple[str, ...] = ("league.events.reader2",)
_LOADED: list[str] = []


def load_parts() -> None:
    """Import every module of `PART_MODULES` once (each registers its part at import). A module that cannot be imported
    raises: a reader that cannot say which file decides a program must not read it as the main file's."""
    import importlib

    for name in PART_MODULES:
        if name not in _LOADED:
            importlib.import_module(name)
            _LOADED.append(name)


def register(part: Part) -> Part:
    """Register a file's part (its module calls this at import, or a test in its setUp). The same file registered
    again replaces its part (a reload). Never the main file."""
    if part.file == MAIN:
        raise ValueError("the main slot is the House's own decision: it registers no part")
    PARTS[part.file] = part
    return part


def unregister(file: str) -> None:
    PARTS.pop(file, None)


def file_of(program: Any) -> str:
    """Which file's slot decides `program` (a Program or an id): the registered part that claims it, else "main"."""
    load_parts()
    pid = getattr(program, "id", program)
    for file, part in PARTS.items():
        try:
            if str(pid) in {str(p) for p in part.programs()}:
                return file
        except Exception:  # noqa: BLE001 - a part that cannot say claims nothing
            continue
    return MAIN


# ----------------------------------------------------------------------------------------------------- the table
def main_rows() -> tuple[Slot, Slot]:
    """THE MAIN SLOT'S ROWS, read from the constants the House and the book already run on (league/events/calendar.py,
    league/equity/schedule.py `EVENT_DEFAULTS`, the House's DECIDE_BUDGET and CLOSE_GRACE), so the table cannot state
    a main timing other than today's: the open decision at OPEN_DECIDE_AT with its DECIDE_BUDGET, its sends from the
    book's open send to its open cut-off; the close decision at CLOSE_DECIDE_BEFORE + CLOSE_GRACE before the close with
    the same budget, its sends from the book's close send to its cut-off."""
    from ..equity import schedule as ES

    off = ES.EVENT_DEFAULTS
    open_start = -int((dt.datetime.combine(dt.date(2026, 1, 5), dt.time(9, 30))
                       - dt.datetime.combine(dt.date(2026, 1, 5), C.OPEN_DECIDE_AT)).total_seconds())
    close_grace = 60      # house.CLOSE_GRACE (a minute: the 15:30 bar is on the tape at 15:46), pinned by a test
    budget = 150.0        # house.DECIDE_BUDGET, pinned by a test
    return (
        Slot(MAIN, "open", budget, "open", start=Wall("open", open_start),
             send_from=Wall("open", -off["open_send_before_open_s"]), send_until=Wall("open", -off["open_until_before_open_s"]),
             note="every row of PREREG-EVL-1 to -6 and R3's births, as today (league/events/run.py decide_open)"),
        Slot(MAIN, "close", budget, "close",
             start=Wall("close", -int(C.CLOSE_DECIDE_BEFORE.total_seconds()) + close_grace),
             send_from=Wall("close", -off["close_send_before_close_s"]),
             send_until=Wall("close", -off["close_until_before_close_s"]),
             note="every row of PREREG-EVL-1 to -6 and R3's births; PREREG-EVL-4's and -5's parts inside it, as today "
                  "(league/events/run.py decide_close; PREREG-EVL-5's 45 s part and `part_hold` unchanged)"),
    )


#: THE TIMING TABLE: one pinned constant per auction, the main slot first, then each file's slot in the order its
#: part runs (`after` names earlier rows only). The main rows are the House's own constants (`main_rows`). The rows
#: of the files whose texts are frozen or drafted (PREREG-EVL-7's learners, PREREG-EVL-8's PX and META, PREREG-EVL-9's
#: warm learners) are added BY THEIR BRANCHES beside their `register` call, from their frozen timing tables
#: (docs/SCHEDULER.md lists the rows each text implies); until a part is registered a row is inert.
TABLE: dict[str, tuple[Slot, ...]] = {
    "open": (main_rows()[0],),
    "close": (main_rows()[1],),
}
#: PREREG-EVL-10 SECTION 2.4, FROZEN (docs/prereg/PREREG-EVL-10.md on the tag `prereg-evl-10`): "`decide-close-r2:<D>`
#: is THIS FILE'S SLOT in the decision scheduler's close table ... `scheduler.Slot("evl10", "close", 10.0, "close-r2",
#: start=Wall("close", -1200), never_past=Wall("close", -940), send_from=Wall("close", -780), send_until=Wall("close",
#: -660), catchup=None)`, the LAST row of the close table": a clock start at tau (the close - 20 minutes, 15:40:00 ET
#: on a full day), a bound of 10 seconds, never started past the close - 15 minutes 40 seconds (15:44:20 ET), so it
#: ends by 15:44:30 (HOLD_LEAD's lead) and DECISION_MARGIN before the lane's close decision; the send window
#: [15:47:00, 15:49:00) of the main rows; NO CATCH-UP (a session whose slot did not run live has no decision of this
#: file's rows). Its part is league/events/reader2.py's (`PART_MODULES`); a later file's row goes BEFORE it.
TABLE["close"] = TABLE["close"] + (
    Slot("evl10", "close", 10.0, "close-r2", start=Wall("close", -1200), never_past=Wall("close", -940),
         send_from=Wall("close", -780), send_until=Wall("close", -660), catchup=None),)


def slots(auction: str, table: Mapping[str, tuple[Slot, ...]] | None = None) -> tuple[Slot, ...]:
    return tuple((TABLE if table is None else table).get(auction, ()))


def slot(file: str, auction: str, table: Mapping[str, tuple[Slot, ...]] | None = None) -> Slot | None:
    for s in slots(auction, table):
        if s.file == file:
            return s
    return None


def main_slot(auction: str, table: Mapping[str, tuple[Slot, ...]] | None = None) -> Slot:
    found = slot(MAIN, auction, table)
    if found is None:
        raise LookupError(f"the {auction} auction has no main slot")
    return found


def live_files(auction: str, table: Mapping[str, tuple[Slot, ...]] | None = None) -> list[Slot]:
    """The non-main, non-pre-pass slots of `auction` whose part is registered and whose `since` is set (the ones the
    House runs and the book plans buys for), in table order."""
    load_parts()
    out = []
    for s in slots(auction, table):
        if s.file == MAIN or s.prepass:
            continue
        part = PARTS.get(s.file)
        if part is None:
            continue
        try:
            if part.since() is None:
                continue
        except Exception:  # noqa: BLE001
            continue
        out.append(s)
    return out


def prepasses(auction: str, table: Mapping[str, tuple[Slot, ...]] | None = None) -> list[Slot]:
    """The pre-pass rows of `auction` whose part is registered with a `prepass` and whose `since` is set."""
    load_parts()
    out = []
    for s in slots(auction, table):
        if not s.prepass:
            continue
        part = PARTS.get(s.file)
        if part is None or part.prepass is None:
            continue
        try:
            if part.since() is None:
                continue
        except Exception:  # noqa: BLE001
            continue
        out.append(s)
    return out


def canonical(table: Mapping[str, tuple[Slot, ...]] | None = None) -> str:
    """The table as canonical JSON (sorted keys, no whitespace): what `digest` pins."""
    t = TABLE if table is None else table
    return json.dumps({a: [s.as_dict() for s in t.get(a, ())] for a in AUCTIONS}, sort_keys=True, separators=(",", ":"))


def digest(table: Mapping[str, tuple[Slot, ...]] | None = None) -> str:
    """The sha256 of `canonical` (its first 8 hex in the docs' timing table): a row that moves moves the digest."""
    return hashlib.sha256(canonical(table).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------ the invariants
def check(table: Mapping[str, tuple[Slot, ...]] | None = None) -> list[str]:
    """The table's invariants (the module docstring); [] when it holds, else each problem in words."""
    t = TABLE if table is None else table
    problems: list[str] = []
    for auction in AUCTIONS:
        rows = t.get(auction, ())
        mains = [s for s in rows if s.file == MAIN]
        if len(mains) != 1:
            problems.append(f"{auction}: {len(mains)} main slots (one is required)")
            continue
        main = mains[0]
        if rows[0].file != MAIN:
            problems.append(f"{auction}: the main slot is not the first row")
        if main.start is None or main.send_from is None or main.send_until is None:
            problems.append(f"{auction}: the main slot has no clock start or no send window")
            continue
        cutoff = main.send_until
        seen: set[str] = set()
        kinds: set[str] = set()
        for i, s in enumerate(rows):
            if s.auction != auction:
                problems.append(f"{auction}: {s.file} is a row of the {s.auction} auction")
            if s.file in seen:
                problems.append(f"{auction}: {s.file} has two rows")
            seen.add(s.file)
            for k in (s.kind, s.catchup):
                if k is not None:
                    if k in kinds:
                        problems.append(f"{auction}: the receipt kind {k} is used twice")
                    kinds.add(k)
            if s.bound <= 0:
                problems.append(f"{auction}: {s.file} has no bound")
            if s.start is None and not s.after:
                problems.append(f"{auction}: {s.file} has no clock start and names no slot to follow")
            for name in s.after:
                if name not in {r.file for r in rows[:i]}:
                    problems.append(f"{auction}: {s.file} follows {name}, which is not an earlier row")
            if s.prepass:
                if s.send_from is not None or s.send_until is not None or s.catchup is not None:
                    problems.append(f"{auction}: the pre-pass {s.file} has a send window or a catch-up")
                if s.start is None or s.never_past is None:
                    problems.append(f"{auction}: the pre-pass {s.file} needs a clock start and a never_past")
                continue
            if s.file != MAIN and (s.send_from is None or s.send_until is None):
                problems.append(f"{auction}: {s.file} has no send window")
            if s.send_until is not None and _secs(s.send_until, auction) > _secs(cutoff, auction):
                problems.append(f"{auction}: {s.file} sends after the auction's cut-off {cutoff.text()}")
            if s.send_from is not None and s.send_until is not None and _secs(s.send_from, auction) >= _secs(s.send_until, auction):
                problems.append(f"{auction}: {s.file}'s send window is empty")
            if s.file != MAIN and s.never_past is None:
                problems.append(f"{auction}: {s.file} has no never_past (a slot must be missable)")
            if s.start is not None and s.never_past is not None and _secs(s.never_past, auction) < _secs(s.start, auction):
                problems.append(f"{auction}: {s.file}'s never_past is before its start")
            # (release 1019n-r2: a file may have NO catch-up, `catchup` None: PREREG-EVL-10's text, whose session with no
            # live run has no decision of its rows at all; a file with one names its kind)
            # a slot that starts before the main decision must end DECISION_MARGIN before it, whatever happens
            if s.file != MAIN and s.start is not None and _secs(s.start, auction) < _secs(main.start, auction):
                latest = (_secs(s.never_past, auction) if s.never_past is not None else _secs(s.start, auction)) + s.bound
                if latest > _secs(main.start, auction) - DECISION_MARGIN:
                    problems.append(f"{auction}: {s.file} starts before the main decision but can run into it "
                                    f"(latest finish {latest:.0f} s, the margin ends at "
                                    f"{_secs(main.start, auction) - DECISION_MARGIN:.0f} s)")
                if MAIN in s.after:
                    problems.append(f"{auction}: {s.file} starts before the main decision yet follows it")
    return problems


def _secs(w: Wall, auction: str) -> float:
    """A wall as seconds from the auction's own moment (the open at 0 for the open, the close at 0 for the close)."""
    if w.anchor == auction:
        return float(w.seconds)
    # (an open-anchored wall on the close side or the reverse: on a full day the open is 23,400 s before the close)
    return float(w.seconds) + (-23_400.0 if w.anchor == "open" else 23_400.0)


# ----------------------------------------------------------------------------------------------- the clock reads
def window(s: Slot, session: C.Session, after_finished: Mapping[str, dt.datetime | None] | None = None
           ) -> tuple[dt.datetime | None, dt.datetime | None]:
    """(the slot's start, its latest start) of `session`: a clock start as its wall; a follower's start is the latest
    finish of the slots it names (`after_finished`: file -> when its receipt finished, None while it has not), clamped
    to `not_before`; None while a named slot has not finished. The latest start is `never_past` (None: unbounded)."""
    latest = s.never_past.at(session) if s.never_past is not None else None
    if s.start is not None:
        start = s.start.at(session)
    else:
        finished = [((after_finished or {}).get(f)) for f in s.after]
        if any(f is None for f in finished):
            return None, latest
        start = max(f for f in finished if f is not None)
    if s.not_before is not None:
        start = max(start, s.not_before.at(session))
    return start, latest


def deadline_at(s: Slot, started: dt.datetime, session: C.Session) -> dt.datetime:
    """When a live run started at `started` must end: its bound from its own start, and never past the auction's own
    cut-off for its sends when it has one (a decision past the send line can send nothing anyway)."""
    end = started + dt.timedelta(seconds=float(s.bound))
    return end


def send_window(s: Slot, open_at: float, close_at: float) -> tuple[float, float] | None:
    """The file's send window of a session as epoch seconds (the book's reading), None for a pre-pass."""
    if s.send_from is None or s.send_until is None:
        return None
    return s.send_from.epoch(open_at, close_at), s.send_until.epoch(open_at, close_at)


def worst_case(auction: str, table: Mapping[str, tuple[Slot, ...]] | None = None, *,
               overrun: float = 0.0) -> list[dict[str, Any]]:
    """Each slot's LATEST start and finish on a full day when every part before it runs to its bound (plus `overrun`
    seconds a read can return after a bound: the gateway's timeout), and whether its sends can still fit before its
    `send_until`: the honest line of the docs' timing table. Seconds are New York wall-clock of a full day."""
    rows = [s for s in slots(auction, table) if not s.prepass]      # (a pre-pass ends before any decision)
    done: dict[str, float] = {}
    out: list[dict[str, Any]] = []
    # THE LANE RUNS ONE TASK AT A TIME: the slots run in the order of their nominal starts (a clock start, or the
    # finish of the slots a follower names), the table's order among equals, each after the one before it finished.
    pending = list(rows)
    last_finish = float("-inf")
    while pending:
        nominal: list[tuple[float, int, Slot]] = []
        for i, s in enumerate(pending):
            if s.start is not None:
                at = _secs(s.start, auction)
                if any(f not in done for f in s.after):
                    continue
                at = max([at] + [done[f] for f in s.after])
            else:
                if any(f not in done for f in s.after):
                    continue
                at = max(done[f] for f in s.after)
            if s.not_before is not None:
                at = max(at, _secs(s.not_before, auction))
            nominal.append((at, i, s))
        if not nominal:
            break       # (a follower of a row that never runs: `check` refuses such a table)
        at, i, s = min(nominal, key=lambda x: (x[0], x[1]))
        pending.pop(i)
        start = max(at, last_finish)
        missed = s.never_past is not None and start > _secs(s.never_past, auction)
        finish = start + s.bound + overrun
        done[s.file] = finish
        last_finish = finish
        fits = None
        if s.send_until is not None:
            fits = finish <= _secs(s.send_until, auction)
        out.append({"file": s.file, "start": _clock(auction, start), "finish": _clock(auction, finish),
                    "missed_at_worst": missed, "sends_fit_at_worst": fits,
                    "send_until": None if s.send_until is None else s.send_until.text()})
    return out


def _clock(auction: str, seconds: float) -> str:
    base = dt.datetime(2026, 1, 5, 9, 30) if auction == "open" else dt.datetime(2026, 1, 5, 16, 0)
    return (base + dt.timedelta(seconds=float(seconds))).strftime("%H:%M:%S")


def table_text(table: Mapping[str, tuple[Slot, ...]] | None = None) -> str:
    """The table as the docs print it (docs/events.md's timing table): one markdown table per auction."""
    lines = []
    for auction in AUCTIONS:
        lines.append(f"**The {auction} auction** (times ET on a full day; an early close moves every close-side row with "
                     "the session):")
        lines.append("")
        lines.append("| file | starts | never past | bound | sends | receipt | catch-up | after |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for s in slots(auction, table):
            start = s.start.text() if s.start is not None else "on " + ", ".join(s.after) + "'s receipt"
            if s.not_before is not None:
                start += f", not before {s.not_before.text()}"
            never = s.never_past.text() if s.never_past is not None else "-"
            sends = (f"{s.send_from.text()}-{s.send_until.text()}" if s.send_from is not None and s.send_until is not None
                     else "none (a pre-pass)" if s.prepass else "-")
            lines.append(f"| {s.file} | {start} | {never} | {s.bound:.0f} s | {sends} | `{s.job}:<day>` | "
                         f"{'`' + s.catchup_job + ':<day>`' if s.catchup_job else '-'} | {', '.join(s.after) or '-'} |")
        lines.append("")
    return "\n".join(lines)


__all__ = ["MAIN", "AUCTIONS", "DECISION_MARGIN", "MISSED", "MADE", "FINAL_UNMADE", "Wall", "Slot", "Part", "PARTS",
           "PART_MODULES", "load_parts", "register", "unregister", "file_of", "main_rows", "TABLE", "slots", "slot", "main_slot", "live_files",
           "prepasses", "canonical", "digest", "check", "window", "deadline_at", "send_window", "worst_case",
           "table_text"]

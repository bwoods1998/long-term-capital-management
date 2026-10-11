"""The `forward_shadow` job: every registered program recomputed whole each night on its own forward days (release E3).

Owner: B (league/ops/E3_INTERFACES.md). Protected. After the daily store (`equity_data`, 22:30Z), never inside
09:00-17:30 New York time on a session (`quiet`); in a pause too. It writes `fwd_days`, `fwd_checks` and `fwd_runs` of
`<state>/forward.sqlite` (league/ops/forward_db.py) and its events; it moves no money, gates nothing and judges
nothing.

THE SHADOW RUN (D3). `cap = mint_equity_gate_capability(store_root, GATE_REASON)`; `bars = EquityStore(store_root,
gate=cap).bars(needs.symbols, "forward", history=needs.history + 1, start=first_day(p), end=None)` (a forward slice
without the capability raises `StoreRefused`; one asked from before `forward_db.t0()` is refused here, a ValueError).
The run is `decider.kind("equity", "run", {"code", "params", "name": key, "bars", "k", "capital": None},
budget_seconds=run_budget_seconds)` at k = `config.K_BASE` and again at `config.K_STRESS`: E1's engine from
`first_day`, flat, STATE fresh, recomputed whole every night, in THE JOB'S OWN decider child
(`Decider(log=<root>/forward-decider.log)`: never the live process's decider and never `elane.isolated_runner`; it
inherits the job's `RLIMIT_CPU` and nice and runs as E1's `Decider` runs any child). `s = screen.series(result["lots"],
bars, universe=list(needs.symbols), capital=result["capital"])`. For run session i: `r = s.r[i]`, `w = s.w[i]`, `b =
s.b[i]`, `r15` = the k 1.5 run's `s.r[i]`, `entries` = lots with that `entry_day`, `exits = s.exits[i]`, `status` =
the k 1.0 result's, `engine` = tonight's id (`forward_db.fwd_engine`, `engine_id`), `bars` = `forward_db.bars_hash`
of the decision the day's orders came from (the Gym's inputs at the close of the session before it,
`ctx.inputs_from_bars`; THE BARS HASH, league/ops/forward_db.py). EXCESS, everywhere in E3: x = r - w * b (daily; NOT
`screen.excess`, which subtracts a window mean).

THE FIRST DECISION (D2): a program first decides at the close of `first_close(p)`, the session before `first_day(p)`.
E1's engine decides from the slice's index `max(first - 1, 0)` on `ctx.inputs_from_bars`, which reads the NEEDS
history + 1 sessions ending at the decision when the slice holds them. So the slice carries NEEDS history + 1 sessions
before its first run session: a NEEDS history of 0 does not move the first decision to `first_day`'s close, and the
first decision reads the SAME bars the live book reads at that close (`ctx.inputs_from_fetch`: history + 1 sessions;
a slice with `history` sessions would give the first decision one bar fewer than every later one and than the live
one, a program that waits for its full history would then decide a session late in the shadow only, and the twin's
bars hash at an instance's first decision could never equal the live one). Every later decision is unchanged by it.
A slice with no session before its first run session is refused (a ValueError: the store's calendar starts there).

CHECKPOINTS (D4). A program's COUNTED days are its `fwd_days` rows of tonight's engine id with status "ok" and no
`audit_mismatch` event, in day order (`forward_db.counted_days`); its STORED days are those rows of any status.
Checkpoint n (in `forward_db.CHECKPOINTS`, then every `CHECKPOINT_EVERY`) is written on the first night the program
has n counted days and the n-th is before the store's last day (so its morning audit has run; THE MORNING MARKS,
MADE UP, below). Over the first n counted days: `t_r` = mean(r) / sd(r, ddof 1) * sqrt(n) (None when sd < 1e-12),
`sum_r`, `sum_r15`, `t_x` the same t of x, `mean_w`, `p_x = forward_stats.p_one_sided(t_x, n)` (None when `t_x` is
None). No verdict, no threshold. A FINAL checkpoint (`final` 1, n = its counted days, written once, when n >= 2 and
no row (pid, n) exists) is written for a program stopped off the grid, so no program leaves the record by failing.
THE CHECKPOINT OF RECORD for (pid, n) is the row written first, whatever engine later recomputes it. Sums and means
use `math.fsum`.

THE NIGHT (`Shadow.night`): `preflight`; `forward_register.sync`; `engine_id` (a new label: one `engine_moved` event,
and that night every active program's whole history is written again under the new id; rows of an older id stay and
are never read as the current series); `marks`; `forward_twins.begin`; `controls`; `finals`; `due()` in order until the child
seconds spent reach `cpu_seconds_night` or the clock is within 300 s of the next session's 09:00 ET (the rest are
`stale`: a `budget_hit` event, once a night); `forward_twins.on_run` after each `write`; THE RETRY;
`forward_twins.finish`; one `fwd_runs` row (`programs` = the programs whose run completed THAT NIGHT, whichever start
of the job ran them: what the registry's suspect rule reads beside `run_failed`, which is attributed the same way;
`sessions`, `errors`, `stale` and `seconds` are this start's own: the run sessions it recomputed, what it left, the
child seconds it spent; the receipt's `programs` is this start's too). Each league/ops/forward_twins.py call sits in
its own try/except: a twins failure never loses a shadow day; so do the registry's sync, the controls and the finals,
each named in the receipt when it failed.

THE MORNING MARKS, MADE UP (`Shadow.marks`). A checkpoint is the record a later verdict reads, written once, and it
must not count a day whose bars the book's morning re-fetch found different. The marks are the morning job's
(league/ops/forward_audit.py, 09:05 New York time, 40 minutes of grace): a morning it did not run, or ran before the
book's audit had finished, would leave a day unmarked on the night its checkpoint is due. So the night reads the
book the same way before any checkpoint is read (`forward_audit.mismatches`, `mark`: the book's audit of every day
before the store's last has run by then) and writes what the morning missed; an event is once a (pid, day), so what
the morning wrote is written by nobody twice. A book that cannot be read marks nobody and is named in the receipt.

A LABEL THAT RETURNS. Every reader of the record takes the NEWEST engine id as the current series
(`forward_db.engine_now`: the meters, the session caps of the stop rules, the twins). A label that already has a row
which is not the newest (the evidence identity went BACK to an earlier one after another series was opened: a
rollback) would be written under its old id, and every reader would go on reading a series nobody writes any more,
with no alarm. So a return opens a NEW series like any other move: its label in `fwd_engines` is `<label>~<the id it
follows>` (`RETURNED`), with one `engine_moved` event and the whole history written again under the new id; the rows
of the label's earlier series stay and are never read as the current one. While the identity then stays, the newest
row is that label's own and nothing moves.

WHOSE FAILURE (E2's RUN rule, carried over). A FAILURE NEVER MARKS A PROGRAM HERE: league/ops/forward_register.py
reads the events.
- The House's, before anything: `preflight` (the child answers `ping` AND `CANARY` runs "ok" over the store's last
  five forward days through the same child op); else `NightFailed`, one `night_failed` event (once a night), no
  `fwd_runs` row, no `run_failed`, nothing tagged.
- The data's (`MissingData`, `StoreRefused`, a `ValueError` from the slice or from `screen.series`: a held symbol with
  no price that session; a result of status "no_data"): one `data_failed` event (once a (pid, night), payload the
  class and the symbol), no row that night; the next night's whole recompute fills it once the store is repaired.
- The child's (`RunFailed`, `DeciderError`, no result, a result of status "error"): the program goes on the retry
  list. THE RETRY, after the due loop: `fresh()` gives a newly started decider, pinged; each listed program is run
  again alone while the budget allows. One that completes is written as any other. One that fails again gets a
  `run_failed` event (once a (pid, night); payload the class and `completed`) only when at least one other program's
  run completed that night; with none, or with a fresh child that does not ping, nothing is written for it.
- The forward store's own (a write that fails for another cause than the data): counted in the receipt's `errors`,
  never an event on the program.
- The program's own: a k 1.0 result of status "disqualified" is stored (its rows are not counted) and is one
  `run_disqualified` event (once a (pid, night)).
STATED LIMIT: a bar that never comes (a halted stock's session has none) leaves every program that held it without
rows from that day on, because `screen.series` refuses a held lot with no price; nothing is tagged meanwhile, so the
days fill the night it does.

A RESTATED RECORD: a stored day of tonight's engine id whose r or w differs from the recompute by more than
`forward_db.TOL` is RESTATED; its row stays (the first write stands). It is DATA, never an error, and it is ONE
`restated` event a program and CAUSE, not one a day: the event's `day` is the first restated day and its `once` the
engine id with the first 8 hex of sha256 over every restated (day, new r, new w), r and w rounded to 9 places, so
the same restatement seen again the next nights writes nothing and another value on any day is another event. WHY ONE
A CAUSE (found after the spec, with THE BARS HASH): the vendor rounds adjustment=all prices to cents and rescales the
whole adjusted history at every dividend and split, so on an ex-day nearly every stored day of every program that
held the symbol moves past `TOL` at once (measured on a synthetic store rounded to cents: 49 to 61 of 61 stored days
of a half-sleeve lot, at prices from 51 to 670), which would be one event a stored day a holder an ex-day. The
payload counts them: `days`, `first`, `last`, and by cause `moved` (a day with the bars hash of a decision on or
before it moved: the store's history was restated, the routine ex-day case) and `same` (the day's own figures moved
with every decision's inputs as they were: a correction of that day's own mark, or a recompute that is not
deterministic); `"bars"` is "same" when any day is, else "moved". A CONTROL decides nothing and reads no bar, so
its restatement cannot be told apart this way: `"bars"` "none", `moved` and `same` 0 (its marks move on the same
ex-days as every holder's, so "same" there would name the routine case as the notable one).

The receipt: {through, engine, programs, sessions, new_days, restated, checks, stale, errors, data_failed,
disqualified, retried, budget_hit, seconds, controls, twins, head, finals, register, marks, house}: counts and
verdicts, never a program's figure. Every event payload and receipt text holds ids, counts, dates and class names only (a
decimal figure in a failure's text is masked).

THE HOUSE'S OWN FAILURES ARE SAID ONCE A NIGHT (`house_failures`; the job raises ONE `ctx.alert("warning", ...)` for
them). What a night leaves no event for would else be read by nobody: `house` (in `errors`: the programs left without
rows by a write the forward store refused, by a retry with no fresh child, or by failing twice on a night no other
program's run completed), the controls left without rows by anything but the data, and each step of the night that
raised (the registry's sync, the audit marks, the controls, the final checkpoints, the twins). The data's failures
and a program that failed alone are not in it: they have their events, and league/ops/forward_report.py's alarms read those.

Standard library and numpy only.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from ..equity import config, schedule, screen
from ..equity import ctx as eq_ctx
from ..equity import engine as eq_engine
from ..equity.program import parse_needs
from ..equity.runner import KIND, RunFailed
from ..equity.store import (STORE_DIR, EquityStore, MissingData, StoreRefused, as_date, from_ordinal,
                            mint_equity_gate_capability)
from . import forward_audit, forward_controls, forward_db, forward_register, forward_stats, forward_twins
from .forward_db import Program, ShadowRun

#: The reason the job mints its `EquityGateCapability` with (the forward days are sealed).
GATE_REASON = "forward-shadow"
#: The job's own decider child's log, under the state root.
DECIDER_LOG = "forward-decider.log"
#: New York (hour, minute) between which the job does not run on a session.
QUIET = ((9, 0), (17, 30))
#: THE CANARY: a fixed program that declares one symbol and one session of history and never trades; `{symbol}` is the
#: first symbol of `elane.cfg(settings)["universe"]`. The preflight runs it through the same child op as any program.
CANARY = '''NEEDS = {{"symbols": ["{symbol}"], "history": 1, "max_hold_sessions": 1}}
PARAMS = {{}}


def decide(ctx):
    return []
'''
#: `fwd_runs.job`.
JOB = "forward_shadow"
#: The canary runs over this many of the store's last forward days.
CANARY_SESSIONS = 5
#: No program is started once the clock is within this many seconds of the next session's 09:00 New York time.
OPEN_MARGIN_SECONDS = 300.0
#: `fwd_days.status`: what a run's k 1.0 result may be to have rows.
STATUSES = ("ok", "disqualified")
#: A failure that is the data's (the module docstring): no row that night, one `data_failed` event, nobody marked.
DATA_ERRORS = (MissingData, StoreRefused, ValueError)
#: What joins a label that returns to the id of the series it follows (A LABEL THAT RETURNS); in no engine label.
RETURNED = "~"

_DECIMAL = re.compile(r"\d+\.\d+")
_SYMBOL = re.compile(r"(?<![A-Za-z0-9_.])[A-Z]+(?:\.[A-Z]+)?(?![A-Za-z0-9_])")


class NightFailed(RuntimeError):
    """The preflight failed (a decider that cannot start or answer, a canary that does not run "ok"): the House's.
    No program is run, marked or tagged; the job's receipt is {"status": "failed", "error"}."""


# ------------------------------------------------------------------------------------------------------- small helpers
def _why(exc: BaseException) -> str:
    """A failure's class and text for a payload or a receipt, cut short, a decimal figure masked (never a price)."""
    return f"{type(exc).__name__}: {_DECIMAL.sub('#', str(exc))[:160]}"


def _symbol_of(exc: BaseException, symbols: Sequence[str]) -> str | None:
    """The first of `symbols` the failure's text names (the store's and the screen's refusals name the symbol)."""
    named = set(_SYMBOL.findall(str(exc)))
    return next((str(s) for s in symbols if str(s) in named), None)


def _barless(bars: Any) -> list[str]:
    """The slice's symbols with no close on any run session (what the engine's "no_data" means)."""
    import numpy as np

    return [str(sym) for sym in bars.symbols if not np.isfinite(bars.raw[sym][int(bars.first):, 3]).any()]


def _answered(answer: Any) -> bool:
    return isinstance(answer, Mapping) and bool(answer.get("ok"))


def _symbols(program: Program) -> tuple[str, ...]:
    """The registry row's NEEDS symbols as it holds them (() when the row's NEEDS cannot be read)."""
    needs = program.needs if isinstance(program.needs, Mapping) else {}
    named = needs.get("symbols")
    return tuple(str(s) for s in named) if isinstance(named, (list, tuple)) else ()


@contextlib.contextmanager
def _transaction(db: sqlite3.Connection) -> Iterator[None]:
    """One transaction on `db`, whatever its isolation level: begun with the write lock (never a read that must be
    upgraded mid-way), committed when the block ends, rolled back when it raises. The writes league/ops/forward_db.py
    makes inside it (`event`) join it; were one to commit on its own, what it committed stays."""
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    if db.in_transaction:
        db.commit()


def _grid(limit: int) -> Iterator[int]:
    """The checkpoint counts up to `limit` (D4): `forward_db.CHECKPOINTS`, then every `CHECKPOINT_EVERY`."""
    last = 0
    for n in forward_db.CHECKPOINTS:
        if n > limit:
            return
        yield n
        last = n
    n = (last // forward_db.CHECKPOINT_EVERY + 1) * forward_db.CHECKPOINT_EVERY
    while n <= limit:
        yield n
        n += forward_db.CHECKPOINT_EVERY


def _nine(day: dt.date) -> float:
    return dt.datetime.combine(day, dt.time(*QUIET[0]), schedule.NY).timestamp()


def quiet(now: float) -> bool:
    """Whether epoch `now` is inside `QUIET` (09:00-17:30 New York time) on a session: the job then skips (the evening
    run does the night)."""
    moment = dt.datetime.fromtimestamp(float(now), schedule.NY)
    if not schedule.is_session(moment.date()):
        return False
    return dt.time(*QUIET[0]) <= moment.time() < dt.time(*QUIET[1])


def _decider(root: Path) -> Any:
    """The job's own decider child (never the live process's and never `elane.isolated_runner`); a test hands the job
    an `InlineDecider` here."""
    from ..live.decider import Decider

    return Decider(log=root / DECIDER_LOG)


def house_failures(receipt: Mapping[str, Any]) -> list[str]:
    """What of a night's receipt is the House's own failure and has no event (THE HOUSE'S OWN FAILURES, the module
    docstring), each a short text of counts and class names only; [] for a clean night."""
    def whole(value: Any) -> int:
        return int(value) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0

    def raised(part: Any) -> str | None:
        return str(part["error"])[:60] if isinstance(part, Mapping) and "error" in part else None

    out = []
    if whole(receipt.get("house")):
        out.append(f"{whole(receipt.get('house'))} programs left without rows")
    controls = receipt.get("controls")
    if isinstance(controls, Mapping):
        unmade = whole(controls.get("errors")) - whole(controls.get("data_failed"))
        if unmade > 0:
            out.append(f"{unmade} controls left without rows")
    twins = receipt.get("twins")
    parts = [("the registry's sync", receipt.get("register")), ("the audit marks", receipt.get("marks")),
             ("the controls", controls), ("the final checkpoints", receipt.get("finals"))]
    if isinstance(twins, Mapping):
        parts += [("the twins' timing table", twins.get("begin")), ("the twins' own runs", twins.get("finish"))]
    for name, part in parts:
        if raised(part) is not None:
            out.append(f"{name} raised {raised(part)}")
    if isinstance(twins, Mapping):
        steps = sum(1 for part in ("begin", "finish") if raised(twins.get(part)) is not None)
        if whole(twins.get("errors")) > steps:
            out.append(f"the twins' re-price of {whole(twins.get('errors')) - steps} runs raised")
    return out


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py): skipped when `forward_db.mode` is "off", inside `quiet`, or with no forward
    day in the store; else `Decider(log=<root>/forward-decider.log)` (its own instance; `InlineDecider` in tests
    only), `Shadow(...).night()`, the decider closed in `finally`. A `NightFailed` from the preflight is {"status":
    "failed", "error": ...} (the ops runner starts the job again inside its grace). A `MissingData` on opening the
    store (it is being rewritten) is a failed receipt too. A night that ran with failures of the House's own is one
    warning (`house_failures`)."""
    from ..swarm import settings as swarm_settings

    root = Path(ctx.root)
    settings = swarm_settings.load(root, config=getattr(ctx, "config", None))
    try:
        mode = forward_db.mode(settings)
    except NotImplementedError:  # a release without the forward store's package: nothing to record into, never a crash
        return {"status": "skipped", "why": "the forward store is not in this release (league/ops/forward_db.py)"}
    if mode == "off":
        return {"status": "skipped", "why": "elane.forward.mode is off"}
    if quiet(ctx.now()):
        return {"status": "skipped", "why": "inside 09:00-17:30 New York time on a session: the evening run does the "
                                           "night"}
    store_root = root / STORE_DIR
    if not (store_root / "VERSION").is_file():
        return {"status": "skipped", "why": "no equity store yet: no forward day"}
    try:
        through = EquityStore(store_root).fetched_through
    except (MissingData, StoreRefused) as exc:
        return {"status": "failed", "error": f"the equity store could not be opened ({_why(exc)})"}
    if through < forward_db.t0():
        return {"status": "skipped", "why": f"no forward day in the store yet (its last day is {through.isoformat()})"}
    db = forward_db.open_db(root)
    children: list[Any] = []

    def fresh() -> Any:
        """A newly started child for THE RETRY: the old one is closed first (one child at a time)."""
        while children:
            with contextlib.suppress(Exception):
                children.pop().close()
        children.append(_decider(root))
        return children[-1]

    try:
        shadow = Shadow(root, db, decider=fresh(), settings=settings, clock=ctx.now, fresh=fresh)
        receipt = shadow.night()
        failures = house_failures(receipt)
        if failures:
            ctx.alert("warning", f"forward_shadow: the night of {receipt['through']} had failures of the House's own "
                                 f"({'; '.join(failures)}): no program is marked for them, and the next night's "
                                 "recompute fills what was left out")
        return receipt
    except NightFailed as exc:
        return {"status": "failed", "error": f"the preflight failed, nobody was run or marked: {exc}"}
    except (MissingData, StoreRefused) as exc:
        return {"status": "failed", "error": f"the equity store could not be opened ({_why(exc)})"}
    finally:
        for child in children:
            with contextlib.suppress(Exception):
                child.close()
        db.close()


class Shadow:
    """One night's recompute over the state root `root` and the forward store `db` (the module docstring). `decider`: a
    `league.live.decider` `Decider` or `InlineDecider`; `settings`: the swarm's; `clock`: epoch seconds; `fresh`: a
    callable giving a newly started decider for THE RETRY (the job passes one that closes the old child first; None:
    no retry).

    Attributes: `store` (the `EquityStore` opened with the capability), `through` (its `fetched_through`: the night's
    name) and `engine` (tonight's engine id); `night_day` (`through` as ISO text: the `day` of every event of the
    night) and `spent` (the child seconds spent so far). What it was made with stays readable for the twins
    (league/ops/forward_twins.py): `root`, `db`, `settings`, `cfg` (`forward_db.cfg(settings)`), `clock` and
    `decider` (the child that answers now: THE RETRY's fresh one once it has run)."""

    def __init__(self, root: str | Path, db: sqlite3.Connection, *, decider: Any, settings: Mapping[str, Any] | None,
                 clock: Callable[[], float] = time.time, fresh: Callable[[], Any] | None = None):
        self.root = Path(root)
        self.db = db
        self.decider = decider
        self.settings = settings
        self.clock = clock
        self.fresh = fresh
        self.cfg = forward_db.cfg(settings)
        store_root = self.root / STORE_DIR
        self.store = EquityStore(store_root, gate=mint_equity_gate_capability(store_root, GATE_REASON))
        self.through: dt.date = self.store.fetched_through
        self.night_day = self.through.isoformat()
        self.spent = 0.0
        self._t0: dt.date = forward_db.t0()
        self._engine: int | None = None
        self._held: set[str] | None = None

    # ------------------------------------------------------------------------------------------------ the engine id
    @property
    def engine(self) -> int:
        """Tonight's engine id, read once a night: `forward_db.engine_id` of tonight's label (`_label`). A label seen
        for the first time is one `engine_moved` event (once a label), whoever created its row. It is always the
        NEWEST id (`forward_db.engine_now`), which is the series every reader takes as the current one."""
        if self._engine is None:
            label = self._label()
            eid, _created = forward_db.engine_id(self.db, label, at=self.clock())
            before = self.db.execute("SELECT label FROM fwd_engines WHERE id < ? ORDER BY id DESC LIMIT 1",
                                     (int(eid),)).fetchone()
            forward_db.event(self.db, "engine_moved", at=self.clock(), once=label,
                             payload={"why": "a new engine label opens a new series: every active program's history "
                                             "is written again under it, the older rows stay",
                                      "from": None if before is None else str(before[0]), "to": label,
                                      "engine": int(eid)})
            self._commit()
            self._engine = int(eid)
        return self._engine

    def _label(self) -> str:
        """Tonight's label as `fwd_engines` holds it: `forward_db.fwd_engine()`, or, for A LABEL THAT RETURNS (the
        module docstring), that label with `RETURNED` and the id of the series it follows."""
        label = forward_db.fwd_engine()
        newest = forward_db.engine_now(self.db)
        if newest is None:
            return label
        held = str(forward_db.engine_label(self.db, newest) or "")
        if held == label or held.startswith(label + RETURNED):
            return held                 # the newest series is this label's own (as it opened, or as it returned)
        known = self.db.execute("SELECT 1 FROM fwd_engines WHERE label=?", (label,)).fetchone()
        return label if known is None else f"{label}{RETURNED}{int(newest)}"

    def _commit(self) -> None:
        if self.db.in_transaction:
            self.db.commit()

    def _rollback(self) -> None:
        if self.db.in_transaction:
            self.db.rollback()

    # --------------------------------------------------------------------------------------------------- the child
    def _child(self, decider: Any, *, code: str, params: Mapping[str, Any], name: str, bars: Any, k: float
               ) -> dict[str, Any]:
        """One "run" of the decider child, its seconds added to `spent`, its answer read as `runner.Isolated` reads
        it: `RunFailed` for no answer, a refusal, no result or a result of status "error" (the child's);
        `MissingData` for "no_data" (a NEEDS symbol with no bar in the run: the data's); `DeciderError` as raised."""
        payload = {"code": code, "params": dict(params or {}), "name": name, "bars": bars, "k": float(k),
                   "capital": None}
        began = self.clock()
        try:
            answer = decider.kind(KIND, "run", payload, budget_seconds=float(self.cfg["run_budget_seconds"]))
        finally:
            self.spent += max(0.0, self.clock() - began)
        if not isinstance(answer, Mapping):
            raise RunFailed(f"the decider child answered the run with a {type(answer).__name__}")
        if not answer.get("ok"):
            raise RunFailed(str(answer.get("error") or "the decider child did not answer the run"))
        result = answer.get("result")
        if not isinstance(result, Mapping):
            raise RunFailed("the decider child returned no result")
        status = result.get("status")
        if status == "no_data":
            raise MissingData(f"{name}: {', '.join(_barless(bars)) or 'a NEEDS symbol'} has no bar in the run")
        if status not in STATUSES:
            raise RunFailed(str(result.get("reason") or f"the run ended {status!r}"))
        return dict(result)

    def _forward_days(self) -> list[dt.date]:
        """D1: the store's forward days, from `forward_db.t0()` (never from the window's first session)."""
        return [d for d in self.store.sessions("forward") if d >= self._t0]

    def preflight(self) -> None:
        """`decider.ping()` answers ok AND `CANARY` runs "ok" over the store's last five forward days through the
        same child op; else `NightFailed` and one `night_failed` event (once a night): no `fwd_runs` row, no
        `run_failed`, nothing tagged."""
        try:
            why = self._canary()
        except Exception as exc:  # noqa: BLE001 - whatever stopped the child or its canary, it is the House's
            why = _why(exc)
        if why is None:
            return
        self._rollback()
        forward_db.event(self.db, "night_failed", day=self.night_day, at=self.clock(), once="night",
                         payload={"why": why})
        self._commit()
        raise NightFailed(why)

    def _canary(self) -> str | None:
        """Why the preflight fails, or None."""
        from ..swarm import elane

        if not _answered(self.decider.ping()):
            return "the decider child did not answer its ping"
        days = self._forward_days()
        if not days:
            return "the store holds no forward day"
        universe = elane.cfg(self.settings)["universe"]
        symbol = str(universe[0])
        bars = self.store.bars([symbol], "forward", history=1, start=days[-CANARY_SESSIONS:][0])
        result = self._child(self.decider, code=CANARY.format(symbol=symbol), params={}, name="forward-canary",
                             bars=bars, k=config.K_BASE)
        if result.get("status") != "ok":
            return f"the canary ended {result.get('status')!r}"
        return None

    # ---------------------------------------------------------------------------------------------------- who is due
    def _last_stored(self) -> dict[int, str]:
        """{pid: its last stored day} under tonight's engine id."""
        return {int(row[0]): str(row[1]) for row in self.db.execute(
            "SELECT pid, MAX(day) FROM fwd_days WHERE engine=? GROUP BY pid", (self.engine,)).fetchall()}

    def due(self) -> list[Program]:
        """The active non-control programs whose last stored day is before `through`: tag "live" first, then reasons
        seed and train_pass, then train_fail, then the suspects; inside a class the oldest last-stored day first,
        then pid (so the programs a budget left stale go first the next night). A program with no stored day stands
        at its `first_close`; one whose first day is after `through` has nothing to store and is not due."""
        last = self._last_stored()
        live = {int(row[0]) for row in self.db.execute("SELECT DISTINCT pid FROM fwd_tags WHERE tag='live'").fetchall()}
        rows = []
        for program in forward_db.programs(self.db, active=True):
            if program.lane == "control" or program.reason == "control" or program.first_day > self.through:
                continue
            stored = last.get(program.pid)
            if stored is not None and stored >= self.night_day:
                continue
            if forward_db.suspect(self.db, program.pid):
                rank = 3
            elif program.pid in live or program.reason == "live":
                rank = 0
            elif program.reason == "train_fail":
                rank = 2
            else:
                rank = 1
            rows.append((rank, stored or program.first_close.isoformat(), program.pid, program))
        return [row[3] for row in sorted(rows, key=lambda row: row[:3])]

    # ------------------------------------------------------------------------------------------------------ the run
    def slice(self, program: Program, *, first_day: dt.date | None = None) -> Any:
        """The program's forward `store.Bars` from `first_day` (its own when None) through `through`; None when that
        first day is after `through`. `MissingData`, `StoreRefused` and `ValueError` are the data's.

        The slice carries NEEDS history + 1 sessions before its first run session (THE FIRST DECISION, the module
        docstring). A first day before `forward_db.t0()` is refused (a ValueError: no day before the look cap's next
        session is a forward day, whatever a registry row says), and so is a slice with no session to decide at."""
        first = as_date(program.first_day if first_day is None else first_day)
        if first > self.through:
            return None
        if first < self._t0:
            raise ValueError(f"{program.key}: {first.isoformat()} is before the first forward day "
                             f"{self._t0.isoformat()}")
        needs = parse_needs(program.needs)
        bars = self.store.bars(needs.symbols, "forward", history=int(needs.history) + 1, start=first, end=None)
        if bars.n <= bars.first:
            return None
        if bars.first < 1:
            raise ValueError(f"{program.key}: the store has no session before {first.isoformat()} to decide at")
        return bars

    def _series(self, program: Program, result: Mapping[str, Any], bars: Any) -> Any:
        needs = parse_needs(program.needs)
        return screen.series(result.get("lots") or [], bars, universe=list(needs.symbols),
                             capital=result.get("capital") or config.SLEEVE_USD)

    def run_from(self, program: Program, first_day: dt.date, *, k: float = 1.0) -> ShadowRun | None:
        """D3's run of `program` started flat at another first day (the twin runs of league/ops/forward_twins.py);
        None when that day is after `through`. Raises as `run_program` does."""
        bars = self.slice(program, first_day=first_day)
        if bars is None:
            return None
        result = self._child(self.decider, code=program.code, params=program.params, name=program.key, bars=bars, k=k)
        return ShadowRun(program=program, result=result, bars=bars, series=self._series(program, result, bars))

    def official(self, symbol: str, day: dt.date | str, at: str) -> float | None:
        """The store's raw open (`at` "open") or close ("close") of `symbol` on `day` (`engine.official`); None when
        it has no bar: the timing table's official price."""
        if at not in (eq_engine.OPEN, eq_engine.CLOSE):
            raise ValueError(f"'at' is open or close, not {at!r}")
        sym = str(symbol).strip().upper()
        if self._held is None:
            self._held = set(self.store.symbols())
        if sym not in self._held:
            return None
        when = as_date(day)
        bars = self.store.bars([sym], "forward", history=0, start=when, end=when)
        if bars.n != 1:
            return None
        return eq_engine.official(bars, sym, 0, at)

    def run_program(self, program: Program) -> tuple[ShadowRun, Mapping[str, Any]]:
        """(the k 1.0 run, the k 1.5 result) of one program on its forward days. Raises E1's `runner.RunFailed` or
        the decider's `DeciderError` (the child's), or `MissingData`, `StoreRefused`, `ValueError` (the data's)."""
        bars = self.slice(program)
        if bars is None:
            raise ValueError(f"{program.key} has no forward day through {self.night_day}")
        base = self._child(self.decider, code=program.code, params=program.params, name=program.key, bars=bars,
                           k=config.K_BASE)
        stress = self._child(self.decider, code=program.code, params=program.params, name=program.key, bars=bars,
                             k=config.K_STRESS)
        return ShadowRun(program=program, result=base, bars=bars, series=self._series(program, base, bars)), stress

    # ---------------------------------------------------------------------------------------------------- the rows
    def write(self, run: ShadowRun, result15: Mapping[str, Any]) -> dict[str, int]:
        """One transaction a program: {"new_days", "restated", "checks"}. New days are inserted under tonight's engine
        id, each with its decision's bars hash; the stored days of that id whose r or w differs by more than
        `forward_db.TOL` are one `restated` event (the rows stay; once a program and cause: A RESTATED RECORD, the
        module docstring; "restated" is 1 when the event is new tonight); the due checkpoints (D4); a k 1.0 result
        of status "disqualified" is one `run_disqualified` event (once a (pid, night))."""
        program, bars, base = run.program, run.bars, run.series
        status = str(run.result.get("status"))
        if status not in STATUSES:
            raise ValueError(f"{program.key}: a run of status {status!r} has no rows")
        stress = self._series(program, result15, bars)
        if len(stress.r) != len(base.r):
            raise ValueError(f"{program.key}: the two runs differ in their sessions")
        needs = parse_needs(program.needs)
        entered = Counter(str(lot.get("entry_day"))[:10] for lot in run.result.get("lots") or [])
        hashes: dict[int, str] = {}

        def bars_at(i: int) -> str:
            """THE BARS HASH of run session i's orders: the Gym's inputs at the close of the session before it."""
            if i not in hashes:
                hashes[i] = forward_db.bars_hash(eq_ctx.inputs_from_bars(
                    bars, int(bars.first) + i - 1, needs=needs, cash=0.0, equity=0.0, budget=0.0, caps={}, params={}))
            return hashes[i]

        days = [from_ordinal(int(d)).isoformat() for d in base.days]
        return self._put(program.pid, days, r=base.r, w=base.w, b=base.b, r15=stress.r, r0=None,
                         entries=[entered.get(day, 0) for day in days], exits=base.exits, status=status,
                         bars_at=bars_at)

    def _put(self, pid: int, days: Sequence[str], *, r: Any, w: Any, b: Any, r15: Any, r0: Any, entries: Sequence[int],
             exits: Any, status: str, bars_at: Callable[[int], str] | None) -> dict[str, int]:
        """The rows of one pid in one transaction (`write`, `controls`): the new days, the restated event, the due
        checkpoints, the disqualified event. `bars_at` None: a control (its rows' `bars` are NULL)."""
        engine, now = self.engine, self.clock()
        cols = {"r": [float(v) for v in r], "w": [float(v) for v in w], "b": [float(v) for v in b],
                "r15": [float(v) for v in r15]}
        cost_free = None if r0 is None else [float(v) for v in r0]
        if any(len(col) != len(days) for col in (*cols.values(), entries, exits, cost_free or days)):
            raise ValueError(f"pid {pid}: a series is not aligned with its days")
        if not all(math.isfinite(v) for col in (*cols.values(), cost_free or ()) for v in col):
            raise ValueError(f"pid {pid}: a series holds a value that is not finite")
        stored = {str(row["day"]): row for row in self.db.execute(
            "SELECT day, r, w, bars FROM fwd_days WHERE pid=? AND engine=?", (pid, engine)).fetchall()}
        new = restated = 0
        differ: list[int] = []
        with _transaction(self.db):
            for i, day in enumerate(days):
                old = stored.get(day)
                if old is None:
                    self.db.execute(
                        "INSERT INTO fwd_days(pid, day, engine, r, w, b, r15, r0, entries, exits, status, at, bars) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (pid, day, engine, cols["r"][i], cols["w"][i], cols["b"][i], cols["r15"][i],
                         None if cost_free is None else cost_free[i], int(entries[i]), int(exits[i]), status, now,
                         None if bars_at is None else bars_at(i)))
                    new += 1
                elif abs(float(old["r"]) - cols["r"][i]) > forward_db.TOL or \
                        abs(float(old["w"]) - cols["w"][i]) > forward_db.TOL:
                    differ.append(i)
            if differ:
                # The first run session whose decision's bars hash is not the stored one, up to the last restated day.
                first_moved = None if bars_at is None else next(
                    (i for i in range(differ[-1] + 1) if days[i] in stored and stored[days[i]]["bars"] is not None
                     and str(stored[days[i]]["bars"]) != bars_at(i)), None)
                moved = sum(1 for i in differ if first_moved is not None and first_moved <= i)
                same = 0 if bars_at is None else len(differ) - moved
                value = hashlib.sha256("\n".join(      # + 0.0: a negative zero is zero
                    f"{days[i]}|{round(cols['r'][i], 9) + 0.0:.9f}|{round(cols['w'][i], 9) + 0.0:.9f}" for i in differ
                ).encode()).hexdigest()[:8]
                seq = forward_db.event(
                    self.db, "restated", pid=pid, day=days[differ[0]], at=now, once=f"{engine}:{value}",
                    payload={"why": "the night's recompute differs from the stored rows: the rows stay",
                             "engine": engine, "night": self.night_day, "days": len(differ), "first": days[differ[0]],
                             "last": days[differ[-1]], "moved": moved, "same": same,
                             "bars": "none" if bars_at is None else ("same" if same else "moved")})
                restated = 1 if seq else 0
            checks = self._checkpoints(pid, known=len(stored) + new)
            if status == "disqualified":
                forward_db.event(self.db, "run_disqualified", pid=pid, day=self.night_day, at=now, once="night",
                                 payload={"why": "the k 1.0 run ended disqualified: its rows are stored, not counted"})
        return {"new_days": new, "restated": restated, "checks": checks}

    def _checkpoints(self, pid: int, *, known: int) -> int:
        """The grid checkpoints (D4) a pid is due under tonight's engine id, written; how many. `known`: its stored
        days (its counted days are no more), so a pid short of its next count is not read at all."""
        engine = self.engine
        have = {int(row[0]) for row in self.db.execute("SELECT n FROM fwd_checks WHERE pid=? AND engine=?",
                                                       (pid, engine)).fetchall()}
        wanted = [n for n in _grid(known) if n not in have]
        if not wanted:
            return 0
        counted = forward_db.counted_days(self.db, pid, engine=engine)
        written = 0
        for n in wanted:
            # The n-th counted day is before the store's last day: its morning audit has run.
            if n > len(counted) or not str(counted[n - 1]["day"]) < self.night_day:
                break
            self._check(pid, counted[:n], engine=engine, final=0)
            written += 1
        return written

    def _check(self, pid: int, days: Sequence[Mapping[str, Any]], *, engine: int, final: int) -> None:
        """One `fwd_checks` row over `days` (a pid's first n counted days): D4's statistics, and a control's
        cost-free ones (D5, D8: every day carries `r0`). Recorded, never a verdict."""
        n = len(days)
        r = [float(row["r"]) for row in days]
        w = [float(row["w"]) for row in days]
        b = [float(row["b"]) for row in days]
        x = [ri - wi * bi for ri, wi, bi in zip(r, w, b)]
        t_x = forward_stats.t_stat(x)
        stress = [row["r15"] for row in days]
        t_x0 = p_x0 = None
        if all(row["r0"] is not None for row in days):
            t_x0 = forward_stats.t_stat([float(row["r0"]) - wi * bi for row, wi, bi in zip(days, w, b)])
            p_x0 = forward_stats.p_one_sided(t_x0, n)
        self.db.execute(
            "INSERT INTO fwd_checks(pid, n, day, engine, t_r, sum_r, sum_r15, t_x, mean_w, p_x, t_x0, p_x0, final, at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, n, str(days[-1]["day"]), engine, forward_stats.t_stat(r), math.fsum(r),
             None if any(v is None for v in stress) else math.fsum(float(v) for v in stress), t_x, math.fsum(w) / n,
             forward_stats.p_one_sided(t_x, n), t_x0, p_x0, int(final), self.clock()))

    # ------------------------------------------------------------------------------------------------------- marks
    def marks(self) -> int:
        """THE MORNING MARKS, MADE UP (the module docstring): the `audit_mismatch` events the morning job would write
        from the live book as it stands now; how many were written (one already there writes nothing). 0 with no
        live book; `sqlite3.Error` when the book cannot be read."""
        live = self.root / forward_audit.LIVE_DB
        if not live.exists():
            return 0
        return forward_audit.mark(self.db, forward_audit.mismatches(live), now=self.clock())

    # ---------------------------------------------------------------------------------------------------- controls
    def controls(self) -> dict[str, int]:
        """The controls' rows, in the parent (no child): {"groups", "rows"}. For each registered control:
        `forward_controls.control_lots` at k 1.0, 1.5 and 0.0, `screen.series`, `forward_controls.cost_free`; its
        `fwd_days` rows with `r0` (and `bars` NULL: a control reads no bar); its checkpoints with `t_x0` and `p_x0`
        beside D4's.

        Also {"checks", "restated", "errors", "data_failed"}: a control whose series cannot be made tonight is
        counted in `errors` (the data's, counted in `data_failed` too, is one `data_failed` event, once a (pid,
        night)) and the others go on; one written through `through` is skipped."""
        last = self._last_stored()
        groups: set[str] = set()
        out = {"groups": 0, "rows": 0, "checks": 0, "restated": 0, "errors": 0, "data_failed": 0}
        for program in forward_db.programs(self.db, reasons=("control",), active=True):
            if program.first_day > self.through:
                continue
            groups.add(program.ugroup)
            if (last.get(program.pid) or "") >= self.night_day:
                continue
            try:
                wrote = self._control(program)
            except DATA_ERRORS as exc:
                self._rollback()
                self._data_failed(program, exc)
                out["errors"] += 1
                out["data_failed"] += 1
                continue
            except Exception:  # noqa: BLE001 - one control never costs the others, or the programs' night
                self._rollback()
                out["errors"] += 1
                continue
            out["rows"] += wrote["new_days"]
            out["checks"] += wrote["checks"]
            out["restated"] += wrote["restated"]
        out["groups"] = len(groups)
        return out

    def _control(self, program: Program) -> dict[str, int]:
        """One control's rows (D5): its lots are a pure function of its spec and the sessions; its series is D3's on
        `bars(symbols, "forward", history=1, start=first_day)` with capital `config.SLEEVE_USD`."""
        spec = json.loads(program.code)
        if not isinstance(spec, Mapping):
            raise ValueError(f"{program.key}: its code is not a control's spec")
        symbols = [str(s) for s in spec.get("symbols") or ()]
        if program.first_day < self._t0:
            raise ValueError(f"{program.key}: {program.first_day.isoformat()} is before the first forward day")
        bars = self.store.bars(symbols, "forward", history=1, start=program.first_day, end=None)
        if bars.n <= bars.first:
            return {"new_days": 0, "restated": 0, "checks": 0}
        if bars.first < 1:
            raise ValueError(f"{program.key}: the store has no session before its first day")
        sessions = [bars.day(i) for i in range(int(bars.first) - 1, bars.n)]    # S[0] is `first_close`
        lots = forward_controls.control_lots(spec, sessions, k=config.K_BASE)
        base = screen.series(lots, bars, universe=symbols, capital=config.SLEEVE_USD)
        stress = screen.series(forward_controls.control_lots(spec, sessions, k=config.K_STRESS), bars,
                               universe=symbols, capital=config.SLEEVE_USD)
        r0 = forward_controls.cost_free(forward_controls.control_lots(spec, sessions, k=0.0), bars,
                                        capital=config.SLEEVE_USD)
        days = [from_ordinal(int(d)).isoformat() for d in base.days]
        entered = Counter(as_date(lot["entry_day"]).isoformat() for lot in lots)
        return self._put(program.pid, days, r=base.r, w=base.w, b=base.b, r15=stress.r, r0=r0,
                         entries=[entered.get(day, 0) for day in days], exits=base.exits, status="ok", bars_at=None)

    def finals(self) -> int:
        """The FINAL checkpoint (D4) of each stopped pid that has none; how many were written.

        Over the pid's counted days under the newest engine id it has rows for (a stopped program is not written
        again when the label moves): `final` 1, n = those days, when n >= 2, the last of them is before the store's
        last day (its morning audit has run) and no row (pid, n) exists under any engine (a program stopped ON the
        grid already has its row)."""
        written = 0
        stopped = [int(row[0]) for row in self.db.execute(
            "SELECT DISTINCT pid FROM fwd_tags WHERE tag='stopped' ORDER BY pid").fetchall()]
        for pid in stopped:
            if forward_db.active(self.db, pid):
                continue
            newest = self.db.execute("SELECT MAX(engine) FROM fwd_days WHERE pid=?", (pid,)).fetchone()
            if newest is None or newest[0] is None:
                continue
            counted = forward_db.counted_days(self.db, pid, engine=int(newest[0]))
            n = len(counted)
            if n < 2 or not str(counted[-1]["day"]) < self.night_day:
                continue
            if self.db.execute("SELECT 1 FROM fwd_checks WHERE pid=? AND n=?", (pid, n)).fetchone() is not None:
                continue
            with _transaction(self.db):
                self._check(pid, counted, engine=int(newest[0]), final=1)
            written += 1
        return written

    # ----------------------------------------------------------------------------------------------------- the night
    def _data_failed(self, program: Program, exc: BaseException) -> None:
        """The data's failure of one program tonight: one event, once a (pid, night); nobody is marked."""
        forward_db.event(self.db, "data_failed", pid=program.pid, day=self.night_day, at=self.clock(), once="night",
                         payload={"why": _why(exc), "class": type(exc).__name__,
                                  "symbol": _symbol_of(exc, _symbols(program))})
        self._commit()

    def _completed(self, but: int | None = None) -> int:
        """How many programs' runs completed tonight (those of every pid but `but` when given): the pids with a row
        for the night under tonight's engine id (a control's row has no bars hash and is not a run), whichever start
        of the job wrote it."""
        return int(self.db.execute(
            "SELECT COUNT(DISTINCT pid) FROM fwd_days WHERE day=? AND engine=? AND pid IS NOT ? AND bars IS NOT NULL",
            (self.night_day, self.engine, None if but is None else int(but))).fetchone()[0])

    def _deadline(self, now: float) -> float:
        """The epoch after which no program is started: `OPEN_MARGIN_SECONDS` before the next session's 09:00 ET."""
        day = schedule.ny_day(now)
        if not (schedule.is_session(day) and now < _nine(day)):
            try:
                day = schedule.next_session(day)
            except ValueError:
                return float("inf")
        return _nine(day) - OPEN_MARGIN_SECONDS

    def _guarded(self, call: Callable[[], Any]) -> Any:
        """`call()`, or {"error": its class} when it raised (what it had not committed is rolled back): a step of the
        night that is not a program's run never costs the night."""
        try:
            value = call()
        except Exception as exc:  # noqa: BLE001 - named in the receipt; the night goes on
            self._rollback()
            return {"error": type(exc).__name__}
        self._commit()
        return value

    def _attempt(self, program: Program, tally: Counter) -> str | None:
        """One program's run and write. None when it is settled for the night (written, the data's, or a write the
        forward store refused); the failure's class when the child failed it (THE RETRY's list)."""
        try:
            run, result15 = self.run_program(program)
        except DATA_ERRORS as exc:
            self._data_failed(program, exc)
            tally["data_failed"] += 1
            return None
        except Exception as exc:  # noqa: BLE001 - RunFailed, DeciderError, no result: the child's
            return type(exc).__name__
        try:
            wrote = self.write(run, result15)
        except ValueError as exc:  # the k 1.5 run's series, or a result that does not fit its bars: the data's
            self._data_failed(program, exc)
            tally["data_failed"] += 1
            return None
        except Exception:  # noqa: BLE001 - the forward store's own failure: counted, never the program's
            self._rollback()
            tally["errors"] += 1
            tally["house"] += 1
            return None
        tally["programs"] += 1
        tally["sessions"] += len(run.series.days)
        tally["new_days"] += wrote["new_days"]
        tally["restated"] += wrote["restated"]
        tally["checks"] += wrote["checks"]
        tally["disqualified"] += 1 if run.result.get("status") == "disqualified" else 0
        try:
            tally["ll"] += int(forward_twins.on_run(self.db, run, now=self.clock(), settings=self.settings) or 0)
            self._commit()
        except Exception:  # noqa: BLE001 - a twins failure never loses a shadow day
            self._rollback()
            tally["twins_errors"] += 1
        return None

    def night(self) -> dict[str, Any]:
        """THE NIGHT (the module docstring), resumable: a night killed after one program resumes with no duplicate
        (a program already written through `through` is skipped). The job's receipt."""
        started = self.clock()
        self.preflight()
        synced = self._guarded(lambda: forward_register.sync(self.root, self.db, now=self.clock(),
                                                             settings=self.settings))
        engine = self.engine
        marks = self._guarded(self.marks)
        twins: dict[str, Any] = {"begin": self._guarded(
            lambda: forward_twins.begin(self.root, self.db, self, now=self.clock()))}
        controls = self._guarded(self.controls)
        finals = self._guarded(self.finals)
        budget = float(self.cfg["cpu_seconds_night"])
        deadline = self._deadline(started)

        def over() -> bool:
            return self.spent >= budget or self.clock() >= deadline

        tally: Counter = Counter()
        failed: list[tuple[Program, str]] = []
        due = self.due()
        stale = 0
        for i, program in enumerate(due):
            if over():
                stale = len(due) - i
                break
            why = self._attempt(program, tally)
            if why is not None:
                failed.append((program, why))
        # THE RETRY: each program the child failed, again, alone, in a newly started child that answers its ping.
        retried, twice = 0, []
        child = None
        if failed and self.fresh is not None:
            try:
                child = self.fresh()
                child = child if _answered(child.ping()) else None
            except Exception:  # noqa: BLE001 - no fresh child: the House's, nothing is written for the listed
                child = None
        if child is None:
            tally["errors"] += len(failed)
            tally["house"] += len(failed)
        else:
            self.decider = child
            for i, (program, _first) in enumerate(failed):
                if over():
                    stale += len(failed) - i
                    break
                retried += 1
                why = self._attempt(program, tally)
                if why is not None:
                    twice.append((program, why))
            tally["errors"] += len(twice)
            for program, why in twice:
                completed = self._completed(program.pid)
                if completed < 1:
                    tally["house"] += 1
                    continue    # nobody else's run completed tonight: the House's, no program is named
                forward_db.event(self.db, "run_failed", pid=program.pid, day=self.night_day, at=self.clock(),
                                 once="night", payload={"why": "failed again, alone, in a fresh child while another "
                                                               "program's run completed", "class": why,
                                                        "completed": completed})
            self._commit()
        if stale:
            forward_db.event(self.db, "budget_hit", day=self.night_day, at=self.clock(), once="night",
                             payload={"why": "the night's child seconds or the clock ran out: the rest go first "
                                             "the next night", "stale": int(stale), "programs": int(tally["programs"])})
            self._commit()
        twins["finish"] = self._guarded(lambda: forward_twins.finish(self.root, self.db, self, now=self.clock()))
        twins["rows"] = int(tally["ll"])
        twins["errors"] = int(tally["twins_errors"]) + sum(
            1 for part in ("begin", "finish") if isinstance(twins[part], Mapping) and "error" in twins[part])
        finished = self.clock()
        head = forward_db.head(self.db)
        with _transaction(self.db):
            self.db.execute(
                "INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, programs, sessions, errors, "
                "stale, budget_hit, head) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (JOB, self.night_day, engine, started, finished, round(self.spent, 3), self._completed(),
                 int(tally["sessions"]), int(tally["errors"]), int(stale), 1 if stale else 0, head))
        if isinstance(synced, Mapping) and "error" not in synced:
            synced = {**{k: synced.get(k) for k in ("registered", "controls", "tagged", "stopped", "suspect")},
                      "skipped": len(synced.get("skipped") or ()),
                      "chain_ok": (synced.get("chain") or {}).get("ok") if isinstance(synced.get("chain"), Mapping)
                      else None}
        return {"through": self.night_day, "engine": engine, "programs": int(tally["programs"]),
                "sessions": int(tally["sessions"]), "new_days": int(tally["new_days"]),
                "restated": int(tally["restated"]), "checks": int(tally["checks"]), "stale": int(stale),
                "errors": int(tally["errors"]), "data_failed": int(tally["data_failed"]),
                "disqualified": int(tally["disqualified"]), "retried": retried, "budget_hit": 1 if stale else 0,
                "seconds": round(self.spent, 3), "controls": controls, "twins": twins, "head": head,
                "finals": finals, "register": synced, "marks": marks, "house": int(tally["house"])}


__all__ = ["GATE_REASON", "DECIDER_LOG", "QUIET", "CANARY", "NightFailed", "quiet", "house_failures", "run", "Shadow"]

"""The `forward_shadow` job: every registered program recomputed whole each night on its own forward days (release E3).

Owner: B (league/ops/E3_INTERFACES.md). Protected. After the daily store (`equity_data`, 22:30Z), never inside
09:00-17:30 New York time on a session (`quiet`); in a pause too. It writes `fwd_days`, `fwd_checks` and `fwd_runs` of
`<state>/forward.sqlite` (league/ops/forward_db.py) and its events; it moves no money, gates nothing and judges
nothing.

THE SHADOW RUN (D3). `cap = mint_equity_gate_capability(store_root, GATE_REASON)`; `bars = EquityStore(store_root,
gate=cap).bars(needs.symbols, "forward", history=needs.history, start=first_day(p), end=None)` (a forward slice
without the capability raises `StoreRefused`). The run is `decider.kind("equity", "run", {"code", "params", "name":
key, "bars", "k", "capital": None}, budget_seconds=run_budget_seconds)` at k = `config.K_BASE` and again at
`config.K_STRESS`: E1's engine from `first_day`, flat, STATE fresh, recomputed whole every night, in THE JOB'S OWN
decider child (`Decider(log=<root>/forward-decider.log)`: never the live process's decider and never
`elane.isolated_runner`; it inherits the job's `RLIMIT_CPU` and nice and runs as E1's `Decider` runs any child). `s =
screen.series(result["lots"], bars, universe=list(needs.symbols), capital=result["capital"])`. For run session i: `r =
s.r[i]`, `w = s.w[i]`, `b = s.b[i]`, `r15` = the k 1.5 run's `s.r[i]`, `entries` = lots with that `entry_day`, `exits =
s.exits[i]`, `status` = the k 1.0 result's, `engine` = tonight's id (`forward_db.fwd_engine`, `engine_id`), `bars` =
`forward_db.bars_hash` of the decision the day's orders came from (the Gym's inputs at the close of the session
before it, `ctx.inputs_from_bars`; THE BARS HASH, league/ops/forward_db.py). EXCESS, everywhere in E3: x = r - w * b
(daily; NOT `screen.excess`, which subtracts a window mean).

THE FIRST DECISION (D2): a program first decides at the close of `first_close(p)`, the session before `first_day(p)`.
E1's engine decides from the slice's index `max(first - 1, 0)`, so the slice carries at least one history session
(`history=max(needs.history, 1)`): the ctx is the same (`ctx.inputs_from_bars` reads NEEDS' history, not the slice's),
and a NEEDS history of 0 does not move the first decision to `first_day`'s close.

CHECKPOINTS (D4). A program's COUNTED days are its `fwd_days` rows of tonight's engine id with status "ok" and no
`audit_mismatch` event, in day order (`forward_db.counted_days`); its STORED days are those rows of any status.
Checkpoint n (in `forward_db.CHECKPOINTS`, then every `CHECKPOINT_EVERY`) is written on the first night the program
has n counted days and the n-th is before the store's last day (so its morning audit has run). Over the first n
counted days: `t_r` = mean(r) / sd(r, ddof 1) * sqrt(n) (None when sd < 1e-12), `sum_r`, `sum_r15`, `t_x` the same t
of x, `mean_w`, `p_x = forward_stats.p_one_sided(t_x, n)` (None when `t_x` is None). No verdict, no threshold. A FINAL
checkpoint (`final` 1, n = its counted days, written once, when n >= 2 and no row (pid, n) exists) is written for a
program stopped off the grid, so no program leaves the record by failing. THE CHECKPOINT OF RECORD for (pid, n) is
the row written first, whatever engine later recomputes it. Sums and means use `math.fsum`.

THE NIGHT (`Shadow.night`): `preflight`; `forward_register.sync`; `engine_id` (a new label: one `engine_moved` event,
and that night every active program's whole history is written again under the new id; rows of an older id stay and
are never read as the current series); `forward_twins.begin`; `controls`; `finals`; `due()` in order until the child
seconds spent reach `cpu_seconds_night` or the clock is within 300 s of the next session's 09:00 ET (the rest are
`stale`: a `budget_hit` event, once a night); `forward_twins.on_run` after each `write`; THE RETRY;
`forward_twins.finish`; one `fwd_runs` row (`programs` = the runs completed). Each league/ops/forward_twins.py call
sits in its own try/except: a twins failure never loses a shadow day.

WHOSE FAILURE (E2's RUN rule, carried over). A FAILURE NEVER MARKS A PROGRAM HERE: league/ops/forward_register.py
reads the events.
- The House's, before anything: `preflight` (the child answers `ping` AND `CANARY` runs "ok" over the store's last
  five forward days through the same child op); else `NightFailed`, one `night_failed` event (once a night), no
  `fwd_runs` row, no `run_failed`, nothing tagged.
- The data's (`MissingData`, `StoreRefused`, a `ValueError` from the slice or from `screen.series`: a held symbol with
  no price that session): one `data_failed` event (once a (pid, night), payload the class and the symbol), no row that
  night; the next night's whole recompute fills it once the store is repaired.
- The child's (`RunFailed`, `DeciderError`, no result): the program goes on the retry list. THE RETRY, after the due
  loop: `fresh()` gives a newly started decider, pinged; each listed program is run again alone while the budget
  allows. One that completes is written as any other. One that fails again gets a `run_failed` event (once a (pid,
  night); payload the class and `completed`) only when at least one other program's run completed that night; with
  none, or with a fresh child that does not ping, nothing is written for it.
- The program's own: a k 1.0 result of status "disqualified" is stored (its rows are not counted) and is one
  `run_disqualified` event (once a (pid, night)).
STATED LIMIT: a bar that never comes (a halted stock's session has none) leaves every program that held it without
rows from that day on, because `screen.series` refuses a held lot with no price; nothing is tagged meanwhile, so the
days fill the night it does.

A RESTATED DAY: a stored day of tonight's engine id whose r or w differs from the recompute by more than
`forward_db.TOL` is a `restated` event; the row stays (the first write stands). It is DATA, never an error: its
payload says whether the bars hash of a decision on or before that day moved ("bars": "moved" | "same").

The receipt: {through, engine, programs, sessions, new_days, restated, checks, stale, errors, data_failed,
disqualified, retried, budget_hit, seconds, controls, twins, head}: counts and verdicts, never a program's figure.
Every alert text holds ids, counts and dates only. Standard library and numpy only.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Mapping

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


class NightFailed(RuntimeError):
    """The preflight failed (a decider that cannot start or answer, a canary that does not run "ok"): the House's.
    No program is run, marked or tagged; the job's receipt is {"status": "failed", "error"}."""


def quiet(now: float) -> bool:
    """Whether epoch `now` is inside `QUIET` (09:00-17:30 New York time) on a session: the job then skips (the evening
    run does the night)."""
    raise NotImplementedError("B: league/ops/forward_shadow.py quiet")


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py): skipped when `forward_db.mode` is "off", inside `quiet`, or with no forward
    day in the store; else `Decider(log=<root>/forward-decider.log)` (its own instance; `InlineDecider` in tests
    only), `Shadow(...).night()`, the decider closed in `finally`. A `NightFailed` from the preflight is {"status":
    "failed", "error": ...} (the ops runner starts the job again inside its grace). A `MissingData` on opening the
    store (it is being rewritten) is a failed receipt too."""
    raise NotImplementedError("B: league/ops/forward_shadow.py run")


class Shadow:
    """One night's recompute over the state root `root` and the forward store `db` (the module docstring). `decider`: a
    `league.live.decider` `Decider` or `InlineDecider`; `settings`: the swarm's; `clock`: epoch seconds; `fresh`: a
    callable giving a newly started decider for THE RETRY (the job passes one that closes the old child first; None:
    no retry).

    Attributes: `store` (the `EquityStore` opened with the capability), `through` (its `fetched_through`: the night's
    name) and `engine` (tonight's engine id)."""

    def __init__(self, root: str | Path, db: sqlite3.Connection, *, decider: Any, settings: Mapping[str, Any] | None,
                 clock: Callable[[], float] = time.time, fresh: Callable[[], Any] | None = None):
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.__init__")

    def preflight(self) -> None:
        """`decider.ping()` answers ok AND `CANARY` runs "ok" over the store's last five forward days through the
        same child op; else `NightFailed` and one `night_failed` event (once a night): no `fwd_runs` row, no
        `run_failed`, nothing tagged."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.preflight")

    def due(self) -> list[Program]:
        """The active non-control programs whose last stored day is before `through`: tag "live" first, then reasons
        seed and train_pass, then train_fail, then the suspects; inside a class the oldest last-stored day first,
        then pid (so the programs a budget left stale go first the next night)."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.due")

    def slice(self, program: Program, *, first_day: dt.date | None = None) -> Any:
        """The program's forward `store.Bars` from `first_day` (its own when None) through `through`; None when that
        first day is after `through`. `MissingData`, `StoreRefused` and `ValueError` are the data's."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.slice")

    def run_from(self, program: Program, first_day: dt.date, *, k: float = 1.0) -> ShadowRun | None:
        """D3's run of `program` started flat at another first day (the twin runs of league/ops/forward_twins.py);
        None when that day is after `through`. Raises as `run_program` does."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.run_from")

    def official(self, symbol: str, day: dt.date | str, at: str) -> float | None:
        """The store's raw open (`at` "open") or close ("close") of `symbol` on `day` (`engine.official`); None when
        it has no bar: the timing table's official price."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.official")

    def run_program(self, program: Program) -> tuple[ShadowRun, Mapping[str, Any]]:
        """(the k 1.0 run, the k 1.5 result) of one program on its forward days. Raises E1's `runner.RunFailed` or
        the decider's `DeciderError` (the child's), or `MissingData`, `StoreRefused`, `ValueError` (the data's)."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.run_program")

    def write(self, run: ShadowRun, result15: Mapping[str, Any]) -> dict[str, int]:
        """One transaction a program: {"new_days", "restated", "checks"}. New days are inserted under tonight's engine
        id, each with its decision's bars hash; a stored day of that id whose r or w differs by more than
        `forward_db.TOL` is a `restated` event (the row stays; once a (pid, day) and value: `once` = the engine id and
        the first 8 hex of sha256 of the new r and w rounded to 9 places); the due checkpoints (D4); a k 1.0 result
        of status "disqualified" is one `run_disqualified` event (once a (pid, night))."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.write")

    def controls(self) -> dict[str, int]:
        """The controls' rows, in the parent (no child): {"groups", "rows"}. For each registered control:
        `forward_controls.control_lots` at k 1.0, 1.5 and 0.0, `screen.series`, `forward_controls.cost_free`; its
        `fwd_days` rows with `r0` (and `bars` NULL: a control reads no bar); its checkpoints with `t_x0` and `p_x0`
        beside D4's."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.controls")

    def finals(self) -> int:
        """The FINAL checkpoint (D4) of each stopped pid that has none; how many were written."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.finals")

    def night(self) -> dict[str, Any]:
        """THE NIGHT (the module docstring), resumable: a night killed after one program resumes with no duplicate
        (a program already written through `through` is skipped). The job's receipt."""
        raise NotImplementedError("B: league/ops/forward_shadow.py Shadow.night")


__all__ = ["GATE_REASON", "DECIDER_LOG", "QUIET", "CANARY", "NightFailed", "quiet", "run", "Shadow"]

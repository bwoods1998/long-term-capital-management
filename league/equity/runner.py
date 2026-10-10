"""The equity runs' entry points: in-process (the decider child's), and the decider-isolated wrapper the swarm uses.

Owner: core. Amendment A3: no Gym box for equity. Train, Validation, the sealed look and the screen's Train-era runs
all run ON THE HOUSE, the program inside the decider-isolated child (uid 65534, its own network namespace, rlimits, an
empty environment): the PARENT opens the store (with the gate's capability for a look), slices `store.Bars`, and sends
the arrays; the CHILD (league/equity/child.py, the decider's "equity" kind) loads the program and calls the in-process
entry point here. A program never reaches the store and the store never leaves the House.

IN-PROCESS (the child's; tests call them directly):

    run_bars(code, params, bars, *, name, k=1.0, capital=None) -> result      # one run over a Bars slice

IN THE PARENT (league/swarm/tournament.py, league/swarm/gate.py, league/swarm/elane.py, league/equity/screen.py
`floor_inputs`):

    iso = Isolated(decider, store_root)                     # `decider`: a league.live.decider Decider/InlineDecider
    iso.train(code, params, name=..., start=..., end=..., k=1.0) -> Run
    iso.validation(code, params, name=..., k=1.0) -> Run
    iso.look(code, params, name=..., gate=<EquityGateCapability>, k=1.0) -> Run              # the sealed look (A9 D6)
    iso.segments(code, params, name=...) -> list[Run]       # config.TRAIN_ERA_SEGMENTS, one run each (the floor's)

A `Run` is (result, bars): the whole result record and the exact `store.Bars` slice it ran on, so the screen's
accounting (league/equity/screen.py `series`) reads the same prices the engine filled at.

Each parent call reads `needs` from the program first (a "load" through the child, so the parent never executes it),
slices the store for NEEDS symbols and history, and sends ("kind", "equity", "run", payload) with payload
{"code", "params", "name", "bars": Bars, "k", "capital"}; the answer's `result` is the whole record (in-House only;
`results.view` decides what a researcher sees). A child failure raises `RunFailed` (no trial is counted).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class RunFailed(RuntimeError):
    """The isolated run did not return a result (the child failed, timed out or refused the program)."""


@dataclass(frozen=True)
class Run:
    """One isolated run: `result` (the whole record, league/equity/results.py) and `bars` (the `store.Bars` it ran on)."""

    result: dict[str, Any]
    bars: Any


#: The child's budget for one run (seconds): a year of daily decisions at a second each is far under it.
RUN_BUDGET_SECONDS = 1200.0


def run_bars(code: str, params: Mapping[str, Any] | None, bars: Any, *, name: str = "program", k: float = 1.0,
             capital: Any = None) -> dict[str, Any]:
    """Load the program and replay it over `bars` (`engine.run`); CodeRefused / NeedsRefused when it does not load.
    `capital` None is `config.SLEEVE_USD`."""
    raise NotImplementedError("core: league/equity/runner.py run_bars")


class Isolated:
    """The parent side: slices the store and runs the program in the decider child (the module docstring)."""

    def __init__(self, decider: Any, store_root: str | Path, *, budget_seconds: float = RUN_BUDGET_SECONDS):
        raise NotImplementedError("core: league/equity/runner.py Isolated")

    def needs(self, code: str, params: Mapping[str, Any] | None, *, name: str) -> dict[str, Any]:
        """The program's NEEDS as the child parsed it ({symbols, history, max_hold_sessions}); ProgramRefused."""
        raise NotImplementedError("core: league/equity/runner.py Isolated.needs")

    def train(self, code: str, params: Mapping[str, Any] | None, *, name: str, start: dt.date | None = None,
              end: dt.date | None = None, k: float = 1.0) -> Run:
        raise NotImplementedError("core: league/equity/runner.py Isolated.train")

    def validation(self, code: str, params: Mapping[str, Any] | None, *, name: str, k: float = 1.0) -> Run:
        raise NotImplementedError("core: league/equity/runner.py Isolated.validation")

    def look(self, code: str, params: Mapping[str, Any] | None, *, name: str, gate: Any,
             k: float = 1.0) -> Run:
        """The ONE sealed look: `config.LOOK_FIRST` through min(the last close before now, `config.LOOK_CAP`) (A9 D6;
        the store's holdout and forward days). `gate` must be an `EquityGateCapability` (StoreRefused otherwise)."""
        raise NotImplementedError("core: league/equity/runner.py Isolated.look")

    def segments(self, code: str, params: Mapping[str, Any] | None, *, name: str) -> list[Run]:
        """One run over each of `config.TRAIN_ERA_SEGMENTS` (the screen's per-program floor), in order."""
        raise NotImplementedError("core: league/equity/runner.py Isolated.segments")


__all__ = ["RunFailed", "Run", "RUN_BUDGET_SECONDS", "run_bars", "Isolated"]

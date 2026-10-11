"""The equity runs' entry points: in-process (the decider child's), and the decider-isolated wrapper the swarm uses.

Owner: core. Amendment A3: no Gym box for equity. Train, Validation, the sealed look and the screen's Train-era runs
all run ON THE HOUSE, the program inside the decider-isolated child (uid 65534, its own network namespace, rlimits, an
empty environment): the PARENT opens the store (with the gate's capability for a look), slices `store.Bars`, and sends
the arrays; the CHILD (league/equity/child.py, the decider's "equity" kind) loads the program and calls the in-process
entry point here. A program never reaches the store and the store never leaves the House.

IN-PROCESS (the child's; tests call them directly):

    run_bars(code, params, bars, *, name, k=1.0, capital=None) -> result      # one run over a Bars slice

IN THE PARENT (league/swarm/elane.py `validate` and `look`, dispatched by league/swarm/tournament.py and
league/swarm/gate.py; the screen's floor reads `segments` through `look`: `Isolated.segments` -> `screen.series` ->
`screen.floor`):

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
`results.view` decides what a researcher sees). A child failure raises `RunFailed` (no trial is counted); a program the
child refuses (it does not load) raises `ProgramRefused` (a `CodeRefused`). The parent re-checks the child's NEEDS
(`program.parse_needs`) before it slices anything, so a child's answer never widens what is read.

SENT, AND NOT ANSWERED (`RunLost`, a `RunFailed`). A failure before the bars leave the parent (the NEEDS call, the
store's slice) is the House's and raises `RunFailed`. Once the "run" was sent, the program held its bars: a child that
then fails, is killed, runs past its budget or answers an error raises `RunLost`. The difference matters for the sealed
look alone (league/swarm/elane.py `look`): a program that could choose not to answer, and be owed its look again, would
draw its holdout more than once.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from . import config
from .program import CodeRefused, Needs, NeedsRefused, load_program, parse_needs
from .store import LOOK, EquityGateCapability, EquityStore, StoreRefused

KIND = "equity"
#: The child's budget for learning a program's NEEDS (a load and a parse).
NEEDS_BUDGET_SECONDS = 60.0


class RunFailed(RuntimeError):
    """The isolated run did not return a result (the child failed, timed out or refused the program)."""


class RunLost(RunFailed):
    """The run was sent (the program held its bars) and no result came back: the child failed, was killed, ran past its
    budget or answered an error AFTER the send (the module docstring)."""


class ProgramRefused(CodeRefused):
    """The decider child refused the program (it does not load: the child's reason)."""


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
    from .engine import EngineConfig, run_isolated

    program = load_program(code, name=name, params=params)
    capital = config.SLEEVE_USD if capital is None else Decimal(str(capital))
    return run_isolated(program, bars, cfg=EngineConfig(capital=capital, k=float(k)))


class Isolated:
    """The parent side: slices the store and runs the program in the decider child (the module docstring)."""

    def __init__(self, decider: Any, store_root: str | Path, *, budget_seconds: float = RUN_BUDGET_SECONDS):
        self.decider = decider
        self.store_root = Path(store_root)
        self.budget_seconds = float(budget_seconds)

    def _ask(self, op: str, payload: Mapping[str, Any], budget: float) -> Mapping[str, Any]:
        try:
            answer = self.decider.kind(KIND, op, payload, budget_seconds=budget)
        except Exception as exc:  # noqa: BLE001 - the child failed or timed out (it was restarted): no trial
            raise RunFailed(f"the decider child failed the {op}: {type(exc).__name__}: {str(exc)[:300]}") from None
        if not isinstance(answer, Mapping):
            raise RunFailed(f"the decider child answered the {op} with a {type(answer).__name__}")
        if not answer.get("ok"):
            if answer.get("refused"):
                raise ProgramRefused(str(answer.get("error") or "the program does not load"))
            raise RunFailed(str(answer.get("error") or f"the decider child did not answer the {op}"))
        return answer

    def needs(self, code: str, params: Mapping[str, Any] | None, *, name: str) -> dict[str, Any]:
        """The program's NEEDS as the child parsed it ({symbols, history, max_hold_sessions}); ProgramRefused."""
        answer = self._ask("needs", {"code": code, "params": dict(params or {}), "name": name}, NEEDS_BUDGET_SECONDS)
        return self._parsed(answer).as_dict()

    @staticmethod
    def _parsed(answer: Mapping[str, Any]) -> Needs:
        try:
            return parse_needs(answer.get("needs"))
        except NeedsRefused as exc:
            raise RunFailed(f"the child's NEEDS do not parse: {exc}") from None

    def _needs(self, code: str, params: Mapping[str, Any] | None, name: str) -> Needs:
        return self._parsed(self._ask("needs", {"code": code, "params": dict(params or {}), "name": name},
                                      NEEDS_BUDGET_SECONDS))

    def _run(self, code: str, params: Mapping[str, Any] | None, name: str, bars: Any, k: float) -> Run:
        payload = {"code": code, "params": dict(params or {}), "name": name, "bars": bars, "k": float(k),
                   "capital": None}
        try:
            answer = self._ask("run", payload, self.budget_seconds)
        except RunFailed as exc:  # after the send: the program held its bars (`RunLost`); a refused load is not a run
            raise RunLost(str(exc)) from None
        result = answer.get("result")
        if not isinstance(result, Mapping):
            raise RunLost("the decider child returned no result")
        if result.get("status") == "error":
            raise RunLost(str(result.get("reason") or "the run ended in an error"))
        return Run(dict(result), bars)

    def train(self, code: str, params: Mapping[str, Any] | None, *, name: str, start: dt.date | None = None,
              end: dt.date | None = None, k: float = 1.0) -> Run:
        """One Train run (2016-01-04..2024-12-31, cut to [start, end])."""
        needs = self._needs(code, params, name)
        bars = EquityStore(self.store_root).bars(needs.symbols, "train", history=needs.history, start=start, end=end)
        return self._run(code, params, name, bars, k)

    def validation(self, code: str, params: Mapping[str, Any] | None, *, name: str, k: float = 1.0) -> Run:
        """The Validation run (2025)."""
        needs = self._needs(code, params, name)
        bars = EquityStore(self.store_root).bars(needs.symbols, "validation", history=needs.history)
        return self._run(code, params, name, bars, k)

    def look(self, code: str, params: Mapping[str, Any] | None, *, name: str, gate: Any,
             k: float = 1.0) -> Run:
        """The ONE sealed look: `config.LOOK_FIRST` through min(the last close before now, `config.LOOK_CAP`) (A9 D6 as
        amended by A12: 2026-10-09; the store's holdout and forward days). `gate` must be an `EquityGateCapability` (StoreRefused otherwise)."""
        if not isinstance(gate, EquityGateCapability):
            raise StoreRefused("the sealed look needs the gate's EquityGateCapability")
        store = EquityStore(self.store_root, gate=gate)
        needs = self._needs(code, params, name)
        bars = store.bars(needs.symbols, LOOK, history=needs.history)
        return self._run(code, params, name, bars, k)

    def segments(self, code: str, params: Mapping[str, Any] | None, *, name: str) -> list[Run]:
        """One run over each of `config.TRAIN_ERA_SEGMENTS` (the screen's per-program floor), in order."""
        needs = self._needs(code, params, name)
        store = EquityStore(self.store_root)
        return [self._run(code, params, name, store.span(needs.symbols, first, last, history=needs.history), 1.0)
                for first, last in config.TRAIN_ERA_SEGMENTS]


__all__ = ["RunFailed", "RunLost", "ProgramRefused", "Run", "RUN_BUDGET_SECONDS", "NEEDS_BUDGET_SECONDS", "KIND",
           "run_bars", "Isolated"]

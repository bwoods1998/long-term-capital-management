"""The panel runs' entry points: in-process (the decider child's), and the decider-isolated wrapper the swarm uses.

Owner: package D. The names E1's runner already has are re-exported (`RunFailed`, `RunLost`, `ProgramRefused`,
`SENT_NOT_ANSWERED`: one set of classes, so E1's rules read a panel run's failure as they read an equity run's).

As E1's (amendment A3): every panel run is ON THE HOUSE, the program inside the decider-isolated child. The PARENT
opens the store (with E1's gate capability for a sealed window), learns NEEDS through the child and re-parses them,
builds the `store.Slice` (run key `run_sha|window|first run day`, D8), and sends
`decider.kind("panel", "run", {"code", "params", "name", "bars": PanelBars, "k", "capital", "placebos", "seed",
"calls", "style", "nice"}, budget_seconds=...)`. The CHILD (league/xs/child.py) loads the program and calls `run_bars`. A
program never reaches the store, an aid or a symbol, and the store never leaves the House.

IN-PROCESS (the child's; tests call it directly):

    run_bars(code, params, bars, *, name, k=1.0, capital=None, placebos=0, seed=None, calls=False, style=False)

IN THE PARENT (league/swarm/elane_xs.py's `runner`, over its own niced decider):

    iso = Isolated(decider, store_root)
    iso.needs(code, params, name=...) -> dict
    iso.train(code, params, name=..., start=..., end=..., k=1.0, half=None, placebos=0, calls=False, style=False)
    iso.validation(code, params, name=..., k=1.0)
    iso.look(code, params, name=..., gate=<EquityGateCapability>, k=1.0, placebos=<the receipt's>, seed=<look_seed>)
    iso.segments(code, params, name=...) -> [Run, Run]        # config.TRAIN_SEGMENTS whole: the floor's pools
    iso.forward(code, params, name=..., gate=..., start=..., run_key=None, aids=None, k=1.0)    # package J's
    state_stream(run) -> each called decision's Inputs        # the restart check's, for a run made with calls=True

A run the child took whole and never answered is `RunLost` (every other failure a plain `RunFailed`), exactly as E1's
`Isolated._run` tells them apart: the sealed look's rule needs the difference.

THE LOOK'S RUN (the pinned pre-registration's 4.1; it differs from E1's look, which starts at the holdout): ONE run
that starts flat at Validation's first session and runs through the holdout (`store.PanelStore.bars("look", ...)`),
with the receipt's placebo draws under the seed fixed before the look (`placebo.look_seed`). Its Validation sessions
repeat the Validation run's; a lot opened in Validation and still open in the holdout keeps its Validation-dated cell.

THE SEEDS OF A TRAIN RUN'S PLACEBOS (the Train bar's rank, never evidence): `placebo.train_seed(run_sha, "train|" +
the span's first run day)`, so each seen span of a version draws its own stream and placebo m of one span pairs with
an independent placebo m of the next (`placebo.stat`).

Evidence module (in the xs identity; one of its roots).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ..equity.runner import SENT_NOT_ANSWERED, ProgramRefused, RunFailed, RunLost
from ..equity.store import EquityGateCapability, StoreRefused, as_date, from_ordinal
from . import config

KIND = "panel"
#: The child's budget for one run (seconds), and for learning a program's NEEDS.
RUN_BUDGET_SECONDS = 600.0
NEEDS_BUDGET_SECONDS = 60.0
#: The niceness a research child raises itself to, once (`os.nice`); the live decider's child passes none.
NICE = 19


@dataclass(frozen=True)
class Run:
    """One isolated run: `result` (the whole record, league/xs/results.py) and `slice` (the `store.Slice` it ran on:
    the parent's, with its aids and run key)."""

    result: dict[str, Any]
    slice: Any


def run_bars(code: str, params: Mapping[str, Any] | None, bars: Any, *, name: str = "program", k: float = 1.0,
             capital: Any = None, placebos: int = 0, seed: int | None = None,
             calls: bool = False, style: bool = False) -> dict[str, Any]:
    """Load the program and replay it over `bars` (`engine.run_isolated`): the child's entry point, and the tests'.
    CodeRefused / NeedsRefused when it does not load. `capital` None is `config.XS_SLEEVE_USD`. `style`: the run's
    style block in `result["style"]` (the captain's A22; `league.xs.style.block`)."""
    from . import program as _program
    from .engine import EngineConfig, run_isolated

    loaded = _program.load_program(code, name=name, params=params)
    capital = config.XS_SLEEVE_USD if capital is None else Decimal(str(capital))
    return run_isolated(loaded, bars, cfg=EngineConfig(capital=capital, k=float(k)), placebos=int(placebos),
                        calls=bool(calls), seed=None if seed is None else int(seed), style=bool(style))


def gym_key(run_sha: str, window: str, first: dt.date) -> str:
    """D8: a Gym run's key, `run_sha|window|first run day`: its ids, sector codes and dither are salted with it, so
    they are stable inside the run and unrelated across runs, versions and programs."""
    return f"{run_sha}|{window}|{first.isoformat()}"


class Isolated:
    """The parent side: slices the panel store and runs the program in the decider child (the module docstring).
    `decider`: a league.live.decider Decider / InlineDecider. `nice`: sent with every run (research deciders only)."""

    def __init__(self, decider: Any, store_root: str | Path, *, budget_seconds: float = RUN_BUDGET_SECONDS,
                 nice: int | None = NICE):
        self.decider = decider
        self.store_root = Path(store_root)
        self.budget_seconds = float(budget_seconds)
        self.nice = None if nice is None else int(nice)

    # ------------------------------------------------------------------ the child
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

    def _program(self, code: str, params: Mapping[str, Any] | None, name: str) -> tuple[Any, str]:
        """(the program's NEEDS, re-parsed by the parent; its run sha), learnt through the child: the parent never
        executes a program, and a child's answer never widens what is read."""
        from . import program as _program

        answer = self._ask("needs", {"code": code, "params": dict(params or {}), "name": name}, NEEDS_BUDGET_SECONDS)
        try:
            needs = _program.parse_needs(answer.get("needs"))
        except _program.NeedsRefused as exc:
            raise RunFailed(f"the child's NEEDS do not parse: {exc}") from None
        run_sha = answer.get("run_sha")
        if not isinstance(run_sha, str) or len(run_sha) != 64:
            raise RunFailed("the child's answer names no run sha")
        return needs, run_sha

    def needs(self, code: str, params: Mapping[str, Any] | None, *, name: str) -> dict[str, Any]:
        """The program's NEEDS as the child parsed them and the parent re-parsed (`program.Needs.as_dict`);
        ProgramRefused."""
        return self._program(code, params, name)[0].as_dict()

    def _store(self, gate: Any = None) -> Any:
        from . import store as _store

        return _store.PanelStore(self.store_root, gate=gate)

    @staticmethod
    def _first(sessions: Sequence[dt.date], what: str) -> dt.date:
        if not sessions:
            raise RunFailed(f"the panel store holds no session of {what}")
        return sessions[0]

    def _run(self, code: str, params: Mapping[str, Any] | None, name: str, piece: Any, k: float, *,
             placebos: int = 0, seed: int | None = None, calls: bool = False, style: bool = False) -> Run:
        payload = {"code": code, "params": dict(params or {}), "name": name, "bars": piece.bars, "k": float(k),
                   "capital": None, "placebos": int(placebos), "seed": None if seed is None else int(seed),
                   "calls": bool(calls), "style": bool(style), "nice": self.nice}
        try:
            answer = self._ask("run", payload, self.budget_seconds)
        except RunFailed as exc:
            if any(mark in str(exc) for mark in SENT_NOT_ANSWERED):
                raise RunLost(str(exc)) from None  # sent whole, never answered: the program held its bars
            raise
        result = answer.get("result")
        if not isinstance(result, Mapping):
            raise RunFailed("the decider child returned no result")
        if result.get("status") == "error":
            raise RunFailed(str(result.get("reason") or "the run ended in an error"))
        return Run(dict(result), piece)

    # ------------------------------------------------------------------ the runs
    def train(self, code: str, params: Mapping[str, Any] | None, *, name: str, start: dt.date, end: dt.date,
              k: float = 1.0, half: int | None = None, placebos: int = 0, calls: bool = False,
              style: bool = False) -> Run:
        """One Train run over [start, end] inside ONE span of `config.TRAIN_SEGMENTS` (a seen span, a hidden year),
        starting flat; `half`: a D18 half run; `placebos`: the Train bar's, under `placebo.train_seed`; `style`: the
        run's style block (the captain's A22: asked of the seen spans' full-universe runs at k 1.0)."""
        from . import placebo as _placebo

        start, end = as_date(start), as_date(end)
        needs, run_sha = self._program(code, params, name)
        store = self._store()
        first = self._first([d for d in store.sessions("train") if start <= d <= end], f"Train in {start}..{end}")
        piece = store.train(start, end, history=needs.history, run_key=gym_key(run_sha, "train", first), half=half)
        seed = _placebo.train_seed(run_sha, f"train|{first.isoformat()}") if int(placebos) > 0 else None
        run = self._run(code, params, name, piece, k, placebos=placebos, seed=seed, calls=calls, style=style)
        run.result["half"] = half           # the parent's fact: the child reads `elig0`, never which half it is
        return run

    def validation(self, code: str, params: Mapping[str, Any] | None, *, name: str, k: float = 1.0) -> Run:
        """The Validation run (2025), starting flat."""
        needs, run_sha = self._program(code, params, name)
        store = self._store()
        first = self._first(store.sessions("validation"), "Validation")
        piece = store.bars("validation", history=needs.history, run_key=gym_key(run_sha, "validation", first))
        return self._run(code, params, name, piece, k)

    def look(self, code: str, params: Mapping[str, Any] | None, *, name: str, gate: Any, k: float = 1.0,
             placebos: int, seed: int) -> Run:
        """The ONE sealed look's run (the module docstring): Validation's first session through min(the store's last
        close, `league.equity.config.LOOK_CAP`), with `placebos` draws under `seed`, read on the spans "V" and "H".
        `gate` must be E1's `EquityGateCapability` (StoreRefused otherwise)."""
        if not isinstance(gate, EquityGateCapability):
            raise StoreRefused("the sealed look needs the gate's EquityGateCapability")
        if int(placebos) < 1:
            raise ValueError("the look draws the receipt's placebos")
        store = self._store(gate)
        needs, run_sha = self._program(code, params, name)
        first = self._first(store.sessions("look"), "the look")
        piece = store.bars("look", history=needs.history, run_key=gym_key(run_sha, "look", first))
        return self._run(code, params, name, piece, k, placebos=int(placebos), seed=int(seed))

    def segments(self, code: str, params: Mapping[str, Any] | None, *, name: str) -> list[Run]:
        """One run over each of `config.TRAIN_SEGMENTS`, whole, at k 1.0, in order: the floor's pools, and the two
        Train series the lineage rule keeps (x and u)."""
        needs, run_sha = self._program(code, params, name)
        store = self._store()
        sessions = store.sessions("train")
        out = []
        for start, end in config.TRAIN_SEGMENTS:
            first = self._first([d for d in sessions if start <= d <= end], f"the Train segment {start}..{end}")
            piece = store.train(start, end, history=needs.history, run_key=gym_key(run_sha, "train", first))
            out.append(self._run(code, params, name, piece, 1.0))
        return out

    def forward(self, code: str, params: Mapping[str, Any] | None, *, name: str, gate: Any, start: dt.date,
                run_key: str | None = None, aids: Sequence[int] | None = None, k: float = 1.0) -> Run:
        """Package J's: the forward days from `start`, starting flat. `run_key`: the instance id for a live
        instance's twin (so the twin reads the ids, the sector codes and the dither the live ctx read), with `aids`
        its columns."""
        if not isinstance(gate, EquityGateCapability):
            raise StoreRefused("the forward days need the forward record's EquityGateCapability")
        start = as_date(start)
        store = self._store(gate)
        needs, run_sha = self._program(code, params, name)
        first = self._first([d for d in store.sessions("forward") if d >= start], f"the forward days from {start}")
        key = gym_key(run_sha, "forward", first) if run_key is None else str(run_key)
        piece = store.bars("forward", history=needs.history, run_key=key, start=first, aids=aids)
        return self._run(code, params, name, piece, k)


def state_stream(run: Run) -> Iterator[Any]:
    """For a run made with `calls=True`: each CALLED decision's `ctx.Inputs`, rebuilt by `ctx.inputs_from_panel(
    run.slice.bars, t, **book)` from the run's `calls`. `RunFailed` (the House's, never the program's) when a rebuilt
    ctx's sha is not the `ctx_sha` the run's `picks` recorded for that call. The restart check decides on these."""
    from . import ctx as _ctx
    from . import program as _program

    result, bars = run.result, run.slice.bars
    calls = result.get("calls")
    if not isinstance(calls, list):
        raise RunFailed("the run carries no calls (it was not made with calls=True)")
    try:
        needs = _program.parse_needs(result.get("needs"))
    except _program.NeedsRefused as exc:
        raise RunFailed(f"the run's NEEDS do not parse: {exc}") from None
    called = [pick for pick in result.get("picks") or () if pick.get("called")]
    if len(called) != len(calls):
        raise RunFailed(f"the run holds {len(calls)} calls for {len(called)} called decisions")
    for call, pick in zip(calls, called):
        try:
            t = int(call["t"])
            day = from_ordinal(int(bars.days[t])).isoformat()
            inputs = _ctx.inputs_from_panel(bars, t, needs=needs, positions=call["positions"], closed=call["closed"],
                                            rejects=call["rejects"], cash=call["cash"], equity=call["equity"],
                                            budget=call["budget"], params=result.get("params") or {})
            sha = hashlib.sha256(_ctx.ctx_bytes(_ctx.build(inputs))).hexdigest()
        except RunFailed:
            raise
        except Exception as exc:  # noqa: BLE001 - whatever the rebuild met, the stream is not the run's
            raise RunFailed(f"a call's inputs could not be rebuilt: {type(exc).__name__}: {str(exc)[:200]}") from None
        if day != pick.get("decided") or sha != pick.get("ctx_sha"):
            raise RunFailed("a rebuilt ctx is not the ctx the run's call read (the House's fault, never the "
                            "program's): the restart check has no stream to decide on")
        yield inputs


__all__ = ["KIND", "RUN_BUDGET_SECONDS", "NEEDS_BUDGET_SECONDS", "NICE", "RunFailed", "RunLost", "ProgramRefused",
           "SENT_NOT_ANSWERED", "Run", "run_bars", "gym_key", "Isolated", "state_stream"]

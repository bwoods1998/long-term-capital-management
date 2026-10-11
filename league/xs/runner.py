"""The panel runs' entry points: in-process (the decider child's), and the decider-isolated wrapper the swarm uses.

Owner: package D. STEP 0 STUB: the names E1's runner already has are re-exported for real (`RunFailed`, `RunLost`,
`ProgramRefused`, `SENT_NOT_ANSWERED`: one set of classes, so E1's rules read a panel run's failure as they read an
equity run's); everything else raises NotImplementedError until D lands.

As E1's (amendment A3): every panel run is ON THE HOUSE, the program inside the decider-isolated child. The PARENT
opens the store (with E1's gate capability for a sealed window), learns NEEDS through the child and re-parses them,
builds the `store.Slice` (run key `run_sha|window|first run day`, D8), and sends
`decider.kind("panel", "run", {"code", "params", "name", "bars": PanelBars, "k", "capital", "placebos", "seed",
"calls", "style", "nice"}, budget_seconds=...)`. The CHILD (league/xs/child.py) loads the program and calls `run_bars`. A
program never reaches the store, an aid or a symbol, and the store never leaves the House.

A run the child took whole and never answered is `RunLost` (every other failure a plain `RunFailed`), exactly as E1's
`Isolated._run` tells them apart: the sealed look's rule needs the difference.

THE LOOK'S RUN (the pinned pre-registration's 4.1; it differs from E1's look, which starts at the holdout): ONE run
that starts flat at Validation's first session and runs through the holdout (`store.PanelStore.bars("look", ...)`),
with the receipt's placebo draws under the seed fixed before the look (`placebo.look_seed`). Its Validation sessions
repeat the Validation run's; a lot opened in Validation and still open in the holdout keeps its Validation-dated cell.

Evidence module (in the xs identity; one of its roots).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ..equity.runner import SENT_NOT_ANSWERED, ProgramRefused, RunFailed, RunLost

KIND = "panel"
#: The child's budget for one run (seconds), and for learning a program's NEEDS.
RUN_BUDGET_SECONDS = 600.0
NEEDS_BUDGET_SECONDS = 60.0
#: The niceness a research child raises itself to, once (`os.nice`); the live decider's child passes none.
NICE = 19

_STUB = "league.xs.runner is a Step 0 stub: package D builds it (league/xs/E4_INTERFACES.md)"


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
    raise NotImplementedError(_STUB)


class Isolated:
    """The parent side: slices the panel store and runs the program in the decider child (the module docstring).
    `decider`: a league.live.decider Decider / InlineDecider. `nice`: sent with every run (research deciders only)."""

    def __init__(self, decider: Any, store_root: str | Path, *, budget_seconds: float = RUN_BUDGET_SECONDS,
                 nice: int | None = NICE):
        raise NotImplementedError(_STUB)

    def needs(self, code: str, params: Mapping[str, Any] | None, *, name: str) -> dict[str, Any]:
        """The program's NEEDS as the child parsed them and the parent re-parsed (`program.Needs.as_dict`);
        ProgramRefused."""
        raise NotImplementedError(_STUB)

    def train(self, code: str, params: Mapping[str, Any] | None, *, name: str, start: dt.date, end: dt.date,
              k: float = 1.0, half: int | None = None, placebos: int = 0, calls: bool = False,
              style: bool = False) -> Run:
        """One Train run over [start, end] inside ONE span of `config.TRAIN_SEGMENTS` (a seen span, a hidden year),
        starting flat; `half`: a D18 half run; `placebos`: the Train bar's, under `placebo.train_seed`; `style`: the
        run's style block (the captain's A22: asked of the seen spans' full-universe runs at k 1.0)."""
        raise NotImplementedError(_STUB)

    def validation(self, code: str, params: Mapping[str, Any] | None, *, name: str, k: float = 1.0) -> Run:
        """The Validation run (2025), starting flat."""
        raise NotImplementedError(_STUB)

    def look(self, code: str, params: Mapping[str, Any] | None, *, name: str, gate: Any, k: float = 1.0,
             placebos: int, seed: int) -> Run:
        """The ONE sealed look's run (the module docstring): Validation's first session through min(the store's last
        close, `league.equity.config.LOOK_CAP`), with `placebos` draws under `seed`, read on the spans "V" and "H".
        `gate` must be E1's `EquityGateCapability` (StoreRefused otherwise)."""
        raise NotImplementedError(_STUB)

    def segments(self, code: str, params: Mapping[str, Any] | None, *, name: str) -> list[Run]:
        """One run over each of `config.TRAIN_SEGMENTS`, whole, at k 1.0, in order: the floor's pools, and the two
        Train series the lineage rule keeps (x and u)."""
        raise NotImplementedError(_STUB)

    def forward(self, code: str, params: Mapping[str, Any] | None, *, name: str, gate: Any, start: dt.date,
                run_key: str | None = None, aids: Sequence[int] | None = None, k: float = 1.0) -> Run:
        """Package J's: the forward days from `start`, starting flat. `run_key`: the instance id for a live
        instance's twin (so the twin reads the ids, the sector codes and the dither the live ctx read), with `aids`
        its columns."""
        raise NotImplementedError(_STUB)


def state_stream(run: Run) -> Iterator[Any]:
    """For a run made with `calls=True`: each CALLED decision's `ctx.Inputs`, rebuilt by `ctx.inputs_from_panel(
    run.slice.bars, t, **book)` from the run's `calls`. `RunFailed` (the House's, never the program's) when a rebuilt
    ctx's sha is not the `ctx_sha` the run's `picks` recorded for that call. The restart check decides on these."""
    raise NotImplementedError(_STUB)


__all__ = ["KIND", "RUN_BUDGET_SECONDS", "NEEDS_BUDGET_SECONDS", "NICE", "RunFailed", "RunLost", "ProgramRefused",
           "SENT_NOT_ANSWERED", "Run", "run_bars", "Isolated", "state_stream"]

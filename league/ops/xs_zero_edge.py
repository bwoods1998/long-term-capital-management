"""The `xs_zero_edge` job: what the panel Train bar passes at ZERO edge, measured every week on the bar as built.

Owner: package G of release E4. Protected (league/ops/). STEP 0 STUB: the constants are the contract; every function
raises NotImplementedError until G lands. The registry rows are package A's patch (E4-SPEC 13: four chunks on Sunday).

Each week `elane.panel.zero_edge_programs` (100) seeded RANDOM-SCORE programs (the top k by a hash of (seed, id,
decision index); k in `KS`; weekly and monthly; each with a hidden year drawn as a family's is) run the WHOLE bar
equity-xs-v1, the restart check included, through the job's own niced decider (never the swarm's, never the live
one), `PROGRAMS_RUN` a run. Into the swarm store's kv `elane_xs_zero_edge` {week: {programs, passes, by_rule}}: the
Train map shows each cell's passes beside births x that pass rate (the ZERO-EDGE EXPECTED column). An alarm when the
rate is above `ALARM_RATE`: the bar is too loose. Rule-level figures only: no program of the swarm is read, and no
result of one is written.
"""

from __future__ import annotations

from typing import Any

KV = "elane_xs_zero_edge"
PROGRAMS_RUN = 25
KS = (5, 8, 12)
SCHEDULES = ("weekly", "monthly")
ALARM_RATE = 0.05
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 3000

_STUB = "league.ops.xs_zero_edge is a Step 0 stub: package G builds it (league/xs/E4_INTERFACES.md)"


def program_code(seed: int, k: int, rebalance: str) -> str:
    """The source of one random-score panel program (XS.md's contract; no signal: its picks are a hash's)."""
    raise NotImplementedError(_STUB)


def week_of(now: float) -> str:
    """The ISO week key of the epoch `now` ("2026-W42")."""
    raise NotImplementedError(_STUB)


def run(ctx: Any) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`."""
    raise NotImplementedError(_STUB)


__all__ = ["KV", "PROGRAMS_RUN", "KS", "SCHEDULES", "ALARM_RATE", "WALL_S", "program_code", "week_of", "run"]

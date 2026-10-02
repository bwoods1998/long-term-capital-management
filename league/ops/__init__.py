"""The House's jobs (LTCM v3, Oct 2026): the operator's daily scripts as code on the House's own clock.

`House._ops_step` calls `tick(house)` once a tick; `attach(house, root)` (from `league/service.py`, on the House box
only, never in a canary) gives the House its runner. Everything else is in the modules:

- `schedule`: when a job is due, from the House's NYSE calendar (`ltcm.data.us_equity_session`), DST-proof;
- `registry`: the jobs, their triggers, grace and limits; modules other packages own are imported lazily;
- `runner`: the per-tick runner (one child at a time, `python -m league.ops run <job>`), receipts in `ops.sqlite`;
- `receipts`: the private `<state>/receipts/<day>.json` and `latest.json` the operator reads (`scripts/desk_receipts.py`);
- `guard`: read-only SQLite and the habits that keep an extract from hurting the House;
- the jobs: `preopen`, `economics`, `scoreboard`, `hygiene`, `clock` (and `grant`, `budget`, `drills`, ... when present).

`budget` (league/ops/budget.py) is the budget rule and the funding notices: protected (`league/ci.py` FORBIDDEN), as are
`grant`, `drills` (which asks the updater for the rollback drill rather than running it in its child) and `context`
(what every job, the budget rule included, is handed).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def attach(house: Any, root: str | Path, *, base: str | Path | None = None) -> Any:
    """Give `house` its job runner (`house.ops`)."""
    from .runner import Ops

    house.ops = Ops(root, base=base, clock=house.clock)
    return house.ops


def tick(house: Any) -> dict[str, Any] | None:
    """One tick of the House's jobs: cheap, never waits (`runner.Ops.tick`). Nothing when the House has no runner."""
    runner = getattr(house, "ops", None)
    if runner is None:
        return None
    return runner.tick(house)


def health(house: Any) -> dict[str, Any] | None:
    """health.json `ops`, or None when the House has no runner."""
    runner = getattr(house, "ops", None)
    if runner is None:
        return None
    return runner.health()

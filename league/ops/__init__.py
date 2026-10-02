"""The House's jobs (LTCM v3, Oct 2026): the operator's daily scripts as code on the House's own clock.

`House._ops_step` calls `tick(house)` once a tick; `start(house, root)` (from `league/service.py`, on the House box
only, only for `python -m league run`, never in a canary) gives the House its runner (`attach`, guarded). Everything
else is in the modules:

- `schedule`: when a job is due, from the House's NYSE calendar (`ltcm.data.us_equity_session`), DST-proof;
- `registry`: the jobs, their triggers, grace and limits; modules other packages own are imported lazily;
- `runner`: the per-tick runner (one child at a time, `python -m league.ops run <job>`), receipts in `ops.sqlite`;
- `receipts`: the private `<state>/receipts/<day>.json` and `latest.json` the operator reads (`scripts/desk_receipts.py`);
- `guard`: read-only SQLite and the habits that keep an extract from hurting the House;
- the jobs: `preopen`, `economics`, `scoreboard`, `hygiene`, `clock` (and `grant`, `budget`, `drills`, ... when present).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def attach(house: Any, root: str | Path, *, base: str | Path | None = None) -> Any:
    """Give `house` its job runner (`house.ops`)."""
    from .runner import Ops

    house.ops = Ops(root, base=base, clock=house.clock)
    return house.ops


def start(house: Any, root: str | Path, *, base: str | Path | None = None) -> Any:
    """`attach`, guarded: a runner that cannot be built (an unreadable `ops.sqlite`, a failed recovery) is a House
    warning and `house.ops` None, never a House that does not start. The runner or None."""
    try:
        return attach(house, root, base=base)
    except Exception as exc:  # noqa: BLE001 - the jobs never keep the House from starting
        house.ops = None
        house.alert("warning", f"the House's jobs could not start ({type(exc).__name__}: {str(exc)[:200]}); "
                               "the House runs without them")
        return None


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

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
`grant` and `drills`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def attach(house: Any, root: str | Path, *, base: str | Path | None = None) -> Any:
    """Give `house` its job runner (`house.ops`). Never raises: the jobs never cost the House its start. A store SQLite
    calls no database (a torn restore) is moved aside to `ops.sqlite.corrupt-<epoch>` and made again; any other failure
    leaves `house.ops` None (no jobs this run) and raises one warning."""
    import sqlite3
    import time

    from .runner import Ops
    from .store import FILE

    house.ops = None
    try:
        house.ops = Ops(root, base=base, clock=house.clock)
    except sqlite3.DatabaseError as exc:
        if "not a database" in str(exc) or "malformed" in str(exc):
            path = Path(root) / FILE
            aside = path.with_name(f"{FILE}.corrupt-{int(time.time())}")
            try:
                path.replace(aside)
                for suffix in ("-wal", "-shm"):
                    extra = path.with_name(FILE + suffix)
                    if extra.exists():
                        extra.replace(aside.with_name(aside.name + suffix))
                house.ops = Ops(root, base=base, clock=house.clock)
                _warn(house, f"the House's job store was unreadable ({str(exc)[:120]}): moved aside to {aside.name} and made again")
            except Exception as again:  # noqa: BLE001
                _warn(house, f"the House's jobs are off this run: the job store could not be made again ({type(again).__name__}: {str(again)[:160]})")
        else:
            _warn(house, f"the House's jobs are off this run: the job store could not be opened ({type(exc).__name__}: {str(exc)[:160]})")
    except Exception as exc:  # noqa: BLE001 - the House starts without its jobs rather than not at all
        _warn(house, f"the House's jobs are off this run: the runner could not start ({type(exc).__name__}: {str(exc)[:160]})")
    return house.ops


def _warn(house: Any, text: str) -> None:
    alert = getattr(house, "alert", None)
    if callable(alert):
        try:
            alert("warning", text)
        except Exception:  # noqa: BLE001 - an alert raised while the House is still being built
            pass


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

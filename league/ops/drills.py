"""The monthly failure drills (LTCM v3, V3-A; GOAL.md criterion 1): the first Saturday of the month, 15:00 UTC.

Protected (`league/ci.py` FORBIDDEN): a drill proves the way back, so only the owner's deploy changes what it does.

Two drills run here, each with its recovery check:

- **funding** (`league/ops/budget.py` `drill`), for each meter: a synthetic cliff goes through the budget rule and is
  sent as the real funding notice would be, with `test: true`; the same meter with an unreadable balance must give no
  research. Nothing is written to `budget.json` or to the notices' record.
- **rollback**: the self-rollback (`python -m league.watchdog drill-rollback`) restarts the House twice, so it is never
  run inside this job's child: the House's next restart would kill the child with the drill in it (`Ops._recover`),
  the copy would stay current with nothing watching it, and anything the child starts inherits its nice 19 and its CPU
  and memory limits -- the canary and the House the drill restarts included. This job writes a request
  (`<state>/ops/drill-request.json`, `league/updater.py` `DRILL_REQUEST`); the updater, in the House's own process,
  launches the drill detached at its next look, with nothing else in flight, and the drill writes its `stage: "drill"`
  row to `deploys.jsonl` whatever happens (a drill copy left with no drill alive rolls itself back: `Updater.check`).
  The receipt reports the last rollback drill on the record, so each month's receipt carries the previous one's verdict
  and a drill that did not pass is a warning.

Not built in V3-A, and named in every receipt so the record says so: the swarm kill, a Gym box failure, a gateway
outage and a Sail balance read failure drills (the House restart is exercised by the rollback drill, twice).

`run(ctx)` reads `root` (the House's state directory), `base` (the release base; default the root's parent), `now()`
or `clock`, `config`, `alert(level, text)`, and the seams `notify` and `funding_drill(ctx, meter)`.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Mapping

NAME = "drills"
#: Must equal `league/updater.py` `DRILL_REQUEST` (under the House's state directory): the updater launches it.
REQUEST = Path("ops") / "drill-request.json"
#: The drills V3-A does not build yet. Each receipt names them.
NOT_BUILT = ("swarm_kill", "gym_box_failure", "gateway_outage", "sail_balance_read_failure")
#: How far back a rollback drill's row counts as this cycle's (a month and a few days).
LOOKBACK_SECONDS = 40 * 86400
DEPLOYS_TAIL_BYTES = 4 << 20


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


def _now(ctx: Any) -> float:
    now = _get(ctx, "now")
    if callable(now):
        now = now()
    if now is None:
        clock = _get(ctx, "clock")
        now = clock() if callable(clock) else time.time()
    return float(now)


def _iso(ts: float) -> str:
    from league.watchdog import iso

    return iso(ts)


def _epoch(text: Any) -> float | None:
    from league.watchdog import epoch

    return epoch(text)


def _alert(ctx: Any, level: str, text: str) -> None:
    alert = _get(ctx, "alert")
    if callable(alert):
        alert(level, text)


def _deploy_rows(base: Path) -> list[dict[str, Any]]:
    path = base / "deploys.jsonl"
    try:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - DEPLOYS_TAIL_BYTES))
            raw = handle.read().decode("utf-8", "replace")
    except OSError:
        return []
    rows = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def last_rollback_drill(base: Path, now: float) -> dict[str, Any] | None:
    """The newest `stage: "drill"` row of the deploy record within `LOOKBACK_SECONDS`, cut to what the receipt shows."""
    found = None
    for row in _deploy_rows(base):
        if row.get("stage") != "drill":
            continue
        at = _epoch(row.get("at"))
        if at is None or not 0 <= now - at <= LOOKBACK_SECONDS:
            continue
        found = row
    if found is None:
        return None
    return {k: found.get(k) for k in ("at", "outcome", "ok", "release", "copy_of", "deploy_verdict", "reasons") if k in found}


def request_rollback(root: Path, now: float, due_at: float | None) -> dict[str, Any]:
    """Write the request the updater launches the rollback drill from. One request stands at a time: a request the
    updater never took (it runs only with `auto_update` on) is replaced, and the receipt says so."""
    path = root / REQUEST
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    replaced = path.exists()
    body = {"at": _iso(now), "due_at": _iso(due_at) if due_at is not None else None, "by": "league.ops.drills"}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(body, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return {"requested": True, "path": str(path), **({"replaced_unlaunched": True} if replaced else {})}


def run(ctx: Any) -> dict[str, Any]:
    root = Path(_get(ctx, "root"))
    base = Path(_get(ctx, "base") or root.parent)
    now = _now(ctx)
    out: dict[str, Any] = {"not_built": list(NOT_BUILT)}

    # 1. The rollback drill of the cycle before this one, as the record has it; then this cycle's request.
    previous = last_rollback_drill(base, now)
    out["last_rollback_drill"] = previous
    if previous is None:
        _alert(ctx, "info", "drills: no rollback drill on the record in the last 40 days (the first is requested now)")
    elif previous.get("outcome") != "rolled_back":
        _alert(ctx, "warning", f"drills: the last rollback drill ({previous.get('at')}) ended {previous.get('outcome')}: "
                               + "; ".join(str(r) for r in previous.get("reasons") or [])[:400])
    try:
        out["rollback"] = request_rollback(root, now, _get(ctx, "due_at"))
    except OSError as exc:
        out["rollback"] = {"requested": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        _alert(ctx, "warning", f"drills: the rollback drill could not be requested ({type(exc).__name__})")

    # 2. The funding drills, one per meter.
    funding: Callable[[Any, str], Mapping[str, Any]] | None = _get(ctx, "funding_drill")
    if funding is None:
        from . import budget

        funding, meters = budget.drill, budget.METERS
    else:
        meters = ("sail", "claude")
    results = []
    for meter in meters:
        try:
            result = dict(funding(ctx, meter))
        except Exception as exc:  # noqa: BLE001 - one drill failing is that drill's result
            result = {"drill": "funding", "meter": meter, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        result.pop("root", None)
        results.append(result)
        if not result.get("ok"):
            _alert(ctx, "warning", f"drills: the {meter} funding drill did not pass ({result.get('error') or result.get('checks')})")
    out["funding"] = results
    out["ok"] = all(r.get("ok") for r in results) and bool(out["rollback"].get("requested"))
    return out


__all__ = ["run", "request_rollback", "last_rollback_drill", "REQUEST", "NOT_BUILT"]

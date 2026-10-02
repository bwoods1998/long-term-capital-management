"""The monthly failure drills (LTCM v3, V3-A; `league/ops/registry.py` job `drills`, first Saturday 15:00 UTC).

FORBIDDEN to the updater (`league/ci.py`): only the owner's deploy changes what a drill proves.

What runs here, every month, without touching the running House, the swarm or a box:

- `funding:<meter>` (each meter of the budget rule): `league.ops.budget.drill`: a synthetic runway cliff goes through the
  rule and is sent as the real `funding` notice would be, with `test: true` and its own notice id; an unreadable
  balance on the same meter must give no research. Writes nothing to budget.json or the notices' record.
- `sail_read_failure`: a Sail guard on a scratch store whose balance read raises must brake (FAIL CLOSED), stay braked
  on a second failed read, and release only on a good reading above its line with budget room.
- `gateway_outage`: the budget job on a scratch state root whose gateway health read raises must give the Claude meter
  no research (unknown is never money), and its funding notice must be recorded as not sent.
- `stale_budget`: a stale budget.json whose meters say 0 must not loosen to the floor (`league.ops.budget.effective`).

What does not run here, and why (each named in the receipt, so a month's receipt is never read as more than it is):
restart, swarm kill and Gym box failure act on the running House, and the rollback drill deploys a copy of the release
(`python -m league.watchdog drill-rollback`, outside the session window): those are the operator's, on the runbook.

`run(ctx)` returns the receipt: {status: ok | failed, drills: {name: {ok, ...}}, not_run: {...}}; a failed drill is a
failed receipt and a House warning. Standard library only (and the league's own modules).
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping

#: Drills that act on the running House or deploy, and are therefore the operator's (the module docstring).
NOT_RUN = {
    "restart": "acts on the running House: the operator's (RUNBOOK)",
    "swarm_kill": "acts on the running swarm: the operator's (RUNBOOK)",
    "gym_box_failure": "acts on a billed Sail box: the operator's (RUNBOOK)",
    "rollback": "deploys a drill copy of the release: `python -m league.watchdog drill-rollback`, the operator's",
}


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


def _now(ctx: Any) -> float:
    now = _get(ctx, "now")
    if callable(now):
        now = now()
    return float(time.time() if now is None else now)


def sail_read_failure(now: float) -> dict[str, Any]:
    """A guard whose read raises brakes and stays braked; a good reading with room releases it."""
    from league.swarm.guard import SailGuard
    from league.swarm.store import SwarmStore

    with tempfile.TemporaryDirectory(prefix="ltcm-drill-") as tmp:
        store = SwarmStore(Path(tmp), clock=lambda: now)
        settings = {"guard": {"house_burn_usd_day": 1.0, "margin_usd": 30.0, "min_free_disk_gb": 0.0},
                    "budget": {"source": "drill", "sail_usd_day": 3.0, "claude_usd_day": 2.0, "fixed_sail_usd_day": 1.0}}
        readings: list[Callable[[], tuple[Any, Any]]] = []

        def reader() -> tuple[Any, Any]:
            return readings.pop(0)()

        def fail() -> tuple[Any, Any]:
            raise OSError("drill: the Sail balance read fails")
        guard = SailGuard(store, settings, reader, clock=lambda: now, disk_free=lambda: float(2 ** 40))
        readings.extend([fail, fail, lambda: (1000.0, 1.0)])
        first, second, third = guard.check(), guard.check(), guard.check()
        try:
            store.close()
        except Exception:  # noqa: BLE001 - a scratch store
            pass
    checks = {"braked_on_failed_read": first["braked"] is True, "stays_braked": second["braked"] is True,
              "releases_on_good_read": third["braked"] is False}
    return {"ok": all(checks.values()), "checks": checks}


def gateway_outage(now: float) -> dict[str, Any]:
    """The budget job with the gateway down: Claude research 0, its notice not sent."""
    from . import budget

    def down() -> Any:
        raise OSError("drill: the gateway does not answer")

    class NoSail:  # never the real client: a drill makes no call to Sail
        def spend(self, **_: Any) -> Any:
            raise OSError("drill: no Sail")
    sent: list[Any] = []
    with tempfile.TemporaryDirectory(prefix="ltcm-drill-") as tmp:
        receipt = budget.run({"root": tmp, "now": now, "config": {}, "sail": NoSail(), "gateway_health": down,
                              "notify": lambda facts: sent.append(facts) or {"sent": False, "reason": "drill"}})
        doc = json.loads((Path(tmp) / budget.BUDGET_FILE).read_text(encoding="utf-8"))
    claude = doc["meters"]["claude"]
    checks = {"claude_unreadable": claude.get("limited_by") == "unreadable",
              "claude_no_research": claude.get("research_usd_day") == 0.0,
              "no_notice_recorded": not any(n.get("sent") for n in receipt.get("notices") or [])}
    return {"ok": all(checks.values()), "checks": checks}


def stale_budget(now: float) -> dict[str, Any]:
    """A stale budget.json that said no research never loosens to the floor."""
    from . import budget

    with tempfile.TemporaryDirectory(prefix="ltcm-drill-") as tmp:
        stale = {"schema": budget.SCHEMA, "at": now - budget.STALE_SECONDS - 3600,
                 "meters": {m: {"research_usd_day": 0.0} for m in budget.METERS}}
        (Path(tmp) / budget.BUDGET_FILE).write_text(json.dumps(stale), encoding="utf-8")
        block = budget.effective(tmp, now)
    checks = {"sail_not_loosened": block.get("sail_usd_day") == 0.0, "claude_not_loosened": block.get("claude_usd_day") == 0.0}
    return {"ok": all(checks.values()), "checks": checks}


def run(ctx: Any) -> dict[str, Any]:
    from . import budget

    now = _now(ctx)
    drills: dict[str, Any] = {}
    for meter in budget.METERS:
        try:
            drills[f"funding:{meter}"] = budget.drill(ctx, meter)
        except Exception as exc:  # noqa: BLE001 - a drill that cannot run is a failed drill
            drills[f"funding:{meter}"] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    for name, drill in (("sail_read_failure", sail_read_failure), ("gateway_outage", gateway_outage),
                        ("stale_budget", stale_budget)):
        try:
            drills[name] = drill(now)
        except Exception as exc:  # noqa: BLE001 - a drill that cannot run is a failed drill
            drills[name] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    failed = sorted(name for name, out in drills.items() if not (isinstance(out, Mapping) and out.get("ok") is True))
    receipt: dict[str, Any] = {"status": "failed" if failed else "ok", "drills": drills, "not_run": dict(NOT_RUN),
                               "failed": failed}
    if failed:
        receipt["error"] = f"drills failed: {', '.join(failed)}"
    return receipt


__all__ = ["run", "sail_read_failure", "gateway_outage", "stale_budget", "NOT_RUN"]

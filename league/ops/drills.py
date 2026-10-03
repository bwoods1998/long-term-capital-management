"""The monthly failure drills (LTCM v3, GOAL Phase 1.6; BUILD WP2 registry `drills`): each one breaks something on
purpose and checks that the House recovered without a human. Protected: `league/ci.py` FORBIDDEN lists this file.

Due twice on the first Saturday of each month (15:00Z and 17:00Z, outside every session). The month's state is
`<state>/ops/drills.json`: a drill done this month is never run again, so a run the House's own restart interrupted
(the runner retries it) or the second occurrence picks up where the first stopped.

- `funding`: the budget's funding drill (`league/ops/budget.py` `drill`), for each meter: a synthetic runway cliff goes
  out as the real funding notice would, with `test: true`; an unreadable balance must give that meter no research.
- `sail_read`: a Sail balance and box-spend read that fails gives Sail no research and the configured fixed cost (fail
  closed); recovered when the Sail guard's own reading in the swarm store is fresh.
- `gateway_outage`: a gateway that does not answer fails fast (bounded, no hang) and gives Claude no research;
  recovered when the real gateway's `/v1/health` answers.
- `swarm_kill`: the swarm process (verified by its command line and lock) gets SIGTERM; recovered when the House's
  swarm step has started a new one (a new pid holds the lock and its heartbeat is newer than the kill), within
  `SWARM_RECOVERY_SECONDS`. Not run (and not failed) when no swarm runs.
- `rollback` (with `restart`): REQUESTED, last, and the job returns. The drill restarts the House twice (a copy
  carrying `DRILL_BREAK` is deployed, the watch must roll it back), so it is never started from this job's child: the
  child runs at nice 19 under CPU and memory limits (`league/ops/__main__.py`) that the watchdog and its canary would
  inherit, and the House's next start kills a job child it finds. This job writes `<state>/ops/drill-request.json`
  (`REQUEST`, `league/updater.py` `DRILL_REQUEST`); the updater, in the House's own process, launches
  `python -m league.watchdog drill-rollback` detached at its next full look with nothing in flight, and records a
  `stage: "drill"` row if it drops the request or cannot launch it. The recovery check is the next occurrence's: the
  `stage: "drill"` row after the request says `rolled_back`, and the House restarted (`restart` rows) and is running
  jobs again (this very check runs in it). A request still untaken then is withdrawn, so no drill starts unchecked.

Not drilled here: a Gym box failure (it needs the pool to fail one of its own boxes on purpose; the pool has no such
hook yet). The receipt says so in `not_drilled`.

The receipt carries outcomes and reasons, never an account figure. A drill that did not recover makes the run
`failed` (a warning), and the second occurrence of the day reports a requested rollback with no verdict as failed.
"""
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from . import schedule as S
from .context import Gateway, GatewayError, read_json, write_json

STATE_FILE = Path("ops") / "drills.json"
ORDER = ("funding", "sail_read", "gateway_outage", "swarm_kill", "rollback")
NOT_DRILLED = {"gym_box_failure": "the Gym pool has no hook to fail one of its own boxes on purpose yet"}
SWARM_RECOVERY_SECONDS = 600
#: The rollback drill's verdict is looked for this long after its request before the check calls it failed: the
#: updater's next full look (`Updater.every`, half an hour), then the drill's wait of up to ten minutes for the nightly
#: daemon, a canary, the promotion's restart, a ten-minute watch and the rollback's restart. Under the two hours to the
#: second occurrence, so that one always decides.
ROLLBACK_VERDICT_SECONDS = 110 * 60
#: Where the updater reads the request (must equal `league/updater.py` `DRILL_REQUEST`, under the House's state dir).
REQUEST = Path("ops") / "drill-request.json"
#: An address nothing listens on: the simulated gateway outage.
DEAD_GATEWAY = "http://127.0.0.1:9"


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    value = ctx.get(name) if isinstance(ctx, Mapping) else getattr(ctx, name, None)
    return default if value is None else value


def _now(ctx: Any) -> float:
    now = _get(ctx, "now")
    return float(now()) if callable(now) else time.time()


def _month(now: float) -> str:
    return S.iso(now)[:7]


def load(root: Path, now: float) -> dict[str, Any]:
    state = read_json(root / STATE_FILE, None)
    if not isinstance(state, dict) or state.get("month") != _month(now) or not isinstance(state.get("drills"), dict):
        return {"month": _month(now), "drills": {}}
    return state


def save(root: Path, state: Mapping[str, Any]) -> None:
    write_json(root / STATE_FILE, state)


# ------------------------------------------------------------------------------------------------ the drills
def drill_funding(ctx: Any) -> dict[str, Any]:
    """The budget's funding drill on every meter (`budget.METERS`); ok only when each one passed."""
    from . import budget

    drill = _get(ctx, "funding_drill", budget.drill)
    meters: dict[str, Any] = {}
    for meter in budget.METERS:
        try:
            out = dict(drill(ctx, meter))
        except Exception as exc:  # noqa: BLE001 - one meter's drill failing is that meter's result
            out = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        meters[meter] = {"ok": bool(out.get("ok")), "checks": out.get("checks"), "sent": out.get("sent"),
                         "error": out.get("error"), "notice_id": out.get("notice_id")}
    failed = [m for m, r in meters.items() if not r["ok"]]
    return {"ok": not failed, "meters": meters,
            **({"error": "the funding drill did not pass on " + ", ".join(failed)} if failed else {})}


def _synthetic(meter: str) -> dict[str, Any]:
    from . import budget

    return {"p30_usd": 0.0, "p30_source": "drill", "edge": {"stop": False, "why": "drill"},
            "meters": {m: {"balance_usd": None if m == meter else budget.RESERVE_USD[m] + 10_000.0, "fixed_usd_day": 1.0,
                           "need_usd": 0.0} for m in budget.METERS}}


def drill_sail_read(ctx: Any) -> dict[str, Any]:
    from . import budget

    root, now = Path(_get(ctx, "root")), _now(ctx)

    class Down:
        def spend(self, *a: Any, **k: Any) -> Any:
            raise OSError("drill: Sail does not answer")

    errors: list[str] = []
    fixed, _source = budget._sail_fixed(Down(), ["sb_drill"], now, 1.0, errors)
    doc = budget.compute(_synthetic("sail"), now=now)
    checks = {"unreadable_balance_gives_no_research": doc["meters"]["sail"]["research_usd_day"] == 0.0,
              "failed_spend_read_falls_back": fixed == 1.0 and bool(errors)}
    reading_age = None
    try:
        from . import guard

        path = root / "swarm.sqlite"
        rows = guard.read(path, lambda db: guard.rows(db, "SELECT value FROM kv WHERE key='guard'", ())) if path.exists() else []
        last = (json.loads(rows[0]["value"]) or {}).get("last") if rows else None
        at = float(last.get("at")) if isinstance(last, Mapping) and last.get("at") is not None else None
        reading_age = None if at is None else now - at
    except Exception as exc:  # noqa: BLE001 - an unreadable reading is no recovery
        checks["recovered"] = False
        return {"ok": False, "checks": checks, "error": f"the guard's reading could not be read ({type(exc).__name__})"}
    checks["recovered"] = reading_age is not None and 0 <= reading_age <= budget.BALANCE_FRESH_SECONDS
    return {"ok": all(checks.values()), "checks": checks,
            "guard_reading_age_seconds": None if reading_age is None else round(reading_age)}


def drill_gateway_outage(ctx: Any) -> dict[str, Any]:
    from . import budget

    now = _now(ctx)
    dead = _get(ctx, "dead_gateway") or Gateway(DEAD_GATEWAY, lambda: "drill-token-not-a-secret", timeout=5.0)
    started, refused = time.monotonic(), False
    try:
        dead.get("/v1/health")
    except GatewayError:
        refused = True
    except Exception:  # noqa: BLE001 - any failure is a refusal, as long as it is quick
        refused = True
    took = time.monotonic() - started
    doc = budget.compute(_synthetic("claude"), now=now)
    checks = {"outage_fails_fast": refused and took <= 15.0,
              "no_reading_gives_no_research": doc["meters"]["claude"]["research_usd_day"] == 0.0}
    try:
        health = _get(ctx, "gateway").get("/v1/health")
        checks["recovered"] = isinstance(health, Mapping)
        error = None
    except Exception as exc:  # noqa: BLE001
        checks["recovered"] = False
        error = f"the real gateway did not answer ({type(exc).__name__})"
    return {"ok": all(checks.values()), "checks": checks, "outage_seconds": round(took, 2), "error": error}


def drill_swarm_kill(ctx: Any) -> dict[str, Any]:
    from ..data_job import process_info
    from ..swarm import HEARTBEAT, LOCK_FILE
    from ..swarm.hook import lock_held

    root = Path(_get(ctx, "root"))
    proc: Callable[[int], Any] = _get(ctx, "proc", process_info)
    kill: Callable[[int, int], None] = _get(ctx, "kill", os.kill)
    sleep: Callable[[float], None] = _get(ctx, "sleep", time.sleep)
    held: Callable[[Path], bool] = _get(ctx, "lock_held", lock_held)
    wait = float(_get(ctx, "swarm_recovery_seconds", SWARM_RECOVERY_SECONDS))
    if not held(root / LOCK_FILE):
        return {"ok": None, "skipped": "no swarm is running: nothing to kill"}
    lock = read_json(root / LOCK_FILE, {}) or {}
    pid = lock.get("pid")
    seen = proc(int(pid)) if isinstance(pid, int) else None
    if not seen or not any("league.swarm" in part for part in seen[0]) or str(root) not in " ".join(seen[0]):
        return {"ok": False, "error": "the swarm lock's pid is not verifiably the swarm: nothing was signalled"}
    if lock.get("start") is not None and str(seen[1]) != str(lock.get("start")):
        return {"ok": False, "error": "the swarm lock's pid was reused: nothing was signalled"}
    killed_at = _now(ctx)
    try:
        kill(int(pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = killed_at + wait
    while True:
        beat = read_json(root / HEARTBEAT, {}) or {}
        now_lock = read_json(root / LOCK_FILE, {}) or {}
        new_pid = now_lock.get("pid")
        if (held(root / LOCK_FILE) and new_pid not in (None, pid) and float(beat.get("at") or 0) > killed_at
                and beat.get("pid") == new_pid):
            return {"ok": True, "recovered_seconds": round(_now(ctx) - killed_at), "checks": {"killed": True, "restarted": True}}
        if _now(ctx) >= deadline:
            return {"ok": False, "checks": {"killed": True, "restarted": False},
                    "error": f"no new swarm took the lock with a fresh heartbeat within {int(wait)} s"}
        sleep(10)


def request_rollback(ctx: Any) -> dict[str, Any]:
    """Ask the updater for the rollback drill (`REQUEST`): it launches `python -m league.watchdog drill-rollback` from
    the House's own process, never from this child. One request stands at a time; an older one is replaced."""
    root, now = Path(_get(ctx, "root")), _now(ctx)
    path = root / REQUEST
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    replaced = path.exists()
    write_json(path, {"at": S.iso(now), "by": "league.ops.drills"})
    return {"requested_at": S.iso(now), "requested_ts": now, **({"replaced": True} if replaced else {})}


def check_rollback(ctx: Any, requested: Mapping[str, Any]) -> dict[str, Any] | None:
    """The rollback drill's verdict from `deploys.jsonl`, or None while it is still due. A request still on disk when
    this decides (the updater never took it: `auto_update` off, or a deploy in flight all along) is withdrawn, so no
    drill starts that nothing checks."""
    from .grant import deploy_rows

    base, root, now = Path(_get(ctx, "base")), Path(_get(ctx, "root")), _now(ctx)
    since = float(requested.get("requested_ts") or 0)
    rows = [r for r in deploy_rows(base) if float(r.get("ts") or 0) >= since]
    verdict = next((r for r in reversed(rows) if r.get("stage") == "drill"), None)
    if verdict is None and now - since < ROLLBACK_VERDICT_SECONDS:
        return None
    untaken = (root / REQUEST).exists()
    if untaken:
        (root / REQUEST).unlink(missing_ok=True)
    if verdict is None:
        return {"ok": False, "withdrawn": untaken,
                "error": f"no drill verdict in deploys.jsonl {int((now - since) // 60)} minutes after the request"
                         + ("; the updater never took it (is auto_update on?), and it is withdrawn" if untaken else "")}
    drill_id = verdict.get("release")
    restarts = [r for r in rows if r.get("stage") == "restart" and r.get("ok")]
    checks = {"rolled_back": verdict.get("outcome") == "rolled_back" and verdict.get("ok") is True,
              "house_restarted": len(restarts) >= 1, "house_running_jobs": True}
    return {"ok": all(checks.values()), "checks": checks, "outcome": verdict.get("outcome"),
            "reasons": [str(r)[:200] for r in verdict.get("reasons") or []][:5], "release": drill_id,
            "copy_of": verdict.get("copy_of"), "restarts": len(restarts), **({"withdrawn": True} if untaken else {})}


DRILLS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "funding": drill_funding, "sail_read": drill_sail_read, "gateway_outage": drill_gateway_outage,
    "swarm_kill": drill_swarm_kill,
}


def run(ctx: Any) -> dict[str, Any]:
    root = Path(_get(ctx, "root"))
    now = _now(ctx)
    state = load(root, now)
    done: dict[str, Any] = state["drills"]
    ran: list[str] = []
    for name in ORDER:
        if name in done and (name != "rollback" or done[name].get("checked")):
            continue
        if name == "rollback":
            if name not in done:
                try:
                    done[name] = {"requested": request_rollback(ctx), "checked": False}
                except Exception as exc:  # noqa: BLE001 - a request that cannot be written is the drill's failure
                    done[name] = {"ok": False, "checked": True, "error": f"the drill could not be requested ({type(exc).__name__}: {str(exc)[:160]})"}
                save(root, state)
                ran.append(name)
                continue
            verdict = check_rollback(ctx, done[name].get("requested") or {})
            if verdict is not None:
                done[name] = {**done[name], **verdict, "checked": True}
                save(root, state)
                ran.append(name)
            continue
        try:
            result = DRILLS[name](ctx)
        except Exception as exc:  # noqa: BLE001 - a drill that breaks is that drill's failure
            result = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        done[name] = {**result, "at": S.iso(_now(ctx))}
        save(root, state)
        ran.append(name)
    failed = sorted(n for n, r in done.items() if r.get("ok") is False)
    pending = sorted(n for n, r in done.items() if n == "rollback" and not r.get("checked"))
    receipt: dict[str, Any] = {"month": state["month"], "ran": ran, "failed": failed, "pending": pending,
                               "drills": {n: {k: v for k, v in r.items() if k not in ("requested",)} for n, r in done.items()},
                               "not_drilled": NOT_DRILLED}
    if failed:
        receipt.update(status="failed", error="drills that did not recover: " + ", ".join(failed))
    elif not ran and not pending:
        receipt.update(status="skipped", why=f"this month's drills are done ({state['month']})")
    return receipt

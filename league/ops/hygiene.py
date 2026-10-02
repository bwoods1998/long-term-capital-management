"""The `hygiene` job (daily 02:00Z, never inside a session): the operator's sweeps as code.

1. Practice cohorts: an ACTIVE cohort whose program the swarm barred from the incubator (`incubator_barred[run_sha]`
   in its family's state) is ended through the observe store's own `fail_cohort`, reason "hygiene: ...". A cohort
   whose research family retired is listed, and ended only when `ops.json` `hygiene.end_retired_cohorts` is true:
   the practice record is designed to outlive its family (`league/live/observe.py`), and the forward ladder counts
   every entrant's whole record.
2. The Gym pool's `failed` box rows: marked `terminated` when Sail lists the box terminal or no longer knows it.
3. Families past the idle rule: the tournament's own idle pass (`Tournament.idle_pass`: the same rule, reasons,
   lessons and cohort keep), never below `population.floor` (`SwarmStore.retire_gym`), sparing a family that had a
   research cycle in the last `BUSY_SECONDS`. The swarm runs the same pass every few minutes; this is its daily
   backstop when that pass is off or stalled.
4. Stale live instances (reported only): a live-path instance whose family is retired or unknown, or that errors.

Each part runs in its own try: one that fails is in the receipt, and the others still run.
"""
from __future__ import annotations

import json
import time
from typing import Any, Mapping

from . import guard
from . import schedule as S

BUSY_SECONDS = 600
LOCKED_TRIES, LOCKED_WAIT = 5, 1.0
SAIL_TERMINAL = ("terminated", "terminating", "failed", "create_failed", "deleted")


def _attempt(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """`fn(*args, **kwargs)`, again after a short wait when SQLite says it is locked (the live minute writes the same
    file), `LOCKED_TRIES` times at most."""
    import sqlite3

    for attempt in range(LOCKED_TRIES):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == LOCKED_TRIES - 1:
                raise
            time.sleep(LOCKED_WAIT)
    return None


def cohorts(root: Any) -> list[dict[str, Any]]:
    """The ACTIVE practice cohorts: family, version, run_sha, first_day (read-only)."""
    path = root / "observe.sqlite"
    if not path.exists():
        return []

    def read(db: Any) -> list[dict[str, Any]]:
        out = []
        for row in guard.rows(db, "SELECT family, version, first_day, snapshot FROM cohorts WHERE status='active' "
                                  "ORDER BY admitted_at, family, version"):
            try:
                snap = json.loads(row["snapshot"])
            except (TypeError, ValueError):
                snap = {}
            out.append({"family": row["family"], "version": int(row["version"]), "first_day": row["first_day"],
                        "run_sha": snap.get("run_sha") if isinstance(snap, dict) else None})
        return out

    return guard.read(path, read)


def families(root: Any, ids: list[str]) -> dict[str, dict[str, Any]]:
    """{family id: {retired_at, band, state}} for `ids` (read-only, batched)."""
    path = root / "swarm.sqlite"
    if not ids or not path.exists():
        return {}
    rows = guard.read(path, lambda db: guard.batched(db, "SELECT id, retired_at, band, state FROM families WHERE id IN ({marks})", ids))
    out = {}
    for row in rows:
        try:
            state = json.loads(row["state"] or "{}")
        except ValueError:
            state = None
        out[row["id"]] = {"retired_at": row["retired_at"], "band": row["band"], "state": state}
    return out


def barred(fam: Mapping[str, Any] | None, run_sha: str | None) -> str | None:
    """Why the cohort's program is incubator-barred, or None."""
    if fam is None or not run_sha:
        return None
    state = fam.get("state")
    bars = state.get("incubator_barred") if isinstance(state, Mapping) else None
    if isinstance(bars, Mapping) and run_sha in bars:
        entry = bars[run_sha]
        why = entry.get("why") if isinstance(entry, Mapping) else None
        return str(why or "the swarm barred its program from the incubator")[:300]
    return None


def end_cohorts(ctx: Any, day: str, *, end_retired: bool, store: Any = None) -> dict[str, Any]:
    rows = cohorts(ctx.root)
    fams = families(ctx.root, sorted({r["family"] for r in rows}))
    ended, retired_kept = [], []
    for row in rows:
        fam = fams.get(row["family"])
        why = barred(fam, row["run_sha"])
        reason = None
        if why:
            reason = f"hygiene: its program is barred from the incubator ({why})"
        elif fam is None or fam.get("retired_at"):
            if end_retired:
                reason = "hygiene: its research family retired"
            else:
                retired_kept.append(f"{row['family']}@{row['version']}")
        if reason:
            if store is None:
                from ..live.observe import ObserveStore

                store = ObserveStore(ctx.root)
            _attempt(store.fail_cohort, row["family"], row["version"], day=day, reason=reason)
            ended.append({"cohort": f"{row['family']}@{row['version']}", "reason": reason})
    return {"active": len(rows), "ended": ended, "retired_family_kept": retired_kept}


def clean_pool(ctx: Any, *, store: Any = None) -> dict[str, Any]:
    from ..sailbox import SailboxError

    if store is None:
        from ..swarm.store import SwarmStore

        store = SwarmStore(ctx.root)
    failed = [b for b in store.boxes(live=False) if b.get("state") == "failed"]
    marked, kept, errors = [], [], []
    for box in failed:
        try:
            row = ctx.sail.get(box["id"])
            status = str(row.get("status") or "")
        except SailboxError as exc:
            if exc.status == 404:
                status = "absent"
            else:
                errors.append(f"{box['id']}: {str(exc)[:120]}")
                continue
        if status == "absent" or status in SAIL_TERMINAL:
            _attempt(store.set_box_state, box["id"], "terminated")
            marked.append(f"{box['id']} ({status})")
        else:
            kept.append(f"{box['id']} ({status})")
    return {"failed_rows": len(failed), "terminated": marked, "still_running_at_sail": kept, "errors": errors}


class _NoPool:
    """The idle pass's pool from outside the swarm's process: nothing to cancel here, nothing to report."""

    def cancel_family(self, fid: str) -> None:
        return None


def retire_idle(ctx: Any, *, store: Any = None, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from ..swarm import settings as swarm_settings
    from ..swarm.tournament import Tournament

    if store is None:
        from ..swarm.store import SwarmStore

        store = SwarmStore(ctx.root)
    settings = settings if settings is not None else swarm_settings.load(ctx.root, config=ctx.config)
    since = S.iso(ctx.now() - BUSY_SECONDS)
    busy = {r["family"] for r in store._all("SELECT DISTINCT family FROM events WHERE kind='swarm.cycle' AND at>=?", (since,))
            if r.get("family")}
    tournament = Tournament(store, _NoPool(), settings, clock=ctx.clock)
    result = tournament.idle_pass(busy=lambda fid: fid in busy)
    return {"retired": [r["family"] for r in result.get("retired") or []], "busy": result.get("busy"),
            "alive": result.get("alive"), "floor": int((settings.get("population") or {}).get("floor", 16))}


def stale_instances(ctx: Any) -> dict[str, Any]:
    from .context import read_json

    health = read_json(ctx.root / "health.json", {}) or {}
    instances = ((health.get("options_live") or {}).get("instances") or {}) if isinstance(health, dict) else {}
    names = sorted({str(i.get("family")) for i in instances.values() if isinstance(i, Mapping) and i.get("family")
                    and not str(i.get("family")).startswith("house:")})
    fams = families(ctx.root, names)
    stale = []
    for key, inst in sorted(instances.items()):
        if not isinstance(inst, Mapping):
            continue
        family = str(inst.get("family") or "")
        if not family or family.startswith("house:"):
            continue
        fam = fams.get(family)
        why = ("its family is unknown to the swarm" if fam is None else "its family retired" if fam.get("retired_at")
               else f"it errors: {str(inst.get('error'))[:120]}" if inst.get("error") else None)
        if why:
            stale.append({"instance": key, "mode": inst.get("mode"), "why": why})
    return {"instances": len(instances), "stale": stale[:50]}


def run(ctx: Any) -> dict[str, Any]:
    now = ctx.now()
    if S.in_session(now, pad_minutes=30):
        return {"status": "skipped", "why": "hygiene never runs inside a session"}
    mine = ctx.job_settings()
    from ..swarm.incubator import session_day

    day = session_day(ctx.clock)
    out: dict[str, Any] = {}
    opened: dict[str, Any] = {}

    def swarm_store() -> Any:
        if "swarm" not in opened:
            from ..swarm.store import SwarmStore

            opened["swarm"] = SwarmStore(ctx.root)
        return opened["swarm"]

    def observe_store() -> Any:
        if "observe" not in opened:
            from ..live.observe import ObserveStore

            opened["observe"] = ObserveStore(ctx.root)
        return opened["observe"]

    parts = (("cohorts", lambda: end_cohorts(ctx, day, end_retired=mine.get("end_retired_cohorts") is True, store=observe_store())),
             ("pool", lambda: clean_pool(ctx, store=swarm_store())),
             ("idle", lambda: retire_idle(ctx, store=swarm_store()) if mine.get("retire_idle", True) is not False else {"off": True}),
             ("stale_instances", lambda: stale_instances(ctx)))
    try:
        for name, part in parts:
            try:
                out[name] = part()
            except Exception as exc:  # noqa: BLE001 - one part's failure is its own line in the receipt
                out[name] = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    finally:
        for store in opened.values():
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
    errors = [name for name, value in out.items() if isinstance(value, dict) and value.get("error")]
    if errors:
        ctx.alert("warning", f"hygiene: {', '.join(errors)} could not run")
    return out

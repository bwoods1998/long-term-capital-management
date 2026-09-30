"""The owner's commands for the live options path, on the House box (the House need not stop: it reads them each minute).

    python3 -m league.live --root /workspace/state --status
    python3 -m league.live --root /workspace/state --release-drawdown     # lift the drawdown stop's pause
    python3 -m league.live --root /workspace/state --clear-assignment     # lift an assignment's freeze on real entries
    python3 -m league.live --root /workspace/state --calibration          # the D3 calibration samples, read-only
    python3 -m league.live --root /workspace/state --incubator            # the incubator's state, read-only

Nothing here sends an order or reads a venue: it reads and writes the live state (`<root>/live.sqlite`). `--calibration`
only reads `<root>/calibration.sqlite`: the plan (symbols, the six slots, the patient slots) and every cell, the patient
"mid25" and those not yet sampled included (per cell: working minutes, attempts, outcomes, fill rate, mean fill against
the mid in ticks, median seconds to fill); it prints quotes-derived numbers to the owner's terminal, never anywhere
public. `--incubator` only reads (`mode=ro`) `<root>/live.sqlite` and `<root>/swarm.json`: the switch, today's pins
(and why each passing cohort was not pinned), every first look with its P1-P6 values, the tally (R, H, W, what is held
or working, today's legs and dispatch) and today's incubator refusals (`league/live/incubator.py`).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .state import STATE_FILE, LiveState


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True, help="The House's state root (on the box: /workspace/state).")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true", help="Print the live path's state (the default).")
    action.add_argument("--release-drawdown", action="store_true", help="Owner: lift the drawdown stop's pause.")
    action.add_argument("--clear-assignment", action="store_true", help="Owner: lift the freeze an assignment set.")
    action.add_argument("--calibration", action="store_true",
                        help="Read-only: the D3 calibration round trips' samples per cell (league/live/calibration.py).")
    action.add_argument("--incubator", action="store_true",
                        help="Read-only: the incubator's switch, pins, first looks, tally and today's refusals.")
    args = parser.parse_args(argv)
    if args.incubator:
        out = incubator_report(args.root)
        print(json.dumps(out, indent=2, default=str))
        return out
    if args.calibration:
        from .calibration import report

        out = report(args.root)
        print(json.dumps(out, indent=2, default=str))
        return out
    path = args.root / STATE_FILE
    if not path.exists():
        raise SystemExit(f"no live state at {path}")
    state = LiveState(path)
    try:
        if args.release_drawdown:
            state.put("owner_release_drawdown", {"at": time.time(), "by": "the owner (python -m league.live)"})
        elif args.clear_assignment:
            state.put("owner_clear_assignment", {"at": time.time()})
        out = {
            "stops": state.get("stops"), "reconciliation": state.get("recon"), "paper_proof": state.get("paper_proof"),
            "assignment_latch": state.get("assignment_latch"), "orders_today": state.get("count"),
            "pending_owner_actions": {k: state.get(k) for k in ("owner_release_drawdown", "owner_clear_assignment") if state.get(k)},
            "open_positions": state.rows("SELECT pid, family, type, root, qty, status, opened_day FROM positions "
                                         "WHERE status IN ('open', 'awaiting_expiry') ORDER BY pid"),
            "working_orders": state.rows("SELECT oid, client_id, family, action, type, qty, filled_qty, status, day FROM orders "
                                         "WHERE status IN ('pending', 'working', 'unknown') ORDER BY oid"),
            "instances": state.rows("SELECT id, family, band, tuition, mode, why FROM instances WHERE retired_at IS NULL"),
        }
        print(json.dumps(out, indent=2, default=str))
        return out
    finally:
        state.close()


def incubator_report(root: Path, *, now: float | None = None) -> dict:
    """The incubator's state, read-only (the module docstring). Never writes: `live.sqlite` is opened `mode=ro`."""
    import datetime as dt
    import sqlite3
    from zoneinfo import ZoneInfo

    from .incubator import KEEP, PINS, VERDICTS, WEEK, week_start_of
    from .real import incubator_tally, is_incubator
    from .state import loads

    path = root / STATE_FILE
    if not path.exists():
        raise SystemExit(f"no live state at {path}")
    try:
        raw = json.loads((root / "swarm.json").read_text(encoding="utf-8"))
        switch = raw.get("live", {}).get("incubator") if isinstance(raw, dict) else None
    except FileNotFoundError:
        switch = None
    except (OSError, ValueError, AttributeError) as exc:
        switch = f"unreadable ({type(exc).__name__}): off"
    today = dt.datetime.fromtimestamp(time.time() if now is None else now, ZoneInfo("America/New_York")).date()
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    db.row_factory = sqlite3.Row
    try:
        def rows(sql: str, params=()) -> list[dict]:
            return [dict(r) for r in db.execute(sql, tuple(params)).fetchall()]

        def kv(key: str):
            found = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return loads(found["value"], None) if found else None

        tally = incubator_tally(rows, day=today.isoformat(), week_start=week_start_of(today))
        start = dt.datetime.combine(today, dt.time(0), ZoneInfo("America/New_York")).timestamp()
        refusals = [{"at": r["at"], **loads(r["payload"], {})} for r in rows(
            "SELECT at, payload FROM events WHERE kind='live.refusal' AND at>=? ORDER BY seq", (start,))]
        refusals = [{k: v for k, v in r.items() if k != "_intent"} for r in refusals if is_incubator(r.get("instance"))]
        return {"switch": {"live.incubator": switch, "on": switch is True},
                "pins": kv(PINS), "keep": kv(KEEP), "week_stopped": kv(WEEK), "verdicts": kv(VERDICTS) or {},
                "tally": tally.as_dict(),
                "instances": [r for r in rows("SELECT id, family, band, tuition, mode, why FROM instances WHERE retired_at IS NULL")
                              if is_incubator(r["id"])],
                "refusals_today": refusals}
    finally:
        db.close()


if __name__ == "__main__":
    main()

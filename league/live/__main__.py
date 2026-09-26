"""The owner's commands for the live options path, on the House box (the House need not stop: it reads them each minute).

    python3 -m league.live --root /workspace/state --status
    python3 -m league.live --root /workspace/state --release-drawdown     # lift the drawdown stop's pause
    python3 -m league.live --root /workspace/state --clear-assignment     # lift an assignment's freeze on real entries

Nothing here sends an order or reads a venue: it reads and writes the live state (`<root>/live.sqlite`).
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
    args = parser.parse_args(argv)
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
            "credit_accepted": state.get("credit_accepted", False),
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


if __name__ == "__main__":
    main()

"""`python -m league.swarm run|status|seed-check|hold-gate --root /workspace/state`

- `run`: the swarm's process (`loop.Swarm.run`); `--once` runs one pass of the main loop and no researcher.
- `status`: the heartbeat and the store's totals, as JSON (read-only); the families the operator holds at the gate.
- `seed-check`: every founding family's starter program through the Gym's safety check and `load_program`
  (needs the Gym on this tree; numpy for `load_program`).
- `hold-gate --family <id> [--clear] [--reason ...]`: the operator's gate hold (`SwarmStore.hold_gate`): the gate looks
  at nothing of the family until it is cleared; its `gate_ready` is kept. Safe beside a running swarm.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m league.swarm")
    parser.add_argument("command", choices=("run", "status", "seed-check", "hold-gate"))
    parser.add_argument("--root", default="/workspace/state")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--family", help="hold-gate: the family to hold (or release with --clear)")
    parser.add_argument("--clear", action="store_true", help="hold-gate: clear the hold")
    parser.add_argument("--reason", default="", help="hold-gate: why (kept in a private swarm.gate event)")
    args = parser.parse_args(argv)
    if args.command == "run":
        from .loop import main_run

        return main_run(args.root, once=args.once)
    if args.command == "hold-gate":
        from .store import SwarmStore

        if not args.family or not (Path(args.root) / "swarm.sqlite").exists():
            print(json.dumps({"error": "hold-gate needs --family and a swarm store under --root"}))
            return 2
        store = SwarmStore(args.root)
        try:
            ok = store.hold_gate(args.family, not args.clear, reason=args.reason)
            state = (store.family(args.family) or {}).get("state") or {}
        finally:
            store.close()
        print(json.dumps({"family": args.family, "found": ok, "gate_hold": bool(state.get("gate_hold")),
                          "gate_ready": bool(state.get("gate_ready"))}))
        return 0 if ok else 1
    if args.command == "status":
        from . import HEARTBEAT, bands
        from .store import SwarmStore

        root = Path(args.root)
        out: dict = {}
        try:
            out["heartbeat"] = json.loads((root / HEARTBEAT).read_text())
        except (OSError, ValueError):
            out["heartbeat"] = None
        if (root / "swarm.sqlite").exists():
            store = SwarmStore(root, readonly=True)
            out["totals"] = store.totals()
            out["bands"] = {b: sum(1 for f in store.families() if f["band"] == b) for b in ("gym", "candidate", "probe", "sized", "retired")}
            out["live_rows"] = [{k: r[k] for k in ("family", "band", "validation_passed", "holdout_passed", "version")} for r in bands.read(root)]
            out["gate_held"] = [{"family": f["id"], "gate": "held by the operator", "gate_ready": bool(f["state"].get("gate_ready"))}
                                for f in store.families(alive=True) if (f.get("state") or {}).get("gate_hold")]
            store.close()
        print(json.dumps(out, indent=1, default=str))
        return 0
    from .researcher import check_code
    from .seeds import SEEDS, program_for

    bad = 0
    for spec in SEEDS:
        code, params = program_for(spec)
        why = check_code(code)
        if why is None:
            try:
                from ..gym.runtime import load_program

                load_program(code, name=spec["id"], params=params)
            except ImportError:
                pass
            except Exception as exc:  # noqa: BLE001
                why = str(exc)
        if why:
            bad += 1
            print(f"{spec['id']}: {why}")
    print(json.dumps({"seeds": len(SEEDS), "refused": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

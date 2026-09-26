"""`python -m league.swarm run|status|seed-check --root /workspace/state`

- `run`: the swarm's process (`loop.Swarm.run`); `--once` runs one pass of the main loop and no researcher.
- `status`: the heartbeat and the store's totals, as JSON (read-only).
- `seed-check`: every founding family's starter program through the Gym's safety check and `load_program`
  (needs the Gym on this tree; numpy for `load_program`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m league.swarm")
    parser.add_argument("command", choices=("run", "status", "seed-check"))
    parser.add_argument("--root", default="/workspace/state")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run":
        from .loop import main_run

        return main_run(args.root, once=args.once)
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
            out["bands"] = {b: sum(1 for f in bands.read(root)["families"] if f["band"] == b)
                            for b in ("gym", "candidate", "probe", "sized", "retired")}
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

#!/usr/bin/env python3
"""Put the ranges family's bred desks on the founder's hourly clock, on the floor box.

Children copy their parent's cadence and model at birth, so the hourly cadence written into
`ltcm/desks/scholes.json` on Sept 16, 2026 reached only the founder. This edits the children's
manifests on the box in place: one session an hour, staggered so the family does not all wake at
once, at medium effort with a 24-turn ceiling so a session ends well before the market it priced
settles. Playbooks, tools, capital, lineage and everything else are left exactly as they are.

    python3 scripts/hourly_ranges.py            # show what would change
    python3 scripts/hourly_ranges.py --apply    # write it, then restart the loop with floor_box.py

Reads the box id from the same state file `scripts/floor_box.py` keeps. Prints no secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import floor_box  # noqa: E402

FAMILY = "ranges"
OFFSETS = ("10", "15", "20", "25", "30")  # minutes past the hour, one per child, in id order
MODEL = {"reasoning_effort": "medium", "max_turns": 24}
ORDERS_PER_DAY = 60

REMOTE = r'''
import json, glob, os, sys
apply = sys.argv[1] == "apply"
offsets = sys.argv[2].split(",")
changes = []
children = []
for path in sorted(glob.glob("/workspace/ltcm/desks/*.json")):
    d = json.load(open(path))
    if d.get("family") == "%(family)s" and d.get("parent_id"):
        children.append((path, d))
for n, (path, d) in enumerate(children):
    minute = offsets[n %% len(offsets)]
    sessions = ["%%02d:%%s" %% (h, minute) for h in range(24)]
    before = (d["cadence"]["sessions"], d["model"].get("reasoning_effort"), d["model"].get("max_turns"), d["limits"].get("max_orders_per_day"))
    d["cadence"]["sessions"] = sessions
    d["cadence"]["timezone"] = "UTC"
    d["model"]["reasoning_effort"] = "%(effort)s"
    d["model"]["max_turns"] = %(turns)d
    d["limits"]["max_orders_per_day"] = %(orders)d
    after = (sessions, d["model"]["reasoning_effort"], d["model"]["max_turns"], d["limits"]["max_orders_per_day"])
    changes.append((os.path.basename(path), before[0][:2], len(before[0]), after[0][:2], len(after[0]), before[1:], after[1:]))
    if apply:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, indent=2); f.write("\n")
        os.chmod(tmp, 0o600); os.replace(tmp, path)
for c in changes:
    print("%%s: %%s... x%%d -> %%s... x%%d | %%s -> %%s" %% c)
print("applied" if apply else "dry run", len(changes), "children")
'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the manifests (default: dry run)")
    args = parser.parse_args(argv)
    state = floor_box.read_state()
    box = floor_box.require_box(state)
    api = floor_box.client()
    script = REMOTE % {
        "family": FAMILY,
        "effort": MODEL["reasoning_effort"],
        "turns": MODEL["max_turns"],
        "orders": ORDERS_PER_DAY,
    }
    mode = "apply" if args.apply else "dry"
    result = api.exec(
        box,
        ["python3", "-c", script, mode, ",".join(OFFSETS)],
        timeout=120,
        on_output=None,
    )
    output = getattr(result, "output", None) or getattr(result, "stdout", "") or ""
    print(output.strip())
    code = getattr(result, "return_code", 0)
    if code:
        print(f"remote exit {code}", file=sys.stderr)
        return int(code)
    if args.apply:
        print("now restart the loop so the manifests are reloaded:  python3 scripts/floor_box.py deploy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

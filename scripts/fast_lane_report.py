"""FAST LANE V2's report on COPIES, from the command line (Oct 7, 2026; D2 and D4): the drift fit and the same-risk
buy-and-hold beside every screen result and every band row, the contamination measures beside every holdout look, the D5
status of every live band, and the Probe loss budget. REPORTED, NEVER A BAR. The report itself is
`league/ops/fast_lane.py` (`report`; its docstring says what each field is); the House's `fast_lane` job writes it daily
to `<state>/fast-lane-report.json` with the last 7 days of screen rows. This script is the same report on copies, with
any window:

    python scripts/fast_lane_report.py --swarm-root COPY --live LIVE_COPY --closes direction-closes.json [--since ISO]

It opens COPIES only (the swarm store read-only, the live state's copy read-only) and never the House's live files.
The captain's daily funnel report quotes it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the checkout's own league package

from league.ops.fast_lane import report  # noqa: E402 - after the checkout's path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--swarm-root", required=True, help="a COPY of the swarm's state root")
    parser.add_argument("--live", help="a COPY of live.sqlite")
    parser.add_argument("--closes", required=True, help="direction-closes.json (league/ops/direction.py)")
    parser.add_argument("--since", help="ISO time: Validation runs and looks from it")
    args = parser.parse_args(argv)
    print(json.dumps(report(args.swarm_root, args.live, args.closes, since=args.since), indent=1, default=str))
    return 0


__all__ = ["report", "main"]

if __name__ == "__main__":
    raise SystemExit(main())

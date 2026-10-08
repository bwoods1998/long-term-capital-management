"""THE LEARNING GAME's report from the command line (Oct 8, 2026; league/swarm/game.py, the build spec's section 7): R1
plumbing, R2 selection carry, R3 out-of-fold quality, R4 generation gain, R5 flow and cost, R6 Validation and money, and
the pre-registered decisions, aggregate and OPERATOR-ONLY (no agent reads it). The report itself is
`league/ops/game_report.py` (`report`; its docstring says what each part is); the House's `game` job writes it daily at
00:00Z. This script is the same report on demand:

    python scripts/game_report.py --swarm-root STATE [--day YYYY-MM-DD] [--draws 2000] [--seed 0] [--out DIR] [--print]

It opens the swarm store READ-ONLY (a copy or the House's state root) under that root's own settings (swarm.json over
policy.json) and writes `<root>/game/report-<day>.json` (or `<out>/report-<day>.json`), atomically. `--day` names the
file and the report's clock (the end of that UTC day; today's clock when absent). Family-cluster bootstrap intervals,
2,000 draws by default, 90% two-sided, seeded: the same store gives the same report.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the checkout's own league package

from league.ops.context import write_json  # noqa: E402 - after the checkout's path
from league.ops.game_report import path_for, report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--swarm-root", required=True, help="the swarm's state root (or a COPY of it): swarm.sqlite inside")
    parser.add_argument("--day", help="YYYY-MM-DD: the report's day (its clock is that day's end, UTC); today when absent")
    parser.add_argument("--draws", type=int, default=None, help="bootstrap draws (2,000 when absent)")
    parser.add_argument("--seed", type=int, default=0, help="the bootstrap's seed (0)")
    parser.add_argument("--out", help="the directory to write into (<swarm-root>/game when absent)")
    parser.add_argument("--print", action="store_true", help="print the report as well")
    args = parser.parse_args(argv)
    root = Path(args.swarm_root)
    if not (root / "swarm.sqlite").exists():
        parser.error(f"no swarm.sqlite in {root}")
    now = None
    if args.day:
        day = dt.date.fromisoformat(args.day)
        now = dt.datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=dt.timezone.utc).timestamp()
    out = report(root, now=now, draws=args.draws, seed=args.seed)
    path = (Path(args.out) / f"report-{out['day']}.json") if args.out else path_for(root, out["day"])
    write_json(path, out)
    if args.print:
        print(json.dumps(out, indent=1, sort_keys=True, default=str))
    print(str(path))
    return 0


__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())

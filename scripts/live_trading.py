"""Account-owner control: persistent earned trading on the existing venue balances.

    python scripts/live_trading.py
    python scripts/live_trading.py --enable earned-live-20260921
    python scripts/live_trading.py --disable
    python scripts/live_trading.py --ratify earned-live-20260921
    python scripts/live_trading.py --ratify earned-live-20260921 --grant-version 2
    python scripts/live_trading.py --scale-report [--json] [--funded kalshi=1046.83]
    python scripts/live_trading.py --scale-report --root ./state-copy [--json]
    python scripts/live_trading.py --scale-report --capacity-json k2.json   # a what-if on K2's Kalshi fill curves

The report only reads balances. Enabling records the current cash allocation, resumes unused
provider allowance without expiry, and restarts the House to load the accelerated game.
Rerunning cannot reset spending, enlarge capital or reactivate a revoked authorization.

`--ratify ... --grant-version 2` is the owner's switch for the scale rule (`league/grants.py`):
it ratifies the grant under the current money rules and records version 2, whose `scale_tranches`
let a deposit enter a venue's envelope in tranches that proven capacity and real profit unlock;
`--grant-version 1` switches it off. `--scale-report` is read-only, on the box by default or on a
copied state directory with `--root` (its `allocator-board.json`, `ledger.sqlite`, `campaigns.sqlite`).
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.floor_box import client, read_state, require_box


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--enable', help='Explicit account-owner authorization identity.')
    action.add_argument('--disable', action='store_true', help='Revoke new live entries, keeping exits available.')
    action.add_argument('--ratify', help='Keep this grant, same capital, under revised money rules.')
    action.add_argument('--scale-report', action='store_true',
                        help='Read-only: per venue, proven capacity against the envelope and the tranche the evidence unlocks.')
    parser.add_argument('--grant-version', type=int, choices=(1, 2),
                        help='With --ratify: 2 adds the scale rule (scale_tranches); 1 switches it off.')
    parser.add_argument('--json', action='store_true', help='With --scale-report: JSON rather than text.')
    parser.add_argument('--funded', action='append', default=[], metavar='VENUE=USD',
                        help="With --scale-report: a venue account's equity (default: the ledger's last floor.mark).")
    parser.add_argument('--root', type=Path, help='With --scale-report: a copied state directory, read here, not on the box.')
    parser.add_argument('--capacity-json', type=Path, metavar='PATH',
                        help="With --scale-report: the K2 study's output (scripts/kalshi_capacity.py --json), read here; "
                             "a what-if beside the rule's own reading, never a decision.")
    args = parser.parse_args(argv)
    if args.grant_version is not None and not args.ratify:
        parser.error('--grant-version goes with --ratify')
    if (args.json or args.funded or args.root or args.capacity_json) and not args.scale_report:
        parser.error('--json, --funded, --root and --capacity-json go with --scale-report')
    report_args = ['--scale-report'] + (['--json'] if args.json else []) + [f'--funded={item}' for item in args.funded]
    if args.scale_report and args.root:
        from league.live_trading import main as league_main
        league_main(['--root', str(args.root), *report_args]
                    + ([f'--capacity-json={args.capacity_json}'] if args.capacity_json else []))
        return
    if args.scale_report and args.capacity_json:
        # The study is a file here, not on the box: its curves travel reduced, as an argument.
        from league.live_trading import capacity_study
        reduced = capacity_study(json.loads(args.capacity_json.read_text(encoding='utf-8')), args.capacity_json)
        report_args.append('--capacity-curves=' + json.dumps(reduced, separators=(',', ':')))
    command = ['/workspace/.venv/bin/python', '-c',
        "import os,sys; os.environ['LEAGUE_ENV']='/workspace/.env'; sys.path.insert(0,'/workspace/current'); "
        "from league.live_trading import main; main()", '--root', '/workspace/state']
    if args.enable:
        command += ['--enable', args.enable]
    elif args.disable:
        command += ['--disable']
    elif args.ratify:
        command += ['--ratify', args.ratify]
        if args.grant_version is not None:
            command += ['--grant-version', str(args.grant_version)]
    elif args.scale_report:
        command += report_args
    api, box = client(), require_box(read_state())
    result = api.exec(box, command, timeout=120 if args.scale_report else 60, on_output=None)
    result.check()
    print(result.stdout)
    if (args.enable or args.ratify) and (json.loads(result.stdout).get('live_trading') or {}).get('active'):
        result = api.exec(box, ['sh', '/workspace/restart.sh'], timeout=45, on_output=None)
        result.check()
        print(result.stdout)


if __name__ == '__main__':
    main()

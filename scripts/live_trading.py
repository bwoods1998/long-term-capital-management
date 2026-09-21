"""Account-owner control: persistent earned trading on the existing venue balances.

    python scripts/live_trading.py
    python scripts/live_trading.py --enable earned-live-20260921
    python scripts/live_trading.py --disable

The report only reads balances. Enabling records the current cash allocation, resumes unused
provider allowance without expiry, and restarts the House to load the accelerated game.
Rerunning cannot reset spending, enlarge capital or reactivate a revoked authorization.
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
    args = parser.parse_args(argv)
    command = ['/workspace/.venv/bin/python', '-c',
        "import os,sys; os.environ['LEAGUE_ENV']='/workspace/.env'; sys.path.insert(0,'/workspace/current'); "
        "from league.live_trading import main; main()", '--root', '/workspace/state']
    if args.enable:
        command += ['--enable', args.enable]
    elif args.disable:
        command += ['--disable']
    api, box = client(), require_box(read_state())
    result = api.exec(box, command, timeout=60, on_output=None)
    result.check()
    print(result.stdout)
    if args.enable and (json.loads(result.stdout).get('live_trading') or {}).get('active'):
        result = api.exec(box, ['sh', '/workspace/restart.sh'], timeout=45, on_output=None)
        result.check()
        print(result.stdout)


if __name__ == '__main__':
    main()

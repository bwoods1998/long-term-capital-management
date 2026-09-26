"""Account-owner control of the grant of real money on the House box (`league/live_trading.py`).

    python3 scripts/live_trading.py                          # report: the grant, and what enabling would record now
    python3 scripts/live_trading.py --enable                 # create options-swarm-20260928 (the Brokerage Account only)
    python3 scripts/live_trading.py --ratify                 # after a money-rule change or a deposit: re-pin, capital read afresh
    python3 scripts/live_trading.py --disable                # revoke for good: no new real entry; exits go on

Capital is the lower of the Brokerage Account's equity and the owner's ceiling (`league/config.json`
`live_trading.ceiling_usd`) at each ratification. The command runs on the box against
`/workspace/state/live-grant.sqlite`; the House reads that store at every check, so nothing restarts.
A revoked grant is never reactivated.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.floor_box import client, read_state, require_box  # noqa: E402

GRANT_ID = "options-swarm-20260928"  # league.live_trading.GRANT_ID


def command(args: argparse.Namespace) -> list[str]:
    line = ['/workspace/.venv/bin/python', '-c',
            "import os,sys; os.environ['LEAGUE_ENV']='/workspace/.env'; sys.path.insert(0,'/workspace/current'); "
            "from league.live_trading import main; main(sys.argv[1:])", '--root', '/workspace/state']
    if args.enable:
        line += ['--enable', args.enable]
    elif args.ratify:
        line += ['--ratify', args.ratify]
    elif args.disable:
        line += ['--disable']
    return line


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--enable', nargs='?', const=GRANT_ID, help=f'Create the grant (default {GRANT_ID}).')
    action.add_argument('--ratify', nargs='?', const=GRANT_ID, help='Re-pin the grant to the current money rules, capital read afresh.')
    action.add_argument('--disable', action='store_true', help='Revoke new real entries for good, keeping exits available.')
    args = parser.parse_args(argv)
    api, box = client(), require_box(read_state())
    result = api.exec(box, command(args), timeout=60, on_output=None)
    result.check()
    print(result.stdout)


if __name__ == '__main__':
    main()

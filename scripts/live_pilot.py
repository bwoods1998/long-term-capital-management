"""Account-owner command: report or explicitly enable the prepared micro-real window on the House.

    python scripts/live_pilot.py
    python scripts/live_pilot.py --activate micro-learning-20260921

Activation allows qualified agents to request fresh audits and trade at the existing micro limits.
The window ends with the current research burst. Earned scaling is bounded by $50 per agent
and the same $200 aggregate loss envelope; promotion never escapes that envelope.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.floor_box import client, read_state, require_box


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', help='Explicit account-owner activation identity; omission only reports.')
    args = parser.parse_args(argv)
    command = ['/workspace/.venv/bin/python', '-c',
        "import sys; sys.path.insert(0, '/workspace/current'); from league.live_pilot import main; main()",
        '--root', '/workspace/state']
    if args.activate:
        command += ['--activate', args.activate]
    result = client().exec(require_box(read_state()), command, timeout=45, on_output=None)
    result.check()
    print(result.stdout)


if __name__ == '__main__':
    main()

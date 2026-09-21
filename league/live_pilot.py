"""Prepare/report or explicitly activate a bounded live learning window.

Activation enables the existing automatic paper screen -> audit -> micro path on real accounts.
Evidence-based scaling stays inside the same $200 aggregate envelope, at most $50 lent per agent.
The account owner executes --activate; deploying this module alone grants nothing.
"""
from pathlib import Path


def policy():
    from .constitution import digest
    return {'version': 1, 'max_rung': 3, 'max_agents': 8,
            'max_loss_usd': '200', 'stake_usd': '25', 'max_stake_usd': '50',
            'constitution_digest': digest(),
            'question': 'Do qualified paper programs execute within their recorded limits on real venues?',
            'acceptance': 'Compare real fills, fees, missed fills, exits and reconciliation with paper; record losses and uncertainty.'}


def main(argv=None):
    import argparse
    import json
    from .campaigns import CampaignBudget
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--activate', help='Explicit account-owner experiment identity; omission only reports.')
    args = parser.parse_args(argv)
    if not (args.root / 'campaigns.sqlite').is_file():
        parser.error('an existing campaign database is required')
    guard = CampaignBudget(args.root / 'campaigns.sqlite')
    try:
        if args.activate:
            guard.activate_live_pilot(args.activate)
        print(json.dumps({'live_pilot': guard.live_pilot(),
                          'micro_entries_allowed': guard.allows_live(2),
                          'scaled_entries_allowed': guard.allows_live(3),
                          'prepared_policy': policy()}, indent=2))
    finally:
        guard.close()


if __name__ == '__main__':
    main()

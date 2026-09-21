"""Owner-activated persistent trading, using a fixed allocation of existing venue cash.

No calendar expiry and no performance bypass. Provider commitments and monetary caps survive.
Reporting and deployment do not activate trading. The account owner runs --enable.
"""
from decimal import Decimal, ROUND_DOWN
import json
from pathlib import Path


def policy(venue_capital):
    from .constitution import CONSTITUTION, digest
    if set(venue_capital) != {'alpaca', 'kalshi'}:
        raise ValueError('capital must name Alpaca and Kalshi')
    amounts = {k: Decimal(str(v)) for k, v in venue_capital.items()}
    if any(not v.is_finite() or v < 0 for v in amounts.values()):
        raise ValueError('venue capital must be finite and nonnegative')
    amounts = {k: v.quantize(Decimal('.01'), rounding=ROUND_DOWN) for k, v in amounts.items()}
    total = sum(amounts.values())
    stake = Decimal(CONSTITUTION['rungs']['2']['stake_usd'])
    if max(amounts.values()) < stake or not stake <= total <= Decimal('10000'):
        raise ValueError('live allocation must cover a micro stake and remain within the $10,000 project envelope')
    return {'version': 1, 'max_rung': 3, 'max_agents': int(total // stake),
            'max_loss_usd': str(total), 'stake_usd': str(stake),
            'venue_capital_usd': {k: str(v) for k, v in amounts.items()},
            'constitution_digest': digest(), 'expires': None,
            'research_funding': 'Only unused original burst allowance within campaign caps; no calendar expiry or replenishment.',
            'scaling': 'Existing performance gates and quarter-Kelly sizing; venue and aggregate capital limits include historical losses.',
            'capital_source': 'Existing cash only; later deposits do not enlarge this allocation.'}


def read_venue_capital():
    """Read account cash; never construct House, submit orders or transfer collateral."""
    from .service import load_config, load_env, secret
    from .venues import gateway_broker
    load_env()
    config = load_config()
    amounts = {}
    for venue in ('alpaca', 'kalshi'):
        broker = gateway_broker(venue, gateway_url=config['gateway_url'], token=secret('GATEWAY_TOKEN'))
        balance = broker.balance()
        if balance.currency != 'USD':
            raise ValueError('live capital must be denominated in USD')
        # Buying power can include leverage. It is deliberately not part of this allocation.
        amounts[venue] = str(max(Decimal(0), min(balance.cash, balance.equity)))
    return policy(amounts)['venue_capital_usd']


def report(guard, *, prepared_capital=None):
    live = guard.live_trading()
    burst = guard.burst()
    unused = ({k: str(max(Decimal(0), Decimal(str(cap)) - Decimal(guard._burst_used(k, burst)) / 1000000))
               for k, cap in burst['policy']['caps_usd'].items()} if burst else {})
    return {'live_trading': live, 'micro_entries_allowed': guard.allows_live(2),
            'scaled_entries_allowed': guard.allows_live(3), 'research_running': guard.running(),
            'research_remaining_usd': {k: str(guard.remaining(k)) for k in ('sail', 'openai')},
            'unused_burst_allowance_usd': unused, 'meters_ready': {k: guard.ready(k) for k in ('sail', 'openai')},
            'prepared_policy': policy(prepared_capital) if prepared_capital else live['policy'] if live else None}


def main(argv=None):
    import argparse
    from .campaigns import CampaignBudget
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--enable', help='Account-owner authorization identity; enables persistent trading.')
    action.add_argument('--disable', action='store_true', help='Revoke new live entries; keep exits and accounting.')
    args = parser.parse_args(argv)
    if not (args.root / 'campaigns.sqlite').is_file():
        parser.error('an existing campaign database is required')
    guard = CampaignBudget(args.root / 'campaigns.sqlite')
    try:
        live = guard.live_trading()
        capital = live['policy']['venue_capital_usd'] if live else None if args.disable else read_venue_capital()
        if args.enable:
            guard.activate_live_trading(args.enable, capital)
        elif args.disable:
            guard.revoke_live_trading()
        print(json.dumps(report(guard, prepared_capital=capital), indent=2))
    finally:
        guard.close()


if __name__ == '__main__':
    main()

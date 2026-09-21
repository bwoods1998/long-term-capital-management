"""A timed owner-funded learning experiment; never a self-authorized budget increase."""
from copy import deepcopy
from decimal import Decimal
import json
import math
from pathlib import Path


def load_policy():
    value = json.loads(Path(__file__).with_name('overnight.json').read_text())
    validate(value)
    return value


def validate(p):
    expected = {'version', 'duration_hours', 'caps_usd', 'research_minutes', 'luna_fraction',
                'research_workers', 'replay_workers', 'newcomer_seconds', 'replay_lease_minutes',
                'minimum_research_passes', 'performance_exponent', 'performance_min_blocks',
                'niche_floor_share', 'max_population', 'question', 'acceptance'}
    if set(p) != expected or p['version'] != 1:
        raise ValueError('unsupported overnight policy')
    ranges = {'duration_hours': (1, 8), 'research_minutes': (10, 180), 'luna_fraction': (0, 1),
              'research_workers': (1, 16), 'replay_workers': (1, 6), 'newcomer_seconds': (600, 3600),
              'replay_lease_minutes': (60, 720), 'minimum_research_passes': (2, 20),
              'performance_exponent': (2, 4), 'performance_min_blocks': (5, 50),
              'niche_floor_share': (.1, .7), 'max_population': (12, 48)}
    integral = {'research_workers', 'replay_workers', 'minimum_research_passes',
                'performance_exponent', 'performance_min_blocks', 'max_population'}
    for name, (low, high) in ranges.items():
        value = p[name]
        if (type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high
                or name in integral and type(value) is not int):
            raise ValueError('invalid overnight '+name)
    if set(p['caps_usd']) != {'sail', 'openai'}:
        raise ValueError('overnight only funds Sail and OpenAI; Jev has its existing gateway allowance')
    for value in p['caps_usd'].values():
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 < amount <= 1000:
            raise ValueError('invalid overnight allowance')
    if not all(isinstance(p[k], str) and p[k].strip() for k in ('question', 'acceptance')):
        raise ValueError('a learning experiment needs a question and acceptance criteria')


def active(guard, clock):
    burst = guard.burst() if guard is not None else None
    live = guard.live_trading() if guard is not None else None
    if burst and live and live['active']:
        return {**burst, 'ends': None, 'live_authorization': live['id']}
    return burst if burst and burst['started'] <= clock() < burst['ends'] and guard.running() else None


def game_for(base, burst):
    game = deepcopy(base)
    if not burst:
        return game
    p = burst['policy']
    validate(p)
    e = game['economy']
    # Changing the payout clock must not shorten paper opportunity or the old hard replay deadline.
    grace = float(e.get('displace_after_epochs', 2)) * float(e['epoch_seconds'])
    deadline = float(e.get('replay_deadline_epochs', 12)) * float(e['epoch_seconds'])
    e.update(epoch_seconds=3600, displace_after_epochs=grace / 3600,
             replay_deadline_epochs=deadline / 3600, newcomer_seconds=p['newcomer_seconds'],
             performance_exponent=p['performance_exponent'], performance_min_blocks=p['performance_min_blocks'],
             niche_floor_share=str(p['niche_floor_share']), max_population=p['max_population'],
             endowment_usd='2.00', fork_threshold_usd='2.00')
    research = game['research']
    research.update(min_hours_between=p['research_minutes'] / 60, max_turns=12)
    research.setdefault('idle', {})['min_hours_between'] = p['research_minutes'] / 60
    game['merton']['schedule_hours'].update(operator=.25, toolsmith=.5, architect=.5, teacher=1, designer=1)
    # Faster frontier access is for WINNERS only. A losing agent keeps the base game's wait:
    # Sept 21, 2026, losing paper agents hired Merton hourly (hilibrand-2 $7, huang-7 $9.69).
    game['consult']['profitable_cooldown_hours_by_rung'] = {'1': .5, '2': .25, '3': .25}
    from .economy import check_bounds
    check_bounds(game)
    return game


def main():
    import argparse
    from .campaigns import CampaignBudget
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--activate', help='Explicit immutable owner experiment identity; omitted only reports.')
    args = parser.parse_args()
    guard = CampaignBudget(args.root / 'campaigns.sqlite')
    try:
        if args.activate:
            guard.activate_burst(args.activate, load_policy())
        print(json.dumps(guard.report(), indent=2))
    finally:
        guard.close()


if __name__ == '__main__':
    main()

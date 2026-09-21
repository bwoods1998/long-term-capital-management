import math
from datetime import datetime
from decimal import Decimal, ROUND_CEILING


NEEDS = {
    'venue': 'kalshi',
    'horizon': 'day',
    'style': 'sports-favorites-taker',
    'series': [
        'KXNFLGAME',
        'KXLIGAPORTUGALGAME',
        'KXLIGAMXGAME',
        'KXARGPREMDIVGAME',
        'KXMLSGAME',
    ],
    'max_hours_to_close': 48,
    'wake_minutes': 5,
    'parameter_rules': {
        'bounds': {
            'ask_min': [0.90, 0.94],
            'ask_max': [0.94, 0.97],
            'all_in_max': [0.97, 0.99],
            'max_spread': [0.0, 0.03],
            'max_positions': [1, 3],
        },
        'ordered': [
            ['ask_min', 'ask_max'],
            ['ask_max', 'all_in_max'],
        ],
        'frozen': ['notional_usd'],
    },
}

PARAMS = {
    'ask_min': 0.90,
    'ask_max': 0.97,
    'all_in_max': 0.98,
    'max_spread': 0.02,
    'max_positions': 3,
    'notional_usd': 2.0,
}


def number(value, default=None):
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except (ValueError, OverflowError):
        return None


def event_key(market):
    # Moneyline tickers share an event prefix before the outcome suffix.
    # No cross-series event identity or sports schedule is inferred.
    return market.rsplit('-', 1)[0]


def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get('params') or {})
    prior = ctx.get('memory') or {}
    memory = {
        'last_attempt': number(prior.get('last_attempt'), 0.0),
        'screens': {},
    }
    result = {
        'intents': [],
        'cancels': [],
        'thought': 'No eligible moneyline entry is available.',
        'memory': memory,
    }

    # A marketable limit can remain open after a quote moves. Do not let
    # yesterday's decision turn into persistent, unmonitored maker exposure.
    orders = ctx.get('open_orders') or []
    if orders:
        ids = []
        for order in orders:
            order_id = order.get('order_id')
            if isinstance(order_id, str) and order_id and order_id not in ids:
                ids.append(order_id)
                if len(ids) == 20:
                    break
        result['cancels'] = ids
        result['thought'] = 'Cancel outstanding orders and wait for acknowledgement before submitting another entry.'
        return result

    if ctx.get('venue') != 'kalshi':
        result['thought'] = 'This program only trades Kalshi moneylines.'
        return result

    now = timestamp(ctx.get('now'))
    if now is None:
        result['thought'] = 'A valid decision timestamp is required before entering.'
        return result

    # Throttle submissions, not fills; never assume an emitted intent filled.
    last_attempt = memory['last_attempt']
    if last_attempt > 0 and now - last_attempt < 600:
        result['thought'] = 'Wait ten minutes after the last submission to avoid duplicate entries during acknowledgement delays.'
        return result

    positions = [
        position for position in (ctx.get('positions') or [])
        if number(position.get('quantity'), 0.0) > 0
    ]
    if len(positions) >= p['max_positions']:
        result['thought'] = 'The holding cap is reached; existing contracts are held to settlement.'
        return result

    held_markets = set()
    held_events = set()
    for position in positions:
        market = position.get('market')
        if isinstance(market, str) and market:
            held_markets.add(market)
            held_events.add(event_key(market))

    limits = ctx.get('limits') or {}
    budget = min(
        p['notional_usd'],
        number(ctx.get('cash'), 0.0),
        number(limits.get('max_order_usd'), 0.0),
        number(limits.get('max_position_usd'), 0.0),
    )
    if budget <= 0:
        result['thought'] = 'No cash or permitted entry budget is available.'
        return result

    rate = number((ctx.get('fees') or {}).get('kalshi_taker_rate'), 0.07)
    if rate < 0:
        result['thought'] = 'The supplied fee rate is invalid; do not enter.'
        return result

    counts = {
        'screened': 0,
        'unsupported_series': 0,
        'held_event': 0,
        'horizon': 0,
        'book': 0,
        'band': 0,
        'spread': 0,
        'cost': 0,
        'eligible': 0,
    }
    memory['screens'] = counts
    best = None
    best_rank = None
    seen = set()

    for row in (ctx.get('markets') or []):
        counts['screened'] += 1
        series = row.get('series')
        market = row.get('market')
        if (
            series not in NEEDS['series']
            or not isinstance(market, str)
            or market.count('-') < 2
            or market.split('-', 1)[0] != series
        ):
            counts['unsupported_series'] += 1
            continue
        if market in seen:
            continue
        seen.add(market)
        if market in held_markets or event_key(market) in held_events:
            counts['held_event'] += 1
            continue

        close_hours = number(row.get('hours_to_close'))
        resolve_hours = number(row.get('hours_to_resolve'))
        if (
            close_hours is None or resolve_hours is None
            or not 0 < close_hours <= 48
            or not 0 < resolve_hours <= 48
        ):
            counts['horizon'] += 1
            continue

        yes_bid = number(row.get('yes_bid'))
        yes_ask = number(row.get('yes_ask'))
        if (
            yes_bid is None or yes_ask is None
            or not 0 <= yes_bid <= yes_ask <= 1
        ):
            counts['book'] += 1
            continue

        # NFL arm: buy the quoted YES favourite. Soccer arm: buy NO on
        # a quoted longshot, without mistaking a three-way game for binary.
        leg = 'yes' if series == 'KXNFLGAME' else 'no'
        price = yes_ask if leg == 'yes' else round(1.0 - yes_bid, 10)
        spread = round(yes_ask - yes_bid, 10)
        if not p['ask_min'] <= price <= p['ask_max']:
            counts['band'] += 1
            continue
        if spread > p['max_spread'] + 1e-12:
            counts['spread'] += 1
            continue

        price_decimal = Decimal(str(price))
        # Per-contract rounding is conservative relative to aggregate-order
        # rounding and reserves enough for whole-contract partial fills.
        fee_per_contract = (
            Decimal(str(rate)) * price_decimal
            * (Decimal('1') - price_decimal)
        ).quantize(Decimal('0.01'), rounding=ROUND_CEILING)
        unit_cost = price_decimal + fee_per_contract
        if unit_cost > Decimal(str(p['all_in_max'])):
            counts['cost'] += 1
            continue
        quantity = int(Decimal(str(budget)) / unit_cost)
        if quantity < 1:
            counts['cost'] += 1
            continue

        counts['eligible'] += 1
        volume = max(0.0, number(row.get('volume_24h'), 0.0))
        # Rank execution quality only; neither volume nor price is treated
        # as a calibrated settlement probability.
        rank = (spread, -volume, market)
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best = {
                'market': market,
                'leg': leg,
                'side': 'buy',
                'quantity': quantity,
                'type': 'limit',
                'limit_price': price,
                'reason': 'Take the quoted moneyline favourite with a price cap and rounded taker-fee reserve; hold to expected settlement within 48 hours.',
            }

    if best is None:
        result['thought'] = 'No unheld moneyline passes the horizon, favourite-band, spread and all-in budget screens; rejection counts are retained in memory.'
        return result

    result['intents'] = [best]
    memory['last_attempt'] = now
    result['thought'] = 'Submit one marketable limit to test the sports favourite bias after fees; the quoted price is not a known win probability.'
    return result

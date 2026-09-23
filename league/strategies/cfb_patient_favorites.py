import math
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR


NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "cfb-patient-favorites",
    "series": ["KXNCAAFGAME"],
    "max_hours_to_close": 48,
    "wake_minutes": 5,
    "parameter_rules": {
        "bounds": {
            "resolve_min_hours": [6, 12],
            "resolve_max_hours": [24, 48],
            "quote_ttl_minutes": [30, 120],
            "quote_lag": [0.01, 0.03],
            "portfolio_usd": [1, 6]
        },
        "ordered": [["resolve_min_hours", "resolve_max_hours"]],
        "frozen": [
            "bid_min", "bid_max", "max_spread", "resolve_min_hours",
            "resolve_max_hours", "quote_lag", "notional_usd",
            "portfolio_usd", "max_positions"
        ]
    }
}

PARAMS = {
    "bid_min": 0.93,
    "bid_max": 0.97,
    "max_spread": 0.04,
    "resolve_min_hours": 6,
    "resolve_max_hours": 36,
    "quote_ttl_minutes": 60,
    "quote_lag": 0.02,
    "notional_usd": 2.0,
    "portfolio_usd": 6.0,
    "max_positions": 3
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
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def game_key(ticker):
    if not isinstance(ticker, str):
        return None
    parts = ticker.split('-')
    if len(parts) < 3 or parts[0] != 'KXNCAAFGAME':
        return None
    if not all(parts):
        return None
    return ticker.rsplit('-', 1)[0]


def fee(quantity, price, rate):
    return math.ceil(rate * quantity * price * (1.0 - price) * 10000.0) / 10000.0


def eligible(row, params):
    ticker = row.get('market')
    game = game_key(ticker)
    if row.get('series') != 'KXNCAAFGAME' or game is None:
        return None
    close = number(row.get('hours_to_close'))
    resolve = number(row.get('hours_to_resolve'))
    bid = number(row.get('yes_bid'))
    ask = number(row.get('yes_ask'))
    if None in (close, resolve, bid, ask):
        return None
    if not 0 < close <= 48:
        return None
    if not params['resolve_min_hours'] <= resolve <= params['resolve_max_hours']:
        return None
    if not 0 < bid < ask <= 1:
        return None
    if ask - bid > params['max_spread'] + 1e-12:
        return None
    price = float((Decimal(str(bid)) * 100).to_integral_value(rounding=ROUND_FLOOR) / 100)
    if not params['bid_min'] <= price <= params['bid_max'] or price >= ask:
        return None
    return {
        'market': ticker, 'game': game, 'price': price, 'ask': ask,
        'resolve': resolve,
        'volume': max(0.0, number(row.get('volume_24h'), 0.0))
    }


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params') or {})
    orders = ctx.get('open_orders') or []
    output = {'intents': [], 'cancels': [], 'thought': '', 'memory': {}}
    now = timestamp(ctx.get('now'))
    if now is None:
        output['cancels'] = [
            order['order_id'] for order in orders
            if order.get('side') == 'buy' and order.get('order_id')
        ][:20]
        output['thought'] = 'The decision clock is unavailable; cancel resting buys and add no risk.'
        return output

    limits = ctx.get('limits') or {}
    order_cap = max(0.0, number(limits.get('max_order_usd'), 0.0))
    position_cap = max(0.0, number(limits.get('max_position_usd'), 0.0))
    cash = max(0.0, number(ctx.get('cash'), 0.0))
    rate = max(0.07, number((ctx.get('fees') or {}).get('kalshi_taker_rate'), 0.07))
    quotes = {}
    for row in ctx.get('markets') or []:
        quote = eligible(row, params)
        if quote is not None:
            quotes[quote['market']] = quote

    games = set()
    committed = 0.0
    held_count = 0
    uncertain = False
    for position in ctx.get('positions') or []:
        quantity = number(position.get('quantity'))
        if quantity is None:
            uncertain = True
            continue
        if quantity <= 0:
            continue
        game = game_key(position.get('market'))
        if game is None:
            uncertain = True
        else:
            games.add(game)
        cost = number(position.get('average_cost'), 1.0)
        if not 0 < cost <= 1:
            cost = 1.0
        committed += quantity * cost + fee(quantity, cost, rate)
        held_count += 1

    reserved_cash = 0.0
    working_count = 0
    cancellation_needed = False
    for order in orders:
        if order.get('side') != 'buy':
            uncertain = True
            continue
        ticker = order.get('market')
        quote = quotes.get(ticker)
        price = number(order.get('limit_price'))
        quantity = number(order.get('quantity'))
        filled = number(order.get('filled'), 0.0)
        submitted = timestamp(order.get('submitted_at'))
        remaining = None if quantity is None else max(0.0, quantity - filled)
        valid = (
            not uncertain and quote is not None and order.get('leg') == 'yes'
            and price is not None and remaining is not None
            and remaining >= 1 and remaining == math.floor(remaining)
            and submitted is not None
        )
        cost = 0.0
        if valid:
            cost = remaining * price + fee(remaining, price, rate)
            valid = (
                params['bid_min'] <= price <= params['bid_max']
                and price <= quote['price'] and price < quote['ask']
                and quote['price'] - price <= params['quote_lag'] + 1e-12
                and 0 <= now - submitted <= 60 * params['quote_ttl_minutes']
                and cost <= min(params['notional_usd'], order_cap, position_cap)
                and committed + cost <= params['portfolio_usd']
                and quote['game'] not in games
                and len(games) < params['max_positions']
                and remaining * price >= 1.0
            )
        if not valid:
            cancellation_needed = True
            order_id = order.get('order_id')
            if order_id and len(output['cancels']) < 20:
                output['cancels'].append(order_id)
            continue
        games.add(quote['game'])
        committed += cost
        reserved_cash += cost
        working_count += 1

    output['memory'] = {
        'eligible_markets': len(quotes),
        'held_positions': held_count,
        'retained_buys': working_count,
        'recent_refusals': sum(
            1 for outcome in ctx.get('recent_order_outcomes') or []
            if outcome.get('status') == 'refused'
        )
    }
    if cancellation_needed or uncertain:
        output['thought'] = 'Remove ineligible or duplicate commitments and wait for confirmed account state before adding risk. Filled contracts remain held for settlement.'
        return output

    cash = max(0.0, cash - reserved_cash)
    risk = ctx.get('event_risk') or {}
    headroom = risk.get('remaining_by_market_usd')
    ranked = sorted(quotes.values(), key=lambda item: (-item['volume'], item['resolve'], item['market']))
    for quote in ranked:
        if len(games) >= params['max_positions'] or len(output['intents']) >= 8:
            break
        if quote['game'] in games:
            continue
        budget = min(
            params['notional_usd'], order_cap, position_cap,
            params['portfolio_usd'] - committed, cash
        )
        # A supplied map is authoritative; a missing ticker is not permission.
        if headroom is not None:
            if not isinstance(headroom, dict):
                continue
            budget = min(budget, max(0.0, number(headroom.get(quote['market']), 0.0)))
        if budget <= 0.0001:
            continue
        price = quote['price']
        unit_cost = price + rate * price * (1.0 - price)
        quantity = math.floor((budget - 0.0001) / unit_cost)
        while quantity > 0 and quantity * price + fee(quantity, price, rate) > budget:
            quantity -= 1
        if quantity < 1 or quantity * price < 1.0:
            continue
        cost = quantity * price + fee(quantity, price, rate)
        output['intents'].append({
            'market': quote['market'], 'leg': 'yes', 'side': 'buy',
            'quantity': quantity, 'type': 'limit', 'limit_price': price,
            'post_only': True,
            'reason': 'Rest at the CFB favourite bid within the fixed payout window; fee-reserved sizing, one selection per game, hold to settlement.'
        })
        games.add(quote['game'])
        committed += cost
        cash -= cost

    output['thought'] = (
        'Found ' + str(len(quotes)) + ' eligible CFB books and retained '
        + str(working_count) + ' working bids. Submitted '
        + str(len(output['intents']))
        + ' passive entries within cash, game and fee-reserved portfolio limits.'
    )
    return output

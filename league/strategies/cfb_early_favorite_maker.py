import math
from datetime import datetime


NEEDS = {
    'venue': 'kalshi',
    'horizon': 'day',
    'style': 'early-favourite-maker',
    'series': ['KXNCAAFGAME'],
    'max_hours_to_close': 48,
    'wake_minutes': 5,
    'parameter_rules': {
        'bounds': {
            'max_spread': [0.02, 0.05],
            'quote_ttl_minutes': [15, 60],
        },
        'frozen': [
            'yes_bid_min', 'yes_bid_max', 'min_resolve_hours',
            'notional_usd', 'portfolio_budget_usd', 'max_positions',
        ],
    },
}

PARAMS = {
    'yes_bid_min': 0.93,
    'yes_bid_max': 0.97,
    'max_spread': 0.04,
    'min_resolve_hours': 12.0,
    'quote_ttl_minutes': 30,
    'notional_usd': 2.0,
    'portfolio_budget_usd': 6.0,
    'max_positions': 3,
}


def number(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def stamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def event_id(ticker):
    parts = str(ticker).split('-')
    return '-'.join(parts[:-1]) if len(parts) >= 3 else str(ticker)


def conservative_price(value):
    price = number(value, 1.0)
    return price if 0.0 < price <= 1.0 else 1.0


def expense(quantity, price, rate):
    # Reserve the full taker schedule even though every new order is passive.
    fee = math.ceil(rate * quantity * price * (1.0 - price) * 10000.0) / 10000.0
    return quantity * price + fee


def market_terms(market, now, params):
    ticker = str(market.get('market', ''))
    parts = ticker.split('-')
    if market.get('series') != 'KXNCAAFGAME':
        return None
    if len(parts) != 3 or parts[0] != 'KXNCAAFGAME' or not parts[1] or not parts[2]:
        return None
    resolves = number(market.get('hours_to_resolve'), -1.0)
    closes = number(market.get('hours_to_close'), -1.0)
    close_at = stamp(market.get('close_time'))
    if not params['min_resolve_hours'] <= resolves <= 48.0:
        return None
    if not 0.0 < closes <= 48.0 or close_at is None or close_at <= now:
        return None
    bid = number(market.get('yes_bid'), -1.0)
    ask = number(market.get('yes_ask'), -1.0)
    if not 0.0 < bid < ask <= 1.0:
        return None
    if bid < params['yes_bid_min'] or bid > params['yes_bid_max']:
        return None
    if ask - bid > params['max_spread'] + 1e-9:
        return None
    ceiling = min(params['yes_bid_max'], bid + 0.01, ask - 0.01)
    price = math.floor(ceiling * 100.0 + 1e-8) / 100.0
    if price < params['yes_bid_min'] - 1e-9 or price >= ask:
        return None
    return (bid, ask, price)


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params') or {})
    now = stamp(ctx.get('now'))
    orders = ctx.get('open_orders') or []
    outcomes = ctx.get('recent_order_outcomes') or []
    refusals = [row for row in outcomes if row.get('status') == 'refused']
    memory = {
        'eligible_markets': 0,
        'recent_refusals': len(refusals),
        'last_refusal': str(refusals[-1].get('reason', ''))[:180] if refusals else '',
    }

    def result(thought, intents=None, cancels=None):
        return {
            'intents': intents or [],
            'cancels': (cancels or [])[:20],
            'thought': thought,
            'memory': memory,
        }

    if now is None:
        cancels = [row['order_id'] for row in orders
                   if row.get('side') == 'buy' and row.get('order_id')]
        return result('The decision clock is unavailable; cancel resting entries and take no new risk.', cancels=cancels)

    fees = ctx.get('fees') or {}
    rate = max(0.07, number(fees.get('kalshi_taker_rate'), 0.07))
    limits = ctx.get('limits') or {}
    order_cap = max(0.0, number(limits.get('max_order_usd')))
    position_cap = max(0.0, number(limits.get('max_position_usd')))
    ticket_cap = min(params['notional_usd'], order_cap, position_cap)

    markets = {}
    terms = {}
    for market in ctx.get('markets') or []:
        ticker = str(market.get('market', ''))
        markets[ticker] = market
        quote = market_terms(market, now, params)
        if quote is not None:
            terms[ticker] = quote
    memory['eligible_markets'] = len(terms)

    held_markets = set()
    held_events = set()
    held_cost = 0.0
    for position in ctx.get('positions') or []:
        quantity = max(0.0, number(position.get('quantity')))
        if quantity <= 0.0:
            continue
        ticker = str(position.get('market', ''))
        held_markets.add(ticker)
        held_events.add(event_id(ticker))
        price = conservative_price(position.get('average_cost'))
        # Fee-inclusive again is deliberately conservative if average_cost already includes fees.
        held_cost += expense(quantity, price, rate)

    cancels = []
    buy_ids = []
    working_markets = set()
    working_events = set()
    reserved = 0.0
    unmanageable_order = False
    other_working_order = False

    for order in orders:
        quantity = max(0.0, number(order.get('quantity')) - number(order.get('filled')))
        if quantity <= 0.0:
            # Unknown quantities must not be treated as free capacity.
            if order.get('quantity') is None:
                unmanageable_order = True
                if order.get('side') == 'buy' and order.get('order_id'):
                    cancels.append(order['order_id'])
            continue
        if order.get('side') != 'buy':
            other_working_order = True
            continue
        order_id = order.get('order_id')
        if not order_id:
            unmanageable_order = True
        else:
            buy_ids.append(order_id)
        ticker = str(order.get('market', ''))
        event = event_id(ticker)
        price = conservative_price(order.get('limit_price'))
        cost = expense(quantity, price, rate)
        reserved += cost
        submitted = stamp(order.get('submitted_at'))
        quote = terms.get(ticker)
        valid = (
            quote is not None
            and order.get('leg') == 'yes'
            and event not in held_events
            and event not in working_events
            and params['yes_bid_min'] <= price <= params['yes_bid_max']
            and submitted is not None
            and 0.0 <= now - submitted <= params['quote_ttl_minutes'] * 60.0
            and cost <= ticket_cap + 1e-9
            and abs(quantity - math.floor(quantity)) < 1e-9
        )
        if quote is not None and price >= quote[1]:
            valid = False
        if not valid and order_id:
            cancels.append(order_id)
        working_markets.add(ticker)
        working_events.add(event)

    occupied_markets = held_markets | working_markets
    if (held_cost + reserved > params['portfolio_budget_usd'] + 1e-9
            or len(occupied_markets) > params['max_positions']):
        cancels.extend(buy_ids)
    cancels = list(dict.fromkeys(cancels))
    if cancels:
        return result('Cancel stale, duplicate or over-budget entries; replacements wait until the book confirms removal.', cancels=cancels)
    if unmanageable_order or other_working_order:
        return result('An existing order prevents safe entry accounting; no new exposure is requested.')
    if len(occupied_markets) >= params['max_positions']:
        return result('All three exposure slots are occupied; preserve valid bids and hold filled contracts to settlement.')

    free_cash = max(0.0, number(ctx.get('cash')) - reserved - 0.01)
    portfolio_room = max(0.0, params['portfolio_budget_usd'] - held_cost - reserved)
    risk = ctx.get('event_risk') or {}
    remaining = risk.get('remaining_by_market_usd')
    blocked_events = held_events | working_events
    candidates = sorted(
        terms,
        key=lambda ticker: (
            -max(0.0, number(markets[ticker].get('volume_24h'))),
            terms[ticker][1] - terms[ticker][0],
            ticker,
        ),
    )
    budget_skips = 0
    for ticker in candidates:
        if event_id(ticker) in blocked_events:
            continue
        headroom = ticket_cap
        if isinstance(remaining, dict):
            # Supplied headroom already includes peer holdings and outstanding buys.
            headroom = max(0.0, number(remaining.get(ticker), 0.0))
        budget = min(ticket_cap, free_cash, portfolio_room, headroom)
        price = terms[ticker][2]
        quantity = max(0, math.floor(budget / price))
        while quantity > 0 and expense(quantity, price, rate) > budget:
            quantity -= 1
        if quantity <= 0 or quantity * price < 1.0:
            budget_skips += 1
            continue
        memory['budget_skips'] = budget_skips
        intent = {
            'market': ticker,
            'leg': 'yes',
            'side': 'buy',
            'quantity': quantity,
            'type': 'limit',
            'limit_price': price,
            'post_only': True,
            'reason': 'Test an early-window CFB favourite with a passive bid, a full fee reserve and separate-game exposure.',
        }
        return result('An eligible early-window favourite fits the fee-inclusive budget; submit one passive entry without duplicating a game.', intents=[intent])

    memory['budget_skips'] = budget_skips
    return result('No unoccupied early-window favourite fits both the quote rules and available whole-contract capacity; do not force a trade.')

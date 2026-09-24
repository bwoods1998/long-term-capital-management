# Corrected child of hilibrand-lc04657; family crypto-strikes-lab-955dae.
# Preserve the parent's NO-favourite maker selection and settlement holding.
# Budget all strikes and both legs of an event together before proposing buys.
from datetime import datetime, timezone

NEEDS = {'venue': 'kalshi',
 'horizon': 'hour',
 'style': 'favorites-no',
 'series': ['KXBTCD', 'KXETHD'],
 'max_hours_to_close': 12,
 'wake_minutes': 10}
PARAMS = {'bid_max': 0.97,
 'bid_min': 0.9,
 'max_hours': 6.0,
 'max_open': 4,
 'max_spread': 0.03,
 'min_hours': 0.25,
 'min_volume_24h': 2000,
 'notional_usd': 10.97298,
 'requote_minutes': 30}
LEG = 'no'
EPS = 1e-9
MAX_MARKET_SHARE = 0.30
MAX_EVENT_SHARE = 0.25


def _num(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float('inf') else default


def _when(text):
    try:
        clean = str(text).strip()
        if clean[-1:] in 'Zz':
            clean = clean[:-1] + '+00:00'
        moment = datetime.fromisoformat(clean)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _touch(market):
    yes_bid = _num(market.get('yes_bid'))
    yes_ask = _num(market.get('yes_ask'))
    if yes_bid is None or yes_ask is None or not 0.0 < yes_bid < yes_ask < 1.0:
        return None
    return round(1.0 - yes_ask, 4), round(1.0 - yes_bid, 4)


def _event(ticker):
    return '-'.join(str(ticker).split('-')[:2])


def _cost_price(value):
    price = _num(value)
    return price if price is not None and 0.0 <= price <= 1.0 else 1.0


def decide(ctx):
    p = {**PARAMS, **(ctx.get('params') or {})}
    knob = lambda name: _num(p.get(name), float(PARAMS[name]))
    now = _when(ctx.get('now'))
    markets = [m for m in ctx.get('markets') or [] if isinstance(m, dict) and m.get('market')]
    positions = [x for x in ctx.get('positions') or [] if isinstance(x, dict) and _num(x.get('quantity'), 0.0) > 0]
    orders = [o for o in ctx.get('open_orders') or [] if isinstance(o, dict)]
    busy = {str(x.get('market')) for x in positions} | {str(o.get('market')) for o in orders}

    # Cancellation requests do not release a slot or budget in this decision.
    cancels = []
    for order in orders:
        sent = _when(order.get('submitted_at'))
        if order.get('side') == 'buy' and order.get('order_id') and sent is not None and now is not None:
            if (now - sent).total_seconds() / 60.0 > knob('requote_minutes'):
                cancels.append(str(order['order_id']))
    cancels = cancels[:20]

    found = []
    for market in markets:
        touch = _touch(market)
        hours = _num(market.get('hours_to_close'))
        volume = _num(market.get('volume_24h'), 0.0)
        if touch is None or hours is None:
            continue
        bid, ask = touch
        if not knob('bid_min') - EPS <= bid <= knob('bid_max') + EPS or ask - bid > knob('max_spread') + EPS:
            continue
        if not knob('min_hours') <= hours <= knob('max_hours') or volume < knob('min_volume_24h'):
            continue
        found.append((-volume, str(market['market']), bid, ask, hours))
    found.sort()

    # Both legs and every strike consume the same event budget. Outstanding
    # quantity excludes fills, which are already present in positions.
    event_used = {}
    for position in positions:
        event = _event(position.get('market'))
        cost = _num(position.get('quantity'), 0.0) * _cost_price(position.get('average_cost'))
        event_used[event] = event_used.get(event, 0.0) + cost
    reserved = 0.0
    for order in orders:
        if order.get('side') != 'buy':
            continue
        remaining = max(0.0, _num(order.get('quantity'), 0.0) - max(0.0, _num(order.get('filled'), 0.0)))
        cost = remaining * _cost_price(order.get('limit_price'))
        event = _event(order.get('market'))
        event_used[event] = event_used.get(event, 0.0) + cost
        reserved += cost

    limits = ctx.get('limits') or {}
    want = knob('notional_usd')
    free = max(0.0, _num(ctx.get('cash'), 0.0) - reserved) * 0.98
    per_market = min(want, _num(limits.get('max_order_usd'), want), _num(limits.get('max_position_usd'), want))
    equity = max(0.0, _num(ctx.get('equity'), 0.0))
    per_market = min(per_market, MAX_MARKET_SHARE * equity)
    event_cap = MAX_EVENT_SHARE * equity
    market_room = (ctx.get('event_risk') or {}).get('remaining_by_market_usd') or {}
    slots = min(int(knob('max_open')) - len(busy), 8)

    intents = []
    for minus_volume, ticker, bid, ask, hours in found:
        if len(intents) >= slots:
            break
        if ticker in busy:
            continue
        event = _event(ticker)
        event_room = max(0.0, event_cap - event_used.get(event, 0.0))
        budget = max(0.0, min(per_market, free, event_room))
        if ticker in market_room:
            budget = min(budget, max(0.0, _num(market_room[ticker], 0.0)))
        quantity = int(budget / bid)
        # Never round an entry up through a capacity ceiling.
        while quantity > 0 and quantity * bid > budget:
            quantity -= 1
        if quantity < 1 or quantity * bid < 1.0:
            continue
        cost = quantity * bid
        free -= cost
        event_used[event] = event_used.get(event, 0.0) + cost
        busy.add(ticker)
        intents.append({
            'market': ticker, 'leg': LEG, 'side': 'buy', 'quantity': quantity, 'type': 'limit',
            'limit_price': bid, 'post_only': True,
            'reason': (f'Resting a post-only {LEG.upper()} bid for {quantity} at {bid:.2f} on {ticker}: '
                       f'the favourite is in the {knob("bid_min"):.2f}-{knob("bid_max"):.2f} band '
                       f'(bid {bid:.2f}, ask {ask:.2f}), {hours:.1f}h to close, '
                       f'{-minus_volume:.0f} contracts traded today. Held to settlement; '
                       f'event commitments including this bid are ${event_used[event]:.4f} '
                       f'of a ${event_cap:.4f} allowance.'),
        })

    thought = (f'Saw {len(markets)} open markets, {len(found)} qualifying NO favourites. '
               f'Rested {len(intents)} bids within shared event budgets and requested {len(cancels)} stale cancellations.')
    return {'intents': intents, 'cancels': cancels, 'thought': thought, 'memory': {}}

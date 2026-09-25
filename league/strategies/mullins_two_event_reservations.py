# Corrected child of mullins-2, family weather-favorites.
# Preserve favourite-NO maker entries and settlement exits; reserve event risk
# across holdings, working buys and this decision's new bids.
from datetime import datetime, timezone
from decimal import Decimal

NEEDS = {'venue': 'kalshi',
 'horizon': 'day',
 'style': 'favorites-no',
 'series': ['KXRAIN',
            'KXHIGHLAX',
            'KXHIGHMIA',
            'KXHIGHNY',
            'KXLOWTNYC',
            'KXHIGHTATL',
            'KXHIGHCHI',
            'KXHIGHAUS',
            'KXRAINDNYC',
            'KXHIGHTPHX',
            'KXHIGHDEN',
            'KXRAINWKND'],
 'max_hours_to_close': 30,
 'wake_minutes': 60}
PARAMS = {'bid_min': 0.9,
 'bid_max': 0.97,
 'max_spread': 0.03,
 'min_hours': 1.0,
 'max_hours': 30.0,
 'min_volume_24h': 1000,
 'notional_usd': 10.0,
 'max_open': 6,
 'requote_minutes': 180}
LEG = 'no'
EPS = 1e-9
MAX_MARKET_SHARE = 0.30


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


def _decimal(value):
    return Decimal(str(value))


def decide(ctx):
    p = {**PARAMS, **(ctx.get('params') or {})}
    knob = lambda name: _num(p.get(name), float(PARAMS[name]))
    now = _when(ctx.get('now'))
    markets = [m for m in ctx.get('markets') or [] if isinstance(m, dict) and m.get('market')]
    positions = [x for x in ctx.get('positions') or [] if isinstance(x, dict) and (_num(x.get('quantity'), 0.0) or 0.0) > 0]
    orders = [o for o in ctx.get('open_orders') or [] if isinstance(o, dict)]
    busy = {str(x.get('market')) for x in positions} | {str(o.get('market')) for o in orders}

    # Pending cancellation releases neither its slot nor event headroom.
    cancels = []
    for order in orders:
        sent = _when(order.get('submitted_at'))
        if order.get('side') == 'buy' and order.get('order_id') and sent is not None and now is not None:
            if (now - sent).total_seconds() / 60.0 > knob('requote_minutes'):
                cancels.append(str(order['order_id']))

    zero = Decimal('0')
    equity = _num(ctx.get('equity'))
    event_cap = _decimal(max(0.0, equity or 0.0)) * Decimal('0.25')
    committed = {}
    blocked = set()
    for position in positions:
        event = _event(position.get('market'))
        cost = _num(position.get('average_cost'))
        if cost is None or cost < 0:
            blocked.add(event)
            continue
        amount = _decimal(_num(position.get('quantity'), 0.0)) * _decimal(cost)
        committed[event] = committed.get(event, zero) + amount
    for order in orders:
        if order.get('side') != 'buy':
            continue
        event = _event(order.get('market'))
        quantity = _num(order.get('quantity'))
        filled = _num(order.get('filled', 0))
        price = _num(order.get('limit_price'))
        if quantity is None or filled is None or quantity < 0 or filled < 0:
            blocked.add(event)
            continue
        remaining = max(zero, _decimal(quantity) - _decimal(filled))
        if remaining == zero:
            continue
        if price is None or price <= 0:
            blocked.add(event)
            continue
        committed[event] = committed.get(event, zero) + remaining * _decimal(price)

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

    limits = ctx.get('limits') or {}
    want = knob('notional_usd')
    reserved = sum((_num(o.get('quantity'), 0.0) or 0.0) * (_num(o.get('limit_price'), 0.0) or 0.0) for o in orders if o.get('side') == 'buy')
    free = ((_num(ctx.get('cash'), 0.0) or 0.0) - reserved) * 0.98
    per_market = min(want, _num(limits.get('max_order_usd'), want), _num(limits.get('max_position_usd'), want))
    if equity is not None and equity > 0:
        per_market = min(per_market, MAX_MARKET_SHARE * equity)
    slots = min(int(knob('max_open')) - len(busy), 8)

    intents = []
    for minus_volume, ticker, bid, ask, hours in found:
        if len(intents) >= slots:
            break
        event = _event(ticker)
        if ticker in busy or event in blocked:
            continue
        headroom = max(zero, event_cap - committed.get(event, zero))
        quantity = min(int(min(per_market, free) / bid + EPS), int(headroom / _decimal(bid)))
        if quantity < 1 or quantity * bid < 1.0:
            continue
        committed[event] = committed.get(event, zero) + Decimal(quantity) * _decimal(bid)
        free -= quantity * bid
        busy.add(ticker)
        intents.append({
            'market': ticker, 'leg': LEG, 'side': 'buy', 'quantity': quantity, 'type': 'limit',
            'limit_price': bid, 'post_only': True,
            'reason': (f'Resting a post-only {LEG.upper()} bid for {quantity} at {bid:.2f} on {ticker}: '
                       f'the favourite sits in the {knob("bid_min"):.2f}-{knob("bid_max"):.2f} band '
                       f'({LEG.upper()} bid {bid:.2f}, ask {ask:.2f}), {hours:.1f}h to close, '
                       f'{-minus_volume:.0f} contracts traded today. Sized within remaining event headroom; held to settlement.'),
        })

    thought = (f'Saw {len(markets)} open markets, {len(found)} favourites in the band with a tight spread and enough volume. '
               f'Rested {len(intents)} new {LEG.upper()} bids within event headroom and requested {len(cancels)} stale cancellations.')
    return {'intents': intents, 'cancels': cancels[:20], 'thought': thought, 'memory': {}}

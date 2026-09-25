# Corrected child of hilibrand-lc04657; family crypto-strikes-lab-955dae.
# Preserve NO-favourite maker entries and settlement exits; share entry
# capacity across all strikes and both legs of each Kalshi event.
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
    yes_bid, yes_ask = _num(market.get('yes_bid')), _num(market.get('yes_ask'))
    if yes_bid is None or yes_ask is None or not 0.0 < yes_bid < yes_ask < 1.0:
        return None
    return round(1.0 - yes_ask, 4), round(1.0 - yes_bid, 4)


def _event(ticker):
    return '-'.join(str(ticker).split('-')[:2])


def _commitment_price(value):
    price = _num(value)
    # An unknown commitment must not be mistaken for free capacity.
    return price if price is not None and 0.0 <= price <= 1.0 else 1.0


def decide(ctx):
    p = {**PARAMS, **(ctx.get('params') or {})}
    knob = lambda name: _num(p.get(name), float(PARAMS[name]))
    now = _when(ctx.get('now'))
    markets = [m for m in ctx.get('markets') or [] if isinstance(m, dict) and m.get('market')]
    positions = [x for x in ctx.get('positions') or [] if isinstance(x, dict) and (_num(x.get('quantity'), 0.0) or 0.0) > 0]
    orders = [o for o in ctx.get('open_orders') or [] if isinstance(o, dict)]
    busy = {str(x.get('market')) for x in positions} | {str(o.get('market')) for o in orders}

    # Requested cancellations still reserve capacity until a later snapshot
    # confirms they are gone. Pending sells do not release holding cost.
    cancels = []
    for order in orders:
        sent = _when(order.get('submitted_at'))
        if order.get('side') == 'buy' and order.get('order_id') and sent is not None and now is not None:
            if (now - sent).total_seconds() / 60.0 > knob('requote_minutes'):
                if len(cancels) < 20:
                    cancels.append(str(order['order_id']))

    event_used = {}
    unknown_commitment = False
    for position in positions:
        if not position.get('market'):
            unknown_commitment = True
            continue
        event = _event(position['market'])
        cost = _num(position.get('quantity'), 0.0) * _commitment_price(position.get('average_cost'))
        event_used[event] = event_used.get(event, 0.0) + cost

    reserved = 0.0
    for order in orders:
        if order.get('side') != 'buy':
            continue
        remaining = max(0.0, _num(order.get('quantity'), 0.0) - max(0.0, _num(order.get('filled'), 0.0)))
        cost = remaining * _commitment_price(order.get('limit_price'))
        reserved += cost
        if not order.get('market'):
            unknown_commitment = True
            continue
        event = _event(order['market'])
        event_used[event] = event_used.get(event, 0.0) + cost

    found = []
    for market in markets:
        touch = _touch(market)
        hours, volume = _num(market.get('hours_to_close')), _num(market.get('volume_24h'), 0.0)
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
    free = max(0.0, _num(ctx.get('cash'), 0.0) - reserved) * 0.98
    per_market = min(want, _num(limits.get('max_order_usd'), want), _num(limits.get('max_position_usd'), want))
    event_cap = MAX_EVENT_SHARE * max(0.0, _num(ctx.get('equity'), 0.0))
    slots = min(int(knob('max_open')) - len(busy), 8)
    if unknown_commitment:
        slots = 0

    intents = []
    for minus_volume, ticker, bid, ask, hours in found:
        if len(intents) >= slots:
            break
        if ticker in busy:
            continue
        event = _event(ticker)
        headroom = max(0.0, event_cap - event_used.get(event, 0.0) - EPS)
        quantity = int(max(0.0, min(per_market, free, headroom)) / bid)
        if quantity < 1 or quantity * bid < 1.0:
            continue
        cost = quantity * bid
        free -= cost
        # Reserve before considering another strike from this same event.
        event_used[event] = event_used.get(event, 0.0) + cost
        busy.add(ticker)
        intents.append({
            'market': ticker, 'leg': LEG, 'side': 'buy', 'quantity': quantity, 'type': 'limit',
            'limit_price': bid, 'post_only': True,
            'reason': (f'Resting a post-only {LEG.upper()} bid for {quantity} at {bid:.2f} on {ticker}: '
                       f'favourite in the {knob("bid_min"):.2f}-{knob("bid_max"):.2f} band '
                       f'(bid {bid:.2f}, ask {ask:.2f}), {hours:.1f}h to close, '
                       f'{-minus_volume:.0f} contracts traded today. Held to settlement; '
                       f'event commitments including this bid are ${event_used[event]:.4f} '
                       f'within the ${event_cap:.4f} event cap.'),
        })

    thought = (f'Saw {len(markets)} open markets, {len(found)} qualifying favourites. '
               f'Rested {len(intents)} NO bids within cumulative event budgets and requested '
               f'{len(cancels)} stale bid cancellations.')
    if unknown_commitment:
        thought += ' Entries wait because an existing commitment has no market identity.'
    return {'intents': intents, 'cancels': cancels, 'thought': thought, 'memory': {}}

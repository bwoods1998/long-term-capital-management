# Child of hawkins-3, family prices-favorites. New rung-0 candidate.
# Preserve the WTI/diesel maker strategy; gate buys on payout time as well as close time.
from datetime import datetime, timezone

NEEDS = {
    'venue': 'kalshi',
    'horizon': 'day',
    'style': 'favorites-daily-commodity',
    'series': ['KXWTI', 'KXDIESELD'],
    'max_hours_to_close': 40,
    'wake_minutes': 60,
}

PARAMS = {
    'bid_min': 0.90,
    'bid_max': 0.99,
    'max_spread': 0.03,
    'min_hours': 1.0,
    'max_hours': 40.0,
    'min_volume_24h': 500,
    'notional_usd': 10.0,
    'max_open': 6,
    'requote_minutes': 180,
}

EPS = 1e-9


def num(value, default=None):
    try:
        x = float(value)
        if x != x or abs(x) == float('inf'):
            return default
        return x
    except (TypeError, ValueError):
        return default


def resolves_in_horizon(row):
    # The daily payout ceiling is a rule, not a mutable strategy parameter.
    # Missing payout timing is not permission to substitute trading-close time.
    if not isinstance(row, dict):
        return False
    value = row.get('hours_to_resolve')
    if isinstance(value, bool):
        return False
    hours = num(value)
    return hours is not None and 0.0 <= hours <= 48.0


def when(value):
    try:
        text = str(value).strip()
        if text[-1:] in ('Z', 'z'):
            text = text[:-1] + '+00:00'
        result = datetime.fromisoformat(text)
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def touch(row):
    if not isinstance(row, dict):
        return None
    bid = num(row.get('yes_bid'))
    ask = num(row.get('yes_ask'))
    if bid is None or ask is None or not (0.0 < bid < ask < 1.0):
        return None
    return round(bid, 4), round(ask, 4)


def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get('params') or {})

    def knob(name):
        return num(p.get(name), PARAMS[name])

    now = when(ctx.get('now'))
    markets = [x for x in (ctx.get('markets') or [])
               if isinstance(x, dict) and x.get('market')]
    positions = [x for x in (ctx.get('positions') or [])
                 if isinstance(x, dict) and num(x.get('quantity'), 0.0) > 0.0]
    orders = [x for x in (ctx.get('open_orders') or []) if isinstance(x, dict)]
    busy = {str(x.get('market')) for x in positions}
    busy.update(str(x.get('market')) for x in orders)
    rows = {str(x.get('market')): x for x in markets}

    cancels = []
    for order in orders:
        if order.get('side') != 'buy' or not order.get('order_id'):
            continue
        row = rows.get(str(order.get('market')))
        q = touch(row)
        limit = num(order.get('limit_price'))
        sent = when(order.get('submitted_at'))
        aged = bool(sent and now and (now - sent).total_seconds() / 60.0 > knob('requote_minutes'))
        gone = row is None or q is None
        invalid = False
        if row is not None and q is not None:
            bid, ask = q
            hours = num(row.get('hours_to_close'))
            volume = num(row.get('volume_24h'), 0.0)
            invalid = (
                (limit is not None and limit > bid + EPS) or
                not (knob('bid_min') - EPS <= bid <= knob('bid_max') + EPS) or
                ask - bid > knob('max_spread') + EPS or
                hours is None or
                not (knob('min_hours') <= hours <= knob('max_hours')) or
                volume < knob('min_volume_24h')
            )
        if aged or gone or invalid or not resolves_in_horizon(row):
            cancels.append(str(order['order_id']))

    candidates = []
    for row in markets:
        if not resolves_in_horizon(row):
            continue
        q = touch(row)
        hours = num(row.get('hours_to_close'))
        volume = num(row.get('volume_24h'), 0.0)
        if q is None or hours is None:
            continue
        bid, ask = q
        if not (knob('bid_min') - EPS <= bid <= knob('bid_max') + EPS):
            continue
        if ask - bid > knob('max_spread') + EPS:
            continue
        if not (knob('min_hours') <= hours <= knob('max_hours')):
            continue
        if volume < knob('min_volume_24h'):
            continue
        candidates.append((-volume, str(row['market']), bid, ask, hours))
    candidates.sort()

    limits = ctx.get('limits') or {}
    cash = num(ctx.get('cash'), 0.0)
    reserved = 0.0
    for order in orders:
        if order.get('side') == 'buy' and str(order.get('order_id')) not in cancels:
            reserved += num(order.get('quantity'), 0.0) * num(order.get('limit_price'), 0.0)
    free = max(0.0, (cash - reserved) * 0.98)
    per_market = min(knob('notional_usd'),
                     num(limits.get('max_order_usd'), knob('notional_usd')),
                     num(limits.get('max_position_usd'), knob('notional_usd')))
    equity = num(ctx.get('equity'))
    if equity is not None and equity > 0.0:
        per_market = min(per_market, 0.30 * equity)
    slots = max(0, min(8, int(knob('max_open')) - len(busy)))

    intents = []
    for unused, market, bid, ask, hours in candidates:
        if len(intents) >= slots or market in busy:
            continue
        quantity = int(min(per_market, free) / bid + EPS)
        if quantity < 1 or quantity * bid < 1.0:
            continue
        free -= quantity * bid
        intents.append({
            'market': market,
            'leg': 'yes',
            'side': 'buy',
            'quantity': quantity,
            'type': 'limit',
            'limit_price': bid,
            'post_only': True,
            'reason': 'Post-only YES bid on a liquid WTI/diesel favourite within the tested 0.90-0.99 band, with tight spread and settlement horizon.'
        })

    return {
        'intents': intents,
        'cancels': cancels,
        'thought': 'Rechecked existing quotes, cancelled stale or invalid rests, and ranked eligible favourites by volume; buys require known payout timing within 48 hours.',
        'memory': {}
    }

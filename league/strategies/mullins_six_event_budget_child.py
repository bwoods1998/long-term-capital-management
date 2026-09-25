from datetime import datetime, timezone
from decimal import Decimal

# Corrected child of mullins-6; family weather-favorites.
NEEDS = {'venue': 'kalshi', 'horizon': 'day', 'style': 'favorites-no', 'series': ['KXRAIN','KXHIGHLAX','KXHIGHMIA','KXHIGHNY','KXLOWTNYC','KXHIGHTATL','KXHIGHCHI','KXHIGHAUS','KXRAINDNYC','KXHIGHTPHX','KXHIGHDEN','KXRAINWKND'], 'max_hours_to_close': 30, 'wake_minutes': 60}
PARAMS = {'bid_min': 0.9, 'bid_max': 0.97, 'max_spread': 0.03, 'min_hours': 0.937403, 'max_hours': 30.0, 'min_volume_24h': 1000, 'notional_usd': 10.0, 'max_open': 6, 'requote_minutes': 180, 'skip_half_strike_bins': True}
LEG = 'no'
EPS = 1e-9
MAX_MARKET_SHARE = 0.30


def _num(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float('inf') else default


def _money(value, default=0.0):
    return Decimal(str(max(0.0, _num(value, default))))


def _event(ticker):
    return '-'.join(str(ticker).split('-')[:2])


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


def decide(ctx):
    p = {**PARAMS, **(ctx.get('params') or {})}
    def knob(name):
        return _num(p.get(name), float(PARAMS[name]))
    now = _when(ctx.get('now'))
    markets = [m for m in ctx.get('markets') or [] if isinstance(m, dict) and m.get('market')]
    positions = [x for x in ctx.get('positions') or [] if isinstance(x, dict) and (_num(x.get('quantity'), 0.0) or 0.0) > 0]
    orders = [o for o in ctx.get('open_orders') or [] if isinstance(o, dict)]
    busy = {str(x.get('market')) for x in positions} | {str(o.get('market')) for o in orders}
    cancels = []
    for order in orders:
        sent = _when(order.get('submitted_at'))
        if order.get('side') == 'buy' and order.get('order_id') and sent is not None and now is not None:
            if (now - sent).total_seconds() / 60.0 > knob('requote_minutes'):
                cancels.append(str(order['order_id']))
    cancels = cancels[:20]

    # Aggregate BOTH legs and every strike of the event. Reserve pending
    # cancels too: cancellation is not confirmed by asking for it.
    zero = Decimal('0')
    event_cap = _money(ctx.get('equity')) * Decimal('0.25')
    committed = {}
    for position in positions:
        event = _event(position.get('market'))
        cost = _money(position.get('quantity')) * _money(position.get('average_cost'), 1.0)
        committed[event] = committed.get(event, zero) + cost
    reserved = zero
    for order in orders:
        if order.get('side') != 'buy':
            continue
        remaining = max(zero, _money(order.get('quantity')) - _money(order.get('filled')))
        cost = remaining * _money(order.get('limit_price'), 1.0)
        event = _event(order.get('market'))
        committed[event] = committed.get(event, zero) + cost
        reserved += cost

    found = []
    skipped_bins = 0
    for market in markets:
        touch = _touch(market)
        hours = _num(market.get('hours_to_close'))
        volume = _num(market.get('volume_24h'), 0.0)
        if touch is None or hours is None:
            continue
        strike = _num(market.get('strike'))
        if bool(p.get('skip_half_strike_bins', True)) and strike is not None and abs(strike - round(strike)) > 0.01:
            skipped_bins += 1
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
    free = max(zero, _money(ctx.get('cash')) - reserved) * Decimal('0.98')
    per_market = min(want, _num(limits.get('max_order_usd'), want), _num(limits.get('max_position_usd'), want))
    equity = _num(ctx.get('equity'))
    if equity is not None and equity > 0:
        per_market = min(per_market, MAX_MARKET_SHARE * equity)
    slots = min(int(knob('max_open')) - len(busy), 8)
    intents = []
    for minus_volume, ticker, bid, ask, hours in found:
        if len(intents) >= slots or ticker in busy:
            continue
        event = _event(ticker)
        headroom = max(zero, event_cap - committed.get(event, zero))
        price = _money(bid)
        quantity = int(min(_money(per_market), free, headroom) // price)
        cost = quantity * price
        if quantity < 1 or cost < Decimal('1'):
            continue
        free -= cost
        committed[event] = committed.get(event, zero) + cost
        busy.add(ticker)
        intents.append({'market': ticker, 'leg': LEG, 'side': 'buy', 'quantity': quantity, 'type': 'limit', 'limit_price': bid, 'post_only': True, 'reason': f'Resting post-only NO bid at {bid:.2f}; favourite in target band, integer strike or rain, {hours:.1f}h to close, within remaining event budget.'})
    return {'intents': intents, 'cancels': cancels, 'thought': f'Saw {len(markets)} markets, skipped {skipped_bins} bins, found {len(found)} eligible favourites with max entry horizon {knob("max_hours"):.0f}h, rested {len(intents)} event-budgeted bids.', 'memory': {}}

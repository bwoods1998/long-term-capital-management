from datetime import datetime
from decimal import Decimal, ROUND_CEILING

NEEDS = {
    'venue': 'kalshi', 'horizon': 'day', 'style': 'lottery-demand-no',
    'series': ['KXRAIN', 'KXHIGHMIA', 'KXHIGHLAX', 'KXHIGHNY', 'KXHIGHTATL', 'KXHIGHTDAL', 'KXHIGHCHI', 'KXHIGHTDC', 'KXHIGHAUS', 'KXHIGHTMIN', 'KXHIGHTOKC', 'KXHIGHPHIL'],
    'max_hours_to_close': 48, 'wake_minutes': 30,
    'parameter_rules': {
        'bounds': {'entry_floor': [0.90, 0.94], 'entry_ceiling': [0.94, 0.97], 'spread_cap': [0.02, 0.06], 'min_close_hours': [0.5, 2.0], 'max_close_hours': [12.0, 36.0], 'order_minutes': [60, 180], 'notional_usd': [25.0, 25.0]},
        'ordered': [['entry_floor', 'entry_ceiling'], ['min_close_hours', 'max_close_hours']],
        'frozen': ['notional_usd']
    }
}
PARAMS = {
    'entry_ceiling': 0.96,
    'entry_floor': 0.9,
    'max_close_hours': 23.800536,
    'min_close_hours': 0.5,
    'notional_usd': 25.0,
    'order_minutes': 90,
    'spread_cap': 0.04
}

def money(value):
    return Decimal(str(value))

def cash_cost(quantity, price, rate):
    fee = (quantity * rate * price * (1 - price)).quantize(
        Decimal('0.0001'), rounding=ROUND_CEILING)
    return quantity * price + fee

def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()

def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get('params', {}))
    now = stamp(ctx['now'])
    rows = {m['market']: m for m in ctx.get('markets', []) if m.get('series') in NEEDS['series']}
    orders = ctx.get('open_orders', [])
    cancels = []
    # Series maker fees are not supplied here. Reserve the higher taker fee.
    rate = max(Decimal('0.07'), money(ctx.get('fees', {}).get('kalshi_taker_rate', 0.07)))
    reserved = Decimal('0')
    occupied = {x.get('market') for x in ctx.get('positions', []) if x.get('quantity', 0) > 0}
    for o in orders:
        ticker = o.get('market')
        occupied.add(ticker)
        if o.get('side') == 'buy':
            remaining = max(Decimal('0'), money(o.get('quantity', 0)) - money(o.get('filled', 0)))
            reserved += cash_cost(remaining, money(o.get('limit_price', 0)), rate)
        m = rows.get(ticker)
        age = (now - stamp(o.get('submitted_at', ctx['now']))) / 60.0
        if age >= p['order_minutes'] or m is None or m.get('hours_to_close', 0) <= p['min_close_hours']:
            cancels.append(o['order_id'])
    choices = []
    for ticker, m in rows.items():
        if ticker in occupied:
            continue
        hc = m.get('hours_to_close')
        hr = m.get('hours_to_resolve')
        if hc is None or hr is None or not (p['min_close_hours'] <= hc <= p['max_close_hours'] and 0 < hr <= 48):
            continue
        yb, ya = m.get('yes_bid'), m.get('yes_ask')
        if yb is None or ya is None or not (0 <= yb <= ya <= 1):
            continue
        bid, ask = round(1 - ya, 2), round(1 - yb, 2)
        if p['entry_floor'] <= bid <= p['entry_ceiling'] and 0 < ask - bid <= p['spread_cap'] + 0.000001:
            choices.append((ask - bid, ticker, bid))
    intents = []
    free = max(Decimal('0'), money(ctx.get('cash', 0)) - reserved)
    limits = ctx.get('limits', {})
    risk = ctx.get('event_risk', {}).get('remaining_by_market_usd')
    for score, ticker, price in sorted(choices, reverse=True):
        cap = min(money(p['notional_usd']), free, money(limits.get('max_order_usd', 75.0)), money(limits.get('max_position_usd', 100.0)))
        if risk is not None:
            cap = min(cap, max(Decimal('0'), money(risk.get(ticker, 0.0))))
        px = money(price)
        unit_cost = px + rate * px * (1 - px)
        quantity = min(int(max(Decimal('0'), cap) / px), int(free / unit_cost))
        # The unit estimate omits upward rounding of the aggregate fee.
        if quantity > 0 and cash_cost(quantity, px, rate) > free:
            quantity -= 1
        if quantity < 1:
            continue
        intents.append({'market': ticker, 'leg': 'no', 'side': 'buy', 'quantity': quantity, 'type': 'limit', 'limit_price': price, 'post_only': True, 'reason': 'Supply the NO side to cheap-YES lottery demand; reserve cash including fees and hold to settlement.'})
        break
    return {'intents': intents, 'cancels': cancels[:20], 'thought': 'Only passive expensive-NO entries qualify, sized with fee-inclusive cash reservations. No weather forecast, quote timestamp, or assumed settlement time is used.', 'memory': {}}

# Corrected child of haghani-56; family crypto-alts-reversion.
# Keep deep-dip signals and exits; size entries at current ask value.
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING

NEEDS = {
    'venue': 'alpaca', 'horizon': 'hour', 'style': 'deep-dip-maker',
    'symbols': ['SOL/USD', 'XRP/USD', 'LTC/USD', 'LINK/USD', 'AVAX/USD'],
    'bars': {'timeframe': '15Min', 'limit': 64}, 'wake_minutes': 15,
    'parameter_rules': {'bounds': {
        'entry_dip_pct': [0.5, 5.0], 'take_profit_pct': [0.5, 5.0],
        'stop_pct': [0.5, 8.0], 'notional_usd': [10.0, 75.0],
        'max_hold_hours': [1.0, 48.0], 'replace_pct': [0.1, 2.0],
        'min_price': [1.0, 10.0]
    }}
}
PARAMS = {
    'entry_dip_pct': 1.5, 'take_profit_pct': 2.0, 'stop_pct': 2.5,
    'notional_usd': 25.0, 'max_hold_hours': 24.0,
    'replace_pct': 0.5, 'min_price': 1.0
}

def num(x, default=0.0):
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except (TypeError, ValueError):
        return default

def when(s):
    try:
        t = str(s).strip()
        if t.endswith(('Z', 'z')):
            t = t[:-1] + '+00:00'
        d = datetime.fromisoformat(t)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None

def age_hours(a, b):
    x, y = when(a), when(b)
    return None if x is None or y is None else (y-x).total_seconds()/3600.0

def grid(price, inc, side):
    step = num(inc)
    if step <= 0:
        return price
    d = Decimal(str(price)) / Decimal(str(step))
    rounding = ROUND_FLOOR if side == 'buy' else ROUND_CEILING
    return float(d.to_integral_value(rounding=rounding) * Decimal(str(step)))

def remaining(order):
    return max(0.0, num(order.get('quantity')) - num(order.get('filled')))

def decide(ctx):
    p = {**PARAMS, **(ctx.get('params') or {})}
    entry = num(p['entry_dip_pct'], 1.5) / 100.0
    take = num(p['take_profit_pct'], 2.0) / 100.0
    stop = num(p['stop_pct'], 2.5) / 100.0
    notional = num(p['notional_usd'], 25.0)
    max_hold = num(p['max_hold_hours'], 24.0)
    replace_pct = num(p['replace_pct'], 0.5)
    min_price = num(p['min_price'], 1.0)
    quotes = ctx.get('quotes') or {}
    rules = ctx.get('venue_rules') or {}
    positions = {x.get('symbol'): x for x in ctx.get('positions') or []
                 if isinstance(x, dict) and num(x.get('quantity')) > 0}
    orders = [x for x in ctx.get('open_orders') or [] if isinstance(x, dict) and x.get('order_id')]
    intents, cancels, notes = [], [], []
    limits = ctx.get('limits') or {}
    position_budget = max(0.0, min(num(limits.get('max_position_usd')),
                                   num(ctx.get('equity')) * 0.5)) * 0.98
    order_budget = max(0.0, num(limits.get('max_order_usd')))
    fee_rate = max(0.0025, num((ctx.get('fees') or {}).get('crypto_taker'), 0.0025))
    reserved = 0.0
    for o in orders:
        if o.get('side') == 'buy':
            quote = quotes.get(o.get('symbol')) or {}
            value_price = max(num(o.get('limit_price')), num(quote.get('ask')), num(quote.get('bid')))
            reserved += remaining(o) * value_price * (1.0 + fee_rate)
    # Do not spend cancellation proceeds until a later snapshot confirms them.
    free = max(0.0, num(ctx.get('cash')) - reserved) * 0.98
    for symbol in NEEDS['symbols']:
        own = [o for o in orders if o.get('symbol') == symbol]
        buys = [o for o in own if o.get('side') == 'buy']
        sells = [o for o in own if o.get('side') == 'sell']
        pos = positions.get(symbol)
        quote = quotes.get(symbol) or {}
        bid = num(quote.get('bid'))
        ask = num(quote.get('ask'))
        increment = (rules.get(symbol) or {}).get('price_increment')
        if pos:
            for o in buys:
                if o['order_id'] not in cancels: cancels.append(o['order_id'])
            cost = num(pos.get('average_cost'))
            if cost <= 0 or bid <= 0:
                notes.append(symbol + ': holding; missing cost or bid')
                continue
            age = age_hours(pos.get('opened_at'), ctx.get('now'))
            if bid <= cost * (1.0-stop) or (age is not None and age >= max_hold):
                for o in sells:
                    if o['order_id'] not in cancels: cancels.append(o['order_id'])
                why = 'stop threshold' if bid <= cost * (1.0-stop) else 'holding-time limit'
                intents.append({'symbol': symbol, 'side': 'sell', 'quantity': pos['quantity'],
                                'type': 'market', 'reason': 'Exit the held position at the bid after the ' + why + '.'})
                notes.append(symbol + ': market exit (' + why + ')')
                continue
            target = grid(cost * (1.0+take), increment, 'sell')
            stale = [o for o in sells if target <= 0 or abs(num(o.get('limit_price'))/target-1.0)*100.0 > replace_pct]
            stale += sells[1:]
            for o in stale:
                if o['order_id'] not in cancels: cancels.append(o['order_id'])
            if not sells:
                intents.append({'symbol': symbol, 'side': 'sell', 'quantity': pos['quantity'],
                                'type': 'limit', 'limit_price': target,
                                'reason': 'Maker take-profit at ' + str(take*100.0) + '% above cost; close the dip trade.'})
            notes.append(symbol + ': holding for maker take-profit')
            continue
        for o in sells:
            if o['order_id'] not in cancels: cancels.append(o['order_id'])
        if bid < min_price or bid <= 0 or ask < bid or ask <= 0:
            for o in buys:
                if o['order_id'] not in cancels: cancels.append(o['order_id'])
            notes.append(symbol + ': excluded by minimum-price guard or unavailable two-sided quote')
            continue
        target = grid(bid * (1.0-entry), increment, 'buy')
        committed = sum(remaining(o) * max(ask, num(o.get('limit_price'))) for o in buys)
        if committed > position_budget:
            for o in buys:
                if o['order_id'] not in cancels: cancels.append(o['order_id'])
            notes.append(symbol + ': cancelling bids above the current equity-valued position budget')
            continue
        stale = [o for o in buys if target <= 0 or abs(num(o.get('limit_price'))/target-1.0)*100.0 > replace_pct]
        stale += buys[1:]
        for o in stale:
            if o['order_id'] not in cancels: cancels.append(o['order_id'])
        if buys:
            notes.append(symbol + ': existing dip bid')
            continue
        if bid <= 0 or target <= 0 or target >= bid:
            continue
        valuation = max(ask, target)
        budget = max(0.0, min(notional, order_budget, position_budget, free / (1.0 + fee_rate)))
        quantity = float((Decimal(str(budget)) / Decimal(str(valuation))).quantize(
            Decimal('0.000000001'), rounding=ROUND_FLOOR))
        dollars = quantity * target
        min_order = max(10.0, num((rules.get(symbol) or {}).get('min_order_usd'), 10.0))
        if quantity <= 0 or dollars < min_order:
            notes.append(symbol + ': below minimum order after exposure and cash sizing')
            continue
        free = max(0.0, free - quantity * valuation * (1.0 + fee_rate))
        intents.append({'symbol': symbol, 'side': 'buy', 'quantity': quantity,
                        'type': 'limit', 'limit_price': target, 'post_only': True,
                        'reason': 'Rest a post-only maker bid ' + str(entry*100.0) + '% below the current bid for a deep-dip reversion entry, sized at the ask below current equity and position limits with cash and fees reserved.'})
        notes.append(symbol + ': resting exposure-budgeted deep-dip maker bid')
    return {'intents': intents[:8], 'cancels': cancels[:20],
            'thought': 'Test deep-dip maker entries with a $1 tick-risk floor; take profit above cost and exit on a bounded stop or age. ' + '; '.join(notes),
            'memory': {}}

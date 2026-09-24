import math
from datetime import datetime

NEEDS = {
    'venue': 'kalshi',
    'horizon': 'hour',
    'style': 'btc-sol-standardized-probability-continuation',
    'series': ['KXBTC15M', 'KXSOL15M'],
    'max_hours_to_close': 1,
    'wake_minutes': 5,
    'parameter_rules': {'frozen': ['risk_fraction', 'min_standardized_move', 'continuation_weight', 'edge_buffer', 'max_spread']}
}
PARAMS = {
    'risk_fraction': 0.005,
    'min_standardized_move': 0.16,
    'continuation_weight': 0.5,
    'edge_buffer': 0.025,
    'max_spread': 0.04
}


def number(value, default=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (ValueError, TypeError):
        return default


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def probit(p):
    lo, hi = -6.0, 6.0
    for _ in range(36):
        mid = (lo + hi) * 0.5
        if cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def fee(quantity, price, rate):
    raw = rate * quantity * price * (1.0 - price)
    return math.ceil(raw * 10000.0 - 1e-10) / 10000.0


def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get('params') or {})
    now = timestamp(ctx.get('now'))
    old = ctx.get('memory') or {}
    orders = ctx.get('open_orders') or []
    cancels = [o['order_id'] for o in orders if o.get('order_id')][:20]
    if now is None:
        return {'intents': [], 'cancels': cancels, 'thought': 'Invalid clock; cancel and abstain.', 'memory': {}}

    equity = max(0.0, number(ctx.get('equity')))
    base = number(old.get('base_equity'))
    if base <= 0:
        base = equity
    halted = bool(old.get('halted', False))
    if base > 0 and equity <= base * 0.92:
        halted = True

    attempts = []
    for item in old.get('attempts', []):
        if isinstance(item, list) and len(item) == 2 and now - 3600 <= number(item[1]) <= now:
            attempts.append(item)
    attempts = attempts[-32:]

    rows = []
    for m in ctx.get('markets', []):
        series, ticker = m.get('series'), m.get('market')
        if series not in NEEDS['series'] or not ticker:
            continue
        end = timestamp(m.get('close_time'))
        bid, ask = number(m.get('yes_bid'), -1), number(m.get('yes_ask'), -1)
        resolve = number(m.get('hours_to_resolve'), -1)
        if end is None or not (0 < (end-now)/60 <= 15) or not (0 < resolve <= 12):
            continue
        if not (0 < bid < ask < 1) or ask-bid > p['max_spread'] or not (0.08 <= (bid+ask)/2 <= 0.92):
            continue
        minutes = (end-now)/60
        mid = (bid+ask)/2
        rows.append({'market': ticker, 'series': series, 'end': end, 't': now,
                     'minutes': minutes, 'bid': bid, 'ask': ask, 'mid': mid,
                     'x': probit(mid)*math.sqrt(minutes/15)})

    prior = {r.get('market'): r for r in old.get('anchors', []) if isinstance(r, dict)}
    memory = {'base_equity': base, 'halted': halted, 'anchors': rows, 'attempts': attempts}

    def result(thought, intents=None):
        return {'intents': intents or [], 'cancels': cancels, 'thought': thought, 'memory': memory}

    if orders:
        return result('Cancel surviving limits and wait for cancellation confirmation.')
    if any(number(pos.get('quantity')) > 0 for pos in ctx.get('positions', [])):
        return result('Hold current contract to settlement; do not stack exposure.')
    if halted or base <= 0 or equity <= 0:
        return result('Loss guard or nonpositive equity prevents new entries.')

    rate = max(0.0, number((ctx.get('fees') or {}).get('kalshi_taker_rate'), 0.07))
    price_floor = 0.30 if number(ctx.get('rung')) >= 2 else 0.15
    attempted = {item[0] for item in attempts}
    candidates = []
    for row in rows:
        if row['market'] in attempted:
            continue
        prev = prior.get(row['market'])
        if not prev:
            continue
        dt = now-number(prev.get('t'), -1)
        old_minutes = number(prev.get('minutes'), -1)
        if not (240 <= dt <= 360 and 2 <= row['minutes'] <= 7 and 7 <= old_minutes <= 12):
            continue
        if abs(row['end']-number(prev.get('end'))) > 2:
            continue
        move = row['x']-number(prev.get('x'))
        if abs(move) < p['min_standardized_move']:
            continue
        projected = cdf((row['x'] + p['continuation_weight']*move) / math.sqrt(row['minutes']/15))
        leg = 'yes' if move > 0 else 'no'
        score = projected if leg == 'yes' else 1-projected
        touch = row['ask'] if leg == 'yes' else 1-row['bid']
        taking_price = math.ceil(touch*100-1e-9)/100
        if not 0.15 <= taking_price <= 0.85:
            continue
        edge = score-taking_price-rate*taking_price*(1-taking_price)
        if edge < p['edge_buffer']:
            continue
        # Preserve the parent's signal test, but request resting liquidity.
        # NO bid is the complement of YES ask, not YES bid.
        leg_bid = row['bid'] if leg == 'yes' else 1-row['ask']
        price = math.floor(leg_bid*100+1e-9)/100
        if not price_floor <= price <= 0.85 or price >= touch:
            continue
        candidates.append({'market': row['market'], 'leg': leg, 'price': price,
                           'edge': edge, 'move': move, 'score': score})

    if not candidates:
        return result('No BTC/SOL continuation clears the original taking-cost signal test and passive-entry price floor.')

    limits = ctx.get('limits') or {}
    order_cap = max(0, number(limits.get('max_order_usd')))
    position_cap = max(0, number(limits.get('max_position_usd')))
    cash = max(0, number(ctx.get('cash')))
    remaining = (ctx.get('event_risk') or {}).get('remaining_by_market_usd') or {}
    for c in sorted(candidates, key=lambda x: (-x['edge'], x['market'])):
        budget = min(base*p['risk_fraction'], equity*p['risk_fraction'], cash, order_cap, position_cap,
                     max(0, number(remaining.get(c['market']), position_cap)))
        # Retain the conservative taker-rate reserve even for resting bids.
        unit = c['price'] + rate*c['price']*(1-c['price'])
        qty = int(max(0, budget-0.0001)/unit)
        if qty < 1:
            continue
        total_fee = fee(qty, c['price'], rate)
        if qty*c['price']+total_fee > budget+1e-9 or c['score']-c['price']-total_fee/qty < p['edge_buffer']:
            continue
        attempts = (attempts+[[c['market'], now]])[-32:]
        memory['attempts'] = attempts
        intent = {'market': c['market'], 'leg': c['leg'], 'side': 'buy', 'quantity': qty,
                  'type': 'limit', 'limit_price': c['price'], 'post_only': True,
                  'reason': 'Passive BTC/SOL standardized probability continuation; move %.4f, projected score %.4f, fee-reserved edge %.4f.' % (c['move'], c['score'], c['score']-c['price']-total_fee/qty)}
        return result('Bid passively on a qualifying continuation signal without increasing the risk budget.', [intent])
    return result('Signals found, but no fee-inclusive whole-contract entry fits account and event limits.')

import math

NEEDS = {
    'venue': 'kalshi', 'horizon': 'day', 'style': 'baseball-runline-leverage-demand',
    'series': ['KXMLBSPREAD'], 'max_hours_to_close': 48, 'wake_minutes': 30,
    'parameter_rules': {
        'bounds': {'lot_count': [5, 25], 'ticket_budget': [5.0, 20.0], 'end_buffer': [5.0, 8.0], 'entry_ceiling': [12.0, 36.0], 'touch_floor': [0.40, 0.52], 'touch_ceiling': [0.60, 0.72], 'spread_ceiling': [0.01, 0.04]},
        'ordered': [['end_buffer', 'entry_ceiling'], ['touch_floor', 'touch_ceiling']],
        'frozen': ['ticket_budget', 'max_open_positions']
    }
}
PARAMS = {'lot_count': 20, 'ticket_budget': 15.0, 'end_buffer': 5.0, 'entry_ceiling': 30.0, 'touch_floor': 0.45, 'touch_ceiling': 0.67, 'spread_ceiling': 0.025, 'max_open_positions': 3}

def fee(n, price, rate):
    return math.ceil(rate * n * price * (1.0 - price) * 100.0 - 1e-9) / 100.0

def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get('params', {}))
    result = {'intents': [], 'cancels': [], 'thought': 'Seek protection against a one-run win sold by payout-seeking run-line bettors.', 'memory': {}}
    orders = ctx.get('open_orders', [])
    if orders:
        result['cancels'] = [o['order_id'] for o in orders if o.get('order_id')][:20]
        return result
    held = {x.get('market') for x in ctx.get('positions', []) if float(x.get('quantity', 0)) > 0}
    if len(held) >= p['max_open_positions']:
        result['thought'] = 'The held-market cap is reached; do not add another run-line position.'
        return result
    choices = []
    for m in ctx.get('markets', []):
        if m.get('series') not in NEEDS['series'] or m.get('market') in held:
            continue
        title = str(m.get('title', '')).lower()
        strike = m.get('strike')
        if strike is None or abs(float(strike) - 1.5) > 1e-6:
            continue
        if 'win' not in title or 'run' not in title or '1.5' not in title:
            continue
        if not ('over' in title or 'more than' in title) or 'under' in title or 'not win' in title:
            continue
        h = m.get('hours_to_close')
        r = m.get('hours_to_resolve', h)
        b, a = m.get('yes_bid'), m.get('yes_ask')
        if h is None or r is None or b is None or a is None:
            continue
        h, r, b, a = float(h), float(r), float(b), float(a)
        if not (p['end_buffer'] <= h <= p['entry_ceiling'] and 0 < r <= 48 and 0 < b <= a < 1):
            continue
        ask = round(1.0 - b, 6)
        if a - b > p['spread_ceiling'] or not p['touch_floor'] <= ask <= p['touch_ceiling']:
            continue
        choices.append((a - b, h, m['market'], ask))
    limits = ctx.get('limits', {})
    rate = float(ctx.get('fees', {}).get('kalshi_taker_rate', 0.07))
    remaining = (ctx.get('event_risk') or {}).get('remaining_by_market_usd', {})
    for spread, h, ticker, ask in sorted(choices):
        cap = min(p['ticket_budget'], float(ctx.get('cash', 0)), float(limits.get('max_order_usd', 75)), float(limits.get('max_position_usd', 100)), float(remaining.get(ticker, p['ticket_budget'])))
        n = min(int(p['lot_count']), max(0, int(cap / ask)))
        while n > 0 and n * ask + fee(n, ask, rate) > cap:
            n -= 1
        if n < 5:
            continue
        result['intents'] = [{'market': ticker, 'leg': 'no', 'side': 'buy', 'quantity': n, 'type': 'limit', 'limit_price': ask, 'reason': 'Buy loss-or-one-run-win protection against a strictly over-1.5 baseball winning-margin payoff.'}]
        break
    return result

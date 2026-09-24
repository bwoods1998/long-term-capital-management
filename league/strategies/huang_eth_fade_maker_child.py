import datetime

NEEDS = {
    'venue': 'kalshi', 'horizon': 'hour', 'style': 'prior-window-fade-loose-trigger',
    'series': ['KXETH15M'], 'observe': {'symbols': ['ETH/USD']},
    'bars': {'timeframe': '5Min', 'limit': 40},
    'max_hours_to_close': 1, 'wake_minutes': 5,
    'parameter_rules': {'bounds': {'prior_move_min': [0.0007, 0.006], 'quiet_max': [0.0002, 0.002]}}
}
PARAMS = {'prior_move_min': 0.00077, 'quiet_max': 0.001988}

def decide(ctx):
    def done(intents=None, cancels=None, thought='No qualifying ETH fade.'):
        return {'intents': intents or [], 'cancels': cancels or [], 'thought': thought, 'memory': {}}
    orders = ctx.get('open_orders', [])
    if orders:
        return done(cancels=[o['order_id'] for o in orders if o.get('side') == 'buy' and o.get('order_id')][:20], thought='Cancel stale entry before reconsidering.')
    bars = ctx.get('observed', {}).get('bars', {}).get('ETH/USD', [])
    now = datetime.datetime.fromisoformat(ctx['now'].replace('Z', '+00:00'))
    start = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
    prior = []
    for bar in bars:
        stamp = datetime.datetime.fromisoformat(bar['t'].replace('Z', '+00:00'))
        if start - datetime.timedelta(minutes=20) <= stamp < start:
            prior.append(bar)
    if len(prior) < 2 or not float(prior[0].get('c') or 0) or not bars:
        return done()
    move = float(prior[-1]['c']) / float(prior[0]['c']) - 1
    current_move = float(bars[-1]['c']) / float(prior[-1]['c']) - 1
    if abs(move) < ctx['params']['prior_move_min'] or abs(current_move) > ctx['params']['quiet_max']:
        return done()
    markets = [m for m in ctx.get('markets', []) if m.get('series') == 'KXETH15M' and 0.08 < float(m.get('hours_to_close', 99)) <= 0.35 and 0 < float(m.get('hours_to_resolve', 99)) <= 0.35]
    if not markets:
        return done()
    m = min(markets, key=lambda x: x['hours_to_close'])
    if any(p.get('market') == m['market'] for p in ctx.get('positions', [])):
        return done()
    bid, ask_yes = float(m.get('yes_bid') or 0), float(m.get('yes_ask') or 0)
    if not 0 < bid < ask_yes < 1 or ask_yes - bid > 0.06:
        return done()
    leg = 'no' if move > 0 else 'yes'
    ask = 1 - bid if leg == 'no' else ask_yes
    if not 0.20 <= ask <= 0.80:
        return done()
    entry_price = round(1 - ask_yes if leg == 'no' else bid, 4)
    if not 0 < entry_price < ask:
        return done()
    # Retain the parent's conservative ask-based quantity and fee reserve.
    fee = float(ctx.get('fees', {}).get('kalshi_taker_rate', 0.07)) * ask * (1 - ask)
    cap = min(18, float(ctx.get('cash', 0)) * 0.75, float(ctx.get('limits', {}).get('max_order_usd', 75)), float(ctx.get('limits', {}).get('max_position_usd', 100)))
    cap = min(cap, float(ctx.get('event_risk', {}).get('remaining_by_market_usd', {}).get(m['market'], cap)))
    qty = min(16, int(cap / (ask + fee + 0.0001)))
    if qty < 1:
        return done()
    intent = {'market': m['market'], 'leg': leg, 'side': 'buy', 'quantity': qty, 'type': 'limit', 'limit_price': entry_price, 'post_only': True, 'reason': 'Fade a completed ETH window with a resting bid; the family has not proven taker entries'}
    return done([intent], thought='Keep the prior-window fade signal, but rest the entry post-only instead of taking the ask.')

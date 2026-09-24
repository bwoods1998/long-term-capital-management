import math
import re

NEEDS = {'venue': 'kalshi', 'horizon': 'day', 'style': 'central-over-under', 'series': ['KXMLBTOTAL'], 'max_hours_to_close': 48, 'wake_minutes': 30, 'parameter_rules': {'bounds': {'yes_bid_min': [0.25, 0.45], 'yes_ask_max': [0.55, 0.75], 'max_spread': [0.01, 0.06], 'min_hours': [4.5, 12.0], 'premium': [0.035, 0.09], 'reserve': [0.002, 0.02], 'risk_fraction': [0.2, 1.0], 'bunt_usd': [5.0, 18.0]}}}
PARAMS = {'yes_bid_min': 0.34, 'yes_ask_max': 0.68, 'max_spread': 0.035, 'min_hours': 5.0, 'premium': 0.055, 'reserve': 0.006, 'risk_fraction': 0.75, 'bunt_usd': 10.0}

def decide(ctx):
    p = ctx.get('params', PARAMS)
    positions, orders = ctx.get('positions', []), ctx.get('open_orders', [])
    busy = {x.get('market') for x in positions + orders}
    used = sum(float(x.get('quantity') or 0) * float(x.get('average_cost') or 0) for x in positions)
    used += sum(float(x.get('quantity') or 0) * float(x.get('limit_price') or 0) for x in orders if x.get('side') == 'buy')
    limits = ctx.get('limits') or {}
    risk = (ctx.get('event_risk') or {}).get('remaining_by_market_usd') or {}
    rate = float((ctx.get('fees') or {}).get('kalshi_taker_rate', 0.07))
    intents = []
    for m in ctx.get('markets', []):
        if len(intents) >= 4:
            break
        ticker = m.get('market')
        if m.get('series') != 'KXMLBTOTAL' or not ticker or ticker in busy:
            continue
        title = str(m.get('title') or '').lower()
        if 'under' in title or not re.search(r'\bover\s+\d|\bmore than\s+\d|\bat least\s+\d|\b\d+(?:[.]\d+)?\s*(?:or more|\+)\s*runs?', title):
            continue
        h = m.get('hours_to_resolve')
        if h is None:
            h = m.get('hours_to_close')
        yb, ya = m.get('yes_bid'), m.get('yes_ask')
        if h is None or yb is None or ya is None:
            continue
        h, yb, ya = float(h), float(yb), float(ya)
        if not p['min_hours'] < h <= 48 or not p['yes_bid_min'] <= yb < ya <= p['yes_ask_max'] or ya - yb > p['max_spread']:
            continue
        ask = 1 - yb
        fair = 1 - (yb + ya) / 2 + p['premium']
        fee = math.ceil(rate * ask * (1 - ask) * 10000) / 10000
        edge = fair - ask - fee - p['reserve']
        if edge < 0.012 or fair >= 1:
            continue
        wanted = max(p['bunt_usd'], float(ctx.get('equity') or 0) * p['risk_fraction'] * edge / (1 - ask))
        room = min(wanted, float(ctx.get('cash') or 0) * 0.95, float(limits.get('max_order_usd') or 75), float(limits.get('max_position_usd') or 100) - used, float(risk.get(ticker, 1e9)))
        qty = math.floor(room / (ask + fee))
        if qty < 3:
            continue
        # Keep the parent's ask-based budget; rest at the implied NO bid.
        intents.append({'market': ticker, 'leg': 'no', 'side': 'buy', 'quantity': qty, 'type': 'limit', 'limit_price': round(1 - ya, 10), 'post_only': True, 'reason': 'Pregame central UNDER; rest at the NO bid with conservative ask-based edge and fee allowance.'})
        used += qty * (ask + fee)
        busy.add(ticker)
    return {'intents': intents, 'cancels': [], 'thought': 'Rest post-only at the NO bid only when the proposed central-OVER premium clears the original ask-based spread, fee and reserve test.', 'memory': {}}

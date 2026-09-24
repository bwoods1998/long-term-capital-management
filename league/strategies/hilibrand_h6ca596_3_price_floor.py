import math
import datetime

NEEDS = {
    'venue': 'kalshi',
    'horizon': 'hour',
    'style': 'crypto-strike-realized-vol-two-sided',
    'series': ['KXBTCD', 'KXBTC', 'KXETHD', 'KXETH'],
    'observe': {'symbols': ['BTC/USD', 'ETH/USD']},
    'bars': {'timeframe': '5Min', 'limit': 120},
    'max_hours_to_close': 4,
    'wake_minutes': 5,
    'parameter_rules': {'bounds': {'edge_floor': [0.08, 0.25], 'risk_fraction': [0.02, 0.12]}}
}
PARAMS = {'edge_floor': 0.15, 'risk_fraction': 0.08}

def clock(s):
    try:
        return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError):
        return None

def decide(ctx):
    out = {'intents': [], 'cancels': [], 'thought': 'No middle-priced strike has a conservative two-sided spot/realized-vol edge at an allowed entry price.', 'memory': {}}
    observed = ctx.get('observed', {}).get('bars', {})
    estimates = {}
    for coin in ('BTC', 'ETH'):
        bars = observed.get(coin + '/USD', [])
        closes = [float(x.get('c', 0) or 0) for x in bars[-13:]]
        if len(closes) < 13 or min(closes) <= 0:
            continue
        returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
        sigma_hour = max(0.0025, math.sqrt(12.0 * sum(r*r for r in returns) / len(returns)))
        estimates[coin] = (closes[-1], sigma_hour)

    positions = ctx.get('positions', [])
    orders = ctx.get('open_orders', [])
    occupied = set(x.get('market') for x in positions)
    occupied.update(x.get('market') for x in orders if x.get('side') == 'buy')
    choices = []
    params = ctx.get('params', PARAMS)
    edge_floor = float(params.get('edge_floor', 0.15))
    entry_floor = 0.30 if ctx.get('rung', 0) >= 2 else 0.15
    for m in ctx.get('markets', []):
        series = m.get('series', '')
        if series not in NEEDS['series'] or m.get('market') in occupied or m.get('strike') is None:
            continue
        coin = 'BTC' if series in ('KXBTCD', 'KXBTC') else 'ETH'
        if coin not in estimates:
            continue
        hours = float(m.get('hours_to_resolve') or 0)
        close_h = float(m.get('hours_to_close') or 0)
        if not (1.0 <= hours <= 4.0 and close_h >= 0.75):
            continue
        spot, sigma_hour = estimates[coin]
        strike = float(m['strike'])
        if strike <= 0:
            continue
        yes_bid = float(m.get('yes_bid') or 0)
        yes_ask = float(m.get('yes_ask') or 0)
        if not (0 < yes_bid < yes_ask < 1) or yes_ask - yes_bid > 0.12:
            continue
        sigma = sigma_hour * math.sqrt(hours)
        z = math.log(spot / strike) / sigma
        p_yes = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        sides = [
            ('yes', yes_bid, p_yes),
            ('no', 1.0 - yes_ask, 1.0 - p_yes),
        ]
        for leg, bid, fair in sides:
            # Intersect the original middle-price range with the book's entry floor.
            limit_price = math.floor(bid * 100.0 + 1e-8) / 100.0
            if not (max(0.20, entry_floor) <= limit_price <= 0.65):
                continue
            edge = fair - limit_price
            if edge >= edge_floor:
                choices.append((edge, m, leg, limit_price))

    if not choices:
        return out
    edge, market, leg, price = max(choices, key=lambda x: x[0])
    limits = ctx.get('limits', {})
    risk_map = ctx.get('event_risk', {}).get('remaining_by_market_usd', {})
    risk = float(risk_map.get(market['market'], float('inf')))
    used = 0.0
    for p in positions:
        used += float(p.get('quantity', 0) or 0) * float(p.get('average_cost', 0) or 0)
    for o in orders:
        if o.get('side') == 'buy':
            used += max(0.0, float(o.get('quantity', 0) or 0) - float(o.get('filled', 0) or 0)) * float(o.get('limit_price', 0) or 0)
    budget = min(
        float(limits.get('max_order_usd', 0) or 0),
        max(0.0, float(limits.get('max_position_usd', 0) or 0) - used),
        max(0.0, float(ctx.get('cash', 0) or 0) * 0.95),
        max(0.0, risk),
        max(0.0, float(ctx.get('equity', 0) or 0) * float(params.get('risk_fraction', 0.08)))
    )
    qty = int(budget // price)
    if qty < 1:
        return out
    out['intents'] = [{
        'market': market['market'], 'leg': leg, 'side': 'buy', 'quantity': qty,
        'type': 'limit', 'limit_price': price, 'post_only': True,
        'reason': 'Resting middle-priced bid: spot and recent realized volatility imply a settlement probability well above the bid.'
    }]
    out['thought'] = 'Use a two-sided, realized-vol strike estimate; only one capped, post-only middle-price bid meeting the entry floor is allowed.'
    return out

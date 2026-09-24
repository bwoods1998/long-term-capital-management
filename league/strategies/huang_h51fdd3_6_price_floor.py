NEEDS = {
    'venue': 'kalshi',
    'horizon': 'hour',
    'style': 'spot-strike-volatility-model-maker-no-doge',
    'series': ['KXBTC15M', 'KXETH15M', 'KXSOL15M', 'KXXRP15M'],
    'observe': {'symbols': ['BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD']},
    'bars': {'timeframe': '5Min', 'limit': 30},
    'max_hours_to_close': 1,
    'wake_minutes': 5
}
PARAMS = {'edge_min': 0.10, 'bid_buffer': 0.02, 'vol_window': 12}


def decide(ctx):
    import math
    pairs = {'KXBTC15M': 'BTC/USD', 'KXETH15M': 'ETH/USD',
             'KXSOL15M': 'SOL/USD', 'KXXRP15M': 'XRP/USD'}
    params = ctx.get('params', PARAMS)
    entry_floor = 0.30 if ctx.get('rung', 0) >= 2 else 0.15
    observed = ctx.get('observed', {}).get('bars', {})
    fair_by_series = {}
    for series, symbol in pairs.items():
        bars = observed.get(symbol, [])
        closes = []
        for bar in bars:
            try:
                value = float(bar.get('c'))
                if value > 0:
                    closes.append(value)
            except (TypeError, ValueError):
                pass
        window = int(params.get('vol_window', 12))
        if len(closes) < window + 1:
            continue
        returns = [math.log(closes[i] / closes[i-1])
                   for i in range(len(closes)-window, len(closes))]
        mean = sum(returns) / len(returns)
        variance = sum((r-mean)*(r-mean) for r in returns) / max(1, len(returns)-1)
        sigma5 = math.sqrt(max(variance, 0.0))
        if sigma5 <= 1e-8:
            continue
        fair_by_series[series] = (closes[-1], sigma5)

    markets = [m for m in ctx.get('markets', [])
               if m.get('series') in pairs
               and 0 < float(m.get('hours_to_resolve') or 99) <= 0.25
               and 0.03 <= float(m.get('hours_to_close') or 99) <= 0.25]
    cancels = []
    open_orders = ctx.get('open_orders', [])
    eligible = []
    for market in markets:
        series = market.get('series')
        model = fair_by_series.get(series)
        if not model:
            continue
        spot, sigma5 = model
        try:
            strike = float(market.get('strike'))
            remain_min = max(1.0, float(market.get('hours_to_resolve')) * 60.0)
            yes_bid = float(market.get('yes_bid'))
            yes_ask = float(market.get('yes_ask'))
        except (TypeError, ValueError):
            continue
        if strike <= 0 or not (0 < yes_bid < yes_ask < 1):
            continue
        z = math.log(spot / strike) / (sigma5 * math.sqrt(remain_min / 5.0))
        fair_yes = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        for leg, fair, touch_bid in [('yes', fair_yes, yes_bid),
                                     ('no', 1.0-fair_yes, 1.0-yes_ask)]:
            price = round(touch_bid - float(params.get('bid_buffer', 0.02)), 2)
            # Check the actual buffered bid, not the touch or model probability.
            if not (max(0.05, entry_floor) <= price <= 0.80):
                continue
            if fair - price < float(params.get('edge_min', 0.10)):
                continue
            if any(p.get('market') == market.get('market') for p in ctx.get('positions', [])):
                continue
            eligible.append((fair-price, market, leg, price))

    wanted = {(x[1].get('market'), x[2]) for x in eligible}
    for order in open_orders:
        below_floor = (order.get('side') == 'buy'
                       and float(order.get('limit_price') or 0) < entry_floor)
        if below_floor or order.get('side') != 'buy' or (order.get('market'), order.get('leg')) not in wanted:
            if order.get('order_id'):
                cancels.append(order['order_id'])
    if cancels:
        return {'intents': [], 'cancels': cancels[:20],
                'thought': 'Cancel orders that no longer qualify, including resting buys below the applicable entry floor.', 'memory': {}}
    if open_orders:
        return {'intents': [], 'cancels': [], 'thought': 'Maintain at most one model-qualified resting bid.', 'memory': {}}
    if not eligible:
        return {'intents': [], 'cancels': [], 'thought': 'No non-DOGE contract has a sufficiently large modeled edge at an allowed passive price.', 'memory': {}}
    edge, market, leg, price = max(eligible, key=lambda x: x[0])
    limits = ctx.get('limits', {})
    remaining = ctx.get('event_risk', {}).get('remaining_by_market_usd', {}).get(market.get('market'), 3.0)
    cap = min(3.0, float(ctx.get('cash') or 0) * 0.15,
              float(limits.get('max_order_usd') or 0),
              float(limits.get('max_position_usd') or 0), float(remaining or 0))
    quantity = min(5, int(cap / (price * 1.02)))
    if quantity < 1:
        return {'intents': [], 'cancels': [], 'thought': 'Model edge exists but risk headroom cannot fund one contract.', 'memory': {}}
    intent = {'market': market.get('market'), 'leg': leg, 'side': 'buy', 'quantity': quantity,
              'type': 'limit', 'limit_price': price, 'post_only': True,
              'reason': 'Rest a small bid only when spot-versus-strike probability model clears the price by a wide margin'}
    return {'intents': [intent], 'cancels': [],
            'thought': 'Test a volatility-scaled settlement model on BTC, ETH, SOL and XRP; exclude DOGE pending forward evidence.', 'memory': {}}

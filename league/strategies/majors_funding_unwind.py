import math
from datetime import datetime, timezone


NEEDS = {
    "venue": "alpaca",
    "horizon": "hour",
    "style": "funding-conditioned-reversion",
    "symbols": ["BTC/USD", "ETH/USD"],
    "bars": {"timeframe": "1Hour", "limit": 96},
    "feeds": {"funding": ["BTC", "ETH"]},
    "wake_minutes": 15,
    "parameter_rules": {
        "bounds": {"crowding_z_min": [0.75, 2.5]},
        "frozen": [
            "notional_usd", "negative_rate_8h", "decline_min",
            "target_return", "stop_return", "hold_hours",
            "order_minutes", "signal_minutes", "max_spread",
            "entry_discount"
        ]
    }
}

PARAMS = {
    "crowding_z_min": 1.25,
    "notional_usd": 10.0,
    "negative_rate_8h": 0.000025,
    "decline_min": 0.005,
    "target_return": 0.02,
    "stop_return": 0.025,
    "hold_hours": 36,
    "order_minutes": 45,
    "signal_minutes": 240,
    "max_spread": 0.0015,
    "entry_discount": 0.001
}


def number(value, default=None):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def stamp(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def fresh_quote(ctx, symbol, now):
    row = ctx.get('quotes', {}).get(symbol, {}) or {}
    bid = number(row.get('bid'))
    ask = number(row.get('ask'))
    when = stamp(row.get('t'))
    if bid is None or ask is None or when is None:
        return None
    if not 0 < bid <= ask or not 0 <= now - when <= 30:
        return None
    return {'bid': bid, 'ask': ask}


def signal(ctx, symbol, now, p, maker, taker):
    coin = symbol.split('/')[0]
    feed = ctx.get('feeds', {}).get('funding', {}).get(coin, {}) or {}
    when = stamp(feed.get('t'))
    rate = number(feed.get('rate'))
    interval = number(feed.get('interval_hours'))
    zscore = number(feed.get('zscore_30d'))
    if when is None or rate is None or interval is None or zscore is None:
        return None
    if not 0 <= now - when <= p['signal_minutes'] * 60:
        return None
    if not 0 < interval <= 24:
        return None
    if rate * 8.0 / interval > -p['negative_rate_8h']:
        return None
    if zscore > -p['crowding_z_min']:
        return None
    quote = fresh_quote(ctx, symbol, now)
    if quote is None:
        return None
    spread = quote['ask'] / quote['bid'] - 1.0
    if spread > p['max_spread']:
        return None
    # Include the paper execution haircut in the economic hurdle on every rung.
    friction = maker + taker + 0.0008 + spread
    if p['target_return'] < 2.0 * friction:
        return None
    rows = ctx.get('bars', {}).get(symbol, [])[-24:]
    if len(rows) != 24:
        return None
    closes = []
    highs = []
    lows = []
    times = []
    for row in rows:
        when_bar = stamp(row.get('t'))
        close = number(row.get('c'))
        high = number(row.get('h'))
        low = number(row.get('l'))
        if when_bar is None or close is None or high is None or low is None:
            return None
        if not 0 < low <= close <= high or when_bar > now:
            return None
        if times and not 1800 <= when_bar - times[-1] <= 5400:
            return None
        times.append(when_bar)
        closes.append(close)
        highs.append(high)
        lows.append(low)
    if not 0 <= now - times[-1] <= 7200:
        return None
    # Require a recent decline, then a non-declining completed hourly close.
    if closes[-1] / closes[-4] - 1.0 > -p['decline_min']:
        return None
    if closes[-1] < closes[-2]:
        return None
    if max(highs) / min(lows) - 1.0 < p['target_return'] + friction:
        return None
    if abs(quote['bid'] / closes[-1] - 1.0) > 0.03:
        return None
    return {
        'funding_t': feed['t'], 'score': -zscore,
        'bid': quote['bid'], 'ask': quote['ask'], 'close': closes[-1]
    }


def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get('params', {}))
    previous = (ctx.get('memory', {}) or {}).get('used', {}) or {}
    used = {}
    for symbol in NEEDS['symbols']:
        value = previous.get(symbol)
        if stamp(value) is not None:
            used[symbol] = value
    memory = {'used': used}
    cancels = []
    intents = []

    def cancel(order):
        identity = order.get('order_id')
        if isinstance(identity, str) and identity not in cancels and len(cancels) < 20:
            cancels.append(identity)

    def answer(thought):
        outcomes = ctx.get('recent_order_outcomes', []) or []
        if outcomes and outcomes[-1].get('status') == 'refused':
            thought += ' A recent order was refused; this decision does not enlarge its budget or chase its price.'
        return {'intents': intents, 'cancels': cancels, 'thought': thought, 'memory': memory}

    now = stamp(ctx.get('now'))
    orders = ctx.get('open_orders', []) or []
    if now is None:
        for order in orders:
            if order.get('side') == 'buy':
                cancel(order)
        return answer('The decision clock is unavailable; cancel entry commitments.')
    fees = ctx.get('fees', {}) or {}
    maker = number(fees.get('crypto_maker'), 0.0015)
    taker = number(fees.get('crypto_taker'), 0.0025)
    if not 0 <= maker <= 0.05 or not 0 <= taker <= 0.05:
        maker, taker = 0.05, 0.05
    holdings = [row for row in ctx.get('positions', [])
                if row.get('symbol') in NEEDS['symbols']
                and number(row.get('quantity'), 0.0) > 0]
    if holdings:
        for order in orders:
            if order.get('side') == 'buy':
                cancel(order)
        for position in holdings[:8]:
            symbol = position['symbol']
            opened = stamp(position.get('opened_at'))
            cost = number(position.get('average_cost'))
            quote = fresh_quote(ctx, symbol, now)
            reason = None
            if opened is None or opened > now:
                reason = 'Close because holding age cannot be verified.'
            elif now - opened >= p['hold_hours'] * 3600:
                reason = 'Close at the funding-unwind holding deadline, before the 48-hour ceiling.'
            elif cost is None or cost <= 0:
                reason = 'Close because the cost basis needed for risk controls is unavailable.'
            elif quote is not None:
                net_move = quote['bid'] / cost * (1.0 - taker) / (1.0 + maker) - 1.0
                if quote['bid'] <= cost * (1.0 - p['stop_return']):
                    reason = 'Close on the observed protective price threshold; execution may slip.'
                elif net_move >= p['target_return']:
                    reason = 'Realize the unwind after clearing the estimated entry and exit fee hurdle.'
            if reason is not None:
                for order in orders:
                    if order.get('symbol') == symbol:
                        cancel(order)
                intents.append({
                    'symbol': symbol, 'side': 'sell',
                    'quantity': position['quantity'], 'type': 'market',
                    'reason': reason
                })
        return answer('Manage the existing exposure without adding to it.')

    signals = {}
    for symbol in NEEDS['symbols']:
        value = signal(ctx, symbol, now, p, maker, taker)
        if value is not None:
            signals[symbol] = value
    limits = ctx.get('limits', {}) or {}
    equity = max(0.0, number(ctx.get('equity'), 0.0))
    position_cap = min(number(limits.get('max_position_usd'), 0.0), equity * 0.49)
    order_cap = number(limits.get('max_order_usd'), 0.0)

    if orders:
        retained = False
        for order in orders:
            symbol = order.get('symbol')
            value = signals.get(symbol)
            submitted = stamp(order.get('submitted_at'))
            price = number(order.get('limit_price'), 0.0)
            filled = number(order.get('filled'), 0.0)
            quantity = number(order.get('quantity'), 0.0)
            valid = (
                not retained and order.get('side') == 'buy'
                and value is not None and submitted is not None
                and 0 <= now - submitted < p['order_minutes'] * 60
                and used.get(symbol) == value['funding_t']
                and filled == 0 and quantity > 0
                and 0 < price < value['ask']
                and abs(price / value['bid'] - 1.0) <= 0.09
                and abs(price / value['close'] - 1.0) <= 0.09
                and quantity * value['ask'] <= min(position_cap, order_cap)
                and quantity * price <= p['notional_usd'] + price * 1e-9 + 1e-8
            )
            if valid:
                retained = True
            else:
                cancel(order)
        return answer('Preserve one eligible resting bid or cancel invalid commitments; do not spend anticipated cancellation releases.')

    cash = max(0.0, number(ctx.get('cash'), 0.0))
    ranked = sorted(signals, key=lambda symbol: (-signals[symbol]['score'], symbol))
    for symbol in ranked:
        value = signals[symbol]
        if used.get(symbol) == value['funding_t']:
            continue
        rules = ctx.get('venue_rules', {}).get(symbol, {}) or {}
        minimum = max(10.0, number(rules.get('min_order_usd'), 10.0))
        if minimum > p['notional_usd']:
            continue
        price = value['bid'] * (1.0 - p['entry_discount'])
        tick = number(rules.get('price_increment'), 0.0)
        if tick > 0:
            price = math.floor(price / tick) * tick
        if price <= 0 or price >= value['ask']:
            continue
        if abs(price / value['bid'] - 1.0) > 0.09:
            continue
        # Round the venue minimum upward by at most one permitted quantity step.
        quantity = math.ceil(minimum / price * 1e9) / 1e9
        principal = quantity * price
        if principal + 1e-8 < minimum:
            continue
        if principal > p['notional_usd'] + price * 1e-9 + 1e-8:
            continue
        if quantity * value['ask'] > min(position_cap, order_cap):
            continue
        if principal * (1.0 + maker) + 0.01 > cash:
            continue
        used[symbol] = value['funding_t']
        intents.append({
            'symbol': symbol, 'side': 'buy', 'quantity': quantity,
            'type': 'limit', 'limit_price': price, 'post_only': True,
            'reason': 'Test a short-crowding unwind after unusually negative settled funding and completed-bar stabilization; spot earns no funding.'
        })
        return answer('Submit one venue-minimum passive entry with capacity and fee reserves.')
    return answer('No unused funding observation clears the data, economic and executable-capacity requirements.')

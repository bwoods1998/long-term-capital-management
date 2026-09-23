import datetime
import math
import zoneinfo


NEEDS = {
    'venue': 'alpaca',
    'horizon': 'day',
    'style': 'two-session-pullback',
    'symbols': ['SPY', 'QQQ', 'IWM'],
    'bars': {'timeframe': '1Day', 'limit': 220},
    'wake_minutes': 15,
    'parameter_rules': {
        'bounds': {'rsi_entry': [5.0, 15.0]},
        'ordered': [['entry_start', 'entry_end']],
        'frozen': [
            'trend_window', 'rsi_period', 'rebound_window', 'max_sessions',
            'entry_start', 'entry_end', 'max_spread', 'stop_pct',
            'notional_usd'
        ],
    },
}

PARAMS = {
    'trend_window': 200,
    'rsi_period': 2,
    'rebound_window': 5,
    'max_sessions': 5,
    'rsi_entry': 10.0,
    'entry_start': 585,
    'entry_end': 615,
    'max_spread': 0.001,
    'stop_pct': 0.04,
    'notional_usd': 2.0,
}

NY = zoneinfo.ZoneInfo('America/New_York')


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            result = result.replace(tzinfo=datetime.timezone.utc)
        return result
    except (TypeError, ValueError, OverflowError):
        return None


def daily_rows(ctx, symbol, now):
    today = now.astimezone(NY).date()
    by_day = {}
    for row in ctx.get('bars', {}).get(symbol, []):
        when = timestamp(row.get('t'))
        close = number(row.get('c'))
        if when is None or when > now or close <= 0:
            continue
        day = when.astimezone(NY).date()
        if day < today:
            by_day[day.isoformat()] = close
    return sorted(by_day.items())[-NEEDS['bars']['limit']:]


def fresh_quote(ctx, symbol, now):
    quote = ctx.get('quotes', {}).get(symbol, {})
    when = timestamp(quote.get('t'))
    bid = number(quote.get('bid'))
    ask = number(quote.get('ask'))
    if when is None or bid <= 0 or ask < bid:
        return None
    age = (now - when).total_seconds()
    if age < 0 or age > 120:
        return None
    return bid, ask


def rsi(closes, period):
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    if len(changes) < period:
        return None
    gain = sum(max(change, 0.0) for change in changes[:period]) / period
    loss = sum(max(-change, 0.0) for change in changes[:period]) / period
    for change in changes[period:]:
        gain = ((period - 1) * gain + max(change, 0.0)) / period
        loss = ((period - 1) * loss + max(-change, 0.0)) / period
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params') or {})
    prior = ctx.get('memory') or {}
    memory = {
        'held_days': {},
        'last_exit_day': prior.get('last_exit_day', ''),
        'last_refusal': str(prior.get('last_refusal', ''))[:180],
    }
    for outcome in ctx.get('recent_order_outcomes', []):
        if outcome.get('status') == 'refused':
            memory['last_refusal'] = str(outcome.get('reason', 'Unspecified refusal'))[:180]

    result = {'intents': [], 'cancels': [], 'thought': '', 'memory': memory}
    orders = ctx.get('open_orders') or []
    owned_orders = [order for order in orders if order.get('symbol') in NEEDS['symbols']]
    now = timestamp(ctx.get('now'))
    if now is None:
        memory['held_days'] = {
            symbol: str(day)[:10]
            for symbol, day in (prior.get('held_days') or {}).items()
            if symbol in NEEDS['symbols']
        }
        result['cancels'] = [
            order['order_id'] for order in owned_orders
            if order.get('side') == 'buy' and order.get('order_id')
        ][:20]
        result['thought'] = 'The decision clock is unavailable; no new exposure is allowed.'
        return result

    local = now.astimezone(NY)
    today = local.date().isoformat()
    minute = local.hour * 60 + local.minute
    positions = [
        position for position in ctx.get('positions', [])
        if number(position.get('quantity')) > 0
    ]
    owned_positions = [
        position for position in positions
        if position.get('symbol') in NEEDS['symbols']
    ]
    prior_days = prior.get('held_days') or {}
    active_symbols = set(position.get('symbol') for position in owned_positions)
    if any(symbol not in active_symbols for symbol in prior_days):
        memory['last_exit_day'] = today

    for position in owned_positions:
        symbol = position['symbol']
        opened = timestamp(position.get('opened_at'))
        saved = timestamp(str(prior_days.get(symbol, '')) + 'T00:00:00+00:00')
        if opened is not None and opened <= now:
            entry_day = opened.astimezone(NY).date().isoformat()
        elif saved is not None and saved.date() <= local.date():
            entry_day = saved.date().isoformat()
        else:
            entry_day = today
        memory['held_days'][symbol] = entry_day

    # This strategy uses market orders only. Never overlap an unresolved order
    # with a replacement, including on a wake requesting cancellation.
    if orders:
        for order in owned_orders:
            submitted = timestamp(order.get('submitted_at'))
            stale = submitted is None or (now - submitted).total_seconds() >= 120
            extra_buy = bool(positions) and order.get('side') == 'buy'
            if (stale or extra_buy) and order.get('order_id'):
                result['cancels'].append(order['order_id'])
        result['cancels'] = result['cancels'][:20]
        result['thought'] = 'An order is still unresolved; wait for completion or confirmed cancellation before sending another.'
        return result

    if local.weekday() >= 5 or not 585 <= minute <= 955:
        result['thought'] = 'Outside the regular-session execution window; preserve holdings without adding exposure.'
        return result

    # Position management does not require an entry signal or fresh daily data.
    for position in owned_positions:
        symbol = position['symbol']
        rows = daily_rows(ctx, symbol, now)
        closes = [close for day, close in rows]
        quote = fresh_quote(ctx, symbol, now)
        entry_day = memory['held_days'][symbol]
        completed_sessions = sum(1 for day, close in rows if day >= entry_day)
        entry_date = datetime.date.fromisoformat(entry_day)
        calendar_age = (local.date() - entry_date).days
        reason = ''
        cost = number(position.get('average_cost'))
        if quote is not None and cost > 0 and quote[0] <= cost * (1.0 - params['stop_pct']):
            reason = 'Observed loss reached the protective price threshold; gaps may exceed it.'
        elif completed_sessions >= params['max_sessions'] or calendar_age >= 10:
            reason = 'The bounded pullback holding period has elapsed.'
        elif len(closes) >= params['rebound_window']:
            rebound_mean = sum(closes[-params['rebound_window']:]) / params['rebound_window']
            if closes[-1] >= rebound_mean:
                reason = 'The completed daily close recovered to its short moving average.'
        if reason:
            quantity = number(position.get('quantity'))
            reference = quote[0] if quote is not None else number(position.get('mark'), cost)
            order_cap = number(ctx.get('limits', {}).get('max_order_usd'))
            if reference > 0 and order_cap > 0:
                quantity = min(quantity, 0.99 * order_cap / reference)
            quantity = math.floor(quantity * 1000000000) / 1000000000
            if quantity > 0:
                result['intents'].append({
                    'symbol': symbol,
                    'side': 'sell',
                    'quantity': quantity,
                    'type': 'market',
                    'reason': reason,
                })

    if positions:
        result['intents'] = result['intents'][:8]
        result['thought'] = 'Manage the existing exposure; no additional or replacement entry is allowed while shares remain.'
        return result

    if memory['last_exit_day'] == today:
        result['thought'] = 'An exit was confirmed today; do not recycle the same daily signal.'
        return result
    if not params['entry_start'] <= minute <= params['entry_end']:
        result['thought'] = 'No position is held, but the morning entry window is closed.'
        return result

    limits = ctx.get('limits') or {}
    budget = min(
        params['notional_usd'],
        0.99 * max(0.0, number(ctx.get('cash'))),
        0.99 * max(0.0, number(limits.get('max_order_usd'))),
        0.99 * max(0.0, number(limits.get('max_position_usd'))),
    )
    budget = math.floor(budget * 100) / 100
    if budget < 1.0:
        result['thought'] = 'Less than one dollar fits the cash and risk limits; do not enlarge the allocation to force a trade.'
        return result

    candidates = []
    for symbol in NEEDS['symbols']:
        rows = daily_rows(ctx, symbol, now)
        required = max(params['trend_window'] + 1, params['rebound_window'], params['rsi_period'] + 1, 3)
        if len(rows) < required:
            continue
        last_day = datetime.date.fromisoformat(rows[-1][0])
        if (local.date() - last_day).days > 7:
            continue
        closes = [close for day, close in rows]
        window = params['trend_window']
        trend = sum(closes[-window:]) / window
        previous_trend = sum(closes[-window - 1:-1]) / window
        if closes[-1] <= trend or trend <= previous_trend:
            continue
        if not closes[-1] < closes[-2] < closes[-3]:
            continue
        value = rsi(closes, params['rsi_period'])
        if value is None or value > params['rsi_entry']:
            continue
        quote = fresh_quote(ctx, symbol, now)
        if quote is None:
            continue
        bid, ask = quote
        if (ask - bid) / ((ask + bid) / 2.0) > params['max_spread']:
            continue
        rebound_mean = sum(closes[-params['rebound_window']:]) / params['rebound_window']
        if ask >= rebound_mean:
            continue
        minimum = number(ctx.get('venue_rules', {}).get(symbol, {}).get('min_order_usd'))
        if budget < minimum:
            continue
        candidates.append((value, symbol))

    if not candidates:
        result['thought'] = 'No affordable ETF has the completed two-session pullback, long-term trend and fresh executable spread required.'
        return result

    value, symbol = min(candidates)
    result['intents'] = [{
        'symbol': symbol,
        'side': 'buy',
        'notional_usd': budget,
        'type': 'market',
        'reason': 'Two declining completed sessions and low RSI(2) within a rising long-term trend; test a bounded fractional rebound exposure.',
    }]
    result['thought'] = 'One ETF qualifies for the pullback hypothesis. Submit a small fractional entry without treating submission as a confirmed fill.'
    return result

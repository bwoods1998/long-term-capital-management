import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


NEEDS = {
    'venue': 'alpaca',
    'horizon': 'day',
    'style': 'gap-volume-continuation',
    'symbols': ['AAPL', 'MSFT', 'NVDA', 'AMZN'],
    'bars': {'timeframe': '1Day', 'limit': 60},
    'wake_minutes': 15,
    'parameter_rules': {
        'bounds': {
            'lookback': [20, 20],
            'gap_min': [0.015, 0.03],
            'gap_max': [0.10, 0.10],
            'volume_ratio_min': [1.5, 1.5],
            'close_location_min': [0.75, 0.75],
            'hold_sessions': [2, 4],
            'stop_fraction': [0.05, 0.05],
            'notional_usd': [2.0, 2.0],
        },
        'ordered': [['gap_min', 'gap_max']],
        'frozen': [
            'lookback', 'gap_max', 'volume_ratio_min',
            'close_location_min', 'stop_fraction', 'notional_usd',
        ],
    },
}

PARAMS = {
    'lookback': 20,
    'gap_min': 0.02,
    'gap_max': 0.10,
    'volume_ratio_min': 1.5,
    'close_location_min': 0.75,
    'hold_sessions': 3,
    'stop_fraction': 0.05,
    'notional_usd': 2.0,
}

NY = ZoneInfo('America/New_York')


def number(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            return None
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def answer(thought, memory, intents=None, cancels=None):
    if memory.get('last_refusal'):
        thought += ' Recent House refusal: ' + memory['last_refusal']
    return {
        'intents': intents or [],
        'cancels': cancels or [],
        'thought': thought,
        'memory': memory,
    }


def daily_history(ctx, symbol, now):
    # Use only supplied, closed daily sessions strictly before today.
    today = now.astimezone(NY).date()
    sessions = {}
    for row in (ctx.get('bars', {}).get(symbol) or [])[-60:]:
        stamp = timestamp(row.get('t'))
        if stamp is None or stamp > now:
            continue
        session = stamp.astimezone(NY).date()
        if session >= today:
            continue
        values = {key: number(row.get(key)) for key in ('o', 'h', 'l', 'c', 'v')}
        if min(values.values()) <= 0:
            continue
        if values['h'] < max(values['o'], values['c'], values['l']):
            continue
        if values['l'] > min(values['o'], values['c']):
            continue
        sessions[session] = values
    return [(session, sessions[session]) for session in sorted(sessions)]


def fresh_quote(ctx, symbol, now):
    quote = ctx.get('quotes', {}).get(symbol) or {}
    stamp = timestamp(quote.get('t'))
    if stamp is None:
        return None
    age = (now - stamp).total_seconds()
    if age < 0 or age > 60:
        return None
    bid = number(quote.get('bid'))
    ask = number(quote.get('ask'))
    if bid <= 0 or ask < bid:
        return None
    return bid, ask


def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get('params') or {})
    previous_memory = ctx.get('memory') or {}
    previous_attempts = previous_memory.get('attempted') or {}
    attempted = {}
    for symbol in NEEDS['symbols']:
        value = previous_attempts.get(symbol)
        if isinstance(value, str):
            attempted[symbol] = value[:32]
    memory = {'attempted': attempted}
    for outcome in ctx.get('recent_order_outcomes') or []:
        if outcome.get('status') == 'refused' and outcome.get('submitted_to_venue') is False:
            memory['last_refusal'] = str(outcome.get('reason') or 'unspecified')[:240]

    now = timestamp(ctx.get('now'))
    if now is None:
        return answer('A valid aware clock is required before placing an order.', memory)

    # This program uses market orders only. Do not overlap an unresolved
    # order with a replacement, even when a cancellation has been requested.
    orders = ctx.get('open_orders') or []
    if orders:
        cancels = []
        for order in orders:
            order_id = order.get('order_id')
            if isinstance(order_id, str) and order_id and order_id not in cancels:
                cancels.append(order_id)
            if len(cancels) == 20:
                break
        return answer('Waiting for outstanding orders to clear before any replacement.', memory, cancels=cancels)

    local = now.astimezone(NY)
    minute = local.hour * 60 + local.minute
    if local.weekday() >= 5 or minute < 570 or minute >= 960:
        return answer('Waiting for regular New York trading hours.', memory)

    positions = [position for position in (ctx.get('positions') or [])
                 if number(position.get('quantity')) > 0]
    if positions:
        intents = []
        for position in positions:
            symbol = position.get('symbol')
            if symbol not in NEEDS['symbols']:
                continue
            quote = fresh_quote(ctx, symbol, now)
            if quote is None:
                continue
            bid, ask = quote
            opened = timestamp(position.get('opened_at'))
            cost = number(position.get('average_cost'))
            reason = None
            if opened is None or opened > now or cost <= 0:
                reason = 'Flatten: holding metadata cannot support a reliable risk clock.'
            elif bid <= cost * (1.0 - p['stop_fraction']):
                reason = 'Exit: quoted bid breached the price stop; execution may gap beyond it.'
            else:
                age_hours = (now - opened).total_seconds() / 3600.0
                opened_day = opened.astimezone(NY).date()
                history = daily_history(ctx, symbol, now)
                completed = sum(1 for session, row in history if session >= opened_day)
                if age_hours >= 168:
                    reason = 'Exit: seven-calendar-day holding backstop at the next fresh regular-session quote.'
                elif completed >= p['hold_sessions']:
                    reason = 'Exit: the scheduled holding-session deadline has already passed.'
                elif completed + 1 >= p['hold_sessions'] and minute >= 945:
                    reason = 'Exit: scheduled final holding session, from 15:45 New York.'
            if reason:
                intents.append({
                    'symbol': symbol,
                    'side': 'sell',
                    'quantity': number(position.get('quantity')),
                    'type': 'market',
                    'reason': reason,
                })
            if len(intents) == 8:
                break
        if intents:
            return answer('Closing exposure under the price or holding-time rule; no replacement entry this wake.', memory, intents=intents)
        return answer('Holding the existing exposure; management requires a fresh regular-session quote.', memory)

    if minute < 585 or minute > 615:
        return answer('New entries are restricted to 09:45–10:15 New York.', memory)

    limits = ctx.get('limits') or {}
    budget = min(
        p['notional_usd'],
        max(0.0, number(ctx.get('cash')) - 0.01),
        max(0.0, number(limits.get('max_order_usd'))),
        max(0.0, number(limits.get('max_position_usd'))),
    )
    budget = math.floor(budget * 100.0) / 100.0
    if budget < 1.0:
        return answer('Cash or House limits cannot support a one-dollar fractional entry.', memory)

    candidates = []
    for symbol in NEEDS['symbols']:
        history = daily_history(ctx, symbol, now)
        if len(history) < p['lookback'] + 1:
            continue
        event_day, event = history[-1]
        # Permit weekends and ordinary holiday gaps, not indefinitely old news.
        if not 1 <= (local.date() - event_day).days <= 4:
            continue
        event_key = event_day.isoformat()
        if attempted.get(symbol) == event_key:
            continue
        prior_close = history[-2][1]['c']
        gap = event['o'] / prior_close - 1.0
        if not p['gap_min'] <= gap <= p['gap_max']:
            continue
        event_range = event['h'] - event['l']
        if event_range <= 0 or event['c'] < event['o']:
            continue
        close_location = (event['c'] - event['l']) / event_range
        if close_location < p['close_location_min']:
            continue
        baseline = history[-p['lookback'] - 1:-1]
        average_volume = sum(row['v'] for session, row in baseline) / p['lookback']
        volume_ratio = event['v'] / average_volume
        if volume_ratio < p['volume_ratio_min']:
            continue
        quote = fresh_quote(ctx, symbol, now)
        if quote is None:
            continue
        bid, ask = quote
        spread_fraction = (ask - bid) / ((ask + bid) / 2.0)
        if spread_fraction > 0.001 or bid < event['o']:
            continue
        # Prefer cheaper execution, not the largest historical price shock.
        candidates.append((spread_fraction, symbol, event_key, gap, volume_ratio))

    if not candidates:
        return answer('No unattempted prior-session gap satisfies the fixed volume, close and execution checks.', memory)

    spread, symbol, event_key, gap, volume_ratio = min(candidates)
    # An attempt is not a fill. Do not repeatedly resubmit a refused event;
    # actual positions, never this memory marker, drive the holding clock.
    attempted[symbol] = event_key
    intent = {
        'symbol': symbol,
        'side': 'buy',
        'notional_usd': budget,
        'type': 'market',
        'reason': (
            f'Price-defined continuation test: prior-session gap {gap:.2%}, '
            f'volume {volume_ratio:.2f}x its preceding 20-session average, '
            'and a strong close. No earnings event is inferred.'
        ),
    }
    return answer('Submitting one small fractional continuation test; its edge is unproven.', memory, intents=[intent])

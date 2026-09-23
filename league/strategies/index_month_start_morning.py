import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo


NEEDS = {
    'venue': 'alpaca',
    'horizon': 'day',
    'style': 'month-start-calendar-flow',
    'symbols': ['SPY'],
    'bars': {'timeframe': '1Day', 'limit': 40},
    'wake_minutes': 5,
    'parameter_rules': {
        'bounds': {
            'notional_usd': [2.0, 2.0],
            'first_sessions': [3, 3],
            'entry_start_minute': [585, 585],
            'entry_end_minute': [600, 600],
            'flat_at': [765, 765],
            'max_spread': [0.0001, 0.0005],
        },
        'ordered': [
            ['entry_start_minute', 'entry_end_minute', 'flat_at'],
        ],
        'frozen': [
            'notional_usd', 'first_sessions', 'entry_start_minute',
            'entry_end_minute', 'flat_at',
        ],
    },
}

PARAMS = {
    'notional_usd': 2.0,
    'first_sessions': 3,
    'entry_start_minute': 585,
    'entry_end_minute': 600,
    'flat_at': 765,
    'max_spread': 0.0003,
}

NY = ZoneInfo('America/New_York')
SYMBOL = 'SPY'


def number(value):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result
    except (ValueError, TypeError, OverflowError):
        return None


def answer(memory, thought, intents=None, cancels=None):
    return {
        'intents': intents or [],
        'cancels': (cancels or [])[:20],
        'thought': thought,
        'memory': memory,
    }


def session_number(ctx, today):
    # Equity daily timestamps identify their New York sessions. The House
    # supplies completed daily bars only after the following midnight.
    dates = set()
    for bar in ctx.get('bars', {}).get(SYMBOL, [])[-40:]:
        stamp = timestamp(bar.get('t'))
        close = number(bar.get('c'))
        volume = number(bar.get('v'))
        if stamp is None or close is None or close <= 0:
            continue
        if volume is None or volume <= 0:
            continue
        day = stamp.astimezone(NY).date()
        if day < today and day.weekday() < 5:
            dates.add(day)
    if len(dates) < 15:
        return None
    if (today - max(dates)).days > 6:
        return None
    month = (today.year, today.month)
    if not any((day.year, day.month) < month for day in dates):
        return None
    completed = sum(1 for day in dates if (day.year, day.month) == month)
    return completed + 1


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params') or {})
    previous = ctx.get('memory') or {}
    memory = {
        'attempt_day': str(previous.get('attempt_day', ''))[:10],
        'last_refusal': str(previous.get('last_refusal', ''))[:180],
    }
    for outcome in ctx.get('recent_order_outcomes', [])[-12:]:
        if outcome.get('status') == 'refused':
            memory['last_refusal'] = str(outcome.get('reason', 'refused'))[:180]

    orders = [
        order for order in ctx.get('open_orders', [])
        if order.get('symbol') == SYMBOL
    ]
    now = timestamp(ctx.get('now'))
    if now is None:
        cancels = [
            order['order_id'] for order in orders
            if order.get('side') == 'buy' and order.get('order_id')
        ]
        return answer(memory, 'No valid decision clock; withdraw working entries.', cancels=cancels)

    local = now.astimezone(NY)
    today = local.date()
    day_key = today.isoformat()
    minute = local.hour * 60 + local.minute
    regular = local.weekday() < 5 and 570 <= minute < 960
    entry_clock = regular and params['entry_start_minute'] <= minute < params['entry_end_minute']

    positions = []
    quantity = Decimal('0')
    carried = False
    for position in ctx.get('positions', []):
        if position.get('symbol') != SYMBOL:
            continue
        held = number(position.get('quantity'))
        if held is None or held <= 0:
            continue
        positions.append(position)
        quantity += Decimal(str(held))
        opened = timestamp(position.get('opened_at'))
        if opened is None or opened.astimezone(NY).date() != today:
            carried = True

    # Await cancellation/fill confirmation instead of spending released cash
    # or submitting overlapping exits in the same decision.
    if orders:
        cancels = []
        for order in orders:
            submitted = timestamp(order.get('submitted_at'))
            age = None if submitted is None else (now - submitted).total_seconds()
            expired = age is None or age < 0 or age >= 600
            cancel_buy = order.get('side') == 'buy' and (not entry_clock or bool(positions))
            if (expired or cancel_buy) and order.get('order_id'):
                cancels.append(order['order_id'])
        return answer(
            memory,
            'Manage the existing order before submitting another; cancellations do not release capacity yet.',
            cancels=cancels,
        )

    if not regular:
        return answer(memory, 'Outside the regular-session clock; no new order.')

    quote = ctx.get('quotes', {}).get(SYMBOL) or {}
    bid = number(quote.get('bid'))
    ask = number(quote.get('ask'))
    quote_time = timestamp(quote.get('t'))
    quote_age = None if quote_time is None else (now - quote_time).total_seconds()
    fresh = (
        bid is not None and ask is not None and 0 < bid <= ask
        and quote_age is not None and 0 <= quote_age <= 90
    )
    if not fresh:
        return answer(memory, 'No fresh two-sided SPY quote; do not submit an order against stale inputs.')

    if positions:
        if carried or minute >= params['flat_at']:
            sell_quantity = float(quantity.quantize(Decimal('0.000000001'), rounding=ROUND_DOWN))
            if sell_quantity <= 0:
                return answer(memory, 'Residual holding is below the fractional quantity step.')
            reason = 'Close a carried calendar position at the next fresh regular-session quote.' if carried else 'End the fixed month-start morning holding window.'
            return answer(memory, reason, intents=[{
                'symbol': SYMBOL,
                'side': 'sell',
                'quantity': sell_quantity,
                'type': 'market',
                'reason': reason,
            }])
        return answer(memory, 'Hold the single calendar exposure until its fixed morning exit.')

    if not entry_clock:
        return answer(memory, 'Flat outside the fixed 09:45-10:00 entry window.')
    if memory['attempt_day'] == day_key:
        return answer(memory, 'The single entry attempt for this session is already used; do not retry refusals or churn.')

    ordinal = session_number(ctx, today)
    if ordinal is None:
        return answer(memory, 'Completed daily history is insufficient or stale for identifying the month-start sessions.')
    if ordinal > params['first_sessions']:
        return answer(memory, 'This is not one of the first three observed trading sessions of the month.')

    midpoint = (bid + ask) / 2.0
    if (ask - bid) / midpoint > params['max_spread']:
        return answer(memory, 'The quoted spread exceeds the calendar test execution budget.')

    limits = ctx.get('limits') or {}
    cash = number(ctx.get('cash'))
    order_cap = number(limits.get('max_order_usd'))
    position_cap = number(limits.get('max_position_usd'))
    if cash is None or order_cap is None or position_cap is None:
        return answer(memory, 'Cash or capacity is unavailable; remain flat.')
    budget = min(params['notional_usd'], cash * 0.995, order_cap, position_cap)
    budget = math.floor(max(0.0, budget) * 100.0) / 100.0
    rules = (ctx.get('venue_rules') or {}).get(SYMBOL) or {}
    minimum = number(rules.get('min_order_usd', 0.01))
    if minimum is None or minimum < 0 or budget < max(0.01, minimum):
        return answer(memory, 'Available allocation cannot meet the known venue minimum without exceeding capacity.')

    memory['attempt_day'] = day_key
    reason = 'Test month-start investment flows in session ' + str(ordinal) + ' with a capped fractional SPY position and a 12:45 exit.'
    return answer(memory, reason, intents=[{
        'symbol': SYMBOL,
        'side': 'buy',
        'notional_usd': budget,
        'type': 'market',
        'reason': reason,
    }])

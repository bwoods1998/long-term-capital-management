import datetime
import math
from zoneinfo import ZoneInfo


NEEDS = {
    'venue': 'alpaca',
    'horizon': 'day',
    'style': 'month-start-cash-flow',
    'symbols': ['SPY'],
    'bars': {'timeframe': '1Day', 'limit': 32},
    'wake_minutes': 5,
    'parameter_rules': {
        'bounds': {
            'hold_sessions': [2, 4],
            'max_relative_spread': [0.0001, 0.001],
        },
        'frozen': ['notional_usd'],
    },
}

PARAMS = {
    'hold_sessions': 3,
    'max_relative_spread': 0.0005,
    'notional_usd': 2.0,
}


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
        result = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError, OverflowError):
        return None
    if result.tzinfo is None:
        return None
    return result


def response(thought, memory, intents=None, cancels=None):
    return {
        'intents': intents or [],
        'cancels': cancels or [],
        'thought': thought,
        'memory': memory,
    }


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params') or {})
    old = ctx.get('memory') or {}
    orders = [
        row for row in (ctx.get('open_orders') or [])
        if row.get('symbol') == 'SPY'
    ]
    positions = [
        row for row in (ctx.get('positions') or [])
        if row.get('symbol') == 'SPY' and number(row.get('quantity')) > 0
    ]
    now = timestamp(ctx.get('now'))
    if now is None:
        cancels = [
            row['order_id'] for row in orders
            if row.get('side') == 'buy' and row.get('order_id')
        ][:20]
        return response('The clock is unavailable; cancel entries and request no new exposure.', old, cancels=cancels)

    ny = ZoneInfo('America/New_York')
    local = now.astimezone(ny)
    today = local.date()
    month = today.strftime('%Y-%m')
    same_month = old.get('month') == month
    memory = {
        'month': month,
        'attempts': max(0, min(3, int(number(old.get('attempts'))))) if same_month else 0,
        'used': bool(old.get('used')) if same_month else False,
        'last_attempt': old.get('last_attempt', '') if same_month else '',
        'refusals': [],
    }

    # Compare owned outcomes with the previous wake, including refusal-only
    # outcomes that never became exchange orders. Keep the memory bounded.
    known_refusals = old.get('refusals') or []
    new_refusal = False
    for outcome in (ctx.get('recent_order_outcomes') or [])[-12:]:
        if outcome.get('status') != 'refused':
            continue
        if outcome.get('submitted_to_venue') is not False:
            continue
        signature = (
            str(outcome.get('order_id', ''))[:80]
            + '|'
            + str(outcome.get('reason', ''))[:180]
        )
        memory['refusals'].append(signature)
        if signature not in known_refusals:
            new_refusal = True
    if new_refusal and memory['attempts'] > 0:
        memory['attempts'] = 3
    if positions:
        memory['used'] = True

    minute = local.hour * 60 + local.minute
    weekday = local.weekday() < 5
    regular_clock = weekday and 575 <= minute <= 955
    entry_clock = weekday and 585 <= minute <= 610

    quote = (ctx.get('quotes') or {}).get('SPY') or {}
    bid = number(quote.get('bid'))
    ask = number(quote.get('ask'))
    quoted_at = timestamp(quote.get('t'))
    quote_age = (now - quoted_at).total_seconds() if quoted_at is not None else None
    fresh_quote = (
        bid > 0 and ask >= bid and quote_age is not None
        and 0 <= quote_age <= 60
    )
    relative_spread = (ask - bid) / ((ask + bid) / 2.0) if fresh_quote else None
    entry_quote = (
        fresh_quote
        and relative_spread <= number(params['max_relative_spread'])
    )

    # Alpaca equity daily bars are session-stamped. Ignore any current-day,
    # future or invalid row; daily information must already be available.
    session_dates = set()
    for bar in ((ctx.get('bars') or {}).get('SPY') or [])[-32:]:
        bar_time = timestamp(bar.get('t'))
        if bar_time is None or bar_time > now or number(bar.get('c')) <= 0:
            continue
        session_date = bar_time.astimezone(ny).date()
        if session_date < today and session_date.weekday() < 5:
            session_dates.add(session_date)
    sessions = sorted(session_dates)
    prior_month_end = today.replace(day=1) - datetime.timedelta(days=1)
    first_session = False
    if sessions:
        latest = sessions[-1]
        first_session = (
            (latest.year, latest.month) == (prior_month_end.year, prior_month_end.month)
            and 0 < (today - latest).days <= 7
            and today.day <= 7
        )
    eligible = entry_clock and first_session and entry_quote and not memory['used']

    # Never replace an order in the wake that requests its cancellation.
    # A market order can still be pending or partially filled at a wake.
    cancels = []
    for order in orders:
        submitted = timestamp(order.get('submitted_at'))
        age = (now - submitted).total_seconds() if submitted is not None else None
        stale = age is None or age < 0 or age >= 600
        cancel = False
        if order.get('side') == 'buy':
            cancel = stale or bool(positions) or not eligible
        elif order.get('side') == 'sell':
            cancel = stale or not positions
        if cancel and order.get('order_id'):
            cancels.append(order['order_id'])
    if orders:
        return response(
            'An order is still outstanding; manage it before making another commitment.',
            memory,
            cancels=cancels[:20],
        )

    if positions:
        quantity = sum(number(row.get('quantity')) for row in positions)
        opened_dates = []
        unknown_age = False
        for position in positions:
            opened = timestamp(position.get('opened_at'))
            if opened is None or opened > now:
                unknown_age = True
            else:
                opened_dates.append(opened.astimezone(ny).date())
        due = unknown_age or not opened_dates
        held_sessions = 0
        if opened_dates:
            opened_date = min(opened_dates)
            held_sessions = sum(1 for day in sessions if day >= opened_date) + 1
            target = int(params['hold_sessions'])
            due = (
                due
                or (today - opened_date).days >= 8
                or held_sessions > target
                or (held_sessions == target and minute >= 940)
            )
        if due and regular_clock and fresh_quote:
            return response(
                'The calendar holding window has ended; request liquidation without an exit spread veto.',
                memory,
                intents=[{
                    'symbol': 'SPY',
                    'side': 'sell',
                    'quantity': quantity,
                    'type': 'market',
                    'reason': 'Month-start holding deadline or overdue-position safeguard; close the existing fractional holding.',
                }],
            )
        return response(
            'Hold the single calendar exposure until its session deadline, or wait for a fresh regular-session quote to exit.',
            memory,
        )

    if not eligible:
        return response(
            'No entry: require an unused first trading session of the month, the entry clock, and a fresh narrow quote.',
            memory,
        )
    if memory['attempts'] >= 3:
        return response(
            'Entry attempts are exhausted or a House refusal paused this month; do not force another order.',
            memory,
        )
    last_attempt = timestamp(memory['last_attempt'])
    if last_attempt is not None and (now - last_attempt).total_seconds() < 900:
        return response('Wait before retrying an unconfirmed entry request.', memory)

    limits = ctx.get('limits') or {}
    cash = max(0.0, number(ctx.get('cash')))
    budget = min(
        number(params['notional_usd']),
        max(0.0, number(limits.get('max_order_usd'))),
        max(0.0, number(limits.get('max_position_usd'))),
        cash * 0.99,
    )
    budget = math.floor(max(0.0, budget) * 100.0) / 100.0
    rules = (ctx.get('venue_rules') or {}).get('SPY') or {}
    minimum = max(0.01, number(rules.get('min_order_usd'), 0.01))
    if budget < minimum:
        return response(
            'Available cash and House limits cannot fund the venue minimum; never increase the allocation to force entry.',
            memory,
        )

    memory['attempts'] += 1
    memory['last_attempt'] = now.isoformat()
    return response(
        'Test month-start cash-flow demand with one small fractional SPY purchase; this is a hypothesis, not an established edge.',
        memory,
        intents=[{
            'symbol': 'SPY',
            'side': 'buy',
            'notional_usd': budget,
            'type': 'market',
            'reason': 'First observed trading session of the month; bounded fractional exposure to the month-start cash-flow hypothesis.',
        }],
    )

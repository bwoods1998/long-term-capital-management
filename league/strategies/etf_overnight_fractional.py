import math
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo


NEEDS = {
    'venue': 'alpaca',
    'horizon': 'day',
    'style': 'calendar-overnight',
    'symbols': ['SPY', 'DIA'],
    'bars': {'timeframe': '5Min', 'limit': 12},
    'wake_minutes': 5,
    'parameter_rules': {
        'bounds': {
            'notional_usd': [1.0, 10.0],
            'max_spread_bps': [1.0, 5.0],
            'quote_age_seconds': [30, 300],
        },
        'frozen': ['notional_usd', 'quote_age_seconds'],
    },
}

PARAMS = {
    'notional_usd': 2.0,
    'max_spread_bps': 3.0,
    'quote_age_seconds': 120,
}


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def observed_day(day):
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def nth_weekday(year, month, weekday, occurrence):
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def easter(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    total = h + l - 7 * m + 114
    return date(year, total // 31, total % 31 + 1)


def session_close(day):
    # Standard NYSE calendar, not an authoritative exceptional-closure feed.
    # Fresh market data is independently required before submitting an order.
    if day.weekday() >= 5:
        return None
    year = day.year
    new_year = date(year, 1, 1)
    memorial = date(year, 5, 31)
    memorial -= timedelta(days=memorial.weekday())
    thanksgiving = nth_weekday(year, 11, 3, 4)
    holidays = {
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        easter(year) - timedelta(days=2),
        memorial,
        observed_day(date(year, 7, 4)),
        nth_weekday(year, 9, 0, 1),
        thanksgiving,
        observed_day(date(year, 12, 25)),
    }
    # NYSE does not observe a Saturday New Year on the preceding Friday.
    if new_year.weekday() != 5:
        holidays.add(observed_day(new_year))
    if year >= 2022:
        holidays.add(observed_day(date(year, 6, 19)))
    if day in holidays:
        return None
    if day == thanksgiving + timedelta(days=1):
        return 13 * 60
    if (day.month, day.day) in ((7, 3), (12, 24)):
        return 13 * 60
    return 16 * 60


def fresh_book(ctx, symbol, now, max_age):
    quote = (ctx.get('quotes') or {}).get(symbol) or {}
    bid = number(quote.get('bid'))
    ask = number(quote.get('ask'))
    stamped = timestamp(quote.get('t'))
    if stamped is None or not 0 < bid <= ask:
        return None
    age = (now - stamped).total_seconds()
    if not 0 <= age <= max_age:
        return None
    spread_bps = 10000.0 * (ask - bid) / ((ask + bid) / 2.0)
    return spread_bps


def recent_traded_bar(ctx, symbol, now, local_day):
    bars = (ctx.get('bars') or {}).get(symbol) or []
    if not bars:
        return False
    bar = bars[-1]
    stamped = timestamp(bar.get('t'))
    if stamped is None:
        return False
    age = (now - stamped).total_seconds()
    return (
        0 <= age <= 600
        and stamped.astimezone(ZoneInfo('America/New_York')).date() == local_day
        and number(bar.get('c')) > 0
        and number(bar.get('v')) > 0
    )


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params') or {})
    old_memory = ctx.get('memory') or {}
    memory = {}
    for key in ('entry_attempt_date', 'last_refusal'):
        if isinstance(old_memory.get(key), str):
            memory[key] = old_memory[key][:240]
    # A refusal is not a venue order or fill. Entry attempts are not retried
    # repeatedly that day; exits may retry after outstanding orders disappear.
    for outcome in ctx.get('recent_order_outcomes') or []:
        if outcome.get('status') == 'refused':
            prefix = 'House: ' if outcome.get('submitted_to_venue') is False else 'Refused: '
            memory['last_refusal'] = prefix + str(outcome.get('reason', 'unspecified'))[:200]

    intents = []
    cancels = []

    def answer(thought):
        return {
            'intents': intents,
            'cancels': cancels,
            'thought': thought,
            'memory': memory,
        }

    now = timestamp(ctx.get('now'))
    if now is None:
        return answer('No valid decision timestamp; no order submitted.')
    local = now.astimezone(ZoneInfo('America/New_York'))
    today = local.date()
    day_key = today.isoformat()
    minute = local.hour * 60 + local.minute
    close_minute = session_close(today)
    regular_session = close_minute is not None and 575 <= minute < close_minute
    entry_window = close_minute == 960 and 950 <= minute < 955
    symbols = NEEDS['symbols']
    positions = [
        position for position in ctx.get('positions') or []
        if position.get('symbol') in symbols and number(position.get('quantity')) > 0
    ]
    orders = [
        order for order in ctx.get('open_orders') or []
        if order.get('symbol') in symbols
    ]

    # Never spend a pending cancellation's cash or replace an unconfirmed order.
    if orders:
        for order in orders:
            submitted = timestamp(order.get('submitted_at'))
            age = (now - submitted).total_seconds() if submitted is not None else None
            is_buy = order.get('side') == 'buy'
            expired = age is None or age < 0 or age >= (300 if is_buy else 600)
            invalid_buy = is_buy and (not entry_window or bool(positions))
            order_id = order.get('order_id')
            if order_id and (expired or invalid_buy) and len(cancels) < 20:
                cancels.append(order_id)
        return answer('Waiting for owned orders to finish; stale commitments are cancelled without replacement in this decision.')

    max_age = number(params['quote_age_seconds'])
    if positions:
        if not regular_session:
            return answer('Holding the overnight exposure until an available session after 09:35 New York.')
        for position in positions[:8]:
            opened = timestamp(position.get('opened_at'))
            # Unknown entry age is handled conservatively by flattening in-session.
            if opened is not None:
                opened_day = opened.astimezone(ZoneInfo('America/New_York')).date()
                if opened_day >= today:
                    continue
            symbol = position['symbol']
            if fresh_book(ctx, symbol, now, max_age) is None:
                continue
            quantity = math.floor(number(position.get('quantity')) * 1000000000) / 1000000000
            if quantity <= 0:
                continue
            intents.append({
                'symbol': symbol,
                'side': 'sell',
                'quantity': quantity,
                'type': 'market',
                'reason': 'Close the prior-session overnight holding after 09:35 New York; no new directional forecast.',
            })
        if intents:
            return answer('Closing overnight holdings using fresh quotes; the entry spread filter never blocks a scheduled exit.')
        return answer('Holding a same-day entry, or waiting for a fresh executable quote for the scheduled exit.')

    if not entry_window:
        return answer('Flat outside the fixed 15:50-15:55 normal-session entry window.')
    if memory.get('entry_attempt_date') == day_key:
        return answer('Already attempted an entry today; no repeated purchases or refusal loop.')

    eligible = []
    for symbol in symbols:
        spread = fresh_book(ctx, symbol, now, max_age)
        if spread is None or spread > number(params['max_spread_bps']):
            continue
        if not recent_traded_bar(ctx, symbol, now, today):
            continue
        eligible.append((spread, symbol))
    if not eligible:
        return answer('No ETF has both a fresh narrow quote and a recent traded bar; stay flat rather than force an overnight observation.')

    limits = ctx.get('limits') or {}
    budget = min(
        number(params['notional_usd']),
        max(0.0, number(ctx.get('cash'))) * 0.98,
        max(0.0, number(limits.get('max_order_usd'))),
        max(0.0, number(limits.get('max_position_usd'))),
    )
    budget = math.floor(budget * 100) / 100
    if budget < 1.0:
        return answer('Available cash or account limits cannot fund a one-dollar fractional entry with a cash reserve.')

    eligible.sort()
    symbol = eligible[0][1]
    memory['entry_attempt_date'] = day_key
    intents.append({
        'symbol': symbol,
        'side': 'buy',
        'notional_usd': budget,
        'type': 'market',
        'reason': 'Small fractional close-to-next-open calendar test; choose the tighter eligible ETF book and exit next session after 09:35.',
    })
    return answer('Testing the overnight calendar hypothesis with one capped fractional exposure, not a fitted price-pattern signal.')

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


NEEDS = {
    'venue': 'alpaca',
    'horizon': 'day',
    'style': 'overnight-calendar',
    'symbols': ['DIA'],
    'bars': {'timeframe': '5Min', 'limit': 80},
    'wake_minutes': 5,
    'parameter_rules': {
        'bounds': {'max_spread_bps': [1.0, 4.0]},
        'frozen': ['notional_usd'],
    },
}

PARAMS = {'notional_usd': 2.0, 'max_spread_bps': 2.0}


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


def reply(thought, memory, intents=None, cancels=None):
    return {
        'intents': intents or [],
        'cancels': cancels or [],
        'thought': thought,
        'memory': memory,
    }


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params') or {})
    previous = ctx.get('memory') or {}
    memory = {
        'last_entry_session': str(previous.get('last_entry_session') or '')[:10],
        'last_late_exit_session': str(previous.get('last_late_exit_session') or '')[:10],
        'last_refusal': str(previous.get('last_refusal') or '')[:180],
    }
    for outcome in ctx.get('recent_order_outcomes') or []:
        if outcome.get('status') == 'refused' and outcome.get('submitted_to_venue') is False:
            memory['last_refusal'] = str(outcome.get('reason') or 'House refusal')[:180]

    now = timestamp(ctx.get('now'))
    if now is None:
        return reply('No valid decision timestamp; no orders are generated.', memory)

    ny = ZoneInfo('America/New_York')
    local = now.astimezone(ny)
    session = local.date().isoformat()
    minute = local.hour * 60 + local.minute
    regular = local.weekday() < 5 and 570 <= minute < 960
    entry_window = regular and 950 <= minute <= 955

    pending = [o for o in (ctx.get('open_orders') or []) if o.get('symbol') == 'DIA']
    if pending:
        cancels = []
        for order in pending:
            submitted = timestamp(order.get('submitted_at'))
            age = None if submitted is None else (now - submitted).total_seconds()
            stale = age is None or age < 0 or age >= 300
            outside = not regular or (order.get('side') == 'buy' and not entry_window)
            order_id = order.get('order_id')
            if (stale or outside) and isinstance(order_id, str) and order_id:
                cancels.append(order_id)
        return reply(
            'An existing DIA order blocks new orders; stale or out-of-window orders are canceled without assuming cancellation has completed.',
            memory,
            cancels=cancels[:20],
        )

    holdings = [p for p in (ctx.get('positions') or [])
                if p.get('symbol') == 'DIA' and number(p.get('quantity')) > 0]
    quantity = sum(number(p.get('quantity')) for p in holdings)
    due = False
    for position in holdings:
        opened = timestamp(position.get('opened_at'))
        opened_session = opened.astimezone(ny).date().isoformat() if opened else memory['last_entry_session']
        if opened_session != session:
            due = True

    if not regular:
        return reply('Outside the regular weekday session; existing equity exposure waits for an eligible session.', memory)
    if quantity > 0 and not due:
        return reply('The position was opened this session and is being held overnight.', memory)
    if quantity > 0 and minute < 575:
        return reply('An overnight exit is due, but execution waits until 09:35 New York time.', memory)
    if quantity <= 0:
        if not entry_window:
            return reply('Flat outside the fixed 15:50–15:55 overnight entry window.', memory)
        if memory['last_entry_session'] == session:
            return reply('This session already had an entry attempt; no repeated submission follows a refusal or fill.', memory)
        if memory['last_late_exit_session'] == session:
            return reply('A late exit occurred in this entry window; skip an immediate sell-and-rebuy cycle.', memory)

    quote = (ctx.get('quotes') or {}).get('DIA') or {}
    bid = number(quote.get('bid'))
    ask = number(quote.get('ask'))
    quoted = timestamp(quote.get('t'))
    quote_age = None if quoted is None else (now - quoted).total_seconds()
    if not (0 < bid <= ask) or quote_age is None or not 0 <= quote_age <= 120:
        return reply('No fresh, valid two-sided DIA quote; the entry or pending exit waits for usable data.', memory)

    bars = (ctx.get('bars') or {}).get('DIA') or []
    bar = bars[-1] if bars else {}
    stamped = timestamp(bar.get('t'))
    if stamped is None:
        return reply('No timestamped closed DIA bar confirms an active session.', memory)
    bar_local = stamped.astimezone(ny)
    bar_minute = bar_local.hour * 60 + bar_local.minute
    bar_age = (now - stamped).total_seconds()
    if (bar_local.date() != local.date() or not 570 <= bar_minute < 960
            or not 0 <= bar_age <= 600 or number(bar.get('c')) <= 0):
        return reply('Closed bars do not confirm a fresh regular session; do not infer that a holiday or early-close market is open.', memory)

    limits = ctx.get('limits') or {}
    order_cap = max(0.0, number(limits.get('max_order_usd')))
    if quantity > 0:
        if order_cap <= 0:
            return reply('An overnight exit is due, but no positive order allowance is supplied.', memory)
        # Use the ask as a conservative notional estimate for a sale.
        sell_quantity = quantity
        if quantity * ask > order_cap:
            sell_quantity = math.floor(0.98 * order_cap / ask * 1000000000) / 1000000000
        if sell_quantity <= 0:
            return reply('The supplied order allowance cannot represent a positive fractional exit.', memory)
        if minute >= 950:
            memory['last_late_exit_session'] = session
        return reply(
            'Submit the scheduled overnight exit; a partial exit remains due on the next wake.',
            memory,
            intents=[{
                'symbol': 'DIA',
                'side': 'sell',
                'quantity': sell_quantity,
                'type': 'market',
                'reason': 'Overnight calendar control: close prior-session exposure from 09:35 on the next eligible regular session.',
            }],
        )

    midpoint = (bid + ask) / 2.0
    spread_bps = (ask - bid) / midpoint * 10000.0
    if spread_bps > number(params.get('max_spread_bps')):
        return reply('The DIA spread exceeds the entry cost ceiling; no overnight position is opened.', memory)

    # Equities are commission-free in the supplied contract. Market notional
    # permits fractional shares; whole-share limits would strand this stake.
    budget = min(
        max(0.0, number(params.get('notional_usd'))),
        max(0.0, number(ctx.get('cash'))),
        max(0.0, number(limits.get('max_position_usd'))),
        order_cap,
    )
    budget = math.floor(budget * 100.0) / 100.0
    if budget < 1.0:
        return reply('Cash or House limits leave less than the conservative one-dollar fractional entry minimum.', memory)

    # This records an attempt, never an assumed fill. Refusals remain visible
    # in memory and cannot trigger repeated orders during the same session.
    memory['last_entry_session'] = session
    return reply(
        'Submit one capped fractional DIA entry to test overnight drift after the observed spread; profitability is not assumed.',
        memory,
        intents=[{
            'symbol': 'DIA',
            'side': 'buy',
            'notional_usd': budget,
            'type': 'market',
            'reason': 'Fixed overnight calendar control: enter at 15:50–15:55 New York with a narrow fresh spread and exit next eligible session from 09:35.',
        }],
    )

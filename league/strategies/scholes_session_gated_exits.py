import datetime
import zoneinfo

NEEDS = {
    'venue': 'alpaca',
    'horizon': 'hour',
    'style': 'intraday-first-hour-momentum',
    'symbols': ['SPY', 'QQQ', 'IWM', 'DIA'],
    'bars': {'timeframe': '5Min', 'limit': 150},
    'wake_minutes': 5,
}
PARAMS = {}


def parse_time(value):
    try:
        return datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, TypeError, ValueError):
        return None


def decide(ctx):
    tz = zoneinfo.ZoneInfo('America/New_York')
    now = parse_time(ctx.get('now'))
    memory = ctx.get('memory') or {}
    if now is None:
        return {'intents': [], 'cancels': [], 'thought': 'Clock unavailable; abstain.', 'memory': memory}
    now = now.astimezone(tz)
    minute = now.hour * 60 + now.minute
    today = now.date().isoformat()
    if now.weekday() >= 5 or not 570 <= minute < 960:
        return {'intents': [], 'cancels': [],
                'thought': 'Outside weekday regular session hours; defer market orders and retain any overdue exit for the next eligible wake.',
                'memory': memory}
    symbols = NEEDS['symbols']
    positions = [p for p in (ctx.get('positions') or [])
                 if p.get('symbol') in symbols and float(p.get('quantity', 0) or 0) > 0]
    orders = ctx.get('open_orders') or []

    if positions:
        exits = []
        for p in positions:
            sym = p.get('symbol')
            if any(o.get('symbol') == sym and o.get('side') == 'sell' for o in orders):
                continue
            opened = parse_time(p.get('opened_at'))
            if opened is None:
                continue
            opened = opened.astimezone(tz)
            if now.date() > opened.date() or minute >= 950:
                qty = float(p.get('quantity', 0) or 0)
                if qty > 0:
                    exits.append({'symbol': sym, 'side': 'sell', 'quantity': qty, 'type': 'market',
                                  'reason': 'Close the intraday momentum position before the ETF session ends'})
        return {'intents': exits, 'cancels': [],
                'thought': 'Manage the existing same-day position; do not add while invested.', 'memory': memory}

    if minute < 600 or minute > 900:
        return {'intents': [], 'cancels': [],
                'thought': 'Wait for the intraday momentum entry window or the scheduled close.', 'memory': memory}
    if (memory.get('entry_day') == today or
            any(o.get('side') == 'buy' and o.get('symbol') in symbols for o in orders)):
        return {'intents': [], 'cancels': [], 'thought': 'Already entered or have a pending entry today.', 'memory': memory}

    candidates = []
    for sym in symbols:
        rows = (ctx.get('bars') or {}).get(sym) or []
        session = []
        for bar in rows:
            stamp = parse_time(bar.get('t'))
            if stamp is None:
                continue
            local = stamp.astimezone(tz)
            if local.date() == now.date() and 570 <= local.hour * 60 + local.minute <= minute:
                try:
                    close = float(bar.get('c'))
                    if close > 0:
                        session.append((stamp, close))
                except (TypeError, ValueError):
                    pass
        if len(session) < 7:
            continue
        session.sort(key=lambda item: item[0])
        latest_time, latest_close = session[-1]
        if (now - latest_time.astimezone(tz)).total_seconds() > 600:
            continue
        momentum = latest_close / session[-7][1] - 1.0
        if momentum > 0:
            candidates.append((momentum, sym))

    if not candidates:
        return {'intents': [], 'cancels': [], 'thought': 'No ETF has positive 30-minute momentum; abstain.', 'memory': memory}
    momentum, sym = max(candidates)
    limits = ctx.get('limits') or {}
    try:
        notional = min(75.0, max(0.0, float(ctx.get('cash', 0) or 0)),
                       float(limits.get('max_order_usd', 0) or 0),
                       float(limits.get('max_position_usd', 0) or 0))
    except (TypeError, ValueError):
        notional = 0.0
    if notional <= 0:
        return {'intents': [], 'cancels': [], 'thought': 'No available entry capacity.', 'memory': memory}
    new_memory = dict(memory)
    new_memory['entry_day'] = today
    return {'intents': [{'symbol': sym, 'side': 'buy', 'notional_usd': notional, 'type': 'market',
                         'reason': 'Buy the strongest broad ETF with positive 30-minute intraday momentum'}],
            'cancels': [],
            'thought': 'Select the strongest positive 30-minute ETF momentum and close the position before the bell.',
            'memory': new_memory}

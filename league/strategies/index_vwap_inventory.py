import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


NEEDS = {
    'venue': 'alpaca',
    'horizon': 'day',
    'style': 'intraday-vwap-inventory',
    'symbols': ['SPY', 'QQQ', 'IWM'],
    'bars': {'timeframe': '5Min', 'limit': 120},
    'wake_minutes': 5,
    'parameter_rules': {
        'bounds': {
            'discount_fraction': [0.003, 0.008],
            'stop_loss_pct': [0.005, 0.015],
            'spread_fraction': [0.0001, 0.001]
        },
        'frozen': ['notional_usd']
    }
}

PARAMS = {
    'discount_fraction': 0.004,
    'stop_loss_pct': 0.008,
    'spread_fraction': 0.0005,
    'notional_usd': 2.0
}


def number(value, default=None):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            return None
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def quote(ctx, symbol, now):
    row = (ctx.get('quotes') or {}).get(symbol) or {}
    bid = number(row.get('bid'))
    ask = number(row.get('ask'))
    when = stamp(row.get('t'))
    if bid is None or ask is None or when is None:
        return None
    if not 0 < bid <= ask or not 0 <= (now - when).total_seconds() <= 30:
        return None
    return bid, ask


def session_vwap(ctx, symbol, now, local):
    weighted = 0.0
    volume = 0.0
    count = 0
    newest = None
    seen = set()
    for bar in (ctx.get('bars') or {}).get(symbol, [])[-120:]:
        when = stamp(bar.get('t'))
        if when is None or when > now or when in seen:
            continue
        seen.add(when)
        clock = when.astimezone(ZoneInfo('America/New_York'))
        minute = clock.hour * 60 + clock.minute
        if clock.date() != local.date() or not 570 <= minute < 960:
            continue
        high = number(bar.get('h'))
        low = number(bar.get('l'))
        close = number(bar.get('c'))
        size = number(bar.get('v'))
        if None in (high, low, close, size):
            continue
        if not 0 < low <= close <= high or size <= 0:
            continue
        weighted += ((high + low + close) / 3.0) * size
        volume += size
        count += 1
        newest = when if newest is None or when > newest else newest
    if count < 6 or volume <= 0 or newest is None:
        return None
    if (now - newest).total_seconds() > 600:
        return None
    result = weighted / volume
    return result if math.isfinite(result) and result > 0 else None


def grid(ctx, symbol, price):
    rules = (ctx.get('venue_rules') or {}).get(symbol) or {}
    step = number(rules.get('price_increment'))
    return step if step is not None and step > 0 else (0.01 if price >= 1 else 0.0001)


def down(price, step):
    return round(math.floor(price / step + 1e-9) * step, 10)


def up(price, step):
    return round(math.ceil(price / step - 1e-9) * step, 10)


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params') or {})
    previous = ctx.get('memory') or {}
    traded_day = previous.get('traded_day', '')
    if not isinstance(traded_day, str) or len(traded_day) > 10:
        traded_day = ''
    memory = {'traded_day': traded_day}
    intents = []
    cancels = []
    orders = ctx.get('open_orders') or []

    def finish(thought):
        return {
            'intents': intents[:8],
            'cancels': list(dict.fromkeys(cancels))[:20],
            'thought': thought,
            'memory': memory
        }

    def cancel(order):
        identity = order.get('order_id')
        if isinstance(identity, str) and identity:
            cancels.append(identity)

    now = stamp(ctx.get('now'))
    if now is None:
        for order in orders:
            if order.get('side') == 'buy':
                cancel(order)
        return finish('The decision clock is unavailable; withdraw entry orders.')
    if len(orders) > 20:
        for order in orders[:20]:
            cancel(order)
        return finish('Unexpected excess working orders; drain commitments before trading.')

    local = now.astimezone(ZoneInfo('America/New_York'))
    day = local.date().isoformat()
    minute = local.hour * 60 + local.minute
    regular = local.weekday() < 5 and 570 <= minute < 960
    entry_clock = regular and 600 <= minute <= 690
    positions = [p for p in (ctx.get('positions') or [])
                 if number(p.get('quantity'), 0.0) > 0]
    if positions or any(number(o.get('filled'), 0.0) > 0 for o in orders):
        memory['traded_day'] = day

    limits = ctx.get('limits') or {}
    equity = max(0.0, number(ctx.get('equity'), 0.0))
    ceiling = max(0.0, min(
        params['notional_usd'],
        number(limits.get('max_position_usd'), 0.0),
        number(limits.get('max_order_usd'), 0.0),
        0.49 * equity
    ))

    if positions:
        for order in orders:
            if order.get('side') == 'buy':
                cancel(order)
        for position in positions[:8]:
            symbol = position.get('symbol')
            if symbol not in NEEDS['symbols']:
                continue
            quantity = number(position.get('quantity'), 0.0)
            cost = number(position.get('average_cost'))
            opened = stamp(position.get('opened_at'))
            old = opened is None or opened.astimezone(ZoneInfo('America/New_York')).date() < local.date()
            touch = quote(ctx, symbol, now)
            stopped = (touch is not None and cost is not None and cost > 0
                       and touch[0] <= cost * (1.0 - params['stop_loss_pct']))
            urgent = old or minute >= 765 or stopped
            sells = [o for o in orders if o.get('symbol') == symbol and o.get('side') == 'sell']
            if not regular:
                continue
            if urgent:
                if sells:
                    for order in sells:
                        if order.get('type') != 'market':
                            cancel(order)
                    continue
                intents.append({
                    'symbol': symbol, 'side': 'sell', 'quantity': quantity,
                    'type': 'market',
                    'reason': 'Reduce inventory at the observed stop or session holding deadline.'
                })
                continue
            benchmark = session_vwap(ctx, symbol, now, local)
            if touch is None or benchmark is None or cost is None or cost <= 0:
                for order in sells:
                    cancel(order)
                continue
            step = grid(ctx, symbol, touch[1])
            target = up(max(benchmark, cost * 1.001), step)
            if target > touch[1] * 1.09:
                for order in sells:
                    cancel(order)
                continue
            if sells:
                if len(sells) != 1:
                    for order in sells:
                        cancel(order)
                else:
                    order = sells[0]
                    price = number(order.get('limit_price'))
                    remaining = max(0.0, number(order.get('quantity'), 0.0) - number(order.get('filled'), 0.0))
                    if price is None or abs(price - target) >= step * 0.99 or abs(remaining - quantity) > 1e-8:
                        cancel(order)
                continue
            intents.append({
                'symbol': symbol, 'side': 'sell', 'quantity': quantity,
                'type': 'limit', 'limit_price': target,
                'reason': 'Offer inventory on recovery toward session VWAP, with a gross cost cushion.'
            })
        return finish('Manage the existing inventory; no second entry is permitted this session.')

    if orders:
        buys = [o for o in orders if o.get('side') == 'buy']
        for order in orders:
            symbol = order.get('symbol')
            touch = quote(ctx, symbol, now) if symbol in NEEDS['symbols'] else None
            benchmark = session_vwap(ctx, symbol, now, local) if touch is not None else None
            submitted = stamp(order.get('submitted_at'))
            price = number(order.get('limit_price'))
            remaining = max(0.0, number(order.get('quantity'), 0.0) - number(order.get('filled'), 0.0))
            valid = (order.get('side') == 'buy' and len(buys) == 1 and entry_clock
                     and memory['traded_day'] != day and touch is not None
                     and benchmark is not None and submitted is not None and price is not None
                     and number(order.get('filled'), 0.0) == 0
                     and 0 <= (now - submitted).total_seconds() <= 900)
            if valid:
                bid, ask = touch
                step = grid(ctx, symbol, ask)
                valid = (
                    (ask - bid) / ask <= params['spread_fraction']
                    and 0 < price <= down(min(bid, benchmark * (1.0 - params['discount_fraction'])), step) + 1e-9
                    and price >= bid * 0.91
                    and abs(price - down(price, step)) < 1e-8
                    and 0 < remaining * ask <= ceiling + 1e-9
                )
            if not valid:
                cancel(order)
        return finish('Revalidate working inventory bids without spending anticipated cancellation proceeds.')

    if not entry_clock or memory['traded_day'] == day:
        return finish('Outside the fixed entry window, or this session already had a fill.')
    cash = max(0.0, number(ctx.get('cash'), 0.0))
    budget = min(ceiling, cash * 0.995)
    candidates = []
    for symbol in NEEDS['symbols']:
        touch = quote(ctx, symbol, now)
        benchmark = session_vwap(ctx, symbol, now, local)
        if touch is None or benchmark is None:
            continue
        bid, ask = touch
        spread = (ask - bid) / ask
        if spread > params['spread_fraction']:
            continue
        if ask > benchmark * (1.0 - params['discount_fraction'] / 2.0):
            continue
        step = grid(ctx, symbol, ask)
        price = down(min(bid, benchmark * (1.0 - params['discount_fraction'])), step)
        if price <= 0 or price >= ask or price < bid * 0.91:
            continue
        quantity = math.floor(budget / ask * 1000000000.0) / 1000000000.0
        rules = (ctx.get('venue_rules') or {}).get(symbol) or {}
        minimum = max(1.0, number(rules.get('min_order_usd'), 1.0))
        if quantity <= 0 or quantity * price < minimum:
            continue
        candidates.append((spread, symbol, price, quantity))
    if not candidates:
        return finish('No fresh, affordable discount to session VWAP clears the spread and price checks.')
    candidates.sort()
    spread, symbol, price, quantity = candidates[0]
    intents.append({
        'symbol': symbol, 'side': 'buy', 'quantity': quantity,
        'type': 'limit', 'limit_price': price,
        'reason': 'Supply limited morning liquidity below session VWAP; prefer the narrowest qualifying spread.'
    })
    return finish('Place one capped resting bid; recovery is a hypothesis, not an assured outcome.')

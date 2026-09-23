import math

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "overnight-drift-final-hour-entry",
    "symbols": ["SPY", "QQQ", "IWM", "DIA"],
    "bars": {"timeframe": "5Min", "limit": 500},
    "wake_minutes": 15,
}

PARAMS = {"notional_usd": 18.0}


def _num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _parts(value):
    try:
        text = str(value)
        return text[:10], int(text[11:13]) * 60 + int(text[14:16])
    except (TypeError, ValueError, IndexError):
        return None, -1


def _out(intents, thought, memory):
    return {"intents": intents, "cancels": [], "thought": thought, "memory": memory}


def decide(ctx):
    params = dict(PARAMS)
    supplied = ctx.get("params")
    if isinstance(supplied, dict):
        params.update(supplied)
    date, minute = _parts(ctx.get("now"))
    if date is None or minute < 0:
        return _out([], "Invalid timestamp; abstaining.", {})

    memory = ctx.get("memory") if isinstance(ctx.get("memory"), dict) else {}
    buy_day = memory.get("buy_day") if isinstance(memory.get("buy_day"), str) else None
    symbols = NEEDS["symbols"]
    positions = [p for p in (ctx.get("positions") or [])
                 if isinstance(p, dict) and p.get("symbol") in symbols
                 and _num(p.get("quantity")) > 0]
    working = [o for o in (ctx.get("open_orders") or [])
               if isinstance(o, dict) and o.get("symbol") in symbols]
    if working:
        return _out([], "A basket order is working; waiting for its outcome.", memory)

    exit_window = (810 <= minute <= 840) or (870 <= minute <= 900)
    entry_window = 1140 <= minute <= 1199

    if positions:
        if buy_day and buy_day != date and exit_window:
            intents = [{
                "symbol": p.get("symbol"),
                "side": "sell",
                "quantity": _num(p.get("quantity")),
                "type": "market",
                "reason": "Close prior-session overnight holdings in the planned regular-session open window."
            } for p in positions]
            return _out(intents, "Closing prior-session overnight holdings at the mapped open.", {"buy_day": buy_day, "sell_day": date})
        return _out([], "Holding the overnight basket outside its planned exit window.", memory)

    # Exiting yesterday's basket does not consume today's entry opportunity.
    if buy_day == date:
        return _out([], "Today's basket entry has already been requested.", memory)
    if not entry_window:
        return _out([], "Waiting for the final-hour close entry window.", memory)

    quotes = ctx.get("quotes") if isinstance(ctx.get("quotes"), dict) else {}
    selected = []
    for symbol in symbols:
        quote = quotes.get(symbol) if isinstance(quotes.get(symbol), dict) else {}
        bid = _num(quote.get("bid"))
        ask = _num(quote.get("ask"))
        mid = (bid + ask) / 2.0
        if mid > 0.0 and ask >= bid and (ask - bid) / mid <= 0.0025:
            selected.append(symbol)
    if not selected:
        return _out([], "No ETF quote passes the spread guard; recheck on the next eligible wake.", memory)

    limits = ctx.get("limits") if isinstance(ctx.get("limits"), dict) else {}
    max_order = _num(limits.get("max_order_usd"), 75.0)
    max_position = _num(limits.get("max_position_usd"), 100.0)
    cash = max(0.0, _num(ctx.get("cash")))
    each = min(_num(params.get("notional_usd"), 18.0), max_order, max_position, cash / float(len(selected)) * 0.98)
    each = math.floor(each * 100.0) / 100.0
    if each < 1.0:
        return _out([], "Insufficient cash or limit headroom; recheck on the next eligible wake.", memory)
    intents = [{
        "symbol": symbol,
        "side": "buy",
        "notional_usd": each,
        "type": "market",
        "reason": "Test final-hour close-to-close entry timing with a 0.25% ETF spread guard."
    } for symbol in selected]
    return _out(intents, "Entering the overnight basket during the final hour after the spread filter.", {"buy_day": date, "sell_day": None})

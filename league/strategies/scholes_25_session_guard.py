import datetime
import math
import zoneinfo

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "first-hour-etf-pullback-intraday-reversal",
    "symbols": ["SPY", "QQQ", "IWM", "DIA"],
    "bars": {"timeframe": "5Min", "limit": 500},
    "wake_minutes": 15,
    "parameter_rules": {"bounds": {"pullback_min": [0.0, 0.01]}},
}
PARAMS = {"notional_usd": 75.0, "pullback_min": 0.0005}
SYMBOLS = NEEDS["symbols"]
NY = zoneinfo.ZoneInfo("America/New_York")


def _num(x, default=0.0):
    try:
        value = float(x)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _ny(text):
    try:
        value = str(text).strip()
        if value.endswith(("Z", "z")):
            value = value[:-1] + "+00:00"
        stamp = datetime.datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=datetime.timezone.utc)
        return stamp.astimezone(NY)
    except (TypeError, ValueError, OverflowError):
        return None


def _out(intents, thought, memory):
    return {"intents": intents, "cancels": [], "thought": thought, "memory": memory}


def decide(ctx):
    params = {**PARAMS, **(ctx.get("params") or {})}
    now = _ny(ctx.get("now"))
    prior = ctx.get("memory") if isinstance(ctx.get("memory"), dict) else {}
    memory = {"buy_date": prior.get("buy_date")}
    if now is None or now.weekday() >= 5:
        return _out([], "Outside weekday trading; no entry.", memory)
    minute = now.hour * 60 + now.minute
    if not (570 <= minute < 960):
        return _out([], "Outside regular trading hours; defer market orders until the next regular session.", memory)
    today = now.strftime("%Y-%m-%d")
    positions = [p for p in (ctx.get("positions") or [])
                 if isinstance(p, dict) and p.get("symbol") in SYMBOLS and _num(p.get("quantity")) > 0]
    working = [o for o in (ctx.get("open_orders") or [])
               if isinstance(o, dict) and o.get("symbol") in SYMBOLS]
    if positions:
        exits = []
        for p in positions:
            opened = _ny(p.get("opened_at"))
            prior_day = opened is not None and opened.strftime("%Y-%m-%d") < today
            if minute >= 945 or (prior_day and minute >= 570):
                exits.append({"symbol": p["symbol"], "side": "sell", "quantity": _num(p.get("quantity")),
                              "type": "market", "reason": "Close the intraday pullback position before the session ends."})
        if exits:
            return _out(exits, "Exiting the intraday ETF position at the afternoon cutoff or after an overnight carry.", memory)
        return _out([], "Holding the selected ETF pullback until the afternoon exit window.", memory)
    if working:
        return _out([], "A relevant order is still working; wait for its outcome.", memory)
    if memory.get("buy_date") == today or not (600 <= minute <= 615):
        return _out([], "Waiting for the first-hour pullback entry window.", memory)

    bars_by_symbol = ctx.get("bars") if isinstance(ctx.get("bars"), dict) else {}
    returns = []
    for symbol in SYMBOLS:
        rows = bars_by_symbol.get(symbol)
        if not isinstance(rows, list):
            continue
        session = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            stamp = _ny(row.get("t"))
            close = _num(row.get("c"))
            if stamp is not None and stamp.strftime("%Y-%m-%d") == today and 570 <= stamp.hour * 60 + stamp.minute < 600 and close > 0:
                session.append((stamp, row))
        session.sort(key=lambda item: item[0])
        if len(session) < 4:
            continue
        opening = _num(session[0][1].get("o"))
        latest = _num(session[-1][1].get("c"))
        if opening > 0 and latest > 0:
            returns.append((latest / opening - 1.0, symbol))
    if len(returns) < 3:
        return _out([], "Too few ETFs have first-half-hour bars; abstaining.", memory)
    returns.sort()
    pullback, symbol = returns[0]
    threshold = max(0.0, _num(params.get("pullback_min"), 0.0005))
    if pullback > -threshold:
        memory["buy_date"] = today
        return _out([], "No ETF has a sufficiently negative first-half-hour return; skip today.", memory)
    limits = ctx.get("limits") if isinstance(ctx.get("limits"), dict) else {}
    cash = max(0.0, _num(ctx.get("cash")))
    amount = min(_num(params.get("notional_usd"), 75.0),
                 _num(limits.get("max_order_usd"), 75.0),
                 _num(limits.get("max_position_usd"), 100.0), cash * 0.95)
    amount = math.floor(amount * 100.0) / 100.0
    if amount < 1.0:
        return _out([], "Insufficient cash for a bounded ETF entry.", memory)
    memory["buy_date"] = today
    intent = {"symbol": symbol, "side": "buy", "notional_usd": amount, "type": "market",
              "reason": "Test same-day mean reversion by buying the weakest ETF after a negative first-half-hour move."}
    return _out([intent], "Buying the most negative first-half-hour ETF return, subject to a pullback threshold; exit before close.", memory)

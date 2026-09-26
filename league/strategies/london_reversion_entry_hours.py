from datetime import datetime
from zoneinfo import ZoneInfo

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "symmetric-mean-reversion-zscore",
    "symbols": ["BTC/USD", "SPY", "QQQ", "GLD", "XLE"],
    "bars": {"timeframe": "1Hour", "limit": 120},
    "wake_minutes": 60,
    "parameter_rules": {
        "bounds": {
            "lookback": [10, 60],
            "entry_z": [-3.0, 0.0],
            "exit_z": [-3.0, 3.0],
            "stop_pct": [0.005, 0.10],
            "take_profit_pct": [0.005, 0.10],
            "timeout_hours": [4, 120],
            "position_pct": [0.02, 0.30],
        },
        "ordered": [["entry_z", "exit_z"]],
    },
}

PARAMS = {
    "lookback": 20,
    "entry_z": -1.3,
    "exit_z": 0.3,
    "stop_pct": 0.02,
    "take_profit_pct": 0.03,
    "timeout_hours": 30,
    "position_pct": 0.12,
}


def _stock_entry_hours(now):
    # Necessary clock window only; the House still enforces the venue calendar.
    try:
        stamp = datetime.fromisoformat(now.replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            return False
        local = stamp.astimezone(ZoneInfo("America/New_York"))
        minute = local.hour * 60 + local.minute
        return local.weekday() < 5 and 570 <= minute < 960
    except (TypeError, ValueError, AttributeError):
        return False


def _stdev(xs):
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def decide(ctx):
    bars = ctx.get("bars", {})
    quotes = ctx.get("quotes", {})
    pos = ctx.get("positions", [])
    intents = []
    now = ctx.get("now", "")
    stock_entry_hours = _stock_entry_hours(now)
    p = dict(PARAMS)
    p.update(ctx.get("params", {}))
    n = int(p["lookback"])
    z_entry = float(p["entry_z"])
    z_exit = float(p["exit_z"])
    stop_pct = float(p["stop_pct"])
    tp_pct = float(p["take_profit_pct"])
    timeout_h = float(p["timeout_hours"])
    pos_pct = float(p["position_pct"])

    held = {}
    for ps in pos:
        s = ps.get("symbol")
        qty = float(ps.get("quantity", 0) or 0)
        cost = float(ps.get("average_cost", 0) or 0)
        if qty <= 0 or cost <= 0:
            continue
        held[s] = True
        r = bars.get(s, [])
        if len(r) < n + 1:
            continue
        closes = [float(x.get("c", 0)) for x in r]
        if min(closes) <= 0:
            continue
        m = sum(closes[-n:]) / n
        sd = _stdev(closes[-n:])
        z = (closes[-1] - m) / sd if sd > 0 else 0.0
        bid = float(quotes.get(s, {}).get("bid", 0) or closes[-1])
        age = 0.0
        opened = ps.get("opened_at", "")
        try:
            age = (datetime.fromisoformat(now.replace("Z", "+00:00")) - datetime.fromisoformat(opened.replace("Z", "+00:00"))).total_seconds() / 3600.0
        except Exception:
            pass
        reason = None
        if bid <= cost * (1 - stop_pct):
            reason = "protective stop"
        elif bid >= cost * (1 + tp_pct):
            reason = "take profit"
        elif z >= z_exit:
            reason = "mean reverted"
        elif age >= timeout_h:
            reason = "timeout"
        if reason:
            intents.append({"symbol": s, "side": "sell", "quantity": qty,
                            "type": "market", "reason": reason})

    equity = float(ctx.get("equity", 0) or 0)
    cash = float(ctx.get("cash", 0) or 0)
    max_order = float(ctx.get("limits", {}).get("max_order_usd", 75) or 75)
    pending = {o.get("symbol") for o in ctx.get("open_orders", []) if o.get("side") == "buy"}
    for s in NEEDS["symbols"]:
        if s in held or s in pending:
            continue
        if not s.endswith("/USD") and not stock_entry_hours:
            continue
        r = bars.get(s, [])
        if len(r) < n + 1:
            continue
        closes = [float(x.get("c", 0)) for x in r]
        if min(closes) <= 0:
            continue
        m = sum(closes[-n:]) / n
        sd = _stdev(closes[-n:])
        if sd <= 0:
            continue
        z = (closes[-1] - m) / sd
        if z <= z_entry:
            size = round(min(max_order, equity * pos_pct, cash * 0.5), 2)
            min_usd = 10 if s.endswith("/USD") else 1
            if size >= min_usd:
                intents.append({"symbol": s, "side": "buy", "notional_usd": size,
                                "type": "market", "reason": "oversold mean-reversion entry"})
                break
    return {"intents": intents, "cancels": [],
            "thought": "Symmetric z-score mean reversion with stock entries restricted to New York weekday session hours; crypto signals and exits are unchanged.",
            "memory": ctx.get("memory", {})}

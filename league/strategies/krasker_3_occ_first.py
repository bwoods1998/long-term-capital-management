import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "options-pullback-coverage-test",
    "asset_class": "option",
    "symbols": ["F", "SOFI", "T", "AAL", "RIVN", "SNAP", "CCL", "VALE"],
    "bars": {"timeframe": "1Day", "limit": 40},
    "max_days_to_expiry": 30,
    "wake_minutes": 30,
}
PARAMS = {
    "rsi_entry": 45.0,
    "rsi_high": 55.0,
    "trend_days": 5,
    "exit_mean_days": 5,
    "min_days": 3,
    "max_days": 30,
    "target_delta": 0.50,
    "max_spread_pct": 20.0,
    "min_premium": 0.05,
    "notional_usd": 20.0,
    "max_open": 2,
    "take_profit_pct": 33.331888,
    "stop_pct": 35.0,
    "exit_days": 2,
    "requote_minutes": 30,
    "rv_window": 20,
    "max_iv_rv": 1.6,
    "max_chase_sigma": 2.5,
    "max_chase_floor": 0.02,
}

def number(x, default=0.0):
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except (TypeError, ValueError):
        return default

def local_time(x):
    try:
        z = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        if z.tzinfo is None:
            z = z.replace(tzinfo=timezone.utc)
        return z.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return None

def option_symbol(row):
    if not isinstance(row, dict):
        return ""
    return str(row.get("occ") or row.get("symbol") or "")

def expiry_from_symbol(symbol):
    m = re.search(r"[0-9]{6}[CP]", str(symbol).upper())
    if not m:
        return None
    d = m.group(0)[:6]
    return "20" + d[:2] + "-" + d[2:4] + "-" + d[4:6]

def days_left(value, now):
    try:
        if not value:
            return None
        return (datetime.strptime(str(value), "%Y-%m-%d").date() - now.date()).days
    except Exception:
        return None

def closes(ctx, symbol):
    result = []
    for bar in (ctx.get("bars") or {}).get(symbol, []) or []:
        if isinstance(bar, dict):
            close = number(bar.get("c"), -1.0)
            if close > 0:
                result.append(close)
    return result

def short_rsi(values):
    if len(values) < 3:
        return None
    gains = sum(max(values[i] - values[i - 1], 0.0) for i in (-2, -1)) / 2.0
    losses = sum(max(values[i - 1] - values[i], 0.0) for i in (-2, -1)) / 2.0
    if losses == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gains / losses)

def decide(ctx):
    p = dict(PARAMS)
    for key, value in (ctx.get("params") or {}).items():
        if key in p:
            p[key] = number(value, p[key])
    now = local_time(ctx.get("now"))
    memory = dict(ctx.get("memory") or {})
    memory["wakes"] = int(memory.get("wakes", 0)) + 1
    intents = []
    positions = ctx.get("positions") or []
    orders = ctx.get("open_orders") or []
    working = {option_symbol(x) for x in orders if isinstance(x, dict)}
    bids = {}
    for row in ctx.get("chain") or []:
        if isinstance(row, dict):
            symbol = option_symbol(row)
            bid = number(row.get("bid"))
            if symbol and bid > 0:
                bids[symbol] = bid
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        symbol = option_symbol(pos)
        if not symbol or symbol in working:
            continue
        mark = number(pos.get("mark"))
        cost = number(pos.get("average_cost"))
        if mark <= 0 or cost <= 0:
            continue
        left = days_left(pos.get("expiry") or expiry_from_symbol(symbol), now) if now else None
        change = mark / cost - 1.0
        if change >= p["take_profit_pct"] / 100.0 or change <= -p["stop_pct"] / 100.0 or (left is not None and left <= p["exit_days"]):
            price = round(max(0.01, bids.get(symbol, mark)), 2)
            intents.append({
                "occ": symbol,
                "side": "sell",
                "quantity": int(number(pos.get("quantity"))),
                "type": "limit",
                "limit_price": price,
                "reason": "Exit at target, stop, or near expiry using the current bid.",
            })
    if now is None or now.weekday() >= 5:
        return {"intents": intents[:8], "cancels": [], "thought": "No entry outside the regular session.", "memory": memory}
    minute = now.hour * 60 + now.minute
    if minute < 570 or minute >= 960:
        return {"intents": intents[:8], "cancels": [], "thought": "No entry outside the regular options session.", "memory": memory}
    busy = {option_symbol(x) for x in positions + orders if isinstance(x, dict)}
    slots = int(p["max_open"]) - len(busy)
    limits = ctx.get("limits") or {}
    cash = max(0.0, number(ctx.get("cash")))
    max_order = number(limits.get("max_order_usd"), 20.0)
    budget = min(p["notional_usd"], max_order, cash * 0.95)
    for underlying in NEEDS["symbols"]:
        if slots <= 0 or budget < 1.0:
            break
        values = closes(ctx, underlying)
        window = int(p["trend_days"])
        signal = short_rsi(values)
        if len(values) < window or signal is None:
            continue
        mean = sum(values[-window:]) / float(window)
        right = "call" if signal < p["rsi_entry"] and values[-1] > mean else "put" if signal > p["rsi_high"] and values[-1] < mean else None
        if right is None:
            continue
        best = None
        for row in ctx.get("chain") or []:
            if not isinstance(row, dict) or row.get("underlying") != underlying or row.get("right") != right:
                continue
            bid = number(row.get("bid"))
            ask = number(row.get("ask"))
            left = days_left(row.get("expiry"), now)
            if left is None or left < p["min_days"] or left > p["max_days"] or not (0 < bid < ask):
                continue
            mid = (bid + ask) / 2.0
            if mid <= 0 or (ask - bid) / mid * 100.0 > p["max_spread_pct"] or ask * 100.0 > budget or mid < p["min_premium"]:
                continue
            delta = number(row.get("delta"))
            score = abs(abs(delta) - p["target_delta"])
            candidate = (score, left, -number(row.get("volume")), row, ask)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
        if best is None:
            continue
        row, ask = best[3], best[4]
        symbol = option_symbol(row)
        if not symbol or symbol in busy or ask * 100.0 > budget:
            continue
        intents.append({
            "occ": symbol,
            "side": "buy",
            "quantity": 1,
            "type": "limit",
            "limit_price": round(ask, 2),
            "post_only": False,
            "reason": "Broader pullback signal with bounded premium, expiry, spread, and displayed-ask entry.",
        })
        busy.add(symbol)
        slots -= 1
    return {"intents": intents[:8], "cancels": [], "thought": "Coverage test uses a five-day trend window and 45/55 RSI triggers while retaining execution safeguards.", "memory": memory}

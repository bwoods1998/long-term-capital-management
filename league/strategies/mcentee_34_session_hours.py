import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "megacap-two-session-pullback",
    "symbols": ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO"],
    "bars": {"timeframe": "1Day", "limit": 210},
    "wake_minutes": 30,
}

PARAMS = {"exit_mean_days": 5, "max_days": 5, "notional_usd": 25.0,
          "max_positions": 4}


def number(x, default=0.0):
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except (TypeError, ValueError):
        return default


def date_part(text):
    s = str(text or "")
    return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else ""


NY = ZoneInfo("America/New_York")
#: The regular session, in New York minutes: 9:35 to 15:55, five minutes inside the open and the
#: close. The parent (mcentee-34) wrote these as 14:35-20:55 UTC, which is that window only while
#: New York is on standard time (EST, UTC-5). From March to November it is on daylight time
#: (EDT, UTC-4), the UTC window is 13:35-19:55, and the parent sat idle through the first hour of
#: every session and tried to trade for an hour after the close.
OPEN_MINUTE, CLOSE_MINUTE = 9 * 60 + 35, 15 * 60 + 55


def new_york(now):
    """`ctx["now"]` (an ISO stamp, UTC) as a New York time, or None when it cannot be read."""
    s = str(now or "").strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(s)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(NY)


def regular_session(now):
    """A weekday between 9:35 and 15:55 New York time, whatever the season."""
    local = new_york(now)
    if local is None or local.weekday() >= 5:
        return False
    minute = local.hour * 60 + local.minute
    return OPEN_MINUTE <= minute <= CLOSE_MINUTE


def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get("params") or {})
    exit_days = max(2, int(number(p.get("exit_mean_days"), 5)))
    max_days = max(1, int(number(p.get("max_days"), 5)))
    notional = max(0.0, number(p.get("notional_usd"), 25.0))
    max_positions = max(1, int(number(p.get("max_positions"), 4)))
    if not regular_session(ctx.get("now")):
        return {"intents": [], "cancels": [],
                "thought": "Outside the regular session; no orders submitted.", "memory": {}}

    positions = {}
    for pos in ctx.get("positions") or []:
        if isinstance(pos, dict) and number(pos.get("quantity")) > 0:
            positions[pos.get("symbol")] = pos
    working = set()
    reserved = 0.0
    for order in ctx.get("open_orders") or []:
        if isinstance(order, dict):
            working.add(order.get("symbol"))
            if order.get("side") == "buy":
                reserved += number(order.get("quantity")) * number(order.get("limit_price"))

    limits = ctx.get("limits") or {}
    free = max(0.0, (number(ctx.get("cash")) - reserved) * 0.98)
    intents, notes = [], []
    bars_by_symbol = ctx.get("bars") or {}
    today = date_part(ctx.get("now"))
    for symbol in NEEDS["symbols"]:
        rows = [r for r in bars_by_symbol.get(symbol, []) if isinstance(r, dict)]
        closes = [number(r.get("c")) for r in rows]
        pos = positions.get(symbol)
        if symbol in working:
            continue
        if pos is not None:
            if len(closes) < exit_days:
                continue
            opened = date_part(pos.get("opened_at"))
            held = sum(1 for r in rows if opened and date_part(r.get("t")) > opened)
            recent = closes[-exit_days:]
            mean = sum(recent) / len(recent) if recent else 0.0
            if held >= max_days or (closes[-1] > 0 and closes[-1] >= mean):
                intents.append({"symbol": symbol, "side": "sell",
                                "quantity": number(pos.get("quantity")), "type": "market",
                                "reason": "Exit the trend pullback on recovery to its five-session mean or after five sessions."})
                notes.append(symbol + " exit")
            continue

        if (len(positions) + sum(1 for x in intents if x.get("side") == "buy") >= max_positions
                or len(closes) < 51):
            continue
        # Trend filter: price above the 50-session mean and the 20-session mean above it.
        mean20 = sum(closes[-20:]) / 20.0
        mean50 = sum(closes[-50:]) / 50.0
        # Two completed sessions of weakness, with a bounded cumulative drawdown.
        base = closes[-3]
        pullback = closes[-1] / base - 1.0 if base > 0 else 0.0
        if not (closes[-1] > mean50 and mean20 > mean50 and -0.06 <= pullback <= -0.01):
            continue

        cap = min(notional, number(limits.get("max_order_usd"), notional),
                  number(limits.get("max_position_usd"), notional), free)
        dollars = math.floor(max(0.0, cap) * 100.0) / 100.0
        if dollars < 1.0:
            continue
        free -= dollars
        intents.append({"symbol": symbol, "side": "buy", "notional_usd": dollars,
                        "type": "market",
                        "reason": "Buy a two-session 1–6% pullback while price remains above the 50-session mean and the 20-session mean is above the 50-session mean."})
        notes.append(symbol + " trend-pullback entry")

    return {"intents": intents, "cancels": [],
            "thought": "Tests two-session pullbacks within an established medium-term uptrend. " + "; ".join(notes),
            "memory": {}}

import datetime
import math
import statistics

NEEDS = {
    "venue": "kalshi",
    "horizon": "hour",
    "style": "btc-15m-spot-strike-probability",
    "series": ["KXBTC15M"],
    "max_hours_to_close": 1,
    "wake_minutes": 5,
    "observe": {"symbols": ["BTC/USD"]},
    "bars": {"timeframe": "5Min", "limit": 48},
}
PARAMS = {}

def decide(ctx):
    intents = []
    if ctx.get("positions") or any(o.get("side") == "buy" for o in ctx.get("open_orders", [])):
        return {"intents": intents, "cancels": [], "thought": "Avoid adding exposure while a position or buy order is outstanding.", "memory": {}}

    bars = ctx.get("observed", {}).get("bars", {}).get("BTC/USD", [])
    closes = [float(b.get("c", 0)) for b in bars if float(b.get("c", 0)) > 0]
    if len(closes) < 12:
        return {"intents": intents, "cancels": [], "thought": "Insufficient observed BTC bars to estimate short-horizon dispersion.", "memory": {}}

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i] > 0 and closes[i - 1] > 0]
    if len(log_returns) < 10:
        return {"intents": intents, "cancels": [], "thought": "Insufficient valid BTC returns.", "memory": {}}
    sigma_5m = max(statistics.pstdev(log_returns[-36:]), 0.00015)
    spot = closes[-1]
    rate = float(ctx.get("fees", {}).get("kalshi_taker_rate", 0.07))
    entry_floor = 0.30 if ctx.get("rung", 0) >= 2 else 0.15

    for m in ctx.get("markets", []):
        if m.get("series") != "KXBTC15M":
            continue
        hours = float(m.get("hours_to_close", 99))
        if not (0.001 <= hours <= 0.20):
            continue
        strike = m.get("strike")
        bid, ask = m.get("yes_bid"), m.get("yes_ask")
        if strike is None or bid is None or ask is None:
            continue
        strike = float(strike)
        bid, ask = float(bid), float(ask)
        if strike <= 0 or not (0 < bid < ask < 1) or ask - bid > 0.06:
            continue

        # Outcome is determined at market close; 5-minute return volatility scales by sqrt(time).
        z = math.log(spot / strike) / (sigma_5m * math.sqrt(max(hours * 12.0, 0.02)))
        p_yes = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        no_ask = 1.0 - bid
        choices = [(p_yes, ask, "yes"), (1.0 - p_yes, no_ask, "no")]
        best = None
        for probability, price, leg in choices:
            if price < entry_floor:
                continue
            fee = math.ceil(rate * price * (1.0 - price) * 10000.0) / 10000.0
            edge = probability - price - fee
            if price > 0 and edge >= 0.04 and (best is None or edge > best[0]):
                best = (edge, price, fee, leg)
        if best is None:
            continue

        edge, price, fee, leg = best
        remaining = ctx.get("event_risk", {}).get("remaining_by_market_usd", {}).get(m.get("market"), 4.0)
        cap = min(4.0, float(ctx.get("limits", {}).get("max_order_usd", 4.0)), float(ctx.get("limits", {}).get("max_position_usd", 4.0)), float(ctx.get("cash", 0.0)) * 0.5, float(remaining))
        quantity = min(8, int(cap / (price + fee + 0.0001)))
        if quantity >= 1:
            intents.append({"market": m["market"], "leg": leg, "side": "buy", "quantity": quantity, "type": "market", "reason": "Buy only when a zero-drift, recent-realized-volatility spot-to-strike estimate exceeds the executable price and taker fee by at least 4 cents; exposure is capped."})
            break

    return {"intents": intents, "cancels": [], "thought": "Estimate the BTC close-above-strike probability from point-in-time spot bars and remaining close time; abstain unless modeled edge clears fees and a fixed cushion.", "memory": {}}

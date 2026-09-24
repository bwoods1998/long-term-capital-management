import math

NEEDS = {
    "venue": "kalshi",
    "horizon": "hour",
    "style": "btc-15m-maker-momentum",
    "series": ["KXBTC15M"],
    "max_hours_to_close": 1,
    "wake_minutes": 5,
    "observe": {"symbols": ["BTC/USD"]},
    "bars": {"timeframe": "5Min", "limit": 48},
    "parameter_rules": {
        "bounds": {"min_move": [0.0002, 0.0020], "ask_lo": [0.10, 0.50], "ask_hi": [0.50, 0.85], "contracts": [1, 10]},
        "ordered": [["ask_lo", "ask_hi"]],
    },
}
PARAMS = {"min_move": 0.0006, "ask_lo": 0.30, "ask_hi": 0.80, "contracts": 5}


def decide(ctx):
    intents = []
    if ctx.get("positions") or any(o.get("side") == "buy" for o in ctx.get("open_orders", [])):
        return {"intents": [], "cancels": [], "thought": "Hold to settlement; single BTC position or resting entry at a time.", "memory": {}}

    bars = ctx.get("observed", {}).get("bars", {}).get("BTC/USD", [])
    closes = [float(b["c"]) for b in bars if float(b.get("c", 0)) > 0]
    if len(closes) < 2:
        return {"intents": [], "cancels": [], "thought": "Need two BTC closes.", "memory": {}}

    r = math.log(closes[-1] / closes[-2])
    p = ctx.get("params", {})
    if abs(r) < float(p.get("min_move", 0.0006)):
        return {"intents": [], "cancels": [], "thought": "Fresh 5m move under threshold.", "memory": {}}
    direction = "yes" if r > 0 else "no"
    ask_lo = float(p.get("ask_lo", 0.30))
    ask_hi = float(p.get("ask_hi", 0.80))
    contracts = int(p.get("contracts", 5))
    price_floor = 0.30 if ctx.get("rung", 0) >= 2 else 0.15

    for m in ctx.get("markets", []):
        if m.get("series") != "KXBTC15M":
            continue
        yb, ya = m.get("yes_bid"), m.get("yes_ask")
        if yb is None or ya is None:
            continue
        ask = float(ya) if direction == "yes" else 1.0 - float(yb)
        if not (ask_lo <= ask <= ask_hi):
            continue
        bid = float(yb) if direction == "yes" else 1.0 - float(ya)
        if not math.isfinite(bid):
            continue
        price = math.floor(bid * 100 + 1e-9) / 100
        if not (price_floor <= price < ask):
            continue
        room = min(float(ctx.get("limits", {}).get("max_order_usd", 0)),
                   float(ctx.get("limits", {}).get("max_position_usd", 0)),
                   float(ctx.get("cash", 0)))
        qty = min(contracts, int(room / (ask + 0.001)))
        if qty < 1:
            continue
        intents.append({"market": m["market"], "leg": direction, "side": "buy", "quantity": qty,
                        "type": "limit", "limit_price": price, "post_only": True,
                        "reason": "Maker momentum-continuation: rest at the bid after a fresh 5m BTC move clears the threshold and ask band."})
        break

    return {"intents": intents, "cancels": [], "thought": "BTC momentum-continuation with post-only entries only.", "memory": {}}

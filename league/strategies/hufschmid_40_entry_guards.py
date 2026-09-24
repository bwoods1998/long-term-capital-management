NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "mlb-home-run-low-priced-yes-taker",
    "series": ["KXMLBHR"],
    "max_hours_to_close": 12,
    "wake_minutes": 30,
}

PARAMS = {
    "yes_max": 0.15,
    "min_hours": 1.0,
    "max_hours": 12.0,
    "max_spread": 0.06,
    "min_volume_24h": 200,
    "notional_usd": 6.0,
    "max_open": 3,
}


def num(value, default=None):
    try:
        x = float(value)
        if x != x or abs(x) == float("inf"):
            return default
        return x
    except (TypeError, ValueError):
        return default


def valid_market(ticker):
    # Accept only a conservative subset of KXMLBHR ticker identities.
    # Never repair, truncate, or stringify an identity into another market.
    if not isinstance(ticker, str) or len(ticker) > 64:
        return False
    parts = ticker.split("-")
    return (len(parts) >= 3 and parts[0] == "KXMLBHR"
            and all(part and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                                for c in part) for part in parts[1:]))


def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get("params") or {})
    markets = [m for m in ctx.get("markets") or [] if isinstance(m, dict)]
    positions = [x for x in ctx.get("positions") or [] if isinstance(x, dict)]
    orders = [x for x in ctx.get("open_orders") or [] if isinstance(x, dict)]
    busy = {str(x.get("market")) for x in positions if num(x.get("quantity"), 0) > 0}
    busy.update(str(x.get("market")) for x in orders)

    cancels = [str(o.get("order_id")) for o in orders
               if o.get("side") == "buy" and o.get("order_id")][:20]
    cash = max(0.0, num(ctx.get("cash"), 0) or 0)
    reserved = sum((num(o.get("quantity"), 0) or 0) * (num(o.get("limit_price"), 0) or 0)
                   for o in orders if o.get("side") == "buy")
    free = max(0.0, cash - reserved) * 0.98
    limits = ctx.get("limits") or {}
    per_market = min(num(p.get("notional_usd"), 6),
                     num(limits.get("max_order_usd"), 6),
                     num(limits.get("max_position_usd"), 6))
    if num(ctx.get("equity"), 0):
        per_market = min(per_market, 0.03 * (num(ctx.get("equity"), 0) or 0))

    remaining = ((ctx.get("event_risk") or {}).get("remaining_by_market_usd") or {})
    price_floor = 0.30 if num(ctx.get("rung"), 0) >= 2 else 0.15
    candidates = []
    for m in markets:
        ticker = m.get("market")
        if not valid_market(ticker):
            continue
        bid, ask = num(m.get("yes_bid")), num(m.get("yes_ask"))
        hours = num(m.get("hours_to_close"))
        resolves = num(m.get("hours_to_resolve"))
        volume = num(m.get("volume_24h"), 0) or 0
        if bid is None or ask is None or hours is None or not (0 < bid < ask < 1):
            continue
        if resolves is None or not (0 < resolves <= 48):
            continue
        if not (price_floor <= ask <= num(p.get("yes_max"), 0.15)):
            continue
        if ask - bid > num(p.get("max_spread"), 0.06):
            continue
        if not (num(p.get("min_hours"), 1) <= hours <= num(p.get("max_hours"), 12)):
            continue
        if volume < num(p.get("min_volume_24h"), 200) or ticker in busy:
            continue
        candidates.append((-volume, ticker, ask, hours))
    candidates.sort()

    slots = max(0, min(int(num(p.get("max_open"), 3)), 8) - len(busy))
    intents = []
    for negative_volume, ticker, ask, hours in candidates:
        if len(intents) >= slots:
            break
        cap = min(per_market, free, num(remaining.get(ticker), per_market))
        qty = int(cap / (ask + 0.01))
        if qty < 1 or qty * ask < 1.0:
            continue
        intents.append({
            "market": ticker,
            "leg": "yes",
            "side": "buy",
            "quantity": qty,
            "type": "limit",
            "limit_price": ask,
            "reason": f"Small low-priced YES entry bounded at {ask:.2f}; {hours:.1f}h to close, volume {int(-negative_volume)}."
        })
        free -= qty * (ask + 0.01)
    return {
        "intents": intents,
        "cancels": cancels,
        "thought": f"Screened {len(markets)} markets; {len(candidates)} passed identity, price-floor, resolution and original signal filters; submitted {len(intents)} bounded YES entries. No entry is eligible when the floor exceeds the signal ceiling.",
        "memory": {},
    }

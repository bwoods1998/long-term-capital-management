"""House starter for the crypto family, maker side: rest post-only bids a spread under the
Coinbase mid, and when a coin is held, rest a post-only offer a spread over cost.

Coinbase charges the taker 0.6% and the maker less than half of that on this account, so a
desk that only ever rests captures the spread instead of paying it. Every run, for each
symbol: read the quote; when the desk holds none of the coin, rest a post-only bid at
mid x (1 - spread) sized to the learning notional; when it holds some, rest a post-only offer
for the whole holding at the higher of cost x (1 + spread) and mid x (1 + spread / 2), so a
fill closes the round trip above cost. Quotes older than `requote_seconds`, or more than
`drift` away from where they belong now, are cancelled and replaced. A quote that would cross
the book is refused by the venue and by the shadow book alike, so the desk can never take.

Params: symbols, spread, drift, requote_seconds, notional_usd, max_symbols.
"""

from datetime import datetime, timezone

DEFAULTS = {
    "symbols": ["BTC-USD", "ETH-USD", "SOL-USD"],
    "spread": 0.004,
    "drift": 0.002,
    "requote_seconds": 900,
    "notional_usd": None,
    "max_symbols": 3,
}


def _num(value, default=None):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _when(text):
    try:
        return datetime.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _price(value):
    return f"{value:.2f}"


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 25.0)
    held = {}
    for x in ctx.get("positions") or []:
        if str(x.get("asset_class") or "") == "crypto" and _num(x.get("quantity"), 0) > 0:
            held[str(x.get("symbol"))] = (_num(x.get("quantity"), 0), _num(x.get("average_cost"), 0) or 0)
    resting = [o for o in (ctx.get("open_orders") or []) if o.get("strategy") == "spot_quotes"]
    cancels, intents, kept = [], [], {}
    targets = {}
    for symbol in list(p["symbols"])[: int(p["max_symbols"])]:
        quote = kit.quote(symbol) or {}
        bid, ask = _num(quote.get("bid")), _num(quote.get("ask"))
        if not bid or not ask or ask <= 0:
            kit.say(f"{symbol}: no quote")
            continue
        mid = (bid + ask) / 2.0
        if symbol in held:
            quantity, cost = held[symbol]
            offer = max(cost * (1.0 + float(p["spread"])), mid * (1.0 + float(p["spread"]) / 2.0))
            offer = max(offer, ask + 0.01)  # never cross: an offer at or under the ask would take
            targets[(symbol, "sell")] = (offer, quantity, f"offer {quantity:.6f} {symbol} at {offer:,.2f}: cost {cost:,.2f}, mid {mid:,.2f}; a fill closes the round trip {float(p['spread']) * 100:.1f}% over cost at the maker rate. Exit rule: this offer is the exit; it is replaced when mid drifts {float(p['drift']) * 100:.1f}% or after {int(p['requote_seconds']) // 60} min")
        else:
            bid_price = min(mid * (1.0 - float(p["spread"])), bid - 0.01)  # never cross
            quantity = notional / bid_price
            targets[(symbol, "buy")] = (bid_price, quantity, f"bid {quantity:.6f} {symbol} at {bid_price:,.2f}, {float(p['spread']) * 100:.1f}% under mid {mid:,.2f}, post-only at the maker rate. Setup: market making, not a directional call; the edge is the spread and the maker rebate. Exit: an offer {float(p['spread']) * 100:.1f}% over cost is posted the run after a fill; the bid is cancelled if mid drifts {float(p['drift']) * 100:.1f}% or after {int(p['requote_seconds']) // 60} min; 48h time stop on the inventory")
    for order in resting:
        key = (str(order.get("symbol")), str(order.get("side")))
        price = _num(order.get("limit_price"))
        placed = _when(order.get("submitted_at"))
        age = (now - placed).total_seconds() if placed else None
        target = targets.get(key)
        stale = age is not None and age > float(p["requote_seconds"])
        gone = target is None
        drifted = target is not None and price is not None and abs(price - target[0]) / max(target[0], 1e-9) > float(p["drift"])
        if stale or gone or drifted:
            if order.get("order_id"):
                cancels.append(order["order_id"])
        else:
            kept[key] = price
    for (symbol, side), (price, quantity, why) in targets.items():
        if (symbol, side) in kept or quantity <= 0:
            continue
        intents.append(
            {
                "instrument": {"asset_class": "crypto", "symbol": symbol},
                "side": side,
                "quantity": f"{quantity:.6f}",
                "order_type": "limit",
                "limit_price": _price(price),
                "post_only": True,
                "rationale": "Quote: " + why,
                **({"holding_period_hours": 48} if side == "buy" else {}),
            }
        )
    kit.say(f"{len(targets)} target(s), {len(kept)} kept, {len(cancels)} cancelled, {len(intents)} placed")
    return {"intents": intents, "cancels": cancels, "notes": f"{len(kept)} kept, {len(cancels)} cancelled, {len(intents)} placed"}

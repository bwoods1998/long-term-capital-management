import math
from datetime import datetime


NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "wnba-duration-maker-control",
    "series": ["KXWNBAGAME"],
    "max_hours_to_close": 48,
    "wake_minutes": 15,
    "parameter_rules": {
        "bounds": {
            "min_resolve_hours": [12.0, 48.0],
            "max_resolve_hours": [12.0, 48.0],
            "order_ttl_minutes": [30, 120]
        },
        "ordered": [["min_resolve_hours", "max_resolve_hours"]],
        "frozen": [
            "bid_min", "bid_max", "max_spread", "notional_usd",
            "min_resolve_hours", "max_resolve_hours"
        ]
    }
}

PARAMS = {
    "bid_min": 0.78,
    "bid_max": 0.88,
    "max_spread": 0.05,
    "min_resolve_hours": 12.0,
    "max_resolve_hours": 48.0,
    "order_ttl_minutes": 90,
    "notional_usd": 2.0
}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def cancellation_ids(orders):
    result = []
    for order in orders:
        identity = order.get("order_id")
        if order.get("side") == "buy" and identity and identity not in result:
            result.append(identity)
            if len(result) == 20:
                break
    return result


def answer(thought, cancels=None, intents=None):
    return {
        "intents": intents or [],
        "cancels": cancels or [],
        "thought": thought,
        "memory": {}
    }


def eligible(market, params):
    if market.get("series") != "KXWNBAGAME":
        return None
    identity = market.get("market")
    if not isinstance(identity, str) or not identity.startswith("KXWNBAGAME-"):
        return None
    close_hours = number(market.get("hours_to_close"))
    resolve_hours = number(market.get("hours_to_resolve"))
    bid = number(market.get("yes_bid"))
    ask = number(market.get("yes_ask"))
    if None in (close_hours, resolve_hours, bid, ask):
        return None
    if not 0 < close_hours <= 48:
        return None
    if not params["min_resolve_hours"] <= resolve_hours <= params["max_resolve_hours"]:
        return None
    if not 0 < bid < ask < 1:
        return None
    if not params["bid_min"] <= bid <= params["bid_max"]:
        return None
    price = math.floor(bid * 100.0 + 1e-9) / 100.0
    if not params["bid_min"] <= price <= params["bid_max"]:
        return None
    if price >= ask or ask - price > params["max_spread"] + 1e-9:
        return None
    return {"market": identity, "price": price, "ask": ask, "spread": ask - price}


def fee_reserve(quantity, price, rate):
    # Full taker fees conservatively cover ordinary maker charges too.
    return math.ceil(rate * quantity * price * (1.0 - price) * 10000.0) / 10000.0


def spending_limit(ctx, params, market, committed_notional=0.0):
    limits = ctx.get("limits") or {}
    values = [
        number(ctx.get("cash")),
        number(limits.get("max_order_usd")),
        number(limits.get("max_position_usd"))
    ]
    if any(value is None for value in values):
        return 0.0
    cap = min(params["notional_usd"], min(values))
    risk = ctx.get("event_risk") or {}
    remaining = risk.get("remaining_by_market_usd") or {}
    if market in remaining:
        headroom = number(remaining[market])
        if headroom is None:
            return 0.0
        # Existing buys already consume reported headroom. Credit only the
        # sole order being checked, never an anticipated cancellation release.
        cap = min(cap, headroom + committed_notional)
    return max(0.0, cap)


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get("params") or {})
    orders = ctx.get("open_orders") or []
    cancels = cancellation_ids(orders)
    now = stamp(ctx.get("now"))
    if now is None:
        return answer("The decision clock is unavailable; withdraw entry commitments.", cancels)

    # No averaging down, additional games, or reliance on pending sale proceeds.
    if ctx.get("positions"):
        return answer("Hold the existing exposure to settlement and withdraw any remaining buys.", cancels)

    rate = number((ctx.get("fees") or {}).get("kalshi_taker_rate"))
    rate = max(0.07, rate if rate is not None else 0.07)
    targets = {}
    for market in ctx.get("markets") or []:
        target = eligible(market, params)
        if target is not None:
            targets[target["market"]] = target

    if orders:
        if len(orders) != 1:
            return answer("Multiple commitments are present; withdraw buys before considering another entry.", cancels)
        order = orders[0]
        if order.get("side") != "buy":
            return answer("An existing order must finish before another exposure is considered.")
        target = targets.get(order.get("market"))
        price = number(order.get("limit_price"))
        quantity = number(order.get("quantity"))
        filled = number(order.get("filled", 0.0))
        submitted = stamp(order.get("submitted_at"))
        valid = (
            target is not None
            and order.get("leg") == "yes"
            and price is not None
            and quantity is not None
            and filled == 0.0
            and submitted is not None
        )
        if valid:
            valid = (
                quantity > 0
                and quantity == math.floor(quantity)
                and params["bid_min"] <= price <= params["bid_max"]
                and price <= target["price"] + 1e-9
                and price < target["ask"]
                and target["ask"] - price <= params["max_spread"] + 1e-9
                and 0 <= now - submitted < params["order_ttl_minutes"] * 60
            )
        if valid:
            notional = quantity * price
            spending = notional + fee_reserve(quantity, price, rate)
            cap = spending_limit(ctx, params, order["market"], notional)
            valid = notional >= 1.0 and spending <= cap
        if valid:
            return answer("The sole resting WNBA bid remains eligible; preserve its queue priority.")
        return answer("Withdraw the expired, partially filled or ineligible bid and wait for cancellation confirmation.", cancels)

    candidates = sorted(targets.values(), key=lambda item: (item["spread"], -item["price"], item["market"]))
    for target in candidates:
        price = target["price"]
        cap = spending_limit(ctx, params, target["market"])
        unit_cost = price + rate * price * (1.0 - price)
        quantity = int(math.floor(cap / unit_cost))
        while quantity > 0 and quantity * price + fee_reserve(quantity, price, rate) > cap:
            quantity -= 1
        if quantity <= 0 or quantity * price < 1.0:
            continue
        intent = {
            "market": target["market"],
            "leg": "yes",
            "side": "buy",
            "quantity": quantity,
            "type": "limit",
            "limit_price": price,
            "post_only": True,
            "reason": "WNBA duration-window replication: passive 78-88 cent YES bid, explicit 12-48 hour resolution, one fee-reserved exposure."
        }
        return answer("Place one capped WNBA maker bid; expected resolution timing is not a verified game-status signal.", intents=[intent])

    return answer("No WNBA book satisfies the fixed price, resolution and affordable whole-contract requirements.")

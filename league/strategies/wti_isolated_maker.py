"""WTI-only maker-favourite experiment; not a calibrated probability model.

The narrow series and price band come from reused development evidence.
One outstanding exposure avoids stacking correlated strikes. Positions are
held for recorded settlement; this module never reads settlement labels.
"""

import math
from datetime import datetime, timezone


NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "wti-isolated-favorites-maker",
    "series": ["KXWTI"],
    "max_hours_to_close": 48,
    "wake_minutes": 15,
    "parameter_rules": {
        "bounds": {
            "max_spread": [0.01, 0.06],
            "order_ttl_minutes": [15, 240],
            "entry_buffer_hours": [0.25, 4.0],
        },
        "ordered": [["bid_min", "bid_max"]],
        "frozen": ["bid_min", "bid_max", "notional_usd"],
    },
}

PARAMS = {
    "bid_min": 0.90,
    "bid_max": 0.93,
    "max_spread": 0.04,
    "order_ttl_minutes": 60,
    "entry_buffer_hours": 1.0,
    "notional_usd": 2.0,
}


def number(value, default=None):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return value if math.isfinite(value) else default


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def result(thought, intents=None, cancels=None):
    return {
        "intents": intents or [],
        "cancels": (cancels or [])[:20],
        "thought": thought,
        "memory": {},
    }


def quote_plan(market, now, params):
    ticker = market.get("market")
    if market.get("series") != "KXWTI":
        return None
    if not isinstance(ticker, str) or not ticker.startswith("KXWTI-"):
        return None

    close_at = parse_time(market.get("close_time"))
    close_hint = number(market.get("hours_to_close"))
    resolve_hours = number(market.get("hours_to_resolve"))
    if close_at is None or close_hint is None or resolve_hours is None:
        return None
    clock_hours = (close_at - now) / 3600.0
    if not 0.0 < resolve_hours <= 48.0:
        return None
    if not 0.0 < clock_hours <= 48.0 or not 0.0 < close_hint <= 48.0:
        return None
    if min(clock_hours, close_hint) < params["entry_buffer_hours"]:
        return None

    bid = number(market.get("yes_bid"))
    ask = number(market.get("yes_ask"))
    if bid is None or ask is None or not 0.0 < bid < ask < 1.0:
        return None
    if not params["bid_min"] <= bid <= params["bid_max"]:
        return None
    spread = ask - bid
    if spread > params["max_spread"] + 1e-9:
        return None

    # Never improve through the ask; use a conservative whole-cent bid.
    price = round(math.floor(bid * 100.0 + 1e-9) / 100.0, 2)
    if not params["bid_min"] <= price <= params["bid_max"]:
        return None
    if price >= ask:
        return None
    return {
        "market": ticker,
        "price": price,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "resolve_hours": resolve_hours,
    }


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get("params") or {})
    orders = ctx.get("open_orders") or []
    positions = [
        position for position in (ctx.get("positions") or [])
        if number(position.get("quantity"), 0.0) > 0.0
    ]
    order_ids = [
        order["order_id"] for order in orders
        if isinstance(order.get("order_id"), str) and order["order_id"]
    ]
    now = parse_time(ctx.get("now"))
    if now is None:
        return result("The decision clock is missing; cancel orders and do not enter.", cancels=order_ids)

    limits = ctx.get("limits") or {}
    capacity = max(0.0, min(
        params["notional_usd"],
        number(limits.get("max_order_usd"), 0.0),
        number(limits.get("max_position_usd"), 0.0),
    ))
    fees = ctx.get("fees") or {}
    # Budget as though every individual contract incurred a rounded taker fee.
    # Actual post-only maker fees are assessed by the House, not this estimate.
    fee_rate = max(0.0, number(fees.get("kalshi_taker_rate"), 0.07))

    markets = {
        market["market"]: market
        for market in (ctx.get("markets") or [])
        if isinstance(market.get("market"), str)
    }

    if orders:
        if positions or len(orders) != 1:
            return result(
                "A fill or multiple working orders occupy the exposure slot; cancel remaining orders before doing anything else.",
                cancels=order_ids,
            )

        order = orders[0]
        plan = quote_plan(markets.get(order.get("market"), {}), now, params)
        submitted = parse_time(order.get("submitted_at"))
        price = number(order.get("limit_price"))
        quantity = number(order.get("quantity"), 0.0)
        filled = max(0.0, number(order.get("filled"), 0.0))
        remaining = max(0.0, quantity - filled)
        valid = (
            plan is not None
            and order.get("side") == "buy"
            and order.get("leg") == "yes"
            and submitted is not None
            and price is not None
            and remaining > 0.0
            and filled == 0.0
        )
        if valid:
            fee_each = math.ceil(fee_rate * price * (1.0 - price) * 100.0) / 100.0
            valid = (
                0.0 <= now - submitted < params["order_ttl_minutes"] * 60.0
                and params["bid_min"] <= price <= params["bid_max"]
                and price <= plan["bid"] + 1e-9
                and price < plan["ask"]
                and remaining * (price + fee_each) <= capacity + 1e-9
            )
        if valid:
            return result("One eligible WTI bid remains resting; do not stack another strike or chase a higher bid.")
        return result(
            "The working bid is stale, partially filled or outside its entry rules; cancel it and wait for confirmation.",
            cancels=order_ids,
        )

    if positions:
        return result("The exposure slot is occupied; hold the existing contracts for recorded settlement without adding risk.")

    budget = max(0.0, min(
        capacity,
        number(ctx.get("cash"), 0.0),
        number(ctx.get("equity"), 0.0),
    ))
    plans = []
    for market in markets.values():
        plan = quote_plan(market, now, params)
        if plan is not None:
            plans.append(plan)
    plans.sort(key=lambda plan: (plan["spread"], plan["resolve_hours"], plan["market"]))

    if not plans:
        return result("No WTI YES bid meets the frozen price band, spread and explicit settlement-clock requirements.")

    for plan in plans:
        price = plan["price"]
        fee_each = math.ceil(fee_rate * price * (1.0 - price) * 100.0) / 100.0
        quantity = int(math.floor(budget / (price + fee_each)))
        if quantity < 1:
            continue
        intent = {
            "market": plan["market"],
            "leg": "yes",
            "side": "buy",
            "quantity": quantity,
            "type": "limit",
            "limit_price": price,
            "post_only": True,
            "reason": "Test the reported WTI-only maker-favourite effect at a resting 90-93 cent YES bid, with one exposure and resolution within 48 hours.",
        }
        return result(
            "Submit one small post-only WTI bid with a conservative fee reserve; the reported historical effect remains unproven.",
            intents=[intent],
        )

    return result("Eligible WTI quotes exist, but available cash and limits cannot fund one whole contract plus the fee reserve.")

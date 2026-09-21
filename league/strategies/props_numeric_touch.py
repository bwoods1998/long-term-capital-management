"""Bounded numeric-prop underdog execution test, not a calibrated forecast."""

from datetime import datetime
from decimal import Decimal, ROUND_CEILING
import math


NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "numeric-props-underdog-touch",
    "series": [
        "KXNFLPASSYDS", "KXNFLRECYDS", "KXNFLRSHYDS",
        "KXMLBKS", "KXMLBOUTS", "KXWNBAPTS",
        "KXWNBAREB", "KXWNBAAST",
    ],
    "max_hours_to_close": 48,
    "wake_minutes": 5,
    "parameter_rules": {
        "bounds": {"max_spread": [0.01, 0.03]},
        "ordered": [["entry_ask_min", "underdog_ask_max"]],
        "frozen": [
            "entry_ask_min", "underdog_ask_max", "notional_usd",
            "min_hours_to_close", "max_all_in_price",
        ],
    },
}

PARAMS = {
    "entry_ask_min": 0.20,
    "underdog_ask_max": 0.40,
    "max_spread": 0.02,
    "notional_usd": 2.0,
    "min_hours_to_close": 0.25,
    "max_all_in_price": 0.42,
}


def number(value, default=None):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def answer(thought, memory, intents=None, cancels=None):
    return {
        "intents": intents or [],
        "cancels": cancels or [],
        "thought": thought,
        "memory": memory,
    }


def size_order(price, budget, rate, all_in_cap):
    # Settlement requires no exit trade. Reserve the full entry taker fee,
    # including upward cent rounding, even if a live residual becomes a maker.
    unit = Decimal(str(price))
    available = Decimal(str(budget))
    fee_rate = Decimal(str(rate))
    cap = Decimal(str(all_in_cap))
    quantity = int(available / unit)
    while quantity > 0:
        fee = (fee_rate * quantity * unit * (Decimal("1") - unit)).quantize(
            Decimal("0.01"), rounding=ROUND_CEILING
        )
        total = quantity * unit + fee
        if total <= available and total <= quantity * cap:
            return quantity, float(total)
        quantity -= 1
    return 0, 0.0


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get("params") or {})
    now = timestamp(ctx.get("now"))
    previous = ctx.get("memory") or {}
    last_submit = timestamp(previous.get("last_submit"))
    memory = {}
    if now is not None and last_submit is not None:
        if 0 <= now - last_submit <= 172800:
            memory["last_submit"] = previous["last_submit"]

    orders = ctx.get("open_orders") or []
    cancels = [
        order["order_id"] for order in orders
        if isinstance(order.get("order_id"), str)
    ][:20]
    if orders:
        return answer(
            "Cancel residual orders before considering another entry; do not chase the ask.",
            memory, cancels=cancels,
        )

    if any(number(position.get("quantity"), 0.0) > 0
           for position in (ctx.get("positions") or [])):
        return answer(
            "An exposure is already held to settlement; no additional correlated bets.",
            memory,
        )

    if now is None:
        return answer("No valid decision timestamp; entry withheld.", memory)
    if last_submit is not None and now - last_submit < 300:
        return answer("Wait for the previous submission to reconcile before retrying.", memory)

    limits = ctx.get("limits") or {}
    budget = min(
        params["notional_usd"],
        max(0.0, number(ctx.get("cash"), 0.0)),
        max(0.0, number(limits.get("max_order_usd"), 0.0)),
        max(0.0, number(limits.get("max_position_usd"), 0.0)),
    )
    if budget < params["entry_ask_min"]:
        return answer("Available cash or order limits cannot fund one eligible contract.", memory)

    fees = ctx.get("fees") or {}
    rate = max(0.07, number(fees.get("kalshi_taker_rate"), 0.07))
    allowed = set(NEEDS["series"])
    candidates = []
    for market in ctx.get("markets") or []:
        if market.get("series") not in allowed:
            continue
        ticker = market.get("market")
        if not isinstance(ticker, str) or not ticker:
            continue
        close = number(market.get("hours_to_close"))
        resolve = number(market.get("hours_to_resolve"))
        if close is None or resolve is None:
            continue
        # Do not substitute a formal close timestamp for expected payout time,
        # or infer pre-game/in-game status from either duration.
        if not params["min_hours_to_close"] <= close <= resolve <= 48.0:
            continue
        bid = number(market.get("yes_bid"))
        ask = number(market.get("yes_ask"))
        if bid is None or ask is None or not 0.0 < bid < ask < 1.0:
            continue
        price = math.ceil(ask * 100.0 - 1e-9) / 100.0
        if not params["entry_ask_min"] <= price <= params["underdog_ask_max"]:
            continue
        spread = price - bid
        if spread > params["max_spread"] + 1e-9:
            continue
        quantity, total = size_order(
            price, budget, rate, params["max_all_in_price"]
        )
        if quantity < 1:
            continue
        volume = max(0.0, number(market.get("volume_24h"), 0.0))
        # Volume only breaks ties; it is not evidence of executable depth.
        candidates.append((round(spread, 8), -volume, resolve, ticker,
                           price, quantity, total))

    if not candidates:
        return answer(
            "No allowlisted numeric prop meets the payout, two-sided quote, price, spread and fee-inclusive budget checks.",
            memory,
        )

    chosen = min(candidates)
    ticker, price, quantity, total = chosen[3:]
    memory["last_submit"] = ctx["now"]
    intent = {
        "market": ticker,
        "leg": "yes",
        "side": "buy",
        "quantity": quantity,
        "type": "limit",
        "limit_price": price,
        "post_only": False,
        "reason": (
            "Numeric-prop underdog YES execution test at the capped touch; "
            "fee-reserved total $" + format(total, ".2f") +
            ". Hold to settlement; no calibrated win probability is assumed."
        ),
    }
    return answer(
        "One numeric-prop underdog passes the cost and horizon checks. Its proposed edge remains unproven.",
        memory, intents=[intent],
    )

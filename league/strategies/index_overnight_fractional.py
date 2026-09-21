"""A capped fractional-share test of SPY close-to-open drift.

The clock is fixed before testing. This is not a claim that the published
auction-to-auction effect survives execution at 15:50 and 09:35.
"""

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


NEEDS = {
    "venue": "alpaca",
    "horizon": "hour",
    "style": "overnight-drift",
    "symbols": ["SPY"],
    "bars": {"timeframe": "5Min", "limit": 120},
    "wake_minutes": 5,
    "parameter_rules": {
        "bounds": {"spread_fraction": [0.0001, 0.001]},
        "frozen": ["notional_usd"],
    },
}

PARAMS = {"notional_usd": 2.0, "spread_fraction": 0.0003}

NY = ZoneInfo("America/New_York")


def number(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def reply(thought, memory, intents=None, cancels=None):
    return {
        "intents": intents or [],
        "cancels": cancels or [],
        "thought": thought,
        "memory": memory,
    }


def fresh_session_bar(ctx, now, day):
    bars = ctx.get("bars", {}).get("SPY", [])
    if not bars:
        return False
    bar = bars[-1]
    when = stamp(bar.get("t"))
    if when is None:
        return False
    age = (now - when).total_seconds()
    local = when.astimezone(NY)
    minute = local.hour * 60 + local.minute
    return (
        0 <= age <= 600
        and local.date().isoformat() == day
        and 570 <= minute < 960
        and number(bar.get("c")) > 0
        and number(bar.get("v")) > 0
    )


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get("params") or {})
    prior = ctx.get("memory") or {}
    memory = {}
    entry_day = prior.get("entry_day")
    if isinstance(entry_day, str) and len(entry_day) == 10:
        memory["entry_day"] = entry_day
    previous_refusal = prior.get("last_refusal")
    if isinstance(previous_refusal, str):
        memory["last_refusal"] = previous_refusal[:240]
    for outcome in (ctx.get("recent_order_outcomes") or [])[-12:]:
        if outcome.get("status") == "refused":
            source = (
                "House"
                if outcome.get("submitted_to_venue") is False
                else "Reported"
            )
            memory["last_refusal"] = (
                source + ": " + str(outcome.get("reason", "unspecified"))
            )[:240]

    now = stamp(ctx.get("now"))
    if now is None:
        return reply("Missing a valid decision clock; no action.", memory)
    local = now.astimezone(NY)
    day = local.date().isoformat()
    minute = local.hour * 60 + local.minute
    regular = local.weekday() < 5 and 570 <= minute < 960
    entry_window = regular and 950 <= minute <= 955

    positions = [
        position for position in (ctx.get("positions") or [])
        if number(position.get("quantity")) > 0
    ]
    owned = [position for position in positions if position.get("symbol") == "SPY"]
    quantity = sum(number(position.get("quantity")) for position in owned)
    orders = ctx.get("open_orders") or []

    # Do not replace an order until its disappearance is confirmed in ctx.
    # A partial buy fill also cancels the unfilled remainder before any exit.
    if orders:
        cancels = []
        for order in orders:
            if order.get("symbol") != "SPY":
                continue
            submitted = stamp(order.get("submitted_at"))
            age = (now - submitted).total_seconds() if submitted else None
            expired = age is None or age < 0 or age >= 300
            wrong_day = submitted is None or submitted.astimezone(NY).date().isoformat() != day
            invalid_buy = order.get("side") == "buy" and (
                not entry_window or quantity > 0 or wrong_day
            )
            if expired or invalid_buy or not regular:
                order_id = order.get("order_id")
                if isinstance(order_id, str) and order_id:
                    cancels.append(order_id)
        return reply(
            "Waiting for outstanding orders; cancel stale or out-of-window commitments before another action.",
            memory,
            cancels=cancels[:20],
        )

    if not regular:
        return reply("Outside the regular weekday session; no new orders.", memory)
    if not fresh_session_bar(ctx, now, day):
        return reply(
            "No fresh positive-volume regular-session bar; do not assume a holiday or closed session is executable.",
            memory,
        )

    if quantity > 0:
        held_overnight = False
        for position in owned:
            opened = stamp(position.get("opened_at"))
            if opened is None:
                if memory.get("entry_day") != day:
                    held_overnight = True
            elif opened.astimezone(NY).date() != local.date():
                held_overnight = True
        # An unexpected daytime holding is also flattened. A same-day
        # late-afternoon fill is held for the next session, not round-tripped.
        if minute >= 575 and (held_overnight or minute < 950):
            sell_quantity = math.floor(quantity * 1000000000) / 1000000000
            if sell_quantity <= 0:
                return reply("Only sub-step SPY dust remains; no additional exposure.", memory)
            return reply(
                "Exit the overnight holding at the first available session wake after 09:35; no spread filter delays liquidation.",
                memory,
                intents=[{
                    "symbol": "SPY",
                    "side": "sell",
                    "quantity": sell_quantity,
                    "type": "market",
                    "reason": "Close the overnight SPY holding at the first fresh regular-session opportunity at or after 09:35 New York.",
                }],
            )
        return reply("Hold the late-session SPY entry until the next session's exit window.", memory)

    if positions:
        return reply("Unexpected non-SPY holdings are present; add no exposure.", memory)
    if not entry_window:
        return reply("Flat; the fixed entry window is 15:50 through 15:55 New York.", memory)
    if memory.get("entry_day") == day:
        return reply("Today's single entry attempt has already been used; do not retry a refusal or cancellation.", memory)

    quote = ctx.get("quotes", {}).get("SPY", {})
    quoted = stamp(quote.get("t"))
    if quoted is None or not 0 <= (now - quoted).total_seconds() <= 90:
        return reply("No fresh SPY quote; skip the overnight entry.", memory)
    bid = number(quote.get("bid"))
    ask = number(quote.get("ask"))
    if bid <= 0 or ask < bid:
        return reply("Invalid or crossed SPY quote; skip entry.", memory)
    midpoint = (bid + ask) / 2
    spread = (ask - bid) / midpoint
    if spread > number(params.get("spread_fraction")):
        return reply("The quoted spread exceeds the predeclared entry cap.", memory)

    limits = ctx.get("limits") or {}
    cash = max(0.0, number(ctx.get("cash")))
    budget = min(
        2.0,
        max(0.0, number(params.get("notional_usd"))),
        cash * 0.98,
        max(0.0, number(limits.get("max_order_usd"))),
        max(0.0, number(limits.get("max_position_usd"))),
    )
    budget = math.floor(budget * 100) / 100
    if budget < 1.0:
        return reply("Less than $1 fits cash and House limits after the buffer; skip entry.", memory)

    memory["entry_day"] = day
    return reply(
        "Test the published overnight hypothesis with one capped fractional entry; profitability remains unproven.",
        memory,
        intents=[{
            "symbol": "SPY",
            "side": "buy",
            "notional_usd": budget,
            "type": "market",
            "reason": "Test SPY close-to-open drift with a fractional entry in the fixed late-session window, capped at $2 and a narrow quoted spread.",
        }],
    )

import datetime
import math


NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "nfl-total-favorite-maker",
    "series": ["KXNFLTOTAL"],
    "max_hours_to_close": 48,
    "wake_minutes": 5,
    "parameter_rules": {
        "bounds": {"max_spread": [0.02, 0.04]},
        "ordered": [["minimum_hours", "maximum_hours"]],
        "frozen": [
            "bid_min", "bid_max", "minimum_hours", "maximum_hours",
            "order_ttl_minutes", "entry_budget_usd"
        ]
    }
}

PARAMS = {
    "bid_min": 0.93,
    "bid_max": 0.97,
    "max_spread": 0.04,
    "minimum_hours": 6.0,
    "maximum_hours": 36.0,
    "order_ttl_minutes": 60,
    "entry_budget_usd": 2.0
}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        result = parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def event_key(ticker):
    return "-".join(ticker.split("-")[:2])


def reserve_fee(quantity, price, rate):
    return math.ceil(rate * quantity * price * (1.0 - price) * 10000.0) / 10000.0


def quotes(row, params):
    ticker = row.get("market", "")
    if not isinstance(ticker, str) or not ticker.startswith("KXNFLTOTAL-"):
        return None
    if row.get("series") != "KXNFLTOTAL":
        return None
    resolve = number(row.get("hours_to_resolve"))
    close = number(row.get("hours_to_close"))
    if resolve is None or close is None:
        return None
    if not params["minimum_hours"] <= resolve <= params["maximum_hours"]:
        return None
    if not 0.0 < close <= 48.0:
        return None
    bid = number(row.get("yes_bid"))
    ask = number(row.get("yes_ask"))
    if bid is None or ask is None or not 0.0 < bid < ask < 1.0:
        return None
    if ask - bid > params["max_spread"] + 1e-10:
        return None
    return {"yes": (bid, ask), "no": (1.0 - ask, 1.0 - bid)}


def eligible_leg(pair, params):
    bid, ask = pair
    price = math.floor(bid * 100.0 + 1e-9) / 100.0
    if not params["bid_min"] <= price <= params["bid_max"]:
        return None
    if price >= ask - 1e-10:
        return None
    return price


def result(intents, cancels, thought, memory):
    return {
        "intents": intents,
        "cancels": list(dict.fromkeys(cancels))[:20],
        "thought": thought,
        "memory": memory
    }


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get("params") or {})
    orders = ctx.get("open_orders") or []
    positions = ctx.get("positions") or []
    buys = [order for order in orders if order.get("side") == "buy"]
    buy_ids = [order["order_id"] for order in buys if order.get("order_id")]
    now = timestamp(ctx.get("now"))
    if now is None:
        return result([], buy_ids, "The decision clock is unavailable; cancel entry commitments.", {})

    previous = ctx.get("memory") or {}
    prior_seen = previous.get("seen") or {}
    seen = {}
    if isinstance(prior_seen, dict):
        for event, value in prior_seen.items():
            when = number(value)
            if isinstance(event, str) and when is not None and 0.0 <= now - when <= 259200.0:
                seen[event] = when
    for holding in positions:
        ticker = holding.get("market")
        quantity = number(holding.get("quantity"))
        if isinstance(ticker, str) and quantity is not None and quantity > 0.0:
            seen[event_key(ticker)] = now
    for order in buys:
        ticker = order.get("market")
        filled = number(order.get("filled", 0.0))
        if isinstance(ticker, str) and filled is not None and filled > 0.0:
            seen[event_key(ticker)] = now
    seen = dict(sorted(seen.items(), key=lambda item: item[1], reverse=True)[:32])
    memory = {"seen": seen}
    for outcome in (ctx.get("recent_order_outcomes") or [])[-12:]:
        if outcome.get("status") == "refused":
            memory["last_refusal"] = str(outcome.get("reason", ""))[:180]

    # A holding consumes the entire strategy's exposure slot. Never average down.
    if positions:
        return result([], buy_ids, "Hold the existing exposure to settlement and cancel all remaining entry bids.", memory)

    cash = number(ctx.get("cash"))
    equity = number(ctx.get("equity"))
    limits = ctx.get("limits") or {}
    order_cap = number(limits.get("max_order_usd"))
    position_cap = number(limits.get("max_position_usd"))
    stated_rate = number((ctx.get("fees") or {}).get("kalshi_taker_rate", 0.07))
    values = [cash, equity, order_cap, position_cap, stated_rate]
    if any(value is None or value < 0.0 for value in values):
        return result([], buy_ids, "Account limits or fee inputs are unavailable; no entry is safe to size.", memory)
    rate = max(0.07, stated_rate)
    budget = min(params["entry_budget_usd"], cash, 0.25 * equity, order_cap, position_cap)
    markets = {
        row["market"]: row
        for row in (ctx.get("markets") or [])
        if isinstance(row.get("market"), str)
    }
    risk = ctx.get("event_risk") or {}
    remaining = risk.get("remaining_by_market_usd")

    # Cancellation proceeds are never reused within this decision. Existing
    # orders already consume reported remaining headroom, so do not subtract
    # their commitment from that headroom a second time.
    if orders:
        if len(orders) != 1 or len(buys) != 1:
            return result([], buy_ids, "Wait for excess or unexpected commitments to clear before considering an entry.", memory)
        order = buys[0]
        ticker = order.get("market", "")
        row = markets.get(ticker, {})
        pairs = quotes(row, params)
        leg = order.get("leg")
        price = number(order.get("limit_price"))
        quantity = number(order.get("quantity"))
        filled = number(order.get("filled", 0.0))
        submitted = timestamp(order.get("submitted_at"))
        valid = pairs is not None and leg in ("yes", "no")
        valid = valid and price is not None and quantity is not None and filled == 0.0
        valid = valid and submitted is not None
        if valid:
            current_bid, current_ask = pairs[leg]
            valid = eligible_leg(pairs[leg], params) is not None
            valid = valid and params["bid_min"] <= price <= params["bid_max"]
            valid = valid and price < current_ask and price <= current_bid + 1e-10
            valid = valid and quantity >= 1.0 and quantity == math.floor(quantity)
            valid = valid and 0.0 <= now - submitted <= 60.0 * params["order_ttl_minutes"]
            valid = valid and event_key(ticker) not in seen
            if valid:
                cost = quantity * price + reserve_fee(quantity, price, rate)
                valid = quantity * price >= 1.0 and cost <= budget + 1e-10
            if valid and remaining is not None:
                headroom = number(remaining.get(ticker)) if isinstance(remaining, dict) else None
                valid = headroom is not None and headroom >= 0.0
        if valid:
            return result([], [], "Keep the eligible resting bid and its queue priority; do not add another exposure.", memory)
        return result([], buy_ids, "Cancel the expired, partial or no-longer-eligible entry and wait for confirmation.", memory)

    if budget < 1.0:
        return result([], [], "Available risk budget is below the venue minimum; do not enlarge it to force a trade.", memory)

    candidates = []
    for ticker, row in markets.items():
        if event_key(ticker) in seen:
            continue
        pairs = quotes(row, params)
        if pairs is None:
            continue
        market_budget = budget
        if remaining is not None:
            headroom = number(remaining.get(ticker)) if isinstance(remaining, dict) else None
            if headroom is None or headroom <= 0.0:
                continue
            market_budget = min(market_budget, headroom)
        for leg in ("yes", "no"):
            price = eligible_leg(pairs[leg], params)
            if price is None:
                continue
            quantity = math.floor(market_budget / price)
            while quantity > 0:
                total = quantity * price + reserve_fee(quantity, price, rate)
                if total <= market_budget + 1e-10:
                    break
                quantity -= 1
            if quantity < 1 or quantity * price < 1.0:
                continue
            spread = pairs[leg][1] - pairs[leg][0]
            candidates.append((spread, number(row["hours_to_resolve"]), ticker, leg, price, quantity))

    if not candidates:
        return result([], [], "No NFL total has an eligible favourite bid, payout window and fully funded whole-contract order.", memory)
    candidates.sort()
    spread, resolve, ticker, leg, price, quantity = candidates[0]
    intent = {
        "market": ticker,
        "leg": leg,
        "side": "buy",
        "quantity": quantity,
        "type": "limit",
        "limit_price": price,
        "post_only": True,
        "reason": "Test a 93-97 cent NFL-total favourite at the resting bid, with explicit 6-36 hour payout and a $2 fee-reserved exposure cap."
    }
    return result([intent], [], "Join one NFL-total favourite bid without crossing; this is a small unproven maker test, not a probability forecast.", memory)

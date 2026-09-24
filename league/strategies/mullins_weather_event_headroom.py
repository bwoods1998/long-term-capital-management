# Corrected child of mullins-2; family: weather-favorites.
# Preserve the weather NO-favourite maker signal and hold fills to settlement.
# Budget entries across all strikes and both legs of each event.

from datetime import datetime, timezone
from decimal import Decimal

NEEDS = {'venue': 'kalshi',
 'horizon': 'day',
 'style': 'favorites-no',
 'series': ['KXRAIN',
            'KXHIGHLAX',
            'KXHIGHMIA',
            'KXHIGHNY',
            'KXLOWTNYC',
            'KXHIGHTATL',
            'KXHIGHCHI',
            'KXHIGHAUS',
            'KXRAINDNYC',
            'KXHIGHTPHX',
            'KXHIGHDEN',
            'KXRAINWKND'],
 'max_hours_to_close': 30,
 'wake_minutes': 60}
PARAMS = {'bid_min': 0.9,
 'bid_max': 0.97,
 'max_spread': 0.03,
 'min_hours': 1.0,
 'max_hours': 30.0,
 'min_volume_24h': 1000,
 'notional_usd': 10.0,
 'max_open': 6,
 'requote_minutes': 180}
LEG = "no"
EPS = 1e-9
MAX_MARKET_SHARE = 0.30
MAX_EVENT_SHARE = Decimal("0.25")
ZERO = Decimal("0")


def _num(value, default=None):
    """A finite float, or the default for anything else."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float("inf") else default


def _amount(value, default=0.0):
    return Decimal(str(_num(value, default)))


def _event(ticker):
    return "-".join(str(ticker).split("-")[:2])


def _when(text):
    """ISO-8601 text as an aware datetime, or None."""
    try:
        clean = str(text).strip()
        if clean[-1:] in "Zz":
            clean = clean[:-1] + "+00:00"
        moment = datetime.fromisoformat(clean)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _touch(market):
    yes_bid, yes_ask = _num(market.get("yes_bid")), _num(market.get("yes_ask"))
    if yes_bid is None or yes_ask is None or not 0.0 < yes_bid < yes_ask < 1.0:
        return None
    return round(1.0 - yes_ask, 4), round(1.0 - yes_bid, 4)


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    knob = lambda name: _num(p.get(name), float(PARAMS[name]))
    now = _when(ctx.get("now"))
    markets = [m for m in ctx.get("markets") or [] if isinstance(m, dict) and m.get("market")]
    positions = [x for x in ctx.get("positions") or [] if isinstance(x, dict) and (_num(x.get("quantity"), 0.0) or 0.0) > 0]
    orders = [o for o in ctx.get("open_orders") or [] if isinstance(o, dict)]
    busy = {str(x.get("market")) for x in positions} | {str(o.get("market")) for o in orders}

    # A cancellation releases neither a slot nor event capacity until confirmed.
    cancels = []
    for order in orders:
        sent = _when(order.get("submitted_at"))
        if order.get("side") == "buy" and order.get("order_id") and sent is not None and now is not None:
            if (now - sent).total_seconds() / 60.0 > knob("requote_minutes"):
                cancels.append(str(order["order_id"]))

    event_used = {}
    for position in positions:
        event = _event(position.get("market"))
        cost = max(ZERO, _amount(position.get("quantity"))) * max(ZERO, _amount(position.get("average_cost"), 1.0))
        event_used[event] = event_used.get(event, ZERO) + cost
    for order in orders:
        if order.get("side") != "buy":
            continue
        event = _event(order.get("market"))
        remaining = max(ZERO, _amount(order.get("quantity")) - max(ZERO, _amount(order.get("filled"))))
        cost = remaining * max(ZERO, _amount(order.get("limit_price"), 1.0))
        event_used[event] = event_used.get(event, ZERO) + cost
    event_cap = max(ZERO, _amount(ctx.get("equity"))) * MAX_EVENT_SHARE

    found = []
    for market in markets:
        touch = _touch(market)
        hours, volume = _num(market.get("hours_to_close")), _num(market.get("volume_24h"), 0.0)
        if touch is None or hours is None:
            continue
        bid, ask = touch
        if not knob("bid_min") - EPS <= bid <= knob("bid_max") + EPS or ask - bid > knob("max_spread") + EPS:
            continue
        if not knob("min_hours") <= hours <= knob("max_hours") or volume < knob("min_volume_24h"):
            continue
        found.append((-volume, str(market["market"]), bid, ask, hours))
    found.sort()

    limits = ctx.get("limits") or {}
    want = knob("notional_usd")
    reserved = sum((_num(o.get("quantity"), 0.0) or 0.0) * (_num(o.get("limit_price"), 0.0) or 0.0) for o in orders if o.get("side") == "buy")
    free = ((_num(ctx.get("cash"), 0.0) or 0.0) - reserved) * 0.98
    per_market = min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want))
    equity = _num(ctx.get("equity"))
    if equity is not None and equity > 0:
        per_market = min(per_market, MAX_MARKET_SHARE * equity)
    slots = min(int(knob("max_open")) - len(busy), 8)

    intents = []
    for minus_volume, ticker, bid, ask, hours in found:
        if len(intents) >= slots:
            break
        if ticker in busy:
            continue
        event = _event(ticker)
        headroom = max(ZERO, event_cap - event_used.get(event, ZERO))
        budget = max(ZERO, min(_amount(per_market), _amount(free), headroom))
        price = _amount(bid)
        quantity = int(budget / price)
        cost = quantity * price
        if quantity < 1 or cost < Decimal("1"):
            continue
        event_used[event] = event_used.get(event, ZERO) + cost
        free -= float(cost)
        intents.append({
            "market": ticker, "leg": LEG, "side": "buy", "quantity": quantity, "type": "limit",
            "limit_price": bid, "post_only": True,
            "reason": (f"Resting a post-only {LEG.upper()} bid for {quantity} at {bid:.2f} on {ticker}: "
                       f"favourite in the {knob('bid_min'):.2f}-{knob('bid_max'):.2f} band, "
                       f"ask {ask:.2f}, {hours:.1f}h to close and {-minus_volume:.0f} contracts traded today. "
                       "Sized within remaining event capacity; held to settlement."),
        })
        busy.add(ticker)

    thought = (f"Saw {len(markets)} open markets, {len(found)} favourites in the band with a tight spread and enough volume. "
               f"Rested {len(intents)} event-budgeted NO bids and requested {len(cancels)} stale cancellations.")
    return {"intents": intents, "cancels": cancels[:20], "thought": thought, "memory": {}}

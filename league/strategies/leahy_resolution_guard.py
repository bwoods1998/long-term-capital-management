# SPECIALTY: kalshi-attention (Counts, ratings and mentions on Kalshi).
# Corrected child of Leahy, family attention-favorites. Starts with no record.
# Preserve the parent's maker-favourite logic, but screen resolution separately
# from trading close time: a day-horizon entry must resolve within 48 hours.

from datetime import datetime, timezone

NEEDS = {'venue': 'kalshi',
 'horizon': 'day',
 'style': 'favorites-daily',
 'series': ['KXRT',
            'KXTRUMPAPPROVE',
            'KXTRUMPSAY',
            'KXTRUTHSOCIAL',
            'KXANTHSHARE',
            'KXTENCENTSHARE',
            'KXDEEPSHARE',
            'KXBABASHARE',
            'KXGOOGSHARE',
            'KXTRUMPACT',
            'KXOPENSHARE',
            'KXTOKENUSE'],
 'max_hours_to_close': 40,
 'wake_minutes': 60}
PARAMS = {'bid_min': 0.9,
 'bid_max': 0.97,
 'max_spread': 0.03,
 'min_hours': 1.0,
 'max_hours': 40.0,
 'min_volume_24h': 500,
 'notional_usd': 10.0,
 'max_open': 6,
 'requote_minutes': 180}
LEG = "yes"
EPS = 1e-9
MAX_MARKET_SHARE = 0.30  # the House lets one market be about 30% of the agent's equity


def _num(value, default=None):
    """A finite float, or the default for anything else (None, text, NaN)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float("inf") else default


def _when(text):
    """ISO-8601 text as an aware datetime (UTC when it has no offset), or None."""
    try:
        clean = str(text).strip()
        if clean[-1:] in "Zz":
            clean = clean[:-1] + "+00:00"
        moment = datetime.fromisoformat(clean)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _touch(market):
    """(bid, ask) of the leg this seed buys, from the YES touch the market row carries."""
    bid, ask = _num(market.get("yes_bid")), _num(market.get("yes_ask"))
    if bid is None or ask is None or not 0.0 < bid < ask < 1.0:
        return None
    return round(bid, 4), round(ask, 4)


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    knob = lambda name: _num(p.get(name), float(PARAMS[name]))
    now = _when(ctx.get("now"))
    markets = [m for m in ctx.get("markets") or [] if isinstance(m, dict) and m.get("market")]
    positions = [x for x in ctx.get("positions") or [] if isinstance(x, dict) and (_num(x.get("quantity"), 0.0) or 0.0) > 0]
    orders = [o for o in ctx.get("open_orders") or [] if isinstance(o, dict)]
    busy = {str(x.get("market")) for x in positions} | {str(o.get("market")) for o in orders}

    # Stale quotes go first. A cancelled order still counts as busy until the next wake shows it gone.
    cancels = []
    for order in orders:
        sent = _when(order.get("submitted_at"))
        if order.get("side") == "buy" and order.get("order_id") and sent is not None and now is not None:
            if (now - sent).total_seconds() / 60.0 > knob("requote_minutes"):
                cancels.append(str(order["order_id"]))

    found = []
    for market in markets:
        # Closing soon does not imply paying soon. Unknown resolution is ineligible.
        resolve_hours = _num(market.get("hours_to_resolve"))
        if resolve_hours is None or not 0.0 <= resolve_hours <= 48.0:
            continue
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
    free = ((_num(ctx.get("cash"), 0.0) or 0.0) - reserved) * 0.98  # 2% headroom
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
        quantity = int(min(per_market, free) / bid + EPS)
        if quantity < 1 or quantity * bid < 1.0:
            continue
        free -= quantity * bid
        intents.append({
            "market": ticker, "leg": LEG, "side": "buy", "quantity": quantity, "type": "limit",
            "limit_price": bid, "post_only": True,
            "reason": (f"Resting a post-only {LEG.upper()} bid for {quantity} at {bid:.2f} on {ticker}: the favourite sits in the "
                       f"{knob('bid_min'):.2f}-{knob('bid_max'):.2f} band ({LEG.upper()} bid {bid:.2f}, ask {ask:.2f}), {hours:.1f}h to close, "
                       f"{-minus_volume:.0f} contracts traded today. Maker bids on favourites above 90c earned +2.15c a contract in the first run; held to settlement."),
        })

    thought = (f"Saw {len(markets)} open markets, {len(found)} of them favourites in the band with a tight spread and enough volume, within the resolution horizon. "
               f"Rested {len(intents)} new {LEG.upper()} bids and cancelled {len(cancels)} stale ones; {len(busy)} of {int(knob('max_open'))} slots were already in use.")
    return {"intents": intents, "cancels": cancels, "thought": thought, "memory": {}}

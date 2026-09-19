# favorites-no: the mirror of favorites-maker on the NO leg. When YES is a 3 to 10 cent longshot,
# NO is the 90 to 97 cent favourite: rest a post-only NO bid and hold it to settlement.
#
# THE IDEA. "Betting against" a Kalshi market is buying its NO leg. The NO touch is the YES touch
# seen from the other side: NO bid = 1 - YES ask, NO ask = 1 - YES bid. When the YES ask is 10
# cents or less the NO leg is the favourite, and the people lifting that cheap YES offer are the
# longshot buyers who lose the most. Waiting on the NO bid is being their counterparty.
#
# THE EVIDENCE. Across 72 million Kalshi trades NO beat YES at most prices, takers lose about
# 1.1% and makers earn it, and buying at 10 cents or less lost 0.9 to 6.7 cents a contract. The
# first run's one measured edge was resting maker bids on favourites above 90 cents: +2.15 cents a
# contract out of sample (interval +1.62 to +2.72). Crypto favourites were the weak group on a
# small sample, and this seed trades the crypto hourlies (no maker fee there): it has to earn its
# own record.
#
# WHAT IT NEEDS. The open markets of the hourly BTC and ETH strike series, with the YES touch,
# hours to close and the day's volume. No bars, no memory.
#
# WHEN IT TRADES. A market qualifies when its NO bid (1 - YES ask) is between bid_min and bid_max,
# the spread is at most max_spread, it closes in min_hours to max_hours and volume_24h is at least
# min_volume_24h. It rests a post-only NO bid AT the current NO bid (never above it, so it can
# never cross the NO ask), sized notional_usd in whole contracts. At most max_open markets at
# once, counting holdings and resting orders, and never a second order in a market it is already
# in (either leg). The busiest markets are taken first.
#
# HOW IT EXITS. It does not sell: a filled contract is held to settlement and pays $1 or $0. A
# resting bid older than requote_minutes is cancelled; the slot is free again on the next wake.

from datetime import datetime, timezone

NEEDS = {
    "venue": "kalshi",
    "horizon": "hour",
    "style": "favorites-no",
    "series": ["KXBTCD", "KXETHD"],
    "max_hours_to_close": 12,
    "wake_minutes": 10,
}
PARAMS = {
    "bid_min": 0.90,
    "bid_max": 0.97,
    "max_spread": 0.03,
    "min_hours": 0.25,
    "max_hours": 6.0,
    "min_volume_24h": 2000,
    "notional_usd": 10.0,
    "max_open": 4,
    "requote_minutes": 30,
}
LEG = "no"
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
    yes_bid, yes_ask = _num(market.get("yes_bid")), _num(market.get("yes_ask"))
    if yes_bid is None or yes_ask is None or not 0.0 < yes_bid < yes_ask < 1.0:
        return None
    return round(1.0 - yes_ask, 4), round(1.0 - yes_bid, 4)  # NO bid = 1 - YES ask, NO ask = 1 - YES bid


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

    thought = (f"Saw {len(markets)} open markets, {len(found)} of them favourites in the band with a tight spread and enough volume. "
               f"Rested {len(intents)} new {LEG.upper()} bids and cancelled {len(cancels)} stale ones; {len(busy)} of {int(knob('max_open'))} slots were already in use.")
    return {"intents": intents, "cancels": cancels, "thought": thought, "memory": {}}

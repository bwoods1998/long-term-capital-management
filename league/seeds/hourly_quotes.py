# hourly-quotes: a two-sided maker in the hourly BTC strike markets. A CONTROL, not a proven edge.
#
# THE IDEA. In a wide, undecided market (mid between 25 and 75 cents, spread of 4 cents or more)
# rest a YES bid one cent above the best YES bid and a NO bid one cent above the best NO bid
# (NO bid = 1 - YES ask). If both fill, the pair cost at most 98 cents and pays exactly $1
# whichever way the hour settles: two cents or more locked in, and Kalshi charges makers nothing
# on the crypto series. If only one fills, the seed holds a one-sided bet bought inside the spread.
#
# THE EVIDENCE. Kalshi makers as a whole earn about 1.1% (72 million trades). But the first run
# measured NO edge for this particular strategy: its losing legs were the ones filled late in the
# hour, when the result was nearly known and only the wrong side still wanted to trade. It is
# here as a control the league is allowed to kill; do not read its presence as a recommendation.
#
# WHAT IT NEEDS. The open KXBTCD markets closing within the hour, with the YES touch. No memory.
#
# WHEN IT TRADES. A new market: mid in mid_min..mid_max, spread at least min_spread, closing in
# min_minutes..max_minutes (20 to 58: nothing new rests into the last twenty minutes), both
# improved bids still inside the touch (post-only, they can never cross), both at 15 cents or
# more, and YES bid + NO bid at most 1 - min_locked. Both legs get the SAME whole number of
# contracts, about notional_usd on the dearer leg. At most max_markets markets at once. A leg it
# already holds or already has an order on is never bid again; when exactly one leg has filled
# and the other has no order, it re-rests the missing leg (same contract count) only if the
# held cost plus the new bid still locks min_locked.
#
# HOW IT EXITS. It sells nothing: pairs and single legs are held to settlement. Resting bids
# older than requote_minutes are cancelled and replaced, if still wanted, on the next wake.

from datetime import datetime, timezone

NEEDS = {
    "venue": "kalshi",
    "horizon": "hour",
    "style": "maker",
    "series": ["KXBTCD"],
    "max_hours_to_close": 1,
    "wake_minutes": 5,
}
PARAMS = {
    "mid_min": 0.25,
    "mid_max": 0.75,
    "min_spread": 0.04,
    "min_minutes": 20,
    "max_minutes": 58,
    "improve": 0.01,
    "min_locked": 0.02,
    "notional_usd": 5.0,
    "max_markets": 2,
    "requote_minutes": 10,
}
EPS = 1e-9
MIN_PRICE = 0.15  # the House refuses opening event buys under 15 cents


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


def _bid(ticker, leg, quantity, price, why):
    return {"market": ticker, "leg": leg, "side": "buy", "quantity": quantity, "type": "limit",
            "limit_price": price, "post_only": True, "reason": why}


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    knob = lambda name: _num(p.get(name), float(PARAMS[name]))
    now = _when(ctx.get("now"))
    markets = [m for m in ctx.get("markets") or [] if isinstance(m, dict) and m.get("market")]
    positions = [x for x in ctx.get("positions") or [] if isinstance(x, dict) and (_num(x.get("quantity"), 0.0) or 0.0) > 0]
    orders = [o for o in ctx.get("open_orders") or [] if isinstance(o, dict)]
    held = {(str(x.get("market")), str(x.get("leg") or "yes")): x for x in positions}
    working = {str(o.get("market")) for o in orders}
    busy = {key[0] for key in held} | working

    cancels = []
    for order in orders:
        sent = _when(order.get("submitted_at"))
        if order.get("side") == "buy" and order.get("order_id") and sent is not None and now is not None:
            if (now - sent).total_seconds() / 60.0 > knob("requote_minutes"):
                cancels.append(str(order["order_id"]))

    limits = ctx.get("limits") or {}
    want = knob("notional_usd")
    reserved = sum((_num(o.get("quantity"), 0.0) or 0.0) * (_num(o.get("limit_price"), 0.0) or 0.0) for o in orders if o.get("side") == "buy")
    free = ((_num(ctx.get("cash"), 0.0) or 0.0) - reserved) * 0.98  # 2% headroom
    per_leg = min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want))
    slots = int(knob("max_markets")) - len(busy)
    improve, locked = knob("improve"), knob("min_locked")

    intents, quotable = [], 0
    for market in sorted(markets, key=lambda m: str(m["market"])):
        ticker = str(market["market"])
        yes_bid, yes_ask, hours = _num(market.get("yes_bid")), _num(market.get("yes_ask")), _num(market.get("hours_to_close"))
        if yes_bid is None or yes_ask is None or hours is None or not 0.0 < yes_bid < yes_ask < 1.0 or len(intents) > 6:
            continue
        minutes, spread, mid = hours * 60.0, yes_ask - yes_bid, (yes_bid + yes_ask) / 2.0
        prices = {"yes": round(yes_bid + improve, 2), "no": round(1.0 - yes_ask + improve, 2)}
        asks = {"yes": yes_ask, "no": 1.0 - yes_bid}
        if any(prices[leg] >= asks[leg] - EPS or prices[leg] < MIN_PRICE for leg in prices):
            continue  # an improved bid would cross the touch or sit under 15 cents
        legs_held = [leg for leg in ("yes", "no") if (ticker, leg) in held]
        if len(legs_held) == 1 and ticker not in working:
            # One leg filled, the other is gone: re-rest the missing leg if the pair still locks a profit.
            have, leg = held[(ticker, legs_held[0])], ("no" if legs_held[0] == "yes" else "yes")
            cost, price = _num(have.get("average_cost"), 1.0), prices[leg]
            quantity = int(min(_num(have.get("quantity"), 0.0), min(per_leg, free) / price) + EPS)
            if cost + price <= 1.0 - locked + EPS and quantity >= 1 and quantity * price >= 1.0:
                free -= quantity * price
                intents.append(_bid(ticker, leg, quantity, price,
                    f"Completing the pair on {ticker}: hold {legs_held[0].upper()} at {cost:.2f}, resting a post-only {leg.upper()} bid for {quantity} at "
                    f"{price:.2f}; together {cost + price:.2f}, paying $1 at settlement whichever way it goes."))
            continue
        if ticker in busy:
            continue
        if not knob("mid_min") - EPS <= mid <= knob("mid_max") + EPS or spread < knob("min_spread") - EPS:
            continue
        if not knob("min_minutes") <= minutes <= knob("max_minutes") or prices["yes"] + prices["no"] > 1.0 - locked + EPS:
            continue
        quotable += 1
        quantity = int(min(per_leg, free / 2.0) / max(prices.values()) + EPS)
        if slots < 1 or quantity < 1 or quantity * min(prices.values()) < 1.0:
            continue
        slots -= 1
        free -= quantity * (prices["yes"] + prices["no"])
        for leg in ("yes", "no"):
            intents.append(_bid(ticker, leg, quantity, prices[leg],
                f"Quoting both sides of {ticker}: mid {mid:.2f}, spread {spread:.2f}, {minutes:.0f} minutes to close. Post-only {leg.upper()} bid for "
                f"{quantity} at {prices[leg]:.2f}; the two bids total {prices['yes'] + prices['no']:.2f}, so a filled pair locks {1.0 - prices['yes'] - prices['no']:.2f} a contract."))

    thought = (f"Saw {len(markets)} hourly markets, {quotable} new ones wide and undecided enough to quote. Rested {len(intents)} bids and cancelled "
               f"{len(cancels)} stale ones; {len(busy)} of {int(knob('max_markets'))} markets were already in use. This is a control with no measured edge.")
    return {"intents": intents, "cancels": cancels, "thought": thought, "memory": {}}

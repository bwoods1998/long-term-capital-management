"""House starter for the crypto family, maker side: rest post-only bids a spread under the
Coinbase mid, and when a coin is held, rest a post-only offer over cost that clears the fees.

Every run, for each symbol: read the quote; when the desk holds none of the coin, rest a
post-only bid at mid x (1 - spread) sized to the learning notional; when it holds some, rest a
post-only offer for the whole holding at the highest of cost x (1 + 2 x maker_fee + min_margin),
mid x (1 + spread / 2) and one tick over the ask, rounded up to the tick, so a fill closes the
round trip above cost after both maker fees. A round trip captures about `spread` measured from
cost (a bid `spread` under mid, an offer over cost), not twice the spread. Quotes older than
`requote_seconds`, or more than `drift` away from where they belong now, are cancelled and
replaced; an offer still at its target price and size is kept however old (an exit-only desk
would re-place each offer every 15 minutes, some 96 orders a day a coin against a 120-order desk
limit). A quote that would cross the book is refused by the venue and by the shadow book alike,
so the desk can never take.

The fee guard (Sept 17, 2026). This account pays 0.5% as a maker and 1.2% as a taker on its real
fills, so a round trip pays 1% in fees before it earns anything. The live desks quoted at a 1%
spread with the offer at cost x 1.01: a clean round trip netted about nothing, and a lot that hit
the 48-hour time stop paid the taker fee on top. A 90-day replay on one-minute candles for BTC,
ETH and SOL (June 19 - Sept 17) lost at every spread from 0.4% to 2% at a 0.5% maker fee:
-$0.64 a day per $100 lot per product at 1% [-1.04, -0.22], through a +21% BTC rally that
flattered long inventory. So bids are placed only when `bid` is true and the spread clears the
round trip: spread >= 2 x maker_fee + min_margin. Otherwise no bid target is built, and any
resting bid is cancelled because it no longer has one. The guard lives in code on purpose: a
promotion that copies a shadow's params onto the live desk cannot turn bids back on unless the
spread clears the fees, and `maker_fee` and `min_margin` only ever raise the bar -- the guard
never uses less than the values in DEFAULTS, which the Foundry may not change. Offers for held
inventory are always quoted, so a desk with bids off exits what it holds.

A holding worth less than `min_inventory_usd` is dust, not inventory: the venue will not take
an order that small, and on Sept 16, 2026 a few cents of ETH and BTC left by earlier round
trips kept the live desk offering dust it could not sell instead of bidding. Offer sizes are
rounded down, so an offer never exceeds the holding. A coin whose mid is under `min_price_usd`
gets no bid: prices print to the cent, and a one-cent step under a sub-dollar bid can go to zero.
A holding in such a coin is still offered, so it is never stranded.

Params: symbols, spread, drift, requote_seconds, notional_usd, max_symbols, min_inventory_usd,
maker_fee, min_margin, bid, min_price_usd.
"""

import math
from datetime import datetime, timezone

DEFAULTS = {
    "symbols": ["BTC-USD", "ETH-USD", "SOL-USD"],
    "spread": 0.004,
    "drift": 0.002,
    "requote_seconds": 900,
    "notional_usd": None,
    "max_symbols": 3,
    "min_inventory_usd": 1.0,
    # The maker rate on this account's real fills (Sept 16, 2026), and what a round trip must
    # clear on top of two of them before bids are placed.
    "maker_fee": 0.005,
    "min_margin": 0.002,
    "bid": True,
    "min_price_usd": 1.0,
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


def _up(value, tick=0.01):
    """An offer rounded up to the tick, so rounding never takes it under its floor or off the grid."""
    return round(math.ceil(value / tick - 1e-6) * tick, 2)


def _down_to(value, tick=0.01):
    """A bid rounded down to the tick: never over its target, never off the grid."""
    return round(math.floor(value / tick + 1e-6) * tick, 2)


def _down(quantity, places=6):
    """Round a size down, never up: a sell rounded up asks for more than the desk holds."""
    scale = 10 ** places
    return math.floor(quantity * scale + 1e-9) / scale


def _symbols(kit, spec, fallback, increments):
    """A list of product ids, or "top:N": the N most traded USD products on Coinbase right now,
    so the universe is the venue's, not a hand-written list. A listed row's `quote_increment`,
    when the kit carries one, is kept in `increments`."""
    if isinstance(spec, str) and spec.startswith("top:"):
        try:
            rows = kit.products(int(spec.split(":", 1)[1]))
        except Exception:
            rows = []
        symbols = []
        for r in rows:
            if r.get("symbol"):
                symbols.append(r["symbol"])
                if _num(r.get("quote_increment")):
                    increments[r["symbol"]] = _num(r.get("quote_increment"))
        if symbols:
            return symbols
        return list(fallback)
    return list(spec or fallback)


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 25.0)
    spread = float(p["spread"])
    # The account's real maker rate and the margin are floors: a param may raise them, never lower
    # them, so no promoted or Foundry-made setting can quote a spread the fees eat.
    fee = max(DEFAULTS["maker_fee"], _num(p.get("maker_fee"), 0.0) or 0.0)
    margin = max(DEFAULTS["min_margin"], _num(p.get("min_margin"), 0.0) or 0.0)
    round_trip = 2.0 * fee + margin
    bids_on = bool(p.get("bid", True)) and spread + 1e-12 >= round_trip
    if not p.get("bid", True):
        kit.say("bids off: params")
    elif not bids_on:
        kit.say(f"bids off: spread {spread * 100:.2f}% < 2*fee+margin {round_trip * 100:.2f}%")
    held = {}
    for x in ctx.get("positions") or []:
        if str(x.get("asset_class") or "") == "crypto" and _num(x.get("quantity"), 0) > 0:
            held[str(x.get("symbol"))] = (_num(x.get("quantity"), 0), _num(x.get("average_cost"), 0) or 0)
    resting = [o for o in (ctx.get("open_orders") or []) if o.get("strategy") == "spot_quotes"]
    cancels, intents, kept = [], [], {}
    targets = {}
    increments = {}
    for symbol in _symbols(kit, p["symbols"], DEFAULTS["symbols"], increments)[: int(p["max_symbols"])]:
        quote = kit.quote(symbol) or {}
        bid, ask = _num(quote.get("bid")), _num(quote.get("ask"))
        if not bid or not ask or ask <= 0:
            kit.say(f"{symbol}: no quote")
            continue
        mid = (bid + ask) / 2.0
        # Prices print to the cent, so a finer venue increment still steps a whole cent.
        tick = max(0.01, increments.get(symbol) or 0.01)
        inventory = held.get(symbol)
        if inventory is not None and _down(inventory[0]) * mid < float(p.get("min_inventory_usd") or 0):
            inventory = None  # dust: bid as if flat
        if inventory is None and mid < float(p.get("min_price_usd") or 0.0):
            # No bid on a sub-dollar coin; a holding in one is still offered below, never stranded.
            kit.say(f"{symbol}: mid {mid:.4f} is under {float(p['min_price_usd']):.2f}, no bid")
            continue
        if inventory is not None:
            quantity, cost = inventory
            quantity = _down(quantity)
            cost_floor = cost * (1.0 + round_trip)
            offer = _up(max(cost_floor, mid * (1.0 + spread / 2.0), ask + tick), tick)  # never cross: at or under the ask would take
            targets[(symbol, "sell")] = (offer, quantity, f"offer {quantity:.6f} {symbol} at {offer:,.2f}: cost {cost:,.2f}, mid {mid:,.2f}; at least {round_trip * 100:.1f}% over cost, which pays both {fee * 100:.1f}% maker fees and a {margin * 100:.1f}% margin. Exit rule: this offer is the exit; it is replaced when mid drifts {float(p['drift']) * 100:.1f}%, or after {int(p['requote_seconds']) // 60} min once its target has moved")
        elif bids_on:
            bid_price = _down_to(min(mid * (1.0 - spread), bid - tick), tick)  # never cross
            if bid_price <= 0:
                continue
            quantity = notional / bid_price
            targets[(symbol, "buy")] = (bid_price, quantity, f"bid {quantity:.6f} {symbol} at {bid_price:,.2f}, {spread * 100:.1f}% under mid {mid:,.2f}, post-only at the maker rate. Setup: market making, not a directional call; the edge is a spread wider than a round trip's {round_trip * 100:.1f}% of fees and margin. Exit: an offer at least {round_trip * 100:.1f}% over cost is posted the run after a fill; the bid is cancelled if mid drifts {float(p['drift']) * 100:.1f}% or after {int(p['requote_seconds']) // 60} min; 48h time stop on the inventory")
    for order in resting:
        key = (str(order.get("symbol")), str(order.get("side")))
        price = _num(order.get("limit_price"))
        placed = _when(order.get("submitted_at"))
        age = (now - placed).total_seconds() if placed else None
        target = targets.get(key)
        # An offer still at its target price and size is kept however old: re-placing it only
        # spends the desk's daily order count and its place in the queue, and the replacement of
        # an offer at the cost floor more than 3% over the bid is refused after the cancel.
        same = key[1] == "sell" and target is not None and price is not None and abs(price - target[0]) < 0.005 and f"{_num(order.get('quantity'), 0.0):.6f}" == f"{target[1]:.6f}"
        stale = age is not None and age > float(p["requote_seconds"]) and not same
        gone = target is None
        drifted = target is not None and price is not None and abs(price - target[0]) / max(target[0], 1e-9) > float(p["drift"])
        if stale or gone or drifted or key in kept:
            # `key in kept`: a second order on the same symbol and side is a duplicate (the floor
            # once lost track of its own quotes and posted a fresh bid every run); keep one.
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

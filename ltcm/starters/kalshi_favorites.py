"""House starter for the Kalshi events family: rest maker bids on the favorite side of liquid
markets across every category, where the longshot is overpriced.

On Kalshi a contract that trades at a few cents resolves YES less often than its price says, and
the favorite on the other side earns a small positive return (the favorite-longshot bias, found
across Kalshi's own trade history by Bürgi, Deng and Whelan, "Makers and Takers: The Economics of
the Kalshi Prediction Market", 2025). The edge is a few cents a contract, which a taker's fee
would mostly eat and a maker pays no fee on. So every run: list the open single markets (combos
excluded) settling between `min_hours` and `max_hours` from now, keep those whose YES ask is
between `yes_min` and `yes_max` with at least `min_volume_24h` contracts traded in the last day,
and rest a post-only NO bid one cent above the best NO bid, never at or through the NO ask, sized
to the learning notional. At most one position per event and `max_open_per_series` per series,
`max_new` new bids a run; a bid older than `requote_seconds` is cancelled and placed again at
the current book. Held to settlement.

Params: yes_min, yes_max, min_hours, max_hours, min_volume_24h, max_new, max_open_per_series,
requote_seconds, maker (false takes the NO ask instead, paying the fee), no_max (never pay more
than this for NO: a 99-cent bid risks 99 cents to make one), exclude_prefixes, pages,
notional_usd.
"""

import math
from datetime import datetime, timezone

DEFAULTS = {
    "yes_min": 0.02,
    "yes_max": 0.10,
    "min_hours": 1.0,
    "max_hours": 36.0,
    "min_volume_24h": 1000,
    "max_new": 3,
    "max_open_per_series": 2,
    "requote_seconds": 1800,
    "maker": True,
    "no_max": 0.98,
    "exclude_prefixes": ["KXMVE"],
    "pages": 8,
    "notional_usd": None,
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


def _fee(price):
    return math.ceil(0.07 * price * (1.0 - price) * 100.0) / 100.0


def _event(ticker):
    return "-".join(str(ticker or "").split("-")[:2])


def _series(ticker):
    return str(ticker or "").split("-")[0]


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 10.0)
    held_events, per_series, held = set(), {}, set()
    for x in ctx.get("positions") or []:
        ticker = str(x.get("market_id") or x.get("symbol") or "")
        if str(x.get("asset_class") or "event") != "event" or not ticker:
            continue
        held.add(ticker)
        held_events.add(_event(ticker))
        per_series[_series(ticker)] = per_series.get(_series(ticker), 0) + 1
    resting = [o for o in (ctx.get("open_orders") or []) if o.get("strategy") == "kalshi_favorites"]
    cancels, kept = [], set()
    for order in resting:
        placed = _when(order.get("submitted_at"))
        age = (now - placed).total_seconds() if placed else 0.0
        ticker = str(order.get("market_id") or "")
        if age > float(p["requote_seconds"]) or _event(ticker) in kept:
            if order.get("order_id"):
                cancels.append(order["order_id"])
            continue
        kept.add(_event(ticker))
        per_series[_series(ticker)] = per_series.get(_series(ticker), 0) + 1
    try:
        markets = kit.kalshi_markets(max_close_hours=float(p["max_hours"]), pages=int(p["pages"]))
    except Exception as exc:
        kit.say(f"market listing failed: {type(exc).__name__}")
        markets = []
    excluded = tuple(str(x) for x in (p.get("exclude_prefixes") or []))
    candidates = []
    for market in markets:
        ticker = str(market.get("ticker") or "")
        if not ticker or ticker in held or (excluded and ticker.startswith(excluded)):
            continue
        if str(market.get("status") or "open") not in ("open", "active"):
            continue
        close = _when(market.get("close_time"))
        if close is None:
            continue
        hours = (close - now).total_seconds() / 3600.0
        if not float(p["min_hours"]) <= hours <= float(p["max_hours"]):
            continue
        yes_ask, yes_bid = _num(market.get("yes_ask")), _num(market.get("yes_bid"))
        volume = _num(market.get("volume_24h"), 0.0) or 0.0
        if yes_ask is None or yes_bid is None or volume < float(p["min_volume_24h"]):
            continue
        if not float(p["yes_min"]) <= yes_ask <= float(p["yes_max"]):
            continue
        candidates.append((volume, ticker, market, hours, yes_ask, yes_bid))
    candidates.sort(key=lambda c: -c[0])
    intents = []
    for volume, ticker, market, hours, yes_ask, yes_bid in candidates:
        if len(intents) >= int(p["max_new"]):
            break
        event, series = _event(ticker), _series(ticker)
        if event in held_events or event in kept or per_series.get(series, 0) >= int(p["max_open_per_series"]):
            continue
        no_bid, no_ask = 1.0 - yes_ask, 1.0 - yes_bid
        if p.get("maker", True):
            price = round(min(no_bid + 0.01, no_ask - 0.01), 2)
            if price < no_bid - 1e-9 or price >= no_ask - 1e-9:
                continue  # never under the best bid, never at the ask; a one-cent spread joins the bid
            how = f"resting a post-only NO bid at {price:.2f}, a cent over the best NO bid, as a maker (no fee)"
        else:
            price = round(no_ask, 2)
            if price >= 0.99:
                continue
            how = f"taking the NO ask at {price:.2f} (fee {_fee(price):.2f})"
        if price > float(p.get("no_max") or 0.98):
            continue
        quantity = max(1, int(notional / price))
        intents.append(
            {
                "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": "no"},
                "side": "buy",
                "quantity": str(quantity),
                "order_type": "limit",
                "limit_price": f"{price:.2f}",
                **({"post_only": True} if p.get("maker", True) else {}),
                "rationale": (
                    f"Favorite: {ticker} ({str(market.get('title') or '')[:80]}) has YES at {yes_ask:.2f} with "
                    f"{volume:,.0f} contracts traded today and settles in {hours:.0f}h. Kalshi longshots resolve YES less "
                    f"often than their price implies (Bürgi, Deng and Whelan 2025), so the NO side is the favorite with the "
                    f"edge; {how}. One position per event. Holds to settlement; wrong if this band's settled NO record "
                    f"returns less than the fees it saved."
                ),
                "holding_period_hours": max(1, int(hours) + 1),
            }
        )
        held_events.add(event)
        per_series[series] = per_series.get(series, 0) + 1
    kit.say(f"{len(markets)} markets listed, {len(candidates)} in the band, {len(intents)} bid(s), {len(cancels)} requoted")
    return {"intents": intents, "cancels": cancels, "notes": f"{len(candidates)} favorites in band, {len(intents)} placed, {len(cancels)} cancelled"}

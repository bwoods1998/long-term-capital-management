"""House starter for the ranges family: price Kalshi's hourly BTC and ETH range buckets from
realized volatility and buy the cheaper side when the market has left it cheap.

Every run: read the open markets of each hourly series, keep the buckets that settle between
`min_minutes` and `max_minutes` from now, estimate the settlement distribution as lognormal with
the trailing hourly realized volatility scaled to the time left, shrink that probability
halfway toward the market's own price (the desks' recorded lesson: snapshot edges on these
books are half noise), subtract Kalshi's fee, and propose the best `max_intents` buckets whose
edge clears `min_edge`. Limit at the ask, so it fills. The floor caps a live desk's size at its
learning size whatever `notional_usd` says.

The desk owns this file: read the record with strategy_report, change what is wrong, and
redeploy. Params: series (list), symbols (map series -> spot symbol), bars_limit, min_minutes,
max_minutes, min_edge, shrink, notional_usd, max_intents.
"""

import math
import re
from datetime import datetime, timezone

DEFAULTS = {
    "series": ["KXBTC", "KXETH"],
    "symbols": {"KXBTC": "BTC-USD", "KXETH": "ETH-USD"},
    "bars_limit": 48,
    "min_minutes": 8,
    "max_minutes": 55,
    "min_edge": 0.02,
    "shrink": 0.5,
    "notional_usd": None,
    "max_intents": 2,
}
RANGE = re.compile(r"\$?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:to|-|–)\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)")


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


def _bounds(market):
    """The bucket's [low, high) from its subtitle or title, or None for a threshold market."""
    for key in ("yes_sub_title", "title"):
        found = RANGE.search(str(market.get(key) or ""))
        if found:
            lo, hi = _num(found.group(1)), _num(found.group(2))
            if lo is not None and hi is not None and hi > lo:
                return lo, hi
    return None


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _fee(price):
    """Kalshi: 0.07 x P x (1 - P) per contract, rounded up to the cent."""
    return math.ceil(0.07 * price * (1.0 - price) * 100.0) / 100.0


def _hourly_sigma(kit, symbol, limit):
    bars = kit.bars(symbol, "1h", limit) or []
    closes = [_num(b.get("close")) for b in bars if _num(b.get("close"))]
    if len(closes) < 12:
        return None
    rets = [math.log(b / a) for a, b in zip(closes[:-1], closes[1:]) if a > 0 and b > 0]
    if len(rets) < 10:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    return math.sqrt(var)


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    held = {str(x.get("market_id")) for x in (ctx.get("positions") or [])}
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 10.0)
    candidates = []
    for series in p["series"]:
        symbol = (p.get("symbols") or {}).get(series)
        if not symbol:
            continue
        spot = _num((kit.quote(symbol) or {}).get("last")) or _num((kit.quote(symbol) or {}).get("bid"))
        sigma_h = _hourly_sigma(kit, symbol, int(p["bars_limit"]))
        if not spot or not sigma_h:
            kit.say(f"{series}: no spot or volatility ({spot}, {sigma_h})")
            continue
        for market in kit.kalshi_series(series):
            ticker = str(market.get("ticker") or "")
            if ticker in held or str(market.get("status") or "open") not in ("open", "active"):
                continue
            close = _when(market.get("close_time"))
            bounds = _bounds(market)
            if close is None or bounds is None:
                continue
            minutes = (close - now).total_seconds() / 60.0
            if not float(p["min_minutes"]) <= minutes <= float(p["max_minutes"]):
                continue
            yes_ask, yes_bid = _num(market.get("yes_ask")), _num(market.get("yes_bid"))
            if yes_ask is None or yes_bid is None or yes_ask <= 0 or yes_ask >= 1:
                continue
            sigma = sigma_h * math.sqrt(max(minutes, 1.0) / 60.0)
            lo, hi = bounds
            prob = _phi(math.log(hi / spot) / sigma) - _phi(math.log(lo / spot) / sigma)
            market_p = (yes_ask + yes_bid) / 2.0
            shrunk = prob + float(p["shrink"]) * (market_p - prob)
            no_ask = 1.0 - yes_bid
            edge_yes = shrunk - yes_ask - _fee(yes_ask)
            edge_no = (1.0 - shrunk) - no_ask - _fee(no_ask)
            side, price, edge = ("yes", yes_ask, edge_yes) if edge_yes >= edge_no else ("no", no_ask, edge_no)
            if edge < float(p["min_edge"]) or price < 0.02 or price > 0.98:
                continue
            candidates.append((edge, ticker, side, price, prob, shrunk, market_p, minutes, spot, sigma, symbol, lo, hi))
    candidates.sort(key=lambda c: -c[0])
    intents = []
    for edge, ticker, side, price, prob, shrunk, market_p, minutes, spot, sigma, symbol, lo, hi in candidates[: int(p["max_intents"])]:
        quantity = max(1, int(notional / price))
        intents.append(
            {
                "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": side},
                "side": "buy",
                "quantity": str(quantity),
                "order_type": "limit",
                "limit_price": f"{price:.2f}",
                "rationale": (
                    f"{symbol} spot {spot:,.0f}, bucket {lo:,.0f}-{hi:,.0f} settles in {minutes:.0f} min; "
                    f"realized vol implies p(in bucket)={prob:.3f}, shrunk to {shrunk:.3f} against the market's {market_p:.2f}; "
                    f"{side.upper()} at {price:.2f} has {edge:.3f} of edge after fees. Holds to settlement."
                ),
                "holding_period_hours": 1,
            }
        )
    kit.say(f"{len(candidates)} candidate(s), {len(intents)} proposed")
    return {"intents": intents, "notes": f"{len(candidates)} buckets with edge >= {p['min_edge']}"}

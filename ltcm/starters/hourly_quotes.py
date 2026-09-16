"""House starter for the ranges family, maker side: rest bids on both legs of the hourly BTC
and ETH buckets nearest spot, a spread below fair value, and replace them as fair moves.

Kalshi pays the resting side. The floor's other ranges starter takes the ask when a bucket is
cheap; this one offers to be the other side of everyone else's taking. Every run: price the
nearest `buckets` of the next hourly market (realized volatility, shrunk halfway to the
market), then for each bucket rest a YES bid at fair minus `spread` and a NO bid at
(1 - fair) minus `spread`. If both fill the pair costs 1 - 2 x spread and pays 1 whichever way
the hour settles; if one fills the desk holds a position bought under fair. Quotes older than
`requote_seconds`, or whose implied fair has drifted more than `drift` from the current fair,
or on a market inside `min_minutes` of settlement, are cancelled and, when there is still
time, replaced. The floor caps a live desk's size at its learning size per leg.

Params: series, symbols, bars_limit, min_minutes, max_minutes, spread, drift, requote_seconds,
buckets, shrink, notional_usd.
"""

import math
import re
from datetime import datetime, timezone

DEFAULTS = {
    "series": ["KXBTC", "KXETH"],
    "symbols": {"KXBTC": "BTC-USD", "KXETH": "ETH-USD"},
    "vol_interval": "5m",
    "vol_bars": 36,
    "min_minutes": 12,
    "max_minutes": 58,
    "spread": 0.04,
    "drift": 0.02,
    "requote_seconds": 600,
    "buckets": 2,
    "shrink": 0.5,
    "notional_usd": None,
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
    for key in ("yes_sub_title", "title"):
        found = RANGE.search(str(market.get(key) or ""))
        if found:
            lo, hi = _num(found.group(1)), _num(found.group(2))
            if lo is not None and hi is not None and hi > lo:
                return lo, hi
    return None


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "60m": 3600}


def _hourly_sigma(kit, symbol, limit, interval="5m"):
    """Realized volatility per hour from `limit` bars of `interval`; the last three hours of
    five-minute bars by default, since two days of hourly bars overstated sub-hour volatility."""
    bars = kit.bars(symbol, interval, limit) or []
    closes = [_num(b.get("close")) for b in bars if _num(b.get("close"))]
    if len(closes) < 12:
        return None
    rets = [math.log(b / a) for a, b in zip(closes[:-1], closes[1:]) if a > 0 and b > 0]
    if len(rets) < 10:
        return None
    mean = sum(rets) / len(rets)
    per_bar = math.sqrt(sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1))
    return per_bar * math.sqrt(3600.0 / SECONDS.get(str(interval), 3600))


def _price(value, low=0.01, high=0.97):
    return min(high, max(low, round(value, 2)))


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 10.0)
    resting = [o for o in (ctx.get("open_orders") or []) if o.get("strategy") == "hourly_quotes"]
    cancels = []
    intents = []
    fair_by_market = {}
    for series in p["series"]:
        symbol = (p.get("symbols") or {}).get(series)
        if not symbol:
            continue
        quote = kit.quote(symbol) or {}
        spot = _num(quote.get("last")) or _num(quote.get("bid"))
        sigma_h = _hourly_sigma(kit, symbol, int(p.get("vol_bars") or 36), str(p.get("vol_interval") or "5m"))
        if not spot or not sigma_h:
            kit.say(f"{series}: no spot or volatility")
            continue
        buckets = []
        for market in kit.kalshi_series(series):
            ticker = str(market.get("ticker") or "")
            close = _when(market.get("close_time"))
            bounds = _bounds(market)
            if close is None or bounds is None or str(market.get("status") or "open") not in ("open", "active"):
                continue
            minutes = (close - now).total_seconds() / 60.0
            if minutes > float(p["max_minutes"]) or minutes < 0:
                continue
            lo, hi = bounds
            buckets.append((abs((lo + hi) / 2.0 - spot), ticker, minutes, lo, hi))
        buckets.sort(key=lambda b: b[0])
        for _, ticker, minutes, lo, hi in buckets[: int(p["buckets"])]:
            live = kit.kalshi_market(ticker) or {}
            yes_ask, yes_bid = _num(live.get("yes_ask")), _num(live.get("yes_bid"))
            if yes_ask is None or yes_bid is None:
                continue
            sigma = sigma_h * math.sqrt(max(minutes, 1.0) / 60.0)
            prob = _phi(math.log(hi / spot) / sigma) - _phi(math.log(lo / spot) / sigma)
            market_p = (yes_ask + yes_bid) / 2.0
            fair = prob + float(p["shrink"]) * (market_p - prob)
            fair_by_market[ticker] = (fair, minutes, symbol, lo, hi, spot, yes_bid, yes_ask)
    def target_price(info, leg):
        """Where this leg's bid belongs now: a spread under fair, never at or through the ask."""
        fair, minutes, symbol, lo, hi, spot, yes_bid, yes_ask = info
        raw = fair - float(p["spread"]) if leg == "yes" else (1.0 - fair) - float(p["spread"])
        price = _price(raw)
        ask = yes_ask if leg == "yes" else 1.0 - yes_bid
        if price >= ask:
            price = _price(ask - 0.01)
        return price

    # Retire quotes that are stale, drifted from where the bid belongs now, or on a market
    # about to settle.
    quoted = {}
    for order in resting:
        ticker = str(order.get("market_id") or "")
        age = None
        placed = _when(order.get("submitted_at"))
        if placed is not None:
            age = (now - placed).total_seconds()
        info = fair_by_market.get(ticker)
        price = _num(order.get("limit_price"))
        leg = str(order.get("right") or "").lower()
        stale = age is not None and age > float(p["requote_seconds"])
        gone = info is None or info[1] < float(p["min_minutes"])
        drifted = info is not None and price is not None and abs(price - target_price(info, leg)) > float(p["drift"])
        if stale or gone or drifted or (ticker, leg) in quoted:
            # a second quote on the same leg is a duplicate: keep one
            if order.get("order_id"):
                cancels.append(order["order_id"])
        else:
            quoted[(ticker, leg)] = price
    for ticker, info in fair_by_market.items():
        fair, minutes, symbol, lo, hi, spot, yes_bid, yes_ask = info
        if minutes < float(p["min_minutes"]):
            continue
        for leg in ("yes", "no"):
            if (ticker, leg) in quoted:
                continue
            price = target_price(info, leg)
            if price < 0.02:
                continue
            quantity = max(1, int(notional / price))
            intents.append(
                {
                    "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": leg},
                    "side": "buy",
                    "quantity": str(quantity),
                    "order_type": "limit",
                    "limit_price": f"{price:.2f}",
                    "rationale": (
                        f"Quote: {symbol} spot {spot:,.0f}, bucket {lo:,.0f}-{hi:,.0f} settles in {minutes:.0f} min; "
                        f"fair p(in bucket)={fair:.3f} (vol model shrunk to the market's {((yes_bid + yes_ask) / 2):.2f}); "
                        f"resting {leg.upper()} bid at {price:.2f}, {float(p['spread']):.2f} under fair, replaced on drift; "
                        f"the pair costs {1 - 2 * float(p['spread']):.2f} if both legs fill."
                    ),
                    "holding_period_hours": 1,
                }
            )
    kit.say(f"{len(fair_by_market)} bucket(s) priced, {len(quoted)} quote(s) kept, {len(cancels)} cancelled, {len(intents)} placed")
    return {"intents": intents, "cancels": cancels, "notes": f"{len(quoted)} kept, {len(cancels)} cancelled, {len(intents)} placed"}

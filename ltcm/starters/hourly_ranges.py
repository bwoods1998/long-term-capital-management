"""House starter for the ranges family: price Kalshi's crypto price markets (range buckets and
above/below thresholds, on every coin Coinbase also trades) from realized volatility and buy the
cheaper side when the market has left it cheap.

Every run: read the open markets of each hourly series, keep the buckets that settle between
`min_minutes` and `max_minutes` from now, estimate the settlement distribution as lognormal with
the trailing hourly realized volatility scaled to the time left, shrink that probability
halfway toward the market's own price (the desks' recorded lesson: snapshot edges on these
books are half noise), subtract Kalshi's fee, and propose the best `max_intents` buckets whose
edge clears `min_edge`. Limit at the ask, so it fills. The floor caps a live desk's size at its
learning size whatever `notional_usd` says.

The desk owns this file: read the record with strategy_report, change what is wrong, and
redeploy. Params: series ("all" for every series in CRYPTO_SERIES, or a list), symbols (map
series -> spot symbol, merged over CRYPTO_SERIES), bars_limit, min_minutes, max_minutes,
min_edge, min_price, shrink, notional_usd, max_intents, max_quotes (live quotes per run, across
all series).
"""

import math
import re
from datetime import datetime, timezone

#: Every Kalshi crypto price series with a Coinbase spot reference (Sept 16, 2026). The daily
#: and hourly thresholds (the D series) trade fifty times the volume of the range buckets.
CRYPTO_SERIES = {
    "KXBTC": "BTC-USD", "KXBTCD": "BTC-USD", "KXETH": "ETH-USD", "KXETHD": "ETH-USD",
    "KXSOLD": "SOL-USD", "KXSOLE": "SOL-USD", "KXXRP": "XRP-USD", "KXXRPD": "XRP-USD",
    "KXDOGE": "DOGE-USD", "KXDOGED": "DOGE-USD", "KXHYPE": "HYPE-USD", "KXHYPED": "HYPE-USD",
    "KXSHIBA": "SHIB-USD", "KXSHIBAD": "SHIB-USD",
}

DEFAULTS = {
    "series": "all",
    "symbols": {},
    # Volatility from the last three hours of five-minute bars. Two days of hourly bars
    # overstated sub-hour volatility in the quiet hours on Sept 16, 2026: the model priced the
    # at-the-money bucket at 0.21-0.28 against a market at 0.33-0.36, bought NO on both BTC
    # and ETH, and the market was right six times out of seven.
    "vol_interval": "5m",
    "vol_bars": 36,
    "min_minutes": 8,
    "max_minutes": 55,
    "min_edge": 0.02,
    "min_price": 0.02,
    "shrink": 0.5,
    "notional_usd": None,
    "max_intents": 2,
    "max_quotes": 16,
    "max_open_per_event": 2,
}
SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "60m": 3600}
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


def _strike(market):
    """What the contract pays on: ("between", lo, hi), ("above", k) or ("below", k), from the
    venue's strike fields, falling back to the bucket in the subtitle; None when unreadable."""
    kind = str(market.get("strike_type") or "").lower()
    lo, hi = _num(market.get("floor_strike")), _num(market.get("cap_strike"))
    if kind in ("greater", "greater_or_equal") and lo:
        return ("above", lo)
    if kind in ("less", "less_or_equal") and hi:
        return ("below", hi)
    if kind == "between" and lo and hi and hi > lo:
        return ("between", lo, hi)
    bounds = _bounds(market)
    return ("between", bounds[0], bounds[1]) if bounds else None


def _model_probability(strike, spot, sigma):
    """Lognormal P(YES) for a strike given spot and the volatility to settlement."""
    if strike[0] == "between":
        return _phi(math.log(strike[2] / spot) / sigma) - _phi(math.log(strike[1] / spot) / sigma)
    above = 1.0 - _phi(math.log(strike[1] / spot) / sigma)
    return above if strike[0] == "above" else 1.0 - above


def _strike_label(strike):
    if strike[0] == "between":
        return f"bucket {strike[1]:,.4g}-{strike[2]:,.4g}"
    return f"{strike[0]} {strike[1]:,.6g}"


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


def _hourly_sigma(kit, symbol, limit, interval="1h"):
    """Realized volatility per hour from `limit` bars of `interval`."""
    bars = kit.bars(symbol, interval, limit) or []
    closes = [_num(b.get("close")) for b in bars if _num(b.get("close"))]
    if len(closes) < 12:
        return None
    rets = [math.log(b / a) for a, b in zip(closes[:-1], closes[1:]) if a > 0 and b > 0]
    if len(rets) < 10:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    per_bar = math.sqrt(var)
    return per_bar * math.sqrt(3600.0 / SECONDS.get(str(interval), 3600))


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    held = {str(x.get("market_id")) for x in (ctx.get("positions") or [])}
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 10.0)
    symbols = {**CRYPTO_SERIES, **(p.get("symbols") or {})}
    series_list = list(CRYPTO_SERIES) if p["series"] == "all" else list(p["series"] or [])
    # No more than a couple of positions on one settlement: six at-the-money NO bets on one
    # hour cost a shadow desk half its book on Sept 16, 2026.
    open_by_event = {}
    for x in ctx.get("positions") or []:
        code = "-".join(str(x.get("market_id") or "").split("-")[:2])
        open_by_event[code] = open_by_event.get(code, 0) + 1
    spots = {}
    screened = []
    for series in series_list:
        symbol = symbols.get(series)
        if not symbol:
            continue
        if symbol not in spots:
            quote = kit.quote(symbol) or {}
            spot = _num(quote.get("last")) or _num(quote.get("bid"))
            sigma_h = _hourly_sigma(kit, symbol, int(p.get("vol_bars") or p.get("bars_limit") or 36), str(p.get("vol_interval") or "5m")) if spot else None
            spots[symbol] = (spot, sigma_h)
            if spot and sigma_h:
                kit.say(f"{symbol}: spot {spot:,.6g}, vol {sigma_h * 100:.2f}%/h")
        spot, sigma_h = spots[symbol]
        if not spot or not sigma_h:
            continue
        try:
            listing = kit.kalshi_series(series)
        except Exception:
            listing = []
        for market in listing:
            ticker = str(market.get("ticker") or "")
            if ticker in held or str(market.get("status") or "open") not in ("open", "active"):
                continue
            if open_by_event.get("-".join(ticker.split("-")[:2]), 0) >= int(p["max_open_per_event"]):
                continue
            close = _when(market.get("close_time"))
            strike = _strike(market)
            if close is None or strike is None:
                continue
            minutes = (close - now).total_seconds() / 60.0
            if not float(p["min_minutes"]) <= minutes <= float(p["max_minutes"]):
                continue
            sigma = sigma_h * math.sqrt(max(minutes, 1.0) / 60.0)
            prob = _model_probability(strike, spot, sigma)
            # Screen on the listing's own prices when it has them (the edge the live quote must
            # confirm); without them, nearest the money first.
            bid, ask = _num(market.get("yes_bid")), _num(market.get("yes_ask"))
            if bid is not None and ask is not None and 0 < ask < 1:
                rank = -abs(prob - (bid + ask) / 2.0)
            else:
                rank = -1.0 + min(abs((strike[1] + (strike[2] if strike[0] == "between" else strike[1])) / 2.0 - spot) / spot, 0.99)
            screened.append((rank, ticker, market, strike, minutes, sigma, prob, spot, symbol))
    screened.sort(key=lambda s: s[0])
    candidates = []
    for _, ticker, market, strike, minutes, sigma, prob, spot, symbol in screened[: int(p["max_quotes"])]:
        live = kit.kalshi_market(ticker) or {}
        yes_ask = _num(live.get("yes_ask")) or _num(market.get("yes_ask"))
        yes_bid = _num(live.get("yes_bid")) if _num(live.get("yes_bid")) is not None else _num(market.get("yes_bid"))
        if yes_ask is None or yes_bid is None or yes_ask <= 0 or yes_ask >= 1:
            continue
        market_p = (yes_ask + yes_bid) / 2.0
        shrunk = prob + float(p["shrink"]) * (market_p - prob)
        no_ask = 1.0 - yes_bid
        edge_yes = shrunk - yes_ask - _fee(yes_ask)
        edge_no = (1.0 - shrunk) - no_ask - _fee(no_ask)
        side, price, edge = ("yes", yes_ask, edge_yes) if edge_yes >= edge_no else ("no", no_ask, edge_no)
        if edge < float(p["min_edge"]) or price < max(0.02, float(p.get("min_price") or 0)) or price > 0.98:
            continue
        candidates.append((edge, ticker, side, price, prob, shrunk, market_p, minutes, spot, sigma, symbol, strike))
    candidates.sort(key=lambda c: -c[0])
    intents = []
    for edge, ticker, side, price, prob, shrunk, market_p, minutes, spot, sigma, symbol, strike in candidates[: int(p["max_intents"])]:
        quantity = max(1, int(notional / price))
        intents.append(
            {
                "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": side},
                "side": "buy",
                "quantity": str(quantity),
                "order_type": "limit",
                "limit_price": f"{price:.2f}",
                "rationale": (
                    f"{symbol} spot {spot:,.6g}, {_strike_label(strike)} settles in {minutes:.0f} min; "
                    f"realized vol implies p(YES)={prob:.3f}, shrunk to {shrunk:.3f} against the market's {market_p:.2f}; "
                    f"{side.upper()} at {price:.2f} has {edge:.3f} of edge after fees. Holds to settlement."
                ),
                "holding_period_hours": 1 if minutes <= 60 else max(1, int(minutes // 60) + 1),
            }
        )
    kit.say(f"{len(screened)} market(s) screened across {len(series_list)} series, {len(candidates)} with edge >= {p['min_edge']}, {len(intents)} proposed")
    return {"intents": intents, "notes": f"{len(candidates)} markets with edge >= {p['min_edge']} of {len(screened)} screened"}

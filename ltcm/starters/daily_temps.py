"""House starter for the weather family: price Kalshi's daily high-temperature markets from the
National Weather Service forecast and buy the cheaper side when the market has left it cheap.

Every run: for each city, read the NWS forecast (`kit.weather`), take the forecast high for
each market's settlement day, and treat the outcome as normal around that forecast with a
standard error of `sigma_day_ahead` degrees for a day-ahead forecast plus `sigma_per_day` for
each further day. A bucket "81° to 82°" pays if the settled high rounds to 81 or 82, so its
probability is the mass between 80.5 and 82.5; "83° or above" is the mass above 82.5; "74° or
below" the mass below 74.5. Shrink halfway toward the market, subtract the fee, quote the
nearest `max_quotes` markets live, and propose the best `max_intents` whose edge clears
`min_edge`, at the ask, held to settlement. The floor caps a live desk's size at its learning
size whatever `notional_usd` says.

Params: cities ("all" for every city the kit knows a series for, or names as Kalshi and the NWS
name them), sigma_day_ahead, sigma_per_day, min_edge, min_price, shrink, notional_usd,
max_intents, max_quotes, max_hours. `min_price` skips contracts cheaper than it: a thin tail
the normal curve overprices is the classic longshot a shadow variant can test against.
"""

import math
import re
from datetime import datetime, timezone

DEFAULTS = {
    "cities": "all",
    "sigma_day_ahead": 2.5,
    "sigma_per_day": 1.0,
    "min_edge": 0.02,
    "min_price": 0.02,
    "shrink": 0.5,
    "notional_usd": None,
    "max_intents": 2,
    "max_quotes": 4,
    "max_hours": 40,
}
RANGE = re.compile(r"(-?[0-9]+(?:\.[0-9]+)?)°?\s*(?:to|-|–)\s*(-?[0-9]+(?:\.[0-9]+)?)°")
ABOVE = re.compile(r"(-?[0-9]+(?:\.[0-9]+)?)°?\s*or above")
BELOW = re.compile(r"(-?[0-9]+(?:\.[0-9]+)?)°?\s*or below")
MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}


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


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _fee(price):
    return math.ceil(0.07 * price * (1.0 - price) * 100.0) / 100.0


def settlement_day(ticker):
    """KXHIGHNY-26SEP16-B81.5 -> 2026-09-16."""
    parts = str(ticker or "").split("-")
    if len(parts) < 2 or len(parts[1]) < 7:
        return None
    code = parts[1]
    try:
        year, month, day = 2000 + int(code[:2]), MONTHS.get(code[2:5].upper()), int(code[5:7])
    except ValueError:
        return None
    if not month:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def probability(market, mu, sigma):
    """P(settled high lands where the market pays), from its subtitle."""
    text = str(market.get("yes_sub_title") or market.get("title") or "")
    found = RANGE.search(text)
    if found:
        lo, hi = _num(found.group(1)), _num(found.group(2))
        if lo is None or hi is None:
            return None
        return _phi((hi + 0.5 - mu) / sigma) - _phi((lo - 0.5 - mu) / sigma)
    found = ABOVE.search(text)
    if found:
        return 1.0 - _phi((_num(found.group(1)) - 0.5 - mu) / sigma)
    found = BELOW.search(text)
    if found:
        return _phi((_num(found.group(1)) + 0.5 - mu) / sigma)
    return None


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    held = {str(x.get("market_id")) for x in (ctx.get("positions") or [])}
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 10.0)
    series_of = {c["name"]: c["series"] for c in (kit.weather_cities() or []) if c.get("series")}
    candidates = []
    cities = list(series_of) if p["cities"] == "all" else list(p["cities"] or [])
    for city in cities:
        series = series_of.get(city)
        if not series:
            kit.say(f"{city}: no series")
            continue
        try:
            forecast = kit.weather(city) or {}
        except Exception as exc:
            kit.say(f"{city}: forecast failed ({type(exc).__name__})")
            continue
        highs = {}
        for day in forecast.get("days") or []:
            high = _num(day.get("day_high")) or _num(day.get("hourly_max"))
            if high is not None and day.get("date"):
                highs[str(day["date"])[:10]] = high
        if not highs:
            kit.say(f"{city}: no forecast highs")
            continue
        markets = []
        for market in kit.kalshi_series(series):
            ticker = str(market.get("ticker") or "")
            if ticker in held or str(market.get("status") or "open") not in ("open", "active"):
                continue
            close = _when(market.get("close_time"))
            day = settlement_day(ticker)
            if close is None or day is None or day not in highs:
                continue
            hours = (close - now).total_seconds() / 3600.0
            if hours < 1 or hours > float(p["max_hours"]):
                continue
            mu = highs[day]
            days_ahead = max(0.0, (datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc) - now).total_seconds() / 86400.0)
            sigma = float(p["sigma_day_ahead"]) + float(p["sigma_per_day"]) * days_ahead
            prob = probability(market, mu, sigma)
            if prob is None:
                continue
            # Nearest to the forecast first: the buckets around it carry the real edge and the
            # live quote costs a call each.
            found = RANGE.search(str(market.get("yes_sub_title") or ""))
            center = (_num(found.group(1)) + _num(found.group(2))) / 2.0 if found else mu
            markets.append((abs(center - mu), ticker, market, prob, mu, sigma, hours, city))
        markets.sort(key=lambda m: m[0])
        for _, ticker, market, prob, mu, sigma, hours, city in markets[: int(p["max_quotes"])]:
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
            candidates.append((edge, ticker, side, price, prob, shrunk, market_p, mu, sigma, hours, city, str(market.get("yes_sub_title") or "")))
    candidates.sort(key=lambda c: -c[0])
    intents = []
    for edge, ticker, side, price, prob, shrunk, market_p, mu, sigma, hours, city, label in candidates[: int(p["max_intents"])]:
        quantity = max(1, int(notional / price))
        intents.append(
            {
                "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": side},
                "side": "buy",
                "quantity": str(quantity),
                "order_type": "limit",
                "limit_price": f"{price:.2f}",
                "rationale": (
                    f"{city} forecast high {mu:.0f}F (sigma {sigma:.1f}F) against the {label} market settling in {hours:.0f}h: "
                    f"p={prob:.3f}, shrunk to {shrunk:.3f} against the market's {market_p:.2f}; "
                    f"{side.upper()} at {price:.2f} has {edge:.3f} of edge after fees. Holds to settlement."
                ),
                "holding_period_hours": max(1, int(hours) + 1),
            }
        )
    kit.say(f"{len(candidates)} candidate(s) with edge >= {p['min_edge']}, {len(intents)} proposed")
    return {"intents": intents, "notes": f"{len(candidates)} markets with edge >= {p['min_edge']}"}

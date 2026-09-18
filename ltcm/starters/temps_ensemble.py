"""House starter (the arena, Sept 18, 2026): price Kalshi's daily high-temperature markets from
open-meteo's GFS and ECMWF ensembles instead of one point forecast.

A bracket market ("81° to 82°") pays when the settled high rounds into it, so its fair price is
the share of ensemble members whose daily high lands there. Every run: for each Kalshi weather
city, `kit.ensemble` gives up to 82 members' daily highs for the next days; each open market of
the city's series settling within `max_hours` is priced as a blend of that empirical share and a
normal curve around the ensemble mean with its spread widened by `inflate` (ensembles run tight),
shrunk `shrink` of the way toward the market's mid; the cheaper side is bought when its edge after
the taker fee clears `min_edge` (`maker` rests a bid a cent over the best bid instead). Held to
settlement. The floor caps size; the record decides whether the ensemble knows something.

Params: cities ("all" or names), inflate, floor_sigma, weight (empirical share vs normal),
min_edge, min_price, shrink, maker, notional_usd, max_intents, max_quotes, max_hours.
"""

import math
import re
from datetime import datetime, timezone

DEFAULTS = {
    "cities": "all",
    "inflate": 1.3,
    "floor_sigma": 1.5,
    "weight": 0.6,
    "min_edge": 0.02,
    "min_price": 0.03,
    "shrink": 0.4,
    "maker": False,
    "notional_usd": None,
    "max_intents": 3,
    "max_quotes": 6,
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
    return math.ceil(round(0.07 * price * (1.0 - price) * 10000.0, 6)) / 10000.0


def settlement_day(ticker):
    parts = str(ticker or "").split("-")
    if len(parts) < 2 or len(parts[1]) < 7:
        return None
    code = parts[1]
    try:
        year, month, day = 2000 + int(code[:2]), MONTHS.get(code[2:5].upper()), int(code[5:7])
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}" if month else None


def bracket(market):
    """(low, high) of the bracket the market pays on, either end None when open."""
    text = str(market.get("yes_sub_title") or market.get("title") or "")
    found = RANGE.search(text)
    if found:
        return _num(found.group(1)), _num(found.group(2))
    found = ABOVE.search(text)
    if found:
        return _num(found.group(1)), None
    found = BELOW.search(text)
    if found:
        return None, _num(found.group(1))
    return None


def probability(members, mean, sd, low, high, p):
    """The blend: the members' share inside the bracket and a widened normal's mass."""
    n = len(members)
    if not n:
        return None
    hits = sum(1 for m in members if (low is None or round(m) >= low) and (high is None or round(m) <= high))
    empirical = (hits + 0.5) / (n + 1.0)
    sigma = max(float(p["floor_sigma"]), (sd or 0.0) * float(p["inflate"]))
    lo = -1e9 if low is None else low - 0.5
    hi = 1e9 if high is None else high + 0.5
    normal = _phi((hi - mean) / sigma) - _phi((lo - mean) / sigma)
    w = min(1.0, max(0.0, float(p["weight"])))
    return w * empirical + (1.0 - w) * normal


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    held = {str(x.get("market_id")) for x in (ctx.get("positions") or [])}
    working = {str(x.get("market_id")) for x in (ctx.get("open_orders") or [])}
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 10.0)
    series_of = {c["name"]: c["series"] for c in (kit.weather_cities() or []) if c.get("series")}
    cities = list(series_of) if p["cities"] == "all" else list(p["cities"] or [])
    candidates = []
    for city in cities:
        series = series_of.get(city)
        if not series:
            continue
        try:
            ens = kit.ensemble(city, 3) or {}
        except Exception as exc:
            kit.say(f"{city}: ensemble failed ({type(exc).__name__})")
            continue
        days = {str(d.get("date"))[:10]: d for d in (ens.get("days") or []) if d.get("date") and d.get("members")}
        if not days:
            kit.say(f"{city}: no ensemble days")
            continue
        priced = []
        for market in kit.kalshi_series(series) or []:
            ticker = str(market.get("ticker") or "")
            if ticker in held or ticker in working or str(market.get("status") or "open") not in ("open", "active"):
                continue
            close = _when(market.get("close_time"))
            day = settlement_day(ticker)
            if close is None or day is None or day not in days:
                continue
            hours = (close - now).total_seconds() / 3600.0
            if hours < 1 or hours > float(p["max_hours"]):
                continue
            ends = bracket(market)
            if ends is None:
                continue
            row = days[day]
            members = [m for m in (_num(x) for x in row["members"]) if m is not None]
            prob = probability(members, _num(row.get("mean"), 0.0), _num(row.get("sd"), 0.0), ends[0], ends[1], p)
            if prob is None:
                continue
            center = ((ends[0] if ends[0] is not None else ends[1]) + (ends[1] if ends[1] is not None else ends[0])) / 2.0
            priced.append((abs(center - _num(row.get("mean"), center)), ticker, market, prob, row, hours, city))
        priced.sort(key=lambda m: m[0])
        for _, ticker, market, prob, row, hours, city in priced[: int(p["max_quotes"])]:
            live = kit.kalshi_market(ticker) or {}
            yes_ask = _num(live.get("yes_ask")) or _num(market.get("yes_ask"))
            yes_bid = _num(live.get("yes_bid")) if _num(live.get("yes_bid")) is not None else _num(market.get("yes_bid"))
            if yes_ask is None or yes_bid is None or yes_ask <= 0 or yes_ask >= 1:
                continue
            mid = (yes_ask + yes_bid) / 2.0
            shrunk = prob + float(p["shrink"]) * (mid - prob)
            no_ask, no_bid = 1.0 - yes_bid, 1.0 - yes_ask
            if p.get("maker"):
                yes_px, no_px = min(yes_ask - 0.01, yes_bid + 0.01), min(no_ask - 0.01, no_bid + 0.01)
                edge_yes, edge_no = shrunk - yes_px, (1.0 - shrunk) - no_px
            else:
                yes_px, no_px = yes_ask, no_ask
                edge_yes, edge_no = shrunk - yes_ask - _fee(yes_ask), (1.0 - shrunk) - no_ask - _fee(no_ask)
            side, price, edge = ("yes", yes_px, edge_yes) if edge_yes >= edge_no else ("no", no_px, edge_no)
            if edge < float(p["min_edge"]) or price < max(0.02, float(p.get("min_price") or 0)) or price > 0.98:
                continue
            candidates.append((edge, ticker, side, price, prob, shrunk, mid, row, hours, city, str(market.get("yes_sub_title") or "")))
    candidates.sort(key=lambda c: -c[0])
    intents, events = [], set()
    for edge, ticker, side, price, prob, shrunk, mid, row, hours, city, label in candidates:
        event = "-".join(ticker.split("-")[:2])
        if event in events:
            continue
        events.add(event)
        intents.append(
            {
                "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": side},
                "side": "buy",
                "quantity": str(max(1, int(notional / price))),
                "order_type": "limit",
                "limit_price": f"{price:.2f}",
                **({"post_only": True} if p.get("maker") else {}),
                "rationale": (
                    f"{city}: {int(row.get('n') or len(row.get('members') or []))} ensemble members put the high at {_num(row.get('mean'), 0):.1f}F "
                    f"(p10 {_num(row.get('p10'), 0):.0f}, p90 {_num(row.get('p90'), 0):.0f}); the {label} market settling in {hours:.0f}h "
                    f"has p={prob:.3f}, shrunk to {shrunk:.3f} against the market's {mid:.2f}; {side.upper()} at {price:.2f} "
                    f"has {edge:.3f} of edge{' as a maker' if p.get('maker') else ' after fees'}. Holds to settlement."
                ),
                "holding_period_hours": max(1, int(hours) + 1),
            }
        )
        if len(intents) >= int(p["max_intents"]):
            break
    kit.say(f"{len(candidates)} candidate(s) with edge >= {p['min_edge']}, {len(intents)} proposed")
    return {"intents": intents, "notes": f"{len(candidates)} brackets with edge >= {p['min_edge']} from the ensembles"}

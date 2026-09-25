# weather-ensemble: price every daily high and low bracket of up to six stations from the GFS and
# ECMWF ensemble members, and rest post-only bids where the calibrated fair value clears the price.
#
# THE IDEA. A Kalshi high or low market settles on the NWS climate report's whole-degree maximum or
# minimum for one station and one climate day (midnight to midnight local STANDARD time). The House
# records Open-Meteo's 82 ensemble members for that day per station (ctx["feeds"]["weather"]) and
# the NWS forecast (ctx["feeds"]["nws"]). Shift the members by the station's measured bias, widen
# them, smooth each with a normal kernel so no bracket is ever 0 or 1, blend in the NWS forecast,
# and the share of that mixture inside a bracket (or beyond a threshold) is the fair value. This is
# the foundry's first transfer: the weather favourites scaled onto the ensemble's fair value.
#
# THE EVIDENCE. Realized values are Kalshi's own settlements (expiration_value) of Aug 1-Sep 24,
# 2026, 55 days a station. GFS and ECMWF forecasts at one day's lead (Open-Meteo's archive, the
# forecast feed's source) missed them by -4.0 to +3.9 F on average by station (Miami's highs run
# 3.9 F hot, Los Angeles' 3.6 F cool; STATIONS below) with a residual sd of 1.3-3.5 F. A proxy of
# this pricing (deterministic mean, station bias, normal error) against Kalshi's own hourly prices
# on 16 days scored WORSE than the market's mid (Brier 0.161 v 0.134 highs, 0.149 v 0.121 lows),
# takers made nothing on highs and lost on lows, and favourite-side makers earned about 3 cents whether or not the
# model filtered them. So the model is shrunk toward the market (model_weight), entries rest as a
# maker, and a taker needs take_edge. Unproven: the forward record decides.
#
# WHAT IT NEEDS. The daily high and low series of its stations, markets closing within 30 hours
# (entries must pay within 48), the weather and nws feeds for the same stations. Woken every 20
# minutes. Memory is one timestamp.
#
# WHEN IT TRADES. Only before the day's own observations can inform the price: highs until
# cutoff_hour_high (06:00 local standard time on the day), lows until cutoff_hour_low (23:00 the
# evening before), on an ensemble run younger than max_run_age_hours. For each market the fair YES
# is P(value in the bracket or beyond the threshold); either leg priced bid_min-bid_max (never under
# the real book's 30-cent longshot floor) is bid one tick inside the touch, post-only, when fair
# minus price minus the maker fee clears min_edge (min_edge_tail on the open-ended thresholds); at
# the ask only when it clears take_edge after the taker fee and no real book refused a taker lately.
# One market per event (a city-day): a taker first, then the best return per dollar; max_new a wake, sized
# notional_usd within cash, the limits, a quarter of equity per event and event_risk's room.
#
# HOW IT EXITS. It holds to settlement and never sells. A resting bid is cancelled when its edge
# at the current fair falls under half of min_edge (a new model run that flips the side does
# that), when its station-day goes stale, missing or past the cutoff, or when it was outbid and is
# older than requote_minutes (the slot is bid again next wake).

from datetime import datetime, timedelta, timezone
import math
import re

NEEDS = {
    "venue": "kalshi",
    "horizon": "day",
    "style": "model-versus-market",
    "series": ["KXHIGHNY", "KXLOWTNYC", "KXHIGHCHI", "KXLOWTCHI", "KXHIGHMIA", "KXLOWTMIA",
               "KXHIGHAUS", "KXLOWTAUS", "KXHIGHDEN", "KXLOWTDEN", "KXHIGHLAX", "KXLOWTLAX"],
    "max_hours_to_close": 30,
    "wake_minutes": 20,
    "feeds": {"weather": ["KNYC", "KMDW", "KMIA", "KAUS", "KDEN", "KLAX"],
              "nws": ["KNYC", "KMDW", "KMIA", "KAUS", "KDEN", "KLAX"]},
    "parameter_rules": {"bounds": {
        "notional_usd": [2.0, 50.0], "bid_min": [0.30, 0.90], "bid_max": [0.60, 0.97], "min_edge": [0.02, 0.25],
        "min_edge_tail": [0.03, 0.30], "take_edge": [0.08, 0.50], "model_weight": [0.2, 1.0], "bias_high_f": [-3.0, 3.0],
        "bias_low_f": [-3.0, 3.0], "spread_mult": [0.7, 2.0], "kernel_f": [0.5, 3.0], "nws_weight": [0.0, 0.6],
        "max_run_age_hours": [8.0, 36.0], "cutoff_hour_high": [-6, 12], "cutoff_hour_low": [-8, 0], "min_members": [10, 82],
        "max_new": [1, 8], "max_open": [1, 24], "requote_minutes": [30, 600], "improve_ticks": [0, 2]}},
}
PARAMS = {
    "notional_usd": 10.0,       # the favourites seeds' ticket; real money caps it by limits
    "bid_min": 0.30,            # allocator.longshot_floor_real: the real book refuses entries under 30 cents
    "bid_max": 0.95,            # above 95 cents a 5-cent edge cannot exist
    "min_edge": 0.05,           # brackets: twice the 0.023 a 0.3 F bias error (the table's) moves a flank bracket
    "min_edge_tail": 0.08,      # open-ended thresholds: twice the 0.037 the same error moves a tail
    "take_edge": 0.20,          # proxy takers: +3.6c (se 3.4) on highs, -17c (se 4.4) on lows; 0.20 is rare
    "model_weight": 0.5,        # fair = mid + w x (model - mid): the proxy's fitted w was 0, the card's is 1
    "bias_high_f": 0.0,         # on top of STATIONS: the ensemble mean ran 0.2 F warm of the pair (40 station-days)
    "bias_low_f": -1.7,         # the same for lows: the members ran +1.7 F warm of the pair at one day's lead (-0.1 F at two);
                                # lows trade only until 23:00 the evening before, a day's lead, so the day-ahead figure (review, Sept 25)
    "spread_mult": 1.1,         # members' sd 1.4-2.0 F on the day ahead against a 2.1 F station error
    "kernel_f": 1.0,            # each member is N(value, 1 F); the station's error sd is the floor
    "nws_weight": 0.25,         # the NWS point forecast as a quarter of the mixture: unmeasured here
    "max_run_age_hours": 18.0,  # GEFS runs every 6 h and is out 5.7 h later: one run missed is stale
    "cutoff_hour_high": 6,      # hours after the climate day's start: before the morning's heating
    "cutoff_hour_low": -1,      # the evening before: the first reading of the day caps the low (bounded at 0, midnight)
    "min_members": 20,
    "max_new": 4,
    "max_open": 12,             # one event per station-day: six stations, highs and lows
    "requote_minutes": 120,
    "improve_ticks": 1,
}
# station: (UTC offset in standard time, high bias F, high sd F, low bias F, low sd F): the realized
# settlement minus the mean of GFS and ECMWF at one day's lead, Aug 1-Sep 24, 2026, n 54-55 each.
STATIONS = {
    "KNYC": (-5, -1.0, 2.2, 1.2, 2.2), "KMDW": (-6, 0.5, 2.1, 1.6, 1.8), "KMIA": (-5, 3.9, 1.9, 0.7, 1.8),
    "KAUS": (-6, 2.1, 1.5, -2.9, 2.2), "KDEN": (-7, 0.3, 2.1, -2.5, 2.9), "KLAX": (-8, -3.6, 3.1, 2.4, 1.3),
    "KPHL": (-5, 1.7, 1.9, 2.3, 1.9), "KSEA": (-8, 0.8, 2.2, 0.0, 1.4), "KATL": (-5, 0.3, 2.0, 1.2, 1.8),
    "KHOU": (-6, 0.1, 2.3, 0.9, 1.5), "KDFW": (-6, 1.0, 1.9, -0.4, 1.6), "KPHX": (-7, 1.0, 1.8, 2.3, 2.9),
    "KBOS": (-5, 0.3, 2.4, 1.7, 2.0), "KDCA": (-5, -0.8, 2.4, 0.9, 2.1), "KLAS": (-8, 0.4, 2.3, 3.3, 1.9),
    "KSFO": (-8, -1.3, 3.5, 1.5, 1.6), "KMSP": (-6, 0.2, 2.8, 1.1, 1.6), "KOKC": (-6, 1.5, 2.7, -4.0, 2.8),
    "KMSY": (-6, 1.2, 2.3, -1.1, 1.6), "KSAT": (-6, 0.4, 1.7, 1.5, 1.5),
}
CODES = {"NY": "KNYC", "NYC": "KNYC", "CHI": "KMDW", "MIA": "KMIA", "AUS": "KAUS", "DEN": "KDEN", "LAX": "KLAX",
         "PHIL": "KPHL", "SEA": "KSEA", "ATL": "KATL", "HOU": "KHOU", "DAL": "KDFW", "PHX": "KPHX", "BOS": "KBOS",
         "DC": "KDCA", "LV": "KLAS", "SFO": "KSFO", "MIN": "KMSP", "OKC": "KOKC", "NOLA": "KMSY", "SATX": "KSAT"}
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
TICK = 0.01
MAKER_RATE = 0.0175  # a quarter of the taker rate: weather pays no maker fee today; charged anyway
EPS = 1e-9
# The last climate day in STATIONS' sample (settlements Aug 1-Sep 24, 2026). A day on or before it is never priced:
# the weather feed was recorded from Sep 24 08:33Z, so a replay could otherwise trade Sep 24's highs on a table
# that already holds their settlement. Live days are all after it; this keeps every replay out of sample.
FITTED_THROUGH = "2026-09-24"


def num(value, default=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def obj(value):
    """A mapping as given, or {} for anything else (a feed row, a field of one, a ctx field)."""
    return value if isinstance(value, dict) else {}


def seq(value):
    """A list as given, or [] for anything else."""
    return value if isinstance(value, (list, tuple)) else []


def when(text):
    try:
        clean = str(text).strip()
        moment = datetime.fromisoformat(clean[:-1] + "+00:00" if clean[-1:] in "Zz" else clean)
    except (TypeError, ValueError, IndexError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def station_day(ticker):
    """(station, kind, day, strike letter, strike) a weather ticker names, or None."""
    parts = str(ticker or "").upper().split("-")
    found = re.match(r"^KX(HIGH|LOW)T?([A-Z]+)$", parts[0]) if len(parts) == 3 else None
    date = re.match(r"^(\d\d)([A-Z]{3})(\d\d)$", parts[1]) if found else None
    strike = re.match(r"^([TB])(-?\d+(?:\.\d+)?)$", parts[2]) if date else None
    if strike is None or CODES.get(found.group(2)) is None or date.group(2) not in MONTHS:
        return None
    try:
        day = datetime(2000 + int(date.group(1)), MONTHS[date.group(2)], int(date.group(3))).date().isoformat()
    except ValueError:
        return None
    return CODES[found.group(2)], ("high" if found.group(1) == "HIGH" else "low"), day, strike.group(1), float(strike.group(2))


def parse_market(row, siblings):
    """(station, kind, day, low_f, high_f, tail) of a weather market, or None. The YES set is the
    continuous reading in [low_f, high_f): a whole-degree report k covers [k - 0.5, k + 0.5)."""
    found, title = station_day(row.get("market")), str(row.get("title") or "")
    if found is None:
        return None
    station, kind, day, letter, s = found
    if letter == "B":
        pair = re.search(r"(-?\d+)\s*(?:-|to)\s*(-?\d+)\s*°", title)
        low, high = (int(pair.group(1)), int(pair.group(2))) if pair else (math.floor(s), math.ceil(s))
        low, high = (low, high) if low <= s <= high else (math.floor(s), math.ceil(s))
        return station, kind, day, low - 0.5, high + 0.5, False
    above, under = ">" in title or "above" in title.lower(), "<" in title or "below" in title.lower()
    titled = None if above == under else above  # a title naming both ways, or neither, does not say
    centers = [c for c in siblings if c is not None]
    bracketed = None if not centers or min(centers) <= s <= max(centers) else s > max(centers)
    if titled is not None and bracketed is not None and titled != bracketed:
        return None  # the title and the event's brackets disagree: not guessed
    greater = titled if titled is not None else bracketed
    if greater is None:
        return None  # no title says which way, and the brackets do not either
    if greater:
        return station, kind, day, math.floor(s) + 0.5, None, True
    return station, kind, day, None, math.ceil(s) - 0.5, True


def below(z):
    """P(N(0, 1) < z), exact in both tails (erfc keeps a far tail from rounding to 0 or 1)."""
    return 0.5 * math.erfc(-z / 1.4142135623730951)


def mass(points, sd, low, high):
    """The mean over points of P(low <= N(point, sd) < high); None ends are open."""
    total = 0.0
    for point in points:
        a = -1e9 if low is None else (low - point) / sd
        b = 1e9 if high is None else (high - point) / sd
        total += below(-a) - below(-b) if a > 0 else below(b) - below(a)
    return total / len(points)


def model(p, row, nws, day, kind, station, now):
    """(points, kernel sd, NWS point or None, station sd) for a station-day, or why it cannot be priced."""
    if not isinstance(row, dict):
        return "no ensemble row"
    runs = [when(r.get("init")) for r in obj(row.get("runs")).values() if isinstance(r, dict)]
    runs = [r for r in runs if r is not None] or [when(row.get("t"))]
    if runs[0] is None or now is None or (now - max(runs)).total_seconds() / 3600.0 > p["max_run_age_hours"]:
        return "a stale ensemble"
    dist = obj(obj(obj(row.get("dates")).get(day)).get(kind))
    members = [v for v in (num(x) for x in seq(dist.get("members"))) if v is not None]
    if len(members) < p["min_members"]:
        return "too few members"
    offset, hb, hs, lb, ls = STATIONS[station]
    mean = sum(members) / len(members)
    spread = math.sqrt(sum((v - mean) ** 2 for v in members) / max(1, len(members) - 1))
    bias, floor = (hb + p["bias_high_f"], hs) if kind == "high" else (lb + p["bias_low_f"], ls)
    points = [mean + bias + p["spread_mult"] * (v - mean) for v in members]
    kernel = max(p["kernel_f"], math.sqrt(max(0.0, floor * floor - (p["spread_mult"] * spread) ** 2)))
    point = None
    if isinstance(nws, dict) and when(nws.get("issued")) and (now - when(nws["issued"])).total_seconds() < p["max_run_age_hours"] * 3600:
        for period in seq(nws.get("periods")):
            if isinstance(period, dict) and bool(period.get("daytime")) == (kind == "high"):
                if str(period.get("start" if kind == "high" else "end") or "")[:10] == day:
                    point = num(period.get("temperature"))
                    break
        for entry in seq(nws.get("days")):
            if point is None and isinstance(entry, dict) and entry.get("date") == day and (num(entry.get("hours"), 0) or 0) >= 18:
                point = num(entry.get("hourly_max" if kind == "high" else "hourly_min"))
    return points, kernel, point, floor


def decide(ctx):
    p = {k: num(obj(ctx.get("params")).get(k), v) for k, v in PARAMS.items()}
    now = when(ctx.get("now"))
    memory = ctx.get("memory") if isinstance(ctx.get("memory"), dict) else {}
    feeds = obj(ctx.get("feeds"))
    weather, nws = obj(feeds.get("weather")), obj(feeds.get("nws"))
    markets = [m for m in seq(ctx.get("markets")) if isinstance(m, dict) and m.get("market")]
    positions = [x for x in seq(ctx.get("positions")) if isinstance(x, dict) and (num(x.get("quantity"), 0) or 0) > 0]
    orders = [o for o in seq(ctx.get("open_orders")) if isinstance(o, dict) and str(o.get("side") or "").lower() == "buy"]
    taker_rate = num(obj(ctx.get("fees")).get("kalshi_taker_rate"), 0.07)
    event = lambda ticker: "-".join(str(ticker).upper().split("-")[:2])
    centers = {}
    for m in markets:
        if re.search(r"-B-?\d", str(m["market"]).upper()):
            centers.setdefault(event(m["market"]), []).append(num(m.get("strike")))
    fairs, skipped, cache = {}, {}, {}

    def status(key):
        """A station-day's pricing inputs, or why it cannot be priced now; once a wake."""
        if key not in cache:
            station, kind, day = key
            start = datetime.fromisoformat(day + "T00:00:00+00:00") - timedelta(hours=STATIONS[station][0])
            cutoff = start + timedelta(hours=p["cutoff_hour_high" if kind == "high" else "cutoff_hour_low"])
            if day <= FITTED_THROUGH:
                cache[key] = "inside the calibration sample"
            elif now >= cutoff:
                cache[key] = "past the cutoff"
            else:
                cache[key] = model(p, weather.get(station), nws.get(station), day, kind, station, now)
            if isinstance(cache[key], str):
                skipped[key] = cache[key]
        return cache[key]

    for m in markets:
        info = parse_market(m, centers.get(event(m["market"]), []))
        bid, ask = num(m.get("yes_bid")), num(m.get("yes_ask"))
        if info is None or bid is None or ask is None or not 0 < bid < ask < 1 or now is None:
            continue
        station, kind, day, low, high, tail = info
        if isinstance(status((station, kind, day)), str):
            continue
        points, kernel, point, floor = status((station, kind, day))
        fair = mass(points, kernel, low, high)
        if point is not None:
            fair = (1 - p["nws_weight"]) * fair + p["nws_weight"] * mass([point], floor, low, high)
        fair = min(0.995, max(0.005, (bid + ask) / 2 + p["model_weight"] * (fair - (bid + ask) / 2)))
        fairs[m["market"]] = (fair, bid, ask, tail, m)

    def edge(ticker, leg, price, fee_rate):
        fair, bid, ask, tail, m = fairs[ticker]
        return (fair if leg == "yes" else 1 - fair) - price - fee_rate * price * (1 - price)

    cancels, busy, committed, reserved = [], set(), {}, 0.0
    for x in positions:
        busy.add(event(x.get("market")))
        committed[event(x.get("market"))] = committed.get(event(x.get("market")), 0.0) + (num(x.get("quantity"), 0) or 0) * (num(x.get("average_cost"), 1) or 1)
    for o in orders:
        ticker, leg, price = str(o.get("market") or ""), str(o.get("leg") or "yes"), num(o.get("limit_price"), 1.0)
        cost = max(0.0, (num(o.get("quantity"), 0) or 0) - (num(o.get("filled"), 0) or 0)) * price
        busy.add(event(ticker))
        info = station_day(ticker)
        stale = info is not None and now is not None and isinstance(status(info[:3]), str)
        why = None
        if ticker in fairs:
            fair, bid, ask, tail, m = fairs[ticker]
            best = bid if leg == "yes" else 1 - ask
            sent = when(o.get("submitted_at"))
            if edge(ticker, leg, price, MAKER_RATE) < 0.5 * (p["min_edge_tail"] if tail else p["min_edge"]):
                why = "edge"
            elif best > price + EPS and sent is not None and (now - sent).total_seconds() > 60 * p["requote_minutes"]:
                why = "outbid"
        if (why or stale) and o.get("order_id") and len(cancels) < 20:
            cancels.append(str(o["order_id"]))
            continue
        committed[event(ticker)] = committed.get(event(ticker), 0.0) + cost
        reserved += cost

    until = when(memory.get("taker_off_until"))
    for row in seq(ctx.get("recent_order_outcomes")):
        text = str(row.get("reason") or "").lower() if isinstance(row, dict) else ""
        if now and text and row.get("status") == "refused" and ("post-only" in text or "post_only" in text or "real_entry_liquidity" in text):
            until = max(until or now, now + timedelta(hours=24))  # the real book wants a maker: rest for a day
    takers = not (until and now and now < until)

    candidates = []
    for ticker, (fair, bid, ask, tail, m) in fairs.items():
        if event(ticker) in busy or not 0.5 <= (num(m.get("hours_to_close"), 0) or 0) or (num(m.get("hours_to_resolve"), 0) or 0) > 47:
            continue
        for leg, lb, la in (("yes", bid, ask), ("no", round(1 - ask, 4), round(1 - bid, 4))):
            price = round(lb + TICK * int(p["improve_ticks"]), 2)
            price = price if price < la - EPS else lb
            if p["bid_min"] - EPS <= price <= p["bid_max"] + EPS:
                gap = edge(ticker, leg, price, MAKER_RATE)
                if gap >= (p["min_edge_tail"] if tail else p["min_edge"]) - EPS:
                    candidates.append((1, -gap / price, ticker, leg, price, gap, False))
            if takers and p["bid_min"] - EPS <= la <= p["bid_max"] + EPS:
                gap = edge(ticker, leg, la, taker_rate)
                if gap >= p["take_edge"] - EPS:
                    candidates.append((0, -gap / la, ticker, leg, la, gap, True))
    candidates.sort()  # a taker first (its edge is there now), then the best return per dollar

    limits, risk = obj(ctx.get("limits")), obj(obj(ctx.get("event_risk")).get("remaining_by_market_usd"))
    equity = num(ctx.get("equity"), 0.0) or 0.0
    free = max(0.0, (num(ctx.get("cash"), 0.0) or 0.0) - reserved) * 0.98
    slots = min(int(p["max_new"]), int(p["max_open"]) - len(busy), 8)
    intents = []
    for rank, minus_roi, ticker, leg, price, gap, take in candidates:
        if len(intents) >= slots or event(ticker) in busy:
            continue
        room = [p["notional_usd"], free, 0.25 * equity - committed.get(event(ticker), 0.0)]
        room += [v for v in (num(limits.get("max_order_usd")), num(limits.get("max_position_usd")), num(risk.get(ticker))) if v is not None]
        fee_rate = taker_rate if take else MAKER_RATE
        quantity = int(min(room) / (price * (1 + fee_rate * (1 - price))) + EPS)
        fee = math.ceil(100 * fee_rate * quantity * price * (1 - price) - EPS) / 100 if take else 0.0
        if quantity < 1 or quantity * price < 1.0 or (take and quantity * (gap + fee_rate * price * (1 - price)) - fee < quantity * p["take_edge"]):
            continue
        fair = fairs[ticker][0] if leg == "yes" else 1 - fairs[ticker][0]
        free -= quantity * price + fee
        busy.add(event(ticker))
        intent = {"market": ticker, "leg": leg, "side": "buy", "quantity": quantity, "type": "limit", "limit_price": price,
                  "reason": (f"{'Taking' if take else 'Resting a post-only bid for'} {quantity} {leg.upper()} at {price:.2f} on {ticker}: "
                             f"the ensemble's calibrated fair is {fair:.3f} (shrunk {p['model_weight']:.2f} toward the mid), an edge of "
                             f"{gap:.3f} after the {'taker' if take else 'maker'} fee; one market of this city-day, held to settlement.")}
        if not take:
            intent["post_only"] = True
        intents.append(intent)

    best = max((abs(f - (b + a) / 2) for f, b, a, t, m in fairs.values()), default=0.0)
    thought = (f"Priced {len(fairs)} of {len(markets)} markets on {len(cache) - len(skipped)} station-days from the ensemble "
               f"({len(skipped)} skipped: {', '.join(sorted(set(skipped.values()))) or 'none'}); the widest gap from a mid was {best:.3f}. "
               f"Placed {len(intents)} bids, cancelled {len(cancels)}; takers {'on' if takers else 'off after a real-book refusal'}.")
    return {"intents": intents, "cancels": cancels, "thought": thought,
            "memory": {"taker_off_until": until.strftime("%Y-%m-%dT%H:%M:%SZ") if until else None}}

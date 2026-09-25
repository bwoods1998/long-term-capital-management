# options-butterfly-pin: buy a $1-winged long butterfly on SPY, QQQ or IWM expiring TODAY, centred
# on the strike that has traded most in the last two hours, and sell it before the close.
#
# THE IDEA. On an expiry day the strikes where the most contracts change hands are where dealers'
# hedging is heaviest; their hedges (sell into rallies above, buy the dips below) tend to hold the
# price near that strike into the close -- the pin. A long butterfly (one contract below, two sold at
# the body, one above, equal wings) pays most when the underlying finishes at the body and loses at
# most its debit. Buy it only when that strike is within `pin_pct` percent of the price, it carried at
# least `min_share` of the band's volume over the last `pin_minutes`, and its expected value at the
# close under the realized distribution clears the touch paid on all legs and the fee on both fills.
#
# THE EVIDENCE. Published: stock-price clustering at option strikes on expiration days (Ni, Pearson
# and Poteshman, 2005), stronger where open interest and hedging are large. Unmeasured by this firm
# before this replay; the volume here is traded contracts (no point-in-time open interest exists).
#
# WHAT IT NEEDS. Today's expiry in the chain (with each contract's traded volume) and 15-minute bars.
# It remembers each strike's volume at `pin_minutes` before `entry_start` to read the last hours' flow.
#
# WHEN IT TRADES. From `entry_start` to `entry_end` New York (before the House's 14:30 cut on an
# expiry day), one butterfly an underlying a day, `max_open` at once, at the touch.
#
# HOW IT EXITS. At the touch: `profit_target` of the maximum gain made, down `stop_loss` of the
# debit, and `exit_minutes_before_close` before the close (it never meets the House's 15:30 close).
#
# PARAMS (ranges): width 1-5 (the wing); dte_min 0 and dte_max 0 (the expiry day only); entry_delta
# 0.3-0.7 (the body's call |delta|: near the money); profit_target 0.1-0.8 (of the maximum gain);
# stop_loss 0.2-0.9 (of the debit); exit_minutes_before_close 30-60; max_open 1-3;
# entry_start/entry_end 780-865; pin_minutes 60-180; pin_pct 0.1-1 (percent); min_share 0.05-0.5;
# vol_days 3-15; vol_cushion 0.6-1.5; min_edge 0-0.2; risk_usd 10-75; requote_minutes 5-30;
# max_entries_day 1-2.

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
HOLIDAYS = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
            "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
CREDIT_TYPES = ("credit_vertical", "iron_condor", "iron_butterfly")
BOUNDED_TYPES = ("debit_vertical", "long_butterfly", "credit_vertical", "iron_condor", "iron_butterfly")
FEE = 0.05          # dollars a contract a leg a fill (the replay's and the shadow book's assumption)
OPEN, CLOSE = 570, 960   # the regular session, minutes after midnight New York
HOUSE_CUT = 870     # no entry on an expiry day from 14:30 New York (the House's rule)
HOUSE_CLOSE = 930   # the House closes a structure from 15:30 New York on its earliest expiry day

# A unit-variance Student-t (4 degrees of freedom) on a grid: fatter tails than a normal, so a
# credit structure's expected loss is not flattered by a thin-tailed model.
GRID = [i / 10.0 for i in range(-70, 71)]
_RAW = [(1.0 + z * z / 2.0) ** -2.5 for z in GRID]
WEIGHTS = [w / sum(_RAW) for w in _RAW]


def _num(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _when(text):
    """An ISO stamp as an aware datetime in New York, or None."""
    try:
        moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00").replace("z", "+00:00"))
        return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(NY)
    except Exception:
        return None


def _clock(ny):
    return ny.hour * 60 + ny.minute


def _open_day(day):
    return day.weekday() < 5 and day.isoformat() not in HOLIDAYS


def _date(text):
    try:
        return datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _sessions_after(today, expiry):
    """Trading sessions after `today` up to and including `expiry` (each brings one overnight)."""
    count, day = 0, today
    while day < expiry and count < 60:
        day = day + timedelta(days=1)
        if _open_day(day):
            count += 1
    return count


def _occ(text):
    """(underlying, expiry, right, strike) from an OCC code, or None."""
    code = str(text or "").strip().upper()
    if len(code) < 16 or code[-9] not in "CP" or not code[-15:-9].isdigit() or not code[-8:].isdigit() or not code[:-15].isalpha():
        return None
    return (code[:-15], "20" + code[-15:-13] + "-" + code[-13:-11] + "-" + code[-11:-9],
            "call" if code[-9] == "C" else "put", int(code[-8:]) / 1000.0)


def _years(expiry, ny):
    """Calendar years from now to 16:00 New York on `expiry` (as the replay's greeks count time)."""
    day = _date(expiry)
    if day is None:
        return 0.0
    close = datetime(day.year, day.month, day.day, 16, 0, tzinfo=NY)
    return max(0.0, (close - ny).total_seconds() / (365.0 * 86400.0))


def _cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs(spot, strike, years, vol, right):
    if years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return max(0.0, spot - strike if right == "call" else strike - spot)
    sq = vol * math.sqrt(years)
    d1 = (math.log(spot / strike) + 0.5 * vol * vol * years) / sq
    d2 = d1 - sq
    if right == "call":
        return spot * _cdf(d1) - strike * _cdf(d2)
    return strike * _cdf(-d2) - spot * _cdf(-d1)


def _bs_delta(spot, strike, years, vol, right):
    if years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        inside = spot > strike if right == "call" else spot < strike
        return (1.0 if inside else 0.0) * (1.0 if right == "call" else -1.0)
    d1 = (math.log(spot / strike) + 0.5 * vol * vol * years) / (vol * math.sqrt(years))
    return _cdf(d1) if right == "call" else _cdf(d1) - 1.0


def _implied(price, spot, strike, years, right):
    """Black-Scholes implied volatility by bisection; None when no volatility fits the price."""
    if not (price > 0 and spot > 0 and strike > 0 and years > 0):
        return None
    low, high = 0.01, 4.0
    if not _bs(spot, strike, years, low, right) < price < _bs(spot, strike, years, high, right):
        return None
    for _ in range(50):
        mid = 0.5 * (low + high)
        if _bs(spot, strike, years, mid, right) < price:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


# ------------------------------------------------------------------------------ the chain
def _chain(ctx):
    """The chain as {underlying: {expiry: {right: {strike: row}}}} and {occ: row}. A row keeps its
    `bid` (None read as 0: a worthless wing) and `ask`; one with no positive ask is not quotable."""
    tree, by_occ = {}, {}
    for row in ctx.get("chain") or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("occ") or row.get("symbol") or "").upper()
        parsed = _occ(code)
        ask, bid = _num(row.get("ask"), 0.0), _num(row.get("bid"), 0.0)
        if parsed is None or ask <= 0 or bid < 0 or bid > ask:
            continue
        under, expiry, right, strike = parsed
        clean = {"occ": code, "underlying": under, "expiry": expiry, "right": right, "strike": strike, "bid": bid, "ask": ask,
                 "iv": _num(row.get("iv"), None), "delta": _num(row.get("delta"), None), "volume": _num(row.get("volume"), 0.0),
                 "spot": _num(row.get("underlying_price"), None)}
        by_occ[code] = clean
        tree.setdefault(under, {}).setdefault(expiry, {}).setdefault(right, {})[strike] = clean
    return tree, by_occ


def _spot(ctx, tree, symbol):
    """The underlying's price: the chain's `underlying_price`, else the quote's mid, else the last bar."""
    for rights in (tree.get(symbol) or {}).values():
        for rows in rights.values():
            for row in rows.values():
                if row["spot"]:
                    return row["spot"]
    quote = (ctx.get("quotes") or {}).get(symbol) or {}
    bid, ask = _num(quote.get("bid"), 0.0), _num(quote.get("ask"), 0.0)
    if bid > 0 and ask >= bid:
        return (bid + ask) / 2.0
    bars = (ctx.get("bars") or {}).get(symbol) or []
    return _num(bars[-1].get("c"), None) if bars and isinstance(bars[-1], dict) else None


def _expiries(tree, symbol, today, dte_min, dte_max):
    """This underlying's expiries inside [dte_min, dte_max] calendar days, nearest first."""
    found = []
    for expiry in (tree.get(symbol) or {}):
        day = _date(expiry)
        if day is not None and dte_min <= (day - today).days <= dte_max:
            found.append(((day - today).days, expiry))
    return [expiry for _, expiry in sorted(found)]


def _atm_iv(tree, symbol, expiry, spot, ny):
    """The at-the-money implied volatility of one expiry: the call and put nearest the money, their
    `iv` where the feed gives one, else solved from the mid."""
    values = []
    for right in ("call", "put"):
        rows = (tree.get(symbol) or {}).get(expiry, {}).get(right) or {}
        if not rows or not spot:
            continue
        row = rows[min(rows, key=lambda k: abs(k - spot))]
        vol = row["iv"]
        if not vol or vol <= 0:
            vol = _implied((row["bid"] + row["ask"]) / 2.0, spot, row["strike"], _years(expiry, ny), right)
        if vol and 0.02 < vol < 3.0:
            values.append(vol)
    return sum(values) / len(values) if values else None


def _delta(row, spot, ny, fallback_iv):
    if row["delta"] is not None:
        return row["delta"]
    vol = row["iv"] or fallback_iv
    if not vol or not spot:
        return None
    return _bs_delta(spot, row["strike"], _years(row["expiry"], ny), vol, row["right"])


# ------------------------------------------------------------------------------ realized volatility
def _profile(ctx, symbol, days):
    """What the underlying has really done, from its regular-session bars (close-stamped): the
    variance a session minute (from bar-to-bar log returns inside a session), the variance of an
    overnight gap (a session's last close to the next session's first open), the daily closes, and
    today's open, high, low and last. None with fewer than three sessions."""
    sessions = {}
    for bar in (ctx.get("bars") or {}).get(symbol) or []:
        if not isinstance(bar, dict):
            continue
        ny = _when(bar.get("t"))
        close = _num(bar.get("c"), 0.0)
        if ny is None or close <= 0 or not OPEN < _clock(ny) <= CLOSE:
            continue
        sessions.setdefault(ny.date(), []).append((ny, _num(bar.get("o"), close) or close, _num(bar.get("h"), close) or close,
                                                  _num(bar.get("l"), close) or close, close))
    ordered = sorted(sessions)[-(int(days) + 1):]
    if len(ordered) < 3:
        return None
    intraday, minutes, gaps, closes = 0.0, 0.0, [], []
    previous = None
    for day in ordered:
        rows = sorted(sessions[day])
        for (t0, _, _, _, c0), (t1, _, _, _, c1) in zip(rows, rows[1:]):
            span = (t1 - t0).total_seconds() / 60.0
            if 0 < span <= 60:
                intraday += math.log(c1 / c0) ** 2
                minutes += span
        if previous is not None and rows[0][1] > 0:
            gaps.append(math.log(rows[0][1] / previous) ** 2)
        previous = rows[-1][4]
        closes.append(rows[-1][4])
    if minutes <= 0:
        return None
    today = sorted(sessions[ordered[-1]])
    return {"per_minute": intraday / minutes, "gap": (sum(gaps) / len(gaps)) if gaps else 0.0, "closes": closes,
            "day": ordered[-1], "open": today[0][1], "high": max(r[2] for r in today), "low": min(r[3] for r in today),
            "last": today[-1][4], "bars_today": len(today), "prior_close": closes[-2] if len(closes) >= 2 else None,
            "today_rows": today}


def _move_sd(profile, ny, expiry, until=CLOSE):
    """The standard deviation of the log move from now to `until` (minutes, New York) on `expiry`,
    at the realized rates: session minutes at the per-minute variance plus one gap a night."""
    day = _date(expiry)
    if profile is None or day is None:
        return None
    today = ny.date()
    if day < today:
        return None
    now = min(max(_clock(ny), OPEN), CLOSE)
    if day == today:
        minutes, nights = max(0, until - now), 0
    else:
        nights = _sessions_after(today, day)
        minutes = (CLOSE - now) + (nights - 1) * (CLOSE - OPEN) + max(0, until - OPEN)
    variance = profile["per_minute"] * minutes + profile["gap"] * nights
    return math.sqrt(variance) if variance > 0 else None


def _implied_sd(iv, expiry, ny):
    return iv * math.sqrt(_years(expiry, ny)) if iv else None


# ------------------------------------------------------------------------------ structures
def _legs_of(rows):
    """[(row, sign, ratio)] as an intent's legs."""
    return [{"occ": row["occ"], "role": "long" if sign > 0 else "short", **({"ratio": ratio} if ratio != 1 else {})}
            for row, sign, ratio in rows]


def _collateral(kind, rows):
    if kind == "credit_vertical":
        return abs(rows[0][0]["strike"] - rows[1][0]["strike"])
    if kind in ("iron_condor", "iron_butterfly"):
        puts = [r["strike"] for r, _, _ in rows if r["right"] == "put"]
        calls = [r["strike"] for r, _, _ in rows if r["right"] == "call"]
        return max(max(puts) - min(puts), max(calls) - min(calls))
    return 0.0


def _max_value(kind, rows):
    if kind == "debit_vertical":
        return abs(rows[0][0]["strike"] - rows[1][0]["strike"])
    if kind == "long_butterfly":
        strikes = sorted(r["strike"] for r, _, _ in rows)
        return strikes[1] - strikes[0]
    if kind in CREDIT_TYPES:
        return _collateral(kind, rows)
    return None


def _price(kind, rows):
    """The structure at the touches. `open` is the natural price to open (a debit to pay, or a credit
    to take), `close` the natural price to close (what a debit structure's sale gets, or what buying a
    credit one back costs); `held_open`/`held_close` are the same as the held price S = net + K."""
    long_ask = sum(ratio * r["ask"] for r, sign, ratio in rows if sign > 0)
    long_bid = sum(ratio * r["bid"] for r, sign, ratio in rows if sign > 0)
    short_ask = sum(ratio * r["ask"] for r, sign, ratio in rows if sign < 0)
    short_bid = sum(ratio * r["bid"] for r, sign, ratio in rows if sign < 0)
    mid = sum(sign * ratio * (r["bid"] + r["ask"]) / 2.0 for r, sign, ratio in rows)
    k = _collateral(kind, rows)
    if kind in CREDIT_TYPES:
        credit, buy_back = short_bid - long_ask, short_ask - long_bid
        return {"kind": kind, "credit": True, "k": k, "open": credit, "close": buy_back, "held_open": k - credit,
                "held_close": max(0.0, k - buy_back), "mid": -mid, "max_value": k, "contracts": sum(x for _, _, x in rows)}
    debit, value = long_ask - short_bid, max(0.0, long_bid - short_ask)
    return {"kind": kind, "credit": False, "k": 0.0, "open": debit, "close": value, "held_open": debit, "held_close": value,
            "mid": mid, "max_value": _max_value(kind, rows), "contracts": sum(x for _, _, x in rows)}


def _payoff(rows, spot):
    """The legs' net value a share at their (common) expiry with the underlying at `spot`."""
    value = 0.0
    for row, sign, ratio in rows:
        inside = spot - row["strike"] if row["right"] == "call" else row["strike"] - spot
        value += sign * ratio * max(0.0, inside)
    return value


def _expected(rows, spot, sd):
    """The expected net value at expiry under the realized distribution (a unit-variance Student-t
    of the log move, scaled to `sd`, with no drift)."""
    if not sd or sd <= 0 or not spot:
        return None
    return sum(w * _payoff(rows, spot * math.exp(sd * z - 0.5 * sd * sd)) for z, w in zip(GRID, WEIGHTS))


def _edge(price, rows, spot, sd):
    """What holding the structure to expiry is expected to make a share after paying the touch to
    open and the fee on every leg of both fills (it is closed early at the touch or expires)."""
    value = _expected(rows, spot, sd)
    if value is None:
        return None
    net_paid = -price["open"] if price["credit"] else price["open"]
    return value - net_paid - 2.0 * FEE * price["contracts"] / 100.0


def _cents_up(value):
    return math.ceil(round(value * 100.0, 6)) / 100.0


def _cents_down(value):
    return math.floor(round(value * 100.0, 6)) / 100.0


def _open_limit(price):
    """The natural limit that opens at the touch: a debit rounded up to a cent (the most to pay), a
    credit rounded down (the least to take). None when that is no order a book admits."""
    if price["credit"]:
        limit = _cents_down(price["open"])
        return limit if 0.01 <= limit < price["k"] - 0.005 else None
    limit = _cents_up(price["open"])
    if limit < 0.01 or (price["max_value"] is not None and limit >= price["max_value"] - 0.005):
        return None
    return limit


def _close_limit(price):
    """The natural limit that closes at the touch: the least a debit structure's sale takes (rounded
    down, at least a cent), or the most a credit structure's buy-back pays (rounded up, under K)."""
    if price["credit"]:
        return max(0.01, min(_cents_up(price["close"]), round(price["k"] - 0.01, 2)))
    return max(0.01, _cents_down(price["close"]))


def _fits(price, quantity, ctx, risk_usd):
    """Whether `quantity` structures fit the caps, the agent's own risk budget and free cash, all read
    as maximum loss (the held price x 100) plus the fee."""
    limits = ctx.get("limits") or {}
    cost = price["held_open"] * 100.0 * quantity
    caps = [risk_usd, _num(limits.get("max_order_usd"), 0.0), _num(limits.get("max_position_usd"), 0.0)]
    return 0 < cost <= min(caps) + 1e-9 and cost + FEE * price["contracts"] * quantity <= _num(ctx.get("cash"), 0.0) * 0.98


def _size(price, ctx, risk_usd, most=4):
    quantity = 0
    while quantity < most and _fits(price, quantity + 1, ctx, risk_usd):
        quantity += 1
    return quantity


def _intent(kind, rows, action, quantity, limit, reason):
    return {"structure": kind, "action": action, "quantity": int(quantity), "type": "limit", "limit_price": round(limit, 2),
            "legs": _legs_of(rows), "reason": reason[:480]}


# ------------------------------------------------------------------------------ what is held
def _structure_legs(item):
    """[(occ, sign, ratio)] of a held structure or a working structure order, from its `legs` or,
    failing that, from the code its `market_id`/`symbol`/`occ` carries (`type|+1OCC|-1OCC...`)."""
    legs = []
    for leg in item.get("legs") or []:
        if isinstance(leg, dict) and (leg.get("occ") or leg.get("symbol")):
            sign = 1 if str(leg.get("role") or leg.get("side") or "long").lower() in ("long", "buy") else -1
            legs.append((str(leg.get("occ") or leg.get("symbol")).upper(), sign, int(_num(leg.get("ratio"), 1) or 1)))
    if legs:
        return legs
    for field in ("market_id", "code", "symbol", "occ"):
        text = str(item.get(field) or "")
        if "|" in text:
            for part in text.split("|")[1:]:
                if len(part) > 2 and part[0] in "+-" and part[1].isdigit():
                    legs.append((part[2:].upper(), 1 if part[0] == "+" else -1, int(part[1])))
            if legs:
                return legs
    return []


def _structure_kind(item):
    kind = item.get("structure") or item.get("spread")
    if kind:
        return str(kind)
    for field in ("market_id", "code", "symbol", "occ"):
        text = str(item.get(field) or "")
        if "|" in text:
            return text.split("|")[0]
    return None


def _key(legs):
    return "|".join(sorted(f"{sign}{ratio}{occ}" for occ, sign, ratio in legs))


def _held(ctx, by_occ):
    """The structures this agent holds, each with its legs, the held price paid and the natural
    touch to close it now (from the chain's legs where all are shown, else the House's mark)."""
    out = []
    for position in ctx.get("positions") or []:
        if not isinstance(position, dict) or _num(position.get("quantity"), 0.0) <= 0:
            continue
        kind, legs = _structure_kind(position), _structure_legs(position)
        if not kind or not legs:
            continue
        parsed = [_occ(occ) for occ, _, _ in legs]
        if any(p is None for p in parsed):
            continue
        rows = [({"occ": occ, "underlying": p[0], "expiry": p[1], "right": p[2], "strike": p[3], "bid": 0.0, "ask": 0.0},
                 sign, ratio) for (occ, sign, ratio), p in zip(legs, parsed)]
        k = _collateral(kind, rows)
        paid = _num(position.get("average_cost"), 0.0)
        live = [by_occ.get(occ) for occ, _, _ in legs]
        if all(live):
            price = _price(kind, [(row, sign, ratio) for row, (_, sign, ratio) in zip(live, legs)])
            close_held, close_natural, source = price["held_close"], price["close"], "the legs' touches"
        else:
            close_held = _num(position.get("mark"), 0.0)
            close_natural = (k - close_held) if kind in CREDIT_TYPES else close_held
            price, source = {"kind": kind, "credit": kind in CREDIT_TYPES, "k": k, "close": close_natural,
                             "held_close": close_held, "max_value": _max_value(kind, rows)}, "the House's mark"
        natural_open = _num(position.get("natural_open"), None)
        if natural_open is None:
            natural_open = (k - paid) if kind in CREDIT_TYPES else paid
        out.append({"kind": kind, "legs": legs, "rows": rows, "key": _key(legs), "quantity": _num(position.get("quantity"), 0.0),
                    "paid": paid, "natural_open": natural_open, "k": k, "price": price, "close_held": close_held,
                    "close_natural": close_natural, "source": source, "underlying": parsed[0][0],
                    "expiry": min(p[1] for p in parsed), "opened_at": position.get("opened_at")})
    return out


def _working(ctx):
    """Working structure orders: {key: (is_close, order_id, submitted_at)}, and the underlyings with a
    working opening order."""
    keys, unders = {}, set()
    for order in ctx.get("open_orders") or []:
        if not isinstance(order, dict):
            continue
        legs = _structure_legs(order)
        if not legs:
            continue
        closing = str(order.get("action") or "").lower() == "close" or str(order.get("side") or "").lower() == "sell"
        keys[_key(legs)] = (closing, order.get("order_id"), order.get("submitted_at"))
        parsed = _occ(legs[0][0])
        if parsed and not closing:
            unders.add(parsed[0])
    return keys, unders


def _stale(ctx, ny, minutes):
    """Order ids of this agent's working orders older than `minutes` (re-priced at the next wake)."""
    out = []
    for order in ctx.get("open_orders") or []:
        sent = _when(order.get("submitted_at")) if isinstance(order, dict) else None
        if sent is not None and order.get("order_id") and (ny - sent).total_seconds() >= minutes * 60.0 - 1.0:
            out.append(str(order["order_id"]))
    return out


def _exit_reason(item, p, ny):
    """Why a held structure should be closed now, or None: its profit target, its stop, or its time
    exit (the minutes before the close of its earliest expiry, the agent's own flat time, or its
    holding limit in sessions)."""
    clock, today = _clock(ny), ny.date()
    expiry = _date(item["expiry"])
    exit_at = CLOSE - int(p["exit_minutes_before_close"])
    paid, now = item["paid"], item["close_held"]
    pnl = now - paid
    if item["kind"] in CREDIT_TYPES:
        credit = max(item["natural_open"], 0.01)
        if pnl >= p["profit_target"] * credit:
            return f"the profit target: {pnl:+.2f} a share is {pnl / credit:.0%} of the {credit:.2f} credit (target {p['profit_target']:.0%})"
        if item["close_natural"] >= p["stop_loss"] * credit:
            return f"the stop: buying it back costs {item['close_natural']:.2f}, {p['stop_loss']:.1f}x the {credit:.2f} credit"
    else:
        top = item["price"].get("max_value")
        gain = (top - paid) if top is not None else paid
        if gain > 0 and pnl >= p["profit_target"] * gain:
            what = "maximum gain" if top is not None else "debit"
            return f"the profit target: {pnl:+.2f} a share is {pnl / gain:.0%} of the {gain:.2f} {what} (target {p['profit_target']:.0%})"
        if paid > 0 and pnl <= -p["stop_loss"] * paid:
            return f"the stop: worth {now:.2f} against {paid:.2f} paid, down {-pnl / paid:.0%} (stop {p['stop_loss']:.0%})"
    if expiry is not None and expiry <= today and clock >= min(exit_at, HOUSE_CLOSE - 5):
        return f"the time exit: {CLOSE - clock} minutes before the close of its expiry day"
    flat = int(p.get("flat_at", 0) or 0)
    if flat and clock >= flat:
        return f"the time exit: {flat // 60:02d}:{flat % 60:02d} New York, flat every day"
    opened = _when(item.get("opened_at"))
    hold = int(p.get("max_hold_days", 0) or 0)
    if hold and opened is not None and _sessions_after(opened.date(), today) >= hold and clock >= exit_at:
        return f"the time exit: held {hold} session(s)"
    return None


def _manage(ctx, p, ny, by_occ, notes):
    """Cancel stale orders; close every held structure whose exit has come, at the touch."""
    intents, cancels = [], _stale(ctx, ny, p["requote_minutes"])
    working, _ = _working(ctx)
    held = _held(ctx, by_occ)
    for item in held:
        why = _exit_reason(item, p, ny)
        label = f"{item['kind']} {item['underlying']} {item['expiry']}"
        if why is None:
            notes.append(f"{label}: holding, {item['close_held'] - item['paid']:+.2f} a share at {item['source']}")
            continue
        order = working.get(item["key"])
        if order is not None and order[0] and str(order[1]) not in cancels:
            notes.append(f"{label}: closing, an order already works")
            continue
        limit = _close_limit(item["price"])
        intents.append({"structure": item["kind"], "action": "close", "quantity": int(item["quantity"]), "type": "limit",
                        "limit_price": limit, "legs": [{"occ": occ, "role": "long" if sign > 0 else "short", **({"ratio": ratio} if ratio != 1 else {})}
                                                      for occ, sign, ratio in item["legs"]],
                        "reason": f"Closing the {label} at the touch ({'pay at most' if item['kind'] in CREDIT_TYPES else 'take at least'} "
                                  f"{limit:.2f} a share, from {item['source']}): {why}."[:480]})
        notes.append(f"{label}: closing, {why}")
    return intents, cancels, held


def _params(ctx, defaults):
    p = dict(defaults)
    for key, value in (ctx.get("params") or {}).items():
        if key in defaults:
            p[key] = value if isinstance(defaults[key], str) else _num(value, defaults[key])
    return p


def _day_memory(ctx, ny):
    memory = ctx.get("memory") if isinstance(ctx.get("memory"), dict) else {}
    today = ny.date().isoformat()
    if memory.get("day") != today:
        memory = {"day": today, "entries": {}}
    memory.setdefault("entries", {})
    return memory

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "options-butterfly-pin",
    "asset_class": "option",
    "structures": True,
    "symbols": ["SPY", "QQQ", "IWM"],
    "bars": {"timeframe": "15Min", "limit": 500},
    "max_days_to_expiry": 2,
    "wake_minutes": 5,
    "parameter_rules": {
        "bounds": {"width": [1, 5], "dte_min": [0, 0], "dte_max": [0, 0], "entry_delta": [0.3, 0.7], "profit_target": [0.1, 0.8],
                   "stop_loss": [0.2, 0.9], "exit_minutes_before_close": [30, 60], "max_open": [1, 3], "entry_start": [780, 865],
                   "entry_end": [780, 865], "pin_minutes": [60, 180], "pin_pct": [0.1, 1.0], "min_share": [0.05, 0.5], "vol_days": [3, 15],
                   "vol_cushion": [0.6, 1.5], "min_edge": [0.0, 0.2], "risk_usd": [10, 75], "requote_minutes": [5, 30],
                   "max_entries_day": [1, 2]},
        "ordered": [["dte_min", "dte_max"]],
    },
}
PARAMS = {"structure": "long_butterfly", "width": 1.0, "dte_min": 0, "dte_max": 0, "entry_delta": 0.5, "profit_target": 0.35,
          "stop_loss": 0.5, "exit_minutes_before_close": 35, "max_open": 2, "entry_start": 825, "entry_end": 860,
          "pin_minutes": 120, "pin_pct": 0.35, "min_share": 0.12, "vol_days": 5, "vol_cushion": 1.0, "min_edge": 0.0,
          "risk_usd": 60.0, "requote_minutes": 10, "max_entries_day": 1}


def _volumes(tree, symbol, expiry, spot, pct):
    """Each strike's traded volume today (calls and puts together) within `pct` percent of the price."""
    out = {}
    for right in ("call", "put"):
        for strike, row in ((tree.get(symbol) or {}).get(expiry, {}).get(right) or {}).items():
            if abs(strike / spot - 1.0) * 100.0 <= pct:
                out[strike] = out.get(strike, 0.0) + row["volume"]
    return out


def _entry(ctx, p, ny, tree, symbol, notes, memory):
    spot = _spot(ctx, tree, symbol)
    profile = _profile(ctx, symbol, p["vol_days"])
    if not spot or profile is None:
        notes.append(f"{symbol}: no price or too few session bars")
        return None
    expiry = ny.date().isoformat()
    if expiry not in (tree.get(symbol) or {}):
        notes.append(f"{symbol}: no expiry today")
        return None
    now = _volumes(tree, symbol, expiry, spot, max(1.0, 2.0 * p["pin_pct"]))
    before = {float(k): v for k, v in ((memory.get("snap") or {}).get(symbol) or {}).items()}
    flow = {s: max(0.0, v - before.get(s, 0.0)) for s, v in now.items()}
    band = {s: v for s, v in flow.items() if abs(s / spot - 1.0) * 100.0 <= p["pin_pct"]}
    total = sum(flow.values())
    if not band or total <= 0:
        notes.append(f"{symbol}: no traded strikes within {p['pin_pct']:.2f}% of {spot:.2f}")
        return None
    body = max(band, key=lambda s: (band[s], -abs(s - spot)))
    share = band[body] / total
    if share < p["min_share"]:
        notes.append(f"{symbol}: the busiest strike near the price, {body:g}, took {share:.0%} of the flow (a pin needs {p['min_share']:.0%})")
        return None
    call_body = ((tree.get(symbol) or {}).get(expiry, {}).get("call") or {}).get(body)
    iv = _atm_iv(tree, symbol, expiry, spot, ny)
    delta = _delta(call_body, spot, ny, iv) if call_body else None
    if delta is not None and abs(delta - p["entry_delta"]) > 0.25:
        notes.append(f"{symbol}: the {body:g} pin is too far from the money (call delta {delta:.2f}, wanted {p['entry_delta']:.2f} +- 0.25)")
        return None
    real = _move_sd(profile, ny, expiry)
    best = None
    for right in ("call", "put"):
        rows_by = (tree.get(symbol) or {}).get(expiry, {}).get(right) or {}
        low, mid, high = rows_by.get(round(body - p["width"], 3)), rows_by.get(body), rows_by.get(round(body + p["width"], 3))
        if low is None or mid is None or high is None or mid["bid"] <= 0:
            continue
        rows = [(low, 1, 1), (mid, -1, 2), (high, 1, 1)]
        price = _price("long_butterfly", rows)
        edge = _edge(price, rows, spot, real * p["vol_cushion"]) if real else None
        if price["open"] <= 0 or edge is None or edge < p["min_edge"] or _open_limit(price) is None or not _fits(price, 1, ctx, p["risk_usd"]):
            continue
        if best is None or price["open"] < best[0]["open"]:
            best = (price, rows, edge, right)
    if best is None:
        notes.append(f"{symbol}: the {body:g} pin ({share:.0%} of the flow), but no {p['width']:g}-wing butterfly clears the touch and fits")
        return None
    price, rows, edge, right = best
    quantity = _size(price, ctx, p["risk_usd"])
    limit = _open_limit(price)
    reason = (f"Buying the {symbol} {expiry} {body - p['width']:g}/{body:g}/{body + p['width']:g} {right} butterfly for {limit:.2f} (at the "
              f"touches): {body:g} took {share:.0%} of the traded volume within {max(1.0, 2.0 * p['pin_pct']):.1f}% of the price since "
              f"the snapshot, and the price {spot:.2f} is {abs(spot / body - 1):.2%} from it; expected {edge:+.3f} a share at the close "
              f"after costs; at most ${price['held_open'] * 100 * quantity:.0f} can be lost. Out at {p['profit_target']:.0%} of the "
              f"maximum gain, -{p['stop_loss']:.0%}, or {int(p['exit_minutes_before_close'])} minutes before the close.")
    notes.append(f"{symbol}: buying the {body:g} {right} butterfly for {limit:.2f}, {share:.0%} of the flow, edge {edge:+.3f}")
    return _intent("long_butterfly", rows, "open", quantity, limit, reason)


def decide(ctx):
    p = _params(ctx, PARAMS)
    ny = _when(ctx.get("now"))
    if ny is None:
        return {"intents": [], "cancels": [], "thought": "Pin butterfly: no clock.", "memory": {}}
    tree, by_occ = _chain(ctx)
    notes = []
    intents, cancels, held = _manage(ctx, p, ny, by_occ, notes)
    memory = _day_memory(ctx, ny)
    clock = _clock(ny)
    snap_at = int(p["entry_start"]) - int(p["pin_minutes"])
    if _open_day(ny.date()) and snap_at <= clock < int(p["entry_start"]) and not memory.get("snap"):
        snap = {}
        for symbol in NEEDS["symbols"]:
            spot = _spot(ctx, tree, symbol)
            if spot and ny.date().isoformat() in (tree.get(symbol) or {}):
                snap[symbol] = {f"{k:g}": v for k, v in _volumes(tree, symbol, ny.date().isoformat(), spot, max(1.0, 2.0 * p["pin_pct"])).items()}
        memory["snap"] = snap
        memory["snap_at"] = ctx.get("now")
        notes.append(f"volumes noted at {ny.strftime('%H:%M')} for {', '.join(sorted(snap)) or 'no underlying'}")
    end = min(int(p["entry_end"]), HOUSE_CUT - 5)
    if not _open_day(ny.date()) or not p["entry_start"] <= clock < end:
        return {"intents": intents[:8], "cancels": cancels[:20], "memory": memory,
                "thought": ("Pin butterfly. No entries now. " + "; ".join(notes))[:1500]}
    working, busy = _working(ctx)
    busy = busy | {item["underlying"] for item in held}
    slots = int(p["max_open"]) - len(held) - sum(1 for closing, _, _ in working.values() if not closing)
    for symbol in NEEDS["symbols"]:
        if slots <= 0:
            break
        if symbol in busy or memory["entries"].get(symbol, 0) >= p["max_entries_day"]:
            continue
        intent = _entry(ctx, p, ny, tree, symbol, notes, memory)
        if intent is not None:
            intents.append(intent)
            memory["entries"][symbol] = memory["entries"].get(symbol, 0) + 1
            slots -= 1
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": ("Pin butterfly. " + "; ".join(notes) + ".")[:1500], "memory": memory}

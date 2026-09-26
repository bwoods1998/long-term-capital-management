# putspread-dip (a Deploy G founder's mechanism, re-expressed for the Gym's program API; not fitted).
#
# THE IDEA. Index puts carry the richest implied vol on the chain, richest right after a sell-off; in
# an uptrend an intraday dip is more often bought than extended. So after a dip in an uptrend, sell a
# put credit vertical (short put near `entry_delta`, long put `width` below) and buy it back soon.
#
# SIGNAL. The prior session's close is above the mean of the last `trend_days` closes, and the price
# now is at least `dip_pct` percent under the higher of today's high and the prior close.
# ENTRY. From `entry_start` to `entry_end`, one spread a day, `max_open` at once, `risk_usd` of maximum
# loss, at the natural price. EXIT. `profit_target` of the credit; `stop_loss` times the credit to buy
# back; `exit_minutes_before_close` before its expiry day's close; or after `max_hold_days` sessions.
import numpy as np

NEEDS = {"roots": ["SPY"], "dte": [0, 4], "band": 0.05, "cadence": 10, "history": 12}
PARAMS = {"width": 1.0, "dte_min": 1, "dte_max": 4, "entry_delta": 0.3, "profit_target": 0.5, "stop_loss": 2.0,
          "exit_minutes_before_close": 30, "max_open": 2, "entry_start": 630, "entry_end": 900, "trend_days": 10,
          "dip_pct": 0.4, "risk_usd": 150.0, "max_hold_days": 1}

STATE = {"last_minute": 10 ** 6, "entered_today": False}


def signal(under, p):
    closes = np.asarray(under.closes)
    days = int(p["trend_days"])
    if closes.size < days or under.prices.size == 0:
        return False, "not enough history"
    mean = float(np.mean(closes[-days:]))
    prior = float(closes[-1])
    if prior <= mean:
        return False, "no uptrend"
    top = max(float(under.high), prior)
    drop = (top - float(under.price)) / top * 100.0
    return drop >= p["dip_pct"], f"{drop:.2f}% under {top:.2f} in an uptrend"


def decide(ctx):
    p = ctx.params
    if ctx.minute < STATE["last_minute"]:
        STATE["entered_today"] = False
    STATE["last_minute"] = ctx.minute
    intents = []
    for pos in ctx.positions:
        if pos["natural"] is None or pos["entry"] >= 0:
            continue
        credit, buy_back = -pos["entry"], -pos["natural"]
        expiring = min(leg["dte"] for leg in pos["legs"]) == 0
        late = ctx.minutes_to_close <= p["exit_minutes_before_close"]
        why = None
        if buy_back <= (1.0 - p["profit_target"]) * credit:
            why = "target"
        elif buy_back >= p["stop_loss"] * credit:
            why = "stop"
        elif late and (expiring or pos["held_days"] >= p["max_hold_days"]):
            why = "time"
        if why and not any(o["position"] == pos["id"] for o in ctx.orders):
            intents.append({"close": pos["id"], "limit": "natural", "note": why})
    chain = ctx.chain
    if chain is None or chain.n == 0 or STATE["entered_today"] or len(ctx.positions) >= p["max_open"]:
        return intents
    if not (p["entry_start"] <= ctx.minute < p["entry_end"]):
        return intents
    ok, why = signal(ctx.under, p)
    if not ok:
        return intents
    listed = [int(d) for d in chain.expiries if p["dte_min"] <= d <= p["dte_max"]]
    if not listed:
        return intents
    intents.append({
        "open": "credit_vertical", "root": ctx.root,
        "legs": [{"side": "short", "right": "P", "dte": listed[0], "delta": p["entry_delta"]},
                 {"side": "long", "right": "P", "rel": 0, "offset": -p["width"]}],
        "max_loss": p["risk_usd"], "limit": "natural", "tif": 5, "tag": "dip", "note": why})
    STATE["entered_today"] = True
    return intents

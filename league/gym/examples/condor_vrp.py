# condor-vrp (a Deploy G founder's mechanism, re-expressed for the Gym's program API; not fitted).
#
# THE IDEA. Short-dated index options are priced above the volatility that follows on average: sellers
# are paid to insure. An iron condor (an out-of-the-money put credit vertical plus a call credit
# vertical, one expiry, `width` wings) sells that premium with the loss capped at the wing less the
# credit. Sell it only when the at-the-money implied vol is at least `vrp_min` times the realized vol
# of the last `vol_days` sessions.
#
# ENTRY. From `entry_start` to `entry_end` (minutes since midnight ET), at most `max_entries_day`
# condors a day and `max_open` at once, short strikes near `entry_delta`, sized to `risk_usd` of
# maximum loss, at the natural price (or `limit_ticks` ticks from the mid toward it).
# EXIT. `profit_target` of the credit made; buying back costs `stop_loss` times the credit; or
# `exit_minutes_before_close` before the close of the expiry day. Nothing is held into an expiry.
import math

import numpy as np

NEEDS = {"roots": ["SPY"], "dte": [0, 2], "band": 0.04, "cadence": 5, "history": 10}
PARAMS = {"width": 1.0, "dte_min": 0, "dte_max": 2, "entry_delta": 0.15, "profit_target": 0.5, "stop_loss": 2.0,
          "exit_minutes_before_close": 30, "max_open": 2, "entry_start": 600, "entry_end": 840, "vrp_min": 1.1,
          "vol_days": 5, "risk_usd": 150.0, "max_entries_day": 2, "limit_ticks": -1}

STATE = {"last_minute": 10 ** 6, "entries": 0}


def realized_vol(under, days):
    closes = np.asarray(under.closes)[-(int(days) + 1):]
    if closes.size >= 3:
        return float(np.std(np.diff(np.log(closes)), ddof=1) * math.sqrt(252.0))
    prices = np.asarray(under.prices)
    if prices.size >= 30:
        return float(np.std(np.diff(np.log(prices)), ddof=1) * math.sqrt(252.0 * 390.0))
    return float("nan")


def atm_iv(chain, dte):
    pick = np.flatnonzero(chain.dte == dte)
    if pick.size == 0:
        return float("nan")
    near = pick[np.argsort(np.abs(chain.strike[pick] - chain.spot))[:4]]
    iv = chain.iv[near]
    return float(np.nanmean(iv)) if np.isfinite(iv).any() else float("nan")


def exits(ctx, p):
    out = []
    for pos in ctx.positions:
        if pos["natural"] is None or pos["entry"] >= 0:
            continue
        credit = -pos["entry"]
        buy_back = -pos["natural"]
        expiring = min(leg["dte"] for leg in pos["legs"]) == 0
        why = None
        if buy_back <= (1.0 - p["profit_target"]) * credit:
            why = "target"
        elif buy_back >= p["stop_loss"] * credit:
            why = "stop"
        elif expiring and ctx.minutes_to_close <= p["exit_minutes_before_close"]:
            why = "time"
        if why and not any(o["position"] == pos["id"] for o in ctx.orders):
            out.append({"close": pos["id"], "limit": "natural", "note": why})
    return out


def decide(ctx):
    p = ctx.params
    if ctx.minute < STATE["last_minute"]:
        STATE["entries"] = 0
    STATE["last_minute"] = ctx.minute
    intents = exits(ctx, p)
    chain = ctx.chain
    if chain is None or chain.n == 0 or not (p["entry_start"] <= ctx.minute < p["entry_end"]):
        return intents
    if len(ctx.positions) >= p["max_open"] or STATE["entries"] >= p["max_entries_day"]:
        return intents
    listed = [int(d) for d in chain.expiries if p["dte_min"] <= d <= p["dte_max"]]
    if not listed:
        return intents
    dte = listed[0]
    iv = atm_iv(chain, dte)
    rv = realized_vol(ctx.under, p["vol_days"])
    if not (math.isfinite(iv) and math.isfinite(rv) and rv > 0 and iv >= p["vrp_min"] * rv):
        return intents
    limit = "natural" if p["limit_ticks"] < 0 else {"mid": p["limit_ticks"]}
    intents.append({
        "open": "iron_condor", "root": ctx.root,
        "legs": [{"side": "long", "right": "P", "rel": 1, "offset": -p["width"]},
                 {"side": "short", "right": "P", "dte": dte, "delta": p["entry_delta"]},
                 {"side": "short", "right": "C", "dte": dte, "delta": p["entry_delta"]},
                 {"side": "long", "right": "C", "rel": 2, "offset": p["width"]}],
        "max_loss": p["risk_usd"], "limit": limit, "tif": 10, "tag": "vrp",
        "note": f"iv {iv:.3f} vs realized {rv:.3f}"})
    STATE["entries"] += 1
    return intents

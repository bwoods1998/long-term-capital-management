"""The 48 founding families and their starter programs, and the equity lanes' three seeds (release E1, A4).

A family is a MECHANISM (why the trade should make money), a structure type and a universe slice. The
first twelve re-express the Deploy G structure founders (condor-vrp, putspread-dip, ironfly-quiet,
strangle-cheap, calendar-term, butterfly-pin, orb, trend-vertical, reversal, skew, diagonal, gap-drift):
their mechanisms, not their old code. The other thirty-six spread the plan's library across the core
roots and the structure types: the variance risk premium in short-dated index options, intraday momentum
and trend days, opening-range breaks and fades, gap reversion, end-of-day drift, 0DTE pinning near large
open interest, term-structure and skew mean reversion, post-event volatility crush, weekly-expiry
dynamics.

THE STARTERS. Each family's first program is assembled here from one signal and one structure builder
with plain, round, unfitted defaults, so a researcher's first cycle runs something real and revises from
there. They are written before any data is seen (nothing here is fitted to licensed data), like the
Gym's own examples; every version after the first is the researcher's and lives only in the House's
state. The starter passes the Gym's safety check (`league/gym/safety.py`): math and numpy only, no date.

Standard library only.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

# --------------------------------------------------------------------------- the program skeleton
SKELETON = '''# {fid}: a founder of the options swarm. {mechanism}
# Structure {structure}; roots {roots}; {dte_lo}-{dte_hi} days to expiry; signal "{signal}". Written before any
# data was seen (unfitted round defaults): the researcher revises it from the Gym's diagnostics.
import math

import numpy as np

NEEDS = {needs}
PARAMS = {params}
STATE = {{"last_minute": 100000, "entries": 0, "day": 0, "daily": {{}}, "center": {{}}}}


def realized_vol(under, days):
    closes = np.asarray(under.closes, dtype=float)
    closes = closes[np.isfinite(closes)][-(int(days) + 1):]
    if closes.size >= 3:
        return float(np.std(np.diff(np.log(closes)), ddof=1) * math.sqrt(252.0))
    return float("nan")


def intraday_vol(under, minutes):
    prices = np.asarray(under.prices, dtype=float)
    prices = prices[np.isfinite(prices)][-(int(minutes) + 1):]
    if prices.size >= 10:
        return float(np.std(np.diff(np.log(prices)), ddof=1) * math.sqrt(252.0 * 390.0))
    return float("nan")


def atm_iv(chain, dte):
    pick = np.flatnonzero(chain.dte == dte)
    if pick.size == 0:
        return float("nan")
    near = pick[np.argsort(np.abs(chain.strike[pick] - chain.spot))[:4]]
    iv = np.asarray(chain.iv[near], dtype=float)
    iv = iv[np.isfinite(iv)]
    return float(np.mean(iv)) if iv.size else float("nan")


def delta_iv(chain, dte, call, target):
    pick = np.flatnonzero((chain.dte == dte) & (chain.is_call == call))
    if pick.size == 0:
        return float("nan")
    d = np.abs(np.asarray(chain.delta[pick], dtype=float))
    ok = np.isfinite(d)
    if not ok.any():
        return float("nan")
    i = pick[ok][np.argmin(np.abs(d[ok] - target))]
    return float(chain.iv[i])


def pick_dte(chain, lo, hi):
    listed = [int(d) for d in chain.expiries if lo <= d <= hi]
    return listed[0] if listed else None


def exits(ctx, p):
    out = []
    for pos in ctx.positions:
        if pos["natural"] is None or any(o["position"] == pos["id"] for o in ctx.orders):
            continue
        entry, now = pos["entry"], pos["natural"]
        why = None
        if entry < 0:
            credit, cost = -entry, -now
            if cost <= (1.0 - p["profit_target"]) * credit:
                why = "target"
            elif cost >= p["stop_loss"] * credit:
                why = "stop"
        elif entry > 0:
            if now >= entry * (1.0 + p["debit_target"]):
                why = "target"
            elif now <= entry * (1.0 - p["debit_stop"]):
                why = "stop"
        near = min(leg["dte"] for leg in pos["legs"])
        if near == 0 and ctx.minute >= ctx.rules.get(pos["root"], {{}}).get("close_cutoff", 960) - 1:
            continue  # past the venue's closing cutoff on an expiring contract: it settles or is liquidated
        late = ctx.minutes_to_close <= p["exit_minutes_before_close"]
        if why is None and late and (near == 0 or pos["held_days"] >= p["max_hold_days"]):
            why = "time"
        if why:
            out.append({{"close": pos["id"], "limit": "natural", "note": why}})
    return out


def signal(ctx, root, chain, under, dte, p):
{signal_code}


def legs_for(root, direction, dte, p):
{build_code}


def decide(ctx):
    p = ctx.params
    if ctx.minute < STATE["last_minute"]:
        STATE["entries"] = 0
        STATE["day"] += 1
    STATE["last_minute"] = ctx.minute
    intents = exits(ctx, p)
    if not (p["entry_start"] <= ctx.minute < p["entry_end"]) or STATE["entries"] >= p["max_entries_day"]:
        return intents
    for root in ctx.chains:
        chain = ctx.chains[root]
        under = ctx.underlyings.get(root)
        if chain is None or chain.n == 0 or under is None:
            continue
        if sum(1 for pos in ctx.positions if pos["root"] == root) >= p["max_open"]:
            continue
        dte = pick_dte(chain, p["dte_min"], p["dte_max"])
        if dte is None or (dte == 0 and ctx.minute >= ctx.rules.get(root, {{}}).get("open_cutoff", 900) - 1):
            continue
        go, direction, note = signal(ctx, root, chain, under, dte, p)
        if not go:
            continue
        built = legs_for(root, direction, dte, p)
        if built is None:
            continue
        kind, legs = built
        intents.append({{"open": kind, "root": root, "legs": legs, "max_loss": p["risk_usd"], "limit": "natural",
                        "tif": p["tif"], "tag": "{signal}", "note": note}})
        STATE["entries"] += 1
        if STATE["entries"] >= p["max_entries_day"]:
            break
    return intents
'''

COMMON = {"profit_target": 0.5, "stop_loss": 2.0, "debit_target": 0.8, "debit_stop": 0.5, "exit_minutes_before_close": 55,
          "max_hold_days": 1, "max_open": 2, "max_entries_day": 2, "entry_start": 600, "entry_end": 900, "risk_usd": 150.0,
          "tif": 10, "width": 1.0}

# --------------------------------------------------------------------------- signals: (go, direction, note)
SIGNALS: dict[str, tuple[str, dict[str, Any]]] = {
    "vrp": ('''    iv = atm_iv(chain, dte)
    rv = realized_vol(under, p["vol_days"])
    if not (math.isfinite(iv) and math.isfinite(rv) and rv > 0):
        return False, 0, "no vol"
    return iv >= p["vrp_min"] * rv, 0, "implied over realized"''', {"vrp_min": 1.2, "vol_days": 5}),
    "quiet": ('''    iv = atm_iv(chain, dte)
    rv = intraday_vol(under, p["quiet_minutes"])
    span = (float(under.high) - float(under.low)) / float(under.price) * 100.0 if under.price else 99.0
    if not (math.isfinite(iv) and math.isfinite(rv) and rv > 0):
        return False, 0, "no vol"
    return rv <= p["quiet_ratio"] * iv and span <= p["range_pct"], 0, "a quiet midday"''',
              {"quiet_minutes": 45, "quiet_ratio": 0.6, "range_pct": 0.8}),
    "dip": ('''    closes = np.asarray(under.closes, dtype=float)
    days = int(p["trend_days"])
    if closes.size < days or not math.isfinite(float(under.price)):
        return False, 0, "no history"
    if closes[-1] <= float(np.mean(closes[-days:])):
        return False, 0, "no uptrend"
    top = max(float(under.high), float(closes[-1]))
    drop = (top - float(under.price)) / top * 100.0
    return drop >= p["dip_pct"], 1, "a dip in an uptrend"''', {"trend_days": 10, "dip_pct": 0.5}),
    "orb_break": ('''    prices = np.asarray(under.prices, dtype=float)
    m = int(p["range_minutes"])
    if prices.size <= m + 1:
        return False, 0, "range forming"
    hi, lo = float(np.nanmax(prices[:m])), float(np.nanmin(prices[:m]))
    now = float(under.price)
    if now > hi * (1.0 + p["break_pct"] / 100.0):
        return True, 1, "broke the opening range up"
    if now < lo * (1.0 - p["break_pct"] / 100.0):
        return True, -1, "broke the opening range down"
    return False, 0, "inside the range"''', {"range_minutes": 30, "break_pct": 0.05}),
    "orb_fade": ('''    prices = np.asarray(under.prices, dtype=float)
    m = int(p["range_minutes"])
    if prices.size <= m + 1:
        return False, 0, "range forming"
    hi, lo = float(np.nanmax(prices[:m])), float(np.nanmin(prices[:m]))
    now = float(under.price)
    if now > hi * (1.0 + p["break_pct"] / 100.0):
        return True, -1, "fading a break up"
    if now < lo * (1.0 - p["break_pct"] / 100.0):
        return True, 1, "fading a break down"
    return False, 0, "inside the range"''', {"range_minutes": 30, "break_pct": 0.05}),
    "gap_revert": ('''    prior = float(under.prior_close) if under.prior_close else float("nan")
    if not math.isfinite(prior) or prior <= 0:
        return False, 0, "no prior close"
    gap = (float(under.open) - prior) / prior * 100.0
    now = float(under.price)
    if abs(gap) < p["gap_pct"]:
        return False, 0, "no gap"
    unfilled = (now - prior) * gap > 0
    return unfilled, -1 if gap > 0 else 1, "betting the gap fills"''', {"gap_pct": 0.4}),
    "gap_go": ('''    prior = float(under.prior_close) if under.prior_close else float("nan")
    if not math.isfinite(prior) or prior <= 0:
        return False, 0, "no prior close"
    gap = (float(under.open) - prior) / prior * 100.0
    now = float(under.price)
    held = (now - float(under.open)) * gap >= 0
    return abs(gap) >= p["gap_pct"] and held, 1 if gap > 0 else -1, "riding a gap that held"''', {"gap_pct": 0.6}),
    "trend_day": ('''    opened = float(under.open)
    if not opened:
        return False, 0, "no open"
    move = (float(under.price) - opened) / opened * 100.0
    if abs(move) < p["move_pct"]:
        return False, 0, "no trend yet"
    return True, 1 if move > 0 else -1, "a trend day continues"''', {"move_pct": 0.5}),
    "eod_drift": ('''    opened = float(under.open)
    if not opened:
        return False, 0, "no open"
    move = (float(under.price) - opened) / opened * 100.0
    if abs(move) < p["move_pct"]:
        return False, 0, "a flat day"
    return True, 1 if move > 0 else -1, "the day's drift into the close"''', {"move_pct": 0.3}),
    "late_fade": ('''    opened = float(under.open)
    if not opened:
        return False, 0, "no open"
    move = (float(under.price) - opened) / opened * 100.0
    if abs(move) < p["move_pct"]:
        return False, 0, "no stretch"
    return True, -1 if move > 0 else 1, "fading a stretched day"''', {"move_pct": 1.0}),
    "open_drive": ('''    prices = np.asarray(under.prices, dtype=float)
    m = int(p["drive_minutes"])
    if prices.size <= m or not float(under.open):
        return False, 0, "too early"
    move = (float(prices[m]) - float(under.open)) / float(under.open) * 100.0
    if abs(move) < p["drive_pct"]:
        return False, 0, "no drive"
    return True, 1 if move > 0 else -1, "the opening drive"''', {"drive_minutes": 15, "drive_pct": 0.25}),
    "pin": ('''    if dte != 0 or ctx.minute < p["pin_after"]:
        return False, 0, "not an expiry afternoon"
    pick = np.flatnonzero((chain.dte == 0) & (np.abs(chain.strike - chain.spot) <= chain.spot * p["pin_pct"] / 100.0))
    oi = np.asarray(chain.oi[pick], dtype=float) if pick.size else np.zeros(0)
    if oi.size == 0 or not np.isfinite(oi).any():
        return False, 0, "no open interest"
    best = pick[int(np.nanargmax(oi))]
    STATE["center"][root] = float(chain.strike[best])
    return True, 0, "pinned to the largest open interest"''', {"pin_after": 780, "pin_pct": 0.4}),
    "skew": ('''    put = delta_iv(chain, dte, False, 0.25)
    call = delta_iv(chain, dte, True, 0.25)
    if not (math.isfinite(put) and math.isfinite(call)):
        return False, 0, "no skew"
    skew = put - call
    hist = STATE["daily"].setdefault(root, [])
    if not hist or hist[-1][0] != STATE["day"]:
        hist.append([STATE["day"], skew])
        del hist[:-int(p["skew_days"])]
    before = np.asarray([h[1] for h in hist[:-1]], dtype=float)
    if before.size < 5:
        return False, 0, "learning the skew"
    sd = float(np.std(before)) or 1e-6
    z = (skew - float(np.mean(before))) / sd
    return z >= p["skew_z"], 1, "put skew rich against its recent days"''', {"skew_days": 20, "skew_z": 1.0}),
    "term": ('''    back = pick_dte(chain, p["back_min"], p["back_max"])
    if back is None or back <= dte:
        return False, 0, "no back month"
    front, far = atm_iv(chain, dte), atm_iv(chain, back)
    if not (math.isfinite(front) and math.isfinite(far) and far > 0):
        return False, 0, "no vol"
    STATE["center"][root] = back
    return front / far >= p["kink_min"], 0, "the front's vol kinked over the back's"''', {"back_min": 5, "back_max": 12, "kink_min": 1.1}),
    "cheap_vol": ('''    iv = atm_iv(chain, dte)
    rv = realized_vol(under, p["vol_days"])
    if not (math.isfinite(iv) and math.isfinite(rv) and rv > 0):
        return False, 0, "no vol"
    return iv <= p["cheap_ratio"] * rv, 0, "implied under realized"''', {"cheap_ratio": 0.9, "vol_days": 10}),
    "event_crush": ('''    ev = ctx.events
    if not (ev.get("cpi") or ev.get("jobs") or ev.get("fomc")):
        return False, 0, "no event today"
    if ev.get("fomc") and ctx.minute < p["fomc_after"]:
        return False, 0, "before the statement"
    iv = atm_iv(chain, dte)
    rv = realized_vol(under, p["vol_days"])
    if not (math.isfinite(iv) and math.isfinite(rv) and rv > 0):
        return False, 0, "no vol"
    return iv >= p["vrp_min"] * rv, 0, "selling the vol an event left behind"''', {"fomc_after": 875, "vrp_min": 1.0, "vol_days": 5}),
    "event_long": ('''    ev = ctx.events_next
    if not (ev.get("cpi") or ev.get("jobs") or ev.get("fomc")):
        return False, 0, "no event next session"
    iv = atm_iv(chain, dte)
    rv = realized_vol(under, p["vol_days"])
    if not (math.isfinite(iv) and math.isfinite(rv) and rv > 0):
        return False, 0, "no vol"
    return iv <= p["cheap_ratio"] * rv, 0, "owning vol into an event"''', {"cheap_ratio": 1.1, "vol_days": 10}),
    "weekly": ('''    if ctx.weekday != p["weekday"]:
        return False, 0, "not the day"
    iv = atm_iv(chain, dte)
    rv = realized_vol(under, p["vol_days"])
    if not (math.isfinite(iv) and math.isfinite(rv) and rv > 0):
        return False, 0, "no vol"
    return iv >= p["vrp_min"] * rv, 0, "the weekly expiry's premium"''', {"weekday": 4, "vrp_min": 1.0, "vol_days": 5}),
    "momentum": ('''    closes = np.asarray(under.closes, dtype=float)
    days = int(p["trend_days"])
    if closes.size < days:
        return False, 0, "no history"
    mean = float(np.mean(closes[-days:]))
    now = float(under.price)
    if abs(now - mean) / mean * 100.0 < p["trend_pct"]:
        return False, 0, "no trend"
    return True, 1 if now > mean else -1, "with the multi-day trend"''', {"trend_days": 20, "trend_pct": 1.0}),
    "reversal": ('''    closes = np.asarray(under.closes, dtype=float)
    days = int(p["trend_days"])
    if closes.size < max(days, 3):
        return False, 0, "no history"
    up = closes[-1] > float(np.mean(closes[-days:]))
    fall = (closes[-3] - float(under.price)) / closes[-3] * 100.0
    return up and fall >= p["fall_pct"], 1, "a sharp pullback in an uptrend"''', {"trend_days": 50, "fall_pct": 1.5}),
    "breakout": ('''    highs = np.asarray(under.highs, dtype=float)
    lows = np.asarray(under.lows, dtype=float)
    days = int(p["range_days"])
    if highs.size < days:
        return False, 0, "no history"
    now = float(under.price)
    if now > float(np.max(highs[-days:])):
        return True, 1, "a range breakout up"
    if now < float(np.min(lows[-days:])):
        return True, -1, "a range breakdown"
    return False, 0, "inside the range"''', {"range_days": 20}),
}

# --------------------------------------------------------------------------- structures: (type, legs)
BUILDS: dict[str, str] = {
    "iron_condor": '''    return "iron_condor", [
        {"side": "long", "right": "P", "rel": 1, "offset": -p["width"]},
        {"side": "short", "right": "P", "dte": dte, "delta": p["short_delta"]},
        {"side": "short", "right": "C", "dte": dte, "delta": p["short_delta"]},
        {"side": "long", "right": "C", "rel": 2, "offset": p["width"]}]''',
    "iron_butterfly": '''    return "iron_butterfly", [
        {"side": "short", "right": "P", "dte": dte, "atm": 0},
        {"side": "short", "right": "C", "rel": 0, "offset": 0.0},
        {"side": "long", "right": "P", "rel": 0, "offset": -p["width"]},
        {"side": "long", "right": "C", "rel": 0, "offset": p["width"]}]''',
    "credit_vertical": '''    if direction >= 0:
        return "credit_vertical", [{"side": "short", "right": "P", "dte": dte, "delta": p["short_delta"]},
                                   {"side": "long", "right": "P", "rel": 0, "offset": -p["width"]}]
    return "credit_vertical", [{"side": "short", "right": "C", "dte": dte, "delta": p["short_delta"]},
                               {"side": "long", "right": "C", "rel": 0, "offset": p["width"]}]''',
    "debit_vertical": '''    if direction == 0:
        return None
    if direction > 0:
        return "debit_vertical", [{"side": "long", "right": "C", "dte": dte, "delta": p["long_delta"]},
                                  {"side": "short", "right": "C", "rel": 0, "offset": p["width"]}]
    return "debit_vertical", [{"side": "long", "right": "P", "dte": dte, "delta": p["long_delta"]},
                              {"side": "short", "right": "P", "rel": 0, "offset": -p["width"]}]''',
    "long_call": '''    if direction < 0:
        return "long_put", [{"side": "long", "right": "P", "dte": dte, "delta": p["long_delta"]}]
    return "long_call", [{"side": "long", "right": "C", "dte": dte, "delta": p["long_delta"]}]''',
    "long_put": '''    if direction > 0:
        return "long_call", [{"side": "long", "right": "C", "dte": dte, "delta": p["long_delta"]}]
    return "long_put", [{"side": "long", "right": "P", "dte": dte, "delta": p["long_delta"]}]''',
    # The two-sided single (Sept 29, 2026): the signal's sign picks the side, and no signal sends nothing.
    "long_single": '''    if direction == 0:
        return None
    if direction > 0:
        return "long_call", [{"side": "long", "right": "C", "dte": dte, "delta": p["long_delta"]}]
    return "long_put", [{"side": "long", "right": "P", "dte": dte, "delta": p["long_delta"]}]''',
    "long_straddle": '''    return "long_straddle", [{"side": "long", "right": "C", "dte": dte, "atm": 0},
                             {"side": "long", "right": "P", "rel": 0, "offset": 0.0}]''',
    "long_strangle": '''    return "long_strangle", [{"side": "long", "right": "C", "dte": dte, "delta": p["wing_delta"]},
                             {"side": "long", "right": "P", "dte": dte, "delta": p["wing_delta"]}]''',
    "long_butterfly": '''    center = STATE["center"].get(root)
    body = {"side": "short", "right": "C", "dte": dte, "ratio": 2}
    if center is not None and direction == 0:
        body["strike"] = center
    elif direction == 0:
        body["atm"] = 0
    else:
        body["moneyness"] = p["body_moneyness"] * direction
    return "long_butterfly", [{"side": "long", "right": "C", "rel": 1, "offset": -p["width"]}, body,
                              {"side": "long", "right": "C", "rel": 1, "offset": p["width"]}]''',
    "calendar": '''    back = STATE["center"].get(root) or p["back_dte"]
    return "calendar", [{"side": "short", "right": "C", "dte": dte, "atm": 0},
                        {"side": "long", "right": "C", "rel": 0, "offset": 0.0, "dte": back}]''',
    "diagonal": '''    right = "C" if direction >= 0 else "P"
    sign = 1.0 if direction >= 0 else -1.0
    return "diagonal", [{"side": "short", "right": right, "dte": dte, "delta": p["short_delta"]},
                        {"side": "long", "right": right, "rel": 0, "offset": -sign * p["width"], "dte": p["back_dte"]}]''',
}

BUILD_PARAMS: dict[str, dict[str, Any]] = {
    "iron_condor": {"short_delta": 0.15}, "iron_butterfly": {}, "credit_vertical": {"short_delta": 0.25},
    "debit_vertical": {"long_delta": 0.5}, "long_call": {"long_delta": 0.5}, "long_put": {"long_delta": 0.5},
    "long_single": {"long_delta": 0.5},
    "long_straddle": {}, "long_strangle": {"wing_delta": 0.3}, "long_butterfly": {"body_moneyness": 0.003},
    "calendar": {"back_dte": 7}, "diagonal": {"short_delta": 0.3, "back_dte": 7},
}


def _seed(fid: str, mechanism: str, structure: str, roots: list[str], dte: tuple[int, int], signal: str, rejection: str,
          *, founder: str | None = None, cadence: int = 5, history: int = 25, band: float = 0.04, **params: Any) -> dict[str, Any]:
    return {"id": fid, "mechanism": mechanism, "structure": structure, "roots": roots, "dte": list(dte), "signal": signal,
            "rejection": rejection, "founder": founder, "needs": {"roots": roots, "dte": list(dte), "band": band, "cadence": cadence,
                                                                   "history": history}, "params": params}


FOUNDERS = [
    _seed("condor-vrp", "Short-dated index options price a bigger move than follows on average (the variance risk premium); "
          "an iron condor sells it with the loss capped at the wing.", "iron_condor", ["SPY"], (0, 2), "vrp",
          "Rejected if the condor loses after fees over the train window or its worst week wipes out a quarter's gains.",
          founder="options-condor-vrp"),
    _seed("putspread-dip", "Index puts are richest right after a sell-off, and in an uptrend an intraday dip is bought more often "
          "than extended; a put credit vertical sells the dip's premium.", "credit_vertical", ["SPY"], (1, 4), "dip",
          "Rejected if dips in uptrends extend as often as they recover (win rate below the breakeven of the credit).",
          founder="options-putspread-dip", cadence=10),
    _seed("ironfly-quiet", "Volatility clusters: a quiet midday tends to stay quiet while at-the-money options still carry the "
          "morning's vol; an iron butterfly sells that decay.", "iron_butterfly", ["QQQ"], (0, 1), "quiet",
          "Rejected if quiet middays are followed by afternoon moves that exceed the fly's credit.", founder="options-ironfly-quiet",
          entry_start=690, entry_end=840, max_entries_day=1),
    _seed("strangle-cheap", "When implied vol falls below the vol the underlying has been realizing, owning a strangle buys "
          "movement cheaply.", "long_strangle", ["IWM"], (1, 5), "cheap_vol",
          "Rejected if strangles bought under realized vol still lose their premium on average.", founder="options-strangle-cheap",
          cadence=15, max_hold_days=2),
    _seed("calendar-term", "When the front expiry's implied vol is kinked above the back's, the kink tends to relax and the front "
          "decays fastest; a calendar is long that normalisation.", "calendar", ["SPY"], (1, 3), "term",
          "Rejected if front-over-back kinks persist or widen as often as they relax.", founder="options-calendar-term", cadence=15),
    _seed("butterfly-pin", "On an expiry afternoon, dealer hedging near the strike with the most open interest tends to hold the "
          "price there into the close; a long butterfly centered on it pays most at the pin.", "long_butterfly", ["SPY"], (0, 0),
          "pin", "Rejected if expiry closes land no nearer the largest open interest than chance would put them.",
          founder="options-butterfly-pin", entry_start=780, entry_end=900, max_entries_day=1),
    _seed("orb-fade", "Breaks of the first half hour's range in liquid index ETFs often fail and give the move back; a debit "
          "vertical against the break caps the loss.", "debit_vertical", ["SPY"], (0, 4), "orb_fade",
          "Rejected if breaks of the opening range extend more often than they fail.", founder="options-orb", entry_start=615,
          entry_end=780),
    _seed("trend-vertical", "Multi-day trends in index ETFs persist (time-series momentum); a debit vertical with the trend "
          "rides it with the loss capped at the debit.", "debit_vertical", ["QQQ"], (3, 7), "momentum",
          "Rejected if the trend's direction predicts the next days' move no better than a coin.", founder="options-trend-vertical",
          cadence=30, max_hold_days=3, max_entries_day=1),
    _seed("reversal-call", "A sharp two-day pullback inside a long uptrend tends to be bought back within days; a call caps the "
          "loss if the pullback is the start of something worse.", "long_call", ["IWM"], (3, 7), "reversal",
          "Rejected if pullbacks in uptrends keep falling as often as they bounce.", founder="options-reversal", cadence=30,
          max_hold_days=3, max_entries_day=1),
    _seed("skew-revert", "When the put skew is rich against its own recent days, selling a put credit vertical collects the "
          "excess as the skew mean-reverts.", "credit_vertical", ["SPY"], (1, 5), "skew",
          "Rejected if rich put skew is followed by down moves large enough to pay for it.", founder="options-skew", cadence=15),
    _seed("diagonal-trend", "Near-dated options decay fastest: in an uptrend, a short near call pays for a longer call below it, "
          "and a move with the trend lifts the long leg more.", "diagonal", ["QQQ"], (1, 3), "momentum",
          "Rejected if the near leg's decay does not cover the far leg's decay and the spread paid.", founder="options-diagonal",
          cadence=30, max_hold_days=2, max_entries_day=1, trend_days=10, trend_pct=0.5, risk_usd=300.0),
    _seed("gap-drift", "A gap that holds through the first half hour tends to keep drifting its way for days (under-reaction "
          "to news); a debit vertical rides it.", "debit_vertical", ["SPY"], (2, 7), "gap_go",
          "Rejected if held gaps reverse as often as they drift.", founder="options-gap-drift", entry_start=615, entry_end=720,
          max_hold_days=3, max_entries_day=1),
]

LIBRARY = [
    # the variance risk premium in short-dated index options
    _seed("vrp-condor-xsp", "The variance risk premium is largest at the shortest maturities: sell a 0DTE iron condor on XSP "
          "(cash-settled, no assignment) when implied vol sits over realized.", "iron_condor", ["XSP"], (0, 0), "vrp",
          "Rejected if 0DTE condors lose after fees or their losses cluster in high-vol weeks.", width=2.0, risk_usd=300.0),
    _seed("vrp-condor-spxw", "The same premium on SPXW's 0DTE chain, where strikes are finer and the premium is paid in larger "
          "units.", "iron_condor", ["SPXW"], (0, 0), "vrp", "Rejected if the premium does not survive SPXW's fees.", width=5.0, risk_usd=600.0,
          band=0.03),
    _seed("vrp-fly-xsp", "At-the-money 0DTE options decay fastest in the afternoon: an XSP iron butterfly sells the last hours' "
          "decay when implied vol is over realized.", "iron_butterfly", ["XSP"], (0, 0), "vrp",
          "Rejected if afternoon moves exceed the fly's credit as often as not.", width=2.0, risk_usd=300.0, entry_start=750, entry_end=870,
          max_entries_day=1),
    _seed("vrp-putspread-iwm", "Small-cap index puts carry a rich premium; a put credit vertical on IWM sells it when implied "
          "vol runs over realized.", "credit_vertical", ["IWM"], (1, 4), "vrp", "Rejected if IWM's put premium is eaten by its "
          "down moves.", cadence=10),
    _seed("vrp-callspread-qqq", "The call side of the premium: when QQQ's implied vol is rich, a call credit vertical above the "
          "market collects it with the loss capped.", "credit_vertical", ["QQQ"], (1, 4), "vrp",
          "Rejected if QQQ's upside moves pay out more than the call premium collected.", cadence=10),
    # intraday momentum and trend days
    _seed("trend-day-spy", "Intraday momentum: a day that has moved half a percent from its open by midday tends to keep going "
          "into the close; a 0DTE debit vertical rides it.", "debit_vertical", ["SPY"], (0, 1), "trend_day",
          "Rejected if midday moves reverse into the close as often as they extend.", entry_start=720, entry_end=870,
          max_entries_day=1),
    _seed("trend-day-xsp", "The same intraday momentum on XSP, cash-settled so the vertical can be held into the close.",
          "debit_vertical", ["XSP"], (0, 0), "trend_day", "Rejected if XSP's midday moves do not extend into the close.",
          width=2.0, risk_usd=300.0, entry_start=720, entry_end=870, max_entries_day=1),
    _seed("trend-day-qqq-call", "Technology leads trend days: a QQQ trend day's direction bought with a single 0-1 DTE option.",
          "long_call", ["QQQ"], (0, 1), "trend_day", "Rejected if single options lose their premium on trend days.",
          entry_start=720, entry_end=870, max_entries_day=1),
    _seed("open-drive-qqq", "The first fifteen minutes' drive sets the day's direction more often than not; a debit vertical "
          "follows it.", "debit_vertical", ["QQQ"], (0, 2), "open_drive", "Rejected if opening drives reverse as often as they run.",
          entry_start=586, entry_end=660, max_entries_day=1),
    _seed("open-drive-iwm-fly", "A strong opening drive in IWM pulls the close toward a level beyond the open; a long butterfly "
          "a little beyond the money pays if it lands there.", "long_butterfly", ["IWM"], (0, 1), "open_drive",
          "Rejected if drive days close no nearer the fly's body than chance.", entry_start=586, entry_end=660, max_entries_day=1),
    # opening-range breaks and fades
    _seed("orb-break-xsp", "The published intraday momentum: a break of the opening range tends to extend; an XSP debit "
          "vertical with the break.", "debit_vertical", ["XSP"], (0, 0), "orb_break",
          "Rejected if XSP's range breaks fail more often than they extend.", width=2.0, risk_usd=300.0, entry_start=615, entry_end=780),
    _seed("orb-break-qqq", "QQQ's opening-range breaks, taken with a single option for the cleanest payoff on an extension.",
          "long_call", ["QQQ"], (0, 2), "orb_break", "Rejected if the option's premium outruns the breaks' follow-through.",
          entry_start=615, entry_end=780),
    _seed("orb-fade-iwm", "Small caps overshoot early: IWM's breaks of the opening range tend to fail and return to the range.",
          "debit_vertical", ["IWM"], (0, 4), "orb_fade", "Rejected if IWM's breaks extend more often than they fail.",
          entry_start=615, entry_end=780),
    # gap reversion
    _seed("gap-revert-spy", "Opening gaps in index ETFs without news tend to fill during the day; a debit vertical toward the "
          "prior close.", "debit_vertical", ["SPY"], (0, 2), "gap_revert", "Rejected if gaps extend as often as they fill.",
          entry_start=600, entry_end=690, max_entries_day=1),
    _seed("gap-revert-qqq-credit", "Selling the side of the gap: a credit vertical that wins if the gap does not extend further.",
          "credit_vertical", ["QQQ"], (0, 2), "gap_revert", "Rejected if gaps that have not filled by mid-morning keep running.",
          entry_start=600, entry_end=690, max_entries_day=1),
    _seed("gap-revert-iwm", "IWM's opening gaps overshoot the index's news; a single option toward the fill.", "long_put", ["IWM"],
          (0, 2), "gap_revert", "Rejected if IWM's gaps do not fill often enough to pay the premium.", entry_start=600,
          entry_end=690, max_entries_day=1),
    # end-of-day drift
    _seed("eod-drift-xsp", "The last hour tends to extend the day's move (rebalancing and leveraged-ETF hedging); an XSP 0DTE "
          "debit vertical with the day's direction.", "debit_vertical", ["XSP"], (0, 0), "eod_drift",
          "Rejected if the last hour reverses the day as often as it extends it.", width=2.0, risk_usd=300.0, entry_start=870, entry_end=899,
          max_entries_day=1, exit_minutes_before_close=0),
    _seed("eod-drift-spxw", "The same last-hour drift on SPXW, where the fee per dollar of risk is lowest.", "debit_vertical",
          ["SPXW"], (0, 0), "eod_drift", "Rejected if SPXW's last hour does not extend the day after fees.", width=5.0, risk_usd=600.0, band=0.03,
          entry_start=870, entry_end=899, max_entries_day=1, exit_minutes_before_close=0),
    _seed("late-fade-spy", "A day stretched a full percent by mid-afternoon tends to give some back into the close; a debit "
          "vertical against it.", "debit_vertical", ["SPY"], (0, 1), "late_fade", "Rejected if stretched days extend into the close.",
          entry_start=840, entry_end=900, max_entries_day=1),
    # 0DTE pinning
    _seed("pin-xsp", "0DTE pinning: XSP's close drifts toward the strike with the largest open interest; a long butterfly "
          "centered there.", "long_butterfly", ["XSP"], (0, 0), "pin", "Rejected if XSP closes land no nearer the largest open "
          "interest than chance.", width=2.0, risk_usd=300.0, entry_start=780, entry_end=900, max_entries_day=1, exit_minutes_before_close=0),
    _seed("pin-spxw", "The same pin on SPXW, cash-settled and held to the close.", "long_butterfly", ["SPXW"], (0, 0), "pin",
          "Rejected if SPXW's close is not drawn to the largest open interest.", width=5.0, risk_usd=600.0, band=0.03, entry_start=780,
          entry_end=900, max_entries_day=1, exit_minutes_before_close=0),
    _seed("pin-qqq-fly", "QQQ's expiry afternoons pin near their largest open interest; an iron butterfly sells the decay at the "
          "pin.", "iron_butterfly", ["QQQ"], (0, 0), "pin", "Rejected if QQQ's pins break as often as they hold.", entry_start=780,
          entry_end=870, max_entries_day=1),
    # term structure and skew
    _seed("term-calendar-qqq", "QQQ's front-week vol kinks over the back when news is priced into the next days; a calendar is "
          "long its relaxation.", "calendar", ["QQQ"], (1, 3), "term", "Rejected if QQQ's front kinks do not relax.", cadence=15),
    _seed("term-calendar-iwm", "The same term kink on IWM, whose front vol spikes most.", "calendar", ["IWM"], (1, 3), "term",
          "Rejected if IWM's front kinks persist.", cadence=15),
    _seed("skew-revert-qqq", "QQQ's put skew mean-reverts; sell a put credit vertical when it is rich against its recent days.",
          "credit_vertical", ["QQQ"], (1, 5), "skew", "Rejected if QQQ's rich skew precedes down moves that pay for it.", cadence=15),
    _seed("skew-revert-xsp", "The index put skew on XSP's short-dated chain, sold when rich.", "credit_vertical", ["XSP"], (0, 3),
          "skew", "Rejected if XSP's rich skew precedes the moves it priced.", width=2.0, risk_usd=300.0, cadence=15),
    # post-event vol crush and pre-event vol
    _seed("event-crush-spy", "After a scheduled macro release (CPI, jobs, the FOMC statement) implied vol falls faster than the "
          "market moves; an iron condor sells what the event left behind.", "iron_condor", ["SPY"], (0, 2), "event_crush",
          "Rejected if post-event days move more than the condor's credit covers.", max_entries_day=1),
    _seed("event-crush-xsp-fly", "The same post-event crush sold at the money on XSP.", "iron_butterfly", ["XSP"], (0, 1),
          "event_crush", "Rejected if post-event afternoons move beyond the fly's credit.", width=2.0, risk_usd=300.0, max_entries_day=1),
    _seed("event-straddle-qqq", "The day before a macro release, owning a straddle while implied vol is not yet over realized "
          "buys the release's move cheaply.", "long_straddle", ["QQQ"], (1, 5), "event_long",
          "Rejected if pre-event straddles lose their premium on average.", entry_start=840, entry_end=930, max_hold_days=1,
          max_entries_day=1),
    # weekly-expiry dynamics
    _seed("weekly-friday-condor-spxw", "Friday's weekly expiry carries the week's last premium; an SPXW 0DTE iron condor sells "
          "it on Friday mornings when implied vol is over realized.", "iron_condor", ["SPXW"], (0, 0), "weekly",
          "Rejected if Fridays' moves outrun the premium collected.", width=5.0, risk_usd=600.0, band=0.03, max_entries_day=1),
    _seed("weekly-monday-qqq", "Weekend decay is priced into Monday's weekly options; a QQQ iron condor sells Monday's premium.",
          "iron_condor", ["QQQ"], (0, 4), "weekly", "Rejected if Monday's premium does not pay for the week's moves.",
          weekday=0, max_entries_day=1),
    # daily trends and breakouts with single options
    _seed("breakout-iwm", "A twenty-day range breakout in IWM tends to extend; a single option in its direction caps the loss "
          "at the premium.", "long_call", ["IWM"], (3, 10), "breakout", "Rejected if breakouts fail more often than the premium "
          "allows.", cadence=30, max_hold_days=4, max_entries_day=1),
    _seed("momentum-spy-diagonal", "SPY's multi-day trend with a diagonal: the near leg's decay funds the far leg.", "diagonal",
          ["SPY"], (1, 3), "momentum", "Rejected if the trend's follow-through does not pay the spread.", cadence=30,
          max_hold_days=2, max_entries_day=1, trend_days=10, trend_pct=0.5, risk_usd=300.0),
    _seed("cheap-vol-spy-straddle", "When SPY's implied vol trades under its realized vol, a straddle buys movement below its "
          "recent price.", "long_straddle", ["SPY"], (1, 5), "cheap_vol", "Rejected if cheap-vol straddles still lose on average.",
          cadence=15, max_hold_days=2, max_entries_day=1),
    _seed("dip-debit-qqq", "QQQ dips in an uptrend are bought back; a call debit vertical owns the bounce with the loss capped.",
          "debit_vertical", ["QQQ"], (1, 5), "dip", "Rejected if QQQ's dips extend as often as they bounce.", cadence=10,
          max_entries_day=1),
    _seed("quiet-condor-spy", "A quiet SPY midday stays quiet; a 0DTE iron condor sells the afternoon's decay.", "iron_condor",
          ["SPY"], (0, 0), "quiet", "Rejected if quiet middays lead to afternoon moves beyond the wings.", entry_start=690,
          entry_end=840, max_entries_day=1),
]

SEEDS: list[dict[str, Any]] = FOUNDERS + LIBRARY


def program_for(spec: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """(the starter program's source, {}) for a seed spec. The defaults are in the source's PARAMS; the
    overrides dict is empty (a researcher changes them by writing new versions or passing params)."""
    signal = spec["signal"]
    structure = spec["structure"]
    sig_code, sig_params = SIGNALS[signal]
    params = {**COMMON, **BUILD_PARAMS.get(structure, {}), **sig_params}
    lo, hi = spec["dte"]
    params.update({"dte_min": int(lo), "dte_max": int(hi)})
    params.update(spec.get("params") or {})
    needs = dict(spec.get("needs") or {"roots": list(spec["roots"]), "dte": [int(lo), int(hi)], "band": 0.04, "cadence": 5,
                                         "history": 25})
    needs.setdefault("start", 571)
    needs.setdefault("end", 958)
    code = SKELETON.format(fid=spec.get("id") or spec.get("founder") or "family", mechanism=" ".join(str(spec["mechanism"]).split()), structure=structure,
                           roots=", ".join(spec["roots"]), dte_lo=lo, dte_hi=hi, signal=signal, needs=repr(needs),
                           params=repr(params), signal_code=sig_code, build_code=BUILDS[structure])
    return code, {}


def family_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """The family's record (what the store keeps) from a seed spec."""
    return {"id": spec["id"], "mechanism": spec["mechanism"], "structure": spec["structure"], "roots": list(spec["roots"]),
            "dte": list(spec["dte"]), "rejection": spec["rejection"], "signal": spec["signal"], "founder": spec.get("founder"),
            "needs": dict(spec["needs"]), "params": dict(spec.get("params") or {})}


# --------------------------------------------------------------------------- THE EQUITY SEEDS (release E1, A4)
#: THE THREE BETA SEEDS (amendment A4; league/swarm/elane.py `birth_seeds`): each a program with a published prior,
#: written by the captain's build agents under the EQUITY.md contract (league/equity/EQUITY.md: NEEDS, PARAMS,
#: decide(ctx); math and numpy only, no date), and judged by the swarm's screen like any family: born once as a
#: beta-lane family (MARKET BETA), then Validation (2025) with the share screen's pre-check, then one sealed look under
#: the pinned screen (S2, amendment A11). Their cards name the prior and no figure (no census or market result: the
#: repository is public).
#: WHERE EACH CAME FROM, stated as it is (`provenance` in each spec and in the family's record; the program's own
#: header says the same without a year, since a program names no year even in a comment). The two overnight seeds are
#: written from a published prior. The reversal seed is NOT blind on history: its theta and h are the cell a
#: pre-registered census selected on earlier history, which overlaps the Train-era pools its own screen floor is built
#: from. No session of 2020, 2021, 2025 or 2026 was used for any of the three, so Validation and the one sealed look
#: are clean of that choice.
_OVERNIGHT_PROVENANCE = "written from a published prior"
_REVERSAL_PROVENANCE = ("its theta and h are the cell a pre-registered census selected on earlier history, which "
                        "overlaps the Train-era pools its own screen floor is built from; no 2020, 2021, 2025 or 2026 "
                        "session was used")
_OVERNIGHT_WRITTEN = "Written from its published prior."
_REVERSAL_WRITTEN = ("Its theta and h are the cell a pre-registered census selected on earlier history; the Validation "
                     "year and the sealed holdout were never used. They are PARAMS.")
EQUITY_OVERNIGHT = '''# {fid}: MARKET BETA (the beta lane). Seeded by the captain's build agents (A4) and judged by the swarm's screen
# like any family.
# Prior: {prior}.
# {rule} {written}
import math

NEEDS = {needs}
PARAMS = {params}


def decide(ctx):
    share = float(ctx.params["share"])
    intents = []
    for lot in ctx.positions:
        if lot["symbol"] == "{symbol}":
            # bought at a close: sold at the next open (a lot bought at the close may sell at the next open)
            intents.append({{"sell": lot["id"], "at": "open", "tag": "overnight-exit"}})
    close = ctx.bars["{symbol}"].close
    if len(close) < 2:
        return intents
    last, prior = float(close[-1]), float(close[-2])
    if not (math.isfinite(last) and math.isfinite(prior)) or last <= 0:
        return intents
    if {condition}:
        intents.append({{"buy": "{symbol}", "share": share, "at": "close", "tag": "overnight-entry"}})
    return intents
'''

EQUITY_REVERSAL = '''# {fid}: MARKET BETA (the beta lane). Seeded by the captain's build agents (A4) and judged by the swarm's screen
# like any family.
# Prior: {prior}.
# {rule}
# {written}
import math

NEEDS = {needs}
PARAMS = {params}


def decide(ctx):
    theta = float(ctx.params["theta"])
    h = int(ctx.params["h"])
    share = float(ctx.params["share"])
    intents = []
    held = {{}}
    for lot in ctx.positions:
        # held_sessions: the sessions since the lot's entry session, 0 at that session's close (EQUITY.md); the open h
        # sessions after the entry follows the close where it is h - 1
        if int(lot["held_sessions"]) + 1 >= h:
            intents.append({{"sell": lot["id"], "at": "open", "tag": "reversal-exit"}})
        else:
            held[lot["symbol"]] = True
    for symbol in ctx.symbols:
        if held.get(symbol):
            continue
        close = ctx.bars[symbol].close
        if len(close) < 2:
            continue
        last, prior = float(close[-1]), float(close[-2])
        if not (math.isfinite(last) and math.isfinite(prior)) or prior <= 0 or last <= 0:
            continue
        if last / prior - 1.0 <= -theta:
            intents.append({{"buy": symbol, "share": share, "at": "open", "tag": "reversal-entry"}})
    return intents
'''

_OVERNIGHT_PRIOR = ("the overnight effect: index returns accrue mostly from the close to the next open (Cliff, Cooper and "
                    "Gulen 2008; Lou, Polk and Skouras 2019)")
_REVERSAL_PRIOR = "short-term reversal in index ETFs after a sharp down close (Connors and Alvarez 2008)"
_COMPARISON = ("the same-exposure buy-and-hold of the same ETFs over the same sessions (the screen's S1-X label); a pass "
               "that does not beat it is labelled beta, never alpha")
_FALSIFICATION = ("refuted when its one sealed look fails the share screen S2: the holdout's summed daily P&L not above "
                  "zero, or the holdout-only daily t below c_H,used (the larger of the receipt's floor and the program's "
                  "own floor plus the receipt's margin)")

#: THE ORDER OF THIS LIST IS THE ORDER THE SEEDS' LOOKS ARE TAKEN IN (league/swarm/elane.py `round_order`, `seed_wait`),
#: and it is a decision (the captain's, Oct 11, 2026, before any Validation or look, from Train-era figures only). The
#: rehearsal on real bars found the two overnight seeds to be ONE LINEAGE under the lane's own rule (their Train daily
#: returns correlate at or above the rule's 0.7), so only one of them is ever looked at (D3: one look a lineage) and the
#: other is refused its look and retired as the same lineage. Which one must not be the ids' alphabet or a clock tick:
#: seed-overnight-qqq goes first because its own floor sets it the lower bar of the two at the look, so the lineage's
#: one look has the higher power there; seed-reversal-index, a lineage of its own, follows; seed-overnight-spy is last
#: and, with seed-overnight-qqq looked at, is refused its look as the same lineage and retired with that reason,
#: plainly reported.
#: WITHIN A LINEAGE THE ORDER IS STRICT (amendment A18; `elane.seed_wait`): each seed's `lineage` below DECLARES the
#: lineage it is in (the two overnight seeds are one; the reversal seed is its own), and a seed's look is never taken
#: while a seed declared before it in the same lineage is alive without a verdict. There is no timeout: the later seed
#: waits until the earlier one has been looked at (D3 then refuses the later one), has failed its Validation pre-check
#: with no retry owed, or is retired. Seeds of different lineages never wait on each other. The declaration is read by
#: that wait alone: D3's own test (the Train correlation, the template) still judges every look, and `lineage` is no
#: part of a family's record (`equity_family_spec`).
EQUITY_SEEDS: list[dict[str, Any]] = [
    {"id": "seed-overnight-qqq", "lane": "beta", "structure": "etf", "symbols": ["QQQ"], "template": "overnight-down",
     "lineage": "overnight",
     "mechanism": "QQQ's overnight return after a down close: hold QQQ from a close below the prior close to the next "
                  "open (MARKET BETA).",
     "prior": _OVERNIGHT_PRIOR + ", conditioned on short-term reversal (Connors and Alvarez 2008)",
     "provenance": _OVERNIGHT_PROVENANCE,
     "rule": "Buy QQQ at the next close when QQQ closed below its prior close; sell each lot at the following open.",
     "needs": {"symbols": ["QQQ"], "history": 2, "max_hold_sessions": 2}, "params": {"share": 0.5},
     "condition": "last < prior",
     "card": {"lane": "beta", "structure": "etf", "symbols": ["QQQ"],
              "hypothesis": "The overnight effect is larger after a down session: liquidity providers who absorbed the "
                            "day's selling are paid as prices recover overnight (Cliff, Cooper and Gulen 2008; Lou, Polk "
                            "and Skouras 2019; Connors and Alvarez 2008 on short-term reversal).",
              "mechanism_class": "reversal_liquidity", "inputs": ["clock", "underlying_price"], "holding": "days_1_3",
              "cost": {"hurdle": 0.0003, "why": "a round trip pays two QQQ half-spreads at the close and the open, and "
                                                "the SEC and TAF fees on the sale"},
              "comparison": _COMPARISON, "falsification": _FALSIFICATION}},
    {"id": "seed-reversal-index", "lane": "beta", "structure": "etf", "symbols": ["SPY", "QQQ", "IWM", "DIA"],
     "template": "reversal", "lineage": "reversal",
     "mechanism": "Index ETF reversal: buy SPY, QQQ, IWM or DIA at the open after a close at least theta below its "
                  "prior close, and sell it at the open h sessions later (MARKET BETA).",
     "prior": _REVERSAL_PRIOR, "provenance": _REVERSAL_PROVENANCE,
     "rule": "Buy a symbol at the next open after a close at least theta below its prior close; sell it at the open h "
             "sessions later.",
     "needs": {"symbols": ["SPY", "QQQ", "IWM", "DIA"], "history": 2, "max_hold_sessions": 10},
     "params": {"theta": 0.02, "h": 8, "share": 0.25},
     "card": {"lane": "beta", "structure": "etf", "symbols": ["SPY", "QQQ", "IWM", "DIA"],
              "hypothesis": "A sharp one-day fall in a broad index ETF is partly liquidity-driven selling that later "
                            "reverses: the buyer who supplies liquidity after the fall is paid over the next sessions "
                            "(Connors and Alvarez 2008).",
              "mechanism_class": "reversal_liquidity", "inputs": ["underlying_price"], "holding": "days_4_10",
              "cost": {"hurdle": 0.0003, "why": "a round trip pays two index-ETF half-spreads at the opens, and the SEC "
                                                "and TAF fees on the sale"},
              "comparison": _COMPARISON, "falsification": _FALSIFICATION}},
    {"id": "seed-overnight-spy", "lane": "beta", "structure": "etf", "symbols": ["SPY"], "template": "overnight",
     "lineage": "overnight",
     "mechanism": "SPY's return accrues overnight: hold SPY from each close to the next open, every session (MARKET BETA).",
     "prior": _OVERNIGHT_PRIOR, "provenance": _OVERNIGHT_PROVENANCE,
     "rule": "Buy SPY at the next close, every session; sell each lot at the following open.",
     "needs": {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}, "params": {"share": 0.5},
     "condition": "True",
     "card": {"lane": "beta", "structure": "etf", "symbols": ["SPY"],
              "hypothesis": "Most of the index's long-run return has accrued overnight, between the close and the next "
                            "open: holders who carry the overnight gap bear the news that arrives while the market is "
                            "shut and are paid for it (Cliff, Cooper and Gulen 2008; Lou, Polk and Skouras 2019).",
              "mechanism_class": "calendar_flow", "inputs": ["clock"], "holding": "days_1_3",
              "cost": {"hurdle": 0.0003, "why": "a round trip pays two SPY half-spreads at the close and the open, and "
                                                "the SEC and TAF fees on the sale"},
              "comparison": _COMPARISON, "falsification": _FALSIFICATION}},
]


def equity_program_for(spec: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """(the seed program's source, {}) for an `EQUITY_SEEDS` spec: its defaults are the source's PARAMS (theta and h for
    the reversal seed), the overrides dict empty, as `program_for`'s. The source passes the Gym's safety check
    (`league.gym.safety.check_program`, which league/equity/program.py uses unchanged)."""
    # The prior's authors in the comment, without their years: a program carries no year, even in a comment.
    prior = re.sub(r"\s+(?:19|20)\d\d\b", "", str(spec["prior"]))
    common = {"fid": spec["id"], "prior": prior, "rule": spec["rule"], "needs": repr(dict(spec["needs"])),
              "params": repr(dict(spec["params"]))}
    if spec.get("template") == "reversal":
        return EQUITY_REVERSAL.format(**common, written=_REVERSAL_WRITTEN), {}
    return EQUITY_OVERNIGHT.format(**common, written=_OVERNIGHT_WRITTEN, symbol=spec["symbols"][0],
                                   condition=spec["condition"]), {}


def equity_family_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """The family's record (what the store keeps) from an `EQUITY_SEEDS` spec: its lane, structure and symbols (the
    store's roots), its prior, where it came from (`provenance`, stated as it is), and `seeded` (the Done meter reads
    the three seeds apart, A8.12)."""
    return {"id": spec["id"], "mechanism": spec["mechanism"], "structure": spec["structure"], "roots": list(spec["symbols"]),
            "symbols": list(spec["symbols"]), "lane": spec["lane"], "seeded": True, "template": spec["template"],
            "prior": spec["prior"], "provenance": spec["provenance"], "rejection": _FALSIFICATION,
            "needs": dict(spec["needs"]), "params": dict(spec["params"])}


__all__ = ["SEEDS", "FOUNDERS", "LIBRARY", "program_for", "family_spec", "SIGNALS", "BUILDS", "EQUITY_SEEDS",
           "equity_program_for", "equity_family_spec"]

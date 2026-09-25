# options-diagonal: in a stock's trend, sell a 1-3 day option and own a 5-11 day one at a better strike (a diagonal).
#
# THE IDEA. An option loses its time value fastest in its last days. Short the near option `entry_delta` out of the
# money in the trend's direction and own a later one at least `width` nearer the money: the near leg's decay pays
# for the far leg, and a move with the trend lifts the far leg more than the near. The loss is capped at the debit
# as long as it is closed before the near leg's expiry, which the founder always does.
# THE EVIDENCE. Published: theta is steepest near expiry (Black-Scholes); short-dated index and stock options
# carry the richest variance premium (Bakshi and Kapadia 2003). Not measured by this firm. On SPY and QQQ a
# diagonal costs more than the $75 cap, so this trades stocks of $12-60 with weekly options.
# WHAT IT NEEDS. Daily bars (40) and quotes of six stocks, the chain within 11 days, `structures: True`.
# WHEN IT TRADES. From `entry_start` (10:00 New York) to `entry_end` (14:00), once a stock a day, at most
# `max_open` at once, with the near leg `near_dte_min`-`near_dte_max` days out and the far leg `dte_min`-`dte_max`.
# HOW IT EXITS. At `profit_target` of its debit, at `stop_loss` of the debit, when the price crosses the trend's
# mean against it, and `exit_minutes_before_close` before the close `exit_dte` days before the near expiry (the
# House closes it from 15:30 on that day). PARAMS: `trend_days`, `slope_days`, `both_sides`, `width`, `notional_usd`.

import json, math, re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HOLIDAYS = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05"}
OCC, CREDIT = r"[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}", ("credit_vertical", "iron_condor", "iron_butterfly")

def _num(value, default=0.0):
    try:
        return float(value) if math.isfinite(float(value)) else default
    except (TypeError, ValueError):
        return default
def _ny(text):
    try:
        moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
        return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return None
def _dte(expiry, ny):
    try:
        return (datetime.strptime(str(expiry)[:10], "%Y-%m-%d").date() - ny.date()).days
    except Exception:
        return None
def _occs(row):  # the contracts a position or an order names, however the row spells them
    return sorted(set(re.findall(OCC, json.dumps([row.get("legs"), row.get("market_id"), row.get("occ")], default=str))))
def _parts(occ):  # (underlying, expiry, right, strike)
    return occ[:-15], f"20{occ[-15:-13]}-{occ[-13:-11]}-{occ[-11:-9]}", "call" if occ[-9] == "C" else "put", int(occ[-8:]) / 1000.0
def _closes(ctx, under):  # closed bars' closes, oldest first
    return [c for c in (_num(b.get("c"), None) for b in (ctx.get("bars") or {}).get(under) or [] if isinstance(b, dict)) if c is not None and c > 0]
def _price(ctx, under):  # the underlying's mid now, else the chain's spot
    q, spots = (ctx.get("quotes") or {}).get(under) or {}, [_num(r.get("underlying_price")) for r in ctx.get("chain") or [] if isinstance(r, dict) and r.get("underlying") == under]
    return (_num(q.get("bid")) + _num(q.get("ask"))) / 2.0 if 0 < _num(q.get("bid")) <= _num(q.get("ask")) else max(spots + [0.0])
def _setup(ctx):  # PARAMS with this agent's mutations, New York's time, memory, and whether the session is shut
    p = {k: (str(v) if k == "structure" else _num(v, PARAMS[k])) for k, v in {**PARAMS, **(ctx.get("params") or {})}.items() if k in PARAMS}
    ny, memory = _ny(ctx.get("now")), ctx.get("memory") if isinstance(ctx.get("memory"), dict) else {}
    return p, ny, memory, ny is None or ny.weekday() >= 5 or ny.strftime("%Y-%m-%d") in HOLIDAYS or not 570 <= ny.hour * 60 + ny.minute < 960
def _vertical(ctx, under, bullish, kind, p, ny, budget):
    # The strike nearest entry_delta and the one `width` further out of the money, one expiry in [dte_min, dte_max]:
    # a debit vertical buys the near strike (calls when bullish), a credit vertical sells it (puts when bullish).
    credit = kind == "credit_vertical"
    right = ("put" if bullish else "call") if credit else ("call" if bullish else "put")
    rows = [r for r in ctx.get("chain") or [] if isinstance(r, dict) and r.get("underlying") == under and r.get("right") == right]
    index, best = {(r.get("expiry"), round(_num(r.get("strike")), 2)): r for r in rows}, None
    for near in rows:
        dte, delta = _dte(near.get("expiry"), ny), _num(near.get("delta"), None)
        far = index.get((near.get("expiry"), round(_num(near.get("strike")) + (p["width"] if right == "call" else -p["width"]), 2)))
        miss = 1.0 if delta is None else abs(abs(delta) - p["entry_delta"])  # never a lottery ticket in place of the bet asked for
        if far is None or dte is None or miss > 0.15 or not p["dte_min"] <= dte <= p["dte_max"] or (dte == 0 and ny.hour * 60 + ny.minute >= 840):
            continue
        nb, na, fb, fa = _num(near.get("bid")), _num(near.get("ask")), _num(far.get("bid")), _num(far.get("ask"))
        price = round(nb - fa - p["slip"], 2) if credit else round(na - fb + p["slip"], 2)
        risk = round(p["width"] - price, 2) if credit else price
        if not (0 < nb <= na and 0 < fb <= fa) or not 0 < risk * 100 <= budget or (
                price < p["min_credit"] * p["width"] if credit else not 0.05 <= price <= p["max_debit"] * p["width"]):
            continue
        if best is None or (round(miss / 0.05), dte, miss) < best[0]:  # the nearest expiry with a strike near entry_delta
            best = ((round(miss / 0.05), dte, miss), {"structure": kind, "price": price, "risk": risk, "right": right, "strike": _num(near.get("strike")),
                    "delta": delta, "dte": dte, "legs": [{"occ": near.get("occ") or near.get("symbol"), "role": "short" if credit else "long"},
                                                         {"occ": far.get("occ") or far.get("symbol"), "role": "long" if credit else "short"}]})
    return best[1] if best else None
def _exits(ctx, ny, p, notes, signal_exit):
    # Stale orders are cancelled; a held structure is closed at its time, its target, its stop, or its signal.
    intents, cancels, resting, mins = [], [], set(), ny.hour * 60 + ny.minute
    for order in [o for o in ctx.get("open_orders") or [] if isinstance(o, dict) and o.get("order_id")]:
        if _ny(order.get("submitted_at")) is None or (ny - _ny(order.get("submitted_at"))).total_seconds() >= p["requote_minutes"] * 60:
            cancels.append(str(order["order_id"]))
        elif order.get("side") == "sell" or order.get("action") == "close":
            resting.add(tuple(_occs(order)))
    for row in [r for r in ctx.get("positions") or [] if isinstance(r, dict) and len(_occs(r)) >= 2 and _num(r.get("quantity")) >= 1]:
        occs = _occs(row)
        kind, parts = str(row.get("structure") or str(row.get("market_id") or "").split("|")[0]), [_parts(c) for c in occs]
        width, credit, paid, mark = max(x[3] for x in parts) - min(x[3] for x in parts), kind in CREDIT, _num(row.get("average_cost")), _num(row.get("mark"))
        dte, gain = min(_dte(x[1], ny) for x in parts), mark - paid
        room = width - paid if kind in ("debit_vertical", "credit_vertical") else paid  # the most it can make (a diagonal: its debit)
        unit = width - paid if credit else paid  # the stop's unit: the credit taken, or the debit paid
        why = (f"{dte} days to its first expiry at {mins // 60:02d}:{mins % 60:02d} New York: out before the close"
               if dte <= p["exit_dte"] and mins >= min(960 - p["exit_minutes_before_close"], 915 if dte <= 0 else 960)
               else f"up {gain:.2f} a share, the target is {p['profit_target']:.0%} of the {room:.2f} it can make" if room > 0 and gain >= p["profit_target"] * room
               else f"down {-gain:.2f} a share, the stop is {p['stop_loss']:.0%} of {unit:.2f}" if unit > 0 and -gain >= p["stop_loss"] * unit
               else signal_exit(row, kind, occs, dte))
        if tuple(occs) in resting or not why:
            notes.append(f"{parts[0][0]} {kind}: {'selling' if why else 'holding'} at {gain:+.2f} a share")
            continue
        natural = round(max(0.01, mark if "target" in why else mark - p["slip"]), 2)
        natural = round(max(0.01, min(width - 0.01, width - natural)), 2) if credit else natural  # a credit close names the most to pay
        legs = [{"occ": g["occ"], "role": g["role"]} for g in row.get("legs") or [] if isinstance(g, dict) and g.get("occ") and g.get("role") in ("long", "short")]
        legs = legs or [{"occ": c, "role": "long" if s == "+" else "short"} for s, c in re.findall(r"([+-])[12](" + OCC + ")", str(row.get("market_id") or ""))]
        intents.append({"structure": kind, "action": "close", "quantity": int(_num(row.get("quantity"))), "type": "limit", "limit_price": natural,
                        "legs": legs, "reason": f"Closing the {parts[0][0]} {kind} at {natural:.2f} a share or better: {why}."})
        notes.append(f"{parts[0][0]} {kind}: closing, {why}")
    return intents, cancels
def _enter(ctx, p, ny, notes, cancels, done, signal, build):
    # One structure an underlying: `signal(under)` is a note, or (bullish, why, structure, event); `build` finds the structure.
    held = [r for r in ctx.get("positions") or [] if isinstance(r, dict) and len(_occs(r)) >= 2]
    buys = [o for o in ctx.get("open_orders") or [] if isinstance(o, dict) and o.get("side") != "sell" and o.get("action") != "close" and str(o.get("order_id")) not in cancels]
    used = sum(_num(r.get(k)) * 100 * _num(r.get("quantity")) for r, k in [(r, "average_cost") for r in held] + [(o, "limit_price") for o in buys])
    limits, slots, busy, intents = ctx.get("limits") or {}, int(p["max_open"]) - len(held) - len(buys), {_parts(_occs(r)[0])[0] for r in held + buys if _occs(r)}, []
    budget = min(p["notional_usd"], _num(limits.get("max_order_usd")), _num(limits.get("max_position_usd")) - used, _num(ctx.get("cash")) * 0.95)
    for under in NEEDS["symbols"]:
        view = "holding one" if under in busy else "no room: max_open held" if slots <= 0 else signal(under)
        v = None if isinstance(view, str) or done.get(under) == view[3] else build(ctx, under, view[0], view[2], p, ny, budget)
        if v is None:
            notes.append(f"{under}: " + (view if isinstance(view, str) else f"{view[1]}, but traded already" if done.get(under) == view[3] else f"{view[1]}, but no {view[2]} fits"))
            continue
        qty = max(1, min(int(p["max_qty"]), int(budget // (v["risk"] * 100))))
        intents.append({"structure": v["structure"], "action": "open", "quantity": qty, "type": "limit", "limit_price": v["price"], "legs": v["legs"],
                        "reason": f"{view[1]}: a {v['dte']}-day {v['right']} {v['structure']} at {v['price']:.2f} ({v['strike']:g} strike, delta "
                                  f"{v['delta']:+.2f}); it can lose ${v['risk'] * 100 * qty:.0f}."})
        notes.append(f"{under}: {view[1]}; sending {v['price']:.2f}")
        done[under], slots, budget = view[3], slots - 1, budget - v["risk"] * 100 * qty
    return intents

NEEDS = {"venue": "alpaca", "horizon": "day", "style": "options-diagonal", "asset_class": "option", "structures": True,
         "symbols": ["BAC", "SOFI", "F", "T", "PFE", "AAL"], "bars": {"timeframe": "1Day", "limit": 40}, "max_days_to_expiry": 11, "wake_minutes": 10,
         "parameter_rules": {"bounds": {"width": [0.5, 5], "dte_min": [3, 11], "dte_max": [3, 11], "near_dte_min": [1, 4], "near_dte_max": [1, 4],
                                        "entry_delta": [0.15, 0.5], "profit_target": [0.2, 2.0], "stop_loss": [0.2, 1.0], "exit_minutes_before_close": [30, 240],
                                        "exit_dte": [0, 3], "max_open": [1, 3], "max_qty": [1, 3], "notional_usd": [20, 75], "slip": [0, 0.05],
                                        "trend_days": [10, 30], "slope_days": [1, 10], "both_sides": [0, 1]},
                             "ordered": [["dte_min", "dte_max"], ["near_dte_min", "near_dte_max"]]}}
PARAMS = {"structure": "diagonal", "width": 0.5, "dte_min": 5, "dte_max": 11, "near_dte_min": 1, "near_dte_max": 3, "entry_delta": 0.3,
          "profit_target": 0.4, "stop_loss": 0.5, "exit_minutes_before_close": 120, "exit_dte": 0, "max_open": 2, "max_qty": 1, "notional_usd": 60.0,
          "slip": 0.01, "requote_minutes": 30, "trend_days": 20, "slope_days": 5, "both_sides": 1, "entry_start": 600, "entry_end": 840}

def _diagonal(ctx, under, bullish, kind, p, ny, budget):
    # Short the near leg nearest entry_delta; long the far leg at the strike at least `width` more favourable (the nearest such).
    right = "call" if bullish else "put"
    rows = [r for r in ctx.get("chain") or [] if isinstance(r, dict) and r.get("underlying") == under and r.get("right") == right and _dte(r.get("expiry"), ny) is not None]
    best = None
    for near in [r for r in rows if p["near_dte_min"] <= _dte(r.get("expiry"), ny) <= p["near_dte_max"] and _num(r.get("delta"), None) is not None]:
        miss, k = abs(abs(_num(near["delta"])) - p["entry_delta"]), _num(near.get("strike"))
        fars = [r for r in rows if p["dte_min"] <= _dte(r.get("expiry"), ny) <= p["dte_max"] and str(r.get("expiry")) > str(near.get("expiry"))
                and ((_num(r.get("strike")) <= k - p["width"] + 1e-9) if bullish else (_num(r.get("strike")) >= k + p["width"] - 1e-9))]
        far = max(fars, key=lambda r: (-_dte(r.get("expiry"), ny), _num(r.get("strike")) if bullish else -_num(r.get("strike"))), default=None)
        nb, fb, fa = _num(near.get("bid")), _num((far or {}).get("bid")), _num((far or {}).get("ask"))
        price = round(fa - nb + p["slip"], 2)
        if far is None or miss > 0.15 or not (0 < nb <= _num(near.get("ask")) and 0 < fb <= fa) or not (0.05 <= price and price * 100 <= budget):
            continue
        if best is None or (round(miss / 0.05), _dte(near.get("expiry"), ny), miss) < best[0]:
            best = ((round(miss / 0.05), _dte(near.get("expiry"), ny), miss), {"structure": "diagonal", "price": price, "risk": price, "right": right,
                    "strike": k, "delta": _num(near["delta"]), "dte": _dte(near.get("expiry"), ny),
                    "legs": [{"occ": far.get("occ") or far.get("symbol"), "role": "long"}, {"occ": near.get("occ") or near.get("symbol"), "role": "short"}]})
    return best[1] if best else None

def _trend(ctx, under, p):  # (price now, the trend's mean, its slope) or None
    closes, n, k = _closes(ctx, under), int(p["trend_days"]), int(p["slope_days"])
    if len(closes) < n + k or _price(ctx, under) <= 0:
        return None
    return _price(ctx, under), sum(closes[-n:]) / n, sum(closes[-n:]) / n - sum(closes[-n - k:-k]) / n

def decide(ctx):
    p, ny, memory, shut = _setup(ctx)
    if shut:
        return {"intents": [], "cancels": [], "thought": "Options diagonal: the market is shut.", "memory": memory}
    day, notes = ny.date().toordinal(), []

    def against(row, held_kind, occs, dte):  # the trend turned against it
        found, bull = _trend(ctx, _parts(occs[0])[0], p), _parts(occs[0])[2] == "call"
        return f"the price {found[0]:.2f} crossed the {int(p['trend_days'])}-day mean {found[1]:.2f} against it" if found and (found[0] < found[1] if bull else found[0] > found[1]) else None

    def signal(under):
        found = _trend(ctx, under, p)
        if found is None:
            return f"fewer than {int(p['trend_days'] + p['slope_days'])} daily bars"
        price, mean, slope = found
        bull = True if price > mean and slope > 0 else False if p["both_sides"] >= 1 and price < mean and slope < 0 else None
        return (f"{price:.2f} against a {int(p['trend_days'])}-day mean {mean:.2f} ({slope:+.2f}): no trend" if bull is None else
                (bull, f"{under} {price:.2f} is {'above a rising' if bull else 'below a falling'} {int(p['trend_days'])}-day mean {mean:.2f}", "diagonal", day))

    intents, cancels = _exits(ctx, ny, p, notes, against)
    done = {k: v for k, v in (memory.get("done") or {}).items() if v == day} if isinstance(memory.get("done"), dict) else {}
    if p["entry_start"] <= ny.hour * 60 + ny.minute < p["entry_end"]:
        intents += _enter(ctx, p, ny, notes, cancels, done, signal, _diagonal)
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options diagonal. " + ("; ".join(notes) or "nothing to do") + ".", "memory": {"done": done}}

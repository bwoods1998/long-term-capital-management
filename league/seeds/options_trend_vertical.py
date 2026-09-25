# options-trend-vertical: buy the pullback in a 20-day trend with a 4-11 day debit vertical on SPY, QQQ or IWM.
#
# THE IDEA. An index ETF above a rising 20-day mean that closed yesterday under its 5-day mean has pulled back
# inside its trend; trends in index ETFs tend to resume within days. A $1 debit vertical with the trend (calls
# up, puts in the mirror image) risks its debit to make the rest of its width, and takes `profit_target` of it.
# THE EVIDENCE. Published: time-series momentum (Moskowitz, Ooi and Pedersen 2012) and short-term pullbacks in
# uptrends (Connors' RSI(2) on index ETFs). SPY ranged 725-776 from May to September 2026 (this firm's options
# history), so the trend filter must earn its keep. The replay fills conservatively; entries pay four fills.
# WHAT IT NEEDS. Daily bars (60) of the three ETFs, their quotes, the chain within 11 days, `structures: True`.
# WHEN IT TRADES. From `entry_start` (10:00 New York) to `entry_end` (15:00), once an underlying a day, at most
# `max_open` structures, never on an expiry day after 14:00. A limit at the natural net debit plus `slip`.
# HOW IT EXITS. At `profit_target` of its width less the debit, at `stop_loss` of the debit, when the price
# crosses the 20-day mean against it, after `max_hold_days`, and on its expiry day `exit_minutes_before_close`
# before the close. PARAMS: `structure` debit_vertical or credit_vertical (the view as a put or call credit
# spread), `width` dollars, `dte_min`-`dte_max` days, `trend_days`, `slope_days`, `fast`, `both_sides` (1 trades
# downtrends with puts too), `notional_usd` the most one structure may lose.

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

NEEDS = {"venue": "alpaca", "horizon": "day", "style": "options-trend-vertical", "asset_class": "option", "structures": True,
         "symbols": ["SPY", "QQQ", "IWM"], "bars": {"timeframe": "1Day", "limit": 60}, "max_days_to_expiry": 11, "wake_minutes": 10,
         "parameter_rules": {"bounds": {"width": [1, 5], "dte_min": [1, 11], "dte_max": [1, 11], "entry_delta": [0.2, 0.6], "profit_target": [0.2, 0.95],
                                        "stop_loss": [0.2, 1.0], "exit_minutes_before_close": [30, 240], "exit_dte": [0, 5], "max_open": [1, 3],
                                        "max_qty": [1, 3], "notional_usd": [20, 75], "slip": [0, 0.05], "max_debit": [0.3, 0.8], "min_credit": [0.1, 0.5],
                                        "trend_days": [10, 50], "slope_days": [1, 10], "fast": [2, 10], "max_hold_days": [1, 10], "both_sides": [0, 1]},
                             "ordered": [["dte_min", "dte_max"], ["fast", "trend_days"]]}}
PARAMS = {"structure": "debit_vertical", "width": 1.0, "dte_min": 4, "dte_max": 11, "entry_delta": 0.45, "profit_target": 0.6, "stop_loss": 0.5,
          "exit_minutes_before_close": 60, "exit_dte": 0, "max_open": 2, "max_qty": 1, "notional_usd": 70.0, "slip": 0.01, "max_debit": 0.65,
          "min_credit": 0.3, "requote_minutes": 30, "trend_days": 20, "slope_days": 5, "fast": 5, "max_hold_days": 4, "both_sides": 1,
          "entry_start": 600, "entry_end": 900}

def _trend(ctx, under, p):  # (price now, the 20-day mean, its slope, yesterday's close against the 5-day mean) or None
    closes, n, k, f = _closes(ctx, under), int(p["trend_days"]), int(p["slope_days"]), int(p["fast"])
    if len(closes) < n + k or _price(ctx, under) <= 0:
        return None
    mean = sum(closes[-n:]) / n
    return _price(ctx, under), mean, mean - sum(closes[-n - k:-k]) / n, closes[-1] - sum(closes[-f:]) / f

def decide(ctx):
    p, ny, memory, shut = _setup(ctx)
    if shut:
        return {"intents": [], "cancels": [], "thought": "Options trend vertical: the market is shut.", "memory": memory}
    day, notes, kind = ny.strftime("%Y-%m-%d"), [], "credit_vertical" if p["structure"] == "credit_vertical" else "debit_vertical"

    def broken(row, held_kind, occs, dte):  # the trend turned against it, or it has been held long enough
        found, bull, opened = _trend(ctx, _parts(occs[0])[0], p), (_parts(occs[0])[2] == "call") != (held_kind in CREDIT), _ny(row.get("opened_at"))
        if found and (found[0] < found[1] if bull else found[0] > found[1]):
            return f"the price {found[0]:.2f} crossed the {int(p['trend_days'])}-day mean {found[1]:.2f} against it"
        return f"held {(ny.date() - opened.date()).days} days, the most is {int(p['max_hold_days'])}" if opened and (ny.date() - opened.date()).days >= p["max_hold_days"] else None

    def signal(under):
        found = _trend(ctx, under, p)
        if found is None:
            return f"fewer than {int(p['trend_days'] + p['slope_days'])} daily bars"
        price, mean, slope, pulled = found
        bull = True if price > mean and slope > 0 and pulled < 0 else False if p["both_sides"] >= 1 and price < mean and slope < 0 and pulled > 0 else None
        return (f"{price:.2f} against a {int(p['trend_days'])}-day mean {mean:.2f} ({slope:+.2f}): no pullback inside a trend" if bull is None else
                (bull, f"{under} {price:.2f} is {'above a rising' if bull else 'below a falling'} {int(p['trend_days'])}-day mean {mean:.2f} and closed "
                       f"{'under' if bull else 'over'} its {int(p['fast'])}-day mean yesterday", kind, day))

    intents, cancels = _exits(ctx, ny, p, notes, broken)
    done = {k: v for k, v in (memory.get("done") or {}).items() if v == day} if isinstance(memory.get("done"), dict) else {}
    if p["entry_start"] <= ny.hour * 60 + ny.minute < p["entry_end"]:
        intents += _enter(ctx, p, ny, notes, cancels, done, signal, _vertical)
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options trend vertical. " + ("; ".join(notes) or "nothing to do") + ".", "memory": {"done": done}}

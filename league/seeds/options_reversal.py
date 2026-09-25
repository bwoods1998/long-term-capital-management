# options-reversal: fade a two-sigma day on SPY, QQQ or IWM with a 2-7 day debit vertical against the move.
#
# THE IDEA. A day that moves an index ETF two standard deviations of its last 20 daily moves is mostly
# liquidity demand (forced sellers, short covering), and index ETFs give back part of it within days. At the end
# of that day (or the next morning) buy a $1 debit vertical against the move: calls after a plunge, puts after a
# spike (`fade_up`), risking the debit to make most of the width.
# THE EVIDENCE. Published: short-term reversal in index and ETF returns after extreme days (Connors and Alvarez;
# Nagel 2012, "Evaporating liquidity"). Measured here: SPY's 11 moves over 1.5 sigma from May 14 to September 23,
# 2026 were followed by a move against them the next day 6 times out of 9 on the upside. Thin; replay judges it.
# WHAT IT NEEDS. Daily bars (40) and quotes of the three ETFs, the chain within 7 days, `structures: True`.
# WHEN IT TRADES. Today's move from `entry_start` (14:30 New York) to `entry_end` (15:30), or yesterday's move
# from 10:00 to 11:00, once an event. At most `max_open` at once; never on an expiry day after 14:00.
# HOW IT EXITS. At `profit_target` of what it can make, at `stop_loss` of the debit, when the move has fully
# reversed (the price back beyond the close before it), after `max_hold_days`, and on its expiry day
# `exit_minutes_before_close` before the close. PARAMS: `z_entry` sigmas, `lookback` days, `fade_up` (1 fades
# spikes too), `structure` debit_vertical or credit_vertical, `width`, `dte_min`-`dte_max`, `notional_usd`.

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
    # One expiry in [dte_min, dte_max]: the strike nearest entry_delta, and further out of the money (at most `width` away) the one
    # nearest wing_delta. A debit vertical buys the first (calls when bullish), a credit vertical sells it (puts when bullish).
    credit = kind == "credit_vertical"
    right = ("put" if bullish else "call") if credit else ("call" if bullish else "put")
    out = 1.0 if right == "call" else -1.0
    rows = [r for r in ctx.get("chain") or [] if isinstance(r, dict) and r.get("underlying") == under and r.get("right") == right and _num(r.get("delta"), None) is not None]
    best = None
    for near in rows:
        dte, miss, k = _dte(near.get("expiry"), ny), abs(abs(_num(near.get("delta"))) - p["entry_delta"]), _num(near.get("strike"))
        if dte is None or miss > 0.1 or not p["dte_min"] <= dte <= p["dte_max"] or (dte == 0 and ny.hour * 60 + ny.minute >= 840):
            continue  # never a lottery ticket in place of the bet asked for, nor a structure the House would refuse
        for far in [r for r in rows if r.get("expiry") == near.get("expiry") and 0 < (_num(r.get("strike")) - k) * out <= p["width"] + 1e-9]:
            nb, na, fb, fa, width = _num(near.get("bid")), _num(near.get("ask")), _num(far.get("bid")), _num(far.get("ask")), abs(_num(far.get("strike")) - k)
            price = round(nb - fa - p["slip"], 2) if credit else round(na - fb + p["slip"], 2)
            risk = round(width - price, 2) if credit else price
            if not (0 < nb <= na and 0 < fb <= fa) or not 0 < risk * 100 <= budget or (
                    price < p["min_credit"] * width if credit else not 0.05 <= price <= p["max_debit"] * width):
                continue
            score = (round(miss / 0.05), dte, abs(abs(_num(far.get("delta"))) - p["wing_delta"]), miss)
            if best is None or score < best[0]:  # the nearest expiry with a strike near entry_delta, its wing nearest wing_delta
                best = (score, {"structure": kind, "price": price, "risk": risk, "right": right, "strike": k, "delta": _num(near.get("delta")), "dte": dte,
                                "legs": [{"occ": near.get("occ") or near.get("symbol"), "role": "short" if credit else "long"},
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
        # A target is taken at the bid less `slip`; a stop or a signal gives up to half the mark; the clock takes whatever the bid is.
        natural = round(max(0.01, mark - p["slip"] if "target" in why else mark * 0.5 if "first expiry" not in why else 0.01), 2)
        natural = round(max(0.01, min(width - 0.01, width - natural)), 2) if credit else natural  # a credit close names the most to pay
        legs = [{"occ": g["occ"], "role": g["role"]} for g in row.get("legs") or [] if isinstance(g, dict) and g.get("occ") and g.get("role") in ("long", "short")]
        legs = legs or [{"occ": c, "role": "long" if s == "+" else "short"} for s, c in re.findall(r"([+-])[12](" + OCC + ")", str(row.get("market_id") or ""))]
        intents.append({"structure": kind, "action": "close", "quantity": int(_num(row.get("quantity"))), "type": "limit", "limit_price": natural,
                        "legs": legs, "reason": f"Closing the {parts[0][0]} {kind} at {natural:.2f} a share or better: {why}."})
        notes.append(f"{parts[0][0]} {kind}: closing, {why}")
    return intents, cancels
def _enter(ctx, p, ny, notes, cancels, memory, signal, build):
    # One structure an underlying an event: `signal(under)` is a note, or (bullish, why, structure, event); `build` finds the structure.
    # An event is spent once a structure sent for it is seen held; an entry that did not fill is sent again while the signal stands.
    held = [r for r in ctx.get("positions") or [] if isinstance(r, dict) and len(_occs(r)) >= 2]
    buys = [o for o in ctx.get("open_orders") or [] if isinstance(o, dict) and o.get("side") != "sell" and o.get("action") != "close" and str(o.get("order_id")) not in cancels]
    used = sum(_num(r.get(k)) * 100 * _num(r.get("quantity")) for r, k in [(r, "average_cost") for r in held] + [(o, "limit_price") for o in buys])
    limits, slots, busy, intents = ctx.get("limits") or {}, int(p["max_open"]) - len(held) - len(buys), {_parts(_occs(r)[0])[0] for r in held + buys if _occs(r)}, []
    budget = min(p["notional_usd"], _num(limits.get("max_order_usd")), _num(limits.get("max_position_usd")) - used, _num(ctx.get("cash")) * 0.95)
    sent, done = [m if isinstance(m, dict) else {} for m in (memory.get("sent"), memory.get("done"))]
    done.update({u: sent[u] for u in busy if u in sent and u not in {_parts(_occs(o)[0])[0] for o in buys if _occs(o)}})
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
        sent[under], slots, budget = view[3], slots - 1, budget - v["risk"] * 100 * qty
    keep = set(NEEDS["symbols"])
    return intents, {"sent": {k: v for k, v in sent.items() if k in keep}, "done": {k: v for k, v in done.items() if k in keep}}

NEEDS = {"venue": "alpaca", "horizon": "day", "style": "options-reversal", "asset_class": "option", "structures": True,
         "symbols": ["SPY", "QQQ", "IWM"], "bars": {"timeframe": "1Day", "limit": 40}, "max_days_to_expiry": 7, "wake_minutes": 10,
         "parameter_rules": {"bounds": {"width": [1, 20], "dte_min": [1, 7], "dte_max": [1, 7], "wing_delta": [0.02, 0.3], "entry_delta": [0.2, 0.6], "profit_target": [0.2, 0.95],
                                        "stop_loss": [0.2, 1.0], "exit_minutes_before_close": [30, 240], "exit_dte": [0, 5], "max_open": [1, 3],
                                        "max_qty": [1, 3], "notional_usd": [20, 75], "slip": [0, 0.05], "max_debit": [0.3, 0.8], "min_credit": [0.1, 0.5],
                                        "z_entry": [1.0, 3.5], "lookback": [10, 30], "fade_up": [0, 1], "max_hold_days": [1, 7]},
                             "ordered": [["dte_min", "dte_max"]]}}
PARAMS = {"structure": "debit_vertical", "width": 10.0, "dte_min": 2, "dte_max": 7, "wing_delta": 0.08, "entry_delta": 0.3, "profit_target": 0.5, "stop_loss": 0.6,
          "exit_minutes_before_close": 60, "exit_dte": 0, "max_open": 2, "max_qty": 1, "notional_usd": 70.0, "slip": 0.02, "max_debit": 0.65,
          "min_credit": 0.3, "requote_minutes": 30, "z_entry": 1.8, "lookback": 20, "fade_up": 1, "max_hold_days": 3, "entry_start": 870, "entry_end": 930}

def _event(ctx, under, p, ny, late):
    # (z of the move, the close before it, the event's day): today's move so far late in the day, else yesterday's.
    closes, n = _closes(ctx, under), int(p["lookback"])
    if len(closes) < n + 2 or _price(ctx, under) <= 0:
        return None
    moves = [closes[i] / closes[i - 1] - 1.0 for i in range(len(closes) - n, len(closes))]
    sd = math.sqrt(sum(m * m for m in moves) / n) or 1.0
    bars = [b for b in (ctx.get("bars") or {}).get(under) or [] if isinstance(b, dict) and _num(b.get("c")) > 0]
    stamp = _ny(bars[-1].get("t")) if bars else None  # a daily bar is stamped at the midnight after its session: the event is its session's
    return ((_price(ctx, under) / closes[-1] - 1.0) / sd, closes[-1], ny.date().toordinal()) if late else (
        (closes[-1] / closes[-2] - 1.0) / sd, closes[-2], (stamp.date().toordinal() - (1 if stamp.hour < 6 else 0)) if stamp else 0)

def decide(ctx):
    p, ny, memory, shut = _setup(ctx)
    if shut:
        return {"intents": [], "cancels": [], "thought": "Options reversal: the market is shut.", "memory": memory}
    notes, mins, kind = [], ny.hour * 60 + ny.minute, "credit_vertical" if p["structure"] == "credit_vertical" else "debit_vertical"
    late = p["entry_start"] <= mins < p["entry_end"]
    events = memory.get("events") if isinstance(memory.get("events"), dict) else {}

    def reverted(row, held_kind, occs, dte):  # fully reversed, or held long enough
        under, bull, opened = _parts(occs[0])[0], (_parts(occs[0])[2] == "call") != (held_kind in CREDIT), _ny(row.get("opened_at"))
        before, price = _num(events.get(under), 0.0), _price(ctx, under)
        if before > 0 and price > 0 and (price >= before if bull else price <= before):
            return f"the move has reversed: {price:.2f} is back {'over' if bull else 'under'} the close before it, {before:.2f}"
        return f"held {(ny.date() - opened.date()).days} days, the most is {int(p['max_hold_days'])}" if opened and (ny.date() - opened.date()).days >= p["max_hold_days"] else None

    def signal(under):
        found = _event(ctx, under, p, ny, late)
        if found is None:
            return f"fewer than {int(p['lookback']) + 2} daily bars"
        z, before, when = found
        bull = True if z <= -p["z_entry"] else False if z >= p["z_entry"] and p["fade_up"] >= 1 else None
        if bull is not None:
            events[under] = before
        return (f"a {z:+.1f} sigma move, under the {p['z_entry']:.1f} to fade" if bull is None else
                (bull, f"{under} moved {z:+.1f} sigma {'today' if late else 'yesterday'} (from {before:.2f}): fading it", kind, when))

    intents, cancels = _exits(ctx, ny, p, notes, reverted)
    kept = {k: memory.get(k) if isinstance(memory.get(k), dict) else {} for k in ("sent", "done")}
    if late or 600 <= mins < 660:
        opened, kept = _enter(ctx, p, ny, notes, cancels, memory, signal, _vertical)
        intents += opened
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options reversal. " + ("; ".join(notes) or "nothing to do") + ".",
            "memory": {**kept, "events": {k: v for k, v in events.items() if k in NEEDS["symbols"]}}}

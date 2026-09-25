# options-orb: trade the opening range's breakout (or, as measured, fade it) with a 0-4 day debit vertical, flat by the close.
#
# THE IDEA. The first half hour sets a range. A 15-minute close outside it, beyond the day's open, is order flow;
# whether the rest of the day follows it or gives it back is the market's regime. `fade` 0 rides the breakout
# (calls up, puts down), `fade` 1 bets it fails; a near-the-money debit vertical caps the loss at the debit.
# THE EVIDENCE. Published: intraday momentum in SPY (Gao, Han, Li and Zhou, JFE 2018). Measured on this firm's
# history (15-minute bars, May 22 to Aug 11, 2026; breakout 10:00-13:00, out at 15:35): the breakout LOST on
# average, IWM -0.16% (42), BAC -0.23% (32), SOFI -0.37% (44), SNAP -0.14% (38), AAL -0.44% (45); SPY -0.01%
# (45). So the founder fades by default, on those five; the published momentum is one mutation (`fade` 0) away.
# WHAT IT NEEDS. 15-minute bars (60: two and a half sessions), the chain within 4 days, `structures: True`.
# WHEN IT TRADES. From `entry_start` (10:00 New York) to `entry_end` (13:00), once an underlying a day, at most
# `max_open` structures at once, never on an expiry day after 14:00. A limit at the natural net ask plus `slip`.
# HOW IT EXITS. At `profit_target` of what it can make, at `stop_loss` of the debit (1.0: none), when price is
# back at the range's middle (a fade's work done, or a breakout failed), and `exit_minutes_before_close` before
# the close, every day (by 15:15 on an expiry day). PARAMS: `range_bars`, `breakout_pct`, `fade`, `structure`.

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
        if dte is None or miss > 0.15 or not p["dte_min"] <= dte <= p["dte_max"] or (dte == 0 and ny.hour * 60 + ny.minute >= 840):
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
        if dte <= 0 and mins >= 930:  # from 15:30 on its expiry day the House is closing it: nothing to send
            notes.append(f"{parts[0][0]} {kind}: the House is closing it before its expiry")
            continue
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

NEEDS = {"venue": "alpaca", "horizon": "day", "style": "options-orb", "asset_class": "option", "structures": True,
         "symbols": ["IWM", "BAC", "SOFI", "SNAP", "AAL"], "bars": {"timeframe": "15Min", "limit": 60}, "max_days_to_expiry": 4, "wake_minutes": 5,
         "parameter_rules": {"bounds": {"width": [1, 20], "dte_min": [0, 4], "dte_max": [0, 4], "wing_delta": [0.02, 0.3], "entry_delta": [0.2, 0.6], "profit_target": [0.2, 0.95],
                                        "stop_loss": [0.2, 1.0], "exit_minutes_before_close": [15, 240], "exit_dte": [0, 99], "max_open": [1, 3],
                                        "max_qty": [1, 3], "notional_usd": [20, 75], "slip": [0, 0.05], "max_debit": [0.3, 0.8], "min_credit": [0.1, 0.5],
                                        "range_bars": [1, 4], "breakout_pct": [0, 0.01], "fade": [0, 1]}, "ordered": [["dte_min", "dte_max"]]}}
PARAMS = {"structure": "debit_vertical", "width": 1.0, "dte_min": 0, "dte_max": 4, "wing_delta": 0.25, "entry_delta": 0.5, "profit_target": 0.5, "stop_loss": 1.0,
          "exit_minutes_before_close": 25, "exit_dte": 99, "max_open": 2, "max_qty": 1, "notional_usd": 60.0, "slip": 0.02, "max_debit": 0.65,
          "min_credit": 0.3, "requote_minutes": 20, "range_bars": 2, "breakout_pct": 0.001, "fade": 1, "entry_start": 600, "entry_end": 780}

def _range(ctx, under, ny, n):
    # Today's closed 15-minute bars: the opening range (high, low), the day's open and the last close.
    stamps = [(_ny(b.get("t")), b) for b in (ctx.get("bars") or {}).get(under) or [] if isinstance(b, dict) and _num(b.get("c")) > 0]
    today = [b for t, b in stamps if t is not None and t.date() == ny.date() and t.hour * 60 + t.minute > 570]
    if len(today) <= n:
        return None
    return max(_num(b.get("h")) for b in today[:n]), min(_num(b.get("l")) for b in today[:n]), _num(today[0].get("o")), _num(today[-1].get("c"))

def decide(ctx):
    p, ny, memory, shut = _setup(ctx)
    if shut:
        return {"intents": [], "cancels": [], "thought": "Options ORB: the market is shut.", "memory": memory}
    day, notes, n, kind = ny.strftime("%Y-%m-%d"), [], int(p["range_bars"]), "credit_vertical" if p["structure"] == "credit_vertical" else "debit_vertical"

    def failed(row, held_kind, occs, dte):  # back through the range's middle: a failed breakout, or a fade that has done its work
        found, bull = _range(ctx, _parts(occs[0])[0], ny, n), (_parts(occs[0])[2] == "call") != (held_kind in CREDIT)
        middle = (found[0] + found[1]) / 2.0 if found else 0.0
        if not found or (found[3] < middle if bull else found[3] > middle) == (p["fade"] >= 1):
            return None
        return f"{found[3]:.2f} is back at the range's middle {middle:.2f}: " + ("the fade has done its work" if p["fade"] >= 1 else "the breakout failed")

    def signal(under):
        found = _range(ctx, under, ny, n)
        if found is None:
            return "the opening range is not set"
        high, low, opened, last = found
        bull = True if last > high * (1 + p["breakout_pct"]) and last > opened else False if last < low * (1 - p["breakout_pct"]) and last < opened else None
        return (f"{last:.2f} inside the range {low:.2f}-{high:.2f} or against the open {opened:.2f}" if bull is None else
                (bull != (p["fade"] >= 1), f"{under} {last:.2f} broke {'above' if bull else 'below'} its opening range {low:.2f}-{high:.2f}"
                 + (": fading it" if p["fade"] >= 1 else ""), kind, day))

    intents, cancels = _exits(ctx, ny, p, notes, failed)
    kept = {k: memory.get(k) if isinstance(memory.get(k), dict) else {} for k in ("sent", "done")}
    if p["entry_start"] <= ny.hour * 60 + ny.minute < p["entry_end"]:
        opened, kept = _enter(ctx, p, ny, notes, cancels, memory, signal, _vertical)
        intents += opened
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options ORB. " + ("; ".join(notes) or "nothing to do") + ".", "memory": kept}

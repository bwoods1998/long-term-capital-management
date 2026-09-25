# options-gap-drift: ride a stock's news move for days with a 3-10 day vertical in the move's direction.
#
# THE IDEA. When a stock moves two standard deviations of its daily moves on news (an earnings release, most
# often), the market under-reacts and the price keeps drifting the same way for days. Buy a near-the-money debit
# vertical with the move once the first 45 minutes have confirmed it, or the next morning if it has not reversed.
# THE EVIDENCE. Published: post-earnings-announcement drift (Ball and Brown 1968; Bernard and Thomas 1989).
# Measured on this firm's history (underlying closes): 3-day drift after a 2-sigma, 3% day, May 22 to Aug 11,
# 2026: BAC +0.46% (1), T +2.04% (5), F +11.5% (1), AAL +2.07% (6), RIVN +5.15% (4), CCL +0.56% (4); HOOD, SOFI
# and SNAP went the other way and are left out. EDGAR's 8-K Item 2.02 feed would name the earnings days, but the
# options replay tape carries no feeds (a founder declaring one cannot be replayed): the event is read from price.
# WHAT IT NEEDS. Daily bars (40) and quotes of six stocks, the chain within 10 days, `structures: True`.
# WHEN IT TRADES. From `entry_start` (10:15 New York) to `entry_end` (12:00), once an event, at most `max_open`.
# HOW IT EXITS. At `profit_target` of what it can make, at `stop_loss` of the debit (1.0: none), when the gap
# fills (the price back through the close before it), after `max_hold_days`, and on its expiry day
# `exit_minutes_before_close` before the close. PARAMS: `gap_z`, `min_gap_pct`, `lookback`, `structure`, `width`.

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

NEEDS = {"venue": "alpaca", "horizon": "day", "style": "options-gap-drift", "asset_class": "option", "structures": True,
         "symbols": ["BAC", "T", "F", "AAL", "RIVN", "CCL"], "bars": {"timeframe": "1Day", "limit": 40}, "max_days_to_expiry": 10,
         "wake_minutes": 10,
         "parameter_rules": {"bounds": {"width": [1, 20], "dte_min": [1, 10], "dte_max": [1, 10], "wing_delta": [0.02, 0.3], "entry_delta": [0.2, 0.6], "profit_target": [0.2, 0.95],
                                        "stop_loss": [0.2, 1.0], "exit_minutes_before_close": [30, 240], "exit_dte": [0, 5], "max_open": [1, 3],
                                        "max_qty": [1, 3], "notional_usd": [20, 75], "slip": [0, 0.05], "max_debit": [0.3, 0.8], "min_credit": [0.1, 0.5],
                                        "gap_z": [1.0, 4.0], "min_gap_pct": [0, 10], "lookback": [10, 30], "max_hold_days": [1, 10]},
                             "ordered": [["dte_min", "dte_max"]]}}
PARAMS = {"structure": "debit_vertical", "width": 1.0, "dte_min": 3, "dte_max": 10, "wing_delta": 0.25, "entry_delta": 0.5, "profit_target": 0.6, "stop_loss": 1.0,
          "exit_minutes_before_close": 60, "exit_dte": 0, "max_open": 2, "max_qty": 1, "notional_usd": 70.0, "slip": 0.02, "max_debit": 0.65,
          "min_credit": 0.3, "requote_minutes": 30, "gap_z": 2.0, "min_gap_pct": 3.0, "lookback": 20, "max_hold_days": 4, "entry_start": 615, "entry_end": 720}

def _event(ctx, under, p, ny):
    # (bullish, z, the close before the move, the move's session) for today's move, else yesterday's if today has not undone it.
    closes, n, price = _closes(ctx, under), int(p["lookback"]), _price(ctx, under)
    if len(closes) < n + 2 or price <= 0:
        return None
    moves = [closes[i] / closes[i - 1] - 1.0 for i in range(len(closes) - n - 1, len(closes) - 1)]
    sd = math.sqrt(sum(m * m for m in moves) / n) or 1.0
    bars = [b for b in (ctx.get("bars") or {}).get(under) or [] if isinstance(b, dict) and _num(b.get("c")) > 0]
    stamp = _ny(bars[-1].get("t")) if bars else None  # a daily bar is stamped at the midnight after its session
    for move, before, when in ((price / closes[-1] - 1.0, closes[-1], ny.date().toordinal()),
                               (closes[-1] / closes[-2] - 1.0, closes[-2], stamp.date().toordinal() - (1 if stamp.hour < 6 else 0) if stamp else 0)):
        if abs(move) >= max(p["gap_z"] * sd, p["min_gap_pct"] / 100.0) and (when == ny.date().toordinal() or (price - closes[-1]) * move >= 0):
            return move > 0, move / sd, before, when
    return None

def decide(ctx):
    p, ny, memory, shut = _setup(ctx)
    if shut:
        return {"intents": [], "cancels": [], "thought": "Options gap drift: the market is shut.", "memory": memory}
    notes, kind = [], "credit_vertical" if p["structure"] == "credit_vertical" else "debit_vertical"
    events = memory.get("events") if isinstance(memory.get("events"), dict) else {}

    def filled(row, held_kind, occs, dte):  # the gap filled, or held long enough
        under, bull, opened = _parts(occs[0])[0], (_parts(occs[0])[2] == "call") != (held_kind in CREDIT), _ny(row.get("opened_at"))
        before, price = _num(events.get(under), 0.0), _price(ctx, under)
        if before > 0 and price > 0 and (price <= before if bull else price >= before):
            return f"the gap filled: {price:.2f} is back through the close before it, {before:.2f}"
        return f"held {(ny.date() - opened.date()).days} days, the most is {int(p['max_hold_days'])}" if opened and (ny.date() - opened.date()).days >= p["max_hold_days"] else None

    def signal(under):
        found = _event(ctx, under, p, ny)
        if found is None:
            return f"no {p['gap_z']:.1f}-sigma move of {p['min_gap_pct']:.0f}% or more"
        events[under] = found[2]
        return (found[0], f"{under} moved {found[1]:+.1f} sigma from {found[2]:.2f}{' today' if found[3] == ny.date().toordinal() else ' yesterday'}: "
                          f"riding the drift", kind, found[3])

    intents, cancels = _exits(ctx, ny, p, notes, filled)
    kept = {k: memory.get(k) if isinstance(memory.get(k), dict) else {} for k in ("sent", "done")}
    if p["entry_start"] <= ny.hour * 60 + ny.minute < p["entry_end"]:
        opened, kept = _enter(ctx, p, ny, notes, cancels, memory, signal, _vertical)
        intents += opened
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options gap drift. " + ("; ".join(notes) or "nothing to do") + ".",
            "memory": {**kept, "events": {k: v for k, v in events.items() if k in NEEDS["symbols"]}}}

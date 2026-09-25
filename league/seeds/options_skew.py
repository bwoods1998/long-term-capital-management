# options-skew: sell rich put skew with a put credit vertical in an uptrend; buy cheap puts with a put debit vertical.
#
# THE IDEA. The 25-delta put's implied volatility over the 25-delta call's (the skew) is the price of crash
# insurance. When it is rich against its own recent level, puts are dear: sell a $1 put credit vertical under
# the market (in an uptrend only), which keeps the credit if the index holds. When it is cheap, protection is on
# sale: buy a $1 put debit vertical. Skew is read from the chain the House shows (its IVs and deltas).
# THE EVIDENCE. Published: the variance and skew risk premia (Bakshi, Kapadia and Madan 2003; Bollerslev and
# Todorov 2011): index puts are overpriced on average, most when fear is high. Measured here (options history,
# May 14 to September 23, 2026): SPY's 30-day 25-delta skew averaged 0.049 (sd 0.013), QQQ's 0.056, IWM's 0.052.
# Until `min_obs` days of its own readings exist the founder measures against `skew_norm` +- `skew_sd`.
# WHAT IT NEEDS. Daily bars (30) and quotes of the three ETFs, the chain within 9 days, `structures: True`.
# WHEN IT TRADES. From `entry_start` (10:30 New York) to `entry_end` (15:00), once an underlying a day, at most
# `max_open` structures, never on an expiry day after 14:00. HOW IT EXITS. At `profit_target` of what it can
# make (a credit: of the credit), at `stop_loss` of the credit (or of the debit), after `max_hold_days`, and on
# its expiry day `exit_minutes_before_close` before the close. PARAMS: `z_rich`, `z_cheap`, `cheap_side` (1 buys
# cheap puts), `structure` (the rich arm: credit_vertical, or debit_vertical to buy calls), `width`, `dte_min`-`dte_max`.

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

NEEDS = {"venue": "alpaca", "horizon": "day", "style": "options-skew", "asset_class": "option", "structures": True,
         "symbols": ["SPY", "QQQ", "IWM"], "bars": {"timeframe": "1Day", "limit": 30}, "max_days_to_expiry": 9, "wake_minutes": 10,
         "parameter_rules": {"bounds": {"width": [1, 5], "dte_min": [1, 9], "dte_max": [1, 9], "entry_delta": [0.15, 0.5], "profit_target": [0.2, 0.95],
                                        "stop_loss": [0.3, 2.0], "exit_minutes_before_close": [30, 240], "exit_dte": [0, 5], "max_open": [1, 3],
                                        "max_qty": [1, 3], "notional_usd": [20, 75], "slip": [0, 0.05], "max_debit": [0.3, 0.8], "min_credit": [0.1, 0.5],
                                        "z_rich": [0.5, 3.0], "z_cheap": [0.5, 3.0], "cheap_side": [0, 1], "skew_norm": [0.0, 0.15], "skew_sd": [0.005, 0.05],
                                        "min_obs": [3, 20], "lookback": [5, 20], "trend_days": [5, 25], "max_hold_days": [1, 7]},
                             "ordered": [["dte_min", "dte_max"]]}}
PARAMS = {"structure": "credit_vertical", "width": 1.0, "dte_min": 1, "dte_max": 9, "entry_delta": 0.35, "profit_target": 0.5, "stop_loss": 1.0,
          "exit_minutes_before_close": 60, "exit_dte": 0, "max_open": 2, "max_qty": 1, "notional_usd": 72.0, "slip": 0.01, "max_debit": 0.65,
          "min_credit": 0.28, "requote_minutes": 30, "z_rich": 1.0, "z_cheap": 1.0, "cheap_side": 1, "skew_norm": 0.05, "skew_sd": 0.013,
          "min_obs": 8, "lookback": 20, "trend_days": 20, "max_hold_days": 4, "entry_start": 630, "entry_end": 900}

def _skew(ctx, under, p, ny):  # the nearest expiry's 25-delta put IV less its 25-delta call IV, or None
    rows = [r for r in ctx.get("chain") or [] if isinstance(r, dict) and r.get("underlying") == under and _num(r.get("iv"), None) and _num(r.get("delta"), None) is not None
            and _dte(r.get("expiry"), ny) is not None and p["dte_min"] <= _dte(r.get("expiry"), ny) <= p["dte_max"]]
    expiry = min((str(r.get("expiry")) for r in rows), default=None)
    puts = [(abs(_num(r["delta"]) + 0.25), _num(r["iv"])) for r in rows if r.get("expiry") == expiry and r.get("right") == "put"]
    calls = [(abs(_num(r["delta"]) - 0.25), _num(r["iv"])) for r in rows if r.get("expiry") == expiry and r.get("right") == "call"]
    put, call = min(puts, default=(1.0, 0.0)), min(calls, default=(1.0, 0.0))
    return put[1] - call[1] if put[0] <= 0.1 and call[0] <= 0.1 else None

def decide(ctx):
    p, ny, memory, shut = _setup(ctx)
    if shut:
        return {"intents": [], "cancels": [], "thought": "Options skew: the market is shut.", "memory": memory}
    day, notes, kind = ny.date().toordinal(), [], "credit_vertical" if p["structure"] == "credit_vertical" else "debit_vertical"
    seen = {k: [x for x in v if isinstance(x, list) and len(x) == 2][-int(p["lookback"]):] for k, v in (memory.get("skew") or {}).items() if k in NEEDS["symbols"] and isinstance(v, list)} \
        if isinstance(memory.get("skew"), dict) else {}

    def aged(row, held_kind, occs, dte):
        opened = _ny(row.get("opened_at"))
        return f"held {(ny.date() - opened.date()).days} days, the most is {int(p['max_hold_days'])}" if opened and (ny.date() - opened.date()).days >= p["max_hold_days"] else None

    readings = {}
    for under in NEEDS["symbols"] if p["entry_start"] <= ny.hour * 60 + ny.minute < p["entry_end"] else []:
        skew, past = _skew(ctx, under, p, ny), [x[1] for x in seen.get(under, []) if x[0] != day]
        if skew is not None:  # one reading a day (the day's last), judged against the days before it
            seen[under] = [x for x in seen.get(under, []) if x[0] != day] + [[day, round(skew, 5)]]
            mean = sum(past) / len(past) if len(past) >= p["min_obs"] else p["skew_norm"]
            sd = math.sqrt(sum((x - mean) ** 2 for x in past) / len(past)) if len(past) >= p["min_obs"] else p["skew_sd"]
            readings[under] = (skew, (skew - mean) / max(sd, 0.002), mean)

    def signal(under):
        closes, price = _closes(ctx, under), _price(ctx, under)
        if under not in readings or price <= 0 or len(closes) < p["trend_days"]:
            return "no 25-delta put and call to read the skew from, or too few daily bars"
        (skew, z, mean), trend = readings[under], sum(closes[-int(p["trend_days"]):]) / int(p["trend_days"])
        if z >= p["z_rich"] and price > trend:
            return True, f"{under}'s 25-delta skew {skew:.3f} is rich ({z:+.1f} sd over {mean:.3f}) above its {int(p['trend_days'])}-day mean: selling the fear", kind, day
        if z <= -p["z_cheap"] and p["cheap_side"] >= 1:
            return False, f"{under}'s 25-delta skew {skew:.3f} is cheap ({z:+.1f} sd under {mean:.3f}): buying protection on sale", "debit_vertical", day
        return f"skew {skew:.3f} is {z:+.1f} sd from {mean:.3f}" + (", rich but under the trend" if z >= p["z_rich"] else "")

    intents, cancels = _exits(ctx, ny, p, notes, aged)
    done = {k: v for k, v in (memory.get("done") or {}).items() if v == day} if isinstance(memory.get("done"), dict) else {}
    if p["entry_start"] <= ny.hour * 60 + ny.minute < p["entry_end"]:
        intents += _enter(ctx, p, ny, notes, cancels, done, signal, _vertical)
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options skew. " + ("; ".join(notes) or "nothing to do") + ".", "memory": {"done": done, "skew": seen}}

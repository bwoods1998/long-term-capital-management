# options-breakout: buy one near-the-money option when a cheap, liquid stock breaks out of its
# 20-day range in the direction of its trend. A call on a breakout up, a put on a breakdown.
#
# THE IDEA. A long option is leverage with the loss capped at the premium. That only pays if the
# underlying MOVES, soon, the right way: so buy only when it has just made a 20-day high above a
# rising 50-day mean (or a 20-day low under a falling one), which is when trends tend to extend.
#
# THE EVIDENCE. None from this firm: the first run never traded options. Published: time-series
# momentum is real in stocks; option BUYERS lose on average (they pay the variance premium and
# the spread), so this must be right about direction often enough to pay for both. Treat it as
# the specialty's first question, not its answer.
#
# WHAT IT NEEDS. Daily bars (70) and the option chain the House shows: contracts on these
# underlyings expiring after today, near the money, two-sided and affordable in one order. One
# contract is 100 shares, and an order is capped at $75 on paper and $20 with real money, so the
# premiums in reach are under 75 cents: at-the-money weeklies on stocks under about $20.
#
# WHEN IT TRADES. 09:45 to 15:30 New York. One contract an underlying, at most max_open at once.
# A LIMIT order between the mid and the ask (the quotes it sees are fifteen minutes old, so a
# market order is not allowed and a stale price costs a fill, never more). Unfilled bids are
# cancelled after requote_minutes.
#
# HOW IT EXITS. A limit sell at the bid at +take_profit_pct or -stop_pct on the premium paid, or
# with exit_days left. The House itself sells anything still held on its last afternoon.

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HOLIDAYS = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
            "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}

def _num(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default

def _new_york(text):
    try:
        moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00").replace("z", "+00:00"))
        return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return None

def _in_session(ny):
    # 09:45 to 15:30 New York: spreads are widest at the open, and the House sells on a last afternoon.
    if ny is None or ny.weekday() >= 5 or ny.strftime("%Y-%m-%d") in HOLIDAYS:
        return False
    return 585 <= ny.hour * 60 + ny.minute < 930

def _days_to(expiry, ny):
    try:
        return (datetime.strptime(str(expiry), "%Y-%m-%d").date() - ny.date()).days
    except Exception:
        return None

def _closes(ctx, symbol):
    return [c for c in (_num(bar.get("c"), None) for bar in (ctx.get("bars") or {}).get(symbol) or [] if isinstance(bar, dict)) if c is not None and c > 0]

def _pick(chain, symbol, right, ny, p, budget):
    # This underlying and right, inside the days window, a tight spread, affordable, nearest the money.
    best = None
    for row in chain:
        if not isinstance(row, dict) or row.get("underlying") != symbol or row.get("right") != right:
            continue
        days = _days_to(row.get("expiry"), ny)
        bid, ask, spot = _num(row.get("bid"), 0.0), _num(row.get("ask"), 0.0), _num(row.get("underlying_price"), 0.0)
        if days is None or not p["min_days"] <= days <= p["max_days"] or not 0.0 < bid < ask:
            continue
        mid = (bid + ask) / 2.0
        if (ask - bid) / mid * 100.0 > p["max_spread_pct"] or ask * 100.0 > budget or mid < p["min_premium"]:
            continue
        delta = _num(row.get("delta"), None)
        score = abs(abs(delta) - p["target_delta"]) if delta is not None else (abs(_num(row.get("strike"), 0.0) / spot - 1.0) if spot > 0 else 9.0)
        if best is None or (score, days) < best[0]:
            best = ((score, days), row, bid, ask)
    return best

def _manage(ctx, ny, p, notes):
    # Cancel stale bids; sell at a target, a stop, or near expiry. A position's mark is the BID.
    intents, cancels = [], []
    for order in ctx.get("open_orders") or []:
        sent = _new_york(order.get("submitted_at")) if isinstance(order, dict) else None
        if sent is not None and ny is not None and order.get("order_id") and (ny - sent).total_seconds() > p["requote_minutes"] * 60:
            cancels.append(str(order["order_id"]))
    working = {str(o.get("occ")) for o in ctx.get("open_orders") or [] if isinstance(o, dict) and o.get("side") == "sell"}
    for held in ctx.get("positions") or []:
        if not isinstance(held, dict) or not held.get("occ") or _num(held.get("quantity"), 0.0) <= 0 or str(held["occ"]) in working:
            continue
        cost, mark, days = _num(held.get("average_cost"), 0.0), _num(held.get("mark"), 0.0), _days_to(held.get("expiry"), ny)
        if cost <= 0 or mark <= 0:
            continue
        change = mark / cost - 1.0
        why = (f"up {change:+.0%} on the premium paid: the target is +{p['take_profit_pct']:.0f}%" if change >= p["take_profit_pct"] / 100.0 else
               f"down {change:+.0%} on the premium paid: the stop is -{p['stop_pct']:.0f}%" if change <= -p["stop_pct"] / 100.0 else
               f"{days} days to expiry: time decay is steepest at the end" if days is not None and days <= p["exit_days"] else None)
        if why:
            intents.append({"occ": held["occ"], "side": "sell", "quantity": int(_num(held.get("quantity"), 0.0)), "type": "limit",
                            "limit_price": round(mark, 2), "reason": f"Selling {held['occ']} at the bid {mark:.2f}: {why}."})
            notes.append(f"{held['occ']}: selling, {why}")
        else:
            notes.append(f"{held['occ']}: holding at {change:+.0%}")
    return intents, cancels

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "options-breakout",
    "asset_class": "option",
    "symbols": ["F", "SOFI", "AAL", "T", "PFE", "INTC"],
    "bars": {"timeframe": "1Day", "limit": 70},
    "max_days_to_expiry": 28,
    "wake_minutes": 30,
}
PARAMS = {"breakout_days": 20, "trend_days": 50, "min_days": 7, "max_days": 28, "target_delta": 0.5, "max_spread_pct": 15.0,
          "min_premium": 0.10, "notional_usd": 75.0, "max_open": 2, "take_profit_pct": 60.0, "stop_pct": 40.0, "exit_days": 2, "requote_minutes": 30}


def decide(ctx):
    p = {**PARAMS, **{k: _num(v, PARAMS[k]) for k, v in (ctx.get("params") or {}).items() if k in PARAMS}}
    ny = _new_york(ctx.get("now"))
    notes = []
    intents, cancels = _manage(ctx, ny, p, notes)
    if not _in_session(ny):
        return {"intents": intents, "cancels": cancels, "thought": "Options breakout. Outside 09:45-15:30 New York: no entries. " + "; ".join(notes), "memory": {}}
    chain = [row for row in ctx.get("chain") or [] if isinstance(row, dict)]
    busy = {str(x.get("symbol")) for x in (ctx.get("positions") or []) + (ctx.get("open_orders") or []) if isinstance(x, dict)}
    limits = ctx.get("limits") or {}
    budget = min(p["notional_usd"], _num(limits.get("max_order_usd"), 0.0), _num(limits.get("max_position_usd"), 0.0), _num(ctx.get("cash"), 0.0) * 0.95)
    slots = int(p["max_open"]) - len(busy)
    for symbol in NEEDS["symbols"]:
        if slots <= 0 or symbol in busy:
            continue
        closes = _closes(ctx, symbol)
        span, trend = int(p["breakout_days"]), int(p["trend_days"])
        if len(closes) < trend + 1:
            notes.append(f"{symbol}: {len(closes)} daily bars, {trend + 1} needed")
            continue
        last, window, mean = closes[-1], closes[-span - 1:-1], sum(closes[-trend:]) / trend
        right = "call" if last > max(window) and last > mean else ("put" if last < min(window) and last < mean else None)
        if right is None:
            notes.append(f"{symbol}: {last:.2f} inside its {span}-day range {min(window):.2f}-{max(window):.2f}")
            continue
        found = _pick(chain, symbol, right, ny, p, budget)
        if found is None:
            notes.append(f"{symbol}: a {span}-day {'high' if right == 'call' else 'low'}, but no {right} in reach (days, spread or price)")
            continue
        _, row, bid, ask = found
        price = round(min(ask, (bid + ask) / 2.0 + 0.01), 2)
        intents.append({"occ": row["symbol"], "side": "buy", "quantity": 1, "type": "limit", "limit_price": price,
                        "reason": (f"Buying one {row['symbol']} at {price:.2f} (bid {bid:.2f}, ask {ask:.2f}): {symbol} closed at {last:.2f}, a {span}-day "
                                   f"{'high' if right == 'call' else 'low'} {'above' if right == 'call' else 'below'} its {trend}-day mean {mean:.2f}. "
                                   f"The most this can lose is the ${price * 100:.0f} paid.")})
        notes.append(f"{symbol}: breakout, bidding {price:.2f} for {row['symbol']}")
        slots -= 1
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options breakout. " + "; ".join(notes) + ".", "memory": {}}

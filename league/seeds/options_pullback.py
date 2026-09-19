# options-pullback: buy one near-the-money CALL when a stock in an uptrend has fallen hard for
# two days, and sell it on the bounce.
#
# THE IDEA. Connors' RSI(2) pullback, expressed with a call instead of shares: in an uptrend
# (close above its 100-day mean) two sharp down days tend to be bought back within the week. A
# call turns a $0.30 bounce in a $13 stock into a large move on a small premium, and caps the
# loss at that premium if the pullback is the start of something worse.
#
# THE EVIDENCE. The pullback effect is published and was strongest before 2010; nothing here is
# measured by this firm, and option buyers pay the spread and the variance premium. A short hold
# (days, not weeks) keeps time decay small. The league will need patience: signals are rare.
#
# WHAT IT NEEDS. Daily bars (130) and the option chain the House shows (see options-breakout's
# notes: premiums under 75 cents on paper, so cheap liquid underlyings).
#
# WHEN IT TRADES. 09:45 to 15:30 New York: RSI(2) under rsi_entry and the close above the
# 100-day mean. One call an underlying, 10 to 30 days out so a few days of decay cost little.
#
# HOW IT EXITS. When the underlying closes back above its 5-day mean (the bounce), or at
# +take_profit_pct / -stop_pct on the premium, or with exit_days left. Limit sells at the bid.

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
    "style": "options-pullback",
    "asset_class": "option",
    "symbols": ["F", "SOFI", "AAL", "T", "PFE", "INTC"],
    "bars": {"timeframe": "1Day", "limit": 130},
    "max_days_to_expiry": 30,
    "wake_minutes": 30,
}
PARAMS = {"rsi_entry": 15.0, "trend_days": 100, "exit_mean_days": 5, "min_days": 10, "max_days": 30, "target_delta": 0.55, "max_spread_pct": 15.0,
          "min_premium": 0.10, "notional_usd": 75.0, "max_open": 2, "take_profit_pct": 50.0, "stop_pct": 50.0, "exit_days": 3, "requote_minutes": 30}
def _rsi2(closes):
    if len(closes) < 3:
        return None
    gain = sum(max(closes[i] - closes[i - 1], 0.0) for i in (-2, -1)) / 2.0
    loss = sum(max(closes[i - 1] - closes[i], 0.0) for i in (-2, -1)) / 2.0
    return 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)


def decide(ctx):
    p = {**PARAMS, **{k: _num(v, PARAMS[k]) for k, v in (ctx.get("params") or {}).items() if k in PARAMS}}
    ny = _new_york(ctx.get("now"))
    notes = []
    intents, cancels = _manage(ctx, ny, p, notes)
    selling = {i["occ"] for i in intents}  # then the bounce: sell once the underlying closes back above its short mean
    for held in ctx.get("positions") or []:
        if not isinstance(held, dict) or not held.get("occ") or held["occ"] in selling or _num(held.get("mark"), 0.0) <= 0:
            continue
        closes = _closes(ctx, str(held.get("symbol")))
        days = int(p["exit_mean_days"])
        if len(closes) >= days and closes[-1] > sum(closes[-days:]) / days:
            mark = round(_num(held["mark"]), 2)
            intents.append({"occ": held["occ"], "side": "sell", "quantity": int(_num(held.get("quantity"), 0.0)), "type": "limit", "limit_price": mark,
                            "reason": f"Selling {held['occ']} at the bid {mark:.2f}: {held.get('symbol')} closed back above its {days}-day mean, which is the bounce this was bought for."})
    if not _in_session(ny):
        return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options pullback. Outside 09:45-15:30 New York: no entries. " + "; ".join(notes), "memory": {}}
    chain = [row for row in ctx.get("chain") or [] if isinstance(row, dict)]
    busy = {str(x.get("symbol")) for x in (ctx.get("positions") or []) + (ctx.get("open_orders") or []) if isinstance(x, dict)}
    limits = ctx.get("limits") or {}
    budget = min(p["notional_usd"], _num(limits.get("max_order_usd"), 0.0), _num(limits.get("max_position_usd"), 0.0), _num(ctx.get("cash"), 0.0) * 0.95)
    slots = int(p["max_open"]) - len(busy)
    for symbol in NEEDS["symbols"]:
        if slots <= 0 or symbol in busy:
            continue
        closes, trend = _closes(ctx, symbol), int(p["trend_days"])
        rsi = _rsi2(closes)
        if len(closes) < trend or rsi is None:
            notes.append(f"{symbol}: {len(closes)} daily bars, {trend} needed")
            continue
        mean = sum(closes[-trend:]) / trend
        if not (rsi < p["rsi_entry"] and closes[-1] > mean):
            notes.append(f"{symbol}: RSI(2) {rsi:.0f}, close {closes[-1]:.2f} against a {trend}-day mean of {mean:.2f}: no pullback in an uptrend")
            continue
        found = _pick(chain, symbol, "call", ny, p, budget)
        if found is None:
            notes.append(f"{symbol}: a pullback (RSI(2) {rsi:.0f}), but no call in reach (days, spread or price)")
            continue
        (_, row, bid, ask), price = found, round(min(found[3], (found[2] + found[3]) / 2.0 + 0.01), 2)
        intents.append({"occ": row["symbol"], "side": "buy", "quantity": 1, "type": "limit", "limit_price": price,
                        "reason": (f"Buying one {row['symbol']} at {price:.2f} (bid {bid:.2f}, ask {ask:.2f}): {symbol} is above its {trend}-day mean "
                                   f"({closes[-1]:.2f} against {mean:.2f}) and RSI(2) is {rsi:.0f} after two hard down days. The most this can lose is the ${price * 100:.0f} paid.")})
        notes.append(f"{symbol}: pullback, bidding {price:.2f} for {row['symbol']}")
        slots -= 1
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": "Options pullback. " + "; ".join(notes) + ".", "memory": {}}

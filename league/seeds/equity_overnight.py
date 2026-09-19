# equity-overnight: buy SPY and QQQ in the last twenty minutes of the session, sell them in the
# first half hour of the next one. It owns the index only while the market is closed.
#
# THE IDEA. The overnight-drift anomaly: measured over decades, most (in some samples all) of
# the US index's return accrued between the close and the next open, and very little of it
# during the trading day. So hold overnight and sit in cash intraday. A simple trend filter keeps
# it out when the index is weak: it only buys when the last daily close is above the mean of the
# last `mean_days` (20) daily closes.
#
# THE EVIDENCE. Published research, not the first run (which never traded equities). Costs are
# kind here: Alpaca charges no commission on ETFs, so the whole cost is the spread twice a day,
# about a basis point each way on SPY and QQQ. The league will measure whether the drift still
# pays after that.
#
# WHAT IT NEEDS. 1Day bars (30) and the touch for SPY and QQQ, and to be woken every 10 minutes
# so that it lands inside both windows. No memory: a holding carries its own opened_at.
#
# WHEN IT TRADES. Only in the regular session, read from ctx["now"] on the New York clock
# (weekdays 09:30-16:00, not a full-day holiday): a market order outside it would be refused.
# Buy window 15:40-15:58 New York: not held, no order working, daily bars fresh, last daily close
# above its 20-day mean: a fractional market buy of notional_usd, capped by the order limit, the
# position limit and free cash less 2%. (On a 13:00 early-close day the window never opens.)
#
# HOW IT EXITS. Sell window 09:35-10:00 New York: market-sell the whole holding. If a wake was
# missed, anything bought on an earlier day is sold at the next wake before the buy window.

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "overnight",
    "symbols": ["SPY", "QQQ"],
    "bars": {"timeframe": "1Day", "limit": 30},
    "wake_minutes": 10,
}
# Window edges are minutes after midnight in New York: 940 = 15:40, 958 = 15:58, 575 = 09:35, 600 = 10:00.
PARAMS = {"mean_days": 20, "notional_usd": 50.0, "buy_start": 940, "buy_end": 958, "sell_start": 575, "sell_end": 600}
HOLIDAYS = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
            "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
STALE_DAYS = 5.0  # the last daily bar may be a long weekend old, not older


def _num(value, default=0.0):
    """A finite float, or the default for anything else (None, text, NaN)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _new_york(text):
    """ISO-8601 text as a New York datetime (UTC when it has no offset), or None."""
    try:
        clean = str(text).strip()
        if clean[-1:] in "Zz":
            clean = clean[:-1] + "+00:00"
        moment = datetime.fromisoformat(clean)
        moment = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return None


def _session_minute(ny):
    """Minutes after midnight in New York while the regular session is open, else None."""
    if ny is None or ny.weekday() >= 5 or ny.strftime("%Y-%m-%d") in HOLIDAYS:
        return None
    minute = ny.hour * 60 + ny.minute
    return minute if 570 <= minute < 960 else None


def _budget(ctx, want, held_usd, spent):
    """Dollars for one buy: the wanted size, capped by the order limit, by the room left under
    the position limit, and by free cash (cash less resting buys and this wake's buys) less 2%."""
    limits = ctx.get("limits") or {}
    resting = sum(_num(o.get("quantity")) * _num(o.get("limit_price")) for o in ctx.get("open_orders") or []
                  if isinstance(o, dict) and o.get("side") == "buy")
    free = (_num(ctx.get("cash")) - resting - spent) * 0.98
    return min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want) - held_usd, free)


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    mean_days = max(2, int(_num(p.get("mean_days"), 20)))
    buy_start, buy_end = _num(p.get("buy_start"), 940), _num(p.get("buy_end"), 958)
    sell_start, sell_end = _num(p.get("sell_start"), 575), _num(p.get("sell_end"), 600)
    ny = _new_york(ctx.get("now"))
    minute = _session_minute(ny)
    if minute is None:
        return {"intents": [], "cancels": [], "memory": {},
                "thought": "New York's regular session is closed (or the clock is unreadable): an equity market order would be refused, so nothing to do."}
    today = ny.strftime("%Y-%m-%d")
    bars = ctx.get("bars") or {}
    held = {x.get("symbol"): x for x in ctx.get("positions") or [] if isinstance(x, dict) and _num(x.get("quantity")) > 0}
    working = {o.get("symbol") for o in ctx.get("open_orders") or [] if isinstance(o, dict)}

    intents, notes, spent = [], [], 0.0
    for symbol in NEEDS["symbols"]:
        position = held.get(symbol)
        if symbol in working:
            notes.append(f"{symbol}: an order is already working")
        elif position is not None:
            opened = _new_york(position.get("opened_at"))
            overdue = opened is not None and opened.strftime("%Y-%m-%d") < today and sell_end < minute < buy_start
            if sell_start <= minute <= sell_end or overdue:
                intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "market",
                                "reason": (f"Selling all {symbol} at {ny.strftime('%H:%M')} New York: the overnight hold is over"
                                           f"{' (the 09:35-10:00 window was missed, selling late)' if overdue else ''}; bought at "
                                           f"{_num(position.get('average_cost')):.2f}, now marked {_num(position.get('mark')):.2f}. Cash until the close.")})
                notes.append(f"{symbol}: selling the overnight holding")
            else:
                notes.append(f"{symbol}: holding until the 09:35-10:00 sell window")
        elif buy_start <= minute <= buy_end:
            rows = [b for b in bars.get(symbol) or [] if isinstance(b, dict) and _num(b.get("c")) > 0]
            closes = [_num(b.get("c")) for b in rows]
            last_bar = _new_york(rows[-1].get("t")) if rows else None
            if len(closes) < mean_days or last_bar is None or (ny - last_bar).total_seconds() / 86400.0 > STALE_DAYS:
                notes.append(f"{symbol}: {len(closes)} fresh daily bars, need {mean_days}; no buy")
                continue
            mean = sum(closes[-mean_days:]) / mean_days
            if closes[-1] <= mean:
                notes.append(f"{symbol}: last daily close {closes[-1]:.2f} is not above its {mean_days}-day mean {mean:.2f}; staying in cash tonight")
                continue
            dollars = math.floor(_budget(ctx, _num(p.get("notional_usd"), 50.0), 0.0, spent) * 100.0) / 100.0
            if dollars < 1.0:
                notes.append(f"{symbol}: the filter passes but only ${max(dollars, 0.0):.2f} can be spent")
                continue
            spent += dollars
            intents.append({"symbol": symbol, "side": "buy", "notional_usd": dollars, "type": "market",
                            "reason": (f"Buying ${dollars:.2f} of {symbol} at {ny.strftime('%H:%M')} New York to hold overnight: the last daily close {closes[-1]:.2f} "
                                       f"is above its {mean_days}-day mean {mean:.2f}. Most of the index's long-run return accrued overnight; sold after tomorrow's open.")})
            notes.append(f"{symbol}: buying for the overnight hold")
        else:
            notes.append(f"{symbol}: in cash, waiting for the 15:40 buy window")
    thought = f"Overnight drift, {ny.strftime('%a %H:%M')} New York. " + "; ".join(notes) + "."
    return {"intents": intents, "cancels": [], "thought": thought, "memory": {}}

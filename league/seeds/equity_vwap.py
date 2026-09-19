# equity-vwap: intraday only. Buy SPY, QQQ or IWM when it trades more than 0.4% under today's
# volume-weighted average price, sell when it is back at VWAP. Always flat by 15:50 New York.
#
# THE IDEA. VWAP is where the day's volume actually changed hands, and large orders are
# benchmarked to it, so on an ordinary day the price is pulled back toward it. A stretch of
# `band_pct` below VWAP in the middle of the day is bought for the snap back. On a trend day the
# stretch keeps going, which is what the tight stop and the one-stop-per-day rule are for.
#
# THE EVIDENCE. A common desk heuristic with mixed published support; not from the first run,
# which never traded equities. No commission on Alpaca ETFs, so the cost is the spread (about a
# basis point on these three), small against a 0.4% target. It is the only equity seed that a
# 5-minute replay tape can exercise bar by bar.
#
# WHAT IT NEEDS. 5Min bars (100) and the touch for the three ETFs, woken every 5 minutes. Bars are
# stamped with their close, so today's regular-session bars are those closing 09:35-16:00 on
# today's New York date; VWAP = sum(typical price x volume) / sum(volume) over them. Memory holds
# the date each symbol was last stopped out, so a symbol that stopped is left alone until tomorrow.
#
# WHEN IT TRADES. Only in the regular session on the New York clock read from ctx["now"]
# (weekdays, not a full-day holiday). Entries 10:00-15:00: not held, no order working, at least
# min_bars session bars with the last one fresh, not stopped today, and the ask more than
# band_pct under VWAP: a fractional market buy of notional_usd, capped by the order limit, the
# position limit and free cash less 2%.
#
# HOW IT EXITS. It market-sells the whole holding when the bid is back at VWAP, when the bid is
# stop_pct (0.5%) under average_cost, at or after 15:50 New York, or at the first open-session
# wake if it somehow holds something bought on an earlier day. It never holds overnight by design.

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEEDS = {
    "venue": "alpaca",
    "horizon": "hour",
    "style": "intraday-reversion",
    "symbols": ["SPY", "QQQ", "IWM"],
    "bars": {"timeframe": "5Min", "limit": 100},
    "wake_minutes": 5,
}
# entry_start, entry_end and flat_at are minutes after midnight in New York: 600 = 10:00, 900 = 15:00, 950 = 15:50.
PARAMS = {"band_pct": 0.4, "stop_pct": 0.5, "min_bars": 6, "notional_usd": 50.0, "entry_start": 600, "entry_end": 900, "flat_at": 950}
HOLIDAYS = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
            "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
STALE_MINUTES = 15.0  # the last session bar must have closed this recently for a new buy


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


def _session_vwap(rows, ny):
    """(VWAP, bars used, minutes since the last one closed) over today's regular-session bars."""
    today, used, money, volume, last = ny.strftime("%Y-%m-%d"), 0, 0.0, 0.0, None
    for bar in rows:
        closed = _new_york(bar.get("t"))
        high, low, close = _num(bar.get("h")), _num(bar.get("l")), _num(bar.get("c"))
        if closed is None or closed.strftime("%Y-%m-%d") != today or not 570 < closed.hour * 60 + closed.minute <= 960 or min(high, low, close) <= 0:
            continue
        weight = max(_num(bar.get("v")), 0.0) or 1e-9  # a bar with no volume barely counts
        used, money, volume, last = used + 1, money + (high + low + close) / 3.0 * weight, volume + weight, closed
    if not used:
        return None, 0, None
    return money / volume, used, (ny - last).total_seconds() / 60.0


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    band_pct, stop_pct, min_bars = _num(p.get("band_pct"), 0.4), _num(p.get("stop_pct"), 0.5), int(_num(p.get("min_bars"), 6))
    memory = ctx.get("memory")
    remembered = memory.get("stopped") if isinstance(memory, dict) else None
    stopped = {k: v for k, v in (remembered if isinstance(remembered, dict) else {}).items() if k in NEEDS["symbols"] and isinstance(v, str)}
    ny = _new_york(ctx.get("now"))
    minute = _session_minute(ny)
    if minute is None:
        return {"intents": [], "cancels": [], "memory": {"stopped": stopped},
                "thought": "New York's regular session is closed (or the clock is unreadable): an equity market order would be refused, so nothing to do."}
    today = ny.strftime("%Y-%m-%d")
    quotes, limits, want = ctx.get("quotes") or {}, ctx.get("limits") or {}, _num(p.get("notional_usd"), 50.0)
    held = {x.get("symbol"): x for x in ctx.get("positions") or [] if isinstance(x, dict) and _num(x.get("quantity")) > 0}
    working = {o.get("symbol") for o in ctx.get("open_orders") or [] if isinstance(o, dict)}
    free = (_num(ctx.get("cash")) - sum(_num(o.get("quantity")) * _num(o.get("limit_price")) for o in ctx.get("open_orders") or []
                                        if isinstance(o, dict) and o.get("side") == "buy")) * 0.98

    intents, notes = [], []
    for symbol in NEEDS["symbols"]:
        rows = [b for b in (ctx.get("bars") or {}).get(symbol) or [] if isinstance(b, dict)]
        vwap, used, age = _session_vwap(rows, ny)
        quote, position = quotes.get(symbol) or {}, held.get(symbol)
        if symbol in working:
            notes.append(f"{symbol}: an order is already working")
        elif position is not None:
            cost, bid = _num(position.get("average_cost")), _num(quote.get("bid")) or _num(position.get("mark"))
            loss_pct = (1.0 - bid / cost) * 100.0 if cost > 0 and bid > 0 else 0.0
            opened, why = _new_york(position.get("opened_at")), None
            if opened is not None and opened.strftime("%Y-%m-%d") < today:
                why = f"it was bought on {opened.strftime('%Y-%m-%d')} and this strategy never holds overnight"
            elif minute >= _num(p.get("flat_at"), 950):
                why = f"it is {ny.strftime('%H:%M')} New York and the book is flat by 15:50 (bid {bid:.2f}, bought at {cost:.2f})"
            elif loss_pct >= stop_pct:
                why = f"stop: the bid {bid:.2f} is {loss_pct:.2f}% under the average cost {cost:.2f} (limit {stop_pct:.2f}%); no more {symbol} today"
                stopped[symbol] = today
            elif vwap is not None and bid >= vwap:
                why = f"target reached: the bid {bid:.2f} is back at today's VWAP {vwap:.2f} (bought at {cost:.2f})"
            if why:
                intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "market", "reason": f"Selling all {symbol}: {why}."})
            notes.append(f"{symbol}: {'selling, ' + why if why else f'holding under VWAP {_num(vwap):.2f}, bid {bid:.2f}'}")
        else:
            ask = _num(quote.get("ask")) or (_num(rows[-1].get("c")) if rows else 0.0)
            in_window = _num(p.get("entry_start"), 600) <= minute < _num(p.get("entry_end"), 900)
            if vwap is None or used < min_bars or age is None or age > STALE_MINUTES or ask <= 0:
                notes.append(f"{symbol}: {used} fresh session bars, need {min_bars}; no VWAP to trade against")
                continue
            gap_pct = (1.0 - ask / vwap) * 100.0
            if not in_window or stopped.get(symbol) == today or gap_pct <= band_pct:
                notes.append(f"{symbol}: ask {ask:.2f} is {gap_pct:+.2f}% under VWAP {vwap:.2f}, no entry"
                             f"{' (stopped out earlier today)' if stopped.get(symbol) == today else '' if in_window else ' (outside 10:00-15:00)'}")
                continue
            dollars = math.floor(min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want), free) * 100.0) / 100.0
            if dollars < 1.0:
                notes.append(f"{symbol}: {gap_pct:.2f}% under VWAP is a signal but only ${max(dollars, 0.0):.2f} can be spent")
                continue
            free -= dollars
            intents.append({"symbol": symbol, "side": "buy", "notional_usd": dollars, "type": "market",
                            "reason": (f"Buying ${dollars:.2f} of {symbol} at {ny.strftime('%H:%M')} New York: the ask {ask:.2f} is {gap_pct:.2f}% under today's VWAP {vwap:.2f} "
                                       f"(band {band_pct:.2f}%, {used} session bars). Exit at VWAP, {stop_pct:.2f}% down, or 15:50; never held overnight.")})
            notes.append(f"{symbol}: buying {gap_pct:.2f}% under VWAP {vwap:.2f}")
    return {"intents": intents, "cancels": [], "thought": f"Intraday VWAP reversion, {ny.strftime('%H:%M')} New York. " + "; ".join(notes) + ".", "memory": {"stopped": stopped}}

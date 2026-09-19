# equity-rsi2: Larry Connors' two-day RSI pullback. In an uptrend, buy a sharp two-day drop in
# SPY or QQQ and sell the first bounce.
#
# THE IDEA. Index ETFs mean-revert over a few days while they trend over months. When the close
# is above its 200-day mean (an uptrend) and RSI(2) is under 10 (two hard down days), buyers tend
# to come back within the week. Sell when the close is back above its 5-day mean, or give up
# after seven trading days. No price stop: in Connors' tests stops hurt this system; the
# 200-day filter, the time limit and the small size are the protection.
#
# THE EVIDENCE. Published and widely replicated on 1993-2010s data, weaker since; not from the
# first run, which never traded equities. No commission on Alpaca ETFs, so the cost is the
# spread. Signals are rare (a handful a year per symbol): the league will need patience.
#
# WHAT IT NEEDS. 1Day bars (210) and the touch for SPY and QQQ, woken every 30 minutes. Bars are
# closed bars, so during a session the signal comes from yesterday's close. Memory holds the New
# York date each symbol was last traded, so it acts at most once per symbol per day.
#
# WHEN IT TRADES. Only in the regular session, 09:35-15:55 on the New York clock read from
# ctx["now"] (weekdays, not a full-day holiday): a market order outside it would be refused. Not
# held, no order working, bars fresh, RSI(2) < rsi_entry and close > 200-day mean: a fractional
# market buy of notional_usd, capped by the order limit, the position limit and free cash less 2%.
#
# HOW IT EXITS. It market-sells the whole holding when the last daily close is above the mean of
# the last `exit_mean_days` (5) closes, or when `max_days` (7) daily bars have closed since it bought.

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "reversion",
    "symbols": ["SPY", "QQQ"],
    "bars": {"timeframe": "1Day", "limit": 210},
    "wake_minutes": 30,
}
PARAMS = {"rsi_period": 2, "rsi_entry": 10.0, "trend_days": 200, "exit_mean_days": 5, "max_days": 7, "notional_usd": 60.0}
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


def _rsi(closes, period):
    """Wilder's RSI of the last close, 0 to 100; None with too few closes."""
    changes = [b - a for a, b in zip(closes, closes[1:])]
    if len(changes) < period:
        return None
    gain = sum(max(c, 0.0) for c in changes[:period]) / period
    loss = sum(max(-c, 0.0) for c in changes[:period]) / period
    for change in changes[period:]:
        gain = (gain * (period - 1) + max(change, 0.0)) / period
        loss = (loss * (period - 1) + max(-change, 0.0)) / period
    if loss <= 0:
        return 100.0 if gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    period, trend_days = max(1, int(_num(p.get("rsi_period"), 2))), max(2, int(_num(p.get("trend_days"), 200)))
    exit_days, max_days, rsi_entry = max(1, int(_num(p.get("exit_mean_days"), 5))), _num(p.get("max_days"), 7), _num(p.get("rsi_entry"), 10.0)
    acted = {k: v for k, v in ((ctx.get("memory") or {}).get("acted") or {}).items() if k in NEEDS["symbols"] and isinstance(v, str)}
    ny = _new_york(ctx.get("now"))
    minute = _session_minute(ny)
    if minute is None or not 575 <= minute <= 955:
        return {"intents": [], "cancels": [], "memory": {"acted": acted},
                "thought": "Outside 09:35-15:55 New York in a regular session: an equity market order would be refused, so nothing to do."}
    today = ny.strftime("%Y-%m-%d")
    held = {x.get("symbol"): x for x in ctx.get("positions") or [] if isinstance(x, dict) and _num(x.get("quantity")) > 0}
    working = {o.get("symbol") for o in ctx.get("open_orders") or [] if isinstance(o, dict)}
    limits, want = ctx.get("limits") or {}, _num(p.get("notional_usd"), 60.0)
    free = (_num(ctx.get("cash")) - sum(_num(o.get("quantity")) * _num(o.get("limit_price")) for o in ctx.get("open_orders") or []
                                        if isinstance(o, dict) and o.get("side") == "buy")) * 0.98

    intents, notes = [], []
    for symbol in NEEDS["symbols"]:
        rows = [b for b in (ctx.get("bars") or {}).get(symbol) or [] if isinstance(b, dict) and _num(b.get("c")) > 0]
        closes = [_num(b.get("c")) for b in rows]
        position = held.get(symbol)
        if symbol in working or acted.get(symbol) == today:
            notes.append(f"{symbol}: {'an order is working' if symbol in working else 'already traded today'}")
        elif position is not None:
            opened = _new_york(position.get("opened_at"))
            days = sum(1 for b in rows if opened is not None and (_new_york(b.get("t")) or opened) > opened)
            exit_mean = sum(closes[-exit_days:]) / exit_days if len(closes) >= exit_days else None
            why = None
            if exit_mean is not None and closes[-1] > exit_mean:
                why = f"the bounce came: the last daily close {closes[-1]:.2f} is above its {exit_days}-day mean {exit_mean:.2f}"
            elif days >= max_days:
                why = f"time is up: {days} trading days held against a limit of {max_days:.0f} without a close above the {exit_days}-day mean"
            if why:
                acted[symbol] = today
                intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "market",
                                "reason": f"Selling all {symbol}, {why}. Bought at {_num(position.get('average_cost')):.2f}."})
            notes.append(f"{symbol}: {'selling, ' + why if why else f'holding, day {days} of {max_days:.0f}, waiting for a close above the {exit_days}-day mean'}")
        else:
            last_bar = _new_york(rows[-1].get("t")) if rows else None
            if len(closes) < trend_days or last_bar is None or (ny - last_bar).total_seconds() / 86400.0 > STALE_DAYS:
                notes.append(f"{symbol}: {len(closes)} fresh daily bars, need {trend_days}")
                continue
            rsi, trend = _rsi(closes[-(period + 100):], period), sum(closes[-trend_days:]) / trend_days
            if rsi is None or rsi >= rsi_entry or closes[-1] <= trend:
                notes.append(f"{symbol}: RSI({period}) {_num(rsi, 50.0):.1f}, close {closes[-1]:.2f} against a {trend_days}-day mean of {trend:.2f}, no entry")
                continue
            dollars = math.floor(min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want), free) * 100.0) / 100.0
            if dollars < 1.0:
                notes.append(f"{symbol}: RSI({period}) {rsi:.1f} is a signal but only ${max(dollars, 0.0):.2f} can be spent")
                continue
            free -= dollars
            acted[symbol] = today
            intents.append({"symbol": symbol, "side": "buy", "notional_usd": dollars, "type": "market",
                            "reason": (f"Buying ${dollars:.2f} of {symbol}: RSI({period}) is {rsi:.1f}, under {rsi_entry:.0f}, after a sharp pullback while the close "
                                       f"{closes[-1]:.2f} is still above its {trend_days}-day mean {trend:.2f}. Exit on a close above the {exit_days}-day mean or after {max_days:.0f} trading days.")})
            notes.append(f"{symbol}: buying the pullback, RSI({period}) {rsi:.1f}")
    return {"intents": intents, "cancels": [], "thought": "Connors RSI(2). " + "; ".join(notes) + ".", "memory": {"acted": acted}}

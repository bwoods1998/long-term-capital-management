# equity-trend: once a day, hold the one ETF with the best 60-day return among those trading
# above their own 100-day mean; when none qualifies, hold cash.
#
# THE IDEA. Relative momentum with an absolute trend filter, across five ETFs that cover US large
# caps (SPY), tech (QQQ), small caps (IWM), long Treasuries (TLT) and gold (GLD). Assets that led
# over the last few months tend to keep leading for a while, and refusing anything under its own
# long mean sidesteps the long declines. Holding stocks, bonds or gold means there is usually
# something in an uptrend.
#
# THE EVIDENCE. Published research (cross-asset momentum and trend following), not the first run,
# which never traded equities. Costs are small: no commission on Alpaca ETFs and a rotation only
# every few weeks. It is slow: the league will need many days to judge it.
#
# WHAT IT NEEDS. 1Day bars (130) and the touch for the five ETFs, woken hourly. Memory holds one
# thing, the New York date on which today's work was finished, so it acts once a day.
#
# WHEN IT TRADES. Only between 10:00 and 15:30 New York in the regular session (weekdays, not a
# full-day holiday; ctx["now"] read on the New York clock): a market order outside the session
# would be refused. Rank by close / close `return_days` (60) ago; candidates must close above the
# mean of their last `mean_days` (100) closes. If it holds nothing and there is a leader: a
# fractional market buy of notional_usd, capped by the order limit, the position limit and free
# cash less 2%.
#
# HOW IT EXITS. If it holds anything that is not today's leader (or there is no leader), it
# market-sells the whole holding FIRST and buys nothing in that decision; the new leader is
# bought on a later wake, once the sale shows in positions. Then the day is marked done.

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEEDS = {
    "venue": "alpaca",
    "horizon": "day",
    "style": "trend",
    "symbols": ["SPY", "QQQ", "IWM", "TLT", "GLD"],
    "bars": {"timeframe": "1Day", "limit": 130},
    "wake_minutes": 60,
}
# act_start and act_end are minutes after midnight in New York: 600 = 10:00, 930 = 15:30.
PARAMS = {"return_days": 60, "mean_days": 100, "notional_usd": 75.0, "act_start": 600, "act_end": 930}
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


def _answer(intents, thought, done):
    return {"intents": intents, "cancels": [], "thought": thought, "memory": {"done": done} if done else {}}


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    return_days, mean_days = max(1, int(_num(p.get("return_days"), 60))), max(2, int(_num(p.get("mean_days"), 100)))
    memory = ctx.get("memory")
    done = memory.get("done") if isinstance(memory, dict) else None
    done = done if isinstance(done, str) else None
    ny = _new_york(ctx.get("now"))
    minute = _session_minute(ny)
    if minute is None or not _num(p.get("act_start"), 600) <= minute <= _num(p.get("act_end"), 930):
        return _answer([], "Outside the 10:00-15:30 New York window of a regular session: no equity orders now.", done)
    today = ny.strftime("%Y-%m-%d")
    if done == today:
        return _answer([], "Today's rotation check is already done; next look tomorrow.", done)
    symbols = NEEDS["symbols"]
    held = [x for x in ctx.get("positions") or [] if isinstance(x, dict) and x.get("symbol") in symbols and _num(x.get("quantity")) > 0]
    if any(isinstance(o, dict) and o.get("symbol") in symbols for o in ctx.get("open_orders") or []):
        return _answer([], "An order is still working; waiting for it before looking at the rotation.", done)

    ranked, above = [], []
    for symbol in symbols:
        rows = [b for b in (ctx.get("bars") or {}).get(symbol) or [] if isinstance(b, dict) and _num(b.get("c")) > 0]
        closes = [_num(b.get("c")) for b in rows]
        last_bar = _new_york(rows[-1].get("t")) if rows else None
        if len(closes) < max(return_days + 1, mean_days) or last_bar is None or (ny - last_bar).total_seconds() / 86400.0 > STALE_DAYS:
            continue
        gain, mean = closes[-1] / closes[-1 - return_days] - 1.0, sum(closes[-mean_days:]) / mean_days
        ranked.append((gain, symbol, closes[-1], mean))
        if closes[-1] > mean:
            above.append((gain, symbol, closes[-1], mean))
    if not ranked:
        return _answer([], f"No symbol has {max(return_days + 1, mean_days)} fresh daily bars yet: no ranking, no change.", done)
    leader = max(above, key=lambda row: row[0]) if above else None
    board = ", ".join(f"{s} {g * 100:+.1f}%{'' if c > m else ' (under its mean)'}" for g, s, c, m in sorted(ranked, reverse=True))

    sells = []
    for position in held:
        if leader is None or position["symbol"] != leader[1]:
            target = f"{leader[1]} leads with {leader[0] * 100:+.1f}% over {return_days} days" if leader else f"nothing is above its {mean_days}-day mean"
            sells.append({"symbol": position["symbol"], "side": "sell", "quantity": position["quantity"], "type": "market",
                          "reason": f"Selling all {position['symbol']}: it is no longer the leader, {target}. Board: {board}."})
    if sells:
        return _answer(sells, f"Rotating out: {board}. Selling first; the leader, if any, is bought on the next wake.", done)
    if held:
        return _answer([], f"Already holding the leader {leader[1]}: {board}. Nothing to do today.", today)
    if leader is None:
        return _answer([], f"Nothing is above its {mean_days}-day mean: {board}. Staying in cash today.", today)

    want = _num(p.get("notional_usd"), 75.0)
    limits = ctx.get("limits") or {}
    free = _num(ctx.get("cash")) * 0.98  # 2% headroom; no resting orders exist at this point
    dollars = math.floor(min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want), free) * 100.0) / 100.0
    if dollars < 1.0:
        return _answer([], f"{leader[1]} leads but only ${max(dollars, 0.0):.2f} can be spent; trying again next wake.", done)
    gain, symbol, close, mean = leader
    buy = {"symbol": symbol, "side": "buy", "notional_usd": dollars, "type": "market",
           "reason": (f"Buying ${dollars:.2f} of {symbol}: best {return_days}-day return of the five ETFs ({gain * 100:+.1f}%) and its close {close:.2f} "
                      f"is above its {mean_days}-day mean {mean:.2f}. Board: {board}. Held until another ETF leads or it falls under its mean.")}
    return _answer([buy], f"In cash with a leader: buying {symbol}. {board}.", today)

# crypto-trend: buy an hourly close above the highest high of the last two days while the
# one-day average is above the four-day average; leave when the price breaks the last day's low.
#
# THE IDEA. Crypto moves in bursts. A Donchian breakout (a close above the highest high of the
# prior `breakout` bars) says a burst may have started, and the trend filter (24-bar mean above
# the 96-bar mean) keeps it from buying bounces inside a decline. Losses are cut at a channel
# low or a fixed stop; winners are left to run, because the few big runs pay for the many small
# false starts.
#
# THE EVIDENCE. The first run measured no crypto edge after costs, so this is a textbook
# trend-follower on trial. The measured part is the cost: 0.25% to take on Alpaca, 0.5% a round
# trip. A breakout system trades rarely and aims at moves of several percent, which is why it
# can afford market orders; a version that trades often will be eaten by fees.
#
# WHAT IT NEEDS. 1Hour bars (120 of them) and the touch for BTC/USD, ETH/USD and SOL/USD. No
# memory: a holding carries its own average_cost.
#
# WHEN IT TRADES. Not holding the symbol, no order working in it, the last bar is fresh, the last
# close is above the highest high of the `breakout` bars before it, and mean(last `fast` closes)
# is above mean(last `slow` closes): market buy of notional_usd, capped by the order limit, the
# position limit and free cash less 2%.
#
# HOW IT EXITS. It market-sells the whole holding when the last close is under the lowest low of
# the `exit_bars` bars before it, or when the bid is stop_pct below average_cost.

import math
from datetime import datetime, timezone

NEEDS = {
    "venue": "alpaca",
    "horizon": "hour",
    "style": "trend",
    "symbols": ["BTC/USD", "ETH/USD", "SOL/USD"],
    "bars": {"timeframe": "1Hour", "limit": 120},
    "wake_minutes": 30,
}
PARAMS = {"breakout": 48, "fast": 24, "slow": 96, "exit_bars": 24, "stop_pct": 4.0, "notional_usd": 40.0}
STALE_HOURS = 3.0  # a last bar older than this means the feed is behind: no new buys


def _num(value, default=0.0):
    """A finite float, or the default for anything else (None, text, NaN)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _when(text):
    """ISO-8601 text as an aware datetime (UTC when it has no offset), or None."""
    try:
        clean = str(text).strip()
        if clean[-1:] in "Zz":
            clean = clean[:-1] + "+00:00"
        moment = datetime.fromisoformat(clean)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _budget(ctx, want, held_usd, spent):
    """Dollars for one buy: the wanted size, capped by the order limit, by the room left under
    the position limit, and by free cash: 98% of (cash less resting buys), less this wake's earlier buys."""
    limits = ctx.get("limits") or {}
    resting = sum(_num(o.get("quantity")) * _num(o.get("limit_price")) for o in ctx.get("open_orders") or []
                  if isinstance(o, dict) and o.get("side") == "buy")
    free = (_num(ctx.get("cash")) - resting) * 0.98 - spent
    return min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want) - held_usd, free)


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    breakout, exit_bars = max(2, int(_num(p.get("breakout"), 48))), max(2, int(_num(p.get("exit_bars"), 24)))
    fast, slow = max(1, int(_num(p.get("fast"), 24))), max(2, int(_num(p.get("slow"), 96)))
    stop_pct = _num(p.get("stop_pct"), 4.0)
    bars, quotes, now = ctx.get("bars") or {}, ctx.get("quotes") or {}, _when(ctx.get("now"))
    held = {x.get("symbol"): x for x in ctx.get("positions") or [] if isinstance(x, dict) and _num(x.get("quantity")) > 0}
    working = {o.get("symbol") for o in ctx.get("open_orders") or [] if isinstance(o, dict)}

    intents, notes, spent = [], [], 0.0
    for symbol in NEEDS["symbols"]:
        rows = [b for b in bars.get(symbol) or [] if isinstance(b, dict) and min(_num(b.get("c")), _num(b.get("h")), _num(b.get("l"))) > 0]
        closes = [_num(b.get("c")) for b in rows]
        position = held.get(symbol)
        if symbol in working:
            notes.append(f"{symbol}: an order is already working")
            continue
        if position is not None:
            cost = _num(position.get("average_cost"))
            price = _num((quotes.get(symbol) or {}).get("bid")) or _num(position.get("mark")) or (closes[-1] if closes else 0.0)
            loss_pct = (1.0 - price / cost) * 100.0 if cost > 0 and price > 0 else 0.0
            floor = min(_num(b.get("l")) for b in rows[-exit_bars - 1:-1]) if len(rows) >= exit_bars + 1 else None
            why = None
            if loss_pct >= stop_pct:
                why = f"stop: the bid {price:.2f} is {loss_pct:.1f}% under the average cost {cost:.2f} (limit {stop_pct:.1f}%)"
            elif floor is not None and closes[-1] < floor:
                why = f"the trend broke: the hourly close {closes[-1]:.2f} is under {floor:.2f}, the lowest low of the prior {exit_bars} bars"
            if why:
                intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "market",
                                "reason": f"Selling all {symbol}, {why}."})
            notes.append(f"{symbol}: {'selling, ' + why if why else 'holding the trend'}")
            continue
        if len(rows) < max(breakout + 1, slow, fast):
            notes.append(f"{symbol}: only {len(rows)} usable bars, need {max(breakout + 1, slow, fast)}")
            continue
        last_bar = _when(rows[-1].get("t"))
        fresh = now is not None and last_bar is not None and (now - last_bar).total_seconds() / 3600.0 <= STALE_HOURS
        ceiling = max(_num(b.get("h")) for b in rows[-breakout - 1:-1])
        fast_mean, slow_mean = sum(closes[-fast:]) / fast, sum(closes[-slow:]) / slow
        if not fresh or closes[-1] <= ceiling or fast_mean <= slow_mean:
            notes.append(f"{symbol}: close {closes[-1]:.2f} against a {breakout}-bar high of {ceiling:.2f}, "
                         f"{fast}-bar mean {'above' if fast_mean > slow_mean else 'not above'} the {slow}-bar mean, no entry")
            continue
        dollars = math.floor(_budget(ctx, _num(p.get("notional_usd"), 40.0), 0.0, spent) * 100.0) / 100.0
        if dollars < 1.0:
            notes.append(f"{symbol}: a breakout, but only ${max(dollars, 0.0):.2f} can be spent")
            continue
        spent += dollars
        intents.append({"symbol": symbol, "side": "buy", "notional_usd": dollars, "type": "market",
                        "reason": (f"Buying ${dollars:.2f} of {symbol}: the hourly close {closes[-1]:.2f} broke above {ceiling:.2f}, the highest high of the "
                                   f"prior {breakout} bars, with the {fast}-bar mean {fast_mean:.2f} above the {slow}-bar mean {slow_mean:.2f}. "
                                   f"Exit under the {exit_bars}-bar low or {stop_pct:.1f}% down.")})
        notes.append(f"{symbol}: buying the breakout over {ceiling:.2f}")
    thought = "Hourly breakout trend. " + "; ".join(notes) + "."
    return {"intents": intents, "cancels": [], "thought": thought, "memory": {}}

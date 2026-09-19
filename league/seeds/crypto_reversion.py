# crypto-reversion: buy an hourly crypto close that is two standard deviations under its own
# recent mean, and sell when it has come back to the mean.
#
# THE IDEA. Over a day or so BTC, ETH and SOL wander around a local average; a sharp hourly drop
# with no follow-through tends to be given back. Measure the last closed hourly bar against the
# mean and standard deviation of the `lookback` closes before it (a z-score) and buy the stretch.
#
# THE EVIDENCE. None of the first run's crypto strategies showed a measured edge after costs, so
# this is a classic idea on trial, not a finding. What IS measured is the cost: Alpaca crypto
# charges 0.25% to take and 0.15% to make, so a market round trip costs 0.5%. The seed therefore
# also demands that the mean sits at least min_gap_pct (1%) above the price: a target well beyond
# the fees, or no trade.
#
# WHAT IT NEEDS. 1Hour bars (72 of them) and the touch for BTC/USD, ETH/USD and SOL/USD. It keeps
# no memory: a holding carries its own opened_at and average_cost.
#
# WHEN IT TRADES. Not holding the symbol, no order working in it, the last bar is fresh, and
# z <= -z_entry with the mean at least min_gap_pct above the close: market buy of notional_usd,
# capped by the order limit, the position limit and free cash less 2%.
#
# HOW IT EXITS. It market-sells the whole holding when z >= 0 (back at the mean), when it has
# been held max_hold_hours, or when the bid is stop_pct below average_cost.

import math
from datetime import datetime, timezone

NEEDS = {
    "venue": "alpaca",
    "horizon": "hour",
    "style": "reversion",
    "symbols": ["BTC/USD", "ETH/USD", "SOL/USD"],
    "bars": {"timeframe": "1Hour", "limit": 72},
    "wake_minutes": 15,
}
PARAMS = {"lookback": 24, "z_entry": 2.0, "min_gap_pct": 1.0, "notional_usd": 40.0, "max_hold_hours": 12, "stop_pct": 3.0}
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


def _hours_between(earlier, later):
    start, end = _when(earlier), _when(later)
    return None if start is None or end is None else (end - start).total_seconds() / 3600.0


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
    lookback = max(2, int(_num(p.get("lookback"), 24)))
    z_entry, gap_pct = _num(p.get("z_entry"), 2.0), _num(p.get("min_gap_pct"), 1.0)
    stop_pct, max_hold = _num(p.get("stop_pct"), 3.0), _num(p.get("max_hold_hours"), 12.0)
    bars, quotes = ctx.get("bars") or {}, ctx.get("quotes") or {}
    held = {x.get("symbol"): x for x in ctx.get("positions") or [] if isinstance(x, dict) and _num(x.get("quantity")) > 0}
    working = {o.get("symbol") for o in ctx.get("open_orders") or [] if isinstance(o, dict)}

    intents, notes, spent = [], [], 0.0
    for symbol in NEEDS["symbols"]:
        rows = [b for b in bars.get(symbol) or [] if isinstance(b, dict) and _num(b.get("c")) > 0]
        closes = [_num(b.get("c")) for b in rows]
        z = mean = None
        if len(closes) >= lookback + 1:
            window = closes[-lookback - 1:-1]
            mean = sum(window) / lookback
            sd = math.sqrt(sum((c - mean) ** 2 for c in window) / lookback)
            z = (closes[-1] - mean) / sd if sd > 0 else None
        position = held.get(symbol)
        if position is not None:
            if symbol in working:
                notes.append(f"{symbol}: an order is already working")
                continue
            cost = _num(position.get("average_cost"))
            price = _num((quotes.get(symbol) or {}).get("bid")) or _num(position.get("mark")) or (closes[-1] if closes else 0.0)
            loss_pct = (1.0 - price / cost) * 100.0 if cost > 0 and price > 0 else 0.0
            age = _hours_between(position.get("opened_at"), ctx.get("now"))
            why = None
            if loss_pct >= stop_pct:
                why = f"stop: the bid {price:.2f} is {loss_pct:.1f}% under the average cost {cost:.2f} (limit {stop_pct:.1f}%)"
            elif z is not None and z >= 0:
                why = f"target reached: the hourly close {closes[-1]:.2f} is back at its {lookback}-bar mean {mean:.2f} (z {z:+.2f})"
            elif age is not None and age >= max_hold:
                why = f"time is up: held {age:.1f} hours against a limit of {max_hold:.0f} without reverting"
            if why:
                intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "market",
                                "reason": f"Selling all {symbol}, {why}."})
            notes.append(f"{symbol}: {'selling, ' + why if why else 'holding, z ' + (f'{z:+.2f}' if z is not None else 'unknown')}")
            continue
        if z is None:
            notes.append(f"{symbol}: only {len(closes)} usable bars, need {lookback + 1}")
            continue
        age = _hours_between(rows[-1].get("t"), ctx.get("now"))
        gap = (mean / closes[-1] - 1.0) * 100.0
        if symbol in working or age is None or age > STALE_HOURS or z > -z_entry or gap < gap_pct:
            notes.append(f"{symbol}: z {z:+.2f}, mean {gap:+.1f}% away, no entry")
            continue
        dollars = math.floor(_budget(ctx, _num(p.get("notional_usd"), 40.0), 0.0, spent) * 100.0) / 100.0
        if dollars < 1.0:
            notes.append(f"{symbol}: z {z:+.2f} is a signal but only ${max(dollars, 0.0):.2f} can be spent")
            continue
        spent += dollars
        intents.append({"symbol": symbol, "side": "buy", "notional_usd": dollars, "type": "market",
                        "reason": (f"Buying ${dollars:.2f} of {symbol}: the hourly close {closes[-1]:.2f} is {-z:.2f} standard deviations under its "
                                   f"{lookback}-bar mean {mean:.2f} (entry at {z_entry:.1f}), and the mean is {gap:.1f}% above, beyond the 0.5% round-trip fee. "
                                   f"Exit at the mean, after {max_hold:.0f} hours or {stop_pct:.1f}% down.")})
        notes.append(f"{symbol}: buying, z {z:+.2f}")
    thought = "Hourly mean reversion. " + "; ".join(notes) + "."
    return {"intents": intents, "cancels": [], "thought": thought, "memory": {}}

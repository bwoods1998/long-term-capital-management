# Corrected child of haghani-42; family: crypto-alts-reversion.
# Preserve calculated crypto limit prices rather than rounding them to cents.
# The House applies the instrument's known venue grid directionally.
# Effective parent parameters are retained; this child has no inherited record.

import math
from datetime import datetime, timezone

NEEDS = {'venue': 'alpaca',
 'horizon': 'hour',
 'style': 'maker-reversion',
 'symbols': ['SOL/USD', 'XRP/USD', 'DOGE/USD', 'LTC/USD', 'LINK/USD', 'AVAX/USD'],
 'bars': {'timeframe': '15Min', 'limit': 64},
 'wake_minutes': 15}
PARAMS = {'window': 35,
 'k': 2.0,
 'min_edge_pct': 0.8,
 'replace_pct': 0.2,
 'notional_usd': 40.0,
 'stop_pct': 3.0,
 'max_hold_hours': 24}
STALE_HOURS = 1.0  # a last bar older than this means the feed is behind: no new buys


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


def _mean_and_atr(rows, window):
    """(mean close, average true range) of the last `window` bars; needs one bar before them."""
    if len(rows) < window + 1:
        return None, None
    last = rows[-window:]
    before = [_num(b.get("c")) for b in rows[-window - 1:-1]]
    ranges = [max(_num(b.get("h")), prior) - min(_num(b.get("l")), prior) for b, prior in zip(last, before)]
    return sum(_num(b.get("c")) for b in last) / window, sum(ranges) / window


def _moved(order, target, replace_pct):
    return target <= 0 or abs(_num(order.get("limit_price")) / target - 1.0) * 100.0 > replace_pct


def _cancel(cancels, orders):
    for order in orders:
        if str(order["order_id"]) not in cancels:
            cancels.append(str(order["order_id"]))


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    window, k, replace_pct = max(2, int(_num(p.get("window"), 32))), _num(p.get("k"), 2.0), _num(p.get("replace_pct"), 0.2)
    stop_pct, max_hold, edge_pct = _num(p.get("stop_pct"), 3.0), _num(p.get("max_hold_hours"), 24.0), _num(p.get("min_edge_pct"), 0.8)
    bars, quotes, limits = ctx.get("bars") or {}, ctx.get("quotes") or {}, ctx.get("limits") or {}
    orders = [o for o in ctx.get("open_orders") or [] if isinstance(o, dict) and o.get("order_id")]
    held = {x.get("symbol"): x for x in ctx.get("positions") or [] if isinstance(x, dict) and _num(x.get("quantity")) > 0}
    want = _num(p.get("notional_usd"), 40.0)
    free = (_num(ctx.get("cash")) - sum(_num(o.get("quantity")) * _num(o.get("limit_price")) for o in orders if o.get("side") == "buy")) * 0.98

    intents, cancels, notes = [], [], []
    for symbol in NEEDS["symbols"]:
        rows = [b for b in bars.get(symbol) or [] if isinstance(b, dict) and min(_num(b.get("c")), _num(b.get("h")), _num(b.get("l"))) > 0]
        mean, atr = _mean_and_atr(rows, window)
        buys = [o for o in orders if o.get("symbol") == symbol and o.get("side") == "buy"]
        sells = [o for o in orders if o.get("symbol") == symbol and o.get("side") == "sell"]
        bid = _num((quotes.get(symbol) or {}).get("bid"))
        position = held.get(symbol)
        if position is not None:
            _cancel(cancels, buys)  # it already holds: never add
            cost, price = _num(position.get("average_cost")), bid or _num(position.get("mark"))
            loss_pct = (1.0 - price / cost) * 100.0 if cost > 0 and price > 0 else 0.0
            age = _hours_between(position.get("opened_at"), ctx.get("now"))
            why = None
            if loss_pct >= stop_pct:
                why = f"stop: the bid {price:.2f} is {loss_pct:.1f}% under the average cost {cost:.2f} (limit {stop_pct:.1f}%)"
            elif age is not None and age >= max_hold:
                why = f"time is up: held {age:.1f} hours against a limit of {max_hold:.0f} without reaching the mean"
            if why:
                _cancel(cancels, sells)
                intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "market",
                                "reason": f"Market-selling all {symbol} and cancelling the resting sell, {why}."})
                notes.append(f"{symbol}: selling, {why}")
            elif mean is None:
                notes.append(f"{symbol}: holding, too few bars to price the exit")
            elif sells:
                stale = [o for o in sells if _moved(o, mean, replace_pct)] + sells[1:]
                _cancel(cancels, stale)
                notes.append(f"{symbol}: holding, the sell at the mean {'is being moved' if stale else 'rests'} near {mean:.2f}")
            else:
                intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "limit", "limit_price": mean,
                                "reason": (f"Resting a limit sell of all {symbol} at {mean:.2f}, the mean of the last {window} 15-minute closes: "
                                           f"bought at {cost:.2f}, the trade is over when the price is back at its mean.")})
                notes.append(f"{symbol}: holding, resting the exit at {mean:.2f}")
            continue
        _cancel(cancels, sells)  # nothing held: a leftover sell has no purpose
        if mean is None:
            _cancel(cancels, buys)
            notes.append(f"{symbol}: only {len(rows)} usable bars, need {window + 1}")
            continue
        target = min(mean - k * atr, mean * (1.0 - edge_pct / 100.0))
        if buys:
            stale = [o for o in buys if _moved(o, target, replace_pct)] + buys[1:]
            _cancel(cancels, stale)
            notes.append(f"{symbol}: the dip bid {'is being moved' if stale else 'rests'} near {target:.2f}")
            continue
        age = _hours_between(rows[-1].get("t"), ctx.get("now"))
        dollars = math.floor(min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want), free) * 100.0) / 100.0
        if age is None or age > STALE_HOURS or target <= 0 or bid <= 0 or target >= bid or dollars < 1.0:
            notes.append(f"{symbol}: no bid placed (dip price {target:.2f}, bid {bid:.2f}, ${max(dollars, 0.0):.2f} spendable)")
            continue
        free -= dollars
        intents.append({"symbol": symbol, "side": "buy", "notional_usd": dollars, "type": "limit", "limit_price": target,
                        "reason": (f"Resting a limit buy of ${dollars:.2f} of {symbol} at {target:.2f}: {(1.0 - target / mean) * 100.0:.1f}% under the "
                                   f"{window}-bar mean {mean:.2f} ({k:.1f} x the average range {atr:.2f}). It fills only on a sharp dip, as a maker; exit at the mean.")})
        notes.append(f"{symbol}: resting a dip bid at {target:.2f}")
    thought = "Resting dip bids. " + "; ".join(notes) + "."
    return {"intents": intents[:8], "cancels": cancels[:20], "thought": thought, "memory": {}}

# crypto-pairs: trade the ETH/BTC ratio back toward its three-day mean, long only. When ETH is
# cheap against BTC hold ETH, when BTC is cheap against ETH hold BTC, otherwise hold cash.
#
# THE IDEA. ETH and BTC move together, so their ratio r = ETH close / BTC close is steadier than
# either price. Measure the last hourly r against the mean and standard deviation of the
# `lookback` (72) ratios before it. A z of -2 says ETH has fallen behind BTC and tends to catch
# up; +2 says the reverse. A textbook pair trade shorts the rich coin too; this account cannot
# short, so it holds only the cheap coin and carries the market's direction as a risk, with a
# hard stop for that reason.
#
# THE EVIDENCE. The first run measured no crypto edge after costs: this is an idea on trial. The
# measured part is the fee, 0.25% to take and 0.5% a round trip, so the seed also demands that
# the ratio sits at least min_gap_pct (1%) from its mean before it pays to trade.
#
# WHAT IT NEEDS. 1Hour bars (100) and the touch for ETH/USD and BTC/USD; the two series are
# matched bar by bar on their timestamps. No memory.
#
# WHEN IT TRADES. Flat in both coins, no order working, fresh bars: z <= -z_entry buys ETH,
# z >= +z_entry buys BTC, a market order of notional_usd capped by the order limit, the position
# limit and free cash less 2%. One position at a time, never both.
#
# HOW IT EXITS. It market-sells the whole holding when the ratio is back within z_exit (0.5) of
# its mean or has gone through it (holding ETH: z >= -z_exit; holding BTC: z <= +z_exit), or when
# the bid is stop_pct (4%) under average_cost.

import math
from datetime import datetime, timezone

NEEDS = {
    "venue": "alpaca",
    "horizon": "hour",
    "style": "pairs",
    "symbols": ["ETH/USD", "BTC/USD"],
    "bars": {"timeframe": "1Hour", "limit": 100},
    "wake_minutes": 30,
}
PARAMS = {"lookback": 72, "z_entry": 2.0, "z_exit": 0.5, "min_gap_pct": 1.0, "stop_pct": 4.0, "notional_usd": 50.0}
ETH, BTC = "ETH/USD", "BTC/USD"
STALE_HOURS = 3.0  # a last matched bar older than this means the feed is behind: no new buys


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


def _ratio_z(bars, lookback):
    """(z, last ratio, mean ratio, time of the last matched bar), or None when there are too few
    hours on which both coins have a bar."""
    closes = {}
    for symbol in (ETH, BTC):
        closes[symbol] = {str(b.get("t")): _num(b.get("c")) for b in bars.get(symbol) or [] if isinstance(b, dict) and _num(b.get("c")) > 0}
    shared = sorted(set(closes[ETH]) & set(closes[BTC]))
    if len(shared) < lookback + 1:
        return None
    ratios = [closes[ETH][t] / closes[BTC][t] for t in shared]
    window = ratios[-lookback - 1:-1]
    mean = sum(window) / lookback
    sd = math.sqrt(sum((r - mean) ** 2 for r in window) / lookback)
    return ((ratios[-1] - mean) / sd, ratios[-1], mean, shared[-1]) if sd > 0 else None


def decide(ctx):
    p = {**PARAMS, **(ctx.get("params") or {})}
    lookback = max(2, int(_num(p.get("lookback"), 72)))
    z_entry, z_exit = _num(p.get("z_entry"), 2.0), _num(p.get("z_exit"), 0.5)
    stop_pct, gap_pct, want = _num(p.get("stop_pct"), 4.0), _num(p.get("min_gap_pct"), 1.0), _num(p.get("notional_usd"), 50.0)
    quotes, limits = ctx.get("quotes") or {}, ctx.get("limits") or {}
    held = [x for x in ctx.get("positions") or [] if isinstance(x, dict) and x.get("symbol") in (ETH, BTC) and _num(x.get("quantity")) > 0]
    orders = [o for o in ctx.get("open_orders") or [] if isinstance(o, dict)]
    working = {o.get("symbol") for o in orders}
    signal = _ratio_z(ctx.get("bars") or {}, lookback)
    z_text = f"z {signal[0]:+.2f}" if signal else "z unknown (too few matched bars)"

    intents, notes = [], []
    for position in held:
        symbol = position["symbol"]
        if symbol in working:
            notes.append(f"{symbol}: an order is already working")
            continue
        cost = _num(position.get("average_cost"))
        price = _num((quotes.get(symbol) or {}).get("bid")) or _num(position.get("mark"))
        loss_pct = (1.0 - price / cost) * 100.0 if cost > 0 and price > 0 else 0.0
        why = None
        if loss_pct >= stop_pct:
            why = f"stop: the bid {price:.2f} is {loss_pct:.1f}% under the average cost {cost:.2f} (limit {stop_pct:.1f}%)"
        elif signal and (signal[0] >= -z_exit if symbol == ETH else signal[0] <= z_exit):
            why = f"the ETH/BTC ratio {signal[1]:.5f} is back at its {lookback}-hour mean {signal[2]:.5f} (z {signal[0]:+.2f}, exit inside {z_exit:.1f})"
        if why:
            intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "market",
                            "reason": f"Selling all {symbol} to cash, {why}."})
        notes.append(f"{symbol}: {'selling, ' + why if why else 'holding, ' + z_text}")
    if held or working:
        return {"intents": intents, "cancels": [], "thought": "ETH/BTC pair. " + "; ".join(notes or ["an order is working, waiting"]) + ".", "memory": {}}
    if not signal:
        return {"intents": [], "cancels": [], "thought": f"ETH/BTC pair: fewer than {lookback + 1} hours with both coins, staying in cash.", "memory": {}}

    z, ratio, mean, last_t = signal
    now, last_bar = _when(ctx.get("now")), _when(last_t)
    fresh = now is not None and last_bar is not None and (now - last_bar).total_seconds() / 3600.0 <= STALE_HOURS
    gap = abs(ratio / mean - 1.0) * 100.0
    symbol = ETH if z <= -z_entry else BTC if z >= z_entry else None
    if symbol is None or not fresh or gap < gap_pct:
        return {"intents": [], "cancels": [], "memory": {},
                "thought": f"ETH/BTC pair: ratio {ratio:.5f} against a mean of {mean:.5f}, z {z:+.2f}, {gap:.1f}% apart. No entry (needs |z| of {z_entry:.1f} and {gap_pct:.1f}%)."}
    resting = sum(_num(o.get("quantity")) * _num(o.get("limit_price")) for o in orders if o.get("side") == "buy")
    free = (_num(ctx.get("cash")) - resting) * 0.98  # 2% headroom covers the 0.25% fee
    dollars = math.floor(min(want, _num(limits.get("max_order_usd"), want), _num(limits.get("max_position_usd"), want), free) * 100.0) / 100.0
    if dollars < 1.0:
        return {"intents": [], "cancels": [], "memory": {}, "thought": f"ETH/BTC pair: z {z:+.2f} is a signal but only ${max(dollars, 0.0):.2f} can be spent."}
    cheap, rich = ("ETH", "BTC") if symbol == ETH else ("BTC", "ETH")
    intent = {"symbol": symbol, "side": "buy", "notional_usd": dollars, "type": "market",
              "reason": (f"Buying ${dollars:.2f} of {symbol}: the ETH/BTC ratio {ratio:.5f} is {abs(z):.2f} standard deviations "
                         f"{'under' if symbol == ETH else 'over'} its {lookback}-hour mean {mean:.5f} ({gap:.1f}% apart), so {cheap} is cheap against {rich}. "
                         f"Exit when z is inside {z_exit:.1f} or {stop_pct:.1f}% down.")}
    return {"intents": [intent], "cancels": [], "thought": f"ETH/BTC pair: z {z:+.2f}, {cheap} is cheap against {rich}; buying {symbol}.", "memory": {}}

"""House starter for the crypto family: hourly mean reversion on Coinbase spot.

Every run: for each symbol, take the last `lookback` hourly closes, compute the z-score of the
latest close against their mean and standard deviation, and when the market has fallen more
than `z_entry` standard deviations below its mean with no position held, buy at the ask with a
stop `stop_pct` below, a target at the mean, and a time stop of `holding_hours`. Long only: the
mandate allows no shorting. The floor caps a live desk's size at its learning size whatever
`notional_usd` says.

The desk owns this file: read the record with strategy_report, change what is wrong, and
redeploy. Params: symbols, lookback, z_entry, stop_pct, holding_hours, notional_usd, max_intents.
"""

import math

DEFAULTS = {
    "symbols": ["BTC-USD", "ETH-USD", "SOL-USD"],
    "lookback": 24,
    "z_entry": 2.0,
    "stop_pct": 0.02,
    "holding_hours": 12,
    "notional_usd": None,
    "max_intents": 1,
}


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    held = {str(x.get("symbol")) for x in (ctx.get("positions") or [])}
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 25.0)
    intents = []
    scores = []
    for symbol in p["symbols"]:
        if symbol in held:
            continue
        bars = kit.bars(symbol, "1h", int(p["lookback"]) + 1) or []
        closes = [_num(b.get("close")) for b in bars if _num(b.get("close"))]
        if len(closes) < int(p["lookback"]):
            kit.say(f"{symbol}: only {len(closes)} bars")
            continue
        window = closes[-int(p["lookback"]) :]
        mean = sum(window) / len(window)
        sd = math.sqrt(sum((c - mean) ** 2 for c in window) / max(1, len(window) - 1))
        last = closes[-1]
        if sd <= 0:
            continue
        z = (last - mean) / sd
        scores.append((z, symbol, mean, last))
        if z > -float(p["z_entry"]):
            continue
        quote = kit.quote(symbol) or {}
        ask = _num(quote.get("ask")) or _num(quote.get("last"))
        if not ask:
            continue
        quantity = notional / ask
        if quantity <= 0:
            continue
        intents.append(
            {
                "instrument": {"asset_class": "crypto", "symbol": symbol},
                "side": "buy",
                "quantity": f"{quantity:.6f}",
                "order_type": "limit",
                "limit_price": f"{ask:.2f}",
                "rationale": (
                    f"{symbol} closed {z:.2f} standard deviations below its {p['lookback']}-hour mean ({last:,.2f} vs {mean:,.2f}); "
                    f"mean reversion at the ask, target the mean, stop {float(p['stop_pct']) * 100:.1f}% below, {p['holding_hours']}h time stop."
                ),
                "target_price": f"{mean:.2f}",
                "stop_price": f"{ask * (1.0 - float(p['stop_pct'])):.2f}",
                "holding_period_hours": int(p["holding_hours"]),
            }
        )
        if len(intents) >= int(p["max_intents"]):
            break
    kit.say("z-scores: " + ", ".join(f"{s} {z:+.2f}" for z, s, _, _ in scores))
    return {"intents": intents, "notes": "z-scores " + ", ".join(f"{s} {z:+.2f}" for z, s, _, _ in scores)}

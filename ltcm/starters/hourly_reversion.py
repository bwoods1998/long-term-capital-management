"""House starter for the crypto family: hourly mean reversion on Coinbase spot.

Every run: for each symbol, take the last `lookback` hourly closes, compute the z-score of the
latest close against their mean and standard deviation, and when the market has fallen more
than `z_entry` standard deviations below its mean with no position held, buy at the ask with a
stop `stop_pct` below, a target at the mean, and a time stop of `holding_hours`. Long only: the
mandate allows no shorting. The floor caps a live desk's size at its learning size whatever
`notional_usd` says.

Entry also requires a fresh account fee tier and a target net of two taker fees that clears
at least 1% plus the current spread and a 0.2% slippage cushion. Existing positions and working
buys are skipped. Prices round to product ticks; entry orders expire after two minutes.

The desk owns this file: read the record with strategy_report, change what is wrong, and
redeploy. Params: symbols, lookback, z_entry, stop_pct, holding_hours, notional_usd, max_intents,
min_margin, slippage_buffer. A forecast passing the fee hurdle is not proof of a profitable edge.
The fee-aware revision must earn a new forward record before promotion.
"""

import math

DEFAULTS = {
    # "top:N" is the N most traded USD products on Coinbase right now; the list is the fallback
    # when the venue's listing cannot be read.
    "symbols": "top:15",
    "fallback_symbols": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "LINK-USD", "AVAX-USD", "ADA-USD", "LTC-USD", "BCH-USD"],
    "lookback": 24,
    "z_entry": 2.0,
    "stop_pct": 0.02,
    "holding_hours": 12,
    "notional_usd": None,
    "max_intents": 1,
    "min_margin": 0.01,
    "slippage_buffer": 0.002,
}


def _num(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _symbols(kit, spec, fallback, increments):
    """A list of product ids, or "top:N": the N most traded USD products on Coinbase right now,
    so the universe is the venue's, not a hand-written list."""
    if isinstance(spec, str) and spec.startswith("top:"):
        try:
            rows = kit.products(int(spec.split(":", 1)[1]))
        except Exception:
            rows = []
        symbols = [r["symbol"] for r in rows if r.get("symbol")]
        for row in rows:
            tick = _num(row.get("quote_increment"))
            if row.get("symbol") and tick is not None and tick > 0:
                increments[row["symbol"]] = tick
        if symbols:
            return symbols
        return list(fallback)
    return list(spec or fallback)


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    fees = (ctx.get("fee_rates") or {}).get("coinbase") or {}
    taker, age = _num(fees.get("taker")), _num(fees.get("age_seconds"))
    if taker is None or not 0 <= taker <= 0.1 or age is None or not 0 <= age <= 900:
        kit.say("entries blocked: current Coinbase fee tier unavailable")
        return {"intents": [], "notes": "entries blocked: current Coinbase fee tier unavailable"}
    # Marketable entry and exit both pay taker. Target is a forecast, not guaranteed profit.
    margin = max(DEFAULTS["min_margin"], _num(p.get("min_margin"), 0) or 0)
    buffer = max(DEFAULTS["slippage_buffer"], _num(p.get("slippage_buffer"), 0) or 0)
    held = {str(x.get("symbol")) for x in (ctx.get("positions") or [])}
    pending = {str(x.get("symbol")) for x in (ctx.get("open_orders") or []) if x.get("side") == "buy"}
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 25.0)
    intents = []
    scores = []
    increments = {}
    for symbol in _symbols(kit, p["symbols"], DEFAULTS["fallback_symbols"], increments):
        if symbol in held or symbol in pending:
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
        bid = _num(quote.get("bid"))
        if not ask or not bid or bid <= 0 or ask < bid:
            continue
        tick = increments.get(symbol, 0.01)
        # A marketable buy must round UP, not below the ask into an unintended resting order.
        ask = math.ceil(ask / tick - 1e-9) * tick
        target = math.floor(mean / tick + 1e-9) * tick
        # Include the current book spread as well as a slippage cushion and both fees.
        net_move = (target * (1.0 - taker)) / (ask * (1.0 + taker)) - 1.0
        hurdle = margin + buffer + (ask - bid) / ask
        if net_move < hurdle:
            kit.say(f"{symbol}: no entry, target net {net_move * 100:.2f}% < required {hurdle * 100:.2f}% after {taker * 100:.2f}% fees each way")
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
                "limit_price": f"{ask:.12f}".rstrip("0").rstrip("."),
                "expire_after_seconds": 120,
                "rationale": (
                    f"{symbol} closed {z:.2f} standard deviations below its {p['lookback']}-hour mean ({last:,.2f} vs {mean:,.2f}); "
                    f"Buy {quantity:.6f} {symbol} on mean reversion at the ask; target net move {net_move * 100:.2f}% after "
                    f"{taker * 100:.2f}% fees each way, required {hurdle * 100:.2f}% including spread/slippage. "
                    f"Target the mean, stop {float(p['stop_pct']) * 100:.1f}% below, {p['holding_hours']}h time stop."
                ),
                "target_price": f"{target:.12f}".rstrip("0").rstrip("."),
                "stop_price": f"{math.floor(ask * (1.0 - float(p['stop_pct'])) / tick) * tick:.12f}".rstrip("0").rstrip("."),
                "holding_period_hours": int(p["holding_hours"]),
            }
        )
        if len(intents) >= int(p["max_intents"]):
            break
    kit.say("z-scores: " + ", ".join(f"{s} {z:+.2f}" for z, s, _, _ in scores))
    return {"intents": intents, "notes": "z-scores " + ", ".join(f"{s} {z:+.2f}" for z, s, _, _ in scores)}

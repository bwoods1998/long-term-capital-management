"""House starter (the arena, Sept 18, 2026): fade crowded funding on Coinbase's perpetuals.

When a perp's funding rate sits far above its recent settlements the longs are paying to stay
long: the crowd is one way and the premium tends to bleed back. Every run: `kit.derivs` gives
each symbol's OKX funding rate, its z-score against the trailing thirty settlements, Hyperliquid's
and Kraken's rates and Deribit's implied vol. When the z-score is beyond `z_entry` and the rate
beyond `rate_entry` (per 8 hours), enter one Coinbase CDE perp contract against the crowd at the
touch: short when funding is high, long when it is negative. The target is a move of `target_pct`
(or the implied vol's expected move over `holding_hours`, whichever is larger) and the stop
`stop_mult` times that beyond entry; `holding_hours` is the time stop. The entry must clear the
round trip's contract fees, the spread and `min_margin`. Params: z_entry, rate_entry, symbols,
holding_hours, target_pct, stop_mult, contracts, min_margin, min_contract_usd, max_contract_usd,
max_position_pct, fee_per_contract, min_volume_usd, max_intents.
"""

import math

DEFAULTS = {
    "z_entry": 2.0,
    "rate_entry": 0.0002,
    "symbols": ["BTC", "ETH", "SOL"],
    "holding_hours": 4,
    "target_pct": 0.004,
    "stop_mult": 1.5,
    "contracts": 1,
    "min_margin": 0.001,
    "min_contract_usd": 60.0,
    "max_contract_usd": 900.0,
    "max_position_pct": 0.6,
    "fee_per_contract": 0.20,
    "min_volume_usd": 250000.0,
    "max_intents": 1,
}


def _num(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _tick(value, default=0.01):
    tick = _num(value)
    return tick if tick and tick > 0 else default


def _fmt(value):
    return f"{value:.12f}".rstrip("0").rstrip(".")


def _perps(kit, p, equity):
    try:
        rows = kit.futures() or []
    except Exception:
        rows = []
    cap = float(p["max_contract_usd"])
    if equity is not None and equity > 0:
        cap = min(cap, equity * float(p["max_position_pct"]))
    out = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        root = str(row.get("root") or symbol.split("-")[0]).upper()
        if not symbol.endswith("-CDE") or not row.get("perpetual"):
            continue
        usd = _num(row.get("contract_usd"))
        if usd is None or usd < float(p["min_contract_usd"]) or usd > cap:
            continue
        if (_num(row.get("volume_usd"), 0) or 0) < float(p["min_volume_usd"]):
            continue
        if root not in out or (_num(row.get("volume_usd"), 0) or 0) > (_num(out[root].get("volume_usd"), 0) or 0):
            out[root] = row
    return out


def signal(row, p):
    """(direction, z, rate_8h, dvol) for one derivs row, direction +1 long, -1 short, 0 none."""
    z = _num(row.get("funding_z"))
    okx = row.get("okx") or {}
    hl = row.get("hyperliquid") or {}
    rate = _num(okx.get("rate"))
    if rate is None and _num(hl.get("rate")) is not None:
        rate = _num(hl.get("rate")) * 8.0
    dvol = _num(row.get("dvol"))
    if z is None or rate is None:
        return 0, z, rate, dvol
    if z >= float(p["z_entry"]) and rate >= float(p["rate_entry"]):
        return -1, z, rate, dvol
    if z <= -float(p["z_entry"]) and rate <= -float(p["rate_entry"]):
        return 1, z, rate, dvol
    return 0, z, rate, dvol


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    rates = (ctx.get("fee_rates") or {}).get("coinbase") or {}
    fee = max(float(DEFAULTS["fee_per_contract"]), _num(p.get("fee_per_contract"), 0) or 0, _num(rates.get("future_contract"), 0) or 0)
    margin = max(float(DEFAULTS["min_margin"]), _num(p.get("min_margin"), 0) or 0)
    equity = _num(ctx.get("equity_usd"))
    held = {str(x.get("symbol")).upper(): _num(x.get("quantity"), 0) for x in (ctx.get("positions") or []) if str(x.get("asset_class") or "") == "future"}
    working = {str(x.get("symbol") or x.get("market_id") or "").upper() for x in (ctx.get("open_orders") or []) if str(x.get("asset_class") or "") == "future"}
    contracts = max(1, int(_num(p.get("contracts"), 1) or 1))
    symbols = [str(s).upper() for s in (p.get("symbols") or DEFAULTS["symbols"])]
    try:
        snap = kit.derivs(tuple(symbols)) or []
    except Exception as exc:
        kit.say(f"derivs failed ({type(exc).__name__})")
        return {"intents": [], "notes": "no funding snapshot"}
    perps = _perps(kit, p, equity)
    intents, notes = [], []
    for row in snap:
        root = str(row.get("symbol") or "").upper()
        direction, z, rate, dvol = signal(row, p)
        notes.append(f"{root} z {z if z is None else round(z, 2)} rate {rate if rate is None else f'{rate * 100:.4f}%'}")
        perp = perps.get(root)
        if direction == 0 or perp is None:
            continue
        symbol = str(perp["symbol"]).upper()
        if held.get(symbol) or symbol in working:
            continue
        size = _num(perp.get("contract_size"))
        if not size or size <= 0:
            continue
        quote = kit.quote(symbol, "future") or {}
        bid, ask = _num(quote.get("bid")), _num(quote.get("ask"))
        if not bid or not ask or bid <= 0 or ask < bid:
            continue
        tick = _tick(perp.get("quote_increment"))
        side = "buy" if direction > 0 else "sell"
        entry = (math.ceil(ask / tick - 1e-9) + 1) * tick if side == "buy" else (math.floor(bid / tick + 1e-9) - 1) * tick
        entry = round(entry, 10)
        if entry <= 0:
            continue
        expected = (dvol / 100.0) * math.sqrt(float(p["holding_hours"]) / 8760.0) * 0.5 if dvol else 0.0
        move = max(float(p["target_pct"]), expected)
        notional = entry * size * contracts
        hurdle = (2.0 * fee * contracts) / notional + (ask - bid) / entry + margin
        if move < hurdle:
            kit.say(f"{symbol}: target {move * 100:.2f}% under the hurdle {hurdle * 100:.2f}%")
            continue
        target = entry * (1.0 + move) if side == "buy" else entry * (1.0 - move)
        stop = entry * (1.0 - move * float(p["stop_mult"])) if side == "buy" else entry * (1.0 + move * float(p["stop_mult"]))
        target = (math.floor if side == "buy" else math.ceil)(target / tick + (1e-9 if side == "buy" else -1e-9)) * tick
        stop = (math.floor if side == "buy" else math.ceil)(stop / tick + (1e-9 if side == "buy" else -1e-9)) * tick
        intents.append(
            {
                "instrument": {"asset_class": "future", "symbol": symbol, "market_id": symbol, "venue": "coinbase"},
                "side": side,
                "quantity": str(contracts),
                "order_type": "limit",
                "limit_price": _fmt(entry),
                "expire_after_seconds": 120,
                "rationale": (
                    f"{root} funding {rate * 100:.4f}% per 8h is {z:+.2f} standard deviations from its last thirty settlements"
                    f"{f', implied vol {dvol:.0f}' if dvol else ''}: the crowd is {'long and paying' if side == 'sell' else 'short and paying'}. "
                    f"{'Sell short' if side == 'sell' else 'Buy'} {contracts} {symbol} contract(s) ({size:g} each, ~${notional:,.0f}) at the touch, "
                    f"target {move * 100:.2f}% against a hurdle of {hurdle * 100:.2f}%, stop {move * float(p['stop_mult']) * 100:.2f}% beyond entry, "
                    f"{p['holding_hours']}h time stop. Wrong if the record after fees is not positive."
                ),
                "target_price": _fmt(target),
                "stop_price": _fmt(stop),
                "holding_period_hours": int(p["holding_hours"]),
            }
        )
        if len(intents) >= int(p["max_intents"]):
            break
    kit.say("; ".join(notes)[:300])
    return {"intents": intents, "notes": f"{len(perps)} perps, {len(intents)} entry(ies); " + "; ".join(notes)[:200]}

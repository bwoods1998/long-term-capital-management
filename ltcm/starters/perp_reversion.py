"""House starter for the crypto family, futures side: mean reversion on Coinbase's CDE
perpetual-style contracts, long and short (leap: futures, Sept 17, 2026).

Why futures: the account pays 0.5% maker / 0.9% taker on spot, which no hourly signal clears,
and about twenty cents a contract on CDE futures (UNVERIFIED until the first fill), which is a
few hundredths of a percent of a $200-800 contract. The same reversion signal that lost after
spot fees is worth testing here, and a short is as easy as a long.

Every run: the venue's perpetual contracts whose one-contract notional fits the desk
(`min_contract_usd`..`max_contract_usd`, and under `max_position_pct` of the desk's equity read
from the context), by volume; for each, the z-score of the last five-minute close against the
last `lookback` closes; when |z| >= `z_entry` and nothing is held or working in it, enter
`contracts` (1) against the move at the touch: buy the ask after a drop, sell the bid after a
spike, with a target at the mean, a stop `stop_pct` beyond entry and a `holding_hours` time
stop, all kept by the floor. The entry must clear the round trip's fees, the spread and a
`min_margin` of the notional, or nothing is placed. Entries expire after two minutes.

Params: contracts, lookback, interval, z_entry, stop_pct, holding_hours, max_intents,
min_margin, min_contract_usd, max_contract_usd, max_position_pct, fee_per_contract (a floor;
the context's rate is used when higher), symbols (a list to restrict the universe).
A forecast clearing the hurdle is not proof of edge: the record decides size.
"""

import math

DEFAULTS = {
    "contracts": 1,
    "lookback": 36,
    "interval": "5m",
    "z_entry": 2.0,
    "stop_pct": 0.012,
    "holding_hours": 4,
    "max_intents": 1,
    "min_margin": 0.002,
    "min_contract_usd": 60.0,
    "max_contract_usd": 900.0,
    "max_position_pct": 0.6,
    "fee_per_contract": 0.20,
    "symbols": None,
    "min_volume_usd": 250000.0,
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


def _universe(kit, p, equity):
    """Perpetual contracts the desk can hold one of, most traded first."""
    try:
        rows = kit.futures() or []
    except Exception:
        rows = []
    allow = set(str(x).upper() for x in (p.get("symbols") or []) if x) or None
    cap = float(p["max_contract_usd"])
    if equity is not None and equity > 0:
        cap = min(cap, equity * float(p["max_position_pct"]))
    out = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol.endswith("-CDE") or (allow and symbol not in allow):
            continue
        if not row.get("perpetual") and not allow:
            continue  # a dated contract expires under the position; the perps roll by funding
        usd = _num(row.get("contract_usd"))
        if usd is None or usd < float(p["min_contract_usd"]) or usd > cap:
            continue
        if (_num(row.get("volume_usd"), 0) or 0) < float(p["min_volume_usd"]):
            continue
        out.append(row)
    out.sort(key=lambda r: -(_num(r.get("volume_usd"), 0) or 0))
    return out


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
    lookback = max(8, int(_num(p.get("lookback"), 36) or 36))
    intents, scores = [], []
    universe = _universe(kit, p, equity)
    if not universe:
        kit.say("no perpetual contract fits the desk; nothing to price")
    for row in universe:
        symbol = str(row["symbol"]).upper()
        if held.get(symbol) or symbol in working:
            continue
        size = _num(row.get("contract_size"))
        if not size or size <= 0:
            continue
        bars = kit.bars(symbol, str(p["interval"]), lookback + 1, "future") or []
        closes = [_num(b.get("close")) for b in bars if _num(b.get("close"))]
        if len(closes) < lookback:
            kit.say(f"{symbol}: only {len(closes)} bars")
            continue
        window = closes[-lookback:]
        mean = sum(window) / len(window)
        sd = math.sqrt(sum((c - mean) ** 2 for c in window) / max(1, len(window) - 1))
        if sd <= 0:
            continue
        last = closes[-1]
        z = (last - mean) / sd
        scores.append((z, symbol))
        if abs(z) < float(p["z_entry"]):
            continue
        quote = kit.quote(symbol, "future") or {}
        bid, ask = _num(quote.get("bid")), _num(quote.get("ask"))
        if not bid or not ask or bid <= 0 or ask < bid:
            continue
        tick = _tick(row.get("quote_increment"))
        side = "buy" if z < 0 else "sell"
        # Take the touch: buy the ask after a drop, sell the bid after a spike.
        entry = math.ceil(ask / tick - 1e-9) * tick if side == "buy" else math.floor(bid / tick + 1e-9) * tick
        target = math.floor(mean / tick + 1e-9) * tick if side == "buy" else math.ceil(mean / tick - 1e-9) * tick
        move = (target - entry) if side == "buy" else (entry - target)
        notional = entry * size * contracts
        if notional <= 0:
            continue
        # Two contract fees and the spread, plus the margin, out of the move to the mean.
        hurdle = (2.0 * fee * contracts) / notional + (ask - bid) / entry + margin
        net = move / entry
        if net < hurdle:
            kit.say(f"{symbol}: no entry, move to the mean {net * 100:.2f}% < hurdle {hurdle * 100:.2f}%")
            continue
        stop = entry * (1.0 - float(p["stop_pct"])) if side == "buy" else entry * (1.0 + float(p["stop_pct"]))
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
                    f"{symbol} printed {z:+.2f} standard deviations from its {lookback}-bar {p['interval']} mean ({last:,.4g} vs {mean:,.4g}). "
                    f"{'Buy' if side == 'buy' else 'Sell short'} {contracts} contract(s) ({size:g} {row.get('root') or 'units'} each, ~${notional:,.0f}) "
                    f"on mean reversion at the touch; move to the mean {net * 100:.2f}% against a hurdle of {hurdle * 100:.2f}% "
                    f"(two ${fee:.2f} contract fees, the spread, {margin * 100:.1f}% margin). Target the mean, stop {float(p['stop_pct']) * 100:.1f}% "
                    f"beyond entry, {p['holding_hours']}h time stop. Wrong if the record after fees is not positive."
                ),
                "target_price": _fmt(target),
                "stop_price": _fmt(stop),
                "holding_period_hours": int(p["holding_hours"]),
            }
        )
        if len(intents) >= int(p["max_intents"]):
            break
    kit.say(f"{len(universe)} contract(s) in play; z-scores: " + ", ".join(f"{s} {z:+.2f}" for z, s in scores))
    return {"intents": intents, "notes": f"{len(universe)} perps priced, {len(intents)} entry(ies); " + ", ".join(f"{s} {z:+.2f}" for z, s in scores)[:200]}

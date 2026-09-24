import datetime
import json
import math
import statistics

NEEDS = {
    "venue": "kalshi",
    "horizon": "hour",
    "style": "btc-15m-spot-strike-probability",
    "series": ["KXBTC15M"],
    "max_hours_to_close": 1,
    "wake_minutes": 5,
    "observe": {"symbols": ["BTC/USD"]},
    "bars": {"timeframe": "5Min", "limit": 48},
}
PARAMS = {}


def decide(ctx):
    intents = []
    previous = ctx.get("memory") or {}
    blocked = list(previous.get("blocked_markets", []))
    seen = list(previous.get("seen_conflicts", []))
    last_market = previous.get("last_entry_market")
    for outcome in ctx.get("recent_order_outcomes", []):
        reason = str(outcome.get("reason", "")).lower()
        if outcome.get("status") != "refused" or outcome.get("submitted_to_venue") is not False:
            continue
        if not any(text in reason for text in (
            "house already holds or bids",
            "one account cannot hold both",
            "house's own resting order",
        )):
            continue
        fingerprint = json.dumps(outcome, sort_keys=True, separators=(",", ":"))
        if fingerprint in seen:
            continue
        market = outcome.get("market") or last_market
        if not market:
            continue
        if market not in blocked:
            blocked.append(market)
        seen.append(fingerprint)

    # Keep only recent short-lived markets and compact refusal identities.
    # Fingerprints are capped by total characters as well as count to bound memory.
    blocked = blocked[-32:]
    seen = seen[-12:]
    while seen and sum(len(value) for value in seen) > 3500:
        seen.pop(0)
    memory = {
        "blocked_markets": blocked,
        "seen_conflicts": seen,
        "last_entry_market": last_market,
    }
    if ctx.get("positions") or any(o.get("side") == "buy" for o in ctx.get("open_orders", [])):
        return {"intents": intents, "cancels": [], "thought": "Avoid adding exposure while a position or buy order is outstanding.", "memory": memory}

    bars = ctx.get("observed", {}).get("bars", {}).get("BTC/USD", [])
    closes = [float(b.get("c", 0)) for b in bars if float(b.get("c", 0)) > 0]
    if len(closes) < 12:
        return {"intents": intents, "cancels": [], "thought": "Insufficient observed BTC bars to estimate short-horizon dispersion.", "memory": memory}

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i] > 0 and closes[i - 1] > 0]
    if len(log_returns) < 10:
        return {"intents": intents, "cancels": [], "thought": "Insufficient valid BTC returns.", "memory": memory}
    sigma_5m = max(statistics.pstdev(log_returns[-36:]), 0.00015)
    spot = closes[-1]
    rate = float(ctx.get("fees", {}).get("kalshi_taker_rate", 0.07))

    for m in ctx.get("markets", []):
        if m.get("series") != "KXBTC15M":
            continue
        if m.get("market") in blocked:
            continue
        hours = float(m.get("hours_to_close", 99))
        if not (0.001 <= hours <= 0.20):
            continue
        strike = m.get("strike")
        bid, ask = m.get("yes_bid"), m.get("yes_ask")
        if strike is None or bid is None or ask is None:
            continue
        strike = float(strike)
        bid, ask = float(bid), float(ask)
        if strike <= 0 or not (0 < bid < ask < 1) or ask - bid > 0.06:
            continue

        # Outcome is determined at market close; 5-minute return volatility scales by sqrt(time).
        z = math.log(spot / strike) / (sigma_5m * math.sqrt(max(hours * 12.0, 0.02)))
        p_yes = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        no_ask = 1.0 - bid
        choices = [(p_yes, ask, "yes"), (1.0 - p_yes, no_ask, "no")]
        best = None
        for probability, price, leg in choices:
            fee = math.ceil(rate * price * (1.0 - price) * 10000.0) / 10000.0
            edge = probability - price - fee
            if price > 0 and edge >= 0.04 and (best is None or edge > best[0]):
                best = (edge, price, fee, leg)
        if best is None:
            continue

        edge, price, fee, leg = best
        remaining = ctx.get("event_risk", {}).get("remaining_by_market_usd", {}).get(m.get("market"), 4.0)
        cap = min(4.0, float(ctx.get("limits", {}).get("max_order_usd", 4.0)), float(ctx.get("limits", {}).get("max_position_usd", 4.0)), float(ctx.get("cash", 0.0)) * 0.5, float(remaining))
        quantity = min(8, int(cap / (price + fee + 0.0001)))
        if quantity >= 1:
            intents.append({"market": m["market"], "leg": leg, "side": "buy", "quantity": quantity, "type": "market", "reason": "Buy only when a zero-drift, recent-realized-volatility spot-to-strike estimate exceeds the executable price and taker fee by at least 4 cents; exposure is capped."})
            memory["last_entry_market"] = m["market"]
            break

    return {"intents": intents, "cancels": [], "thought": "Estimate BTC close-above-strike probability from point-in-time bars; require edge after fees. Skip markets remembered from shared-account conflict refusals, without switching legs or order types to retry.", "memory": memory}

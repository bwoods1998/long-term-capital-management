"""Evidence: whether a strategy's settled record shows an edge or only luck (leap: evidence).

The floor promoted a strategy after 6 settled positions with a positive P&L and sized it up
after `earned_settled` 6 with P&L above zero. On a lopsided payoff that rule cannot tell luck from
edge. A favorite bought at 0.93 wins 7 cents or loses 93, so a run of wins is what a strategy
with no edge produces most of the time. Sept 17, 2026: at an average price of 0.93 a breakeven
favorites variant passed the old gate with probability 0.65 at 6 settled and 0.46 at 40, and a
variant losing 3 cents a contract still passed 0.53 at 6.

`passes(record)` is the gate every reader of a strategy record now uses (`Strategies.promote`,
`Strategies.size_cap`, the Foundry's fast-track). Passing starts a live strategy's size ramp; it
does not jump to full size (`full_size_multiple`, `strategies.earned_ramp`):

* **A lopsided event strategy** (every settled position an event contract, volume-weighted
  average entry price at or above `skew_price`, 0.80) passes when it has settled at least
  `n_needed = max(40, ceil(3 / (1 - avg_price)))` positions, enough to expect three losses at
  breakeven, and the Wilson upper bound of its loss rate at `z` (0.84, one-sided 80%) is under the
  breakeven loss rate `b = 1 - avg_price - avg_fee_per_contract`.
* **Anything else** passes when it has settled at least `min_n` (25) positions over at least
  `min_days` (3) settlement days, and the 20th percentile of a day-block bootstrap of its return
  per dollar is above zero. Positions that settle on the same day share a market move, so days
  are resampled, not positions.

The trade-off is written down on purpose. At n = 80-120 a breakeven favorites variant passes about
0.18-0.26 of the time instead of 0.46-0.65, and a true +2 cent variant passes about 0.43-0.61.
Telling +2 cents from breakeven on a 1:13 payoff takes roughly 100-300 separate settlements, so a
real edge earns its size days later than it used to. That is the price of not sizing up on luck.

Pure functions, standard library only.
"""

from __future__ import annotations

import functools
import math
import random
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

DEFAULTS: dict[str, Any] = {
    "z": 0.84,
    "min_n": 25,
    "skew_price": 0.80,
    # One day is one block: a bootstrap over a single day cannot see a bad day coming. Not in the
    # Sept 17 build plan; added so 25 positions settled in one afternoon never pass.
    "min_days": 3,
    "q": 0.20,
    "resamples": 1000,
    "seed": 17,
    # Earned size is a ramp, not a step (`Strategies.size_cap`): learning size at `n_needed`
    # settlements, the desk's full order limit at `full_size_multiple` x `n_needed`, linear between.
    "full_size_multiple": 3.0,
}
#: The smallest lopsided sample: fewer than 40 settlements says nothing about a loss rate.
MIN_LOPSIDED_N = 40


def fresh_clusters(log: Any, after: int, *, families: Mapping[str, str] | None = None,
                   allowed_families: Iterable[str] | None = None) -> int:
    """Count new independent outcomes for scheduling, not partial fills or repeated strikes.
    This is a wake-up signal only; it never weakens a promotion or statistical gate."""
    from .mind import parse_outcome

    allowed = None if allowed_families is None else set(allowed_families)
    groups = set()
    for event in log.read(kind="desk.outcome", after=max(0, int(after)), limit=10000, newest=True):
        outcome = parse_outcome(event, families)
        if outcome is not None and (allowed is None or outcome.family in allowed):
            groups.add(outcome.group)
    return len(groups)


def settings(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """`strategies.evidence` from config.json merged over the defaults, numbers parsed (the
    config writes prices as strings)."""
    merged = {**DEFAULTS, **{k: v for k, v in dict(config or {}).items() if k in DEFAULTS and v is not None}}
    out: dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        try:
            out[key] = type(default)(float(merged[key])) if isinstance(default, int) else float(merged[key])
        except (TypeError, ValueError):
            out[key] = default
    return out


def wilson_upper(losses: int, n: int, z: float = 0.84) -> float:
    """The Wilson score upper bound of a loss rate: `losses` of `n` at `z` standard errors. 1.0
    with no observations, so an empty record never looks safe."""
    n = int(n)
    if n <= 0:
        return 1.0
    losses = max(0, min(int(losses), n))
    p = losses / n
    z2 = z * z
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return min(1.0, (centre + margin) / (1 + z2 / n))


def block_bootstrap_lower(
    returns_by_day: Mapping[Any, Sequence[float]] | Iterable[Sequence[float]],
    q: float = 0.20,
    n: int = 1000,
    seed: Any = 17,
) -> float | None:
    """The `q` quantile of the pooled mean return when whole days are resampled with replacement.
    Deterministic for a seed. None when there is nothing to resample."""
    groups = returns_by_day.values() if isinstance(returns_by_day, Mapping) else returns_by_day
    blocks = []
    for group in groups:
        values = [float(v) for v in group if v is not None and math.isfinite(float(v))]
        if values:
            blocks.append((sum(values), len(values)))
    if not blocks:
        return None
    return _bootstrap(tuple(blocks), float(q), max(1, int(n)), seed if isinstance(seed, (int, str)) else repr(seed))


@functools.lru_cache(maxsize=512)
def _bootstrap(blocks: tuple[tuple[float, int], ...], q: float, n: int, seed: Any) -> float:
    """The resampling itself, cached: a checkpoint describes every strategy on the floor, and a
    record that has not changed since the last one resamples to the same answer."""
    rng = random.Random(seed)
    draw = rng.random
    count = len(blocks)
    sums = [b[0] for b in blocks]
    sizes = [b[1] for b in blocks]
    means = []
    for _ in range(n):
        total = 0.0
        size = 0
        for _ in range(count):
            pick = int(draw() * count)
            total += sums[pick]
            size += sizes[pick]
        means.append(total / size)
    means.sort()
    return means[min(n - 1, max(0, int(q * (n - 1))))]


def lopsided(record: Mapping[str, Any], skew_price: float = 0.80) -> bool:
    """True for a strategy whose every settled position was an event contract bought, on
    average, at `skew_price` or more: a favorites payoff, many small wins against rare full losses."""
    price = _float(record.get("avg_entry_price"))
    return record.get("asset_class") == "event" and price is not None and price >= float(skew_price)


def lopsided_n_needed(avg_price: float) -> int:
    """Settlements before a favorites loss rate means anything: enough to expect three losses
    at breakeven, and never fewer than 40."""
    gap = max(1e-6, 1.0 - float(avg_price))
    # Rounded before the ceiling so 3 / 0.075 is 40, not 41 on a float's last digit.
    return max(MIN_LOPSIDED_N, math.ceil(round(3.0 / gap, 9)))


def assess(record: Mapping[str, Any] | None, **config: Any) -> dict[str, Any]:
    """The whole verdict on a record: `passes`, `reason`, `n_needed`, `lower` (a per-dollar lower
    bound on the return, None when it cannot be computed) and `kind` (`lopsided` or `bootstrap`)."""
    cfg = settings(config)
    record = dict(record or {})
    n = int(_float(record.get("independent_settled", record.get("settled"))) or 0)
    if lopsided(record, cfg["skew_price"]):
        price = min(0.999, float(_float(record.get("avg_entry_price")) or 0.0))
        fee = max(0.0, float(_float(record.get("avg_fee_per_contract")) or 0.0))
        losses = int(_float(record.get("losses")) or 0)
        need = lopsided_n_needed(price)
        breakeven = 1.0 - price - fee
        upper = wilson_upper(losses, n, cfg["z"])
        lower = (breakeven - upper) / (price + fee) if price + fee > 0 else None
        out = {"kind": "lopsided", "n": n, "n_needed": need, "losses": losses, "avg_entry_price": round(price, 4),
               "breakeven_loss_rate": round(breakeven, 4), "loss_rate_upper": round(upper, 4),
               "lower": None if lower is None else round(lower, 6)}
        if n < need:
            return {**out, "passes": False, "reason": f"{n} of {need} settlements at an average price of {price:.2f}: a lopsided payoff needs {need} before its loss rate means anything"}
        if upper >= breakeven:
            return {**out, "passes": False, "reason": f"{losses} losses in {n}: the loss rate could be {upper:.3f}, at or above the breakeven {breakeven:.3f}"}
        return {**out, "passes": True, "reason": f"{losses} losses in {n}: the loss rate is under {upper:.3f}, below the breakeven {breakeven:.3f}"}
    need = int(cfg["min_n"])
    days: dict[str, list[float]] = {}
    for row in record.get("returns") or ():
        try:
            day, value = row[0], float(row[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if math.isfinite(value):
            days.setdefault(str(day or ""), []).append(value)
    out = {"kind": "bootstrap", "n": n, "n_needed": need, "days": len(days), "lower": None}
    if n < need:
        return {**out, "passes": False, "reason": f"{n} of {need} settlements"}
    if len(days) < int(cfg["min_days"]):
        unit = "hour" if str(record.get("block") or "") == "hour" else "day"
        return {**out, "passes": False, "reason": f"settlements in {len(days)} {unit}(s); the bootstrap needs {int(cfg['min_days'])}"}
    # Resampled only once the count and the days are there: the bootstrap is the costly part.
    lower = block_bootstrap_lower(days, cfg["q"], int(cfg["resamples"]), cfg["seed"]) if days else None
    out["lower"] = None if lower is None else round(lower, 6)
    if lower is None or lower <= 0:
        shown = "n/a" if lower is None else f"{lower:+.4f}"
        return {**out, "passes": False, "reason": f"the {cfg['q']:.0%} bootstrap bound on return per $ is {shown}, not above zero"}
    return {**out, "passes": True, "reason": f"the {cfg['q']:.0%} bootstrap bound on return per $ is {lower:+.4f} over {len(days)} days"}


def passes(record: Mapping[str, Any] | None, *, z: float = 0.84, min_n: int = 25, **config: Any) -> tuple[bool, str, int]:
    """(ok, reason, n_needed) for a strategy record. See the module docstring for the rules."""
    verdict = assess(record, z=z, min_n=min_n, **config)
    return bool(verdict["passes"]), str(verdict["reason"]), int(verdict["n_needed"])


def lower_bound(record: Mapping[str, Any] | None, **config: Any) -> float | None:
    """The per-dollar lower bound `assess` computes: the bootstrap quantile, or for a lopsided
    record `(b - wilson_upper) / (avg_price + avg_fee)`."""
    return assess(record, **config).get("lower")


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


__all__ = ["DEFAULTS", "assess", "block_bootstrap_lower", "lopsided", "lopsided_n_needed", "lower_bound", "passes", "settings", "wilson_upper"]

"""The evidence lines, exactly as the plan states them ("Evidence: fast without fooling ourselves").

A search over tens of thousands of programs finds something that looks great on any window by chance,
so these lines are the swarm's brakes. They may be TIGHTENED on evidence; loosening one is the owner's
decision, which is why they are constants here and not settings.

THE VALIDATION LINE (a family's best program, on Validation 2025):
  - at least 100 trades on at least 60 distinct trading days;
  - mean P&L per dollar of maximum loss above zero after fees, with a one-sided t of at least 2 (the t on
    DAILY-aggregated P&L per dollar of maximum loss, `t_daily`: correlated intraday entries make a per-trade t
    overstate the evidence, the Gym's review of Sept 26);
  - a deflated Sharpe probability of at least 0.95 given the LINEAGE's trial count (`league/stats.py`);
  - positive in at least 3 of Validation's 4 quarters;
  - positive at 1.5x the half-spread (the stress run's P&L after fees).

THE HOLDOUT LINE (one look per program version, at most three per lineage; the gate's box only):
  - P&L after fees above zero;
  - a day-block bootstrap one-sided 95% lower bound on mean daily P&L above zero, with a Holm-Bonferroni
    correction across EVERY holdout look the swarm has made;
  - holdout Sharpe at least half of the validation Sharpe.
  The researcher is told pass or fail, never the numbers.

THE LEAKAGE ALARM: once there are at least 10 holdout looks, more than 30% passing stops the gate.

THE BANDIT: Thompson sampling over validation evidence, with a 25% exploration share for new families.

Standard library only (the House box runs it without numpy).
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Mapping, Sequence

from .. import stats

# ---------------------------------------------------------------------------- the lines (the plan's)
MIN_TRADES = 100
MIN_DAYS = 60
MIN_T = 2.0
MIN_DSR = 0.95
MIN_QUARTERS_POSITIVE = 3
STRESS = 1.5
HOLDOUT_ALPHA = 0.05
HOLDOUT_SHARPE_SHARE = 0.5
LOOKS_PER_LINEAGE = 3
ALARM_MIN_LOOKS = 10
ALARM_PASS_SHARE = 0.30
BOOTSTRAP_BLOCK = 5
BOOTSTRAP_DRAWS = 2000


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def quarters_positive(summary: Mapping[str, Any]) -> tuple[int, int]:
    """(positive, of) from a Gym summary's "k/n"."""
    text = str(summary.get("quarters_positive") or "0/0")
    try:
        k, n = text.split("/")
        return int(k), int(n)
    except ValueError:
        return 0, 0


def daily_pnl(result: Mapping[str, Any]) -> list[float]:
    return [float(d[1]) for d in (result.get("daily") or []) if isinstance(d, (list, tuple)) and len(d) >= 2
            and _num(d[1]) is not None]


#: When a summary does not carry the daily series' moments, the deflated Sharpe assumes these: a fat, left tail
#: (short-premium programs have one), never the normal's flattering 0 and 3.
CONSERVATIVE_SKEW = -1.0
CONSERVATIVE_KURT = 6.0


def daily_t(summary: Mapping[str, Any]) -> float | None:
    """The t statistic of the mean on DAILY-aggregated P&L per dollar of maximum loss (`t_daily`, the Gym's review
    of Sept 26: a per-trade t with correlated intraday entries overstates the evidence). None when absent."""
    return _num(summary.get("t_daily"))


def daily_mean(summary: Mapping[str, Any]) -> float | None:
    """The mean the daily t is about (`mean_return_on_max_loss_daily`); the per-trade mean only from an older Gym."""
    value = _num(summary.get("mean_return_on_max_loss_daily"))
    return value if value is not None else _num(summary.get("mean_return_on_max_loss"))


def stressed_of(result: Mapping[str, Any]) -> dict[str, Any] | None:
    """The 1.5x-stress figures a validation view carries (`stress_1.5`, the batch's twin run) as a result-shaped dict."""
    twin = result.get("stress_1.5")
    return {"status": twin.get("status"), "summary": dict(twin)} if isinstance(twin, Mapping) else None


def deflated(summary: Mapping[str, Any], daily: Sequence[float], *, lineage_trials: int, trial_sharpes: Sequence[float]) -> float | None:
    """The deflated Sharpe probability given the lineage's trials: from the daily series when the result carries
    it, else from the summary's daily Sharpe, days and moments (conservative moments when they are absent)."""
    sharpes = [float(x) for x in trial_sharpes if _num(x) is not None]
    trials = max(1, int(lineage_trials))
    if len(daily) >= 2:
        row = stats.deflated_sharpe(list(daily), sharpes, trials)
        return row["dsr"] if row else None
    sr = _num(summary.get("sharpe_daily"))
    n = int(summary.get("days") or 0)
    if sr is None or n < 2:
        return None
    skew = _num(summary.get("skew_daily"))
    kurt = _num(summary.get("kurt_daily"))
    benchmark = stats.expected_max_sharpe(sharpes, trials, fallback_variance=1.0 / n)
    return stats.probabilistic_sharpe(sr, n, CONSERVATIVE_SKEW if skew is None else skew, CONSERVATIVE_KURT if kurt is None else kurt,
                                      benchmark)


def validation_line(result: Mapping[str, Any], stressed: Mapping[str, Any] | None, *, lineage_trials: int,
                    trial_sharpes: Sequence[float]) -> dict[str, Any]:
    """Does a validation result meet the line? It may be the Gym's validation VIEW (summaries only: no trades,
    no dates, no daily series); `stressed` is the same program's validation result at 1.5x the half-spread."""
    s = dict(result.get("summary") or {})
    trades = int(s.get("trades") or 0)
    days = int(s.get("days_traded") or 0)
    mean = daily_mean(s)
    t = daily_t(s)
    k, n = quarters_positive(s)
    dsr = deflated(s, daily_pnl(result), lineage_trials=lineage_trials, trial_sharpes=trial_sharpes)
    stress_pnl = _num((stressed or {}).get("summary", {}).get("pnl")) if stressed else None
    checks = {
        "status_ok": result.get("status") == "ok",
        "trades": trades >= MIN_TRADES,
        "days": days >= MIN_DAYS,
        "mean_positive": mean is not None and mean > 0,
        "t": t is not None and t >= MIN_T,
        "dsr": dsr is not None and dsr >= MIN_DSR,
        "quarters": k >= MIN_QUARTERS_POSITIVE,
        "stress": stress_pnl is not None and stress_pnl > 0,
    }
    return {"passed": all(checks.values()), "checks": checks,
            "numbers": {"trades": trades, "days": days, "mean": mean, "t": t, "dsr": dsr, "quarters": f"{k}/{n}",
                        "stress_pnl": stress_pnl, "lineage_trials": int(lineage_trials),
                        "sharpe_daily": _num(s.get("sharpe_daily")), "pnl": _num(s.get("pnl"))}}


def score(summary: Mapping[str, Any] | None, *, min_trades: int = 30) -> float | None:
    """One number for "is this version better" on a window: the daily t of the mean return on maximum loss
    (`t_daily`; the per-trade `t_stat` only from a Gym that does not report it yet), None below `min_trades`
    trades (too few to say)."""
    if not summary:
        return None
    if int(summary.get("trades") or 0) < min_trades:
        return None
    t = daily_t(summary)
    return t if t is not None else _num(summary.get("t_stat"))


# ---------------------------------------------------------------------------- the holdout line
def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def block_bootstrap(xs: Sequence[float], *, block: int = BOOTSTRAP_BLOCK, draws: int = BOOTSTRAP_DRAWS,
                    seed: str = "") -> dict[str, float] | None:
    """A moving-block bootstrap of the mean of `xs` (daily P&L): {mean, lcb95, p}. `p` is the share of
    resampled means at or below zero (the one-sided p-value of "the mean is above zero"). Deterministic
    for a given seed. None under 2 points."""
    values = [float(x) for x in xs if _num(x) is not None]
    n = len(values)
    if n < 2:
        return None
    b = max(1, min(int(block), n))
    starts = n - b + 1
    rng = random.Random(_seed(seed or str(n)))
    means = []
    for _ in range(int(draws)):
        total, count = 0.0, 0
        while count < n:
            i = rng.randrange(starts)
            for x in values[i:i + b]:
                if count >= n:
                    break
                total += x
                count += 1
        means.append(total / n)
    means.sort()
    lcb = means[int(0.05 * len(means))]
    p = sum(1 for m in means if m <= 0) / len(means)
    return {"mean": sum(values) / n, "lcb95": lcb, "p": max(p, 1.0 / (len(means) + 1))}


def holm_passes(p_new: float, previous: Sequence[float], *, alpha: float = HOLDOUT_ALPHA) -> tuple[bool, float]:
    """Holm-Bonferroni across every look (the earlier ones and this one): (does this look's hypothesis
    reject, the threshold its rank faced). Step-down: sort the m p-values ascending; reject p(1..k-1)
    where k is the first rank with p(k) > alpha / (m - k + 1)."""
    ps = sorted([float(p) for p in previous if _num(p) is not None] + [float(p_new)])
    m = len(ps)
    rank_new = ps.index(float(p_new))  # the first (smallest) rank the new value can take
    for k, p in enumerate(ps):
        threshold = alpha / (m - k)
        if p > threshold:
            return rank_new < k, alpha / (m - rank_new)
    return True, alpha / (m - rank_new)


def holdout_line(result: Mapping[str, Any], *, validation_sharpe: float | None, previous_ps: Sequence[float],
                 seed: str) -> dict[str, Any]:
    """Does a holdout result meet the line? The numbers stay with the gate: the researcher hears pass or fail."""
    s = dict(result.get("summary") or {})
    pnl = _num(s.get("pnl"))
    daily = daily_pnl(result)
    boot = block_bootstrap(daily, seed=seed)
    p = boot["p"] if boot else 1.0
    holm, threshold = holm_passes(p, previous_ps)
    sharpe = stats.sharpe(daily) if len(daily) >= 2 else None
    need = (validation_sharpe or 0.0) * HOLDOUT_SHARPE_SHARE
    checks = {
        "status_ok": result.get("status") == "ok",
        "pnl": pnl is not None and pnl > 0,
        "bootstrap": boot is not None and boot["lcb95"] > 0,
        "holm": boot is not None and holm,
        "sharpe": sharpe is not None and validation_sharpe is not None and validation_sharpe > 0 and sharpe >= need,
    }
    return {"passed": all(checks.values()), "checks": checks, "p": p,
            "numbers": {"pnl": pnl, "mean_daily": boot["mean"] if boot else None, "lcb95": boot["lcb95"] if boot else None,
                        "p": p, "holm_threshold": threshold, "looks_before": len(previous_ps), "sharpe_daily": sharpe,
                        "validation_sharpe_daily": validation_sharpe, "days": len(daily)}}


def leakage_alarm(looks: int, passes: int) -> bool:
    """Stop the gate: at least 10 holdout looks and more than 30% of them passed."""
    return looks >= ALARM_MIN_LOOKS and passes > ALARM_PASS_SHARE * looks


# ---------------------------------------------------------------------------- the forward record
def forward_record(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """A family's forward record (nightly + shadow + real): trades, wins, P&L, the mean return on maximum
    loss and its 80% one-sided lower bound. Sized needs >= 20 trades, mean > 0 and the bound > 0; a
    Candidate whose record is negative over >= 20 trades loses its band."""
    roms = [float(t["pnl"]) / float(t["max_loss"]) for t in trades if _num(t.get("max_loss")) and float(t["max_loss"]) > 0]
    n = len(trades)
    pnl = sum(float(t["pnl"]) for t in trades)
    mean = sum(roms) / len(roms) if roms else None
    lcb80 = None
    if len(roms) >= 2:
        sd = math.sqrt(sum((r - mean) ** 2 for r in roms) / (len(roms) - 1))  # type: ignore[operator]
        lcb80 = mean - stats.t_quantile(0.80, len(roms) - 1) * sd / math.sqrt(len(roms))  # type: ignore[operator]
    return {"trades": n, "wins": sum(1 for t in trades if float(t["pnl"]) > 0), "pnl_usd": round(pnl, 2),
            "mean_rom": mean, "lcb80": lcb80,
            "sized": n >= 20 and mean is not None and mean > 0 and lcb80 is not None and lcb80 > 0,
            "negative": n >= 20 and pnl < 0}


# ---------------------------------------------------------------------------- the bandit
PRIOR_SD = 0.05


def thompson(families: Sequence[Mapping[str, Any]], *, explore_share: float = 0.25, new_validations: int = 2,
             rng: random.Random | None = None) -> dict[str, float]:
    """Each family's share of researcher cycles and Gym time: Thompson sampling over validation
    evidence (a normal posterior on the mean return on maximum loss, its standard error from the t
    statistic), with `explore_share` reserved for NEW families (fewer than `new_validations` looks).

    `families`: [{id, validations, mean, t}] (mean/t of its latest validation; None when there is none).
    Returns {id: share}, summing to 1 (0 each for an empty list)."""
    rng = rng or random.Random()
    new = [f for f in families if int(f.get("validations") or 0) < new_validations or _num(f.get("mean")) is None]
    old = [f for f in families if f not in new]
    shares: dict[str, float] = {}
    if not families:
        return shares
    new_share = explore_share if new and old else (1.0 if new else 0.0)
    old_share = 1.0 - new_share
    if new:
        draws = {f["id"]: rng.gauss(0.0, PRIOR_SD) for f in new}
        _allocate(draws, new_share, shares)
    if old:
        draws = {}
        for f in old:
            mean = float(f["mean"])
            t = _num(f.get("t"))
            se = abs(mean / t) if t not in (None, 0.0) and mean != 0 else PRIOR_SD
            draws[f["id"]] = rng.gauss(mean, max(se, 1e-6))
        _allocate(draws, old_share, shares)
    return shares


def _allocate(draws: Mapping[str, float], total: float, out: dict[str, float]) -> None:
    """Rank-weighted shares: the best draw gets the most (weights n, n-1, ..., 1), normalized to `total`."""
    ranked = sorted(draws, key=lambda k: (-draws[k], k))
    n = len(ranked)
    denom = n * (n + 1) / 2.0
    for i, key in enumerate(ranked):
        out[key] = total * (n - i) / denom


__all__ = ["validation_line", "holdout_line", "block_bootstrap", "holm_passes", "leakage_alarm", "forward_record", "thompson",
           "score", "quarters_positive", "daily_pnl", "MIN_TRADES", "MIN_DAYS", "MIN_T", "MIN_DSR", "STRESS",
           "LOOKS_PER_LINEAGE"]

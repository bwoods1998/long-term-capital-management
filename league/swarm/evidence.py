"""The evidence lines, exactly as the plan states them ("Evidence: fast without fooling ourselves"), as amended by
the owner's decision D2 of Sept 26, 2026.

A search over tens of thousands of programs finds something that looks great on any window by chance,
so these lines are the swarm's brakes. They may be TIGHTENED on evidence; loosening one is the owner's
decision, which is why they are constants here and not settings.

D2, THE EVIDENCE REFORM (docs/goals/LTCM_SWARM_SPRINT.md, "Owner decisions"; decided by the owner, Blake, Sept 26
2026: "D2 evidence reform as written: yes"): "(a) Researchers see Validation only as pass or fail and a count of checks
passed. (b) The deflated Sharpe uses the traded-day Sharpe, with N = the lineage's validated versions (inherited ones
included). (c) Frequency: at least 50 trades on at least 25 distinct days. Unchanged: t >= 2, positive in 3 of 4
quarters, positive at 1.5x the half-spread, and the whole holdout line (bootstrap lower bound above zero with Holm,
holdout Sharpe at least half of validation's, at most 3 looks per lineage)." Before D2 the line asked for 100 trades
on 60 days and deflated the all-days Sharpe by every Train trial of the lineage, which capped a family trading a
fraction f of days at sqrt(f / (1 - f)) and punished sparse mechanisms twice. (a) lives in `diagnostics.py`.

THE VALIDATION LINE (a family's best program, on Validation 2025):
  - at least 50 trades on at least 25 distinct trading days (D2c);
  - mean P&L per dollar of maximum loss above zero after fees, with a one-sided t of at least 2 (the t on
    DAILY-aggregated P&L per dollar of maximum loss, `t_daily`: correlated intraday entries make a per-trade t
    overstate the evidence, the Gym's review of Sept 26);
  - a deflated Sharpe probability of at least 0.95 on the TRADED-DAY Sharpe (`t_daily / sqrt(days_traded)` over
    `days_traded` observations, with the traded-day moments), against the best of N luck, N = the lineage's
    validated versions (inherited ones included) and the spread of their traded-day Sharpes (D2b; `league/stats.py`);
  - positive in at least 3 of Validation's 4 quarters;
  - positive at 1.5x the half-spread (the stress run's P&L after fees).

THE TRAIN OBJECTIVE (`train_score`, the sprint's "robust Train objective", Sept 26): a version is scored on its WORST
Train year (the `t_daily` of each year its own roots had data, the Gym's `by_year`), times the share of those years'
quarters that were positive. It is eligible to be a family's best only with at least 40 trades on at least 20 traded days in EVERY Train
year with data; a version whose 1.5x-stress Train run loses is never the best (`researcher.py`). The full-window t
with a 30-trade floor it replaced rewarded sparse filters that could never meet the line's frequency. The Train years
are the ones from the swarm's `gym.train_from` on (2022-2024 by default, 2020-2024 with the 2020-21 switch on,
Sept 27): `first_year` drops any earlier year a result may carry, so 2020 and 2021 enter the worst year only once on.

THE DRIFT SCREEN (`drift_screen`, Sept 27; the owner approved tightening pre-Validation with a placebo test after the
one family that passed Validation, back-month long SPY calls after low closes, failed its holdout: its Train and 2025
profit was the bull market's drift, which long calls earn whatever the signal says). The Gym measures, each Train year, the
exposure a program held (the slope of its P&L on the move of the roots it held over the hours it held them, held days
only) and charges it the roots' unconditional drift over those hours (`league.gym.results.drift_fit`): alpha is what its
timing added beyond that, after costs. A version is validated only when its pooled alpha t is at least
`tournament.drift_min_t` (1.0) and its alpha is positive in `tournament.drift_years_positive` Train years (all but one);
a version that fails is never the family's best again (`researcher.py`), and the gate refuses a look at one. It only ADDS
a brake: it is a setting, `tournament.drift_screen`, because it is the operator's tightening, not a line of the plan. A
run from before the figures is not screened (`known` False): it is never validated until its Train run is made again
(`researcher.py`, the robustness label "drift"). Over the Train extension (Sept 27) it counts the running span's years only
(`first_year`), and a year before 2022 only when every root of the program had data on half its days (as the Train score
does); "all but one" is over the years it counts, and the pooled t is refitted over them.

THE HOLDOUT LINE (one look per program version, at most three per lineage; the gate's box only):
  - P&L after fees above zero;
  - a day-block bootstrap one-sided 95% lower bound on mean daily P&L above zero, with a Holm-Bonferroni
    correction across EVERY holdout look the swarm has made;
  - holdout Sharpe at least half of the validation Sharpe.
  The researcher is told pass or fail, never the numbers.

THE LOOK HOLDS (L6(b) and L6(c), approved by the owner on Oct 2, 2026 as a TIGHTENING; the gate's
`Gate.look_hold`). Every look raises the Holm bar of every later one, so the gate does not spend one on a version
the holdout cannot judge. It HOLDS the look (no look, no review, no sealed read) when:
  - (b) THE DRIFT HOLD (`drift_lean`): the version's own Train drift fit is long-delta (pooled beta above zero) and its
    drift share, |drift_usd| / (|alpha_usd| + |drift_usd|) over the years THE DRIFT SCREEN counts, is at least
    `LOOK_HOLD_DRIFT_SHARE`. A Validation pass by such a program has mostly measured the market's drift;
  - (c) THE POWER HOLD (`holdout_power`): the one-sided power of the holdout's own test, at the level the look would
    have to reach under Holm (`holm_level`), is below `LOOK_HOLD_MIN_POWER`, taking the version's Validation all-days
    daily Sharpe as its true Sharpe over the holdout's sessions. The test is a day-block bootstrap of the mean daily
    P&L; its power is taken in the normal approximation, P(Z >= z(level) - S sqrt(N)), which leaves out the bootstrap's
    extra width and the line's other checks (both only lower it).
  Missing figures hold too (fail-closed). These are the owner's settings (`gate.look_holds`), each switchable to null.

THE LEAKAGE ALARM: once there are at least 10 holdout looks, more than 30% passing stops the gate.

THE BANDIT: Thompson sampling over validation evidence, with a 25% exploration share for new families.

Standard library only (the House box runs it without numpy).
"""

from __future__ import annotations

import hashlib
import math
import random
from statistics import NormalDist
from typing import Any, Mapping, Sequence

from .. import stats

# ---------------------------------------------------------------------------- the lines (the plan's)
MIN_TRADES = 50  # D2c (was 100)
MIN_DAYS = 25    # D2c (was 60)
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
#: The robust Train objective's eligibility: every Train year with data (the sprint, Sept 26).
TRAIN_YEAR_MIN_TRADES = 40
TRAIN_YEAR_MIN_DAYS = 20
#: The Train extension's years (2020-21, Sept 27) count for a result only when EVERY root of its had data in them (the
#: Gym's per-year `roots`): a program pooling SPY with a name that has no 2020-21 chains would otherwise be scored there on
#: SPY alone, another program than the one it is.
PARTIAL_YEARS_BEFORE = 2022


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


#: When a summary does not carry the traded-day moments, the deflated Sharpe assumes these: a fat, left tail
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


def traded_sharpe(summary: Mapping[str, Any]) -> float | None:
    """The Sharpe of the daily returns on maximum loss over the days with entries: `t_daily / sqrt(days_traded)` (D2b).
    None without a t or a traded day."""
    t = daily_t(summary)
    n = int(summary.get("days_traded") or 0)
    return None if t is None or n < 1 else t / math.sqrt(n)


def deflated(summary: Mapping[str, Any], *, validated_versions: int, version_sharpes: Sequence[float]) -> float | None:
    """The deflated Sharpe probability on the TRADED-DAY Sharpe (D2b): `traded_sharpe` over `days_traded` observations
    with the traded-day moments (`skew_traded`, `kurt_traded`; conservative ones when absent), against the Sharpe the
    best of N = `validated_versions` unskilled versions shows by luck (their traded-day Sharpes' spread, never under the
    1 / n of sampling noise)."""
    sr = traded_sharpe(summary)
    n = int(summary.get("days_traded") or 0)
    if sr is None or n < 2:
        return None
    sharpes = [float(x) for x in version_sharpes if _num(x) is not None]
    benchmark = stats.expected_max_sharpe(sharpes, max(1, int(validated_versions)), fallback_variance=1.0 / n)
    skew = _num(summary.get("skew_traded"))
    kurt = _num(summary.get("kurt_traded"))
    return stats.probabilistic_sharpe(sr, n, CONSERVATIVE_SKEW if skew is None else skew, CONSERVATIVE_KURT if kurt is None else kurt,
                                      benchmark)


def validation_line(result: Mapping[str, Any], stressed: Mapping[str, Any] | None, *, validated_versions: int,
                    version_sharpes: Sequence[float], lineage_trials: int = 0) -> dict[str, Any]:
    """Does a validation result meet the line? It may be the Gym's validation VIEW (summaries only: no trades,
    no dates, no daily series); `stressed` is the same program's validation result at 1.5x the half-spread.
    `validated_versions` and `version_sharpes` are the lineage's (`SwarmStore.lineage_validated`, this one included);
    `lineage_trials` is recorded, no longer a divisor (D2b)."""
    s = dict(result.get("summary") or {})
    trades = int(s.get("trades") or 0)
    days = int(s.get("days_traded") or 0)
    mean = daily_mean(s)
    t = daily_t(s)
    k, n = quarters_positive(s)
    dsr = deflated(s, validated_versions=validated_versions, version_sharpes=version_sharpes)
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
                        "validated_versions": int(validated_versions), "sharpe_traded": traded_sharpe(s),
                        "sharpe_daily": _num(s.get("sharpe_daily")), "pnl": _num(s.get("pnl"))}}


def checks_passed(line: Mapping[str, Any] | None) -> tuple[int, int]:
    """(checks met, checks) of a validation line: all a researcher or the architect may know of it besides pass or
    fail (D2a)."""
    checks = (line or {}).get("checks") or {}
    return sum(1 for ok in checks.values() if ok), len(checks)


def years_of(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """A Train result's per-year rows: the Gym's `by_year`, else computed from its trades and daily series (a Gym bundle
    from before the block, the same arithmetic: `league.gym.results.by_year`). {} when neither is there."""
    rows = result.get("by_year")
    if isinstance(rows, Mapping):
        return {str(k): dict(v) for k, v in rows.items() if isinstance(v, Mapping)}
    daily, trades = result.get("daily"), result.get("trades")
    if not isinstance(daily, list) or not isinstance(trades, list) or not daily:
        return {}
    from ..gym.results import by_year  # standard library only, like this module

    try:
        return by_year([t for t in trades if isinstance(t, Mapping) and t.get("day") and _num(t.get("pnl")) is not None
                        and _num(t.get("max_loss")) is not None], [d for d in daily if isinstance(d, (list, tuple)) and len(d) >= 2])
    except (KeyError, TypeError, ValueError):
        return {}


def train_score(result: Mapping[str, Any], *, first_year: int | None = None) -> dict[str, Any]:
    """The robust Train objective (the module docstring): {score, eligible, why, worst_year, quarters, years}.
    `first_year` (the switch's first Train year) leaves out any year before it; None counts every year with data. A year
    before `PARTIAL_YEARS_BEFORE` counts only when every root of the result had data in it (its Gym row's `roots`).

    score = the lowest per-year `t_daily` over the Train years with data, times the share of Train quarters positive (a
    worst year below zero is scaled by 2 - share instead, so fewer positive quarters never flatter a loss); None when a
    year has no t. eligible: a score, and at least `TRAIN_YEAR_MIN_TRADES` trades on `TRAIN_YEAR_MIN_DAYS` traded days
    in every year; `why` names the first year short of it."""
    years = years_of(result)
    if first_year is not None:
        years = {y: r for y, r in years.items() if not (y[:4].isdigit() and int(y[:4]) < int(first_year))}
    # The program's own roots: its NEEDS within the batch's (a result's `roots` is its batch's universe).
    wanted = {str(r).upper() for r in result.get("roots") or ()}
    declared = (result.get("needs") or {}).get("roots") if isinstance(result.get("needs"), Mapping) else None
    if isinstance(declared, (list, tuple)) and declared:
        wanted &= {str(r).upper() for r in declared}
    years = {y: r for y, r in years.items()
             if not (y[:4].isdigit() and int(y[:4]) < PARTIAL_YEARS_BEFORE and isinstance(r.get("roots"), list)
                     and wanted - {str(x).upper() for x in r["roots"]})}
    k, n = quarters_positive(result.get("summary") or {})
    quarters = [v for r in years.values() for v in ((r.get("quarter_pnl") or {}).values() if isinstance(r.get("quarter_pnl"), Mapping) else [])]
    if quarters:  # the quarters the program's own roots had data in (the Gym's per-year block), not its batch company's
        k, n = sum(1 for v in quarters if _num(v) is not None and v > 0), len(quarters)
    out: dict[str, Any] = {"score": None, "eligible": False, "why": None, "worst_year": None, "quarters": f"{k}/{n}",
                           "years": {y: {"trades": int(r.get("trades") or 0), "days_traded": int(r.get("days_traded") or 0),
                                         "pnl": _num(r.get("pnl")), "t_daily": _num(r.get("t_daily"))} for y, r in sorted(years.items())}}
    if result.get("status") != "ok" or not years or n <= 0:
        out["why"] = "no completed Train run with a per-year breakdown"
        return out
    ts = {y: r["t_daily"] for y, r in out["years"].items()}
    if all(t is not None for t in ts.values()):
        worst = min(ts, key=lambda y: (ts[y], y))
        share = k / n
        low = float(ts[worst])
        out["worst_year"] = worst
        out["score"] = round(low * share if low >= 0 else low * (2.0 - share), 6)
    for y, r in out["years"].items():
        if r["trades"] < TRAIN_YEAR_MIN_TRADES or r["days_traded"] < TRAIN_YEAR_MIN_DAYS:
            out["why"] = (f"{y} has {r['trades']} trades on {r['days_traded']} days: every Train year needs at least "
                          f"{TRAIN_YEAR_MIN_TRADES} trades on {TRAIN_YEAR_MIN_DAYS} days")
            return out
    if out["score"] is None:
        out["why"] = "a Train year has no daily t"
        return out
    out["eligible"] = True
    return out


def robustness_view(result: Mapping[str, Any]) -> dict[str, Any]:
    """A robustness run's compact figures for the researcher: status, P&L, `t_daily`, trades, and per year P&L and t."""
    s = result.get("summary") or {}
    return {"status": result.get("status"), "pnl": _num(s.get("pnl")), "t_daily": _num(s.get("t_daily")), "trades": s.get("trades"),
            "by_year": {y: {"pnl": _num(r.get("pnl")), "t_daily": _num(r.get("t_daily")), "trades": r.get("trades")}
                        for y, r in sorted(years_of(result).items())}}


# ---------------------------------------------------------------------------- the drift screen
#: The screen's defaults (`tournament.drift_min_t`; `drift_years_positive` None is every Train year but one).
DRIFT_MIN_T = 1.0


def drift_numbers(block: Any) -> dict[str, Any] | None:
    """A Gym Train result's `drift` block without its statistics: {"pooled": {...}, "years": {year: {...}}, "roots"}, what
    a run row's summary and a family's state keep. None when there is no block (a run from before the figures) or it is
    malformed."""
    if not isinstance(block, Mapping) or not isinstance(block.get("years"), Mapping) or not isinstance(block.get("pooled"), Mapping):
        return None
    out = {"pooled": {k: v for k, v in block["pooled"].items() if k not in ("stats", "moments")},
           "years": {str(y): {k: v for k, v in row.items() if k not in ("stats", "moments")} for y, row in sorted(block["years"].items())
                     if isinstance(row, Mapping)}}
    if isinstance(block.get("roots"), (list, tuple)):
        out["roots"] = [str(r) for r in block["roots"]]
    return out


def drift_years(numbers: Mapping[str, Any], first_year: int | None = None) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    """(the years the screen counts, the years it left out): from `first_year` (the running Train span's) on, and a year
    before `PARTIAL_YEARS_BEFORE` only when every root of the program (the block's `roots`) had data on
    `ROOT_YEAR_SHARE` of its days (the row's `root_days`): as the Train score counts them."""
    from ..gym.results import roots_in_year  # standard library only, like this module

    roots = {str(r) for r in numbers.get("roots") or ()}
    kept: dict[str, Mapping[str, Any]] = {}
    left: list[str] = []
    for year, row in sorted((numbers.get("years") or {}).items()):
        if not isinstance(row, Mapping):
            continue
        early = year[:4].isdigit() and int(year[:4]) < PARTIAL_YEARS_BEFORE
        if first_year is not None and year[:4].isdigit() and int(year[:4]) < int(first_year):
            left.append(year)
        elif early and roots and isinstance(row.get("root_days"), Mapping) \
                and roots - set(roots_in_year(row["root_days"], int(row.get("days") or 0))):
            left.append(year)
        else:
            kept[year] = row
    return kept, left


def pooled_drift_t(years: Mapping[str, Mapping[str, Any]]) -> tuple[bool, float | None]:
    """(could, t): the pooled t of the drift-adjusted daily P&L over these years alone, from each year's sums (the Gym's
    `sum_sq`, `sum_pp`, `alpha_usd`, `days`); `could` is False when a year lacks them (figures from before the extension)."""
    from ..gym.results import _t_of  # standard library only, like this module

    total = sq = pp = 0.0
    n = 0
    for row in years.values():
        values = [_num(row.get(k)) for k in ("alpha_usd", "sum_sq", "sum_pp")]
        if any(v is None for v in values) or not isinstance(row.get("days"), int):
            return False, None
        total, sq, pp, n = total + values[0], sq + values[1], pp + values[2], n + int(row["days"])
    return True, _t_of(total, sq, n, pp)


def drift_screen(numbers: Mapping[str, Any] | None, *, min_t: float = DRIFT_MIN_T, years_positive: int | None = None,
                 first_year: int | None = None) -> dict[str, Any]:
    """THE DRIFT SCREEN (the module docstring) on a version's drift figures (`drift_numbers`): {known, passed, t, positive,
    years, need, why}. `known` is False when there are no figures (a run from before them); a year's alpha is positive
    when its alpha dollars are; `need` is `years_positive`, or every year but one (at least one) when None. The years are
    those `drift_years` counts (from `first_year`, the running Train span's); when it leaves one out, the pooled t is
    refitted over the rest (`pooled_drift_t`), and figures that cannot be refitted are not `known`."""
    out: dict[str, Any] = {"known": False, "passed": False, "t": None, "positive": 0, "years": 0, "need": None, "why": None}
    if not isinstance(numbers, Mapping) or not isinstance(numbers.get("years"), Mapping):
        out["why"] = "its Train run predates the drift figures: it is run again before it is screened"
        return out
    years, left = drift_years(numbers, first_year)
    t = _num((numbers.get("pooled") or {}).get("t"))
    if left:
        could, t = pooled_drift_t(years)
        out["left_out"] = left
        if not could:
            out["why"] = "its drift figures predate the per-year sums the Train extension needs: it is run again before it is screened"
            return out
    positive = sum(1 for r in years.values() if (_num(r.get("alpha_usd")) or 0.0) > 0)
    need = max(1, len(years) - 1) if years_positive is None else min(max(0, int(years_positive)), len(years))
    out.update(known=True, t=t, positive=positive, years=len(years), need=need)
    if not years:
        out["why"] = "no Train year has a return to fit"
    elif t is None or t < float(min_t):
        out["why"] = (f"its drift-adjusted alpha has t {'n/a' if t is None else round(t, 2)} over Train, below {float(min_t):g}: "
                      "its profit is the market's drift, not its timing")
    elif positive < need:
        out["why"] = f"its drift-adjusted alpha is positive in {positive} of {len(years)} Train years; the screen needs {need}"
    else:
        out["passed"] = True
    return out


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
    # Enough draws that the smallest p the bootstrap can give (1 / (draws + 1)) stays well under the smallest Holm
    # threshold (alpha / m, m = every look so far and this one): 20x, capped at 200,000.
    m = len([p for p in previous_ps if _num(p) is not None]) + 1
    draws = min(200_000, max(BOOTSTRAP_DRAWS, int(math.ceil(20.0 * m / HOLDOUT_ALPHA))))
    boot = block_bootstrap(daily, seed=seed, draws=draws)
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
                        "draws": draws, "holm_reachable": 1.0 / (draws + 1) <= HOLDOUT_ALPHA / m,
                        "validation_sharpe_daily": validation_sharpe, "days": len(daily)}}


def leakage_alarm(looks: int, passes: int) -> bool:
    """Stop the gate: at least 10 holdout looks and more than 30% of them passed."""
    return looks >= ALARM_MIN_LOOKS and passes > ALARM_PASS_SHARE * looks


# ---------------------------------------------------------------------------- the look holds (L6)
#: THE LOOK HOLDS' defaults (the module docstring; the owner's approval of Oct 2, 2026): `gate.look_holds`.
LOOK_HOLD_DRIFT_SHARE = 0.25
LOOK_HOLD_MIN_POWER = 0.30


def drift_lean(numbers: Mapping[str, Any] | None, *, first_year: int | None = None) -> dict[str, Any]:
    """THE DRIFT HOLD's figures from a version's Train drift fit (`drift_numbers`): {known, beta, alpha_usd, drift_usd,
    share, long_delta, years, why}. The pooled line over the years THE DRIFT SCREEN counts (`drift_years`, from
    `first_year`); when it leaves a year out, the kept years are pooled again as the Gym pools them (alpha and drift
    dollars summed, beta the held-day-weighted mean of the years'). share = |drift_usd| / (|alpha_usd| + |drift_usd|),
    None when both are zero; long_delta: beta above zero. `known` is False when there is no fit (a run from before the
    figures) or it cannot be pooled; `why` says which."""
    out: dict[str, Any] = {"known": False, "beta": None, "alpha_usd": None, "drift_usd": None, "share": None,
                           "long_delta": None, "years": 0, "why": None}
    if not isinstance(numbers, Mapping) or not isinstance(numbers.get("years"), Mapping) \
            or not isinstance(numbers.get("pooled"), Mapping):
        out["why"] = "no Train drift fit"
        return out
    years, left = drift_years(numbers, first_year)
    if left:
        rows = [(_num(r.get("alpha_usd")), _num(r.get("drift_usd")), _num(r.get("beta")), _num(r.get("held_days")))
                for r in years.values()]
        if not rows or any(v is None for row in rows for v in row):
            out["why"] = "its Train drift fit cannot be pooled over the years the drift screen counts"
            return out
        held = sum(float(h) for _, _, _, h in rows)
        alpha = sum(float(a) for a, _, _, _ in rows)
        drift = sum(float(d) for _, d, _, _ in rows)
        beta = sum(float(b) * float(h) for _, _, b, h in rows) / held if held > 0 else 0.0
    else:
        pooled = numbers["pooled"]
        alpha, drift, beta = _num(pooled.get("alpha_usd")), _num(pooled.get("drift_usd")), _num(pooled.get("beta"))
        if alpha is None or drift is None or beta is None:
            out["why"] = "its pooled Train drift fit lacks its alpha, drift or beta"
            return out
    whole = abs(alpha) + abs(drift)
    out.update(known=True, beta=beta, alpha_usd=alpha, drift_usd=drift, share=abs(drift) / whole if whole > 0 else None,
               long_delta=beta > 0, years=len(years))
    return out


def holm_level(previous_ps: Sequence[float], *, alpha: float = HOLDOUT_ALPHA) -> float:
    """The level the next holdout look's p must reach under Holm across every look (`holm_passes`, the gate's own rule,
    with the earlier looks' p-values): the largest of alpha / (m - k), k = 0 .. m - 1, at which it would reject. With
    every earlier look failed that is alpha / m (the 4th look: 0.0125)."""
    m = len([p for p in previous_ps if _num(p) is not None]) + 1
    for level in sorted({alpha / (m - k) for k in range(m)}, reverse=True):
        if holm_passes(level, previous_ps, alpha=alpha)[0]:
            return level
    return alpha / m


def holdout_power(sharpe_daily: Any, sessions: Any, level: Any) -> float | None:
    """THE POWER HOLD's figure: the one-sided power of the holdout's test of "mean daily P&L above zero" at `level` over
    `sessions` days, for a program whose true all-days daily Sharpe is `sharpe_daily`, in the normal approximation
    (the day-block bootstrap's mean is about normal): P(Z >= z(1 - level) - S sqrt(N)). None without a Sharpe, at least
    two sessions and a level strictly between 0 and 1."""
    s, n, a = _num(sharpe_daily), _num(sessions), _num(level)
    if s is None or n is None or n < 2 or a is None or not 0.0 < a < 1.0:
        return None
    normal = NormalDist()
    return normal.cdf(s * math.sqrt(n) - normal.inv_cdf(1.0 - a))


# ---------------------------------------------------------------------------- the forward record
SOURCE_ORDER = ("real", "shadow", "nightly")


def one_record(rows: Sequence[Mapping[str, Any]], *, version: Any = None) -> list[Mapping[str, Any]]:
    """The forward rows that count (the live path's rule, league/live/money.py, agreed Sept 26): (1) only the CURRENT
    program version's rows once any row carries a version (rows without one count only while none does); (2) ONE
    source a market day: real, else shadow, else the nightly replay (the three trade the same decisions on the same
    day: counting them all would count one decision two or three times and narrow the bound that sizes money)."""
    rows = list(rows)
    if any(r.get("version") is not None for r in rows):
        rows = [r for r in rows if r.get("version") is not None and version is not None and int(r["version"]) == int(version)]
    by_day: dict[str, dict[str, list]] = {}
    for r in rows:
        by_day.setdefault(str(r.get("day") or ""), {}).setdefault(str(r.get("source") or ""), []).append(r)
    out: list[Mapping[str, Any]] = []
    for day in sorted(by_day):
        for source in SOURCE_ORDER + ("",):
            if by_day[day].get(source):
                out.extend(by_day[day][source])
                break
    return out


def _returns(rows: Sequence[Mapping[str, Any]]) -> list[float]:
    out = []
    for r in rows:
        p, m = _num(r.get("pnl")), _num(r.get("max_loss"))
        if p is not None and m is not None and m > 0:
            out.append(p / m)
    return out


def forward_record(trades: Sequence[Mapping[str, Any]], *, version: Any = None) -> dict[str, Any]:
    """A family's forward record over `one_record`: r = P&L / maximum loss a trade (a trade without a positive maximum
    loss is no return, and is not counted in n); the mean of r and its 80% one-sided lower bound (`stats.mean_bounds`).
    negative: n >= 20 and mean < 0 (a Candidate goes back to the Gym). sized: n >= 20, mean > 0 and the bound > 0 (the
    live path adds the band condition). real_bad: at least 10 real trades with mean <= 0 (the live path holds or lowers
    the band)."""
    rows = one_record(trades, version=version)
    returns = _returns(rows)
    n = len(returns)
    bounds = stats.mean_bounds(returns, 0.20) if n >= 2 else None
    mean = bounds["mean"] if bounds else (returns[0] if n == 1 else None)
    lcb80 = bounds["lcb"] if bounds else None
    real = _returns([r for r in rows if r.get("source") == "real"])
    real_mean = sum(real) / len(real) if real else None
    return {"trades": n, "rows": len(rows), "wins": sum(1 for x in returns if x > 0),
            "pnl_usd": round(sum(float(r.get("pnl") or 0.0) for r in rows), 2), "mean_rom": mean, "lcb80": lcb80,
            "sized": n >= 20 and mean is not None and mean > 0 and lcb80 is not None and lcb80 > 0,
            "negative": n >= 20 and mean is not None and mean < 0,
            "real_trades": len(real), "real_bad": len(real) >= 10 and real_mean is not None and real_mean <= 0,
            "version": version}


# ---------------------------------------------------------------------------- the bandit
PRIOR_SD = 0.05


#: R11-5: each old family with a positive latest validation mean earns at most this much of the exploit share.
EXPLOIT_PER_POSITIVE = 0.15


def thompson(families: Sequence[Mapping[str, Any]], *, explore_share: float = 0.25, new_validations: int = 2,
             rng: random.Random | None = None, exploit_per_positive: float | None = EXPLOIT_PER_POSITIVE) -> dict[str, float]:
    """Each family's share of researcher cycles and Gym time: Thompson sampling over validation
    evidence (a normal posterior on the mean return on maximum loss, its standard error from the t
    statistic), with at least `explore_share` reserved for the EXPLORE pool.

    THE EXPLOIT POOL (R11-5, Sept 29: the four old families held 75% of the share with validation t of +0.16, -0.53,
    -1.95 and -1.67) holds only OLD families (at least `new_validations` looks) whose latest validation mean is positive.
    Every other family is in the explore pool: the new ones draw from the prior, and an old one whose mean is zero or
    less draws from its own posterior among them. The explore pool's share is at least `1 - exploit_per_positive x` the
    number of positive old families (never below `explore_share`), so the exploit share grows only with positive evidence;
    `exploit_per_positive` None keeps `explore_share` alone. Within each pool the shares are rank-weighted.

    `families`: [{id, validations, mean, t}] (mean/t of its latest validation; None when there is none).
    Returns {id: share}, summing to 1 (0 each for an empty list)."""
    rng = rng or random.Random()
    new = [f for f in families if int(f.get("validations") or 0) < new_validations or _num(f.get("mean")) is None]
    old = [f for f in families if f not in new]
    exploit = [f for f in old if float(f["mean"]) > 0]
    explore = new + [f for f in old if f not in exploit]
    shares: dict[str, float] = {}
    if not families:
        return shares
    floor = explore_share
    per = _num(exploit_per_positive)
    if per is not None and per > 0:
        floor = max(explore_share, 1.0 - per * len(exploit))
    explore_total = min(1.0, max(0.0, floor)) if explore and exploit else (1.0 if explore else 0.0)

    def posterior(f: Mapping[str, Any]) -> float:
        mean = float(f["mean"])
        t = _num(f.get("t"))
        se = abs(mean / t) if t not in (None, 0.0) and mean != 0 else PRIOR_SD
        return rng.gauss(mean, max(se, 1e-6))

    if explore:
        draws = {f["id"]: rng.gauss(0.0, PRIOR_SD) if f in new else posterior(f) for f in explore}
        _allocate(draws, explore_total, shares)
    if exploit:
        _allocate({f["id"]: posterior(f) for f in exploit}, 1.0 - explore_total, shares)
    return shares


def _allocate(draws: Mapping[str, float], total: float, out: dict[str, float]) -> None:
    """Rank-weighted shares: the best draw gets the most (weights n, n-1, ..., 1), normalized to `total`."""
    ranked = sorted(draws, key=lambda k: (-draws[k], k))
    n = len(ranked)
    denom = n * (n + 1) / 2.0
    for i, key in enumerate(ranked):
        out[key] = total * (n - i) / denom


__all__ = ["validation_line", "holdout_line", "block_bootstrap", "holm_passes", "leakage_alarm", "forward_record", "thompson",
           "train_score", "years_of", "robustness_view", "traded_sharpe", "checks_passed", "quarters_positive", "daily_pnl",
           "one_record", "MIN_TRADES", "MIN_DAYS", "MIN_T", "MIN_DSR", "STRESS", "LOOKS_PER_LINEAGE", "TRAIN_YEAR_MIN_TRADES",
           "TRAIN_YEAR_MIN_DAYS", "drift_numbers", "drift_screen", "DRIFT_MIN_T", "EXPLOIT_PER_POSITIVE", "drift_lean",
           "holm_level", "holdout_power", "LOOK_HOLD_DRIFT_SHARE", "LOOK_HOLD_MIN_POWER"]

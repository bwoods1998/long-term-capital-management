"""The statistics the ladder decides on: who is promoted, how large they trade, who is retired.

Every function here is small, pure and standard library only, because the answers move real
money. The rules they share:

- **Growth is log growth.** An account is scored on the log of its wealth (`log_growth`), which is
  what compounds, and which prices ruin as the catastrophe it is (`RUIN`).
- **Decide on the bound, not the estimate.** Promotion needs the one-sided *lower* confidence
  bound of growth above zero and demotion needs the *upper* bound below zero (`mean_bounds`), and
  size comes from the lower bound too (`quarter_kelly`).
- **Every look costs alpha.** The House looks at an agent again and again, so look `k` may only
  spend `alpha * 6 / (pi^2 k^2)` (`spend`): the looks sum to alpha however long the agent lives.
- **A record without a loss proves little.** Selling favourites wins small and often and loses
  large and rarely. Until a loss is on the record the sample sd is tiny and a t-interval is badly
  anti-conservative, so such a record (`lopsided`) is judged by `lopsided_growth_lcb`: an exact
  upper bound on the loss probability (`exact_upper`, Clopper-Pearson) times the worst loss that
  could have happened. The Wilson score bound (`wilson_upper`) is kept for reference only: on
  records with few losses it covers 92-94% where it says 95%, so it is not the gate.
- **Every trial counts.** A Sharpe ratio picked from many backtests is deflated by the Sharpe the
  best of that many unskilled trials would have shown (`expected_max_sharpe`, `deflated_sharpe`,
  after Bailey and Lopez de Prado, "The Deflated Sharpe Ratio", 2014).
- **Edges decay.** `cusum_decay` raises an alarm when live results drift below what was promised.

Degenerate input never raises: a statistic that cannot be computed (too few points, no variance,
a value that is not finite) is `None`, or the conservative constant its docstring names. Only a
malformed *parameter* raises `ValueError` (an alpha outside (0, 1), a look below 1), because that
is a bug in the caller and not a property of the data. Floats throughout: this is evidence, not
money.

Student's t has no inverse in the standard library, so `t_quantile` carries its own: the
regularized incomplete beta function by continued fraction (modified Lentz) for the tail, inverted
by bracketed Newton steps.
"""

from __future__ import annotations

import math
from functools import lru_cache
from statistics import NormalDist
from typing import Sequence

#: Log growth of an account that lost everything: about ln(1e-6). The true value is minus
#: infinity, which would poison every mean it enters. This keeps a ruin finite and still so large
#: that no run of ordinary wins can average it away. `log_growth` never returns less.
RUIN = -13.8

EULER_GAMMA = 0.5772156649015329

_NORMAL = NormalDist()
_FLAT = 1e-12  # a sample whose sd is below this share of its largest value has no variance, only rounding noise
_TINY = 1e-300
_CF_EPS = 1e-15
_CF_MAX_ITERATIONS = 200_000
_T_MAX = 1e150  # t * t must not overflow
_NORMAL_DOF = 1e5  # beyond this the t quantile is the normal one plus a short series in 1/dof


# ---------------------------------------------------------------------------------------------
# growth
# ---------------------------------------------------------------------------------------------

def log_growth(start: float, end: float, flow: float = 0.0) -> float | None:
    """ln((end - flow) / start): the log growth of an account over a period.

    `flow` is the net money paid in during the period (negative for money taken out); it is
    removed from `end` so that a deposit is not counted as profit. `None` when `start` is not
    positive (there was nothing to grow) or an input is not finite. When `start` is positive and
    `end - flow` is zero or less, the account is ruined and the answer is `RUIN`. Growth is floored
    at `RUIN`, so the function never falls as `end` rises.
    """
    if not all(math.isfinite(v) for v in (start, end, flow)) or start <= 0:
        return None
    left = end - flow
    if left <= 0:
        return RUIN
    ratio = left / start
    if ratio <= 0:  # underflow
        return RUIN
    return max(RUIN, math.log(ratio))


def max_drawdown(equity: Sequence[float]) -> float:
    """The largest fall from a peak to a later trough, as a fraction of the peak, in [0, 1].

    0 for fewer than two points. A fall to zero or below from a positive peak is 1. Points before
    the first positive peak have no peak to fall from and are ignored, as are values that are not
    finite.
    """
    peak = 0.0
    worst = 0.0
    for value in equity:
        if not math.isfinite(value):
            continue
        if value > peak:
            peak = value
        elif peak > 0:
            worst = max(worst, (peak - value) / peak)
    return min(1.0, worst)


# ---------------------------------------------------------------------------------------------
# Student's t
# ---------------------------------------------------------------------------------------------

def _ln(u: float, v: float) -> float:
    """ln(u) where v = 1 - u is known exactly: log1p keeps the digits when u is close to 1."""
    return math.log1p(-v) if u > 0.5 else math.log(u)


def _beta_cf(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function, by the modified Lentz method."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _TINY:
        d = _TINY
    d = 1.0 / d
    h = d
    for m in range(1, _CF_MAX_ITERATIONS + 1):
        m2 = 2.0 * m
        for term in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + term * d
            if abs(d) < _TINY:
                d = _TINY
            c = 1.0 + term / c
            if abs(c) < _TINY:
                c = _TINY
            d = 1.0 / d
            delta = d * c
            h *= delta
        if abs(delta - 1.0) < _CF_EPS:
            return h
    return h  # not reached in practice: the fraction converges in O(sqrt(max(a, b))) steps


def _betainc(a: float, b: float, x: float, y: float) -> float:
    """The regularized incomplete beta function I_x(a, b). `y` is 1 - x, passed in so that neither loses digits."""
    if x <= 0:
        return 0.0
    if y <= 0:
        return 1.0
    ln_front = a * _ln(x, y) + b * _ln(y, x) - (math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(ln_front) * _beta_cf(a, b, x) / a
    return 1.0 - math.exp(ln_front) * _beta_cf(b, a, y) / b


def _t_tail(t: float, dof: float) -> float:
    """P(T > t) for t >= 0."""
    if t <= 0:
        return 0.5
    t2 = t * t
    return 0.5 * _betainc(dof / 2.0, 0.5, dof / (dof + t2), t2 / (dof + t2))


def _t_pdf(t: float, dof: float) -> float:
    ln_c = math.lgamma((dof + 1.0) / 2.0) - math.lgamma(dof / 2.0) - 0.5 * math.log(dof * math.pi)
    return math.exp(ln_c - (dof + 1.0) / 2.0 * math.log1p(t * t / dof))


def _t_upper_series(q: float, dof: float) -> float:
    """The upper quantile for a large dof: the normal quantile plus the Cornish-Fisher terms in 1/dof
    (Abramowitz and Stegun 26.7.5). Beyond dof = 1e5 the first term left out is below 1e-15 for any
    q >= 1e-9, while the incomplete beta route starts to lose digits in lgamma of a large argument."""
    z = -_NORMAL.inv_cdf(q)
    z3, z5, z7, z9 = z ** 3, z ** 5, z ** 7, z ** 9
    return (z + (z3 + z) / (4.0 * dof) + (5.0 * z5 + 16.0 * z3 + 3.0 * z) / (96.0 * dof ** 2)
            + (3.0 * z7 + 19.0 * z5 + 17.0 * z3 - 15.0 * z) / (384.0 * dof ** 3)
            + (79.0 * z9 + 776.0 * z7 + 1482.0 * z5 - 1920.0 * z3 - 945.0 * z) / (92160.0 * dof ** 4))


def _t_upper_numeric(q: float, dof: float) -> float:
    """Solve P(T > t) = q for t > 0, with 0 < q < 0.5: Newton steps kept inside a bracket."""
    lo, hi = 0.0, 1.0
    while _t_tail(hi, dof) > q:
        lo, hi = hi, hi * 2.0
        if hi >= _T_MAX:
            return _T_MAX
    t = 0.5 * (lo + hi)
    for _ in range(400):
        excess = _t_tail(t, dof) - q  # positive while t is still too small
        if excess == 0:
            return t
        if excess > 0:
            lo = t
        else:
            hi = t
        density = _t_pdf(t, dof)
        step = t + excess / density if density > 0 else hi
        if not lo < step < hi:
            step = 0.5 * (lo + hi)
        if abs(step - t) <= 1e-15 * max(1.0, abs(t)) or hi - lo <= 1e-15 * max(1.0, hi):
            return step
        t = step
    return t


@lru_cache(maxsize=4096)
def _t_upper(q: float, dof: float) -> float:
    """The t with P(T > t) = q. Working from the tail probability keeps every digit of a small q,
    which `1 - q` would throw away."""
    if q == 0.5:
        return 0.0
    if q > 0.5:
        return -_t_upper(1.0 - q, dof)
    if dof == 1:
        return min(_T_MAX, 1.0 / math.tan(math.pi * q))  # Cauchy: exact
    if dof == 2:
        return min(_T_MAX, (1.0 - 2.0 * q) / math.sqrt(2.0 * q * (1.0 - q)))  # exact too
    if dof > _NORMAL_DOF:
        return _t_upper_series(q, dof)
    return _t_upper_numeric(q, dof)


def _check_alpha(alpha: float) -> None:
    if not 0.0 < alpha < 1.0:  # also refuses nan
        raise ValueError(f"alpha must be inside (0, 1), not {alpha!r}")


def t_quantile(p: float, dof: float) -> float:
    """The inverse CDF of Student's t with `dof` degrees of freedom (any real dof > 0).

    For dof >= 1 and 1e-9 < p < 1 - 1e-9 the error is below 1e-6, or below 1e-9 of the value where
    the value itself is huge (dof = 1 at p = 1 - 1e-9 is 3e8, and `p` does not carry enough digits
    for more). `ValueError` when p is not inside (0, 1) or dof is not positive.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be inside (0, 1), not {p!r}")
    if not dof > 0:
        raise ValueError(f"dof must be positive, not {dof!r}")
    dof = float(dof)
    return -_t_upper(p, dof) if p < 0.5 else _t_upper(1.0 - p, dof)  # 1 - p is exact for p >= 0.5


# ---------------------------------------------------------------------------------------------
# sequential tests on a mean
# ---------------------------------------------------------------------------------------------

def spend(alpha: float, look: int) -> float:
    """The alpha the k-th look of a sequential test may spend: alpha * 6 / (pi^2 k^2).

    The series 1/k^2 sums to pi^2/6, so all the looks together spend exactly alpha, and by the
    union bound an agent that is looked at for ever is still wrongly promoted with probability at
    most alpha. `ValueError` unless look is a whole number >= 1.
    """
    _check_alpha(alpha)
    if isinstance(look, bool) or not isinstance(look, int) or look < 1:
        raise ValueError(f"look must be a whole number >= 1, not {look!r}")
    return alpha * 6.0 / (math.pi ** 2 * look ** 2)


def _mean_sd(xs: Sequence[float]) -> tuple[list[float], float, float] | None:
    """(values, mean, sample sd), or None when the sample is empty or holds a value that is not finite.

    The sd is exactly 0 for a sample that is constant up to rounding noise: a ratio over a noise
    sd of 1e-17 is not evidence.
    """
    values = [float(x) for x in xs]
    if not values or not all(math.isfinite(v) for v in values):
        return None
    lo, hi = min(values), max(values)
    if lo == hi:
        return values, lo, 0.0
    n = len(values)
    try:
        mean = math.fsum(values) / n
        sd = math.sqrt(math.fsum((v - mean) * (v - mean) for v in values) / (n - 1))
    except OverflowError:  # values near the top of the float range: not a record anyone can judge
        return None
    if not math.isfinite(sd):
        return None
    if sd <= _FLAT * max(abs(lo), abs(hi)):
        sd = 0.0
    return values, mean, sd


def mean_bounds(xs: Sequence[float], alpha: float) -> dict | None:
    """One-sided confidence bounds on the mean of `xs`: {"n", "mean", "sd", "lcb", "ucb"}.

    lcb = mean - t(1 - alpha, n - 1) * sd / sqrt(n), and ucb is the same distance above. Each is a
    one-sided bound at level alpha on its own: the mean is above lcb with confidence 1 - alpha, and
    below ucb with confidence 1 - alpha (together they are a two-sided interval at 2 * alpha).
    `sd` is the sample sd (n - 1). `None` when n < 2 or a value is not finite. With no variance at
    all, lcb = ucb = mean: that is a record the t-interval cannot judge, see `lopsided`.
    """
    _check_alpha(alpha)
    sample = _mean_sd(xs)
    if sample is None or len(sample[0]) < 2:
        return None
    values, mean, sd = sample
    n = len(values)
    half = _t_upper(float(alpha), float(n - 1)) * sd / math.sqrt(n) if sd > 0 else 0.0
    return {"n": n, "mean": mean, "sd": sd, "lcb": mean - half, "ucb": mean + half}


def quarter_kelly(mean_lcb: float, variance: float, fraction: float = 0.25, cap: float = 1.0) -> float:
    """The share of capital to commit: fraction * mean_lcb / variance, clipped to [0, cap].

    Full Kelly is mean / variance, and it is ruinous when the mean is overestimated, so the size
    comes from the *lower bound* of the mean and only a quarter of it is taken. 0 when the lower
    bound or the variance is not positive, or anything is not finite.
    """
    if not all(math.isfinite(v) for v in (mean_lcb, variance, fraction, cap)):
        return 0.0
    if mean_lcb <= 0 or variance <= 0 or fraction <= 0 or cap <= 0:
        return 0.0
    return min(cap, fraction * mean_lcb / variance)


# ---------------------------------------------------------------------------------------------
# lopsided records: many small wins, rare large losses
# ---------------------------------------------------------------------------------------------

def wilson_upper(losses: int, n: int, alpha: float) -> float:
    """A one-sided Wilson score upper bound, at confidence 1 - alpha, on the probability of a loss
    after `losses` losses in `n` trades. 1.0 when n <= 0 (no evidence: assume the worst). With no
    loss on the record it is z^2 / (n + z^2). It is an approximation and runs a little low for
    records with few losses (see `exact_upper`, which the lopsided gate uses instead)."""
    _check_alpha(alpha)
    if n <= 0:
        return 1.0
    losses = min(max(losses, 0), n)
    z = -_NORMAL.inv_cdf(alpha)
    share = losses / n
    z2n = z * z / n
    centre = share + z2n / 2.0
    spread = z * math.sqrt(max(0.0, share * (1.0 - share) / n + z2n / (4.0 * n)))
    return min(1.0, max(0.0, (centre + spread) / (1.0 + z2n)))


def exact_upper(losses: int, n: int, alpha: float) -> float:
    """The exact (Clopper-Pearson) one-sided upper bound on a loss probability at confidence
    1 - alpha. The Wilson bound covers only about 92-94% at alpha = 0.05 for records with few
    losses, which is the very case this gate exists for; this one never covers less than it says.
    It is the p at which seeing `losses` or fewer in `n` has probability alpha. 1.0 when n <= 0
    (no evidence: assume the worst) or when every trade was a loss; a negative count is read as 0.
    With no loss on the record it is 1 - alpha^(1/n), about 3/n at alpha = 0.05."""
    _check_alpha(alpha)
    if n <= 0 or losses >= n:
        return 1.0
    losses = max(int(losses), 0)
    if losses == 0:
        return -math.expm1(math.log(alpha) / n)  # (1 - p)^n = alpha, solved exactly
    low, high = 0.0, 1.0
    for _ in range(200):  # P(X <= losses | p) = I_{1-p}(n - losses, losses + 1), decreasing in p
        mid = (low + high) / 2.0
        if not low < mid < high:  # the bracket is one float wide: `high` is the answer, on the safe side
            break
        if _betainc(n - losses, losses + 1.0, 1.0 - mid, mid) > alpha:
            low = mid
        else:
            high = mid
    return high


def lopsided(trade_returns: Sequence[float], min_win_rate: float = 0.8) -> bool:
    """True when there are at least 5 trades and the share of strictly positive returns is at least
    `min_win_rate`: a favourites-style record of many small wins and rare large losses, where a
    t-interval is badly anti-conservative until a loss has been seen."""
    n = len(trade_returns)
    if n < 5:
        return False
    return sum(1 for r in trade_returns if r > 0) / n >= min_win_rate


def lopsided_growth_lcb(trade_returns: Sequence[float], risk_per_trade: float, alpha: float) -> float | None:
    """A conservative lower bound on the expected log growth per trade of a lopsided record.

    `trade_returns` are per-trade returns as a fraction of the account's stake, after costs.
    The bound is (1 - p) * mean(ln(1 + win)) + p * ln(1 + loss), where

    - p is `exact_upper` of the count of returns <= 0 (a scratch counts as a loss),
    - the win term is the mean of ln(1 + w) over the strictly positive returns (0 when there are none),
    - loss is the most negative return seen, but never milder than -abs(risk_per_trade): until a
      full loss is on the record, assume one of everything that was at risk. It is clamped above
      -0.999999 so that the log stays finite (ln(1e-6), about `RUIN`).

    `None` when there are no trades. This bound is a gate, and a caller may read `None` as "no
    gate applies", so bad data never produces it: a return that is not finite is taken as a total
    loss, and a risk that is not finite as everything at risk.
    """
    _check_alpha(alpha)
    returns = [float(r) if math.isfinite(r) else -1.0 for r in trade_returns]
    if not returns:
        return None
    risk = abs(risk_per_trade) if math.isfinite(risk_per_trade) else 1.0
    wins = [r for r in returns if r > 0]
    p_loss = exact_upper(len(returns) - len(wins), len(returns), alpha)
    # The mean of the logs, not the log of the mean: uneven wins grow an account more slowly.
    win_growth = math.fsum(math.log1p(min(w, 1e300)) for w in wins) / len(wins) if wins else 0.0
    loss = max(-0.999999, min(min(returns), -risk))
    return (1.0 - p_loss) * win_growth + p_loss * math.log1p(loss)


# ---------------------------------------------------------------------------------------------
# Sharpe ratios, and deflating them for the number of trials
# ---------------------------------------------------------------------------------------------

def sharpe(xs: Sequence[float]) -> float | None:
    """mean / sample sd, per observation and not annualized. `None` when n < 2 or there is no variance."""
    sample = _mean_sd(xs)
    if sample is None or len(sample[0]) < 2 or sample[2] == 0:
        return None
    return sample[1] / sample[2]


def _standardized_moment(xs: Sequence[float], power: int, min_n: int) -> float | None:
    sample = _mean_sd(xs)
    if sample is None or len(sample[0]) < min_n or sample[2] == 0:
        return None
    values, mean, _ = sample
    n = len(values)
    scale = math.sqrt(math.fsum((v - mean) * (v - mean) for v in values) / n)  # population sd
    if not scale > 0:
        return None
    # Standardize first: each z is at most sqrt(n), so no power of it can overflow.
    return math.fsum(((v - mean) / scale) ** power for v in values) / n


def skewness(xs: Sequence[float]) -> float | None:
    """The third standardized moment, m3 / m2^1.5 (population estimator). `None` when n < 3 or no variance."""
    return _standardized_moment(xs, 3, 3)


def kurtosis(xs: Sequence[float]) -> float | None:
    """The fourth standardized moment, m4 / m2^2: NOT excess, a normal sample gives 3.
    `None` when n < 4 or no variance."""
    return _standardized_moment(xs, 4, 4)


def probabilistic_sharpe(sr: float, n: int, skew: float, kurt: float, benchmark: float = 0.0) -> float:
    """The probability that the true Sharpe ratio is above `benchmark`, given an estimate `sr` from
    `n` observations with the given skewness and (non-excess) kurtosis:

        Phi((sr - benchmark) * sqrt(n - 1) / sqrt(1 - skew * sr + (kurt - 1) / 4 * sr^2))

    Negative skew and fat tails widen the error of a Sharpe estimate, and this charges for both.
    Every real sample has kurt >= skew^2 + 1, which keeps the term under the root at or above
    (1 - skew * sr / 2)^2 >= 0; moments that break that are floored at a tiny positive number.
    0.5 (no evidence either way) when n < 2 or an input is not finite.
    """
    if n < 2 or not all(math.isfinite(v) for v in (sr, skew, kurt, benchmark)):
        return 0.5
    spread = max(1e-12, 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr)
    z = (sr - benchmark) * math.sqrt(n - 1) / math.sqrt(spread)
    if math.isnan(z):
        return 0.5
    return _NORMAL.cdf(z)


def expected_max_sharpe(
    trial_sharpes: Sequence[float], n_trials: int | None = None, *, fallback_variance: float = 0.0
) -> float:
    """The Sharpe ratio the best of N unskilled trials is expected to show by luck alone:

        sqrt(V) * ((1 - g) * Z^-1(1 - 1/N) + g * Z^-1(1 - 1/(N * e)))

    with g the Euler-Mascheroni constant and V the sample variance of the trials' Sharpe ratios,
    but never less than `fallback_variance`. The caller passes 1 / observations there, the variance
    a Sharpe estimate has from sampling noise alone when the true Sharpe is zero: trials that are
    variants of one idea move together and show less spread than that, and a small measured V
    must not lower the bar. It is also what stands in when V cannot be measured at all (fewer than
    two finite trial Sharpes, or all of them equal). N defaults to the number of trials listed;
    pass `n_trials` when more were run than were kept. 0.0 when N <= 1 (one trial is not a
    selection).
    """
    n = len(trial_sharpes) if n_trials is None else n_trials
    if not n > 1:
        return 0.0
    sample = _mean_sd([s for s in trial_sharpes if s is not None and math.isfinite(s)])
    variance = sample[2] ** 2 if sample is not None and len(sample[0]) >= 2 else 0.0
    # Correlated trials can show less spread than sampling noise alone would: never go below it.
    if math.isfinite(fallback_variance) and fallback_variance > variance:
        variance = fallback_variance
    quantiles = (1.0 - EULER_GAMMA) * -_NORMAL.inv_cdf(1.0 / n) + EULER_GAMMA * -_NORMAL.inv_cdf(1.0 / (n * math.e))
    return math.sqrt(variance) * quantiles


def deflated_sharpe(
    xs: Sequence[float], trial_sharpes: Sequence[float], n_trials: int | None = None
) -> dict | None:
    """The probabilistic Sharpe ratio of `xs` against the luck of all the trials that were run:
    {"sharpe", "n", "skew", "kurt", "benchmark", "dsr", "trials"}.

    benchmark = `expected_max_sharpe` of the trials (with 1 / n as the floor on their variance), and
    dsr = `probabilistic_sharpe` against that benchmark. More trials never raise it. `None` when
    the Sharpe ratio is undefined. With fewer than 3 (4) points the skewness (kurtosis) cannot be
    measured and the normal value 0 (3) stands in; the dict reports the values used.
    """
    ratio = sharpe(xs)
    if ratio is None:
        return None
    n = len(xs)
    skew = skewness(xs)
    kurt = kurtosis(xs)
    skew = 0.0 if skew is None else skew
    kurt = 3.0 if kurt is None else kurt
    trials = len(trial_sharpes) if n_trials is None else n_trials
    benchmark = expected_max_sharpe(trial_sharpes, n_trials, fallback_variance=1.0 / n)
    return {
        "sharpe": ratio,
        "n": n,
        "skew": skew,
        "kurt": kurt,
        "benchmark": benchmark,
        "dsr": probabilistic_sharpe(ratio, n, skew, kurt, benchmark),
        "trials": trials,
    }


# ---------------------------------------------------------------------------------------------
# decay
# ---------------------------------------------------------------------------------------------

def cusum_decay(xs: Sequence[float], reference_mean: float, sd: float, k: float = 0.5, h: float = 4.0) -> dict:
    """A one-sided lower CUSUM: has the mean of `xs` fallen below `reference_mean`?

    s_i = max(0, s_(i-1) + (reference_mean - x_i) / sd - k). The slack `k` (in sds) is what an
    honest series is forgiven at every step, and `h` is how much accumulated shortfall raises the
    alarm. Returns {"statistic": the largest s, "last": the final s, "alarm": last >= h,
    "at": the index of the first crossing of h, or None}. The alarm is on the *final* value: a
    series that crossed and then recovered keeps its `at` but is not in alarm now. With sd <= 0
    there is no scale to measure a shortfall on: no alarm, statistic 0. Values that are not finite
    are skipped.
    """
    quiet = {"statistic": 0.0, "last": 0.0, "alarm": False, "at": None}
    if not all(math.isfinite(v) for v in (reference_mean, sd, k, h)) or sd <= 0:
        return quiet
    s = 0.0
    statistic = 0.0
    at = None
    for index, x in enumerate(xs):
        if not math.isfinite(x):
            continue
        s = max(0.0, s + (reference_mean - x) / sd - k)
        statistic = max(statistic, s)
        if at is None and s >= h:
            at = index
    return {"statistic": statistic, "last": s, "alarm": s >= h, "at": at}

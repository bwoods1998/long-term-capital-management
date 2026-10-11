"""THE FORWARD METERS' ARITHMETIC (release E3): pure functions, each a pre-registered formula a test checks.

Owner: C (league/ops/E3_INTERFACES.md). Protected. No store, no clock, no file: arrays in, numbers out. The meters
that call these are league/ops/forward_report.py's; the forward shadow reads `t_stat` and `p_one_sided` for its
checkpoints (D4). Report only: nothing here is a verdict or a threshold.

- EXCESS, everywhere in E3: x = r - w * b, daily (`excess`; NOT `league.equity.screen.excess`, which subtracts a
  window mean).
- t AND p (D4): t = mean(x) / sd(x, ddof 1) * sqrt(n), None when n < 2 or sd < 1e-12; `p_one_sided(t, n)` the upper
  tail of a Student t with n - 1 degrees of freedom (t 0 gives 0.5).
- N_eff (D6), over members' daily excess inside the window: rho_ij the Pearson correlation of members i and j over
  their last n_ij = min(n_i, n_j) sessions (0 when either has no variance there). A raw rho^2 over n sessions carries
  about 1 / (n - 1) of sampling noise, so each is adjusted, rho~_ij^2 = 1 - (1 - rho_ij^2)(n_ij - 1) / (n_ij - 2),
  and summed unfloored over i != j. With N members: N_eff = min(N, N^2 / (N + max(0, sum_{i != j} rho~_ij^2))) (N_eff
  = N for N < 2). `neff_raw` = N^2 / sum_ij rho_ij^2 (the unadjusted participation ratio, rho_ii = 1) is stored
  beside, never used: it is capped near the window length and FALLS when short-history members are born.
- BH AND BY (D8), q = `forward_db.Q`: p_(1) <= ... <= p_(m); BH = max{k : p_(k) <= k q / m}; BY = max{k : p_(k) <= k
  q / (m H_m)}, H_m = sum_{j=1..m} 1/j (0 when none).
- THE REPLAY MULTIPLE (D7): sim_py / (hist_iy + CEY), None when the denominator is 0; `independent_years` is hist_iy:
  the sum over calendar years y of N_y * T_y / 252, N_y the adjusted N_eff formula on that year's daily returns.
- AN RC READ (D9): over a pair's usable sessions, d_t = a_t - b_t; t = mean(d_t) / sd(d_t, ddof 1) * sqrt(n).

Every sum and mean a statistic reads goes through `math.fsum` (the built-in `sum` is not exact on Python 3.11, and CI
runs 3.11 and 3.14). The correlations are numpy's products (`pairwise_corr`): their last digits follow the numpy
build, so a test compares them within a stated tolerance, never to the last digit. Standard library and numpy only
(numpy inside the functions that read arrays: `t_stat`, `p_one_sided`, `bh`, `by` and `replay_multiple` need none).
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .forward_db import NEFF_MIN_DAYS, Q

#: A standard deviation under this is no variance (D4: t is None; D6: the row is no member, the correlation 0).
SD_FLOOR = 1e-12
#: The fewest sessions the adjustment of a rho^2 can read (it divides by n - 2).
ADJUST_MIN_DAYS = 3
#: Sessions in a year (D6's cey_day and D7's years divide by it).
YEAR_SESSIONS = 252.0


def _floats(x: Any) -> list[float]:
    """A one-dimensional sequence or array as Python floats (ValueError for anything else)."""
    values = x.tolist() if callable(getattr(x, "tolist", None)) else list(x)
    if any(isinstance(v, (list, tuple)) for v in values):
        raise ValueError("a statistic reads one series (one dimension)")
    return [float(v) for v in values]


def _mean_sd(values: Sequence[float]) -> tuple[float, float]:
    """(mean, sd with ddof 1) of at least two finite floats, summed exactly."""
    n = len(values)
    mean = math.fsum(values) / n
    return mean, math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (n - 1))


def excess(r: Any, w: Any, b: Any) -> Any:
    """x = r - w * b, element by element (float64 ndarray; equal lengths, else ValueError)."""
    import numpy as np

    r, w, b = (np.asarray(v, dtype=np.float64) for v in (r, w, b))
    if not (r.shape == w.shape == b.shape) or r.ndim != 1:
        raise ValueError(f"excess reads three series of one length; got {r.shape}, {w.shape}, {b.shape}")
    return r - w * b


def t_stat(x: Any) -> float | None:
    """mean(x) / sd(x, ddof 1) * sqrt(n); None when n < 2, a value is not finite or sd < 1e-12."""
    values = _floats(x)
    n = len(values)
    if n < 2 or not all(math.isfinite(v) for v in values):
        return None
    mean, sd = _mean_sd(values)
    if not math.isfinite(sd) or sd < SD_FLOOR:
        return None
    return mean / sd * math.sqrt(n)


def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function (the modified Lentz method)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 20001):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            delta = d * c
            h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """The regularized incomplete beta function I_x(a, b), 0 <= x <= 1."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def p_one_sided(t: float | None, n: int) -> float | None:
    """The upper tail of a Student t with n - 1 degrees of freedom at `t` (0.5 at t 0); None when `t` is None or
    n < 2. Standard library and numpy only (no scipy)."""
    if t is None or isinstance(t, bool) or isinstance(n, bool):
        return None
    try:
        t, n = float(t), int(n)
    except (TypeError, ValueError):
        return None
    if n < 2 or math.isnan(t):
        return None
    if math.isinf(t):
        return 0.0 if t > 0 else 1.0
    df = float(n - 1)
    tail = 0.5 * _betainc(df / 2.0, 0.5, df / (df + t * t))   # P(T > |t|)
    return min(1.0, max(0.0, tail if t >= 0 else 1.0 - tail))


def _runs(X: Any) -> tuple[Any, Any, Any]:  # noqa: N803 - the contract's name
    """(X as float64 (N, T), n_i: each row's count of finite sessions ending at the last column, whether the row has
    variance over that run)."""
    import numpy as np

    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2:
        raise ValueError(f"the members' series are rows of one (N, T) array; got {X.ndim} dimensions")
    count, width = X.shape
    back = np.isfinite(X)[:, ::-1]
    runs = np.where(back.all(axis=1), width, np.argmin(back, axis=1)) if width else np.zeros(count, dtype=np.int64)
    varies = np.zeros(count, dtype=bool)
    for i in range(count):
        k = int(runs[i])
        if k >= 2:
            varies[i] = _mean_sd(X[i, width - k:].tolist())[1] >= SD_FLOOR
    return X, runs.astype(np.int64), varies


def _corr(X: Any, runs: Any, varies: Any) -> tuple[Any, Any]:  # noqa: N803
    """`pairwise_corr` on `_runs`' answer."""
    import numpy as np

    count, width = X.shape
    rho = np.zeros((count, count), dtype=np.float64)
    n_ij = np.minimum.outer(runs, runs)
    # Members of one run length share their window with every longer member: one product a distinct length.
    for length in sorted({int(k) for k in runs.tolist() if k >= 2}):
        longer = np.flatnonzero((runs >= length) & varies)
        same = np.flatnonzero((runs == length) & varies)
        if not same.size:
            continue
        block = X[longer, width - length:]
        block = block - block.mean(axis=1, keepdims=True)
        norm = np.sqrt((block * block).sum(axis=1))
        ok = norm >= SD_FLOOR * math.sqrt(length - 1)   # a longer member may have no variance in this shorter window
        unit = np.zeros_like(block)
        unit[ok] = block[ok] / norm[ok][:, None]
        part = unit[np.isin(longer, same)] @ unit.T
        rho[np.ix_(same, longer)] = part
        rho[np.ix_(longer, same)] = part.T
    np.clip(rho, -1.0, 1.0, out=rho)
    np.fill_diagonal(rho, 1.0)
    return rho, n_ij


def pairwise_corr(X: Any) -> tuple[Any, Any]:  # noqa: N803 - the contract's name
    """(rho, n_ij) of the rows of `X`: (N, T) float, NaN before a member's first day, each row's finite values a
    suffix. rho[i, j] is the Pearson correlation over the last n_ij[i, j] = min(n_i, n_j) sessions (0 when either row
    has no variance there; rho[i, i] = 1)."""
    return _corr(*_runs(X))


def _participation(rho: Any, n_ij: Any) -> tuple[float, float]:
    """(N_eff, the unadjusted ratio) of N >= 2 members' correlations (D6), each sum exact."""
    import numpy as np

    count = int(rho.shape[0])
    off = ~np.eye(count, dtype=bool)
    square, n = (rho * rho)[off], n_ij[off].astype(np.float64)
    adjusted = 1.0 - (1.0 - square) * (n - 1.0) / (n - 2.0)
    total = math.fsum(adjusted.tolist())
    raw = math.fsum(square.tolist())
    return min(float(count), count * count / (count + max(0.0, total))), count * count / (count + raw)


def neff(X: Any, *, min_days: int = NEFF_MIN_DAYS) -> dict[str, Any]:  # noqa: N803 - the contract's name
    """D6 on `X` (as `pairwise_corr` reads it): {"members" (rows kept: at least `min_days` finite sessions ending at the
    last column, with non-zero variance; the rest dropped), "n_w" (the columns), "neff", "neff_raw"}. `neff` is 0.0
    when n_w < `min_days`, the member count for fewer than 2 members. `neff_raw` is None with no member. `min_days`
    under 3 is a ValueError (the adjustment divides by n - 2)."""
    import numpy as np

    min_days = int(min_days)
    if min_days < ADJUST_MIN_DAYS:
        raise ValueError(f"min_days is at least {ADJUST_MIN_DAYS}: the adjustment of a rho^2 divides by n - 2")
    X, runs, varies = _runs(X)
    width = int(X.shape[1])
    if width < min_days:
        return {"members": 0, "n_w": width, "neff": 0.0, "neff_raw": None}
    keep = np.flatnonzero((runs >= min_days) & varies)
    count = int(keep.size)
    if count < 2:
        return {"members": count, "n_w": width, "neff": float(count), "neff_raw": float(count) if count else None}
    rho, n_ij = _corr(X[keep], runs[keep], varies[keep])
    value, raw = _participation(rho, n_ij)
    return {"members": count, "n_w": width, "neff": value, "neff_raw": raw}


def _p(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"a p-value is a number in [0, 1]; got {value!r}")
    return float(value)


def _step_up(pvalues: Sequence[float], q: float, penalty: float) -> int:
    """The largest k with p_(k) <= k q / (m * penalty) (a step-up count: 0 when none)."""
    if isinstance(q, bool) or not isinstance(q, (int, float)) or not 0.0 < float(q) < 1.0:
        raise ValueError(f"q is a rate in (0, 1); got {q!r}")
    ordered = sorted(_p(p) for p in pvalues)
    m, found = len(ordered), 0
    for k, p in enumerate(ordered, 1):
        if p <= k * float(q) / (m * penalty):
            found = k
    return found


def bh(pvalues: Sequence[float], q: float = Q) -> int:
    """Benjamini-Hochberg's count of rejections at `q` (0 for none or an empty family)."""
    return _step_up(pvalues, q, 1.0)


def by(pvalues: Sequence[float], q: float = Q) -> int:
    """Benjamini-Yekutieli's count at `q`: BH with q / H_m, H_m the m-th harmonic number."""
    pvalues = list(pvalues)
    return _step_up(pvalues, q, math.fsum(1.0 / j for j in range(1, len(pvalues) + 1)) or 1.0)


def independent_years(by_year: Mapping[int, Any]) -> float:
    """D7's hist_iy: the sum over years y of N_y * T_y / 252, each value an (S, T_y) array of S symbols' daily
    returns over the year's T_y sessions and N_y the adjusted N_eff of its rows (`neff`'s formula). A year too short to
    adjust a correlation (under 3 sessions) or with no symbol adds nothing."""
    import numpy as np

    parts = []
    for year in sorted(by_year):
        returns = np.asarray(by_year[year], dtype=np.float64)
        if returns.ndim != 2:
            raise ValueError(f"year {year}: the returns are an (S, T) array; got {returns.ndim} dimensions")
        if returns.shape[0] and returns.shape[1] >= ADJUST_MIN_DAYS:
            parts.append(neff(returns, min_days=ADJUST_MIN_DAYS)["neff"] * returns.shape[1] / YEAR_SESSIONS)
    return math.fsum(parts)


def replay_multiple(sim_py: float | None, hist_iy: float | None, cey_total: float | None) -> float | None:
    """sim_py / (hist_iy + cey_total); None when an input is None or the denominator is 0."""
    values = (sim_py, hist_iy, cey_total)
    if any(v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return None
    below = float(hist_iy) + float(cey_total)   # type: ignore[arg-type]
    return float(sim_py) / below if below > 0.0 else None   # type: ignore[arg-type]


def rc_read(a: Any, b: Any) -> dict[str, Any]:
    """One RC read of a pair: `a` and `b` are equal-length arrays of the two groups' daily means on the pair's usable
    sessions; {"n", "mean_bp" (the mean difference in 1e-4 of E0), "t" (sd with ddof 1; None when it has none)}."""
    first, second = _floats(a), _floats(b)
    if len(first) != len(second):
        raise ValueError(f"an RC read takes two series of one length; got {len(first)} and {len(second)}")
    diff = [x - y for x, y in zip(first, second)]
    n = len(diff)
    finite = n > 0 and all(math.isfinite(d) for d in diff)
    return {"n": n, "mean_bp": math.fsum(diff) / n * 1e4 if finite else None, "t": t_stat(diff)}


__all__ = ["excess", "t_stat", "p_one_sided", "pairwise_corr", "neff", "bh", "by", "independent_years",
           "replay_multiple", "rc_read"]

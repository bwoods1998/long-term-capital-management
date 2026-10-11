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
runs 3.11 and 3.14). Standard library and numpy only.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .forward_db import NEFF_MIN_DAYS, Q


def excess(r: Any, w: Any, b: Any) -> Any:
    """x = r - w * b, element by element (float64 ndarray; equal lengths, else ValueError)."""
    raise NotImplementedError("C: league/ops/forward_stats.py excess")


def t_stat(x: Any) -> float | None:
    """mean(x) / sd(x, ddof 1) * sqrt(n); None when n < 2, a value is not finite or sd < 1e-12."""
    raise NotImplementedError("C: league/ops/forward_stats.py t_stat")


def p_one_sided(t: float | None, n: int) -> float | None:
    """The upper tail of a Student t with n - 1 degrees of freedom at `t` (0.5 at t 0); None when `t` is None or
    n < 2. Standard library and numpy only (no scipy)."""
    raise NotImplementedError("C: league/ops/forward_stats.py p_one_sided")


def pairwise_corr(X: Any) -> tuple[Any, Any]:  # noqa: N803 - the contract's name
    """(rho, n_ij) of the rows of `X`: (N, T) float, NaN before a member's first day, each row's finite values a
    suffix. rho[i, j] is the Pearson correlation over the last n_ij[i, j] = min(n_i, n_j) sessions (0 when either row
    has no variance there; rho[i, i] = 1)."""
    raise NotImplementedError("C: league/ops/forward_stats.py pairwise_corr")


def neff(X: Any, *, min_days: int = NEFF_MIN_DAYS) -> dict[str, Any]:  # noqa: N803 - the contract's name
    """D6 on `X` (as `pairwise_corr` reads it): {"members" (rows kept: at least `min_days` finite sessions ending at the
    last column, with non-zero variance; the rest dropped), "n_w" (the columns), "neff", "neff_raw"}. `neff` is 0.0
    when n_w < `min_days`, the member count for fewer than 2 members."""
    raise NotImplementedError("C: league/ops/forward_stats.py neff")


def bh(pvalues: Sequence[float], q: float = Q) -> int:
    """Benjamini-Hochberg's count of rejections at `q` (0 for none or an empty family)."""
    raise NotImplementedError("C: league/ops/forward_stats.py bh")


def by(pvalues: Sequence[float], q: float = Q) -> int:
    """Benjamini-Yekutieli's count at `q`: BH with q / H_m, H_m the m-th harmonic number."""
    raise NotImplementedError("C: league/ops/forward_stats.py by")


def independent_years(by_year: Mapping[int, Any]) -> float:
    """D7's hist_iy: the sum over years y of N_y * T_y / 252, each value an (S, T_y) array of S symbols' daily
    returns over the year's T_y sessions and N_y the adjusted N_eff of its rows (`neff`'s formula)."""
    raise NotImplementedError("C: league/ops/forward_stats.py independent_years")


def replay_multiple(sim_py: float | None, hist_iy: float | None, cey_total: float | None) -> float | None:
    """sim_py / (hist_iy + cey_total); None when an input is None or the denominator is 0."""
    raise NotImplementedError("C: league/ops/forward_stats.py replay_multiple")


def rc_read(a: Any, b: Any) -> dict[str, Any]:
    """One RC read of a pair: `a` and `b` are equal-length arrays of the two groups' daily means on the pair's usable
    sessions; {"n", "mean_bp" (the mean difference in 1e-4 of E0), "t" (sd with ddof 1; None when it has none)}."""
    raise NotImplementedError("C: league/ops/forward_stats.py rc_read")


__all__ = ["excess", "t_stat", "p_one_sided", "pairwise_corr", "neff", "bh", "by", "independent_years",
           "replay_multiple", "rc_read"]

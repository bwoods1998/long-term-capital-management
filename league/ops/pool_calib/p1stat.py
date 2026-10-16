"""POOL1 calibration: THE STATISTIC (PREREG section 2) and the bar's grid (3.3). Pure numpy.

Per member and session t (2 step 2): a_t = r^g_t - sum_s w_{s,t} mu_s - sum_s what_{s,t} (R_{s,t} - mu_s), with
what_{s,t} = (PRIOR wbar_s + sum of w_s over the member's earlier counted days since it joined) / (PRIOR + their
count), decided at t-1; a15_t = a_t - (r_t - r15_t). r^g = r - g sides (the haircut). z = a / sigma_used,
sigma_used = max(sigma_i, 5 bp, sigma_tilde / 3), sigma_tilde = 1 / median(1 / sigma_j) over the unit's founders.

THE WINDOW MATRIX (`alpha_windows`): for every window start J and lag l, a(J, l) is a_{J+l} with what restarted at J
(the forward record starts a member at its first counted day): with X = R - mu, P_t = sum_s wbar_s X_{s,t},
CW_s[t] = sum_{u<t} w_{s,u}, Q_t = sum_s CW_s[t] X_{s,t} and K(J, t) = sum_s CW_s[J] X_{s,t},
    sum_s what_{s,t}(J) X_{s,t} = (PRIOR P_t + Q_t - K(J, t)) / (PRIOR + t - J).
`alpha_direct` is the same by a plain loop (the tests hold the two equal).

THE TEST (2 step 5): T_k = mean(D_1..k) / sd(D_1..k, ddof 1) sqrt(k) at k in PLAN; a look passes when T_k >= c and
sum(D15_1..k) > 1e-12 (the stress leg). `tby` gives, per window, the best valid T by each look (cumulative max), so
"passes by look j at grid k" is grid_index(tby[:, j]) >= k. numpy sums stand in for math.fsum (DEVIATIONS D17)."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from p1const import K_MAX, PLAN, PRIOR, SIGMA_FLOOR, WEIGHT_CAP, ZERO

GRID = np.arange(K_MAX + 1) / 100.0


# ---------------------------------------------------------------------------------------------- legs and alpha
def legs_close(W: np.ndarray, R: np.ndarray, hs: np.ndarray, *, k15: float = 1.5) -> tuple[np.ndarray, ...]:
    """Close-to-close legs of a per-symbol weight path W (S, T): W[:, t] is held through session t (decided at the
    close of t-1). -> (r, r15, sides, gross): r = sum W R - sum hs |dW|, r15 the same at k15 x hs, sides = sum |dW|
    (dW_t = W_t - W_{t-1}, W_{-1} = 0), gross = sum W R."""
    W = np.asarray(W, dtype=np.float64)
    dW = np.abs(np.diff(np.concatenate([np.zeros((W.shape[0], 1)), W], axis=1), axis=1))
    hs = np.asarray(hs, dtype=np.float64)[:, None]
    gross = (W * R).sum(0)
    cost = (hs * dW).sum(0)
    return gross - cost, gross - k15 * cost, dW.sum(0), gross


def exclusive_cumsum(W: np.ndarray) -> np.ndarray:
    """CW[:, t] = sum_{u < t} W[:, u]; one more column (CW[:, T] = the total)."""
    out = np.zeros((W.shape[0], W.shape[1] + 1))
    np.cumsum(W, axis=1, out=out[:, 1:])
    return out


def alpha_windows(base: np.ndarray, W: np.ndarray, X: np.ndarray, wbar: np.ndarray, starts: np.ndarray,
                  nlag: int, prior: float = PRIOR) -> np.ndarray:
    """(len(starts), nlag): a(J, l) = base[J+l] - sum_s what_{s,J+l}(J) X[s, J+l], NaN where J + l >= T.
    base = r^g - sum_s W_s mu_s (any accounting); W, X (S, T); wbar (S,)."""
    W = np.asarray(W, dtype=np.float64)
    X = np.asarray(X, dtype=np.float64)
    T = W.shape[1]
    starts = np.asarray(starts, dtype=np.int64)
    CW = exclusive_cumsum(W)[:, :T]                      # CW[:, t] = sum_{u<t} W[:, u]
    P = (np.asarray(wbar, dtype=np.float64)[:, None] * X).sum(0)
    Q = (CW * X).sum(0)
    CWJ = CW[:, starts]                                   # (S, nJ)
    out = np.full((len(starts), nlag), np.nan)
    for l in range(nlag):
        t = starts + l
        ok = t < T
        if not ok.any():
            break
        tt = np.where(ok, t, 0)
        K = (CWJ * X[:, tt]).sum(0)
        H = (prior * P[tt] + Q[tt] - K) / (prior + l)
        out[:, l] = np.where(ok, base[tt] - H, np.nan)
    return out


def alpha_direct(base: np.ndarray, W: np.ndarray, X: np.ndarray, wbar: np.ndarray, J: int, n: int,
                 prior: float = PRIOR) -> np.ndarray:
    """The same as one row of `alpha_windows`, by a plain loop (the tests' reference)."""
    S = W.shape[0]
    out = []
    acc = [0.0] * S
    cnt = 0
    for t in range(J, min(J + n, W.shape[1])):
        what = [(prior * float(wbar[s]) + acc[s]) / (prior + cnt) for s in range(S)]
        out.append(float(base[t]) - sum(what[s] * float(X[s, t]) for s in range(S)))
        for s in range(S):
            acc[s] += float(W[s, t])
        cnt += 1
    return np.array(out)


def alpha_era(base: np.ndarray, W: np.ndarray, X: np.ndarray, wbar: np.ndarray, prior: float = PRIOR) -> np.ndarray:
    """a over a whole pool with what restarted at its first session (one window spanning it)."""
    return alpha_windows(base, W, X, wbar, np.array([0]), W.shape[1], prior)[0]


def sigma_used(sigma: np.ndarray, sigma_tilde: float) -> np.ndarray:
    return np.maximum(np.maximum(np.asarray(sigma, dtype=np.float64), SIGMA_FLOOR), sigma_tilde / WEIGHT_CAP)


def sigma_tilde(sigmas: Sequence[float]) -> float:
    """1 / median(1 / sigma_j) over the founders (each sigma floored at 5 bp first, so the weight is finite)."""
    s = np.maximum(np.asarray(sigmas, dtype=np.float64), SIGMA_FLOOR)
    return float(1.0 / np.median(1.0 / s))


# ------------------------------------------------------------------------------------------------------- the test
def tby(D: np.ndarray, D15: np.ndarray, plan: Sequence[int] = PLAN) -> np.ndarray:
    """(n, len(plan)): per window (row of D, D15 of at least max(plan) cell sessions), the best valid T_k by each
    look (cumulative max over the looks so far); -inf where no look so far is valid. Valid: sd >= 1e-12, T finite
    and the stress sum above 1e-12. NaN rows give -inf."""
    D = np.asarray(D, dtype=np.float64)
    D15 = np.asarray(D15, dtype=np.float64)
    out = np.full((D.shape[0], len(plan)), -np.inf)
    best = np.full(D.shape[0], -np.inf)
    for j, k in enumerate(plan):
        x = D[:, :k]
        m = x.mean(axis=1)
        sd = x.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = m / sd * math.sqrt(k)
        s15 = D15[:, :k].sum(axis=1)
        ok = np.isfinite(t) & (sd >= ZERO) & np.isfinite(s15) & (s15 > ZERO)
        best = np.maximum(best, np.where(ok, t, -np.inf))
        out[:, j] = best
    return out


def t_direct(D: Sequence[float], D15: Sequence[float], plan: Sequence[int] = PLAN) -> list[float | None]:
    """Each look's T_k with math.fsum (None where invalid), for the hand-case tests."""
    out = []
    for k in plan:
        x = [float(v) for v in D[:k]]
        n = len(x)
        mean = math.fsum(x) / n
        var = math.fsum((v - mean) ** 2 for v in x) / (n - 1)
        sd = math.sqrt(var) if var > 0 else 0.0
        s15 = math.fsum(float(v) for v in D15[:k])
        if sd < ZERO or not s15 > ZERO:
            out.append(None)
        else:
            out.append(mean / sd * math.sqrt(k))
    return out


def grid_index(T: np.ndarray) -> np.ndarray:
    """The largest k in 0..500 with k / 100 <= T (fwd1_rule._grid); -1 for -inf, NaN or T < 0; 500 for T >= 5."""
    T = np.asarray(T, dtype=np.float64)
    T = np.where(np.isfinite(T) | (T == np.inf), T, -np.inf)
    g = np.searchsorted(GRID, T, side="right") - 1
    return np.minimum(g, K_MAX).astype(np.int16)


def curve(g: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    """C[k] = sum of the weights of the entries with grid index >= k, k = 0..500 (float64)."""
    g = np.asarray(g).ravel()
    w = np.ones(g.shape, dtype=np.float64) if w is None else np.asarray(w, dtype=np.float64).ravel()
    m = g >= 0
    acc = np.bincount(g[m].astype(np.int64), weights=w[m], minlength=K_MAX + 1)[:K_MAX + 1]
    return acc[::-1].cumsum()[::-1]


def smallest_k(share: np.ndarray, cap: float) -> int | None:
    """The smallest k on 0..500 with share[k] <= cap (share nonincreasing in k); None when even k = 500 fails."""
    ok = np.asarray(share) <= cap + 1e-12
    if not ok.any():
        return None
    return int(np.argmax(ok))


def floor_k(g: np.ndarray, w: np.ndarray, cap: float) -> int | None:
    """The smallest grid k whose weighted pass share (g >= k) is at most cap; None when none is, or no world."""
    tot = float(np.sum(w))
    if tot <= 0:
        return None
    return smallest_k(curve(g, w) / tot, cap)


def rreg_floor(g: np.ndarray, w: np.ndarray, cells: np.ndarray, cap: float) -> int | None:
    """R-REG: the largest, over the regime cells (cells: (n_worlds, n_cells) bool membership), of each cell's floor;
    a cell with no world is skipped; None when any cell has none."""
    best = 0
    any_cell = False
    for c in range(cells.shape[1]):
        sel = cells[:, c]
        if not sel.any():
            continue
        any_cell = True
        k = floor_k(g[sel], w[sel], cap)
        if k is None:
            return None
        best = max(best, k)
    return best if any_cell else None


def newey_west_z(x: np.ndarray, lag: int) -> float | None:
    """mean / sqrt(NW long-run variance / n) with Bartlett weights to `lag`; None for n < lag + 2 or zero variance."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < lag + 2:
        return None
    m = x.mean()
    e = x - m
    v = float(e @ e) / n
    for k in range(1, lag + 1):
        v += 2.0 * (1.0 - k / (lag + 1.0)) * float(e[k:] @ e[:-k]) / n
    if not v > 0:
        return None
    return float(m / math.sqrt(v / n))

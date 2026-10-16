"""POOL1 calibration: UNITS (cells and clusters), their worlds (every contiguous 120-cell-session window inside one
era), the point pass statistic and THE BOOTSTRAP (4.4).

POINT (`point_tby`): for every window start J of the unit's common span and the cell lags l0..l0+119 (l0: the first
lag with M_MIN active members), D(J, l) = the mean of z over the members active at lag l (a member joining at j is
active from lag j, with what restarted at J + j), z = (a - null mean) / sigma_used; D15 the same on a15. -> per window
the best valid T by each look (p1stat.tby).

BOOTSTRAP (`boot_g`, DEVIATIONS D6): a stationary block bootstrap of the unit's aligned daily series within the era
(mean block 120 sessions; B resamples), with the unit's members resampled with replacement on each draw; every
window is recomputed on each resample from the resampled series (z with what restarted at the span's first session,
not at each window's: the one approximation), with its regime cells recomputed from the resampled market series.
-> the grid index of each resampled window's best T by look 120, and its cells."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from p1const import B_BOOT, BLOCK_MEAN, L, M_MIN, PLAN, SEED_ROOT, ZERO
from p1members import EraBase, Member, cells_of, seed_of, unit_cells, vol_tercile, window_stats
from p1stat import GRID, grid_index, sigma_tilde, sigma_used, tby


@dataclass
class Unit:
    uid: str
    family: str
    group: str
    members: list
    joins: np.ndarray
    pattern: str
    roll_span: bool = False        # House units: N1 rolls inside the common span (stand-ins: inside the pool)
    cells: np.ndarray = None
    sig_u: np.ndarray = None
    span: dict = field(default_factory=dict)
    l0: int = 0
    meta: dict = field(default_factory=dict)

    @property
    def m(self) -> int:
        return len(self.members)


def make_unit(uid: str, family: str, group: str, members: list, joins, pattern: str, eras: list[int],
              roll_span: bool = False, founders_sigma: list | None = None) -> Unit:
    joins = np.asarray(joins, dtype=np.int64)
    u = Unit(uid=uid, family=family, group=group, members=list(members), joins=joins, pattern=pattern,
             roll_span=roll_span)
    u.cells = unit_cells(group)
    sig = [mm.sigma for mm in members]
    st = sigma_tilde(founders_sigma if founders_sigma is not None else sig)
    u.sig_u = sigma_used(np.array(sig), st)
    order = np.sort(joins)
    # l0: the first lag with M_MIN members active
    u.l0 = int(order[M_MIN - 1]) if len(order) >= M_MIN else 10 ** 6
    for e in eras:
        parts = [mm.parts[e] for mm in members]
        if any(p is None for p in parts):
            continue
        P0 = max(p.p0 for p in parts)
        P1 = min(p.p1 for p in parts)
        if P1 - P0 >= L + u.l0 + 1:
            u.span[e] = (P0, P1)
    return u


def starts_of(u: Unit, e: int) -> np.ndarray:
    P0, P1 = u.span[e]
    return np.arange(P0, P1 - L - u.l0 + 1)


def _dm(mm: Member, null: str, J: np.ndarray, vt: np.ndarray, means: dict | None) -> np.ndarray:
    """The per-window null mean of a member: 0 (N1, RAW), abar (N0), abar_v(J) (N0R)."""
    if null in ("N1", "RAW"):
        return np.zeros(len(J))
    abar, abar_v = (means[mm.name] if means is not None else (mm.abar, mm.abar_v))
    if null == "N0":
        return np.full(len(J), abar)
    v = vt[J]
    return np.where(v >= 0, np.asarray(abar_v)[np.maximum(v, 0)], abar)


def point_tby(u: Unit, e: int, null: str, offset: int | None, vt: np.ndarray, *, g3: bool = False,
              plant_sr: float = 0.0, means: dict | None = None, members_mask=None) -> tuple[np.ndarray, np.ndarray]:
    """(J, tby (nJ, 3)) of unit u on era e under `null` ("N0", "N0R", "N1", "RAW"); N1 needs `offset`. vt: the
    era's vol tercile by window start. `means` overrides the members' null means (OUT). `plant_sr`: a planted member
    Sharpe (annualized) on every member-day, in the member's own alpha sd. `members_mask`: members kept (G7)."""
    J = starts_of(u, e)
    span = u.span[e] if u.roll_span else None
    lags = u.l0 + np.arange(L)
    num = np.zeros((len(J), L))
    num15 = np.zeros((len(J), L))
    nact = np.zeros(L)
    for i, mm in enumerate(u.members):
        if members_mask is not None and not members_mask[i]:
            continue
        j = int(u.joins[i])
        off = offset if null == "N1" else None
        a_first, M = mm.A(e, off, span if off is not None else None)
        _, base, c15, _ = mm.path(e, off, span if off is not None else None)
        cols = lags - j
        act = cols >= 0
        nact += act
        rows = J + j - a_first
        sub = M[rows[:, None], np.where(act, cols, 0)[None, :]]
        t_abs = J[:, None] + lags[None, :]
        if g3:
            sub = sub - mm.g3_extra(e, off, span if off is not None else None)[t_abs]
        dm = _dm(mm, null, J, vt, means)[:, None]
        su = u.sig_u[i]
        z = (sub - dm) / su
        z15 = z - c15[t_abs] / su
        if plant_sr:
            shift = plant_sr / math.sqrt(252.0) * mm.sigma / su
            z = z + shift
            z15 = z15 + shift
        num += np.where(act[None, :], z, 0.0)
        num15 += np.where(act[None, :], z15, 0.0)
    nact = np.maximum(nact, 1)
    return J, tby(num / nact, num15 / nact)


# ------------------------------------------------------------------------------------------------- the bootstrap
def stationary_idx(n: int, B: int, seed, mean_block: int = BLOCK_MEAN) -> np.ndarray:
    """(B, n) indices of a stationary block bootstrap (Politis-Romano), circular inside 0..n-1."""
    g = np.random.default_rng(seed)
    new = g.random((B, n)) < 1.0 / mean_block
    new[:, 0] = True
    bid = np.cumsum(new, axis=1) - 1
    starts = g.integers(0, n, size=(B, n))
    first = np.zeros((B, n), dtype=np.int64)
    pos = np.arange(n)[None, :].repeat(B, axis=0)
    first_pos = np.where(new, pos, 0)
    first = np.maximum.accumulate(first_pos, axis=1)
    offset = pos - first
    s = np.take_along_axis(starts, bid, axis=1)
    return (s + offset) % n


class EraBoot:
    """The resampled regime cells of one era span: for each draw, the cells (B, nJ, 12) of each window start J' of
    the resampled span (J' in 0..n-L)."""

    def __init__(self, base: EraBase, P0: int, P1: int, cuts: np.ndarray, B: int, seed):
        self.P0, self.P1 = P0, P1
        n = P1 - P0
        self.idx = stationary_idx(n, B, seed)
        sub = base.sliced(P0, P1)
        starts = np.arange(0, n - L + 1)
        cells = np.zeros((B, len(starts), 12), dtype=bool)
        for b in range(B):
            cells[b] = cells_of(window_stats(sub, self.idx[b], starts), cuts)
        self.cells = cells


def boot_g(u: Unit, e: int, null: str, offset: int | None, eb: EraBoot, *, g3: bool = False,
           means: dict | None = None, seed=None, chunk: int = 250, counts: np.ndarray | None = None) -> np.ndarray:
    """(B, nJ') int16: the grid index of each resampled window's best valid T by look 120 (-1: none valid).
    `counts` (B, m) overrides the members' resample counts (tests: the identity)."""
    P0, P1 = u.span[e]
    assert (eb.P0, eb.P1) == (P0, P1), "the unit's span is not the bootstrap's"
    n = P1 - P0
    B = eb.idx.shape[0]
    span = (P0, P1) if u.roll_span else None
    off = offset if null == "N1" else None
    sp = span if off is not None else None
    m = u.m
    if counts is not None:
        cnt_all = np.asarray(counts, dtype=np.float64)
    else:
        g = np.random.default_rng([SEED_ROOT, 707, seed_of(u.uid, e, "members") if seed is None else seed])
        picks = g.integers(0, m, size=(B, m))
        cnt_all = np.zeros((B, m))
        for k in range(m):
            np.add.at(cnt_all, (np.arange(B), picks[:, k]), 1.0)
    levels = np.unique(u.joins)
    lev_of = np.searchsorted(levels, u.joins)
    nlev = len(levels)
    nJ = n - L - u.l0 + 1
    Jp = np.arange(nJ)
    bounds = list(levels) + [10 ** 9]
    # the members' resampled inputs: z (a / sigma_used, the N0 mean taken), c15 / sigma_used, the N0R means
    zs, cs, avs = [], [], []
    for i, mm in enumerate(u.members):
        a = mm.a_era(e, off, sp)[P0:P1]
        _, _, c15, _ = mm.path(e, off, sp)
        if g3:
            a = a - mm.g3_extra(e, off, sp)[P0:P1]
        su = u.sig_u[i]
        if null == "N0":
            a = a - (means[mm.name][0] if means is not None else mm.abar)
        zs.append(np.nan_to_num(a / su))
        cs.append(c15[P0:P1] / su)
        if null == "N0R":
            avs.append(np.asarray(means[mm.name][1] if means is not None else mm.abar_v) / su)
    out = np.empty((B, nJ), dtype=np.int16)
    for b0 in range(0, B, chunk):
        b1 = min(B, b0 + chunk)
        nb = b1 - b0
        idx = eb.idx[b0:b1]
        cnt = cnt_all[b0:b1]
        G = np.zeros((nlev, nb, n))
        C = np.zeros((nlev, nb, n))
        nq = np.zeros((nlev, nb))
        Acoef = np.zeros((nlev, nb, 3)) if null == "N0R" else None
        for i in range(m):
            q = lev_of[i]
            G[q] += cnt[:, i][:, None] * zs[i][idx]
            C[q] += cnt[:, i][:, None] * cs[i][idx]
            nq[q] += cnt[:, i]
            if Acoef is not None:
                Acoef[q] += cnt[:, i][:, None] * avs[i][None, :]
        G = np.cumsum(G, axis=0)
        C = np.cumsum(C, axis=0)
        nq = np.cumsum(nq, axis=0)
        if Acoef is not None:
            Acoef = np.cumsum(Acoef, axis=0)
            vt = vol_tercile(eb.cells[b0:b1, :nJ].reshape(-1, 12)).reshape(nb, nJ)
        zero = np.zeros((nlev, nb, 1))
        PG = np.concatenate([zero, np.cumsum(G, axis=2)], axis=2)
        PG2 = np.concatenate([zero, np.cumsum(G * G, axis=2)], axis=2)
        PC = np.concatenate([zero, np.cumsum(C, axis=2)], axis=2)
        del G, C
        best = np.full((nb, nJ), -np.inf)
        for k in PLAN:
            lo, hi = u.l0, u.l0 + k
            s1 = np.zeros((nb, nJ))
            s2 = np.zeros((nb, nJ))
            s15 = np.zeros((nb, nJ))
            for q in range(nlev):
                a0, a1 = max(lo, bounds[q]), min(hi, bounds[q + 1])
                if a1 <= a0:
                    continue
                ln = a1 - a0
                nn = np.maximum(nq[q], 1.0)[:, None]
                sg = PG[q][:, Jp + a1] - PG[q][:, Jp + a0]
                sg2 = PG2[q][:, Jp + a1] - PG2[q][:, Jp + a0]
                sc = PC[q][:, Jp + a1] - PC[q][:, Jp + a0]
                if Acoef is not None:
                    cq = np.take_along_axis(Acoef[q], np.maximum(vt, 0), axis=1)
                    cq = np.where(vt >= 0, cq, 0.0)
                    sg2 = sg2 - 2 * cq * sg + ln * cq * cq
                    sg = sg - ln * cq
                empty = (nq[q] <= 0)[:, None]
                s1 += np.where(empty, 0.0, sg / nn)
                s2 += np.where(empty, 0.0, sg2 / (nn * nn))
                s15 += np.where(empty, 0.0, (sg - sc) / nn)
            mean = s1 / k
            var = (s2 - s1 * s1 / k) / (k - 1)
            ok = (var > 1e-9 * np.maximum(s2 / k, 1e-300)) & (var > ZERO * ZERO) & (s15 > ZERO)
            with np.errstate(divide="ignore", invalid="ignore"):
                t = mean / np.sqrt(np.where(ok, var, 1.0)) * math.sqrt(k)
            best = np.maximum(best, np.where(ok & np.isfinite(t), t, -np.inf))
        out[b0:b1] = grid_index(best)
    return out


def share_curves(g: np.ndarray, w: float = 1.0) -> np.ndarray:
    """(B, 501): per draw the weighted count of windows with grid index >= k."""
    B, n = g.shape
    gi = g.astype(np.int64)
    flat = (np.arange(B)[:, None] * 502 + (gi + 1)).ravel()
    h = np.bincount(flat, minlength=B * 502).reshape(B, 502)[:, 1:] * w      # drop the -1 bin
    return h[:, ::-1].cumsum(axis=1)[:, ::-1]


def bound_curve(share_b: np.ndarray, point: np.ndarray, q: float = 0.975) -> np.ndarray:
    """(501,): max(Q97.5 over draws, point + Q97.5 - mean) of the share at each grid k (DEVIATIONS D6)."""
    qq = np.quantile(share_b, q, axis=0)
    return np.maximum(qq, point + qq - share_b.mean(axis=0))

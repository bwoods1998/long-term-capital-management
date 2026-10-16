"""POOL1 calibration: MEMBERS (one program's Train-era series per era), THE NULLS (4.3) and THE REGIME CELLS (4.4).

A Member holds, per era, its pool span [p0, p1) in the era's session index, its per-symbol exposure path W (S, T),
its own net legs r, r15 and sides (close-to-close for the stand-ins; the House's lot accounting for House members
and twins) and the era's per-symbol cost-free returns R (S, T).

CONSTANTS (frozen from IN, 2 step 3): mu_s = the mean of R_s over the member's pool days of both IN eras; wbar_s the
mean of W_s there; sigma = sd (ddof 1) of a over both pools with what restarted at each pool start; abar its mean
(N0); abar_v its mean over the days of the pool windows of SPY volatility tercile v, inclusion-weighted (N0R,
DEVIATIONS D5).

THE NULLS. N0: a - abar. N0R: a - abar_v(J), v the window's SPY volatility tercile. N1 (drift kept, timing killed):
the per-symbol path rolled circularly inside its pool by an offset o (one common offset for a unit), r, r15 and
sides recomputed on the rolled path close-to-close (DEVIATIONS D7), the statistic read RAW; the allowed offsets are
those of N1_OFFSETS under the pool's length less 120, and the N1 rate is the mean over them (DEVIATIONS D4).
G3 (worse fills): a less sum_s |dW_s| (2 bp + 10 bp eps), eps standard normal, seeded per member, era and path.

REGIME CELLS (4.4), per window [J, J + 120): terciles of SPY's realized volatility (vol0-2) and of its return
(ret0-2); for sector units also the mean cross-sectional sd of the sector ETFs' daily returns (those with a return on
every session of the window: disp0-2); for defensive units the TLT-GLD window return gap (gap0-2). Cutpoints are set
on the IN windows and applied unchanged elsewhere."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from p1const import (G3_NOISE, G3_WORSE, HAIRCUT, HS_BP, K_STRESS, L, LAG_MAX, N1_OFFSETS, SEC_ALL, SEED_ROOT)
from p1stat import alpha_era, alpha_windows, legs_close

CELL_NAMES = ("vol0", "vol1", "vol2", "ret0", "ret1", "ret2", "disp0", "disp1", "disp2", "gap0", "gap1", "gap2")


def seed_of(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def offsets_for(n: int) -> tuple[int, ...]:
    """The N1 offsets allowed in a pool (or common span) of n sessions: under n - 120."""
    return tuple(o for o in N1_OFFSETS if o < n - L)


# ------------------------------------------------------------------------------------------------------- regimes
@dataclass
class EraBase:
    """The daily series the regime cells read, on one era's calendar (index 0..T-1). The sectors are taken in launch
    order; `rank[t]` is the length of the longest launch-ordered prefix of them with a return on day t (the local rows
    are nested: a sector, once listed, has a return every later session); `sd_rank[r, t]` the cross-sectional sd (ddof 1) of the
    first r sectors' returns on day t (NaN where rank[t] < r or r < 2)."""
    spy: np.ndarray
    tlt: np.ndarray
    gld: np.ndarray
    rank: np.ndarray
    sd_rank: np.ndarray

    @classmethod
    def from_returns(cls, R: dict, have: dict) -> "EraBase":
        secs = [s for s in SEC_ALL if s in R]
        T = len(R["SPY"])
        first = {s: (int(np.argmax(have[s])) if have[s].any() else T + 1) for s in secs}
        order = sorted(secs, key=lambda s: (first[s], s))
        H = np.array([have[s] for s in order])
        rank = np.zeros(T, dtype=np.int64)
        for t in range(T):
            col = H[:, t]
            rank[t] = int(np.argmin(col)) if not col.all() else len(order)   # the launch-ordered prefix present
        X = np.array([R[s] for s in order])
        sd_rank = np.full((len(order) + 1, T), np.nan)
        for r in range(2, len(order) + 1):
            ok = rank >= r
            sd_rank[r, ok] = X[:r, ok].std(axis=0, ddof=1)
        return cls(spy=np.asarray(R["SPY"], dtype=np.float64), tlt=np.asarray(R["TLT"], dtype=np.float64),
                   gld=np.asarray(R["GLD"], dtype=np.float64), rank=rank, sd_rank=sd_rank)

    def sliced(self, P0: int, P1: int) -> "EraBase":
        return EraBase(spy=self.spy[P0:P1], tlt=self.tlt[P0:P1], gld=self.gld[P0:P1], rank=self.rank[P0:P1],
                       sd_rank=self.sd_rank[:, P0:P1])


def window_stats(base: EraBase, idx: np.ndarray | None, starts: np.ndarray) -> np.ndarray:
    """(n_starts, 4): SPY realized vol, SPY return, sector dispersion and the TLT-GLD return gap of each window
    [J, J+L) of the series taken in the order `idx` (a resampled order; None: as it is)."""
    def take(x):
        return x if idx is None else x[..., idx]
    spy = take(base.spy)
    c1 = np.concatenate([[0.0], np.cumsum(spy)])
    c2 = np.concatenate([[0.0], np.cumsum(spy * spy)])
    lc = np.concatenate([[0.0], np.cumsum(np.log1p(spy))])
    s1 = c1[starts + L] - c1[starts]
    s2 = c2[starts + L] - c2[starts]
    vol = np.sqrt(np.maximum((s2 - s1 * s1 / L) / (L - 1), 0.0))
    ret = np.expm1(lc[starts + L] - lc[starts])
    rank = take(base.rank)
    sdr = take(base.sd_rank)
    disp = np.full(len(starts), np.nan)
    minrank = np.full(len(starts), -1)
    for r in np.unique(rank):
        below = np.concatenate([[0], np.cumsum(rank < r)])
        none_below = (below[starts + L] - below[starts]) == 0
        minrank = np.where(none_below, np.maximum(minrank, r), minrank)
    for r in np.unique(minrank):
        if r < 2:
            continue
        sel = minrank == r
        cs = np.concatenate([[0.0], np.cumsum(np.nan_to_num(sdr[r]))])
        disp[sel] = (cs[starts[sel] + L] - cs[starts[sel]]) / L
    tl = np.concatenate([[0.0], np.cumsum(np.log1p(take(base.tlt)))])
    gl = np.concatenate([[0.0], np.cumsum(np.log1p(take(base.gld)))])
    gap = np.expm1(tl[starts + L] - tl[starts]) - np.expm1(gl[starts + L] - gl[starts])
    return np.stack([vol, ret, disp, gap], axis=1)


def cutpoints(stats: np.ndarray) -> np.ndarray:
    """(4, 2): the tercile cutpoints of each statistic over the IN windows (NaN-free entries)."""
    out = np.zeros((4, 2))
    for c in range(4):
        x = stats[:, c]
        x = x[np.isfinite(x)]
        out[c] = np.quantile(x, [1 / 3, 2 / 3])
    return out


def cells_of(stats: np.ndarray, cuts: np.ndarray) -> np.ndarray:
    """(n, 12) bool: membership in vol0-2, ret0-2, disp0-2, gap0-2 (a NaN statistic is in none of its three)."""
    n = stats.shape[0]
    out = np.zeros((n, 12), dtype=bool)
    for c in range(4):
        x = stats[:, c]
        fin = np.isfinite(x)
        lo, hi = cuts[c]
        t = np.where(x <= lo, 0, np.where(x <= hi, 1, 2))
        for k in range(3):
            out[:, 3 * c + k] = fin & (t == k)
    return out


def unit_cells(group: str) -> np.ndarray:
    """The regime columns a unit is judged in: the 6 SPY cells, plus dispersion (sectors) or the gap (defensive)."""
    cols = list(range(6))
    if group == "sectors":
        cols += [6, 7, 8]
    elif group == "defensive":
        cols += [9, 10, 11]
    return np.array(cols)


def vol_tercile(cells: np.ndarray) -> np.ndarray:
    """0, 1, 2 from the vol columns (-1 when none)."""
    v = np.full(cells.shape[0], -1)
    for k in range(3):
        v[cells[:, k]] = k
    return v


# -------------------------------------------------------------------------------------------------------- members
@dataclass
class EraPart:
    p0: int
    p1: int
    W: np.ndarray              # (S, T) exposure path (0 outside the pool)
    r: np.ndarray              # (T,) net return at k 1.0 (0 outside)
    r15: np.ndarray
    sides: np.ndarray
    R: np.ndarray              # (S, T) per-symbol close-to-close return
    lots: bool = False         # lot-accounted (House, twins): N1 is recomputed close-to-close


@dataclass
class Member:
    name: str
    family: str
    group: str
    cls: str
    syms: tuple
    parts: list                # one EraPart (or None) per era
    hs: np.ndarray = None
    mu: np.ndarray = None
    wbar: np.ndarray = None
    sigma: float = None
    abar: float = None
    abar_v: np.ndarray = None
    meta: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.hs is None:
            self.hs = np.array([HS_BP[s] / 1e4 for s in self.syms])

    # ------------------------------------------------------------------------------------------ the path's pieces
    def path(self, e: int, offset: int | None = None, span: tuple[int, int] | None = None):
        """(W, base, c15, dS) of era e: the original path, or the N1 path rolled by `offset` inside `span`
        (default the pool). base = r - g sides - sum_s W mu; c15 = r - r15; dS (S, T) = |dW| per symbol."""
        key = ("path", e, offset, span)
        if key in self.cache:
            return self.cache[key]
        pt = self.parts[e]
        p0, p1 = span if span is not None else (pt.p0, pt.p1)
        W = pt.W
        if offset is None:
            r, r15, sides = pt.r, pt.r15, pt.sides
            dS = np.abs(np.diff(np.concatenate([np.zeros((W.shape[0], 1)), W], axis=1), axis=1))
        else:
            n = p1 - p0
            Wr = np.zeros_like(W)
            seg = W[:, p0:p1]
            Wr[:, p0:p1] = np.roll(seg, -int(offset) % n, axis=1)
            W = Wr
            r, r15, sides, _ = legs_close(W, pt.R, self.hs, k15=K_STRESS)
            dS = np.abs(np.diff(np.concatenate([np.zeros((W.shape[0], 1)), W], axis=1), axis=1))
            mask = np.zeros(W.shape[1], dtype=bool)
            mask[p0:p1] = True
            r, r15, sides = np.where(mask, r, 0.0), np.where(mask, r15, 0.0), np.where(mask, sides, 0.0)
            dS = dS * mask[None, :]
        base = r - HAIRCUT * sides - (W * self.mu[:, None]).sum(0)
        out = (W, base, r - r15, dS)
        self.cache[key] = out
        return out

    def X(self, e: int) -> np.ndarray:
        return self.parts[e].R - self.mu[:, None]

    def g3_extra(self, e: int, offset: int | None, span=None) -> np.ndarray:
        """(T,) the G3 cost: sum_s |dW_s| (2 bp + 10 bp eps), eps seeded per (member, era, offset)."""
        key = ("g3", e, offset, span)
        if key in self.cache:
            return self.cache[key]
        _, _, _, dS = self.path(e, offset, span)
        g = np.random.default_rng([SEED_ROOT, 303, seed_of(self.name, e, offset, span)])
        eps = g.standard_normal(dS.shape)
        out = (dS * (G3_WORSE + G3_NOISE * eps)).sum(0)
        self.cache[key] = out
        return out

    def a_era(self, e: int, offset: int | None = None, span=None) -> np.ndarray:
        """(T,) a with what restarted at the span's (pool's) first session; NaN outside it."""
        key = ("aera", e, offset, span)
        if key in self.cache:
            return self.cache[key]
        pt = self.parts[e]
        p0, p1 = span if span is not None else (pt.p0, pt.p1)
        W, base, _, _ = self.path(e, offset, span)
        out = np.full(W.shape[1], np.nan)
        out[p0:p1] = alpha_era(base[p0:p1], W[:, p0:p1], self.X(e)[:, p0:p1], self.wbar)
        self.cache[key] = out
        return out

    def A(self, e: int, offset: int | None = None, span=None) -> tuple[int, np.ndarray]:
        """(first start, matrix): a(J, l) for every start J in [p0, p1) of the span and l < LAG_MAX."""
        key = ("A", e, offset, span)
        if key in self.cache:
            return self.cache[key]
        pt = self.parts[e]
        p0, p1 = span if span is not None else (pt.p0, pt.p1)
        W, base, _, _ = self.path(e, offset, span)
        starts = np.arange(p0, p1)
        Wp, Xp = W[:, :p1], self.X(e)[:, :p1]
        M = alpha_windows(base[:p1], Wp, Xp, self.wbar, starts, LAG_MAX)
        out = (p0, M)
        self.cache[key] = out
        return out

    def drop(self, keep_paths: bool = False):
        self.cache = {k: v for k, v in self.cache.items() if keep_paths and k[0] == "path"}


def fit_constants(m: Member, eras_in: list[int], vol_cells: dict[int, np.ndarray]) -> None:
    """mu, wbar from the pools of the IN eras; then sigma, abar and abar_v on a (what restarted at each pool start).
    vol_cells[e]: (T_e - L + 1,) the vol tercile of each window start J of era e (-1 where undefined)."""
    Rs, Ws = [], []
    for e in eras_in:
        pt = m.parts[e]
        if pt is None:
            continue
        Rs.append(pt.R[:, pt.p0:pt.p1])
        Ws.append(pt.W[:, pt.p0:pt.p1])
    m.mu = np.concatenate(Rs, axis=1).mean(axis=1)
    m.wbar = np.concatenate(Ws, axis=1).mean(axis=1)
    m.cache = {}
    a_all = []
    num = np.zeros(3)
    den = np.zeros(3)
    for e in eras_in:
        pt = m.parts[e]
        if pt is None:
            continue
        a = m.a_era(e)
        a_all.append(a[pt.p0:pt.p1])
        n_v = inclusion_by_tercile(pt.p0, pt.p1, vol_cells[e], len(a))
        for v in range(3):
            num[v] += float(np.nansum(n_v[v] * np.nan_to_num(a)))
            den[v] += float(n_v[v].sum())
    a_all = np.concatenate(a_all)
    m.sigma = float(a_all.std(ddof=1))
    m.abar = float(a_all.mean())
    m.abar_v = np.where(den > 0, num / np.maximum(den, 1e-300), m.abar)


def null_means(m: Member, eras: list[int], vol_cells: dict[int, np.ndarray]) -> tuple[float, np.ndarray]:
    """(abar, abar_v) of a over the given eras' pools with the member's frozen constants (OUT's own null means)."""
    a_all = []
    num = np.zeros(3)
    den = np.zeros(3)
    for e in eras:
        pt = m.parts[e]
        a = m.a_era(e)
        a_all.append(a[pt.p0:pt.p1])
        n_v = inclusion_by_tercile(pt.p0, pt.p1, vol_cells[e], len(a))
        for v in range(3):
            num[v] += float(np.nansum(n_v[v] * np.nan_to_num(a)))
            den[v] += float(n_v[v].sum())
    abar = float(np.concatenate(a_all).mean())
    return abar, np.where(den > 0, num / np.maximum(den, 1e-300), abar)


def inclusion_by_tercile(p0: int, p1: int, vt: np.ndarray, T: int) -> np.ndarray:
    """(3, T): how many windows [J, J+L) with J in [p0, p1-L] of each vol tercile hold each session."""
    out = np.zeros((3, T + 1))
    for J in range(p0, p1 - L + 1):
        v = vt[J] if J < len(vt) else -1
        if v < 0:
            continue
        out[v, J] += 1
        out[v, J + L] -= 1
    return np.cumsum(out, axis=1)[:, :T]


def stand_in_member(name: str, fam: str, syms, W: np.ndarray, era_parts: list, group: str, cls: str) -> Member:
    """A close-to-close member from per-era weight paths: era_parts[e] = (W_e, R_e, p0, p1) or None."""
    hs = np.array([HS_BP[s] / 1e4 for s in syms])
    parts = []
    for item in era_parts:
        if item is None:
            parts.append(None)
            continue
        We, Re, p0, p1 = item
        r, r15, sides, _ = legs_close(We, Re, hs, k15=K_STRESS)
        mask = np.zeros(We.shape[1], dtype=bool)
        mask[p0:p1] = True
        parts.append(EraPart(p0=p0, p1=p1, W=We * mask[None, :], r=np.where(mask, r, 0.0),
                             r15=np.where(mask, r15, 0.0), sides=np.where(mask, sides, 0.0), R=Re))
    return Member(name=name, family=fam, group=group, cls=cls, syms=tuple(syms), parts=parts, hs=hs)

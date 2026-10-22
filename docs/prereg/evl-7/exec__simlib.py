"""simlib.py: shared SYNTHETIC generator and screen for the EXEC-7 calibrations (costs, execution, hold structure).

SYNTHETIC ONLY. Nothing here reads the lane, the House, the gateway, events.sqlite, live.sqlite or any market data.
Every return below is drawn from the generator, whose shape copies the risks PREREG-EVL-6's judge generator holds
(goal-2026-10-19/evl6/judge/calib_judge.py): a residual day shock common to every event of a session with factor
momentum (AR 0.10), symmetric t(3) days or crash days (5% of sessions at -3 sd: skew -1.6), a persistent family drift
(AR 0.97), a volatility regime (AR 0.9), heteroskedastic names (sigma 1%-10% a session, log-uniform), t(3) event noise
and mean-compensated +-30% jumps at 0.5% an event. One block = one session (one-auction-span holds), or one calendar
session of exposure (calendar-time blocks for multi-session holds).

THE SCREEN (a proxy of PREREG-EVL-6's candidate "SB-SEQ" as its judge's search file reads it on Oct 22: a look at every
block S = 7..120 (S = 6 cannot cross: the exact minimum p is 1/64), crossing when the one-sided sign-flip p of
mean(x - m0) > 0 is <= c / S with c = 0.09, >= 30 events, mean a > 0 and mean r > 0. Exact sign-flip p for S <= 14, Monte
Carlo (9,999 fixed vectors) above. The issuer guard and the control guard are left out: they can only lower a pass
rate, so every false-positive figure here is an upper bound for the full screen.)
"""
from __future__ import annotations

import itertools
import math
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402

TIE = 1e-12
EXACT_S = 14
B_MC = 9_999
S_MIN, S_MAX, C_SEQ = 7, 120, 0.09
MIN_EV = 30
Z_PRE = 1.3


def unit_t3(rng, size, left=1.0, right=1.0):
    x = rng.standard_t(3.0, size) / math.sqrt(3.0)
    if left != 1.0 or right != 1.0:
        x = np.where(x < 0, left * x, right * x)
        m_abs = 2.0 * math.sqrt(3.0) / math.pi / math.sqrt(3.0)  # E|t3| / sd(t3) = 2 sqrt(3)/pi / sqrt(3)
        m1 = (right - left) * m_abs / 2.0
        m2 = (left ** 2 + right ** 2) / 2.0
        x = (x - m1) / math.sqrt(m2 - m1 ** 2)
    return x


def day_innov(rng, kind, size):
    if kind == "t3":
        return unit_t3(rng, size)
    p, k = (0.05, 3.0)
    m = p * k / (1 - p)
    s = math.sqrt((1 - p * (k * k + 1)) / (1 - p) - m * m)
    hit = rng.random(size) < p
    return np.where(hit, rng.normal(-k, 1.0, size), rng.normal(m, s, size))


V0 = ((0.10 ** 2 - 0.01 ** 2) / (2.0 * math.log(10.0))) + 0.005 * 0.30 ** 2 + 0.0001 + 3e-5


def sd_day(rho_day):
    return math.sqrt(rho_day / (1.0 - rho_day) * V0) if rho_day > 0 else 0.0


class DayProcess:
    """The common processes of R independent replicates, one session at a time: day shock c (AR phi), drift D (AR
    0.97), volatility h (AR 0.9), benchmark b."""

    def __init__(self, rng, R, rho_day=0.05, day="t3", drift_sd=0.0, phi=0.10, drift_rho=0.97):
        self.rng, self.R, self.day, self.phi = rng, R, day, phi
        self.sdc = sd_day(rho_day)
        self.drift_sd, self.drift_rho = drift_sd, drift_rho
        self.z = day_innov(rng, day, R)
        self.D = rng.standard_normal(R) * drift_sd if drift_sd > 0 else np.zeros(R)
        self.lv = rng.standard_normal(R) * 0.3

    def step(self):
        rng, R = self.rng, self.R
        self.lv = 0.9 * self.lv + math.sqrt(1 - 0.81) * 0.3 * rng.standard_normal(R)
        h = np.exp(self.lv - 0.09)
        if self.drift_sd > 0:
            self.D = self.drift_rho * self.D + math.sqrt(1 - self.drift_rho ** 2) * self.drift_sd * rng.standard_normal(R)
        self.z = self.phi * self.z + math.sqrt(1 - self.phi ** 2) * day_innov(rng, self.day, R)
        b = 0.0004 + 0.010 * rng.standard_normal(R)
        return self.sdc * self.z, self.D.copy(), h, b


def event_noise(rng, n, ev="t3"):
    """Per-event idiosyncratic return (one session): sigma_i x t3 (+ mean-compensated jumps)."""
    sig = np.exp(rng.uniform(math.log(0.01), math.log(0.10), n))
    left, right = (1.4, 0.6) if ev == "skew" else (1.0, 1.0)
    e = sig * unit_t3(rng, n, left, right)
    hit = rng.random(n) < 0.005
    jl = 0.8 if ev == "skew" else 0.5
    sgn = np.where(rng.random(n) < jl, -1.0, 1.0)
    jmean = 0.005 * 0.30 * (1.0 - 2.0 * jl)
    return e + hit * sgn * 0.30 - jmean


def gen_blocks(seed, R, T, nbar, rho_day=0.05, day="t3", drift_sd=0.0, ev="t3", mu=0.0):
    """One-session-hold program paths: B (R x T) block mean a, N (R x T) events, BR (R x T) block mean r."""
    rng = np.random.default_rng(seed)
    dp = DayProcess(rng, R, rho_day, day, drift_sd)
    B = np.zeros((R, T))
    BR = np.zeros((R, T))
    N = np.zeros((R, T), np.int64)
    rows = np.arange(R)
    for t in range(T):
        c, D, h, b = dp.step()
        n = rng.poisson(nbar * rng.gamma(3.0, 1.0 / 3.0, R))
        tot = int(n.sum())
        if tot == 0:
            continue
        er = np.repeat(rows, n)
        a = mu + D[er] + h[er] * (c[er] + event_noise(rng, tot, ev))
        a = np.maximum(a, -1.0)
        s = np.bincount(er, a, R)
        N[:, t] = n
        B[:, t] = np.where(n > 0, s / np.maximum(n, 1), 0.0)
        BR[:, t] = np.where(n > 0, B[:, t] + b, 0.0)
    return B, BR, N


_PAT: dict[int, np.ndarray] = {}
_SIGNS = None


def _pat(S):
    if S not in _PAT:
        _PAT[S] = np.array(list(itertools.product((-1.0, 1.0), repeat=S)), dtype=np.float64)
    return _PAT[S]


def _signs():
    global _SIGNS
    if _SIGNS is None:
        _SIGNS = np.where(np.random.default_rng(20261022).random((B_MC, S_MAX + 400)) < 0.5, -1.0, 1.0).astype(np.float32)
    return _SIGNS


def signflip_p(X):
    """One-sided sign-flip p of mean > 0 for each row of X (k x S)."""
    k, S = X.shape
    T = X.sum(axis=1)
    A = np.abs(X)
    out = np.empty(k)
    for lo in range(0, k, 256):
        hi = min(lo + 256, k)
        if S <= EXACT_S:
            M = _pat(S) @ A[lo:hi].T
            out[lo:hi] = np.count_nonzero(M >= (T[lo:hi] - S * TIE)[None, :], axis=0) / float(1 << S)
        else:
            M = _signs()[:, :S] @ A[lo:hi].T.astype(np.float32)
            thr = (T[lo:hi] - 1e-6 * np.abs(T[lo:hi]) - S * TIE).astype(np.float32)
            out[lo:hi] = (1 + np.count_nonzero(M >= thr[None, :], axis=0)) / (1.0 + B_MC)
    return out


def compress(B, N, BR):
    """Blocks = sessions with >= 1 event, left-aligned: Xc (R x T), Rc, Nc, cnt (blocks), and the session of each
    block (sess, -1 padding)."""
    R, T = B.shape
    has = N > 0
    order = np.argsort(~has, axis=1, kind="stable")
    Xc = np.take_along_axis(B, order, axis=1)
    Rc = np.take_along_axis(BR, order, axis=1)
    Nc = np.take_along_axis(N, order, axis=1)
    cnt = has.sum(axis=1)
    sess = np.where(np.arange(T)[None, :] < cnt[:, None], order, -1)
    return Xc, Rc, Nc, cnt, sess


def screen_first_pass(Xc, Rc, Nc, cnt, sess, shift=None, m0=0.0, s_max=S_MAX, c=C_SEQ, t_max=None):
    """First session (0-based, the session of the passing block) at which each path passes, -1 if never.

    shift: None, or an (R x T) array: the per-event cost shift IN FORCE at session t, added to every block of a look
    written at session t (a cost basis applied to the whole record at the look). The look at block S is written at
    session sess[S-1]."""
    R, T = Xc.shape
    first = np.full(R, -1, np.int64)
    csum_n = np.cumsum(Nc, axis=1)
    csum_x_w = np.cumsum(Xc * Nc, axis=1)   # event-weighted sums for the money condition
    csum_r_w = np.cumsum(Rc * Nc, axis=1)
    alive = np.ones(R, bool)
    for S in range(S_MIN, min(s_max, T) + 1):
        ok = alive & (cnt >= S)
        if not ok.any():
            continue
        idx = np.nonzero(ok)[0]
        at = sess[idx, S - 1]
        if t_max is not None:
            keep = at <= t_max
            idx, at = idx[keep], at[keep]
            if idx.size == 0:
                continue
        mu = shift[idx, at] if shift is not None else np.zeros(idx.size)
        X = Xc[idx, :S] + mu[:, None] - m0
        nev = csum_n[idx, S - 1]
        mean_a = csum_x_w[idx, S - 1] / np.maximum(nev, 1) + mu
        mean_r = csum_r_w[idx, S - 1] / np.maximum(nev, 1) + mu
        sx = X.sum(axis=1)
        z = sx / np.sqrt(np.maximum((X * X).sum(axis=1), 1e-30))
        cand = (nev >= MIN_EV) & (mean_a > 0) & (mean_r > 0) & (z >= Z_PRE)
        if not cand.any():
            continue
        ci = idx[cand]
        p = signflip_p(X[cand])
        hit = p <= c / S + TIE
        if hit.any():
            won = ci[hit]
            first[won] = sess[won, S - 1]
            alive[won] = False
    return first

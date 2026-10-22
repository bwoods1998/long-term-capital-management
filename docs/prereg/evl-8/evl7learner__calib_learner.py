#!/usr/bin/env python
"""calib_learner.py: SYNTHETIC calibration of PREREG-EVL-7's pre-registered online learners (lens: learner).

Nothing here reads the live lane: no events.sqlite, no live.sqlite, no House, no gateway, no market data, no price,
no return, no look, no band. Every number comes from the generator below, chosen blind.

THE LEARNER UNDER TEST ("SDR-K8": session-demeaned ridge, top 8 above a cost hurdle), per replicate:
  each session t a POOL of n_t candidate events (the union of the controls' events at one auction, one per issuer);
  every candidate has a feature vector x (D = 40: 5 family dummies, 5 score features, 5 score x family, 13 binaries,
  7 issuer-level, 5 event-level continuous). The learner, at its decision of session t, knows only the outcomes of
  sessions <= t - LAG (LAG = 2: an overnight program's events settle the night after their exit).
  TRAINING: target y = clip(a / sigma_hat, -5, 5); within every settled session the features and y are demeaned
  (session fixed effects: the day shock, the stream drift and the benchmark cancel); sufficient statistics A = sum w
  X~'X~, b = sum w X~'y~ with exponential forgetting w = 2^(-age / H); ridge on standardised columns,
  beta = D^-1 (D^-1 A D^-1 + lam I)^-1 D^-1 b, D = sqrt(diag(A) / N_w).
  PREDICTION: e_i = (x_i - xbar_t) . beta (the candidate's predicted vol-scaled excess over today's pool).
  LEVEL L_i (what the pool itself is predicted to earn): V1 = -cost_i / sigma_hat_i (the prior that the pool's GROSS
  abnormal mean is zero; no learning, no timing); V2 = (n0 L0 + sum_s ybar_s) / (n0 + S) (an expanding mean with a
  prior); V3 = EWMA of ybar_s with half-life H (timing); V0 = +inf (no hurdle: always the top K).
  PICK: eligible (not picked in the last 5 sessions), L_i + e_i > 0, the top K by L_i + e_i. WARM-UP: no pick until
  the training set holds >= WARM_ROWS rows from >= WARM_SESSIONS sessions (pre-registration sessions count).
THE RECORD = the picks (each one session long). Its block value B_t = mean a of the picks of session t; its CONTROL =
the pool's mean a of session t (the learner must beat the pool it picks from).

THE GENERATOR (the EVL-6 judge's risk set, goal-2026-10-19/evl6/judge/calib_judge.py, re-implemented):
  3000 issuers, 11 sectors, Zipf(0.8) popularity (the same names recur), sigma_i log-uniform 1%-10% a session, three
  style factors (loadings N((.2,-.1,.2), .5^2)), a persistent issuer effect tau_i ~ N(0, tau) (issuer-repeated
  returns), a vol regime h_t = exp(x_t - .09), x AR(.9) sd .3.
  a = sigma_i E[y|x] + D_t + Dfam_{f,t} + h_t (c_t + s_sector,t + beta_i . f_t + sigma_i e_it) + jump + tau_i, floor -1;
  r = a + b_t, b_t ~ N(4 bp, 1%).
  c_t: the residual DAY shock common to the session's events, sd_c z_t, z_t = phi z_{t-1} + sqrt(1-phi^2) eps_t,
       eps 't3' (unit t3) or 'crash' (5% of sessions N(-3, 1), skew -1.6); sd_c^2 = rho_day / (1 - rho_day) x V0.
  e_it unit t3, or LEFT-SKEWED (two-piece t3, scales 1.4 / 0.6); jumps +-30% w.p. 0.5% (50% or 80% down), mean-
  compensated. D_t: a STREAM-WIDE persistent drift AR(drift_rho) with stationary sd drift_sd (it hits every candidate
  alike, so no selection escapes it). Dfam: per-family zero-mean drifts (a STRESS: trackable by the family dummies).
NULLS: N1 (features carry nothing: E[y|x] = 0, every candidate's mean a exactly 0); N2 THE KNIFE EDGE (the features
  rank the pool for real, E[y|x] = ic x min(u - u95, 0): the top 5% by the true index u have mean exactly 0 and every
  other event is worse, so a learner that learns the ranking perfectly buys events whose mean is exactly 0 while
  beating its pool by a wide margin: the control condition never protects it).
ALTERNATIVES: A (E[y|x] = mu_z + ic u, mu_z = -0.04: the pool loses about the round-trip cost and the features carry
  an information coefficient ic); A2 (the same, the true weights half sign-flipped at session 60: a regime change).

THE SCREENS applied to the learner's record (the seating screen it would face):
  EVL3   PREREG-EVL-3 section 3 exactly as registered, minus its skew check (which only tightens: an upper bound):
         looks at >= 60, 90, 135, 200, 300, 450, 675, ... events with >= 40 issuers and >= 8 blocks; session-block
         and issuer-block sign-flip p each <= 0.018; mean a > 0; mean r > 0; beats its control; PREREG-EVL-3's
         retirement (mean a < 0 and the reversed session-block p <= 0.05 at a held look).
  L12    the EVL-6 judge's leading 10%-cap candidate (search_alone_L0_main.jsonl, 'list:7,...,30', const 0.01, m0 10
         bp, full guards, retirement): looks at the first block-adding close with S >= 7, 8, 9, 10, 11, 12, 14, 16, 18,
         20, 25, 30 and >= 30 events and >= 30 issuers; p of mean(B - 0.001) > 0 <= 0.01; mean a > 0; mean r > 0;
         beats its control; issuer-block p <= 0.10; retire first when mean a < 0 and the lower-tail p <= 0.01.
  E840   the judge's other 10%-cap candidate ('every:8:40', c/S with c = 0.125, m0 10 bp, full guards, retirement).
  Sign-flip p exact over all 2^S vectors for S <= 16, else (1 + #) / (1 + 19,999) over 19,999 fixed vectors; a p is
  computed only where z = sum x / sqrt(sum x^2) >= 1.0 (no alpha here is above 0.018, which needs z near 2).

Usage: calib_learner.py run --grid GRID [--workers 4] [--reps R] [--out PREFIX]   |   selftest
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TIE = 1e-12
V0 = 0.0027
EXACT_S = 16
B_MC = 19_999
B_ISS3 = 4_999        # PREREG-EVL-3's issuer test at 0.018
B_ISS6 = 999          # EVL-6's issuer guard at 0.10
Z_PRE = 1.0
SECTOR_W = np.array([.22, .14, .12, .11, .09, .08, .07, .06, .04, .04, .03])
FAM_P = np.array([.40, .20, .12, .10, .10, .08])          # six pool families (the ON pool has six, O1 four)
D = 40
U = 3000
V3_NS = (60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250)
L12 = (7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 25, 30)


@dataclasses.dataclass(frozen=True)
class Cell:
    name: str
    null: str = "N1"          # N1 | N2 | A | A2
    ic: float = 0.0
    mu_z: float = 0.0
    nbar: float = 300.0
    T: int = 120
    pre: int = 3
    rho_day: float = 0.05
    day: str = "t3"
    ev_skew: bool = False
    jump_left: float = 0.5
    drift_sd: float = 0.0
    drift_rho: float = 0.97
    fam_drift_sd: float = 0.0
    tau: float = 0.0
    phi_day: float = 0.10
    fac_rho: float = 0.0
    load_corr: float = 0.0
    K: int = 8
    H: float = 40.0
    lam: float = 2000.0
    level: str = "V1"
    n0: float = 60.0
    L0: float = -0.04
    warm_rows: int = 2000
    warm_sessions: int = 3
    lag: int = 2
    learn: bool = True        # False: a RANDOM picker (the same K, hurdle-free): the fixed-program reference
    rank: str = "z"           # z: rank by the vol-scaled prediction; a: by sigma_hat x z, the predicted after-cost return
    kappa: float = 0.0        # the pessimistic hurdle: pick only when z - kappa x se(e) > 0

    def sd_day(self) -> float:
        return math.sqrt(self.rho_day / (1.0 - self.rho_day) * V0) if self.rho_day > 0 else 0.0


# ------------------------------------------------------------------------------------------------ shapes
def unit_t3(rng, size, left=1.0, right=1.0):
    x = rng.standard_t(3.0, size) / math.sqrt(3.0)
    if left != 1.0 or right != 1.0:
        x = np.where(x < 0, left * x, right * x)
        am = 2.0 * math.sqrt(3.0) * math.gamma(2.0) / (math.sqrt(math.pi) * 2.0 * math.gamma(1.5)) / math.sqrt(3.0)
        m1 = (right - left) * am / 2.0
        m2 = (left ** 2 + right ** 2) / 2.0
        x = (x - m1) / math.sqrt(m2 - m1 ** 2)
    return x


def day_innov(rng, kind, R):
    if kind == "t3":
        return unit_t3(rng, R)
    p, k = (0.05, 3.0) if kind == "crash" else (0.03, 4.5)
    m = p * k / (1 - p)
    s = math.sqrt((1 - p * (k * k + 1)) / (1 - p) - m * m)
    hit = rng.random(R) < p
    return np.where(hit, rng.normal(-k, 1.0, R), rng.normal(m, s, R))


# ------------------------------------------------------------------------------------------------ features
W_TRUE = np.zeros(D)
# indices: 0-4 family dummies (families 1..5), 5 s_num, 6 s>=2, 7 s=3, 8 s<=-1, 9 missing, 10-14 s x fam(1..5),
#          15-27 binaries, 28-34 issuer level (ln_adv, ln_px, ln_sig, sic0..3), 35-39 event continuous
#          (r1, r5, r20, n_art, dmove)
W_TRUE[5] = 0.5
W_TRUE[6] = 0.3
W_TRUE[0] = 0.3
W_TRUE[30] = 0.3
W_TRUE[39] = -0.3
W_TRUE[35] = -0.2
W_TRUE[10] = 0.3
W_FLIP = W_TRUE.copy()
W_FLIP[[5, 0, 39]] *= -1.0       # A2: after session 60 the score, a family and the day move reverse
BIN_P = np.array([.05, .08, .10, .12, .15, .18, .20, .25, .30, .35, .40, .10, .06])
SCORE_P = {0: [.06, .08, .10, .30, .16, .20, .10], 1: [.05, .07, .10, .25, .13, .25, .15],
           2: [.05, .07, .08, .25, .15, .25, .15]}


def issuers(rng, R, cell):
    """Per-replicate issuer attributes (R, U)."""
    ranks = np.argsort(rng.random((R, U)), axis=1) + 1
    logp = -0.8 * np.log(ranks.astype(float))
    sector = rng.choice(11, size=(R, U), p=SECTOR_W)
    lsig = rng.uniform(math.log(0.01), math.log(0.10), (R, U))
    sig = np.exp(lsig)
    zs = (lsig - lsig.mean()) / lsig.std()
    beta = rng.normal(0, 0.5, (R, U, 3)) + np.array([0.2, -0.1, 0.2])
    if cell.load_corr:
        zb = (beta[..., 0] - 0.2) / 0.5
        zs = cell.load_corr * zb + math.sqrt(1 - cell.load_corr ** 2) * zs
    tau = rng.normal(0, cell.tau, (R, U)) if cell.tau > 0 else np.zeros((R, U))
    lnadv = -0.6 * zs + 0.8 * rng.normal(0, 1, (R, U))
    lnpx = -0.4 * zs + 0.9 * rng.normal(0, 1, (R, U))
    lnsig_f = zs + 0.3 * rng.normal(0, 1, (R, U))
    sic = np.zeros((R, U, 4))
    for g in range(4):
        sic[..., g] = (sector == g)
    sig_hat = sig * np.exp(0.15 * rng.normal(0, 1, (R, U)))
    cost = np.where(lnadv > -0.3, 0.0011, 0.0021)            # 11 bp or 21 bp a round trip (the replay's allowance)
    ilev = np.concatenate([lnadv[..., None], lnpx[..., None], lnsig_f[..., None], sic], axis=2)   # (R, U, 7)
    return dict(logp=logp, sector=sector, sig=sig, sig_hat=sig_hat, beta=beta, tau=tau, ilev=ilev, cost=cost)


def pool_features(rng, R, N, iss, ids):
    """X (R, N, D) and the family index (R, N) of the pool's events."""
    fam = rng.choice(6, size=(R, N), p=FAM_P)
    X = np.zeros((R, N, D))
    for f in range(1, 6):
        X[..., f - 1] = (fam == f)
    fgrp = np.where(fam == 0, 0, np.where(fam <= 2, 1, 2))
    u = rng.random((R, N))
    s = np.zeros((R, N))
    for g in range(3):
        cp = np.cumsum(SCORE_P[g])
        sg = np.searchsorted(cp, u) - 3
        s = np.where(fgrp == g, sg, s)
    s = np.clip(s, -3, 3)
    miss = rng.random((R, N)) < 0.10
    s = np.where(miss, 0, s)
    X[..., 5] = s / 3.0
    X[..., 6] = (s >= 2)
    X[..., 7] = (s == 3)
    X[..., 8] = (s <= -1)
    X[..., 9] = miss
    for f in range(5):
        X[..., 10 + f] = X[..., 5] * X[..., f]
    X[..., 15:28] = rng.random((R, N, 13)) < BIN_P
    X[..., 28:35] = np.take_along_axis(iss["ilev"], ids[..., None], axis=1)
    X[..., 35] = np.clip(unit_t3(rng, (R, N)), -5, 5)
    X[..., 36] = np.clip(unit_t3(rng, (R, N)), -5, 5)
    X[..., 37] = np.clip(unit_t3(rng, (R, N)), -5, 5)
    X[..., 38] = np.log1p(rng.poisson(1.5, (R, N)))
    X[..., 39] = np.clip(unit_t3(rng, (R, N)), -5, 5)
    return X, fam


_UNORM: dict = {}


def u_norm(w, seed=7):
    """Population mean, sd and 0.95 quantile of the true index u_raw = X . w (from a large draw)."""
    key = tuple(np.round(w, 6))
    if key not in _UNORM:
        rng = np.random.default_rng(seed)
        c = Cell("norm")
        iss = issuers(rng, 4, c)
        ids = rng.integers(0, U, (4, 5000))
        X, _ = pool_features(rng, 4, 5000, iss, ids)
        ur = (X @ w).ravel()
        m, sd = ur.mean(), ur.std()
        _UNORM[key] = (m, sd, float(np.quantile((ur - m) / sd, 0.95)))
    return _UNORM[key]


# ------------------------------------------------------------------------------------------------ simulation
def simulate(cell: Cell, seed: int, R: int) -> dict:
    rng = np.random.default_rng(seed)
    T, K = cell.T, cell.K
    iss = issuers(rng, R, cell)
    Nmax = int(cell.nbar * 3.2) + 20
    sd_c = cell.sd_day()
    zday = np.zeros(R)
    vx = rng.normal(0, 0.3, R)
    drift = rng.normal(0, cell.drift_sd, R) if cell.drift_sd else np.zeros(R)
    fdrift = rng.normal(0, cell.fam_drift_sd, (R, 6)) if cell.fam_drift_sd else np.zeros((R, 6))
    fac = np.zeros((R, 3))
    # learner state
    A = np.zeros((R, D, D))
    bv = np.zeros((R, D))
    Nw = np.zeros(R)
    yy = np.zeros(R)
    rows = np.zeros(R)
    nsess = np.zeros(R)
    lev_sum = np.zeros(R)
    lev_n = np.zeros(R)
    lev_ew = np.full(R, cell.L0)
    lev_ew_w = np.zeros(R)
    pend: list = []
    delta = 2.0 ** (-1.0 / cell.H) if math.isfinite(cell.H) else 1.0
    last = np.full((R, U), -10_000, dtype=np.int64)
    out_B = np.full((R, T), np.nan)
    out_Rm = np.full((R, T), np.nan)
    out_n = np.zeros((R, T), dtype=np.int16)
    out_ctrl = np.full((R, T), np.nan)
    out_iss = np.full((R, T, K), -1, dtype=np.int32)
    out_a = np.full((R, T, K), np.nan)
    curve_edge = np.full((R, T), np.nan)      # the picks' TRUE expected a (no noise): the learning curve
    curve_ic = np.full((R, T), np.nan)        # within-session corr(e, y) over the pool (realised IC)
    oracle_edge = np.full((R, T), np.nan)     # the top K by the TRUE expectation, same hurdle logic (positive only)
    fixed_edge = np.full((R, T), np.nan)      # a fixed filter: score >= 2, K random of them
    w_now = W_TRUE
    um, usd, u95 = u_norm(W_TRUE)
    for t in range(-cell.pre, T):
        if cell.null == "A2" and t == 60:
            w_now = W_FLIP
            um, usd, u95 = u_norm(W_FLIP)
        # ---- the pool of session t
        n_t = np.minimum(rng.poisson(cell.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
        ids = np.take_along_axis(ids, order, axis=1)          # the n_t largest Gumbel keys = a Zipf draw without replacement
        valid = np.arange(Nmax)[None, :] < n_t[:, None]
        X, fam = pool_features(rng, R, Nmax, iss, ids)
        if cell.null in ("A", "A2", "N2"):
            u = (X @ w_now - um) / usd
            if cell.null == "N2":
                Ey = cell.ic * np.minimum(u - u95, 0.0)
            else:
                Ey = cell.mu_z + cell.ic * u
        else:
            u = None
            Ey = np.zeros((R, Nmax))
        sig = np.take_along_axis(iss["sig"], ids, axis=1)
        sig_hat = np.take_along_axis(iss["sig_hat"], ids, axis=1)
        cost = np.take_along_axis(iss["cost"], ids, axis=1)
        sec = np.take_along_axis(iss["sector"], ids, axis=1)
        beta = np.take_along_axis(iss["beta"], ids[..., None], axis=1)
        tau = np.take_along_axis(iss["tau"], ids, axis=1)
        # ---- day-level shocks
        zday = cell.phi_day * zday + math.sqrt(1 - cell.phi_day ** 2) * day_innov(rng, cell.day, R)
        c_t = sd_c * zday
        vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
        h_t = np.exp(vx - 0.09)
        s_sec = unit_t3(rng, (R, 11)) * 0.010
        if cell.fac_rho:
            fac = cell.fac_rho * fac + math.sqrt(1 - cell.fac_rho ** 2) * unit_t3(rng, (R, 3)) * 0.006
        else:
            fac = unit_t3(rng, (R, 3)) * 0.006
        if cell.drift_sd:
            drift = cell.drift_rho * drift + math.sqrt(1 - cell.drift_rho ** 2) * rng.normal(0, cell.drift_sd, R)
        if cell.fam_drift_sd:
            fdrift = cell.drift_rho * fdrift + math.sqrt(1 - cell.drift_rho ** 2) * rng.normal(0, cell.fam_drift_sd, (R, 6))
        b_t = rng.normal(0.0004, 0.010, R)
        e = unit_t3(rng, (R, Nmax), 1.4, 0.6) if cell.ev_skew else unit_t3(rng, (R, Nmax))
        jl = 0.8 if cell.ev_skew else cell.jump_left
        jump = np.where(rng.random((R, Nmax)) < 0.005, np.where(rng.random((R, Nmax)) < jl, -0.30, 0.30), 0.0)
        jump = jump - 0.005 * 0.30 * (1 - 2 * jl)
        noise = h_t[:, None] * (c_t[:, None] + np.take_along_axis(s_sec, sec, axis=1)
                                + np.einsum("rnk,rk->rn", beta, fac) + sig * e)
        a = sig * Ey + drift[:, None] + np.take_along_axis(fdrift, fam, axis=1) + noise + jump + tau
        a = np.maximum(a, -1.0)
        r = a + b_t[:, None]
        y = np.clip(a / sig_hat, -5, 5)
        vf = valid.astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        # ---- the learner's training: sessions <= t - lag are settled
        while pend and pend[0][0] <= t - cell.lag:
            _, As, bs, ns, ybar, ys = pend.pop(0)
            A = delta * A + As
            bv = delta * bv + bs
            yy = delta * yy + ys
            Nw = delta * Nw + ns
            rows += ns
            nsess += (ns > 0)
            lev_sum += ybar
            lev_n += 1
            lam_ew = 2.0 ** (-1.0 / cell.H)
            lev_ew_w = lam_ew * lev_ew_w + 1.0
            lev_ew = lev_ew + (ybar - lev_ew) / lev_ew_w
        # ---- the decision of session t (only t >= 0 is recorded)
        if t >= 0:
            elig = valid & (np.take_along_axis(last, ids, axis=1) < t - 5)
            xbar = (X * vf[..., None]).sum(axis=1) / nv[:, None]
            Xc = X - xbar[:, None, :]
            ready = (rows >= cell.warm_rows) & (nsess >= cell.warm_sessions)
            if cell.learn:
                dsd = np.sqrt(np.maximum(np.einsum("rii->ri", A) / np.maximum(Nw, 1)[:, None], 1e-12))
                As_ = A / (dsd[:, :, None] * dsd[:, None, :]) + cell.lam * np.eye(D)[None]
                bs_ = bv / dsd
                beta_s = np.linalg.solve(As_, bs_[..., None])[..., 0]
                bhat = beta_s / dsd
                ehat = np.einsum("rnd,rd->rn", Xc, bhat)
                if cell.level == "V1":
                    lev = -cost / sig_hat
                elif cell.level == "V2":
                    lev = ((cell.n0 * cell.L0 + lev_sum) / (cell.n0 + lev_n))[:, None] + 0 * ehat
                elif cell.level == "V3":
                    lev = lev_ew[:, None] + 0 * ehat
                else:
                    lev = np.full_like(ehat, 1e9)
                zhat = lev + ehat
                if cell.kappa > 0:
                    Minv = np.linalg.inv(As_)
                    Xs = Xc / dsd[:, None, :]
                    q = np.einsum("rnd,rde,rne->rn", Xs, Minv, Xs)
                    s2 = (yy / np.maximum(Nw, 1))[:, None]
                    zlow = zhat - cell.kappa * np.sqrt(np.maximum(q * s2, 0.0))
                else:
                    zlow = zhat
                key = zhat * sig_hat if cell.rank == "a" else zhat
                score = np.where(elig & ready[:, None] & (zlow > 0), key, -np.inf)
                if cell.level == "V0":
                    score = np.where(elig & ready[:, None], ehat, -np.inf)
            else:
                ehat = rng.random((R, Nmax))
                score = np.where(elig & ready[:, None], ehat, -np.inf)
            top = np.argsort(-score, axis=1)[:, :K]
            ok = np.take_along_axis(score, top, axis=1) > -np.inf
            pa = np.where(ok, np.take_along_axis(a, top, axis=1), np.nan)
            pr = np.where(ok, np.take_along_axis(r, top, axis=1), np.nan)
            pid = np.where(ok, np.take_along_axis(ids, top, axis=1), -1)
            npk = ok.sum(axis=1)
            has = npk > 0
            with np.errstate(invalid="ignore"):
                out_B[has, t] = np.nanmean(pa[has], axis=1)
                out_Rm[has, t] = np.nanmean(pr[has], axis=1)
            out_n[:, t] = npk
            out_ctrl[:, t] = (a * vf).sum(axis=1) / nv
            out_iss[:, t, :] = pid
            out_a[:, t, :] = pa
            rr, kk = np.nonzero(ok)
            last[rr, pid[rr, kk]] = t
            sEa = sig * Ey
            pe = np.where(ok, np.take_along_axis(sEa, top, axis=1), np.nan)
            with np.errstate(invalid="ignore"):
                curve_edge[has, t] = np.nanmean(pe[has], axis=1)
            # realised IC over the pool
            yc = (y - (y * vf).sum(axis=1, keepdims=True) / nv[:, None]) * vf
            ec = (ehat - (ehat * vf).sum(axis=1, keepdims=True) / nv[:, None]) * vf
            den = np.sqrt((yc ** 2).sum(axis=1) * (ec ** 2).sum(axis=1))
            with np.errstate(invalid="ignore", divide="ignore"):
                curve_ic[:, t] = np.where(ready & (den > 0), (yc * ec).sum(axis=1) / den, np.nan)
            if cell.null != "N1":
                ztrue = np.where(elig, Ey, -np.inf)
                otop = np.argsort(-ztrue, axis=1)[:, :K]
                oz = np.take_along_axis(ztrue, otop, axis=1)
                ook = oz > 0
                ov = np.where(ook, np.take_along_axis(sEa, otop, axis=1), np.nan)
                with np.errstate(invalid="ignore"):
                    oracle_edge[ook.any(axis=1), t] = np.nanmean(ov[ook.any(axis=1)], axis=1)
                fsel = np.where(elig & (X[..., 6] > 0), rng.random((R, Nmax)), -np.inf)
                ftop = np.argsort(-fsel, axis=1)[:, :K]
                fok = np.take_along_axis(fsel, ftop, axis=1) > -np.inf
                fv = np.where(fok, np.take_along_axis(sEa, ftop, axis=1), np.nan)
                with np.errstate(invalid="ignore"):
                    fixed_edge[fok.any(axis=1), t] = np.nanmean(fv[fok.any(axis=1)], axis=1)
        # ---- this session's sufficient statistics (settle after `lag` sessions)
        ybar = (y * vf).sum(axis=1) / nv
        Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
        yd = (y - ybar[:, None]) * vf
        As = np.matmul(Xd.transpose(0, 2, 1), Xd)
        bs = np.einsum("rnd,rn->rd", Xd, yd)
        pend.append((t, As, bs, vf.sum(axis=1), ybar, (yd ** 2).sum(axis=1)))
    return dict(B=out_B, Rm=out_Rm, n=out_n, ctrl=out_ctrl, iss=out_iss, a=out_a, curve_edge=curve_edge,
                curve_ic=curve_ic, oracle_edge=oracle_edge, fixed_edge=fixed_edge)


# ------------------------------------------------------------------------------------------------ sign flips
_PAT: dict = {}
_SG = None


def _signs():
    global _SG
    if _SG is None:
        _SG = np.where(np.random.default_rng(20261022).random((B_MC, 600)) < 0.5, -1.0, 1.0)
    return _SG


def _pat(S):
    if S not in _PAT:
        _PAT[S] = np.array(list(itertools.product((-1.0, 1.0), repeat=S)))
    return _PAT[S]


def flip_p(x, nvec=B_MC):
    """One-sided sign-flip p of mean(x) > 0, ties against the program; exact for len <= 16."""
    x = np.asarray(x, float)
    S = len(x)
    T = x.sum()
    if S <= EXACT_S:
        M = _pat(S) @ np.abs(x)
        return np.count_nonzero(M >= T - S * TIE) / float(1 << S)
    sg = _signs()
    if S > sg.shape[1]:
        sg = np.where(np.random.default_rng(S).random((B_MC, S)) < 0.5, -1.0, 1.0)
    M = sg[:nvec, :S] @ np.abs(x)
    return (1 + np.count_nonzero(M >= T - S * TIE)) / (1.0 + nvec)


def zstat(x):
    x = np.asarray(x, float)
    q = math.sqrt(float((x * x).sum()))
    return float(x.sum()) / q if q > 0 else 0.0


def issuer_p(iss, a, nvec):
    m = {}
    for i, v in zip(iss, a):
        m.setdefault(int(i), []).append(float(v))
    vals = [sum(v) / len(v) for _, v in sorted(m.items())]
    if zstat(vals) < Z_PRE:
        return 1.0
    return flip_p(vals, nvec)


# ------------------------------------------------------------------------------------------------ screens
def screen_one(sim, rep, rule, start=0, with_end=False):
    """(passed, session of pass or -1, retired) for one replicate under `rule` in {EVL3, L12, E840}, its record the
    picks from session `start` on (a re-entered version's fresh record). `with_end`: also the session its version
    ended (a retirement, or EXHAUSTION: the last look of L12's list, or the 40th block of E840), else -1."""
    B, Rm, n, ctrl = sim["B"][rep], sim["Rm"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av = sim["iss"][rep], sim["a"][rep]
    T = len(B)
    blocks: list[float] = []
    bsess: list[int] = []
    ev_iss: list[int] = []
    ev_a: list[float] = []
    ev_r_sum = 0.0
    seen: set = set()
    k3 = 0
    k12 = 0
    for t in range(start, T):
        if n[t] == 0:
            continue
        if rule == "L12" and k12 >= len(L12):
            return (False, -1, True, t - 1) if with_end else (False, -1, True)
        if rule == "E840" and len(blocks) >= 40:
            return (False, -1, True, t - 1) if with_end else (False, -1, True)
        blocks.append(float(B[t]))
        bsess.append(t)
        kk = int(n[t])
        ev_iss.extend(int(x) for x in iss[t, :kk])
        ev_a.extend(float(x) for x in av[t, :kk])
        ev_r_sum += float(Rm[t]) * kk
        seen.update(int(x) for x in iss[t, :kk])
        S = len(blocks)
        N = len(ev_a)
        if rule == "EVL3":
            if k3 >= len(V3_NS) or N < V3_NS[k3] or len(seen) < 40 or S < 8:
                continue
            while k3 < len(V3_NS) and N >= V3_NS[k3]:
                k3 += 1
            alpha, m0, ret_alpha = 0.018, 0.0, 0.05
        elif rule == "L12":
            if k12 >= len(L12) or S < L12[k12] or N < 30 or len(seen) < 30:
                continue
            while k12 < len(L12) and S >= L12[k12]:
                k12 += 1
            alpha, m0 = 0.01, 0.001
            ret_alpha = alpha
        else:   # E840
            if S < 8 or S > 40 or N < 30 or len(seen) < 30:
                continue
            alpha, m0 = 0.125 / S, 0.001
            ret_alpha = alpha
        xb = np.array(blocks)
        mean_a = sum(ev_a) / N
        # retirement first
        if mean_a < 0 and zstat(-xb) >= Z_PRE and flip_p(-xb) <= ret_alpha + TIE:
            return (False, -1, True, t) if with_end else (False, -1, True)
        x = xb - m0
        if zstat(x) < Z_PRE:
            continue
        p = flip_p(x)
        if p > alpha + TIE:
            continue
        if not (mean_a > 0 and ev_r_sum / N > 0):
            continue
        cm = float(np.mean(ctrl[bsess]))
        if not (xb.mean() > cm):
            continue
        if rule == "EVL3":
            if issuer_p(ev_iss, ev_a, B_ISS3) > 0.018 + TIE:
                continue
        else:
            if issuer_p(ev_iss, ev_a, B_ISS6) > 0.10 + TIE:
                continue
        return (True, t, False, t) if with_end else (True, t, False)
    return (False, -1, False, -1) if with_end else (False, -1, False)


def screen_chain(sim, rep, rule, versions=3):
    """PREREG-EVL-7 L10's re-entry: version 1 from session 0; after a retirement or an exhaustion at session e, the next
    version's record starts at session e + 1 (registered the first night after); at most `versions` in all. Returns
    (passed, session of pass, versions used)."""
    start = 0
    for v in range(1, versions + 1):
        ok, when, _, end = screen_one(sim, rep, rule, start, with_end=True)
        if ok:
            return True, when, v
        if end < 0 or end + 1 >= len(sim["B"][rep]):
            return False, -1, v
        start = end + 1
    return False, -1, versions


def summarise(cell: Cell, sim: dict, rules=("EVL3", "L12", "E840")) -> dict:
    R = sim["B"].shape[0]
    out = {"cell": dataclasses.asdict(cell), "R": R}
    for rule in rules:
        res = [screen_one(sim, i, rule) for i in range(R)]
        passed = np.array([x[0] for x in res])
        when = np.array([x[1] for x in res])
        ret = np.array([x[2] for x in res])
        d = {"pass": float(passed.mean()), "retired": float(ret.mean())}
        for h in (20, 40, 60, 120, 300):
            if h <= cell.T:
                d[f"by{h}"] = float((passed & (when < h)).mean())
        if passed.any():
            d["median_pass_session"] = float(np.median(when[passed]) + 1)
        out[rule] = d
    for rule in ("L12", "E840"):
        res = [screen_chain(sim, i, rule) for i in range(R)]
        passed = np.array([x[0] for x in res])
        when = np.array([x[1] for x in res])
        used = np.array([x[2] for x in res])
        d = {"pass": float(passed.mean()), "versions_mean": float(used.mean())}
        for h in (40, 60, 120, 300):
            if h <= cell.T:
                d[f"by{h}"] = float((passed & (when < h)).mean())
        out[rule + "x3"] = d
    n = sim["n"]
    out["events_per_session"] = float(n.mean())
    out["sessions_with_picks"] = float((n > 0).mean())
    with np.errstate(invalid="ignore"):
        allB = sim["a"][~np.isnan(sim["a"])]
        out["mean_a_picks_bp"] = float(allB.mean() * 1e4) if allB.size else None
        out["mean_ctrl_bp"] = float(np.nanmean(sim["ctrl"]) * 1e4)
        for key in ("curve_edge", "curve_ic", "oracle_edge", "fixed_edge"):
            arr = sim[key]
            if np.all(np.isnan(arr)):
                continue
            segs = {}
            for lo in range(0, cell.T, 10):
                seg = arr[:, lo:lo + 10]
                if np.all(np.isnan(seg)):
                    continue
                v = float(np.nanmean(seg))
                segs[f"{lo + 1}-{lo + 10}"] = round(v * (1e4 if key != "curve_ic" else 1.0), 4 if key == "curve_ic" else 2)
            out[key] = segs
    return out


# ------------------------------------------------------------------------------------------------ grids
WORST = dict(rho_day=0.15, day="crash", ev_skew=True, drift_sd=0.0020, tau=0.01)


def grid(name: str) -> list[Cell]:
    cells: list[Cell] = []
    if name in ("null", "null800"):
        for nb in ((300,) if name == "null" else (800,)):
            cells.append(Cell(f"N1-base-n{nb}", nbar=nb))
            cells.append(Cell(f"N1-worst-n{nb}", nbar=nb, **WORST))
            cells.append(Cell(f"N2-ic03-worst-n{nb}", null="N2", ic=0.03, nbar=nb, **WORST))
            cells.append(Cell(f"N2-ic05-worst-n{nb}", null="N2", ic=0.05, nbar=nb, **WORST))
        if name == "null":
            cells.append(Cell("N1-worst-n300-rand", nbar=300, learn=False, **WORST))
            cells.append(Cell("N1-base-n300-rand", nbar=300, learn=False))
    elif name == "levels":
        for lv in ("V0", "V2", "V3"):
            cells.append(Cell(f"N1-worst-n300-{lv}", nbar=300, level=lv, **WORST))
            cells.append(Cell(f"N2-ic05-worst-n300-{lv}", null="N2", ic=0.05, nbar=300, level=lv, **WORST))
    elif name == "stress":
        cells.append(Cell("N1-worst-notau-n300", nbar=300, **(WORST | dict(tau=0.0))))
        cells.append(Cell("N1-worst-notau-n300-rand", nbar=300, learn=False, **(WORST | dict(tau=0.0))))
        cells.append(Cell("N2-ic05-worst-notau-n300", null="N2", ic=0.05, nbar=300, **(WORST | dict(tau=0.0))))
        cells.append(Cell("N1-rho30-n300", nbar=300, **(WORST | dict(rho_day=0.30))))
        cells.append(Cell("N1-drift30-n300", nbar=300, **(WORST | dict(drift_sd=0.0030))))
        cells.append(Cell("N1-drift20ar99-n300", nbar=300, **(WORST | dict(drift_rho=0.99))))
        cells.append(Cell("N1-mom40-n300", nbar=300, **(WORST | dict(rho_day=0.30, phi_day=0.40))))
        cells.append(Cell("N1-tau3-n300", nbar=300, **(WORST | dict(tau=0.03))))
        cells.append(Cell("N3-famdrift20-n300", nbar=300, fam_drift_sd=0.0020, **WORST))
        cells.append(Cell("N4-loadcorr-fac25-n300", nbar=300, load_corr=0.7, fac_rho=0.25, **WORST))
        cells.append(Cell("N1-worst-n300-H10-lam200", nbar=300, H=10.0, lam=200.0, **WORST))
        cells.append(Cell("N2-ic05-worst-n300-H10-lam200", null="N2", ic=0.05, nbar=300, H=10.0, lam=200.0, **WORST))
        cells.append(Cell("N1-worst-n300-K24", nbar=300, K=24, **WORST))
    elif name == "power":
        for ic in (0.02, 0.03, 0.05):
            for nb in (300, 800):
                cells.append(Cell(f"A-ic{int(ic*100):02d}-base-n{nb}", null="A", ic=ic, mu_z=-0.04, nbar=nb, T=60))
        cells.append(Cell("A-ic03-worst-n800", null="A", ic=0.03, mu_z=-0.04, nbar=800, T=60, **WORST))
        cells.append(Cell("A-ic05-worst-n800", null="A", ic=0.05, mu_z=-0.04, nbar=800, T=60, **WORST))
        cells.append(Cell("A-ic03-base-n800-K24", null="A", ic=0.03, mu_z=-0.04, nbar=800, T=60, K=24))
        cells.append(Cell("A-ic03-base-n800-V2", null="A", ic=0.03, mu_z=-0.04, nbar=800, T=60, level="V2"))
        cells.append(Cell("A-ic03-base-n800-warm15k", null="A", ic=0.03, mu_z=-0.04, nbar=800, T=60, warm_rows=15000))
        cells.append(Cell("A-ic03-base-n800-lam8k", null="A", ic=0.03, mu_z=-0.04, nbar=800, T=60, lam=8000.0))
        cells.append(Cell("A-ic03-base-n800-rand", null="A", ic=0.03, mu_z=-0.04, nbar=800, T=60, learn=False))
    elif name == "drift":
        cells.append(Cell("A2-ic05-base-n800-H40", null="A2", ic=0.05, mu_z=-0.04, nbar=800, T=120))
        cells.append(Cell("A2-ic05-base-n800-Hinf", null="A2", ic=0.05, mu_z=-0.04, nbar=800, T=120, H=float("inf")))
        cells.append(Cell("A2-ic05-base-n800-H15", null="A2", ic=0.05, mu_z=-0.04, nbar=800, T=120, H=15.0))
    elif name == "rank":
        for nm, kw in (("ranka", dict(rank="a")), ("ranka-lam8k", dict(rank="a", lam=8000.0)),
                       ("ranka-lam8k-k1", dict(rank="a", lam=8000.0, kappa=1.0))):
            cells.append(Cell(f"A-ic05-base-n800-{nm}", null="A", ic=0.05, mu_z=-0.04, nbar=800, T=60, **kw))
            cells.append(Cell(f"A-ic03-base-n800-{nm}", null="A", ic=0.03, mu_z=-0.04, nbar=800, T=60, **kw))
    elif name == "ranknull":
        kw = dict(rank="a", lam=8000.0, kappa=1.0)
        cells.append(Cell("N1-base-n300-final", nbar=300, **kw))
        cells.append(Cell("N1-worst-n300-final", nbar=300, **(WORST | kw)))
        cells.append(Cell("N1-worst-notau-n300-final", nbar=300, **(WORST | dict(tau=0.0) | kw)))
        cells.append(Cell("N2-ic05-worst-n300-final", null="N2", ic=0.05, nbar=300, **(WORST | kw)))
        cells.append(Cell("N2-ic03-worst-n300-final", null="N2", ic=0.03, nbar=300, **(WORST | kw)))
        cells.append(Cell("N1-worst-n800-final", nbar=800, **(WORST | kw)))
    elif name.startswith("final_"):
        F = json.loads(os.environ.get("LEARNER_FINAL", "{}"))
        if name == "final_null":
            cells.append(Cell("F-N1-base-n300", nbar=300, **F))
            cells.append(Cell("F-N1-worst-n300", nbar=300, **(WORST | F)))
            cells.append(Cell("F-N1-worst-notau-n300", nbar=300, **(WORST | dict(tau=0.0) | F)))
            cells.append(Cell("F-N2-ic03-worst-n300", null="N2", ic=0.03, nbar=300, **(WORST | F)))
            cells.append(Cell("F-N2-ic05-worst-n300", null="N2", ic=0.05, nbar=300, **(WORST | F)))
            cells.append(Cell("F-N2-ic05-worst-notau-n300", null="N2", ic=0.05, nbar=300, **(WORST | dict(tau=0.0) | F)))
        elif name == "final_null800":
            cells.append(Cell("F-N1-worst-n800", nbar=800, **(WORST | F)))
            cells.append(Cell("F-N1-worst-notau-n800", nbar=800, **(WORST | dict(tau=0.0) | F)))
        elif name == "final_stress":
            cells.append(Cell("F-N1-rho30-notau-n300", nbar=300, **(WORST | dict(rho_day=0.30, tau=0.0) | F)))
            cells.append(Cell("F-N1-drift30-notau-n300", nbar=300, **(WORST | dict(drift_sd=0.0030, tau=0.0) | F)))
            cells.append(Cell("F-N1-mom40-notau-n300", nbar=300, **(WORST | dict(rho_day=0.30, phi_day=0.40, tau=0.0) | F)))
            cells.append(Cell("F-N3-famdrift20-notau-n300", nbar=300, fam_drift_sd=0.0020, **(WORST | dict(tau=0.0) | F)))
            cells.append(Cell("F-N4-loadcorr-fac25-notau-n300", nbar=300, load_corr=0.7, fac_rho=0.25, **(WORST | dict(tau=0.0) | F)))
        elif name == "final_power":
            for ic in (0.03, 0.05, 0.08, 0.12):
                cells.append(Cell(f"F-A-ic{int(ic*100):02d}-base-n800", null="A", ic=ic, mu_z=-0.04, nbar=800, T=120, **F))
            cells.append(Cell("F-A-ic05-worst-notau-n800", null="A", ic=0.05, mu_z=-0.04, nbar=800, T=120, **(WORST | dict(tau=0.0) | F)))
            cells.append(Cell("F-A-ic05-base-n300", null="A", ic=0.05, mu_z=-0.04, nbar=300, T=120, **F))
            cells.append(Cell("F-A2-ic05-base-n800", null="A2", ic=0.05, mu_z=-0.04, nbar=800, T=120, **F))
            cells.append(Cell("F-A2-ic05-base-n800-Hinf", null="A2", ic=0.05, mu_z=-0.04, nbar=800, T=120, **(F | dict(H=float("inf")))))
        elif name == "final_life":
            cells.append(Cell("F-N1-worst-notau-n300-T300", nbar=300, T=300, **(WORST | dict(tau=0.0) | F)))
            cells.append(Cell("F-N2-ic05-worst-notau-n300-T300", null="N2", ic=0.05, nbar=300, T=300, **(WORST | dict(tau=0.0) | F)))
    elif name == "life":
        cells.append(Cell("N1-worst-n300-T300", nbar=300, T=300, **WORST))
        cells.append(Cell("N2-ic05-worst-n300-T300", null="N2", ic=0.05, nbar=300, T=300, **WORST))
    elif name == "smoke":
        cells.append(Cell("smoke-N1", nbar=200, T=40))
        cells.append(Cell("smoke-A", null="A", ic=0.05, mu_z=-0.04, nbar=200, T=40))
    return cells


def _job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = simulate(cell, seed, R)
    return cell, sim, time.time() - t0


def merge(parts):
    keys = parts[0].keys()
    return {k: np.concatenate([p[k] for p in parts], axis=0) for k in keys}


def run(gridname: str, reps: int, chunk: int, workers: int, out: str, seed0: int):
    from multiprocessing import Pool
    cells = grid(gridname)
    jobs = []
    for ci, cell in enumerate(cells):
        nchunks = max(1, reps // chunk)
        for j in range(nchunks):
            jobs.append((cell, seed0 + 1000 * ci + j, chunk))
    t0 = time.time()
    parts: dict = {}
    with Pool(workers) as pool:
        for k, (cell, sim, dt_) in enumerate(pool.imap_unordered(_job, jobs)):
            parts.setdefault(cell.name, []).append(sim)
            if (k + 1) % 5 == 0 or k + 1 == len(jobs):
                print(f"{gridname}: {k + 1}/{len(jobs)} jobs, {time.time() - t0:.0f}s (last {dt_:.0f}s)", flush=True)
    with open(out + ".jsonl", "w") as fh:
        for cell in cells:
            sim = merge(parts[cell.name])
            s = summarise(cell, sim)
            fh.write(json.dumps(s) + "\n")
            print(json.dumps({"cell": cell.name, **{r: s[r] for r in ("EVL3", "L12", "E840")},
                              "ev": round(s["events_per_session"], 2), "mean_a_bp": s["mean_a_picks_bp"]}), flush=True)


def selftest():
    # the exact sign-flip: a vector of 8 positives has p = 1/256
    assert abs(flip_p(np.ones(8)) - 1 / 256) < 1e-12
    # symmetric null p is roughly uniform
    rng = np.random.default_rng(1)
    ps = [flip_p(rng.normal(0, 1, 30), 1999) for _ in range(400)]
    print("selftest: P(p <= 0.05) under N(0,1) =", np.mean(np.array(ps) <= 0.05))
    c = Cell("st", nbar=100, T=12)
    sim = simulate(c, 3, 4)
    print("selftest: shapes", {k: v.shape for k, v in sim.items()})
    print("selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "selftest"))
    ap.add_argument("--grid", default="smoke")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=71_000_001)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
        sys.exit(0)
    run(a.grid, a.reps, a.chunk, min(a.workers, 4), a.out or os.path.join(HERE, f"calib_learner.{a.grid}"), a.seed)

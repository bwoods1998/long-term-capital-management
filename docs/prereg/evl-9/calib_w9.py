#!/usr/bin/env python
"""calib_w9.py: PREREG-EVL-9's FINAL calibration (the captain's W1, W6 and W12). SYNTHETIC ONLY.

Nothing here reads the lane: no House, gateway, events.sqlite, live.sqlite, vault, run record, price, return, look or
band. Every number is drawn from the learner lens's generator (evl7/learner/calib_learner.py, imported unchanged, sha256
fdb2c74fe9543c3f5e18142c7d8c97388253657bc5dbd73caff749adee2237d9) with PREREG-EVL-6's frozen plausible grid's day shapes
and day-following counts (copied from evl7/final/calib_w7.py, sha256 7d4500d5..., which copies PREREG-EVL-6's
calib_v2.py laws), the warm prior of evl9/learners/calib_evl9.py (re-derived below on this file's columns), and judged by
PREREG-EVL-6's screen AS FROZEN (docs/prereg/PREREG-EVL-6.md, sha256
0f67f94ecac93f6b5542654e33ce5180fdbac254238badd571a37bcb0950f057, sections 1-3) on the REPLAY basis (PREREG-EVL-1
section 5's a and r, as PREREG-EVL-9 section 9 reads them).

WHAT IS NEW AGAINST EVERY EARLIER EVL-9 CALIBRATION:
  W1  NO ISSUER-OWN RETURN COLUMNS: the lens's columns 35-37 (r1, r5, r20) are DROPPED from the learner's x (they stay
      in the generator's truth index, so the alternatives' power pays for the reversal signal the learner no longer
      sees). EVL-WL-ON's gap is dropped. EVL-WL-ON keeps dmove and |dmove| (PREREG-EVL-7 keeps dmove for its cold
      learner), and here dmove is BUILT FROM THE ISSUER'S OWN SIMULATED RETURNS: dmove(D) = clip(o(P) + m(D), +-0.5),
      o(P) the issuer's close-to-open abnormal return of P (its ON event return, tau and every shock included, when it
      was in the pool at P; else its overnight noise) and m(D) its open-to-15:30 return (noise of sd 1.47 x sigma; with
      tau_mode 'all' tau too). So the 1% persistent issuer effect reaches the learner through dmove exactly as it would.
  W6  THE TREE SCORE g is one column: g = 0.5 z(x . w_h) + sqrt(0.75) eta, w_h the history index's direction and eta
      per-candidate noise (the interactions a tree adds, which carry nothing forward under every null). Its prior row is
      scaled for FORWARD-CHAINED out-of-fold scores: the 2022 rows carry g = 0 (a fifth of the history rows), so A_0's g
      entries are 0.8 (variance) / sqrt(0.8) (covariances) of the contiguous-fold build's; in an HD cell its history
      slope is half the history edge (the tree found half of it out of fold), 0 otherwise.
  W12 THE SHAPE GUARD IN HOLD UNITS (check 1's major 2): a candidate is eligible to be picked only when sigH20 >= 0.015,
      sigH20 the sample sd (divisor n - 1) of its last 20 (EVL-WL-O1: open-to-close) or 19 (EVL-WL-ON: close-to-open)
      hold-period abnormal returns with the one of largest absolute size removed, read from the same simulated daily
      series (its event return on its pool sessions, else h_t (sector + beta . f + sigma e) + jumps).
  W12 BOTH LAGS: EVL-WL-O1 trains at lag 1 (its outcomes settle the same night), EVL-WL-ON at lag 2.
  The registered INNER PROCEDURE of section 5.2 is applied to the prior: four era folds of N_HIST / 4 rows each, beta'
      = their mean with every column whose fold sign differs from it in 2 or more folds set to 0, b_0 = A_0 beta'.
  THE GROSS LABEL (section 3.6): y = clip(a_g / sig20, -5, 5); the replay cost c_rep enters once, at the hurdle.

THE NULLS, in the screen's own units (a = a_g - c_rep, the replay):
  N1  E[a] = 0 for EVERY candidate (E[a_g] = c_rep): the binding null. History: H0 (history carried the same null), HD
      (a DECAYED EDGE: history carried ic_h 0.05 / 0.08 along u_h, live carries none), CHAR (HD plus a zero-mean AR 0.97
      drift kappa_t (u_h - pool mean) of sd 10 / 20 bp a unit, pool-demeaned: a drift along the learner's own history
      direction that the control never sees), TAUH (the ON learner's history carried the population slope of y on its
      own-return columns implied by tau), ADV (adversarial priors: leak / rand / lowvol, check 1's check1_adv.py).
  N2  the knife edge, history of the same structure.
ALTERNATIVE A: E[a_g] = sigma ic u (the pool's gross mean about 0, so after cost it loses c_rep); history ic_h = ic at
  correlation rho with live; COLD the same learner without history (PREREG-EVL-7's, with the 2,000-row warm-up).

THE FROZEN SCREEN (PREREG-EVL-6 sections 1-3; the code is calib_w7.py's `screen`, copied): blocks = sessions with a pick;
y_s = min(n_s, 14) (B_s - 10 bp); looks at S = 22, 25, 30, 35, 40, 50, 60 once >= 30 events, >= 30 issuers and >= 6
blocks; alpha 0.020 (S 22-30), 0.006 (31-40), 0.001 (41-60); RETIRE first, then PASS with every guard (mean a > 0, mean r
> 0, the top-14 pooled means, the POOL control, issuer-block p_I <= 0.10); a run ENDS at its 60th block and the next run
starts with the next block. Monte Carlo shortcuts as PREREG-EVL-6 section 4.2.

Usage: calib_w9.py run --grid NAME [--reps R] [--chunk C] [--workers W] [--seed S] [--tag T]  |  report [--only X]
       calib_w9.py selftest
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GOAL = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(GOAL, "evl7", "learner"))
import calib_learner as cl  # noqa: E402

U = cl.U
D0 = cl.D                                   # the lens's 40 generator columns
KEEP = [j for j in range(D0) if j not in (35, 36, 37)]      # W1: r1, r5, r20 dropped from the learner's x
N_HIST = 500_000.0
DE = 2.0
N_EQ = 25_000.0
LAM = 8000.0
H_LIFE = 40.0
K_PICKS = 8
GUARD = 0.015
INTRA = 1.47                                # sd of the open-to-15:30 move over the overnight hold sigma
EXTRA_P = np.array([.02, .03, .04, .05, .06, .08, .10, .12, .15, .02, .03, .05, .08, .10, .20, .30])

# ------------------------------------------------------------------------------ the frozen screen's constants
LOOKS = (22, 25, 30, 35, 40, 50, 60)
PIECES = ((30, 0.020), (40, 0.006), (60, 0.001))
M0 = 0.0010
CAP = 14
HORIZON = 60
MIN_N, MIN_ISS, MIN_BLK = 30, 30, 6
ISS_ALPHA = 0.10
TIE = 1e-12

# ------------------------------------------------------------------------------ costs (E = $1,898; score.py)
E_EQ = 1898.0


def c_replay(lnadv):
    """score.py cost_bp at E = $1,898, entry plus exit, as a return (calib_w7.costs' c_rep)."""
    adv = 1e7 * np.exp(lnadv)
    n = 0.05 * E_EQ
    return (2 * (0.5 + np.where(adv >= 1e7, 5.0, 10.0)) + (0.01 / n + 0.02 / n) * 1e4) / 1e4


# ------------------------------------------------------------------------------ day shapes (calib_w7.py's, copied)
CR_P, CR_K, CL_G, CL_MAX, VSD = 0.05, 3.0, 2.0, 0.09, 0.3


def day_eps(kind, R, vx, pre):
    u, crash, body = pre
    p = np.minimum(CR_P * np.exp(CL_G * vx) / math.exp(CL_G ** 2 * VSD ** 2 / 2.0), CL_MAX) if kind.endswith("cl") \
        else np.full(R, CR_P)
    m = p * CR_K / (1.0 - p)
    s = np.sqrt((1.0 - p * (CR_K ** 2 + 1.0)) / (1.0 - p) - m * m)
    return np.where(u < p, crash, m + s * body)


_CNORM: dict = {}


def count_norm(kind, kappa):
    key = (kind, kappa)
    if key not in _CNORM:
        rr = np.random.default_rng(424242)
        M = 2_000_000
        if kind in ("", "t3", "crash"):
            e_ = cl.day_innov(rr, kind or "t3", M)
        else:
            vx = VSD * rr.standard_normal(M)
            u = rr.random(M)
            cr = rr.normal(-CR_K, 1.0, M)
            body = cl.unit_t3(rr, M) if "t3" in kind else rr.standard_normal(M)
            e_ = day_eps(kind, M, vx, (u, cr, body))
        _CNORM[key] = float(np.exp(kappa * np.minimum(np.abs(e_), 4.0)).mean())
    return _CNORM[key]


# ------------------------------------------------------------------------------ cells
@dataclasses.dataclass(frozen=True)
class W9:
    name: str
    learner: str = "ON"          # O1 (lag 1, no dmove) | ON (lag 2, own-return dmove)
    hist: str = "warm"           # warm | cold
    null: str = "N1"             # N1 | N2 | A
    ic: float = 0.0
    ic_h: float = 0.0
    rho_h: float = 1.0
    drift_c: float = 0.0         # CHAR
    tauh: bool = False           # TAUH: history carried the own-return slope implied by tau
    adv: str = ""                # '' | leak | rand | lowvol
    adv_k: float = 0.30
    nbar: float = 300.0
    T: int = 120
    pre: int = 3
    rho_day: float = 0.15
    shape: str = "crash"         # t3 | crash | crasht3 | crashcl | crasht3cl
    ev_skew: bool = True
    drift_sd: float = 0.0020
    drift_rho: float = 0.97
    tau: float = 0.01
    tau_mode: str = "event"      # event | all
    phi_day: float = 0.20
    cnt: float = 0.0
    lag: int = 0                 # 0: the learner's own (O1 1, ON 2)
    guard: bool = True
    n_eq: float = N_EQ
    sec_drift: float = 0.0
    fam_drift: float = 0.0

    def L(self) -> int:
        return self.lag or (1 if self.learner == "O1" else 2)

    def sd_day(self) -> float:
        return math.sqrt(self.rho_day / (1.0 - self.rho_day) * cl.V0) if self.rho_day > 0 else 0.0


def ncols(learner: str) -> int:
    return len(KEEP) + 17 + 1 + (2 if learner == "ON" else 0)      # + 16 kw + dup72 + g (+ dmove, |dmove|)


def _lens_cell(c: W9) -> cl.Cell:
    return cl.Cell(c.name, tau=c.tau, nbar=c.nbar)


# ------------------------------------------------------------------------------ the generator
class Gen:
    """One replicate block of R programs: the issuers, the daily series and the pools of the lens's generator with the
    frozen grid's day laws, and the learner's columns of this file."""

    def __init__(self, c: W9, rng, R):
        self.c, self.rng, self.R = c, rng, R
        self.iss = cl.issuers(rng, R, _lens_cell(c))
        self.iss["c_rep"] = c_replay(self.iss["ilev"][..., 0])
        self.Nmax = int(c.nbar * (4.5 if c.cnt else 3.2)) + 20
        self.zday = np.zeros(R)
        self.vx = rng.normal(0, 0.3, R)
        self.drift = rng.normal(0, c.drift_sd, R) if c.drift_sd else np.zeros(R)
        self.sdrift = rng.normal(0, c.sec_drift, (R, 11)) if c.sec_drift else np.zeros((R, 11))
        self.fdrift = rng.normal(0, c.fam_drift, (R, 6)) if c.fam_drift else np.zeros((R, 6))
        self.kap = rng.normal(0, c.drift_c, R) if c.drift_c else np.zeros(R)
        self.newday = c.shape in ("crasht3", "crashcl", "crasht3cl")
        self.kind = c.shape if self.newday else ("crash" if c.shape == "crash" else "t3")
        self.Em = count_norm(self.kind, c.cnt) if c.cnt else 1.0
        # the daily hold-period abnormal series of every issuer (20 sessions), started with non-pool noise
        self.ring = np.zeros((20, R, U))
        for k in range(20):
            h = np.exp(rng.normal(0, 0.3, R) - 0.09)
            s_sec = cl.unit_t3(rng, (R, 11)) * 0.010
            fac = cl.unit_t3(rng, (R, 3)) * 0.006
            self.ring[k] = self._nonpool(h, s_sec, fac)
        self.k = 0

    def _nonpool(self, h, s_sec, fac):
        rng, R, iss = self.rng, self.R, self.iss
        e = cl.unit_t3(rng, (R, U))
        jump = np.where(rng.random((R, U)) < 0.005, np.where(rng.random((R, U)) < 0.5, -0.30, 0.30), 0.0)
        out = h[:, None] * (np.take_along_axis(s_sec, iss["sector"], axis=1)
                            + np.einsum("ruk,rk->ru", iss["beta"], fac) + iss["sig"] * e) + jump
        if self.c.tau_mode == "all":
            out = out + iss["tau"]
        return out

    def session(self, wh_dir, P):
        """Draw one session: returns a dict of the pool's arrays (R, Nmax[, ...])."""
        c, rng, R, iss, Nmax = self.c, self.rng, self.R, self.iss, self.Nmax     # Nmax: the count's cap
        eps = None
        if c.cnt:
            if self.newday:
                pre = (rng.random(R), rng.normal(-CR_K, 1.0, R), cl.unit_t3(rng, R) if "t3" in self.kind
                       else rng.standard_normal(R))
                self.vx = 0.9 * self.vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
                eps = day_eps(self.kind, R, self.vx, pre)
            else:
                eps = cl.day_innov(rng, self.kind, R)
                self.vx = 0.9 * self.vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
            mult = np.exp(c.cnt * np.minimum(np.abs(eps), 4.0)) / self.Em
            n_t = np.minimum(rng.poisson(c.nbar * mult * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        else:
            n_t = np.minimum(rng.poisson(c.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        # only the first max(n_t) of the Zipf draw can be valid: the arrays stop there (speed; the law is unchanged)
        Nmax = max(int(n_t.max()), 1)
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
        ids = np.take_along_axis(ids, order, axis=1)
        valid = np.arange(Nmax)[None, :] < n_t[:, None]
        X40, fam = cl.pool_features(rng, R, Nmax, iss, ids)
        if eps is None:
            if self.newday:
                pre = (rng.random(R), rng.normal(-CR_K, 1.0, R), cl.unit_t3(rng, R) if "t3" in self.kind
                       else rng.standard_normal(R))
                self.vx = 0.9 * self.vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
                eps = day_eps(self.kind, R, self.vx, pre)
            else:
                eps = cl.day_innov(rng, self.kind, R)
                self.vx = 0.9 * self.vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
        self.zday = c.phi_day * self.zday + math.sqrt(1 - c.phi_day ** 2) * eps
        c_t = c.sd_day() * self.zday
        h_t = np.exp(self.vx - 0.09)
        s_sec = cl.unit_t3(rng, (R, 11)) * 0.010
        fac = cl.unit_t3(rng, (R, 3)) * 0.006
        if c.drift_sd:
            self.drift = c.drift_rho * self.drift + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.drift_sd, R)
        if c.sec_drift:
            self.sdrift = c.drift_rho * self.sdrift + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.sec_drift, (R, 11))
        if c.fam_drift:
            self.fdrift = c.drift_rho * self.fdrift + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.fam_drift, (R, 6))
        if c.drift_c:
            self.kap = c.drift_rho * self.kap + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.drift_c, R)
        b_t = rng.normal(0.0004, 0.010, R)
        sig = np.take_along_axis(iss["sig"], ids, axis=1)
        sig_hat = np.take_along_axis(iss["sig_hat"], ids, axis=1)
        c_rep = np.take_along_axis(iss["c_rep"], ids, axis=1)
        sec = np.take_along_axis(iss["sector"], ids, axis=1)
        beta = np.take_along_axis(iss["beta"], ids[..., None], axis=1)
        tau = np.take_along_axis(iss["tau"], ids, axis=1)
        e = cl.unit_t3(rng, (R, Nmax), 1.4, 0.6) if c.ev_skew else cl.unit_t3(rng, (R, Nmax))
        jl = 0.8 if c.ev_skew else 0.5
        jump = np.where(rng.random((R, Nmax)) < 0.005, np.where(rng.random((R, Nmax)) < jl, -0.30, 0.30), 0.0)
        jump = jump - 0.005 * 0.30 * (1 - 2 * jl)
        noise = h_t[:, None] * (c_t[:, None] + np.take_along_axis(s_sec, sec, axis=1)
                                + np.einsum("rnk,rk->rn", beta, fac) + sig * e)
        vf = valid.astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        # the truth
        if c.null in ("A", "N2"):
            u = (X40 @ P["w40"] - P["m40"]) / P["sd40"]
            Ey = c.ic * np.minimum(u - P["u95"], 0.0) if c.null == "N2" else c.ic * u
        else:
            Ey = np.zeros((R, Nmax))
        chard = 0.0
        uh = X40 @ wh_dir
        uh_c = uh - (uh * vf).sum(axis=1, keepdims=True) / nv[:, None]
        if c.drift_c:
            chard = self.kap[:, None] * uh_c
        struct = (self.drift[:, None] + np.take_along_axis(self.sdrift, sec, axis=1)
                  + np.take_along_axis(self.fdrift, fam, axis=1) + chard + tau)
        if c.null == "A":
            cm_g = sig * Ey + struct
            cm = cm_g - c_rep
        else:
            cm = sig * Ey + struct
            cm_g = cm + c_rep
        a_g = np.maximum(cm_g + noise + jump, -1.0)
        a = a_g - c_rep
        # the learner's columns
        L = c.learner
        Dt = ncols(L)
        X = np.zeros((R, Nmax, Dt))
        X[..., :len(KEEP)] = X40[..., KEEP]
        j = len(KEEP)
        X[..., j:j + 16] = rng.random((R, Nmax, 16)) < EXTRA_P
        X[..., j + 16] = rng.beta(0.6, 2.0, (R, Nmax))
        j += 17
        zg = uh / P["sduh"]
        X[..., j] = 0.5 * (zg - P["muh"] / P["sduh"]) + math.sqrt(0.75) * rng.standard_normal((R, Nmax))
        j += 1
        if L == "ON":
            o_prev = self.ring[(self.k - 1) % 20][np.arange(R)[:, None], ids]
            m_now = h_t[:, None] * sig * INTRA * cl.unit_t3(rng, (R, Nmax))
            if c.tau_mode == "all":
                m_now = m_now + tau
            dmv = np.clip(o_prev + m_now, -0.5, 0.5)
            X[..., j] = dmv
            X[..., j + 1] = np.abs(dmv)
        # the shape guard's sigH20 from the series BEFORE this session
        nH = 19 if L == "ON" else 20
        rix = np.arange(R)[:, None]
        hist = self.ring[[(self.k - 1 - q) % 20 for q in range(nH)]][:, rix, ids]
        ab = np.abs(hist)
        drop = np.argmax(ab, axis=0)
        mask = np.ones_like(hist, dtype=bool)
        np.put_along_axis(mask, drop[None], False, axis=0)
        kept = np.where(mask, hist, np.nan)
        sigH = np.nanstd(kept, axis=0, ddof=1)
        # this session's series: event return where in the pool, else noise
        dly = self._nonpool(h_t, s_sec, fac)
        rr_, nn_ = np.nonzero(valid)
        dly[rr_, ids[rr_, nn_]] = a_g[rr_, nn_]
        self.ring[self.k % 20] = dly
        self.k += 1
        y = np.clip(a_g / sig_hat, -5, 5)
        with np.errstate(invalid="ignore", divide="ignore"):
            uhsd = np.sqrt((uh_c ** 2 * vf).sum(axis=1) / nv)
            uhz = uh_c / np.where(uhsd > 0, uhsd, 1.0)[:, None]
        return dict(ids=ids, valid=valid, vf=vf, nv=nv, X=X, y=y, a=a, cm=cm, b=b_t, sig=sig, sig_hat=sig_hat,
                    c_rep=c_rep, tau=tau, sigH=sigH, Ey=Ey, uhz=uhz)


# ------------------------------------------------------------------------------ population facts and the prior
_POP: dict = {}


def population(learner: str, tau: float, tau_mode: str):
    """Within-session covariance S of the learner's columns; the cost structure's slope; the history index's slopes in
    the learner's columns; the own-return columns' slope implied by tau; the label's residual variance."""
    key = (learner, round(tau, 6), tau_mode)
    if key in _POP:
        return _POP[key]
    w40 = cl.W_TRUE.copy()
    m40, sd40, u95 = cl.u_norm(w40)
    wp = np.zeros(D0)
    for jj, v in ((7, 0.4), (8, -0.3), (15, 0.3), (20, 0.3), (29, -0.3), (34, 0.3), (38, 0.3), (31, 0.2)):
        wp[jj] = v
    P0 = dict(w40=w40, m40=m40, sd40=sd40, u95=u95, muh=0.0, sduh=1.0)
    c = W9("pop", learner=learner, hist="cold", tau=tau, tau_mode=tau_mode, nbar=300.0, T=40, shape="t3",
           ev_skew=False, drift_sd=0.0, rho_day=0.05, phi_day=0.10)
    rng = np.random.default_rng(int(os.environ.get("W9_POPSEED", "77000009")))
    R = 32
    gen = Gen(c, rng, R)
    Dt = ncols(learner)
    Sxx = np.zeros((Dt, Dt))
    sxc = np.zeros(Dt)
    sxy = np.zeros(Dt)
    sxu = np.zeros(Dt)
    sxp = np.zeros(Dt)
    syy = 0.0
    n = 0.0
    for t in range(-3, 60):
        s = gen.session(w40 / sd40, P0)
        X, vf, nv = s["X"], s["vf"], s["nv"]
        Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
        cy = s["c_rep"] / s["sig_hat"]
        cd = (cy - ((cy * vf).sum(axis=1) / nv)[:, None]) * vf
        yd = (s["y"] - ((s["y"] * vf).sum(axis=1) / nv)[:, None]) * vf
        # the live and the orthogonal history indices in the learner's columns: regress on the kept lens columns
        Xk = X[..., :len(KEEP)]
        ul = Xk @ (w40[KEEP] / sd40)
        up = Xk @ wp[KEEP]
        uld = (ul - ((ul * vf).sum(axis=1) / nv)[:, None]) * vf
        upd = (up - ((up * vf).sum(axis=1) / nv)[:, None]) * vf
        Sxx += np.einsum("rnd,rne->de", Xd, Xd)
        sxc += np.einsum("rnd,rn->d", Xd, cd)
        sxy += np.einsum("rnd,rn->d", Xd, yd)
        sxu += np.einsum("rnd,rn->d", Xd, uld)
        sxp += np.einsum("rnd,rn->d", Xd, upd)
        syy += float((yd ** 2).sum())
        n += float(vf.sum())
    S = Sxx / n
    Si = np.linalg.inv(S + 1e-10 * np.eye(Dt))
    b_cost = Si @ (sxc / n)
    b_live = Si @ (sxu / n)
    b_perp_raw = Si @ (sxp / n)
    # make the orthogonal index population-orthogonal to the live one (under S) and of unit variance
    proj = (b_perp_raw @ S @ b_live) / (b_live @ S @ b_live)
    b_perp = b_perp_raw - proj * b_live
    b_live = b_live / math.sqrt(b_live @ S @ b_live)
    b_perp = b_perp / math.sqrt(b_perp @ S @ b_perp)
    own = np.zeros(Dt)
    if learner == "ON":
        idx = [Dt - 2, Dt - 1]
        full = Si @ (sxy / n)                   # the history OLS slope of the gross label on every column
        own[idx] = full[idx] - b_cost[idx]      # its own-return entries beyond the cost structure
    s2 = syy / n
    out = dict(S=S, b_cost=b_cost, b_live=b_live, b_perp=b_perp, own=own, s2=s2, w40=w40, m40=m40, sd40=sd40,
               u95=u95, wp40=wp)
    # the history index in generator columns (for CHAR and g) and its normalisation
    wh = w40 / sd40
    rr = np.random.default_rng(5)
    iss = cl.issuers(rr, 4, cl.Cell("n"))
    X40, _ = cl.pool_features(rr, 4, 5000, iss, rr.integers(0, U, (4, 5000)))
    uh = (X40 @ wh).ravel()
    out["muh"], out["sduh"] = float(uh.mean()), float(uh.std())
    _POP[key] = out
    return out


def hist_dirs(c: W9, P):
    """(history index direction in generator columns for CHAR / g; the history true slope in learner columns)."""
    if c.ic_h > 0:
        w_gen = c.rho_h * P["w40"] / P["sd40"] + math.sqrt(max(0.0, 1 - c.rho_h ** 2)) * P["wp40"]
        bh = P["b_cost"] + c.ic_h * (c.rho_h * P["b_live"] + math.sqrt(max(0.0, 1 - c.rho_h ** 2)) * P["b_perp"])
    else:
        w_gen = P["w40"] / P["sd40"]
        bh = P["b_cost"].copy()
    if c.tauh:
        bh = bh + P["own"]
    return w_gen, bh


def prior(c: W9, P, rng, R):
    """(A_0, b_0, N_0) per replicate: the registered inner procedure (four era folds, sign-stability zeroing)."""
    Dt = ncols(c.learner)
    S = P["S"].copy()
    gi = len(KEEP) + 17                     # the g column
    sc = np.ones(Dt)
    sc[gi] = math.sqrt(0.8)                 # W6: the 2022 rows carry g = 0
    S = S * np.outer(sc, sc)
    A0 = c.n_eq * S
    _, bh = hist_dirs(c, P)
    bh = bh.copy()
    if c.ic_h > 0:
        bh[gi] += 0.5 * c.ic_h              # the tree found half the history edge out of fold
    if c.adv:
        sd = np.sqrt(np.diag(P["S"]))
        b = np.zeros((R, Dt))
        if c.adv == "leak":
            b[:, len(KEEP) - 1] = c.adv_k / sd[len(KEEP) - 1]      # all weight on one event column (the lens's col 39)
        elif c.adv == "lowvol":
            b[:, KEEP.index(30)] = -c.adv_k / sd[KEEP.index(30)]   # against ln(sig20)
        elif c.adv == "rand":
            z = rng.normal(0, 1, (R, Dt))
            z /= np.linalg.norm(z, axis=1, keepdims=True)
            b = c.adv_k * z / sd[None, :]
        bp = b + P["b_cost"][None, :]
    else:
        Lc = np.linalg.cholesky(P["S"] + 1e-10 * np.eye(Dt))
        folds = []
        for _k in range(4):
            z = rng.normal(0, 1, (R, Dt))
            noise = np.linalg.solve(Lc.T, z.T).T * math.sqrt(DE * P["s2"] / (N_HIST / 4.0))
            folds.append(bh[None, :] + noise)
        F = np.stack(folds)                 # (4, R, Dt)
        full = F.mean(axis=0)
        dis = (np.sign(F) != np.sign(full)[None]).sum(axis=0)
        bp = np.where(dis >= 2, 0.0, full)
    b0 = np.einsum("de,re->rd", A0, bp)
    return np.broadcast_to(A0, (R, Dt, Dt)).copy(), b0, np.full(R, c.n_eq)


# ------------------------------------------------------------------------------ the learner over a path
def simulate(c: W9, seed: int, R: int) -> dict:
    P = population(c.learner, c.tau, c.tau_mode)
    rng = np.random.default_rng(seed)
    gen = Gen(c, rng, R)
    T, K, lag = c.T, K_PICKS, c.L()
    Dt = ncols(c.learner)
    w_gen, _ = hist_dirs(c, P)
    warm = c.hist == "warm"
    if warm:
        A0, b0, N0 = prior(c, P, rng, R)
    else:
        A0, b0, N0 = np.zeros((R, Dt, Dt)), np.zeros((R, Dt)), np.zeros(R)
    A = np.zeros((R, Dt, Dt))
    bv = np.zeros((R, Dt))
    Nw = np.zeros(R)
    rows = np.zeros(R)
    nsess = np.zeros(R)
    pend: list = []
    delta = 2.0 ** (-1.0 / H_LIFE)
    last = np.full((R, U), -10_000, dtype=np.int64)
    out = dict(n=np.zeros((R, T), dtype=np.int16), iss=np.full((R, T, K), -1, dtype=np.int32),
               a=np.full((R, T, K), np.nan), cm=np.full((R, T, K), np.nan), b=np.zeros((R, T)),
               ctl=np.full((R, T), np.nan), tau=np.full((R, T), np.nan), sig=np.full((R, T), np.nan),
               edge=np.full((R, T), np.nan), guarded=np.zeros((R, T), dtype=np.int16), uhz=np.full((R, T), np.nan))
    eye = np.eye(Dt)[None]
    for t in range(-c.pre, T):
        s = gen.session(w_gen, P)
        X, vf, nv, valid, ids = s["X"], s["vf"], s["nv"], s["valid"], s["ids"]
        if not warm:
            X[..., len(KEEP) + 17] = 0.0        # the cold learner has no g
        while pend and pend[0][0] <= t - lag:
            _, As, bs, ns = pend.pop(0)
            A = delta * A + As
            bv = delta * bv + bs
            Nw = delta * Nw + ns
            rows += ns
            nsess += (ns > 0)
        if t >= 0:
            elig = valid & (np.take_along_axis(last, ids, axis=1) < t - 5)
            if c.guard:
                g_ok = s["sigH"] >= GUARD
                out["guarded"][:, t] = (elig & ~g_ok).sum(axis=1)
                elig = elig & g_ok
            xbar = (X * vf[..., None]).sum(axis=1) / nv[:, None]
            Xc = X - xbar[:, None, :]
            ready = np.ones(R, dtype=bool) if warm else (rows >= 2000) & (nsess >= 3)
            At = A0 + A
            bt = b0 + bv
            Nt = np.maximum(N0 + Nw, 1.0)
            dg = np.einsum("rii->ri", At) / Nt[:, None]
            dsd = np.sqrt(np.maximum(dg, 1e-18))
            zero = dg < 1e-18
            dsd = np.where(zero, 1.0, dsd)
            As_ = At / (dsd[:, :, None] * dsd[:, None, :])
            bs_ = bt / dsd
            if zero.any():
                zz = zero.astype(float)
                keep = 1.0 - zz
                As_ = As_ * keep[:, :, None] * keep[:, None, :]
                bs_ = bs_ * keep
            beta_s = np.linalg.solve(As_ + LAM * eye, bs_[..., None])[..., 0]
            bhat = beta_s / dsd
            ehat = np.einsum("rnd,rd->rn", Xc, bhat)
            zhat = ehat - s["c_rep"] / s["sig_hat"]
            key = zhat * s["sig_hat"]
            score = np.where(elig & ready[:, None] & (zhat > 0), key, -np.inf)
            top = np.argsort(-score, axis=1)[:, :K]
            ok = np.take_along_axis(score, top, axis=1) > -np.inf
            pid = np.where(ok, np.take_along_axis(ids, top, axis=1), -1)
            out["n"][:, t] = ok.sum(axis=1)
            out["iss"][:, t, :] = pid
            out["a"][:, t, :] = np.where(ok, np.take_along_axis(s["a"], top, axis=1), np.nan)
            out["cm"][:, t, :] = np.where(ok, np.take_along_axis(s["cm"], top, axis=1), np.nan)
            out["b"][:, t] = s["b"]
            out["ctl"][:, t] = (s["a"] * vf).sum(axis=1) / nv
            has = ok.any(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                out["tau"][has, t] = np.nanmean(np.where(ok, np.take_along_axis(s["tau"], top, axis=1), np.nan)[has], axis=1)
                out["sig"][has, t] = np.nanmean(np.where(ok, np.take_along_axis(s["sig"], top, axis=1), np.nan)[has], axis=1)
                out["edge"][has, t] = np.nanmean(np.where(ok, np.take_along_axis(s["cm"], top, axis=1), np.nan)[has], axis=1)
                out["uhz"][has, t] = np.nanmean(np.where(ok, np.take_along_axis(s["uhz"], top, axis=1), np.nan)[has], axis=1)
            rr, kk = np.nonzero(ok)
            last[rr, pid[rr, kk]] = t
        y = s["y"]
        ybar = (y * vf).sum(axis=1) / nv
        Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
        yd = (y - ybar[:, None]) * vf
        As = np.matmul(Xd.transpose(0, 2, 1), Xd)
        bs = np.einsum("rnd,rn->rd", Xd, yd)
        pend.append((t, As, bs, vf.sum(axis=1)))
    return out


# ------------------------------------------------------------------------------ the frozen screen (calib_w7's)
def alpha_of(S):
    lo = 0
    for s_up, a in PIECES:
        if lo < S <= s_up:
            return a
        lo = s_up
    return 0.0


def screen(sim, rep, max_runs=99, T_lim=None):
    """First pass on one program: (session of the pass or -1, run, the record's TRUE mean a at the pass or None,
    runs started, retired). RETIRE ends the version. A run ends at its 60th block; the next starts with the next."""
    n = sim["n"][rep]
    T = len(n) if T_lim is None else min(T_lim, len(n))
    av, ctl, bt, iss, cmv = sim["a"][rep], sim["ctl"][rep], sim["b"][rep], sim["iss"][rep], sim["cm"][rep]
    run = 1
    t0 = 0
    while t0 < T and run <= max_runs:
        blocks, w, cblocks = [], [], []
        ev_iss: list = []
        ev_a: list = []
        ev_cm: list = []
        sum_a = sum_r = top_a = top_r = 0.0
        ntop = 0
        seen: set = set()
        k = 0
        ended = -1
        for t in range(t0, T):
            kk = int(n[t])
            if kk == 0:
                continue
            a_t = av[t, :kk].astype(float)
            blocks.append(float(a_t.mean()))
            w.append(min(kk, CAP))
            cblocks.append(float(ctl[t]))
            ev_iss.extend(int(x) for x in iss[t, :kk])
            ev_a.extend(float(x) for x in a_t)
            ev_cm.extend(float(x) for x in cmv[t, :kk])
            sa = math.fsum(a_t)
            sum_a += sa
            sum_r += sa + kk * float(bt[t])
            kt = min(kk, CAP)
            st = math.fsum(a_t[:kt])
            top_a += st
            top_r += st + kt * float(bt[t])
            ntop += kt
            seen.update(int(x) for x in iss[t, :kk])
            S = len(blocks)
            N = len(ev_a)
            if k < len(LOOKS) and S >= LOOKS[k] and N >= MIN_N and len(seen) >= MIN_ISS and S >= MIN_BLK:
                while k < len(LOOKS) and S >= LOOKS[k]:
                    k += 1
                alpha = alpha_of(S)
                xb = np.array(blocks)
                wv = np.array(w, float)
                mean_a = sum_a / N
                yq = -wv * xb
                if mean_a < 0 and cl.zstat(yq) >= cl.Z_PRE and cl.flip_p(yq) <= alpha + TIE:
                    return -1, run, None, run, True
                yv = wv * (xb - M0)
                if (cl.zstat(yv) >= cl.Z_PRE and cl.flip_p(yv) <= alpha and mean_a > 0 and sum_r / N > 0
                        and top_a / ntop > 0 and top_r / ntop > 0 and xb.mean() > float(np.mean(cblocks))
                        and cl.issuer_p(ev_iss, ev_a, cl.B_ISS6) <= ISS_ALPHA + TIE):
                    return t, run, float(np.mean(ev_cm)), run, False
            if S >= HORIZON:
                ended = t
                break
        if ended < 0:
            return -1, run, None, run, False
        run += 1
        t0 = ended + 1
    return -1, min(run, max_runs), None, min(run, max_runs), False


# ------------------------------------------------------------------------------ grids
SHAPES = ("crash", "crasht3", "crashcl", "crasht3cl")


def nm(c: W9) -> str:
    h = "cold" if c.hist == "cold" else (f"ADV{c.adv}{int(c.adv_k * 100):02d}" if c.adv else
                                          (f"CHAR{int(round(c.drift_c * 1e4)):02d}-" if c.drift_c else "") +
                                          ("H0" if c.ic_h == 0 else f"HD{int(round(c.ic_h * 100)):02d}") +
                                          ("-tauh" if c.tauh else ""))
    if c.null == "A":
        h = ("cold" if c.hist == "cold" else f"rho{int(round(c.rho_h * 10)):02d}") + f"-ic{int(round(c.ic * 100)):02d}"
    if c.null == "N2":
        h = f"N2ic{int(round(c.ic * 100)):02d}-" + h
    return (f"{c.learner}-{h}-{c.shape}-{'skew' if c.ev_skew else 'sym'}-rho{int(round(c.rho_day * 100)):02d}"
            f"-phi{int(round(c.phi_day * 100)):02d}-dr{int(round(c.drift_sd * 1e4)):02d}-tau{int(round(c.tau * 100))}"
            f"{'all' if c.tau_mode == 'all' else ''}-n{int(c.nbar)}-lag{c.L()}{'-cnt' if c.cnt else ''}"
            f"{'' if c.guard else '-noguard'}{'-sec%02d' % round(c.sec_drift * 1e4) if c.sec_drift else ''}"
            f"{'-fam%02d' % round(c.fam_drift * 1e4) if c.fam_drift else ''}{'-T%d' % c.T if c.T != 120 else ''}")


def mk(**kw) -> W9:
    c = W9("x", **kw)
    return dataclasses.replace(c, name=nm(c))


def grid(name):
    """(cells, first seed). Fresh seed sets: 401e6 (search), 402e6 (the selected worst cells' fresh replicate), 403e6
    (power), 404e6 (life), 405e6 (stresses), 406e6 (reported structures). Used elsewhere: the EVL-9 judge 191-196e6,
    its learners lens 90-99e6, check 1 301-303e6, check 2 197e6; PREREG-EVL-6 111-126e6 and 150-166e6; PREREG-EVL-7's
    fix 201-206e6; the lens 71e6."""
    cells = []
    if name == "search":
        for L in ("O1", "ON"):
            for h in (dict(ic_h=0.0), dict(ic_h=0.08)):
                for sh in SHAPES:
                    cells.append(mk(learner=L, shape=sh, phi_day=0.20, drift_sd=0.0020, **h))
                cells.append(mk(learner=L, shape="crasht3cl", phi_day=0.15, drift_sd=0.0020, **h))
                cells.append(mk(learner=L, shape="crasht3cl", phi_day=0.20, drift_sd=0.0010, **h))
                cells.append(mk(learner=L, shape="crasht3cl", phi_day=0.10, drift_sd=0.0020, **h))
                cells.append(mk(learner=L, shape="crasht3cl", phi_day=0.20, drift_sd=0.0, **h))
            for sh in SHAPES:
                cells.append(mk(learner=L, shape=sh, ic_h=0.08, drift_c=0.0010))
                cells.append(mk(learner=L, shape=sh, ic_h=0.08, drift_c=0.0020))
                cells.append(mk(learner=L, shape=sh, ic_h=0.0, cnt=0.3))
            for sh in ("crasht3", "crasht3cl"):
                cells.append(mk(learner=L, shape=sh, ic_h=0.05))
                cells.append(mk(learner=L, shape=sh, ic_h=0.08, cnt=0.3))
                cells.append(mk(learner=L, shape=sh, ic_h=0.0, tau=0.0))
            for adv, k in (("leak", 0.30), ("rand", 0.60), ("lowvol", 0.30)):
                cells.append(mk(learner=L, shape="crasht3cl", adv=adv, adv_k=k))
            cells.append(mk(learner=L, shape="crasht3cl", ic_h=0.08, drift_c=0.0020, cnt=0.3))
            cells.append(mk(learner=L, shape="crasht3cl", ic_h=0.0, ev_skew=False))
            cells.append(mk(learner=L, shape="crasht3cl", ic_h=0.0, nbar=600.0))
            cells.append(mk(learner=L, shape="crasht3cl", ic_h=0.08, nbar=600.0))
            cells.append(mk(learner=L, shape="crasht3cl", ic_h=0.0, rho_day=0.05))
            cells.append(mk(learner=L, shape="crasht3cl", null="N2", ic=0.05, ic_h=0.05))
            cells.append(mk(learner=L, shape="crasht3cl", null="N2", ic=0.08, ic_h=0.08))
            cells.append(mk(learner=L, shape="crasht3cl", hist="cold"))
            cells.append(mk(learner=L, shape="crashcl", hist="cold"))
            cells.append(mk(learner=L, shape="t3", ic_h=0.0, rho_day=0.05, phi_day=0.10, ev_skew=False, drift_sd=0.0,
                            tau=0.0))
            cells.append(mk(learner=L, shape="t3", ic_h=0.08, rho_day=0.05, phi_day=0.10, ev_skew=False, drift_sd=0.0,
                            tau=0.0))
        for sh in SHAPES:
            cells.append(mk(learner="ON", shape=sh, ic_h=0.0, tauh=True))
        cells.append(mk(learner="ON", shape="crasht3cl", ic_h=0.0, tauh=True, cnt=0.3))
        return cells, 401_000_001
    if name.startswith("fresh"):
        spec = json.loads(os.environ["W9_CELLS"])
        return [W9(**s) for s in spec], int(os.environ.get("W9_SEED", "402000001"))
    if name == "power":
        for L, pool in (("O1", 300.0), ("ON", 600.0)):
            for ic in (0.03, 0.05, 0.08):
                cells.append(mk(learner=L, null="A", ic=ic, hist="cold", nbar=pool, shape="t3", rho_day=0.05,
                                phi_day=0.10, ev_skew=False, drift_sd=0.0, tau=0.0))
                for rho in (1.0, 0.7, 0.0):
                    cells.append(mk(learner=L, null="A", ic=ic, ic_h=ic, rho_h=rho, nbar=pool, shape="t3",
                                    rho_day=0.05, phi_day=0.10, ev_skew=False, drift_sd=0.0, tau=0.0))
        for hist, rho in (("cold", 1.0), ("warm", 1.0), ("warm", 0.7)):
            cells.append(mk(learner="ON", null="A", ic=0.05, ic_h=0.05, rho_h=rho, hist=hist, nbar=600.0,
                            shape="crasht3cl", tau=0.0))
        return cells, 403_000_001
    if name == "life":
        spec = json.loads(os.environ["W9_CELLS"])
        return [dataclasses.replace(W9(**s), T=200, name=W9(**s).name + "-T200") for s in spec], 404_000_001
    if name == "stress":
        for L in ("O1", "ON"):
            cells.append(mk(learner=L, shape="crasht3cl", phi_day=0.25, ic_h=0.0))
            cells.append(mk(learner=L, shape="crash", rho_day=0.30, phi_day=0.10, ic_h=0.0))
            cells.append(mk(learner=L, shape="crash", rho_day=0.30, phi_day=0.40, ic_h=0.0))
            cells.append(mk(learner=L, shape="crasht3cl", drift_sd=0.0030, ic_h=0.0))
            cells.append(mk(learner=L, shape="crasht3cl", ic_h=0.08, drift_c=0.0030))
            cells.append(mk(learner=L, shape="crasht3cl", ic_h=0.0, sec_drift=0.0020, tau=0.0))
            cells.append(mk(learner=L, shape="crasht3cl", ic_h=0.0, guard=False))
            cells.append(mk(learner=L, shape="crasht3cl", adv="lowvol", adv_k=0.30, guard=False))
        cells.append(mk(learner="ON", shape="crasht3cl", ic_h=0.0, tau_mode="all"))
        cells.append(mk(learner="ON", shape="crasht3cl", ic_h=0.0, tau_mode="all", tauh=True))
        cells.append(mk(learner="ON", shape="crasht3cl", ic_h=0.0, tau=0.02, tauh=True))
        return cells, 405_000_001
    if name == "smoke":
        return [mk(learner="ON", shape="crasht3cl", ic_h=0.0, T=40), mk(learner="O1", shape="crasht3cl", ic_h=0.08,
                                                                          T=40)], 400_000_001
    raise SystemExit(f"unknown grid {name}")


def _job(args):
    c, seed, R = args
    t0 = time.time()
    sim = simulate(c, seed, R)
    allr = [screen(sim, i) for i in range(R)]
    res = {"cell": c.name, "seed": seed, "R": R, "T": c.T, "spec": dataclasses.asdict(c),
           "when": [x[0] for x in allr], "run": [x[1] for x in allr], "cm": [x[2] for x in allr],
           "nruns": [x[3] for x in allr], "ret": [int(x[4]) for x in allr]}
    if c.T > 120:
        cap3 = [screen(sim, i, max_runs=3) for i in range(R)]
        res["c3when"] = [x[0] for x in cap3]
        res["c3runs"] = [x[3] for x in cap3]
    with np.errstate(invalid="ignore"):
        res["ev_s"] = float(sim["n"].mean())
        res["a_bp"] = float(np.nanmean(sim["a"]) * 1e4)
        res["cm_bp"] = float(np.nanmean(sim["cm"]) * 1e4)
        res["tau_bp"] = float(np.nanmean(sim["tau"]) * 1e4)
        res["sig"] = float(np.nanmean(sim["sig"]))
        res["guarded"] = float(sim["guarded"].mean())
        res["uhz"] = float(np.nanmean(sim["uhz"]))   # the picks' mean history index, in pool sd above the pool mean
        ed = sim["edge"]
        res["edge_bp"] = {f"{lo + 1}-{lo + 10}": round(float(np.nanmean(ed[:, lo:lo + 10])) * 1e4, 2)
                          for lo in range(0, c.T, 10) if not np.all(np.isnan(ed[:, lo:lo + 10]))}
    res["secs"] = round(time.time() - t0, 1)
    return res


def run_multi(spec, chunk, workers):
    """spec: [(grid, reps), ...]: one pool of jobs over several grids, each grid's cells with their own seed base and
    their own output file w9.<grid>.jsonl (the same seeds a separate run of each grid would draw)."""
    from multiprocessing import Pool
    jobs, fhs = [], {}
    for gname, reps in spec:
        cells, seed0 = grid(gname)
        for c in cells:
            population(c.learner, c.tau, c.tau_mode)
        fhs[gname] = open(os.path.join(HERE, f"w9.{gname}.jsonl"), "w")
        for ci, c in enumerate(cells):
            for j in range(max(1, reps // chunk)):
                jobs.append((gname, j, (c, seed0 + 1000 * ci + j, chunk)))
    jobs.sort(key=lambda x: x[1])
    order = [x[0] for x in jobs]
    t0 = time.time()
    with Pool(workers) as pool:
        for k, (res, gname) in enumerate(pool.imap_unordered(_tagged, [(g, a) for g, _, a in jobs])):
            fhs[gname].write(json.dumps(res) + "\n")
            fhs[gname].flush()
            print(f"{gname}: {k + 1}/{len(order)} {res['cell']} seed {res['seed']} {res['secs']}s total "
                  f"{time.time() - t0:.0f}s", flush=True)
    for fh in fhs.values():
        fh.close()


def _tagged(x):
    return _job(x[1]), x[0]


def run(gridname, reps, chunk, workers, seed=None, tag=None, resume=False, only=None):
    from multiprocessing import Pool
    cells, seed0 = grid(gridname)
    if seed:
        seed0 = seed
    for c in cells:
        population(c.learner, c.tau, c.tau_mode)
    path = os.path.join(HERE, f"w9.{tag or gridname}.jsonl")
    done = set()
    if resume and os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            done.add((r["cell"], r["seed"]))
    jobs = []
    for ci, c in enumerate(cells):
        if only and not any(o in c.name for o in only):
            continue
        for j in range(max(1, reps // chunk)):
            if (c.name, seed0 + 1000 * ci + j) not in done:
                jobs.append((c, seed0 + 1000 * ci + j, chunk))
    # interleave cells so a partial run covers every cell
    jobs.sort(key=lambda x: (x[1] - seed0) % 1000)
    t0 = time.time()
    with Pool(workers) as pool, open(path, "a" if resume else "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gridname}: {k + 1}/{len(jobs)} {res['cell']} seed {res['seed']} {res['secs']}s "
                  f"total {time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------------------ report
def _se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / max(n, 1))


def summarise(parts):
    R = sum(p["R"] for p in parts)
    wh = np.concatenate([p["when"] for p in parts])
    rn = np.concatenate([p["run"] for p in parts])
    cm = np.array([c if c is not None else np.nan for p in parts for c in p["cm"]])
    nr = np.concatenate([p["nruns"] for p in parts])
    rt = np.concatenate([p["ret"] for p in parts])
    one = (wh >= 0) & (rn == 1)
    s = dict(R=R, run1=float(one.mean()), run1_se=_se(float(one.mean()), R), v120=float(((wh >= 0) & (wh < 120)).mean()),
             cm0=float((one & (cm <= 0)).mean()), cm10=float((one & (cm <= 0.0010)).mean()), runs=float(nr.mean()),
             retired=float(rt.mean()))
    for h in (20, 22, 25, 30, 40, 60, 120):
        s[f"by{h}"] = float((one & (wh < h)).mean())
        s[f"vby{h}"] = float(((wh >= 0) & (wh < h)).mean())
    if "c3when" in parts[0]:
        c3 = np.concatenate([p["c3when"] for p in parts])
        c3r = np.concatenate([p["c3runs"] for p in parts])
        T = parts[0]["T"]
        s["life3"] = float((c3 >= 0).mean())
        s["life3_runs"] = float(c3r.mean())
        for h in (60, 120, 180, T):
            s[f"life3_by{h}"] = float(((c3 >= 0) & (c3 < h)).mean())
    for key in ("ev_s", "a_bp", "cm_bp", "tau_bp", "sig", "guarded"):
        s[key] = float(np.mean([p[key] for p in parts]))
    s["uhz"] = float(np.mean([p["uhz"] for p in parts])) if all("uhz" in p for p in parts) else float("nan")
    p0 = parts[0]
    s["edge_bp"] = {k: round(float(np.mean([p["edge_bp"].get(k, np.nan) for p in parts])), 1) for k in p0["edge_bp"]}
    return s


def load(tag):
    by: dict = {}
    for line in open(os.path.join(HERE, f"w9.{tag}.jsonl")):
        r = json.loads(line)
        by.setdefault(r["cell"], []).append(r)
    return by


def report(only=None):
    for path in sorted(glob.glob(os.path.join(HERE, "w9.*.jsonl"))):
        tag = os.path.basename(path)[3:-6]
        if only and only not in tag:
            continue
        by = load(tag)
        print(f"== w9.{tag}.jsonl ({sum(len(v) for v in by.values())} jobs)")
        rows = sorted(((summarise(p), n) for n, p in by.items()), key=lambda x: -x[0]["run1"])
        for s, name in rows:
            extra = ""
            if "life3" in s:
                extra = (f" | LIFE(<=3 runs) {s['life3']:.4f} by60 {s['life3_by60']:.3f} by120 {s['life3_by120']:.3f} "
                         f"runs {s['life3_runs']:.2f}")
            print(f"{name:<66} R={s['R']:<5} RUN1 {s['run1']:.4f} (se {s['run1_se']:.4f}) [cm<=0 {s['cm0']:.4f}] "
                  f"by20/25/40/60/120 {s['by20']:.3f}/{s['by25']:.3f}/{s['by40']:.3f}/{s['by60']:.3f}/{s['by120']:.3f} "
                  f"| VERSION by120 {s['v120']:.4f} | ev/s {s['ev_s']:.2f} a {s['a_bp']:+.1f}bp tau {s['tau_bp']:+.1f}bp "
                  f"sig {s['sig']:.3f} guarded/s {s['guarded']:.1f}{extra}")
            if any(np.isfinite(v) and v != 0 for v in s["edge_bp"].values()) and ("-ic" in name):
                print("      picks' true a edge (bp) " + " ".join(f"{k}:{v}" for k, v in s["edge_bp"].items()))


def selftest():
    for L in ("O1", "ON"):
        P = population(L, 0.01, "event")
        print(L, "D", ncols(L), "s2", round(P["s2"], 3), "own slope", np.round(P["own"][-2:], 3),
              "b_cost norm", round(float(np.linalg.norm(P["b_cost"])), 4))
    for c in grid("smoke")[0]:
        t0 = time.time()
        sim = simulate(c, 1, 20)
        print(c.name, f"{time.time() - t0:.1f}s", "ev/s", round(float(sim["n"].mean()), 2), "a bp",
              round(float(np.nanmean(sim["a"]) * 1e4), 1), "sig", round(float(np.nanmean(sim["sig"])), 4),
              "guarded/s", round(float(sim["guarded"].mean()), 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "multi", "report", "selftest"))
    ap.add_argument("--grid", default="search")
    ap.add_argument("--reps", type=int, default=400)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    if a.cmd == "report":
        report(a.only[0] if a.only else None)
    elif a.cmd == "selftest":
        selftest()
    elif a.cmd == "multi":
        run_multi([(g.split(":")[0], int(g.split(":")[1])) for g in a.only], a.chunk, min(8, a.workers))
    else:
        run(a.grid, a.reps, a.chunk, min(8, a.workers), a.seed, a.tag, a.resume, a.only)

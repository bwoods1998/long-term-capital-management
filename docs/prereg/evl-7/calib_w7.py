#!/usr/bin/env python
"""calib_w7.py: PREREG-EVL-7's FINAL calibration (the captain's E1 and E7). SYNTHETIC ONLY.

Nothing here reads the lane: no House, gateway, events.sqlite, live.sqlite, run record, price, return, look or band.
Every number is drawn from the learner lens's generator and learner (evl7/learner/calib_learner.py, imported
unchanged), extended as below, and judged by PREREG-EVL-6's screen AS FROZEN (docs/prereg/PREREG-EVL-6.md, sha256
0f67f94ecac93f6b5542654e33ce5180fdbac254238badd571a37bcb0950f057, sections 1-3).

THE LEARNER (the final design; PREREG-EVL-7 sections 1.4-1.6): session-demeaned weighted ridge, lambda 8,000 on
standardized columns, half-life 40 sessions, K = 8, ranked by ahat = sig20 x z, z = e - c_rep / sig20, warm-up 2,000
rows from 3 sessions (3 pre-registration sessions), training lag LAG (1: EVL-LRN-O1; 2: EVL-LRN-ON or a late score).
D = 40 (the lens's columns) + EXTRA pure-noise columns (17: the 16 headline keyword flags and dup72 PREREG-EVL-7 adds,
as calib_evl7.py's D57 draws them; 23 = 17 + 6 more for EVL-LRN-ON's 63 columns). The extra columns carry nothing.

E7, THE GROSS LABEL: every candidate has three returns of the same event: a_g, the GROSS abnormal return (no cost);
a_rep = a_g - c_rep (the replay's cost, score.py cost_bp at E = $1,898: 14.2 bp a round trip at ADV >= $10M, 24.2 bp
thinner); a7 = a_g - c7 (COST-7 at its warm-up, E = $1,898: margin 2.5 bp a side, the penny-ceiling fees at the
Probe share 0.035 on the issuer's price, impact 1e4 x sigma x sqrt(0.10 E / ADV) a side with sigma = sig20 floored at
0.02 and capped at 0.25 (E9), G = 0). The learner's LABEL is y = clip(a_g / sig20, -5, 5) (E7); its hurdle is c_rep
(section 1.6); THE SCREEN READS a7 and r7 = a7 + b (section 3.1). ADV = $10M x exp(ln_adv), price = $20 x exp(ln_px),
from the lens's issuer columns.

THE NULLS, in the screen's own units (a7):
  N1  the features carry nothing: E[a7] = 0 for EVERY candidate (so E[a_g] = c7: gross pays exactly COST-7). Whatever
      the learner learns, its picks' mean a7 is exactly 0: the binding null.
  N2  the knife edge: E[a7] = sig x ic x min(u - u95, 0): the top 5% by the true index have mean exactly 0.
  N3  learnable persistent structure (STRESSES): a family or sector drift; its picks can carry a positive mean, so each
      pass is reported with the share whose record's TRUE conditional mean a7 is <= 0 and <= 10 bp.
THE ALTERNATIVE (power): A, E[a_g] = sig x ic x u (the pool's GROSS mean about 0, the fixed level's prior), so the
pool loses its cost after cost and the features carry an information coefficient ic.

THE FROZEN PLAUSIBLE GRID'S STRUCTURES added to the lens's generator (PREREG-EVL-6 sections 4.2-4.3, D1, D14):
  day   t3 (symmetric), crash (5% of sessions N(-3, 1), a normal body: the lens's), crasht3 (a t(3) body), crashcl
        (crash probability p_t = 0.05 exp(2 x_t) / E[exp(2 x)], at most 0.09, x_t the volatility regime's log state,
        stationary sd 0.3, the lens's own regime), crasht3cl (both); each day of mean 0 and variance 1.
  phi   the day shock's AR, 0.10, 0.15, 0.20 (stresses 0.25, 0.40).
  cnt   counts that follow the size of the day shock: the POOL's count x exp(0.3 min(|eps_t|, 4)) / its mean (the
        learner picks at most 8 a session, so the frozen rule's money weights min(n_s, 14) = n_s throughout).
  issuer effects of 1%, drift 0 / 10 / 20 bp AR 0.97, left-skewed events, rho_day <= 0.15, pools of 300 and 800.

THE SCREEN (PREREG-EVL-6 sections 1-3 as frozen): blocks = sessions with a pick; y_s = min(n_s, 14) (B_s - 10 bp);
looks at S = 22, 25, 30, 35, 40, 50, 60 once >= 30 events, >= 30 issuers and >= 6 blocks; alpha(S) 0.020 (S 22-30),
0.006 (31-40), 0.001 (41-60); at a look RETIRE first (mean a < 0 and q <= alpha + 1e-12, q the sign-flip count on
-min(n_s, 14) B_s), then PASS (p <= alpha; mean a > 0; mean r > 0; the top-14 events of each block by the learner's
rank (all of its at most 8) pooled: mean a > 0 and mean r > 0; the mean block value (unweighted) above the POOL
control's over the same sessions; issuer-block p_I <= 0.10). A run ENDS at its 60th block and run n + 1 starts with
the next block (the budget assumed to hold it). Monte Carlo shortcuts as PREREG-EVL-6 section 4.2 (and the lens):
exact p for S <= 16, else 19,999 fixed sign vectors; the issuer guard over 999; p or q computed only where z >= 1.0.

Usage: calib_w7.py run --grid NAME [--reps R] [--chunk C] [--workers W] [--seed S]  |  report [--only NAME]
       calib_w7.py validate   (the screen against check 1's ev6d_w on the judge's own paths)
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
for _p in (HERE, os.path.join(os.path.dirname(HERE), "learner")):
    if os.path.exists(os.path.join(_p, "calib_learner.py")):
        sys.path.insert(0, _p)
        break
import calib_learner as cl  # noqa: E402

U = cl.U
D0 = cl.D                      # 40, the lens's columns
FINAL = dict(rank="a", lam=8000.0, kappa=0.0)
WORST = cl.WORST               # rho_day 0.15, crash days, left-skewed events, 20 bp drift, 1% issuer effects

# ------------------------------------------------------------------------------------------- the frozen screen
LOOKS7 = (22, 25, 30, 35, 40, 50, 60)
PIECES7 = ((30, 0.020), (40, 0.006), (60, 0.001))
M0 = 0.0010
CAP = 14
HORIZON = 60
MIN_N, MIN_ISS, MIN_BLK = 30, 30, 6
ISS_ALPHA = 0.10
TIE = 1e-12

# validation: check 1's ev6d_w (looks from 6, 0.016 to S 20, 0.004 after, weighted, run-chained)
RULES = {
    "frozen": dict(looks=LOOKS7, pieces=PIECES7),
    "ev6d_w": dict(looks=(6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60),
                   pieces=((20, 0.016), (60, 0.004))),
}

# ------------------------------------------------------------------------------------------- costs (E = $1,898)
E_EQ = 1898.0
PS = 0.035


def ceilcent(x):
    return np.ceil(np.round(x * 100.0, 9)) / 100.0


def costs(lnadv, lnpx, sig_hat):
    """(c_rep, c7) round trips as returns, per issuer: score.py's replay and COST-7's warm-up (sections 2.1, E9)."""
    adv = 1e7 * np.exp(lnadv)
    px = 20.0 * np.exp(lnpx)
    n = 0.05 * E_EQ
    c_rep = (2 * (0.5 + np.where(adv >= 1e7, 5.0, 10.0)) + (0.01 / n + 0.02 / n) * 1e4) / 1e4
    nref = np.maximum(1.0, np.floor(PS * E_EQ / (1.25 * px)))
    N = nref * px
    fee = (0.01 / N + (0.01 + ceilcent(27.80e-6 * N) + ceilcent(np.minimum(0.000166 * nref, 8.30))) / N) * 1e4
    sigma = np.clip(sig_hat, 0.02, 0.25)
    imp = 1e4 * sigma * np.sqrt(0.10 * E_EQ / adv)
    c7 = (2 * 2.5 + fee + 2 * imp) / 1e4
    return c_rep, c7


# ------------------------------------------------------------------------------------------- cells
@dataclasses.dataclass(frozen=True)
class X7:
    day: str = ""              # '' = the Cell's own (t3 / crash); else crasht3 | crashcl | crasht3cl
    cnt: float = 0.0           # counts that follow the day (0.3)
    extra: int = 17            # extra noise columns (17: D 57; 23: D 63; 0: D 40)
    sec_drift: float = 0.0     # a learnable sector drift (stress)
    gross: bool = True         # E7's gross label (False: the draft's after-replay-cost label, for comparison)


EXTRA_P = np.array([.02, .03, .04, .05, .06, .08, .10, .12, .15, .02, .03, .05, .08, .10, .20, .30])
ON_P = np.array([.30, .45, .10])


def issuers7(rng, R, cell, x7):
    """calib_learner.issuers' draws in its order (identical paths), with the costs and a sector drift's sectors."""
    iss = cl.issuers(rng, R, cell)
    lnadv, lnpx = iss["ilev"][..., 0], iss["ilev"][..., 1]
    c_rep, c7 = costs(lnadv, lnpx, iss["sig_hat"])
    iss["c_rep"], iss["c7"] = c_rep, c7
    return iss


def pool_features7(rng, R, N, iss, ids, extra):
    X0, fam = cl.pool_features(rng, R, N, iss, ids)
    if extra <= 0:
        return X0, fam
    X = np.zeros((R, N, D0 + extra))
    X[..., :D0] = X0
    X[..., D0:D0 + 16] = rng.random((R, N, 16)) < EXTRA_P
    X[..., D0 + 16] = rng.beta(0.6, 2.0, (R, N))
    if extra > 17:          # EVL-LRN-ON's six more: three binaries and three continuous, all noise
        X[..., D0 + 17:D0 + 20] = rng.random((R, N, 3)) < ON_P
        X[..., D0 + 20:D0 + 23] = np.clip(cl.unit_t3(rng, (R, N, 3)), -5, 5)
    return X, fam


CR_P, CR_K, CL_G, CL_MAX, VSD = 0.05, 3.0, 2.0, 0.09, 0.3


def day_draws(rng, R):
    """The three arrays a crash day draws (the lens's crash shape draws three as well)."""
    return rng.random(R), rng.normal(-CR_K, 1.0, R), None


def day_eps(kind, rng, R, vx, pre=None):
    """eps of unit variance and mean 0 for the D14 shapes, the clustered ones from the regime state vx (this session's)."""
    u, crash = pre[0], pre[1]
    body = pre[2]
    p = np.minimum(CR_P * np.exp(CL_G * vx) / math.exp(CL_G ** 2 * VSD ** 2 / 2.0), CL_MAX) if kind.endswith("cl") \
        else np.full(R, CR_P)
    m = p * CR_K / (1.0 - p)
    s = np.sqrt((1.0 - p * (CR_K ** 2 + 1.0)) / (1.0 - p) - m * m)
    return np.where(u < p, crash, m + s * body)


_CNORM: dict = {}


def count_norm(kind, kappa):
    """E[exp(kappa min(|eps|, 4))] under the day law (the regime's stationary law for the clustered shapes)."""
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
            e_ = day_eps(kind, rr, M, vx, (u, cr, body))
        _CNORM[key] = float(np.exp(kappa * np.minimum(np.abs(e_), 4.0)).mean())
    return _CNORM[key]


def simulate7(cell, x7, seed, R):
    rng = np.random.default_rng(seed)
    T, K = cell.T, cell.K
    iss = issuers7(rng, R, cell, x7)
    Dt = D0 + x7.extra
    Nmax = int(cell.nbar * (4.5 if x7.cnt else 3.2)) + 20
    sd_c = cell.sd_day()
    zday = np.zeros(R)
    vx = rng.normal(0, 0.3, R)
    drift = rng.normal(0, cell.drift_sd, R) if cell.drift_sd else np.zeros(R)
    fdrift = rng.normal(0, cell.fam_drift_sd, (R, 6)) if cell.fam_drift_sd else np.zeros((R, 6))
    sdsd = x7.sec_drift
    sdrift = rng.normal(0, sdsd, (R, 11)) if sdsd else np.zeros((R, 11))
    fac = np.zeros((R, 3))
    A = np.zeros((R, Dt, Dt))
    bv = np.zeros((R, Dt))
    Nw = np.zeros(R)
    rows = np.zeros(R)
    nsess = np.zeros(R)
    pend: list = []
    delta = 2.0 ** (-1.0 / cell.H) if math.isfinite(cell.H) else 1.0
    last = np.full((R, U), -10_000, dtype=np.int64)
    out = dict(n=np.zeros((R, T), dtype=np.int16), iss=np.full((R, T, K), -1, dtype=np.int32),
               a7=np.full((R, T, K), np.nan), arep=np.full((R, T, K), np.nan), cm7=np.full((R, T, K), np.nan),
               sig=np.full((R, T, K), np.nan), b=np.zeros((R, T)), c7ctl=np.full((R, T), np.nan),
               crepctl=np.full((R, T), np.nan), edge7=np.full((R, T), np.nan), npool=np.zeros((R, T), dtype=np.int32),
               edgerep=np.full((R, T), np.nan), c7p=np.full((R, T, K), np.nan), crepp=np.full((R, T, K), np.nan))
    um, usd, u95 = cl.u_norm(cl.W_TRUE)
    w_now = cl.W_TRUE
    newday = x7.day in ("crasht3", "crashcl", "crasht3cl")
    kind = x7.day if newday else cell.day
    Em = count_norm(kind, x7.cnt) if x7.cnt else 1.0
    for t in range(-cell.pre, T):
        if cell.null == "A2" and t == 60:
            w_now = cl.W_FLIP
            um, usd, u95 = cl.u_norm(cl.W_FLIP)
        eps = None
        if x7.cnt:            # the day comes first: the pool's count follows its size
            if newday:
                pre = (rng.random(R), rng.normal(-CR_K, 1.0, R),
                       cl.unit_t3(rng, R) if "t3" in kind else rng.standard_normal(R))
                vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
                eps = day_eps(kind, rng, R, vx, pre)
            else:
                eps = cl.day_innov(rng, cell.day, R)
                vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
            mult = np.exp(x7.cnt * np.minimum(np.abs(eps), 4.0)) / Em
            n_t = np.minimum(rng.poisson(cell.nbar * mult * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        else:
            n_t = np.minimum(rng.poisson(cell.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
        ids = np.take_along_axis(ids, order, axis=1)
        valid = np.arange(Nmax)[None, :] < n_t[:, None]
        X, fam = pool_features7(rng, R, Nmax, iss, ids, x7.extra)
        sig = np.take_along_axis(iss["sig"], ids, axis=1)
        if cell.null in ("A", "A2", "N2"):
            u = (X[..., :D0] @ w_now - um) / usd
            Ey = cell.ic * np.minimum(u - u95, 0.0) if cell.null == "N2" else cell.mu_z + cell.ic * u
        else:
            Ey = np.zeros((R, Nmax))
        sig_hat = np.take_along_axis(iss["sig_hat"], ids, axis=1)
        c_rep = np.take_along_axis(iss["c_rep"], ids, axis=1)
        c7 = np.take_along_axis(iss["c7"], ids, axis=1)
        sec = np.take_along_axis(iss["sector"], ids, axis=1)
        beta = np.take_along_axis(iss["beta"], ids[..., None], axis=1)
        tau = np.take_along_axis(iss["tau"], ids, axis=1)
        if eps is None:
            if newday:
                pre = (rng.random(R), rng.normal(-CR_K, 1.0, R),
                       cl.unit_t3(rng, R) if "t3" in kind else rng.standard_normal(R))
                vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
                eps = day_eps(kind, rng, R, vx, pre)
            else:
                eps = cl.day_innov(rng, cell.day, R)
                vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
        zday = cell.phi_day * zday + math.sqrt(1 - cell.phi_day ** 2) * eps
        c_t = sd_c * zday
        h_t = np.exp(vx - 0.09)
        s_sec = cl.unit_t3(rng, (R, 11)) * 0.010
        if cell.fac_rho:
            fac = cell.fac_rho * fac + math.sqrt(1 - cell.fac_rho ** 2) * cl.unit_t3(rng, (R, 3)) * 0.006
        else:
            fac = cl.unit_t3(rng, (R, 3)) * 0.006
        if cell.drift_sd:
            drift = cell.drift_rho * drift + math.sqrt(1 - cell.drift_rho ** 2) * rng.normal(0, cell.drift_sd, R)
        if cell.fam_drift_sd:
            fdrift = cell.drift_rho * fdrift + math.sqrt(1 - cell.drift_rho ** 2) * rng.normal(0, cell.fam_drift_sd, (R, 6))
        if sdsd:
            sdrift = cell.drift_rho * sdrift + math.sqrt(1 - cell.drift_rho ** 2) * rng.normal(0, sdsd, (R, 11))
        b_t = rng.normal(0.0004, 0.010, R)
        e = cl.unit_t3(rng, (R, Nmax), 1.4, 0.6) if cell.ev_skew else cl.unit_t3(rng, (R, Nmax))
        jl = 0.8 if cell.ev_skew else cell.jump_left
        jump = np.where(rng.random((R, Nmax)) < 0.005, np.where(rng.random((R, Nmax)) < jl, -0.30, 0.30), 0.0)
        jump = jump - 0.005 * 0.30 * (1 - 2 * jl)
        noise = h_t[:, None] * (c_t[:, None] + np.take_along_axis(s_sec, sec, axis=1)
                                + np.einsum("rnk,rk->rn", beta, fac) + sig * e)
        struct = drift[:, None] + np.take_along_axis(fdrift, fam, axis=1) + np.take_along_axis(sdrift, sec, axis=1) + tau
        if cell.null == "A" or cell.null == "A2":
            cm_g = sig * Ey + struct            # the alternative is stated GROSS (the pool's gross mean about 0)
            cm7 = cm_g - c7
        else:
            cm7 = sig * Ey + struct             # the nulls are stated in the screen's units (a7)
            cm_g = cm7 + c7
        a_g = np.maximum(cm_g + noise + jump, -1.0)
        a7 = a_g - c7
        arep = a_g - c_rep
        lab = a_g if x7.gross else arep
        y = np.clip(lab / sig_hat, -5, 5)
        vf = valid.astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        while pend and pend[0][0] <= t - cell.lag:
            _, As, bs, ns = pend.pop(0)
            A = delta * A + As
            bv = delta * bv + bs
            Nw = delta * Nw + ns
            rows += ns
            nsess += (ns > 0)
        if t >= 0:
            elig = valid & (np.take_along_axis(last, ids, axis=1) < t - 5)
            xbar = (X * vf[..., None]).sum(axis=1) / nv[:, None]
            Xc = X - xbar[:, None, :]
            ready = (rows >= cell.warm_rows) & (nsess >= cell.warm_sessions)
            dsd = np.sqrt(np.maximum(np.einsum("rii->ri", A) / np.maximum(Nw, 1)[:, None], 1e-12))
            As_ = A / (dsd[:, :, None] * dsd[:, None, :]) + cell.lam * np.eye(Dt)[None]
            bs_ = bv / dsd
            beta_s = np.linalg.solve(As_, bs_[..., None])[..., 0]
            bhat = beta_s / dsd
            ehat = np.einsum("rnd,rd->rn", Xc, bhat)
            zhat = -c_rep / sig_hat + ehat
            key = zhat * sig_hat
            score = np.where(elig & ready[:, None] & (zhat > 0), key, -np.inf)
            top = np.argsort(-score, axis=1)[:, :K]
            ok = np.take_along_axis(score, top, axis=1) > -np.inf
            pid = np.where(ok, np.take_along_axis(ids, top, axis=1), -1)
            out["n"][:, t] = ok.sum(axis=1)
            out["iss"][:, t, :] = pid
            out["a7"][:, t, :] = np.where(ok, np.take_along_axis(a7, top, axis=1), np.nan)
            out["arep"][:, t, :] = np.where(ok, np.take_along_axis(arep, top, axis=1), np.nan)
            out["cm7"][:, t, :] = np.where(ok, np.take_along_axis(cm7, top, axis=1), np.nan)
            out["sig"][:, t, :] = np.where(ok, np.take_along_axis(sig, top, axis=1), np.nan)
            out["b"][:, t] = b_t
            out["c7ctl"][:, t] = (a7 * vf).sum(axis=1) / nv
            out["crepctl"][:, t] = (arep * vf).sum(axis=1) / nv
            out["npool"][:, t] = n_t
            has = ok.any(axis=1)
            with np.errstate(invalid="ignore"):
                ed = np.nanmean(np.where(ok, np.take_along_axis(sig * Ey - (c7 if cell.null in ("A", "A2") else 0.0),
                                                                top, axis=1), np.nan)[has], axis=1)
            out["edge7"][has, t] = ed
            with np.errstate(invalid="ignore"):     # output only (added after the search stage; no draw changes)
                out["edgerep"][has, t] = np.nanmean(np.where(ok, np.take_along_axis(cm_g - c_rep, top, axis=1),
                                                             np.nan)[has], axis=1)
            out["c7p"][:, t, :] = np.where(ok, np.take_along_axis(c7, top, axis=1), np.nan)
            out["crepp"][:, t, :] = np.where(ok, np.take_along_axis(c_rep, top, axis=1), np.nan)
            rr, kk = np.nonzero(ok)
            last[rr, pid[rr, kk]] = t
        ybar = (y * vf).sum(axis=1) / nv
        Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
        yd = (y - ybar[:, None]) * vf
        As = np.matmul(Xd.transpose(0, 2, 1), Xd)
        bs = np.einsum("rnd,rn->rd", Xd, yd)
        pend.append((t, As, bs, vf.sum(axis=1)))
    return out


# ------------------------------------------------------------------------------------------- the screen
def alpha_of(pieces, S):
    lo = 0
    for s_up, a in pieces:
        if lo < S <= s_up:
            return a
        lo = s_up
    return 0.0


def screen(sim, rep, rule="frozen", basis="a7", max_runs=99, T_lim=None):
    """First pass under the rule on one program: (session of the pass or -1, run of the pass or of the last run,
    the record's TRUE conditional mean a7 (event-weighted) at the pass or None, runs started, retired: bool).
    RETIRE ends the version (no later run). A run ends at its 60th block; the next starts with the next block."""
    P = RULES[rule]
    looks, pieces = P["looks"], P["pieces"]
    n = sim["n"][rep]
    T = len(n) if T_lim is None else min(T_lim, len(n))
    av = sim["a7"][rep] if basis == "a7" else sim["arep"][rep]
    ctl = sim["c7ctl"][rep] if basis == "a7" else sim["crepctl"][rep]
    bt = sim["b"][rep]
    iss, cmv = sim["iss"][rep], sim["cm7"][rep]
    run = 1
    t0 = 0
    while t0 < T and run <= max_runs:
        blocks, w, cblocks = [], [], []
        ev_iss: list = []
        ev_a: list = []
        ev_cm: list = []
        sum_a = sum_r = 0.0
        top_a = top_r = 0.0
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
            if k < len(looks) and S >= looks[k] and N >= MIN_N and len(seen) >= MIN_ISS and S >= MIN_BLK:
                while k < len(looks) and S >= looks[k]:
                    k += 1
                alpha = alpha_of(pieces, S)
                xb = np.array(blocks)
                wv = np.array(w, float)
                mean_a = sum_a / N
                yq = -wv * xb
                if mean_a < 0 and cl.zstat(yq) >= cl.Z_PRE and cl.flip_p(yq) <= alpha + TIE:
                    return -1, run, None, run, True
                y = wv * (xb - M0)
                if (cl.zstat(y) >= cl.Z_PRE and cl.flip_p(y) <= alpha and mean_a > 0 and sum_r / N > 0
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


# ------------------------------------------------------------------------------------------- grids
C = cl.Cell


def mk(name, x7=None, **kw):
    return (C(name, **(FINAL | kw)), x7 or X7())


SHAPES = ("crash", "crasht3", "crashcl", "crasht3cl")
SPECS: dict = {}


def corner(shape, phi, drift, lag, pool=300, tau=0.01, skew=True, cnt=0.0, rho=0.15, extra=17, null="N1", ic=0.0,
           T=120, gross=True):
    day = "crash" if shape == "crash" else ("t3" if shape == "t3" else "crash")
    x7 = X7(day=shape if shape in ("crasht3", "crashcl", "crasht3cl") else "", cnt=cnt, extra=extra, gross=gross)
    nm = (f"{null}{'-ic%02d' % round(ic * 100) if ic else ''}-{shape}-{'skew' if skew else 'sym'}-rho{int(rho * 100):02d}"
          f"-phi{int(round(phi * 100)):02d}-dr{int(round(drift * 1e4)):02d}-tau{int(round(tau * 100))}-n{pool}-lag{lag}"
          f"{'-cnt' if cnt else ''}-D{40 + extra}{'' if gross else '-netlab'}{'-T%d' % T if T != 120 else ''}")
    spec = dict(shape=shape, phi=phi, drift=drift, lag=lag, pool=pool, tau=tau, skew=skew, cnt=cnt, rho=rho, extra=extra,
                null=null, ic=ic, T=T, gross=gross)
    cell, x7_ = mk(nm, x7, null=null, ic=ic, nbar=pool, T=T, rho_day=rho, day=day, ev_skew=skew, drift_sd=drift, tau=tau,
                   phi_day=phi, lag=lag)
    SPECS[cell.name] = spec
    return cell, x7_


def grid(name):
    """(cells, first seed). Every seed set is fresh: 201e6 + (search), 202e6 + (the worst cells' fresh replicate), 203e6 +
    (power), 204e6 + (life), 205e6 + (stresses), 206e6 + (sensitivity). The judge used 81-86e6, the checks 91-95e6, the
    lens 71e6; PREREG-EVL-6 used 111-126e6 and its re-check 150-166e6."""
    cells = []
    if name == "search":       # SEARCH seeds: the plausible grid around its corner, 1,000 programs a cell
        for sh in SHAPES:                                                    # the corner: every day shape, phi, drift, lag
            for phi in (0.10, 0.15, 0.20):
                for dr in (0.0, 0.0010, 0.0020):
                    for lag in (1, 2):
                        cells.append(corner(sh, phi, dr, lag))
        for lag in (1, 2):
            for phi in (0.10, 0.15, 0.20):
                cells.append(corner("t3", phi, 0.0020, lag))                 # symmetric days
            for sh in SHAPES:
                cells.append(corner(sh, 0.20, 0.0020, lag, skew=False))      # symmetric events
                cells.append(corner(sh, 0.20, 0.0020, lag, tau=0.0))         # no issuer effect
                cells.append(corner(sh, 0.20, 0.0020, lag, cnt=0.3))         # counts that follow the day
                cells.append(corner(sh, 0.15, 0.0020, lag, cnt=0.3))
                cells.append(corner(sh, 0.20, 0.0020, lag, pool=800))        # pool 800
                cells.append(corner(sh, 0.20, 0.0020, lag, rho=0.05))        # rho_day 0.05
                cells.append(corner(sh, 0.20, 0.0020, lag, null="N2", ic=0.03))   # the knife edge
                cells.append(corner(sh, 0.20, 0.0020, lag, null="N2", ic=0.05))
            cells.append(corner("t3", 0.10, 0.0, lag, rho=0.05, skew=False, tau=0.0))   # BASE
            cells.append(corner("t3", 0.20, 0.0, lag, rho=0.05, skew=False, tau=0.0))   # base at phi 0.20
        return cells, 201_000_001
    if name.startswith("fresh"):     # the worst cells on fresh seeds (the cells are passed in W7_CELLS)
        spec = json.loads(os.environ["W7_CELLS"])
        for c in spec:
            cells.append(corner(**c))
        return cells, int(os.environ.get("W7_SEED", "202000001"))
    if name == "power":
        for ic in (0.03, 0.05, 0.08):
            cells.append(mk(f"A-ic{int(ic * 100):02d}-base-n800-lag2-D57", X7(), null="A", ic=ic, nbar=800, lag=2))
        cells.append(mk("A-ic05-base-n800-lag1-D57", X7(), null="A", ic=0.05, nbar=800, lag=1))
        cells.append(mk("A-ic05-base-n300-lag2-D57", X7(), null="A", ic=0.05, nbar=300, lag=2))
        cells.append(corner("crasht3cl", 0.20, 0.0020, 2, pool=800, tau=0.0, null="A", ic=0.05))
        return cells, 203_000_001
    if name == "life":
        for lag in (1, 2):
            cells.append(corner("crasht3cl", 0.20, 0.0020, lag, T=200))
        return cells, 204_000_001
    if name == "stress":
        W = dict(drift=0.0020, tau=0.0)
        for lag in (1, 2):
            cells.append(corner("crasht3cl", 0.25, 0.0020, lag))                       # phi_day 0.25
            nm = f"N3-famdrift20-crash-skew-rho15-phi10-n300-lag{lag}-D57"
            cells.append(mk(nm, X7(), nbar=300, lag=lag, fam_drift_sd=0.0020, **(WORST | dict(tau=0.0))))
            nm = f"N3-secdrift20-crash-skew-rho15-phi20-n300-lag{lag}-D57"
            cells.append(mk(nm, X7(sec_drift=0.0020), nbar=300, lag=lag, phi_day=0.20, **(WORST | dict(tau=0.0))))
        cells.append(corner("crash", 0.10, 0.0020, 2, rho=0.30))                       # rho_day 0.30
        cells.append(corner("crash", 0.25, 0.0020, 2, rho=0.30))                       # day momentum 0.25
        cells.append(corner("crash", 0.40, 0.0020, 2, rho=0.30))                       # day momentum 0.40
        cells.append(corner("crasht3cl", 0.20, 0.0030, 2))                             # a 30 bp drift
        cells.append(mk("N4-loadcorr-fac25-crash-skew-rho15-phi20-n300-lag2-D57", X7(), nbar=300, lag=2, phi_day=0.20,
                        load_corr=0.7, fac_rho=0.25, **(WORST | dict(tau=0.0))))
        return cells, 205_000_001
    if name == "sens":         # the worst cell at D 40 / 63 and with the draft's after-replay-cost label
        spec = json.loads(os.environ["W7_CELLS"])
        for c in spec:
            cells.append(corner(**c))
        return cells, int(os.environ.get("W7_SEED", "206000001"))
    raise SystemExit(f"unknown grid {name}")


def _job(args):
    cell, x7, seed, R = args[:4]
    spec = args[4] if len(args) > 4 else SPECS.get(cell.name)   # the grid's spec (workers do not share SPECS)
    t0 = time.time()
    sim = simulate7(cell, x7, seed, R)
    res = {"cell": cell.name, "seed": seed, "R": R, "T": cell.T, "x7": dataclasses.asdict(x7),
           "cellp": dataclasses.asdict(cell), "spec": spec}
    bases = ("a7", "arep") if cell.null in ("A", "A2") else ("a7",)
    for basis in bases:
        allr = [screen(sim, i, "frozen", basis) for i in range(R)]
        cap3 = [screen(sim, i, "frozen", basis, max_runs=3) for i in range(R)] if cell.T > 120 else None
        d = dict(when=[x[0] for x in allr], run=[x[1] for x in allr], cm=[x[2] for x in allr],
                 nruns=[x[3] for x in allr], ret=[int(x[4]) for x in allr])
        if cap3 is not None:
            d["c3when"] = [x[0] for x in cap3]
            d["c3runs"] = [x[3] for x in cap3]
        res["frozen_" + basis] = d
    with np.errstate(invalid="ignore"):
        res["ev_s"] = float(sim["n"].mean())
        res["npool"] = float(sim["npool"].mean())
        res["mean_a7_picks_bp"] = float(np.nanmean(sim["a7"]) * 1e4)
        res["mean_cm7_picks_bp"] = float(np.nanmean(sim["cm7"]) * 1e4)
        res["sig_picks"] = float(np.nanmean(sim["sig"]))
        ed = sim["edge7"]
        res["edge7_bp"] = {f"{lo + 1}-{lo + 10}": round(float(np.nanmean(ed[:, lo:lo + 10])) * 1e4, 2)
                           for lo in range(0, cell.T, 10) if not np.all(np.isnan(ed[:, lo:lo + 10]))}
        er = sim["edgerep"]
        res["edgerep_bp"] = {f"{lo + 1}-{lo + 10}": round(float(np.nanmean(er[:, lo:lo + 10])) * 1e4, 2)
                             for lo in range(0, cell.T, 10) if not np.all(np.isnan(er[:, lo:lo + 10]))}
        res["c7_picks_bp"] = float(np.nanmean(sim["c7p"]) * 1e4)
        res["crep_picks_bp"] = float(np.nanmean(sim["crepp"]) * 1e4)
    res["secs"] = round(time.time() - t0, 1)
    return res


def run(gridname, reps, chunk, workers, seed=None, tag=None, resume=False):
    """`resume`: keep the jobs (cell, seed) already in the output and append only the missing ones (the same seeds a
    full run would draw: seed0 + 1000 x cell index + chunk index)."""
    from multiprocessing import Pool
    cells, seed0 = grid(gridname)
    if seed:
        seed0 = seed
    path = os.path.join(HERE, f"w7.{tag or gridname}.jsonl")
    done = set()
    if resume and os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            done.add((r["cell"], r["seed"]))
    jobs = []
    for ci, (cell, x7) in enumerate(cells):
        for j in range(max(1, reps // chunk)):
            if (cell.name, seed0 + 1000 * ci + j) not in done:
                jobs.append((cell, x7, seed0 + 1000 * ci + j, chunk, SPECS.get(cell.name)))
    t0 = time.time()
    with Pool(workers) as pool, open(path, "a" if resume else "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gridname}: {k + 1}/{len(jobs)} {res['cell']} seed {res['seed']} {res['secs']}s "
                  f"total {time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------------------------------- report
def _se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / max(n, 1))


def summarise(parts, basis="a7"):
    key = "frozen_" + basis
    R = sum(p["R"] for p in parts)
    wh = np.concatenate([p[key]["when"] for p in parts])
    rn = np.concatenate([p[key]["run"] for p in parts])
    cm = np.array([c if c is not None else np.nan for p in parts for c in p[key]["cm"]])
    nr = np.concatenate([p[key]["nruns"] for p in parts])
    rt = np.concatenate([p[key]["ret"] for p in parts])
    one = (wh >= 0) & (rn == 1)
    s = dict(R=R, run1=float(one.mean()), run1_se=_se(float(one.mean()), R),
             v120=float(((wh >= 0) & (wh < 120)).mean()), cm0=float((one & (cm <= 0)).mean()),
             cm10=float((one & (cm <= 0.0010)).mean()), runs=float(nr.mean()), retired=float(rt.mean()))
    for h in (10, 20, 22, 25, 30, 40, 60, 120):
        s[f"by{h}"] = float((one & (wh < h)).mean())
        s[f"vby{h}"] = float(((wh >= 0) & (wh < h)).mean())
    if "c3when" in parts[0][key]:
        c3 = np.concatenate([p[key]["c3when"] for p in parts])
        c3r = np.concatenate([p[key]["c3runs"] for p in parts])
        T = parts[0]["T"]
        s["life3"] = float((c3 >= 0).mean())
        s["life3_runs"] = float(c3r.mean())
        for h in (60, 120, 180, T):
            s[f"life3_by{h}"] = float(((c3 >= 0) & (c3 < h)).mean())
            s[f"any_by{h}"] = float(((wh >= 0) & (wh < h)).mean())
    p0 = parts[0]
    s["ev_s"] = float(np.mean([p["ev_s"] for p in parts]))
    s["npool"] = float(np.mean([p["npool"] for p in parts]))
    s["mean_a7_bp"] = float(np.mean([p["mean_a7_picks_bp"] for p in parts]))
    s["mean_cm7_bp"] = float(np.mean([p["mean_cm7_picks_bp"] for p in parts]))
    s["sig_picks"] = float(np.mean([p["sig_picks"] for p in parts]))
    s["edge7_bp"] = {k: round(float(np.mean([p["edge7_bp"].get(k, np.nan) for p in parts])), 1)
                     for k in p0["edge7_bp"]}
    return s


def report(only=None):
    for path in sorted(glob.glob(os.path.join(HERE, "w7.*.jsonl"))):
        if only and only not in os.path.basename(path):
            continue
        rows = [json.loads(x) for x in open(path)]
        by: dict = {}
        for r in rows:
            by.setdefault(r["cell"], []).append(r)
        print(f"== {os.path.basename(path)}")
        for name, parts in sorted(by.items()):
            for basis in ("a7", "arep"):
                if "frozen_" + basis not in parts[0]:
                    continue
                s = summarise(parts, basis)
                extra = ""
                if "life3" in s:
                    extra = (f" | LIFE (<=3 runs) {s['life3']:.4f} by60 {s['life3_by60']:.3f} by120 "
                             f"{s['life3_by120']:.3f} by180 {s['life3_by180']:.3f}; runs {s['life3_runs']:.2f}; "
                             f"uncapped by{parts[0]['T']} {s['any_by%d' % parts[0]['T']]:.3f}")
                print(f"{name:<62} {basis:<4} R={s['R']:<5} RUN1 {s['run1']:.4f} (se {s['run1_se']:.4f}) "
                      f"[cm<=0 {s['cm0']:.4f} <=10bp {s['cm10']:.4f}] by10/20/40/60 {s['by10']:.3f}/{s['by20']:.3f}/"
                      f"{s['by40']:.3f}/{s['by60']:.3f} | VERSION by120 {s['v120']:.4f} runs {s['runs']:.2f} "
                      f"retired {s['retired']:.3f} | ev/s {s['ev_s']:.2f} pool {s['npool']:.0f} a7 {s['mean_a7_bp']:.1f}bp "
                      f"cm7 {s['mean_cm7_bp']:.1f}bp sig {s['sig_picks']:.3f}{extra}")
                if any(np.isfinite(v) and v != 0 for v in s["edge7_bp"].values()):
                    print("      picks' true a7 edge (bp) " + " ".join(f"{k}:{v}" for k, v in s["edge7_bp"].items()))


def validate():
    """The screen code against check 1's: rule ev6d_w on the judge's own paths (cl.simulate, seeds 81,001,001 + j,
    chunks of 100, the F-N1-worst-n300 cell). check 1 measured run 1 = 0.1185, all runs by 120 = 0.2230 on 2,000."""
    from multiprocessing import Pool
    cell = C("R-N1-worst-n300", nbar=300, **(WORST | FINAL))
    jobs = [(cell, 81_001_001 + j, 100) for j in range(20)]
    with Pool(8) as pool:
        res = pool.map(_vjob, jobs)
    one = np.concatenate([r[0] for r in res])
    allp = np.concatenate([r[1] for r in res])
    print(f"validate: ev6d_w on the judge's paths: run 1 {one.mean():.4f}, all runs by 120 {allp.mean():.4f} "
          f"(check 1: 0.1185, 0.2230), R={one.size}")


def _vjob(args):
    cell, seed, R = args
    sim = cl.simulate(cell, seed, R)
    s7 = dict(n=sim["n"], a7=sim["a"], arep=sim["a"], c7ctl=sim["ctrl"], crepctl=sim["ctrl"],
              b=np.nan_to_num(sim["Rm"] - sim["B"]), iss=sim["iss"], cm7=np.zeros_like(sim["a"]))
    res = [screen(s7, i, "ev6d_w") for i in range(R)]
    return np.array([x[0] >= 0 and x[1] == 1 for x in res]), np.array([x[0] >= 0 for x in res])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report", "validate"))
    ap.add_argument("--grid", default="search")
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    if a.cmd == "report":
        report(a.only)
    elif a.cmd == "validate":
        validate()
    else:
        run(a.grid, a.reps, a.chunk, min(8, a.workers), a.seed, a.tag, a.resume)

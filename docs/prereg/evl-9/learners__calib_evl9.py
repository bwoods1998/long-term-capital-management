#!/usr/bin/env python
"""calib_evl9.py: SYNTHETIC calibration of PREREG-EVL-9's warm-started learners (lens: learners and protocol).

Nothing here reads the lane, the House, the gateway, events.sqlite, live.sqlite, SEC or Alpaca data. No price, return,
look, band, bar or P&L of any real event, symbol or program is read. Every number is drawn from the EVL-7 learner
lens's generator (evl7/learner/calib_learner.py, imported unchanged) plus the HISTORY PRIOR below.

WHAT IS NEW AGAINST EVL-7 (the cold learner):
  HISTORY. Before its first decision a warm learner holds the sufficient statistics of a ridge fit on N_HIST historical
  rows, re-weighted to count as N_EQ rows (the PRIOR WEIGHT):  A_prior = N_EQ x Sigma_w,  b_prior = A_prior beta_hat_h,
  with Sigma_w the within-session covariance of the features (a large draw of the generator) and beta_hat_h the history
  OLS slope, drawn from its sampling law beta_h + N(0, DE x s2 / N_HIST x Sigma_w^-1) (s2 the generator's residual
  variance of the vol-scaled label, DE = 2 a design effect for within-session clustering: conservative for power).
  The history's true slope: E_h[y|x] = ic_h x u_h, u_h = rho_h u_live + sqrt(1 - rho_h^2) u_perp (u_perp a standardised
  index on other columns, population-orthogonal to u_live): rho_h = 1 the live structure, 0 an unrelated one.
  FORWARD REFITS. Every settled session adds its within-session-demeaned A_s, b_s with forgetting 2^(-age/H) (the
  prior never decays); the fit is the EVL-7 fit on A_prior + A_fwd, b_prior + b_fwd, N_EQ + N_w (ridge lam on
  standardised columns), so with N_EQ = 0 and the warm-up it is EVL-7's cold learner exactly.
  PICKS. z_i = e_i - cost_i / sig_hat_i (the fixed level: the pool's gross abnormal mean is zero); the eligible
  candidates with z > 0 ranked by sig_hat x z; the first K. A warm learner needs no warm-up rows (its prior is its
  training set); a cold one needs 2,000 rows from 3 sessions.

NULLS (the live mean a of every candidate is exactly 0, or the knife edge):
  N1-H0  history carries nothing (ic_h = 0): the prior is noise of size ~1/sqrt(N_HIST).
  N1-HD  THE DECAYED EDGE: history carried ic_h (0.05 / 0.08) and the live stream carries none: the learner is a
         STABLE confident picker of characteristic-defined names whose mean is exactly 0.
  CHAR   a CHARACTERISTIC DRIFT on top of N1-HD: a zero-mean AR(drift_rho) drift kappa_t x (u_h - pool mean of u_h)
         added to every candidate's a (sd drift_c per unit of u_h), pool-demeaned so the control never sees it: the
         stable picker's own "family drift" (the analogue of EVL-6's stream drift for a fixed program).
  N2-H   the knife edge with history: live E[y|x] = ic min(u - u95, 0) and history the same structure.
ALTERNATIVES: A-H: live E[y|x] = -0.04 + ic u; history ic_h = ic at correlation rho_h; COLD the same without history.

SCREENS (applied to the picks' record; the control is the POOL's mean a, PREREG-EVL-7 section 6's derived control):
  ev6d  PREREG-EVL-6's draft (looks 6,7,...,16,18,20,22,25,30,35,40,50,60 blocks with >= 30 events and >= 30
        issuers; alpha 0.016 to S = 20 then 0.004; 10 bp margin; RETIRE, control, mean a > 0, mean r > 0, issuer-block
        p <= 0.10; EXHAUSTION at the 60th block), as evl7/calib/calib_evl7.py implements it (imported unchanged).
  ev6t  the EVL-6 check's tighter variant (0.014 / 0.0035, a 15 bp margin).
  ev6px PREREG-EVL-8's PX screen: ev6d with its looks beginning at the 15th block.

Usage: calib_evl9.py run --grid NAME [--reps R] [--chunk C] [--workers 4]   |   report   |   selftest
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
EVL7 = os.path.join(os.path.dirname(os.path.dirname(HERE)), "evl7")
sys.path.insert(0, os.path.join(EVL7, "learner"))
sys.path.insert(0, os.path.join(EVL7, "calib"))
import calib_learner as cl  # noqa: E402

D = cl.D
U = cl.U
HORIZON = 60
MIN_N = 30
MIN_ISS = 30
ISS_ALPHA = 0.10
EV6_LOOKS = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
PX_LOOKS = (15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
RULES = {
    "ev6d": dict(a_lo=0.016, s_sw=20, a_hi=0.004, m0=0.0010, looks=EV6_LOOKS),
    "ev6t": dict(a_lo=0.014, s_sw=20, a_hi=0.0035, m0=0.0015, looks=EV6_LOOKS),
    "ev6px": dict(a_lo=0.016, s_sw=20, a_hi=0.004, m0=0.0010, looks=PX_LOOKS),
}
DE = 2.0


@dataclasses.dataclass(frozen=True)
class WCell:
    name: str
    null: str = "N1"          # N1 | N2 | A
    ic: float = 0.0           # live information coefficient
    mu_z: float = 0.0
    hist: str = "warm"        # warm | cold
    ic_h: float = 0.0         # history information coefficient
    rho_h: float = 1.0        # corr(history index, live index)
    n_hist: float = 500_000.0
    n_eq: float = 25_000.0    # the prior weight in rows (the final design; tune grid: 25k / 100k / 400k)
    drift_c: float = 0.0      # characteristic drift sd per unit of u_h (CHAR)
    nbar: float = 600.0
    T: int = 120
    pre: int = 3
    rho_day: float = 0.05
    day: str = "t3"
    ev_skew: bool = False
    jump_left: float = 0.5
    drift_sd: float = 0.0
    drift_rho: float = 0.97
    tau: float = 0.0
    phi_day: float = 0.10
    K: int = 8
    H: float = 40.0
    lam: float = 8000.0
    lag: int = 2
    rank: str = "a"           # a: by sig_hat x z (the predicted after-cost return); z: by the vol-scaled z

    def sd_day(self) -> float:
        return math.sqrt(self.rho_day / (1.0 - self.rho_day) * cl.V0) if self.rho_day > 0 else 0.0


WORST = dict(rho_day=0.15, day="crash", ev_skew=True, drift_sd=0.0020, tau=0.01)
WORST_NT = dict(rho_day=0.15, day="crash", ev_skew=True, drift_sd=0.0020, tau=0.0)


def _cl_cell(c: WCell) -> cl.Cell:
    return cl.Cell(c.name, tau=c.tau)


# --------------------------------------------------------------------------------------------- population facts
_POP: dict = {}


def population():
    """Sigma_w (the within-session covariance of the features), the live index's normalisation, an orthogonal
    second index, and s2 (the residual variance of the vol-scaled label under N1), from one large fixed draw."""
    if _POP:
        return _POP
    rng = np.random.default_rng(20261022)
    c0 = cl.Cell("pop")
    R, N = 8, 4000
    iss = cl.issuers(rng, R, c0)
    ids = rng.integers(0, U, (R, N))
    X, _ = cl.pool_features(rng, R, N, iss, ids)
    Xd = X - X.mean(axis=1, keepdims=True)
    S = np.einsum("rnd,rne->de", Xd, Xd) / (R * N)
    # live index
    w = cl.W_TRUE.copy()
    ur = X @ w
    m, sd = float(ur.mean()), float(ur.std())
    u95 = float(np.quantile((ur - m) / sd, 0.95))
    # an unrelated index on other columns, made population-orthogonal to the live one (under Sigma_w)
    wp = np.zeros(D)
    for j, v in ((7, 0.4), (8, -0.3), (15, 0.3), (20, 0.3), (29, -0.3), (36, 0.3), (38, 0.3), (31, 0.2)):
        wp[j] = v
    proj = (wp @ S @ w) / (w @ S @ w)
    wp = wp - proj * w
    upr = X @ wp
    mp, sdp = float(upr.mean()), float(upr.std())
    # the label's residual variance (N1, base cell): simulate the noise part for these candidates
    sig = np.take_along_axis(iss["sig"], ids, axis=1)
    sig_hat = np.take_along_axis(iss["sig_hat"], ids, axis=1)
    sec = np.take_along_axis(iss["sector"], ids, axis=1)
    beta = np.take_along_axis(iss["beta"], ids[..., None], axis=1)
    s_sec = cl.unit_t3(rng, (R, 11)) * 0.010
    fac = cl.unit_t3(rng, (R, 3)) * 0.006
    e = cl.unit_t3(rng, (R, N))
    noise = np.take_along_axis(s_sec, sec, axis=1) + np.einsum("rnk,rk->rn", beta, fac) + sig * e
    y = np.clip(noise / sig_hat, -5, 5)
    yd = y - y.mean(axis=1, keepdims=True)
    s2 = float((yd ** 2).mean())
    _POP.update(S=S, w=w, m=m, sd=sd, u95=u95, wp=wp, mp=mp, sdp=sdp, s2=s2)
    return _POP


def history_beta(c: WCell, rng, R):
    """(R, D) beta_hat_h: the history OLS slope drawn from its sampling law (raw feature units)."""
    P = population()
    if c.ic_h > 0:
        bh = c.ic_h * (c.rho_h * P["w"] / P["sd"] + math.sqrt(max(0.0, 1 - c.rho_h ** 2)) * P["wp"] / P["sdp"])
    else:
        bh = np.zeros(D)
    L = np.linalg.cholesky(P["S"] + 1e-12 * np.eye(D))
    z = rng.normal(0, 1, (R, D))
    noise = np.linalg.solve(L.T, z.T).T * math.sqrt(DE * P["s2"] / c.n_hist)
    return bh[None, :] + noise, bh


# --------------------------------------------------------------------------------------------- simulation
def simulate(c: WCell, seed: int, R: int) -> dict:
    P = population()
    rng = np.random.default_rng(seed)
    T, K = c.T, c.K
    iss = cl.issuers(rng, R, _cl_cell(c))
    Nmax = int(c.nbar * 3.2) + 20
    sd_c = c.sd_day()
    zday = np.zeros(R)
    vx = rng.normal(0, 0.3, R)
    drift = rng.normal(0, c.drift_sd, R) if c.drift_sd else np.zeros(R)
    kap = rng.normal(0, c.drift_c, R) if c.drift_c else np.zeros(R)
    # prior
    warm = c.hist == "warm" and c.n_eq > 0
    if warm:
        bhat, bh_true = history_beta(c, rng, R)
        A0 = np.broadcast_to(c.n_eq * P["S"], (R, D, D)).copy()
        b0 = np.einsum("rde,re->rd", A0, bhat)
        N0 = np.full(R, c.n_eq)
    else:
        A0 = np.zeros((R, D, D))
        b0 = np.zeros((R, D))
        N0 = np.zeros(R)
        bh_true = np.zeros(D)
    # u_h direction for the characteristic drift (defined whatever the history)
    if c.ic_h > 0:
        wh = (c.rho_h * P["w"] / P["sd"] + math.sqrt(max(0.0, 1 - c.rho_h ** 2)) * P["wp"] / P["sdp"])
    else:
        wh = P["w"] / P["sd"]
    A = np.zeros((R, D, D))
    bv = np.zeros((R, D))
    Nw = np.zeros(R)
    rows = np.zeros(R)
    nsess = np.zeros(R)
    pend: list = []
    delta = 2.0 ** (-1.0 / c.H) if math.isfinite(c.H) else 1.0
    last = np.full((R, U), -10_000, dtype=np.int64)
    out_B = np.full((R, T), np.nan)
    out_Rm = np.full((R, T), np.nan)
    out_n = np.zeros((R, T), dtype=np.int16)
    out_ctrl = np.full((R, T), np.nan)
    out_iss = np.full((R, T, K), -1, dtype=np.int32)
    out_a = np.full((R, T, K), np.nan)
    curve_edge = np.full((R, T), np.nan)
    oracle_edge = np.full((R, T), np.nan)
    turnover = np.full((R, T), np.nan)
    prev_pick = [set() for _ in range(R)]
    m, sd, u95 = P["m"], P["sd"], P["u95"]
    for t in range(-c.pre, T):
        n_t = np.minimum(rng.poisson(c.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
        ids = np.take_along_axis(ids, order, axis=1)
        valid = np.arange(Nmax)[None, :] < n_t[:, None]
        X, fam = cl.pool_features(rng, R, Nmax, iss, ids)
        if c.null in ("A", "N2"):
            u = (X @ P["w"] - m) / sd
            Ey = c.ic * np.minimum(u - u95, 0.0) if c.null == "N2" else c.mu_z + c.ic * u
        else:
            Ey = np.zeros((R, Nmax))
        sig = np.take_along_axis(iss["sig"], ids, axis=1)
        sig_hat = np.take_along_axis(iss["sig_hat"], ids, axis=1)
        cost = np.take_along_axis(iss["cost"], ids, axis=1)
        sec = np.take_along_axis(iss["sector"], ids, axis=1)
        beta = np.take_along_axis(iss["beta"], ids[..., None], axis=1)
        tau = np.take_along_axis(iss["tau"], ids, axis=1)
        zday = c.phi_day * zday + math.sqrt(1 - c.phi_day ** 2) * cl.day_innov(rng, c.day, R)
        c_t = sd_c * zday
        vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
        h_t = np.exp(vx - 0.09)
        s_sec = cl.unit_t3(rng, (R, 11)) * 0.010
        fac = cl.unit_t3(rng, (R, 3)) * 0.006
        if c.drift_sd:
            drift = c.drift_rho * drift + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.drift_sd, R)
        if c.drift_c:
            kap = c.drift_rho * kap + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.drift_c, R)
        b_t = rng.normal(0.0004, 0.010, R)
        e = cl.unit_t3(rng, (R, Nmax), 1.4, 0.6) if c.ev_skew else cl.unit_t3(rng, (R, Nmax))
        jl = 0.8 if c.ev_skew else c.jump_left
        jump = np.where(rng.random((R, Nmax)) < 0.005, np.where(rng.random((R, Nmax)) < jl, -0.30, 0.30), 0.0)
        jump = jump - 0.005 * 0.30 * (1 - 2 * jl)
        noise = h_t[:, None] * (c_t[:, None] + np.take_along_axis(s_sec, sec, axis=1)
                                + np.einsum("rnk,rk->rn", beta, fac) + sig * e)
        vf = valid.astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        chard = 0.0
        if c.drift_c:
            uh = X @ wh
            uh = uh - (uh * vf).sum(axis=1, keepdims=True) / nv[:, None]
            chard = kap[:, None] * uh
        a = sig * Ey + drift[:, None] + chard + noise + jump + tau
        a = np.maximum(a, -1.0)
        r = a + b_t[:, None]
        y = np.clip(a / sig_hat, -5, 5)
        while pend and pend[0][0] <= t - c.lag:
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
            if warm:
                ready = np.ones(R, dtype=bool)
            else:
                ready = (rows >= 2000) & (nsess >= 3)
            At = A0 + A
            bt = b0 + bv
            Nt = np.maximum(N0 + Nw, 1.0)
            dsd = np.sqrt(np.maximum(np.einsum("rii->ri", At) / Nt[:, None], 1e-12))
            As_ = At / (dsd[:, :, None] * dsd[:, None, :]) + c.lam * np.eye(D)[None]
            bs_ = bt / dsd
            beta_s = np.linalg.solve(As_, bs_[..., None])[..., 0]
            bhat_t = beta_s / dsd
            ehat = np.einsum("rnd,rd->rn", Xc, bhat_t)
            zhat = ehat - cost / sig_hat
            key = zhat * sig_hat if c.rank == "a" else zhat
            score = np.where(elig & ready[:, None] & (zhat > 0), key, -np.inf)
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
            if c.null != "N1":
                ztrue = np.where(elig, Ey, -np.inf)
                otop = np.argsort(-ztrue, axis=1)[:, :K]
                oz = np.take_along_axis(ztrue, otop, axis=1)
                ook = oz > 0
                ov = np.where(ook, np.take_along_axis(sEa, otop, axis=1), np.nan)
                with np.errstate(invalid="ignore"):
                    oracle_edge[ook.any(axis=1), t] = np.nanmean(ov[ook.any(axis=1)], axis=1)
        ybar = (y * vf).sum(axis=1) / nv
        Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
        yd = (y - ybar[:, None]) * vf
        As = np.matmul(Xd.transpose(0, 2, 1), Xd)
        bs = np.einsum("rnd,rn->rd", Xd, yd)
        pend.append((t, As, bs, vf.sum(axis=1)))
    return dict(B=out_B, Rm=out_Rm, n=out_n, ctrl=out_ctrl, iss=out_iss, a=out_a, curve_edge=curve_edge,
                oracle_edge=oracle_edge)


# --------------------------------------------------------------------------------------------- the screens
def screen(sim, rep, rule, start=0):
    """(passed, session of pass or -1, ended 'retire' | 'exhaust' | None, session it ended or -1)."""
    P = RULES[rule]
    looks = P["looks"]
    B, Rm, n, ctrl = sim["B"][rep], sim["Rm"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av = sim["iss"][rep], sim["a"][rep]
    T = len(B)
    blocks, bsess, ev_iss, ev_a = [], [], [], []
    ev_r_sum = 0.0
    seen: set = set()
    k = 0
    for t in range(start, T):
        kk = int(n[t])
        if kk == 0:
            continue
        a_t = av[t, :kk].astype(float)
        blocks.append(float(a_t.mean()))
        bsess.append(t)
        ev_iss.extend(int(x) for x in iss[t, :kk])
        ev_a.extend(float(x) for x in a_t)
        ev_r_sum += float(Rm[t]) * kk
        seen.update(int(x) for x in iss[t, :kk])
        S = len(blocks)
        N = len(ev_a)
        look = False
        if k < len(looks) and S >= looks[k] and N >= MIN_N and len(seen) >= MIN_ISS:
            look = True
            while k < len(looks) and S >= looks[k]:
                k += 1
        if look:
            alpha = P["a_lo"] if S <= P["s_sw"] else P["a_hi"]
            xb = np.array(blocks)
            mean_a = sum(ev_a) / N
            if mean_a < 0 and cl.zstat(-xb) >= cl.Z_PRE and cl.flip_p(-xb) <= alpha + cl.TIE:
                return False, -1, "retire", t
            x = xb - P["m0"]
            if cl.zstat(x) >= cl.Z_PRE and cl.flip_p(x) <= alpha + cl.TIE and mean_a > 0 and ev_r_sum / N > 0:
                cm = float(np.mean(ctrl[bsess]))
                if xb.mean() > cm and cl.issuer_p(ev_iss, ev_a, cl.B_ISS6) <= ISS_ALPHA + cl.TIE:
                    return True, t, None, t
        if S >= HORIZON:
            return False, -1, "exhaust", t
    return False, -1, None, -1


def chain(sim, rep, rule, versions=3):
    start = 0
    for v in range(1, versions + 1):
        ok, when, ended, end = screen(sim, rep, rule, start)
        if ok:
            return True, when, v
        if ended is None or end + 1 >= len(sim["B"][rep]):
            return False, -1, v
        start = end + 1
    return False, -1, versions


# --------------------------------------------------------------------------------------------- grids
def grid(name):
    C = WCell
    W, WN = WORST, WORST_NT
    if name in ("null", "null2", "char", "life"):
        C = lambda *a, **k: WCell(*a, **({"nbar": 300.0} | k))  # noqa: E731
    if name == "null":
        cells = [
            C("N1-HD08-worst", ic_h=0.08, **W),
            C("N1-H0-worst", ic_h=0.0, **W),
            C("N1-cold-worst", hist="cold", **W),
            C("N2-H08-worst", null="N2", ic=0.08, ic_h=0.08, **W),
            C("N1-HD05-worst", ic_h=0.05, **W),
            C("N1-HD08-worst-notau", ic_h=0.08, **WN),
        ]
        return cells, 91_000_001
    if name == "null2":
        cells = [
            C("N1-H0-base", ic_h=0.0),
            C("N1-HD08-base", ic_h=0.08),
            C("N1-HD08-worst-neq100k", ic_h=0.08, n_eq=100_000.0, **W),
            C("N2-H05-worst", null="N2", ic=0.05, ic_h=0.05, **W),
        ]
        return cells, 98_000_001
    if name == "char":
        cells = [
            C("CHAR10-HD08-worst", ic_h=0.08, drift_c=0.0010, **W),
            C("CHAR10-cold-worst", hist="cold", drift_c=0.0010, **W),
            C("CHAR05-HD08-worst", ic_h=0.08, drift_c=0.0005, **W),
            C("CHAR20-HD08-worst", ic_h=0.08, drift_c=0.0020, **W),
            C("CHAR10-H0-worst", ic_h=0.0, drift_c=0.0010, **W),
        ]
        return cells, 92_000_001
    if name == "life":
        cells = [C("N1-HD08-worst-notau-T300", ic_h=0.08, T=300, **WN),
                 C("CHAR10-HD08-worst-notau-T300", ic_h=0.08, drift_c=0.0010, T=300, **WN)]
        return cells, 93_000_001
    if name in ("power", "powerw"):
        C = lambda *a, **k: WCell(*a, **({"T": 60} | k))  # noqa: E731
    if name == "power":
        cells = []
        for ic in (0.03, 0.05, 0.08):
            tag = f"ic{int(ic * 100):02d}"
            cells.append(C(f"A-{tag}-cold", null="A", ic=ic, mu_z=-0.04, hist="cold"))
            cells.append(C(f"A-{tag}-warm-rho10", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=1.0))
            cells.append(C(f"A-{tag}-warm-rho07", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=0.7))
            cells.append(C(f"A-{tag}-warm-rho00", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=0.0))
            cells.append(C(f"A-{tag}-warm-H0", null="A", ic=ic, mu_z=-0.04, ic_h=0.0))
        return cells, 94_000_001
    if name == "tune":
        cells = []
        for ic in (0.05,):
            tag = f"ic{int(ic * 100):02d}"
            for rho in (1.0, 0.7, 0.0):
                for neq in (25_000.0, 100_000.0, 400_000.0):
                    cells.append(C(f"A-{tag}-rho{int(rho * 10):02d}-neq{int(neq / 1000)}k", null="A", ic=ic,
                                   mu_z=-0.04, ic_h=ic, rho_h=rho, n_eq=neq))
            for K in (14,):
                cells.append(C(f"A-{tag}-rho10-neq100k-K{K}", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=1.0, K=K))
                cells.append(C(f"A-{tag}-rho07-neq100k-K{K}", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=0.7, K=K))
            cells.append(C(f"A-{tag}-rho10-neq100k-H120", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=1.0, H=120.0))
            cells.append(C(f"A-{tag}-rho00-neq100k-H120", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=0.0, H=120.0))
            cells.append(C(f"A-{tag}-cold", null="A", ic=ic, mu_z=-0.04, hist="cold"))
        return cells, 95_000_001
    if name == "powerw":
        cells = []
        for ic in (0.05, 0.08):
            tag = f"ic{int(ic * 100):02d}"
            cells.append(C(f"A-{tag}-cold-worst", null="A", ic=ic, mu_z=-0.04, hist="cold", **WN))
            cells.append(C(f"A-{tag}-warm-rho10-worst", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=1.0, **WN))
            cells.append(C(f"A-{tag}-warm-rho07-worst", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=0.7, **WN))
        return cells, 96_000_001
    if name == "phi":
        C = lambda *a, **k: WCell(*a, **({"nbar": 300.0} | k))  # noqa: E731
        cells = [C("N1-HD08-worst-notau-phi20", ic_h=0.08, **(WN | dict(phi_day=0.20))),
                 C("N1-cold-worst-notau-phi20", hist="cold", **(WN | dict(phi_day=0.20))),
                 C("CHAR10-HD08-worst-notau-phi20", ic_h=0.08, drift_c=0.0010, **(WN | dict(phi_day=0.20)))]
        return cells, 99_000_001
    if name == "tune2":
        cells = [C("A-ic05-rho10-rankz", null="A", ic=0.05, mu_z=-0.04, ic_h=0.05, rho_h=1.0, rank="z", T=60),
                 C("A-ic05-rho07-rankz", null="A", ic=0.05, mu_z=-0.04, ic_h=0.05, rho_h=0.7, rank="z", T=60),
                 C("A-ic05-rho10-nhist150k", null="A", ic=0.05, mu_z=-0.04, ic_h=0.05, rho_h=1.0, n_hist=150_000.0, T=60)]
        return cells, 97_000_001
    if name == "smoke":
        return [C("smoke-N1-HD08", ic_h=0.08, T=40, nbar=300), C("smoke-A-warm", null="A", ic=0.05, mu_z=-0.04,
                                                                  ic_h=0.05, T=40, nbar=300)], 90_000_001
    raise SystemExit(f"unknown grid {name}")


def _job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = simulate(cell, seed, R)
    out = {"cell": cell.name, "params": dataclasses.asdict(cell), "seed": seed, "R": R, "T": cell.T}
    for rule in RULES:
        one = [screen(sim, i, rule) for i in range(R)]
        ch = [chain(sim, i, rule) for i in range(R)]
        out[rule] = dict(pass_=[int(x[0]) for x in one], when=[int(x[1]) for x in one],
                         ended=[x[2] or "" for x in one], cpass=[int(x[0]) for x in ch],
                         cwhen=[int(x[1]) for x in ch], cver=[int(x[2]) for x in ch])
    if os.environ.get("EVL9_EVL3", "1") == "1":
        one = [cl.screen_one(sim, i, "EVL3") for i in range(R)]
        out["evl3"] = dict(pass_=[int(x[0]) for x in one], when=[int(x[1]) for x in one])
    with np.errstate(invalid="ignore"):
        out["mean_a_picks_bp"] = float(np.nanmean(sim["a"]) * 1e4)
        out["events_per_session"] = float(sim["n"].mean())
        out["sessions_with_picks"] = float((sim["n"] > 0).mean())
        for key in ("curve_edge", "oracle_edge"):
            arr = sim[key]
            if np.all(np.isnan(arr)):
                continue
            out[key + "_bp"] = {f"{lo + 1}-{lo + 10}": round(float(np.nanmean(arr[:, lo:lo + 10])) * 1e4, 2)
                                for lo in range(0, cell.T, 10) if not np.all(np.isnan(arr[:, lo:lo + 10]))}
    out["secs"] = round(time.time() - t0, 1)
    return out


def run(gridname, reps, chunk, workers):
    from multiprocessing import Pool
    cells, seed0 = grid(gridname)
    jobs = []
    for ci, cell in enumerate(cells):
        for j in range(max(1, reps // chunk)):
            jobs.append((cell, seed0 + 1000 * ci + j, chunk))
    path = os.path.join(HERE, f"calib_evl9.{gridname}.jsonl")
    population()
    t0 = time.time()
    with Pool(workers) as pool, open(path, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gridname}: {k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s",
                  flush=True)


# --------------------------------------------------------------------------------------------- report
def _se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / max(n, 1))


def report():
    for path in sorted(glob.glob(os.path.join(HERE, "calib_evl9.*.jsonl"))):
        g = os.path.basename(path).split(".")[1]
        by: dict = {}
        for line in open(path):
            d = json.loads(line)
            by.setdefault(d["cell"], []).append(d)
        print(f"=== grid {g} ({path})")
        for cell, parts in by.items():
            R = sum(p["R"] for p in parts)
            T = parts[0]["T"]
            line = [f"{cell:34s} R={R:5d}"]
            for rule in RULES:
                ps = np.concatenate([p[rule]["pass_"] for p in parts])
                wh = np.concatenate([p[rule]["when"] for p in parts])
                cps = np.concatenate([p[rule]["cpass"] for p in parts])
                cwh = np.concatenate([p[rule]["cwhen"] for p in parts])
                f = ps.mean()
                b40 = ((ps == 1) & (wh < 40)).mean()
                b60 = ((ps == 1) & (wh < 60)).mean()
                c3 = cps.mean()
                line.append(f"{rule}: {f:.4f}({_se(f, R):.4f}) by40 {b40:.3f} by60 {b60:.3f} x3 {c3:.4f}")
            if all("evl3" in p for p in parts):
                ps = np.concatenate([p["evl3"]["pass_"] for p in parts])
                wh = np.concatenate([p["evl3"]["when"] for p in parts])
                line.append(f"evl3: {ps.mean():.4f}({_se(ps.mean(), R):.4f}) by40 {((ps == 1) & (wh < 40)).mean():.3f}")
            ev = np.mean([p["events_per_session"] for p in parts])
            ma = np.mean([p["mean_a_picks_bp"] for p in parts])
            line.append(f"ev/s {ev:.2f} mean_a {ma:+.1f}bp")
            ce = parts[0].get("curve_edge_bp")
            if ce:
                keys = list(ce.keys())
                vals = {k: np.mean([p["curve_edge_bp"][k] for p in parts if k in p.get("curve_edge_bp", {})])
                        for k in keys}
                pick = [k for k in keys if k in ("1-10", "31-40", "51-60", "111-120", "291-300")]
                line.append("edge " + " ".join(f"{k}:{vals[k]:+.1f}" for k in pick))
            oe = parts[0].get("oracle_edge_bp")
            if oe:
                line.append(f"oracle1-10 {np.mean([p['oracle_edge_bp'].get('1-10', np.nan) for p in parts]):+.1f}")
            print(" | ".join(line))


def selftest():
    P = population()
    print("s2", round(P["s2"], 3), "sd", round(P["sd"], 3), "u95", round(P["u95"], 3))
    w, wp, S = P["w"], P["wp"], P["S"]
    print("corr(u, u_perp) =", float((wp @ S @ w) / math.sqrt((w @ S @ w) * (wp @ S @ wp))))
    c = WCell("t", ic_h=0.08, T=30, nbar=300)
    sim = simulate(c, 1, 8)
    print("ev/s", float(sim["n"].mean()), "mean a bp", float(np.nanmean(sim["a"]) * 1e4))
    c = WCell("t", null="A", ic=0.05, mu_z=-0.04, ic_h=0.05, T=30, nbar=300)
    sim = simulate(c, 2, 8)
    print("A warm: ev/s", float(sim["n"].mean()), "edge bp", float(np.nanmean(sim["curve_edge"]) * 1e4))
    c = WCell("t", null="A", ic=0.05, mu_z=-0.04, hist="cold", T=30, nbar=300)
    sim = simulate(c, 2, 8)
    print("A cold: ev/s", float(sim["n"].mean()), "edge bp", float(np.nanmean(sim["curve_edge"]) * 1e4))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--grid", required=True)
    r.add_argument("--reps", type=int, default=1000)
    r.add_argument("--chunk", type=int, default=50)
    r.add_argument("--workers", type=int, default=4)
    sub.add_parser("report")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.grid, a.reps, a.chunk, min(a.workers, 4))
    elif a.cmd == "report":
        report()
    else:
        selftest()


if __name__ == "__main__":
    main()

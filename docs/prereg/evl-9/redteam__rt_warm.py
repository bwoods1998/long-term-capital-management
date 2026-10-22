#!/usr/bin/env python
"""rt_warm.py: the LEAKAGE AND SURVIVORSHIP RED TEAM's synthetic calibration of a WARM-STARTED learner (A106).

SYNTHETIC ONLY. Nothing here reads the lane, the House, the gateway, events.sqlite, live.sqlite or any market data:
no price, no return, no look, no band. Every number comes from the generator below, chosen blind.

QUESTION: can years of history make PREREG-EVL-6's forward screen pass a learner with no forward edge more often
than it passes a fixed program or PREREG-EVL-7's forward-only learner? The claim to prove or break: "the judge is
forward-only, so history cannot change the false-pass rate; it only changes how good the learner is".

THE LEARNER (PREREG-EVL-7's: session-demeaned weighted ridge on standardised columns, lambda 8,000, label
y = clip(a / sigma_hat, -5, 5), fixed level -cost / sigma_hat, ranked by sigma_hat x z, the top K = 8 with z > 0, an
issuer not picked in the last 5 sessions, a 2-session settlement lag), WARM-STARTED: it first accumulates H_hist
sessions of history (training rows only, no record), then decides T forward sessions, refitting forward-only on rows
settled before each decision. The forward record is screened by PREREG-EVL-6's draft screen (calib_evl7.screen_ev6,
imported unchanged: looks at S = 6 .. 60 blocks, alpha 0.016 / 0.004, a 10 bp margin, mean a > 0, mean r > 0, beats its
pool control, issuer-block p <= 0.10, RETIRE, EXHAUSTION at 60 blocks).

THE GENERATOR (lean re-implementation of evl7/learner/calib_learner.py's, plus a MARKET with issuer betas, persistent
SECTOR drifts and a history/forward split): 3,000 issuers, 11 sectors, Zipf(0.8) repeats, sigma log-uniform 1-10%, a
vol regime, t(3) noise, +-30% jumps; beta_i = clip(1 + 0.35 z_sigma + 0.25 N, 0.3, 2.2) (volatile names are high
beta); the benchmark is the market m_t ~ mu_m + 1% t3, so a = (beta_i - 1) m_t + ...; r = a + m_t.
Features (D = 23): 0-3 family dummies, 4-11 binaries, 12 ln_sig (issuer), 13 ln_adv (issuer), 14-17 SIC-group
dummies (sectors 0-3), 18 r1, 19 r5, 20 n_art, 21 TE (an issuer TARGET ENCODING: the shrunk mean of the issuer's
settled labels, used only where a cell says), 22 LEAK (a look-ahead column: 0.3 x the label + N(0, 1) in HISTORY
rows only, pure noise forward; used only where a cell says).

CELLS (each answers one red-team question; see grid()):
  REF-RANDOM  a random picker (the fixed-program reference)
  REF-FWD     PREREG-EVL-7's forward-only learner (3 pre-registration sessions)
  W-NOISE     warm, history carries nothing
  W-DECAY     warm, history carries a real edge (ic 0.05) that is GONE at registration (McLean-Pontiff decay)
  W-LEAK      warm, history has a look-ahead column (restated or post-decision field)
  W-TE        warm, an issuer target-encoding feature, no overlap
  BRK-OVL     THE BREAK: the training snapshot includes the first k forward sessions' outcomes, and those sessions
              are decided (backfilled) with the model fitted on them; generic features only, and with TE
  BETA-*      history bull market (mu_m 4 bp); forward mu_m 0 / 4 / 10 bp; plain label vs the beta-hedged label
  SEL-*       THE HONESTY BREAK: 6 candidate procedures (half-lives 20, 40, 120, 500, flat; flat without sector
              columns); 'blind' = the pre-registered one (half-life 500); 'best' = the one with the best walk-forward
              record over the last 60 history sessions (what a person who peeks would pick); under N1 with no
              nuisance, with persistent sector drift (AR 0.97, sd 15 bp), and with a beta premium.
  FLIP        regime break: history edge ic 0.05 on W, forward ic 0.05 on -W: the price of a learner that history
              taught the wrong sign (how much it trades, at what true edge, before RETIRE or EXHAUSTION).

Usage: rt_warm.py run --grid G [--reps R] [--chunk C] [--workers 4] | report
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
import calib_evl7 as ce  # noqa: E402

U = 3000
NSEC = 11
SECTOR_W = cl.SECTOR_W
D = 23
GENERIC = list(range(0, 21))
FAM_P = np.array([.40, .20, .15, .15, .10])
BIN_P = np.array([.05, .08, .10, .15, .20, .25, .30, .40])
W_TRUE = np.zeros(D)
W_TRUE[[0, 4, 5, 12, 13, 18, 20]] = [0.3, 0.4, 0.3, 0.2, -0.2, -0.3, 0.2]
W_FLIP = -W_TRUE
INF = float("inf")
V0 = cl.V0


@dataclasses.dataclass(frozen=True)
class Cell:
    name: str
    H_hist: int = 500
    T: int = 120
    nbar: float = 300.0
    h_ic: float = 0.0
    h_mu: float = 0.0
    f_ic: float = 0.0
    f_mu: float = 0.0
    f_flip: bool = False
    mu_m_h: float = 0.0
    mu_m_f: float = 0.0
    rho_day: float = 0.05
    phi_day: float = 0.10
    day: str = "t3"
    ev_skew: bool = False
    drift_sd: float = 0.0
    drift_rho: float = 0.97
    sec_drift_sd: float = 0.0
    sec_drift_rho: float = 0.97
    tau: float = 0.0
    leak: float = 0.0
    te: bool = False
    overlap: int = 0
    hedge: bool = False
    cands: tuple = ((500.0, "all"),)
    select: str = "blind"
    learn: bool = True
    K: int = 8
    lam: float = 8000.0
    lag: int = 2
    warm_rows: int = 2000
    warm_sessions: int = 3
    sel_window: int = 60

    def sd_day(self) -> float:
        return math.sqrt(self.rho_day / (1.0 - self.rho_day) * V0) if self.rho_day > 0 else 0.0


def masks(cell: Cell):
    out = []
    for _, m in cell.cands:
        keep = np.zeros(D, bool)
        keep[GENERIC] = True
        if m == "nosec":
            keep[14:18] = False
        if m == "noiss":
            keep[12:18] = False
        keep[21] = cell.te
        keep[22] = cell.leak > 0
        out.append(keep)
    return np.array(out)


def issuers(rng, R, cell):
    ranks = np.argsort(rng.random((R, U)), axis=1) + 1
    logp = -0.8 * np.log(ranks.astype(float))
    sector = rng.choice(NSEC, size=(R, U), p=SECTOR_W)
    lsig = rng.uniform(math.log(0.01), math.log(0.10), (R, U))
    sig = np.exp(lsig)
    zs = (lsig - lsig.mean()) / lsig.std()
    beta_m = np.clip(1.0 + 0.35 * zs + 0.25 * rng.normal(0, 1, (R, U)), 0.3, 2.2)
    beta_hat = beta_m + 0.25 * rng.normal(0, 1, (R, U))          # a pre-decision 60-session estimate
    beta_hat = 0.5 * beta_hat + 0.5                                # shrunk half-way to 1
    fload = rng.normal(0, 0.5, (R, U, 3)) + np.array([0.2, -0.1, 0.2])
    tau = rng.normal(0, cell.tau, (R, U)) if cell.tau > 0 else np.zeros((R, U))
    lnadv = -0.6 * zs + 0.8 * rng.normal(0, 1, (R, U))
    lnsig_f = zs + 0.3 * rng.normal(0, 1, (R, U))
    sig_hat = sig * np.exp(0.15 * rng.normal(0, 1, (R, U)))
    cost = np.where(lnadv > -0.3, 0.0011, 0.0021)
    return dict(logp=logp, sector=sector, sig=sig, sig_hat=sig_hat, beta_m=beta_m, beta_hat=beta_hat, fload=fload,
                tau=tau, lnadv=lnadv, lnsig_f=lnsig_f, cost=cost)


def take(arr, ids):
    return np.take_along_axis(arr, ids, axis=1)


class World:
    """One chunk of R replicates: draws sessions in order."""

    def __init__(self, cell: Cell, seed: int, R: int):
        self.c = cell
        self.R = R
        self.rng = np.random.default_rng(seed)
        self.iss = issuers(self.rng, R, cell)
        self.Nmax = int(cell.nbar * 3.2) + 20
        self.zday = np.zeros(R)
        self.vx = self.rng.normal(0, 0.3, R)
        self.sdrift = self.rng.normal(0, cell.sec_drift_sd, (R, NSEC)) if cell.sec_drift_sd else np.zeros((R, NSEC))
        self.drift = self.rng.normal(0, cell.drift_sd, R) if cell.drift_sd else np.zeros(R)
        self.te_sum = np.zeros((R, U))
        self.te_n = np.zeros((R, U))

    def session(self, t: int) -> dict:
        c, R, rng, iss, Nmax = self.c, self.R, self.rng, self.iss, self.Nmax
        hist = t < 0
        n_t = np.minimum(rng.poisson(c.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-take(keys, ids), axis=1)
        ids = take(ids, order)
        valid = np.arange(Nmax)[None, :] < n_t[:, None]
        X = np.zeros((R, Nmax, D))
        fam = rng.choice(5, size=(R, Nmax), p=FAM_P)
        for f in range(1, 5):
            X[..., f - 1] = (fam == f)
        X[..., 4:12] = rng.random((R, Nmax, 8)) < BIN_P
        X[..., 12] = take(iss["lnsig_f"], ids)
        X[..., 13] = take(iss["lnadv"], ids)
        sec = take(iss["sector"], ids)
        for gg in range(4):
            X[..., 14 + gg] = (sec == gg)
        X[..., 18] = np.clip(cl.unit_t3(rng, (R, Nmax)), -5, 5)
        X[..., 19] = np.clip(cl.unit_t3(rng, (R, Nmax)), -5, 5)
        X[..., 20] = np.log1p(rng.poisson(1.5, (R, Nmax)))
        X[..., 21] = take(self.te_sum, ids) / (take(self.te_n, ids) + 10.0)
        ic, mu = (c.h_ic, c.h_mu) if hist else (c.f_ic, c.f_mu)
        w = W_FLIP if (not hist and c.f_flip) else W_TRUE
        if ic != 0.0 or mu != 0.0:
            s = X @ w
            vf = valid.astype(float)
            nv = np.maximum(vf.sum(axis=1), 1)
            m = (s * vf).sum(axis=1) / nv
            sd = np.sqrt(np.maximum(((s - m[:, None]) ** 2 * vf).sum(axis=1) / nv, 1e-12))
            u = (s - m[:, None]) / sd[:, None]
            Ey = mu + ic * u
        else:
            Ey = np.zeros((R, Nmax))
        sig = take(iss["sig"], ids)
        sig_hat = take(iss["sig_hat"], ids)
        cost = take(iss["cost"], ids)
        beta_m = take(iss["beta_m"], ids)
        beta_hat = take(iss["beta_hat"], ids)
        fload = np.take_along_axis(iss["fload"], ids[..., None], axis=1)
        tau = take(iss["tau"], ids)
        self.zday = c.phi_day * self.zday + math.sqrt(1 - c.phi_day ** 2) * cl.day_innov(rng, c.day, R)
        c_t = c.sd_day() * self.zday
        self.vx = 0.9 * self.vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
        h_t = np.exp(self.vx - 0.09)
        s_sec = cl.unit_t3(rng, (R, NSEC)) * 0.010
        fac = cl.unit_t3(rng, (R, 3)) * 0.006
        if c.sec_drift_sd:
            self.sdrift = c.sec_drift_rho * self.sdrift + math.sqrt(1 - c.sec_drift_rho ** 2) * rng.normal(
                0, c.sec_drift_sd, (R, NSEC))
        mu_m = c.mu_m_h if hist else c.mu_m_f
        m_t = mu_m + 0.010 * cl.unit_t3(rng, R)
        if c.drift_sd:
            self.drift = c.drift_rho * self.drift + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.drift_sd, R)
        e = cl.unit_t3(rng, (R, Nmax), 1.4, 0.6) if c.ev_skew else cl.unit_t3(rng, (R, Nmax))
        jl = 0.8 if c.ev_skew else 0.5
        jump = np.where(rng.random((R, Nmax)) < 0.005, np.where(rng.random((R, Nmax)) < jl, -0.30, 0.30), 0.0)
        jump = jump - 0.005 * 0.30 * (1 - 2 * jl)
        noise = h_t[:, None] * (c_t[:, None] + take(s_sec, sec) + np.einsum("rnk,rk->rn", fload, fac) + sig * e)
        a = (sig * Ey + (beta_m - 1.0) * m_t[:, None] + take(self.sdrift, sec) + self.drift[:, None] + noise + jump
             + tau)
        a = np.maximum(a, -1.0)
        r = a + m_t[:, None]
        lab = a - (beta_hat - 1.0) * m_t[:, None] if c.hedge else a
        y = np.clip(lab / sig_hat, -5, 5)
        if c.leak > 0:
            X[..., 22] = (c.leak * y if hist else 0.0) + rng.normal(0, 1, (R, Nmax))
        return dict(ids=ids, valid=valid, X=X, a=a, r=r, y=y, sig=sig, sig_hat=sig_hat, cost=cost, Ey=Ey,
                    beta_m=beta_m)

    def settle_te(self, S: dict):
        if not self.c.te:
            return
        vf = S["valid"]
        rr, nn = np.nonzero(vf)
        np.add.at(self.te_sum, (rr, S["ids"][rr, nn]), S["y"][rr, nn])
        np.add.at(self.te_n, (rr, S["ids"][rr, nn]), 1.0)


def session_stats(S: dict):
    X, y, vf = S["X"], S["y"], S["valid"].astype(float)
    nv = np.maximum(vf.sum(axis=1), 1)
    Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
    yd = (y - ((y * vf).sum(axis=1) / nv)[:, None]) * vf
    return np.matmul(Xd.transpose(0, 2, 1), Xd), np.einsum("rnd,rn->rd", Xd, yd), vf.sum(axis=1)


class Learners:
    """M candidate procedures, each its own forgetting, mask, and pick history."""

    def __init__(self, cell: Cell, R: int):
        self.c = cell
        self.M = len(cell.cands)
        self.R = R
        self.A = np.zeros((self.M, R, D, D))
        self.b = np.zeros((self.M, R, D))
        self.Nw = np.zeros((self.M, R))
        self.rows = np.zeros(R)
        self.nsess = np.zeros(R)
        self.delta = np.array([2.0 ** (-1.0 / h) if math.isfinite(h) else 1.0 for h, _ in cell.cands])
        self.mask = masks(cell)
        self.last = np.full((self.M, R, U), -10_000, dtype=np.int64)

    def add(self, As, bs, ns):
        for m in range(self.M):
            self.A[m] = self.delta[m] * self.A[m] + As
            self.b[m] = self.delta[m] * self.b[m] + bs
            self.Nw[m] = self.delta[m] * self.Nw[m] + ns
        self.rows += ns
        self.nsess += (ns > 0)

    def decide(self, S: dict, t: int, rng):
        """(M, R, K) pick indices into the pool (-1 = none)."""
        c, R, K = self.c, self.R, self.c.K
        vf = S["valid"].astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        xbar = (S["X"] * vf[..., None]).sum(axis=1) / nv[:, None]
        Xc = S["X"] - xbar[:, None, :]
        ready = (self.rows >= c.warm_rows) & (self.nsess >= c.warm_sessions)
        out = np.full((self.M, R, K), -1, dtype=np.int64)
        for m in range(self.M):
            elig = S["valid"] & (take(self.last[m], S["ids"]) < t - 5)
            if c.learn:
                keep = self.mask[m]
                A = self.A[m] * (keep[:, None] & keep[None, :])[None]
                bb = self.b[m] * keep[None]
                diag = np.einsum("rii->ri", A)
                dsd = np.where(diag > 1e-12, np.sqrt(np.maximum(diag, 1e-300) / np.maximum(self.Nw[m], 1)[:, None]), 1.0)
                As_ = A / (dsd[:, :, None] * dsd[:, None, :]) + c.lam * np.eye(D)[None]
                beta_s = np.linalg.solve(As_, (bb / dsd)[..., None])[..., 0]
                bhat = beta_s / dsd
                ehat = np.einsum("rnd,rd->rn", Xc, bhat)
                z = -S["cost"] / S["sig_hat"] + ehat
                score = np.where(elig & ready[:, None] & (z > 0), z * S["sig_hat"], -np.inf)
            else:
                score = np.where(elig & ready[:, None], rng.random(elig.shape), -np.inf)
            top = np.argsort(-score, axis=1)[:, :K]
            ok = take(score, top) > -np.inf
            out[m] = np.where(ok, top, -1)
            rr, kk = np.nonzero(ok)
            self.last[m, rr, S["ids"][rr, top[rr, kk]]] = t
        return out


def record(S: dict, picks: np.ndarray, K: int):
    """Per replicate: block value, mean r, n, pool control, issuers, a, true edge, beta excess."""
    ok = picks >= 0
    pk = np.where(ok, picks, 0)
    pa = np.where(ok, take(S["a"], pk), np.nan)
    pr = np.where(ok, take(S["r"], pk), np.nan)
    pid = np.where(ok, take(S["ids"], pk), -1)
    pe = np.where(ok, take(S["sig"] * S["Ey"], pk), np.nan)
    pb = np.where(ok, take(S["beta_m"], pk), np.nan)
    vf = S["valid"].astype(float)
    nv = np.maximum(vf.sum(axis=1), 1)
    ctrl = (S["a"] * vf).sum(axis=1) / nv
    pool_beta = (S["beta_m"] * vf).sum(axis=1) / nv
    n = ok.sum(axis=1)
    import warnings
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        B = np.where(n > 0, np.nanmean(np.where(ok, pa, np.nan), axis=1), np.nan)
        Rm = np.where(n > 0, np.nanmean(np.where(ok, pr, np.nan), axis=1), np.nan)
        E = np.where(n > 0, np.nanmean(np.where(ok, pe, np.nan), axis=1), np.nan)
        BX = np.where(n > 0, np.nanmean(np.where(ok, pb, np.nan), axis=1) - pool_beta, np.nan)
    return B, Rm, n, ctrl, pid, pa, E, BX


def simulate(cell: Cell, seed: int, R: int) -> dict:
    W = World(cell, seed, R)
    L = Learners(cell, R)
    rng = W.rng
    T, K, M = cell.T, cell.K, L.M
    pend: list = []
    out = {k: np.full((M, R, T), np.nan) for k in ("B", "Rm", "ctrl", "E", "BX")}
    out["n"] = np.zeros((M, R, T), dtype=np.int16)
    out["iss"] = np.full((M, R, T, K), -1, dtype=np.int32)
    out["a"] = np.full((M, R, T, K), np.nan)
    wf = np.zeros((M, R))
    wf_n = np.zeros((M, R))

    def settle_upto(t_cut):
        while pend and pend[0][0] <= t_cut:
            _, As, bs, ns, S_ = pend.pop(0)
            L.add(As, bs, ns)
            W.settle_te(S_)

    def store(m, t, S, picks):
        B, Rm, n, ctrl, pid, pa, E, BX = record(S, picks, K)
        out["B"][m, :, t], out["Rm"][m, :, t], out["n"][m, :, t] = B, Rm, n
        out["ctrl"][m, :, t], out["E"][m, :, t], out["BX"][m, :, t] = ctrl, E, BX
        out["iss"][m, :, t, :], out["a"][m, :, t, :] = pid, pa

    # ---- history: training rows only; walk-forward picks over the last sel_window sessions (for SEL cells)
    for t in range(-cell.H_hist, 0):
        S = W.session(t)
        settle_upto(t - cell.lag)
        if cell.select == "best" and t >= -cell.sel_window:
            picks = L.decide(S, t, rng)
            for m in range(M):
                B = record(S, picks[m], K)[0]
                good = np.isfinite(B)
                wf[m] += np.where(good, B, 0.0)
                wf_n[m] += good
        As, bs, ns = session_stats(S)
        pend.append((t, As, bs, ns, S if cell.te else None))
    # ---- registration. THE BREAK (overlap > 0): the snapshot includes forward sessions 0..k-1 and the model and the
    # TE fitted on them decide those sessions (a backfill decided after training on its own outcomes)
    t0 = 0
    if cell.overlap > 0:
        k = cell.overlap
        Ss = [W.session(t) for t in range(k)]
        settle_upto(10 ** 9)
        for t, S in enumerate(Ss):
            As, bs, ns = session_stats(S)
            L.add(As, bs, ns)
            W.settle_te(S)
        for t, S in enumerate(Ss):
            if cell.te:
                S["X"][..., 21] = take(W.te_sum, S["ids"]) / (take(W.te_n, S["ids"]) + 10.0)
            picks = L.decide(S, t, rng)
            for m in range(M):
                store(m, t, S, picks[m])
        t0 = k
    for t in range(t0, T):
        S = W.session(t)
        settle_upto(t - cell.lag)
        picks = L.decide(S, t, rng)
        for m in range(M):
            store(m, t, S, picks[m])
        As, bs, ns = session_stats(S)
        pend.append((t, As, bs, ns, S if cell.te else None))
    with np.errstate(invalid="ignore", divide="ignore"):
        score = np.where(wf_n > 0, wf / np.maximum(wf_n, 1), -np.inf)
    sel = np.argmax(score, axis=0) if cell.select == "best" else np.zeros(R, dtype=np.int64)
    out["sel"] = sel
    return out


def screen_all(cell: Cell, sim: dict) -> dict:
    M, R = sim["B"].shape[:2]
    res = {}
    for rule in ("ev6d", "ev6t"):
        passed = np.zeros((M, R), dtype=np.int8)
        when = np.full((M, R), -1)
        ended = np.full((M, R), "", dtype=object)
        endt = np.full((M, R), -1)
        for m in range(M):
            one = dict(B=np.nan_to_num(sim["B"][m]), Rm=np.nan_to_num(sim["Rm"][m]), n=sim["n"][m],
                       ctrl=sim["ctrl"][m], iss=sim["iss"][m], a=sim["a"][m])
            for rep in range(R):
                ok, wh, en, et = ce.screen_ev6(one, rep, rule)
                passed[m, rep], when[m, rep], ended[m, rep], endt[m, rep] = int(ok), wh, en or "", et
        res[rule] = dict(passed=passed, when=when, ended=ended, endt=endt)
    return res


def summarise(cell: Cell, sim: dict, scr: dict) -> dict:
    M, R, T = sim["B"].shape
    sel = sim["sel"]
    out = dict(cell=cell.name, R=int(R), M=int(M))
    for rule, s in scr.items():
        P = s["passed"]
        out[f"{rule}_pass_sel"] = float(P[sel, np.arange(R)].mean())
        out[f"{rule}_pass_blind"] = float(P[0].mean())
        out[f"{rule}_pass_by_cand"] = [float(x) for x in P.mean(axis=1)]
        out[f"{rule}_pass_any"] = float((P.max(axis=0) > 0).mean())
        en = s["ended"][sel, np.arange(R)]
        out[f"{rule}_retired_sel"] = float((en == "retire").mean())
        out[f"{rule}_exhaust_sel"] = float((en == "exhaust").mean())
        et = s["endt"][sel, np.arange(R)]
        out[f"{rule}_mean_end_sel"] = float(np.mean(np.where(et >= 0, et, T)))
        # events traded (shadow picks) before the version ends, and their mean true edge
        n = sim["n"][sel, np.arange(R)]
        E = sim["E"][sel, np.arange(R)]
        until = np.where(et >= 0, et, T - 1)
        tt = np.arange(T)[None, :]
        live = tt <= until[:, None]
        ev = (n * live).sum(axis=1)
        with np.errstate(invalid="ignore"):
            wsum = np.nansum(np.where(live, E * n, 0.0), axis=1)
        out[f"{rule}_events_until_end"] = float(ev.mean())
        out[f"{rule}_true_edge_until_end_bp"] = float(1e4 * wsum.sum() / max(ev.sum(), 1))
    E = sim["E"][sim["sel"], np.arange(R)]
    BX = sim["BX"][sim["sel"], np.arange(R)]
    nn = sim["n"][sim["sel"], np.arange(R)]
    import warnings
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        out["true_edge_bp_first20"] = float(1e4 * np.nanmean(E[:, :20]))
        out["true_edge_bp_all"] = float(1e4 * np.nanmean(E))
        out["beta_excess_picks"] = float(np.nanmean(BX))
    out["picks_per_session"] = float(nn.mean())
    out["sel_hist"] = [int((sim["sel"] == m).sum()) for m in range(M)]
    return out


SEL6 = ((500.0, "all"), (20.0, "all"), (40.0, "all"), (120.0, "all"), (INF, "all"), (INF, "nosec"))


def grid(name: str):
    C = Cell
    if name == "base":
        return [C("REF-RANDOM", learn=False), C("REF-FWD", H_hist=3, cands=((40.0, "all"),)),
                C("W-NOISE"), C("W-NOISE-HL40", cands=((40.0, "all"),)),
                C("W-DECAY", h_ic=0.05, h_mu=-0.04),
                C("W-LEAK", leak=0.3), C("W-TE", te=True), C("W-TE-tau1", te=True, tau=0.01)]
    if name == "break":
        return [C("BRK-OVL5-gen", overlap=5, cands=((40.0, "all"),)),
                C("BRK-OVL10-gen", overlap=10, cands=((40.0, "all"),)),
                C("BRK-OVL5-te", overlap=5, te=True), C("BRK-OVL10-te", overlap=10, te=True),
                C("GRD-OVL0-te", te=True)]
    if name == "beta":
        return [C(f"BETA-f{int(mf * 1e4)}-{'hedge' if h else 'plain'}", mu_m_h=0.0004, mu_m_f=mf, hedge=h)
                for mf, h in ((0.0, False), (0.0004, False), (0.0010, False), (0.0010, True), (0.0020, False),
                              (0.0020, True))]
    if name == "sel":
        return [C("SEL-N1", cands=SEL6, select="best"),
                C("SEL-SECDRIFT15", cands=SEL6, select="best", sec_drift_sd=0.0015),
                C("SEL-SECDRIFT30", cands=SEL6, select="best", sec_drift_sd=0.0030),
                C("SEL-BETA10", cands=SEL6, select="best", mu_m_h=0.0010, mu_m_f=0.0010)]
    if name == "power":
        return [C("PWR-clean-ic05", h_ic=0.05, h_mu=-0.04, f_ic=0.05, f_mu=-0.04),
                C("PWR-leak-ic05", h_ic=0.05, h_mu=-0.04, f_ic=0.05, f_mu=-0.04, leak=0.3),
                C("PWR-fwdonly-ic05", H_hist=3, f_ic=0.05, f_mu=-0.04, cands=((40.0, "all"),)),
                C("FLIP-ic05", h_ic=0.05, h_mu=-0.04, f_ic=0.05, f_mu=-0.04, f_flip=True)]
    if name == "worst":
        Wst = dict(rho_day=0.15, day="crash", ev_skew=True, drift_sd=0.0020)
        return [C("WST-REF-RANDOM", learn=False, **Wst), C("WST-REF-FWD", H_hist=3, cands=((40.0, "all"),), **Wst),
                C("WST-W-NOISE", **Wst), C("WST-W-NOISE-HL40", cands=((40.0, "all"),), **Wst),
                C("WST-W-NOISE-tau1", tau=0.01, **Wst), C("WST-W-TE-tau1", te=True, tau=0.01, **Wst)]
    if name == "worst3":
        Wst = dict(rho_day=0.15, day="crash", ev_skew=True, drift_sd=0.0020, tau=0.01)
        return [C("WST-W-NOISE-tau1", **Wst), C("WST-REF-FWD-tau1", H_hist=3, cands=((40.0, "all"),), **Wst)]
    if name == "worst2":
        Wst = dict(rho_day=0.15, day="crash", ev_skew=True, drift_sd=0.0020, tau=0.01)
        return [C("WST-REF-RANDOM-tau1", learn=False, **Wst), C("WST-REF-FWD-tau1", H_hist=3, cands=((40.0, "all"),), **Wst)]
    if name == "brk2":
        return [C("W-NOISE-HL10", cands=((10.0, "all"),)), C("BRK-OVL10-HL10", overlap=10, cands=((10.0, "all"),)),
                C("BRK-OVL20-HL10", overlap=20, cands=((10.0, "all"),))]
    if name == "smoke":
        return [C("SMOKE", H_hist=60, T=40)]
    raise SystemExit(f"unknown grid {name}")


SEEDS = dict(worst3=97_700_001, worst2=97_500_001, brk2=92_500_001, worst=97_000_001, base=91_000_001, brk=92_000_001, beta=93_000_001, sel=94_000_001, power=95_000_001, smoke=99_000_001)


def _job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = simulate(cell, seed, R)
    scr = screen_all(cell, sim)
    s = summarise(cell, sim, scr)
    s["seed"] = seed
    s["secs"] = round(time.time() - t0, 1)
    return s


def run(gname, reps, chunk, workers, out):
    import multiprocessing as mp
    cells = grid(gname)
    s0 = SEEDS.get("brk" if gname == "break" else gname, 98_000_001)
    jobs = []
    for ci, c in enumerate(cells):
        for j in range(max(1, reps // chunk)):
            jobs.append((c, s0 + 1000 * ci + j, chunk))
    t0 = time.time()
    with mp.get_context("fork").Pool(workers) as pool, open(out, "a") as fh:
        for i, s in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(s) + "\n")
            fh.flush()
            print(f"{gname}: {i + 1}/{len(jobs)} {s['cell']} {s['secs']}s total {time.time() - t0:.0f}s", flush=True)


def _se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / max(n, 1))


def report(paths):
    rows = []
    for p in paths:
        with open(p) as fh:
            rows += [json.loads(x) for x in fh if x.strip()]
    by = {}
    for r in rows:
        by.setdefault(r["cell"], []).append(r)
    for name, parts in by.items():
        R = sum(p["R"] for p in parts)
        w = [p["R"] / R for p in parts]

        def avg(k):
            return sum(wi * p[k] for wi, p in zip(w, parts))
        line = [f"{name}  R={R}"]
        for rule in ("ev6d", "ev6t"):
            ps, pb = avg(f"{rule}_pass_sel"), avg(f"{rule}_pass_blind")
            bc = [sum(wi * p[f"{rule}_pass_by_cand"][m] for wi, p in zip(w, parts)) for m in range(parts[0]["M"])]
            line.append(f"  {rule}: pass(selected)={ps:.4f} (se {_se(ps, R):.4f})  pass(blind cand0)={pb:.4f}"
                        f"  by cand={['%.3f' % x for x in bc]}  retired={avg(f'{rule}_retired_sel'):.3f}"
                        f" exhausted={avg(f'{rule}_exhaust_sel'):.3f} mean end={avg(f'{rule}_mean_end_sel'):.1f}"
                        f" events until end={avg(f'{rule}_events_until_end'):.0f}"
                        f" true edge until end={avg(f'{rule}_true_edge_until_end_bp'):.1f} bp")
        line.append(f"  picks/session={avg('picks_per_session'):.2f} true edge first20={avg('true_edge_bp_first20'):.1f} bp"
                    f" all={avg('true_edge_bp_all'):.1f} bp beta excess of picks={avg('beta_excess_picks'):+.3f}")
        if parts[0]["M"] > 1:
            hist = np.sum([p["sel_hist"] for p in parts], axis=0)
            line.append(f"  selected candidate counts={hist.tolist()}")
        print("\n".join(line))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report"))
    ap.add_argument("--grid", default="smoke")
    ap.add_argument("--reps", type=int, default=400)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=None)
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    if a.cmd == "report":
        report(a.paths or sorted(glob.glob(os.path.join(HERE, "rt_warm.*.jsonl"))))
        sys.exit(0)
    run(a.grid, a.reps, a.chunk, min(4, a.workers), a.out or os.path.join(HERE, f"rt_warm.{a.grid}.jsonl"))

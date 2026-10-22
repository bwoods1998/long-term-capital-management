#!/usr/bin/env python3
"""CALIBRATION RECORD for PREREG-EVL-6's promotion screen SFE-SWITCH (the 'strata' design). SYNTHETIC DATA ONLY.

No lane data is read: no events.sqlite, no live.sqlite, no boxrun.py, no market data. Every number below comes from the
generator in this file, so the screen is chosen blind to the lane's results.

THE DESIGN CALIBRATED (as registered text describes it; one-session holds, window OC; CC is not simulated):
  Looks at the first close with N_k = ceil(30 x 1.25^(k-1)) covered events (k = 1..24), >= 20 issuers, >= 2 session blocks;
  thresholds reached at one close are one look; at most one look a close.
  A look with fewer than 7 session blocks: HYBRID p = max(p_V1, p_V2) at alpha_E = 0.008, where p_V is the sign-flip of
  the exact split T = sum M_d + sum Q_dk + sum U_j + sum B_d plus VIRTUAL blocks W_d (observed 0) of size
  sqrt(rho_eff ((sum s)^2 - sum s^2)), rho_eff = 0.01 or max(0.01, rho_hat) once 4 referenced sessions have >= 2 events.
  M/Q/U come from a per-session WLS fit (weights 1/s^2) of the lane reference's GROSS returns on (1, s), FF12 industry
  effects shrunk by O_dk/(O_dk + 10); V1 keeps the intercept in the day part, V2 drops it. Sessions with a reference of
  fewer than 30 rows are B_d blocks.
  A look with 7 or more blocks: PREREG-EVL-1 section 7's session-block sign-flip (mean of per-session means) at 0.010.
  Skew checks (only tighten): hybrid = stratified bootstrap within M/Q/U/B (virtual fixed), alpha lowered by 0.001 while
  f > alpha (floor 0.001); session blocks = today's skew_check with alpha = cap = 0.010 (step 0.002, floor 0.002).
  PASS: p <= alpha AND mean a > 0 AND mean r > 0 (r reported both ways: the conservative FP ignores the r condition).

MONTE CARLO SHORTCUTS (each leaves the decision rule's level unchanged):
  * B = 1,999 sign vectors instead of 99,999 (a Monte Carlo sign-flip p with B draws is itself an exact test; alpha is a
    multiple of 1/2000 so the nominal level is identical).
  * Skew checks are computed only when p <= 0.020 and mean a > 0 (they only tighten, so a look with p > alpha or mean
    a <= 0 fails whatever they say). The f-curves are stored for alpha 0.001..0.020 so any alpha in that range can be
    re-evaluated offline.
  * Fresh random sign vectors per look (instead of seeded per program id); equivalent in distribution.

Run: TMPDIR=/dev/shm/calib-strata .venv/bin/python calib_strata.py run [--reps 2000] [--workers 8] [--cells regex]
     .venv/bin/python calib_strata.py summarize
     .venv/bin/python calib_strata.py test        (identity and tiny-run checks)
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import glob  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import get_context  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE_DIR = os.environ.get("CALIB_TRACE_DIR", os.path.join(HERE, "calib_strata_traces"))
OUT_JSON = os.environ.get("CALIB_OUT_JSON", os.path.join(HERE, "calib_strata_out.json"))

K = 12                      # FF12 industries
NF_OTHER = 3                # other event families in the lane reference (8-K, earnings, news ... whichever P is not)
NFAC = 3                    # factor-day rotations (momentum, value, size)
SQ3 = math.sqrt(3.0)
LN_LO, LN_HI = math.log(0.01), math.log(0.10)
RMS_SIG = math.sqrt((0.10 ** 2 - 0.01 ** 2) / (2 * math.log(10.0)))  # RMS of log-uniform sigma on [1%, 10%] = 4.6%

B = 1999
SKEW_N = 1000
SKEW_B = 1999
P_REC = 0.020
AGRID = [round(0.001 * i, 3) for i in range(1, 21)]  # f-curves stored at these alphas
TIE = 1e-12
HYB_MAX = 10                # hybrid p computed at looks with fewer than 10 blocks (switch points 7..10 evaluable)

SFE_NS = [int(math.ceil(30 * 1.25 ** (k - 1) - 1e-9)) for k in range(1, 25)]
SFE_MIN_ISS, SFE_MIN_BLK = 20, 2
EVL3_NS = [60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250]
EVL3_MIN_ISS, EVL3_MIN_BLK, EVL3_ALPHA = 40, 8, 0.018

BASE = dict(
    lam=85.0,            # READ events a session (mean; gamma-mixed day intensity)
    ctrl_mult=3.0,       # control = 3x READ
    sel=1.0 / 3.0,       # subset mode: READ takes each control event with this probability (no reading skill)
    mode="subset",       # 'subset' (READ = random subset of its control) or 'own' (own selection, sector + factor tilt)
    others=None,         # other families' events a session in the reference (None: max(60, 300 - 3 lam))
    rho_day=0.05,        # residual day shock, share of event variance, proportional to sigma
    rho_add=0.01,        # additive day shock (not proportional to sigma), share of RMS event variance
    rho_sec=0.03,        # FF12 industry-day shock
    rho_fam=0.03,        # family-day shock (P, its control and its family share it; other families do not)
    rho_fac=0.03,        # factor-day rotations, 3 factors, issuer loadings N(family mean, 1)
    fac_sd=0.5,          # sd of a family's (or own-mode program's) mean factor loading
    rho_res=0.0,         # own mode only: a day shock only P's events load on (selection the reference cannot see)
    rho_eta=0.02,        # persistent issuer effect (repeats of an issuer share it)
    delta_p=0.0,         # bp: mean after-cost a of P's family (READ and control); 0 = the money null's boundary
    g_o=0.0,             # bp: mean GROSS return of the other families (0 = they make nothing before costs)
    edge=0.0,            # bp: added to READ (P) events only
    jump_p=0.004, jump=0.30, skew="sym",  # occasional +-30% moves ('left': -30% crash, mean-compensated)
    s_noise=0.3, s_day_noise=0.05,        # sigma60 error: persistent per issuer and per day (log sd)
    rate_cv=0.5, vol_regime=0.5,          # day intensity ~ Gamma(cv); event vol x intensity^0.5 (busy days are wild)
    pool_p=2500, pool_o=2000, zipf=0.8,   # issuer pools (Zipf weights): repeats of popular issuers
    holdout=5,           # P never re-enters an issuer within 5 sessions (repeats >= 6 sessions apart)
    own_conc=1.0,        # own mode: Dirichlet concentration of P's industry tilt (low = clustered)
    o_min=30, kappa=10.0,
    cost_a=3.0, cost_b=0.02,              # cost a side = 3 bp + 0.02 sigma (round trip 2x)
    mkt_sd=0.01,         # benchmark (market) return a session, t3, zero drift: r = a + benchmark
    ar=0.0,              # AR(1) persistence of the day, family and factor shocks across sessions (0 = independent)
    sessions=40,
    lifetime=False,      # True: run the whole look schedule (to N_24 = 5083) instead of 40 sessions
)

WORST = dict(rho_day=0.30, rho_add=0.02, rho_sec=0.05, rho_fam=0.05, rho_fac=0.06, fac_sd=0.7, rho_eta=0.03,
             g_o=-30.0, skew="left", jump_p=0.01, mode="own", rho_res=0.02, own_conc=0.5)


def cells() -> dict[str, dict]:
    out: dict[str, dict] = {}
    rates = (85, 30, 13, 8)
    for lam in rates:
        for rho in (0.0, 0.05, 0.15, 0.30):
            tag = f"r{int(round(rho * 100)):02d}"
            out[f"null_subset_{lam}_{tag}"] = dict(lam=lam, rho_day=rho)
            out[f"null_own_{lam}_{tag}"] = dict(lam=lam, rho_day=rho, mode="own", rho_res=0.01)
            out[f"null_driftneg_{lam}_{tag}"] = dict(lam=lam, rho_day=rho, delta_p=-30.0)
            out[f"null_driftpos_{lam}_{tag}"] = dict(lam=lam, rho_day=rho, delta_p=30.0)
        w = dict(lam=lam, rho_day=0.30)
        out[f"stress_gref30_{lam}"] = dict(w, g_o=-30.0)
        out[f"stress_gref60_{lam}"] = dict(w, g_o=-60.0)
        out[f"stress_add05_{lam}"] = dict(w, rho_add=0.05)
        out[f"stress_res05_{lam}"] = dict(w, mode="own", rho_res=0.05)
        out[f"stress_thin_{lam}"] = dict(w, others=0)
        out[f"stress_left_{lam}"] = dict(w, skew="left", jump_p=0.01)
        out[f"stress_persist_{lam}"] = dict(w, rho_eta=0.08, pool_p=800, zipf=1.0)
        out[f"stress_worst_{lam}"] = dict(WORST, lam=lam)
        out[f"stress_ar20_{lam}"] = dict(w, ar=0.2, mode="own", rho_res=0.02)
        out[f"stress_ar40_{lam}"] = dict(w, ar=0.4, mode="own", rho_res=0.02)
        for e in (30, 60, 100):
            out[f"power_base_{lam}_{e}"] = dict(lam=lam, edge=float(e))
            out[f"power_r00_{lam}_{e}"] = dict(lam=lam, edge=float(e), rho_day=0.0)
            out[f"power_worst_{lam}_{e}"] = dict(WORST, lam=lam, edge=float(e))
    for lam in rates:  # whole look schedule (the lifetime FP), base and worst
        out[f"life_subset_{lam}"] = dict(lam=lam, rho_day=0.30, lifetime=True)
        out[f"life_worst_{lam}"] = dict(WORST, lam=lam, lifetime=True)
        out[f"life_res05_{lam}"] = dict(lam=lam, rho_day=0.30, mode="own", rho_res=0.05, lifetime=True)
        out[f"life_ar20_{lam}"] = dict(lam=lam, rho_day=0.30, ar=0.2, mode="own", rho_res=0.02, lifetime=True)
    return out


def seed_of(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def t3(r, size=None):
    return r.standard_t(3, size) / SQ3


# ---------------------------------------------------------------------------------------------------- sign flips
def flips(r, b: int, n: int) -> np.ndarray:
    """b x n matrix of +-1 (float64)."""
    if n == 0:
        return np.zeros((b, 0))
    nb = (n + 7) // 8
    by = np.frombuffer(r.bytes(b * nb), dtype=np.uint8).reshape(b, nb)
    return np.unpackbits(by, axis=1, count=n).astype(np.float64) * 2.0 - 1.0


def _tables(x: np.ndarray) -> np.ndarray:
    """Per run of 8 values, the 256 signed partial sums (entry b: +x_j where bit j of b is set, else -x_j)."""
    nb = (len(x) + 7) // 8
    xp = np.zeros(nb * 8)
    xp[:len(x)] = x
    X = xp.reshape(nb, 8)
    t = np.zeros((nb, 1))
    for j in range(8):
        v = X[:, j:j + 1]
        t = np.concatenate([t - v, t + v], axis=1)
    return t.ravel()


STOP = int(round(P_REC * (1 + B))) - 1  # p <= P_REC  <=>  count <= STOP (= 39)


def p_flip(r, vals: np.ndarray, virt: np.ndarray, obs: float) -> float:
    """(1 + #{v : sum eps x + sum eps' W >= obs - n 1e-12}) / (1 + B), exact float64 via 8-bit tables. Counting
    stops once p > P_REC is certain (returns 1.0 then: every rule evaluated uses alpha <= P_REC)."""
    x = np.concatenate([vals, virt]) if len(virt) else np.asarray(vals, dtype=np.float64)
    tab = _tables(x)
    nb = len(tab) // 256
    off = (np.arange(nb) * 256)[None, :]
    thr = obs - len(vals) * TIE
    cnt, done = 0, 0
    while done < B:
        m = min(250, B - done)
        by = np.frombuffer(r.bytes(m * nb), dtype=np.uint8).reshape(m, nb)
        sims = tab[by.astype(np.intp) + off].sum(axis=1)
        cnt += int(np.count_nonzero(sims >= thr))
        done += m
        if cnt > STOP:
            return 1.0
    return (1 + cnt) / (1 + B)


def fcurve_hybrid(r, strata: list[np.ndarray], virt: np.ndarray) -> np.ndarray:
    """Stratified skew check: each stratum centred, SKEW_N bootstrap samples resampled within strata, virtual blocks
    fixed; f(a) = share of samples with sum > 0 and p <= a over SKEW_B shared sign vectors. Returns f at AGRID
    (a sample is dropped once its count shows p > P_REC, which no alpha in AGRID can use)."""
    parts = []
    for s in strata:
        if len(s) == 0:
            continue
        c = s - s.mean()
        parts.append(c[r.integers(0, len(s), size=(SKEW_N, len(s)))])
    x = np.concatenate(parts, axis=1)
    nr = x.shape[1]
    tot = x.sum(axis=1)
    thr = tot - nr * TIE
    act = np.flatnonzero(tot > 0)
    cnt = np.zeros(SKEW_N, dtype=np.int64)
    e_all = flips(r, SKEW_B, nr + len(virt))
    done = 0
    while done < SKEW_B and len(act):
        m = min(200, SKEW_B - done)
        e = e_all[done:done + m]
        sims = x[act] @ e[:, :nr].T
        if len(virt):
            sims = sims + (e[:, nr:] @ virt)[None, :]
        cnt[act] += np.count_nonzero(sims >= thr[act, None], axis=1)
        done += m
        act = act[cnt[act] <= STOP]
    p = (1 + cnt) / (1 + SKEW_B)
    ok = tot > 0
    p[~ok] = 1.0
    return np.array([np.count_nonzero(ok & (p <= a + 1e-12)) / SKEW_N for a in AGRID])


def fcurve_plain(r, vals: np.ndarray) -> np.ndarray:
    """Today's skew_check (unstratified bootstrap of the centred values), f at AGRID."""
    return fcurve_hybrid(r, [vals], np.zeros(0))


def alpha_hybrid(f: np.ndarray, start: float) -> float:
    """Lower alpha by 0.001 while f(alpha) > alpha (floor 0.001)."""
    a = start
    while a > 0.001 + 1e-12:
        if f[int(round(a * 1000)) - 1] <= a + 1e-12:
            return a
        a = round(a - 0.001, 3)
    return 0.001


def alpha_plain(f: np.ndarray, start: float, cap: float, step: float = 0.002, floor: float = 0.002) -> float:
    """Today's skew_check: from start, lower by step while f(alpha) > cap (floor)."""
    a = start
    while True:
        if f[int(round(a * 1000)) - 1] <= cap + 1e-12:
            return a
        nxt = round(a - step, 3)
        if nxt < floor - 1e-12:
            return a
        a = nxt


# --------------------------------------------------------------------------------------------------- the program
class Program:
    """One synthetic READ program, its control, and the lane reference of its window, grown session by session."""

    def __init__(self, r: np.random.Generator, cfg: dict):
        self.r, self.c = r, cfg
        c = cfg
        self.others = c["others"] if c["others"] is not None else max(60.0, 300.0 - 3.0 * c["lam"])
        sizes = [c["pool_p"]] + [c["pool_o"]] * NF_OTHER
        self.lo = np.cumsum([0] + sizes[:-1])
        self.hi = np.cumsum(sizes)
        n = int(sum(sizes))
        self.sigma = np.exp(r.uniform(LN_LO, LN_HI, n))
        self.slog = c["s_noise"] * r.standard_normal(n)
        self.H = t3(r, n)
        self.b = r.standard_normal((n, NFAC))
        self.sec = np.zeros(n, dtype=np.int64)
        self.lw = np.zeros(n)
        for f in range(1 + NF_OTHER):
            m = sizes[f]
            pk = r.dirichlet(np.full(K, 2.0))
            self.sec[self.lo[f]:self.hi[f]] = r.choice(K, m, p=pk)
            self.lw[self.lo[f]:self.hi[f]] = -c["zipf"] * np.log1p(r.permutation(m))
        self.mu = r.normal(0.0, c["fac_sd"], (1 + NF_OTHER, NFAC))
        if c["mode"] == "own":
            m = sizes[0]
            tilt = np.log(r.dirichlet(np.full(K, c["own_conc"])) + 1e-12)
            self.lwP = -c["zipf"] * np.log1p(r.permutation(m)) + tilt[self.sec[:m]]
            self.muP = r.normal(0.0, c["fac_sd"], NFAC)
        self.recent: list[np.ndarray] = []
        self.D = 0
        self.ev: list[dict] = []        # per session: arrays of P's events
        self.ctrl_mean: list[float] = []
        self.nblk = 0
        self.stats = {"O": [], "ref": 0, "ses": 0}

    # -- one session's rows
    def _gen(self, idx, fam, mu_rows, res_share, sh, drift):
        c, r = self.c, self.r
        n = len(idx)
        sig = self.sigma[idx]
        idio = math.sqrt(max(1e-9, 1 - c["rho_day"] - c["rho_sec"] - c["rho_fam"] - c["rho_fac"] - c["rho_eta"]
                             - res_share))
        z = (math.sqrt(c["rho_day"]) * sh["C"] + math.sqrt(c["rho_sec"]) * sh["S"][self.sec[idx]]
             + math.sqrt(c["rho_fam"]) * sh["F"][fam]
             + math.sqrt(c["rho_fac"] / NFAC) * ((self.b[idx] + mu_rows) @ sh["PHI"])
             + math.sqrt(c["rho_eta"]) * self.H[idx] + idio * t3(r, n))
        if res_share > 0:
            z = z + math.sqrt(res_share) * sh["R"]
        y = sig * sh["v"] * z + math.sqrt(c["rho_add"]) * RMS_SIG * sh["v"] * sh["A"]
        if c["jump_p"] > 0:
            hit = r.random(n) < c["jump_p"]
            if c["skew"] == "sym":
                y = y + hit * c["jump"] * np.where(r.random(n) < 0.5, -1.0, 1.0)
            else:
                y = y + hit * (-c["jump"]) + c["jump"] * c["jump_p"]
        cost = 2.0 * (c["cost_a"] * 1e-4 + c["cost_b"] * sig)
        s = np.clip(sig * np.exp(self.slog[idx] + c["s_day_noise"] * r.standard_normal(n)), 0.01, 0.15)
        a = drift(cost) + y
        return a, cost, s

    def _topk(self, lw, n):
        if n <= 0:
            return np.zeros(0, dtype=np.int64)
        g = lw + self.r.gumbel(size=len(lw))
        if n >= len(lw):
            return np.arange(len(lw))
        return np.argpartition(-g, n)[:n]

    def step(self, need_fit: bool):
        r, c = self.r, self.c
        self.D += 1
        gd = r.gamma(1.0 / c["rate_cv"] ** 2, c["rate_cv"] ** 2)
        sh = dict(v=gd ** c["vol_regime"], C=t3(r), A=t3(r), R=t3(r), MK=t3(r) * c["mkt_sd"], S=t3(r, K),
                  F=t3(r, 1 + NF_OTHER), PHI=t3(r, NFAC))
        if c["ar"] > 0:
            phi, inn = c["ar"], math.sqrt(1 - c["ar"] ** 2)
            prev = getattr(self, "_prev", None)
            if prev is not None:
                for key in ("C", "F", "PHI", "R", "S"):
                    sh[key] = phi * prev[key] + inn * sh[key]
            self._prev = {key: sh[key] for key in ("C", "F", "PHI", "R", "S")}
        lo0, hi0 = self.lo[0], self.hi[0]
        rec = np.concatenate(self.recent[-c["holdout"]:]) if self.recent else np.zeros(0, dtype=np.int64)
        dp = c["delta_p"] * 1e-4
        edge = c["edge"] * 1e-4
        # control: every event of P's family this session (no hold-out)
        nc = r.poisson(c["ctrl_mult"] * c["lam"] * gd)
        ci = lo0 + self._topk(self.lw[lo0:hi0], nc)
        ca, ccost, cs = self._gen(ci, 0, self.mu[0], 0.0, sh, lambda cost: dp)
        if c["mode"] == "subset":
            free = ~np.isin(ci, rec)
            fs = free.mean() if len(ci) else 1.0
            pick = free & (r.random(len(ci)) < min(1.0, c["sel"] / max(fs, 1e-9)))
            pi, pa, pcost, ps = ci[pick], ca[pick] + edge, ccost[pick], cs[pick]
            ca = ca.copy()
            ca[pick] += edge
            ref_c = ~pick
        else:
            npn = r.poisson(c["lam"] * gd)
            lwp = self.lwP.copy()
            if len(rec):
                lwp[rec - lo0] = -np.inf
            npn = min(npn, int(np.isfinite(lwp).sum()))
            pi = lo0 + self._topk(lwp, npn)
            pa, pcost, ps = self._gen(pi, 0, self.muP, c["rho_res"], sh, lambda cost: dp)
            pa = pa + edge
            ref_c = ~np.isin(ci, pi)
        self.ctrl_mean.append(float(ca.mean()) if len(ca) else float("nan"))
        # the reference: the control's other events + the other families' events (one row per issuer)
        rg, rs, rk = [ca[ref_c] + ccost[ref_c]], [cs[ref_c]], [self.sec[ci[ref_c]]]
        for f in range(1, 1 + NF_OTHER):
            if not need_fit:
                break
            no = r.poisson(self.others / NF_OTHER * gd)
            oi = self.lo[f] + self._topk(self.lw[self.lo[f]:self.hi[f]], no)
            go = c["g_o"] * 1e-4
            oa, ocost, os_ = self._gen(oi, f, self.mu[f], 0.0, sh, lambda cost, go=go: go - cost)
            rg.append(oa + ocost)
            rs.append(os_)
            rk.append(self.sec[oi])
        g = np.concatenate(rg)
        s_ref = np.concatenate(rs)
        k_ref = np.concatenate(rk)
        O = len(g)
        n = len(pi)
        refd = O >= c["o_min"]
        if need_fit:
            self.stats["O"].append(O)
            self.stats["ses"] += 1
            self.stats["ref"] += int(refd)
        ev = dict(d=np.full(n, self.D, dtype=np.int64), iss=pi.astype(np.int64), sec=self.sec[pi], s=ps, a=pa,
                  r=pa + sh["MK"], ref=np.full(n, refd))
        if need_fit and refd and n:
            w = 1.0 / s_ref ** 2
            S0, S1, S2 = math.fsum(w), math.fsum(1.0 / s_ref), float(O)
            Sy, Sys = math.fsum(w * g), math.fsum(g / s_ref)
            det = S0 * S2 - S1 * S1
            al = (S2 * Sy - S1 * Sys) / det
            ga = (S0 * Sys - S1 * Sy) / det
            e = (g - al - ga * s_ref) / s_ref
            nk = np.bincount(k_ref, minlength=K).astype(float)
            ek = np.bincount(k_ref, weights=e, minlength=K)
            h = np.where(nk > 0, nk / (nk + c["kappa"]) * ek / np.maximum(nk, 1), 0.0)
            ev["m1"] = al + ga * ps
            ev["m2"] = ga * ps
            ev["q"] = ps * h[ev["sec"]]
        else:
            z = np.zeros(n)
            ev["m1"], ev["m2"], ev["q"] = z, z, z
        if n:
            self.nblk += 1
        self.ev.append(ev)
        self.recent.append(pi.astype(np.int64))
        return n

    def arrays(self) -> dict:
        keys = ("d", "iss", "sec", "s", "a", "r", "ref", "m1", "m2", "q")
        return {k: np.concatenate([e[k] for e in self.ev]) for k in keys}


# ------------------------------------------------------------------------------------------------------ the tests
def rho_hat(d, s, u1, ok) -> tuple[float, int]:
    if not ok.any():
        return 0.0, 0
    z = u1[ok] / s[ok]
    dd = d[ok]
    _, inv = np.unique(dd, return_inverse=True)
    n = np.bincount(inv).astype(float)
    sz = np.bincount(inv, weights=z)
    szz = np.bincount(inv, weights=z * z)
    m = n >= 2
    nd = int(m.sum())
    if nd < 2:
        return 0.0, nd
    zb = sz / n
    within = (szz - n * zb ** 2)  # = (n - 1) s_d^2
    s2 = within[m].sum() / (n[m] - 1).sum()
    nn, zz = n[m], zb[m]
    N = nn.sum()
    zbar = (nn * zz).sum() / N
    Q = (nn * (zz - zbar) ** 2).sum()
    den = ((nn - 1) * (1 - nn / N)).sum()
    if s2 <= 0 or den <= 0:
        return 0.0, nd
    return float(min(1.0, max(0.0, (Q / s2 - (1 - nn / N).sum()) / den))), nd


def hybrid_parts(x: dict, variant: str, rho_eff: float):
    d, iss, sec, s, a, ok = x["d"], x["iss"], x["sec"], x["s"], x["a"], x["ref"]
    m = x["m1"] if variant == "V1" else x["m2"]
    q = x["q"]
    u = a - m - q
    if ok.any():
        dk, inv = np.unique(d[ok], return_inverse=True)
        M = np.bincount(inv, weights=m[ok])
        S1 = np.bincount(inv, weights=s[ok])
        S2 = np.bincount(inv, weights=s[ok] ** 2)
        cell = d[ok] * K + sec[ok]
        _, cinv = np.unique(cell, return_inverse=True)
        Q = np.bincount(cinv, weights=q[ok])
        Q = Q[Q != 0]
        _, iinv = np.unique(iss[ok], return_inverse=True)
        U = np.bincount(iinv, weights=u[ok])
        W = np.sqrt(np.maximum(0.0, rho_eff * (S1 ** 2 - S2)))
        W = W[W > 0]
    else:
        M = Q = U = W = np.zeros(0)
    if (~ok).any():
        _, binv = np.unique(d[~ok], return_inverse=True)
        Bd = np.bincount(binv, weights=a[~ok])
    else:
        Bd = np.zeros(0)
    return M, Q, U, Bd, W


def session_values(x: dict) -> np.ndarray:
    _, inv = np.unique(x["d"], return_inverse=True)
    return np.bincount(inv, weights=x["a"]) / np.bincount(inv)


# ----------------------------------------------------------------------------------------------------- simulation
def simulate(cfg: dict, reps: int, seed: int) -> dict:
    """reps programs. Returns SFE look rows, f-curves and today's (PREREG-EVL-3) first-pass sessions."""
    r = np.random.default_rng(seed)
    rows = []          # prog, D, N, nblk, p1, p2, psb, posa, posr, ih1, ih2, isb, rho_eff, Mshare
    fcs = []           # f-curves (AGRID)
    evl3 = []          # prog, first pass session (r cond), first pass (no r cond), looks held
    meta = {"events_per_session": [], "ref_share": [], "O_mean": [], "sessions": []}
    for prog in range(reps):
        P = Program(r, cfg)
        k_sfe = k3 = 0
        first3 = [-1, -1]
        held3 = 0
        Dmax = cfg["sessions"] if not cfg["lifetime"] else 100000
        while P.D < Dmax:
            if cfg["lifetime"] and k_sfe >= len(SFE_NS) and k3 >= len(EVL3_NS):
                break
            P.step(need_fit=P.nblk < HYB_MAX)
            N = sum(len(e["a"]) for e in P.ev)
            want_sfe = k_sfe < len(SFE_NS) and N >= SFE_NS[k_sfe]
            want_3 = k3 < len(EVL3_NS) and N >= EVL3_NS[k3]
            if not (want_sfe or want_3):
                continue
            x = P.arrays()
            nis = len(np.unique(x["iss"]))
            nblk = P.nblk
            T = float(x["a"].sum())
            posa = T > 0
            posr = float(x["r"].sum()) > 0
            sv = None
            if want_sfe and nis >= SFE_MIN_ISS and nblk >= SFE_MIN_BLK:
                while k_sfe < len(SFE_NS) and N >= SFE_NS[k_sfe]:
                    k_sfe += 1
                sv = session_values(x)
                psb = p_flip(r, sv, np.zeros(0), float(sv.sum()))
                p1 = p2 = float("nan")
                ih1 = ih2 = isb = -1
                rho_eff = float("nan")
                msh = float("nan")
                if nblk < HYB_MAX:
                    rh, nd = rho_hat(x["d"], x["s"], x["a"] - x["m1"] - x["q"], x["ref"])
                    rho_eff = max(0.01, rh) if nd >= 4 else 0.01
                    parts = {}
                    for V in ("V1", "V2"):
                        M, Q, U, Bd, W = hybrid_parts(x, V, rho_eff)
                        vals = np.concatenate([M, Q, U, Bd])
                        parts[V] = (M, Q, U, Bd, W)
                        pv = p_flip(r, vals, W, T)
                        if V == "V1":
                            p1 = pv
                            msh = float(M.sum() / T) if T != 0 else float("nan")
                        else:
                            p2 = pv
                    if posa and max(p1, p2) <= P_REC:
                        for V in ("V1", "V2"):
                            M, Q, U, Bd, W = parts[V]
                            fcs.append(fcurve_hybrid(r, [M, Q, U, Bd], W))
                            if V == "V1":
                                ih1 = len(fcs) - 1
                            else:
                                ih2 = len(fcs) - 1
                if posa and psb <= P_REC:
                    fcs.append(fcurve_plain(r, sv))
                    isb = len(fcs) - 1
                rows.append((prog, P.D, N, nblk, p1, p2, psb, int(posa), int(posr), ih1, ih2, isb, rho_eff, msh))
            if want_3 and nis >= EVL3_MIN_ISS and nblk >= EVL3_MIN_BLK:
                while k3 < len(EVL3_NS) and N >= EVL3_NS[k3]:
                    k3 += 1
                held3 += 1
                if first3[1] < 0 or first3[0] < 0:
                    if sv is None:
                        sv = session_values(x)
                    ok = False
                    ps3 = p_flip(r, sv, np.zeros(0), float(sv.sum()))
                    if posa and ps3 <= EVL3_ALPHA:
                        _, iinv = np.unique(x["iss"], return_inverse=True)
                        iv = np.bincount(iinv, weights=x["a"]) / np.bincount(iinv)
                        pi3 = p_flip(r, iv, np.zeros(0), float(iv.sum()))
                        if pi3 <= EVL3_ALPHA:
                            a_s = alpha_plain(fcurve_plain(r, sv), EVL3_ALPHA, EVL3_ALPHA)
                            a_i = alpha_plain(fcurve_plain(r, iv), EVL3_ALPHA, EVL3_ALPHA)
                            ctrl_ok = True
                            if cfg["mode"] == "subset":
                                days = np.unique(x["d"])
                                cm = np.array([P.ctrl_mean[dd - 1] for dd in days])
                                cm = cm[np.isfinite(cm)]
                                ctrl_ok = len(cm) > 0 and float(sv.mean()) > float(cm.mean())
                            ok = ps3 <= a_s + 1e-12 and pi3 <= a_i + 1e-12 and ctrl_ok
                    if ok and first3[1] < 0:
                        first3[1] = P.D
                    if ok and posr and first3[0] < 0:
                        first3[0] = P.D
            if cfg["lifetime"] and k_sfe >= len(SFE_NS) and k3 >= len(EVL3_NS):
                break
        evl3.append((prog, first3[0], first3[1], held3))
        N = sum(len(e["a"]) for e in P.ev)
        meta["events_per_session"].append(N / max(1, P.D))
        meta["ref_share"].append(P.stats["ref"] / max(1, P.stats["ses"]))
        meta["O_mean"].append(float(np.mean(P.stats["O"])) if P.stats["O"] else float("nan"))
        meta["sessions"].append(P.D)
    return dict(rows=np.array(rows, dtype=np.float64).reshape(-1, 14),
                fc=np.array(fcs, dtype=np.float32).reshape(-1, len(AGRID)),
                evl3=np.array(evl3, dtype=np.int64).reshape(-1, 4),
                meta={k: float(np.mean(v)) for k, v in meta.items()})


def _task(args):
    name, cfg, reps, chunk = args
    t0 = time.time()
    out = simulate(cfg, reps, seed_of(f"calib_strata|{name}|{chunk}"))
    out["sec"] = time.time() - t0
    out["name"], out["chunk"] = name, chunk
    return out


# ------------------------------------------------------------------------------------------------- rule evaluation
def evaluate(rows: np.ndarray, fc: np.ndarray, nprog: int, aE=0.008, aL=0.010, S=7, use_r=False,
             only=None) -> dict:
    """First passing session per program under SFE-SWITCH(aE, aL, S). only='hyb'|'sb' counts only that test's looks."""
    first = np.full(nprog, -1, dtype=np.int64)
    first_n = np.full(nprog, -1, dtype=np.int64)
    kind = np.zeros(nprog, dtype=np.int64)  # 1 hybrid, 2 session
    for row in rows:
        prog = int(row[0])
        if first[prog] >= 0:
            continue
        D, N, nblk, p1, p2, psb, posa, posr, ih1, ih2, isb = row[1], row[2], row[3], row[4], row[5], row[6], \
            row[7], row[8], int(row[9]), int(row[10]), int(row[11])
        if not posa or (use_r and not posr):
            continue
        if nblk < S:
            if only == "sb":
                continue
            if not (p1 <= aE + 1e-12 and p2 <= aE + 1e-12) or ih1 < 0:
                continue
            a1 = alpha_hybrid(fc[ih1], aE)
            a2 = alpha_hybrid(fc[ih2], aE)
            if p1 <= a1 + 1e-12 and p2 <= a2 + 1e-12:
                first[prog], first_n[prog], kind[prog] = int(D), int(N), 1
        else:
            if only == "hyb":
                continue
            if not psb <= aL + 1e-12 or isb < 0:
                continue
            a = alpha_plain(fc[isb], aL, aL)
            if psb <= a + 1e-12:
                first[prog], first_n[prog], kind[prog] = int(D), int(N), 2
    return dict(first=first, first_n=first_n, kind=kind)


def _adj_hybrid(F: np.ndarray, start: float) -> np.ndarray:
    out = np.full(len(F), 0.001)
    todo = np.ones(len(F), dtype=bool)
    a = start
    while a > 0.001 + 1e-12 and todo.any():
        ok = todo & (F[:, int(round(a * 1000)) - 1] <= a + 1e-12)
        out[ok] = a
        todo &= ~ok
        a = round(a - 0.001, 3)
    return out


def _adj_plain(F: np.ndarray, start: float, cap: float, step: float = 0.002, floor: float = 0.002) -> np.ndarray:
    out = np.full(len(F), np.nan)
    todo = np.ones(len(F), dtype=bool)
    a = start
    while True:
        ok = todo & (F[:, int(round(a * 1000)) - 1] <= cap + 1e-12)
        out[ok] = a
        todo &= ~ok
        nxt = round(a - step, 3)
        if nxt < floor - 1e-12 or not todo.any():
            break
        a = nxt
    out[todo] = a
    return out


def evaluate_vec(rows: np.ndarray, fc: np.ndarray, nprog: int, aE=0.008, aL=0.010, S=7, use_r=False, only=None,
                 cache: dict | None = None) -> dict:
    """Vectorised evaluate() (identical decisions; rows are ordered by program, then session)."""
    cache = {} if cache is None else cache
    if ("h", aE) not in cache:
        cache[("h", aE)] = _adj_hybrid(fc, aE) if len(fc) else np.zeros(0)
    if ("s", aL) not in cache:
        cache[("s", aL)] = _adj_plain(fc, aL, aL) if len(fc) else np.zeros(0)
    ah, as_ = cache[("h", aE)], cache[("s", aL)]
    first = np.full(nprog, -1, dtype=np.int64)
    first_n = np.full(nprog, -1, dtype=np.int64)
    kind = np.zeros(nprog, dtype=np.int64)
    if len(rows) == 0:
        return dict(first=first, first_n=first_n, kind=kind)
    prog = rows[:, 0].astype(np.int64)
    nblk, p1, p2, psb = rows[:, 3], rows[:, 4], rows[:, 5], rows[:, 6]
    posa, posr = rows[:, 7] > 0, rows[:, 8] > 0
    ih1, ih2, isb = rows[:, 9].astype(np.int64), rows[:, 10].astype(np.int64), rows[:, 11].astype(np.int64)
    base = posa & (posr | (not use_r))
    hy = base & (nblk < S) & (ih1 >= 0) & (np.nan_to_num(p1, nan=9) <= aE + 1e-12) & \
        (np.nan_to_num(p2, nan=9) <= aE + 1e-12)
    if only == "sb":
        hy[:] = False
    a1 = np.where(ih1 >= 0, ah[np.maximum(ih1, 0)] if len(ah) else 0, 0)
    a2 = np.where(ih2 >= 0, ah[np.maximum(ih2, 0)] if len(ah) else 0, 0)
    hy &= (p1 <= a1 + 1e-12) & (p2 <= a2 + 1e-12)
    sb = base & (nblk >= S) & (isb >= 0) & (psb <= aL + 1e-12)
    if only == "hyb":
        sb[:] = False
    asb = np.where(isb >= 0, as_[np.maximum(isb, 0)] if len(as_) else 0, 0)
    sb &= psb <= asb + 1e-12
    ok = hy | sb
    idx = np.flatnonzero(ok)
    if len(idx):
        up, fi = np.unique(prog[idx], return_index=True)
        sel = idx[fi]
        first[up] = rows[sel, 1].astype(np.int64)
        first_n[up] = rows[sel, 2].astype(np.int64)
        kind[up] = np.where(hy[sel], 1, 2)
    return dict(first=first, first_n=first_n, kind=kind)


def rate(x: np.ndarray, n: int) -> tuple[float, float]:
    p = float(np.count_nonzero(x >= 0)) / n
    return p, math.sqrt(max(p * (1 - p), 1e-12) / n)


def summarize_cell(name: str, cfg: dict, data: dict, grid: bool) -> dict:
    rows, fc, evl3 = data["rows"], data["fc"], data["evl3"]
    n = len(evl3)
    out = {"cfg": {k: v for k, v in cfg.items() if BASE.get(k) != v}, "programs": n, "meta": data["meta"]}
    cache: dict = {}
    for use_r in (False, True):
        ev = evaluate_vec(rows, fc, n, use_r=use_r, cache=cache)
        p, se = rate(ev["first"], n)
        hit = ev["first"][ev["first"] >= 0]
        tag = "with_r" if use_r else "no_r"
        out[f"design_{tag}"] = {
            "pass": round(p, 4), "se": round(se, 4),
            "by_hybrid": round(float(np.count_nonzero(ev["kind"] == 1)) / n, 4),
            "by_session": round(float(np.count_nonzero(ev["kind"] == 2)) / n, 4),
            "median_session": (float(np.median(hit)) if len(hit) else None),
            "p25_session": (float(np.percentile(hit, 25)) if len(hit) else None),
            "median_session_all": (float(np.median(np.where(ev["first"] >= 0, ev["first"], 10 ** 6)))
                                   if p >= 0.5 else None),
            "median_events": (float(np.median(ev["first_n"][ev["first"] >= 0])) if len(hit) else None),
        }
        e3 = evl3[:, 1] if use_r else evl3[:, 2]
        p3, se3 = rate(e3, n)
        h3 = e3[e3 >= 0]
        out[f"evl3_{tag}"] = {"pass": round(p3, 4), "se": round(se3, 4),
                              "median_session": (float(np.median(h3)) if len(h3) else None)}
    # hybrid alone at every look before 12 blocks, session alone: the parts
    for only in ("hyb", "sb"):
        ev = evaluate_vec(rows, fc, n, only=only, cache=cache)
        p, se = rate(ev["first"], n)
        out[f"part_{only}"] = {"pass": round(p, 4), "se": round(se, 4)}
    if grid:
        g = {}
        for S in (7, 8, 10):
            for aE in (0.002, 0.004, 0.006, 0.008, 0.010):
                for aL in (0.004, 0.006, 0.008, 0.010, 0.012, 0.014, 0.016):
                    ev = evaluate_vec(rows, fc, n, aE=aE, aL=aL, S=S, cache=cache)
                    p, se = rate(ev["first"], n)
                    hit = ev["first"][ev["first"] >= 0]
                    g[f"S{S}|aE{aE:.3f}|aL{aL:.3f}"] = [round(p, 4), round(se, 4),
                                                        (float(np.median(hit)) if len(hit) else None)]
        out["grid_no_r"] = g
    # look-level diagnostics
    if len(rows):
        h = rows[~np.isnan(rows[:, 12])]
        out["rho_eff_mean"] = round(float(np.nanmean(h[:, 12])), 4) if len(h) else None
        out["M_share_median"] = round(float(np.nanmedian(h[:, 13])), 4) if len(h) else None
        out["looks_per_program"] = round(len(rows) / n, 2)
    return out


def run(args):
    allc = cells()
    names = [k for k in allc if re.search(args.cells, k)]
    os.makedirs(TRACE_DIR, exist_ok=True)
    tasks = []
    for name in names:
        cfg = dict(BASE)
        cfg.update(allc[name])
        reps = args.life_reps if cfg["lifetime"] else (args.power_reps if name.startswith("power") else args.reps)
        if os.path.exists(os.path.join(TRACE_DIR, name + ".npz")) and not args.force:
            continue
        nch = max(1, reps // args.chunk)
        for ch in range(nch):
            tasks.append((name, cfg, reps // nch + (1 if ch < reps % nch else 0), ch))
    # slow cells first
    tasks.sort(key=lambda t: -(t[1]["lam"] * (4 if t[1]["lifetime"] else 1)))
    print(f"{len(tasks)} tasks over {len({t[0] for t in tasks})} cells, {args.workers} workers", flush=True)
    acc: dict[str, list] = {}
    need = {}
    for t in tasks:
        need[t[0]] = need.get(t[0], 0) + 1
    t0 = time.time()
    ctx = get_context("fork")
    with ctx.Pool(args.workers, maxtasksperchild=50) as pool:
        for res in pool.imap_unordered(_task, tasks):
            acc.setdefault(res["name"], []).append(res)
            if len(acc[res["name"]]) == need[res["name"]]:
                parts = sorted(acc.pop(res["name"]), key=lambda x: x["chunk"])
                rows, fc, ev3, off_p, off_f = [], [], [], 0, 0
                metas = []
                for pt in parts:
                    rw = pt["rows"].copy()
                    if len(rw):
                        rw[:, 0] += off_p
                        for col in (9, 10, 11):
                            m = rw[:, col] >= 0
                            rw[m, col] += off_f
                    e3 = pt["evl3"].copy()
                    e3[:, 0] += off_p
                    rows.append(rw)
                    fc.append(pt["fc"])
                    ev3.append(e3)
                    off_p += len(pt["evl3"])
                    off_f += len(pt["fc"])
                    metas.append(pt["meta"])
                meta = {k: float(np.mean([m[k] for m in metas])) for k in metas[0]}
                np.savez_compressed(os.path.join(TRACE_DIR, res["name"] + ".npz"), rows=np.concatenate(rows),
                                    fc=np.concatenate(fc), evl3=np.concatenate(ev3),
                                    meta=json.dumps(meta), cfg=json.dumps(parts[0].get("cfg", {})))
                print(f"[{time.time() - t0:7.0f}s] done {res['name']} ({sum(p['sec'] for p in parts):.0f} cpu-s)",
                      flush=True)


def load(name):
    z = np.load(os.path.join(TRACE_DIR, name + ".npz"))
    return dict(rows=z["rows"], fc=z["fc"].astype(np.float64), evl3=z["evl3"], meta=json.loads(str(z["meta"])))


def summarize(args):
    allc = cells()
    res = {}
    for path in sorted(glob.glob(os.path.join(TRACE_DIR, "*.npz"))):
        name = os.path.basename(path)[:-4]
        if name not in allc:
            continue
        cfg = dict(BASE)
        cfg.update(allc[name])
        res[name] = summarize_cell(name, cfg, load(name), grid=True)
    nulls = {k: v for k, v in res.items() if k.startswith(("null_subset", "null_own", "null_driftneg", "stress",
                                                            "life"))}
    # the worst case (money null: drift+ is not a money null)
    worst = max(nulls.items(), key=lambda kv: kv[1]["design_no_r"]["pass"]) if nulls else None
    rules = sorted({k for v in nulls.values() for k in v.get("grid_no_r", {})})
    worst_by_rule = {}
    for rule in rules:
        vals = [(v["grid_no_r"][rule][0], v["grid_no_r"][rule][1], k) for k, v in nulls.items()
                if rule in v.get("grid_no_r", {}) and not k.startswith("life")]
        if vals:
            m = max(vals)
            worst_by_rule[rule] = {"worst_fp": m[0], "se": m[1], "cell": m[2]}
    worst_life = {}
    for rule in rules:
        vals = [(v["grid_no_r"][rule][0], v["grid_no_r"][rule][1], k) for k, v in nulls.items()
                if rule in v.get("grid_no_r", {}) and k.startswith("life")]
        if vals:
            m = max(vals)
            worst_life[rule] = {"worst_fp": m[0], "se": m[1], "cell": m[2]}
    power = {k: v for k, v in res.items() if k.startswith("power")}
    pow_by_rule = {}
    for rule in rules:
        xs = [v["grid_no_r"][rule][0] for k, v in power.items() if rule in v.get("grid_no_r", {})
              and k.startswith("power_base")]
        if xs:
            pow_by_rule[rule] = round(float(np.mean(xs)), 4)
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "B": B, "skew": [SKEW_N, SKEW_B],
           "base": BASE, "worst_mix": WORST, "SFE_NS": SFE_NS, "cells": res,
           "worst_case": ({"cell": worst[0], **worst[1]["design_no_r"]} if worst else None),
           "worst_by_rule_40_sessions": worst_by_rule, "worst_by_rule_lifetime": worst_life,
           "mean_power_base_by_rule": pow_by_rule}
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"wrote {OUT_JSON}: {len(res)} cells")


def report(args):
    d = json.load(open(OUT_JSON))
    c = d["cells"]

    def f(name, key="design_no_r"):
        v = c.get(name)
        if not v:
            return "    --    "
        x = v[key]
        return f"{100 * x['pass']:5.2f}+-{100 * x['se']:.2f}"

    print("FP, design as specified (no r condition = conservative), within 40 sessions; [hybrid-look share]")
    for null in ("subset", "own", "driftneg", "driftpos"):
        for lam in (85, 30, 13, 8):
            cols = []
            for rho in ("00", "05", "15", "30"):
                nm = f"null_{null}_{lam}_r{rho}"
                h = c.get(nm, {}).get("design_no_r", {}).get("by_hybrid")
                cols.append(f"{f(nm)} [{100 * h:4.2f}]" if h is not None else f(nm))
            print(f"  {null:9s} {lam:3d}: " + " | ".join(cols))
    print("STRESS (rho_day 0.30 unless the worst mix)")
    for st in ("gref30", "gref60", "add05", "res05", "thin", "left", "persist", "ar20", "ar40", "worst"):
        print(f"  {st:8s}: " + " | ".join(f"{lam}: {f(f'stress_{st}_{lam}')}" for lam in (85, 30, 13, 8)))
    print("LIFETIME (all 24 looks)")
    for lf in ("subset", "worst"):
        print(f"  {lf:8s}: " + " | ".join(f"{lam}: {f(f'life_{lf}_{lam}')}" for lam in (85, 30, 13, 8)))
    print("WORST:", d["worst_case"])
    print("POWER: P(promoted within 40 sessions) / median session among promoted / median overall; EVL-3 today")
    for kind in ("base", "r00", "worst"):
        for lam in (85, 30, 13, 8):
            parts = []
            for e in (30, 60, 100):
                v = c.get(f"power_{kind}_{lam}_{e}")
                if not v:
                    parts.append("--")
                    continue
                x, t = v["design_no_r"], v["evl3_with_r"]
                parts.append(f"{e}bp {100 * x['pass']:5.1f}% med {x['median_session']} all {x['median_session_all']}"
                             f" (hyb {100 * x['by_hybrid']:.1f}%) | EVL3 {100 * t['pass']:5.1f}% med {t['median_session']}")
            print(f"  {kind:5s} {lam:3d}: " + " || ".join(parts))
    print("RULE GRID: worst FP (40 sessions | lifetime) and mean power over power_base cells")
    for rule, w in sorted(d["worst_by_rule_40_sessions"].items()):
        lw = d["worst_by_rule_lifetime"].get(rule, {})
        print(f"  {rule}: {100 * w['worst_fp']:5.2f} ({w['cell']}) | {100 * lw.get('worst_fp', float('nan')):5.2f} "
              f"({lw.get('cell')}) | power {d['mean_power_base_by_rule'].get(rule)}")


def adjust(args):
    """The minimum threshold change for FP <= 15% (and <= 8%) at the worst plausible case, all looks included.
    Plausible nulls: every null_subset/null_own/null_driftneg cell, every stress cell except AR(1) 0.4 (reported, judged
    implausible for day-to-day persistence of residual day shocks), every lifetime cell. driftpos is not a money null."""
    d = json.load(open(OUT_JSON))
    c = d["cells"]
    plaus = [k for k in c if k.startswith(("null_subset", "null_own", "null_driftneg", "stress", "life"))
             and not k.startswith("stress_ar40")]
    rules = sorted(c[plaus[0]]["grid_no_r"])
    res = []
    for rule in rules:
        w = max((c[k]["grid_no_r"][rule][0], c[k]["grid_no_r"][rule][1], k) for k in plaus)
        w40 = max((c[k]["grid_no_r"][rule][0], k) for k in plaus if not k.startswith("life"))
        a40 = max((c[k]["grid_no_r"][rule][0], k) for k in c if k.startswith("stress_ar40"))
        pw = [c[k]["grid_no_r"][rule][0] for k in c if k.startswith("power_base")]
        res.append((rule, w, w40, a40, float(np.mean(pw))))
    out = {}
    for cap in (0.15, 0.08):
        ok = [x for x in res if x[1][0] <= cap]
        ok2 = [x for x in res if x[1][0] + 2 * x[1][1] <= cap]
        best = max(ok, key=lambda x: x[4]) if ok else None
        best2 = max(ok2, key=lambda x: x[4]) if ok2 else None
        out[str(cap)] = {"best_point": best, "best_2se": best2}
        print(f"cap {cap}: best (point) {best}\n          best (+2 SE) {best2}")
    design = [x for x in res if x[0] == "S7|aE0.008|aL0.010"][0]
    print("design:", design)
    pw = {}
    for rule in ("S7|aE0.008|aL0.010", "S7|aE0.008|aL0.008", "S7|aE0.008|aL0.006", "S7|aE0.002|aL0.004",
                 "S7|aE0.006|aL0.004"):
        row = {}
        for kind in ("base", "r00", "worst"):
            for lam in (85, 30, 13, 8):
                for e in (30, 60, 100):
                    v = c.get(f"power_{kind}_{lam}_{e}")
                    if v:
                        row[f"{kind}_{lam}_{e}"] = v["grid_no_r"][rule]
        pw[rule] = row
    out["power_by_rule"] = pw
    out["all"] = res
    with open(OUT_JSON.replace(".json", "_adjust.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    for rule, row in pw.items():
        print(rule)
        for kind in ("base", "worst"):
            for lam in (85, 30, 13, 8):
                print(f"  {kind} {lam:3d}: " + " | ".join(
                    f"{e}bp {100 * row[f'{kind}_{lam}_{e}'][0]:5.1f}% med {row[f'{kind}_{lam}_{e}'][2]}"
                    for e in (30, 60, 100)))


def test(args):
    cfg = dict(BASE)
    cfg.update(lam=30, sessions=8)
    r = np.random.default_rng(1)
    P = Program(r, cfg)
    for _ in range(6):
        P.step(True)
    x = P.arrays()
    T = math.fsum(x["a"])
    for V in ("V1", "V2"):
        M, Q, U, Bd, W = hybrid_parts(x, V, 0.01)
        tot = math.fsum(np.concatenate([M, Q, U, Bd]).tolist())
        assert abs(tot - T) < 1e-12, (V, tot, T)
    f = np.array([0.0] * 5 + [0.5] * 15)
    assert alpha_hybrid(f, 0.008) == 0.005, alpha_hybrid(f, 0.008)
    assert alpha_plain(np.array([0.0] * 7 + [0.5] * 13), 0.010, 0.010) == 0.006
    t0 = time.time()
    for lam in (85, 30, 13, 8):
        c2 = dict(BASE)
        c2.update(lam=lam)
        t1 = time.time()
        o = simulate(c2, 6, 7)
        print(lam, f"{(time.time() - t1) / 6:.3f}s/program", o["meta"], len(o["rows"]), "looks", len(o["fc"]), "fc")
    c2 = dict(WORST)
    c2.update({k: v for k, v in BASE.items() if k not in WORST})
    c2.update(lam=85, edge=100.0)
    t1 = time.time()
    o = simulate(c2, 6, 7)
    print("worst+100bp", f"{(time.time() - t1) / 6:.3f}s/program", o["meta"], len(o["rows"]), len(o["fc"]))
    print("identity ok; total", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "summarize", "test", "report", "adjust"))
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--life-reps", type=int, default=2000)
    ap.add_argument("--power-reps", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=250)
    ap.add_argument("--cells", default=".")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"run": run, "summarize": summarize, "test": test, "report": report, "adjust": adjust}[a.cmd](a)

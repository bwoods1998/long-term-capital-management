#!/usr/bin/env python
"""calib_judge.py: the JUDGE's calibration record for PREREG-EVL-6 (SYNTHETIC DATA ONLY).

Nothing here reads the live lane: no events.sqlite, no live.sqlite, no boxrun.py, no market data, no price, no
return, no look, no band. Every number comes from the generator below, chosen blind to the lane's results.

WHY THIS FILE EXISTS. The three designs of wf_560ee5dd-ef8 were calibrated on three different generators, each
missing a risk another found: calib_within.py had day-level left skew with factor momentum (AR 0.10 on the day shock)
but no persistent family drift; calib_evalue.py had the persistent drift (AR 0.97) but no crash days and no day-shock
momentum; calib_strata.py had day-shock momentum up to AR 0.40. PREREG-EVL-6 is ADDITIONAL to PREREG-EVL-3's screen
(the captain's A91: "today's screen stays as a path ... the per-program FP of both paths together is accounted"), so
its false-positive rate is the UNION of both paths on the same data. This file runs, on ONE generator holding every
one of those risks at once, (i) PREREG-EVL-3's screen exactly as registered (minus its skew check, which only
tightens: its FP here is an upper bound), (ii) the PREREG-EVL-6 candidate on a grid of its constants, and (iii) their
union, per program, at every look.

THE CANDIDATE (PREREG-EVL-6, "SB-SEQ"), per program version, counting only blocks after its own start (LAG = the
sessions PREREG-EVL-3's path has already seen when PREREG-EVL-6 registers: 3 for the nine version 2 programs and
PREREG-EVL-4's three, 0 for PREREG-EVL-5's three and every later birth):
  block s = the s-th entry session holding >= 1 event; B_s = mean a of its events; S = blocks so far.
  p = one-sided sign-flip p of mean(B - m0) > 0: exact over all 2^S sign vectors for S <= 16
      (#{v : sum v |B - m0| >= sum (B - m0) - S 1e-12} / 2^S), else (1 + #{b : ... - 1e-12}) / (1 + B_MC) over
      B_MC sign vectors (nested across looks here; the registered rule draws a fresh seed per look: the size of each
      look is the same).
  a look at EVERY session that adds a block, S_min <= S <= S_max, with >= 30 events and >= 30 distinct issuers;
  it crosses when p <= c / S; PASS = crosses AND mean a > 0 AND mean r > 0 [AND, the "full" guard set, for a READ
  program its mean block value > its control's over the same sessions AND the issuer-block sign-flip p <= 0.10].
PREREG-EVL-3 (the "old" path, from the program's own session 1): look k at the first close with >= N_k events
(60 ... 2250), >= 40 issuers, >= 8 blocks (thresholds reached together are one look); PASS when the session-block
p <= 0.018 AND the issuer-block p <= 0.018 AND mean a > 0 AND mean r > 0 AND (READ) block mean > control's.

THE GENERATOR (vectorized over R replicates; one replicate = one READ program and its same-window family control):
  U = 3000 issuers, 11 sectors, Zipf(0.8) popularity, sigma_i log-uniform 1%-10% a session, 3 style factors
  (loadings N((.2, -.1, .2), .5^2)), 5-session cooldown per issuer, one hot sector (x4 weight) on half the sessions.
  control events a session ~ Poisson(nbar / 0.30 x Gamma(3, 1/3)); READ = each control event w.p. 0.30.
  a = mu_family + D_t + h_t (c_t + s_sector,t + beta . f_t + sigma_i e_it) + jump + tau_i + skill [READ], floor -1;
  r = a + b_t, b_t ~ N(4 bp, 1%).
  c_t = sd_c z_t, z_t = phi_day z_{t-1} + sqrt(1 - phi_day^2) eps_t (factor momentum), eps_t unit variance:
        't3' (symmetric t3), 'crash' (5% of sessions N(-3, 1), else N(m, s): skew -1.6), 'crashx' (3% at -4.5),
        'skew' (two-piece t3 1.4/0.6); sd_c^2 = rho_day / (1 - rho_day) x V0 (rho_day = Var(c) / event variance).
  D_t = persistent family drift, AR(1) drift_rho with stationary sd drift_sd (READ and control alike).
  e_it unit t3 (two-piece 1.4/0.6 in the 'evskew' shapes); jumps +-30% w.p. 0.5%, 50% down ('sym') or 80% down
  ('left'), mean-compensated; h_t vol regime exp(x - .09), x AR(.9) sd .3; tau_i optional persistent issuer effect.
NULLS: N3 knife edge (skill 60 bp, mu_family -60 bp: READ's mean is exactly 0 and it beats its control by 42 bp, so
the control condition gives no protection: the intersection-union worst case and the FP of a program WITHOUT a
control); N1 no skill (READ a random subset, mean 0); N2+ no skill with +30 bp common drift (the "beats its control"
false pass, not an owner FP: mean a > 0).

Usage:  calib_judge.py pilot | run [--phase P] [--workers N] | report
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
SHM = os.environ.get("CALIB_SHM", "/dev/shm/calib-judge")
os.makedirs(SHM, exist_ok=True)

TIE = 1e-12
EXACT_S = 16
B_MC = 19_999
B_ISS = 4_999
B_ISS_G = 999                   # the guard's issuer sign-flip (level 0.10: resolution 0.001 is ample)
S_CAP = 300
Z_PRE = 1.0                      # below this z no grid c can cross (validated by `pilot`)
C_GRID = (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.125)
C_MAX = max(C_GRID)
S_MINS = (6, 7, 8)
S_MAXS = (40, 60, 120, 300)
M0S = (0.0, 0.0005, 0.0010, 0.0015, 0.0020)
ISS_NEED = 0.03                 # the issuer guard is computed wherever p(m0 = 0) <= this (every schedule searched)
LAGS = (0, 3)
GUARDS = ("abs", "full")   # abs: mean a > 0, mean r > 0; full: + beats its control + issuer p <= ISS_G
ISS_G = 0.10
NEW_MIN_EV, NEW_MIN_ISS = 30, 30
V2_NS = (60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250)
V2_MIN_ISS, V2_MIN_BLK, V2_ALPHA = 40, 8, 0.018
RETIRE_P = 0.05                 # PREREG-EVL-3 section 2's retirement: mean a < 0 and reversed p <= 0.05 at a held look
SECTOR_W = np.array([.22, .14, .12, .11, .09, .08, .07, .06, .04, .04, .03])
HORIZONS = (20, 40, 60, 120, 300)


@dataclasses.dataclass(frozen=True)
class Gen:
    nbar: float = 85.0
    p_read: float = 0.30
    shape_n: float = 3.0
    rho_day: float = 0.05
    U: int = 3000
    zipf_s: float = 0.8
    hot_p: float = 0.5
    hot_mult: float = 4.0
    sd_sector: float = 0.010
    sd_factor: float = 0.006
    beta_mean: tuple = (0.2, -0.1, 0.2)
    beta_sd: float = 0.5
    sig_lo: float = 0.01
    sig_hi: float = 0.10
    day: str = "t3"
    phi_day: float = 0.10
    ev_left: float = 1.0
    ev_right: float = 1.0
    jump_p: float = 0.005
    jump_size: float = 0.30
    jump_left: float = 0.5
    vol_sd: float = 0.30
    vol_rho: float = 0.90
    cooldown: int = 5
    issuer_tau: float = 0.0
    mu_family: float = 0.0
    drift_sd: float = 0.0
    drift_rho: float = 0.97
    skill: float = 0.0
    b_mu: float = 0.0004
    b_sd: float = 0.010

    def v0(self) -> float:
        es2 = (self.sig_hi ** 2 - self.sig_lo ** 2) / (2.0 * math.log(self.sig_hi / self.sig_lo))
        jv = self.jump_p * self.jump_size ** 2
        fv = sum(m * m + self.beta_sd ** 2 for m in self.beta_mean) * self.sd_factor ** 2
        return es2 + jv + self.sd_sector ** 2 + fv

    def sd_day(self) -> float:
        return math.sqrt(self.rho_day / (1.0 - self.rho_day) * self.v0()) if self.rho_day > 0 else 0.0


def _abs_mean_t(df):
    return (2.0 * math.sqrt(df) * math.gamma((df + 1) / 2) / (math.sqrt(math.pi) * (df - 1) * math.gamma(df / 2))
            / math.sqrt(df / (df - 2.0)))


def unit_t3(rng, size, left=1.0, right=1.0):
    x = rng.standard_t(3.0, size) / math.sqrt(3.0)
    if left != 1.0 or right != 1.0:
        x = np.where(x < 0, left * x, right * x)
        m1 = (right - left) * _abs_mean_t(3.0) / 2.0
        m2 = (left ** 2 + right ** 2) / 2.0
        x = (x - m1) / math.sqrt(m2 - m1 ** 2)
    return x


CRASH = {"crash": (0.05, 3.0), "crashx": (0.03, 4.5)}


def day_innov(rng, kind, R):
    if kind == "t3":
        return unit_t3(rng, R)
    if kind == "skew":
        return unit_t3(rng, R, 1.4, 0.6)
    p, k = CRASH[kind]
    m = p * k / (1 - p)
    s = math.sqrt((1 - p * (k * k + 1)) / (1 - p) - m * m)
    hit = rng.random(R) < p
    return np.where(hit, rng.normal(-k, 1.0, R), rng.normal(m, s, R))


# ------------------------------------------------------------------------------------------------ sign flips
_PAT: dict[int, np.ndarray] = {}
_SIGNS: np.ndarray | None = None


def _pat(S):
    if S not in _PAT:
        _PAT[S] = np.array(list(itertools.product((-1.0, 1.0), repeat=S)))
    return _PAT[S]


def _signs():
    global _SIGNS
    if _SIGNS is None:
        _SIGNS = np.where(np.random.default_rng(20261022).random((B_MC, S_CAP)) < 0.5, -1.0, 1.0)
    return _SIGNS


def signflip_p_rows(X, S):
    """One-sided sign-flip p of mean > 0 for each row of X (k x S, every row S values)."""
    T = X.sum(axis=1)
    A = np.abs(X)
    out = np.empty(X.shape[0])
    for lo in range(0, X.shape[0], 128):
        hi = min(lo + 128, X.shape[0])
        if S <= EXACT_S:
            M = _pat(S) @ A[lo:hi].T
            out[lo:hi] = np.count_nonzero(M >= (T[lo:hi] - S * TIE)[None, :], axis=0) / float(1 << S)
        else:
            M = _signs()[:, :S] @ A[lo:hi].T
            out[lo:hi] = (1 + np.count_nonzero(M >= (T[lo:hi] - TIE)[None, :], axis=0)) / (1.0 + B_MC)
    return out


def issuer_p(vals, flips):
    n = vals.size
    s = flips[:, :n] @ vals
    thr = math.fsum(vals) - n * TIE - 1e-9 * math.fsum(np.abs(vals))
    return (1 + int(np.count_nonzero(s >= thr))) / (1 + flips.shape[0])


SKEW_SAMPLES, SKEW_DRAWS, SKEW_STEP, SKEW_FLOOR = 1000, 1999, 0.002, 0.002


def skew_alpha(values, rng, flips, alpha=V2_ALPHA):
    """PREREG-EVL-1 section 7's skew check as screen.skew_check runs it for version 2 (start and cap 0.018): the values
    centred, SKEW_SAMPLES bootstrap samples, f(a) = share with mean > 0 and sign-flip p <= a over SKEW_DRAWS shared
    vectors; the first a on the grid 0.018, 0.016, ... (floor 0.002) with f(a) <= 0.018."""
    x = np.asarray(values, float)
    n = x.size
    x = x - x.mean()
    Xb = x[rng.integers(0, n, (SKEW_SAMPLES, n))]
    tot = Xb.sum(axis=1)
    pos = tot > 0
    if not pos.any():
        return alpha
    F = flips[:, :n]
    M = F @ Xb[pos].T
    cnt = np.count_nonzero(M >= (tot[pos] - n * TIE - 1e-9 * np.abs(Xb[pos]).sum(axis=1))[None, :], axis=0)
    pb = (1 + cnt) / (1.0 + F.shape[0])
    a = alpha
    while True:
        f = np.count_nonzero(pb <= a + TIE) / SKEW_SAMPLES
        if f <= alpha + TIE or a - SKEW_STEP < SKEW_FLOOR - 1e-12:
            return a
        a = round(a - SKEW_STEP, 6)


# ------------------------------------------------------------------------------------------------ one job
def simulate(g: Gen, R: int, T: int, seed: int, full_p: bool = False, old_skew: bool = True):
    """R programs over T sessions. Returns per-variant first-pass sessions (new path), the old path's first pass, and
    (full_p) the raw p arrays for the prefilter check."""
    rng = np.random.default_rng(seed)
    U = g.U
    sector = rng.choice(len(SECTOR_W), size=U, p=SECTOR_W)
    logw = -g.zipf_s * np.log(np.arange(1, U + 1))
    isig = np.exp(rng.uniform(math.log(g.sig_lo), math.log(g.sig_hi), (R, U)))
    beta = np.array(g.beta_mean)[None, None, :] + g.beta_sd * rng.standard_normal((R, U, 3))
    tau = None
    if g.issuer_tau > 0:
        tau = g.issuer_tau * rng.standard_normal((R, U))
        tau -= tau.mean(axis=1, keepdims=True)
    last = np.full((R, U), -10_000, np.int32)
    lvol = rng.standard_normal(R) * g.vol_sd
    D = rng.standard_normal(R) * g.drift_sd if g.drift_sd > 0 else np.zeros(R)
    z = day_innov(rng, g.day, R)
    sd_c = g.sd_day()
    jmean = g.jump_p * g.jump_size * (1.0 - 2.0 * g.jump_left)
    rate_c = g.nbar / g.p_read
    hot_add = math.log(g.hot_mult)
    rows = np.arange(R)
    iflips = np.where(np.random.default_rng(seed + 77_777).random((B_ISS, U)) < 0.5, -1.0, 1.0)
    gflips = iflips[:B_ISS_G]
    krng = np.random.default_rng(seed + 55_555)
    kflips = iflips[:SKEW_DRAWS]
    old_skews = 0
    # path state: L -> dict
    st = {}
    for L in LAGS:
        st[L] = {"X": np.zeros((R, S_CAP)), "S": np.zeros(R, np.int64), "ca": np.zeros(R), "cr": np.zeros(R),
                 "ne": np.zeros(R, np.int64), "isum": np.zeros((R, U)), "icnt": np.zeros((R, U), np.int64),
                 "niss": np.zeros(R, np.int64), "cbm": np.zeros(R), "ccm": np.zeros(R),
                 "P": {m0: np.full((R, T), np.nan) for m0 in M0S}, "PL": np.full((R, T), np.nan),
                 "neg": np.zeros((R, T), bool),
                 "Sat": np.zeros((R, T), np.int16), "abs": np.zeros((R, T), bool), "ctrl": np.zeros((R, T), bool),
                 "min": np.zeros((R, T), bool), "iss": np.zeros((R, T), bool), "has": np.zeros((R, T), bool),
                 "ne_t": np.zeros((R, T), np.int32), "niss_t": np.zeros((R, T), np.int32)}
    old_first = np.full(R, -1, np.int32)
    old_ret = np.full(R, -1, np.int32)
    old_j = np.zeros(R, np.int64)
    old_looks = 0
    for t in range(1, T + 1):
        ti = t - 1
        lvol = g.vol_rho * lvol + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R)
        h = np.exp(lvol - g.vol_sd ** 2)
        if g.drift_sd > 0:
            D = g.drift_rho * D + math.sqrt(1 - g.drift_rho ** 2) * g.drift_sd * rng.standard_normal(R)
        z = g.phi_day * z + math.sqrt(1 - g.phi_day ** 2) * day_innov(rng, g.day, R)
        c_day = sd_c * z
        s_sec = g.sd_sector * unit_t3(rng, (R, len(SECTOR_W)))
        f_fac = g.sd_factor * unit_t3(rng, (R, 3))
        b = g.b_mu + g.b_sd * rng.standard_normal(R)
        elig = (t - last) > g.cooldown
        n_el = elig.sum(axis=1)
        nC = np.minimum(rng.poisson(rate_c * rng.gamma(g.shape_n, 1.0 / g.shape_n, R)), n_el)
        nmax = int(nC.max())
        if nmax == 0:
            continue
        keys = logw[None, :] + rng.gumbel(size=(R, U))
        hot = np.where(rng.random(R) < g.hot_p, rng.integers(0, len(SECTOR_W), R), -1)
        keys += np.where(sector[None, :] == hot[:, None], hot_add, 0.0)
        keys[~elig] = -np.inf
        idx = np.argpartition(-keys, nmax - 1, axis=1)[:, :nmax] if nmax < U else np.tile(np.arange(U), (R, 1))
        kv = np.take_along_axis(keys, idx, axis=1)
        idx = np.take_along_axis(idx, np.argsort(-kv, axis=1), axis=1)
        mask = np.arange(nmax)[None, :] < nC[:, None]
        er = np.broadcast_to(rows[:, None], mask.shape)[mask]
        ei = idx[mask]
        last[er, ei] = t
        E = er.size
        sel = rng.random(E) < g.p_read
        noise = isig[er, ei] * unit_t3(rng, E, g.ev_left, g.ev_right)
        common = c_day[er] + s_sec[er, sector[ei]] + (beta[er, ei, :] * f_fac[er, :]).sum(axis=1)
        a = g.mu_family + D[er] + h[er] * (common + noise)
        if g.jump_p > 0:
            hit = rng.random(E) < g.jump_p
            sgn = np.where(rng.random(E) < g.jump_left, -1.0, 1.0)
            a = a + hit * sgn * g.jump_size - jmean
        if tau is not None:
            a = a + tau[er, ei]
        a = a + g.skill * sel
        a = np.maximum(a, -1.0)
        rr = a + b[er]
        pr, pi_, pa, prr = er[sel], ei[sel], a[sel], rr[sel]
        nP = np.bincount(pr, minlength=R)
        sP = np.bincount(pr, pa, R)
        sR = np.bincount(pr, prr, R)
        nCt = np.bincount(er, minlength=R)
        sC = np.bincount(er, a, R)
        has = nP > 0
        Bt = np.where(has, sP / np.maximum(nP, 1), 0.0)
        Ct = np.where(nCt > 0, sC / np.maximum(nCt, 1), 0.0)
        for L in LAGS:
            if t <= L:
                continue
            s = st[L]
            hr = np.nonzero(has)[0]
            s["X"][hr, s["S"][hr]] = Bt[hr]
            s["S"][hr] += 1
            s["ca"] += sP
            s["cr"] += sR
            s["ne"] += nP
            flat = pr * U + pi_
            isum = s["isum"].reshape(-1)
            icnt = s["icnt"].reshape(-1)
            new = icnt[flat] == 0
            np.add.at(isum, flat, pa)
            np.add.at(icnt, flat, 1)
            if new.any():
                s["niss"] += np.bincount(pr[new], minlength=R)
            s["cbm"] += np.where(has, Bt, 0.0)
            s["ccm"] += np.where(has, Ct, 0.0)
            S = s["S"]
            s["Sat"][:, ti] = np.minimum(S, 32767)
            s["has"][:, ti] = has
            s["ne_t"][:, ti] = s["ne"]
            s["niss_t"][:, ti] = s["niss"]
            s["abs"][:, ti] = (s["ca"] > 0) & (s["cr"] > 0)
            s["ctrl"][:, ti] = s["cbm"] > s["ccm"]
            s["min"][:, ti] = (s["ne"] >= NEW_MIN_EV) & (s["niss"] >= NEW_MIN_ISS)
            look = has & (S >= min(S_MINS)) & s["min"][:, ti]
            for m0 in M0S:
                Pm = s["P"][m0]
                cand = np.nonzero(look)[0]
                if cand.size == 0:
                    continue
                Pm[cand, ti] = 1.0
                # prefilter on z of (B - m0)
                for Sv in np.unique(S[cand]):
                    rs = cand[S[cand] == Sv]
                    Xv = s["X"][rs, :Sv] - m0
                    zz = Xv.sum(axis=1) / np.sqrt(np.maximum((Xv * Xv).sum(axis=1), 1e-300))
                    keep = rs if full_p else rs[zz >= Z_PRE]
                    if keep.size:
                        Xk = s["X"][keep, :Sv] - m0
                        Pm[keep, ti] = signflip_p_rows(Xk, int(Sv))
            # the lower tail (EVL-6 retirement: mean a < 0 and p(mean < 0) <= c / S)
            s["neg"][:, ti] = s["ca"] < 0
            cand = np.nonzero(look & s["neg"][:, ti])[0]
            if cand.size:
                s["PL"][cand, ti] = 1.0
                for Sv in np.unique(S[cand]):
                    rs = cand[S[cand] == Sv]
                    Xv = -s["X"][rs, :Sv]
                    zz = Xv.sum(axis=1) / np.sqrt(np.maximum((Xv * Xv).sum(axis=1), 1e-300))
                    keep = rs[zz >= Z_PRE]
                    if keep.size:
                        s["PL"][keep, ti] = signflip_p_rows(-s["X"][keep, :Sv], int(Sv))
            # issuer guard where any grid c could cross (m0 = 0 is the most liberal)
            P0 = s["P"][0.0][:, ti]
            need = np.nonzero(look & (P0 <= ISS_NEED + TIE) & s["abs"][:, ti])[0]
            for r in need:
                c = s["icnt"][r]
                nz = c > 0
                vals = s["isum"][r][nz] / c[nz]
                s["iss"][r, ti] = issuer_p(vals, gflips) <= ISS_G
        # the old path (PREREG-EVL-3) on lag-0 data
        s0 = st[0]
        cand = np.nonzero(has & (old_j < len(V2_NS)))[0]
        for r in cand:
            j = int(old_j[r])
            n = int(s0["ne"][r])
            if n < V2_NS[j] or s0["niss"][r] < V2_MIN_ISS or s0["S"][r] < V2_MIN_BLK:
                continue
            reached = [i for i in range(j, len(V2_NS)) if n >= V2_NS[i]]
            old_j[r] = reached[-1] + 1
            old_looks += 1
            if old_ret[r] < 0 and s0["ca"][r] < 0:
                Sv = int(s0["S"][r])
                if float(signflip_p_rows(-s0["X"][r:r + 1, :Sv], Sv)[0]) <= RETIRE_P + TIE:
                    old_ret[r] = t
                    continue
            if old_first[r] >= 0 or old_ret[r] >= 0:
                continue
            if not (s0["abs"][r, ti] and s0["ctrl"][r, ti]):
                continue
            p_s = s0["P"][0.0][r, ti]
            if math.isnan(p_s):
                Sv = int(s0["S"][r])
                p_s = float(signflip_p_rows(s0["X"][r:r + 1, :Sv], Sv)[0])
            if not p_s <= V2_ALPHA + TIE:
                continue
            c = s0["icnt"][r]
            nz = c > 0
            vals = s0["isum"][r][nz] / c[nz]
            p_i = issuer_p(vals, iflips)
            if not p_i <= V2_ALPHA + TIE:
                continue
            if old_skew:   # PREREG-EVL-1 section 7's skew check, one per test, only tightens
                Sv = int(s0["S"][r])
                a_s = skew_alpha(s0["X"][r, :Sv], krng, kflips)
                a_i = skew_alpha(vals, krng, kflips)
                old_skews += 1
                if not (p_s <= a_s + TIE and p_i <= a_i + TIE):
                    continue
            old_first[r] = t
    # ---- raw per-session arrays (every schedule and threshold is evaluated offline by report_judge.py)
    out = {"old": old_first.astype(np.int16), "old_ret": old_ret.astype(np.int16)}
    for L in LAGS:
        s = st[L]
        out[f"L{L}_Sat"] = s["Sat"]
        out[f"L{L}_has"] = s["has"]
        out[f"L{L}_ne"] = s["ne_t"]
        out[f"L{L}_niss"] = s["niss_t"]
        for g_ in ("abs", "ctrl", "iss", "neg", "min"):
            out[f"L{L}_{g_}"] = s[g_]
        for m0 in M0S:
            out[f"L{L}_P{m0}"] = s["P"][m0].astype(np.float32)
        out[f"L{L}_PL"] = s["PL"].astype(np.float32)
    info = {"old_looks": old_looks, "old_skews": old_skews, "mean_read_n": float(st[0]["ne"].mean() / T)}
    if full_p:
        info["P"] = {L: st[L]["P"][0.0] for L in LAGS}
        info["Sat"] = {L: st[L]["Sat"] for L in LAGS}
    return out, info


# ------------------------------------------------------------------------------------------------ cells
RATES = (85, 30, 13, 8, 3)
RHOS = (0.0, 0.05, 0.15, 0.30)
N3 = dict(skill=0.0060, mu_family=-0.0060)
SHAPES = {"sym": dict(day="t3", jump_left=0.5), "dayskew": dict(day="crash", jump_left=0.5),
          "evskew": dict(day="t3", ev_left=1.4, ev_right=0.6, jump_left=0.8),
          "both": dict(day="crash", ev_left=1.4, ev_right=0.6, jump_left=0.8)}


def cells(phase):
    out = []
    if phase == "main":
        for sh in ("sym", "dayskew", "both"):
            kw = SHAPES[sh]
            for rho in RHOS:
                for nb in RATES:
                    for dname, dkw in (("nodrift", {}), ("AR10", dict(drift_sd=0.0010)), ("AR20", dict(drift_sd=0.0020))):
                        out.append((f"N3|{sh}|{dname}", dict(nbar=nb, rho_day=rho, **N3, **kw, **dkw), 2000, 120))
    elif phase == "stress":
        for rho in (0.0, 0.05):
            for nb in RATES:
                for sh in ("sym", "both"):
                    out.append((f"N3|{sh}|AR30", dict(nbar=nb, rho_day=rho, **N3, **SHAPES[sh], drift_sd=0.0030),
                                2000, 120))
                out.append(("N3|sym|AR20r.99", dict(nbar=nb, rho_day=rho, **N3, drift_sd=0.0020, drift_rho=0.99),
                            2000, 120))
        for nb in RATES:
            out.append(("N3|both|phi.25", dict(nbar=nb, rho_day=0.30, **N3, **SHAPES["both"], phi_day=0.25), 2000, 120))
            out.append(("N3|both|phi.40", dict(nbar=nb, rho_day=0.30, **N3, **SHAPES["both"], phi_day=0.40), 2000, 120))
            out.append(("N3|crashx|leftx", dict(nbar=nb, rho_day=0.30, **N3, day="crashx", ev_left=1.4, ev_right=0.6,
                                                jump_left=0.9, jump_p=0.01), 2000, 120))
            out.append(("N3|sym|issuer1%", dict(nbar=nb, rho_day=0.05, **N3, issuer_tau=0.010), 2000, 120))
            out.append(("N3|evskew|AR20", dict(nbar=nb, rho_day=0.15, **N3, **SHAPES["evskew"], drift_sd=0.0020),
                        2000, 120))
    elif phase == "noskill":
        for sh in ("sym", "both"):
            for rho in (0.0, 0.05, 0.30):
                for nb in RATES:
                    for dname, dkw in (("nodrift", {}), ("AR20", dict(drift_sd=0.0020))):
                        out.append((f"N1|{sh}|{dname}", dict(nbar=nb, rho_day=rho, **SHAPES[sh], **dkw), 1000, 120))
        for nb in RATES:
            out.append(("N2+30|sym|nodrift", dict(nbar=nb, rho_day=0.05, mu_family=0.0030), 1000, 60))
    elif phase == "life":
        # slow programs over a PREREG-EVL-3 lifetime (its looks run to 2,250 events: ~280 sessions at 8 a session)
        for nb in (13, 8):
            for lab, kw in (("N3|sym|AR20", dict(drift_sd=0.0020)), ("N3|both|AR20", dict(**SHAPES["both"],
                                                                                            drift_sd=0.0020)),
                            ("N3|dayskew|nodrift", dict(**SHAPES["dayskew"]))):
                for rho in (0.0, 0.30):
                    out.append((lab, dict(nbar=nb, rho_day=rho, **N3, **kw), 2000, 300))
    elif phase == "power":
        for mu in (0.0030, 0.0060, 0.0100):
            for rho in RHOS:
                for nb in RATES:
                    out.append((f"P{int(mu * 1e4)}|sym|nodrift", dict(nbar=nb, rho_day=rho, skill=mu), 1000, 60))
    elif phase == "power120":
        for mu in (0.0060, 0.0100):
            for rho in (0.05, 0.15):
                for nb in (13, 8, 3):
                    out.append((f"P{int(mu * 1e4)}|sym|nodrift", dict(nbar=nb, rho_day=rho, skill=mu), 1000, 120))
    elif phase == "pilot":
        out = [("N3|both|nodrift", dict(nbar=85, rho_day=0.30, **N3, **SHAPES["both"]), 200, 60),
               ("N3|sym|AR20", dict(nbar=8, rho_day=0.0, **N3, drift_sd=0.0020), 200, 60),
               ("P100|sym|nodrift", dict(nbar=85, rho_day=0.05, skill=0.01), 200, 60)]
    return out


def _job(args):
    lab, kw, R, T, seed, old_skew = args
    t0 = time.time()
    out, info = simulate(Gen(**kw), R, T, seed, old_skew=old_skew)
    path = os.path.join(SHM, f"job{seed}.npz")
    np.savez_compressed(path, **out)
    return lab, json.dumps(kw, sort_keys=True), R, T, seed, path, info, time.time() - t0


SEEDS = {"main": 81_000_000, "stress": 82_000_000, "noskill": 83_000_000, "life": 84_000_000, "power": 85_000_000,
         "power120": 86_000_000, "pilot": 89_000_000}


def run(phase, workers, chunk=500):
    from multiprocessing import get_context
    jobs = []
    seed = SEEDS[phase]
    for lab, kw, R, T in cells(phase):
        for c in range(0, R, chunk):
            seed += 1
            jobs.append((lab, kw, min(chunk, R - c), T, seed, not phase.startswith("power")))
    jobs.sort(key=lambda j: -j[1]["nbar"] * j[3])
    t0 = time.time()
    index = os.path.join(HERE, f"calib_judge.{phase}.index.jsonl")
    with get_context("fork").Pool(workers) as pool, open(index, "w") as fh:
        for k, (lab, kws, R, T, sd, path, info, secs) in enumerate(pool.imap_unordered(_job, jobs), 1):
            fh.write(json.dumps({"cell": lab, "gen": json.loads(kws), "R": R, "T": T, "seed": sd, "path": path,
                                 "info": info, "secs": round(secs, 1)}) + "\n")
            fh.flush()
            if k % 10 == 0 or k == len(jobs):
                print(f"{phase}: {k}/{len(jobs)} jobs, {time.time() - t0:.0f}s", flush=True)


def pilot():
    """Prefilter check (full p at every look: the smallest z among p <= C_MAX/S) and timing."""
    for lab, kw, R, T in cells("pilot"):
        t0 = time.time()
        out, info = simulate(Gen(**kw), R, T, 123, full_p=True)
        dt = time.time() - t0
        zmin = math.inf
        g = Gen(**kw)
        for L in LAGS:
            P = info["P"][L]
            Sat = info["Sat"][L]
            ok = ~np.isnan(P) & (P <= C_MAX / np.maximum(Sat, 1) + TIE)
            n_ok = int(ok.sum())
            print(f"  {lab} L{L}: {n_ok} (rep, look) pairs with p <= C_MAX/S")
        # recompute z on the fly is not stored: re-run with prefilter and compare first passes
        out2, _ = simulate(g, R, T, 123, full_p=False)
        diff = sum(int((out[k] != out2[k]).sum()) for k in out)
        print(f"{lab}: {dt:.1f}s for R={R} T={T} (full p); variants whose first pass differs with the z >= {Z_PRE} "
              f"prefilter: {diff}; old path passes {int((out['old'] >= 0).sum())}; old looks {info['old_looks']}",
              flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pilot", "run"])
    ap.add_argument("--phase", default="main")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--chunk", type=int, default=500)
    a = ap.parse_args()
    if a.cmd == "pilot":
        pilot()
    else:
        run(a.phase, a.workers, a.chunk)

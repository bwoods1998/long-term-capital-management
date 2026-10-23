#!/usr/bin/env python
"""calib_final.py: PREREG-EVL-6's FINAL calibration (SYNTHETIC DATA ONLY).

Nothing here reads the live lane: no events.sqlite, no live.sqlite, no market data, no price, no return, no look, no
band. Every number comes from the generator below.

THE GENERATOR is the judge's (evl6/judge/calib_judge.py `simulate`), copied here so this file runs alone, with every
risk it held unchanged (crash days, left-skewed events, a persistent family drift AR(0.97), day-shock momentum,
issuer repeats, sector clusters, a volatility regime, t(3) names, +-30% jumps), and these additions:
  - phi_day (the day shock's AR) is a cell parameter: 0.10, 0.15, 0.20 in the plausible grid (captain's D1), 0.25 and
    0.40 as stresses;
  - check 1's count coupling (cnt_kappa: the control's count x exp(kappa min(|eps_t|, 4))) with the knife edge set on
    MONEY weights min(n_s, CAP) (mw_knife), check 2's count-residual coupling (kappa) and volatility-coupled drift
    (lam), and check 2's crash10 days;
  - D4: the sign-flip values are y_s = min(n_s, CAP) x (B_s - 0.0010), CAP = 14 (A99's Probe cap); the lower tail q
    uses -min(n_s, CAP) x B_s; a PASS also needs the top-CAP events of every block (the program's own ranking: here
    the control's draw order, popularity plus Gumbel noise, uninformative about returns) to have mean a > 0 and mean
    r > 0 over the record;
  - D2: a run ends at its 60th block; RUN 2 starts with block 61 and is computed on its own record (run2 cells).
Everything a candidate rule needs is stored per (program, session): the block count S, whether a block was added,
the minimums, the guards, the issuer guard, p (the weighted margin test), q (the weighted lower tail); a schedule and
an alpha(S) are evaluated offline (search_final.py), exactly as the judge's search_judge.py does.

MONTE CARLO SHORTCUTS (each leaves a rule's level unchanged, as in the judge's file): S <= 16 exact over all 2^S sign
vectors; S >= 17 over 19,999 fixed sign vectors (a valid Monte Carlo p at each look); the issuer guard over 999
vectors; p computed only where z = sum y / sqrt(sum y^2) >= 1.0 and the guards hold (validated by `pilot`: no
decision at any alpha up to 0.020 changes on full computation); q only where the mean a < 0 and z(-y) >= 1.0.

Usage: calib_final.py pilot | run --phase P [--workers N]
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
ARR = os.environ.get("FINAL_ARR", os.path.join(HERE, "arrays"))
os.makedirs(ARR, exist_ok=True)

TIE = 1e-12
EXACT_S = 16
B_MC = 19_999
B_ISS_G = 999
S_RUN = 60                      # a run's horizon (blocks)
CAP = 14                        # D4: this file's Probe open cap (A99)
MARGIN = 0.0010
Z_PRE = 1.0
ALPHA_MAX = 0.020               # the most liberal alpha of any candidate: the issuer guard is computed where p <= this
MIN_EV, MIN_ISS, MIN_BLK = 30, 30, 6
ISS_G = 0.10
SECTOR_W = np.array([.22, .14, .12, .11, .09, .08, .07, .06, .04, .04, .03])


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
    # additions (checks 1 and 2): count coupling, money-weighted knife edge, count-residual coupling, vol-coupled drift
    cnt_kappa: float = 0.0
    mw_knife: int = 0
    kappa: float = 0.0
    lam: float = 0.0

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


CRASH = {"crash": (0.05, 3.0), "crashx": (0.03, 4.5), "crash10": (0.10, 2.5)}


def day_innov(rng, kind, R):
    """(eps, crash-hit) of unit variance."""
    if kind == "t3":
        return unit_t3(rng, R), np.zeros(R, bool)
    if kind == "skew":
        return unit_t3(rng, R, 1.4, 0.6), np.zeros(R, bool)
    p, k = CRASH[kind]
    m = p * k / (1 - p)
    s = math.sqrt((1 - p * (k * k + 1)) / (1 - p) - m * m)
    hit = rng.random(R) < p
    return np.where(hit, rng.normal(-k, 1.0, R), rng.normal(m, s, R)), hit


def money_knife_mu(g: Gen) -> float:
    """check 1's money-weighted knife edge at cap g.mw_knife: mu_family such that the program's mean a weighted by
    min(n_t, cap) is exactly 0 when counts follow the day shock (numerical, fixed seed)."""
    rr = np.random.default_rng(434343)
    M = 4_000_000
    eps, _ = day_innov(rr, g.day, M)
    mult = np.exp(g.cnt_kappa * np.minimum(np.abs(eps), 4.0))
    mult = mult / mult.mean()
    n = rr.poisson(g.nbar * mult * rr.gamma(g.shape_n, 1.0 / g.shape_n, M))
    w = np.minimum(n, g.mw_knife).astype(float)
    w_ev = float((w * eps).sum() / w.sum())
    Eh = math.exp(-g.vol_sd ** 2 / 2.0)
    return -g.skill - Eh * g.sd_day() * math.sqrt(1 - g.phi_day ** 2) * w_ev


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
        _SIGNS = np.where(np.random.default_rng(20261023).random((B_MC, S_RUN)) < 0.5, -1.0, 1.0)
    return _SIGNS


def signflip_p_rows(Y, S):
    """One-sided sign-flip p of mean > 0 for each row of Y (k x S): exact for S <= 16 (count / 2^S), else
    (1 + count) / (1 + B_MC); count = #{s : sum s|y| >= sum y - S 1e-12} (ties against the program)."""
    T = Y.sum(axis=1)
    A = np.abs(Y)
    out = np.empty(Y.shape[0])
    for lo in range(0, Y.shape[0], 128):
        hi = min(lo + 128, Y.shape[0])
        thr = (T[lo:hi] - S * TIE)[None, :]
        if S <= EXACT_S:
            M = _pat(S) @ A[lo:hi].T
            out[lo:hi] = np.count_nonzero(M >= thr, axis=0) / float(1 << S)
        else:
            M = _signs()[:, :S] @ A[lo:hi].T
            out[lo:hi] = (1 + np.count_nonzero(M >= thr, axis=0)) / (1.0 + B_MC)
    return out


def issuer_p(vals, flips):
    n = vals.size
    s = flips[:, :n] @ vals
    thr = math.fsum(vals) - n * TIE - 1e-9 * math.fsum(np.abs(vals))
    return (1 + int(np.count_nonzero(s >= thr))) / (1 + flips.shape[0])


# ------------------------------------------------------------------------------------------------ one record
class Record:
    """One run's record: blocks from `start` (0-based global block index) on."""

    def __init__(self, R, T, U, start, unweighted):
        self.start = start
        self.X = np.zeros((R, S_RUN + 1))
        self.W = np.zeros((R, S_RUN + 1))
        self.S = np.zeros(R, np.int64)
        self.ca = np.zeros(R); self.cr = np.zeros(R); self.ne = np.zeros(R, np.int64)
        self.ta = np.zeros(R); self.tr = np.zeros(R)
        self.isum = np.zeros((R, U)); self.icnt = np.zeros((R, U), np.int64); self.niss = np.zeros(R, np.int64)
        self.cbm = np.zeros(R); self.ccm = np.zeros(R)
        self.Sat = np.zeros((R, T), np.int16)
        self.has = np.zeros((R, T), bool)
        self.mn = np.zeros((R, T), bool)
        self.g = np.zeros((R, T), bool)
        self.iss = np.zeros((R, T), bool)
        self.neg = np.zeros((R, T), bool)
        self.P = np.full((R, T), np.nan, np.float32)
        self.Q = np.full((R, T), np.nan, np.float32)
        self.unweighted = unweighted
        if unweighted:
            self.gu = np.zeros((R, T), bool)
            self.issu = np.zeros((R, T), bool)
            self.Pu = np.full((R, T), np.nan, np.float32)

    def arrays(self, suffix):
        out = {f"Sat{suffix}": self.Sat, f"has{suffix}": self.has, f"mn{suffix}": self.mn, f"g{suffix}": self.g,
               f"iss{suffix}": self.iss, f"neg{suffix}": self.neg, f"P{suffix}": self.P, f"Q{suffix}": self.Q}
        if self.unweighted:
            out.update({f"gu{suffix}": self.gu, f"issu{suffix}": self.issu, f"Pu{suffix}": self.Pu})
        return out


def _pvals(rows, S, Y, P):
    """p of each row's first S values of Y into P (rows grouped by S by the caller)."""
    if rows.size == 0:
        return
    P[rows] = signflip_p_rows(Y, S)


def simulate(g: Gen, R: int, T: int, seed: int, run2: bool = False, unweighted: bool = False,
             full_p: bool = False):
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
    z, _ = day_innov(rng, g.day, R)
    sd_c = g.sd_day()
    jmean = g.jump_p * g.jump_size * (1.0 - 2.0 * g.jump_left)
    rate_c = g.nbar / g.p_read
    hot_add = math.log(g.hot_mult)
    rows = np.arange(R)
    gflips = np.where(np.random.default_rng(seed + 77_777).random((B_ISS_G, U)) < 0.5, -1.0, 1.0)
    mu_family = money_knife_mu(g) if g.mw_knife else g.mu_family
    Emult = 1.0
    if g.cnt_kappa > 0:
        rr = np.random.default_rng(424242)
        e_, _ = day_innov(rr, g.day, 2_000_000)
        Emult = float(np.exp(g.cnt_kappa * np.minimum(np.abs(e_), 4.0)).mean())
    recs = [Record(R, T, U, 0, unweighted)]
    if run2:
        recs.append(Record(R, T, U, S_RUN, unweighted))
    Sglob = np.zeros(R, np.int64)          # global blocks so far (before this session)
    mw_num = mw_den = ew_num = ew_den = 0.0
    for t in range(1, T + 1):
        ti = t - 1
        lvol = g.vol_rho * lvol + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R)
        h = np.exp(lvol - g.vol_sd ** 2)
        if g.drift_sd > 0:
            D = g.drift_rho * D + math.sqrt(1 - g.drift_rho ** 2) * g.drift_sd * rng.standard_normal(R)
        eps, _ = day_innov(rng, g.day, R)
        z = g.phi_day * z + math.sqrt(1 - g.phi_day ** 2) * eps
        c_day = sd_c * z
        s_sec = g.sd_sector * unit_t3(rng, (R, len(SECTOR_W)))
        f_fac = g.sd_factor * unit_t3(rng, (R, 3))
        b = g.b_mu + g.b_sd * rng.standard_normal(R)
        elig = (t - last) > g.cooldown
        n_el = elig.sum(axis=1)
        Gt = rng.gamma(g.shape_n, 1.0 / g.shape_n, R)
        mult = np.exp(g.cnt_kappa * np.minimum(np.abs(eps), 4.0)) / Emult if g.cnt_kappa > 0 else 1.0
        nC = np.minimum(rng.poisson(rate_c * mult * Gt), n_el)
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
        a = mu_family + D[er] + h[er] * (common + noise)
        if g.kappa:
            a = a + g.kappa * (1.0 / g.shape_n - (Gt[er] - 1.0))
        if g.lam:
            a = a - g.lam * (h[er] - 1.0)
        if g.jump_p > 0:
            hit = rng.random(E) < g.jump_p
            sgn = np.where(rng.random(E) < g.jump_left, -1.0, 1.0)
            a = a + hit * sgn * g.jump_size - jmean
        if tau is not None:
            a = a + tau[er, ei]
        a = a + g.skill * sel
        a = np.maximum(a, -1.0)
        rr_ = a + b[er]
        # the program's rank of each of its events inside its session (draw order: popularity + Gumbel noise)
        cs = np.cumsum(sel)
        first = np.r_[True, er[1:] != er[:-1]]
        start_idx = np.maximum.accumulate(np.where(first, np.arange(E), 0))
        pos = cs - (cs[start_idx] - sel[start_idx])        # 1-based rank among the row's program events
        top = sel & (pos <= CAP)
        pr, pi_, pa, prr = er[sel], ei[sel], a[sel], rr_[sel]
        nP = np.bincount(pr, minlength=R)
        sP = np.bincount(pr, pa, R)
        sR = np.bincount(pr, prr, R)
        tA = np.bincount(er[top], a[top], R)
        tR = np.bincount(er[top], rr_[top], R)
        nCt = np.bincount(er, minlength=R)
        sC = np.bincount(er, a, R)
        has = nP > 0
        Bt = np.where(has, sP / np.maximum(nP, 1), 0.0)
        Ct = np.where(nCt > 0, sC / np.maximum(nCt, 1), 0.0)
        wt = np.minimum(nP, CAP)
        mw_num += float((wt * Bt).sum()); mw_den += float(wt.sum())
        ew_num += float(sP.sum()); ew_den += float(nP.sum())
        for rec in recs:
            act = has & (Sglob >= rec.start)
            hr = np.nonzero(act)[0]
            if hr.size:
                ok = rec.S[hr] < S_RUN + 1
                hr2 = hr[ok]
                rec.X[hr2, rec.S[hr2]] = Bt[hr2]
                rec.W[hr2, rec.S[hr2]] = nP[hr2]
            rec.S[hr] += 1
            am = act.astype(float)
            rec.ca += sP * am; rec.cr += sR * am; rec.ne += nP * act
            rec.ta += tA * am; rec.tr += tR * am
            pm = act[pr]
            if pm.any():
                flat = pr[pm] * U + pi_[pm]
                isum = rec.isum.reshape(-1)
                icnt = rec.icnt.reshape(-1)
                new = icnt[flat] == 0
                np.add.at(isum, flat, pa[pm])
                np.add.at(icnt, flat, 1)
                if new.any():
                    rec.niss += np.bincount(pr[pm][new], minlength=R)
            rec.cbm += np.where(act, Bt, 0.0)
            rec.ccm += np.where(act, Ct, 0.0)
            S = rec.S
            rec.Sat[:, ti] = np.minimum(S, 32767)
            rec.has[:, ti] = act
            mn = (rec.ne >= MIN_EV) & (rec.niss >= MIN_ISS) & (S >= MIN_BLK)
            rec.mn[:, ti] = mn
            ctrl = rec.cbm > rec.ccm
            gd = (rec.ca > 0) & (rec.cr > 0) & (rec.ta > 0) & (rec.tr > 0) & ctrl
            rec.g[:, ti] = gd
            rec.neg[:, ti] = rec.ca < 0
            look = act & mn & (S <= S_RUN)
            # p: the weighted margin test, where the guards hold
            cand = np.nonzero(look & (gd | full_p))[0]
            if cand.size:
                rec.P[cand, ti] = 1.0
                for Sv in np.unique(S[cand]):
                    rs = cand[S[cand] == Sv]
                    Y = np.minimum(rec.W[rs, :Sv], CAP) * (rec.X[rs, :Sv] - MARGIN)
                    zz = Y.sum(axis=1) / np.sqrt(np.maximum((Y * Y).sum(axis=1), 1e-300))
                    keep = np.ones(rs.size, bool) if full_p else zz >= Z_PRE
                    if keep.any():
                        rec.P[rs[keep], ti] = signflip_p_rows(Y[keep], int(Sv))
            # q: the weighted lower tail, where the mean a < 0
            cand = np.nonzero(look & (rec.ca < 0))[0]
            if cand.size:
                rec.Q[cand, ti] = 1.0
                for Sv in np.unique(S[cand]):
                    rs = cand[S[cand] == Sv]
                    Y = -np.minimum(rec.W[rs, :Sv], CAP) * rec.X[rs, :Sv]
                    zz = Y.sum(axis=1) / np.sqrt(np.maximum((Y * Y).sum(axis=1), 1e-300))
                    keep = np.ones(rs.size, bool) if full_p else zz >= Z_PRE
                    if keep.any():
                        rec.Q[rs[keep], ti] = signflip_p_rows(Y[keep], int(Sv))
            # the issuer guard where a candidate could pass
            need = np.nonzero(look & gd & (rec.P[:, ti] <= ALPHA_MAX + TIE))[0]
            for r in need:
                c = rec.icnt[r]
                nz = c > 0
                rec.iss[r, ti] = issuer_p(rec.isum[r][nz] / c[nz], gflips) <= ISS_G
            if rec.unweighted:   # the judge's rule: unweighted values, no top-CAP guard
                gu = (rec.ca > 0) & (rec.cr > 0) & ctrl
                rec.gu[:, ti] = gu
                cand = np.nonzero(look & gu)[0]
                if cand.size:
                    rec.Pu[cand, ti] = 1.0
                    for Sv in np.unique(S[cand]):
                        rs = cand[S[cand] == Sv]
                        Y = rec.X[rs, :Sv] - MARGIN
                        zz = Y.sum(axis=1) / np.sqrt(np.maximum((Y * Y).sum(axis=1), 1e-300))
                        keep = zz >= Z_PRE
                        if keep.any():
                            rec.Pu[rs[keep], ti] = signflip_p_rows(Y[keep], int(Sv))
                need = np.nonzero(look & gu & (rec.Pu[:, ti] <= ALPHA_MAX + TIE))[0]
                for r in need:
                    c = rec.icnt[r]
                    nz = c > 0
                    rec.issu[r, ti] = issuer_p(rec.isum[r][nz] / c[nz], gflips) <= ISS_G
        Sglob += has
    out = recs[0].arrays("")
    if run2:
        out.update(recs[1].arrays("_2"))
    info = {"mean_read_n": float(recs[0].ne.mean() / T), "mu_family": mu_family,
            "mw_mean_a_bp": 1e4 * mw_num / max(mw_den, 1e-300), "ew_mean_a_bp": 1e4 * ew_num / max(ew_den, 1e-300)}
    return out, info


# ------------------------------------------------------------------------------------------------ cells
RATES = (85, 30, 13, 8, 3)
N3 = dict(skill=0.0060, mu_family=-0.0060)
SHAPES = {"sym": dict(day="t3", jump_left=0.5), "dayskew": dict(day="crash", jump_left=0.5),
          "evskew": dict(day="t3", ev_left=1.4, ev_right=0.6, jump_left=0.8),
          "both": dict(day="crash", ev_left=1.4, ev_right=0.6, jump_left=0.8)}
DRIFTS = (("nodrift", {}), ("AR10", dict(drift_sd=0.0010)), ("AR20", dict(drift_sd=0.0020)))


def phis(rho):
    return (0.10,) if rho == 0 else (0.10, 0.15, 0.20)


def null_grid(R_knife, R_noskill):
    """THE PLAUSIBLE GRID (captain's D1): rho_day 0, 0.05, 0.15; phi_day 0.10, 0.15, 0.20 (rho > 0); symmetric days,
    crash days, crash days + left-skewed events; drift 0, 10, 20 bp (AR 0.97); five rates; the knife edge N3; plus
    left-skewed events alone at 20 bp and rho 0.15, issuer effects 1%, and the no-skill null N1."""
    out = []
    for sh in ("sym", "dayskew", "both"):
        for rho in (0.0, 0.05, 0.15):
            for phi in phis(rho):
                for dname, dkw in DRIFTS:
                    for nb in RATES:
                        out.append((f"N3|{sh}|{dname}|phi{phi:.2f}", dict(nbar=nb, rho_day=rho, phi_day=phi, **N3,
                                                                           **SHAPES[sh], **dkw), R_knife, 120))
    for phi in (0.10, 0.15, 0.20):
        for nb in RATES:
            out.append((f"N3|evskew|AR20|phi{phi:.2f}", dict(nbar=nb, rho_day=0.15, phi_day=phi, **N3,
                                                              **SHAPES["evskew"], drift_sd=0.0020), R_knife, 120))
    for nb in RATES:
        out.append(("N3|sym|issuer1%|phi0.10", dict(nbar=nb, rho_day=0.05, **N3, issuer_tau=0.010), R_knife, 120))
    for sh in ("sym", "both"):
        for rho in (0.0, 0.05):
            for phi in phis(rho):
                for dname, dkw in (DRIFTS[0], DRIFTS[2]):
                    for nb in RATES:
                        out.append((f"N1|{sh}|{dname}|phi{phi:.2f}", dict(nbar=nb, rho_day=rho, phi_day=phi,
                                                                           **SHAPES[sh], **dkw), R_noskill, 120))
    return out


def stress_grid(R):
    """STRESSES (named, not binding) and the checks' other structures (reported)."""
    out = []
    for sh in ("sym", "dayskew", "both"):
        for dname, dkw in DRIFTS:
            for nb in RATES:
                out.append((f"S|rho.30|N3|{sh}|{dname}", dict(nbar=nb, rho_day=0.30, **N3, **SHAPES[sh], **dkw), R, 120))
    for rho in (0.0, 0.05):
        for nb in RATES:
            for sh in ("sym", "both"):
                out.append((f"S|AR30|N3|{sh}", dict(nbar=nb, rho_day=rho, **N3, **SHAPES[sh], drift_sd=0.0030), R, 120))
            out.append(("S|AR20r.99|N3|sym", dict(nbar=nb, rho_day=rho, **N3, drift_sd=0.0020, drift_rho=0.99), R, 120))
    for nb in RATES:
        out.append(("S|phi.25|N3|both|AR20", dict(nbar=nb, rho_day=0.15, phi_day=0.25, **N3, **SHAPES["both"],
                                                   drift_sd=0.0020), R, 120))
        out.append(("S|phi.25|N3|dayskew|nodrift", dict(nbar=nb, rho_day=0.15, phi_day=0.25, **N3,
                                                         **SHAPES["dayskew"]), R, 120))
        out.append(("S|phi.25|N3|sym|AR20", dict(nbar=nb, rho_day=0.15, phi_day=0.25, **N3, drift_sd=0.0020), R, 120))
        out.append(("S|phi.40|rho.30|N3|both", dict(nbar=nb, rho_day=0.30, phi_day=0.40, **N3, **SHAPES["both"]), R, 120))
        out.append(("S|crashx|leftx|rho.30", dict(nbar=nb, rho_day=0.30, **N3, day="crashx", ev_left=1.4, ev_right=0.6,
                                                   jump_left=0.9, jump_p=0.01), R, 120))
    for nb in (85, 30, 8):
        out.append(("S|crash10+evskew|AR20", dict(nbar=nb, rho_day=0.15, **N3, day="crash10", ev_left=1.4,
                                                   ev_right=0.6, jump_left=0.8, drift_sd=0.0020), R, 120))
        out.append(("S|lam.005|N3|both|AR20", dict(nbar=nb, rho_day=0.15, **N3, **SHAPES["both"], drift_sd=0.0020,
                                                    lam=0.005), R, 120))
    out.append(("S|crash10|nodrift", dict(nbar=85, rho_day=0.15, **N3, day="crash10", jump_left=0.5), R, 120))
    # check 1: the drift at shorter persistence with the judge's monthly yardstick (about +-3.8% a month)
    for nb in (85, 30):
        out.append(("X|AR.85m28|N3|both", dict(nbar=nb, rho_day=0.15, **N3, **SHAPES["both"], drift_sd=0.0028,
                                                drift_rho=0.85), R, 120))
    out.append(("X|AR.70m37|N3|both", dict(nbar=85, rho_day=0.15, **N3, **SHAPES["both"], drift_sd=0.0037,
                                            drift_rho=0.70), R, 120))
    out.append(("X|AR.90m25|N3|both", dict(nbar=85, rho_day=0.15, **N3, **SHAPES["both"], drift_sd=0.0025,
                                            drift_rho=0.90), R, 120))
    # check 1: counts follow the size of the day shock, the knife edge set on MONEY weights min(n, 14)
    for nb in (30, 8, 3):
        out.append(("X|cnt.3|MW14|dayskew|nodrift", dict(nbar=nb, rho_day=0.15, **N3, **SHAPES["dayskew"],
                                                          cnt_kappa=0.3, mw_knife=CAP), R, 120))
        out.append(("X|cnt.3|MW14|both|AR20", dict(nbar=nb, rho_day=0.15, **N3, **SHAPES["both"], drift_sd=0.0020,
                                                    cnt_kappa=0.3, mw_knife=CAP), R, 120))
    # check 2: a session at twice its normal intensity carries a lower residual (event-weighted mean 0)
    for nb in (3, 5):
        for kp in (0.01, 0.02):
            out.append((f"X|kappa{kp}|N3|sym", dict(nbar=nb, rho_day=0.15, **N3, kappa=kp), R, 120))
    out.append(("X|kappa0.01|N3|both|AR20", dict(nbar=3, rho_day=0.15, **N3, **SHAPES["both"], drift_sd=0.0020,
                                                  kappa=0.01), R, 120))
    out.append(("X|kappa0.01|N3|both|AR20", dict(nbar=8, rho_day=0.15, **N3, **SHAPES["both"], drift_sd=0.0020,
                                                  kappa=0.01), R, 120))
    out.append(("X|N2+30|sym", dict(nbar=85, rho_day=0.05, mu_family=0.0030), R, 60))
    out.append(("X|N2+30|sym", dict(nbar=8, rho_day=0.05, mu_family=0.0030), R, 60))
    return out


def power_grid(R, mus=(0.0060, 0.0100), rhos=(0.05,), T_hi=64, T_lo=120):
    out = []
    for mu in mus:
        for rho in rhos:
            for nb in RATES:
                out.append((f"P{int(round(mu * 1e4))}|sym|nodrift", dict(nbar=nb, rho_day=rho, skill=mu), R,
                            T_hi if nb >= 30 else T_lo))
    return out


SEEDS = {"s1null": 111_000_000, "s1power": 112_000_000, "s2null": 113_000_000, "s2power": 114_000_000,
         "stress": 115_000_000, "s3null": 116_000_000, "pilot": 119_000_000, "s2extra": 117_000_000}


def cells(phase):
    if phase == "s1null":
        return [c + ({},) for c in null_grid(1000, 1000)]
    if phase == "s1power":
        return [c + ({},) for c in power_grid(1000)]
    if phase == "s2power":
        return [c + ({"run2": True},) for c in power_grid(2000, mus=(0.0030, 0.0060, 0.0100), rhos=(0.0, 0.05, 0.15),
                                                           T_hi=120, T_lo=120)]
    if phase == "stress":
        return [c + ({"unweighted": True},) for c in stress_grid(1000)]
    if phase.startswith("s2null") or phase.startswith("s3null") or phase == "s2extra":
        spec = json.load(open(os.path.join(HERE, f"{phase}.cells.json")))
        return [(c["lab"], c["gen"], c["R"], c.get("T", 120), c.get("opts", {})) for c in spec]
    if phase == "pilot":
        return [("N3|both|AR20|phi0.20", dict(nbar=85, rho_day=0.15, phi_day=0.20, **N3, **SHAPES["both"],
                                               drift_sd=0.0020), 200, 64, {}),
                ("N3|sym|nodrift|phi0.10", dict(nbar=3, rho_day=0.05, **N3), 300, 120, {}),
                ("N3|both|AR20|phi0.20", dict(nbar=8, rho_day=0.15, phi_day=0.20, **N3, **SHAPES["both"],
                                               drift_sd=0.0020), 300, 120, {}),
                ("P60|sym|nodrift", dict(nbar=13, rho_day=0.05, skill=0.006), 200, 64, {})]
    raise ValueError(phase)


def _job(args):
    phase, lab, kw, R, T, seed, opts = args
    t0 = time.time()
    out, info = simulate(Gen(**kw), R, T, seed, run2=opts.get("run2", False), unweighted=opts.get("unweighted", False))
    path = os.path.join(ARR, f"{phase}_{seed}.npz")
    np.savez_compressed(path, **out)
    return lab, json.dumps(kw, sort_keys=True), R, T, seed, path, info, time.time() - t0, opts


def run(phase, workers, chunk=500):
    from multiprocessing import get_context
    jobs = []
    seed = SEEDS[phase.split(".")[0]] + (int(phase.split(".")[1]) * 10_000 if "." in phase else 0)
    for lab, kw, R, T, opts in cells(phase):
        for c in range(0, R, chunk):
            seed += 1
            jobs.append((phase, lab, kw, min(chunk, R - c), T, seed, opts))
    jobs.sort(key=lambda j: -j[2]["nbar"] * j[4])
    t0 = time.time()
    index = os.path.join(HERE, f"calib_final.{phase}.index.jsonl")
    with get_context("fork").Pool(workers) as pool, open(index, "w") as fh:
        for k, (lab, kws, R, T, sd, path, info, secs, opts) in enumerate(pool.imap_unordered(_job, jobs), 1):
            fh.write(json.dumps({"phase": phase, "cell": lab, "gen": json.loads(kws), "R": R, "T": T, "seed": sd,
                                 "path": path, "info": info, "opts": opts, "secs": round(secs, 1)}) + "\n")
            fh.flush()
            if k % 20 == 0 or k == len(jobs):
                print(f"{phase}: {k}/{len(jobs)} jobs, {time.time() - t0:.0f}s", flush=True)


def pilot():
    """The prefilter and guard shortcut against full computation: every first pass at every alpha on a grid up to
    ALPHA_MAX, the 20-look and 19-look schedules, must be identical; and timing."""
    sys.path.insert(0, HERE)
    import search_final as SF
    alphas = [0.003, 0.006, 0.008, 0.010, 0.012, 0.014, 0.016, 0.018, 0.020]
    for lab, kw, R, T, opts in cells("pilot"):
        g = Gen(**kw)
        t0 = time.time()
        out, info = simulate(g, R, T, 4242, full_p=False)
        dt1 = time.time() - t0
        t0 = time.time()
        full, _ = simulate(g, R, T, 4242, full_p=True)
        dt2 = time.time() - t0
        # in `full`, P is computed wherever a look is eligible; the guards are applied in the evaluation
        diffs = 0
        for start in (6, 7):
            for a in alphas:
                rule = SF.Rule(start, ((60, a),))
                f1 = SF.first_pass(out, "", rule)[0]
                f2 = SF.first_pass(full, "", rule)[0]
                diffs += int((f1 != f2).sum())
        print(f"{lab} n{kw['nbar']}: {dt1:.1f}s (prefiltered) {dt2:.1f}s (full p) for R={R} T={T}; first passes that "
              f"differ over {2 * len(alphas)} rules: {diffs}; info {json.dumps(info)}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pilot", "run"])
    ap.add_argument("--phase", default="s1null")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=500)
    a = ap.parse_args()
    if a.cmd == "pilot":
        pilot()
    else:
        run(a.phase, min(a.workers, 8), a.chunk)

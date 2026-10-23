#!/usr/bin/env python
"""calib_r2.py: PREREG-EVL-10's synthetic calibration of the READER-2 CONSUMER programs under PREREG-EVL-6's FROZEN
screen (design-reader2 lens). SYNTHETIC DATA ONLY: nothing here reads the lane's store, the House, the gateway, any
price, return, look, band or mark.

THE SCREEN, AS FROZEN (docs/prereg/PREREG-EVL-6.md sha256 0f67f94e..., tag prereg-evl-6): looks at the first close at
which the run's record holds >= S_k blocks and the minimums (30 TRADABLE events, 30 issuers, 6 blocks), S_k = 22, 25,
30, 35, 40, 50, 60 (thresholds reached together are one look); alpha 0.020 (S 22-30), 0.006 (31-40), 0.001 (41-60);
values y_s = min(n_s, 14) x (B_s - 10 bp); RETIRE first (mean a < 0 and q <= alpha + 1e-12); PASS: p <= alpha, mean a
> 0, mean r > 0, the top-14 means > 0 (every pick here: K = 8 <= 14), the mean block value beats the control's (the
consumer's R2 SET record), the issuer-block guard p_I <= 0.10; a run ends at its 60th block and run 2 starts with the
next block. The sign-flip p, its 19,999 fixed vectors, the z >= 1 prefilter and the issuer guard are calib_final.py's
own functions (imported from the frozen copy in evl6_frozen/, sha256 e35e649d...), the day shapes calib_v2.py's
(d2991caa...).

THE CONSUMER (what is new here): each session the R2 SET holds N_t candidates (one per issuer, drawn by popularity as
the frozen generator draws a control's events: Zipf(0.8) plus Gumbel noise, a hot sector on half the sessions);
N_t ~ Poisson(Nbar x Gamma(3, 1/3)) (count CV 0.58), optionally x exp(0.3 min(|eps_t|, 4)) / E (counts that follow
the day, D14); each candidate passes the consumer's fixed filter with probability 0.6; the consumer takes the TOP K = 8
passing candidates by its READER KEY that it does not hold within 5 sessions. Per event a = mu + D_t + h_t (l_i c_t +
s_sector + beta_i . f_t + sigma_i e_it) + jump + tau_i + alpha_i (the frozen generator's terms, l_i = 1 unless named),
r = a + b_t. alpha_i is the event's TRUE news value (sd_alpha x N(0,1)) in the alternatives and in the knife null; the
key is k = c x alpha / sd_alpha + sqrt(1 - c^2) x noise (c the reader's information), or a null key below.

NULLS (every one has a money-weighted mean a of the picks of exactly zero by construction, mu set numerically):
  N1  the key is noise;
  NK  THE KNIFE: the key is informative (c 0.5, sd_alpha 0.6%) so the picks beat their R2 SET record, but mu offsets
      their edge exactly, so the control guard never protects;
  NV  the key prefers VOLATILE names (0.6 z(log sigma) + 0.8 noise) and the day shock loads on sigma (l_i = sigma_i /
      the universe mean, clipped 0.3-3): the picks' blocks carry bigger, skewed day shocks;
  NS  the key prefers BIG NEWS (30% of candidates; key 0.9 flag + 0.45 noise), whose returns are 1.5x noisier, more
      left-skewed (two-piece t(3) 1.6 / 0.4) with 3x the jumps (90% down), mean-compensated;
  NI  the key prefers some ISSUERS persistently (0.7 u_i + 0.7 noise) while issuers carry persistent effects of 1%
      (independent of u): the record concentrates on few names.
CELLS: PREREG-EVL-6's widened grid's worst corner (t(3)-body crash days clustered in high volatility, left-skewed
events, rho_day 0.15, phi_day 0.20, drift 10 / 20 bp at AR 0.97), the base model (symmetric t(3) days, rho_day 0.05,
phi_day 0.10, no drift), Nbar 26 / 12 / 5 (5 with counts that follow the day).

Usage: calib_r2.py run --phase null|power|pilot [--workers 4] [--R 4000]
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "evl6_frozen"))
os.environ.setdefault("FINAL_ARR", "/dev/shm/swing-reader2/arr_cf")
os.environ.setdefault("V2_ARR", "/dev/shm/swing-reader2/arr_v2")
import calib_final as CF  # noqa: E402
import calib_v2 as V2  # noqa: E402

LOOKS = (22, 25, 30, 35, 40, 50, 60)
S_RUN, CAP, MARGIN, TIE = 60, 14, 0.0010, 1e-12
MIN_EV, MIN_ISS, MIN_BLK = 30, 30, 6
K = 8
COOLDOWN = 5
NCAP = 64


def z_pass(f):
    """The standard-normal key's threshold that a share f of candidates passes (the informative filter)."""
    import statistics
    return float(statistics.NormalDist().inv_cdf(1.0 - f))


def alpha_of(S):
    return np.where(S <= 30, 0.020, np.where(S <= 40, 0.006, 0.001))


@dataclasses.dataclass(frozen=True)
class Cell:
    nbar: float = 26.0
    f_pass: float = 0.6
    null: str = "alt"           # alt | N1 | NK | NV | NS | NI | coarse (the v1-like comparator)
    c: float = 0.5              # reader information (alt, NK, coarse)
    sd_alpha: float = 0.006
    mu_set: float = -0.0014     # the R2 set's after-cost mean a in the alternatives (the replay's ~14 bp at liquid)
    day: str = "crasht3cl"
    rho_day: float = 0.15
    phi_day: float = 0.20
    ev: str = "skew"            # sym | skew
    drift_sd: float = 0.0010
    cnt: bool = False
    issuer_tau: float = 0.0
    k: int = 8                  # picks a decision
    finf: bool = False          # the filter is the reader's own (pass when the key is in its top f share) not random

    def gen(self) -> V2.Gen2:
        kw = dict(day=self.day, rho_day=self.rho_day, phi_day=self.phi_day, drift_sd=self.drift_sd,
                  cnt_kappa=0.3 if self.cnt else 0.0, issuer_tau=self.issuer_tau)
        if self.ev == "skew":
            kw.update(ev_left=1.4, ev_right=0.6, jump_left=0.8)
        else:
            kw.update(jump_left=0.5)
        return V2.Gen2(**kw)


def _two_piece(rng, size, left, right):
    return CF.unit_t3(rng, size, left, right)


def draw_session(rng, cell, g, R, U, logw, sector, isig, upref, lvol_x, eps, Emult, hot_add, last=None, t=None):
    """One session's candidates for R reps: (mask, idx, key, alpha, passf, bigflag, nC)."""
    mult = np.exp(0.3 * np.minimum(np.abs(eps), 4.0)) / Emult if cell.cnt else 1.0
    Gt = rng.gamma(3.0, 1.0 / 3.0, R)
    nC = np.minimum(rng.poisson(cell.nbar * mult * Gt), NCAP)
    nmax = int(nC.max())
    if nmax == 0:
        return None
    keys = logw[None, :] + rng.gumbel(size=(R, U))
    hot = np.where(rng.random(R) < 0.5, rng.integers(0, len(CF.SECTOR_W), R), -1)
    keys += np.where(sector[None, :] == hot[:, None], hot_add, 0.0)
    idx = np.argpartition(-keys, nmax - 1, axis=1)[:, :nmax]
    mask = np.arange(nmax)[None, :] < nC[:, None]
    rows = np.arange(R)[:, None]
    xi = rng.standard_normal((R, nmax))
    noise = rng.standard_normal((R, nmax))
    big = np.zeros((R, nmax), bool)
    if cell.null in ("alt", "NK", "coarse"):
        alpha = cell.sd_alpha * xi
        key = cell.c * xi + math.sqrt(1 - cell.c ** 2) * noise
        if cell.null == "coarse":           # a v1-like 3-level score, ties by popularity (the larger name first)
            q = np.where(key > 1.645, 2.0, np.where(key > 0.385, 1.0, 0.0))
            key = q + 1e-3 * np.take_along_axis(keys, idx, axis=1) / 100.0
    else:
        alpha = np.zeros((R, nmax))
        if cell.null == "N1":
            key = noise
        elif cell.null == "NV":
            ls = np.log(isig[rows, idx])
            zs = (ls - math.log(math.sqrt(0.01 * 0.10))) / (math.log(10.0) / math.sqrt(12.0))
            key = 0.6 * zs + 0.8 * noise
        elif cell.null == "NS":
            big = rng.random((R, nmax)) < 0.3
            key = 0.9 * big + 0.45 * noise
        elif cell.null == "NI":
            key = 0.7 * upref[rows, idx] + 0.7 * noise
        else:
            raise ValueError(cell.null)
    if cell.finf:
        passf = (key > z_pass(cell.f_pass)) & mask
    else:
        passf = (rng.random((R, nmax)) < cell.f_pass) & mask
    if last is not None:
        passf &= (t - last[rows, idx]) > COOLDOWN
    return mask, idx, key, alpha, passf, big, nC


def pick(key, passf, k=K):
    """The top k passing candidates by key, as a boolean array."""
    kk = np.where(passf, key, -np.inf)
    n = kk.shape[1]
    kth = min(k, n)
    order = np.argsort(-kk, axis=1)[:, :kth]
    sel = np.zeros_like(passf)
    rows = np.arange(kk.shape[0])[:, None]
    sel[rows, order] = True
    return sel & passf


def knife_mu(cell, seed=4242, R=20000, T=60):
    """mu that makes the MONEY-WEIGHTED (min(n_s, 14) = n_s here) mean a of the picks exactly zero: minus the
    weighted mean over picks of alpha + h_t l_i sd_c sqrt(1 - phi^2) eps_t (V2.knife_mu2's day term with the picks'
    loadings), by a large pilot of the same law: the candidate count, the filter, the key and the picks as simulate()
    draws them; a candidate's sigma drawn as an issuer's (log-uniform 1-10%), which is all the knife needs of it."""
    if cell.null in ("alt", "coarse"):
        return cell.mu_set
    g = cell.gen()
    rng = np.random.default_rng(seed)
    Emult = V2.count_norm(g) if cell.cnt else 1.0
    sd_c = g.sd_day()
    lvol = rng.standard_normal(R) * g.vol_sd
    lmean = (g.sig_hi - g.sig_lo) / math.log(g.sig_hi / g.sig_lo)      # E[sigma] of the log-uniform law
    num = den = 0.0
    for _ in range(T):
        lvol = g.vol_rho * lvol + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R)
        h = np.exp(lvol - g.vol_sd ** 2)
        eps, _ = V2.day_innov2(rng, g, R, lvol)
        mult = np.exp(0.3 * np.minimum(np.abs(eps), 4.0)) / Emult if cell.cnt else 1.0
        nC = np.minimum(rng.poisson(cell.nbar * mult * rng.gamma(3.0, 1.0 / 3.0, R)), NCAP)
        nmax = int(nC.max())
        if nmax == 0:
            continue
        mask = np.arange(nmax)[None, :] < nC[:, None]
        xi = rng.standard_normal((R, nmax)); noise = rng.standard_normal((R, nmax))
        sig = np.exp(rng.uniform(math.log(g.sig_lo), math.log(g.sig_hi), (R, nmax)))
        alpha = np.zeros((R, nmax))
        if cell.null == "NK":
            alpha = cell.sd_alpha * xi
            key = cell.c * xi + math.sqrt(1 - cell.c ** 2) * noise
        elif cell.null == "NV":
            zs = (np.log(sig) - math.log(math.sqrt(g.sig_lo * g.sig_hi))) / (math.log(g.sig_hi / g.sig_lo) / math.sqrt(12.0))
            key = 0.6 * zs + 0.8 * noise
        elif cell.null == "NS":
            key = 0.9 * (rng.random((R, nmax)) < 0.3) + 0.45 * noise
        else:
            key = noise
        if cell.finf:
            passf = (key > z_pass(cell.f_pass)) & mask
        else:
            passf = (rng.random((R, nmax)) < cell.f_pass) & mask
        sel = pick(key, passf, cell.k)
        l = np.clip(sig / lmean, 0.3, 3.0) if cell.null == "NV" else 1.0
        term = alpha + (h * sd_c * math.sqrt(1 - g.phi_day ** 2) * eps)[:, None] * l
        num += float((term * sel).sum())
        den += float(sel.sum())
    return -num / max(den, 1.0)


class Run:
    def __init__(self, R, U, start):
        self.start = start
        self.X = np.zeros((R, S_RUN + 1)); self.W = np.zeros((R, S_RUN + 1))
        self.S = np.zeros(R, np.int64)
        self.ca = np.zeros(R); self.cr = np.zeros(R); self.ne = np.zeros(R, np.int64)
        self.isum = np.zeros((R, U)); self.icnt = np.zeros((R, U), np.int64); self.niss = np.zeros(R, np.int64)
        self.cbm = np.zeros(R); self.ccm = np.zeros(R)
        self.nxt = np.zeros(R, np.int64)
        self.done = np.zeros(R, bool)          # passed, retired or ended
        self.passed = np.full(R, 10 ** 6); self.retired = np.full(R, 10 ** 6); self.ended = np.full(R, 10 ** 6)


def simulate(cell: Cell, R: int, T: int, seed: int, mu: float):
    g = cell.gen()
    rng = np.random.default_rng(seed)
    U = g.U
    sector = rng.choice(len(CF.SECTOR_W), size=U, p=CF.SECTOR_W)
    logw = -g.zipf_s * np.log(np.arange(1, U + 1))
    isig = np.exp(rng.uniform(math.log(g.sig_lo), math.log(g.sig_hi), (R, U)))
    beta = np.array(g.beta_mean)[None, None, :] + g.beta_sd * rng.standard_normal((R, U, 3))
    upref = rng.standard_normal((R, U))
    tau = None
    if cell.issuer_tau > 0 or cell.null == "NI":
        tau = (cell.issuer_tau or 0.010) * rng.standard_normal((R, U))
        tau -= tau.mean(axis=1, keepdims=True)
    lmean = (g.sig_hi - g.sig_lo) / math.log(g.sig_hi / g.sig_lo) if cell.null == "NV" else None
    last = np.full((R, U), -10_000, np.int32)
    lvol = rng.standard_normal(R) * g.vol_sd
    D = rng.standard_normal(R) * g.drift_sd if g.drift_sd > 0 else np.zeros(R)
    z, _ = V2.day_innov2(rng, g, R, lvol)
    sd_c = g.sd_day()
    Emult = V2.count_norm(g) if cell.cnt else 1.0
    gflips = np.where(np.random.default_rng(seed + 77_777).random((CF.B_ISS_G, U)) < 0.5, -1.0, 1.0)
    runs = [Run(R, U, 0)]
    Sg = np.zeros(R, np.int64)
    rows_all = np.arange(R)
    sl = np.array(LOOKS)
    picks_total = 0
    mw_num = 0.0
    for t in range(1, T + 1):
        lvol = g.vol_rho * lvol + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R)
        h = np.exp(lvol - g.vol_sd ** 2)
        if g.drift_sd > 0:
            D = g.drift_rho * D + math.sqrt(1 - g.drift_rho ** 2) * g.drift_sd * rng.standard_normal(R)
        eps, _ = V2.day_innov2(rng, g, R, lvol)
        z = g.phi_day * z + math.sqrt(1 - g.phi_day ** 2) * eps
        c_day = sd_c * z
        s_sec = g.sd_sector * CF.unit_t3(rng, (R, len(CF.SECTOR_W)))
        f_fac = g.sd_factor * CF.unit_t3(rng, (R, 3))
        b = g.b_mu + g.b_sd * rng.standard_normal(R)
        d = draw_session(rng, cell, g, R, U, logw, sector, isig, upref, lvol, eps, Emult, math.log(4.0), last, t)
        if d is None:
            continue
        mask, idx, key, alpha, passf, big, nC = d
        sel = pick(key, passf, cell.k)
        rows = rows_all[:, None]
        nm = idx.shape[1]
        sig = isig[rows, idx]
        if cell.null == "NS":
            e = np.where(big, 1.5 * _two_piece(rng, (R, nm), 1.6, 0.4), CF.unit_t3(rng, (R, nm), g.ev_left, g.ev_right))
            jp = np.where(big, 3 * g.jump_p, g.jump_p)
            jl = np.where(big, 0.9, g.jump_left)
        else:
            e = CF.unit_t3(rng, (R, nm), g.ev_left, g.ev_right)
            jp = np.full((R, nm), g.jump_p)
            jl = np.full((R, nm), g.jump_left)
        l = np.clip(sig / lmean, 0.3, 3.0) if lmean else 1.0
        common = l * c_day[:, None] + s_sec[rows, sector[idx]] + (beta[rows, idx, :] * f_fac[:, None, :]).sum(axis=2)
        a = mu + D[:, None] + h[:, None] * (common + sig * e) + alpha
        hit = rng.random((R, nm)) < jp
        sgn = np.where(rng.random((R, nm)) < jl, -1.0, 1.0)
        a = a + hit * sgn * g.jump_size - jp * g.jump_size * (1.0 - 2.0 * jl)
        if tau is not None:
            a = a + tau[rows, idx]
        a = np.maximum(a, -1.0)
        r_ = a + b[:, None]
        # the control: the whole R2 SET (every candidate read, one per issuer)
        nCt = mask.sum(axis=1)
        Ct = np.where(nCt > 0, (a * mask).sum(axis=1) / np.maximum(nCt, 1), 0.0)
        nP = sel.sum(axis=1)
        sP = (a * sel).sum(axis=1)
        sR = (r_ * sel).sum(axis=1)
        has = nP > 0
        Bt = np.where(has, sP / np.maximum(nP, 1), 0.0)
        picks_total += int(nP.sum())
        mw_num += float(sP.sum())
        pr, pc = np.nonzero(sel)
        pi_ = idx[pr, pc]
        last[pr, pi_] = t
        pa = a[pr, pc]
        # a run's end at its 60th block starts run 2 at the next block
        if len(runs) == 1 and (runs[0].ended < 10 ** 6).any():
            runs.append(Run(R, U, S_RUN))
        for run in runs:
            act = has & (Sg >= run.start) & ~run.done
            if run.start > 0:
                act &= runs[0].ended < 10 ** 6          # run 2 only for a version whose run 1 ended unpassed
            hr = np.nonzero(act)[0]
            if hr.size == 0:
                continue
            run.X[hr, run.S[hr]] = Bt[hr]
            run.W[hr, run.S[hr]] = nP[hr]
            run.S[hr] += 1
            am = act.astype(float)
            run.ca += sP * am; run.cr += sR * am; run.ne += nP * act
            pm = act[pr]
            if pm.any():
                flat = pr[pm] * U + pi_[pm]
                isum = run.isum.reshape(-1); icnt = run.icnt.reshape(-1)
                new = icnt[flat] == 0
                np.add.at(isum, flat, pa[pm]); np.add.at(icnt, flat, 1)
                if new.any():
                    run.niss += np.bincount(pr[pm][new], minlength=R)
            run.cbm += np.where(act, Bt, 0.0)
            run.ccm += np.where(act, Ct, 0.0)
            S = run.S
            mn = (run.ne >= MIN_EV) & (run.niss >= MIN_ISS) & (S >= MIN_BLK)
            live = run.nxt < sl.size
            thr = sl[np.minimum(run.nxt, sl.size - 1)]
            look = act & mn & live & (S >= thr) & (S <= S_RUN)
            lr = np.nonzero(look)[0]
            if lr.size:
                run.nxt[lr] = (S[lr][:, None] >= sl[None, :]).sum(axis=1)
                al = alpha_of(S)
                gd = (run.ca > 0) & (run.cr > 0) & (run.cbm > run.ccm)
                # RETIRE first
                cq = lr[run.ca[lr] < 0]
                ret = np.zeros(R, bool)
                for Sv in np.unique(S[cq]):
                    rs = cq[S[cq] == Sv]
                    Y = -np.minimum(run.W[rs, :Sv], CAP) * run.X[rs, :Sv]
                    zz = Y.sum(axis=1) / np.sqrt(np.maximum((Y * Y).sum(axis=1), 1e-300))
                    kp = zz >= 1.0
                    if kp.any():
                        q = CF.signflip_p_rows(Y[kp], int(Sv))
                        ret[rs[kp]] = q <= al[rs[kp]] + TIE
                rr = np.nonzero(ret)[0]
                run.retired[rr] = t; run.done[rr] = True
                cp = lr[gd[lr] & ~ret[lr]]
                for Sv in np.unique(S[cp]):
                    rs = cp[S[cp] == Sv]
                    Y = np.minimum(run.W[rs, :Sv], CAP) * (run.X[rs, :Sv] - MARGIN)
                    zz = Y.sum(axis=1) / np.sqrt(np.maximum((Y * Y).sum(axis=1), 1e-300))
                    kp = zz >= 1.0
                    if not kp.any():
                        continue
                    p = CF.signflip_p_rows(Y[kp], int(Sv))
                    for r_i, pv in zip(rs[kp], p):
                        if pv <= al[r_i]:
                            c = run.icnt[r_i]
                            nz = c > 0
                            if CF.issuer_p(run.isum[r_i][nz] / c[nz], gflips) <= 0.10:
                                run.passed[r_i] = t; run.done[r_i] = True
            endr = np.nonzero(act & ~run.done & (S >= S_RUN))[0]
            if endr.size and run.start == 0:
                run.ended[endr] = t; run.done[endr] = True
            elif endr.size:
                run.done[endr] = True
        Sg += has
    r1 = runs[0]
    p2 = runs[1].passed if len(runs) > 1 else np.full(R, 10 ** 6)
    out = {"p1": r1.passed.tolist(), "ret1": r1.retired.tolist(), "end1": r1.ended.tolist(), "p2": p2.tolist(),
           "picks_per_session": picks_total / (R * T), "realized_mean_a_bp": 1e4 * mw_num / max(picks_total, 1)}
    return out


def summarize(lab, cell, res, T):
    p1 = np.array(res["p1"]); p2 = np.array(res["p2"]); R = p1.size
    fp = float((p1 <= T).mean())
    se = math.sqrt(max(fp * (1 - fp), 1e-12) / R)
    ver = float(((p1 <= T) | (p2 <= T)).mean())
    by = {s: float((p1 <= s).mean()) for s in (25, 30, 40, 60, 90, 120)}
    return {"cell": lab, "R": R, "pass_run1_120": round(fp, 4), "se": round(se, 4), "per_version_120": round(ver, 4),
            "by_session": by, "retired_120": float((np.array(res["ret1"]) <= T).mean()),
            "picks_per_session": round(res["picks_per_session"], 2), "realized_mean_a_bp": round(res["realized_mean_a_bp"], 2),
            "gen": dataclasses.asdict(cell)}


CORNER = dict(day="crasht3cl", rho_day=0.15, phi_day=0.20, ev="skew")
BASE = dict(day="t3", rho_day=0.05, phi_day=0.10, ev="sym", drift_sd=0.0)


def cells(phase, R):
    out = []
    if phase == "pilot":
        out.append(("pilot|N1|corner|AR10|n26", Cell(null="N1", nbar=26, drift_sd=0.0010, **CORNER), R))
        return out
    if phase == "null":
        for null in ("N1", "NK", "NV", "NS", "NI"):
            for drift in (0.0010, 0.0020):
                for nbar, cnt in ((26, False), (12, False), (5, True)):
                    out.append((f"{null}|corner|AR{int(drift * 1e4)}|n{nbar}{'|cnt' if cnt else ''}",
                                Cell(null=null, nbar=nbar, cnt=cnt, drift_sd=drift, **CORNER), R))
        for null in ("N1", "NK", "NV", "NS", "NI"):
            out.append((f"{null}|base|n26", Cell(null=null, nbar=26, **BASE), R // 2))
        # other day shapes at the corner's other settings (t(3)-body unclustered, clustered normal body)
        for day in ("crasht3", "crashcl", "crash"):
            for null in ("NK", "NV"):
                out.append((f"{null}|{day}|skew|AR20|n12", Cell(null=null, nbar=12, drift_sd=0.0020,
                                                                **{**CORNER, "day": day}), R // 2))
        return out
    if phase == "stress":
        for null in ("NK", "NV", "NS"):
            out.append((f"S|{null}|phi.25|AR20|n12", Cell(null=null, nbar=12, drift_sd=0.0020,
                                                            **{**CORNER, "phi_day": 0.25}), R // 2))
            out.append((f"S|{null}|rho.30|AR20|n12", Cell(null=null, nbar=12, drift_sd=0.0020,
                                                           **{**CORNER, "rho_day": 0.30, "phi_day": 0.10}), R // 2))
            out.append((f"S|{null}|AR30|n12", Cell(null=null, nbar=12, drift_sd=0.0030,
                                                    **{**CORNER, "rho_day": 0.05, "phi_day": 0.10}), R // 2))
        return out
    if phase == "final":
        # THE REGISTERED CONSUMER'S OWN SHAPE (EVL-R2-ON: about 42 read candidates a session, the filter its own fields,
        # K = 8), its false passes at the corner's worst structures on FRESH seeds (4,000 programs), and its power
        for null in ("N1", "NK", "NV", "NS", "NI"):
            for drift in (0.0010, 0.0020):
                out.append((f"F|{null}|corner|AR{int(drift * 1e4)}|n42|finf", Cell(null=null, nbar=42, finf=True,
                                                                                  drift_sd=drift, **CORNER), R))
        for null in ("NK", "NV", "NS"):
            out.append((f"F|{null}|corner|AR20|n5|cnt|finf", Cell(null=null, nbar=5, cnt=True, finf=True, drift_sd=0.0020,
                                                                  **CORNER), R))
            out.append((f"F|{null}|corner|AR20|n14|finf", Cell(null=null, nbar=14, finf=True, drift_sd=0.0020,
                                                                **CORNER), R))
        for null in ("N1", "NK", "NV"):
            out.append((f"F|{null}|base|n42|finf", Cell(null=null, nbar=42, finf=True, **BASE), R // 2))
        for env_name, env in (("base", BASE), ("corner", dict(CORNER, drift_sd=0.0010))):
            for sda in (0.004, 0.008, 0.015):
                for c in (0.3, 0.5, 0.7):
                    out.append((f"P|alt|{env_name}|n42|finf|sda{sda}|c{c}", Cell(null="alt", nbar=42, finf=True, c=c,
                                                                                sd_alpha=sda, **env), R // 2))
        return out
    if phase == "power2":
        for env_name, env in (("base", BASE), ("corner", dict(CORNER, drift_sd=0.0010))):
            for c in (0.5, 0.7):
                out.append((f"alt|{env_name}|n48|sda0.008|c{c}", Cell(null="alt", nbar=48, c=c, sd_alpha=0.008, **env), R))
                out.append((f"alt|{env_name}|n26|sda0.008|c{c}|finf", Cell(null="alt", nbar=26, c=c, sd_alpha=0.008,
                                                                         finf=True, **env), R))
                out.append((f"alt|{env_name}|n26|sda0.008|c{c}|k4", Cell(null="alt", nbar=26, c=c, sd_alpha=0.008, k=4,
                                                                       **env), R))
                out.append((f"alt|{env_name}|n48|sda0.008|c{c}|finf", Cell(null="alt", nbar=48, c=c, sd_alpha=0.008,
                                                                         finf=True, **env), R))
            out.append((f"alt|{env_name}|n26|sda0.015|c0.5|finf", Cell(null="alt", nbar=26, c=0.5, sd_alpha=0.015,
                                                                     finf=True, **env), R))
        # the finf / n48 / k4 consumers' false passes at the corner's worst structures (the knife: picks' mean zero)
        for nm, kw in (("n48", dict(nbar=48)), ("n26|finf", dict(nbar=26, finf=True)), ("n26|k4", dict(nbar=26, k=4)),
                       ("n5|cnt|finf", dict(nbar=5, cnt=True, finf=True))):
            for null in ("NK", "NV"):
                out.append((f"{null}|corner|AR20|{nm}", Cell(null=null, drift_sd=0.0020, **CORNER, **kw), R))
        return out
    if phase == "power":
        for env_name, env in (("base", BASE), ("corner", dict(CORNER, drift_sd=0.0010))):
            for nbar in (26, 12):
                for sd_alpha in (0.004, 0.008):
                    for c in (0.3, 0.5, 0.7):
                        out.append((f"alt|{env_name}|n{nbar}|sda{sd_alpha}|c{c}",
                                    Cell(null="alt", nbar=nbar, c=c, sd_alpha=sd_alpha, **env), R))
                    out.append((f"coarse|{env_name}|n{nbar}|sda{sd_alpha}|c0.3",
                                Cell(null="coarse", nbar=nbar, c=0.3, sd_alpha=sd_alpha, **env), R))
        return out
    raise ValueError(phase)


SEEDS = {"pilot": 231_000_000, "null": 232_000_000, "power": 233_000_000, "stress": 234_000_000,
         "power2": 235_000_000, "final": 236_000_000}


def _job(args):
    phase, lab, cell_kw, R, T, seed, mu = args
    cell = Cell(**cell_kw)
    t0 = time.time()
    res = simulate(cell, R, T, seed, mu)
    return lab, cell_kw, R, seed, mu, res, time.time() - t0


def run(phase, workers, R, chunk=500, T=120):
    from multiprocessing import get_context
    cl = cells(phase, R)
    with get_context("fork").Pool(workers) as pool:
        mus = dict(zip([lab for lab, _, _ in cl], pool.map(knife_mu, [cell for _, cell, _ in cl])))
    print(f"{phase}: knife mu done for {len(mus)} cells", flush=True)
    jobs = []
    seed = SEEDS[phase]
    for lab, cell, Rc in cl:
        for c0 in range(0, Rc, chunk):
            seed += 1
            jobs.append((phase, lab, dataclasses.asdict(cell), min(chunk, Rc - c0), T, seed, mus[lab]))
    agg: dict = {}
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool:
        for k, (lab, kw, Rj, sd, mu, res, secs) in enumerate(pool.imap_unordered(_job, jobs), 1):
            a = agg.setdefault(lab, {"p1": [], "ret1": [], "end1": [], "p2": [], "pps": [], "rma": [], "kw": kw,
                                     "mu": mu, "seeds": []})
            for key_ in ("p1", "ret1", "end1", "p2"):
                a[key_] += res[key_]
            a["pps"].append(res["picks_per_session"] * Rj); a["rma"].append(res["realized_mean_a_bp"] * Rj)
            a["seeds"].append(sd)
            if k % 10 == 0 or k == len(jobs):
                print(f"{phase}: {k}/{len(jobs)} jobs {time.time() - t0:.0f}s", flush=True)
    rows = []
    for lab, a in agg.items():
        n = len(a["p1"])
        res = {"p1": a["p1"], "ret1": a["ret1"], "end1": a["end1"], "p2": a["p2"],
               "picks_per_session": sum(a["pps"]) / n, "realized_mean_a_bp": sum(a["rma"]) / n}
        s = summarize(lab, Cell(**a["kw"]), res, T)
        s["mu_bp"] = round(1e4 * a["mu"], 2)
        s["seeds"] = sorted(a["seeds"])
        rows.append(s)
    rows.sort(key=lambda r: r["cell"])
    path = os.path.join(HERE, f"calib_r2.{phase}.jsonl")
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for r in rows:
        print(f"{r['cell']:<40} R {r['R']:>5} run1 {r['pass_run1_120']:.4f} (+-{r['se']:.4f}) version {r['per_version_120']:.4f}"
              f" by40 {r['by_session'][40]:.3f} by60 {r['by_session'][60]:.3f} picks/s {r['picks_per_session']:.2f}"
              f" mean a {r['realized_mean_a_bp']:+.1f} bp mu {r['mu_bp']:+.1f}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--phase", default="pilot")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--R", type=int, default=2000)
    ap.add_argument("--chunk", type=int, default=500)
    a = ap.parse_args()
    run(a.phase, min(a.workers, 4), a.R, a.chunk)

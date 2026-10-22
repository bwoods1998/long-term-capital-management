#!/usr/bin/env python
"""rc1.py: PREREG-EVL-7 RE-CHECK #1 (statistics and leakage). SYNTHETIC ONLY.

Nothing here reads the lane: no House, gateway, events.sqlite, live.sqlite, run record, price, return, look or band.

What it does:
  1. simulate_rc(): the fix round's generator and learner (evl7/final/calib_w7.py simulate7, copied line for line) with
     ONE optional change, `rmode`: the learner's r1 / r5 / r20 columns (section 1.4 item 11) and, for EVL-LRN-ON, dmove
     (item 15) are built from each issuer's OWN simulated returns instead of fresh t(3) noise:
       every issuer has a return every session: its event's gross abnormal return a_g when it is in the pool (the leg
       the learner holds, so its persistent issuer effect tau is in it), else h_t (s_sector + beta . f + sigma e) (no
       tau, no jump; evl9/check1/check1_rfeat.py's construction), plus, when leg_sd > 0, the complementary leg of the
       same calendar day (overnight for O1, the day for ON) of sd leg_sd x h_t x sigma (noise only);
       'o1' (EVL-LRN-O1, open to close): close-to-close of day t = other_t + leg_t; r1 = cc(t-1), r5 = sum cc(t-5..t-1),
            r20 = sum cc(t-19..t-1);
       'on' (EVL-LRN-ON, close to next open, leg_t = close t -> open t+1): cc(t) = leg(t-1) + other(t); r1 = cc(t-1),
            r5 = sum cc(t-5..t-1), r20 = sum cc(t-19..t-1) (so they hold legs t-20..t-2), and dmove = leg(t-1) +
            0.9 x other(t) (the '1530' mark against the previous close), clipped as item 15;
     a 25-session burn-in fills the issuers' return history before the pre-registration sessions (it trains nothing).
     With rmode None the function is simulate7 itself (selftest: identical output on the same seed).
  2. screen_rc(): PREREG-EVL-6 sections 1.2-3 as frozen (sha256 0f67f94e...), written from the text, independent of
     calib_w7.screen: blocks, y_s = min(n_s, 14) (B_s - 10 bp), looks 22/25/30/35/40/50/60 with the minimums (30 events,
     30 issuers, 6 blocks), alpha 0.020 / 0.006 / 0.001 by S, RETIRE first (mean a < 0 and q <= alpha + 1e-12), PASS
     (p <= alpha; mean a > 0; mean r > 0; the top-14 events' mean a and r > 0; mean block value above the control's;
     p_I <= 0.10), a run ends at its 60th block, run n + 1 starts with the next block, RETIRE ends the version. Sign-flip
     p: exact for S <= 16, else FRESH random sign vectors at every look (the frozen rule draws a fresh seed per S),
     NVEC of them, no z prefilter; the issuer guard over NVEC_I fresh vectors. Variants from the same per-look figures:
     without the control condition, without the issuer guard, without both (how much the guards protect a null).
  3. Every job also runs calib_w7.screen on the same paths (agreement check).
Usage: rc1.py run --grid NAME [--reps R] [--chunk C] [--workers W] | report | selftest
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "final"))
sys.path.insert(1, os.path.join(os.path.dirname(HERE), "learner"))
import calib_w7 as w7  # noqa: E402

cl = w7.cl
U = cl.U
D0 = w7.D0
BURN = 25
NVEC = 19_999
NVEC_I = 9_999


# ------------------------------------------------------------------------------------------------ the generator
def simulate_rc(cell, x7, seed, R, rmode=None, leg_sd=0.6, knife=False):
    rng = np.random.default_rng(seed)
    T, K = cell.T, cell.K
    iss = w7.issuers7(rng, R, cell, x7)
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
               edgerep=np.full((R, T), np.nan), c7p=np.full((R, T, K), np.nan), crepp=np.full((R, T, K), np.nan),
               taup=np.full((R, T, K), np.nan))
    um, usd, u95 = cl.u_norm(cl.W_TRUE)
    w_now = cl.W_TRUE
    newday = x7.day in ("crasht3", "crashcl", "crasht3cl")
    kind = x7.day if newday else cell.day
    Em = w7.count_norm(kind, x7.cnt) if x7.cnt else 1.0
    if rmode:
        leg = np.zeros((32, R, U))      # leg_t: the held leg of day t (event a_g in the pool, else idiosyncratic)
        oth = np.zeros((32, R, U))      # the complementary leg of the same day
    t_start = -cell.pre - (BURN if rmode else 0)
    for t in range(t_start, T):
        if cell.null == "A2" and t == 60:
            w_now = cl.W_FLIP
            um, usd, u95 = cl.u_norm(cl.W_FLIP)
        eps = None
        if x7.cnt:
            if newday:
                pre = (rng.random(R), rng.normal(-w7.CR_K, 1.0, R),
                       cl.unit_t3(rng, R) if "t3" in kind else rng.standard_normal(R))
                vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
                eps = w7.day_eps(kind, rng, R, vx, pre)
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
        X, fam = w7.pool_features7(rng, R, Nmax, iss, ids, x7.extra)
        sig = np.take_along_axis(iss["sig"], ids, axis=1)
        if rmode:                         # THE CHANGE: the issuer's own trailing returns
            off = "o1" if rmode.startswith("o1") else "on"

            def cc(j):                    # close-to-close of day t - j for the pool's issuers
                if off == "o1":
                    full = oth[(t - j) % 32] + leg[(t - j) % 32]
                else:
                    full = leg[(t - j - 1) % 32] + oth[(t - j) % 32]
                return np.take_along_axis(full, ids, axis=1)
            if rmode != "ondm":           # 'ondm': only dmove is built from own returns (r1 / r5 / r20 dropped: noise)
                c_list = [cc(j) for j in range(1, 20)]
                X[..., 35] = np.clip(c_list[0], -0.5, 0.5)
                X[..., 36] = np.clip(sum(c_list[:5]), -1.0, 1.0)
                X[..., 37] = np.clip(sum(c_list), -1.5, 1.5)
            if off == "on":
                eo = cl.unit_t3(rng, (R, Nmax))
                h_now = np.exp(vx - 0.09)
                dm = np.take_along_axis(leg[(t - 1) % 32], ids, axis=1) + 0.9 * leg_sd * h_now[:, None] * sig * eo
                X[..., 39] = np.clip(dm, -0.5, 0.5)
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
                pre = (rng.random(R), rng.normal(-w7.CR_K, 1.0, R),
                       cl.unit_t3(rng, R) if "t3" in kind else rng.standard_normal(R))
                vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
                eps = w7.day_eps(kind, rng, R, vx, pre)
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
            cm_g = sig * Ey + struct
            cm7 = cm_g - c7
        else:
            cm7 = sig * Ey + struct
            cm_g = cm7 + c7
        a_g = np.maximum(cm_g + noise + jump, -1.0)
        a7 = a_g - c7
        arep = a_g - c_rep
        lab = a_g if x7.gross else arep
        y = np.clip(lab / sig_hat, -5, 5)
        vf = valid.astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        if rmode:                         # this day's returns of every issuer, the pool's legs their events' a_g
            isig = iss["sig"]
            idio = h_t[:, None] * (np.take_along_axis(s_sec, iss["sector"], axis=1)
                                   + np.einsum("ruk,rk->ru", iss["beta"], fac) + isig * cl.unit_t3(rng, (R, U)))
            rr_, nn_ = np.nonzero(valid)
            idio[rr_, ids[rr_, nn_]] = 0.0 if rmode.endswith("mask") else a_g[rr_, nn_]   # 'mask': own pool legs 0
            leg[t % 32] = idio
            oth[t % 32] = leg_sd * h_t[:, None] * isig * cl.unit_t3(rng, (R, U)) if leg_sd > 0 else 0.0
            if t < -cell.pre:
                continue
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
            if knife:                 # THE LEARNER'S KNIFE EDGE: a shift common to the session sets the picks' expected
                with np.errstate(invalid="ignore"):   # a7 to exactly 0 (their ranking stays real; the pool is below)
                    pe_ = np.nanmean(np.where(ok, np.take_along_axis(sig * Ey - c7, top, axis=1), np.nan), axis=1)
                shift = np.where(ok.any(axis=1), pe_, 0.0)
                a7 = a7 - shift[:, None]
                arep = arep - shift[:, None]
                cm7 = cm7 - shift[:, None]
                Ey = Ey - (shift[:, None] / sig)
            out["n"][:, t] = ok.sum(axis=1)
            out["iss"][:, t, :] = pid
            out["a7"][:, t, :] = np.where(ok, np.take_along_axis(a7, top, axis=1), np.nan)
            out["arep"][:, t, :] = np.where(ok, np.take_along_axis(arep, top, axis=1), np.nan)
            out["cm7"][:, t, :] = np.where(ok, np.take_along_axis(cm7, top, axis=1), np.nan)
            out["sig"][:, t, :] = np.where(ok, np.take_along_axis(sig, top, axis=1), np.nan)
            out["taup"][:, t, :] = np.where(ok, np.take_along_axis(tau, top, axis=1), np.nan)
            out["b"][:, t] = b_t
            out["c7ctl"][:, t] = (a7 * vf).sum(axis=1) / nv
            out["crepctl"][:, t] = (arep * vf).sum(axis=1) / nv
            out["npool"][:, t] = n_t
            has = ok.any(axis=1)
            with np.errstate(invalid="ignore"):
                ed = np.nanmean(np.where(ok, np.take_along_axis(sig * Ey - (c7 if cell.null in ("A", "A2") else 0.0),
                                                                top, axis=1), np.nan)[has], axis=1)
            out["edge7"][has, t] = ed
            with np.errstate(invalid="ignore"):
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


# ------------------------------------------------------------------------------------------------ the screen
LOOKS = (22, 25, 30, 35, 40, 50, 60)
M0, CAP, HORIZON, TIE = 0.0010, 14, 60, 1e-12


def alpha_of(S):
    if 22 <= S <= 30:
        return 0.020
    if 31 <= S <= 40:
        return 0.006
    if 41 <= S <= 60:
        return 0.001
    return 0.0


def flip_p(y, rng, nvec):
    """One-sided sign-flip p of mean(y) > 0: #{s : sum s_j y_j >= sum y_j - S x 1e-12}, exact for S <= 16, else
    (1 + #) / (1 + nvec) over fresh vectors (PREREG-EVL-6 section 1.3)."""
    y = np.asarray(y, float)
    S = len(y)
    tot = math.fsum(y)
    if S <= 16:
        pats = ((np.arange(1 << S)[:, None] >> np.arange(S)[None, :]) & 1) * 2.0 - 1.0
        return float(np.count_nonzero(pats @ y >= tot - S * TIE)) / float(1 << S)
    sg = rng.integers(0, 2, (nvec, S), dtype=np.int8).astype(np.float64) * 2.0 - 1.0
    return (1 + int(np.count_nonzero(sg @ y >= tot - S * TIE))) / (1.0 + nvec)


def screen_rc(sim, rep, rng, T_lim=120):
    """Run 1's outcome under the frozen rule and three guard variants, and the version's first pass within T_lim.
    Returns dict(run1=session or -1 for each variant, ret1=bool, v=session or -1 (main rule, any run), cm=..., tau=...)."""
    n = sim["n"][rep]
    T = min(T_lim, len(n))
    av, bt, ctl = sim["a7"][rep], sim["b"][rep], sim["c7ctl"][rep]
    iss, cmv, tv = sim["iss"][rep], sim["cm7"][rep], sim["taup"][rep] if "taup" in sim else None
    res = dict(main=-1, noctl=-1, noiss=-1, none=-1, nomargin=-1, ret1=False, v=-1, vrun=0, cm=None, tau=None,
               looks1=0)
    variants = ("main", "noctl", "noiss", "none", "nomargin")
    run, t0 = 1, 0
    while t0 < T:
        B, W, C = [], [], []
        ev_a, ev_iss, ev_cm, ev_tau = [], [], [], []
        sum_r = 0.0
        k = 0
        ended = -1
        live = {v: True for v in variants} if run == 1 else {"main": True}
        for t in range(t0, T):
            kk = int(n[t])
            if kk == 0:
                continue
            a_t = [float(x) for x in av[t, :kk]]
            B.append(math.fsum(a_t) / kk)
            W.append(min(kk, CAP))
            C.append(float(ctl[t]))
            ev_a.extend(a_t)
            ev_iss.extend(int(x) for x in iss[t, :kk])
            ev_cm.extend(float(x) for x in cmv[t, :kk])
            if tv is not None:
                ev_tau.extend(float(x) for x in tv[t, :kk])
            sum_r += math.fsum(a_t) + kk * float(bt[t])
            S = len(B)
            Nn = len(ev_a)
            if k < len(LOOKS) and S >= LOOKS[k] and Nn >= 30 and len(set(ev_iss)) >= 30 and S >= 6:
                while k < len(LOOKS) and S >= LOOKS[k]:
                    k += 1
                if run == 1:
                    res["looks1"] += 1
                al = alpha_of(S)
                Bv = np.array(B)
                Wv = np.array(W, float)
                mean_a = math.fsum(ev_a) / Nn
                mean_r = sum_r / Nn
                if mean_a < 0:
                    q = flip_p(-Wv * Bv, rng, NVEC)
                    if q <= al + TIE:
                        if run == 1 and res["v"] < 0:
                            res["ret1"] = True
                        return res
                    continue
                # top-14 by rank = all picks (at most 8 a session): the same means
                if not (mean_a > 0 and mean_r > 0):
                    continue
                p = flip_p(Wv * (Bv - M0), rng, NVEC)
                ctl_ok = float(np.mean(Bv)) > float(np.mean(C))
                p_ok = p <= al
                p0_ok = p_ok or (run == 1 and live.get("nomargin") and flip_p(Wv * Bv, rng, NVEC) <= al)
                iss_ok = None
                if p_ok or p0_ok:
                    m: dict = {}
                    for i_, a_ in zip(ev_iss, ev_a):
                        m.setdefault(i_, []).append(a_)
                    vals = [math.fsum(m[i_]) / len(m[i_]) for i_ in sorted(m)]
                    iss_ok = flip_p(vals, rng, NVEC_I) <= 0.10 + TIE
                flags = dict(main=p_ok and ctl_ok and bool(iss_ok), noctl=p_ok and bool(iss_ok),
                             noiss=p_ok and ctl_ok, none=p_ok, nomargin=p0_ok and ctl_ok and bool(iss_ok))
                for v in list(live):
                    if live[v] and flags[v]:
                        live[v] = False
                        if run == 1:
                            res[v] = t
                        if v == "main":
                            res["v"] = t
                            res["vrun"] = run
                            res["cm"] = float(np.mean(ev_cm))
                            res["tau"] = float(np.mean(ev_tau)) if ev_tau else None
                if not live.get("main", False):
                    # the version's main-rule pass ends the version's story; finish run 1's variants on this run only
                    if run == 1 and any(live[v] for v in live):
                        continue
                    return res
            if S >= HORIZON:
                ended = t
                break
        if ended < 0 or res["v"] >= 0:
            return res
        run += 1
        t0 = ended + 1
    return res


# ------------------------------------------------------------------------------------------------ cells
def cell_of(spec):
    s = dict(spec)
    rmode = s.pop("rmode", None)
    leg_sd = s.pop("leg_sd", 0.6)
    name = s.pop("name", None)
    knife = s.pop("knife", False)
    fam = s.pop("fam", 0.0)
    cell, x7 = w7.corner(**s)
    if fam:
        cell = dataclasses.replace(cell, fam_drift_sd=fam)
    nm = name or (cell.name + (f"-R{rmode}" if rmode else "") + (f"-leg{leg_sd}" if rmode and leg_sd != 0.6 else "")
                  + ("-KNIFE" if knife else "") + (f"-famdrift{int(round(fam * 1e4))}" if fam else ""))
    return nm, cell, x7, rmode, leg_sd, knife


WC = dict(shape="crasht3cl", phi=0.20, drift=0.0020, pool=300, tau=0.01, skew=True, rho=0.15)
GRIDS = {
    # (1) W7 rebuilt: the fix round's generator unchanged (r columns noise), its worst cell, both lags, fresh seeds
    "w7": [dict(WC, lag=1), dict(WC, lag=2)],
    # (2) the registered feature set: r1 / r5 / r20 (and ON's dmove) from the issuer's own returns, issuer effect 1%
    "rfeat": [dict(WC, lag=1, rmode="o1"), dict(WC, lag=2, rmode="on", extra=23)],
    # (3) the same without the issuer effect (the change alone moves nothing?) and at 0.5%
    "rctl": [dict(WC, lag=1, rmode="o1", tau=0.0), dict(WC, lag=2, rmode="on", extra=23, tau=0.0)],
    "rmore": [dict(WC, lag=1, rmode="o1", leg_sd=0.0), dict(WC, lag=2, rmode="on", extra=23, leg_sd=0.0),
              dict(WC, lag=1, rmode="o1", cnt=0.3), dict(WC, lag=1, rmode="o1", pool=800),
              dict(WC, lag=1, rmode="o1", tau=0.005), dict(WC, lag=2, rmode="on", extra=23, cnt=0.3)],
    "rbase": [dict(shape="t3", phi=0.10, drift=0.0, lag=1, rho=0.05, skew=False, tau=0.01, rmode="o1"),
              dict(shape="t3", phi=0.10, drift=0.0, lag=2, rho=0.05, skew=False, tau=0.01, rmode="on", extra=23)],
    "smoke": [dict(WC, lag=1, T=40), dict(WC, lag=1, rmode="o1", T=40)],
    # (4) the learner's knife edge: real ranking (ic), the picks' expected a7 exactly 0 each session, the pool below
    "knife": [dict(WC, lag=1, null="A", ic=0.05, knife=True), dict(WC, lag=2, null="A", ic=0.05, knife=True),
              dict(WC, lag=1, null="A", ic=0.08, knife=True, pool=800)],
    # (5) a learnable 20 bp FAMILY drift (each pool family its own AR 0.97 drift) at the worst corner, both lags
    "fam": [dict(WC, lag=1, fam=0.0020), dict(WC, lag=2, fam=0.0020)],
    # (6) the candidate fixes: ON with only dmove built from own returns (r1 / r5 / r20 dropped), and the own-leg mask
    "fix": [dict(WC, lag=2, rmode="ondm", extra=23), dict(WC, lag=1, rmode="o1mask"),
            dict(WC, lag=2, rmode="onmask", extra=23)],
    # (7) pool 800 (in the frozen grid): the registered features at ON's lag, the fixed generator's baseline, the fixes
    "r800": [dict(WC, lag=2, rmode="on", extra=23, pool=800), dict(WC, lag=1, pool=800),
             dict(WC, lag=2, rmode="ondm", extra=23, pool=800), dict(WC, lag=1, rmode="o1mask", pool=800)],
}
SEED0 = {"w7": 251_000_001, "rfeat": 252_000_001, "rctl": 253_000_001, "rmore": 254_000_001, "rbase": 255_000_001,
         "smoke": 259_000_001, "knife": 256_000_001, "fam": 257_000_001, "fix": 258_000_001, "r800": 260_000_001}


def _job(args):
    gname, ci, spec, seed, R = args
    nm, cell, x7, rmode, leg_sd, knife = cell_of(spec)
    t0 = time.time()
    sim = simulate_rc(cell, x7, seed, R, rmode, leg_sd, knife)
    rng = np.random.default_rng(seed + 777_777)
    mine = [screen_rc(sim, i, rng) for i in range(R)]
    theirs = [w7.screen(sim, i, "frozen", "a7") for i in range(R)]
    with np.errstate(invalid="ignore"):
        stats = dict(ev_s=float(sim["n"].mean()), a7_bp=float(np.nanmean(sim["a7"]) * 1e4),
                     cm7_bp=float(np.nanmean(sim["cm7"]) * 1e4), tau_bp=float(np.nanmean(sim["taup"]) * 1e4),
                     ctl_bp=float(np.nanmean(sim["c7ctl"]) * 1e4), sig=float(np.nanmean(sim["sig"])))
    return dict(grid=gname, cell=nm, spec=spec, seed=seed, R=R, T=cell.T, mine=mine,
                theirs=[[x[0], x[1], x[4]] for x in theirs], stats=stats, secs=round(time.time() - t0, 1))


def run(gname, reps, chunk, workers):
    from multiprocessing import Pool
    specs = GRIDS[gname]
    jobs = [(gname, ci, sp, SEED0[gname] + 1000 * ci + j, chunk) for ci, sp in enumerate(specs)
            for j in range(max(1, reps // chunk))]
    path = os.path.join(HERE, f"rc1.{gname}.jsonl")
    t0 = time.time()
    with Pool(workers) as pool, open(path, "a") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gname}: {k + 1}/{len(jobs)} {res['cell']} seed {res['seed']} {res['secs']}s "
                  f"total {time.time() - t0:.0f}s", flush=True)


def _se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / max(n, 1))


def report(only=None):
    import glob
    for path in sorted(glob.glob(os.path.join(HERE, "rc1.*.jsonl"))):
        if only and only not in path:
            continue
        by: dict = {}
        for line in open(path):
            r = json.loads(line)
            by.setdefault(r["cell"], []).append(r)
        print(f"== {os.path.basename(path)}")
        for nm, parts in by.items():
            mine = [m for p in parts for m in p["mine"]]
            th = [x for p in parts for x in p["theirs"]]
            R = len(mine)
            out = {}
            for v in ("main", "noctl", "noiss", "none", "nomargin"):
                out[v] = sum(1 for m in mine if m[v] >= 0) / R
            ver = sum(1 for m in mine if m["v"] >= 0 and m["v"] < 120) / R
            ret = sum(1 for m in mine if m["ret1"]) / R
            th1 = sum(1 for x in th if x[0] >= 0 and x[1] == 1) / R
            agree = sum(1 for m, x in zip(mine, th) if (m["main"] >= 0) == (x[0] >= 0 and x[1] == 1)) / R
            cms = [m["cm"] for m in mine if m["main"] >= 0 and m["cm"] is not None]
            taus = [m["tau"] for m in mine if m["main"] >= 0 and m["tau"] is not None]
            cm0 = sum(1 for c in cms if c <= 0) / R
            cm10 = sum(1 for c in cms if c <= 0.0010) / R
            st = {k: float(np.mean([p["stats"][k] for p in parts])) for k in parts[0]["stats"]}
            print(f"{nm:<66} R={R:<5} RUN1 {out['main']:.4f} (se {_se(out['main'], R):.4f}) | calib_w7.screen "
                  f"{th1:.4f} agree {agree:.4f} | no-control {out['noctl']:.4f} no-issuer {out['noiss']:.4f} "
                  f"neither {out['none']:.4f} no-margin {out['nomargin']:.4f} | VERSION by120 {ver:.4f} | "
                  f"retired run1 {ret:.4f} | passes' true cm <=0 {cm0:.4f} <=10bp {cm10:.4f}; passes' mean tau "
                  f"{(np.mean(taus) * 1e4 if taus else float('nan')):+.1f}bp | picks: ev/s {st['ev_s']:.2f} a7 "
                  f"{st['a7_bp']:+.1f}bp cm7 {st['cm7_bp']:+.1f}bp tau {st['tau_bp']:+.1f}bp sig {st['sig']:.3f}; "
                  f"pool a7 {st['ctl_bp']:+.1f}bp")


def selftest():
    cell, x7 = w7.corner("crasht3cl", 0.20, 0.0020, 1, T=30)
    a = w7.simulate7(cell, x7, 12345, 6)
    b = simulate_rc(cell, x7, 12345, 6, None)
    same = all(np.array_equal(np.nan_to_num(a[k], nan=-9.0), np.nan_to_num(b[k], nan=-9.0)) for k in a)
    print("selftest: simulate_rc(rmode=None) == calib_w7.simulate7 on the same seed:", same)
    rng = np.random.default_rng(1)
    ys = np.ones(8)
    print("selftest: exact p of 8 positives", flip_p(ys, rng, 0), "(1/256 =", 1 / 256, ")")
    ps = [flip_p(rng.normal(0, 1, 25), rng, 1999) for _ in range(2000)]
    print("selftest: P(p <= 0.05) under N(0,1), S = 25:", np.mean(np.array(ps) <= 0.05))
    c = simulate_rc(cell, x7, 7, 4, "o1")
    print("selftest: rmode o1 shapes", {k: v.shape for k, v in c.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report", "selftest"))
    ap.add_argument("--grid", default="smoke")
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
    elif a.cmd == "report":
        report(a.only)
    else:
        run(a.grid, a.reps, a.chunk, min(8, a.workers))

#!/usr/bin/env python
"""calib_check1.py: ADVERSARIAL CHECK #1 (statistics) of PREREG-EVL-7's learners. SYNTHETIC ONLY.

Reads nothing of the lane: no House, gateway, events.sqlite, live.sqlite, run record, price, return, look or band.
It imports the learner lens's generator and learner (evl7/learner/calib_learner.py) and adds, behind switches that
consume no random numbers when off (so the original paths are reproduced exactly):
  phi_day      the day shock's AR (a Cell field already; PREREG-EVL-6's widened plausible grid, A107 D1: 0.15, 0.20)
  lag          the training lag (a Cell field already; EVL-LRN-O1's real lag is 1, the lens ran 2)
  sig_hi       the top of the issuers' log-uniform sigma (the lens: 10%; section 1.4 caps sig20 at 25%)
  jump_sig     jump probability rising with sigma: p_i = min(5%, 0.5% x (sigma_i / 3%)^1.5), mean-compensated per event
  tau_sig      a persistent issuer effect proportional to sigma: tau_i ~ N(0, (k sigma_i)^2)
  zipf         the popularity exponent (the lens: 0.8)
  sec_drift    a persistent SECTOR drift, AR(drift_rho), sd sec_drift (learnable through the four SIC dummies)
and records each pick's TRUE conditional mean (sig Ey + stream drift + family drift + sector drift + issuer effect).

SCREENS, each applied to the same paths:
  ev6d     calib_evl7.py's screen_ev6 'ev6d' re-implemented (unweighted, looks from 6, 0.016 / 0.004, 10 bp): the draft's
  ev6d_w   the same with PREREG-EVL-6's money-weighted values y_s = min(n_s, 14) (B_s - 10 bp) (A107 D4)
  F8, F9a, F9b, F10, F12   the EVL-6 final search's shortlisted rules (evl6/final/shortlist.log), weighted (D4):
           F8  looks from 8: 0.016 S8-11, 0.012 S12-20, 0.004 S21-60    (search worst 0.148 for a fixed program)
           F9a looks from 9: 0.012 S9-16, 0.010 S17-20, 0.004 S21-60    (0.130)
           F9b looks from 9: 0.012 S9-12, 0.009 S13-20, 0.004 S21-60    (0.123)
           F10 looks from 10: 0.012 S10-12, 0.009 S13-20, 0.004 S21-60  (0.118)
           F12 looks from 12: 0.012 S12-14, 0.009 S15-20, 0.004 S21-60  (0.109)
  For each: RUN 1 (one version, ends at its 60th block) and RUNS (A107 D2: exhaustion ends a run, run n+1 starts at the
  next block, unbounded within T) -- the lifetime of one learner VERSION under PREREG-EVL-6 as it will be frozen.

Usage: calib_check1.py run --grid NAME [--reps R] [--chunk C] [--workers 4]   |   report
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "learner"))
import calib_learner as cl  # noqa: E402

U = cl.U
D = cl.D
FINAL = dict(rank="a", lam=8000.0, kappa=0.0)
W = cl.WORST
LOOKS = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
CAP = 14
HORIZON = 60
MIN_N = 30
MIN_ISS = 30
ISS_ALPHA = 0.10

RULES = {
    # name: (start, pieces, m0, weighted)
    "ev6d": (6, ((20, 0.016), (60, 0.004)), 0.0010, False),
    "ev6d_w": (6, ((20, 0.016), (60, 0.004)), 0.0010, True),
    "F8": (8, ((11, 0.016), (20, 0.012), (60, 0.004)), 0.0010, True),
    "F9a": (9, ((16, 0.012), (20, 0.010), (60, 0.004)), 0.0010, True),
    "F9b": (9, ((12, 0.012), (20, 0.009), (60, 0.004)), 0.0010, True),
    "F10": (10, ((12, 0.012), (20, 0.009), (60, 0.004)), 0.0010, True),
    "F12": (12, ((14, 0.012), (20, 0.009), (60, 0.004)), 0.0010, True),
}


# --------------------------------------------------------------------------------------------- generator additions
def issuers_x(rng, R, cell, ext):
    """calib_learner.issuers with the ext switches; identical draws when ext is empty."""
    zipf = ext.get("zipf", 0.8)
    sig_hi = ext.get("sig_hi", 0.10)
    ranks = np.argsort(rng.random((R, U)), axis=1) + 1
    logp = -zipf * np.log(ranks.astype(float))
    sector = rng.choice(11, size=(R, U), p=cl.SECTOR_W)
    lsig = rng.uniform(math.log(0.01), math.log(sig_hi), (R, U))
    sig = np.exp(lsig)
    zs = (lsig - lsig.mean()) / lsig.std()
    beta = rng.normal(0, 0.5, (R, U, 3)) + np.array([0.2, -0.1, 0.2])
    if cell.load_corr:
        zb = (beta[..., 0] - 0.2) / 0.5
        zs = cell.load_corr * zb + math.sqrt(1 - cell.load_corr ** 2) * zs
    if ext.get("tau_sig", 0.0) > 0:
        tau = rng.normal(0, 1, (R, U)) * ext["tau_sig"] * sig
    else:
        tau = rng.normal(0, cell.tau, (R, U)) if cell.tau > 0 else np.zeros((R, U))
    lnadv = -0.6 * zs + 0.8 * rng.normal(0, 1, (R, U))
    lnpx = -0.4 * zs + 0.9 * rng.normal(0, 1, (R, U))
    lnsig_f = zs + 0.3 * rng.normal(0, 1, (R, U))
    sic = np.zeros((R, U, 4))
    for g in range(4):
        sic[..., g] = (sector == g)
    sig_hat = sig * np.exp(0.15 * rng.normal(0, 1, (R, U)))
    cost = np.where(lnadv > -0.3, 0.0011, 0.0021)
    ilev = np.concatenate([lnadv[..., None], lnpx[..., None], lnsig_f[..., None], sic], axis=2)
    return dict(logp=logp, sector=sector, sig=sig, sig_hat=sig_hat, beta=beta, tau=tau, ilev=ilev, cost=cost)


def simulate_x(cell, seed, R, ext):
    """calib_learner.simulate (learner part, V1 level, kappa 0) with the ext switches and the picks' conditional mean."""
    rng = np.random.default_rng(seed)
    T, K = cell.T, cell.K
    iss = issuers_x(rng, R, cell, ext)
    Nmax = int(cell.nbar * 3.2) + 20
    sd_c = cell.sd_day()
    zday = np.zeros(R)
    vx = rng.normal(0, 0.3, R)
    drift = rng.normal(0, cell.drift_sd, R) if cell.drift_sd else np.zeros(R)
    fdrift = rng.normal(0, cell.fam_drift_sd, (R, 6)) if cell.fam_drift_sd else np.zeros((R, 6))
    sdsd = ext.get("sec_drift", 0.0)
    sdrift = rng.normal(0, sdsd, (R, 11)) if sdsd else np.zeros((R, 11))
    fac = np.zeros((R, 3))
    A = np.zeros((R, D, D))
    bv = np.zeros((R, D))
    Nw = np.zeros(R)
    rows = np.zeros(R)
    nsess = np.zeros(R)
    pend: list = []
    delta = 2.0 ** (-1.0 / cell.H) if math.isfinite(cell.H) else 1.0
    last = np.full((R, U), -10_000, dtype=np.int64)
    out_B = np.full((R, T), np.nan)
    out_Rm = np.full((R, T), np.nan)
    out_n = np.zeros((R, T), dtype=np.int16)
    out_ctrl = np.full((R, T), np.nan)
    out_iss = np.full((R, T, K), -1, dtype=np.int32)
    out_a = np.full((R, T, K), np.nan)
    out_cm = np.full((R, T, K), np.nan)
    out_sig = np.full((R, T, K), np.nan)
    um, usd, u95 = cl.u_norm(cl.W_TRUE)
    w_now = cl.W_TRUE
    jump_sig = ext.get("jump_sig", False)
    for t in range(-cell.pre, T):
        n_t = np.minimum(rng.poisson(cell.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
        ids = np.take_along_axis(ids, order, axis=1)
        valid = np.arange(Nmax)[None, :] < n_t[:, None]
        X, fam = cl.pool_features(rng, R, Nmax, iss, ids)
        if cell.null in ("A", "N2"):
            u = (X @ w_now - um) / usd
            Ey = cell.ic * np.minimum(u - u95, 0.0) if cell.null == "N2" else cell.mu_z + cell.ic * u
        else:
            Ey = np.zeros((R, Nmax))
        sig = np.take_along_axis(iss["sig"], ids, axis=1)
        sig_hat = np.take_along_axis(iss["sig_hat"], ids, axis=1)
        cost = np.take_along_axis(iss["cost"], ids, axis=1)
        sec = np.take_along_axis(iss["sector"], ids, axis=1)
        beta = np.take_along_axis(iss["beta"], ids[..., None], axis=1)
        tau = np.take_along_axis(iss["tau"], ids, axis=1)
        zday = cell.phi_day * zday + math.sqrt(1 - cell.phi_day ** 2) * cl.day_innov(rng, cell.day, R)
        c_t = sd_c * zday
        vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
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
        pj = np.minimum(0.05, 0.005 * (sig / 0.03) ** 1.5) if jump_sig else 0.005
        jump = np.where(rng.random((R, Nmax)) < pj, np.where(rng.random((R, Nmax)) < jl, -0.30, 0.30), 0.0)
        jump = jump - pj * 0.30 * (1 - 2 * jl)
        noise = h_t[:, None] * (c_t[:, None] + np.take_along_axis(s_sec, sec, axis=1)
                                + np.einsum("rnk,rk->rn", beta, fac) + sig * e)
        sd_term = np.take_along_axis(sdrift, sec, axis=1)
        cmean = sig * Ey + drift[:, None] + np.take_along_axis(fdrift, fam, axis=1) + sd_term + tau
        a = cmean + noise + jump
        a = np.maximum(a, -1.0)
        r = a + b_t[:, None]
        y = np.clip(a / sig_hat, -5, 5)
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
            As_ = A / (dsd[:, :, None] * dsd[:, None, :]) + cell.lam * np.eye(D)[None]
            bs_ = bv / dsd
            beta_s = np.linalg.solve(As_, bs_[..., None])[..., 0]
            bhat = beta_s / dsd
            ehat = np.einsum("rnd,rd->rn", Xc, bhat)
            zhat = -cost / sig_hat + ehat
            key = zhat * sig_hat if cell.rank == "a" else zhat
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
            out_cm[:, t, :] = np.where(ok, np.take_along_axis(cmean, top, axis=1), np.nan)
            out_sig[:, t, :] = np.where(ok, np.take_along_axis(sig, top, axis=1), np.nan)
            rr, kk = np.nonzero(ok)
            last[rr, pid[rr, kk]] = t
        ybar = (y * vf).sum(axis=1) / nv
        Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
        yd = (y - ybar[:, None]) * vf
        As = np.matmul(Xd.transpose(0, 2, 1), Xd)
        bs = np.einsum("rnd,rn->rd", Xd, yd)
        pend.append((t, As, bs, vf.sum(axis=1)))
    return dict(B=out_B, Rm=out_Rm, n=out_n, ctrl=out_ctrl, iss=out_iss, a=out_a, cm=out_cm, sig=out_sig)


# --------------------------------------------------------------------------------------------- the screens
def alpha_of(pieces, S):
    lo = 0
    for s_up, a in pieces:
        if lo < S <= s_up:
            return a
        lo = s_up
    return 0.0


def screen_runs(sim, rep, rule, runs=True):
    """First pass under `rule` on replicate `rep`: (session of pass or -1, run index of the pass, the record's TRUE
    conditional mean a (event-weighted) at the pass, n runs started). RUNS: after a run's 60th block, the next run
    starts with the next block on a fresh record (A107 D2); runs=False stops after run 1 (the one-version figure)."""
    start_k, pieces, m0, weighted = RULES[rule]
    B, Rm, n, ctrl = sim["B"][rep], sim["Rm"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av, cmv = sim["iss"][rep], sim["a"][rep], sim["cm"][rep]
    T = len(B)
    sl = [s for s in LOOKS if s >= start_k]
    run = 1
    t0 = 0
    while t0 < T:
        blocks, w, bsess, ev_iss, ev_a, ev_cm = [], [], [], [], [], []
        ev_r_sum = 0.0
        seen: set = set()
        k = 0
        ended_at = -1
        for t in range(t0, T):
            kk = int(n[t])
            if kk == 0:
                continue
            a_t = av[t, :kk].astype(float)
            blocks.append(float(a_t.mean()))
            w.append(min(kk, CAP) if weighted else 1)
            bsess.append(t)
            ev_iss.extend(int(x) for x in iss[t, :kk])
            ev_a.extend(float(x) for x in a_t)
            ev_cm.extend(float(x) for x in cmv[t, :kk])
            ev_r_sum += float(Rm[t]) * kk
            seen.update(int(x) for x in iss[t, :kk])
            S = len(blocks)
            N = len(ev_a)
            if k < len(sl) and S >= sl[k] and S >= 6 and N >= MIN_N and len(seen) >= MIN_ISS:
                while k < len(sl) and S >= sl[k]:
                    k += 1
                alpha = alpha_of(pieces, S)
                xb = np.array(blocks)
                wv = np.array(w, float)
                mean_a = sum(ev_a) / N
                yq = -wv * xb
                if mean_a < 0 and cl.zstat(yq) >= cl.Z_PRE and cl.flip_p(yq) <= alpha + cl.TIE:
                    return -1, run, None, run            # RETIRE (the version ends)
                y = wv * (xb - m0)
                if cl.zstat(y) >= cl.Z_PRE and cl.flip_p(y) <= alpha + cl.TIE and mean_a > 0 and ev_r_sum / N > 0:
                    cm = float(np.mean(ctrl[bsess]))
                    if xb.mean() > cm and cl.issuer_p(ev_iss, ev_a, cl.B_ISS6) <= ISS_ALPHA + cl.TIE:
                        return t, run, float(np.mean(ev_cm)), run
            if S >= HORIZON:
                ended_at = t
                break
        if ended_at < 0 or not runs:
            return -1, run, None, run
        run += 1
        t0 = ended_at + 1
    return -1, run, None, run


# --------------------------------------------------------------------------------------------- cells
def C(name, **kw):
    ext = kw.pop("ext", {})
    return cl.Cell(name, **kw), ext


WN = W | dict(tau=0.0)


def grid(name):
    """(cell, ext) pairs and the first seed. Fresh seeds (9xx,000,001) except 'repro' (the judge's own)."""
    if name == "repro":       # the judge's F-N1-worst-n300 cell, its own seeds (81e6 + 1 + 1000 x 1): validates the screen
        return [C("R-N1-worst-n300", nbar=300, **(W | FINAL))], 81_001_001
    if name == "phi":
        return [C("N1-worst-phi15-n300", nbar=300, **(W | FINAL | dict(phi_day=0.15))),
                C("N1-worst-phi20-n300", nbar=300, **(W | FINAL | dict(phi_day=0.20))),
                C("N1-worst-phi20-lag1-n300", nbar=300, **(W | FINAL | dict(phi_day=0.20, lag=1))),
                C("N1-worst-phi10-lag1-n300", nbar=300, **(W | FINAL | dict(lag=1))),
                C("N1-worst-phi20-n800", nbar=800, **(W | FINAL | dict(phi_day=0.20)))], 91_000_001
    if name == "tails":
        return [C("N1-worst-phi20-jumpsig-n300", nbar=300, ext=dict(jump_sig=True), **(W | FINAL | dict(phi_day=0.20))),
                C("N1-worst-phi20-sig20-n300", nbar=300, ext=dict(sig_hi=0.20), **(W | FINAL | dict(phi_day=0.20))),
                C("N1-worst-phi20-tausig-zipf1-n300", nbar=300, ext=dict(tau_sig=0.25, zipf=1.0),
                  **(W | FINAL | dict(phi_day=0.20)))], 92_000_001
    if name == "drifts":
        return [C("N3-secdrift20-phi10-lag1-n300", nbar=300, ext=dict(sec_drift=0.0020), **(WN | FINAL | dict(lag=1))),
                C("N3-famdrift20-phi10-lag1-n300", nbar=300, fam_drift_sd=0.0020, **(WN | FINAL | dict(lag=1))),
                C("N3-secdrift20-phi20-lag1-n300", nbar=300, ext=dict(sec_drift=0.0020), **(WN | FINAL | dict(lag=1, phi_day=0.20)))], 93_000_001
    if name == "life":
        return [C("N1-worst-notau-phi20-n300-T300", nbar=300, T=300, **(WN | FINAL | dict(phi_day=0.20))),
                C("N1-worst-notau-phi10-n300-T300", nbar=300, T=300, **(WN | FINAL))], 94_000_001
    if name == "base":
        return [C("N1-base-n300", nbar=300, **FINAL), C("N1-base-phi20-n300", nbar=300, **(FINAL | dict(phi_day=0.20)))], 95_000_001
    raise SystemExit(f"unknown grid {name}")


def _job(args):
    cell, ext, seed, R, orig = args
    t0 = time.time()
    if orig:
        sim = cl.simulate(cell, seed, R)
        sim["cm"] = np.zeros_like(sim["a"])
    else:
        sim = simulate_x(cell, seed, R, ext)
    out = {"cell": cell.name, "ext": ext, "seed": seed, "R": R, "T": cell.T}
    for rule in RULES:
        allr = [screen_runs(sim, i, rule, runs=True) for i in range(R)]
        # RUN 1 alone (one version as the draft counts it) is the prefix of the runs: a pass in run 1, else none
        out[rule] = dict(when=[x[0] if x[1] == 1 else -1 for x in allr], cm=[x[2] if x[1] == 1 else None for x in allr],
                         rwhen=[x[0] for x in allr], rrun=[x[1] for x in allr], rcm=[x[2] for x in allr],
                         nruns=[x[3] for x in allr])
    with np.errstate(invalid="ignore"):
        out["ev_s"] = float(sim["n"].mean())
        out["mean_a_bp"] = float(np.nanmean(sim["a"]) * 1e4)
        out["mean_cm_bp"] = float(np.nanmean(sim["cm"]) * 1e4)
        out["mean_sig_picks"] = float(np.nanmean(sim["sig"])) if "sig" in sim else None
        # issuer concentration of the picks: mean over replicates of the share of picks taken by the top-10 issuers
        shares = []
        for i in range(R):
            ids = sim["iss"][i][sim["iss"][i] >= 0]
            if ids.size:
                _, cnt = np.unique(ids, return_counts=True)
                shares.append(np.sort(cnt)[::-1][:10].sum() / ids.size)
        out["top10_share"] = float(np.mean(shares)) if shares else None
    out["secs"] = round(time.time() - t0, 1)
    return out


def run(gridname, reps, chunk, workers):
    from multiprocessing import Pool
    cells, seed0 = grid(gridname)
    orig = gridname == "repro"
    jobs = []
    for ci, (cell, ext) in enumerate(cells):
        for j in range(max(1, reps // chunk)):
            jobs.append((cell, ext, seed0 + 1000 * ci + j, chunk, orig))
    path = os.path.join(HERE, f"check1.{gridname}.jsonl")
    t0 = time.time()
    with Pool(workers) as pool, open(path, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gridname}: {k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)


def _se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / max(n, 1))


def report(only=None):
    for path in sorted(glob.glob(os.path.join(HERE, "check1.*.jsonl"))):
        if only and only not in path:
            continue
        rows = [json.loads(x) for x in open(path)]
        by: dict = {}
        for r in rows:
            by.setdefault(r["cell"], []).append(r)
        print(f"== {os.path.basename(path)}")
        for name, parts in by.items():
            R = sum(p["R"] for p in parts)
            T = parts[0]["T"]
            ev = np.mean([p["ev_s"] for p in parts])
            ma = np.mean([p["mean_a_bp"] for p in parts])
            mc = np.mean([p["mean_cm_bp"] for p in parts])
            sg = [p["mean_sig_picks"] for p in parts if p.get("mean_sig_picks") is not None]
            t10 = np.mean([p["top10_share"] for p in parts if p.get("top10_share") is not None])
            print(f"{name:<38} R={R:<5} T={T:<4} ev/s={ev:.2f} mean_a={ma:.1f}bp mean_true_cm={mc:.1f}bp "
                  f"sig_picks={np.mean(sg) if sg else float('nan'):.3f} top10_issuer_share={t10:.3f}")
            for rule in RULES:
                wh = np.concatenate([p[rule]["when"] for p in parts])
                cm = [c for p in parts for c in p[rule]["cm"]]
                rwh = np.concatenate([p[rule]["rwhen"] for p in parts])
                rrun = np.concatenate([p[rule]["rrun"] for p in parts])
                one = float((wh >= 0).mean())
                by120 = float(((wh >= 0) & (wh < 120)).mean())
                allp = float((rwh >= 0).mean())
                byh = " ".join(f"by{h}={((rwh >= 0) & (rwh < h)).mean():.3f}" for h in (60, 120, 180, 240, 300) if h <= T)
                # conditionally false: the record's true conditional mean at the pass <= 0 / <= 10 bp
                cmo = np.array([c if c is not None else np.nan for c in cm])
                f0 = float(((wh >= 0) & (cmo <= 0)).mean())
                f10 = float(((wh >= 0) & (cmo <= 0.0010)).mean())
                print(f"   {rule:<7} run 1: pass={one:.4f} (se {_se(one, R):.4f})  [true cm<=0: {f0:.4f}; <=10bp: {f10:.4f}]"
                      f" | all runs: pass={allp:.4f} {byh} | runs started (mean) {np.mean(np.concatenate([p[rule]['nruns'] for p in parts])):.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report"))
    ap.add_argument("--grid", default="repro")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    if a.cmd == "report":
        report(a.only)
        sys.exit(0)
    run(a.grid, a.reps, a.chunk, min(4, a.workers))

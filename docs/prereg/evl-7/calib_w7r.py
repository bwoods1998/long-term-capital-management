#!/usr/bin/env python
"""calib_w7r.py: PREREG-EVL-7's calibration ON THE REGISTERED COLUMNS (the final fix round; re-check 1's blocker).
SYNTHETIC ONLY. Nothing here reads the lane: no House, gateway, events.sqlite, live.sqlite, run record, price, return,
look or band.

WHY. Re-check 1 (evl7/recheck1/rc1.py) found that calib_w7.py drew section 1.4 item 11's r1 / r5 / r20 and EVL-LRN-ON's
dmove as fresh t(3) noise, while they are the issuer's own trailing returns and so hold its own earlier pool legs; under
the frozen grid's 1% persistent issuer effect they act as a noisy target encoding (0.1205 / 0.1247 at the worst cell,
0.199 at pool 800). The fix (re-check 1's): r1, r5 and r20 are DELETED (D = 54 for EVL-LRN-O1, 60 for EVL-LRN-ON), and
every remaining own-price column is built from the issuer's own simulated returns, issuer effect included.

THE GENERATOR: re-check 1's simulate_rc (rc1.py, itself calib_w7.simulate7 line for line plus own returns), copied
here with three changes, each behind a switch that draws nothing when off:
  (1) DROP: the learner's columns 35-37 (the lens's r1 / r5 / r20) are set to 0 after the truth is computed, which is
      exactly the same fit as deleting them (a zero column decouples from the ridge: its row and column of A and its
      entry of b are 0, so its beta is 0 and every other beta is unchanged). Under the alternative the truth keeps the
      lens's r1 weight (-0.2) on the now UNSEEN column: a short-term reversal the learner no longer reads (power falls a
      little; nothing is gained).
  (2) ON'S dmove (column 39) from the issuer's own returns (rc1.py's 'ondm' construction): dmove = leg(t-1) (the
      issuer's close t-1 -> open t leg, its event a_g when it was in the pool, issuer effect included) + 0.9 x the
      complementary-leg noise, clipped to +-0.5. Under the alternative and the knife edge the truth reads it
      standardized within the session (so the lens's -0.3 weight keeps its meaning); the learner reads it raw.
  (3) LEVELS (lev): ln(adv20 / 1e7) and ln(prev_close / 20) (columns 28, 29) are the lens's static draws PLUS the
      issuer's own cumulative close-to-close log return since the start of the burn-in (dollar volume at constant share
      turnover follows the price), so the price level carries every own earlier pool leg too.
  Own returns as rc1.py: every issuer has a return every session, its event's a_g when in the pool, else
  h_t (s_sector + beta . f + sigma e) (no issuer effect, no jump), plus the complementary leg of the same day (sd 0.6 x
  h_t x sigma); a 25-session burn-in fills the history before the pre-registration sessions (it trains nothing).
  sig20 stays the lens's static draw (an own-return column whose own-leg content is |tau|-symmetric: E[tau | sig20] = 0;
  re-check 1 allows it).
THE LEARNERS: 'o1' (EVL-LRN-O1: D = 57 - 3 = 54, open -> close legs, no dmove; its column 39 is the lens's noise) and
'on' (EVL-LRN-ON: D = 63 - 3 = 60, close -> next open legs, dmove from own returns).
THE SCREEN: calib_w7.screen (PREREG-EVL-6 sections 1-3 as frozen, sha256 0f67f94e...; validated against check 1,
validate_w7.out; agreed with rc1.py's independent screen on 99.4-100% of programs in every re-check cell).
Seeds (unused by every earlier calibration of EVL-6 to -10): 500e6 + pilot, 501e6 + search, 502e6 + fresh, 503e6 +
power, 504e6 + life, 505e6 + stresses, 506e6 + sensitivities and the base model, 507e6 + the family drift.
THE PILOT (run first, w7r.pilot.*) found the levels a channel too (EVL-LRN-O1 at the worst corner, pool 300: 0.128 with
own-return levels against 0.083 with the lens's static ones), so the registered learners DELETE THEM as well (lev
'drop', the default: columns 28 and 29 set to 0 after the truth): D = 52 for EVL-LRN-O1 and 58 for EVL-LRN-ON.
Usage: calib_w7r.py run --grid NAME [--reps R] [--chunk C] [--workers W] | report [--only NAME] | selftest
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
sys.path.insert(0, HERE)
for _p in (os.path.join(os.path.dirname(HERE), "learner"), HERE):
    if os.path.exists(os.path.join(_p, "calib_learner.py")):
        sys.path.insert(1, _p)
        break
import calib_w7 as w7  # noqa: E402

cl = w7.cl
U = cl.U
D0 = w7.D0
BURN = 25
RCOLS = (35, 36, 37)          # the lens's r1 / r5 / r20 (calib_learner.py's index note)


# ------------------------------------------------------------------------------------------------ the generator
def simulate_r(cell, x7, seed, R, learner=None, drop=True, lev=True, leg_sd=0.6):
    """learner None: calib_w7.simulate7 exactly (no own returns, no drop). 'o1' / 'on': see the module docstring."""
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
    own = learner is not None and (learner == "on" or lev is True)
    if own:
        leg = np.zeros((32, R, U))      # leg_t: the held leg of day t (event a_g in the pool, else idiosyncratic)
        oth = np.zeros((32, R, U))      # the complementary leg of the same day
        cum = np.zeros((R, U))          # the cumulative own close-to-close log return through the previous close
    t_start = -cell.pre - (BURN if own else 0)
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
        dm_std = None
        if own:
            if lev is True:               # (3) the price and dollar-volume levels carry the own cumulative return
                cpool = np.take_along_axis(cum, ids, axis=1)
                X[..., 28] = X[..., 28] + cpool
                X[..., 29] = X[..., 29] + cpool
            if learner == "on":           # (2) dmove from the issuer's own returns (rc1.py's 'ondm')
                eo = cl.unit_t3(rng, (R, Nmax))
                h_now = np.exp(vx - 0.09)
                dm = np.take_along_axis(leg[(t - 1) % 32], ids, axis=1) + 0.9 * leg_sd * h_now[:, None] * sig * eo
                X[..., 39] = np.clip(dm, -0.5, 0.5)
                if cell.null in ("A", "A2", "N2"):
                    vf0 = valid.astype(float)
                    n0 = np.maximum(vf0.sum(axis=1), 1)
                    m0 = (X[..., 39] * vf0).sum(axis=1) / n0
                    s0 = np.sqrt(np.maximum((((X[..., 39] - m0[:, None]) ** 2) * vf0).sum(axis=1) / n0, 1e-12))
                    dm_std = (X[..., 39] - m0[:, None]) / s0[:, None]
        if cell.null in ("A", "A2", "N2"):
            Xt = X[..., :D0]
            if dm_std is not None:
                Xt = Xt.copy()
                Xt[..., 39] = dm_std
            u = (Xt @ w_now - um) / usd
            Ey = cell.ic * np.minimum(u - u95, 0.0) if cell.null == "N2" else cell.mu_z + cell.ic * u
        else:
            Ey = np.zeros((R, Nmax))
        if learner is not None and drop:   # (1) r1 / r5 / r20 deleted from the learner (after the truth)
            X[..., RCOLS[0]:RCOLS[-1] + 1] = 0.0
        if lev == "drop":                  # (4) a sensitivity: the two levels deleted as well
            X[..., 28:30] = 0.0
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
        if own:                           # this day's returns of every issuer, the pool's legs their events' a_g
            isig = iss["sig"]
            idio = h_t[:, None] * (np.take_along_axis(s_sec, iss["sector"], axis=1)
                                   + np.einsum("ruk,rk->ru", iss["beta"], fac) + isig * cl.unit_t3(rng, (R, U)))
            rr_, nn_ = np.nonzero(valid)
            idio[rr_, ids[rr_, nn_]] = a_g[rr_, nn_]
            leg[t % 32] = idio
            oth[t % 32] = leg_sd * h_t[:, None] * isig * cl.unit_t3(rng, (R, U)) if leg_sd > 0 else 0.0
            if learner == "o1":           # close t = close t-1 + overnight(t) + day leg(t)
                cum += oth[t % 32] + leg[t % 32]
            else:                         # close t = close t-1 + ON leg(t-1) + day(t)
                cum += leg[(t - 1) % 32] + oth[t % 32]
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


# ------------------------------------------------------------------------------------------------ cells
SPECS: dict = {}


def cellr(learner, shape="crasht3cl", phi=0.20, drift=0.0020, lag=None, pool=300, tau=0.01, skew=True, cnt=0.0,
          rho=0.15, null="N1", ic=0.0, T=120, gross=True, lev="drop", fam=0.0, sec=0.0, extra=None, load_corr=0.0,
          fac_rho=0.0):
    """One cell for a learner: calib_w7.corner's cell with the learner's column count and the own-return switches."""
    lag = lag if lag is not None else (1 if learner == "o1" else 2)
    ex = extra if extra is not None else (17 if learner == "o1" else 23)
    cell, x7 = w7.corner(shape, phi, drift, lag, pool=pool, tau=tau, skew=skew, cnt=cnt, rho=rho, extra=ex, null=null,
                         ic=ic, T=T, gross=gross)
    if fam or load_corr or fac_rho:
        cell = dataclasses.replace(cell, fam_drift_sd=fam, load_corr=load_corr, fac_rho=fac_rho)
    if sec:
        x7 = dataclasses.replace(x7, sec_drift=sec)
    Dn = 40 + ex - 3
    base = cell.name.rsplit("-D", 1)[0]
    rest = cell.name.rsplit("-D", 1)[1]
    rest = rest[2:] if rest[:2].isdigit() else rest
    nm = (f"{learner.upper()}-{base}-D{Dn - (2 if lev == 'drop' else 0)}{rest}"
          f"{'' if lev == 'drop' else ('-ownlevels' if lev is True else '-static')}"
          + (f"-famdrift{int(round(fam * 1e4))}" if fam else "") + (f"-secdrift{int(round(sec * 1e4))}" if sec else "")
          + (f"-loadcorr{int(round(load_corr * 10))}-fac{int(round(fac_rho * 100))}" if load_corr else ""))
    cell = dataclasses.replace(cell, name=nm)
    spec = dict(learner=learner, shape=shape, phi=phi, drift=drift, lag=lag, pool=pool, tau=tau, skew=skew, cnt=cnt,
                rho=rho, null=null, ic=ic, T=T, gross=gross, lev=lev, fam=fam, sec=sec, extra=ex, load_corr=load_corr,
                fac_rho=fac_rho)
    SPECS[nm] = spec
    return cell, x7, spec


def grid(name):
    cells = []
    if name == "pilot":        # the levels: static (the lens's) against built from own returns, O1 at the worst corner
        # (run first with lev True / False when True was the default and named with no suffix: its file's names are
        # 'O1-...-D54' for the own-return levels and 'O1-...-D54-static' for the lens's static levels)
        for pool in (300, 800):
            for lev in (False, True):
                cells.append(cellr("o1", pool=pool, lev=lev))
        return cells, 500_000_001
    if name == "search":       # the frozen plausible grid as each learner meets it (section 5.3)
        for L, real in (("o1", 1), ("on", 2)):
            for lag in (1, 2):
                for sh in w7.SHAPES:                                   # the four crash-day shapes at the corner
                    cells.append(cellr(L, shape=sh, lag=lag))
                for sh in ("crashcl", "crasht3cl"):                    # pool 800: the two clustered shapes
                    cells.append(cellr(L, shape=sh, lag=lag, pool=800))
                if lag != real:
                    continue
                for pool in (300, 800):                                # the corner's other factors at the real lag
                    cells.append(cellr(L, lag=lag, pool=pool, tau=0.0))        # no issuer effect
                    cells.append(cellr(L, lag=lag, pool=pool, cnt=0.3))        # counts that follow the day (at pool
                    #   800 the lens's 3,000-issuer universe cannot hold the count's cap: run() skips that cell)
                cells.append(cellr(L, lag=lag, phi=0.15))                      # phi_day 0.15
                cells.append(cellr(L, lag=lag, drift=0.0))                     # no drift
                cells.append(cellr(L, lag=lag, skew=False))                    # symmetric events
                cells.append(cellr(L, lag=lag, rho=0.05))                      # rho_day 0.05
                cells.append(cellr(L, lag=lag, null="N2", ic=0.05))            # the knife edge
        # (the fix round's search measured a 10 bp drift, phi_day 0.10 and symmetric days below the corner at every
        # shape; they are left out here, with the factors other than the day shape at each learner's other lag)
        return cells, 501_000_001
    if name == "fresh":
        for sp in json.loads(os.environ["W7R_CELLS"]):
            cells.append(cellr(**sp))
        return cells, int(os.environ.get("W7R_SEED", "502000001"))
    if name == "power":        # lag 1 = EVL-LRN-O1 (D 54), lag 2 = EVL-LRN-ON (D 60, own dmove); the base model
        B = dict(shape="t3", phi=0.10, drift=0.0, rho=0.05, skew=False, tau=0.0, null="A")
        for ic in (0.03, 0.05, 0.08):
            cells.append(cellr("on", pool=800, ic=ic, **B))
        cells.append(cellr("o1", pool=800, ic=0.05, **B))
        cells.append(cellr("on", pool=300, ic=0.05, **B))
        cells.append(cellr("on", pool=800, tau=0.0, null="A", ic=0.05))            # the worst corner, no issuer effect
        return cells, 503_000_001
    if name == "life":
        for sp in json.loads(os.environ["W7R_CELLS"]):
            cells.append(cellr(**dict(sp, T=200)))
        return cells, 504_000_001
    if name == "fam":          # re-check 1's minor: a learnable 20 bp family drift at the corner, pools 300 and 800
        for L in ("o1", "on"):
            for pool in (300, 800):
                cells.append(cellr(L, fam=0.0020, pool=pool))
        return cells, 507_000_001
    if name == "stress":
        for L in ("o1", "on"):
            cells.append(cellr(L, phi=0.25))                                       # phi_day 0.25
            cells.append(cellr(L, tau=0.0, sec=0.0020, shape="crash"))             # a learnable sector drift
            cells.append(cellr(L, fam=0.0020, shape="crash", phi=0.10, tau=0.0))   # the fix round's family-drift cell
        cells.append(cellr("on", shape="crash", phi=0.10, rho=0.30))              # rho_day 0.30
        cells.append(cellr("on", shape="crash", phi=0.25, rho=0.30))              # day momentum 0.25
        cells.append(cellr("on", shape="crash", phi=0.40, rho=0.30))              # day momentum 0.40
        cells.append(cellr("on", drift=0.0030))                                    # a 30 bp drift
        cells.append(cellr("on", shape="crash", tau=0.0, load_corr=0.7, fac_rho=0.25))   # check 2's cell
        return cells, 505_000_001
    if name == "sens":         # the base model, both learners
        Bm = dict(shape="t3", phi=0.10, drift=0.0, rho=0.05, skew=False, tau=0.0)
        cells.append(cellr("o1", **Bm))
        cells.append(cellr("on", **Bm))
        return cells, 506_000_001
    if name == "smoke":
        cells.append(cellr("o1", T=30))
        cells.append(cellr("on", T=30, pool=800))
        cells.append(cellr("on", T=30, null="A", ic=0.05, tau=0.0))
        return cells, 509_000_001
    raise SystemExit(f"unknown grid {name}")


def _job(args):
    cell, x7, spec, seed, R = args
    t0 = time.time()
    sim = simulate_r(cell, x7, seed, R, spec["learner"], True, spec["lev"])
    res = {"cell": cell.name, "seed": seed, "R": R, "T": cell.T, "x7": dataclasses.asdict(x7),
           "cellp": dataclasses.asdict(cell), "spec": spec}
    bases = ("a7", "arep") if cell.null in ("A", "A2") else ("a7",)
    for basis in bases:
        allr = [w7.screen(sim, i, "frozen", basis) for i in range(R)]
        cap3 = [w7.screen(sim, i, "frozen", basis, max_runs=3) for i in range(R)] if cell.T > 120 else None
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
        res["tau_picks_bp"] = float(np.nanmean(sim["taup"]) * 1e4)
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


def run(gridname, reps, chunk, workers, tag=None, resume=False):
    from multiprocessing import Pool
    cells, seed0 = grid(gridname)
    path = os.path.join(HERE, f"w7r.{tag or gridname}.jsonl")
    done = set()
    if resume and os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            done.add((r["cell"], r["seed"]))
    jobs = []
    for ci, (cell, x7, spec) in enumerate(cells):
        if int(cell.nbar * (4.5 if x7.cnt else 3.2)) + 20 > U:   # the lens's 3,000-issuer universe cannot hold it
            print(f"{gridname}: SKIPPED {cell.name}: its count's cap exceeds the {U}-issuer universe", flush=True)
            continue
        for j in range(max(1, reps // chunk)):
            if (cell.name, seed0 + 1000 * ci + j) not in done:
                jobs.append((cell, x7, spec, seed0 + 1000 * ci + j, chunk))
    t0 = time.time()
    with Pool(workers) as pool, open(path, "a" if resume else "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gridname}: {k + 1}/{len(jobs)} {res['cell']} seed {res['seed']} {res['secs']}s "
                  f"total {time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------------------------------------ report
def summarise(parts, basis="a7"):
    s = w7.summarise(parts, basis)
    s["tau_bp"] = float(np.mean([p.get("tau_picks_bp", np.nan) for p in parts]))
    s["c7_bp"] = float(np.mean([p["c7_picks_bp"] for p in parts]))
    s["crep_bp"] = float(np.mean([p["crep_picks_bp"] for p in parts]))
    return s


def load(name):
    by: dict = {}
    for line in open(os.path.join(HERE, f"w7r.{name}.jsonl")):
        r = json.loads(line)
        by.setdefault(r["cell"], []).append(r)
    return by


def report(only=None):
    for path in sorted(glob.glob(os.path.join(HERE, "w7r.*.jsonl"))):
        if only and only not in os.path.basename(path):
            continue
        by = load(os.path.basename(path)[4:-6])
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
                print(f"{name:<66} {basis:<4} R={s['R']:<5} RUN1 {s['run1']:.4f} (se {s['run1_se']:.4f}) "
                      f"[cm<=0 {s['cm0']:.4f} <=10bp {s['cm10']:.4f}] by10/20/40/60 {s['by10']:.3f}/{s['by20']:.3f}/"
                      f"{s['by40']:.3f}/{s['by60']:.3f} | VERSION by120 {s['v120']:.4f} runs {s['runs']:.2f} "
                      f"retired {s['retired']:.3f} | ev/s {s['ev_s']:.2f} pool {s['npool']:.0f} a7 "
                      f"{s['mean_a7_bp']:+.1f}bp cm7 {s['mean_cm7_bp']:+.1f}bp tau {s['tau_bp']:+.1f}bp sig "
                      f"{s['sig_picks']:.3f} c7/crep {s['c7_bp']:.1f}/{s['crep_bp']:.1f}bp{extra}")
                if any(np.isfinite(v) and v != 0 for v in s["edge7_bp"].values()):
                    print("      picks' true a7 edge (bp) " + " ".join(f"{k}:{v}" for k, v in s["edge7_bp"].items()))


def selftest():
    cell, x7 = w7.corner("crasht3cl", 0.20, 0.0020, 1, T=30)
    a = w7.simulate7(cell, x7, 12345, 6)
    b = simulate_r(cell, x7, 12345, 6, None)
    same = all(np.array_equal(np.nan_to_num(a[k], nan=-9.0), np.nan_to_num(b[k], nan=-9.0)) for k in a)
    print("selftest: simulate_r(learner=None) == calib_w7.simulate7 on the same seed:", same)
    rc_dir = os.path.join(os.path.dirname(HERE), "recheck1")
    if os.path.exists(os.path.join(rc_dir, "rc1.py")):
        sys.path.insert(0, rc_dir)
        import rc1
        cell2, x72 = w7.corner("crasht3cl", 0.20, 0.0020, 2, extra=23, T=30)
        c = rc1.simulate_rc(cell2, x72, 777, 5, "ondm")
        d = simulate_r(cell2, x72, 777, 5, "on", drop=False, lev=False)
        same2 = all(np.array_equal(np.nan_to_num(c[k], nan=-9.0), np.nan_to_num(d[k], nan=-9.0)) for k in c)
        print("selftest: simulate_r('on', drop=False, lev=False) == rc1.simulate_rc(rmode='ondm') on the same seed:",
              same2)
    # the zero-column equivalence: ridge on [X, 0] gives the same beta as ridge on X
    rng = np.random.default_rng(3)
    Xs = rng.normal(size=(400, 6))
    ys = Xs @ np.array([0.2, 0, -0.1, 0, 0.05, 0]) + rng.normal(size=400)
    Xz = np.concatenate([Xs, np.zeros((400, 2))], axis=1)

    def ridge(Xm, yv, lam=50.0):
        Am = Xm.T @ Xm
        dd = np.sqrt(np.maximum(np.diag(Am) / len(yv), 1e-12))
        Ms = Am / (dd[:, None] * dd[None, :]) + lam * np.eye(Xm.shape[1])
        return np.linalg.solve(Ms, (Xm.T @ yv) / dd) / dd
    b1, b2 = ridge(Xs, ys), ridge(Xz, ys)
    print("selftest: ridge with two zero columns == ridge without them:", bool(np.allclose(b1, b2[:6], atol=1e-12)),
          "; zero columns' beta", b2[6:].tolist())
    e = simulate_r(*w7.corner("crasht3cl", 0.20, 0.0020, 1, T=30), 5, 4, "o1")
    print("selftest: o1 with levels runs; picks a session", float(e["n"].mean()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report", "selftest"))
    ap.add_argument("--grid", default="smoke")
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
    elif a.cmd == "report":
        report(a.only)
    else:
        run(a.grid, a.reps, a.chunk, min(8, a.workers), a.tag, a.resume)

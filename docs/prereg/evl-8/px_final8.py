#!/usr/bin/env python
"""px_final8.py: PREREG-EVL-8's FINAL calibration of THE PX SEATS (PX-DROP-ON, PX-SURGE-ON, PX-GAP-O1) under
PREREG-EVL-6 AS FROZEN (docs/prereg/PREREG-EVL-6.md at tag prereg-evl-6, sha256 0f67f94e...), SYNTHETIC ONLY.

Nothing here reads the lane, the House, the gateway, events.sqlite, live.sqlite or any market data: no price, bar,
volume, return, look or band of any symbol or program. Every number comes from the generator below.

THE SCREEN is the frozen one, run by the frozen code: the per-(program, session) record of
`goal-2026-10-19/evl6/final/calib_final.py` (its `Record` arrays: S, blocks, the minimums, the guards, p, q, the issuer
guard; its `signflip_p_rows`, `issuer_p`, prefilters and Monte Carlo shortcuts, imported unchanged) and the frozen
rule evaluation `search_final.py` (`first_pass`, `two_runs`, `look_mask`: looks at the frozen thresholds S_k from the
rule's start, alpha(S) by the record's own S, PASS with no tolerance, RETIRE first, the run ends at its 60th block and
RUN 2 starts with block 61), imported unchanged. The ONLY difference from the frozen calibration is the cap of the
money weights and the top-CAP guard (the captain's F4: CAP = the band's open cap; a PX version's run is judged in
learning, CAP 4 by the money row event.max_open_v8.learning) and the generator.

THE RULES EVALUATED: the frozen schedule (alpha 0.020 for S 22-30, 0.006 for 31-40, 0.001 for 41-60, 10 bp margin)
with its first look moved to each later frozen threshold: F = 22 (the frozen rule), 25, 30, 35, 40 (the looks are the
frozen list's from F on; nothing else changes: the captain's F1).

THE GENERATOR is the PX designer's (`goal-2026-10-19/evl8/price/px_calib.py` `generate`, copied below with its random
stream unchanged when no addition is on: `selftest` checks it draws the same arrays): high-beta losers against a
crash-prone index benchmark, Zipf repeat issuers, hot sectors, a persistent family drift AR(0.97), left-skewed events
with distress jumps, persistent issuer effects, counts that follow the volatility regime, a control block. ADDED (the
frozen plausible grid of PREREG-EVL-6 section 4.3, each day still mean 0 and variance 1, as `calib_v2.py` builds them):
  - the day shock's shapes crasht3 (crash days with a t(3) body), crashcl (crash days clustered in high-volatility
    regimes: p_t = 0.05 exp(2 x_t) / E[exp(2 x)], at most 0.09, x_t the generator's own volatility state) and crasht3cl
    (both), beside the designer's t3 and crash; the benchmark's crash days take the same shape (crash_m);
  - counts that follow the size of the day shock: the rule's qualifying count x exp(0.3 min(|eps_t|, 4)) / its mean,
    with the null set on MONEY weights (the money knife: the mean a weighted by min(n_t, CAP) is exactly 0);
  - an edge on the top-ranked events only (money's population: check 1's attack, reported, never in the grid);
  - a family drift shared by two seats (check 1's SHARED attack: P(both pass)).
THE PX PLAUSIBLE GRID (`grid('search')`): the knife edge NK (mean a exactly 0, the control at -30 bp so "beats its
control" never protects: also the no-control figure) with the designer's PX structure at its worst plausible levels
(beta 1.3, a crash-prone benchmark, issuer effects of 1%, sigma_i 1.5-6%, jumps 0.5% an event, 80% down with skewed
events) crossed with the frozen grid: the residual day shock sd_c 0, 1.2% and 2.2% a session (PREREG-EVL-6's rho_day 0,
0.05 and 0.15 in the absolute units its section 4.2 states; on the PX generator's own event variance rho_day 0.15
would be 1.75%, so this reads high); phi_day 0.10, 0.15, 0.20 (sd_c > 0); days t3, crash, crasht3, crashcl, crasht3cl;
events symmetric or left-skewed; drift 0, 10, 20 bp (AR 0.97); (lam, K) = (3, 20), (5, 20), (8, 20), (20, 20),
(40, 40) qualifying names a session, or counts that follow the day at lam 3, 5, 8 (sd_c > 0).

Usage:
  px_final8.py selftest
  px_final8.py run --phase PHASE [--workers 8] [--cells FILE]      -> final/px8f.<phase>.jsonl (one row a cell)
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EVL6F = os.path.abspath(os.path.join(HERE, "..", "..", "evl6", "final"))
PRICE = os.path.abspath(os.path.join(HERE, "..", "price"))
os.environ.setdefault("FINAL_ARR", os.path.join(HERE, "scratch_arrays"))
os.environ.setdefault("V2_ARR", os.path.join(HERE, "scratch_arrays"))
sys.path.insert(0, EVL6F)
sys.path.insert(0, PRICE)

import numpy as np  # noqa: E402

import calib_final as CF  # noqa: E402  (PREREG-EVL-6's frozen calibration code, unchanged)
import px_calib as PX  # noqa: E402  (the PX designer's generator pieces, unchanged)
import search_final as SF  # noqa: E402  (PREREG-EVL-6's frozen rule evaluation, unchanged)

T = PX.T                      # 120 sessions a replicate
NPOOL = PX.NPOOL
NSEC = len(PX.SECTOR_W)
PIECES = ((30, 0.020), (40, 0.006), (60, 0.001))
FROZEN = SF.Rule(22, PIECES)
assert FROZEN.key() == '[22, [[30, 0.02], [40, 0.006], [60, 0.001]]]'      # chosen_v2.json's rule, exactly
STARTS = (22, 25, 30, 35, 40)
RULES = {f: SF.Rule(f, PIECES) for f in STARTS}
CAP_LEARN = 4                 # F4: a PX version's run is judged in learning, CAP = event.max_open_v8.learning = 4
CRASH_P, CRASH_K, CL_GAMMA, CL_MAX = 0.05, 3.0, 2.0, 0.09
VOL_SD = 0.3


# ------------------------------------------------------------------------------------------------ day shapes
def crash_p_of(x):
    """calib_v2.crash_p on this generator's volatility state x (stationary sd 0.3, as calib_v2's vol_sd)."""
    return np.minimum(CRASH_P * np.exp(CL_GAMMA * x) / math.exp(CL_GAMMA ** 2 * VOL_SD ** 2 / 2.0), CL_MAX)


def day_units(rng, shape, size, x=None):
    """Unit-variance, mean-0 day innovations: 't3' and 'crash' exactly as px_calib (same draws), and calib_v2's three
    new shapes (crash days at -3 sd: a t(3) body, clustered on the volatility state x, or both)."""
    if shape == "t3":
        return PX.t3_unit(rng, size)
    if shape == "crash":
        return PX.crash_unit(rng, size)
    k = CRASH_K
    p = crash_p_of(x) if shape.endswith("cl") else CRASH_P
    m = p * k / (1.0 - p)
    s = np.sqrt((1.0 - p * (k * k + 1.0)) / (1.0 - p) - m * m)
    hit = rng.random(size) < p
    crash = rng.normal(-k, 1.0, size)
    body = PX.t3_unit(rng, size) if "t3" in shape[5:] else rng.standard_normal(size)
    return np.where(hit, crash, m + s * body)


def ar_from(e, rho, sd):
    R_, T_ = e.shape
    z = np.zeros((R_, T_))
    z[:, 0] = e[:, 0]
    k = math.sqrt(1 - rho * rho)
    for t in range(1, T_):
        z[:, t] = rho * z[:, t - 1] + k * e[:, t]
    return sd * z


_NORM: dict = {}


def joint_draws(shape, M=2_000_000, seed=424242):
    """(h, eps) from the stationary law: x ~ N(0, 0.3^2), h = exp(x - .09) (px_calib's), eps | x by the shape."""
    rr = np.random.default_rng(seed)
    x = VOL_SD * rr.standard_normal(M)
    eps = day_units(rr, shape, M, x)
    return np.exp(x - 0.09), eps


def count_norm(shape, cnt):
    key = ("n", shape, cnt)
    if key not in _NORM:
        _, eps = joint_draws(shape)
        _NORM[key] = float(np.exp(cnt * np.minimum(np.abs(eps), 4.0)).mean())
    return _NORM[key]


def money_knife(c):
    """mu such that the money-weighted (min(n_t, cap)) mean of a is exactly 0 when counts follow the day: only h_t c_t
    co-moves with n_t (every other term has mean 0 given the counts); c_t = sd_c (phi z_(t-1) + sqrt(1-phi^2) eps_t) and
    z_(t-1) has mean 0 given the volatility path, so mu = -sd_c sqrt(1-phi^2) E[w h eps] / E[w]."""
    key = ("k", c["day"], c["cnt"], c["lam"], c["K"], c["knife"])
    if key not in _NORM:
        h, eps = joint_draws(c["day"], 4_000_000, 434343)
        rr = np.random.default_rng(454545)
        mult = np.exp(c["cnt"] * np.minimum(np.abs(eps), 4.0)) if c["cnt"] > 0 else np.ones_like(eps)
        mult = mult / mult.mean()
        lam_t = c["lam"] * rr.gamma(3.0, 1.0 / 3.0, eps.size) * h / h.mean() * mult
        n = np.minimum(rr.poisson(lam_t), c["K"])
        w = np.minimum(n, c["knife"]).astype(float)
        _NORM[key] = float((w * h * eps).sum() / w.sum())
    return -c["sd_c"] * math.sqrt(1 - c["phi"] ** 2) * _NORM[key]


# ------------------------------------------------------------------------------------------------ the generator
def generate(rng, R, c, L_given=None, Tn=None):
    """px_calib.generate with the additions in the module docstring. With day in (t3, crash), cnt 0, no knife, no top
    edge and no given drift, it draws exactly px_calib.generate's arrays (`selftest`)."""
    K_ = c["K"]
    T = PX.T if Tn is None else Tn          # (px_demotion8.py's longer stays; the default draws px_calib's 120)
    P = PX.pool(rng, c["tau"], c["sig"])
    x = PX.ar(rng, R, T, 0.9, 0.3, lambda g, s: g.normal(0, 1, s))
    h = np.exp(x - 0.09)
    if c["day"] in ("t3", "crash"):
        eps = day_units(rng, c["day"], (R, T))
    else:
        eps = day_units(rng, c["day"], (R, T), x)
    cday = ar_from(eps, c["phi"], c["sd_c"])
    if c["drift"] > 0:
        L = PX.ar(rng, R, T, 0.97, c["drift"], lambda g, s: g.normal(0, 1, s))
    else:
        L = np.zeros((R, T))
    if L_given is not None:
        L = L_given
    mu_m, sd_m = 0.0004, 0.008
    if c["crash_m"]:
        mshape = "crash" if c["day"] in ("t3", "crash") else c["day"]
        mu_unit = day_units(rng, mshape, (R, T), x)
    else:
        mu_unit = PX.t3_unit(rng, (R, T))
    m = mu_m + sd_m * mu_unit
    s = 0.008 * PX.t3_unit(rng, (R, T, NSEC))
    G = rng.gamma(3.0, 1.0 / 3.0, (R, T))
    lam_t = c["lam"] * G * h / h.mean()
    if c["cnt"] > 0:
        lam_t = lam_t * np.exp(c["cnt"] * np.minimum(np.abs(eps), 4.0)) / count_norm(c["day"], c["cnt"])
    n0 = np.minimum(rng.poisson(lam_t), K_)
    hot = rng.random((R, T)) < 0.5
    hot_k = rng.choice(NSEC, size=(R, T), p=P["sec_share"])
    base = P["sec_share"]
    u = rng.random((R, T, K_))
    sec = np.empty((R, T, K_), dtype=np.int64)
    cum0 = np.cumsum(base)
    sec[:] = np.minimum(np.searchsorted(cum0, u), NSEC - 1)
    for k in range(NSEC):
        sel = hot & (hot_k == k)
        if not sel.any():
            continue
        p = base.copy()
        p[k] *= 4.0
        p /= p.sum()
        sec[sel] = np.minimum(np.searchsorted(np.cumsum(p), u[sel]), NSEC - 1)
    iss = np.empty((R, T, K_), dtype=np.int64)
    u2 = rng.random((R, T, K_))
    for k in range(NSEC):
        sel = sec == k
        pos = np.minimum(np.searchsorted(P["cdfs"][k], u2[sel]), len(P["members"][k]) - 1)
        iss[sel] = P["members"][k][pos]
    slot = np.arange(K_)[None, None, :]
    valid = slot < n0[:, :, None]
    flat = np.where(valid, iss, -1).reshape(R * T, K_)
    order = np.argsort(flat, axis=1, kind="stable")
    srt = np.take_along_axis(flat, order, axis=1)
    dup_sorted = np.zeros_like(srt, dtype=bool)
    dup_sorted[:, 1:] = (srt[:, 1:] == srt[:, :-1]) & (srt[:, 1:] >= 0)
    dup = np.zeros_like(dup_sorted)
    np.put_along_axis(dup, order, dup_sorted, axis=1)
    valid = valid & ~dup.reshape(R, T, K_)
    ev = PX.skew_unit if c["ev"] == "skew" else PX.t3_unit
    e = ev(rng, (R, T, K_))
    sig = P["sigma"][iss]
    bdev = (c["beta"] - 1.0) + P["beta_dev"][iss]
    s_ev = np.take_along_axis(s, sec, axis=2)
    jump = np.zeros((R, T, K_))
    if c["pj"] > 0:
        jh = rng.random((R, T, K_)) < c["pj"]
        down = rng.random((R, T, K_)) < c["dshare"]
        jump = np.where(jh, np.where(down, -0.30, 0.30), 0.0)
        jump -= c["pj"] * 0.30 * (1 - 2 * c["dshare"])
    tau_ev = P["tau"][iss]
    if c["tau"] > 0:
        tau_ev = tau_ev - tau_ev[valid].mean()
    mu = c["mu"]
    if c["knife"]:
        mu = mu + money_knife(c)
    a = (mu + L[:, :, None] + bdev * (m - mu_m)[:, :, None]
         + h[:, :, None] * (cday[:, :, None] + s_ev + sig * e) + jump + tau_ev)
    if c["top_n"]:
        rank = np.cumsum(valid, axis=2)                     # 1-based rank among the session's events (slot order)
        a = a + np.where(rank <= c["top_n"], c["mu_top"] - c["mu"], 0.0)
    a = np.maximum(a, -1.0)
    r = a + m[:, :, None]
    zc = rng.normal(0, 1, (R, T))
    C = c["mu_c"] + 0.5 * L + 0.05 * (m - mu_m) + h * (0.5 * cday + 0.003 * zc)
    return dict(a=a, r=r, iss=iss, valid=valid, C=C, L=L)


# ------------------------------------------------------------------------------------------------ the record
class Rec:
    def __init__(self, R, start):
        self.start = start
        self.X = np.zeros((R, CF.S_RUN + 1)); self.W = np.zeros((R, CF.S_RUN + 1)); self.S = np.zeros(R, np.int64)
        self.ca = np.zeros(R); self.cr = np.zeros(R); self.ne = np.zeros(R, np.int64)
        self.ta = np.zeros(R); self.tr = np.zeros(R)
        self.isum = np.zeros((R, NPOOL)); self.icnt = np.zeros((R, NPOOL), np.int64); self.niss = np.zeros(R, np.int64)
        self.cbm = np.zeros(R); self.ccm = np.zeros(R)
        self.Sat = np.zeros((R, T), np.int16); self.has = np.zeros((R, T), bool); self.mn = np.zeros((R, T), bool)
        self.g = np.zeros((R, T), bool); self.iss = np.zeros((R, T), bool); self.neg = np.zeros((R, T), bool)
        self.P = np.full((R, T), np.nan, np.float32); self.Q = np.full((R, T), np.nan, np.float32)

    def arrays(self, sfx):
        return {f"Sat{sfx}": self.Sat, f"has{sfx}": self.has, f"mn{sfx}": self.mn, f"g{sfx}": self.g,
                f"iss{sfx}": self.iss, f"neg{sfx}": self.neg, f"P{sfx}": self.P, f"Q{sfx}": self.Q}


def records(gd, cap, control=True, seed=0):
    """calib_final.simulate's per-session record (copied: the same arrays, prefilters and shortcuts) on a PX path,
    with the money weights min(n_s, cap) and the top-cap guard. Run 1 from block 1, run 2 from block 61."""
    a, r, iss, valid, C = gd["a"], gd["r"], gd["iss"], gd["valid"], gd["C"]
    R = a.shape[0]
    rows = np.arange(R)
    gflips = np.where(np.random.default_rng(seed + 77_777).random((CF.B_ISS_G, NPOOL)) < 0.5, -1.0, 1.0)
    recs = [Rec(R, 0), Rec(R, CF.S_RUN)]
    Sglob = np.zeros(R, np.int64)
    mw_num = mw_den = ew_num = ew_den = 0.0
    for ti in range(T):
        v = valid[:, ti, :]
        at = np.where(v, a[:, ti, :], 0.0)
        rt = np.where(v, r[:, ti, :], 0.0)
        nP = v.sum(axis=1)
        has = nP > 0
        sP = at.sum(axis=1)
        sR = rt.sum(axis=1)
        top = v & (np.cumsum(v, axis=1) <= cap)
        tA = np.where(top, at, 0.0).sum(axis=1)
        tR = np.where(top, rt, 0.0).sum(axis=1)
        Bt = np.where(has, sP / np.maximum(nP, 1), 0.0)
        Ct = C[:, ti]
        wt = np.minimum(nP, cap)
        mw_num += float((wt * Bt).sum()); mw_den += float(wt.sum())
        ew_num += float(sP.sum()); ew_den += float(nP.sum())
        er, ek = np.nonzero(v)
        ei = iss[:, ti, :][er, ek]
        ea = a[:, ti, :][er, ek]
        for rec in recs:
            act = has & (Sglob >= rec.start)
            hr = np.nonzero(act)[0]
            if hr.size:
                ok = rec.S[hr] < CF.S_RUN + 1
                hr2 = hr[ok]
                rec.X[hr2, rec.S[hr2]] = Bt[hr2]
                rec.W[hr2, rec.S[hr2]] = nP[hr2]
            rec.S[hr] += 1
            am = act.astype(float)
            rec.ca += sP * am; rec.cr += sR * am; rec.ne += nP * act
            rec.ta += tA * am; rec.tr += tR * am
            pm = act[er]
            if pm.any():
                flat = er[pm] * NPOOL + ei[pm]
                isum = rec.isum.reshape(-1)
                icnt = rec.icnt.reshape(-1)
                new = icnt[flat] == 0          # (one event per issuer a session: flat is unique within it)
                np.add.at(isum, flat, ea[pm])
                np.add.at(icnt, flat, 1)
                if new.any():
                    rec.niss += np.bincount(er[pm][new], minlength=R)
            rec.cbm += np.where(act, Bt, 0.0)
            rec.ccm += np.where(act, Ct, 0.0)
            S = rec.S
            rec.Sat[:, ti] = np.minimum(S, 32767)
            rec.has[:, ti] = act
            mn = (rec.ne >= CF.MIN_EV) & (rec.niss >= CF.MIN_ISS) & (S >= CF.MIN_BLK)
            rec.mn[:, ti] = mn
            ctrl = (rec.cbm > rec.ccm) if control else np.ones(R, bool)
            gdd = (rec.ca > 0) & (rec.cr > 0) & (rec.ta > 0) & (rec.tr > 0) & ctrl
            rec.g[:, ti] = gdd
            rec.neg[:, ti] = rec.ca < 0
            look = act & mn & (S <= CF.S_RUN)
            cand = np.nonzero(look & gdd)[0]
            if cand.size:
                rec.P[cand, ti] = 1.0
                for Sv in np.unique(S[cand]):
                    rs = cand[S[cand] == Sv]
                    Y = np.minimum(rec.W[rs, :Sv], cap) * (rec.X[rs, :Sv] - CF.MARGIN)
                    zz = Y.sum(axis=1) / np.sqrt(np.maximum((Y * Y).sum(axis=1), 1e-300))
                    keep = zz >= CF.Z_PRE
                    if keep.any():
                        rec.P[rs[keep], ti] = CF.signflip_p_rows(Y[keep], int(Sv))
            cand = np.nonzero(look & (rec.ca < 0))[0]
            if cand.size:
                rec.Q[cand, ti] = 1.0
                for Sv in np.unique(S[cand]):
                    rs = cand[S[cand] == Sv]
                    Y = -np.minimum(rec.W[rs, :Sv], cap) * rec.X[rs, :Sv]
                    zz = Y.sum(axis=1) / np.sqrt(np.maximum((Y * Y).sum(axis=1), 1e-300))
                    keep = zz >= CF.Z_PRE
                    if keep.any():
                        rec.Q[rs[keep], ti] = CF.signflip_p_rows(Y[keep], int(Sv))
            need = np.nonzero(look & gdd & (rec.P[:, ti] <= CF.ALPHA_MAX + CF.TIE))[0]
            for rr_ in need:
                cnt = rec.icnt[rr_]
                nz = cnt > 0
                rec.iss[rr_, ti] = CF.issuer_p(rec.isum[rr_][nz] / cnt[nz], gflips) <= CF.ISS_G
        Sglob += has
    out = recs[0].arrays("")
    out.update(recs[1].arrays("_2"))
    info = {"mw_mean_a_bp": 1e4 * mw_num / max(mw_den, 1e-300), "ew_mean_a_bp": 1e4 * ew_num / max(ew_den, 1e-300),
            "events_per_session": ew_den / (R * T)}
    return out, info


# ------------------------------------------------------------------------------------------------ cells
PXW = dict(beta=1.3, tau=0.010, sig=(0.015, 0.060), pj=0.005, mu=0.0, mu_c=-0.0030, knife=0, top_n=0, mu_top=0.0)
SDC = {0: 0.0, 5: 0.012, 15: 0.022}          # PREREG-EVL-6's sd_c at rho_day 0, 0.05, 0.15 (section 4.2)
COUNTS = ((3, 20), (5, 20), (8, 20), (20, 20), (40, 40))
FOLLOW = (3, 5, 8)
DAYS = ("t3", "crash", "crasht3", "crashcl", "crasht3cl")


def cell(**kw):
    c = dict(PXW)
    c.update(dict(sd_c=0.0, phi=0.10, day="t3", drift=0.0, crash_m=False, ev="t3", dshare=0.5, lam=40, K=40, cnt=0.0))
    c.update(kw)
    if "crash_m" not in kw:
        c["crash_m"] = c["day"] != "t3"
    if "dshare" not in kw:
        c["dshare"] = 0.8 if c["ev"] == "skew" else 0.5
    if c["cnt"] > 0 and not c.get("knife"):
        c["knife"] = CAP_LEARN
    return c


def label(c):
    rho = {0.0: 0, 0.012: 5, 0.022: 15}.get(round(c["sd_c"], 4), None)
    sdc = f"rho{rho:02d}" if rho is not None else f"sdc{c['sd_c'] * 100:.1f}"
    cnt = f"cnt{c['lam']}" if c["cnt"] > 0 else f"lam{c['lam']}K{c['K']}"
    extra = ""
    if c["mu"]:
        extra += f"|mu{c['mu'] * 1e4:.0f}"
    if c["top_n"]:
        extra += f"|top{c['top_n']}@{c['mu_top'] * 1e4:.0f}"
    if c["mu_c"] != -0.0030:
        extra += f"|ctrl{c['mu_c'] * 1e4:.0f}"
    if c["tau"] != 0.010:
        extra += f"|tau{c['tau'] * 100:.1f}"
    if c["beta"] != 1.3:
        extra += f"|beta{c['beta']}"
    if c.get("designer"):
        extra += f"|PX-{c['designer']}"
    return f"{sdc}|phi{c['phi']:.2f}|{c['day']}|{c['ev']}|d{c['drift'] * 1e4:.0f}|{cnt}{extra}"


def plausible_grid():
    out = []
    for rho, sd in SDC.items():
        phis = (0.10,) if sd == 0 else (0.10, 0.15, 0.20)
        for phi, day, ev, drift in itertools.product(phis, DAYS, ("t3", "skew"), (0.0, 0.0010, 0.0020)):
            for lam, K in COUNTS:
                out.append(cell(sd_c=sd, phi=phi, day=day, ev=ev, drift=drift, lam=lam, K=K))
            if sd > 0:
                for lam in FOLLOW:
                    out.append(cell(sd_c=sd, phi=phi, day=day, ev=ev, drift=drift, lam=lam, K=20, cnt=0.3))
    return out


def stress_grid():
    """Named stresses (reported, not binding): the PX designer's own worst and stress cells (phi_day 0.25), phi_day
    0.25 on the grid's worst shapes, rho_day 0.30 (sd_c 3.4%), a 30 bp drift, betas of 1.5, issuer effects of 0."""
    out = []
    for nz in ("worst", "stress", "mid", "base", "quiet"):
        d = PX.NOISE[nz]
        for lam, K in ((8, 20), (20, 20), (40, 40)):
            out.append(dict(cell(sd_c=d["sd_c"], phi=d["phi"], day=d["day"], drift=d["drift"], ev=d["ev"],
                                 lam=lam, K=K, crash_m=d["crash_m"], dshare=d["dshare"]),
                            beta=d["beta"], tau=d["tau"], sig=d["sig"], pj=d["pj"], designer=nz))
    for day in ("crasht3cl", "crashcl", "crasht3"):
        for ev in ("t3", "skew"):
            for lam, K in ((3, 20), (8, 20), (40, 40)):
                out.append(cell(sd_c=0.022, phi=0.25, day=day, ev=ev, drift=0.0020, lam=lam, K=K))
            out.append(cell(sd_c=0.022, phi=0.25, day=day, ev=ev, drift=0.0020, lam=3, K=20, cnt=0.3))
    for day in ("crash", "crasht3cl"):
        for lam, K in ((3, 20), (8, 20), (40, 40)):
            out.append(cell(sd_c=0.034, phi=0.10, day=day, ev="skew", drift=0.0020, lam=lam, K=K))
            out.append(cell(sd_c=0.022, phi=0.20, day=day, ev="skew", drift=0.0030, lam=lam, K=K))
            out.append(cell(sd_c=0.022, phi=0.20, day=day, ev="skew", drift=0.0020, lam=lam, K=K, beta=1.5))
            out.append(cell(sd_c=0.012, phi=0.20, day=day, ev="skew", drift=0.0030, lam=lam, K=K))
    return out


def power_grid():
    out = []
    base = PX.NOISE["base"]
    for mu in (0.0020, 0.0030, 0.0040, 0.0060, 0.0080, 0.0100):
        for lam, K in ((8, 20), (20, 20), (40, 40)):
            out.append(dict(cell(sd_c=base["sd_c"], phi=0.10, day="t3", ev="t3", lam=lam, K=K, mu=mu, mu_c=0.0,
                                 crash_m=False), beta=1.0, tau=0.0, designer="base"))
            out.append(cell(sd_c=0.012, phi=0.10, day="t3", ev="t3", lam=lam, K=K, mu=mu, mu_c=0.0, beta=1.0,
                            tau=0.0, crash_m=False))
            out.append(cell(sd_c=0.022, phi=0.20, day="crasht3cl", ev="skew", drift=0.0020, lam=lam, K=K, mu=mu,
                            mu_c=0.0))
    return out


def money_grid():
    """Check 1's money-population attack under F4's guard: the edge sits below the cap (the top-ranked events earn
    mu_top, the rest mu). Not nulls of PREREG-EVL-6's estimand (its all-event money-weighted mean is positive):
    measured departures, reported."""
    out = []
    for nz in ("base", "grid"):
        for top_n, mu_top, mu in ((4, 0.0, 0.0060), (4, -0.0015, 0.0080), (14, 0.0, 0.0060), (14, -0.0015, 0.0080),
                                  (4, 0.0, 0.0040), (14, 0.0, 0.0040)):
            if nz == "base":
                b = PX.NOISE["base"]
                c = dict(cell(sd_c=b["sd_c"], phi=0.10, day="t3", ev="t3", lam=40, K=40, mu=mu, crash_m=False),
                         beta=1.0, tau=0.0, top_n=top_n, mu_top=mu_top, designer="base")
            else:
                c = cell(sd_c=0.022, phi=0.20, day="crasht3cl", ev="skew", drift=0.0020, lam=40, K=40, mu=mu,
                         top_n=top_n, mu_top=mu_top)
            out.append(c)
    return out


def base_grid():
    out = []
    b = PX.NOISE["base"]
    for lam, K in COUNTS:
        out.append(dict(cell(sd_c=b["sd_c"], phi=0.10, day="t3", ev="t3", lam=lam, K=K, crash_m=False, mu_c=-0.0030),
                        beta=1.0, tau=0.0, designer="base"))
        out.append(dict(cell(sd_c=b["sd_c"], phi=0.10, day="t3", ev="t3", lam=lam, K=K, crash_m=False, mu_c=0.0),
                        beta=1.0, tau=0.0, designer="base"))
    return out


def shared_grid():
    """Check 1's SHARED attack: PX-DROP-ON and PX-SURGE-ON as two seats sharing only the ON universe's family drift L_t
    (AR 0.97): P(both pass) against the product of the two rates."""
    out = []
    for day, ev in (("crasht3cl", "skew"), ("crash", "skew"), ("crasht3cl", "t3")):
        for lam, K in ((40, 40), (20, 20)):
            out.append(dict(cell(sd_c=0.022, phi=0.20, day=day, ev=ev, drift=0.0020, lam=lam, K=K), shared=True))
    out.append(dict(cell(sd_c=0.022, phi=0.20, day="crasht3cl", ev="skew", drift=0.0030, lam=40, K=40), shared=True))
    return out


def sens_grid():
    """Sensitivities at the grid's corner: no issuer effects (tau 0), the seat's real control (N0: the seat's mean 0
    and its control at 0, so the control condition can bind), and beta 1.0 (no loser beta)."""
    out = []
    for day in ("crasht3cl", "crashcl"):
        for lam, K in ((40, 40), (20, 20), (3, 20)):
            base = dict(sd_c=0.022, phi=0.20, day=day, ev="skew", drift=0.0020, lam=lam, K=K)
            out.append(cell(**base, tau=0.0))
            out.append(cell(**base, mu_c=0.0))
            out.append(cell(**base, beta=1.0))
    return out


SEEDS = {"search": 171_000_000, "fresh": 172_000_000, "confirm": 173_000_000, "stress": 174_000_000,
         "power": 175_000_000, "money": 176_000_000, "base": 176_500_000, "shared": 176_800_000,
         "sens": 177_500_000}
REPS = {"search": 1000, "fresh": 4000, "confirm": 4000, "stress": 2000, "power": 2000, "money": 2000, "base": 4000,
        "shared": 4000, "sens": 4000}


def cells_of(phase, cells_file=None):
    if cells_file:
        return [json.loads(l) for l in open(cells_file)]
    return {"search": plausible_grid, "stress": stress_grid, "power": power_grid, "money": money_grid,
            "base": base_grid, "shared": shared_grid, "sens": sens_grid}[phase]()


def summarize_rule(d, rule, H=120):
    fp, fr, fe = SF.first_pass(d, "", rule)
    _, any2 = SF.two_runs(d, rule)
    out = {"fp120": float(np.mean(fp <= H)), "two_runs120": float(np.mean(any2 <= H)),
           "ret": float(np.mean(fr <= H)), "end": float(np.mean(fe <= H))}
    for h in (22, 25, 30, 40, 60):
        out[f"by{h}"] = float(np.mean(fp <= h))
    out["E60"] = float(np.mean(np.minimum(fp, 60)))
    return out, fp


def job(args):
    phase, c, R, seed = args
    t0 = time.time()
    rng = np.random.default_rng(seed)
    if c.get("shared"):
        # two seats sharing only the family drift L_t (check 1's SHARED): seat B reuses seat A's drift path
        gA = generate(rng, R, c)
        gB = generate(rng, R, c, L_given=gA["L"])
        dA, infoA = records(gA, CAP_LEARN, seed=seed)
        dB, _ = records(gB, CAP_LEARN, seed=seed + 1)
        res = {}
        for f, rule in RULES.items():
            fa, _, _ = SF.first_pass(dA, "", rule)
            fb, _, _ = SF.first_pass(dB, "", rule)
            pa, pb = fa <= T, fb <= T
            res[f] = {"A": int(pa.sum()), "B": int(pb.sum()), "both": int((pa & pb).sum())}
        return phase, c, R, seed, res, infoA, time.time() - t0
    g = generate(rng, R, c)
    d, info = records(g, CAP_LEARN, control=not c.get("nocontrol"), seed=seed)
    res = {}
    for f, rule in RULES.items():
        s, _ = summarize_rule(d, rule)
        res[f] = {k: v * R if k != "E60" else v * R for k, v in s.items()}       # sums, to pool over chunks
    return phase, c, R, seed, res, info, time.time() - t0


def run(phase, workers, cells_file=None, chunk=500, reps=None):
    from multiprocessing import get_context
    cl = cells_of(phase, cells_file)
    R_total = reps or REPS[phase]
    jobs = []
    seed = SEEDS[phase]
    for c in cl:
        for k in range(0, R_total, chunk):
            seed += 1
            jobs.append((phase, c, min(chunk, R_total - k), seed))
    jobs.sort(key=lambda j: -j[1]["lam"])
    out_path = os.path.join(HERE, f"px8f.{phase}.jsonl")
    idx_path = os.path.join(HERE, f"px8f.{phase}.index.jsonl")
    agg: dict = {}
    t0 = time.time()
    with get_context("fork").Pool(min(workers, 8)) as pool, open(idx_path, "w") as fi:
        for k, (ph, c, R, sd, res, info, secs) in enumerate(pool.imap_unordered(job, jobs), 1):
            lab = label(c) + ("|SHARED" if c.get("shared") else "") + ("|nocontrol" if c.get("nocontrol") else "")
            fi.write(json.dumps({"phase": ph, "cell": lab, "R": R, "seed": sd, "secs": round(secs, 1), "info": info}) + "\n")
            fi.flush()
            a = agg.setdefault(lab, {"cell": lab, "spec": c, "R": 0, "res": {}, "info": [], "seeds": []})
            a["R"] += R
            a["seeds"].append(sd)
            a["info"].append(info)
            for f, rr in res.items():
                tgt = a["res"].setdefault(str(f), {})
                for kk, vv in rr.items():
                    tgt[kk] = tgt.get(kk, 0) + vv
            if k % 50 == 0 or k == len(jobs):
                print(f"{phase}: {k}/{len(jobs)} jobs, {time.time() - t0:.0f}s", flush=True)
    with open(out_path, "w") as fo:
        for lab, a in sorted(agg.items()):
            R = a["R"]
            row = {"cell": lab, "R": R, "spec": a["spec"], "seeds": [min(a["seeds"]), max(a["seeds"])],
                   "mw_mean_a_bp": float(np.mean([i["mw_mean_a_bp"] for i in a["info"]])),
                   "ew_mean_a_bp": float(np.mean([i["ew_mean_a_bp"] for i in a["info"]])),
                   "events_per_session": float(np.mean([i["events_per_session"] for i in a["info"]]))}
            for f, rr in a["res"].items():
                if "both" in rr:
                    row[f"F{f}"] = {k: v / R for k, v in rr.items()}
                else:
                    row[f"F{f}"] = {k: v / R for k, v in rr.items()}
            fo.write(json.dumps(row) + "\n")
    print("wrote", out_path)


def selftest():
    """(1) With no addition on, `generate` draws exactly px_calib.generate's arrays. (2) The day shapes have mean 0 and
    variance 1. (3) The money knife: the realized money-weighted mean a of a day-following null is about 0. (4) The
    record reproduces calib_final's sign-flip shortcut on a passing toy record."""
    for nz in ("base", "worst"):
        d = PX.NOISE[nz]
        c = dict(cell(sd_c=d["sd_c"], phi=d["phi"], day=d["day"], drift=d["drift"], ev=d["ev"], lam=20, K=20,
                      crash_m=d["crash_m"], dshare=d["dshare"], mu_c=0.0), beta=d["beta"], tau=d["tau"], sig=d["sig"],
                 pj=d["pj"])
        g1 = generate(np.random.default_rng(5), 50, c)
        g0 = PX.generate(np.random.default_rng(5), 50, 20, d, 0.0, 0.0, 20)
        for k in ("a", "r", "iss", "valid", "C"):
            assert np.array_equal(g1[k], g0[k]), (nz, k)
    for sh in DAYS:
        _, e = joint_draws(sh, 2_000_000, 99)
        print(f"day {sh}: mean {e.mean():+.4f} var {e.var():.4f} skew {((e - e.mean()) ** 3).mean() / e.std() ** 3:+.2f}")
    c = cell(sd_c=0.022, phi=0.20, day="crasht3cl", ev="skew", drift=0.0, lam=3, K=20, cnt=0.3, mu_c=0.0)
    g = generate(np.random.default_rng(7), 400, c)
    d_, info = records(g, CAP_LEARN, seed=7)
    print(f"money knife (crasht3cl, cnt 0.3, lam 3): mu {money_knife(c) * 1e4:+.2f} bp; realized money-weighted mean a "
          f"{info['mw_mean_a_bp']:+.2f} bp, event-weighted {info['ew_mean_a_bp']:+.2f} bp, {info['events_per_session']:.2f}"
          " events a session")
    print("selftest ok: generate reproduces px_calib.generate exactly with no addition on")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("selftest", "run"))
    ap.add_argument("--phase", default="search")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cells", default=None)
    ap.add_argument("--reps", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
    else:
        run(a.phase, a.workers, a.cells, reps=a.reps)

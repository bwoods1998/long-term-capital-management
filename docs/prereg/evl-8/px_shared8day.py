#!/usr/bin/env python
"""px_shared8day.py (PREREG-EVL-8's FINAL FIX, SYNTHETIC ONLY): re-check 1's rc_shared.py (evl8/recheck1/), copied
with its paths moved to final/ and its output renamed, run on the final fix's own seeds (from 183,000,001). PX-DROP-ON
and PX-SURGE-ON as two seats trading the SAME night against the SAME benchmark, sharing not only the family drift L_t
(px_final8's SHARED) but the session's whole day structure: the volatility regime h_t, the residual day shock c_t (its
innovations eps_t), the benchmark's move m_t and the sector shocks s_t; events, issuers and counts independent. A
knife-edge null for both; P(both pass within 120 sessions) against the product. px8f.shared (L_t only) is the lower
bound, this the upper (everything day-level shared).

Usage: px_shared8day.py SEED0 REPS
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["FINAL_ARR"] = os.path.join(HERE, "scratch_arrays")
os.environ["V2_ARR"] = os.path.join(HERE, "scratch_arrays")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
sys.path.insert(0, HERE)

import json  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

import px_final8 as X  # noqa: E402

PX = X.PX
NSEC = X.NSEC


def shared_parts(rng, R, c, T):
    x = PX.ar(rng, R, T, 0.9, 0.3, lambda g, s: g.normal(0, 1, s))
    eps = X.day_units(rng, c["day"], (R, T), x) if c["day"] not in ("t3", "crash") else X.day_units(rng, c["day"], (R, T))
    L = PX.ar(rng, R, T, 0.97, c["drift"], lambda g, s: g.normal(0, 1, s)) if c["drift"] > 0 else np.zeros((R, T))
    mshape = "crash" if c["day"] in ("t3", "crash") else c["day"]
    mu_unit = X.day_units(rng, mshape, (R, T), x) if c["crash_m"] else PX.t3_unit(rng, (R, T))
    s = 0.008 * PX.t3_unit(rng, (R, T, NSEC))
    return dict(x=x, eps=eps, L=L, mu_unit=mu_unit, s=s)


def gen_seat(rng, R, c, sh, T=120):
    """px_final8.generate's lines with the day-level arrays taken from `sh` (events, issuers, counts drawn here)."""
    K_ = c["K"]
    P = PX.pool(rng, c["tau"], c["sig"])
    x = sh["x"]
    h = np.exp(x - 0.09)
    eps = sh["eps"]
    cday = X.ar_from(eps, c["phi"], c["sd_c"])
    L = sh["L"]
    mu_m, sd_m = 0.0004, 0.008
    m = mu_m + sd_m * sh["mu_unit"]
    s = sh["s"]
    G = rng.gamma(3.0, 1.0 / 3.0, (R, T))
    lam_t = c["lam"] * G * h / h.mean()
    n0 = np.minimum(rng.poisson(lam_t), K_)
    hot = rng.random((R, T)) < 0.5
    hot_k = rng.choice(NSEC, size=(R, T), p=P["sec_share"])
    base = P["sec_share"]
    u = rng.random((R, T, K_))
    sec = np.empty((R, T, K_), dtype=np.int64)
    sec[:] = np.minimum(np.searchsorted(np.cumsum(base), u), NSEC - 1)
    for k in range(NSEC):
        sel = hot & (hot_k == k)
        if not sel.any():
            continue
        p = base.copy(); p[k] *= 4.0; p /= p.sum()
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
    a = (c["mu"] + L[:, :, None] + bdev * (m - mu_m)[:, :, None]
         + h[:, :, None] * (cday[:, :, None] + s_ev + sig * e) + jump + tau_ev)
    a = np.maximum(a, -1.0)
    r = a + m[:, :, None]
    zc = rng.normal(0, 1, (R, T))
    C = c["mu_c"] + 0.5 * L + 0.05 * (m - mu_m) + h * (0.5 * cday + 0.003 * zc)
    return dict(a=a, r=r, iss=iss, valid=valid, C=C, L=L)


def job(args):
    c, R, seed = args
    rng = np.random.default_rng(seed)
    sh = shared_parts(rng, R, c, 120)
    gA = gen_seat(rng, R, c, sh)
    gB = gen_seat(rng, R, c, sh)
    dA, _ = X.records(gA, X.CAP_LEARN, seed=seed)
    dB, _ = X.records(gB, X.CAP_LEARN, seed=seed + 1)
    fa, _, _ = X.SF.first_pass(dA, "", X.RULES[22])
    fb, _, _ = X.SF.first_pass(dB, "", X.RULES[22])
    pa, pb = fa <= 120, fb <= 120
    # the correlation of the two seats' session block means (sessions where both hold a block)
    va, vb = gA["valid"], gB["valid"]
    Ba = np.where(va, gA["a"], 0).sum(2) / np.maximum(va.sum(2), 1)
    Bb = np.where(vb, gB["a"], 0).sum(2) / np.maximum(vb.sum(2), 1)
    both = (va.sum(2) > 0) & (vb.sum(2) > 0)
    rho = float(np.corrcoef(Ba[both], Bb[both])[0, 1])
    return X.label(c), R, int(pa.sum()), int(pb.sum()), int((pa & pb).sum()), rho


if __name__ == "__main__":
    from multiprocessing import get_context
    seed0, reps = int(sys.argv[1]), int(sys.argv[2])
    cells = [X.cell(sd_c=0.022, phi=0.20, day="crasht3cl", ev="skew", drift=0.0020, lam=40, K=40),
             X.cell(sd_c=0.022, phi=0.20, day="crasht3cl", ev="skew", drift=0.0020, lam=20, K=20),
             X.cell(sd_c=0.022, phi=0.20, day="crash", ev="skew", drift=0.0020, lam=40, K=40)]
    jobs = []
    seed = seed0
    for c in cells:
        for k in range(0, reps, 500):
            seed += 1
            jobs.append((c, min(500, reps - k), seed))
    agg = {}
    t0 = time.time()
    with get_context("fork").Pool(8) as pool:
        for lab, R, a, b, ab, rho in pool.imap_unordered(job, jobs):
            g = agg.setdefault(lab, [0, 0, 0, 0, []]); g[0] += R; g[1] += a; g[2] += b; g[3] += ab; g[4].append(rho)
    out = []
    for lab, (R, a, b, ab, rhos) in agg.items():
        row = {"cell": lab + "|SHARED-DAY", "R": R, "A": a / R, "B": b / R, "both": ab / R,
               "indep": (a / R) * (b / R), "P(B|A)": ab / max(a, 1), "rho_blocks": float(np.mean(rhos))}
        out.append(row)
        print(json.dumps(row))
    with open(os.path.join(HERE, "px8f.sharedday.jsonl"), "w") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    print(f"{time.time() - t0:.0f}s")

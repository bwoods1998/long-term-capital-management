#!/usr/bin/env python
"""placebo8.py: the PREREG-EVL-8 judge's calibration of THE PLACEBO AUDIT and THE CONTROL CANARY (section 3.3) under
THE PX SCREEN, on the red team's pool model (../redteam/rt_placebo.py, re-implemented with this file's sizes).
SYNTHETIC ONLY.

POOL: a PX control's events a session, N = 200 issuers (one per issuer), each a = delta + D_t + c_t + s_i e_i
(s_i log-uniform 1.5%-6%, e unit t3; D_t AR(0.97) drift of sd `drift`; c_t the day shock 0.5% sd, t3 or CRASH DAYS
(5% of sessions at -3 sd)); r = a + m_t, m_t ~ N(4 bp, 1.2%). delta = 0: an HONEST pool (zero mean after cost);
delta > 0: a DISHONEST pool (a cost basis too low, survivorship or look-ahead lifting every event).
PLACEBO j: each session the 8 pool events with the smallest hash (here: a random 8, independent across j); THE AUDIT
counts placebos passing THE PX SCREEN (no control condition) by their 60th block; it ALARMS at >= k of 8.
CANARY: the pool's own mean block passes the PX screen (no control condition).
Issuers: 200 names per session from a 2,000-name pool with Zipf(0.8) popularity (repeat names), so the 30-issuer
minimum and the issuer-block p are live. Seeds 97,000,001 on. Usage: placebo8.py [reps=2000] [rule=s15]
"""
import json
import math
import multiprocessing as mp
import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evl6d  # noqa: E402

T, N, KP, P, U = 60, 200, 8, 8, 2000
S15 = (15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
RULE = sys.argv[2] if len(sys.argv) > 2 else "s15"
LOOKS = {"s15": S15, "evl6": evl6d.LOOKS}[RULE]
POP = (1.0 / np.arange(1, U + 1) ** 0.8)
POP /= POP.sum()


def t3(rng, size):
    return rng.standard_t(3, size) / math.sqrt(3.0)


def rep(rng, delta, drift_sd, crash):
    D = np.zeros(T)
    if drift_sd:
        D[0] = rng.normal(0, drift_sd)
        for t in range(1, T):
            D[t] = 0.97 * D[t - 1] + math.sqrt(1 - 0.97 ** 2) * rng.normal(0, drift_sd)
    if crash:
        m_, s_ = 0.15 / 0.95, math.sqrt((1 - 0.5) / 0.95 - (0.15 / 0.95) ** 2)
        z = np.where(rng.random(T) < 0.05, rng.normal(-3, 1, T), rng.normal(m_, s_, T))
    else:
        z = t3(rng, T)
    c = 0.005 * z
    m = 0.0004 + 0.012 * rng.standard_normal(T)
    iss = np.array([rng.choice(U, size=N, replace=False, p=POP) for _ in range(T)])
    s = np.exp(rng.uniform(math.log(0.015), math.log(0.06), (T, N)))
    a = delta + D[:, None] + c[:, None] + s * t3(rng, (T, N))
    r = a + m[:, None]
    passes = 0
    for j in range(P):
        idx = np.argsort(rng.random((T, N)), axis=1)[:, :KP]
        aa = np.take_along_axis(a, idx, 1)
        rr = np.take_along_axis(r, idx, 1)
        ii = np.take_along_axis(iss, idx, 1)
        sim = {"B": aa.mean(1)[None], "Rm": rr.mean(1)[None], "n": np.full((1, T), KP), "ctrl": np.zeros((1, T)),
               "iss": ii[None], "a": aa[None]}
        passes += evl6d.screen(sim, 0, 0, False, looks=LOOKS)[0]
    sim = {"B": a.mean(1)[None], "Rm": r.mean(1)[None], "n": np.full((1, T), N), "ctrl": np.zeros((1, T)),
           "iss": iss[None], "a": a[None]}
    canary = evl6d.screen(sim, 0, 0, False, looks=LOOKS)[0]
    return passes, canary


def cell(args):
    delta, drift_sd, crash, reps, seed = args
    rng = np.random.default_rng(seed)
    out = [rep(rng, delta, drift_sd, crash) for _ in range(reps)]
    cnt = np.array([o[0] for o in out])
    can = np.array([o[1] for o in out])
    return {"delta_bp": delta * 1e4, "drift_bp": drift_sd * 1e4, "crash": crash, "reps": reps, "seed": seed,
            "single": float(cnt.mean() / P), **{f"ge{k}": float((cnt >= k).mean()) for k in range(1, 6)},
            "canary": float(can.mean()), "audit_ge3_or_canary": float(((cnt >= 3) | can).mean()),
            "audit_ge4_or_canary": float(((cnt >= 4) | can).mean())}


if __name__ == "__main__":
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    cells = [(0.0, 0.0, False), (0.0, 0.0010, True), (0.0, 0.0020, True), (0.0020, 0.0, False), (0.0030, 0.0, False),
             (0.0050, 0.0, False), (0.0030, 0.0020, True), (0.0050, 0.0020, True)]
    jobs = [(d, s, c, reps, 97_000_001 + i) for i, (d, s, c) in enumerate(cells)]
    with mp.Pool(4) as pool:
        res = pool.map(cell, jobs)
    for r in res:
        print(json.dumps(r), flush=True)
    json.dump({"rule": RULE, "rows": res}, open(os.path.join(HERE, f"placebo8_{RULE}.out.json"), "w"), indent=1)

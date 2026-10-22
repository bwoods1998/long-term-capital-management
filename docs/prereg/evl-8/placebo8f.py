#!/usr/bin/env python
"""placebo8f.py: THE PLACEBO AUDIT and THE CONTROL CANARY (PREREG-EVL-8 section 3.3) under THE FINAL PX SCREEN
(PREREG-EVL-6 sections 1-3 as frozen, looks from the first look F, CAP 4 money weights and the top-4 guard, no control
condition: meta_final8.screen_runs, run 1 only, by the 60th block), on the judge's pool model (../calib/placebo8.py
`rep`, its pool, sizes, cells and seeds' layout unchanged; only the screen is replaced). SYNTHETIC ONLY.

POOL: a PX control's 200 events a session; PLACEBO j: 8 of them a session; the AUDIT alarms when >= 3 of a window's 8
placebos pass by their 60th block, or when the pool itself passes (THE CANARY). Seeds 179,900,001 on.
Usage: placebo8f.py REPS F
"""
import json
import math
import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import meta_final8 as MF  # noqa: E402

T, N, KP, P, U = 60, 200, 8, 8, 2000
POP = (1.0 / np.arange(1, U + 1) ** 0.8)
POP /= POP.sum()
F = int(sys.argv[2]) if len(sys.argv) > 2 else 22
LOOKS = tuple(s for s in MF.LOOKS if s >= F)
CAP = 4


def t3(rng, size):
    return rng.standard_t(3, size) / math.sqrt(3.0)


def rep(rng, delta, drift_sd, crash, gflips):
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
        runs = MF.screen_runs(sim, 0, CAP, gflips, looks=LOOKS, control=False, max_runs=1)
        passes += int(bool(runs) and runs[0][1])
    sim = {"B": a.mean(1)[None], "Rm": r.mean(1)[None], "n": np.full((1, T), N), "ctrl": np.zeros((1, T)),
           "iss": iss[None], "a": a[None]}
    runs = MF.screen_runs(sim, 0, CAP, gflips, looks=LOOKS, control=False, max_runs=1)
    return passes, bool(runs) and runs[0][1]


def cell(args):
    delta, drift_sd, crash, reps, seed = args
    rng = np.random.default_rng(seed)
    gflips = np.where(np.random.default_rng(seed + 77_777).random((MF.CF.B_ISS_G, U)) < 0.5, -1.0, 1.0)
    out = [rep(rng, delta, drift_sd, crash, gflips) for _ in range(reps)]
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
    chunks = 8
    jobs = []
    for i, (d, s_, c) in enumerate(cells):
        for k in range(chunks):
            jobs.append((d, s_, c, reps // chunks, 179_900_001 + 100 * i + k))
    from multiprocessing import get_context
    with get_context("fork").Pool(8) as pool:
        parts = pool.map(cell, jobs)
    res = []
    for i, (d, s_, c) in enumerate(cells):
        ps = parts[i * chunks:(i + 1) * chunks]
        n = sum(p["reps"] for p in ps)
        row = {"delta_bp": d * 1e4, "drift_bp": s_ * 1e4, "crash": c, "reps": n,
               "seeds": [ps[0]["seed"], ps[-1]["seed"]]}
        for k in ("single", "ge1", "ge2", "ge3", "ge4", "ge5", "canary", "audit_ge3_or_canary", "audit_ge4_or_canary"):
            row[k] = sum(p[k] * p["reps"] for p in ps) / n
        res.append(row)
        print(json.dumps(row), flush=True)
    json.dump({"first_look": F, "rows": res}, open(os.path.join(HERE, f"placebo8f_F{F}.out.json"), "w"), indent=1)

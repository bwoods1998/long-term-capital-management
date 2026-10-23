#!/usr/bin/env python
"""evl3_corner.py: PREREG-EVL-3's screen ALONE, exactly as the judge ran it (judge/calib_judge.py `simulate`, its skew
check and its retirement included), at this file's worst plausible cell and its neighbours on the widened grid
(SYNTHETIC ONLY; reads no lane data). Seeds from 117,500,001. Prints P(passed within 120 sessions) per cell.

Usage: evl3_corner.py [workers] > evl3_corner.out
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["CALIB_SHM"] = os.path.join(HERE, "arrays_e3")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))
import numpy as np  # noqa: E402
import calib_judge as CJ  # noqa: E402

N3 = dict(skill=0.0060, mu_family=-0.0060)
BOTH = CJ.SHAPES["both"]
DAYSKEW = CJ.SHAPES["dayskew"]
CELLS = [("N3|both|AR20|phi0.20", dict(nbar=85, rho_day=0.15, phi_day=0.20, **N3, **BOTH, drift_sd=0.0020)),
         ("N3|both|AR20|phi0.20", dict(nbar=30, rho_day=0.15, phi_day=0.20, **N3, **BOTH, drift_sd=0.0020)),
         ("N3|dayskew|AR20|phi0.20", dict(nbar=30, rho_day=0.15, phi_day=0.20, **N3, **DAYSKEW, drift_sd=0.0020))]
R, CHUNK = 2000, 250


def job(args):
    lab, kw, n, seed = args
    CJ.LAGS = (0,)
    CJ.M0S = (0.0,)          # (only the old path is read here: its session-block p is the margin-0 p)
    t0 = time.time()
    out, info = CJ.simulate(CJ.Gen(**kw), n, 120, seed, old_skew=True)
    return lab, kw, seed, out["old"].astype(int).tolist(), time.time() - t0


if __name__ == "__main__":
    from multiprocessing import get_context
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    jobs, seed = [], 117_500_000
    for lab, kw in CELLS:
        for c in range(0, R, CHUNK):
            seed += 1
            jobs.append((lab, kw, CHUNK, seed))
    res = {}
    with get_context("fork").Pool(min(workers, 8)) as pool:
        for lab, kw, seed, old, secs in pool.imap_unordered(job, jobs):
            res.setdefault((lab, kw["nbar"]), []).extend(old)
    for (lab, nb), old in sorted(res.items()):
        old = np.array(old)
        v = float(np.mean((old >= 1) & (old <= 120)))
        print(f"PREREG-EVL-3 alone {lab} n{nb} rho0.15: {v:.4f} (se {math.sqrt(v * (1 - v) / old.size):.4f}, R {old.size})")

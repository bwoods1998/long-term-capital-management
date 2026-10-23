#!/usr/bin/env python
"""rc_px.py (RE-CHECK #1 of PREREG-EVL-8, SYNTHETIC ONLY): the PX seats' false-pass rate under PREREG-EVL-6 AS FROZEN
(first look 22, CAP 4) re-run on THE RE-CHECK'S OWN SEEDS, which no designer, judge, check or fixer used.

It imports the fixer's px_final8.py (the PX generator + the frozen calibration record, read only) and evaluates the
fixer's cells on new seeds: phase A = every plausible cell whose search-seed rate at F22 is >= 0.085 plus the 18 fresh
cells (seeds from 191,000,001, 4,000 programs a cell); phase B = phase A's 12 worst cells on seeds from 192,000,001
(8,000 programs a cell; these seeds chose nothing). Nothing here reads the lane, the House or any market data.

Usage: rc_px.py A | B | cells FILE SEED0 REPS OUT
"""
from __future__ import annotations

import os
import sys

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["FINAL_ARR"] = os.path.join(HERE, "arr")
os.environ["V2_ARR"] = os.path.join(HERE, "arr")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
FINAL = os.path.abspath(os.path.join(HERE, "..", "final"))
sys.path.insert(0, FINAL)

import json  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

import px_final8 as X  # noqa: E402


def job(args):
    c, R, seed = args
    t0 = time.time()
    rng = np.random.default_rng(seed)
    g = X.generate(rng, R, c)
    d, info = X.records(g, X.CAP_LEARN, control=True, seed=seed)
    fp, fr, fe = X.SF.first_pass(d, "", X.RULES[22])
    _, any2 = X.SF.two_runs(d, X.RULES[22])
    return X.label(c), c, R, seed, int((fp <= 120).sum()), int((any2 <= 120).sum()), info, time.time() - t0


def run(cells, seed0, reps, out, chunk=500, workers=8):
    from multiprocessing import get_context
    jobs = []
    seed = seed0
    for c in cells:
        for k in range(0, reps, chunk):
            seed += 1
            jobs.append((c, min(chunk, reps - k), seed))
    jobs.sort(key=lambda j: -j[0]["lam"])
    agg = {}
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool:
        for k, (lab, c, R, sd, n1, n2, info, secs) in enumerate(pool.imap_unordered(job, jobs), 1):
            a = agg.setdefault(lab, {"cell": lab, "spec": c, "R": 0, "pass1": 0, "pass2": 0, "seeds": [], "eps": [],
                                     "mw": []})
            a["R"] += R; a["pass1"] += n1; a["pass2"] += n2; a["seeds"].append(sd)
            a["eps"].append(info["events_per_session"]); a["mw"].append(info["mw_mean_a_bp"])
            if k % 50 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    rows = []
    for lab, a in agg.items():
        p = a["pass1"] / a["R"]
        rows.append({"cell": lab, "R": a["R"], "fp120": p, "se": math.sqrt(p * (1 - p) / a["R"]),
                     "two_runs120": a["pass2"] / a["R"], "seeds": [min(a["seeds"]), max(a["seeds"])],
                     "events_per_session": float(np.mean(a["eps"])), "mw_mean_a_bp": float(np.mean(a["mw"])),
                     "spec": a["spec"]})
    rows.sort(key=lambda r: -r["fp120"])
    with open(out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for r in rows[:25]:
        print(f"{r['cell']:<48} R {r['R']:>5}  per run {r['fp120']:.4f} +- {r['se']:.4f}  two runs {r['two_runs120']:.4f}"
              f"  ev/s {r['events_per_session']:.1f}  mw {r['mw_mean_a_bp']:+.2f} bp")
    return rows


def cells_A():
    search = [json.loads(l) for l in open(os.path.join(FINAL, "px8f.search.jsonl"))]
    fresh = [json.loads(l) for l in open(os.path.join(FINAL, "px8f.fresh.cells.jsonl"))]
    out, seen = [], set()
    for r in search:
        if r["F22"]["fp120"] >= 0.085:
            lab = X.label(r["spec"])
            assert lab == r["cell"], (lab, r["cell"])
            if lab not in seen:
                seen.add(lab); out.append(r["spec"])
    for c in fresh:
        lab = X.label(c)
        if lab not in seen:
            seen.add(lab); out.append(c)
    return out


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "arr"), exist_ok=True)
    if sys.argv[1] == "A":
        cl = cells_A()
        print(len(cl), "cells")
        run(cl, 191_000_000, 4000, os.path.join(HERE, "rc_px.A.jsonl"))
    elif sys.argv[1] == "B":
        rows = [json.loads(l) for l in open(os.path.join(HERE, "rc_px.A.jsonl"))]
        cl = [r["spec"] for r in rows[:12]]
        run(cl, 192_000_000, 8000, os.path.join(HERE, "rc_px.B.jsonl"))
    elif sys.argv[1] == "cells":
        cl = [json.loads(l) for l in open(sys.argv[2])]
        run(cl, int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])

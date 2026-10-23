#!/usr/bin/env python
"""rc_meta.py (RE-CHECK #1 of PREREG-EVL-8, SYNTHETIC ONLY): THE META-LEARNERS' PER-RUN false-pass rate to the RUN'S
OWN END (its 60th block, PREREG-EVL-6 section 2's horizon), not to a session count.

PREREG-EVL-8 section 6.5 states META's per-run rate "within 120 sessions" (0.038) and per version "within 720
sessions" (0.063). A null meta-learner picks in 2-5% of sessions, so by the 720th session its first run holds about
15-37 blocks (meta8f.null.jsonl `blocks_mean`): the run's looks at 25-60 blocks mostly lie beyond the horizon measured.
PREREG-EVL-6 (D11) reads the rate PER TEST: one run, every look it can make to its 60th block. This script runs the
fixer's simulator (final/calib_meta_f8.py) and screen (final/meta_final8.py `screen_runs`, CAP 8 and 4), imported
read only, to T = 2,500 sessions on the RE-CHECK'S OWN SEEDS (from 195,000,001) and reports P(run 1 passes at any
look to its end), P(any run passes by T), both unconditional and given a null pick record, and the share of run 1s
that have ended (pass, retire or 60th block) by T.

Usage: rc_meta.py [--reps 600] [--T 2500] [--only SUBSTR]
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["FINAL_ARR"] = os.path.join(HERE, "arr")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "final")))
sys.path.insert(0, HERE)

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

import meta_final8 as MF  # noqa: E402
import calib_meta_rc as CM2  # noqa: E402  (the re-check's one-knob copy)

CM, CF = MF.CM, MF.CF
Cell = CM.Cell
WORST, NT = MF.WORST, MF.NT
P20 = dict(phi_day=0.20)


def cells(T):
    return [
        Cell(f"RC-FAC06-N0-worstnotauT3CL-phi20-n300-wide4-T{T}", nbar=300, width="wide4", T=T, load_corr=0.9,
             load_all=True, fac_sd=0.006, fac_rho=0.10, **(NT | P20 | dict(day="crasht3cl"))),
        Cell(f"RC-N0-worst-phi20-n300-wide4-T{T}", nbar=300, width="wide4", T=T, **(WORST | P20)),
        Cell(f"RC-N0-worstT3CL-phi20-n300-T{T}", nbar=300, T=T, **(WORST | P20 | dict(day="crasht3cl"))),
        Cell(f"RC-N0-base-n300-T{T}", nbar=300, T=T),
        Cell(f"RC-S-famdrift20-worstnotauT3CL-n300-T{T}", nbar=300, T=T, fam_drift_sd=0.0020,
             **(NT | dict(phi_day=0.20, day="crasht3cl"))),
    ]


def attack_cells(T):
    """THE BETA-TILT ATTACK (calib_meta_rc.py): issuers' day-shock loadings spread with their volatility (1 + b z), so
    the volatility-tercile sub-rules' pool-relative blocks carry b x c_t (sd_c 2.2%, crash days, phi_day 0.20)."""
    C2 = CM2.Cell
    out = []
    for b in (0.3, 0.5):
        out.append(C2(f"AT-beta{b}-N0-worstnotauT3CL-phi20-n300-wide4-T{T}", nbar=300, width="wide4", T=T, beta_day=b,
                      **(NT | P20 | dict(day="crasht3cl"))))
        out.append(C2(f"AT-beta{b}-N0-worstT3CL-phi20-n300-T{T}", nbar=300, T=T, beta_day=b,
                      **(WORST | P20 | dict(day="crasht3cl"))))
    return out


def job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = (CM2 if cell.name.startswith("AT-") else CM).simulate(cell, seed, R)
    with np.errstate(invalid="ignore"):
        tm = np.nanmean(sim["true"].reshape(R, -1), axis=1)
    tm = np.where(np.isnan(tm), 0.0, tm)
    U = int(sim["iss"].max()) + 2 if sim["iss"].size else 3000
    gflips = np.where(np.random.default_rng(seed + 77_777).random((CF.B_ISS_G, max(U, 3000))) < 0.5, -1.0, 1.0)
    out = {"tm": tm.tolist(), "runs": {}}
    for cap in (8, 4):
        out["runs"][cap] = [MF.screen_runs(sim, i, cap, gflips) for i in range(R)]
    n = sim["n"].astype(np.int64)
    out["blocks"] = (n > 0).sum(axis=1).tolist()
    # the session at which run 1 holds its 22nd block (its first possible look)
    cb = np.cumsum(n > 0, axis=1)
    out["s22"] = [int(np.argmax(cb[i] >= 22)) + 1 if cb[i, -1] >= 22 else -1 for i in range(R)]
    out["s60"] = [int(np.argmax(cb[i] >= 60)) + 1 if cb[i, -1] >= 60 else -1 for i in range(R)]
    return cell.name, out, time.time() - t0


def summarise(cell, parts):
    tm = np.concatenate([np.array(p["tm"]) for p in parts])
    null = tm <= 0
    R = tm.size
    res = {"cell": cell.name, "R": int(R), "T": cell.T, "null_share": float(null.mean()),
           "blocks_mean": float(np.mean(np.concatenate([p["blocks"] for p in parts]))),
           "s22_median": float(np.median([s for p in parts for s in p["s22"] if s > 0] or [-1])),
           "s60_median": float(np.median([s for p in parts for s in p["s60"] if s > 0] or [-1])),
           "share_reaching_60_blocks": float(np.mean([s > 0 for p in parts for s in p["s60"]]))}
    for cap in (8, 4):
        runs = [r for p in parts for r in p["runs"][cap]]
        r1_pass = np.array([bool(rr) and rr[0][1] for rr in runs])
        r1_pass_s = np.array([rr[0][2] if (rr and rr[0][1]) else -1 for rr in runs])
        r1_ended = np.array([bool(rr) and (rr[0][1] or rr[0][3] or rr[0][4] >= 0) for rr in runs])
        any_pass = np.array([any(x[1] for x in rr) for rr in runs])
        d = {"run1_pass_by_T": float(r1_pass.mean()),
             "run1_pass_by_T_given_null": float((r1_pass & null).sum() / max(null.sum(), 1)),
             "run1_pass_given_run1_ended": float(r1_pass[r1_ended].mean()) if r1_ended.any() else None,
             "run1_ended_share": float(r1_ended.mean()),
             "any_run_pass_by_T": float(any_pass.mean()),
             "any_run_pass_by_T_given_null": float((any_pass & null).sum() / max(null.sum(), 1))}
        for h in (120, 720, 1200, 1800, 2500):
            if h <= cell.T:
                d[f"run1_by{h}"] = float(((r1_pass_s >= 0) & (r1_pass_s < h)).mean())
                d[f"run1_by{h}_given_null"] = float((((r1_pass_s >= 0) & (r1_pass_s < h)) & null).sum()
                                                    / max(null.sum(), 1))
        se = math.sqrt(max(d["run1_pass_by_T"] * (1 - d["run1_pass_by_T"]), 1e-12) / R)
        d["se_run1_pass_by_T"] = se
        res[f"cap{cap}"] = d
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=600)
    ap.add_argument("--T", type=int, default=2500)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--only", default="")
    ap.add_argument("--seed0", type=int, default=195_000_001)
    ap.add_argument("--out", default=os.path.join(HERE, "rc_meta.jsonl"))
    ap.add_argument("--attack", action="store_true")
    a = ap.parse_args()
    cl = [c for c in (attack_cells(a.T) if a.attack else cells(a.T)) if a.only in c.name]
    jobs = []
    for ci, cell in enumerate(cl):
        for j in range(max(1, a.reps // a.chunk)):
            jobs.append((cell, a.seed0 + 1000 * ci + j, a.chunk))
    jobs.sort(key=lambda j: -(3 if j[0].width == "wide4" else 1))
    need = {c.name: max(1, a.reps // a.chunk) for c in cl}
    byname = {c.name: c for c in cl}
    parts: dict = {}
    t0 = time.time()
    from multiprocessing import get_context
    with get_context("fork").Pool(8) as pool, open(a.out, "a") as fh:
        for k, (name, part, dt_) in enumerate(pool.imap_unordered(job, jobs)):
            parts.setdefault(name, []).append(part)
            print(f"job {k + 1}/{len(jobs)} {name} {dt_:.0f}s [{time.time() - t0:.0f}s]", flush=True)
            if len(parts[name]) == need[name]:
                s = summarise(byname[name], parts.pop(name))
                fh.write(json.dumps(s) + "\n"); fh.flush()
                print(json.dumps(s), flush=True)


if __name__ == "__main__":
    main()

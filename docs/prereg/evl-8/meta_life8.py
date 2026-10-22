#!/usr/bin/env python
"""meta_life8.py: PREREG-EVL-8's FINAL-FIX calibration of THE META-LEARNERS' false passes PER RUN TO THE RUN'S OWN END
(re-check 1's major 2). SYNTHETIC ONLY: nothing here reads the lane, the House, the gateway or any run record.

WHY. meta_final8.py measured the meta-learners' false passes "run 1 within 120 sessions" and "every run within 720".
A null meta-learner picks in a few percent of sessions, so its run reaches its 22nd block only after hundreds of
sessions: those horizons cut most of run 1's looks off. PREREG-EVL-6 (its D11) reads a charge PER TEST, one run with
every look it can make to its 60th block. And the META generator loaded every pool event exactly 1 on the residual day
shock, so pool-relative scoring cancelled it by construction; real pools mix high- and low-beta names.

WHAT. The same learner and screen as meta_final8.py, imported unchanged (`screen_runs`: PREREG-EVL-6 sections 1.2-2 as
frozen, in runs, CAP 8 and CAP 4), on calib_meta_b8.py (calib_meta_f8.py with one knob, beta_day: an issuer's loading on
the day shock is clip(1 + beta_day x its volatility z-score, 0.2, 2.5); beta_day = 0 draws exactly as before,
`selftest`). Every cell runs to T = 2,500 sessions (the worst plausible and the worst stress cells to T = 4,000); the
screen reads every look each run can make inside T. A replicate is NULL when its picks' true mean is <= 0. Reported:
run 1 passing by 120 / 720 / 2,500 (/ 4,000) sessions; the share of run 1s ENDED by T (passed, retired or 60th block);
run 1's pass share among the ended; every run by 720 and by T; each unconditional and given a null record.

GRID (fresh seeds from 182,000,001; none used before by any PX or META calibration of PREREG-EVL-6, -7 or -8 or by
either re-check): beta_day 0.3 is PLAUSIBLE at the corner (the PX designer's beta_dev sd), 0.5 a STRESS (re-check 1's).

Usage: meta_life8.py selftest | run [--phase main|ext] [--workers 8] [--only SUBSTR]
(phase main -> meta8l.life.jsonl; phase ext -> meta8l.ext.jsonl: the plausible cells still open at 2,500, to T 4,000)
"""
from __future__ import annotations

import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

import meta_final8 as MF  # noqa: E402  (the screen, imported unchanged)
import calib_meta_b8 as CB  # noqa: E402  (the simulator with the beta_day knob)

CF, CM = MF.CF, MF.CM
Cell = CB.Cell
WORST = CB.WORST
NT = WORST | dict(tau_i=0.0)
P20 = dict(phi_day=0.20)
CAPS = (8, 4)
SEED0 = 182_000_001


def grid():
    """(cell, reps). Names: L = plausible, S = stress, B<b> = beta_day."""
    T, TL, TX = 2500, 4000, 4000
    fac = dict(load_corr=0.9, load_all=True, fac_sd=0.006, fac_rho=0.10)
    out = [
        # PLAUSIBLE: beta_day 0.3 at the corner
        (Cell(f"L-B03-N0-worstnotauT3CL-phi20-n300-wide4-T{TL}", nbar=300, width="wide4", T=TL, beta_day=0.3,
              **(NT | P20 | dict(day="crasht3cl"))), 800),
        (Cell(f"L-B03-N0-worstT3CL-phi20-n300-T{T}", nbar=300, T=T, beta_day=0.3,
              **(WORST | P20 | dict(day="crasht3cl"))), 600),
        (Cell(f"L-B03-FAC06-N0-worstnotauT3CL-phi20-n300-wide4-T{T}", nbar=300, width="wide4", T=T, beta_day=0.3,
              **(NT | P20 | dict(day="crasht3cl") | fac)), 600),
        (Cell(f"L-B03-N0-worst-phi20-n300-wide4-T{T}", nbar=300, width="wide4", T=T, beta_day=0.3,
              **(WORST | P20)), 400),
        (Cell(f"L-B03-N0-base-n300-T{T}", nbar=300, T=T, beta_day=0.3), 400),
        # PLAUSIBLE: the grid as before (beta_day 0), now to the run's end
        (Cell(f"L-B0-FAC06-N0-worstnotauT3CL-phi20-n300-wide4-T{T}", nbar=300, width="wide4", T=T,
              **(NT | P20 | dict(day="crasht3cl") | fac)), 400),
        (Cell(f"L-B0-N0-base-n300-T{T}", nbar=300, T=T), 400),
        # STRESS
        (Cell(f"S-B05-N0-worstnotauT3CL-phi20-n300-wide4-T{TL}", nbar=300, width="wide4", T=TL, beta_day=0.5,
              **(NT | P20 | dict(day="crasht3cl"))), 600),
        (Cell(f"S-B05-N0-worstT3CL-phi20-n300-T{T}", nbar=300, T=T, beta_day=0.5,
              **(WORST | P20 | dict(day="crasht3cl"))), 600),
        (Cell(f"S-B0-famdrift20-worstnotauT3CL-n300-T{T}", nbar=300, T=T, fam_drift_sd=0.0020,
              **(NT | P20 | dict(day="crasht3cl"))), 400),
        # THE EXTENSION (phase "ext", run after the cells above with --phase ext): the plausible cells whose run 1 was
        # still open in more than 5% of programs at T 2,500, run again to T 4,000 on their own seeds (this list's index
        # sets them: 182,000,001 + 1,000 x its position here), so their figure is the run's end, not a horizon
        (Cell(f"L-B03-FAC06-N0-worstnotauT3CL-phi20-n300-wide4-T{TX}", nbar=300, width="wide4", T=TX, beta_day=0.3,
              **(NT | P20 | dict(day="crasht3cl") | fac)), 600),
        (Cell(f"L-B03-N0-worstT3CL-phi20-n300-T{TX}", nbar=300, T=TX, beta_day=0.3,
              **(WORST | P20 | dict(day="crasht3cl"))), 600),
        (Cell(f"L-B03-N0-worst-phi20-n300-wide4-T{TX}", nbar=300, width="wide4", T=TX, beta_day=0.3,
              **(WORST | P20)), 400),
    ]
    return out


N_MAIN = 10        # the main phase's cells (the first ten above); the rest are the extension


def job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = CB.simulate(cell, seed, R)
    with np.errstate(invalid="ignore"):
        tm = np.nanmean(sim["true"].reshape(R, -1), axis=1) if np.isfinite(sim["true"]).any() else np.zeros(R)
    tm = np.where(np.isnan(tm), 0.0, tm)
    U = int(sim["iss"].max()) + 2 if sim["iss"].size else 3000
    gflips = np.where(np.random.default_rng(seed + 77_777).random((CF.B_ISS_G, max(U, 3000))) < 0.5, -1.0, 1.0)
    out = {"tm": tm.tolist(), "runs": {}}
    for cap in CAPS:
        out["runs"][cap] = [MF.screen_runs(sim, i, cap, gflips) for i in range(R)]
    n = sim["n"].astype(np.int64)
    cb = np.cumsum(n > 0, axis=1)
    out["s22"] = [int(np.argmax(cb[i] >= 22)) + 1 if cb[i, -1] >= 22 else -1 for i in range(R)]
    out["npk"] = int(n.sum())
    out["with"] = float((n > 0).mean())
    return cell.name, out, time.time() - t0


def summarise(cell, parts):
    tm = np.concatenate([np.array(p["tm"]) for p in parts])
    null = tm <= 0
    R = int(tm.size)
    s22 = [s for p in parts for s in p["s22"]]
    res = {"cell": cell.name, "R": R, "T": cell.T, "beta_day": cell.beta_day, "null_share": float(null.mean()),
           "s22_median": float(np.median([s for s in s22 if s > 0])) if any(s > 0 for s in s22) else None,
           "share_reaching_22_blocks": float(np.mean([s > 0 for s in s22])),
           "picks_per_session": float(sum(p["npk"] for p in parts) / (R * cell.T)),
           "sessions_with_picks": float(np.mean([p["with"] for p in parts])),
           "spec": dataclasses.asdict(cell)}

    def share(mask, given_null=False):
        return float((mask & null).sum() / max(null.sum(), 1)) if given_null else float(mask.mean())

    for cap in CAPS:
        runs = [r for p in parts for r in p["runs"][cap]]
        r1p = np.array([rr[0][2] if (rr and rr[0][1]) else -1 for rr in runs])       # run 1's pass session, -1 none
        r1end = np.array([bool(rr) and (rr[0][1] or rr[0][3] or rr[0][4] >= 0) for rr in runs])
        firstp = np.array([next((x[2] for x in rr if x[1]), -1) if rr else -1 for rr in runs])
        d = {"run1_ended_share": float(r1end.mean()), "runs_started_mean": float(np.mean([len(rr) for rr in runs]))}
        for h in (120, 720, 2500, 4000):
            if h > cell.T:
                continue
            m1 = (r1p >= 0) & (r1p < h)
            ma = (firstp >= 0) & (firstp < h)
            d[f"run1_by{h}"] = share(m1)
            d[f"run1_by{h}_given_null"] = share(m1, True)
            d[f"any_run_by{h}"] = share(ma)
            d[f"any_run_by{h}_given_null"] = share(ma, True)
        m = r1p >= 0
        d["run1_by_T"] = share(m)
        d["run1_by_T_se"] = math.sqrt(max(d["run1_by_T"] * (1 - d["run1_by_T"]), 1e-12) / R)
        d["run1_pass_among_ended"] = float(m[r1end].mean()) if r1end.any() else None
        # an upper bound to the run's end: every run 1 still open at T counted as a pass
        d["run1_to_end_upper"] = float((m | ~r1end).mean())
        res[f"cap{cap}"] = d
    return res


def selftest():
    """beta_day = 0 draws exactly as calib_meta_f8.py (the same arrays, bit for bit), on two small cells."""
    for cell in (CM.Cell("st-a", nbar=300, T=60, **(WORST | P20 | dict(day="crasht3cl"))),
                 CM.Cell("st-b", nbar=300, width="wide4", T=40, **(NT | P20))):
        a = CM.simulate(cell, 182_999_001, 3)
        b = CB.simulate(CB.Cell(**dataclasses.asdict(cell)), 182_999_001, 3)
        for k in a:
            x, y = np.asarray(a[k]), np.asarray(b[k])
            assert x.shape == y.shape and np.array_equal(x, y, equal_nan=True), k
    print("selftest ok: beta_day 0 draws exactly as calib_meta_f8.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "selftest"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--only", default="")
    ap.add_argument("--phase", choices=("main", "ext"), default="main")
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
        return
    full = grid()
    idx = range(N_MAIN) if a.phase == "main" else range(N_MAIN, len(full))
    cl = [(ci, full[ci][0], full[ci][1]) for ci in idx if a.only in full[ci][0].name]
    jobs = []
    for ci, cell, reps in cl:
        for j in range(max(1, reps // a.chunk)):
            jobs.append((cell, SEED0 + 1000 * ci + j, a.chunk))
    cl = [(cell, reps) for _, cell, reps in cl]
    jobs.sort(key=lambda j: -(j[0].T * (2.3 if j[0].width == "wide4" else 1)))
    need = {c.name: max(1, r // a.chunk) for c, r in cl}
    byname = {c.name: c for c, _ in cl}
    parts: dict = {}
    t0 = time.time()
    tag = "life" if a.phase == "main" else "ext"
    out = os.path.join(HERE, f"meta8l.{tag}.jsonl")
    idx = os.path.join(HERE, f"meta8l.{tag}.index.jsonl")
    with open(idx, "w") as fh:
        for cell, seed, R in jobs:
            fh.write(json.dumps({"cell": cell.name, "seed": seed, "R": R}) + "\n")
    from multiprocessing import get_context
    with get_context("fork").Pool(min(8, a.workers)) as pool, open(out, "w") as fh:
        for k, (name, part, dt_) in enumerate(pool.imap_unordered(job, jobs)):
            parts.setdefault(name, []).append(part)
            print(f"job {k + 1}/{len(jobs)} {name} {dt_:.0f}s [{time.time() - t0:.0f}s]", flush=True)
            if len(parts[name]) == need[name]:
                s = summarise(byname[name], parts.pop(name))
                fh.write(json.dumps(s) + "\n")
                fh.flush()
                print(json.dumps({k_: s[k_] for k_ in ("cell", "R", "null_share", "s22_median", "cap8", "cap4")}),
                      flush=True)


if __name__ == "__main__":
    main()

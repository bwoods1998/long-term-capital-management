#!/usr/bin/env python
"""meta_final8.py: PREREG-EVL-8's FINAL calibration of THE META-LEARNERS (EVL-META-O1, EVL-META-ON) under PREREG-EVL-6
sections 1-3 AS FROZEN, word for word (the captain's F1), with the money weights and top-CAP guard at CAP = the band's
open cap (F4: learning 8 for the meta-learners by PREREG-EVL-3's learning band, which PREREG-EVL-6 section 6 leaves
unchanged; CAP 4 measured beside, the draft's file-wide learning room). SYNTHETIC ONLY: nothing here reads the lane.

THE SIMULATOR is the META designer's MRL-EB learner and generator (../meta/calib_meta.py `simulate`, as check 1 copied
it with its style knobs, ../check1/calib_meta_c1.py), copied as calib_meta_f8.py with PREREG-EVL-6's frozen-grid day
shapes added (crash days with a t(3) body, clustered in high-volatility regimes, both); its picks (K 16, H 60, TAU 30
bp, SF 20 bp, Z 3, MINB 3, WARM 10, settlement lag 2) are the record; its control is the pool's mean a of the session.

THE SCREEN (`screen_runs`), PREREG-EVL-6 sections 1.2-2 on the picks' blocks, in runs: values y_s = min(n_s, CAP) x
(B_s - 0.0010); looks at the first block-adding close at which S >= S_k (22, 25, 30, 35, 40, 50, 60) and the minimums
(30 TRADABLE events, 30 issuers, 6 blocks) hold, every threshold reached consumed by that look; alpha 0.020 (S <= 30),
0.006 (31-40), 0.001 (41-60); RETIRE first (mean a < 0 and q <= alpha + 1e-12, q on -min(n_s, CAP) B_s); PASS when
p <= alpha (no tolerance), mean a > 0, mean r > 0, the top-CAP picks of every block (rank order) pooled mean a > 0 and
mean r > 0, the mean block beats the control's over the same sessions, and p_I <= 0.10 (999 vectors); the run ENDS at
its 60th block and RUN n + 1 starts with the next block on a fresh record (the budget taken as holding every run).
Sign-flip p by calib_final.signflip_p_rows (S >= 17 over its 19,999 fixed vectors; every look is at S >= 22), the
issuer p by calib_final.issuer_p; a p only where z >= 1.0 (the frozen calibration's prefilter).
A replicate is NULL when its picks' TRUE mean (their expectation given the world) is <= 0; FP = P(pass | null) and
P(pass) (whatever the truth) are both reported, by 120 sessions and, for the lifetime, by 240 / 480 / 720.

Usage: meta_final8.py run --grid {null,stress,power} [--workers 8] [--reps R]
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EVL6F = os.path.abspath(os.path.join(HERE, "..", "..", "evl6", "final"))
os.environ.setdefault("FINAL_ARR", os.path.join(HERE, "scratch_arrays"))
sys.path.insert(0, HERE)
sys.path.insert(0, EVL6F)

import numpy as np  # noqa: E402

import calib_final as CF  # noqa: E402  (PREREG-EVL-6's frozen sign-flip and issuer p)
import calib_meta_f8 as CM  # noqa: E402

LOOKS = (22, 25, 30, 35, 40, 50, 60)
S_RUN = 60
MARGIN = 0.0010
TIE = 1e-12


def alpha(S):
    return 0.020 if S <= 30 else (0.006 if S <= 40 else 0.001)


def _p(y):
    return float(CF.signflip_p_rows(np.asarray(y, float)[None, :], len(y))[0])


def _z(y):
    q = math.sqrt(float(np.dot(y, y)))
    return 0.0 if q == 0 else float(np.sum(y)) / q


def screen_runs(sim, rep, cap, gflips, T_end=None, looks=LOOKS, control=True, max_runs=None):
    """Every run of one replicate: [(first block's session, passed, pass session, retired, end session)], 0-based."""
    B, Rm, n, ctrl = sim["B"][rep], sim["Rm"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av = sim["iss"][rep], sim["a"][rep]
    T_ = len(B) if T_end is None else T_end
    runs = []
    t = 0
    while t < T_:
        blocks, nb, sess, ev_iss, ev_a = [], [], [], [], []
        sr = st = 0.0
        topa = topr = 0.0
        k = 0
        res = None
        t0 = None
        while t < T_:
            kk = int(n[t])
            if kk == 0:
                t += 1
                continue
            if t0 is None:
                t0 = t
            b = float(B[t]); rmean = float(Rm[t])
            blocks.append(b); nb.append(kk); sess.append(t)
            ev_iss.extend(int(x) for x in iss[t, :kk]); ev_a.extend(float(x) for x in av[t, :kk])
            sr += rmean * kk
            ktop = min(kk, cap)
            ta = float(np.sum(av[t, :ktop]))
            topa += ta
            topr += ta + ktop * (rmean - b)            # r = a + b_t, b_t common to the session's picks
            S = len(blocks)
            N = len(ev_a)
            if k < len(looks) and S >= looks[k] and N >= 30 and len(set(ev_iss)) >= 30 and S >= 6:
                while k < len(looks) and S >= looks[k]:
                    k += 1
                al = alpha(S)
                w = np.minimum(np.array(nb, float), cap)
                xb = np.array(blocks)
                mean_a = math.fsum(ev_a) / N
                yq = -w * xb
                if mean_a < 0 and _z(yq) >= 1.0 and _p(yq) <= al + TIE:
                    res = (t0, False, -1, True, t)
                    t += 1
                    break
                y = w * (xb - MARGIN)
                if (_z(y) >= 1.0 and mean_a > 0 and sr / N > 0 and topa > 0 and topr > 0
                        and (not control or xb.mean() > float(np.mean(ctrl[sess]))) and _p(y) <= al):
                    ids, inv = np.unique(np.array(ev_iss), return_inverse=True)
                    vals = np.bincount(inv, weights=np.array(ev_a)) / np.bincount(inv)
                    if CF.issuer_p(vals, gflips) <= CF.ISS_G:
                        res = (t0, True, t, False, t)
                        t += 1
                        break
            t += 1
            if S >= S_RUN:
                res = (t0, False, -1, False, t - 1)          # the run ENDS (never a retirement)
                break
        if res is None:
            if t0 is not None:
                runs.append((t0, False, -1, False, -1))
            break
        runs.append(res)
        if res[1] or res[3] or (max_runs is not None and len(runs) >= max_runs):
            break                                        # passed (moves to Probe) or retired
    return runs


Cell = CM.Cell
WORST = CM.WORST
NT = WORST | dict(tau_i=0.0)


def grid(name):
    c = []
    if name == "null":
        P20 = dict(phi_day=0.20)
        c += [Cell("M-N0-worst-phi10-n300-T720", nbar=300, T=720, **WORST),
              Cell("M-N0-worst-phi20-n300-T720", nbar=300, T=720, **(WORST | P20)),
              Cell("M-N0-worstT3CL-phi20-n300-T720", nbar=300, T=720, **(WORST | P20 | dict(day="crasht3cl"))),
              Cell("M-N0-worstCL-phi20-n300-T720", nbar=300, T=720, **(WORST | P20 | dict(day="crashcl"))),
              Cell("M-N0-worstT3-phi20-n300-T720", nbar=300, T=720, **(WORST | P20 | dict(day="crasht3"))),
              Cell("M-N0-worstnotauT3CL-phi20-n300-wide4-T720", nbar=300, width="wide4", T=720,
                   **(NT | P20 | dict(day="crasht3cl"))),
              Cell("M-N0-worst-phi20-n300-wide4-T720", nbar=300, width="wide4", T=720, **(WORST | P20)),
              Cell("M-N0-worstT3CL-phi20-n800-T720", nbar=800, T=720, **(WORST | P20 | dict(day="crasht3cl"))),
              Cell("M-N2r3-worstT3CL-phi20-n300-T720", mean="N2", rules="r3", nbar=300, T=720,
                   **(WORST | P20 | dict(day="crasht3cl"))),
              Cell("M-N1-worstT3CL-phi20-n300-T720", mean="N1", nbar=300, T=720, **(WORST | P20 | dict(day="crasht3cl"))),
              Cell("M-FAC06-N0-worstnotauT3CL-phi20-n300-wide4-T720", nbar=300, width="wide4", T=720, load_corr=0.9,
                   load_all=True, fac_sd=0.006, fac_rho=0.10, **(NT | P20 | dict(day="crasht3cl"))),
              Cell("M-RAND-N0-worstT3CL-phi20-n300-T720", nbar=300, algo="rand", T=720,
                   **(WORST | P20 | dict(day="crasht3cl"))),
              Cell("M-N0-base-n300-T720", nbar=300, T=720)]
    elif name == "stress":
        c += [Cell("MS-FAC12-N0-worstnotauT3CL-phi20-n300-wide4-T720", nbar=300, width="wide4", T=720, load_corr=0.9,
                   load_all=True, fac_sd=0.012, fac_rho=0.10, **(NT | dict(phi_day=0.20, day="crasht3cl"))),
              Cell("MS-N0-worstT3CL-phi25-n300-wide4-T720", nbar=300, width="wide4", T=720,
                   **(WORST | dict(phi_day=0.25, day="crasht3cl"))),
              Cell("MS-N0-rho30-worstnotau-n300-T720", nbar=300, T=720, **(NT | dict(rho_day=0.30))),
              Cell("MS-N0-famdrift20-worstnotauT3CL-n300-T720", nbar=300, T=720, fam_drift_sd=0.0020,
                   **(NT | dict(phi_day=0.20, day="crasht3cl")))]
    elif name == "power":
        for e in (40, 60, 100):
            c.append(Cell(f"MP-r1-e{e}-base-n300", mean="A", rules="r1", edge=e * 1e-4, nbar=300, T=240))
            c.append(Cell(f"MP-r3-e{e}-base-n300", mean="A", rules="r3", edge=e * 1e-4, nbar=300, T=240))
            c.append(Cell(f"MP-r1-e{e}-worstT3CL-phi20-n300", mean="A", rules="r1", edge=e * 1e-4, nbar=300, T=240,
                          **(WORST | dict(phi_day=0.20, day="crasht3cl"))))
        for e in (40, 60):
            c.append(Cell(f"MP-r1-e{e}-base-n800", mean="A", rules="r1", edge=e * 1e-4, nbar=800, T=240))
            c.append(Cell(f"MP-truthK16-r1-e{e}-base-n300", mean="A", rules="r1", edge=e * 1e-4, nbar=300, T=240,
                          algo="truth"))
    return c


CAPS = (8, 4)
HS = (120, 240, 480, 720)


def job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = CM.simulate(cell, seed, R)
    with np.errstate(invalid="ignore"):
        tm = np.nanmean(sim["true"].reshape(R, -1), axis=1) if np.isfinite(sim["true"]).any() else np.zeros(R)
    tm = np.where(np.isnan(tm), 0.0, tm)
    U = int(sim["iss"].max()) + 2 if sim["iss"].size else 3000
    gflips = np.where(np.random.default_rng(seed + 77_777).random((CF.B_ISS_G, max(U, 3000))) < 0.5, -1.0, 1.0)
    out = {"tm": tm.tolist(), "runs": {}}
    for cap in CAPS:
        out["runs"][cap] = [screen_runs(sim, i, cap, gflips) for i in range(R)]
    n = sim["n"].astype(np.int64)
    out["npk"] = int(n.sum())
    out["with"] = (n > 0).mean(axis=1).tolist()
    out["blocks"] = (n > 0).sum(axis=1).tolist()
    out["sum_true"] = float(np.nansum(sim["true"]))
    return cell.name, out, time.time() - t0


def summarise(cell, parts):
    tm = np.concatenate([np.array(p["tm"]) for p in parts])
    null = tm <= 0
    res = {"cell": cell.name, "R": int(tm.size), "T": cell.T, "null_share": float(null.mean()),
           "spec": dataclasses.asdict(cell)}
    for cap in CAPS:
        runs = [r for p in parts for r in p["runs"][cap]]
        first_pass = np.array([next((x[2] for x in rr if x[1]), -1) if rr else -1 for rr in runs])
        run1_pass = np.array([(rr[0][2] if (rr and rr[0][1]) else -1) for rr in runs])
        nruns = np.array([len(rr) for rr in runs])
        d = {}
        for h in HS:
            if h > cell.T:
                continue
            p1 = (run1_pass >= 0) & (run1_pass < h)
            pa = (first_pass >= 0) & (first_pass < h)
            d[f"run1_by{h}"] = float(p1.mean())
            d[f"run1_by{h}_given_null"] = float((p1 & null).sum() / max(null.sum(), 1))
            d[f"any_run_by{h}"] = float(pa.mean())
            d[f"any_run_by{h}_given_null"] = float((pa & null).sum() / max(null.sum(), 1))
        for h in (40, 60, 80, 120, 240):
            if h <= cell.T:
                d[f"pass_by{h}"] = float(((first_pass >= 0) & (first_pass < h)).mean())
        d["runs_started_mean"] = float(nruns.mean())
        d["median_pass_session"] = float(np.median(first_pass[first_pass >= 0]) + 1) if (first_pass >= 0).any() else None
        res[f"cap{cap}"] = d
    npk = sum(p["npk"] for p in parts)
    res["picks_per_session"] = float(npk / (tm.size * cell.T))
    res["sessions_with_picks"] = float(np.mean(np.concatenate([np.array(p["with"]) for p in parts])))
    res["blocks_mean"] = float(np.mean(np.concatenate([np.array(p["blocks"]) for p in parts])))
    res["true_mean_picks_bp"] = float(sum(p["sum_true"] for p in parts) / npk * 1e4) if npk else None
    return res


SEED0 = {"null": 179_000_001, "stress": 179_500_001, "power": 179_800_001}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--grid", required=True)
    ap.add_argument("--reps", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    reps = a.reps or (1000 if a.grid == "null" else 600)
    cells = [c for c in grid(a.grid) if a.only in c.name]
    jobs = []
    for ci, cell in enumerate(cells):
        for j in range(max(1, reps // a.chunk)):
            jobs.append((cell, SEED0[a.grid] + 1000 * ci + j, a.chunk))
    jobs.sort(key=lambda j: -(j[0].T * (3 if j[0].width == "wide4" else 1)))
    need = {c.name: max(1, reps // a.chunk) for c in cells}
    byname = {c.name: c for c in cells}
    parts: dict = {}
    t0 = time.time()
    out = os.path.join(HERE, f"meta8f.{a.grid}.jsonl")
    from multiprocessing import get_context
    with get_context("fork").Pool(min(8, a.workers)) as pool, open(out, "w") as fh:
        for k, (name, part, dt_) in enumerate(pool.imap_unordered(job, jobs)):
            parts.setdefault(name, []).append(part)
            print(f"job {k + 1}/{len(jobs)} {name} {dt_:.0f}s [{time.time() - t0:.0f}s]", flush=True)
            if len(parts[name]) == need[name]:
                s = summarise(byname[name], parts.pop(name))
                fh.write(json.dumps(s) + "\n")
                fh.flush()
                print(json.dumps({k_: s[k_] for k_ in ("cell", "R", "null_share", "picks_per_session",
                                                         "sessions_with_picks", "blocks_mean", "cap8", "cap4")}),
                      flush=True)


if __name__ == "__main__":
    main()

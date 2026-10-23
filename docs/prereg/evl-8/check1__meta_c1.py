#!/usr/bin/env python
"""meta_c1.py: ADVERSARIAL CHECK #1 of PREREG-EVL-8 (statistics), the META-LEARNERS. SYNTHETIC ONLY: nothing here
reads the lane, the House, the gateway or any run record.

The learner and generator are the META designer's (calib_meta_c1.py = ../meta/calib_meta.py `simulate` copied with
two added knobs, fac_sd and load_all, default off = unchanged); the screen is THE META SCREEN = PREREG-EVL-6's draft as
written (../calib/evl6d.py, looks 6..60, alpha 0.016/0.004), exactly as ../calib/meta8.py runs it.

Attacks:
  LIFE   THE HORIZON. A null meta-learner picks in 5-12% of sessions, so it fills 60 blocks only after ~500-1,200
         sessions; it is never exhausted inside the 120 sessions the file's 0.062 counts. Run to T = 720 sessions and
         read P(pass) by 120 / 240 / 480 / 720 and the share still running.
  PHI    day-shock persistence (PREREG-EVL-6's own checks: phi_day 0.20 joins the plausible grid, 0.25 a stress, at
         crash days + left skew + 20 bp drift + rho_day 0.15). The meta's calibration held phi_day at 0.10.
  FAC    noise sub-rules carrying style-factor co-movement above SF = 20 bp (vol / liquidity / price terciles load on
         three style factors at corr 0.9; factor session sd 0.6% (designer) and 1.2%).
  RAND   the reference: a fixed program of 16 random pool events under THE META SCREEN at phi 0.25.
Seeds 62,000,001 on (1,000 a cell, one per chunk of 100). Usage: meta_c1.py run [--reps 600] [--workers 2] [--only s]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import multiprocessing as mp
import os
import sys
import time

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "calib")))
import calib_meta_c1 as CM  # noqa: E402
import evl6d  # noqa: E402

Cell = CM.Cell
WORST = CM.WORST
NT = WORST | dict(tau_i=0.0)
HORIZONS = (120, 240, 480, 720)


def grid():
    c = [
        Cell("LIFE-N0-worstnotau-n300-wide4-T720", nbar=300, width="wide4", T=720, **NT),
        Cell("LIFE-N0-worst-n300-T720", nbar=300, T=720, **WORST),
        Cell("PHI20-N0-worstnotau-n300-wide4-T720", nbar=300, width="wide4", T=720, **(NT | dict(phi_day=0.20))),
        Cell("PHI25-N0-worstnotau-n300-wide4-T720", nbar=300, width="wide4", T=720, **(NT | dict(phi_day=0.25))),
        Cell("FAC12-N0-worstnotau-n300-wide4-T720", nbar=300, width="wide4", T=720, load_corr=0.9, load_all=True,
             fac_sd=0.012, fac_rho=0.10, **NT),
        Cell("FAC06-N0-worstnotau-n300-T720", nbar=300, T=720, load_corr=0.9, load_all=True, fac_sd=0.006,
             fac_rho=0.10, **NT),
        Cell("RAND-N0-worstnotau-n300-phi25-T120", nbar=300, algo="rand", T=120, **(NT | dict(phi_day=0.25))),
        Cell("RAND-N0-worstnotau-n300-phi10-T120", nbar=300, algo="rand", T=120, **NT),
    ]
    return c


def job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = CM.simulate(cell, seed, R)
    with np.errstate(invalid="ignore"):
        tm = np.nanmean(sim["true"].reshape(R, -1), axis=1)
    tm = np.where(np.isnan(tm), 0.0, tm)
    e6 = [evl6d.screen(sim, i, 0, True) for i in range(R)]
    ch = [evl6d.chain(sim, i, 3, True) for i in range(R)]
    nb = (sim["n"] > 0).sum(axis=1)
    out = {"tm": tm.tolist(), "e6": [[int(x[0]), int(x[1]), int(x[2]), int(x[3])] for x in e6],
           "ch": [[int(x[0]), int(x[1]), int(x[2])] for x in ch], "blocks": nb.tolist(),
           "npk": int(sim["n"].sum()), "with": float((sim["n"] > 0).mean()), "sum_true": float(np.nansum(sim["true"]))}
    return cell.name, out, time.time() - t0


def summarise(cell, parts):
    tm = np.concatenate([np.array(p["tm"]) for p in parts])
    null = tm <= 0
    R = tm.size
    e6 = np.concatenate([np.array(p["e6"]) for p in parts])
    ch = np.concatenate([np.array(p["ch"]) for p in parts])
    blocks = np.concatenate([np.array(p["blocks"]) for p in parts])
    passed, when, ret, end = e6[:, 0].astype(bool), e6[:, 1], e6[:, 2].astype(bool), e6[:, 3]
    res = {"cell": cell.name, "R": int(R), "T": cell.T, "spec": dataclasses.asdict(cell),
           "null_share": float(null.mean())}
    for h in HORIZONS:
        if h <= cell.T:
            ph = passed & (when >= 0) & (when < h)
            res[f"pass_by{h}"] = float(ph.mean())
            res[f"pass_given_null_by{h}"] = float((ph & null).sum() / max(null.sum(), 1))
            cp = ch[:, 0].astype(bool) & (ch[:, 1] >= 0) & (ch[:, 1] < h)
            res[f"chain3_by{h}"] = float(cp.mean())
    res["se_last"] = float(np.sqrt(res[f"pass_by{max(h for h in HORIZONS if h <= cell.T)}"] *
                                   (1 - res[f"pass_by{max(h for h in HORIZONS if h <= cell.T)}"]) / R))
    res["retired_or_exhausted"] = float(ret.mean())
    res["still_running_at_T"] = float((~passed & ~ret).mean())
    res["blocks_mean"] = float(blocks.mean())
    res["blocks_p50"] = float(np.median(blocks))
    npk = sum(p["npk"] for p in parts)
    res["picks_per_session"] = float(npk / (R * cell.T))
    res["sessions_with_picks"] = float(np.mean([p["with"] for p in parts]))
    res["true_mean_picks_bp"] = float(sum(p["sum_true"] for p in parts) / npk * 1e4) if npk else None
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--reps", type=int, default=600)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "meta_c1"))
    a = ap.parse_args()
    cells = [c for c in grid() if a.only in c.name]
    seed0 = 62_000_001
    jobs = []
    for ci, cell in enumerate(grid()):
        if cell not in cells:
            continue
        reps = a.reps if cell.T > 120 else max(a.reps, 2000)
        for j in range(max(1, reps // a.chunk)):
            jobs.append((cell, seed0 + 1000 * ci + j, a.chunk))
    need = {}
    for cell, _, _ in jobs:
        need[cell.name] = need.get(cell.name, 0) + 1
    byname = {c.name: c for c in cells}
    parts: dict = {}
    t0 = time.time()
    with mp.Pool(min(4, a.workers)) as pool, open(a.out + ".jsonl", "a") as fh:
        for k, (name, part, dt_) in enumerate(pool.imap_unordered(job, jobs)):
            parts.setdefault(name, []).append(part)
            print(f"job {k + 1}/{len(jobs)} {name} {dt_:.0f}s [{time.time() - t0:.0f}s]", flush=True)
            if len(parts[name]) == need[name]:
                s = summarise(byname[name], parts.pop(name))
                fh.write(json.dumps(s) + "\n")
                fh.flush()
                print(json.dumps({k_: v for k_, v in s.items() if k_ != "spec"}), flush=True)


if __name__ == "__main__":
    main()

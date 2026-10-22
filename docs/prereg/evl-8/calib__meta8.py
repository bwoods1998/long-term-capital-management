#!/usr/bin/env python
"""meta8.py: the PREREG-EVL-8 judge's recalibration of the META-LEARNERS (MRL-EB, ../meta/calib_meta.py `simulate`,
imported unchanged: the EVL-6 judge's risk set with event attributes, the EB lower-confidence rule walk with K 16,
H 60, TAU 30 bp, SF 20 bp, Z 3, MINB 3, WARM 10, settlement lag 2) under PREREG-EVL-6 AS DRAFTED (evl6d.py), and
PREREG-EVL-3's screen (calib_learner.screen_one 'EVL3', minus its skew check: an upper bound) beside it.
SYNTHETIC ONLY: nothing here reads the lane.

A replicate is a NULL replicate when its picks' TRUE mean is <= 0 (their expectation given the world; a world with a
persistent family drift or issuer effect gives a selector a REAL forward edge, reported, not counted as false).
FP = P(pass | true mean <= 0); 'pass' = P(pass) whatever the truth. 'chain3' = v1 -> v2 -> v3 successors (each a
fresh record from the session after the previous one retired or exhausted), pass by any.

Seeds 93,000,001 on (1,000 a cell, one per chunk). Usage: meta8.py run --grid {null,stress,power} [--workers 4]
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
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "meta")))
import calib_meta as CM  # noqa: E402
import evl6d  # noqa: E402

CL = CM.CL
Cell = CM.Cell
WORST = CM.WORST
NT = WORST | dict(tau_i=0.0)


def grid(name):
    c = []
    if name == "null":
        c += [Cell("M-N0-base-n300", nbar=300), Cell("M-N0-worst-n300", nbar=300, **WORST),
              Cell("M-N0-worstnotau-n300", nbar=300, **NT), Cell("M-N0-base-n800", nbar=800),
              Cell("M-N0-worst-n800", nbar=800, **WORST), Cell("M-N1-worst-n300", mean="N1", nbar=300, **WORST),
              Cell("M-N2r1-worst-n300", mean="N2", rules="r1", nbar=300, **WORST),
              Cell("M-N2r3-worst-n300", mean="N2", rules="r3", nbar=300, **WORST),
              Cell("M-N0-worstnotau-n300-wide2", nbar=300, width="wide2", **NT),
              Cell("M-N0-worst-n300-wide3", nbar=300, width="wide3", **WORST),
              Cell("M-N0-worst-n300-rand", nbar=300, algo="rand", **WORST)]
    elif name == "stress":
        c += [Cell("MS-N0-rho30-n300", nbar=300, **(NT | dict(rho_day=0.30))),
              Cell("MS-N0-famdrift20-n300", nbar=300, fam_drift_sd=0.0020, **NT),
              Cell("MS-N0-tau3-n300", nbar=300, **(WORST | dict(tau_i=0.03))),
              Cell("MS-N0-mom40-rho30-n300", nbar=300, **(NT | dict(rho_day=0.30, phi_day=0.40))),
              Cell("MS-N0-drift30ar99-n300", nbar=300, **(NT | dict(drift_sd=0.0030, drift_rho=0.99))),
              Cell("MS-N0-worstnotau-n300-z2", nbar=300, z=2.0, **NT),
              Cell("MS-N0-worstnotau-n300-wide4", nbar=300, width="wide4", **NT),
              Cell("MS-N2r3-worstnotau-n800-wide3", mean="N2", rules="r3", nbar=800, width="wide3", **NT)]
    elif name == "tune":
        for w in (20, 30):
            c.append(Cell(f"MT-N0-worst-n300-w{w}", nbar=300, warm=w, **WORST))
            for e in (40, 60):
                c.append(Cell(f"MT-r1-e{e}-base-n300-w{w}", mean="A", rules="r1", edge=e * 1e-4, nbar=300, warm=w))
    elif name == "power":
        for e in (30, 40, 60, 100):
            c.append(Cell(f"MP-r1-e{e}-base-n300", mean="A", rules="r1", edge=e * 1e-4, nbar=300))
        for e in (40, 60):
            c.append(Cell(f"MP-r1-e{e}-base-n800", mean="A", rules="r1", edge=e * 1e-4, nbar=800))
            c.append(Cell(f"MP-r3-e{e}-base-n300", mean="A", rules="r3", edge=e * 1e-4, nbar=300))
            c.append(Cell(f"MP-r3-e{e}-worst-n300", mean="A", rules="r3", edge=e * 1e-4, nbar=300, **WORST))
            c.append(Cell(f"MP-truthK16-r1-e{e}-base-n300", mean="A", rules="r1", edge=e * 1e-4, nbar=300,
                          algo="truth"))
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
    e3 = [CL.screen_one(sim, i, "EVL3") for i in range(R)]
    out = {"tm": tm.tolist(),
           "e6": [[int(x[0]), int(x[1])] for x in e6],
           "ch": [[int(x[0]), int(x[1]), int(x[2])] for x in ch],
           "e3": [[int(x[0]), int(x[1])] for x in e3],
           "n": sim["n"].astype(int).sum(axis=1).tolist(),
           "with": (sim["n"] > 0).mean(axis=1).tolist(),
           "sum_true": float(np.nansum(sim["true"])), "npk": int(sim["n"].sum())}
    return cell.name, out, time.time() - t0


def summarise(cell, parts):
    tm = np.concatenate([np.array(p["tm"]) for p in parts])
    null = tm <= 0
    res = {"cell": cell.name, "R": int(tm.size), "null_share": float(null.mean()), "spec": dataclasses.asdict(cell)}
    for key in ("e6", "e3", "ch"):
        arr = np.concatenate([np.array(p[key]) for p in parts])
        passed = arr[:, 0].astype(bool)
        when = arr[:, 1]
        d = {"pass": float(passed.mean()),
             "pass_given_null": float((passed & null).sum() / max(null.sum(), 1)),
             "pass_and_null": float((passed & null).mean())}
        for h in (20, 40, 60, 120):
            d[f"by{h}"] = float((passed & (when < h) & (when >= 0)).mean())
        d["median_pass_session"] = float(np.median(when[passed]) + 1) if passed.any() else None
        if key == "ch":
            d["versions_mean"] = float(arr[:, 2].mean())
        res[key] = d
    npk = sum(p["npk"] for p in parts)
    res["picks_per_session"] = float(npk / (tm.size * cell.T))
    res["sessions_with_picks"] = float(np.mean(np.concatenate([np.array(p["with"]) for p in parts])))
    res["true_mean_picks_bp"] = float(sum(p["sum_true"] for p in parts) / npk * 1e4) if npk else None
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--grid", required=True)
    ap.add_argument("--reps", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    reps = a.reps or (2000 if a.grid == "null" else 600)
    cells = [c for c in grid(a.grid) if a.only in c.name]
    seed0 = {"null": 93_000_001, "stress": 94_000_001, "power": 95_000_001, "tune": 96_000_001}[a.grid]
    jobs = []
    for ci, cell in enumerate(cells):
        for j in range(max(1, reps // a.chunk)):
            jobs.append((cell, seed0 + 1000 * ci + j, a.chunk))
    need = {c.name: max(1, reps // a.chunk) for c in cells}
    byname = {c.name: c for c in cells}
    parts: dict = {}
    t0 = time.time()
    out = os.path.join(HERE, f"meta8_{a.grid}.jsonl")
    with mp.Pool(min(4, a.workers)) as pool, open(out, "w") as fh:
        for k, (name, part, dt_) in enumerate(pool.imap_unordered(job, jobs)):
            parts.setdefault(name, []).append(part)
            if len(parts[name]) == need[name]:
                s = summarise(byname[name], parts.pop(name))
                fh.write(json.dumps(s) + "\n")
                fh.flush()
                print(f"{name}: e6 {s['e6']['pass']:.3f} (|null {s['e6']['pass_given_null']:.3f}) chain3 "
                      f"{s['ch']['pass']:.3f} (|null {s['ch']['pass_given_null']:.3f}) e3 {s['e3']['pass']:.3f} "
                      f"(|null {s['e3']['pass_given_null']:.3f}) picks/s {s['picks_per_session']:.2f} true "
                      f"{s['true_mean_picks_bp']} [{time.time() - t0:.0f}s]", flush=True)


if __name__ == "__main__":
    main()

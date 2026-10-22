#!/usr/bin/env python
"""cal_cost7_ref.py: SYNTHETIC. The screen proxy's false-pass rate against the REAL-money null (true real after-cost
mean 0) for a constant cost shift: COST-7's margin alone (-5 bp), today's replay overcharge (-12 bp liquid, -20 bp thin)
and a judge charging exactly the true cost (0), at screen margins m0 = 0 and 10 bp; cells base/mid/worst, 13 and 30
events a session, 2,000 programs a cell, 120 sessions (simlib.py)."""
import json, multiprocessing as mp, sys
import numpy as np
import simlib as L
from cal_cost7 import CELLS, T

def job(a):
    cell, nb, R, seed = a
    B, BR, N = L.gen_blocks(seed, R, T, nb, **CELLS[cell])
    bl = L.compress(B, N, BR)
    out = {"cell": cell, "nbar": nb, "R": R}
    for s in (0, -5, -12, -20):
        for m0 in (0, 10):
            f = L.screen_first_pass(*bl, shift=np.full((R, T), s * 1e-4), m0=m0 * 1e-4)
            out[f"s{s}_m{m0}"] = float(np.mean(f >= 0))
    return out

if __name__ == "__main__":
    jobs = []; seed = 7_200_001
    for c in ("base", "mid", "worst"):
        for nb in (13, 30):
            jobs.append((c, nb, 2000, seed)); seed += 1
    with mp.Pool(4) as pool, open("cal_cost7_ref.out.jsonl", "w") as fh:
        for r in pool.imap_unordered(job, jobs):
            fh.write(json.dumps(r) + "\n"); fh.flush(); print(r, flush=True)

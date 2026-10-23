#!/usr/bin/env python
"""judge_stress.py (the edge-swings judge; SYNTHETIC ONLY): the named stress beyond PREREG-EVL-6's plausible grid that
its own text reports highest for a fixed program (day momentum phi_day 0.40 at rho_day 0.30: 0.138-0.161 there), run
for both seats on FRESH seeds (EVL-IDN-READ on the frozen generator from 245,000,001; EVL-R2-ON on the READER-2
designer's consumer simulator from 246,000,001). Reported, never binding (PREREG-EVL-6 section 4.3's stress list).
Usage: judge_stress.py [workers]"""
import dataclasses
import json
import math
import os
import sys
from multiprocessing import get_context

import judge_fp as J

HERE = os.path.dirname(os.path.abspath(__file__))


def main(workers):
    sys.path.insert(0, os.path.join(HERE, "evl6_frozen"))
    import calib_final as CF
    import calib_v2 as C2
    tc = C2.shape_kw("TC", "skew")[1]
    idn = [(f"S|idn|TC-skew|phi.40|rho.30|AR20|cnt|n{nb}", dict(nbar=nb, rho_day=0.30, phi_day=0.40, drift_sd=0.0020,
            cnt_kappa=0.3, mw_knife=14, **CF.N3, **tc), 2000) for nb in (5, 8)]
    jobs, seed = [], 245_000_000
    for lab, gk, R in idn:
        for c0 in range(0, R, 1000):
            seed += 1
            jobs.append((lab, gk, 1000, seed))
    rows = []
    with get_context("fork").Pool(workers) as pool:
        res = pool.map(J.idn_job, jobs)
    agg = {}
    for r in res:
        a = agg.setdefault(r["lab"], [])
        a += r["p1"]
    for lab, p1 in agg.items():
        f = sum(x <= 120 for x in p1) / len(p1)
        rows.append(dict(cell=lab, R=len(p1), run1_120=round(f, 4), se=round(math.sqrt(f * (1 - f) / len(p1)), 4)))
    CR = J.r2_mod()
    cells = [(f"S|r2|NV|phi.40|rho.30|AR20|n5|cnt|finf", CR.Cell(null="NV", nbar=5, cnt=True, finf=True, **dict(
        CR.CORNER, rho_day=0.30, phi_day=0.40, drift_sd=0.0020)), 2000),
             (f"S|r2|NV|phi.40|rho.30|AR20|n14|finf", CR.Cell(null="NV", nbar=14, finf=True, **dict(
                 CR.CORNER, rho_day=0.30, phi_day=0.40, drift_sd=0.0020)), 2000)]
    with get_context("fork").Pool(workers) as pool:
        mus = pool.map(J.r2_knife, [dataclasses.asdict(c) for _, c, _ in cells])
    jobs, seed = [], 246_000_000
    for (lab, c, R), mu in zip(cells, mus):
        for c0 in range(0, R, 500):
            seed += 1
            jobs.append((lab, dataclasses.asdict(c), 500, seed, mu))
    with get_context("fork").Pool(workers) as pool:
        res = pool.map(J.r2_job, jobs)
    agg = {}
    for lab, kw, Rj, sd, mu, r, secs in res:
        agg.setdefault(lab, []).extend(r["p1"])
    for lab, p1 in agg.items():
        f = sum(x <= 120 for x in p1) / len(p1)
        rows.append(dict(cell=lab, R=len(p1), run1_120=round(f, 4), se=round(math.sqrt(f * (1 - f) / len(p1)), 4)))
    with open(os.path.join(HERE, "judge_stress.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
            print(json.dumps(r))


if __name__ == "__main__":
    main(min(int(sys.argv[1]) if len(sys.argv) > 1 else 4, 4))

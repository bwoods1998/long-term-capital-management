"""demotion_long.py: the fixer's demotion simulation (unchanged copy) on fresh seeds (155,000,001+) at a LONGER
horizon: P(a true 60 bp edge is demoted by its stay's 1,000th / 2,000th / 3,000th Probe+ event), the 10% stop,
all three triggers, the worst plausible cell. Synthetic only."""
import os
import sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["FINAL_ARR"] = os.path.join(HERE, "theirs_arrays")
sys.path.insert(0, os.path.join(HERE, "theirs"))
import json  # noqa: E402
import time  # noqa: E402
from multiprocessing import get_context  # noqa: E402

import numpy as np  # noqa: E402

import calib_final as CF  # noqa: E402
import demotion_final as DF  # noqa: E402
import search_final as SF  # noqa: E402

DF.N_MAX = 3000
RULE = SF.Rule(9, ((14, 0.012), (20, 0.010), (60, 0.004)))
W = dict(rho_day=0.15, phi_day=0.20, drift_sd=0.0020, **CF.SHAPES["both"])
CELLS = [("60bp worst n85 long", dict(nbar=85, skill=0.006, **W), 3000, 420),
         ("60bp worst n30 long", dict(nbar=30, skill=0.006, **W), 3000, 420)]


def job(a):
    lab, kw, R, T, seed, stop = a
    res = DF.simulate_stay(CF.Gen(**kw), R, T, seed, RULE, 0.20, stop)
    return lab, stop, {k: v.tolist() for k, v in res.items()}


if __name__ == "__main__":
    jobs = []
    s0 = 155_000_000
    for stop in ("pct:0.10", "none"):
        for lab, kw, R, T in CELLS:
            s0 += 10_000
            for c in range(0, R, 250):
                jobs.append((lab, kw, 250, T, s0 + c // 250 + 1, stop))
    t0 = time.time()
    res = {}
    with get_context("fork").Pool(8) as pool:
        for lab, stop, r in pool.imap_unordered(job, jobs):
            d = res.setdefault((lab, stop), {k: [] for k in r})
            for k, v in r.items():
                d[k] += v
    out = []
    for (lab, stop), d in sorted(res.items()):
        d = {k: np.array(v) for k, v in d.items()}
        dem, why, nreal = d["dem_at"], d["why"], d["nreal"]
        row = {"cell": lab, "stop": stop, "R": int(dem.size)}
        for k in (1000, 2000, 3000):
            row[f"by{k}"] = round(float(np.mean(dem <= k)), 4)
            row[f"reached{k}"] = round(float(np.mean((nreal >= k) | (dem <= k))), 3)
            for code, nm in ((1, "stop"), (2, "tail"), (3, "read")):
                row[f"by{k}_{nm}"] = round(float(np.mean((dem <= k) & (why == code))), 4)
        out.append(row)
        print(json.dumps(row), flush=True)
    json.dump(out, open(os.path.join(HERE, "out", "demotion_long.json"), "w"), indent=1)
    print(f"{time.time() - t0:.0f}s")

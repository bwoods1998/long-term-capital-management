"""demotion_alt.py: the fixer's demotion simulation (unchanged copy) on fresh seeds (159,000,001+): the fixed reads at
p <= 0.20 (the file) beside p <= 0.15, the 10% stop, the cells nearest the 0.15 cap, and the knife edge (a false
pass's stay). P(demoted by the 300th / 1,000th / 2,000th Probe+ event). Synthetic only."""
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

DF.N_MAX = 2000
RULE = SF.Rule(9, ((14, 0.012), (20, 0.010), (60, 0.004)))
W = dict(rho_day=0.15, phi_day=0.20, drift_sd=0.0020, **CF.SHAPES["both"])
DS = dict(rho_day=0.15, phi_day=0.20, drift_sd=0.0020, **CF.SHAPES["dayskew"])
CELLS = [("60bp dayskew AR20 rho.15 phi.20 n85", dict(nbar=85, skill=0.006, **DS), 4000, 280),
         ("60bp worst n85", dict(nbar=85, skill=0.006, **W), 4000, 280),
         ("60bp worst n30", dict(nbar=30, skill=0.006, **W), 4000, 280),
         ("knife edge worst n85", dict(nbar=85, skill=0.006, mu_family=-0.006, **W), 2000, 280)]


def job(a):
    lab, kw, R, T, seed, rp = a
    res = DF.simulate_stay(CF.Gen(**kw), R, T, seed, RULE, rp, "pct:0.10")
    return lab, rp, {k: v.tolist() for k, v in res.items()}


if __name__ == "__main__":
    jobs = []
    s0 = 159_000_000
    for rp in (0.20, 0.15):
        for lab, kw, R, T in CELLS:
            s0 += 10_000
            for c in range(0, R, 250):
                jobs.append((lab, kw, 250, T, s0 + c // 250 + 1, rp))
    t0 = time.time()
    res = {}
    with get_context("fork").Pool(8) as pool:
        for lab, rp, r in pool.imap_unordered(job, jobs):
            d = res.setdefault((lab, rp), {k: [] for k in r})
            for k, v in r.items():
                d[k] += v
    out = []
    for (lab, rp), d in sorted(res.items()):
        d = {k: np.array(v) for k, v in d.items()}
        dem, why, nreal = d["dem_at"], d["why"], d["nreal"]
        row = {"cell": lab, "read_p": rp, "R": int(dem.size)}
        for k in (300, 1000, 2000):
            row[f"by{k}"] = round(float(np.mean(dem <= k)), 4)
            row[f"reached{k}"] = round(float(np.mean((nreal >= k) | (dem <= k))), 3)
        row["se1000"] = round(float(np.sqrt(row["by1000"] * (1 - row["by1000"]) / dem.size)), 4)
        out.append(row)
        print(json.dumps(row), flush=True)
    json.dump(out, open(os.path.join(HERE, "out", "demotion_alt.json"), "w"), indent=1)
    print(f"{time.time() - t0:.0f}s")

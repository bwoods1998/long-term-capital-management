"""CHECK #1 runner E (synthetic only): the family drift at shorter persistence with the SAME monthly (21-session)
tracking variance as the judge's 20 bp AR(0.97) drift (about +-3.8% a month, the judge's own plausibility yardstick),
and a second fresh-seed replicate of the corner cell."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calib_c1 as C
from run_c1 import _job
from multiprocessing import get_context
N3 = dict(skill=0.0060, mu_family=-0.0060)
SH = C.SHAPES
def cells():
    out = []
    for nb in (85, 30):
        out.append(("E|N3|both|AR.85m28", dict(nbar=nb, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0028, drift_rho=0.85), 2000))
    out.append(("E|N3|both|AR.70m37", dict(nbar=85, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0037, drift_rho=0.70), 2000))
    out.append(("E|N3|both|AR.90m25", dict(nbar=85, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0025, drift_rho=0.90), 2000))
    out.append(("E|N3|sym|AR.85m28", dict(nbar=85, rho_day=0.05, **N3, drift_sd=0.0028, drift_rho=0.85), 2000))
    out.append(("E|N3|dayskew|AR.85m28", dict(nbar=85, rho_day=0.15, **N3, **SH["dayskew"], drift_sd=0.0028, drift_rho=0.85), 2000))
    out.append(("A2|N3|both|AR20", dict(nbar=85, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0020), 2000))
    return out
if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    jobs = []; seed = 98_000_000
    for lab, kw, R in cells():
        for c in range(0, R, 500):
            seed += 1; jobs.append((lab, kw, 500, 120, seed))
    idx = os.path.join(os.path.dirname(os.path.abspath(__file__)), "c1E.index.jsonl")
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool, open(idx, "w") as fh:
        for k, (lab, kws, R, T, sd, path, info, secs) in enumerate(pool.imap_unordered(_job, jobs), 1):
            fh.write(json.dumps({"cell": lab, "gen": json.loads(kws), "R": R, "T": T, "seed": sd, "path": path, "info": info, "secs": round(secs, 1)}) + "\n"); fh.flush()
            print(f"{k}/{len(jobs)} {lab} n{json.loads(kws)['nbar']} {secs:.0f}s total {time.time()-t0:.0f}s", flush=True)

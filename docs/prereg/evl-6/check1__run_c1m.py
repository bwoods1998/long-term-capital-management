"""CHECK #1 runner BM (synthetic only): news volume follows the size of the day's shock; the knife edge is set on
MONEY weights min(n_t, 6) (Probe holds at most 6 a session), the mean a the real money earns."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calib_c1m as C
from multiprocessing import get_context
import numpy as np
N3 = dict(skill=0.0060, mu_family=-0.0060)
SH = C.SHAPES
def _job(args):
    lab, kw, R, T, seed = args
    t0 = time.time()
    out, info = C.simulate(C.Gen(**kw), R, T, seed, old_skew=False)
    path = os.path.join(C.SHM, f"c1mjob{seed}.npz")
    np.savez_compressed(path, **out)
    return lab, json.dumps(kw, sort_keys=True), R, T, seed, path, info, time.time() - t0
def cells():
    return [("BM|dayskew|nodrift|k.3", dict(nbar=3, rho_day=0.15, **N3, **SH["dayskew"], cnt_kappa=0.3, mw_knife=6), 2000),
            ("BM|both|AR20|k.3", dict(nbar=3, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0020, cnt_kappa=0.3, mw_knife=6), 2000),
            ("BM|both|AR20|k.3", dict(nbar=8, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0020, cnt_kappa=0.3, mw_knife=6), 2000)]
if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    jobs = []; seed = 99_000_000
    for lab, kw, R in cells():
        for c in range(0, R, 500):
            seed += 1; jobs.append((lab, kw, 500, 120, seed))
    idx = os.path.join(os.path.dirname(os.path.abspath(__file__)), "c1M.index.jsonl")
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool, open(idx, "w") as fh:
        for k, (lab, kws, R, T, sd, path, info, secs) in enumerate(pool.imap_unordered(_job, jobs), 1):
            fh.write(json.dumps({"cell": lab, "gen": json.loads(kws), "R": R, "T": T, "seed": sd, "path": path, "info": info, "secs": round(secs, 1)}) + "\n"); fh.flush()
            print(f"{k}/{len(jobs)} {lab} n{json.loads(kws)['nbar']} {secs:.0f}s total {time.time()-t0:.0f}s", flush=True)

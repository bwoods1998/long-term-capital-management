"""CHECK #1 runner (synthetic only): fresh-seed replication of the judge's worst plausible cells, plus structures the
judge's grid did not hold. Outputs arrays to /dev/shm/calib-check1 and an index file here."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calib_c1 as C
from multiprocessing import get_context

N3 = dict(skill=0.0060, mu_family=-0.0060)
SH = C.SHAPES
def cells():
    out = []
    # A: fresh seeds, the judge's own top plausible cells
    for nb in (85, 30, 13, 8):
        out.append(("A|N3|both|AR20", dict(nbar=nb, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0020), 2000))
    out.append(("A|N3|dayskew|AR20", dict(nbar=85, rho_day=0.15, **N3, **SH["dayskew"], drift_sd=0.0020), 2000))
    # B: news volume follows the size of the day's shock (count x exp(0.3 min(|eps|,4))), event-weighted knife edge
    for nb in (30, 13, 8, 3):
        out.append(("B|EW|dayskew|nodrift|k.3", dict(nbar=nb, rho_day=0.15, **N3, **SH["dayskew"], cnt_kappa=0.3, ew_knife=True), 2000))
        out.append(("B|EW|both|AR20|k.3", dict(nbar=nb, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0020, cnt_kappa=0.3, ew_knife=True), 2000))
    for nb in (13, 8):
        out.append(("B|EW|dayskew|nodrift|K3", dict(nbar=nb, rho_day=0.15, **N3, **SH["dayskew"], cnt_crashK=3.0, ew_knife=True), 2000))
        out.append(("B|EW|dayskew|nodrift|k.3|rho.05", dict(nbar=nb, rho_day=0.05, **N3, **SH["dayskew"], cnt_kappa=0.3, ew_knife=True), 2000))
    # B0: control for B: same generator, no coupling, ew_knife on (should match the judge's cells)
    out.append(("B0|EW|dayskew|nodrift|k0", dict(nbar=13, rho_day=0.15, **N3, **SH["dayskew"], ew_knife=True), 2000))
    # C: factor momentum AR 0.25 at plausible rho
    for nb in (85, 13):
        out.append(("C|N3|both|AR20|phi.25", dict(nbar=nb, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0020, phi_day=0.25), 2000))
        out.append(("C|N3|sym|nodrift|phi.25", dict(nbar=nb, rho_day=0.15, **N3, phi_day=0.25), 2000))
    out.append(("C|N3|both|AR20|phi.20", dict(nbar=85, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0020, phi_day=0.20), 2000))
    # D: the drift at AR 0.85 with the long-run variance of 20 bp at AR 0.97 (46 bp stationary sd)
    for nb in (85, 13):
        out.append(("D|N3|both|AR.85eq", dict(nbar=nb, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0046, drift_rho=0.85), 2000))
        out.append(("D|N3|sym|AR.85eq", dict(nbar=nb, rho_day=0.05, **N3, drift_sd=0.0046, drift_rho=0.85), 2000))
    out.append(("D|N3|both|AR.90eq", dict(nbar=85, rho_day=0.15, **N3, **SH["both"], drift_sd=0.0037, drift_rho=0.90), 2000))
    return out

def _job(args):
    lab, kw, R, T, seed = args
    t0 = time.time()
    out, info = C.simulate(C.Gen(**kw), R, T, seed, old_skew=False)
    import numpy as np
    path = os.path.join(C.SHM, f"c1job{seed}.npz")
    np.savez_compressed(path, **out)
    return lab, json.dumps(kw, sort_keys=True), R, T, seed, path, info, time.time() - t0

if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    only = sys.argv[2] if len(sys.argv) > 2 else ""
    jobs = []
    seed = 97_000_000
    for lab, kw, R in cells():
        for c in range(0, R, 500):
            seed += 1
            if only and not lab.startswith(only):
                continue
            jobs.append((lab, kw, 500, 120, seed))
    jobs.sort(key=lambda j: -j[1]["nbar"])
    idx = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"c1{only or 'all'}.index.jsonl")
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool, open(idx, "w") as fh:
        for k, (lab, kws, R, T, sd, path, info, secs) in enumerate(pool.imap_unordered(_job, jobs), 1):
            fh.write(json.dumps({"cell": lab, "gen": json.loads(kws), "R": R, "T": T, "seed": sd, "path": path, "info": info, "secs": round(secs, 1)}) + "\n"); fh.flush()
            print(f"{k}/{len(jobs)} {lab} n{json.loads(kws)['nbar']} {secs:.0f}s total {time.time()-t0:.0f}s", flush=True)

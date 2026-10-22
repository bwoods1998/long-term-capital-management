#!/usr/bin/env python
"""Check #2, part 3 (SYNTHETIC ONLY): the chosen rule against a MONEY-WEIGHTED version of the same test.
Block term y_s = w_s (B_s - 10 bp) with w_s = min(n_s, 6) (the Probe cap: the money a session can hold), and the pure
event-weighted w_s = n_s. Everything else (schedule, alpha, guards, retirement on the unweighted values) as the chosen rule."""
import os, sys, json, time, inspect
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import check2 as C2
CJ = C2.CJ
src = inspect.getsource(CJ.simulate)
rep = list(C2.rep) + [
    ('s["X"][hr, s["S"][hr]] = Bt[hr]',
     's["X"][hr, s["S"][hr]] = Bt[hr]\n            s.setdefault("W", np.zeros((R, S_CAP)))[hr, s["S"][hr]] = nP[hr]'),
    ('            # the lower tail (EVL-6 retirement',
     '''            for wk, cap in (("w6", 6.0), ("wn", 1e9)):
                Pw = s.setdefault("P" + wk, np.full((R, T), np.nan))
                cand = np.nonzero(look)[0]
                if cand.size:
                    Pw[cand, ti] = 1.0
                    for Sv in np.unique(S[cand]):
                        rs = cand[S[cand] == Sv]
                        Xv = np.minimum(s["W"][rs, :Sv], cap) * (s["X"][rs, :Sv] - 0.0010)
                        zz = Xv.sum(axis=1) / np.sqrt(np.maximum((Xv * Xv).sum(axis=1), 1e-300))
                        keep = rs[zz >= Z_PRE]
                        if keep.size:
                            Pw[keep, ti] = signflip_p_rows(np.minimum(s["W"][keep, :Sv], cap) * (s["X"][keep, :Sv] - 0.0010), int(Sv))
            # the lower tail (EVL-6 retirement'''),
    ('        out[f"L{L}_cam"] = s["cam"].astype(np.float32)',
     '        out[f"L{L}_cam"] = s["cam"].astype(np.float32)\n        out[f"L{L}_Pw6"] = s["Pw6"].astype(np.float32)\n        out[f"L{L}_Pwn"] = s["Pwn"].astype(np.float32)'),
]
for a, b in rep:
    assert src.count(a) == 1, a
    src = src.replace(a, b)
ns = dict(CJ.__dict__)
exec(src, ns)
simulate = ns["simulate"]


def job(args):
    lab, kw, R, T, seed, lags, old = args
    ns["LAGS"] = tuple(lags); ns["V2_NS"] = ()
    t0 = time.time()
    out, info = simulate(C2.Gen2(**kw), R, T, seed, old_skew=False)
    res = {"cell": lab, "gen": kw, "R": R, "T": T, "seed": seed, "secs": round(time.time() - t0, 1), "mean_read_n": info["mean_read_n"]}
    fp, _ = C2.SJ.first_pass(out, 0, C2.RULE)
    res["L0"] = fp.tolist()
    for wk in ("w6", "wn"):
        d = dict(out); d["L0_P0.001"] = out[f"L0_P{wk}"]
        fpw, _ = C2.SJ.first_pass(d, 0, C2.RULE)
        res[f"L0_{wk}"] = fpw.tolist()
        dd = dict(d); dd["L0_P0.001"] = np.fmax(out["L0_P0.001"], out[f"L0_P{wk}"])   # both tests must pass
        fpb, _ = C2.SJ.first_pass(dd, 0, C2.RULE)
        res[f"L0_both_{wk}"] = fpb.tolist()
    return res


def main():
    import argparse
    from multiprocessing import get_context
    ap = argparse.ArgumentParser(); ap.add_argument("plan"); ap.add_argument("--workers", type=int, default=4); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plan = json.load(open(a.plan)); jobs = []
    for cell in plan["cells"]:
        seed = cell["seed0"]
        for c in range(0, cell["R"], 500):
            seed += 1
            jobs.append((cell["lab"], cell["gen"], min(500, cell["R"] - c), cell.get("T", 120), seed, [0], False))
    jobs.sort(key=lambda j: -j[1].get("nbar", 85))
    t0 = time.time()
    with get_context("fork").Pool(a.workers) as pool, open(a.out, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(job, jobs), 1):
            fh.write(json.dumps(res) + "\n"); fh.flush()
            print(f"{k}/{len(jobs)} {time.time() - t0:.0f}s {res['cell']} n{res['gen'].get('nbar')} {res['secs']}s", flush=True)


if __name__ == "__main__":
    main()

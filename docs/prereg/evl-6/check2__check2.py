#!/usr/bin/env python
"""Adversarial check #2 of PREREG-EVL-6 (SYNTHETIC ONLY: no lane data, no prices, no stores).

Re-runs the judge's generator (judge/calib_judge.py) on FRESH seeds for the chosen rule, and adds structures the
judge's grid did not hold:
  kappa   event intensity correlated with the session's residual: every event of session t gets
          kappa * (1/k - (G_t - 1)), G_t ~ Gamma(k, 1/k) the session's count intensity. Event-weighted mean of the
          term is exactly 0 (the money null of a program whose positions are one per event); the BLOCK mean is +kappa/k.
  lam     family drift coupled to the volatility regime: every event gets -lam * (h_t - 1) (calm regimes positive,
          volatile ones negative; mean 0).
  crash10 crash days at 10% of sessions, -2.5 sd (P(day shock > 0) = 0.65).
The chosen rule: mlist 6..16,18,20,22,25,30,35,40,50,60; alpha 0.016 (S <= 20) / 0.004; margin 10 bp; full guards;
retirement.  Variants: 'ewg' = the same rule with the event-weighted guard mean a > 10 bp in place of mean a > 0.
"""
from __future__ import annotations
import os, sys, json, math, inspect, dataclasses, time
os.environ["CALIB_SHM"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shm")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"
JUDGE = "/home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl6/judge"
sys.path.insert(0, JUDGE)
import numpy as np
import calib_judge as CJ

CJ.M0S = (0.0, 0.0010, 0.0015, 0.0020)
CJ.CRASH["crash10"] = (0.10, 2.5)

@dataclasses.dataclass(frozen=True)
class Gen2(CJ.Gen):
    kappa: float = 0.0
    lam: float = 0.0

src = inspect.getsource(CJ.simulate)
rep = [
    ("nC = np.minimum(rng.poisson(rate_c * rng.gamma(g.shape_n, 1.0 / g.shape_n, R)), n_el)",
     "Gt = rng.gamma(g.shape_n, 1.0 / g.shape_n, R)\n        nC = np.minimum(rng.poisson(rate_c * Gt), n_el)"),
    ("a = g.mu_family + D[er] + h[er] * (common + noise)",
     "a = g.mu_family + D[er] + h[er] * (common + noise) + g.kappa * (1.0 / g.shape_n - (Gt[er] - 1.0)) - g.lam * (h[er] - 1.0)"),
    ('s["abs"][:, ti] = (s["ca"] > 0) & (s["cr"] > 0)',
     's["abs"][:, ti] = (s["ca"] > 0) & (s["cr"] > 0)\n            s.setdefault("cam", np.zeros((R, T)))[:, ti] = s["ca"] / np.maximum(s["ne"], 1)'),
    ('out[f"L{L}_PL"] = s["PL"].astype(np.float32)',
     'out[f"L{L}_PL"] = s["PL"].astype(np.float32)\n        out[f"L{L}_cam"] = s["cam"].astype(np.float32)'),
]
for a, b in rep:
    assert src.count(a) == 1, a
    src = src.replace(a, b)
ns = dict(CJ.__dict__)
exec(src, ns)
simulate = ns["simulate"]

import search_judge as SJ
D6S = "mlist:6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60"
D7S = "mlist:7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60"
RULE = (D6S, "step:0.016:20:0.004", 0.001, "full", True)
RULES = {"R0": RULE, "R1_sb16": (D6S, "step:0.016:16:0.004", 0.001, "full", True),
         "R2_from7": (D7S, "step:0.016:20:0.004", 0.001, "full", True),
         "R3_from7_sb16": (D7S, "step:0.016:16:0.004", 0.001, "full", True),
         "R4_strict": (D6S, "step:0.012:20:0.003", 0.001, "full", True),
         "R5_m15": (D6S, "step:0.016:20:0.004", 0.0015, "full", True),
         "R6_m20": (D6S, "step:0.016:20:0.004", 0.002, "full", True)}


def first_pass(d, L, rule, ewg=False):
    if ewg:
        d = dict(d)
        d[f"L{L}_abs"] = d[f"L{L}_abs"] & (d[f"L{L}_cam"] > 0.0010)
    return SJ.first_pass(d, L, rule)


def job(args):
    lab, kw, R, T, seed, lags, old = args
    ns["LAGS"] = tuple(lags)
    ns["V2_NS"] = CJ.V2_NS if old else ()
    t0 = time.time()
    out, info = simulate(Gen2(**kw), R, T, seed, old_skew=old)
    res = {"cell": lab, "gen": kw, "R": R, "T": T, "seed": seed, "secs": round(time.time() - t0, 1)}
    for L in lags:
        fp, fr = first_pass(out, L, RULE)
        fpe, _ = first_pass(out, L, RULE, ewg=True)
        res[f"L{L}"] = fp.tolist()
        res[f"L{L}_ewg"] = fpe.tolist()
        res[f"L{L}_ret"] = fr.tolist()
        # the session (block count) of the first pass, for the per-look split
        Sat = out[f"L{L}_Sat"]
        res[f"L{L}_S"] = [int(Sat[i, f - 1]) if f < 10 ** 6 else -1 for i, f in enumerate(fp)]
    for name, rule in RULES.items():
        if name == "R0":
            continue
        for L in lags:
            fp, _ = first_pass(out, L, rule)
            res[f"L{L}_{name}"] = fp.tolist()
    if old:
        res["old"] = out["old"].astype(int).tolist()
    res["mean_read_n"] = info["mean_read_n"]
    return res


def main():
    import argparse
    from multiprocessing import get_context
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    jobs = []
    for cell in plan["cells"]:
        seed = cell["seed0"]
        for c in range(0, cell["R"], 500):
            seed += 1
            jobs.append((cell["lab"], cell["gen"], min(500, cell["R"] - c), cell.get("T", 120), seed,
                         cell.get("lags", [0]), cell.get("old", False)))
    jobs.sort(key=lambda j: -j[1].get("nbar", 85))
    t0 = time.time()
    with get_context("fork").Pool(a.workers) as pool, open(a.out, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(job, jobs), 1):
            fh.write(json.dumps(res) + "\n"); fh.flush()
            print(f"{k}/{len(jobs)} {time.time() - t0:.0f}s {res['cell']} n{res['gen'].get('nbar')} {res['secs']}s", flush=True)


if __name__ == "__main__":
    main()

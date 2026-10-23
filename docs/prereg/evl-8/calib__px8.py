#!/usr/bin/env python
"""px8.py: the PREREG-EVL-8 judge's recalibration of the PRICE LANE's seats (PX-DROP-ON, PX-SURGE-ON, PX-GAP-O1)
under PREREG-EVL-6 AS DRAFTED (evl6d.py), on the PX designer's own generator (../price/px_calib.py `generate`,
imported unchanged: high-beta losers against an index benchmark, crash days on the benchmark, sector-hot sessions,
Zipf repeat issuers, a persistent family drift AR(0.97), left-skewed events and distress jumps, persistent issuer
effects; noise cells quiet / base / mid / worst / stress as that file defines them). SYNTHETIC ONLY.

Cells: nulls N0 (mean a exactly 0, control 0) and NK (the knife edge: mean a 0, the control -30 bp, so "beats its
control" never protects: also the no-control figure) x 5 noise cells x (lam, K) in (8, 20), (20, 20), (40, 40);
power (mu = judged a after the replay's cost) 20-100 bp at base / mid / worst, (20, 20) and (40, 40).
Every replicate: 120 sessions. Seeds 83,000,001 on (one per cell, in the order of `cells`).

Usage: px8.py run [--R 2000] [--Rp 1000] [--workers 4] [--out px8]
"""
from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import os
import sys
import time

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "price")))
import px_calib as PX  # noqa: E402
import evl6d  # noqa: E402

# the judge's added cell: the PX designer's worst cell without its persistent issuer effects (tau 0), to separate the
# share of the worst cell's passes that come from issuer effects (which give a pick record a real forward offset)
PX.NOISE["worstnotau"] = dict(PX.NOISE["worst"], tau=0.0)


def to_sim(g):
    a, r, iss, valid, C = g["a"], g["r"], g["iss"], g["valid"], g["C"]
    R, T, K = a.shape
    order = np.argsort(~valid, axis=2, kind="stable")          # valid entries first
    va = np.take_along_axis(valid, order, axis=2)
    aa = np.where(va, np.take_along_axis(a, order, axis=2), np.nan)
    rr = np.where(va, np.take_along_axis(r, order, axis=2), np.nan)
    ii = np.where(va, np.take_along_axis(iss, order, axis=2), -1)
    n = va.sum(axis=2)
    with np.errstate(invalid="ignore"):
        B = np.where(n > 0, np.nansum(aa, axis=2) / np.maximum(n, 1), np.nan)
        Rm = np.where(n > 0, np.nansum(rr, axis=2) / np.maximum(n, 1), np.nan)
    return {"B": B, "Rm": Rm, "n": n, "ctrl": C, "iss": ii, "a": aa}


RULES = {
    "evl6": (evl6d.alpha, 0.0010),                                    # PREREG-EVL-6 as drafted
    "a12": (lambda S: 0.012 if S <= 20 else 0.003, 0.0010),           # the draft's own 0.106 alternative
    "m15": (evl6d.alpha, 0.0015),                                     # the draft's 15 bp alternative
    "a10": (lambda S: 0.010 if S <= 20 else 0.0025, 0.0010),
    "a08": (lambda S: 0.008 if S <= 20 else 0.002, 0.0010),
    "a10m15": (lambda S: 0.010 if S <= 20 else 0.0025, 0.0015),
    "a12m15": (lambda S: 0.012 if S <= 20 else 0.003, 0.0015),
}
S10 = (10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
S12 = (12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
S15 = (15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
S14 = (14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
LOOKS_OF = {"s10": S10, "s12": S12, "s10a12": S10, "s12a12": S12, "s10a10": S10, "s15": S15, "s14": S14,
            "s14a12": S14}
RULES.update({
    "s10": (evl6d.alpha, 0.0010),
    "s12": (evl6d.alpha, 0.0010),
    "s10a12": (lambda S: 0.012 if S <= 20 else 0.003, 0.0010),
    "s12a12": (lambda S: 0.012 if S <= 20 else 0.003, 0.0010),
    "s10a10": (lambda S: 0.010 if S <= 20 else 0.0025, 0.0010),
    "s15": (evl6d.alpha, 0.0010),
    "s14": (evl6d.alpha, 0.0010),
    "s14a12": (lambda S: 0.012 if S <= 20 else 0.003, 0.0010),
})
RULE = os.environ.get("PX8_RULE", "evl6")
LOOKS8 = LOOKS_OF.get(RULE, evl6d.LOOKS)


def run_cell(args):
    name, kind, noise, lam, kcap, mu, mu_c, R, seed = args
    al, m0 = RULES[RULE]
    t0 = time.time()
    rng = np.random.default_rng(seed)
    res, ch = [], []
    done = 0
    while done < R:
        b = min(100, R - done)
        g = PX.generate(rng, b, lam, PX.NOISE[noise], mu, mu_c, kcap)
        sim = to_sim(g)
        for i in range(b):
            res.append(evl6d.screen(sim, i, 0, True, looks=LOOKS8, alpha_fn=al, margin=m0))
            if kind == "null":
                ch.append(evl6d.chain(sim, i, 3, True, looks=LOOKS8, alpha_fn=al, margin=m0))
        done += b
    passed = np.array([x[0] for x in res])
    when = np.array([x[1] for x in res])
    ret = np.array([x[2] for x in res])
    out = {"rule": RULE, "cell": name, "kind": kind, "noise": noise, "lam": lam, "K": kcap, "mu_bp": round(mu * 1e4, 1),
           "ctrl_bp": round(mu_c * 1e4, 1), "R": R, "seed": seed,
           "pass": float(passed.mean()), "retired_or_exhausted": float(ret.mean())}
    for h in (10, 20, 30, 40, 60, 120):
        out[f"by{h}"] = float((passed & (when < h)).mean())
    out["median_pass_session"] = float(np.median(when[passed]) + 1) if passed.any() else None
    if ch:
        out["chain3_pass"] = float(np.mean([c[0] for c in ch]))
        out["chain3_versions_mean"] = float(np.mean([c[2] for c in ch]))
    out["secs"] = round(time.time() - t0, 1)
    return out


def cells(R, Rp):
    out = []
    seed = int(os.environ.get("PX8_SEED", "83000001"))   # the confirmation run of the chosen rule uses fresh seeds
    for noise, (lam, kcap), null in itertools.product(("quiet", "base", "mid", "worst", "stress"),
                                                      ((8, 20), (20, 20), (40, 40)), ("N0", "NK")):
        out.append((f"{null}-{noise}-lam{lam}-K{kcap}", "null", noise, lam, kcap, 0.0,
                    0.0 if null == "N0" else -0.0030, R, seed))
        seed += 1
    for noise, (lam, kcap), mu in itertools.product(("base", "mid", "worst"), ((20, 20), (40, 40)),
                                                    (20, 30, 40, 60, 80, 100)):
        out.append((f"P{mu}-{noise}-lam{lam}-K{kcap}", "power", noise, lam, kcap, mu * 1e-4, 0.0, Rp, seed))
        seed += 1
    for (lam, kcap), null in itertools.product(((20, 20), (40, 40)), ("N0", "NK")):   # appended: earlier seeds unchanged
        out.append((f"{null}-worstnotau-lam{lam}-K{kcap}", "null", "worstnotau", lam, kcap, 0.0,
                    0.0 if null == "N0" else -0.0030, R, seed))
        seed += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--R", type=int, default=2000)
    ap.add_argument("--Rp", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(HERE, "px8_" + RULE))
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    todo = cells(a.R, a.Rp)
    if a.only:
        keys = a.only.split(",")
        todo = [c for c in todo if any(k == c[0] or (k.endswith("*") and c[0].startswith(k[:-1])) for k in keys)]
    t0 = time.time()
    with mp.Pool(min(4, a.workers)) as pool, open(a.out + ".jsonl", "w") as fh:
        for i, res in enumerate(pool.imap_unordered(run_cell, todo)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{i + 1}/{len(todo)} {res['cell']} pass {res['pass']:.3f} by20 {res['by20']:.3f} "
                  f"chain3 {res.get('chain3_pass', float('nan')):.3f} ({res['secs']}s, {time.time() - t0:.0f}s)",
                  flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""px_c1b.py: ADVERSARIAL CHECK #1 of PREREG-EVL-8, the PX FIX measured: THE PX SCREEN judging the seat's MONEY
POPULATION (the first 14 TRADABLE events of each block by the seat's ranking = A99's Probe room) instead of the
shadow's 40. SYNTHETIC ONLY (the PX designer's generator, imported unchanged; THE PX SCREEN as px_c1.screen).

Cells: the nulls N0 / NK at base, mid, worst, stress, worstnotau (lam40-K40 and lam20-K20; fresh seeds 63,000,001 on);
the money-population attack (top 14 at 0 bp, the rest +40 / +60 bp) and uniform power 30 / 40 / 60 / 80 bp, each
judged on all 40 (as drafted) and on the top 14 (the fix) ON THE SAME PATHS.
Usage: px_c1b.py run [--R 2000] [--workers 2] [--only substr]
"""
from __future__ import annotations

import argparse
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
import px_c1 as C  # noqa: E402

PX = C.PX
PX.NOISE.setdefault("worstnotau", dict(PX.NOISE["worst"], tau=0.0))


def topk(sim, k=14):
    """The first k valid events of each block (sim is left-packed in rank order)."""
    out = dict(sim)
    n = np.minimum(sim["n"], k)
    for key in ("a", "r"):
        x = sim[key].copy()
        x[:, :, k:] = np.nan
        out[key] = x
    ii = sim["iss"].copy()
    ii[:, :, k:] = -1
    out["iss"] = ii
    out["n"] = n
    with np.errstate(invalid="ignore"):
        out["B"] = np.where(n > 0, np.nansum(out["a"], axis=2) / np.maximum(n, 1), np.nan)
        out["Rm"] = np.where(n > 0, np.nansum(out["r"], axis=2) / np.maximum(n, 1), np.nan)
    return out


def run_cell(args):
    name, noise, lam, kcap, mu_top, mu_rest, mu_c, R, seed = args
    t0 = time.time()
    rng = np.random.default_rng(seed)
    mu = np.where(np.arange(kcap) < 14, mu_top, mu_rest)
    p40, p14, w14 = [], [], []
    done = 0
    while done < R:
        b = min(100, R - done)
        g = PX.generate(rng, b, lam, PX.NOISE[noise], mu, mu_c, kcap)
        sim = C.to_sim(g)
        s14 = topk(sim, 14)
        for i in range(b):
            p40.append(C.screen(sim, i)[0])
            x = C.screen(s14, i)
            p14.append(x[0])
            w14.append(x[1])
        done += b
    p40, p14, w14 = np.array(p40), np.array(p14), np.array(w14)
    return {"cell": name, "noise": noise, "lam": lam, "K": kcap, "mu_top_bp": mu_top * 1e4, "mu_rest_bp": mu_rest * 1e4,
            "ctrl_bp": mu_c * 1e4, "R": R, "seed": seed, "pass_all40_drafted": float(p40.mean()),
            "pass_top14_fix": float(p14.mean()), "top14_by20": float(((w14 >= 0) & (w14 < 20) & p14).mean()),
            "top14_by60": float(((w14 >= 0) & (w14 < 60) & p14).mean()), "secs": round(time.time() - t0, 1)}


def cells(R):
    out = []
    seed = 63_000_001

    def add(*c):
        nonlocal seed
        out.append(c + (R, seed))
        seed += 1
    for noise in ("base", "mid", "worst", "stress", "worstnotau"):
        for lam, k in ((40, 40), (20, 20)):
            for null, mc in (("N0", 0.0), ("NK", -0.0030)):
                add(f"NULL-{null}-{noise}-lam{lam}-K{k}", noise, lam, k, 0.0, 0.0, mc)
    for noise in ("base", "worst"):
        for mt, mr in ((0.0, 0.0040), (0.0, 0.0060)):
            add(f"TOPK-{noise}-top{int(mt*1e4)}-rest{int(mr*1e4)}-lam40-K40", noise, 40, 40, mt, mr, 0.0)
        for m in (0.0030, 0.0040, 0.0060, 0.0080):
            add(f"POW-{noise}-{int(m*1e4)}-lam40-K40", noise, 40, 40, m, m, 0.0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--R", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "px_c1b"))
    a = ap.parse_args()
    todo = [c for c in cells(a.R) if a.only in c[0]]
    t0 = time.time()
    with mp.Pool(min(4, a.workers)) as pool, open(a.out + ".jsonl", "a") as fh:
        for i, res in enumerate(pool.imap_unordered(run_cell, todo)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{i + 1}/{len(todo)} {json.dumps(res)} [{time.time() - t0:.0f}s]", flush=True)


if __name__ == "__main__":
    main()

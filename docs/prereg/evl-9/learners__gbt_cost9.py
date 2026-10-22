#!/usr/bin/env python
"""gbt_cost9.py: wall time of one round of PREREG-EVL-9's histogram GBT (W5) on a SYNTHETIC table (random numbers only).

Depth 3, 32 bins a column, leaf penalty 2,000 rows, a split needing >= 2,000 rows a side, gradient sums by np.bincount in
row order (W5's determinism rule). Runs ROUNDS rounds on N rows x D columns and reports seconds a round, and checks
that two runs give bit-identical predictions (the in-job determinism check).
"""
from __future__ import annotations

import hashlib
import sys
import time

import numpy as np

N, D, BINS, DEPTH, LAM, MIN_LEAF, LR = 700_000, 54, 32, 3, 2000.0, 2000, 0.05
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def fit(Xb, y, rounds):
    n = len(y)
    pred = np.zeros(n)
    off = (np.arange(D) * BINS)[None, :]
    flat = (Xb.astype(np.int64) + off)                     # (n, D) global bin ids
    for _ in range(rounds):
        r = y - pred
        node = np.zeros(n, dtype=np.int64)
        for level in range(DEPTH):
            nn = 1 << level
            key = (node[:, None] * (D * BINS) + flat).ravel()
            sr = np.bincount(key, weights=np.repeat(r, D), minlength=nn * D * BINS).reshape(nn, D, BINS)
            sc = np.bincount(key, minlength=nn * D * BINS).reshape(nn, D, BINS).astype(float)
            cr, cc = np.cumsum(sr, axis=2), np.cumsum(sc, axis=2)
            tr, tc = cr[:, :, -1:], cc[:, :, -1:]
            gain = cr ** 2 / (cc + LAM) + (tr - cr) ** 2 / (tc - cc + LAM) - tr ** 2 / (tc + LAM)
            gain = np.where((cc >= MIN_LEAF) & (tc - cc >= MIN_LEAF), gain, -np.inf)
            best = gain.reshape(nn, -1).argmax(axis=1)          # ties: lowest column, then lowest bin
            fcol, fbin = best // BINS, best % BINS
            go = Xb[np.arange(n), fcol[node]] > fbin[node]
            node = 2 * node + go
        lr = np.bincount(node, weights=r, minlength=1 << DEPTH)
        lc = np.bincount(node, minlength=1 << DEPTH)
        pred = pred + LR * (lr / (lc + LAM))[node]
    return pred


def main():
    rng = np.random.default_rng(9)
    Xb = rng.integers(0, BINS, (N, D), dtype=np.int16)
    y = rng.standard_normal(N)
    t0 = time.perf_counter()
    p1 = fit(Xb, y, ROUNDS)
    t1 = time.perf_counter()
    p2 = fit(Xb, y, ROUNDS)
    h1, h2 = hashlib.sha256(p1.tobytes()).hexdigest(), hashlib.sha256(p2.tobytes()).hexdigest()
    print({"N": N, "D": D, "rounds": ROUNDS, "secs_per_round": round((t1 - t0) / ROUNDS, 3), "identical": h1 == h2})


if __name__ == "__main__":
    main()

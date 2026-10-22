#!/usr/bin/env python3
"""house_cost9.py: wall time of PREREG-EVL-9's House-side work in STANDARD-LIBRARY Python (the House runs stdlib only).

Synthetic inputs only (random numbers; nothing from the lane or any market). Measures, single core:
  1. the frozen GBT column: R trees of depth 3 evaluated for N candidates of D columns;
  2. the nightly per-session statistics: A_s (upper triangle) and b_s by math.fsum over N rows;
  3. one decision: A = A_0 + sum of 250 weighted session matrices, standardisation, ridge (lam 8,000), Cholesky
     solve, and the N predictions.
"""
from __future__ import annotations

import math
import random
import time

N, D, R, S = 850, 58, 600, 250


def make_trees(rng):
    trees = []
    for _ in range(R):
        nodes = []
        for _ in range(7):                       # depth 3: 7 internal nodes (heap order), 8 leaves
            nodes.append((rng.randrange(D), rng.random()))
        leaves = [rng.gauss(0, 0.01) for _ in range(8)]
        trees.append((nodes, leaves))
    return trees


def gbt(trees, x):
    s = 0.0
    for nodes, leaves in trees:
        i = 0
        for _ in range(3):
            j, thr = nodes[i]
            i = 2 * i + (2 if x[j] > thr else 1)
        s += leaves[i - 7]
    return s


def session_stats(X, y):
    n = len(X)
    mx = [math.fsum(X[r][j] for r in range(n)) / n for j in range(D)]
    my = math.fsum(y) / n
    Xd = [[X[r][j] - mx[j] for j in range(D)] for r in range(n)]
    yd = [v - my for v in y]
    A = [[0.0] * D for _ in range(D)]
    for j in range(D):
        colj = [row[j] for row in Xd]
        for k in range(j, D):
            v = math.fsum(a * row[k] for a, row in zip(colj, Xd))
            A[j][k] = A[k][j] = v
    b = [math.fsum(row[j] * v for row, v in zip(Xd, yd)) for j in range(D)]
    return A, b, n


def cholesky_solve(M, v):
    n = len(M)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = math.fsum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                L[i][j] = math.sqrt(M[i][i] - s)
            else:
                L[i][j] = (M[i][j] - s) / L[j][j]
    z = [0.0] * n
    for i in range(n):
        z[i] = (v[i] - math.fsum(L[i][k] * z[k] for k in range(i))) / L[i][i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (z[i] - math.fsum(L[k][i] * x[k] for k in range(i + 1, n))) / L[i][i]
    return x


def decision(A0, b0, N0, stats, X):
    w = [2.0 ** (-(S - s) / 40.0) for s in range(S)]
    A = [row[:] for row in A0]
    b = b0[:]
    Nw = N0
    for (As, bs, ns), ws in zip(stats, w):
        for j in range(D):
            Aj, Asj = A[j], As[j]
            for k in range(D):
                Aj[k] += ws * Asj[k]
            b[j] += ws * bs[j]
        Nw += ws * ns
    d = [math.sqrt(max(A[j][j] / Nw, 1e-18)) for j in range(D)]
    M = [[A[j][k] / (d[j] * d[k]) + (8000.0 if j == k else 0.0) for k in range(D)] for j in range(D)]
    bb = [b[j] / d[j] for j in range(D)]
    beta = [v / dj for v, dj in zip(cholesky_solve(M, bb), d)]
    xbar = [math.fsum(row[j] for row in X) / len(X) for j in range(D)]
    return [math.fsum((row[j] - xbar[j]) * beta[j] for j in range(D)) for row in X]


def main():
    rng = random.Random(9)
    trees = make_trees(rng)
    X = [[rng.random() for _ in range(D)] for _ in range(N)]
    y = [rng.gauss(0, 1) for _ in range(N)]
    t0 = time.perf_counter()
    g = [gbt(trees, x) for x in X]
    t1 = time.perf_counter()
    A, b, n = session_stats(X, y)
    t2 = time.perf_counter()
    A0 = [[(100000.0 if j == k else 1000.0) for k in range(D)] for j in range(D)]
    b0 = [0.0] * D
    stats = [(A, b, n)] * S
    e = decision(A0, b0, 100000.0, stats, X)
    t3 = time.perf_counter()
    print({"N": N, "D": D, "trees": R, "sessions": S, "gbt_eval_s": round(t1 - t0, 3),
           "session_stats_s": round(t2 - t1, 3), "decision_s": round(t3 - t2, 3), "finite": all(map(math.isfinite, e)),
           "g_mean": round(sum(g) / N, 6)})


if __name__ == "__main__":
    main()

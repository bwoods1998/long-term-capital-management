#!/usr/bin/env python
"""check_gvar.py: SYNTHETIC check that FILL-7's exact within-session permutation sd of the selection gap
G_w = (1/n_F) sum_s k_s (mean_s,A - mean_s,F) equals the brute-force permutation sd (fill labels shuffled within each
session), on random sessions with t(3) values and session-varying fill counts."""
import numpy as np
rng = np.random.default_rng(7_600_001)
for trial in range(5):
    S = rng.integers(5, 40)
    n = rng.integers(2, 40, S)
    vals = [rng.standard_t(3, k) * 0.05 + rng.normal(0, 0.02) for k in n]
    k = np.array([rng.integers(0, m + 1) for m in n])
    nF = k.sum()
    var = 0.0
    for v, m, kk in zip(vals, n, k):
        if 0 < kk < m:
            var += kk * (m - kk) / (m - 1) * v.var()
    exact = np.sqrt(var) / nF
    sims = []
    for _ in range(20000):
        g = 0.0
        for v, m, kk in zip(vals, n, k):
            if kk == 0:
                continue
            idx = rng.permutation(m)[:kk]
            g += kk * (v.mean() - v[idx].mean())
        sims.append(g / nF)
    sims = np.array(sims)
    print(f"trial {trial}: sessions {S}, attempts {n.sum()}, fills {nF}: exact sd {exact*1e4:.3f} bp, brute {sims.std()*1e4:.3f} bp, brute mean {sims.mean()*1e4:+.3f} bp")

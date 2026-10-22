#!/usr/bin/env python
"""rt_placebo.py (red team; SYNTHETIC ONLY: no lane data, no market data, no outcome of any event is read).

THE PLACEBO AUDIT (K = 8) AND THE CONTROL CANARY (K = 100: the pool's own record screened; it reads as 8 when it passes): P = 8 free placebo records over one POOL (a family's control set, or the price lane's universe):
placebo j takes K = 8 events of the pool each session by a fixed hash (zero skill), and is judged by the same screen as
a seatable version (rt_meta.screen: EVL-6's leading candidate as calib_learner.py states it, no control). The House
counts placebo passes by pick block 30. The audit ALARMS when >= k* of the 8 pass; k* is set so that the alarm's false
rate is <= 5% at the worst plausible honest pool (EVL-6's set: residual day shock 0.5%, t(3), crash days, a persistent
family drift AR(0.97) sd 20 bp). Its POWER is the alarm rate when the pool's mean abnormal return is NOT zero because
the pool is dishonest: look-ahead or survivorship in the universe, a cost basis set too low, or a data leak that lifts
every event of the pool by +delta (20, 30, 50 bp).
Pool events per session n = 100 (one per issuer), each a = delta + D_t + c_t + s_i e_i (s_i log-uniform 1.5%-6%, t(3));
crash days: 5% of sessions c_t ~ N(-3, 1) x 0.5% sd units. r = a + m_t (m_t ~ N(4 bp, 1.2%)). 4,000 replicates a cell.
"""
import json, math, sys
import numpy as np
from rt_meta import screen, unit_t

P, K, N, T = 8, 8, 100, 30


def rep(rng, delta, drift_sd, crash, K=K):
    D = np.zeros(T)
    D[0] = rng.normal(0, drift_sd) if drift_sd else 0.0
    for t in range(1, T):
        D[t] = 0.97 * D[t - 1] + (math.sqrt(1 - 0.97 ** 2) * rng.normal(0, drift_sd) if drift_sd else 0.0)
    if crash:
        z = np.where(rng.random(T) < 0.05, rng.normal(-3, 1, T), rng.normal(0.158, 0.55, T))
        z = (z - z.mean()) / max(z.std(), 1e-9) if False else z
        c = 0.005 * z
    else:
        c = 0.005 * unit_t(rng, 3, T)
    m = 0.0004 + 0.012 * rng.standard_normal(T)
    s = np.exp(rng.uniform(math.log(0.015), math.log(0.06), (T, N)))
    a = delta + D[:, None] + c[:, None] + s * unit_t(rng, 3, (T, N))
    r = a + m[:, None]
    passes = 0
    for j in range(P):
        if K >= N:      # the pool itself: one record (the control canary); the same for every j
            passes += P * screen(a.mean(1), r.mean(1))[0]
            break
        idx = np.argsort(rng.random((T, N)), axis=1)[:, :K]
        ab = np.take_along_axis(a, idx, 1).mean(1)
        rb = np.take_along_axis(r, idx, 1).mean(1)
        passes += screen(ab, rb)[0]
    return passes


def cell(delta, drift_sd, crash, reps, seed, K=K):
    rng = np.random.default_rng(seed)
    counts = np.array([rep(rng, delta, drift_sd, crash, K) for _ in range(reps)])
    return {f">={k}": float((counts >= k).mean()) for k in range(1, P + 1)} | {"mean_single": float(counts.mean() / P)}


if __name__ == "__main__":
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    from multiprocessing import Pool
    cells = [(0.0, 0.0, False), (0.0, 0.0010, True), (0.0, 0.0020, True), (0.0, 0.0020, False),
             (0.0020, 0.0, False), (0.0030, 0.0, False), (0.0050, 0.0, False),
             (0.0030, 0.0020, True), (0.0050, 0.0020, True)]
    with Pool(4) as pool:
        jobs = [(d, s, c, reps, 300 + i + 100 * kk, kv) for kk, kv in enumerate((8, 100)) for i, (d, s, c) in enumerate(cells)]
        res = pool.starmap(cell, jobs)
    rows = []
    for (d, s, c, _, _, kv), r in zip(jobs, res):
        rows.append(dict(K=kv, delta_bp=d * 1e4, drift_bp=s * 1e4, crash=c, **r))
        print(f"K={kv:3d} delta {d*1e4:+3.0f} bp drift {s*1e4:2.0f} bp crash {c!s:5s} | single placebo pass {r['mean_single']:.3f} | "
              + " ".join(f"P(>={k}) {r[f'>={k}']:.3f}" for k in range(1, 6)))
    json.dump(dict(reps=reps, rows=rows), open(__file__.replace(".py", ".out.json"), "w"), indent=1)

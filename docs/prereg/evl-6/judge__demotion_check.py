"""PREREG-EVL-6 section 3's demotion check (synthetic only): PREREG-EVL-3's rolling "last 100 Probe+ events negative
mean" against fixed reads at the 100th, 200th, ... event. Events: r = edge + a session's market move (N(4 bp, 1%),
shared by the session's 6 Probe events) + t(3) noise of sd 5.3%. 20,000 paths, seed 1."""
import numpy as np
rng = np.random.default_rng(1)
R = 20000
for edge in (0.006, 0.010, 0.0):
    out = {}
    for N in (150, 300, 500):
        sess = rng.normal(0.0004, 0.01, (R, N // 6 + 1))
        r = edge + np.repeat(sess, 6, axis=1)[:, :N] + 0.053 * rng.standard_t(3, (R, N)) / np.sqrt(3)
        c = np.cumsum(r, axis=1)
        roll = (c[:, 99:] - np.concatenate([np.zeros((R, 1)), c[:, :-100]], axis=1)[:, :c.shape[1] - 99]) / 100
        dem = (roll < 0).any(axis=1)
        fixed = np.zeros(R, bool)
        for k in range(100, N + 1, 100):
            fixed |= c[:, k - 1] / k < 0
        out[N] = (round(float(dem.mean()), 3), round(float(fixed.mean()), 3))
    print(f"edge {edge * 1e4:.0f} bp: P(demoted within N Probe events) (rolling, fixed reads):", out)

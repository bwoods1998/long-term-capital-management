"""CHECK #1 (synthetic only): an alternative fixed read. At the stay's 100th, 200th, ... Probe+ event, demote when the
one-sided session-block sign-flip p for mean r < 0 over the stay's Probe+ events so far is <= ALPHA (blocks = entry
sessions, 6 Probe events a session). p by the self-normalized normal approximation (17+ blocks at the first read).
Same generator as demotion_c1.py."""
import math, numpy as np
from demotion_c1 import V0
def run(edge, rho, alpha, drift_sd=0.0, R=20000, N=1000, per=6, seed=7):
    rng = np.random.default_rng(seed)
    T = N // per + 1
    sd_c = math.sqrt(rho / (1 - rho) * V0) if rho > 0 else 0.0
    z = rng.standard_t(3, R) / math.sqrt(3); D = rng.standard_normal(R) * drift_sd; lv = rng.standard_normal(R) * 0.3
    sess = np.empty((R, T))
    for t in range(T):
        z = 0.10 * z + math.sqrt(1 - 0.01) * rng.standard_t(3, R) / math.sqrt(3)
        D = 0.97 * D + math.sqrt(1 - 0.97 ** 2) * drift_sd * rng.standard_normal(R)
        lv = 0.9 * lv + math.sqrt(1 - 0.81) * 0.3 * rng.standard_normal(R)
        sess[:, t] = edge + D + rng.normal(0.0004, 0.01, R) + np.exp(lv - 0.09) * sd_c * z
    sig = np.exp(rng.uniform(math.log(0.01), math.log(0.10), (R, T, per)))
    e = sig * rng.standard_t(3, (R, T, per)) / math.sqrt(3)
    hit = rng.random((R, T, per)) < 0.005
    e = e + hit * np.where(rng.random((R, T, per)) < 0.5, -0.3, 0.3)
    B = sess + e.mean(axis=2)            # block value: the session's mean r over its 6 Probe events
    zc = -1.0 * abs(__import__("statistics").NormalDist().inv_cdf(alpha))
    dem = np.zeros(R, bool); out = {}
    for k in range(100, N + 1, 100):
        S = k // per
        x = B[:, :S]
        zz = x.sum(axis=1) / np.sqrt((x * x).sum(axis=1))
        dem |= zz <= zc
        if k in (100, 300, 500, 1000):
            out[k] = round(float(dem.mean()), 3)
    return out
if __name__ == "__main__":
    for alpha in (0.10, 0.20):
        for rho in (0.05, 0.15):
            for edge in (0.006, 0.0, -0.0015):
                print(f"alpha {alpha} rho {rho:.2f} edge {edge*1e4:4.0f} bp: P(demoted by k) {run(edge, rho, alpha)}", flush=True)

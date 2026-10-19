"""PREREG-EVL-4 calibration, every look reachable (synthetic only): calib_evl4.py's model with the horizon raised from
400 to 1200 sessions, zero edge, seed 41, mean rates 2 and 5 events a session. Run: <python with numpy>
calib_evl4_horizon.py (output: calib_evl4_horizon.out)."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evl-3"))
import calibrate_events as C  # noqa: E402

NS = [60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250]
ALPHA = 0.018


def run(alpha, reps, rate_mu, edge=0.0, seed=0, idio=0.03, df=4, ns=NS, min_blocks=8, B=999, S_max=1200):
    r = np.random.default_rng(seed)
    flips = r.choice([-1.0, 1.0], size=(B, S_max))
    passed, first = 0, []
    for _ in range(reps):
        rate = max(0.3, r.gamma(2.0, rate_mu / 2.0))
        n_per = r.poisson(rate, S_max)
        common = r.standard_t(df, S_max) * 0.004
        idv = np.array([r.standard_t(df, k).sum() * idio / max(k, 1) if k else 0.0 for k in n_per])
        means = np.where(n_per > 0, common + idv + edge, np.nan)
        cum_n = np.cumsum(n_per)
        blocks = np.cumsum(n_per > 0)
        for N_k in ns:
            idx = np.where((cum_n >= N_k) & (blocks >= min_blocks))[0]
            if not len(idx):
                break
            s = idx[0] + 1
            x = means[:s][~np.isnan(means[:s])]
            if x.mean() > 0 and C.signflip_p(x, flips) <= alpha:
                passed += 1
                first.append(s)
                break
    return round(passed / reps, 4), (int(np.median(first)) if first else None)


if __name__ == "__main__":
    out = {"alpha": ALPHA, "looks": NS, "min_blocks": 8, "S_max": 1200, "fp": {}}
    for mu in (2.0, 5.0):
        out["fp"][mu] = run(ALPHA, 4000, mu, seed=41)
    print(json.dumps(out))

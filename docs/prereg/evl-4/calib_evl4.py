"""PREREG-EVL-4 calibration (synthetic only, no market data): PREREG-EVL-3's model and pinned schedule
(prereg/evl-3/calibrate_events.py: alpha 0.018 a look, looks at 60..2250 settled events, >= 8 session blocks), run at
PREREG-EVL-4's expected event rates. Zero-edge false-pass rate at mean rates of 5, 19 and 25 events a session
(seed 41; seed 42 with 5% per-event noise), and power at edges of 0.2%, 0.4% and 0.8% an event (seed 43). Per-event
noise 3% t(4) and a per-session residual common shock 0.4% t(4), as PREREG-EVL-3. Session-block test alone.
Run: <python with numpy> calib_evl4.py  (output: calib_evl4.out)."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evl-3"))
import calibrate_events as C  # noqa: E402  PREREG-EVL-3's module: its signflip_p

NS = [60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250]
ALPHA = 0.018


def run(alpha, reps, rate_mu, edge=0.0, seed=0, idio=0.03, df=4, ns=NS, min_blocks=8, B=999):
    r = np.random.default_rng(seed)
    flips = r.choice([-1.0, 1.0], size=(B, 400))
    passed, first = 0, []
    for _ in range(reps):
        rate = max(0.3, r.gamma(2.0, rate_mu / 2.0))
        S_max = 400
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
    out = {"alpha": ALPHA, "looks": NS, "min_blocks": 8, "fp": {}, "fp_idio5": {}, "power": {}}
    for mu in (5.0, 19.0, 25.0):
        out["fp"][mu] = run(ALPHA, 4000, mu, seed=41)
    out["fp_idio5"][5.0] = run(ALPHA, 4000, 5.0, seed=42, idio=0.05)
    for mu in (5.0, 19.0, 25.0):
        for e in (0.002, 0.004, 0.008):
            out["power"][f"{mu}@{e}"] = run(ALPHA, 1500, mu, edge=e, seed=43)
    print(json.dumps(out))

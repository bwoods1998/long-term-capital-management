"""PREREG-EVL-5 calibration (synthetic only, no market data): PREREG-EVL-4's calib_evl4.py model and PREREG-EVL-3's pinned
schedule (alpha 0.018 a look, looks at 60..2250 settled events, >= 8 session blocks), run at PREREG-EVL-5's expected
event rates. Zero-edge false-pass rate within 400 sessions at mean rates of 3, 6 and 12 events a session (seed 51), with
5% per-event noise at 6 (seed 52: EVL-ERN-DROP-ON's heavier per-event noise), and with every look reachable (a 1200-session
horizon) at 6 (seed 54); power at edges of 0.2%, 0.4% and 0.8% an event at 6 and 12 (seed 53). Per-event noise 3% t(4) and
a per-session residual common shock 0.4% t(4), as PREREG-EVL-3 and -4. Session-block test alone.
Run: <python with numpy> calib_evl5.py [part]  (output: calib_evl5.out)."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evl-3"))
import calibrate_events as C  # noqa: E402  PREREG-EVL-3's module: its signflip_p

NS = [60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250]
ALPHA = 0.018


def run(alpha, reps, rate_mu, edge=0.0, seed=0, idio=0.03, df=4, ns=NS, min_blocks=8, B=999, S_max=400):
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


PARTS = {
    "fp3": lambda: ("fp", 3.0, run(ALPHA, 4000, 3.0, seed=51)),
    "fp6": lambda: ("fp", 6.0, run(ALPHA, 4000, 6.0, seed=51)),
    "fp12": lambda: ("fp", 12.0, run(ALPHA, 4000, 12.0, seed=51)),
    "fp6_idio5": lambda: ("fp_idio5", 6.0, run(ALPHA, 4000, 6.0, seed=52, idio=0.05)),
    "fp6_h1200": lambda: ("fp_horizon1200", 6.0, run(ALPHA, 4000, 6.0, seed=54, S_max=1200)),
    **{f"pw{mu:g}_{e}": (lambda mu=mu, e=e: ("power", f"{mu}@{e}", run(ALPHA, 1500, mu, edge=e, seed=53)))
       for mu in (6.0, 12.0) for e in (0.002, 0.004, 0.008)},
}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        kind, key, val = PARTS[sys.argv[1]]()
        print(json.dumps({"part": sys.argv[1], "kind": kind, "key": key, "value": val}))
    else:
        out = {"alpha": ALPHA, "looks": NS, "min_blocks": 8, "fp": {}, "fp_idio5": {}, "fp_horizon1200": {}, "power": {}}
        for name, f in PARTS.items():
            kind, key, val = f()
            out[kind][key] = val
        print(json.dumps(out))

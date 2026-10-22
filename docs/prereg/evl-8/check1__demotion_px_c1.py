#!/usr/bin/env python
"""demotion_px_c1.py: ADVERSARIAL CHECK #1 of PREREG-EVL-8: the PX seats' inherited DEMOTION (PREREG-EVL-6 draft
section 3, copied word for word by THE PX SCREEN): "THE STAY'S FIXED READS: at the stay's 100th, 200th, ... settled
real-money event at Probe size or above, the mean after-cost r of those events is below zero" -> demote. SYNTHETIC ONLY.

A promoted PX seat with a REAL judged edge (mu after cost) buys its first m events a session (m = 14, A99's Probe room,
or 6) in its ranking order; each holds one session; r = a + m_t (raw, the benchmark's own move included), from the PX
designer's generator (../price/px_calib.py `generate`, unchanged) at its base / mid / worst cells. P(demoted by the
k-th Probe event) for k = 100 ... 1000, cumulative over the stay (the reading EVL-6's check 1 measured). The money stop
($150 over the last 50) and the stay's lower tail would only add demotions. Seeds 64,000,001 on.
Usage: demotion_px_c1.py [--R 4000]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "price")))
import px_calib as PX  # noqa: E402

READS = (100, 200, 300, 500, 1000)


def run(noise, mu, m, R, seed):
    rng = np.random.default_rng(seed)
    dem = {k: 0 for k in READS}
    done = 0
    while done < R:
        b = min(200, R - done)
        g = PX.generate(rng, b, 40, PX.NOISE[noise], mu, 0.0, 40)
        valid, r = g["valid"], g["r"]
        for i in range(b):
            ev = []
            for t in range(PX.T):
                rv = r[i, t][valid[i, t]][:m]
                ev.extend(rv.tolist())
                if len(ev) >= READS[-1]:
                    break
            c = np.cumsum(ev)
            hit = False
            for k in range(100, min(len(ev), READS[-1]) + 1, 100):
                hit = hit or (c[k - 1] / k < 0)
                if k in dem and hit:
                    dem[k] += 1
            # a path that stopped short of a read keeps its last state for the later reads
            last = max([k for k in range(100, min(len(ev), READS[-1]) + 1, 100)] or [0])
            for k in READS:
                if k > last and hit:
                    dem[k] += 1
        done += b
    return {k: round(v / R, 3) for k, v in dem.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--R", type=int, default=4000)
    a = ap.parse_args()
    seed = 64_000_001
    for noise in ("base", "mid", "worst"):
        for mu in (0.0040, 0.0060, 0.0100):
            for m in (14, 6):
                res = run(noise, mu, m, a.R, seed)
                seed += 1
                print(json.dumps({"noise": noise, "edge_bp": mu * 1e4, "probe_events_a_session": m, "R": a.R,
                                  "P_demoted_by_kth_probe_event": res}), flush=True)


if __name__ == "__main__":
    main()

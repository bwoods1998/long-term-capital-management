#!/usr/bin/env python
"""check1_guard.py (EVL-9 adversarial check #1, statistics): does the SHAPE GUARD as registered (section 2.3 (iii):
sig20 >= 0.015, sig20 the sd of the 19 daily close-to-close log changes before D) bound what the red team calibrated
(redteam/rt_skew.py: the HOLD-PERIOD abnormal sigma of the picked event)?

SYNTHETIC ONLY: arithmetic on stated assumptions and the red team's generator (imported unchanged), screened by
PREREG-EVL-6's final rule (judge/calib_evl9_final.run_f, via judge/rt_skew_final.gen). No price, bar or return of any
real symbol is read.

PART 1 (arithmetic): the hold sigma the guard admits at its boundary sig20 = 1.5%,
  * EVL-WL-ON holds close -> next open: hold sigma = sqrt(f) x sig20, f the overnight share of close-to-close variance;
  * EVL-WL-O1 holds open -> close: hold sigma = sqrt(1 - f) x sig20;
  * abnormal (minus the benchmark): subtract beta^2 x the benchmark's variance over the same leg (sm = 1.0% a day);
  * a jump inside the 20-close window: one log change of ln(1.25) among 19, the other 18 N(0, 0.4%) (a name that
    re-priced on news and then sits still): sig20 vs the same with the largest |change| removed.
PART 2 (simulation): the red team's steamroller cells (every event's mean a exactly 0) at the hold sigmas the guard
admits, screened by the final rule, run 1 within 120 sessions.
Usage: check1_guard.py [--reps 1500] [--workers 4]
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "redteam"))
import rt_skew_final as rf  # noqa: E402
import calib_evl9_final as cf  # noqa: E402


def part1():
    out = {}
    s20 = 0.015
    rows = []
    for f in (0.15, 0.20, 0.30, 0.40, 0.50):
        on = math.sqrt(f) * s20
        o1 = math.sqrt(1 - f) * s20
        # abnormal: the benchmark's leg variance splits the same way (beta 1, sm 1.0% a day)
        sm = 0.010
        on_ab = math.sqrt(max(f * (s20 ** 2 - sm ** 2), 0.0))
        o1_ab = math.sqrt(max((1 - f) * (s20 ** 2 - sm ** 2), 0.0))
        rows.append(dict(f=f, on_hold=round(on, 5), o1_hold=round(o1, 5), on_abn_beta1=round(on_ab, 5),
                         o1_abn_beta1=round(o1_ab, 5)))
    out["admitted_hold_sigma_at_sig20_1.5pct"] = rows
    rng = np.random.default_rng(303_000_001)
    full, rob, full0 = [], [], []
    for _ in range(2000):
        ch = rng.normal(0, 0.004, 18)
        ch = np.concatenate([[math.log(1.25)], ch])
        full.append(float(np.std(ch, ddof=1)))
        full0.append(float(np.std(ch, ddof=0)))
        k = int(np.argmax(np.abs(ch)))
        rob.append(float(np.std(np.delete(ch, k), ddof=1)))
    out["jump_window"] = dict(sig20_ddof1_mean=round(float(np.mean(full)), 5), sig20_ddof0_mean=round(float(np.mean(full0)), 5),
                              robust_drop_largest_mean=round(float(np.mean(rob)), 5),
                              sessions_inflated=19, true_daily_sigma=0.004)
    return out


CELLS = [
    dict(name="STEAM-sig0.5to0.8-j1pct", left=1.0, right=1.0, pj=0.010, J=0.30, q=0.0, sig=(0.005, 0.008)),
    dict(name="STEAM-sig0.5to0.8-j0.5pct", left=1.0, right=1.0, pj=0.005, J=0.30, q=0.0, sig=(0.005, 0.008)),
    dict(name="STEAM-sig0.8to1.1-j1pct", left=1.0, right=1.0, pj=0.010, J=0.30, q=0.0, sig=(0.008, 0.011)),
    dict(name="STEAM-sig0.8to1.1-j0.5pct", left=1.0, right=1.0, pj=0.005, J=0.30, q=0.0, sig=(0.008, 0.011)),
    dict(name="STEAM-sig1.1to1.4-j1pct", left=1.0, right=1.0, pj=0.010, J=0.30, q=0.0, sig=(0.011, 0.014)),
    dict(name="STEAM-sig0.5to0.8-j0.3pct", left=1.0, right=1.0, pj=0.003, J=0.30, q=0.0, sig=(0.005, 0.008)),
    dict(name="MIX50-STEAM-sig0.5to0.8-j1pct", left=1.0, right=1.0, pj=0.010, J=0.30, q=0.0, sig=(0.005, 0.008), mix=0.50),
    dict(name="STEAM-sig1.5to2.5-j1pct-repro", left=1.0, right=1.0, pj=0.010, J=0.30, q=0.0, sig=(0.015, 0.025)),
]


def _cell(args):
    i, c, reps = args
    sim = rf.gen(c, reps, 303_100_001 + i)
    ps = [cf.run_f(sim, r, 0)[0] == "pass" for r in range(reps)]
    p = float(np.mean(ps))
    return dict(cell=c["name"], reps=reps, ev6f_run1_pass=round(p, 4), se=round(math.sqrt(p * (1 - p) / reps), 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    p1 = part1()
    print(json.dumps(p1, indent=1), flush=True)
    from multiprocessing import Pool
    with Pool(min(4, a.workers)) as pool:
        rows = list(pool.imap(_cell, [(i, c, a.reps) for i, c in enumerate(CELLS)]))
    for r in rows:
        print(json.dumps(r), flush=True)
    with open(os.path.join(HERE, "check1_guard.out.json"), "w") as fh:
        json.dump(dict(part1=p1, part2=rows), fh, indent=1)


if __name__ == "__main__":
    main()

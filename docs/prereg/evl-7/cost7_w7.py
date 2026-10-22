#!/usr/bin/env python
"""cost7_w7.py: COST-7's round trip with E9's impact sigma (sig20, floored at 0.02, capped at 0.25), against the
replay's (score.py cost_bp), at three equities. Arithmetic only: no lane data, no price of any event.

(1) THE TABLE: calib/cost7_today.py's grid and formulas (imported unchanged) at sigma 0.02, 0.04, 0.06, 0.08 and 0.10
    (the learner's picks in the generator carry a mean sigma of about 0.05-0.065: calib_w7.py's 'sig' column), the
    replay minus COST-7 by liquidity, and the impact at Sized size that a flat 0.04 (the NULL sigma60 the draft read)
    would under-charge.
(2) THE GENERATOR'S PICKS: on calib_w7.py's base and worst cells (200 programs each, seeds 207,000,001+), the mean
    replay and COST-7 round trips of the learner's picks and of its pool, from each replicate's own issuers (drawn first
    from the replicate's seed, as calib_evl7.py's _delta does).
Usage: cost7_w7.py
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(os.path.dirname(HERE), "calib")):
    if os.path.exists(os.path.join(_p, "cost7_today.py")):
        sys.path.insert(0, _p)
        break
import cost7_today as c7t  # noqa: E402
import calib_w7 as w  # noqa: E402

SIGMAS = (0.02, 0.04, 0.06, 0.08, 0.10)


def table():
    for E in (1898.0, 5000.0, 30000.0):
        tradable = [p for p in c7t.PRICES if 1.25 * p <= 0.10 * E]
        print(f"E = ${E:,.0f}: replay round trip {c7t.replay_rt(2e7, E):.1f} bp (ADV >= $10M), "
              f"{c7t.replay_rt(5e6, E):.1f} bp (thinner)")
        for s in SIGMAS:
            parts = []
            for label, sel in (("ADV >= $10M", [a for a in c7t.ADVS if a >= 1e7]),
                               ("ADV < $10M", [a for a in c7t.ADVS if a < 1e7])):
                d = [c7t.replay_rt(a, E) - c7t.cost7_rt(p, a, s, E) for p in tradable for a in sel]
                parts.append(f"{label}: mean {sum(d) / len(d):+.1f} bp ({min(d):+.1f} to {max(d):+.1f})")
            print(f"   sigma {s:.2f}: replay minus COST-7, " + "; ".join(parts))
    for E in (1898.0, 30000.0):
        for adv in (1.5e6, 3e6, 1e7):
            for s in (0.06, 0.08, 0.10):
                imp4 = 1e4 * 0.04 * math.sqrt(0.10 * E / adv)
                imp = 1e4 * s * math.sqrt(0.10 * E / adv)
                print(f"E ${E:,.0f} ADV ${adv / 1e6:.1f}M sigma {s:.2f}: IMP a side {imp:.1f} bp (a flat 0.04 charges "
                      f"{imp4:.1f}: {2 * (imp - imp4):.1f} bp a round trip less)")


def picks():
    cells = [w.corner("t3", 0.10, 0.0, 2, rho=0.05, skew=False, tau=0.0),
             w.corner("crasht3cl", 0.20, 0.0020, 2), w.corner("crasht3cl", 0.20, 0.0020, 1, pool=800)]
    for ci, (cell, x7) in enumerate(cells):
        seed = 207_000_001 + 1000 * ci
        R = 200
        sim = w.simulate7(cell, x7, seed, R)
        iss = w.issuers7(np.random.default_rng(seed), R, cell, x7)
        ids = np.where(sim["iss"] >= 0, sim["iss"], 0)
        ok = sim["iss"] >= 0
        rr = np.arange(R)[:, None, None]
        crep = iss["c_rep"][rr, ids][ok]
        cc7 = iss["c7"][rr, ids][ok]
        sg = sim["sig"][ok]
        print(f"{cell.name}: picks {ok.sum()}: replay {crep.mean() * 1e4:.1f} bp, COST-7 {cc7.mean() * 1e4:.1f} bp, "
              f"replay minus COST-7 {np.mean(crep - cc7) * 1e4:+.1f} bp, sigma {sg.mean():.3f}; issuers' unweighted: "
              f"replay {iss['c_rep'].mean() * 1e4:.1f} bp, COST-7 {iss['c7'].mean() * 1e4:.1f} bp")


if __name__ == "__main__":
    table()
    picks()

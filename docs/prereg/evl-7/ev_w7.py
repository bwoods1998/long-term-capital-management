#!/usr/bin/env python
"""ev_w7.py: the expected value of PREREG-EVL-7's learners under STATED scenarios (synthetic; no lane data).

It reads calib_w7.py's power cells (w7.power.jsonl: the learner lens's generator with E7's gross label, PREREG-EVL-6's
FROZEN screen on a7, COST-7 with E9's sigma) and turns each scenario's promotion curve and the picks' true edge into
dollars and Probe events, per learner, over 120 sessions. The method and constants are the judge's (calib/ev_evl7.py),
unchanged: E = $1,898; a learning lot 2% of E; a Probe lot 0.9 x 3.5% of E; 7.9 picks a session; real money buys a
share F_L of a learner's picks at learning (0.25 crowded / 0.50 open) and F_P = 0.75 at Probe; each real pick earns the
picks' TRUE expected replay a of its session decile (calib_w7.py's edgerep: the gross mean less the replay's cost) PLUS
GAP = 8 bp (the replay's overcharge less the real fees at learning size, conservative); a promoted version stays at
Probe; abnormal return only.
THE NULL LINE (E11, check 2's text and its method, check2/check2_cost.py): under the fixed level's own prior (the pool's
GROSS abnormal mean 0), a zero-information pick's replay a is minus the replay's round trip, so it earns -cost + GAP.
Usage: ev_w7.py
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
E = 1898.0
LOT_L = 0.02 * E
LOT_P = 0.9 * 0.035 * E
PICKS = 7.9
F_P = 0.75
GAP = 0.0008
T = 120


def replay_rt(adv, E_):
    n = 0.05 * E_
    return 2 * (0.5 + (5.0 if adv >= 1e7 else 10.0)) + (0.01 / n + 0.02 / n) * 1e4


def load():
    by = {}
    for line in open(os.path.join(HERE, "w7.power.jsonl")):
        r = json.loads(line)
        by.setdefault(r["cell"], []).append(r)
    return by


def curve(parts, basis, version):
    key = "frozen_" + basis
    wh = np.concatenate([p[key]["when"] for p in parts])
    rn = np.concatenate([p[key]["run"] for p in parts])
    ok = (wh >= 0) if version else ((wh >= 0) & (rn == 1))
    return np.array([(ok & (wh < t)).mean() for t in range(T)])


def edge(parts, key):
    ce = parts[0][key]
    out = np.zeros(T)
    for k in ce:
        lo, hi = (int(x) for x in k.split("-"))
        if lo > T:
            continue
        v = [p[key][k] for p in parts if k in p[key] and p[key][k] == p[key][k]]
        out[lo - 1:min(hi, T)] = (np.mean(v) if v else 0.0) / 1e4
    return out


def main():
    by = load()
    print("per learner, 120 sessions; $ = abnormal after real cost; Probe events = real buys at Probe size (Done's kind)")
    print(f"{'scenario':<52} {'screen':<14} {'by40':>6} {'by60':>6} {'by120':>6} {'$ F_L .25':>10} {'$ F_L .50':>10} "
          f"{'Probe ev':>9} {'E-cum 50':>9}")
    for cell, parts in sorted(by.items()):
        e = edge(parts, "edgerep_bp") + GAP
        for basis in ("a7", "arep"):
            if "frozen_" + basis not in parts[0]:
                continue
            for version in (False, True):
                P = curve(parts, basis, version)
                usd = {fl: float(np.sum((1 - P) * fl * PICKS * LOT_L * e + P * F_P * PICKS * LOT_P * e))
                       for fl in (0.25, 0.50)}
                cum = np.cumsum(P * F_P * PICKS)
                to50 = int(np.argmax(cum >= 50)) + 1 if cum[-1] >= 50 else None
                tag = ("COST-7 " if basis == "a7" else "replay ") + ("v<=120" if version else "run 1")
                print(f"{cell:<52} {tag:<14} {P[39]:>6.3f} {P[59]:>6.3f} {P[-1]:>6.3f} {usd[0.25]:>10.1f} "
                      f"{usd[0.50]:>10.1f} {float(cum[-1]):>9.0f} {str(to50):>9}")
        print(f"   picks' true replay a (bp) by decade: " + " ".join(f"{v * 1e4 - GAP * 1e4:.1f}" for v in e[::10])
              + f" | COST-7 / replay on the picks {np.mean([p['c7_picks_bp'] for p in parts]):.1f} / "
              f"{np.mean([p['crep_picks_bp'] for p in parts]):.1f} bp")
    for rt in (replay_rt(2e7, E), replay_rt(5e6, E)):
        per = -rt / 1e4 + GAP
        lo = 0.25 * PICKS * LOT_L * per * T
        hi = 0.50 * PICKS * LOT_L * per * T
        print(f"NULL (IC 0, the pool's gross mean 0), replay round trip {rt:.1f} bp: a pick earns {per * 1e4:+.1f} bp; "
              f"$ over {T} sessions per learner at learning: {lo:+.1f} (F_L .25) to {hi:+.1f} (F_L .50), plus a false "
              "promotion's Probe lots at the same rate, all inside the loss budget")


if __name__ == "__main__":
    main()

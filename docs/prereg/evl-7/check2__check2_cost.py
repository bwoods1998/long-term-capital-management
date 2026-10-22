#!/usr/bin/env python
"""check2_cost.py: arithmetic only (no lane data). (1) COST-7's round trip when sigma is the constant 0.04 that the
code would read (league/events/universe.py writes universe.sigma60 as NULL and nothing else writes it), against the
replay, at three equities; the impact a 4% constant under-charges for an 8%-sigma thin name at $30k. (2) The EV of a
zero-information learner under the draft's own prior (pool GROSS abnormal mean 0, so the picks' replay a = -replay
cost) with ev_evl7.py's own constants (GAP 8 bp, 7.9 picks, learning lot 2% of $1,898, F_L 0.25 / 0.50, 120 sessions)."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calib"))
import cost7_today as c7  # noqa: E402

for E in (1898.0, 5000.0, 30000.0):
    tradable = [p for p in c7.PRICES if 1.25 * p <= 0.10 * E]
    for label, sel in (("ADV >= $10M", [a for a in c7.ADVS if a >= 1e7]), ("ADV < $10M", [a for a in c7.ADVS if a < 1e7])):
        d = [c7.replay_rt(a, E) - c7.cost7_rt(p, a, 0.04, E) for p in tradable for a in sel]
        print(f"E ${E:,.0f} sigma 0.04 only: replay minus COST-7, {label}: mean {sum(d) / len(d):+.1f} bp, "
              f"range {min(d):+.1f} to {max(d):+.1f}")
for adv in (1.5e6, 3e6):
    imp4 = 1e4 * 0.04 * math.sqrt(0.10 * 30000 / adv)
    imp8 = 1e4 * 0.08 * math.sqrt(0.10 * 30000 / adv)
    print(f"E $30,000 ADV ${adv / 1e6:.1f}M: IMP a side at sigma 0.04 {imp4:.1f} bp, at sigma 0.08 {imp8:.1f} bp: "
          f"under-charge {imp8 - imp4:.1f} bp a side, {2 * (imp8 - imp4):.1f} bp a round trip")

E, PICKS, T, GAP = 1898.0, 7.9, 120, 0.0008
lot = 0.02 * E
for rt in (c7.replay_rt(2e7, E), c7.replay_rt(5e6, E)):
    per_pick = -rt / 1e4 + GAP
    lo = 0.25 * PICKS * lot * per_pick * T
    hi = 0.50 * PICKS * lot * per_pick * T
    print(f"IC 0, replay round trip {rt:.1f} bp: a pick earns {per_pick * 1e4:+.1f} bp; $ over {T} sessions per learner "
          f"at learning: {lo:+.1f} (F_L .25) to {hi:+.1f} (F_L .50)")

#!/usr/bin/env python
"""base_w9ff.py: THE BASE MODEL under the final minimal fix's rules (the two levels deleted, the 20-session spacing),
for section 10's three-way report. SYNTHETIC ONLY; nothing here reads the lane. It imports calib_w9ff.py (and through
it final/calib_w9.py) UNCHANGED and adds one grid, 'base': the frozen grid's base model (t(3) body, rho_day 0.05,
phi_day 0.10, symmetric events, no drift, no issuer effect) under the null, noise history (H0) and a decayed history
edge of 0.08 (HD08), EVL-WL-O1 at pools 300 and 600 and EVL-WL-ON at 300 and 800, 600 programs a cell, fresh seeds
868,000,001 + (never used by any earlier stage: a grep of goal-2026-10-19 finds no 868e6 base).
Usage: base_w9ff.py run | report   (writes ff.base.jsonl)"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w9ff as f  # noqa: E402

w = f.w
PB = dict(shape="t3", rho_day=0.05, phi_day=0.10, ev_skew=False, drift_sd=0.0, tau=0.0)
_grid = f.grid


def grid(name):
    if name != "base":
        return _grid(name)
    cells = []
    for L, pools in (("O1", (300.0, 600.0)), ("ON", (300.0, 800.0))):
        for n in pools:
            for ic_h in (0.0, 0.08):
                cells.append(w.mk(learner=L, ic_h=ic_h, nbar=n, **PB))
    return cells, 868_000_001


f.grid = grid

if __name__ == "__main__":
    if sys.argv[1] == "run":
        f.run("base", 8, reps=600)
    else:
        f.report("base")

#!/usr/bin/env python
"""px_supply.py: SCENARIO supply of the three PX seats a session, from universe counts and STATED distributional
assumptions only (no price, bar or return of any symbol is read). The House measures the true counts (outcome-free
counts of qualifying names) on its first decisions; these figures only size the calibration's lam cells.

Assumptions (stated, not measured): the vol-scaled abnormal move z of a PXU name over a window is unit-variance t(4);
the premarket indication's z is scaled by the name's OVERNIGHT sigma (sd of 60 bar-open over previous-close returns), so it is unit-variance t(4) too (the variance-0.4 line shows what a DAILY sigma60 would give); the no-news share
among |z| >= 2 movers is 0.3 or 0.6; SURGE's volume condition keeps 0.5 of its movers; GAP's universe (ADV20 >= $20M)
is 0.6 of PXU and 0.7 of it has >= 3 premarket minute bars."""
import math
import numpy as np
rng = np.random.default_rng(5)
z = rng.standard_t(4, 4_000_000) / math.sqrt(2.0)
p_lo = float(np.mean(z <= -2.0)); p_hi = float(np.mean(z >= 2.0))
zg = z * math.sqrt(0.4)
p_gap = float(np.mean(zg <= -2.0))
print(f"P(z <= -2) {p_lo:.4f}  P(z >= +2) {p_hi:.4f}  P(z_gap <= -2) {p_gap:.4f}")
for n in (1500, 2000, 3000):
    for nn in (0.3, 0.6):
        drop = n * p_lo * nn
        surge = n * p_hi * nn * 0.5
        gap_daily = n * 0.6 * 0.7 * p_gap * nn
        gap = n * 0.6 * 0.7 * p_lo * nn
        print(f"N_U={n} no-news {nn}: DROP-ON lam {drop:5.1f}  SURGE-ON lam {surge:5.1f}  GAP-O1 lam {gap:5.1f} "
              f"(with a daily sigma60: {gap_daily:4.1f})  (cap 20 each)")

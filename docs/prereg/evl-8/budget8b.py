#!/usr/bin/env python
"""budget8b.py: the lane's expected-false-pass count after PREREG-EVL-8 (the captain's F12), ARITHMETIC ONLY, on
PREREG-EVL-6's frozen basis (section 5: 0.13 a seatable version or a run when it starts, a lifetime budget of 3.9,
R3's validator reading the SEATING sum of every seatable version and run of every file, registration order when the
budget cannot hold every draw). FINAL FIX (re-check 1's major 2): the meta-learners' charge is
c_meta = max(0.13, their worst plausible per-run false-pass rate TO THE RUN'S END rounded up to 0.01), read from
meta8l.life.jsonl and meta8l.ext.jsonl (meta_life8.py: run 1's pass share by the last session measured, each cell at its
longest horizon, at the plausible L- cells; the stress S- cells are printed beside and never charged); the PX seats' charge is max(0.13, 0.12) = 0.13 (section 6.2).
A117's PREREG-EVL-9 seats (two, 0.13 each) are counted when that file registers first. Nothing here reads the lane."""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CHARGE, BUDGET = 0.13, 3.9


def up(x):
    return math.ceil(round(x * 100, 6)) / 100


rows = [json.loads(line) for line in open(os.path.join(HERE, "meta8l.life.jsonl"))]
ext = os.path.join(HERE, "meta8l.ext.jsonl")
rows += [json.loads(line) for line in open(ext)] if os.path.exists(ext) else []
# a cell measured to two horizons (the main phase's 2,500 and the extension's 4,000, on their own seeds) is read at its
# LONGER one, the nearer to the run's end; the shorter is printed above it
base = lambda r: r["cell"].rsplit("-T", 1)[0]
longest = {}
for r in rows:
    if base(r) not in longest or r["T"] > longest[base(r)]["T"]:
        longest[base(r)] = r
plaus = [r for r in longest.values() if r["cell"].startswith("L-")]
stress = [r for r in longest.values() if r["cell"].startswith("S-")]
print("THE META-LEARNERS PER RUN TO THE RUN'S END (meta8l.life.jsonl; CAP 8, CAP 4 beside):")
for r in rows:
    c8, c4 = r["cap8"], r["cap4"]
    print(f"  {r['cell']:58s} R {r['R']:4d} run 1 by T {c8['run1_by_T']:.4f} +- {c8['run1_by_T_se']:.4f} (CAP 4 "
          f"{c4['run1_by_T']:.4f}); ended {c8['run1_ended_share']:.3f}; upper (open counted as passes) "
          f"{c8['run1_to_end_upper']:.4f}")
# THE META SEATS' CAP IS 8 (F4: PREREG-EVL-3's learning band; section 5.2): the charge reads CAP 8; CAP 4 is printed beside
w8 = max(plaus, key=lambda r: r["cap8"]["run1_by_T"])
worst = w8["cap8"]["run1_by_T"]
w4 = max(plaus, key=lambda r: r["cap4"]["run1_by_T"])
c_meta = max(CHARGE, up(worst))
ws = max(stress, key=lambda r: r["cap8"]["run1_by_T"]) if stress else None
print(f"WORST PLAUSIBLE per run to the run's end: {worst:.4f} at {w8['cell']} (CAP 8 {w8['cap8']['run1_by_T']:.4f}, "
      f"CAP 4 {w8['cap4']['run1_by_T']:.4f}; ended {w8['cap8']['run1_ended_share']:.3f}) -> rounded up {up(worst):.2f}; "
      f"c_meta = max({CHARGE}, {up(worst):.2f}) = {c_meta:.2f}")
print(f"  (CAP 4 beside, never the META seats' rule: worst {w4['cap4']['run1_by_T']:.4f} at {w4['cell']})")
allp = [r for r in rows if r["cell"].startswith("L-")]
wa = max(allp, key=lambda r: r["cap8"]["run1_by_T"])
print(f"  ROBUSTNESS: the largest run-1 figure of ANY plausible cell on ANY seed set at ANY horizon measured is "
      f"{wa['cap8']['run1_by_T']:.4f} ({wa['cell']}, {wa['cap8']['run1_ended_share']:.2f} of runs ended), rounded up "
      f"{up(wa['cap8']['run1_by_T']):.2f}: max({CHARGE}, {up(wa['cap8']['run1_by_T']):.2f}) = "
      f"{max(CHARGE, up(wa['cap8']['run1_by_T'])):.2f} too")
if ws:
    print(f"worst STRESS (never charged): {ws['cap8']['run1_by_T']:.4f} at {ws['cell']}")
evl6 = 15 * CHARGE
c7 = 0.13
evl7_reg = 2 * c7
evl8_reg = 3 * CHARGE + 2 * c_meta
evl9_reg = 2 * CHARGE
a104 = 3 * CHARGE
print(f"\nPREREG-EVL-6 at REGISTERED_AT_6: 15 x {CHARGE} = {evl6:.2f} (+ {CHARGE} per seatable birth registered before it)")
print(f"PREREG-EVL-7 at its registration: 2 x c7 = {evl7_reg:.2f} (c7 = {c7}, its text)")
print(f"PREREG-EVL-8 at its registration: 3 PX x {CHARGE} + 2 META x {c_meta:.2f} = {evl8_reg:.2f}; every later run "
      f"charged when it starts ({CHARGE} a PX run, {c_meta:.2f} a META run)")
print(f"PREREG-EVL-9 (A117's plan) if it registers first: 2 x {CHARGE} = {evl9_reg:.2f}")
print(f"A104's three day-news births, if registered: {a104:.2f}")
for name, used in (("PREREG-EVL-6, -7 and -8, no birth", evl6 + evl7_reg + evl8_reg),
                   ("PREREG-EVL-6, -7, -8 and A117's -9, no birth", evl6 + evl7_reg + evl8_reg + evl9_reg),
                   ("those four files and A104's three births", evl6 + evl7_reg + evl8_reg + evl9_reg + a104)):
    left = BUDGET - used
    print(f"USED after {name}: {used:.2f} of {BUDGET}; LEFT {left:.2f} = {math.floor(round(left / CHARGE, 6))} charges of "
          f"{CHARGE}")
print(f"if none of PREREG-EVL-6's fifteen passes, their second runs alone need 15 x {CHARGE} = {15 * CHARGE:.2f}, more "
      f"than is left in every line above: they start first (registration order), and this file's second runs start only "
      f"if room is left after them")
print(f"this file's lifetime draw if every one of its five versions ran two runs: {2 * evl8_reg:.2f}; three: "
      f"{3 * evl8_reg:.2f}")
print(f"THE FIVE SEATS' FIRST RUNS on the charge basis: {evl8_reg:.2f}")

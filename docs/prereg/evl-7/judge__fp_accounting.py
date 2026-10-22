#!/usr/bin/env python
"""fp_accounting.py: PREREG-EVL-7's expected-false-pass arithmetic (no data; the frozen files' and drafts' constants).

Two bases are printed, because the lane's count is being restated tonight:
  BASIS A (PREREG-EVL-4 section 3, A71, A81; league/events/screen.py FALSE_PASS_RATE 0.10, LANE_BUDGET 3.0): 0.10 a
           seatable version, thirty versions in all.
  BASIS B (PREREG-EVL-6's draft section 5): 0.14 a seatable version or fresh run (its worst plausible 0.131 rounded
           up), LANE_BUDGET restated 4.2 (the same thirty versions); the fifteen versions PREREG-EVL-6 registers replace
           the fifteen of PREREG-EVL-3 to -5, which held no look and are dropped.
Each EVL-7 learner version is one seatable version: 1/30 of the lifetime budget on either basis.
Usage: fp_accounting.py [births_before_7]
"""
import sys

births = int(sys.argv[1]) if len(sys.argv) > 1 else 0
LEARNERS = 2                 # EVL-LRN-O1 v1, EVL-LRN-ON v1
REENTRY_MAX = 2 * 2          # versions 2 and 3 of each id
for name, rate, budget, prior in (("A (PREREG-EVL-4, 0.10 / 3.0)", 0.10, 3.0, 15),
                                  ("B (PREREG-EVL-6 draft, 0.14 / 4.2)", 0.14, 4.2, 15)):
    used_before = round(rate * (prior + births), 4)
    add = round(rate * LEARNERS, 4)
    used_after = round(used_before + add, 4)
    left = round(budget - used_after, 4)
    worst = round(used_after + rate * REENTRY_MAX, 4)
    print(f"BASIS {name}")
    print(f"  used before PREREG-EVL-7 : {used_before:.2f}  ({prior} seatable versions + {births} births at {rate})")
    print(f"  PREREG-EVL-7 adds        : {add:.2f}  ({LEARNERS} learner versions)")
    print(f"  used after               : {used_after:.2f} of {budget}")
    print(f"  left                     : {left:.2f}  = {int(round(left / rate))} seatable versions at {rate}")
    print(f"  if every re-entry is used: {worst:.2f} of {budget} (re-entries drawn one at a time; refused when the "
          f"budget cannot hold them)")
    print(f"  EVL-7's share at most    : {rate * (LEARNERS + REENTRY_MAX):.2f} ({LEARNERS + REENTRY_MAX} versions)")

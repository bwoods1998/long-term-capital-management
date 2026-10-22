#!/usr/bin/env python
"""budget9ff.py (the final minimal fix; budget9.py with W9 from select_w9ff.py w9): PREREG-EVL-9's charge and the lane's budget (section 10), ARITHMETIC ONLY on the frozen PREREG-EVL-6's
constants (section 5: 0.13 a version or run, a lifetime budget of 3.9 = 30 x 0.13, 1.95 used by its fifteen versions)
and the neighbouring files' stated draws (PREREG-EVL-7: 2 x c7, c7 = 0.13 in its work text; PREREG-EVL-8: 5 x 0.13 =
0.65, its final text section 6.6; the captain's seat plan A117). W9 is read from ff/ff.w9.out when given.
Usage: budget9ff.py [W9]
"""
import math
import sys

C6, BUDGET, USED6 = 0.13, 3.9, 15 * 0.13
W9 = float(sys.argv[1]) if len(sys.argv) > 1 else None


def up2(x):
    return math.ceil(round(x * 100, 9)) / 100.0


c9 = max(C6, up2(W9)) if W9 is not None else C6
evl7, evl8 = 2 * 0.13, 5 * 0.13
print(f"c9 = max(PREREG-EVL-6's 0.13, W9 {W9 if W9 is not None else '(not given)'} rounded up to 0.01) = {c9:.2f}")
print(f"PREREG-EVL-6's budget {BUDGET:.2f}; used at REGISTERED_AT_6 {USED6:.2f} (fifteen versions)")
for births in (0, 3):
    before = USED6 + evl7 + evl8 + 0.13 * births
    after = before + 2 * c9
    print(f"  with {births} seatable birth(s) registered before REGISTERED_AT_9: used before this file {before:.2f} "
          f"(PREREG-EVL-7 {evl7:.2f}, PREREG-EVL-8 {evl8:.2f}); this file 2 x {c9:.2f} = {2 * c9:.2f}; used after "
          f"{after:.2f}; LEFT {BUDGET - after:.2f} ({int(math.floor((BUDGET - after) / 0.13 + 1e-9))} whole charges of 0.13)")
print(f"if LEFT before this file holds {2 * c9:.2f}: both ids; if it holds {c9:.2f} only: EVL-WL-ON alone (the larger pool); "
      f"else this file registers nothing")
print(f"this file's lifetime draw: at most 3 runs a version: 6 x {c9:.2f} = {6 * c9:.2f}")

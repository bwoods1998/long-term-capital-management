#!/usr/bin/env python
"""fp_w7.py: PREREG-EVL-7's expected-false-pass arithmetic on PREREG-EVL-6's FROZEN basis (no data; constants only).

PREREG-EVL-6 section 5 (frozen): 0.13 expected false passes for every seatable version it registers or judges (its run
1) and for every fresh run when it starts; the lane's lifetime budget 3.9 = 30 x 0.13; used at its registration 15 x
0.13 = 1.95 plus 0.13 for each seatable birth registered before REGISTERED_AT_6; every charge is made only when the
budget holds it, in registration order.
PREREG-EVL-7 (sections 1.10 and 4): each learner version's run 1 is charged c7 at registration (2 versions); each later
run c7 when it starts, at most three runs an id over its life; so at most 6 x c7 for this file.
USED BEFORE THIS FILE is the SEATING sum R3's validator reads at REGISTERED_AT_7 (every seatable version and fresh run
registered or started before it, any file, births included); this script shows it for B seatable births and X other
charges (another file frozen first, a fresh run started) at the frozen charge.
Usage: fp_w7.py C7 [B] [X]
"""
import sys

C6 = 0.13
BUDGET = 3.9
c7 = float(sys.argv[1]) if len(sys.argv) > 1 else C6
B = int(sys.argv[2]) if len(sys.argv) > 2 else 0
X = int(sys.argv[3]) if len(sys.argv) > 3 else 0
used_before = round(15 * C6 + C6 * B + C6 * X, 4)
add = round(2 * c7, 4)
after = round(used_before + add, 4)
left = round(BUDGET - after, 4)
later = round(4 * c7, 4)
print(f"PREREG-EVL-6 frozen basis: {C6} a version or run, lifetime budget {BUDGET} (30 x {C6})")
print(f"  USED BEFORE THIS FILE : {used_before:.2f}  (15 versions x {C6} = {15 * C6:.2f}; {B} births and {X} other "
      f"charges at {C6})")
print(f"  THIS FILE ADDS        : {add:.2f}  (2 learner versions' run 1 at c7 = {c7:.2f})")
print(f"  USED AFTER            : {after:.2f} of {BUDGET}")
print(f"  LEFT                  : {left:.2f}  (= {left / C6:.1f} charges at {C6}; {left / c7:.1f} at {c7:.2f})")
print(f"  THE LEARNERS' LATER RUNS: at most {later:.2f} more (4 runs at c7), each drawn when it starts and only when the "
      f"budget holds it; this file at most {6 * c7:.2f} (6 x c7)")
print(f"  IF EVERY LATER LEARNER RUN STARTS: {after + later:.2f} of {BUDGET}, left {BUDGET - after - later:.2f}")
for b in (3, 6):
    ub = round(15 * C6 + C6 * b, 4)
    print(f"  with {b} births before REGISTERED_AT_7: used before {ub:.2f}, after {ub + add:.2f}, left "
          f"{BUDGET - ub - add:.2f}")

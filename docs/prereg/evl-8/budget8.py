#!/usr/bin/env python
"""budget8.py: the lane's expected-false-pass count after PREREG-EVL-8 (the captain's F12), ARITHMETIC ONLY, on
PREREG-EVL-6's frozen basis (section 5: 0.13 a seatable version or a run when it starts, a lifetime budget of 3.9,
R3's validator reading the SEATING sum of every seatable version and run of every file, registration order when the
budget cannot hold every draw). The births registered before REGISTERED_AT_6 (B6), and any other births, enter as
counts the registering amendment reads from the SEATING sum; nothing here reads the lane."""
CHARGE, BUDGET = 0.13, 3.9
evl6 = 15 * CHARGE
c7 = 0.13          # PREREG-EVL-7's per-run charge c7 = max(0.13, its own worst rounded up): 0.13 if its work text holds
evl7_reg, evl7_max = 2 * c7, 6 * c7
evl8_reg = 5 * CHARGE
a104 = 3 * CHARGE
print(f"PREREG-EVL-6 at REGISTERED_AT_6: 15 new versions x {CHARGE} = {evl6:.2f} (+ {CHARGE} per seatable birth B6 registered before it)")
print(f"PREREG-EVL-7 at its registration: 2 x c7 = {evl7_reg:.2f} (c7 = {c7}); at most 6 x c7 = {evl7_max:.2f} over its ids' lives")
print(f"PREREG-EVL-8 at its registration: 5 versions x {CHARGE} = {evl8_reg:.2f}; every later run {CHARGE} when it starts")
print(f"A104's three day-news births, if registered: {a104:.2f}")
used = evl6 + evl7_reg + evl8_reg
print(f"USED after PREREG-EVL-8 (both files registered, no birth): {used:.2f} of {BUDGET}; LEFT {BUDGET - used:.2f} "
      f"= {round((BUDGET - used) / CHARGE)} charges, less {CHARGE} per birth")
used2 = used + a104
print(f"with A104's three births: USED {used2:.2f}, LEFT {BUDGET - used2:.2f} = {round((BUDGET - used2) / CHARGE)} charges "
      f"(every fresh run of every version of every file and every later birth draws from it, in registration order)")
print(f"if none of PREREG-EVL-6's fifteen passes, their second runs alone need 15 x {CHARGE} = {15 * CHARGE:.2f}, more "
      f"than is left: they start first (registration order), and this file's versions' second runs start only if "
      f"room is left after them")
print(f"this file's lifetime draw if every one of its five versions ran two runs: {10 * CHARGE:.2f}; three: {15 * CHARGE:.2f}")

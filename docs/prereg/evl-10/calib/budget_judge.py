#!/usr/bin/env python
"""budget_judge.py (the edge-swings judge; outcome-free arithmetic): the lane's expected-false-pass budget around
PREREG-EVL-10 and -11, on PREREG-EVL-6's frozen basis (section 5: lifetime 3.9 = 30 x 0.13) and the frozen texts'
own charges, as R3's validator reads the SEATING sum. Sources: PREREG-EVL-6 s5 (fifteen versions, 1.95);
PREREG-EVL-7 s4 (two learners at c7 = 0.13: 0.26); PREREG-EVL-8 s6.6 (five seats at 0.13: 0.65); PREREG-EVL-9 s10
(2 x c9 = 0.30 RESERVED at its registration, drawn after CODE_PIN_9, released by a VOID); A104 (three day-news births
at 0.13, timer 01:00Z Oct 24); R3's nightly births (at most three seatable births a night, A81, 0.13 each; the first
Opus night is 01:15Z Oct 23). Nothing here reads any outcome."""
from __future__ import annotations

import json
import os

BUDGET, C = 3.9, 0.13
USED = {"PREREG-EVL-6 (15 versions)": 1.95, "PREREG-EVL-7 (2 learners)": 0.26, "PREREG-EVL-8 (5 seats)": 0.65,
        "PREREG-EVL-9 (2 x c9 reserved)": 0.30}
EVL10_SEAT, EVL11_SEAT_AT_GATE = 0.13, 0.13


def left(used):
    return round(BUDGET - used, 2)


rows = []
base = round(sum(USED.values()), 2)
for births_before in (0, 1, 2, 3, 6):
    used = round(base + C * births_before, 2)
    if used > BUDGET + 1e-9:
        continue
    l0 = left(used)
    r10 = l0 >= EVL10_SEAT - 1e-9
    used10 = round(used + (EVL10_SEAT if r10 else 0.0), 2)
    l10 = left(used10)
    rows.append({"seatable births registered before EVL-10's freeze": births_before, "USED before": used,
                 "LEFT before": l0, "EVL-10 seat registers": r10, "USED after EVL-10": used10,
                 "LEFT after EVL-10": l10, "whole charges left": int(round(l10 / C, 2) // 1),
                 "EVL-11 gated seat can start later (LEFT >= 0.13 then)": l10 >= EVL11_SEAT_AT_GATE - 1e-9,
                 "META-W's two seats (0.26) fit after EVL-10": l10 >= 0.26 - 1e-9})
out = {"basis": {"lifetime": BUDGET, "charge": C, "used_by_frozen_files": USED, "USED_before_any_birth": base,
                 "LEFT_before_any_birth": left(base)},
       "scenarios": rows,
       "lifetime_draws": {"EVL-10 (one seat, at most three runs, PREREG-EVL-7 s1.10's rule)": round(3 * EVL10_SEAT, 2),
                          "EVL-11 (one gated seat, at most three runs)": round(3 * EVL11_SEAT_AT_GATE, 2)},
       "owed_later_if_nothing_passes": {
           "PREREG-EVL-6 second runs (15 x 0.13, from about the 60th session after REGISTERED_AT_6)": 1.95,
           "PREREG-EVL-7 later runs (4 x 0.13)": 0.52, "PREREG-EVL-8 later runs (0.13 each when one starts; its text sets no cap), five seats x one more run": 0.65,
           "PREREG-EVL-9 later runs (4 x 0.15)": 0.60},
       "note": ("Every charge is made only when the budget holds it (PREREG-EVL-6 s3, s5), so the lane's expected false "
                "passes never exceed 3.9; whatever registers now takes room that later runs and births would use. "
                "Restating the budget is the captain's, with its cost stated (each 0.13 = one more expected false pass).")}
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "budget_judge.out"), "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps(out, indent=1))

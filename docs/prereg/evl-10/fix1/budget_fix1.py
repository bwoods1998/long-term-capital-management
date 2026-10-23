#!/usr/bin/env python
"""budget_fix1.py: PREREG-EVL-10 FIX ROUND 1, the lane's expected-false-pass budget as the code on origin/rel/1019l
counts it (outcome-free registration facts only: no store, no outcome).

Sources, read from git (`git show origin/rel/1019l:...`): league/events/births.py `RESERVED` (A137: the frozen files'
charges held while their pins are unset: PREREG-EVL-8 0.65, PREREG-EVL-9 0.30, PREREG-EVL-10 0.13) and the registered
births' specs (docs/births/*.jsonl: `spec.seatable`), every one registered after REGISTERED_AT_6 (2026-10-22T12:24:50Z,
A116; the births of the nights 2026-10-22 and 2026-10-23, A136 and A137). The basis is PREREG-EVL-6 section 5's frozen
lifetime 3.9 = 30 x 0.13 (the owner's goal V3 lets the captain restate a false-pass budget each week; none is restated
at this writing, A138's NOT YET). The screen's own sum (screen.py `budget6`) counts 0.13 for each PREREG-EVL-6 version in
SEATING (fifteen), each PREREG-EVL-7 learner (two, pinned live since release 1019j, A137) and each seatable birth
registered from REGISTERED_AT_6.
Run: .venv/bin/python budget_fix1.py > budget_fix1.out
"""
from __future__ import annotations

import ast
import json
import re
import subprocess

REPO = "/home/bwoods1998/Work/long-term-capital-management"
REF = "origin/rel/1019l"
BASIS, C = 3.90, 0.13


def show(path: str) -> str:
    return subprocess.run(["git", "-C", REPO, "show", f"{REF}:{path}"], check=True, capture_output=True,
                          text=True).stdout


births_py = show("league/events/births.py")
m = re.search(r"^RESERVED = (\(.*?\))\n\n", births_py, re.S | re.M)
reserved = ast.literal_eval(m.group(1))
files = subprocess.run(["git", "-C", REPO, "ls-tree", "--name-only", REF, "docs/births/"], check=True,
                       capture_output=True, text=True).stdout.split()
births = []
for f in files:
    for line in show(f).splitlines():
        if line.strip():
            r = json.loads(line)
            births.append({"night": r["night"], "id": r["spec"]["id"], "seatable": bool(r["spec"].get("seatable"))})
seatable = [b for b in births if b["seatable"]]
used = {"PREREG-EVL-6 (15 versions in SEATING)": round(15 * C, 2), "PREREG-EVL-7 (2 learners, pinned live)": round(2 * C, 2),
        f"seatable births since REGISTERED_AT_6 ({len(seatable)})": round(len(seatable) * C, 2)}
code_used = round(sum(used.values()), 2)
held = {name: h / 100 for name, _, h in reserved}
held_others = round(sum(v for k, v in held.items() if k != "PREREG-EVL-10"), 2)
before = round(code_used + held_others, 2)
after = round(before + C, 2)
out = {"basis": BASIS, "charge": C, "births_registered": births, "screen_budget6_used": used,
       "screen_budget6_used_total": code_used, "code_left_before_reservations": round(BASIS - code_used, 2),
       "births_RESERVED": held,
       "USED_before_this_file (the sum R3's validator reads, the reservations of EVL-8 and EVL-9 in it)": before,
       "LEFT_before_this_file": round(BASIS - before, 2),
       "USED_after_this_file": after, "LEFT_after_this_file": round(BASIS - after, 2),
       "whole_charges_left_after": int(round((BASIS - after) / C, 6) // 1),
       "the_births_room_now (RESERVED already holds this file's 0.13, A137)": round(BASIS - after, 2),
       "this_file_lifetime_draw_at_most": round(3 * C, 2),
       "owed_later_if_nothing_passes": {"PREREG-EVL-6 second runs (15 x 0.13)": 1.95,
                                        "PREREG-EVL-7 later runs (4 x 0.13)": 0.52,
                                        "PREREG-EVL-8 one more run each (5 x 0.13)": 0.65,
                                        "PREREG-EVL-9 later runs (4 x 0.15)": 0.60},
       "note": ("A run that the budget cannot hold waits (PREREG-EVL-6 s3) or, for this file's version, never starts "
                "(section 3 of the file). With LEFT 0.09 after this file, no later run of any file starts until the "
                "captain restates the budget (goal V3 item 3: a false-pass budget he states and may restate each "
                "week), each 0.13 one more expected false pass.")}
print(json.dumps(out, indent=1))

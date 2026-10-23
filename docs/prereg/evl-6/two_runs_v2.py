#!/usr/bin/env python
"""two_runs_v2.py: per VERSION within 120 sessions (run 1 and, after an end at its 60th block, run 2) for every
shortlisted rule on the selection seeds (w2, w2x) and for the chosen rule on the fresh seeds (w3, w3x); synthetic only.
Usage: two_runs_v2.py > two_runs_v2.out"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_v2 as SV  # noqa: E402
import search_final as SF  # noqa: E402

short = json.load(open(os.path.join(HERE, "shortlist_v2.json")))
chosen = json.load(open(os.path.join(HERE, "chosen_v2.json")))["chosen"]["rule"]
sel = [c for c in SF._load(["w2", "w2x"], []) if SV.plausible(c["cell"], c["gen"])]
fresh = [c for c in SF._load(["w3", "w3x"], []) if SV.plausible(c["cell"], c["gen"])]
rows = []
for key in short:
    r = SF.Rule.of(key)
    best = (0.0, None, 0.0)
    for c in sel:
        fp, any_ = SF.two_runs(c["d"], r, c["tag"])
        v2, v1 = SF.rate(any_, 120), SF.rate(fp, 120)
        if v2 > best[0]:
            best = (v2, SF.lab(c["cell"], c["gen"], c["T"]), v1)
    rows.append((best, r.label(), key == chosen))
for (v2, lab, v1), label, ch in sorted(rows, key=lambda x: x[0][0]):
    print(f"{'CHOSEN' if ch else '      '} per version (two runs) worst {v2:.4f} [{lab}] (run 1 there {v1:.4f}) | {label}")
r = SF.Rule.of(chosen)
best = (0.0, None)
for c in fresh:
    _, any_ = SF.two_runs(c["d"], r, c["tag"])
    v = SF.rate(any_, 120)
    best = max(best, (v, SF.lab(c["cell"], c["gen"], c["T"])), key=lambda x: x[0])
print(f"CHOSEN on the fresh seeds: per version worst {best[0]:.4f} [{best[1]}]")

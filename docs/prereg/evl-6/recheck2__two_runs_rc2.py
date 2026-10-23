#!/usr/bin/env python
"""two_runs_rc2.py (recheck #2, SYNTHETIC ONLY): per-VERSION false-pass rate within 120 sessions (run 1, and run 2
where run 1 ended unpassed at its 60th block, D2) for every shortlisted rule, at the fresh s2null worst cells and the
s3null replicate. Reads only final/'s synthetic arrays via search_final.py."""
import json, os, sys
import numpy as np
FINAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "final")
sys.path.insert(0, FINAL)
os.chdir(FINAL)
import search_final as SF

short = json.load(open(os.path.join(FINAL, "shortlist.json")))
want = {"N3|both|AR20|phi0.20": (85, 30), "N3|dayskew|AR20|phi0.20": (85,)}
for phase in ("s2null", "s3null"):
    groups = SF.load_index([phase])
    for (cell, gen, T), rs in sorted(groups.items()):
        g = json.loads(gen)
        if cell not in want or g["nbar"] not in want[cell] or abs(g["rho_day"] - 0.15) > 1e-9:
            continue
        d = SF.load_cell(rs)
        print(f"== {phase} {cell} n{g['nbar']} rho0.15 R {d['Sat'].shape[0]}")
        seen = set()
        rows = []
        for key in short:
            if key in seen:
                continue
            seen.add(key)
            rule = SF.Rule.of(key)
            fp, any_ = SF.two_runs(d, rule)
            r1 = SF.rate(fp, 120)
            r2 = SF.rate(any_, 120) if any_ is not None else float("nan")
            rows.append((r2, r1, rule.label()))
        for r2, r1, labl in sorted(rows):
            print(f"  per version (two runs) {r2:.4f} | run 1 {r1:.4f} | {labl}")

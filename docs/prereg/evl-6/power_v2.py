#!/usr/bin/env python
"""power_v2.py: section 4.5's table for the chosen rule (synthetic only): P(promoted by the h-th session of its record),
E[min(T, 60)], the median, run 1 ended unpassed at its 60th block, and promoted within 120 sessions counting run 2;
a true edge on the program's events, symmetric shapes, no drift, phi_day 0.10; the power seeds (s2power, 2,000
programs a cell over 120 sessions). Usage: power_v2.py > power_v2.txt"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_v2 as SV  # noqa: E402,F401
import search_final as SF  # noqa: E402

rule = SF.Rule.of(json.load(open(os.path.join(HERE, "chosen_v2.json")))["chosen"]["rule"])
pw = SF._load([], ["s2power"])
H = (20, 22, 25, 30, 40, 60)
print(f"RULE {rule.label()}")
for sk in (60, 100, 30):
    for rho in (0.05, 0.0, 0.15):
        rows = []
        for c in sorted(pw, key=lambda c: -c["gen"]["nbar"]):
            g = c["gen"]
            if round(g["skill"] * 1e4) != sk or abs(g["rho_day"] - rho) > 1e-9:
                continue
            fp, fr, fe = SF.first_pass(c["d"], "", rule, c["tag"])
            _, any_ = SF.two_runs(c["d"], rule, c["tag"])
            r = {h: SF.rate(fp, h) for h in H}
            r["E60"] = float(np.mean(np.minimum(fp, 60)))
            fin = np.where(fp < SF.NONE, fp, 10 ** 9)
            r["med"] = float(np.median(fin)) if np.median(fin) < 10 ** 9 else None
            r["end"] = float(np.mean(fe < SF.NONE))
            r["two"] = SF.rate(any_, 120)
            rows.append((g["nbar"], r))
            print(f"{sk:3d} bp rho {rho:.2f} n {g['nbar']:3g}: " + " ".join(f"by{h} {r[h]:.3f}" for h in H)
                  + f" | E60 {r['E60']:.1f} med {r['med']} | ended {r['end']:.3f} | promoted by 120 incl. run 2 {r['two']:.3f}")
        if rows:
            m = {k: float(np.mean([r[k] for _, r in rows])) for k in list(H) + ["E60", "end", "two"]}
            print(f"{sk:3d} bp rho {rho:.2f} MEAN: " + " ".join(f"by{h} {m[h]:.3f}" for h in H)
                  + f" | E60 {m['E60']:.2f} | ended {m['end']:.3f} | promoted by 120 incl. run 2 {m['two']:.3f}")

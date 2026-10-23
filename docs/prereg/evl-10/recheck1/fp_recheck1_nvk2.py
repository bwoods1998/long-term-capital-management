#!/usr/bin/env python
"""fp_recheck1_nvk2.py: ADVERSARIAL RE-CHECK 1 of PREREG-EVL-10, NVK (the knife on NV, fp_recheck1.py's (3)) at the
thin cells where NV read highest after centring by the simulator (fp_recheck1.surface.jsonl: n16 f0.1 0.1197, n10
f0.15 0.1165, AR10 n5 f0.3 0.1200, n8 f0.15 0.1148), a fresh 8,000-program replicate of NVK's worst cell (n5 f0.3),
and a stronger-information NVK (b 1.0). SYNTHETIC ONLY. Seeds: evaluation 385,000,001+, pilots 389,500,001+.
Usage: fp_recheck1_nvk2.py [workers<=3]"""
import os
import sys

import fp_recheck1 as F

CR = F.CR


def cells(phase):
    out = []
    for nb, f, R, dr in ((5, 0.3, 8000, F.C20), (16, 0.1, 4000, F.C20), (10, 0.15, 4000, F.C20), (8, 0.15, 4000, F.C20),
                         (5, 0.3, 4000, F.C10)):
        tag = "AR10" if dr is F.C10 else "AR20"
        out.append((f"NVK2|NVK b0.5 sda0.01|corner|{tag}|n{nb}|cnt|finf|f{f}",
                    CR.Cell(null="NV", nbar=nb, cnt=True, finf=True, f_pass=f, **dr), R, (0.5, 0.010), 0.0, True))
    out.append(("NVK2|NVK b1.0 sda0.01|corner|AR20|n5|cnt|finf|f0.3",
                CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **F.C20), 4000, (1.0, 0.010), 0.0, True))
    return out


F.cells = cells
F.SEEDS = {"eval": 385_000_000, "pilot": 389_500_000, "power": 0, "sens": 0}

if __name__ == "__main__":
    w = min(int(sys.argv[1]) if len(sys.argv) > 1 else 3, 3)
    real_open = open

    def _open(path, *a, **k):
        if str(path).endswith("fp_recheck1.surface.jsonl"):
            path = os.path.join(F.HERE, "fp_recheck1.nvk2.jsonl")
        return real_open(path, *a, **k)
    F.open = _open
    F.main("surface", w)

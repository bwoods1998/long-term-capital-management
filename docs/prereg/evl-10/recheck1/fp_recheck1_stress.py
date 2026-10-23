#!/usr/bin/env python
"""fp_recheck1_stress.py: ADVERSARIAL RE-CHECK 1 of PREREG-EVL-10, the named stress (never binding) at the stricter
reader filter: day momentum phi_day 0.40 at rho_day 0.30 on top of the worst corner (t(3)-body clustered crash days,
skewed events, a 20 bp drift at AR 0.97, counts that follow the day), as calib/judge_stress.py ran it at the designer's
60% filter (0.1755 +- 0.0085 at 5 candidates), here at 30% (5 and 8 candidates), centred by the simulator itself
(fp_recheck1.py's method). SYNTHETIC ONLY. Seeds: evaluation 384,000,001+, pilots 389,400,001+.
Usage: fp_recheck1_stress.py [workers<=3]"""
import sys

import fp_recheck1 as F

CR = F.CR
ST = dict(CR.CORNER, rho_day=0.30, phi_day=0.40, drift_sd=0.0020)


def cells(phase):
    return [(f"ST|NV|phi.40|rho.30|AR20|n{nb}|cnt|finf|f{f}",
             CR.Cell(null="NV", nbar=nb, cnt=True, finf=True, f_pass=f, **ST), 2000, None, 0.0, True)
            for nb, f in ((5, 0.3), (8, 0.3), (5, 0.6))]


F.cells = cells
F.SEEDS = {"eval": 384_000_000, "pilot": 389_400_000, "power": 0, "sens": 0}

if __name__ == "__main__":
    import os
    w = min(int(sys.argv[1]) if len(sys.argv) > 1 else 3, 3)
    # main() keys its seed offsets by phase name; "surface" gives offset 0 on the seeds above, and the output file
    # is renamed below so fp_recheck1.surface.jsonl is never touched.
    real_open = open

    def _open(path, *a, **k):
        if str(path).endswith("fp_recheck1.surface.jsonl"):
            path = os.path.join(F.HERE, "fp_recheck1.stress.jsonl")
        return real_open(path, *a, **k)
    F.open = _open  # main() resolves `open` in its module globals first
    F.main("surface", w)

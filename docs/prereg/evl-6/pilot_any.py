#!/usr/bin/env python
"""pilot_any.py: calib_final.py's prefilter checked for ANY schedule (synthetic only). On the pilot cells, the
prefiltered arrays and the full computation agree on every (program, session) at which the full p is <= 0.020 with
the guards held (the only entries any rule with alpha <= 0.020 can pass at), and the full q is <= 0.020 with mean a < 0
(the only entries a RETIRE can use). Prints the count of such entries and of disagreements per cell."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calib_final as CF  # noqa: E402

for lab, kw, R, T, opts in CF.cells("pilot"):
    g = CF.Gen(**kw)
    pre, _ = CF.simulate(g, R, T, 4242)
    full, _ = CF.simulate(g, R, T, 4242, full_p=True)
    P_full = np.where(np.isnan(full["P"]), 9.0, full["P"])
    P_pre = np.where(np.isnan(pre["P"]), 9.0, pre["P"])
    need = (P_full <= 0.020) & full["g"]
    bad = need & (np.abs(P_pre - P_full) > 1e-12)
    Q_full = np.where(np.isnan(full["Q"]), 9.0, full["Q"])
    Q_pre = np.where(np.isnan(pre["Q"]), 9.0, pre["Q"])
    needq = (Q_full <= 0.020) & full["neg"]
    badq = needq & (np.abs(Q_pre - Q_full) > 1e-12)
    print(f"{lab} n{kw['nbar']}: entries with full p <= 0.020 and the guards {int(need.sum())}, disagreements "
          f"{int(bad.sum())}; entries with full q <= 0.020 and mean a < 0 {int(needq.sum())}, disagreements {int(badq.sum())}",
          flush=True)

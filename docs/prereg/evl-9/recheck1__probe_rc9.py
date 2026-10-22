"""probe_rc9.py: re-check 1 of PREREG-EVL-9, a quick probe (SYNTHETIC ONLY): the block rate a session of the H0 cell and
how often run 1 is still open at session 120 (the per-run figure must be the whole run)."""
import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "final"))
import numpy as np
import calib_w9 as w
c = w.mk(learner="ON", shape="crasht3cl", phi_day=0.20, drift_sd=0.0020, ic_h=0.0, T=200)
t0 = time.time()
sim = w.simulate(c, 761_999_001, 50)
n = sim["n"]
blk = (n > 0)
cum = np.cumsum(blk, axis=1)
s60 = np.array([np.argmax(cum[r] >= 60) if cum[r, -1] >= 60 else 999 for r in range(n.shape[0])])
print(c.name, f"{time.time()-t0:.1f}s", "picks/s", round(float(n.mean()), 2), "share of sessions with a block",
      round(float(blk.mean()), 3), "session of the 60th block: median", int(np.median(s60)), "share > 119",
      round(float((s60 > 119).mean()), 3))

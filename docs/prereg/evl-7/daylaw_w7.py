"""daylaw_w7.py: the day laws calib_w7.py draws (synthetic): mean, variance, skew and crash share of eps for each shape,
the clustered shapes over the volatility regime's stationary law (sd 0.3), and the count multiplier's mean."""
import math
import numpy as np
import calib_w7 as w
import calib_learner as cl
rr = np.random.default_rng(5)
M = 2_000_000
for kind in ("t3", "crash", "crasht3", "crashcl", "crasht3cl"):
    if kind in ("t3", "crash"):
        e = cl.day_innov(rr, kind, M); share = float("nan")
    else:
        vx = w.VSD * rr.standard_normal(M); u = rr.random(M); cr = rr.normal(-w.CR_K, 1.0, M)
        body = cl.unit_t3(rr, M) if "t3" in kind else rr.standard_normal(M)
        e = w.day_eps(kind, rr, M, vx, (u, cr, body))
        p = np.minimum(w.CR_P * np.exp(w.CL_G * vx) / math.exp(w.CL_G ** 2 * w.VSD ** 2 / 2), w.CL_MAX) if kind.endswith("cl") else np.full(M, w.CR_P)
        share = float((u < p).mean())
    m, v = e.mean(), e.var(); sk = ((e - m) ** 3).mean() / v ** 1.5
    print(f"{kind:<10} mean {m:+.4f} var {v:.4f} skew {sk:+.2f} crash share {share:.4f} count mult mean {w.count_norm(kind, 0.3):.4f}")

#!/usr/bin/env python
"""rt_mde.py (red team, SYNTHETIC/closed form only; no lane data): the minimum detectable per-event abnormal edge
(MDE) of a session-block test, as a function of events a session n, the within-session residual correlation rho of
the events' abnormal returns, the per-event abnormal sd s, and the number of session blocks S.

Block value B_t = mean of n events' abnormal a; Var(B_t) = s^2 (rho + (1 - rho) / n) (equicorrelated within session,
independent across sessions). One-sided test at level alpha with power 1 - beta, normal approximation:
    MDE = (z_{1-alpha} + z_{1-beta}) sqrt(Var(B_t) / S) + m0      (m0 = the screen's margin, EVL-6 L12: 10 bp).
alpha 0.01 is the EVL-6 L12 candidate's per-look level (calib_learner.py header); a single look is used, so this is a
LOWER bound on the MDE of a schedule that spends alpha over many looks.
Also: the number of events a session beyond which more events buy < 10% more power (n* where the idiosyncratic share
of Var(B) falls under 10%: (1 - rho) / n <= 0.1 rho / 0.9).
"""
import json, math
from statistics import NormalDist

Z = NormalDist().inv_cdf
out = []
for s in (0.03, 0.04, 0.05):
    for rho in (0.005, 0.0145, 0.03, 0.05):
        for n in (3, 8, 18, 30, 85, 300, 1000, 3000):
            for S in (15, 30, 60):
                v = s * s * (rho + (1 - rho) / n)
                mde = (Z(0.99) + Z(0.80)) * math.sqrt(v / S) + 0.0010
                out.append(dict(s=s, rho=rho, n=n, S=S, block_sd_bp=round(1e4 * math.sqrt(v), 1),
                                mde_bp=round(1e4 * mde, 1)))
print("s     rho     n     S  block_sd_bp  MDE_bp(alpha .01, power .8, +10bp margin)")
for r in out:
    if r["s"] == 0.04 or (r["S"] == 30 and r["n"] in (18, 85, 3000)):
        print(f'{r["s"]:.2f} {r["rho"]:.4f} {r["n"]:5d} {r["S"]:3d} {r["block_sd_bp"]:9.1f} {r["mde_bp"]:9.1f}')
nstar = {f"rho={rho}": math.ceil((1 - rho) * 0.9 / (0.1 * rho)) for rho in (0.005, 0.0145, 0.03, 0.05)}
print("n* (events a session past which < 10% of block variance is idiosyncratic):", nstar)
json.dump({"rows": out, "nstar": nstar}, open(__file__.replace(".py", ".out.json"), "w"), indent=1)

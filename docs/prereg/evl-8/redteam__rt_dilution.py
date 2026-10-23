#!/usr/bin/env python
"""rt_dilution.py (red team; closed form, SYNTHETIC assumptions only): sessions a winner-picking learner needs before
ONE sub-rule with a true per-event edge delta stands out from F - 1 zero-edge sub-rules, when each sub-rule's
session-block score has noise sd sigma_B. The max of F - 1 independent N(0, S sigma_B^2) cumulative scores is about
sigma_B sqrt(S) sqrt(2 ln F); the true rule's cumulative mean is S delta; it leads at about
    S* = 2 ln F (sigma_B / delta)^2      (+ a z_power term: S80 = (sqrt(2 ln F) + 0.84)^2 (sigma_B / delta)^2).
sigma_B: a K = 8-event block of 4%-sd events (1.41%) plus a 0.6% family-day shock: 1.54% (rt_meta.py's generator).
"""
import json, math
rows = []
for sB in (0.0100, 0.0154, 0.0250):
    for d in (0.0010, 0.0020, 0.0030, 0.0060):
        for F in (10, 50, 200, 800):
            s_star = 2 * math.log(F) * (sB / d) ** 2
            s80 = (math.sqrt(2 * math.log(F)) + 0.84) ** 2 * (sB / d) ** 2
            rows.append(dict(sigma_B_bp=round(sB * 1e4), delta_bp=round(d * 1e4), F=F, S_star=round(s_star),
                             S80=round(s80)))
for r in rows:
    if r["sigma_B_bp"] == 154:
        print(r)
json.dump(rows, open(__file__.replace(".py", ".out.json"), "w"), indent=1)

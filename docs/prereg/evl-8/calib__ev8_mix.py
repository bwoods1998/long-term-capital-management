#!/usr/bin/env python
"""ev8_mix.py: an ILLUSTRATIVE mixture of ev8_drive's scenarios under STATED weights (the judge's, not evidence):
the increment PREREG-EVL-8 adds (evl8 minus base) to P(Done within 120 sessions), mean P&L and P(false Done)."""
import glob, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
res = json.load(open(glob.glob(os.path.join(HERE, "ev8_*_1000_98000001.json"))[0]))["res"]
W = {"Z15": 0.50, "E1": 0.15, "PX40": 0.10, "META": 0.10, "E1PX": 0.05, "E3news": 0.05, "PX60": 0.05}
tot = {"dP_done": 0.0, "dpnl": 0.0, "dfalse_done": 0.0, "d_false_promos": 0.0}
for k, w in W.items():
    b, e = res[f"base|{k}"], res[f"evl8|{k}"]
    d = dict(dP_done=e["P_done_H"] - b["P_done_H"], dpnl=e["pnl_mean"] - b["pnl_mean"],
             dfalse_done=e["P_false_done"] - b["P_false_done"], d_false_promos=e["false_promo_mean"] - b["false_promo_mean"])
    for x in tot:
        tot[x] += w * d[x]
    print(f"{k:7s} w {w:.2f} | dP(Done<=120) {d['dP_done']:+.3f} dPnL {d['dpnl']:+7.1f} dP(falseDone) {d['dfalse_done']:+.3f} "
          f"dFalsePromos {d['d_false_promos']:+.3f}")
print("MIXTURE", {k: round(v, 4) for k, v in tot.items()})

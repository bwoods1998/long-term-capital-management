"""Evaluate PREREG-EVL-6's chosen rule (the judge's own first_pass, search_judge.py) on check #1's arrays."""
import collections, json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "judge"))
import search_judge as SJ
RULE = ("mlist:6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60", "step:0.016:20:0.004", 0.001, "full", True)
RULE_ABS = RULE[:3] + ("abs", True)
idx = sys.argv[1] if len(sys.argv) > 1 else "c1all.index.jsonl"
rows = [json.loads(l) for l in open(idx)]
groups = collections.defaultdict(list)
for r in rows:
    groups[(r["cell"], r["gen"]["nbar"], r["gen"]["rho_day"])].append(r)
print(f"{'cell':36s} {'n':>3s} {'rho':>4s} {'R':>5s} | EVL6 L0  (se)  L3   | abs-only L0 | old(no skew) | ev_mean blk_mean bp")
for key in sorted(groups):
    rs = groups[key]
    ds = [dict(np.load(r["path"])) for r in rs]
    d = {k: np.concatenate([x[k] for x in ds]) for k in ds[0]}
    R = d["L0_Sat"].shape[0]
    out = []
    for L in (0, 3):
        f = SJ.combined(d, L, RULE, "alone")
        out.append(SJ.rate(f, 120))
    fa = SJ.rate(SJ.combined(d, 0, RULE_ABS, "alone"), 120)
    old = float(np.mean(d["old"] >= 1))
    se = (out[0] * (1 - out[0]) / R) ** 0.5
    ev = np.mean([r["info"]["ev_mean"] for r in rs]) * 1e4
    bm = np.mean([r["info"]["blk_mean"] for r in rs]) * 1e4
    print(f"{key[0]:36s} {key[1]:3.0f} {key[2]:4.2f} {R:5d} | {out[0]:.3f} ({se:.3f}) {out[1]:.3f} | {fa:.3f}       | {old:.3f}        | {ev:6.1f} {bm:6.1f}")

"""PREREG-EVL-6's rule and stricter variants (margin 10 bp; alpha early/late) on check #1's arrays, lag 0 and 3."""
import collections, json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "judge"))
import search_judge as SJ
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pw_alpha  # noqa: F401
SCHED = "mlist:6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60"
VARS = [("chosen", "step:0.016:20:0.004"), ("6-9 .016|.012|.003", "pw:6-9=0.016,10-20=0.012,21-60=0.003"),
        ("6-8 .016|.012|.003", "pw:6-8=0.016,9-20=0.012,21-60=0.003"), ("6-10 .016|.010|.003", "pw:6-10=0.016,11-20=0.010,21-60=0.003"),
        ("4.4 .012/.003", "step:0.012:20:0.003")]
rows = []
for p in sys.argv[1:]:
    rows += [json.loads(l) for l in open(p)]
groups = collections.defaultdict(list)
for r in rows:
    groups[(r["cell"], r["gen"]["nbar"], r["gen"]["rho_day"])].append(r)
print(f"{'cell':34s} {'n':>3s} {'rho':>4s} {'R':>5s} | " + " | ".join(f"{v[0]:>14s}" for v in VARS) + "   (L0 / L3)")
for key in sorted(groups):
    ds = [dict(np.load(r["path"])) for r in groups[key]]
    d = {k: np.concatenate([x[k] for x in ds]) for k in ds[0]}
    R = d["L0_Sat"].shape[0]
    cells = []
    for _, a in VARS:
        rule = (SCHED, a, 0.001, "full", True)
        v = [SJ.rate(SJ.combined(d, L, rule, "alone"), 120) for L in (0, 3)]
        cells.append(f"{v[0]:.3f}/{v[1]:.3f}")
    print(f"{key[0]:34s} {key[1]:3.0f} {key[2]:4.2f} {R:5d} | " + " | ".join(f"{c:>14s}" for c in cells))

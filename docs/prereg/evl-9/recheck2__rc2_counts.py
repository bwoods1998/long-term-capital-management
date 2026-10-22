#!/usr/bin/env python
"""rc2_counts.py (re-check 2; counts and arithmetic on the fixer's own outputs, no lane data):
(1) form4map_w9.out.json's 'DirectorOther' rows over all quarters vs the history window's quarters 2021q1-2026q3;
(2) the six selected cells' search-minus-fresh gaps in units of the difference's SE (select_w9.w9.out figures)."""
import json, math, os
F = "/home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl9/final/form4map_w9.out.json"
d = json.load(open(F)); q = d["quarters"]
w = [k for k in q if k >= "2021q1"]
print(f"form4map: all {len(q)} quarters {sorted(q)[0]}..{sorted(q)[-1]}: rows {sum(v['rows'] for v in q.values())} "
      f"differ {sum(v['either_differ'] for v in q.values())}; window {len(w)} quarters: rows "
      f"{sum(q[k]['rows'] for k in w)} differ {sum(q[k]['either_differ'] for k in w)} "
      f"({sum(q[k]['either_differ'] for k in w) / sum(q[k]['rows'] for k in w):.4f})")
cells = [(0.150, 200, 0.1265, 2000), (0.145, 200, 0.1135, 2000), (0.145, 200, 0.1040, 2000), (0.140, 200, 0.0970, 2000),
         (0.135, 200, 0.1155, 2000), (0.130, 200, 0.1025, 2000)]
for s, ns, f, nf in cells:
    se = math.sqrt(s * (1 - s) / ns + f * (1 - f) / nf)
    print(f"search {s:.3f} fresh {f:.4f}: gap {s - f:.4f} = {(s - f) / se:.2f} SE of the difference")

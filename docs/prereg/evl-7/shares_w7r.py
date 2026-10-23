#!/usr/bin/env python
"""shares_w7r.py: the derived figures sections 0, 4 and 5 of PREREG-EVL-7 quote from the final fix round (synthetic only;
reads calib_w7r.py's own outputs w7r.*.jsonl, no lane data): pooled per-run rates at W7's cells (fresh + search + life
seeds), the share of PASSING records whose true conditional mean a7 is <= 0 / <= 10 bp (cm0 / run1, cm10 / run1), the
picks' sigma and COST-7 minus replay ranges on the null cells and on the power cells, and the search's summary.
Usage: shares_w7r.py > shares_w7r.out"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w7r as w  # noqa: E402


def S(g):
    return {n: w.summarise(p) for n, p in w.load(g).items()}


def pooled(*pairs):
    k = sum(r * n for r, n in pairs)
    n = sum(n for _, n in pairs)
    p = k / n
    return p, math.sqrt(p * (1 - p) / n), n


def main():
    se, fr, li, fa, st, sn = S("search"), S("fresh"), S("life"), S("fam"), S("stress"), S("sens")
    pw = {n: w.summarise(p, "a7") for n, p in w.load("power").items()}
    print("== W7's cells: fresh, search, life (run 1 within 120 sessions is the same test at T = 200)")
    for n in sorted(fr, key=lambda k: -fr[k]["run1"]):
        f, s = fr[n], se[n]
        lname = n + "-T200"
        parts = [(f["run1"], f["R"]), (s["run1"], s["R"])]
        line = (f"{n:<64} fresh {f['run1']:.4f} ({f['R']}) search {s['run1']:.4f} ({s['R']}) | fresh+search "
                "%.4f (se %.4f, %d)" % pooled(*parts))
        if lname in li:
            L = li[lname]
            line += (" | fresh+life %.4f (se %.4f, %d)" % pooled(parts[0], (L["run1"], L["R"])))
        print(line)
    print("== the share of PASSING run-1 records whose true conditional mean a7 is <= 0 / <= 10 bp")
    for lab, d in (("fresh", fr), ("life", li), ("fam", fa), ("stress", st)):
        for n in sorted(d, key=lambda k: -d[k]["run1"]):
            s = d[n]
            if s["run1"] > 0:
                print(f"{lab:<6} {n:<70} run1 {s['run1']:.4f} v120 {s['v120']:.4f} | of passes: <=0 "
                      f"{s['cm0'] / s['run1']:.3f}, <=10bp {s['cm10'] / s['run1']:.3f}")
    learn = [n for n in list(fa) + list(st) if "famdrift" in n or "secdrift" in n]
    sh0 = [(fa.get(n) or st.get(n))["cm0"] / (fa.get(n) or st.get(n))["run1"] for n in learn]
    sh10 = [(fa.get(n) or st.get(n))["cm10"] / (fa.get(n) or st.get(n))["run1"] for n in learn]
    print(f"learnable drifts ({len(learn)} cells): of passes, true mean <= 0 {min(sh0):.3f}-{max(sh0):.3f}; "
          f"<= 10 bp {min(sh10):.3f}-{max(sh10):.3f}")
    print("== the picks' sigma and COST-7 minus the replay (bp a round trip)")
    for lab, d in (("null fresh cells", fr), ("power cells (alternative)", pw)):
        sg = [s["sig_picks"] for s in d.values()]
        df = [s["c7_bp"] - s["crep_bp"] for s in d.values()]
        c7 = [s["c7_bp"] for s in d.values()]
        cr = [s["crep_bp"] for s in d.values()]
        print(f"{lab}: sigma {min(sg):.3f}-{max(sg):.3f}; COST-7 {min(c7):.1f}-{max(c7):.1f} bp, replay "
              f"{min(cr):.1f}-{max(cr):.1f} bp; COST-7 - replay {min(df):.1f}-{max(df):.1f} bp")
    print("== power: COST-7 (a7) against the replay (arep), run 1 by 120 sessions, points")
    pr = {n: w.summarise(p, "arep") for n, p in w.load("power").items()}
    d1 = [pr[n]["run1"] - pw[n]["run1"] for n in pw]
    print(f"replay minus COST-7, run 1: {min(d1) * 100:.1f}-{max(d1) * 100:.1f} points")
    print("== the picks' mean issuer effect (bp), no-information cells with 1% issuer effects (search + fresh)")
    for L in ("O1", "ON"):
        for pool in (300, 800):
            v = [d[n]["tau_bp"] for d in (se, fr) for n in d
                 if n.startswith(L + "-N1-") and f"-n{pool}-" in n and "-tau1-" in n]
            if v:
                print(f"{L} pool {pool}: {len(v)} cells, {min(v):+.1f} to {max(v):+.1f} bp")
    print("== search")
    v = sorted((s["run1"] for s in se.values()), reverse=True)
    print(f"{len(v)} cells; max {v[0]:.4f}; median {float(np.median(v)):.4f}; min {v[-1]:.4f}; at or above 0.10: "
          f"{sum(x >= 0.10 for x in v)}")
    for n, s in sorted(sn.items()):
        print(f"base model {n}: run1 {s['run1']:.4f} (se {s['run1_se']:.4f}, {s['R']}) v120 {s['v120']:.4f}")


if __name__ == "__main__":
    main()

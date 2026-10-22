#!/usr/bin/env python
"""facts_w7r.py: every figure sections 0, 4 and 5 of PREREG-EVL-7 quote from the final fix round, printed from
calib_w7r.py's own outputs (synthetic only; no lane data). Usage: facts_w7r.py > facts_w7r.out"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w7r as w  # noqa: E402


def have(g):
    return os.path.exists(os.path.join(HERE, f"w7r.{g}.jsonl"))


def line(n, s, extra=""):
    return (f"{n:<70} R={s['R']:<5} run1 {s['run1']:.4f} (se {s['run1_se']:.4f}) v120 {s['v120']:.4f} "
            f"cm<=0 {s['cm0']:.4f} <=10bp {s['cm10']:.4f} retired {s['retired']:.3f} runs {s['runs']:.2f} | picks: "
            f"ev/s {s['ev_s']:.2f} tau {s['tau_bp']:+.1f}bp a7 {s['mean_a7_bp']:+.1f}bp sig {s['sig_picks']:.3f} "
            f"c7 {s['c7_bp']:.1f} crep {s['crep_bp']:.1f}bp{extra}")


def main():
    for g in ("pilot", "search", "fresh", "life", "fam", "stress", "sens"):
        if not have(g):
            continue
        by = w.load(g)
        print(f"== {g}")
        rows = sorted(((w.summarise(p), n) for n, p in by.items()), key=lambda x: -x[0]["run1"])
        for s, n in rows:
            ex = ""
            if "life3" in s:
                ex = (f" | LIFE<=3 {s['life3']:.4f} (se {math.sqrt(s['life3'] * (1 - s['life3']) / s['R']):.4f}) by60 "
                      f"{s['life3_by60']:.3f} by120 {s['life3_by120']:.3f} by180 {s['life3_by180']:.3f} runs "
                      f"{s['life3_runs']:.2f}")
            print(line(n, s, ex))
        if g == "search":
            v = [s["run1"] for s, _ in rows]
            print(f"   search: {len(v)} cells, max {v[0]:.4f}, median {float(np.median(v)):.4f}, min {v[-1]:.4f}")
    if have("power"):
        by = w.load("power")
        print("== power")
        for n, p in sorted(by.items()):
            for basis in ("a7", "arep"):
                s = w.summarise(p, basis)
                print(f"{n:<66} {basis:<4} R={s['R']} by10/20/40/60 {s['by10']:.3f}/{s['by20']:.3f}/{s['by40']:.3f}/"
                      f"{s['by60']:.3f} run1 {s['run1']:.3f} v120 {s['v120']:.3f} sig {s['sig_picks']:.3f} c7/crep "
                      f"{s['c7_bp']:.1f}/{s['crep_bp']:.1f}")
            e = w7_edges(p)
            print(f"      picks' true a7 edge (bp), sessions 1-10 / 51-60 / 111-120: {e}")


def w7_edges(parts):
    out = []
    for k in ("1-10", "51-60", "111-120"):
        v = [q["edge7_bp"][k] for q in parts if k in q["edge7_bp"] and q["edge7_bp"][k] == q["edge7_bp"][k]]
        out.append(round(float(np.mean(v)), 1) if v else None)
    return out


if __name__ == "__main__":
    main()

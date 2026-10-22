#!/usr/bin/env python
"""verify_cited.py: recompute, from the judge's and the checks' own stored outputs, the figures PREREG-EVL-6 cites from
them (synthetic only; reads no lane data).

(a) PREREG-EVL-3's screen alone (its skew check and retirement included, as calib_judge.py ran it) at the judge's
    worst plausible cell, on the judge's arrays (judge/arrays, via judge/search_judge.py), and the union of the judge's
    draft rule with it at lag 3;
(b) PREREG-EVL-3's screen alone on check 2's fresh seeds (check2/run1.jsonl, run3.jsonl: the 'old' first passes);
(d) PREREG-EVL-3's screen alone and the judge's draft on the judge's power arrays (speed);
(e) WSP-IUT's absolute part on the judge's grid, from the judge's search output;
(c) the draft rule's fresh-seed replicates at the corner (check 1: check1/c1all.index.jsonl, c1E.index.jsonl; check 2:
    check2/run1.jsonl, run3.jsonl, run7.jsonl).
"""
import json
import math
import os
import sys

import numpy as np

EVL6 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(EVL6, "judge"))
import report_judge as RJ  # noqa: E402
import search_judge as SJ  # noqa: E402

RJ.AGG = os.path.join(EVL6, "judge", "arrays")
DRAFT = ("mlist:6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60", "step:0.016:20:0.004", 0.001, "full", True)


def se(p, n):
    return math.sqrt(p * (1 - p) / n)


def part_a():
    meta = RJ._meta()
    best_old = (0, None)
    best_union = (0, None)
    for m in meta:
        if not (RJ.is_null(m) and RJ.plausible(m)):
            continue
        d = dict(np.load(m["path"]))
        old = float(np.mean((d["old"] >= 1) & (d["old"] <= 120)))
        un = SJ.rate(SJ.combined(d, 3, DRAFT, "union"), 120)
        if old > best_old[0]:
            best_old = (old, RJ.lab(m), m["R"])
        if un > best_union[0]:
            best_union = (un, RJ.lab(m), m["R"])
    print(f"(a) judge's arrays: PREREG-EVL-3 alone, worst plausible {best_old[0]:.4f} (se {se(best_old[0], best_old[2]):.4f})"
          f" [{best_old[1]}]")
    print(f"(a) judge's arrays: the union with the draft rule (lag 3), worst plausible {best_union[0]:.4f} [{best_union[1]}]")


def part_bc():
    c2 = os.path.join(EVL6, "check2")
    for f in ("run1.jsonl", "run3.jsonl"):
        rows = [json.loads(l) for l in open(os.path.join(c2, f))]
        groups = {}
        for r in rows:
            k = (r["cell"], r["gen"].get("nbar"), r["gen"].get("rho_day"), r["gen"].get("phi_day", 0.10))
            groups.setdefault(k, []).append(r)
        for k in sorted(groups):
            rs = groups[k]
            n = sum(len(r["L0"]) for r in rs)
            new = sum(sum(1 for x in r["L0"] if x <= 120) for r in rs) / n
            line = f"(c) check2/{f} {k}: draft rule lag 0 {new:.4f} (se {se(new, n):.4f}, R {n})"
            if "old" in rs[0]:
                old = sum(sum(1 for x in r["old"] if 1 <= x <= 120) for r in rs) / n
                line += f" | (b) PREREG-EVL-3 alone {old:.4f} (se {se(old, n):.4f})"
            print(line)
    for f in ("run7.jsonl",):
        rows = [json.loads(l) for l in open(os.path.join(c2, f))]
        groups = {}
        for r in rows:
            k = (r["cell"], r["gen"].get("nbar"), r["gen"].get("rho_day"), r["gen"].get("phi_day", 0.10))
            groups.setdefault(k, []).append(r)
        for k in sorted(groups):
            rs = groups[k]
            for name in ("R0", "R4_strict", "R9_tri"):
                if name not in rs[0]:
                    continue
                n = sum(len(r[name]) for r in rs)
                v = sum(sum(1 for x in r[name] if x <= 120) for r in rs) / n
                print(f"(c) check2/{f} {k} {name}: {v:.4f} (se {se(v, n):.4f}, R {n})")
    c1 = os.path.join(EVL6, "check1")
    for idx in ("c1all.index.jsonl", "c1E.index.jsonl"):
        rows = [json.loads(l) for l in open(os.path.join(c1, idx))]
        groups = {}
        for r in rows:
            if not r["cell"].startswith(("A|N3|both|AR20", "A2|N3|both|AR20", "C|N3|both|AR20|phi.20")):
                continue
            groups.setdefault((r["cell"], r["gen"]["nbar"]), []).append(r)
        for k in sorted(groups):
            ds = [dict(np.load(r["path"])) for r in groups[k] if os.path.exists(r["path"])]
            if len(ds) < len(groups[k]):
                print(f"(c) check1/{idx} {k}: arrays not on disk")
                continue
            d = {kk: np.concatenate([x[kk] for x in ds]) for kk in ds[0]}
            v = SJ.rate(SJ.combined(d, 0, DRAFT, "alone"), 120)
            n = d["L0_Sat"].shape[0]
            print(f"(c) check1/{idx} {k}: draft rule lag 0 {v:.4f} (se {se(v, n):.4f}, R {n})")


def part_d():
    """(d) PREREG-EVL-3's screen alone and the judge's draft rule on the judge's POWER arrays (a true edge on the
    program's events, symmetric, no drift, phi_day 0.10): P(promoted by session h) and E[min(T, 60)]."""
    meta = [m for m in RJ._meta() if m["phase"] == "power"]
    for sk in (60, 100):
        for rho in (0.0, 0.05, 0.15):
            rows = []
            for m in sorted(meta, key=lambda m: -m["gen"]["nbar"]):
                g = m["gen"]
                if round(g["skill"] * 1e4) != sk or abs(g["rho_day"] - rho) > 1e-9:
                    continue
                d = dict(np.load(m["path"]))
                old = np.where(d["old"] >= 1, d["old"].astype(np.int64), 10 ** 6)
                new = SJ.combined(d, 0, DRAFT, "alone")
                new = np.where(new >= 1, new, 10 ** 6)
                rows.append((g["nbar"], {h: float(np.mean(old <= h)) for h in (8, 10, 15, 20, 40, 60)},
                             float(np.mean(np.minimum(old, 60))), float(np.mean(np.minimum(new, 60)))))
            if not rows:
                continue
            for nb, pw, e60, e60n in rows:
                print(f"(d) {sk} bp rho {rho:.2f} n {nb:g}: PREREG-EVL-3 alone by 8/10/15/20/40/60 "
                      + "/".join(f"{pw[h]:.3f}" for h in (8, 10, 15, 20, 40, 60)) + f" E60 {e60:.1f} | draft E60 {e60n:.1f}")
            mean = {h: float(np.mean([r[1][h] for r in rows])) for h in (8, 10, 15, 20, 40, 60)}
            print(f"(d) {sk} bp rho {rho:.2f} MEAN OVER THE FIVE RATES: PREREG-EVL-3 alone by 8/10/15/20/40/60 "
                  + "/".join(f"{mean[h]:.3f}" for h in (8, 10, 15, 20, 40, 60))
                  + f" E60 {np.mean([r[2] for r in rows]):.2f} | the judge's draft E60 {np.mean([r[3] for r in rows]):.2f}")


def part_e():
    """(e) WSP-IUT's absolute part (a look at every block from the 6th, alpha c / S to 120 blocks, no margin) as the judge
    measured it on its own grid (judge/search_alone_L0_main.jsonl: worst plausible, and P(promoted by the 20th
    session) at 60 bp, rho_day 0.05, the mean over the five rates)."""
    for l in open(os.path.join(EVL6, "judge", "search_alone_L0_main.jsonl")):
        r = json.loads(l)
        sched, a, m0, g, ret = r["rule"]
        if sched == "every:6:120" and m0 == 0.0 and g == "full" and ret:
            print(f"(e) WSP-IUT absolute part, {a}, no margin: worst plausible {r['worst'][0]:.4f} [{r['worst'][1].strip()}]"
                  f", 60 bp by session 20 {r['s20']:.3f}")


if __name__ == "__main__":
    part_bc()
    part_a()
    part_d()
    part_e()

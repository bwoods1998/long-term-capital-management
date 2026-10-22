#!/usr/bin/env python
"""select_w9ff.py: the selection protocol of the final minimal fix (re-check 1's fix (b)). SYNTHETIC ONLY.
  select   EVERY warm cell of ff.search.jsonl within 0.05 of the warm search maximum (no cap) -> ff.selected1.json
  select2  every cell of ff.fresh1.jsonl (1,000 fresh programs) within 0.03 of the round-1 maximum -> ff.selected2.json
  w9       W9 = the maximum fresh per-run rate (round 1 and round 2 pooled per cell); the worst cell of each learner
           (-> ff.lifecells.json) and their cold twins at the same pool (-> ff.coldcells.json); c9 = max(0.13, W9
           rounded up to 0.01)
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w9ff as f  # noqa: E402

w = f.w


def table(by, keys=None):
    rows = []
    for name, parts in by.items():
        if keys is not None and name not in keys:
            continue
        s = w.summarise(parts)
        rows.append((s["run1"], name, s, parts[0]["spec"]))
    rows.sort(key=lambda x: -x[0])
    return rows


def show(rows, label):
    print(f"== {label}")
    for r1, name, s, spec in rows:
        print(f"{name:<74} R={s['R']:<5} RUN1 {r1:.4f} (se {s['run1_se']:.4f}) v120 {s['v120']:.4f} cm<=0 "
              f"{s['cm0']:.4f} cm<=10bp {s['cm10']:.4f} ev/s {s['ev_s']:.2f} tau {s['tau_bp']:+.1f}bp uhz {s['uhz']:.2f}")


def select():
    by = f.load("search")
    rows = table(by)
    warm = [r for r in rows if r[3]["hist"] == "warm"]
    mx = warm[0][0]
    sel = [r[1] for r in warm if r[0] >= mx - 0.05 - 1e-12]
    show(rows, f"search (200 programs a cell, seeds 861e6 +): warm maximum {mx:.4f} ({warm[0][1]}); "
               f"{len(sel)} warm cells within 0.05 of it re-run fresh")
    json.dump(sel, open(os.path.join(HERE, "ff.selected1.json"), "w"), indent=0)
    print("SELECTED", len(sel))


def select2():
    by = f.load("fresh1")
    rows = table(by)
    mx = rows[0][0]
    sel = [r[1] for r in rows if r[0] >= mx - 0.03 - 1e-12]
    show(rows, f"fresh round 1 (1,000 programs a cell, seeds 862e6 +): maximum {mx:.4f}; {len(sel)} cells within 0.03 "
               f"of it get 1,000 more")
    json.dump(sel, open(os.path.join(HERE, "ff.selected2.json"), "w"), indent=0)
    print("SELECTED2", len(sel))


def w9():
    b1, b2, bs = f.load("fresh1"), f.load("fresh2"), f.load("search")
    pooled = {n: b1[n] + b2.get(n, []) for n in b1}
    rows = table(pooled)
    print("== fresh (round 1 + round 2 pooled per cell; never searched or chosen)")
    for r1, name, s, spec in rows:
        ss = w.summarise(bs[name])
        r2 = w.summarise(b2[name])["run1"] if name in b2 else float("nan")
        print(f"{name:<74} FRESH {r1:.4f} (se {s['run1_se']:.4f}, R {s['R']}) round1 {w.summarise(b1[name])['run1']:.4f}"
              f" round2 {r2:.4f} | search {ss['run1']:.3f} | pooled-with-search "
              f"{(r1 * s['R'] + ss['run1'] * ss['R']) / (s['R'] + ss['R']):.4f} | v120 {s['v120']:.4f} cm<=0 "
              f"{s['cm0']:.4f} cm<=10bp {s['cm10']:.4f} ev/s {s['ev_s']:.2f} tau {s['tau_bp']:+.1f}bp")
    W9 = rows[0][0]
    c9 = max(0.13, math.ceil(W9 * 100 - 1e-9) / 100)
    print(f"W9 = {W9:.4f} ({rows[0][1]}, se {rows[0][2]['run1_se']:.4f}, R {rows[0][2]['R']}); c9 = max(0.13, "
          f"{math.ceil(W9 * 100 - 1e-9) / 100:.2f}) = {c9:.2f}")
    for L in ("ON", "O1"):
        lr = [r for r in rows if r[3]["learner"] == L]
        if lr:
            print(f"worst {L}: {lr[0][1]} {lr[0][0]:.4f} (se {lr[0][2]['run1_se']:.4f})")
        plaus = [r for r in lr if not r[3]["adv"]]
        if plaus:
            print(f"worst {L} without an adversarial prior: {plaus[0][1]} {plaus[0][0]:.4f} (se {plaus[0][2]['run1_se']:.4f})")
    life, cold = [], []
    for L in ("ON", "O1"):
        lr = [r for r in rows if r[3]["learner"] == L]
        if not lr:
            continue
        life.append(lr[0][1])
        spec = lr[0][3]
        cn = w.mk(learner=L, hist="cold", nbar=spec["nbar"], **f.WORST).name
        cold.append(cn)
    json.dump(life, open(os.path.join(HERE, "ff.lifecells.json"), "w"))
    json.dump(cold, open(os.path.join(HERE, "ff.coldcells.json"), "w"))
    print("LIFE", life, "COLD", cold)


if __name__ == "__main__":
    {"select": select, "select2": select2, "w9": w9}[sys.argv[1]]()

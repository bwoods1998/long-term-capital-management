#!/usr/bin/env python
"""select_w9.py: the protocol that names W9's worst cells (synthetic; reads only calib_w9.py's own outputs).

STEP 1 (SEARCH seeds 401,000,001 +, w9.search.jsonl, 200 programs a cell): every null cell of the search grid is in
PREREG-EVL-6's frozen plausible set (rho_day <= 0.15, phi_day <= 0.20, the five day shapes, drift <= 20 bp AR 0.97,
issuer effects 1%, counts independent of the day or following it, pools 300 / 600, symmetric or left-skewed events) and
in this file's own history set (noise history, decayed history edges, drift along the learner's own history direction,
the own-return issuer slope, adversarial priors, the knife edge), for each learner at its own lag (O1 1, ON 2), with the
shape guard. The COLD cells (PREREG-EVL-7's learner on the same paths) are references and never selected. The CHAR20
cells are a STRESS (a drift of 20 bp a session per unit of the history index is about 39 bp a session at a decayed-edge
learner's picks, whose mean index sits 1.9 pool sd above the pool's: beyond PREREG-EVL-6's 20 bp ceiling and its own
30 bp stress); CHAR10 (about 19 bp at the picks) is the plausible ceiling. The worst CHAR20 cell is re-run on fresh seeds
beside.
STEP 2: the warm cells whose search per-run rate is within 4.0 points of the search maximum (about two standard errors
at 200 programs), at most 6, the highest first, are written to w9.selected.json.
STEP 3 (run_w9b.sh): those cells are re-run on FRESH seeds (402,000,001 +), 2,000 programs each (the reference cells, cold twins of PREREG-EVL-7's learner on the same
paths, the base model and the CHAR20 stress, 600 programs each from 402,500,001, never in W9); W9 is the maximum of
their fresh per-run rates (no fresh figure chose anything); the pooled figure (search + fresh) is printed beside.
Usage: select_w9.py select | w9
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w9 as w  # noqa: E402

BAND = 0.040
MAXC = 6


def select():
    by = w.load("search")
    rows = []
    stress = []
    for name, parts in by.items():
        if "-cold-" in name:
            continue
        if "-CHAR20-" in name:      # a STRESS: 20 bp a unit of the history index is about 39 bp a session at the picks
            stress.append((w.summarise(parts)["run1"], name, parts[0]["spec"]))   # (their mean index is 1.9 pool sd
            continue                                                               # above the pool's), beyond the
                                                                                   # frozen grid's 20 bp ceiling
        s = w.summarise(parts)
        rows.append((s["run1"], s["R"], name, parts[0]["spec"]))
    rows.sort(key=lambda x: -x[0])
    top = rows[0][0]
    sel = [r for r in rows if r[0] >= top - BAND][:MAXC]
    print(f"search: {len(rows)} warm cells; maximum per-run rate {top:.4f} ({rows[0][2]}); band {BAND}; selected {len(sel)}")
    for r in rows[:30]:
        mark = "*" if r in sel else " "
        print(f" {mark} {r[0]:.4f} (se {math.sqrt(max(r[0] * (1 - r[0]), 1e-9) / r[1]):.4f}) {r[2]}")
    spec = []
    for r in sel:
        d = dict(r[3])
        d["name"] = r[2]
        spec.append(d)
    json.dump(spec, open(os.path.join(HERE, "w9.selected.json"), "w"))
    refs, seen = [], set()
    for d in spec:
        if d["learner"] in seen:
            continue
        seen.add(d["learner"])
        c = dict(d)
        c.update(hist="cold", ic_h=0.0, drift_c=0.0, tauh=False, adv="")
        c["name"] = w.nm(w.W9(**c))
        refs.append(c)
    stress.sort(key=lambda x: -x[0])
    for run1, name, sp in stress[:1]:     # the worst CHAR20 cell, re-run on fresh seeds as a named stress
        d = dict(sp)
        d["name"] = name
        refs.append(d)
        print(f"stress re-run on fresh seeds: {name} (search {run1:.4f})")
    for name, parts in by.items():        # the base model's cells, for the report's base figure
        if "-t3-sym-rho05-phi10-dr00-tau0-" in name and "-cold-" not in name:
            d = dict(parts[0]["spec"])
            d["name"] = name
            refs.append(d)
    json.dump(refs, open(os.path.join(HERE, "w9.refs.json"), "w"))
    print("cold references for the fresh seeds:", [r["name"] for r in refs])


def w9():
    sel = json.load(open(os.path.join(HERE, "w9.selected.json")))
    a = w.load("search")
    f = w.load("fresh")
    if os.path.exists(os.path.join(HERE, "w9.freshref.jsonl")):
        f.update(w.load("freshref"))
    out = []
    for name, parts in f.items():
        s = w.summarise(parts)
        sa = w.summarise(a[name]) if name in a else dict(run1=0.0, R=0)
        pooled = (s["run1"] * s["R"] + sa["run1"] * sa["R"]) / (s["R"] + sa["R"])  # search + fresh
        se_p = math.sqrt(pooled * (1 - pooled) / (s["R"] + sa["R"]))
        out.append((s["run1"], s["run1_se"], s["R"], name, sa["run1"], pooled, se_p, s))
    out.sort(key=lambda x: -x[0])
    isref = lambda n: "-cold-" in n or "-t3-sym-rho05-phi10-dr00-tau0-" in n or "-CHAR20-" in n  # noqa: E731
    ref = [o for o in out if isref(o[3])]
    out = [o for o in out if not isref(o[3])]
    print(f"fresh seeds: {len(out)} cells of {len(sel)} selected (and {len(ref)} reference cells: cold twins, the base model and the CHAR20 stress, never in W9)")
    for o in ref:
        print(f"  REFERENCE fresh {o[0]:.4f} (se {o[1]:.4f}, R {o[2]}) | search {o[4]:.4f} | {o[3]}")
    for o in out:
        s = o[7]
        print(f"  fresh {o[0]:.4f} (se {o[1]:.4f}, R {o[2]}) | search {o[4]:.4f} | pooled {o[5]:.4f} (se {o[6]:.4f}) | "
              f"version by 120 {s['v120']:.4f} | true mean a <= 0 at the pass {s['cm0']:.4f} | ev/s {s['ev_s']:.2f} | "
              f"{o[3]}")
    W9 = out[0][0]
    c9 = max(0.13, math.ceil(round(W9 * 100, 9)) / 100.0)
    print(f"W9 (the maximum fresh per-run rate) = {W9:.4f} at {out[0][3]}; its pooled figure {out[0][5]:.4f}")
    print(f"c9 = max(0.13, W9 rounded up to two decimals) = {c9:.2f}")


if __name__ == "__main__":
    {"select": select, "w9": w9}[sys.argv[1]]()

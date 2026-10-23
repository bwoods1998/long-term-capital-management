#!/usr/bin/env python
"""select_w7.py: the protocol that names W7's worst cells (synthetic; reads only calib_w7.py's own outputs).

STEP 1 (search seeds, w7.search.jsonl: 1,000 programs a cell for grid cells 0-19, 500 for the rest, run_w7.sh): every cell of the search grid is in PREREG-EVL-6's
plausible set (rho_day <= 0.15, phi_day <= 0.20, the five day shapes, drift <= 20 bp, issuer effects 1%, counts
independent of the day or following it, pools 300 / 800, lags 1 / 2, the no-information and knife-edge nulls).
STEP 2: the cells whose search-seed per-run rate is within 3.0 points of the search maximum (about three standard
errors at 1,000 programs, about 2.3 at 500), at most 8 (the highest first), are written to w7.selected.json.
STEP 3 (run_w7c.sh): those cells are re-run on FRESH seeds (202,000,001 +), 4,000 programs each; W7 is the maximum of
their fresh per-run rates (no fresh figure chose anything); the pooled figure (search + fresh) is printed beside.
Usage: select_w7.py select | w7
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w7 as w  # noqa: E402

BAND = 0.030
MAXC = 8


def load(name):
    by = {}
    for line in open(os.path.join(HERE, f"w7.{name}.jsonl")):
        r = json.loads(line)
        by.setdefault(r["cell"], []).append(r)
    return by


def select():
    by = load("search")
    w.grid("search")            # the cells' specs, rebuilt from the grid (the search's workers recorded none)
    rows = []
    for name, parts in by.items():
        s = w.summarise(parts)
        rows.append((s["run1"], s["R"], name, w.SPECS[name]))
    rows.sort(key=lambda x: -x[0])
    top = rows[0][0]
    sel = [r for r in rows if r[0] >= top - BAND][:MAXC]
    print(f"search: {len(rows)} cells; maximum per-run rate {top:.4f} ({rows[0][2]}); band {BAND}; selected {len(sel)}")
    for r in rows[:25]:
        mark = "*" if r in sel else " "
        print(f" {mark} {r[0]:.4f} (se {math.sqrt(r[0] * (1 - r[0]) / r[1]):.4f}) {r[2]}")
    json.dump([r[3] for r in sel], open(os.path.join(HERE, "w7.selected.json"), "w"))


def w7():
    sel = json.load(open(os.path.join(HERE, "w7.selected.json")))
    a = load("search")
    f = load("fresh")
    out = []
    for name, parts in f.items():
        s = w.summarise(parts)
        sa = w.summarise(a[name])
        pooled = (s["run1"] * s["R"] + sa["run1"] * sa["R"]) / (s["R"] + sa["R"])
        se_p = math.sqrt(pooled * (1 - pooled) / (s["R"] + sa["R"]))
        out.append((s["run1"], s["run1_se"], s["R"], name, sa["run1"], pooled, se_p, s))
    out.sort(key=lambda x: -x[0])
    print(f"fresh seeds: {len(out)} cells of {len(sel)} selected")
    for o in out:
        s = o[7]
        print(f"  fresh {o[0]:.4f} (se {o[1]:.4f}, R {o[2]}) | search {o[4]:.4f} | pooled {o[5]:.4f} (se {o[6]:.4f}) | "
              f"version by 120 {s['v120']:.4f} | true cm<=0 {s['cm0']:.4f} <=10bp {s['cm10']:.4f} | {o[3]}")
    W7 = out[0][0]
    c7 = max(0.13, math.ceil(round(W7 * 100, 9)) / 100.0)
    print(f"W7 (the maximum fresh per-run rate) = {W7:.4f} at {out[0][3]}; its pooled figure {out[0][5]:.4f}")
    print(f"c7 = max(0.13, W7 rounded up to two decimals) = {c7:.2f}")


if __name__ == "__main__":
    {"select": select, "w7": w7}[sys.argv[1]]()

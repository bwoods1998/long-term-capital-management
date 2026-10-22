#!/usr/bin/env python
"""select_w7r.py: the protocol that names W7's worst cells ON THE REGISTERED COLUMNS (the final fix round; synthetic;
reads only calib_w7r.py's own outputs). Written before any search figure of this round existed.

STEP 1 (search seeds 501,000,001 +, w7r.search.jsonl, 400 programs a cell): the frozen plausible grid as each learner
meets it, both learners (EVL-LRN-O1 at D 52, EVL-LRN-ON at D 58 with dmove from its own returns; r1 / r5 / r20 and the two
levels deleted), both training lags, pools 300 and 800 (calib_w7r.grid('search'): 42 cells, of which the two with counts that
follow the day at pool 800 cannot be drawn in the lens's 3,000-issuer universe and are skipped: 40 run).
STEP 2: the TOP CELL OF EACH (lag, pool) GROUP (re-check 1: both lags, pools 300 AND 800), then the other cells whose
search-seed per-run rate is within 3.0 points of the search maximum (the fix round's band), highest first, up to 6 cells
in all (a pool-800 cell costs four to five times a pool-300 cell on the shared machine), are written to
w7r.selected.json.
STEP 3: those cells on FRESH seeds (502,000,001 +) that searched and chose nothing, 4,000 programs each; W7 is the
maximum of their fresh per-run rates; the pooled figure (search + fresh) is printed beside.
Usage: select_w7r.py select | w7
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w7r as w  # noqa: E402

BAND = 0.030
MAXC = 6


def select():
    by = w.load("search")
    rows = []
    for name, parts in by.items():
        s = w.summarise(parts)
        sp = parts[0]["spec"]
        rows.append((s["run1"], s["R"], name, sp))
    rows.sort(key=lambda x: -x[0])
    top = rows[0][0]
    sel = []
    for lag in (1, 2):
        for pool in (300, 800):
            g = [r for r in rows if r[3]["lag"] == lag and r[3]["pool"] == pool]
            if g and g[0] not in sel:
                sel.append(g[0])
    for r in rows:
        if len(sel) >= MAXC:
            break
        if r[0] >= top - BAND and r not in sel:
            sel.append(r)
    sel.sort(key=lambda x: -x[0])
    print(f"search: {len(rows)} cells; maximum per-run rate {top:.4f} ({rows[0][2]}); band {BAND}; selected {len(sel)} "
          f"(the top of each (lag, pool) group, then the band, at most {MAXC})")
    for r in rows:
        mark = "*" if r in sel else " "
        print(f" {mark} {r[0]:.4f} (se {math.sqrt(r[0] * (1 - r[0]) / r[1]):.4f}, R {r[1]}) {r[2]}")
    json.dump([r[3] for r in sel], open(os.path.join(HERE, "w7r.selected.json"), "w"))


def w7():
    sel = json.load(open(os.path.join(HERE, "w7r.selected.json")))
    a = w.load("search")
    f = w.load("fresh")
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
              f"version by 120 {s['v120']:.4f} | true cm<=0 {s['cm0']:.4f} <=10bp {s['cm10']:.4f} | picks' issuer "
              f"effect {s['tau_bp']:+.1f} bp, sigma {s['sig_picks']:.3f}, COST-7 / replay {s['c7_bp']:.1f} / {s['crep_bp']:.1f} bp | {o[3]}")
    W7 = out[0][0]
    c7 = max(0.13, math.ceil(round(W7 * 100, 9)) / 100.0)
    print(f"W7 (the maximum fresh per-run rate) = {W7:.4f} at {out[0][3]}; its pooled figure {out[0][5]:.4f}")
    print(f"c7 = max(0.13, W7 rounded up to two decimals) = {c7:.2f}")
    print("seatable (W7 <= 0.15):", W7 <= 0.15)
    for L, lag in (("O1", 1), ("ON", 2)):
        mine = [o for o in out if o[3].startswith(L + "-") and f"-lag{lag}" in o[3]]
        if mine:
            print(f"at its real lag, {L} (lag {lag}): worst fresh {mine[0][0]:.4f} at {mine[0][3]}")


def top(which):
    """The fresh stage's worst cell at each lag (life: both; sens: the overall worst only), as calib_w7r specs."""
    f = w.load("fresh")
    rows = sorted(((w.summarise(p)["run1"], p[0]["spec"]) for p in f.values()), key=lambda x: -x[0])
    out = []
    for lag in (1, 2):
        g = [sp for r, sp in rows if sp["lag"] == lag]
        if g:
            out.append(g[0])
    if which == "sens":
        out = [rows[0][1]]
    print(json.dumps(out))


if __name__ == "__main__":
    if sys.argv[1] == "top":
        top(sys.argv[2])
    else:
        {"select": select, "w7": w7}[sys.argv[1]]()

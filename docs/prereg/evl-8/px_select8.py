#!/usr/bin/env python
"""px_select8.py: the captain's F1 protocol for THE PX SCREEN's first look (SYNTHETIC ONLY; reads only px_final8.py's
outputs). Written before any fresh-seed figure existed.

  plan     the search seeds (px8f.search.jsonl, 1,000 programs a cell over the whole PX plausible grid) give each
           candidate first look F in (22, 25, 30, 35, 40) its worst plausible rate; every cell within 3.5 points of
           F's search worst (at most the 60 nearest, for F in 22, 25, 30) is re-run on FRESH seeds at 4,000 programs
           (px8f.fresh.cells.jsonl; px_final8.py run --phase fresh --cells ...).
  choose   THE RULE OF F1: the EARLIEST F whose worst plausible per-run false-pass rate within 120 sessions is <= 0.13,
           the worst being the maximum of the fresh-seed rates of the re-run cells and the search-seed rates of every
           other plausible cell (px8f.choose.json). Nothing else in the rule is chosen.
  confirm  the chosen F's 16 worst fresh cells, re-run on CONFIRMATION seeds that chose nothing (4,000 programs each:
           px8f.confirm.cells.jsonl; px_final8.py run --phase confirm --cells ...).
Usage: px_select8.py plan | choose | confirm-plan
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STARTS = (22, 25, 30, 35, 40)
CAP_FP = 0.13
NEAR = 0.035
MAXN = 60


def load(phase):
    return [json.loads(l) for l in open(os.path.join(HERE, f"px8f.{phase}.jsonl"))]


def worst(rows, f):
    best = max(rows, key=lambda r: r[f"F{f}"]["fp120"])
    return best[f"F{f}"]["fp120"], best["cell"]


def plan():
    rows = load("search")
    chosen = {}
    out = []
    for f in STARTS:
        w, lab = worst(rows, f)
        near = sorted([r for r in rows if r[f"F{f}"]["fp120"] >= w - NEAR], key=lambda r: -r[f"F{f}"]["fp120"])
        print(f"F={f}: search worst {w:.4f} [{lab}], {len(near)} cells within {NEAR}")
        if f in (22, 25, 30):
            for r in near[:MAXN]:
                chosen[r["cell"]] = r["spec"]
    with open(os.path.join(HERE, "px8f.fresh.cells.jsonl"), "w") as fh:
        for lab, spec in sorted(chosen.items()):
            fh.write(json.dumps(spec) + "\n")
            out.append(lab)
    print(f"{len(out)} cells to the fresh seeds")


def choose():
    search = {r["cell"]: r for r in load("search")}
    fresh = {r["cell"]: r for r in load("fresh")}
    table = []
    pick = None
    for f in STARTS:
        wf = max(((r[f"F{f}"]["fp120"], c) for c, r in fresh.items()), default=(0.0, None))
        rest = [(r[f"F{f}"]["fp120"], c) for c, r in search.items() if c not in fresh]
        wr = max(rest, default=(0.0, None))
        ws = max(((r[f"F{f}"]["fp120"], c) for c, r in search.items()), default=(0.0, None))
        w = max(wf, wr)
        row = {"first_look": f, "worst": w[0], "worst_cell": w[1], "worst_fresh": wf[0], "worst_fresh_cell": wf[1],
               "se_fresh": (wf[0] * (1 - wf[0]) / 4000) ** 0.5, "worst_rest_search": wr[0], "worst_rest_cell": wr[1],
               "worst_search_all": ws[0], "worst_search_cell": ws[1], "holds": w[0] <= CAP_FP}
        table.append(row)
        if pick is None and row["holds"]:
            pick = f
    res = {"rule": "the earliest first look whose worst plausible rate (fresh where re-run, else search) <= 0.13",
           "table": table, "chosen_first_look": pick}
    json.dump(res, open(os.path.join(HERE, "px8f.choose.json"), "w"), indent=1)
    for row in table:
        print(json.dumps(row))
    print("CHOSEN FIRST LOOK:", pick)


def confirm_plan():
    ch = json.load(open(os.path.join(HERE, "px8f.choose.json")))
    f = ch["chosen_first_look"]
    fresh = load("fresh")
    top = sorted(fresh, key=lambda r: -r[f"F{f}"]["fp120"])[:16]
    with open(os.path.join(HERE, "px8f.confirm.cells.jsonl"), "w") as fh:
        for r in top:
            fh.write(json.dumps(r["spec"]) + "\n")
            print(f"{r[f'F{f}']['fp120']:.4f} {r['cell']}")


if __name__ == "__main__":
    {"plan": plan, "choose": choose, "confirm-plan": confirm_plan}[sys.argv[1]]()

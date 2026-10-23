#!/usr/bin/env python
"""select_final.py: the selection protocol of PREREG-EVL-6's final rule (synthetic only).

STEP 1 (search seeds, s1null + s1power, 1,000 programs a cell): every candidate of search_final.candidates() is
measured (search_s1.jsonl). The SHORTLIST: the candidates on the speed / worst-plausible frontier (no other candidate
both faster at 60 bp and no worse at the worst plausible cell) with a search-seed worst plausible <= SHORT_CAP (the
search seeds' maximum over about 400 cells of 1,000 programs reads high by about two standard errors, so the cap sits
above 0.13), plus the checks' named candidates.
STEP 2 (FRESH seeds, s2null): every plausible cell whose search-seed rate for ANY shortlisted rule is within NEAR of
that rule's search-seed worst is re-run at 4,000 programs (s2null.cells.json, written here); the fresh power cells
(s2power, 2,000 programs) give the speed.
STEP 3: THE CHOSEN RULE is the fastest shortlisted rule (E[min(T, 60)] at a true 60 bp edge, rho_day 0.05, the mean
over the five rates, fresh power seeds) whose worst plausible rate within 120 sessions is <= 0.13, the worst being the
maximum of the fresh rates (s2null) and, for every other plausible cell, its search-seed rate.

Usage: select_final.py shortlist | plan | choose
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_final as SF  # noqa: E402

SHORT_CAP = 0.150
NEAR = 0.035
NEAR_HI = 0.020
TARGET = 0.13
NAMED = [SF.Rule(6, ((9, 0.016), (20, 0.012), (60, 0.003))), SF.Rule(7, ((10, 0.016), (20, 0.010), (60, 0.003))),
         SF.Rule(6, ((20, 0.012), (60, 0.003))), SF.Rule(6, ((20, 0.016), (60, 0.004)))]


def rows_s1():
    rows = []
    for f in ("search_s1.jsonl", "search_s1b.jsonl"):     # first looks at 6-8, then 9, 10, 12
        rows += [json.loads(l) for l in open(os.path.join(HERE, f))]
    return rows


def frontier(rows, cap):
    ok = [r for r in rows if r["worst"][0] <= cap and r["speed60"]]
    ok.sort(key=lambda r: (r["speed60"]["E60"], r["worst"][0]))
    out, best_w = [], 9.0
    for r in ok:                         # faster first: keep a rule only if no faster rule is no worse
        if r["worst"][0] < best_w - 1e-12:
            out.append(r)
            best_w = r["worst"][0]
    return out


def shortlist():
    rows = rows_s1()
    fr = frontier(rows, SHORT_CAP)
    named = {r.key() for r in NAMED}
    extra = [r for r in rows if r["rule"] in named and r["rule"] not in {x["rule"] for x in fr}]
    print(f"{len(rows)} rules measured on the search seeds; frontier at worst <= {SHORT_CAP}: {len(fr)}")
    for r in fr + extra:
        s = r["speed60"]
        print(f"  E60 {s['E60']:.2f}  P60bp by 10/20/40 {s['10']:.3f} {s['20']:.3f} {s['40']:.3f}  worst {r['worst'][0]:.4f} "
              f"[{r['worst'][1]}]  base {max(b[1] for b in r['base']):.4f}  | {r['label']}")
    json.dump([r["rule"] for r in fr + extra], open(os.path.join(HERE, "shortlist.json"), "w"), indent=0)
    return fr + extra


def plan(R=4000, seed0=113_000_000):
    """The fresh cells: the union over the shortlist of the plausible cells within NEAR of the rule's worst."""
    rows = {r["rule"]: r for r in rows_s1()}
    short = json.load(open(os.path.join(HERE, "shortlist.json")))
    cells = SF._load(["s1null"], [])
    want = {}
    for key in short:
        rule = SF.Rule.of(key)
        res = SF.evaluate(rule, cells)
        w = res["worst"][0]
        for c in cells:
            if c["cell"].startswith("P") or not SF.plausible(c["cell"], c["gen"]):
                continue
            fp, _, _ = SF.first_pass(c["d"], "", rule, c["tag"])
            v = SF.rate(fp, 120)
            k = (c["cell"], json.dumps(c["gen"], sort_keys=True))
            if v >= w - NEAR:
                want[k] = max(want.get(k, -1.0), v - w)
    # within NEAR_HI of a shortlisted rule's worst: 4,000 programs (and the unweighted variant beside); else 2,000
    spec = [{"lab": cell, "gen": json.loads(gen), "R": R if gap >= -NEAR_HI else R // 2, "T": 120,
             "opts": {"run2": True, "unweighted": gap >= -NEAR_HI}}
            for (cell, gen), gap in sorted(want.items())]
    json.dump(spec, open(os.path.join(HERE, "s2null.cells.json"), "w"), indent=0)
    print(f"{len(spec)} fresh cells: {sum(1 for s in spec if s['R'] == R)} at {R} programs, the rest at {R // 2}")
    for s in spec:
        print("  ", s["lab"], s["gen"]["nbar"], s["gen"]["rho_day"], s["R"])


def choose(out_path=None):
    short = json.load(open(os.path.join(HERE, "shortlist.json")))
    s1 = SF._load(["s1null"], [])
    s2 = SF._load(["s2null"], [])
    pw = SF._load([], ["s2power"])
    fresh_keys = {(c["cell"], json.dumps(c["gen"], sort_keys=True)) for c in s2}
    table = []
    for key in short:
        rule = SF.Rule.of(key)
        r2 = SF.evaluate(rule, s2)
        rest = [c for c in s1 if (c["cell"], json.dumps(c["gen"], sort_keys=True)) not in fresh_keys]
        r1 = SF.evaluate(rule, rest)
        rp = SF.evaluate(rule, pw)
        sp = SF.speed(rp, 60)
        worst = max(r2["worst"], r1["worst"], key=lambda x: x[0])
        table.append({"rule": key, "label": rule.label(), "worst_fresh": r2["worst"], "worst_rest_s1": r1["worst"],
                      "worst": worst, "speed60": sp, "speed100": SF.speed(rp, 100)})
    table.sort(key=lambda r: r["speed60"]["E60"])
    chosen = next((r for r in table if r["worst"][0] <= TARGET + 1e-12), None)
    for r in table:
        s = r["speed60"]
        flag = "CHOSEN" if r is chosen else ("ok" if r["worst"][0] <= TARGET + 1e-12 else "over")
        print(f"{flag:6s} E60 {s['E60']:.2f} P60 by 10/20/40 {s[10]:.3f}/{s[20]:.3f}/{s[40]:.3f} | worst fresh "
              f"{r['worst_fresh'][0]:.4f} [{r['worst_fresh'][1]}] rest(s1) {r['worst_rest_s1'][0]:.4f} | {r['label']}")
    json.dump({"table": table, "chosen": chosen}, open(out_path or os.path.join(HERE, "chosen.json"), "w"), indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "shortlist":
        shortlist()
    elif cmd == "plan":
        plan()
    else:
        choose()

#!/usr/bin/env python
"""select_v2.py: the selection protocol of D14 (D1's, re-run on the widened grid; synthetic only).

STEP 1, SEARCH SEEDS (s1null and calib_v2's w1, 1,000 programs a cell; s1power for the speed): every candidate of
search_v2.candidates2() (search_v2.jsonl) and, since that pass's frontier sat on its grid's edge, of
search_v2.candidates2b() (search_v2b.jsonl). THE SHORTLIST: the candidates on the search seeds' speed / worst-plausible
frontier with a search-seed worst plausible <= SHORT_CAP (the maximum over about 1,500 cells of 1,000 programs reads
high by two to three standard errors, so the cap sits above 0.13), plus re-check 1's candidate and the previous rule.
STEP 2, SELECTION SEEDS (calib_v2's w2; seeds from 122,000,001): every plausible cell whose search-seed rate for ANY
shortlisted rule is within NEAR of that rule's search-seed worst, at 4,000 programs where within NEAR_HI, else 2,000;
the speed on the fresh power cells (s2power, 2,000 programs a cell).
STEP 3, THE RULE: the fastest shortlisted rule (E[min(T, 60)] at a true 60 bp edge, rho_day 0.05, the mean over the five
rates, s2power) whose worst plausible rate within 120 sessions is <= 0.13, the worst being the maximum of the
selection seeds' rates (w2) and, for every other plausible cell, its search-seed rate.
STEP 4, THE UNSELECTED REPLICATE (calib_v2's w3; seeds from 123,000,001): the chosen rule's worst cells on seeds that
never searched, shortlisted or chose; written by `replicate`, read by report_v2.py.

THE EDGE CHECK: the selection first chose a first look at the 20th block, the largest the two passes searched
(chosen_v2.pass12.json, choose_v2.pass12.log); search_v2.candidates2c() measured first looks at the 22nd and 25th
block on the same search seeds (search_v2c.jsonl), the shortlist was rebuilt on all three passes, `plan_extra` wrote
the selection cells its new rules needed beyond w2's (w2x, seeds from 122,500,001), and the rule was chosen again on
w2 and w2x together.

Usage: select_v2.py shortlist | plan | plan_extra | choose | replicate
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_v2 as SV  # noqa: E402  (sets search_final's plausible set and loader)
import search_final as SF  # noqa: E402

SHORT_CAP = 0.155
NEAR = 0.035
NEAR_HI = 0.020
TARGET = 0.13
NAMED = [SV.RECHECK1, SV.PREV, SV.STRICTEST]
NULL1 = ["s1null", "w1"]


def rows_s1():
    rows = []
    for f in ("search_v2.jsonl", "search_v2b.jsonl", "search_v2c.jsonl"):   # the passes and the edge check
        if os.path.exists(os.path.join(HERE, f)):
            rows += [json.loads(l) for l in open(os.path.join(HERE, f))]
    return rows


def frontier(rows, cap):
    ok = [r for r in rows if r["worst"][0] <= cap and r["speed60"]]
    ok.sort(key=lambda r: (r["speed60"]["E60"], r["worst"][0]))
    out, best_w = [], 9.0
    for r in ok:
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
    json.dump([r["rule"] for r in fr + extra], open(os.path.join(HERE, "shortlist_v2.json"), "w"), indent=0)


SEL = ["w2", "w2x"] if os.path.exists(os.path.join(HERE, "calib_v2.w2x.index.jsonl")) else ["w2"]


def plan(R=4000, extra=False):
    """extra: the cells the shortlisted rules need beyond those w2 already holds (phase w2x, after the edge check)."""
    short = json.load(open(os.path.join(HERE, "shortlist_v2.json")))
    cells = SF._load(NULL1, [])
    want = {}
    for key in short:
        rule = SF.Rule.of(key)
        res = SF.evaluate(rule, cells)
        w = res["worst"][0]
        for c in cells:
            if c["cell"].startswith("P") or not SV.plausible(c["cell"], c["gen"]):
                continue
            fp, _, _ = SF.first_pass(c["d"], "", rule, c["tag"])
            v = SF.rate(fp, 120)
            k = (c["cell"], json.dumps(c["gen"], sort_keys=True))
            if v >= w - NEAR:
                want[k] = max(want.get(k, -1.0), v - w)
    have_ = set()
    if extra:
        have_ = {(c["lab"], json.dumps(c["gen"], sort_keys=True)) for c in json.load(open(os.path.join(HERE, "w2.cells.json")))}
    spec = [{"lab": cell, "gen": json.loads(gen), "R": R if gap >= -NEAR_HI else R // 2, "T": 120,
             "opts": {"run2": True, "unweighted": gap >= -NEAR_HI}}
            for (cell, gen), gap in sorted(want.items()) if (cell, gen) not in have_]
    json.dump(spec, open(os.path.join(HERE, "w2x.cells.json" if extra else "w2.cells.json"), "w"), indent=0)
    print(f"{len(spec)} selection cells: {sum(1 for s in spec if s['R'] == R)} at {R} programs, the rest at {R // 2}")
    for s in spec:
        print("  ", s["lab"], s["gen"]["nbar"], s["gen"]["rho_day"], s["R"])


def choose():
    short = json.load(open(os.path.join(HERE, "shortlist_v2.json")))
    s1 = SF._load(NULL1, [])
    s2 = SF._load(SEL, [])
    pw = SF._load([], ["s2power"])
    sel_keys = {(c["cell"], json.dumps(c["gen"], sort_keys=True)) for c in s2}
    rest = [c for c in s1 if (c["cell"], json.dumps(c["gen"], sort_keys=True)) not in sel_keys]
    table = []
    for key in short:
        rule = SF.Rule.of(key)
        r2 = SF.evaluate(rule, s2)
        r1 = SF.evaluate(rule, rest)
        rp = SF.evaluate(rule, pw)
        worst = max(r2["worst"], r1["worst"], key=lambda x: x[0])
        table.append({"rule": key, "label": rule.label(), "worst_sel": r2["worst"], "worst_rest_s1": r1["worst"],
                      "worst": worst, "speed60": SF.speed(rp, 60), "speed100": SF.speed(rp, 100),
                      "top_sel": sorted([(n["lab"], n["fp"]) for n in r2["nulls"] if n["plaus"]], key=lambda x: -x[1])[:10]})
    table.sort(key=lambda r: r["speed60"]["E60"])
    chosen = next((r for r in table if r["worst"][0] <= TARGET + 1e-12), None)
    for r in table:
        s = r["speed60"]
        flag = "CHOSEN" if r is chosen else ("ok" if r["worst"][0] <= TARGET + 1e-12 else "over")
        print(f"{flag:6s} E60 {s['E60']:.2f} P60 by 10/20/40 {s[10]:.3f}/{s[20]:.3f}/{s[40]:.3f} | worst selection "
              f"{r['worst_sel'][0]:.4f} [{r['worst_sel'][1]}] rest(search) {r['worst_rest_s1'][0]:.4f} "
              f"[{r['worst_rest_s1'][1]}] | {r['label']}")
    json.dump({"table": table, "chosen": chosen}, open(os.path.join(HERE, "chosen_v2.json"), "w"), indent=1)


def replicate(n_cells=16, R=4000):
    """The unselected replicate's cells: the chosen rule's n_cells worst plausible cells on the selection seeds."""
    ch = json.load(open(os.path.join(HERE, "chosen_v2.json")))
    rule = SF.Rule.of(ch["chosen"]["rule"])
    s2 = SF._load(SEL, [])
    rates = []
    for c in s2:
        if not SV.plausible(c["cell"], c["gen"]):
            continue
        fp, _, _ = SF.first_pass(c["d"], "", rule, c["tag"])
        rates.append((SF.rate(fp, 120), c))
    rates.sort(key=lambda x: -x[0])
    spec = [{"lab": c["cell"], "gen": c["gen"], "R": R, "T": 120, "opts": {"run2": True}} for v, c in rates[:n_cells]]
    # after the edge check: w3 (run for the first choice's worst cells) is kept; w3x adds the cells it lacks
    done = set()
    if os.path.exists(os.path.join(HERE, "calib_v2.w3.index.jsonl")):
        done = {(c["lab"], json.dumps(c["gen"], sort_keys=True)) for c in json.load(open(os.path.join(HERE, "w3.cells.pass12.json")))}
    todo = [c for c in spec if (c["lab"], json.dumps(c["gen"], sort_keys=True)) not in done]
    json.dump(todo, open(os.path.join(HERE, "w3x.cells.json" if done else "w3.cells.json"), "w"), indent=0)
    for v, c in rates[:n_cells]:
        k = (c["cell"], json.dumps(c["gen"], sort_keys=True))
        print(f"  {SF.lab(c['cell'], c['gen'], c['T']):64s} selection {v:.4f}" + ("  (in w3)" if k in done else "  (w3x)"))


if __name__ == "__main__":
    {"shortlist": shortlist, "plan": plan, "plan_extra": lambda: plan(extra=True), "choose": choose,
     "replicate": replicate}[sys.argv[1]]()

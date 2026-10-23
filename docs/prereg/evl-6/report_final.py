#!/usr/bin/env python
"""report_final.py: every table of PREREG-EVL-6 section 4 for the chosen rule (synthetic only).

Reads chosen.json (select_final.py) and calib_final.py's arrays: s1null (search seeds), s2null (fresh, the worst
cells at 4,000 programs), s3null (a second fresh replicate of the chosen rule's worst cells, when run), stress, s2power.
Beside the chosen rule it shows, on the same paths, the judge's draft rule (looks from 6, alpha 0.016 / 0.004,
unweighted values, no top-14 guard: variant 'u') and the chosen schedule with unweighted values ('u'), so the effect of
D1 and D4 is visible.

Usage: report_final.py > report_final.txt
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_final as SF  # noqa: E402

DRAFT = SF.Rule(6, ((20, 0.016), (60, 0.004)))


def se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / n)


def have(phase):
    return os.path.exists(os.path.join(HERE, f"calib_final.{phase}.index.jsonl"))


def main():
    ch = json.load(open(os.path.join(HERE, "chosen.json")))
    rule = SF.Rule.of(ch["chosen"]["rule"])
    print(f"THE CHOSEN RULE: {rule.label()}  ({rule.key()})")
    print(f"THE JUDGE'S DRAFT RULE beside it: {DRAFT.label()}, unweighted values, no top-14 guard")
    print()
    print("== THE SELECTION TABLE (select_final.py choose): every shortlisted rule, fastest first")
    for r in ch["table"]:
        s = {str(k): v for k, v in r["speed60"].items()}
        s.update({int(k): v for k, v in s.items() if k.isdigit()})
        print(f"  E60 {s['E60']:.2f} | 60 bp by 10/20/40 {s[10]:.3f}/{s[20]:.3f}/{s[40]:.3f} | worst fresh "
              f"{r['worst_fresh'][0]:.4f} [{r['worst_fresh'][1]}] | other cells (search seeds) {r['worst_rest_s1'][0]:.4f}"
              f" | {r['label']}")
    print()
    s1 = SF._load(["s1null"], [])
    s2 = SF._load(["s2null"], []) if have("s2null") else []
    s3 = SF._load(["s3null"], []) if have("s3null") else []
    fresh_keys = {(c["cell"], json.dumps(c["gen"], sort_keys=True)) for c in s2}

    def rows_for(cells, r, variant="w"):
        out = {}
        for c in cells:
            if c["cell"].startswith("P"):
                continue
            if variant == "u" and "Pu" not in c["d"]:      # (the 2,000-program fresh cells carry no unweighted test)
                out[(c["cell"], json.dumps(c["gen"], sort_keys=True), c["T"])] = (c, {"fp": float("nan"), "R": c["R"]})
                continue
            fp, fr, fe = SF.first_pass(c["d"], "", r, c["tag"], variant)
            row = {"fp": SF.rate(fp, min(120, c["T"])), "R": c["R"], "ret": float(np.mean(fr < SF.NONE)),
                   "end": float(np.mean(fe < SF.NONE))}
            if "Sat_2" in c["d"]:
                _, any_ = SF.two_runs(c["d"], r, c["tag"], variant)
                row["two"] = SF.rate(any_, min(120, c["T"]))
            out[(c["cell"], json.dumps(c["gen"], sort_keys=True), c["T"])] = (c, row)
        return out

    print("== FRESH SEEDS (s2null, 4,000 programs a cell): the worst plausible cells")
    print(f"  {'cell':60s} {'chosen':>15s} {'two runs':>9s} | {'chosen, unweighted':>18s} | {'judge draft':>11s}")
    w2 = rows_for(s2, rule)
    w2u = rows_for(s2, rule, "u")
    d2 = rows_for(s2, DRAFT, "u")
    fresh_worst = (0.0, None)
    for k in sorted(w2, key=lambda k: -w2[k][1]["fp"]):
        c, r = w2[k]
        if SF.plausible(c["cell"], c["gen"]) and r["fp"] > fresh_worst[0]:
            fresh_worst = (r["fp"], SF.lab(c["cell"], c["gen"], c["T"]))
        print(f"  {SF.lab(c['cell'], c['gen'], c['T']):60s} {r['fp']:.4f} ({se(r['fp'], r['R']):.4f}) "
              f"{r.get('two', float('nan')):9.4f} | {w2u[k][1]['fp']:18.4f} | {d2[k][1]['fp']:11.4f}")
    print(f"  FRESH WORST PLAUSIBLE: {fresh_worst[0]:.4f} [{fresh_worst[1]}]")
    if s3:
        print()
        print("== A SECOND FRESH REPLICATE (s3null) of the chosen rule's worst cells")
        w3 = rows_for(s3, rule)
        for k in sorted(w3, key=lambda k: -w3[k][1]["fp"]):
            c, r = w3[k]
            pooled = ""
            if k in w2:
                r2 = w2[k][1]
                pp = (r["fp"] * r["R"] + r2["fp"] * r2["R"]) / (r["R"] + r2["R"])
                pooled = f" pooled with s2 {pp:.4f} ({se(pp, r['R'] + r2['R']):.4f}, R {r['R'] + r2['R']})"
            print(f"  {SF.lab(c['cell'], c['gen'], c['T']):60s} {r['fp']:.4f} ({se(r['fp'], r['R']):.4f}){pooled}")
    print()
    print("== SEARCH SEEDS (s1null, 1,000 programs a cell): every plausible cell, chosen rule | the draft's schedule "
          "(weighted values: the search seeds carry no unweighted test); * = re-run fresh above")
    w1 = rows_for(s1, rule)
    d1 = rows_for(s1, DRAFT, "w")
    rest_worst = (0.0, None)
    for k in sorted(w1):
        c, r = w1[k]
        fresh = (c["cell"], json.dumps(c["gen"], sort_keys=True)) in fresh_keys
        if SF.plausible(c["cell"], c["gen"]) and not fresh and r["fp"] > rest_worst[0]:
            rest_worst = (r["fp"], SF.lab(c["cell"], c["gen"], c["T"]))
        print(f"  {'*' if fresh else ' '} {SF.lab(c['cell'], c['gen'], c['T']):60s} {r['fp']:.3f} | {d1[k][1]['fp']:.3f}"
              f" | ret {r['ret']:.3f}")
    print(f"  WORST PLAUSIBLE OF THE CELLS NOT RE-RUN: {rest_worst[0]:.4f} [{rest_worst[1]}]")
    base = [(c["gen"]["nbar"], r["fp"]) for (c, r) in w1.values()
            if c["cell"] == "N3|sym|nodrift|phi0.10" and abs(c["gen"]["rho_day"] - 0.05) < 1e-9]
    print(f"  BASE (N3 symmetric, rho 0.05, phi 0.10, no drift): {sorted(base, reverse=True)}")
    print()
    print("== THE GRID BY ROW (search seeds; fresh where re-run), the maximum over the five rates")
    grid = {}
    for k, (c, r) in w1.items():
        kk = (c["cell"], json.dumps(c["gen"], sort_keys=True))
        v = r["fp"]
        for k2, (c2, r2) in w2.items():
            if (c2["cell"], json.dumps(c2["gen"], sort_keys=True)) == kk:
                v = r2["fp"]
        g = c["gen"]
        key = (c["cell"].rsplit("|phi", 1)[0], g["rho_day"], g.get("phi_day", 0.10))
        dv = d1[k][1]["fp"]
        cur = grid.get(key, (0.0, 0, 0.0))
        grid[key] = (max(cur[0], v), g["nbar"] if v > cur[0] else cur[1], max(cur[2], dv))
    for key in sorted(grid):
        v, nb, dv = grid[key]
        print(f"  {key[0]:22s} rho {key[1]:.2f} phi {key[2]:.2f}: {v:.3f} (at {nb:g} a session) | the draft's schedule "
              f"(weighted, search seeds) {dv:.3f}")
    if have("stress"):
        print()
        print("== STRESSES AND OTHER STRUCTURES (stress, 1,000 programs a cell): chosen | chosen unweighted | judge draft")
        st = SF._load(["stress"], [])
        ws, wu, dd = rows_for(st, rule), rows_for(st, rule, "u"), rows_for(st, DRAFT, "u")
        for k in sorted(ws):
            c, r = ws[k]
            info = c["info"][0]
            print(f"  {SF.lab(c['cell'], c['gen'], c['T']):60s} {r['fp']:.3f} | {wu[k][1]['fp']:.3f} | {dd[k][1]['fp']:.3f}"
                  f" | money-weighted mean a {np.mean([i['mw_mean_a_bp'] for i in c['info']]):+.1f} bp, event-weighted "
                  f"{np.mean([i['ew_mean_a_bp'] for i in c['info']]):+.1f} bp")
    if have("s2power"):
        print()
        print("== POWER (fresh seeds, s2power, 2,000 programs a cell, 120 sessions): P(promoted by session h); E60;"
              " run 1 ENDED unpassed at its 60th block (D2); lower-tail retired; promoted by 120 incl. run 2")
        pw = SF._load([], ["s2power"])
        for c in sorted(pw, key=lambda c: (c["gen"]["skill"], c["gen"]["rho_day"], -c["gen"]["nbar"])):
            fp, fr, fe = SF.first_pass(c["d"], "", rule, c["tag"])
            _, any_ = SF.two_runs(c["d"], rule, c["tag"])
            row = SF.power_row(fp, fr, fe, c["T"])
            dfp, dfr, dfe = SF.first_pass(c["d"], "", DRAFT, c["tag"], "w")   # (power cells: weighted values only)
            drow = SF.power_row(dfp, dfr, dfe, c["T"])
            g = c["gen"]
            print(f"  {g['skill'] * 1e4:4.0f} bp rho {g['rho_day']:.2f} n {g['nbar']:3g}: "
                  + " ".join(f"{h}:{row[h]:.3f}" for h in (8, 10, 15, 20, 40, 60, 120))
                  + f" | E60 {row['E60']:.1f} med {row['med']} | ended {row['end']:.3f} ret {row['ret']:.3f}"
                  + f" | incl. run 2 by 120: {SF.rate(any_, 120):.3f}"
                  + f" || the draft's schedule (weighted): 10:{drow[10]:.3f} 20:{drow[20]:.3f} 40:{drow[40]:.3f} E60 {drow['E60']:.1f}")
        print("  LAG 3 (a record that starts three sessions after its program's own count, Oct 19 = 1): P(promoted by its "
              "own 10th / 20th / 40th session) = P(by the 7th / 17th / 37th of the record)")
        for c in sorted(pw, key=lambda c: (c["gen"]["skill"], c["gen"]["rho_day"], -c["gen"]["nbar"])):
            g = c["gen"]
            if abs(g["rho_day"] - 0.05) > 1e-9 or round(g["skill"] * 1e4) not in (60, 100):
                continue
            fp, fr, fe = SF.first_pass(c["d"], "", rule, c["tag"])
            print(f"    {g['skill'] * 1e4:4.0f} bp n {g['nbar']:3g}: " + " / ".join(f"{SF.rate(fp, h):.3f}" for h in (7, 17, 37)))
        for sk in (30, 60, 100):
            for rho in (0.0, 0.05, 0.15):
                res = SF.evaluate(rule, [c for c in pw if round(c["gen"]["skill"] * 1e4) == sk
                                         and abs(c["gen"]["rho_day"] - rho) < 1e-9])
                sp = SF.speed(res, sk, rho)
                resd = SF.evaluate(DRAFT, [c for c in pw if round(c["gen"]["skill"] * 1e4) == sk
                                           and abs(c["gen"]["rho_day"] - rho) < 1e-9], "w")
                spd = SF.speed(resd, sk, rho)
                if sp:
                    print(f"  MEAN OVER THE FIVE RATES {sk} bp rho {rho:.2f}: E60 {sp['E60']:.2f} by 8/10/15/20/40/60 "
                          + "/".join(f"{sp[h]:.3f}" for h in (8, 10, 15, 20, 40, 60)) + f" ended {sp['end']:.3f}"
                          + f" || the draft's schedule (weighted) E60 {spd['E60']:.2f} by 10/20/40 {spd[10]:.3f}/{spd[20]:.3f}/{spd[40]:.3f}")


if __name__ == "__main__":
    main()

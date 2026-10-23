#!/usr/bin/env python
"""report_v2.py: every table of PREREG-EVL-6 section 4 for the rule D14's protocol chose (synthetic only).

Reads chosen_v2.json (select_v2.py) and the arrays of calib_final.py and calib_v2.py: SEARCH seeds (s1null, w1),
SELECTION seeds (w2 and w2x: they chose the rule), the UNSELECTED replicate (w3 and w3x: seeds that never searched,
shortlisted or chose), the stresses (stress, wstress) and the power cells (s2power). Beside the chosen rule, on the same paths: the
previous round's rule (looks from 9: 0.012 / 0.010 / 0.004), re-check 1's candidate (looks from 12: 0.012 / 0.006 /
0.0025), the chosen schedule with unweighted values and no top-14 guard ('u', where the arrays carry it), and the
judge's draft rule ('u').

Usage: report_v2.py > report_v2.txt
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_v2 as SV  # noqa: E402
import search_final as SF  # noqa: E402

DRAFT = SF.Rule(6, ((20, 0.016), (60, 0.004)))
FIRST = SF.Rule(20, ((20, 0.016), (30, 0.016), (60, 0.002)))     # the choice before the edge check (chosen_v2.pass12.json)


def se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / n)


def have(phase):
    return os.path.exists(SV.index_path(phase))


def key_of(c):
    return (c["cell"], json.dumps(c["gen"], sort_keys=True), c["T"])


def rows_for(cells, r, variant="w"):
    out = {}
    for c in cells:
        if c["cell"].startswith("P"):
            continue
        if variant == "u" and "Pu" not in c["d"]:
            out[key_of(c)] = (c, {"fp": float("nan"), "R": c["R"]})
            continue
        fp, fr, fe = SF.first_pass(c["d"], "", r, c["tag"], variant)
        row = {"fp": SF.rate(fp, min(120, c["T"])), "R": c["R"], "ret": float(np.mean(fr < SF.NONE)),
               "end": float(np.mean(fe < SF.NONE))}
        if "Sat_2" in c["d"]:
            _, any_ = SF.two_runs(c["d"], r, c["tag"], variant)
            row["two"] = SF.rate(any_, min(120, c["T"]))
        out[key_of(c)] = (c, row)
    return out


def mwew(c):
    return (np.mean([i["mw_mean_a_bp"] for i in c["info"]]), np.mean([i["ew_mean_a_bp"] for i in c["info"]]))


def main():
    ch = json.load(open(os.path.join(HERE, "chosen_v2.json")))
    rule = SF.Rule.of(ch["chosen"]["rule"])
    print(f"THE CHOSEN RULE: {rule.label()}  ({rule.key()})")
    print(f"BESIDE IT: the previous rule {SV.PREV.label()}; re-check 1's candidate {SV.RECHECK1.label()}; the judge's "
          f"draft {DRAFT.label()} (unweighted, no top-14 guard); the choice before the edge check {FIRST.label()}")
    print()
    print("== THE SELECTION TABLE (select_v2.py choose): every shortlisted rule, fastest first")
    for r in ch["table"]:
        s = {str(k): v for k, v in r["speed60"].items()}
        print(f"  E60 {s['E60']:.2f} | 60 bp by 10/20/40 {s['10']:.3f}/{s['20']:.3f}/{s['40']:.3f} | worst selection "
              f"{r['worst_sel'][0]:.4f} [{r['worst_sel'][1]}] | other cells (search seeds) {r['worst_rest_s1'][0]:.4f}"
              f" | {r['label']}")
    print()
    s1 = SF._load(["s1null", "w1"], [])
    s2 = SF._load(["w2"] + (["w2x"] if have("w2x") else []), [])
    s3 = SF._load(["w3"] + (["w3x"] if have("w3x") else []), []) if have("w3") else []
    sel_keys = {(c["cell"], json.dumps(c["gen"], sort_keys=True)) for c in s2}

    print("== SELECTION SEEDS (w2, w2x: these chose the rule): chosen (se) | two runs | chosen unweighted | previous rule |"
          " re-check 1's candidate | judge's draft")
    w2 = rows_for(s2, rule)
    w2u = rows_for(s2, rule, "u")
    p2 = rows_for(s2, SV.PREV)
    r2 = rows_for(s2, SV.RECHECK1)
    d2 = rows_for(s2, DRAFT, "u")
    f2 = rows_for(s2, FIRST)
    worst2 = (0.0, None)
    for k in sorted(w2, key=lambda k: -w2[k][1]["fp"]):
        c, r = w2[k]
        if SV.plausible(c["cell"], c["gen"]) and r["fp"] > worst2[0]:
            worst2 = (r["fp"], SF.lab(c["cell"], c["gen"], c["T"]))
        mw, ew = mwew(c)
        print(f"  {SF.lab(c['cell'], c['gen'], c['T']):66s} R{r['R']:5d} {r['fp']:.4f} ({se(r['fp'], r['R']):.4f}) "
              f"{r.get('two', float('nan')):.4f} | {w2u[k][1]['fp']:.4f} | {p2[k][1]['fp']:.4f} | {r2[k][1]['fp']:.4f} | "
              f"{d2[k][1]['fp']:.4f} | first choice {f2[k][1]['fp']:.4f} | mw {mw:+.1f} ew {ew:+.1f} bp")
    print(f"  SELECTION WORST PLAUSIBLE: {worst2[0]:.4f} [{worst2[1]}]")
    if s3:
        print()
        print("== THE UNSELECTED REPLICATE (w3, w3x: seeds that never searched, shortlisted or chose): chosen (se) | two runs"
              " | pooled with the selection seeds")
        w3 = rows_for(s3, rule)
        p3 = rows_for(s3, SV.PREV)
        f3 = rows_for(s3, FIRST)
        worst3 = (0.0, None)
        for k in sorted(w3, key=lambda k: -w3[k][1]["fp"]):
            c, r = w3[k]
            pooled = ""
            if k in w2:
                rr2 = w2[k][1]
                pp = (r["fp"] * r["R"] + rr2["fp"] * rr2["R"]) / (r["R"] + rr2["R"])
                pt = (r["two"] * r["R"] + rr2["two"] * rr2["R"]) / (r["R"] + rr2["R"])
                pooled = f" | pooled {pp:.4f} ({se(pp, r['R'] + rr2['R']):.4f}, R {r['R'] + rr2['R']}), two runs {pt:.4f}"
            if r["fp"] > worst3[0]:
                worst3 = (r["fp"], SF.lab(c["cell"], c["gen"], c["T"]))
            print(f"  {SF.lab(c['cell'], c['gen'], c['T']):66s} {r['fp']:.4f} ({se(r['fp'], r['R']):.4f}) {r['two']:.4f}"
                  f"{pooled} | previous rule {p3[k][1]['fp']:.4f} | first choice {f3[k][1]['fp']:.4f}")
        print(f"  UNSELECTED WORST: {worst3[0]:.4f} [{worst3[1]}]")
    print()
    print("== SEARCH SEEDS (s1null, w1: 1,000 programs a cell): every plausible cell; * = re-run on the selection seeds")
    w1 = rows_for(s1, rule)
    rest_worst = (0.0, None)
    for k in sorted(w1):
        c, r = w1[k]
        if not SV.plausible(c["cell"], c["gen"]):
            continue
        sel = (c["cell"], json.dumps(c["gen"], sort_keys=True)) in sel_keys
        if not sel and r["fp"] > rest_worst[0]:
            rest_worst = (r["fp"], SF.lab(c["cell"], c["gen"], c["T"]))
        print(f"  {'*' if sel else ' '} {SF.lab(c['cell'], c['gen'], c['T']):66s} {r['fp']:.3f} | ret {r['ret']:.3f}")
    print(f"  WORST PLAUSIBLE OF THE CELLS NOT RE-RUN: {rest_worst[0]:.4f} [{rest_worst[1]}]")
    base = [(c["gen"]["nbar"], r["fp"]) for (c, r) in w1.values()
            if c["cell"] == "N3|sym|nodrift|phi0.10" and abs(c["gen"]["rho_day"] - 0.05) < 1e-9]
    print(f"  BASE (N3 symmetric, rho 0.05, phi 0.10, no drift; search seeds): {sorted(base, reverse=True)}")
    print()
    print("== THE GRID BY ROW (selection seeds where re-run, else search seeds): the maximum over the rates "
          "(counts that follow the day: 3, 5, 8; else 85, 30, 13, 8, 3)")
    grid = {}
    for k, (c, r) in w1.items():
        if not SV.plausible(c["cell"], c["gen"]):
            continue
        kk = (c["cell"], json.dumps(c["gen"], sort_keys=True), c["T"])
        v, src = r["fp"], "s"
        if kk in w2:
            v, src = w2[kk][1]["fp"], "w2"
        g = c["gen"]
        lab, _, rest = c["cell"].partition("|phi")
        cnt = "|cnt" if rest.endswith("|cnt") else ""
        key = (lab + cnt, g["rho_day"], g.get("phi_day", 0.10))
        cur = grid.get(key, (0.0, 0, ""))
        if v > cur[0]:
            grid[key] = (v, g["nbar"], src)
        else:
            grid.setdefault(key, cur)
    for key in sorted(grid):
        v, nb, src = grid[key]
        print(f"  {key[0]:30s} rho {key[1]:.2f} phi {key[2]:.2f}: {v:.3f} (at {nb:g} a session, {src})")
    for nm, phases in (("STRESSES AND OTHER STRUCTURES, calib_final (stress, 1,000 programs a cell): chosen | chosen "
                        "unweighted | judge's draft | previous rule", ["stress"]),
                       ("STRESSES AND OTHER STRUCTURES, calib_v2 (wstress, 2,000 programs a cell): chosen (se) | two "
                        "runs | previous rule | re-check 1's candidate", ["wstress"])):
        if not all(have(p) for p in phases):
            continue
        print()
        print("== " + nm)
        st = SF._load(phases, [])
        ws, wu, dd, pp, rc = (rows_for(st, rule), rows_for(st, rule, "u"), rows_for(st, DRAFT, "u"),
                              rows_for(st, SV.PREV), rows_for(st, SV.RECHECK1))
        for k in sorted(ws):
            c, r = ws[k]
            mw, ew = mwew(c)
            if phases == ["stress"]:
                print(f"  {SF.lab(c['cell'], c['gen'], c['T']):60s} {r['fp']:.3f} | {wu[k][1]['fp']:.3f} | "
                      f"{dd[k][1]['fp']:.3f} | {pp[k][1]['fp']:.3f} | mw {mw:+.1f} ew {ew:+.1f} bp")
            else:
                print(f"  {SF.lab(c['cell'], c['gen'], c['T']):60s} {r['fp']:.4f} ({se(r['fp'], r['R']):.4f}) "
                      f"{r.get('two', float('nan')):.4f} | {pp[k][1]['fp']:.4f} | {rc[k][1]['fp']:.4f} | mw {mw:+.1f} ew "
                      f"{ew:+.1f} bp")
    if have("s2power"):
        print()
        print("== POWER (s2power, 2,000 programs a cell, 120 sessions): P(promoted by session h); E60; run 1 ENDED "
              "unpassed at its 60th block (D2); lower-tail retired; promoted by 120 incl. run 2")
        pw = SF._load([], ["s2power"])
        for c in sorted(pw, key=lambda c: (c["gen"]["skill"], c["gen"]["rho_day"], -c["gen"]["nbar"])):
            fp, fr, fe = SF.first_pass(c["d"], "", rule, c["tag"])
            _, any_ = SF.two_runs(c["d"], rule, c["tag"])
            row = SF.power_row(fp, fr, fe, c["T"])
            pfp, pfr, pfe = SF.first_pass(c["d"], "", SV.PREV, c["tag"])
            prow = SF.power_row(pfp, pfr, pfe, c["T"])
            ffp, ffr, ffe = SF.first_pass(c["d"], "", FIRST, c["tag"])
            frow = SF.power_row(ffp, ffr, ffe, c["T"])
            g = c["gen"]
            print(f"  {g['skill'] * 1e4:4.0f} bp rho {g['rho_day']:.2f} n {g['nbar']:3g}: "
                  + " ".join(f"{h}:{row[h]:.3f}" for h in (8, 10, 12, 15, 20, 40, 60, 120))
                  + f" | E60 {row['E60']:.1f} med {row['med']} | ended {row['end']:.3f} ret {row['ret']:.3f}"
                  + f" | incl. run 2 by 120: {SF.rate(any_, 120):.3f}"
                  + f" || previous rule 10:{prow[10]:.3f} 20:{prow[20]:.3f} 40:{prow[40]:.3f} E60 {prow['E60']:.1f}"
                  + f" || first choice 20:{frow[20]:.3f} 40:{frow[40]:.3f} E60 {frow['E60']:.1f}")
        print("  LAG 3 (a record that starts three sessions after its program's own count): P(promoted by its own "
              "10th / 20th / 40th session) = P(by the 7th / 17th / 37th of the record)")
        for c in sorted(pw, key=lambda c: (c["gen"]["skill"], c["gen"]["rho_day"], -c["gen"]["nbar"])):
            g = c["gen"]
            if abs(g["rho_day"] - 0.05) > 1e-9 or round(g["skill"] * 1e4) not in (60, 100):
                continue
            fp, fr, fe = SF.first_pass(c["d"], "", rule, c["tag"])
            print(f"    {g['skill'] * 1e4:4.0f} bp n {g['nbar']:3g}: " + " / ".join(f"{SF.rate(fp, h):.3f}" for h in (7, 17, 37)))
        for sk in (30, 60, 100):
            for rho in (0.0, 0.05, 0.15):
                sub = [c for c in pw if round(c["gen"]["skill"] * 1e4) == sk and abs(c["gen"]["rho_day"] - rho) < 1e-9]
                sp = SF.speed(SF.evaluate(rule, sub), sk, rho)
                spp = SF.speed(SF.evaluate(SV.PREV, sub), sk, rho)
                spf = SF.speed(SF.evaluate(FIRST, sub), sk, rho)
                if sp:
                    print(f"  MEAN OVER THE FIVE RATES {sk} bp rho {rho:.2f}: E60 {sp['E60']:.2f} by 8/10/15/20/40/60 "
                          + "/".join(f"{sp[h]:.3f}" for h in (8, 10, 15, 20, 40, 60)) + f" ended {sp['end']:.3f}"
                          + f" || previous rule E60 {spp['E60']:.2f} by 10/20/40 {spp[10]:.3f}/{spp[20]:.3f}/{spp[40]:.3f}"
                          + f" || first choice E60 {spf['E60']:.2f} by 20/40 {spf[20]:.3f}/{spf[40]:.3f}")


if __name__ == "__main__":
    main()

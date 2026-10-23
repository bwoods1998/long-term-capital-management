#!/usr/bin/env python
"""report8f.py: every table PREREG-EVL-8's sections 0, 3.3, 6 and 12 cite, from the fix round's outputs in final/
(SYNTHETIC ONLY; reads nothing of the lane). Usage: report8f.py > report8f.txt"""
import collections
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def rows(name):
    p = os.path.join(HERE, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / n)


search = {r["cell"]: r for r in rows("px8f.search.jsonl")}
fresh = {r["cell"]: r for r in rows("px8f.fresh.jsonl")}
conf = {r["cell"]: r for r in rows("px8f.confirm.jsonl")}
ch = json.load(open(os.path.join(HERE, "px8f.choose.json")))
F = ch["chosen_first_look"]
k = f"F{F}"
print("=" * 100)
print("THE PX SCREEN'S FIRST LOOK (F1): search seeds 171,000,001+ (1,000 a cell, 1,590 plausible cells), fresh seeds")
print("172,000,001+ (4,000 a cell, the cells within 3.5 points of each first look's search worst), confirmation seeds")
print("173,000,001+ (4,000 a cell, the chosen first look's 16 worst fresh cells; they chose nothing)")
for row in ch["table"]:
    print(f"  first look {row['first_look']}: search worst {row['worst_search_all']:.4f} [{row['worst_search_cell']}]; fresh worst "
          f"{row['worst_fresh']:.4f} +- {row['se_fresh']:.4f} [{row['worst_fresh_cell']}]; other cells' search worst "
          f"{row['worst_rest_search']:.4f}; holds 0.13: {row['holds']}")
print(f"  CHOSEN (the earliest that holds): {F}")
print("\nCONFIRMATION (never chose) at the chosen first look, beside the fresh (choosing) seeds:")
pool_worst = (0, None)
for c, r in sorted(conf.items(), key=lambda x: -x[1][k]["fp120"]):
    f_ = fresh[c][k]["fp120"]
    cc = r[k]["fp120"]
    pooled = (f_ * fresh[c]["R"] + cc * r["R"]) / (fresh[c]["R"] + r["R"])
    pool_worst = max(pool_worst, (pooled, c))
    print(f"  {c:48s} confirm {cc:.4f} +- {se(cc, r['R']):.4f} (two runs {r[k]['two_runs120']:.4f}) | fresh {f_:.4f} "
          f"(two runs {fresh[c][k]['two_runs120']:.4f}) | pooled {pooled:.4f} +- {se(pooled, 8000):.4f}")
print(f"  pooled worst {pool_worst[0]:.4f} [{pool_worst[1]}]")
print(f"  per version (two runs within 120 sessions), worst over the fresh cells: "
      f"{max(r[k]['two_runs120'] for r in fresh.values()):.4f}; over the confirmation cells: "
      f"{max(r[k]['two_runs120'] for r in conf.values()):.4f}")
print("\nTHE PLAUSIBLE GRID AT THE CHOSEN FIRST LOOK (the knife edge NK; the maximum over the drifts 0/10/20 bp and the count")
print("rates of each row; fresh seeds where the cell was re-run, else search seeds; 'cnt' = counts that follow the day at")
print("lam 3/5/8, 'ind' = independent counts at lam 3/5/8/20/40):")
grid = collections.defaultdict(float)
for c, r in search.items():
    s = r["spec"]
    v = fresh[c][k]["fp120"] if c in fresh else r[k]["fp120"]
    rho = {0.0: "rho0", 0.012: "rho.05", 0.022: "rho.15"}[round(s["sd_c"], 4)]
    key = (s["day"], s["ev"], "cnt" if s["cnt"] > 0 else "ind")
    col = (rho, s["phi"])
    grid[(key, col)] = max(grid[(key, col)], v)
cols = [("rho0", 0.10), ("rho.05", 0.10), ("rho.05", 0.15), ("rho.05", 0.20), ("rho.15", 0.10), ("rho.15", 0.15),
        ("rho.15", 0.20)]
print("  " + " " * 26 + " ".join(f"{a}/{b:.2f}".rjust(12) for a, b in cols))
for day in ("t3", "crash", "crasht3", "crashcl", "crasht3cl"):
    for ev in ("t3", "skew"):
        for cm in ("ind", "cnt"):
            vals = [grid.get(((day, ev, cm), col)) for col in cols]
            if all(v is None or v == 0 for v in vals):
                continue
            print(f"  {day:9s} {ev:4s} {cm:3s}         " + " ".join(("%.3f" % v if v else "  -  ").rjust(12) for v in vals))
print(f"  the realized money-weighted mean a over the search cells: "
      f"{min(r['mw_mean_a_bp'] for r in search.values()):+.1f} to {max(r['mw_mean_a_bp'] for r in search.values()):+.1f} bp, "
      f"mean {sum(r['mw_mean_a_bp'] for r in search.values()) / len(search):+.2f} bp")
for name, title in (("px8f.base.jsonl", "BASE (the PX designer's base: sd_c 0.4%, t3, no drift, beta 1, no issuer effect)"),
                    ("px8f.stress.jsonl", "STRESSES AND THE PX DESIGNER'S OWN CELLS"),
                    ("px8f.sens.jsonl", "SENSITIVITIES AT THE CORNER (tau 0; the real control at 0; beta 1.0)"),
                    ("px8f.money.jsonl", "MONEY'S POPULATION (check 1's attack: the top CAP events at mu_top, the rest at mu)")):
    print(f"\n{title}:")
    for r in sorted(rows(name), key=lambda r: -r[k]["fp120"]):
        print(f"  {r['cell']:72s} {r[k]['fp120']:.4f} (two runs {r[k]['two_runs120']:.4f}; mw mean a {r['mw_mean_a_bp']:+.1f} bp, "
              f"{r['events_per_session']:.1f} events a session)")
print("\nSHARED DRIFT (check 1: two ON seats sharing only the family drift):")
for r in rows("px8f.shared.jsonl"):
    f = r[k]
    print(f"  {r['cell']:60s} P(A) {f['A']:.4f} P(B) {f['B']:.4f} P(both) {f['both']:.4f} (independent {f['A'] * f['B']:.4f}); "
          f"P(B | A) {f['both'] / max(f['A'], 1e-9):.3f}")
print("\nPOWER at the chosen first look (P(promoted) by the session; run 1; 'two runs' = within 120 sessions with run 2):")
for r in sorted(rows("px8f.power.jsonl"), key=lambda r: (r["cell"].split("|mu")[0], r["spec"]["mu"])):
    f = r[k]
    print(f"  {r['cell']:72s} by25 {f['by25']:.3f} by30 {f['by30']:.3f} by40 {f['by40']:.3f} by60 {f['by60']:.3f} by120 "
          f"{f['fp120']:.3f} two {f['two_runs120']:.3f} | run 1 ended unpassed {f['end']:.3f} | E[min(T,60)] {f['E60']:.1f}")
dem = os.path.join(HERE, "px_demotion8.json")
if os.path.exists(dem):
    d = json.load(open(dem))
    print(f"\nPX DEMOTION (F3; PREREG-EVL-6 section 3 frozen; Probe 14 at $67.9, Sized 8 at $190; seeds from {d['seed0'] + 1:,}):")
    for r in d["rows"]:
        marks = []
        for h in (300, 1000, 2000, 3000):
            v = r[f"by{h}"]
            reach = r[f"by{h}_reached"]
            tag = "" if reach >= 0.99 else ("+" if reach >= 0.60 else "-")
            marks.append(f"{v:.3f}{tag}")
        print(f"  {r['cell']:62s} lam {r['lam']:>2} R {r['R']}: by 300/1000/2000/3000 {' / '.join(marks)} | at 1,000: reads "
              f"{r['by1000_read']:.3f} stop {r['by1000_stop']:.3f} tail {r['by1000_tail']:.3f} | Sized {r['sized']:.3f} | se "
              f"{r['se1000']:.4f}")
plc = [f for f in os.listdir(HERE) if f.startswith("placebo8f_F") and f.endswith(".out.json")]
for f in plc:
    d = json.load(open(os.path.join(HERE, f)))
    print(f"\nPLACEBO AUDIT AND CANARY (first look {d['first_look']}, CAP 4, no control condition; 2,000 pools a cell):")
    for r in d["rows"]:
        print(f"  lift {r['delta_bp']:>4.0f} bp drift {r['drift_bp']:>4.0f} bp crash {str(r['crash']):5s}: a placebo "
              f"{r['single']:.4f}, >=3 of 8 {r['ge3']:.4f}, canary {r['canary']:.4f}, ALARM (>=3 or canary) "
              f"{r['audit_ge3_or_canary']:.4f}")
for g in ("null", "stress", "power"):
    rr = rows(f"meta8f.{g}.jsonl")
    if not rr:
        continue
    print(f"\nMETA-LEARNERS ({g}; the frozen screen; CAP 8 = PREREG-EVL-3's learning band, CAP 4 beside):")
    for r in rr:
        c8, c4 = r["cap8"], r["cap4"]
        if g == "power":
            print(f"  {r['cell']:52s} R {r['R']} T {r['T']}: CAP 8 pass by 40/60/80/120/240 {c8.get('pass_by40', 0):.3f} / "
                  f"{c8.get('pass_by60', 0):.3f} / {c8.get('pass_by80', 0):.3f} / {c8.get('pass_by120', 0):.3f} / "
                  f"{c8.get('pass_by240', float('nan')):.3f}; run 1 by 120 {c8['run1_by120']:.3f}; CAP 4 by 120 "
                  f"{c4.get('pass_by120', 0):.3f} | picks/s {r['picks_per_session']:.2f}, true {r['true_mean_picks_bp']}")
        else:
            print(f"  {r['cell']:52s} R {r['R']} T {r['T']} null {r['null_share']:.2f}: CAP 8 run 1 by 120 "
                  f"{c8['run1_by120']:.3f} (|null {c8['run1_by120_given_null']:.3f}), any run by 120/240/480/720 "
                  f"{c8.get('any_run_by120', 0):.3f} / {c8.get('any_run_by240', 0):.3f} / {c8.get('any_run_by480', 0):.3f} / "
                  f"{c8.get('any_run_by720', 0):.3f} (|null by 720 {c8.get('any_run_by720_given_null', 0):.3f}); CAP 4 any by 720 "
                  f"{c4.get('any_run_by720', 0):.3f} | picks/s {r['picks_per_session']:.2f} in {r['sessions_with_picks']:.3f} of "
                  f"sessions, blocks {r['blocks_mean']:.0f}, true {r['true_mean_picks_bp']}")
# ------------------------------------------------------------------------------------------- THE FINAL FIX'S TABLES
life = rows("meta8l.life.jsonl") + rows("meta8l.ext.jsonl")
if life:
    print("\nMETA-LEARNERS PER RUN TO THE RUN'S END (the final fix, meta_life8.py; seeds from 182,000,001; L = plausible, "
          "S = stress; B03 / B05 = beta_day 0.3 / 0.5; CAP 8, CAP 4 beside):")
    for r in life:
        c8, c4 = r["cap8"], r["cap4"]
        hs = [h for h in (120, 720, 2500, 4000) if f"run1_by{h}" in c8]
        print(f"  {r['cell']:58s} R {r['R']} T {r['T']} null {r['null_share']:.2f} s22 med {r['s22_median']}: run 1 by "
              + " / ".join(str(h) for h in hs) + " " + " / ".join(f"{c8[f'run1_by{h}']:.4f}" for h in hs)
              + f" (+- {c8['run1_by_T_se']:.4f}; |null {c8[f'run1_by{hs[-1]}_given_null']:.4f}); ended {c8['run1_ended_share']:.3f}"
              f", among ended {c8['run1_pass_among_ended']:.4f}, upper {c8['run1_to_end_upper']:.4f}; every run by 720 "
              f"{c8['any_run_by720']:.4f} / by T {c8[f'any_run_by{hs[-1]}']:.4f} (|null {c8[f'any_run_by{hs[-1]}_given_null']:.4f})"
              f"; CAP 4 run 1 by T {c4['run1_by_T']:.4f}, every run by T {c4[f'any_run_by{hs[-1]}']:.4f} | picks/s "
              f"{r['picks_per_session']:.2f} in {r['sessions_with_picks']:.3f} of sessions")
sday = rows("px8f.sharedday.jsonl")
if sday:
    print("\nSHARED DAY (the final fix, px_shared8day.py, seeds from 183,000,001: two ON seats sharing every day-level "
          "shock, events, issuers and counts independent):")
for r in sday:
    print(f"  {r['cell']:60s} R {r['R']} P(A) {r['A']:.4f} P(B) {r['B']:.4f} P(both) {r['both']:.4f} (independent "
          f"{r['indep']:.4f}); P(B | A) {r['P(B|A)']:.3f}; block correlation {r['rho_blocks']:.3f}")
dem3 = os.path.join(HERE, "px_demotion8.s184.json")
if os.path.exists(dem3):
    d = json.load(open(dem3))
    print(f"\nPX DEMOTION, A THIRD SEED SET (the final fix; px_demotion8.py --only '40bp|' --R 4000; seeds from "
          f"{d['seed0'] + 1:,}):")
    for r in d["rows"]:
        marks = []
        for h in (300, 1000, 2000, 3000):
            v = r[f"by{h}"]
            reach = r[f"by{h}_reached"]
            tag = "" if reach >= 0.99 else ("+" if reach >= 0.60 else "-")
            marks.append(f"{v:.3f}{tag}")
        print(f"  {r['cell']:62s} lam {r['lam']:>2} R {r['R']}: by 300/1000/2000/3000 {' / '.join(marks)} | at 1,000: reads "
              f"{r['by1000_read']:.3f} stop {r['by1000_stop']:.3f} tail {r['by1000_tail']:.3f} | se {r['se1000']:.4f}")

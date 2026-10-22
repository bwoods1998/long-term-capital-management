"""rc_pool.py: pools the re-check's fresh-seed runs of the chosen rule (run 1 within 120 sessions) by structure.
Inputs: out/plan{A..E}.jsonl (rc_sim.py, independent generator and rule), out/theirs_rep.out and
out/theirs_eval_{t3body,cnt}.json (the fixer's generator and evaluation on re-check seeds). Synthetic only."""
import json
import math
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
O = os.path.join(HERE, "out")


def mine(prefixes_by_plan, v="w"):
    k = n = 0
    for plan, labs in prefixes_by_plan.items():
        for line in open(os.path.join(O, f"{plan}.jsonl")):
            r = json.loads(line)
            if r["lab"] in labs and f"{v}1_st" in r:
                st, at = np.array(r[f"{v}1_st"]), np.array(r[f"{v}1_at"])
                k += int(np.sum((st == 1) & (at <= 120))); n += r["R"]
    return k, n


def theirs_eval(phase, cell):
    for o in json.load(open(os.path.join(O, f"theirs_eval_{phase}.json"))):
        if o["chosen"]:
            return o["rates"][cell][0]


def theirs_rep(cell):
    for line in open(os.path.join(O, "theirs_rep.out")):
        m = re.match(rf"{cell}: R (\d+) chosen rule FP ([0-9.]+)", line)
        if m:
            return float(m.group(2)), int(m.group(1))


def show(name, parts):
    k = sum(p[0] for p in parts); n = sum(p[1] for p in parts)
    p = k / n
    det = "; ".join(f"{lab} {pk / pn:.4f} ({pn})" for lab, pk, pn in [(q[2], q[0], q[1]) for q in parts])
    print(f"{name:58s} pooled {p:.4f} +- {math.sqrt(p * (1 - p) / n):.4f} over {n} | {det}")


rows = []
fp, fn = theirs_rep("corner n85")
show("PLAIN CORNER n85 (unselected re-check seeds)", [
    (*mine({"planA": {"corner n85"}}), "indep A"), (*mine({"planE": {"E plain corner n85 (control)"}}), "indep E"),
    (round(fp * fn), fn, "fixer-gen")])
fp30, fn30 = theirs_rep("corner n30")
show("PLAIN CORNER n30", [(*mine({"planA": {"corner n30"}}), "indep"), (round(fp30 * fn30), fn30, "fixer-gen")])
t = theirs_eval("t3body", "t3body corner n85")
show("t(3)-BODY CRASH DAYS, corner n85", [
    (*mine({"planC": {"BREAK crash days with t(3) ordinary days: corner n85"}}), "indep C"),
    (*mine({"planD": {"CONF t3-body crash days: corner n85"}}), "indep D"),
    (*mine({"planE": {"E t3-body crash days: corner n85"}}), "indep E"), (round(t * 4000), 4000, "fixer-gen")])
t = theirs_eval("t3body", "t3body corner n30")
show("t(3)-BODY CRASH DAYS, corner n30", [
    (*mine({"planD": {"CONF t3-body crash days: corner n30"}}), "indep D"),
    (*mine({"planE": {"E t3-body crash days: corner n30"}}), "indep E"), (round(t * 4000), 4000, "fixer-gen")])
t = theirs_eval("t3body", "t3body dayskew AR20 n85")
show("t(3)-BODY CRASH DAYS, symmetric events, 20 bp, n85", [
    (*mine({"planE": {"E t3-body crash days: dayskew AR20 rho.15 phi.20 n85"}}), "indep E"), (round(t * 4000), 4000, "fixer-gen")])
show("CRASH DAYS CLUSTERED IN HIGH VOL (gamma 2), corner n85", [
    (*mine({"planC": {"BREAK crash days cluster in high vol (gamma 2): corner n85"}}), "indep C"),
    (*mine({"planD": {"CONF crash days cluster in high vol (gamma 2): corner n85"}}), "indep D"),
    (*mine({"planE": {"E crash days cluster in high vol (gamma 2): corner n85"}}), "indep E")])
show("DRIFT-DAY CORRELATION 0.3, corner n85", [
    (*mine({"planB": {"BREAK drift-day corr 0.3: corner n85"}}), "indep B"),
    (*mine({"planD": {"CONF drift-day corr 0.3: corner n85"}}), "indep D"),
    (*mine({"planE": {"E drift-day corr 0.3: corner n85"}}), "indep E")])
t = theirs_eval("cnt", "cnt.3 MW14 corner n3")
show("COUNTS FOLLOW |DAY| (money knife), corner n3", [
    (*mine({"planB": {"BREAK counts follow |day| (kappa .3, money knife): corner n3"}}), "indep B"),
    (*mine({"planD": {"CONF counts follow |day| (kappa .3, money knife): corner n3"}}), "indep D"),
    (*mine({"planE": {"E counts follow |day| (money knife): corner n3"}}), "indep E"), (round(t * 4000), 4000, "fixer-gen")])
t = theirs_eval("cnt", "cnt.3 MW14 corner n5")
show("COUNTS FOLLOW |DAY| (money knife), corner n5", [
    (*mine({"planD": {"CONF counts follow |day| (kappa .3, money knife): corner n5"}}), "indep D"), (round(t * 4000), 4000, "fixer-gen")])
t = theirs_eval("cnt", "cnt.3 MW14 corner n8")
show("COUNTS FOLLOW |DAY| (money knife), corner n8", [
    (*mine({"planB": {"BREAK counts follow |day| (kappa .3, money knife): corner n8"}}), "indep B"), (round(t * 4000), 4000, "fixer-gen")])
t = theirs_eval("cnt", "cnt.3 MW14 corner phi.10 n3")
show("COUNTS FOLLOW |DAY| at phi 0.10 (the file's cell), n3", [
    (*mine({"planD": {"CONF counts follow |day| (kappa .3, money knife): phi.10 n3"}}), "indep D"), (round(t * 4000), 4000, "fixer-gen")])
show("VOL REGIME AR 0.97, corner n85", [
    (*mine({"planB": {"BREAK vol persistence: corner, vol AR0.97 sd0.3 n85"}}), "indep B"),
    (*mine({"planD": {"CONF vol AR.97: corner n85"}}), "indep D")])
show("RATE 150, corner", [
    (*mine({"planB": {"BREAK rate: corner n150"}}), "indep B"), (*mine({"planD": {"CONF rate: corner n150"}}), "indep D")])
show("RATE 110, corner", [(*mine({"planD": {"CONF rate: corner n110"}}), "indep D")])
show("DRIFT AR 0.95 (20 bp), corner n85", [
    (*mine({"planB": {"BREAK drift persistence: corner, drift AR0.95 sd20 n85"}}), "indep B"),
    (*mine({"planD": {"CONF drift AR.95: corner n85"}}), "indep D")])
show("t(3)-BODY + CLUSTERED, corner n85", [(*mine({"planE": {"E t3-body + crash clustering: corner n85"}}), "indep E")])
show("t(3)-BODY + COUNTS FOLLOW |DAY|, corner n3", [(*mine({"planE": {"E t3-body + counts follow |day|: corner n3"}}), "indep E")])
print("\nTHE SLOWER SHORTLISTED SCHEDULE (first look 12; 0.012 S12-14, 0.006 S15-20, 0.0025 S21-60), same paths (planE):")
for lab in ["E plain corner n85 (control)", "E t3-body crash days: corner n85", "E crash days cluster in high vol (gamma 2): corner n85",
            "E t3-body + crash clustering: corner n85", "E drift-day corr 0.3: corner n85", "E counts follow |day| (money knife): corner n3",
            "E t3-body + counts follow |day|: corner n3", "E t3-body crash days: corner n30"]:
    k, n = mine({"planE": {lab}}, "r12")
    print(f"  {lab:58s} {k / n:.4f} +- {math.sqrt(k / n * (1 - k / n) / n):.4f} ({n})")

#!/usr/bin/env python
"""ev_judge.py (the edge-swings judge; SYNTHETIC POWER + STATED PRIORS ONLY): expected value per metered dollar and per
false-pass charge of PREREG-EVL-10's seat EVL-R2-ON and PREREG-EVL-11's gated seat EVL-IDN-READ over 120 sessions.

POWER (no outcome read): EVL-R2-ON from the READER-2 designer's FRESH-seed runs under PREREG-EVL-6's frozen screen
(../reader2/calib_r2.final.jsonl: P(run 1 passes by session s), pick mean a after the replay's cost, by the true news
value's dispersion sd and the reader's information c; base model); EVL-IDN-READ from the red team's frozen-generator
power runs (../redteam/screen10.power.jsonl: base model, 5 / 8 / 14 events a session, a true after-cost edge on every
event). False passes: this judge's fresh-seed replications (judge_fp.*.jsonl) at the worst plausible cells, the base
model beside.

MONEY MODEL (stated): learning lots $38 (2% of about $1,898), Probe lots $67.9 (A99 at-size, KEPT-1019h); EVL-R2-ON
buys 6 a session at learning (the designer's 5-7 after earlier rows take shared names) and 7 at Probe (8 picks less
shared names); EVL-IDN-READ buys min(8, supply) at learning and min(14, supply) at Probe, supply 6 (the gate's floor
is a median of 5). A program promoted at its first pass trades Probe from then to session 120; the first-pass session
is the binned conditional mean of the run's pass-session distribution. The edge is the per-event AFTER-COST abnormal
return (for the intraday seat, net of the ask it pays); real auction fills printed at the replay's prices with the
replay charging 14-24 bp a round trip (EXECUTION-FACTS), so the auction figures are conservative. Metered: READER-2
$0.138 / $0.409 / $0.75 a day (../reader2/cost_r2.out lo / mid / R2's line), the intraday lane $0 (no model call).
A102: about 6 sessions of time-to-Done in the best scenario per metered dollar a session.

PRIORS (THE JUDGE'S STATED JUDGMENT, NOT DATA):
  R2:  no information (c 0) 0.40; c 0.3 at sd 0.8% 0.25; c 0.5 at sd 0.8% 0.20; c 0.7 at sd 0.8% 0.08; c 0.5 at sd 1.5%
       0.07 (the stronger reader may add nothing over v1: Lopez-Lira and Tang 2023 find LLM predictability mostly in
       small stocks and bad news, which a long-only liquid seat cannot use).
  IDN: the red team's (net of the ask: -30 / -15 / 0 / +20 / +30 / +60 bp with .20 / .25 / .25 / .15 / .10 / .05), and a
       GATED variant (the cost gate removes the wide-spread tail: -15 / 0 / +20 / +30 / +60 with .30 / .35 / .18 / .12 /
       .05).
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
T = 120
LOT_L, LOT_P = 38.0, 67.9
A102 = 6.0
BINS = ((25, 24.0), (30, 28.0), (40, 35.0), (60, 50.0), (90, 75.0), (120, 105.0))


def pass_session(by):
    """Binned conditional mean of the first-pass session given a pass by 120, from P(pass by s)."""
    prev_s, prev_p, num = 22, 0.0, 0.0
    for s, mid in BINS:
        p = by.get(str(s), by.get(s, 0.0))
        num += (p - prev_p) * mid
        prev_p = p
    return num / prev_p if prev_p > 0 else float("nan"), prev_p


def money(edge_bp, p_pass, t_pass, buys_l, buys_p):
    e = edge_bp * 1e-4
    learn = e * LOT_L * buys_l * ((1 - p_pass) * T + p_pass * t_pass)
    probe = p_pass * e * LOT_P * buys_p * (T - t_pass)
    return learn + probe


def load(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


out = {"r2": {}, "idn": {}}
# ------------------------------------------------------------------------------------------------ EVL-R2-ON
fin = {r["cell"]: r for r in load(os.path.join(HERE, "..", "reader2", "calib_r2.final.jsonl"))}
jf = {r["cell"]: r for r in load(os.path.join(HERE, "judge_fp.r2.jsonl"))} if os.path.exists(
    os.path.join(HERE, "judge_fp.r2.jsonl")) else {}
cells = {"c0": None, "c0.3|sd0.8": "P|alt|base|n42|finf|sda0.008|c0.3", "c0.5|sd0.8": "P|alt|base|n42|finf|sda0.008|c0.5",
         "c0.7|sd0.8": "P|alt|base|n42|finf|sda0.008|c0.7", "c0.5|sd1.5": "P|alt|base|n42|finf|sda0.015|c0.5",
         "c0.5|sd0.4": "P|alt|base|n42|finf|sda0.004|c0.5", "c0.7|sd1.5": "P|alt|base|n42|finf|sda0.015|c0.7"}
prior_r2 = {"c0": 0.40, "c0.3|sd0.8": 0.25, "c0.5|sd0.8": 0.20, "c0.7|sd0.8": 0.08, "c0.5|sd1.5": 0.07}
fp_base = fin["F|N1|base|n42|finf"]["pass_run1_120"]
fp_worst = max([r["pass_run1_120"] for k, r in fin.items() if k.startswith("F|")] +
               [r["pass_run1_120"] for r in jf.values()] or [0.0])
usd = {"lo": 0.138, "mid": 0.409, "line": 0.75}
rows = {}
for name, lab in cells.items():
    if lab is None:
        edge, p, tp = 0.0, fp_base, 30.0
    else:
        r = fin[lab]
        edge = r["realized_mean_a_bp"]
        tp, p = pass_session(r["by_session"])
    pnl = money(edge, p, tp, 6, 7)
    rows[name] = {"pick_mean_a_bp": round(edge, 1), "P_pass_by120": round(p, 4), "pass_session": round(tp, 1),
                  "pnl_120_usd": round(pnl, 1)}
    for k, u in usd.items():
        m = u * T
        rows[name][f"net_{k}_usd"] = round(pnl - m, 1)
        rows[name][f"pnl_per_metered_usd_{k}"] = round(pnl / m, 2)
ev = {k: round(sum(prior_r2[c] * rows[c][k] for c in prior_r2), 2) for k in ("pnl_120_usd", "net_mid_usd", "net_lo_usd",
                                                                              "net_line_usd")}
ev["pnl_per_metered_usd_mid"] = round(ev["pnl_120_usd"] / (usd["mid"] * T), 2)
ev["true_promotions_per_charge"] = round(sum(prior_r2[c] * rows[c]["P_pass_by120"] for c in prior_r2 if c != "c0"), 3)
ev["false_promotions_per_charge_base_worst"] = (round(prior_r2["c0"] * fp_base, 3), round(prior_r2["c0"] * fp_worst, 3))
ev["A102_sessions_of_done_time_per_day"] = {k: round(A102 * u, 1) for k, u in usd.items()}
out["r2"] = {"cells": rows, "prior": prior_r2, "expected": ev, "fp_base": fp_base, "fp_worst_seen": fp_worst}

# ------------------------------------------------------------------------------------------------ EVL-IDN-READ
pw = {}
for r in load(os.path.join(HERE, "..", "redteam", "screen10.power.jsonl")):
    _, _, e, n = r["lab"].split("|")
    pw[(int(e[1:]), int(n[1:]))] = r
jfi = {r["cell"]: r for r in load(os.path.join(HERE, "judge_fp.idn.jsonl"))}
fpi_base = jfi["idn|base|n8"]["run1_120"]
fpi_worst = max(r["run1_120"] for k, r in jfi.items() if "cnt|n5" in k or "cnt|n8" in k)


def idn_row(edge):
    if edge <= 0:
        p, tp = (fpi_base if edge == 0 else 0.005), 30.0
    else:
        e = min(pw, key=lambda k: (abs(k[0] - edge), abs(k[1] - 5)))
        r = pw[(e[0], 5)] if (e[0], 5) in pw else pw[e]
        p = r["pass120"]
        by = {"25": r["pass30"] * 0.8, "30": r["pass30"], "40": r["pass40"], "60": r["pass60"], "90": r["pass120"],
              "120": r["pass120"]}
        tp, _ = pass_session(by)
    return p, tp, money(edge, p, tp, 6, 6)


priors_idn = {"red team": {-30: .20, -15: .25, 0: .25, 20: .15, 30: .10, 60: .05},
              "gated": {-15: .30, 0: .35, 20: .18, 30: .12, 60: .05}}
for nm, pr in priors_idn.items():
    pnl = tp_ = 0.0
    true_p = 0.0
    tab = {}
    for e, w in pr.items():
        p, tp, m = idn_row(e)
        tab[e] = {"P_pass_by120": round(p, 4), "pnl_120_usd": round(m, 1)}
        pnl += w * m
        if e >= 20:
            true_p += w * p
    out["idn"][nm] = {"prior": pr, "cells": tab, "E_pnl_120_usd": round(pnl, 1), "metered_usd": 0.0,
                      "true_promotions_per_charge": round(true_p, 3),
                      "false_promotions_per_charge_base_worst": (round(pr.get(0, 0) * fpi_base, 3),
                                                                 round(pr.get(0, 0) * fpi_worst, 3))}
# tuition at zero edge before the gate opens (records only: no money) and after (a seat at learning)
out["idn"]["tuition_zero_edge_per_session_usd"] = {f"h_eff {h} bp": round(6 * LOT_L * (2 * h + 10 + 0.3) * 1e-4, 2)
                                                  for h in (5, 10, 15)}
with open(os.path.join(HERE, "ev_judge.out"), "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps(out, indent=1))

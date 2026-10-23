#!/usr/bin/env python
"""ev_recheck1.py: ADVERSARIAL RE-CHECK 1 of PREREG-EVL-10, section 7's expected value on ONE cost basis.
OUTCOME-FREE ARITHMETIC on the fix round's own outputs (../fix1/ev_fix1.out, ../fix1/fp_fix1.power.jsonl) and the
designer's alternative model (../reader2/calib_r2.py: Cell.mu_set = -0.0014, "the R2 set's after-cost mean a in the
alternatives (the replay's ~14 bp at liquid)"). Nothing here reads any price, return, look, band, mark or P&L.

THE POINT: every c > 0 row of ev_fix1's table takes the picks' a AFTER the replay's round trip (the alternatives'
SET mean a is mu_set = -14 bp, so c 0.3's +16.6 bp is 30.6 bp of selection less 14 bp of cost), but its "none (c 0)"
row books a = 0, i.e. no cost at all. On the table's own basis the no-information seat's picks have a = mu_set:
-14 bp on every lot. This restates the c 0 row and the prior's sums on that basis, and prints the real-fill basis
beside it (auction fills at the replay's prices, EXECUTION-FACTS' 0 bp; real fees on a learning lot: CAT $0.01 a side
and TAF $0.01 on the sale, score.py's own constants, over the mean lot at the fill), both before the overnight
benchmark b (P&L in dollars is r = a + b; b is in no row).
Run: python3 ev_recheck1.py > ev_recheck1.out"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ev = json.load(open(os.path.join(HERE, "..", "fix1", "ev_fix1.out")))
pw = {}
for line in open(os.path.join(HERE, "..", "fix1", "fp_fix1.power.jsonl")):
    r = json.loads(line)
    pw[r["cell"]] = r

T, BUYS, MU_SET_BP = 120, 6, -14.0
LOT = ev["lots"]["from $3"]["learning_lot_fill_mean"]
PRIOR_C0 = 0.40
COST = {"lo": 0.140, "mid": 0.411, "caps_mid": 0.602, "line_max": 0.75}
turnover = LOT * BUYS * T
real_fee_bp = 1e4 * (0.01 + 0.01 + 0.01) / LOT          # CAT entry + CAT exit + TAF exit, at the mean lot
replay_rt_bp = 2 * (0.5 + 5.0) + 1e4 * (0.01 + 0.02) / (0.05 * ev["E"])   # score.cost_bp at liquid, both sides
out = {"lot_fill_mean": LOT, "turnover_120_usd": round(turnover, 1), "replay_round_trip_bp_liquid": round(replay_rt_bp, 2),
       "real_fee_round_trip_bp_at_mean_lot": round(real_fee_bp, 2), "scenarios": {}}
twin = "P|alt|base|n42|cnt|finf|sda0.008|c0.5|noline"
for scen, tag in (("no starvation", None), ("L3.0|V1.42", "L3.0|V1.42"), ("L3.0|V1.6", "L3.0|V1.6"),
                  ("L3.75|V1.6", "L3.75|V1.6")):
    e = ev["ev"][scen]["expected"]
    scale = 1.0 if tag is None else pw[f"P|alt|base|n42|cnt|finf|sda0.008|c0.5|{tag}"]["picks_per_session"] / \
        pw[twin]["picks_per_session"]
    c0_pnl = MU_SET_BP * 1e-4 * turnover * scale
    row = {"c0_pnl_120_usd_on_the_table_basis": round(c0_pnl, 1)}
    for k, u in COST.items():
        row[f"c0_net_{k}_usd"] = round(c0_pnl - u * T * scale, 1)
    shift = PRIOR_C0 * c0_pnl
    fixed = {"pnl_120_usd": round(e["pnl_120_usd"] + shift, 2)}
    for k in COST:
        fixed[f"net_{k}_usd"] = round(e[f"net_{k}_usd"] + shift, 2)
    fixed["pnl_per_metered_usd_mid"] = round(fixed["pnl_120_usd"] / (COST["mid"] * T * scale), 2)
    # the real-fill basis: every row gains (replay round trip - real fees) on its turnover; c 0 is then -real fees
    lift = (replay_rt_bp - real_fee_bp) * 1e-4 * turnover * scale
    real = {"pnl_120_usd": round(fixed["pnl_120_usd"] + lift, 2)}
    for k in COST:
        real[f"net_{k}_usd"] = round(fixed[f"net_{k}_usd"] + lift, 2)
    real["c0_pnl_120_usd"] = round(-real_fee_bp * 1e-4 * turnover * scale, 1)
    out["scenarios"][scen] = {"buy_scale": round(scale, 4), "fix1_expected": e, "c0_row": row,
                              "expected_on_the_table_basis": fixed, "expected_on_the_real_fill_basis": real}
print(json.dumps(out, indent=1))

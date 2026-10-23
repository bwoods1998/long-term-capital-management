"""check2/r2_line.py: outcome-free arithmetic for adversarial check #2 of PREREG-EVL-10 (READER-2's dollars).

Reads only: league/ops/budget.py's constants (copied below from origin/main, git show), the designer's
reader2/cost_r2.out (per-read prices, holds, v1's day cost) and r2_spec.py's caps. No store, no outcome.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COST = json.loads((HERE.parent / "reader2" / "cost_r2.out").read_text())

# league/ops/budget.py (origin/main 59663f06): BASE_USD_DAY 5, LANE_USD_DAY 3, LANE_HEADROOM 1.5,
# CLOUDFLARE_USD_DAY = round(5 * 12 / 365, 4), DATA_USD_DAY 0, FLOOR_SAIL_FIXED_USD_DAY 1.5 (the docstring's example)
BASE, LANE, HEAD, CF, DATA, SAIL_FIXED = 5.0, 3.0, 1.5, round(5.0 * 12 / 365, 4), 0.0, 1.5
fixed = SAIL_FIXED + CF + DATA
room = max(0.0, BASE - fixed)
lane = min(room, max(LANE, 0.0))
rest = room - lane
print(f"COST RULE at no profit: fixed {fixed:.4f} + lane {lane:.2f} + research rest {rest:.4f} = "
      f"{fixed + lane + rest:.4f} (the cap {BASE:.2f}: every dollar allocated)")
R2_LINE = 0.75
print(f"R2 outside every line: lines + R2's own line = {fixed + lane + rest + R2_LINE:.4f} > cap {BASE:.2f} "
      f"by {R2_LINE:.2f} when every line is spent")
print(f"  without the old research roles spending: {fixed + lane + R2_LINE:.4f}")

# The proposed sub-line: R2 inside the lane's line, after 1.5 x v1's heaviest day and the births' night cap.
BIRTHS_NIGHT = 0.25
for v1_peak in (1.30, 1.42, 1.60, 1.83, 2.00):
    line_day = min(room, max(LANE, HEAD * v1_peak))
    r2 = max(0.0, min(R2_LINE, line_day - HEAD * v1_peak - BIRTHS_NIGHT))
    print(f"  v1 heaviest day ${v1_peak:.2f}: lane line {line_day:.2f}, R2 sub-line {r2:.2f}")

# Read counts and dollars at the caps (64 news + 8 docs): the score-3 always-read rule can reach the cap.
pr = COST["per_read"]["sonnet55"]
hold = COST["hold"]
for lab in ("lo", "mid", "hi"):
    d = 64 * pr[lab]["news"] + 8 * pr[lab]["8k"]
    print(f"at the caps (64 news, 8 docs), {lab} per-read cost: ${d:.3f} a day "
          f"(cost_r2.py's on_only assumed +2 score-3 reads: ${COST['on_only'][lab]['sonnet55_usd_day']:.3f})")
print(f"worst case if every capped call is lost at its hold: "
      f"${64 * hold['sonnet55_news'] + 8 * hold['sonnet55_doc']:.2f} (R2's line stops it at $0.75)")

# What the cap-filling read count does to the judge's stated net under its prior (calib/ev_judge.out, mid cost).
EV = json.loads((HERE.parent / "calib" / "ev_judge.out").read_text())["r2"]["expected"]
mid_assumed = COST["on_only"]["mid"]["sonnet55_usd_day"]
mid_caps = 64 * pr["mid"]["news"] + 8 * pr["mid"]["8k"]
extra = 120 * (mid_caps - mid_assumed)
print(f"judge's prior: net at the mid cost ${EV['net_mid_usd']:+.2f} over 120 sessions at ${mid_assumed:.3f}/day; "
      f"at the caps' ${mid_caps:.3f}/day it is ${EV['net_mid_usd'] - extra:+.2f} (120 x ${mid_caps - mid_assumed:.3f} more)")

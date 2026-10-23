#!/usr/bin/env python
"""cost_fix1.py: PREREG-EVL-10 FIX ROUND 1, READER-2's dollars after the fixes. OUTCOME-FREE ARITHMETIC ONLY: nothing
here reads the lane's store, the House, the gateway, any price, return, look, band, mark or bar.

What it recomputes, and from what:
  (1) per-read cost and the gateway's worst-case hold with the FIX-1 texts (fix1/r2_spec.py: the p_up line on the
      seat's hold and "Read on {read_day}."), by the designer's own cost model (../reader2/cost_r2.py, imported with
      fix1/r2_spec.py first on the path, so its token model runs on the new texts; its assumptions are unchanged);
  (2) a day's R2 dollars at the designer's read counts (cost_r2.py `on_only`: about 2 score-3 reads above the hash
      share) AND at the caps (64 news + 8 docs: check 2's minor 11, every score-3 issuer is read whatever h);
  (3) R2_LINE = max(0, min(0.75, L - 1.5 x V - 0.25)) (check 2's major 3, adopted in section 1.5): L the lane's line
      (house.py `verdict_line`: the lower of events.verdict_usd_day $3 and budget.py `lane_allowance`), V the heaviest
      UTC day of PROMPT-NEWS / PROMPT-DOC verdict dollars over the trailing 7 days, $0.25 the births' night cap
      (births.NIGHT_USD); and the reads each line buys at each cost case;
  (4) THE COST RULE's lines at no profit, at release 1019l's rule (league/ops/budget.py RULE_VERSION 3: $5 base, $25
      ceiling) and at the owner's goal V3's figures ($10 base, $50 ceiling; not yet the code's rule), with R2 inside
      the lane's line;
  (5) the smoke test's worst cost a call with the FIX-1 texts (fix1/smoke_r2.py's WORST must bound it).
Run: .venv/bin/python cost_fix1.py > cost_fix1.out
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                   # fix1/r2_spec.py FIRST
sys.path.append(os.path.join(HERE, "..", "reader2"))       # then the designer's cost model
import r2_spec as R                                        # noqa: E402  (fix1's)
import cost_r2 as C                                        # noqa: E402  (imports `r2_spec`: fix1's, already loaded)

assert "Read on {read_day}" in R.USER_NEWS and "Read on {read_day}" in R.USER_DOC, "fix1/r2_spec.py must load first"

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    C.main()
base = json.loads(buf.getvalue())

pr = base["per_read"]["sonnet55"]
hold = base["hold"]
out = {"source": "cost_r2.py's model on fix1/r2_spec.py's texts", "shas": {"R2-NEWS": R.sha("news"),
                                                                          "R2-DOC": R.sha("doc")},
       "per_read_sonnet55": {k: {"news": v["news"], "doc": v["8k"], "tokens": v["tokens"]} for k, v in pr.items()},
       "hold_worst_case": {"news": hold["sonnet55_news"], "doc": hold["sonnet55_doc"],
                           "news_body_bytes_max": hold["news_body_bytes_max"],
                           "doc_body_bytes_max": hold["doc_body_bytes_max"]},
       "day_designer_counts": {k: {"reads": v["reads"], "usd": v["sonnet55_usd_day"]}
                               for k, v in base["on_only"].items()},
       "day_at_caps": {}, "r2_line": {}, "cost_rule": {}, "smoke_worst": base["smoke_test"]}
for lab in ("lo", "mid", "hi"):
    out["day_at_caps"][lab] = {"reads": {"news": R.CAP_NEWS, "doc": R.CAP_8K_ON},
                               "usd": round(R.CAP_NEWS * pr[lab]["news"] + R.CAP_8K_ON * pr[lab]["8k"], 3)}
out["day_at_caps"]["worst_if_every_call_lost_at_its_hold"] = round(R.CAP_NEWS * hold["sonnet55_news"]
                                                                   + R.CAP_8K_ON * hold["sonnet55_doc"], 2)

# (3) R2_LINE and what it buys
L, HEAD, BIRTHS, R2MAX = 3.00, 1.5, 0.25, 0.75
for V in (1.00, 1.20, 1.30, 1.42, 1.50, 1.60, 1.70, 1.83, 2.00):
    line = max(0.0, min(R2MAX, L - HEAD * V - BIRTHS))
    row = {"R2_LINE": round(line, 3), "v1_keeps": round(HEAD * V, 3), "births_keep": BIRTHS}
    for lab in ("lo", "mid", "hi"):
        # reads it buys at the session's mix (docs first in qualification order is not assumed: the mix of the caps,
        # 64 news : 8 docs), and the share of the caps' day it covers
        mix = (R.CAP_NEWS * pr[lab]["news"] + R.CAP_8K_ON * pr[lab]["8k"]) / (R.CAP_NEWS + R.CAP_8K_ON)
        row[f"reads_bought_{lab}"] = int(line / mix) if mix > 0 else None
        row[f"share_of_caps_day_{lab}"] = round(min(1.0, line / out["day_at_caps"][lab]["usd"]), 3)
        row[f"share_of_designer_day_{lab}"] = round(min(1.0, line / out["day_designer_counts"][lab]["usd"]), 3) \
            if out["day_designer_counts"][lab]["usd"] > 0 else None
    out["r2_line"][f"V={V:.2f}"] = row

# (4) THE COST RULE's lines at no profit (budget.py's arithmetic; Sail's fixed $1.50 is the docstring's own example)
CF, SAIL_FIXED, DATA = round(5.0 * 12 / 365, 4), 1.5, 0.0
fixed = SAIL_FIXED + CF + DATA
for name, base_usd, ceiling in (("release 1019l (RULE_VERSION 3, the goal of Oct 19)", 5.0, 25.0),
                                ("goal V3 (Oct 23; not yet the code's rule)", 10.0, 50.0)):
    room = max(0.0, base_usd - fixed)
    lane = min(room, max(3.0, 0.0))
    rest = room - lane
    out["cost_rule"][name] = {"cap_no_profit": base_usd, "ceiling": ceiling, "fixed": round(fixed, 4),
                              "lane_line_L": round(lane, 2), "research_rest": round(rest, 4),
                              "sum": round(fixed + lane + rest, 4),
                              "R2_inside_the_lane": "yes: R2 + v1 + births <= L, so no R2 dollar can make a cap breach"}

# (5) smoke worst with the fix-1 texts (cost_r2.py's own smoke model, pessimistic overhead)
out["smoke_worst"]["fix1_WORST_constants_bound_it"] = {
    "doc": base["smoke_test"]["doc"]["worst_usd"] <= 0.0078, "news": base["smoke_test"]["news"]["worst_usd"] <= 0.0061}
print(json.dumps(out, indent=1))

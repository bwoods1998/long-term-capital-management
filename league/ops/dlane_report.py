"""The `dlane` job (at the House's start, daily 01:30Z and before each open) and THE DIRECTION LANE's report (release
D-1, Oct 9, 2026; `league/swarm/dlane.py`; the plan of Oct 9, D8 and its section 6; the operator's decisions 8 and 9):
one operator-only file, `<state>/dlane-report.json`, that says each day what the two research lanes did, what the Probe
envelope holds, where the goal's Done stands under its pinned reading rule, and which of the lane's alarms hold.

OPERATOR-ONLY AND REPORTED: no agent reads it, and no module of league/swarm, league/live or league/gym imports this
module or names its file (`league/tests/test_dlane_report.py` pins that). It changes no site data contract: the website
reads nothing new. It is written whatever the figures say; it never pauses, slows or stops a program or a route.

READ-ONLY, BUT FOR K5 AND THE PROGRAM LOSS LINE. The swarm store is opened read-only and the live book through
`guard.read` (`mode=ro`), inside
`guard.readonly()` (every SQLite open in the child is a `mode=ro` URI). The one write is K5's (decision 9): when the
direction lane's realized net over every route since the options swarm began is at or below K5's line (`dlane.k5_line`:
`dlane.k5_net_usd`, -$600, below the net at the operator's last clear; -$600 itself before any), the job writes the swarm
store's kv `dlane_k5` {at, net, line} once (`dlane.k5_trip`, a writable open AFTER the read-only report). While it is
set the lane reads "shadow" (`dlane.mode_effective`: no new direction Candidate, no incubator direction mark) until the
operator clears it (swarm.json `dlane.k5_clear` true, or deleting the kv). The job records a clear on its next run
(`dlane.k5_rearm`, before the trip check: the kv deleted, the kv `dlane_k5_base` at the net then), so the clear holds
and K5 is armed again at -$600 below that net (the review of Oct 9, 2026). While `dlane.k5_clear` is true K5 can
neither hold nor trip: the report raises a K5 warning every run until the operator takes it out. A tightening, never a
trade, never an order. The second write (DONE-RULE-A1 A1.3, Oct 10, 2026; `retire_due`): a program whose own realized
Probe net is at or below the program loss line (`dlane.program_loss_usd`: -$300 since THE PROBE TOTAL AT $800, PREREG-T,
Oct 10, 2026; -$200 before it) is retired swarm-side, in the same writable open after the report; its real positions
exit by the House's rules (alarm PL1).

WITH THE LANE OFF (`dlane.mode` "off", THE ROLLBACK) the job writes no report and returns a `skipped` receipt, but for
the program loss line: since the review of the weekend fixes (Oct 10, 2026) it still reads each program's realized Probe
net and retires a due one (`lane_off`; A1.3 names one program whatever its lane, and the rollback is the lane's, not the
pinned rule's), each PL1 a House warning and the receipt carrying the figures.

WHEN IT RUNS: at the House's start, daily at 01:30Z, and since the review of the weekend fixes (Oct 10, 2026) on each
trading day 30 minutes before the open. A Probe position held to expiry is `awaiting_expiry` until the House's quiet
passes reconcile the broker's expiry; pid 14's (Oct 7) landed at 01:11Z, minutes before the 01:30Z run, and from Nov 1
(New York on standard time) the same 21:11 New York time is 02:11Z, after it. Without the pre-open run a program whose
expiry carried it past the program loss line would trade one more session before the next 01:30Z run retired it.

THE DONE METER (DONE-RULE.md, pinned Oct 9, 2026 before release L-D or D-1 shipped; `dlane.DONE` holds its sha256 and
constants), read exactly as pinned:
- WHAT COUNTS: every real close of an agent program (a swarm family; never a House route: the calibration round trips,
  the House live test, any `house:*` family) closed since 2026-09-26T06:23Z on Probe/Sized `:r`, tuition `:t` or the
  incubator `:i` (`economics.route_of`), the Oct 8 tuition close included. Nothing is dropped after the fact: a close on
  an agent route the rule does not name is listed apart with a House warning, never silently counted or lost.
- P&L: realized after all fees: the book's cash (fees included at the book's estimate) plus the broker's posted fee
  correction where it has posted (`publish.json`'s saved activity reading, `fees_by_pid`: `league/account_activity.py`),
  each close labelled `broker` or `estimate`. A close the book could not price (`unpriced_close`) makes a meter's net
  unknown, never an invented zero.
- TWO METERS: `done_screen` (`:r` only, the evidence route) and `done_all` (`:r` + `:t` + `:i`, the goal's letter).
- THE BAR: at least 30 closes, at least 5 closes from each of at least 2 programs, and net > 0 after fees.
- CONSISTENT WITH REPLAY: every program with 5 or more MATCHED closes (closes of a version on a day its nightly replay
  also traded: D5's measure, `money.forward_stats`, read here live minus replay and pooled over the program's versions;
  `GAP_MEASURE` says it is a ratio of sums) has a gap within +/-0.10 a dollar of maximum loss, AND (DONE-RULE-A1 A1.1,
  Oct 10, 2026) at least 2 programs are so measured: zero matched closes never passes. Every program is listed with its
  closes, matched closes and gap (each checkpoint's `by_program`, `replay_coverage`), never dropped.
- RESEARCH 24/7 (DONE-RULE item 7; `Research247`, Oct 10, 2026): births, Gym runs and Validations every UTC day of the
  checkpoint's window (its last 7 days for the first, every day since the one before for the rest), at the research
  budget, with no owner step waiting (the `stall` job's receipts: a day with none is not held); the operator's edits
  listed beside it.
  THE PER-CLOSE TWIN (Oct 10, 2026; the readiness audit's B1 (c); `league/ops/twins.py`): a close whose own replay
  twin is priced (the real trade's own orders replayed on the gate image by the Gym's engine and fill model, the swarm's
  kv `close_twins`) is matched to that twin, live minus twin per dollar of each one's maximum loss, pooled with the rest
  as D5's ratio of sums; a close whose twin is final but unpriced (the model did not fill the real open, the image lacks
  the contract or the day, the trade cannot be replayed) is counted by its verdict and never matched to the nightly
  replay instead; a close with no twin record (none yet, or the twins switched off) is matched by (version, entry day)
  to the nightly replay exactly as before. With no twin record at all a program's figures are exactly D5's, key for key.
  `replay_twins` lists every counted close with its twin's verdict.
- READ ONLY AT CHECKPOINTS: the 30th counted close, then every 10th; each reading is over exactly the first K closes in
  close order (`checkpoints`); it holds when items 3, 4 and 7 hold. The running figures between checkpoints are counts,
  never a reading. FINAL READINGS (DONE-RULE-A1 A1.4; `finality`): a reading is final once every counted close's
  replay has landed (its own twin final, with the twins on; else its program's nightly) and its broker fees have posted
  (and the research window has ended); a final reading is frozen (carried from the previous report as it was). A Done claim is a holding FINAL checkpoint (the meter's `holds`);
  A8 (an `info` alert) names one the first time a report sees it final.
- BESIDE IT, ALWAYS: P(Done | zero edge) (`dlane.done_zero_edge_p`, labelled as a simulation; since DONE-RULE-A1 A1.2
  the figure for the rules in force with its horizon, holds, budget and source, `zero_edge`: 2.7% since THE PROBE
  TOTAL AT $800, Oct 10, 2026, PREREG-T's at roster 5; 2.4%, A1.2's pin, under L-D's $400 total before it; both kept
  labelled in `dlane.ZERO_EDGES`); Net after costs (`net_after_costs`, from the close economics over the same days);
  the same-risk buy-and-hold two ways (below); the world-conditional false-positive rate beside the unconditional one
  for the screen that admitted each Candidate, Probe or Sized family (`probes`, with each program's own realized Probe
  net and when DM1 can first fire, A1.3); every loosened rule with its cost (`LOOSENED`); the contamination statement
  (`CONTAMINATION`); and `dlane.LABEL` on every direction figure.

THE SAME-RISK BUY-AND-HOLD (the plan's section 6, item 3), per counted close, summed beside each meter and checkpoint.
Both are labelled approximations from the `direction` job's daily closes (`direction-closes.json`):
- delta-matched: the structure's entry delta (Black-Scholes at ONE implied volatility solved from its entry value, the
  entry day's close as the spot: `league.options_history`), times 100 x its units, held in the root's own stock from the
  entry day's close to the exit day's close. An index root with no stock bars (XSP, SPXW) is not priced this way.
- dollars at risk: the close's maximum loss held in the root (SPY standing in for XSP and SPXW) over the same closes.

THE REST OF THE REPORT:
- `funnel`, per lane over the last 24 hours and 7 days, each count from the record that is the event itself: births
  (`swarm.born`; the payload's lane, else the family's declared lane), Gym runs by window and the program-years they
  cost (the Gym is shared: direction runs slow alpha's), Validation tries and passes (`swarm.tournament`), reviews and
  audits (`swarm.gate`), holdout looks and passes by the screen each look recorded, band moves, real closes by route; the
  bands now; and the direction lane's Train-bar failure counts (`dlane.failure_counts`).
- `fp_beside_trades` (release D-1b; the owner's goal of Oct 9, item 4): every real Probe trade (`:r`, open or closed)
  and every agent real close, each with its program's screen and that screen's false-positive rates at zero edge
  ({screen, fp_lane_mixed, fp_lane_2224, receipt}: the passed look of the version it trades, `trade_screens`), and the
  contamination statement beside them.
- `probe_envelope`: THE PROBE LOSS BUDGET as release L-D's money table reads it from the constitution (`loss_basis`
  "net", $400 of worst net stretch in any `loss_window_sessions` 20 sessions AND `loss_total_usd` net in total, $800
  since Oct 10, 2026 and $400 before, `max_open`, `demotion`): the code in force's own figure
  (`fast_lane.probe_budget`, which names its basis and the envelope that binds), and under each basis, GROSS and NET,
  the window's and the total's realized figures (`real.probe_figures`, told the basis by name), both rooms, the binding
  one and the room in units of today's cap.
- `account`: the equity change since E0 (the first equity reading this report saw: it is written into the file and read
  back next day) beside the agents' and the House's realized closes since then and the account's other activity; what
  is left is labelled unexplained (open positions' marks included).
- `costs`: the swarm's BOOKED research spend by meter since the options swarm began and since the lane started,
  comparison only since Oct 10, 2026: the Net beside the meter is `done.net_after_costs` (every input cost on the close
  economics' billed and metered basis, the gateway's Claude meter included).
- `program_loss` (DONE-RULE-A1 A1.3): each program's own realized Probe net against the program loss line, the programs
  due and the ones this run retired.
- `roster` (THE PROBE ROSTER, Oct 10, 2026; `league/swarm/bands.py` `roster`): the seats (`dlane.roster`), the Probe
  families, the seated families and the Candidates waiting for a seat; None while the roster is off. THE PROBE TOTAL AT
  $800 (PREREG-T, Oct 10, 2026) and its -$300 program loss line were measured at roster 5 alone, and the roster is a
  swarm.json switch (no deploy) while the pair is the owner's deploy: PT1 warns while the pair runs beside any other
  roster (`pt1_alarms`).
- `contamination.meters`: (a) the holdout's head-minus-tail Sharpe gap per lane (`fast_lane.pooled_contamination` over
  the fast lane report's looks), (b) the mean excess over the same-risk buy-and-hold in the known window (Validation)
  against the unknown one (live), per lane, (c) live against the holdout per band (the fast lane report's rows).
- `alarms`: A1-A9, PL1 (the program loss line), PT1 (the $800 total off roster 5) and K5 (HARNESS section 5, as amended
  by the plan and the operator's decisions; K5 also while `dlane.k5_clear` disarms it), each a House alert through
  `ctx.alert` (warning, or info for A8 and A9), never an action on money. The `stall` job reads the warnings and A8 from this file and mails them (its
  `dlane` and `done` causes).

Standard library only, except the Probe envelope's figures (`fast_lane.probe_budget` and `real.probe_figures` read
`league.live.real`, whose Gym legs need numpy, as the House box has): they are an `error` entry where that cannot load.
"""
from __future__ import annotations

import json
import math
import statistics
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

FILE = "dlane-report.json"
SCHEMA = 1
#: The House's state files this report reads (never writes, but its own).
LIVE_DB = "live.sqlite"
PUBLISH_FILE = "publish.json"
FAST_LANE_FILE = "fast-lane-report.json"
HEALTH_FILE = "health.json"
#: `economics.route_of`'s agent routes, as the Done rule names them; the House's routes are never counted.
ROUTE_CODES = {"d2_real": ":r", "tuition": ":t", "incubator": ":i"}
HOUSE_ROUTES = ("calibration", "house_test", "house_other")
#: The funnel's windows, in hours.
WINDOWS = {"24h": 24.0, "7d": 168.0}
#: The Gym windows the funnel counts.
RUN_WINDOWS = ("train", "validation", "holdout", "mechanism", "forward", "probe")
#: A run row with one of these statuses is not a Gym evaluation (`funnel.NOT_RUN`).
NOT_RUN = ("refused", "error")
#: A3's waits (HARNESS section 5): a direction best that cleared every Train bar waits for its Validation more than this
#: many hours; a direction version that entered the gate (a Validation pass, or D2's pre-check: M5, Oct 10, 2026) waits
#: for its holdout look more than this many.
A3_VALIDATION_HOURS = 6.0
A3_GATE_HOURS = 12.0
#: A2: a direction version cleared every Train bar this long ago and no direction Validation try or look since.
A2_HOURS = 24.0
#: A6 (K7): fewer than 1 eligible direction version per this many direction births over 48 hours, judged once the 48
#: hours hold at least this many births (fewer cannot show the ratio).
A6_BIRTHS = 50
A6_HOURS = 48.0
#: A9: every live direction program has opened nothing for this many sessions.
A9_SESSIONS = 10
#: The label of the zero-edge figure (decision 8).
ZERO_EDGE_LABEL = "P(Done | zero edge), simulation"
#: PT1 (THE PROBE TOTAL AT $800, Oct 10, 2026): PREREG-T measured the $800 total and the -$300 program loss line at this
#: roster alone (at no roster the operator's grid found the $800 total almost all cost), and L-D's $400 total and -$200
#: line are the rules it measured them against.
PT1_ROSTER = 5
PT1_TOTAL_USD = 400.0
PT1_LINE_USD = -200.0

#: THE CONTAMINATION STATEMENT (the plan's section 6, extended by the critic's N10 and the operator's decision 8: the
#: 2017-19 census is spent for the direction lane as a whole). In every report, verbatim but for two figures of the
#: operator's private studies, which stay private (the operator's rule: no private-study figure in the repository).
CONTAMINATION = (
    "Train (2022-24), Validation (2025) and most of the holdout (Jan-Sep 2026) lie inside the training data of every "
    "author: the swarm's models and the operators who designed this lane (Claude Opus 5.5, data to June 2026). They know "
    "which of those windows rose. A direction program passes Validation and the look almost only when both windows rose "
    "(nearly every pass in the operator's simulated worlds). So the screen's false-positive rate is a property of the "
    "procedure across historical worlds, not a guarantee in this one. Choosing to open a direction lane now was itself "
    "made by authors who know those years, and that cannot be measured. The 2017-19 census is spent: for the operator's "
    "gates (in-sample, unconfirmed) and for the direction lane as a whole (its guidance on deltas and holds came from "
    "it), so a 2017-19 era is no clean confirmation for a direction program. The clean evidence is the holdout tail after "
    "2026-07-01 (partly) and the live record from the first real close. Done is decided on that record. Measured each "
    "day: (a) the holdout's Sharpe gap before and after 2026-07-01 per look, pooled with its t; (b) the excess over the "
    "same-risk buy-and-hold, in known windows minus unknown ones; (c) live against the holdout, per dollar of maximum "
    "loss, per band."
)

#: EVERY LOOSENED RULE WITH ITS COST (HARNESS 7.4, the plan's section 2 and the operator's decisions of Oct 9): the
#: header of every report (the plan's section 6, item 5). Costs are the operator's measurements (MONEY's simulation and
#: the critic's), stated as measured; release L-D's rows are its own release's, listed because they ride beside every
#: Done figure.
LOOSENED: tuple[dict[str, str], ...] = (
    {"rule": "beat your own exposure", "was": "every family (agenda v19 item 2)", "now": "the alpha lane only",
     "cost": "programs whose profit is index beta reach Validation; the lane is leveraged index beta minus option "
             "costs, reported beside the same-risk buy-and-hold, never called alpha"},
    {"rule": "the Train objective", "was": "the worst Train year's t",
     "now": "direction-v2 for the direction lane: E1, E3, E4, E5 on the 1.0x run; P1, R2, R3 on the 1.5x run; E2, R1 "
            "and the mechanism test reported only; holds of 2 to 8 sessions all admissible",
     "cost": "an always-in call program can pass this bar and the gate is not tested by it; more null programs reach "
             "Validation (more paid reviews and audits, more false passes in count); the false-positive rate per "
             "program screened is unchanged (Train is in-sample)"},
    {"rule": "the hidden look (the learning game)", "was": "every core-five lineage may play",
     "now": "no direction lineage plays (dlane.arm_fraction 0)",
     "cost": "the game's selection pressure is lost for direction; the lane's false-positive rate at zero edge rises "
             "from 0.02% to 0.70% before the screen change below"},
    {"rule": "the holdout look (screen S-C)", "was": "p <= 0.10 and a Sharpe of at least 0.5 of Validation's (S-B)",
     "now": "direction lane only: p <= 0.20 and a Sharpe share of 0.25; the Validation line as coded (since release "
            "D-1b the rollback screen: swarm.json dlane.screen \"S-C\")",
     "cost": "false-positive rate at zero edge: the lane 0.70% -> 1.41% (cluster interval 0.54-2.43%), all cells "
             "0.80% -> 1.53%, swarm placebos 0.18% -> 0.27%; 2.22% when both windows rose; power at +10%: "
             "1.68% -> 3.22%"},
    {"rule": "the holdout look (screen D2, release D-1b)", "was": "S-C (above)",
     "now": "direction lane only, calls only: on Validation at least 50 trades on 25 entry days with a mean entry-day "
            "return above zero; after the one look, the pooled entry-day t over Validation and the holdout at least "
            "c = 1.00 and the holdout's P&L above zero (receipt docs/benchmarks/direction_screen_2.json, sha c3605947)",
     "cost": "the lane's false-positive rate per program at zero edge 1.41% -> 10.37% on mixed worlds (95% world "
             "interval 9.57-11.16%, cluster 7.90-12.76%) and 12.39% on 2022-24 worlds (upper bound 13.29%); all "
             "census cells 13.37% (upper bound 14.08%) and 14.11% on 2022-24 worlds (upper bound 15.01%); swarm "
             "placebos 4.76%; power at +10% 3.22% -> 19.95%. Adopted AFTER it failed the operator's own pre-registered "
             "adoption rule (every upper bound at most 12%): a post-hoc loosening of that ceiling. The lane's rate "
             "stays under the owner's 15% per program; all cells (verticals included) reach 15.01% at the upper bound "
             "on 2022-24 worlds, which is why D2 runs only while the lane is calls only. Weak discrimination: it "
             "passes mostly programs whose screen windows rose; the Probe loss budget ($400 of worst net stretch "
             "in any 20 sessions and $800 net in total since Oct 10; $400 in total at release L-D) bounds the money"},
    {"rule": "the leakage alarm", "was": "one count over every look: 10 looks, over 30% passing",
     "now": "per lane: alpha unchanged; direction 10 looks, over 60% passing",
     "cost": "a real holdout leak in a direction program trips later; the paid review and audit and the post-cutoff "
             "tail still check every look"},
    {"rule": "the incubator mark", "was": "the drift screen alone (the owner's term, Sept 29-30)",
     "now": "direction families: the direction-v2 verdict",
     "cost": "with no edge about -$36 a week expected, at most $150 a week (about $650 a month); its closes are never "
             "evidence"},
    {"rule": "graveyard DRIFT rows", "was": "bind every card", "now": "do not bind a direction card",
     "cost": "direction ideas the drift screen buried may return, once each, inside the rebirth budgets"},
    {"rule": "graveyard alpha rows (PR #519, deployed 12:44Z Oct 9)", "was": "bind every card",
     "now": "a direction card is bound only by direction families' graveyard rows (DRIFT rows never); alpha cards are "
            "bound by every row, as before",
     "cost": "more direction births may retry ideas similar to dead alpha ones; each lineage still gets one Validation "
             "try and one holdout look, at D2's measured false-positive rate of 10.4% per program (mixed worlds)"},
    {"rule": "the birth quota", "was": "no lane",
     "now": "direction gets at least half of a pass's births while under half of the last 24 hours' (at most 60%)",
     "cost": "alpha births fall from about 73 to about 36 a day mid-way through the game's T0 experiment; the "
             "researcher's ROLE prompt (a shared prefix) changes for alpha researchers too, so 'alpha golden' holds "
             "for code paths only"},
    {"rule": "the unit", "was": "MONEY's pre-registered $75 lane cap",
     "now": "10% of equity on the swarm side (E5) as on the live side",
     "cost": "Probe-stage Done averaged over holds 6.3% against 7.8%; P(net <= -$360 in 8 weeks) 0.35 against 0.27"},
    {"rule": "K5's clear (dlane.k5_clear)", "was": "no K5 before D-1",
     "now": "true clears a set K5 at once and disarms K5 while it stays set; the job's next run records the clear and "
            "re-arms K5 at -$600 below the net then (deleting the kv clears the same way, with no setting)",
     "cost": "while dlane.k5_clear stays true the lane can lose past any line with no K5 (the report warns every run "
             "until it is taken out); after a clear, K5 measures a further -$600 from the net at clearing, not from "
             "inception"},
    # THE TRAIN MAP (Oct 9, 2026; PR #520). The graveyard fix's row sits beside the DRIFT rows' above.
    {"rule": "the TRAIN MAP (dlane.train_map; PR #520, deployed 16:17Z Oct 9)",
     "was": "agents read the lane's rules and their own runs, never an operator study's figure",
     "now": "the architect's LANES block lists the call shapes that pass direction-v2 on the Train years in the "
            "operator's census (one line each: S_D to one decimal, the unit's verdict as a word) and the census's "
            "lessons; a direction researcher's brief the lessons and the 5 best passing shapes on its roots; labelled "
            "in-sample (league/swarm/dlane_map.json); swarm.json dlane.train_map false hides it",
     "cost": "births aim at in-sample winners, so more programs whose Train profit is index beta reach the screen; the "
             "screen's false-positive rate per program is unchanged (Train is in-sample), and more programs screened "
             "means more false passes in count (more paid reviews and audits)"},
    {"rule": "release L-D: the Probe budget read NET", "was": "GROSS: a gain never offsets a loss",
     "now": "NET over closed Probe positions (Sized never offsets): in the window its worst net stretch (a gain offsets "
            "only the losses closed before it), in total from inception",
     "cost": "P(net <= -$360 in 8 weeks, no edge) 0.19 -> 0.27; gross Probe losses can pass $400"},
    {"rule": "release L-D: Probe slots", "was": "3", "now": "8 (the $400 window's envelope binds first)",
     "cost": "P(net <= -$360) 0.30 -> 0.35; P(net < -$400) 2.1%, through Sized"},
    {"rule": "release L-D: DM1 demotion", "was": "D5's loss leg (-3 x mean maximum loss)",
     "now": "sticky demotion when 10+ real trades sum below -1.645 sigma sqrt(n)",
     "cost": "a losing program trades longer: P(net <= -$360) 0.27 -> 0.30"},
    # THE PROBE TOTAL AT $800 (PREREG-T, Oct 10, 2026, under the Probe roster): the constitution's total and the program
    # loss line beside it. PREREG-T ran three arms ($400 and -$200; $800 and -$200; $800 and -$300), so each row has its
    # own cost: the total's row the pair as adopted, with the total alone beside it, and the line's row its own step over
    # the $800 total alone. The figures are the operator's pre-registered simulation's (no year named: the header
    # carries none); P(net below -$400 / -$600) reads the agents' running real net, the Probe/Sized route and the
    # incubator together, not the Probe alone.
    {"rule": "the Probe total (PREREG-T, Oct 10)", "was": "$400 net in total from inception (release L-D's setting)",
     "now": "$800 net in total, the owner's ceiling; the $400 in any 20 sessions, the 10% cap, 3 a family, 8 slots, "
            "DM1 and the stops unchanged (rollback: options_money.probe.loss_total_usd 400 with the line below, an "
            "owner deploy)",
     "cost": "simulation (cross-fit, fixed 2-, 3- and 5-session holds standing in for the House's pool, roster 5, "
             "arrivals; index beta minus option costs, not alpha), with the -$300 line below (the pair as adopted): "
             "P(the agents' running real net below -$400 within 12 weeks) 17.8% -> 36.8%, below -$600 0.6% -> 4.4%; "
             "the 12-week net's 5th percentile -$396 -> -$679; P(the 60% drawdown stop trips by 24 weeks) 21% -> 48%; "
             "mean 12-week net +$22 -> +$25, median -$327 -> -$231; for P(Done) 4.6% -> 5.5% at 12 weeks and 11.6% -> "
             "14.4% at 24, and P(Done | zero edge) 2.2% -> 2.7% and 6.9% -> 9.0%. The total alone (the -$200 line "
             "kept): 35.8%, 4.1%, -$674 and 46%, for P(Done) 5.3% and 14.2%. Measured at roster 5 alone (at no roster "
             "almost all cost): a roster rollback or another roster needs this rollback too, or a new measurement "
             "first (alarm PT1)"},
    {"rule": "the program loss line (PREREG-T, Oct 10)", "was": "-$200 (DONE-RULE-A1 A1.3)",
     "now": "-$300 (dlane.program_loss_usd; rollback -200 with the $400 total, an owner deploy)",
     "cost": "one program may lose $300 of its own realized Probe net, not $200, before the dlane job retires it, "
             "so a bad program spends up to $100 more of the shared total (3/8 of the $800, where -$200 was half the "
             "$400). Its own step, against the $800 total with the -$200 line (the same simulation, paired): P(the "
             "agents' running real net below -$400 within 12 weeks) 35.8% -> 36.8%, below -$600 4.1% -> 4.4%; P(the "
             "drawdown stop trips by 24 weeks) 46% -> 48%; P(Done | zero edge) 2.5% -> 2.7% at 12 weeks; for P(Done) "
             "5.3% -> 5.5% at 12 weeks (paired +0.24 points, SE 0.12: past the pre-registered 2-paired-SE preference "
             "for the total alone by a hair, 2.06 SE). Measured at roster 5 alone, as the row above"},
    # THE ALWAYS-IN CARD (Oct 10, 2026; league/swarm/cards.py, dlane.py, architect.py): the lane's own instrument could
    # not be born past the gated ideas refuted in its cells.
    {"rule": "the graveyard for an always-in direction card (Oct 10)",
     "was": "a direction card was bound by every direction family's row in its cell whose inputs overlap its own; an "
            "always-in card reads the clock, so each gated idea refuted there (22-43 rows a cell) bound it, and no "
            "claim could free it (it reads nothing a claim could add)",
     "now": "a direction card whose declared inputs are exactly [\"clock\"] (always-in: it enters every session, no "
            "gate) is bound only by the always-in direction rows on its roots, any class or holding; its birth joins "
            "the always-in lineage on each of its roots, ONE Validation try a root; G1: its program must enter on 90% "
            "of the Train sessions it is flat on, or it is never validated and retires; alpha cards and gated direction "
            "cards are judged as before",
     "cost": "at most one always-in Validation try per root (SPY, QQQ, IWM), ever, unless the owner changes "
             "dlane.val_tries (fewer when a family on two roots joins their lineages): each is the lane's D2 lottery at "
             "10.37% per program at zero edge on mixed worlds (12.39% on 2022-24 worlds; higher when the screen windows "
             "rose), so up to three more such lotteries in all; their profit is index beta minus option costs, reported "
             "beside the same-risk buy-and-hold, never alpha; a program never flat on Train could add gated entries on "
             "top of its always-in position, which G1 cannot see"},
)
#: And what D-1 TIGHTENED (said beside the loosenings), with release L-D's rolling budget, a tightening of its NET.
TIGHTENED: tuple[str, ...] = (
    "K5: the lane reads shadow (no new direction Candidate, no incubator direction mark) once its realized net over every "
    "route is at or below -$600 (after a clear: -$600 below the net at clearing), until the operator clears it",
    "the screen, the leakage alarm and K5's line can only be tightened by a setting (dlane.cfg's bounds); the one "
    "setting that loosens K5 is dlane.k5_clear, which disarms it while it is true (listed with its cost among the "
    "loosened rules)",
    "D2 is refused unless a receipt's sha256 and its c are pinned in the repository's policy.json and CI holds the "
    "receipt to it, and unless the lane is calls only (release D-1b)",
    "E5: one lot at today's prices within 10% of equity before Validation",
    "R3 (the readiness audit of Oct 9, m3): the 1.5x run is compared with a 1.0x Train P&L above zero; a version "
    "that lost money on Train at 1.0x fails R3 (until then R3 always passed it: eqp-term-contango-pool-call v6, -$1,778 "
    "at 1.0x and +$143 at 1.5x, spent its lineage's one Validation try)",
    "the ration before the cohort keep (the readiness audit of Oct 9, M3): a direction family whose lineage spent "
    "its one try or look retires even while the cohort keep holds it, so its slot is freed and its program loses the "
    "incubator route; the alpha lane keeps the keep's order",
    "release D-1b: ONE Validation try and ONE holdout look per direction lineage (was: the alpha lane's three looks and "
    "tries until retirement), so a lineage's false-positive rate is the program's; a lineage that spends either without "
    "a pass still in play retires",
    "release D-1b: calls only: dlane.structures [\"long_single\"] (no debit vertical, no put) and every Train trade a long "
    "call (bar C1)",
    # DONE-RULE-A1 (pinned Oct 9, 2026 ~20:50Z, before the first Probe close; read by the code since the weekend fixes).
    "DONE-RULE-A1 A1.1: a Done claim also needs 2 programs with 5+ matched replay closes each, every one within the gap: "
    "zero replay evidence never passes (it did: B1)",
    "DONE-RULE-A1 A1.3: a program whose own realized Probe net is at or below dlane.program_loss_usd (-$300 since "
    "Oct 10, with the $800 total; -$200 before) is retired swarm-side by the dlane job (exits go on), since DM1 cannot "
    "fire before about 17 real trades",
    "DONE-RULE-A1 A1.4 and item 7: a checkpoint holds only with research 24/7 read per UTC day, and a Done claim is made "
    "only on a FINAL reading (replays landed, broker fees posted), frozen once final",
    "release L-D's rolling Probe budget (L9, beside NET above): the $400 is a wall over any 20 New York sessions, read "
    "as the window's worst net stretch, AND a net total from inception ($400 as L-D set it; the owner's $800 since "
    "Oct 10, a loosening listed with its cost); a bad stretch that ages out of the window frees no room in the total. "
    "Measured cost of the window (the budget simulation, post-hoc, as traded, holds 2/3/5): P(Done) at 12 weeks "
    "6.0/3.3/1.0% against 10.0/7.6/4.5% with the $400 total alone, at 24 weeks 11.1/8.7/5.9% against 11.0/9.0/7.6%",
)


# ------------------------------------------------------------------------------------------------- small helpers
def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _dec(value: Any) -> Decimal | None:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return out if out.is_finite() else None


def _usd(value: Decimal | float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _epoch(text: Any) -> float | None:
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _ny_day(epoch: float | None) -> str | None:
    from zoneinfo import ZoneInfo

    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), ZoneInfo("America/New_York")).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _loads(text: Any, default: Any) -> Any:
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text) if text not in (None, "") else default
    except (TypeError, ValueError):
        return default


def version_of(instance: Any) -> int | None:
    """The program version an instance key names (`<family>@<version>:<kind>`), as `league/live/step.py` reads it."""
    try:
        return int(str(instance).rsplit("@", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return None


def inception() -> float:
    """The Done rule's start (`dlane.DONE["inception"]`) as epoch seconds."""
    from ..swarm import dlane

    return float(_epoch(dlane.DONE["inception"]))


# ------------------------------------------------------------------------------------------------- the lanes
class Lanes:
    """Each family's declared lane (`dlane.declared_lane`: its spec's, else its card's), read once a family."""

    def __init__(self, store: Any):
        self.store = store
        self.cache: dict[str, str] = {}

    def of(self, fid: Any, fam: Mapping[str, Any] | None = None) -> str:
        from ..swarm import dlane

        fid = str(fid or "")
        if fid not in self.cache:
            try:
                fam = fam if fam is not None else self.store.family(fid)
            except Exception:  # noqa: BLE001 - an unreadable family is alpha (the lane's default)
                fam = None
            self.cache[fid] = dlane.declared_lane(self.store, fam) if fam is not None else dlane.ALPHA
        return self.cache[fid]


# ------------------------------------------------------------------------------------------------- the book
def read_book(live_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """The live book's positions and instances (read-only; an absent book is an empty one: nothing traded)."""
    from . import guard

    path = Path(live_path)
    if not path.exists():
        return {"positions": [], "instances": []}

    def read(db: Any) -> dict[str, list[dict[str, Any]]]:
        tables = set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'"))
        positions = guard.rows(db, "SELECT pid, instance, family, type, root, legs, qty, opened_qty, entry, max_loss_share, "
                                   "fees, cash, opened_at, opened_day, status, closed_at, tuition, info FROM positions "
                                   "ORDER BY pid") if "positions" in tables else []
        instances = guard.rows(db, "SELECT id, family, version, band, tuition, mode, created_at, retired_at FROM instances"
                               ) if "instances" in tables else []
        return {"positions": positions, "instances": instances}

    return guard.read(path, read)


def fee_corrections(root: str | Path) -> dict[str, Any]:
    """The broker's posted fee corrections per position (`publish.json`'s saved activity reading: `fees_by_pid`, the
    broker's charged fees less the book's estimates, `league/account_activity.py`) and the account's other activity, or
    {} parts with `why` when there is no reading."""
    out: dict[str, Any] = {"by_pid": {}, "as_of": None, "read_at": None, "other": None, "why": None}
    try:
        saved = json.loads((Path(root) / PUBLISH_FILE).read_text(encoding="utf-8")).get("activity")
        reading = saved["reading"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        out["why"] = "no saved activity reading in publish.json: every close's fees are the book's estimate"
        return out
    for pid, value in (reading.get("fees_by_pid") or {}).items():
        d = _dec(value)
        if d is not None and str(pid).isdigit():
            out["by_pid"][int(pid)] = d
    out["as_of"], out["read_at"] = reading.get("as_of"), saved.get("read_at")
    out["other"] = {k: _usd(_dec(reading.get(k))) for k in ("fees_usd", "crypto_usd", "interest_usd", "misc_usd",
                                                            "unreconciled_usd")}
    return out


def closes(positions: Sequence[Mapping[str, Any]], corrections: Mapping[int, Decimal], *, since: float,
           lanes: Lanes | None = None) -> list[dict[str, Any]]:
    """Every real close since `since` (epoch) in close order (closed_at, then pid), routed (`economics.route_of`):
    {pid, family, instance, version, route, code, house, lane, closed_at, day, opened_day, opened_at, root, type, legs,
    entry, opened_qty, max_loss_usd, cash_usd, pnl_usd, fee_basis, priced}. `pnl_usd` is the book's cash plus the
    broker's posted correction (None for a close the book could not price)."""
    from .economics import route_of

    out = []
    for p in positions:
        status, closed_at = str(p.get("status") or ""), _num(p.get("closed_at"))
        if status == "open" or closed_at is None or closed_at < since:
            continue
        route = route_of(p)
        house = route in HOUSE_ROUTES
        pid = int(p["pid"])
        cash = _dec(p.get("cash"))
        priced = status == "closed" and cash is not None and int(p.get("qty") or 0) == 0
        fix = corrections.get(pid)
        pnl = (cash + (fix or Decimal(0))) if priced else None
        opened_qty = int(p.get("opened_qty") or 0)
        loss = (_num(p.get("max_loss_share")) or 0.0) * 100.0 * opened_qty
        out.append({"pid": pid, "family": str(p.get("family") or ""), "instance": str(p.get("instance") or ""),
                    "version": version_of(p.get("instance")), "route": route, "code": ROUTE_CODES.get(route),
                    "house": house, "lane": None if house or lanes is None else lanes.of(p.get("family")),
                    "closed_at": closed_at, "day": _ny_day(closed_at), "opened_day": str(p.get("opened_day") or ""),
                    "opened_at": _num(p.get("opened_at")), "root": str(p.get("root") or "").upper(),
                    "type": str(p.get("type") or ""), "legs": _loads(p.get("legs"), []), "entry": _num(p.get("entry")),
                    "opened_qty": opened_qty, "max_loss_usd": round(loss, 2), "cash_usd": cash, "pnl_usd": pnl,
                    "fee_basis": "broker" if fix is not None else "estimate", "priced": priced, "status": status})
    out.sort(key=lambda c: (c["closed_at"], c["pid"]))
    return out


# ------------------------------------------------------------------------------------------------- buy-and-hold
def _close_on(series: Mapping[str, float], day: str | None) -> float | None:
    """The symbol's close on `day` exactly, None without one. Until Oct 10, 2026 a missing day took the last close
    before it, silently (the readiness audit's m11): an exit the direction job had not fetched yet was then priced to an
    older close. The caller says why (`buy_and_hold`)."""
    if not series or not day or day not in series:
        return None
    return _num(series[day])


def entry_delta(close: Mapping[str, Any], spot: float) -> float | None:
    """The structure's delta per share at entry: Black-Scholes at one implied volatility, solved by bisection so the legs'
    signed values sum to its entry value, the entry day's close as the spot. None when no volatility in [1%, 300%] gives
    the entry value (or a leg is unreadable)."""
    from ..options_history import bs_delta, bs_price, years_to

    entry, at = _num(close.get("entry")), _num(close.get("opened_at"))
    legs = []
    for leg in close.get("legs") or []:
        if not isinstance(leg, Mapping):
            return None
        strike, side, ratio = _num(leg.get("strike")), _num(leg.get("side")), _num(leg.get("ratio"))
        if strike is None or side is None or ratio is None or not leg.get("expiry"):
            return None
        try:
            years = years_to(str(leg["expiry"]), at or 0.0)
        except (TypeError, ValueError):
            return None
        legs.append((strike, side * ratio, years, "call" if leg.get("is_call") else "put"))
    if not legs or entry is None or at is None or spot <= 0 or any(y <= 0 for _, _, y, _ in legs):
        return None

    def value(vol: float) -> float:
        return sum(w * bs_price(spot, k, y, vol, right) for k, w, y, right in legs)

    # A single option's value rises with the volatility; a vertical's need not (it falls again past its peak), so the
    # lowest volatility that prices the entry is taken: the first sign change on a log grid from 1% to 300%, then bisected.
    grid = [0.01 * (300.0 ** (i / 60.0)) for i in range(61)]
    found = None
    f_prev = value(grid[0]) - entry
    for a, b in zip(grid, grid[1:]):
        f_next = value(b) - entry
        if f_prev == 0 or f_prev * f_next < 0:
            found = (a, b, f_prev)
            break
        f_prev = f_next
    if found is None:
        return None
    lo, hi, f_lo = found
    if f_lo == 0:
        hi = lo
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        f_mid = value(mid) - entry
        if (f_mid < 0) == (f_lo < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break
    vol = 0.5 * (lo + hi)
    return sum(w * bs_delta(spot, k, y, vol, right) for k, w, y, right in legs)


def buy_and_hold(close: Mapping[str, Any], closes_doc: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    """The same-risk buy-and-hold of one close, two ways (the module docstring): {delta_usd, risk_usd, why}."""
    from .direction import PROXY

    root = str(close.get("root") or "").upper()
    symbol = PROXY.get(root, root)
    series = closes_doc.get(symbol) or {}
    start, end = _close_on(series, close.get("opened_day")), _close_on(series, close.get("day"))
    out: dict[str, Any] = {"delta_usd": None, "risk_usd": None, "why": None}
    if start is None or end is None or start <= 0:
        # AN EXACT CLOSE OR A WHY (Oct 10, 2026; the readiness audit's m11): never a stand-in close from another day.
        missing = [d for d, v in ((close.get("opened_day"), start), (close.get("day"), end)) if v is None]
        last = max(series) if series else None
        out["why"] = (f"no daily close of {symbol or 'its root'} on {', '.join(str(d) for d in missing) or 'its days'} "
                      f"in the direction job's file (its last close: {last or 'none'}); the next run fills it")
        return out
    out["risk_usd"] = round(float(close.get("max_loss_usd") or 0.0) * (end / start - 1.0), 2)
    if root in PROXY:
        out["why"] = f"{root} has no stock bars: not delta-matched"
        return out
    delta = entry_delta(close, start)
    if delta is None:
        out["why"] = "no implied volatility gives its entry value: not delta-matched"
        return out
    out["delta_usd"] = round(delta * 100.0 * int(close.get("opened_qty") or 0) * (end - start), 2)
    return out


def _bh_sum(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    d = [r["bh"]["delta_usd"] for r in rows if (r.get("bh") or {}).get("delta_usd") is not None]
    k = [r["bh"]["risk_usd"] for r in rows if (r.get("bh") or {}).get("risk_usd") is not None]
    return {"delta_matched_usd": round(sum(d), 2) if d else None, "delta_priced": len(d),
            "dollars_at_risk_usd": round(sum(k), 2) if k else None, "risk_priced": len(k), "closes": len(rows),
            "basis": "approximation: daily closes of the direction job; delta from Black-Scholes at one implied "
                     "volatility solved from the entry value, the entry day's close as the spot"}


# ------------------------------------------------------------------------------------------------- the Done meter
def nightly_rows(store: Any, fid: str) -> list[dict[str, Any]]:
    """The family's nightly replay rows of the forward record (`source` "nightly"), [] on a store error."""
    try:
        return [r for r in store.forward(fid) if str(r.get("source") or "") == "nightly"]
    except Exception:  # noqa: BLE001 - no replay rows: no matched closes
        return []


def twin_records(store: Any) -> dict[str, dict[str, Any]]:
    """The per-close twins (`league/ops/twins.py`: the swarm store's kv `close_twins`, {str(pid): record}); {} when
    there are none or they cannot be read (every close then falls back to the nightly replay)."""
    from .twins import records

    return records(store)


def replay_gap(program_closes: Sequence[Mapping[str, Any]], nightly: Sequence[Mapping[str, Any]], *,
               limit: float, min_matched: int, twins: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """D5's measure, live minus replay, pooled over the program's versions: on every (version, day) on which the program's
    counted closes (by their entry day, as the forward record dates a real trade) and its version's nightly replay both
    traded, sum(live P&L) / sum(live maximum loss) - sum(replay P&L) / sum(replay maximum loss), over the BOOK's cash (as
    D5 reads it). {matched, gap, consistent}: consistent is None under `min_matched` matched closes (listed, never
    dropped), else |gap| <= `limit`.

    THE PER-CLOSE TWIN (Oct 10, 2026; `league/ops/twins.py`, the module docstring): `twins` ({str(pid): record}) puts a
    close with a PRICED twin into the same sums against its own twin (the twin's P&L and maximum loss, one trade), and
    keeps a close whose twin is final but unpriced out of every sum (counted in `twin_unpriced` by verdict, never matched
    to the nightly replay instead); a close with no record, or a "failed" one still to be asked again, is matched to the
    nightly replay as before. When any of the program's closes has a record the answer also carries `twinned`,
    `nightly_matched` and `twin_unpriced`; when none has, it is D5's three keys exactly."""
    from .twins import FINAL

    twins = twins or {}
    replay: dict[tuple[int, str], list[Mapping[str, Any]]] = {}
    for r in nightly:
        v = r.get("version")
        if v is None:
            continue
        replay.setdefault((int(v), str(r.get("day") or "")), []).append(r)
    live_pnl = live_loss = replay_pnl = replay_loss = 0.0
    matched = twinned = 0
    unpriced: dict[str, int] = {}
    seen_twins = False
    cells: set[tuple[int, str]] = set()
    for c in program_closes:
        rec = twins.get(str(c.get("pid")))
        seen_twins = seen_twins or rec is not None
        cash = _num(c.get("cash_usd"))
        loss = _num(c.get("max_loss_usd"))
        status = (rec or {}).get("status")
        if status == "priced":
            twin = rec.get("twin") or {}
            p, m = _num(twin.get("pnl")), _num(twin.get("max_loss"))
            if cash is None or loss is None or loss <= 0 or p is None or m is None or m <= 0:
                unpriced["unreadable"] = unpriced.get("unreadable", 0) + 1
                continue
            matched += 1
            twinned += 1
            live_pnl += cash
            live_loss += loss
            replay_pnl += p
            replay_loss += m
            continue
        if status in FINAL:
            unpriced[str(status)] = unpriced.get(str(status), 0) + 1
            continue
        key = (c.get("version"), str(c.get("opened_day") or ""))
        if key[0] is None or key not in replay:
            continue
        if cash is None or loss is None or loss <= 0:
            continue
        matched += 1
        live_pnl += cash
        live_loss += loss
        cells.add(key)  # type: ignore[arg-type]
    for key in cells:
        for r in replay[key]:
            p, m = _num(r.get("pnl")), _num(r.get("max_loss"))
            if p is not None and m is not None and m > 0:
                replay_pnl += p
                replay_loss += m
    gap = (live_pnl / live_loss - replay_pnl / replay_loss) if matched and live_loss > 0 and replay_loss > 0 else None
    consistent = None if matched < min_matched or gap is None else abs(gap) <= limit
    out = {"matched": matched, "gap": None if gap is None else round(gap, 4), "consistent": consistent}
    if seen_twins:
        out.update(twinned=twinned, nightly_matched=matched - twinned, twin_unpriced=dict(sorted(unpriced.items())))
    return out


def replay_twins(counted: Sequence[Mapping[str, Any]], twins: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """THE PER-CLOSE TWIN beside the meter (`league/ops/twins.py`): every counted agent close with its twin's verdict
    ({pid, family, route, status, live_r, twin_r, gap_r, live_exit, twin_exit, exit_agrees, why}) and the counts by verdict
    ("none": no record yet, or the twins are off)."""
    rows, by_status = [], {}
    for c in counted:
        rec = twins.get(str(c.get("pid"))) or {}
        status = str(rec.get("status") or "none")
        by_status[status] = by_status.get(status, 0) + 1
        cash, loss = _num(c.get("cash_usd")), _num(c.get("max_loss_usd"))
        live_r = round(cash / loss, 5) if cash is not None and loss and loss > 0 else None
        twin = rec.get("twin") or {}
        twin_r = _num(twin.get("r"))
        rows.append({"pid": c.get("pid"), "family": c.get("family"), "route": c.get("code") or c.get("route"),
                     "status": status, "live_r": live_r, "twin_r": twin_r,
                     "gap_r": round(live_r - twin_r, 5) if live_r is not None and twin_r is not None else None,
                     "live_exit": (rec.get("live") or {}).get("exit"), "twin_exit": twin.get("exit"),
                     "exit_agrees": rec.get("exit_agrees"), "why": rec.get("why")})
    return {"closes": len(rows), "priced": by_status.get("priced", 0), "by_status": dict(sorted(by_status.items())),
            "rows": rows,
            "basis": "each real close's own orders replayed on the gate image by the Gym's engine and fill model "
                     "(league/ops/twins.py); live minus twin per dollar of each one's maximum loss, the book's cash"}


def reading(counted: Sequence[Mapping[str, Any]], store: Any, *, nightly_cache: dict[str, list] | None = None,
            done: Mapping[str, Any] | None = None, lanes: Lanes | None = None,
            twins: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """The Done rule over exactly `counted` (the meter's closes, in close order): {closes, programs, net_usd, net_known,
    estimate_closes, unpriced, per_program_ok, consistent_ok, holds, why, by_route, by_program, bh}."""
    from ..swarm import dlane

    rule = dict(done or dlane.DONE)
    cache = nightly_cache if nightly_cache is not None else {}
    by_program: dict[str, list[Mapping[str, Any]]] = {}
    for c in counted:
        by_program.setdefault(c["family"], []).append(c)
    unpriced = sum(1 for c in counted if c.get("pnl_usd") is None)
    net = sum((c["pnl_usd"] for c in counted if c.get("pnl_usd") is not None), Decimal(0))
    programs = []
    for fid, rows in sorted(by_program.items()):
        if fid not in cache:
            cache[fid] = nightly_rows(store, fid)
        gap = replay_gap(rows, cache[fid], limit=float(rule["gap_limit"]), min_matched=int(rule["gap_min_matched"]),
                         twins=twins)
        routes: dict[str, int] = {}
        for c in rows:
            routes[c.get("code") or c["route"]] = routes.get(c.get("code") or c["route"], 0) + 1
        known = [c["pnl_usd"] for c in rows if c.get("pnl_usd") is not None]
        lane = lanes.of(fid) if lanes is not None else rows[0].get("lane")
        row = {"family": fid, "lane": lane, "closes": len(rows), "routes": routes,
               "net_usd": _usd(sum(known, Decimal(0))) if len(known) == len(rows) else None,
               "replay": gap, "bh": _bh_sum(rows)}
        if lane == dlane.DIRECTION:
            row["label"] = dlane.LABEL
        programs.append(row)
    enough = [p for p in programs if p["closes"] >= int(rule["min_closes_per_program"])]
    per_program_ok = len(enough) >= int(rule["min_programs"])
    # CONSISTENCY MUST BE MEASURED (DONE-RULE-A1 A1.1, pinned Oct 9, 2026; the readiness audit's B1): item 4 alone held
    # with ZERO replay evidence, since a program under 5 matched closes is never inconsistent. Now a reading also needs
    # `min_measured_programs` (2) programs with `gap_min_matched` (5) or more matched closes and a gap measured, and every
    # such program within the gap. Zero matched closes never passes; every program is listed with its closes, matched
    # closes and gap (`by_program`).
    min_matched = int(rule["gap_min_matched"])
    need_measured = int(rule.get("min_measured_programs", dlane.DONE["min_measured_programs"]))
    measured = [p for p in programs if p["replay"]["matched"] >= min_matched and p["replay"]["gap"] is not None]
    inconsistent = [p["family"] for p in measured if p["replay"]["consistent"] is False]
    measured_ok = len(measured) >= need_measured
    matched_total = sum(int(p["replay"]["matched"]) for p in programs)
    net_known = unpriced == 0
    whys = []
    if len(counted) < int(rule["min_closes"]):
        whys.append(f"{len(counted)} closes of the {int(rule['min_closes'])} needed")
    if not per_program_ok:
        whys.append(f"{len(enough)} programs with {int(rule['min_closes_per_program'])}+ closes of the "
                    f"{int(rule['min_programs'])} needed")
    if not net_known:
        whys.append(f"{unpriced} closes the book could not price: the net is unknown")
    elif net <= 0:
        whys.append("the net after fees is not above $0")
    if not measured_ok:
        whys.append(f"replay untested: {matched_total} of {len(counted)} closes matched a replay (a twin or the "
                    f"nightly); {len(measured)} programs with {min_matched}+ matched closes of the {need_measured} needed "
                    "(DONE-RULE-A1 A1.1)")
    if inconsistent:
        whys.append(f"live fills inconsistent with replay: {', '.join(inconsistent[:8])}")
    item3 = len(counted) >= int(rule["min_closes"]) and per_program_ok and net_known and net > 0
    item4 = measured_ok and not inconsistent
    by_route: dict[str, dict[str, Any]] = {}
    for c in counted:
        key = c.get("code") or c["route"]
        slot = by_route.setdefault(key, {"closes": 0, "programs": set(), "net": Decimal(0), "unpriced": 0})
        slot["closes"] += 1
        slot["programs"].add(c["family"])
        if c.get("pnl_usd") is None:
            slot["unpriced"] += 1
        else:
            slot["net"] += c["pnl_usd"]
    return {"closes": len(counted), "programs": len(programs), "programs_with_min_closes": len(enough),
            "net_usd": _usd(net) if net_known else None, "net_known": net_known, "unpriced": unpriced,
            "estimate_closes": sum(1 for c in counted if c.get("priced") and c.get("fee_basis") == "estimate"),
            "per_program_ok": per_program_ok, "consistent_ok": item4, "measured_programs": len(measured),
            "replay_coverage": {"matched": matched_total, "closes": len(counted),
                                "share": round(matched_total / len(counted), 4) if counted else None},
            "items": {"3": item3, "4": item4},
            "holds": not whys, "why": "; ".join(whys) or None,
            "by_route": {k: {"closes": v["closes"], "programs": len(v["programs"]),
                             "net_usd": None if v["unpriced"] else _usd(v["net"]), "unpriced": v["unpriced"]}
                         for k, v in sorted(by_route.items())},
            "by_program": programs, "bh": _bh_sum(counted)}


#: THE GAP'S MEASURE, said beside every reading (the readiness audit's done-meter note: the rule says "mean ... gap", D5
#: reads a ratio of sums).
GAP_MEASURE = ("ratio of sums, D5's measure: over the (version, entry day) cells where a counted close and its "
               "version's nightly replay both traded, sum(live P&L) / sum(live maximum loss) - sum(replay P&L) / "
               "sum(replay maximum loss), the live side at the book's cash")
#: The first checkpoint's research window (DONE-RULE item 7): its last this many UTC days; a later checkpoint's is every
#: UTC day since the one before it.
RESEARCH_FIRST_DAYS = 7


def finality(counted: Sequence[Mapping[str, Any]], *, replay_days: Mapping[str, Mapping[str, Any]] | None,
             fees_as_of: str | None, twins: Mapping[str, Mapping[str, Any]] | None = None,
             twins_on: bool = False) -> dict[str, Any]:
    """FINAL READINGS (DONE-RULE-A1 A1.4, pinned Oct 9, 2026; the readiness audit's M8). A checkpoint's inputs are final
    when, for every counted close:
    - THE REPLAY LANDED: its program's nightly replay has replayed the close's exit day (the family's own
      `forward_replay` target day, `replay_days`), or the program is no longer replayed (not alive in a Candidate, Probe
      or Sized band: its replay rows are frozen, so they can no longer change). Nightly rows are re-run and replaced
      each night (league/swarm/gate.py `record_forward`), so a reading taken before the exit day is replayed compares a
      live close with a replay that may still move.
    - THE BROKER'S FEES POSTED: its fee basis is the broker's (`fees_by_pid`) and the saved activity reading is from a
      New York day after the close's exit day (option fees post the next session; a position whose opening fees posted
      may still have its closing ones to come, so the basis alone is not enough).
    - it is priced (an unpriced close is never final).

    THE PER-CLOSE TWIN (the integration of the weekend fixes, Oct 10, 2026: the ops builder's A1.4 and the replay
    builder's B1 (c) each left this join to the other). A close is matched to its own twin once the twin is judged
    (`replay_gap`), so for a close with a FINAL twin record (`twins.FINAL`: priced, no_fill, no_contract, unpriceable;
    final once judged) THE REPLAY LANDED is that record, whatever the nightly has replayed. With the twins switched on
    (`twins_on`, `forward.twins`), a close with no final twin yet (none, or "failed" and to be asked again) is
    `pending_twin`: its reading would otherwise be frozen on the nightly fallback the twin is about to replace. With the
    switch off, such a close reads the nightly's landing exactly as before.
    {final, pending_replay, pending_twin, pending_fees, unpriced, why}. Pure."""
    from .twins import FINAL as TWIN_FINAL

    replay_days = replay_days or {}
    twins = twins or {}
    pending_replay = pending_twin = pending_fees = unpriced = 0
    for c in counted:
        exit_day = str(c.get("day") or "")
        if c.get("pnl_usd") is None:
            unpriced += 1
        if (twins.get(str(c.get("pid"))) or {}).get("status") in TWIN_FINAL:
            pass
        elif twins_on:
            pending_twin += 1
        else:
            state = replay_days.get(str(c.get("family") or "")) or {}
            if state.get("replayed") and not (state.get("day") and str(state["day"]) >= exit_day):
                pending_replay += 1
        if c.get("fee_basis") != "broker" or not fees_as_of or fees_as_of <= exit_day:
            pending_fees += 1
    whys = []
    if pending_replay:
        whys.append(f"the nightly replay has not yet replayed the exit day of {pending_replay} closes")
    if pending_twin:
        whys.append(f"the per-close twin of {pending_twin} closes has not landed (none yet, or failed and to be asked "
                    "again)")
    if pending_fees:
        whys.append(f"the broker's fees have not posted for {pending_fees} closes (the activity reading is of "
                    f"{fees_as_of or 'no day'})")
    if unpriced:
        whys.append(f"{unpriced} closes are not priced")
    return {"final": not whys, "pending_replay": pending_replay, "pending_twin": pending_twin,
            "pending_fees": pending_fees, "unpriced": unpriced, "why": "; ".join(whys) or None}


def research_window(counted: Sequence[Mapping[str, Any]], k: int, previous_k: int | None) -> tuple[str, str]:
    """The UTC days (first, last) DONE-RULE item 7 is read over at the checkpoint of close `k` (the readiness audit's M7):
    the last `RESEARCH_FIRST_DAYS` days ending on the day of the K-th close for the first checkpoint; for a later one,
    every day after the previous checkpoint's day through its own (at least its own day)."""
    last = time.strftime("%Y-%m-%d", time.gmtime(float(counted[k - 1]["closed_at"])))
    end = datetime.fromisoformat(last).date()
    if previous_k is None:
        first = (end - timedelta(days=RESEARCH_FIRST_DAYS - 1)).isoformat()
    else:
        before = datetime.fromisoformat(time.strftime("%Y-%m-%d", time.gmtime(float(counted[previous_k - 1]["closed_at"])))
                                        ).date()
        first = min(end, before + timedelta(days=1)).isoformat()
    return first, last


def meter(all_closes: Sequence[Mapping[str, Any]], routes: Sequence[str], store: Any, *,
          nightly_cache: dict[str, list] | None = None, lanes: Lanes | None = None,
          previous: Mapping[str, Any] | None = None, research: Any = None,
          replay_days: Mapping[str, Mapping[str, Any]] | None = None, fees_as_of: str | None = None,
          now: float | None = None, twins: Mapping[str, Mapping[str, Any]] | None = None,
          twins_on: bool = False) -> dict[str, Any]:
    """One Done meter (`done_screen` or `done_all`): the agent closes on `routes`, the running figures (never a reading),
    and a reading at every checkpoint reached (the first K closes, K = 30, 40, ...: `dlane.DONE`).

    Each checkpoint (Oct 10, 2026; DONE-RULE-A1 and the readiness audit's B1, M7 and M8) lists every counted program with
    its closes, matched replay closes and gap (`by_program`), reads DONE-RULE item 7 over its research window
    (`research_247`, from `research(first_day, last_day)`; with none handed in, item 7 is unread and the checkpoint does
    not hold), and says whether its inputs are FINAL (`finality`; `final_why` otherwise). It HOLDS when items 3, 4 (A1.1)
    and 7 all hold; a Done claim is made only on a holding FINAL checkpoint (the meter's `holds`; alarm A8). A final
    reading is FROZEN: when the `previous` report's meter has the checkpoint final, it is carried forward as it was,
    whatever the inputs say now (nightly rows are replaced each night; the reading may not flip after A8)."""
    from ..swarm import dlane

    rule = dlane.DONE
    counted = [c for c in all_closes if not c["house"] and c.get("code") in routes]
    cache = nightly_cache if nightly_cache is not None else {}
    running = reading(counted, store, nightly_cache=cache, lanes=lanes, twins=twins)
    frozen = {int(cp["at_close"]): cp for cp in ((previous or {}).get("checkpoints") or [])
              if isinstance(cp, Mapping) and cp.get("final") is True and isinstance(cp.get("at_close"), int)}
    checkpoints = []
    k = int(rule["first_checkpoint"])
    prev_k = None
    while k <= len(counted):
        if k in frozen:
            checkpoints.append({**frozen[k], "frozen": True})
            prev_k, k = k, k + int(rule["checkpoint_every"])
            continue
        at = reading(counted[:k], store, nightly_cache=cache, lanes=lanes, twins=twins)
        first_day, last_day = research_window(counted, k, prev_k)
        r247 = {"holds": False, "first_day": first_day, "last_day": last_day, "why": "research 24/7 was not read"}
        if callable(research):
            try:
                r247 = research(first_day, last_day)
            except Exception as exc:  # noqa: BLE001 - unread is not held: the checkpoint does not hold, the report goes on
                r247 = {**r247, "why": f"research 24/7 could not be read ({type(exc).__name__}: {str(exc)[:120]})"}
        fin = finality(counted[:k], replay_days=replay_days, fees_as_of=fees_as_of, twins=twins,
                       twins_on=twins_on)
        day_ended = now is None or now >= _epoch(f"{last_day}T00:00:00Z") + 86400.0
        if not day_ended:
            fin = {**fin, "final": False, "why": "; ".join(w for w in (fin["why"], f"the research window's last day "
                                                                                  f"({last_day}) has not ended") if w)}
        item7 = r247.get("holds") is True
        whys = [w for w in (at["why"], None if item7 else f"research 24/7 (item 7): {r247.get('why') or 'not held'}") if w]
        programs = [{"family": p["family"], "lane": p["lane"], "closes": p["closes"], "matched": p["replay"]["matched"],
                     "gap": p["replay"]["gap"], "consistent": p["replay"]["consistent"], "net_usd": p["net_usd"],
                     **({"label": p["label"]} if p.get("label") else {})} for p in at["by_program"]]
        checkpoints.append({"at_close": k, "closed_at": _iso(counted[k - 1]["closed_at"]),
                            "holds": at["holds"] and item7, "why": "; ".join(whys) or None,
                            "items": {**at["items"], "7": item7}, "final": fin["final"], "final_why": fin["why"],
                            "closes": at["closes"], "programs": at["programs"],
                            "programs_with_min_closes": at["programs_with_min_closes"], "net_usd": at["net_usd"],
                            "consistent_ok": at["consistent_ok"], "measured_programs": at["measured_programs"],
                            "replay_coverage": at["replay_coverage"], "by_program": programs,
                            "research_247": r247, "by_route": at["by_route"], "bh": at["bh"]})
        prev_k, k = k, k + int(rule["checkpoint_every"])
    nxt = int(rule["first_checkpoint"]) if not checkpoints else checkpoints[-1]["at_close"] + int(rule["checkpoint_every"])
    latest = checkpoints[-1] if checkpoints else None
    return {"routes": list(routes), "running": {**running, "holds": None, "reading": False,
                                                "note": "counts between checkpoints are never a Done reading"},
            "checkpoints": checkpoints, "latest": latest,
            # A Done claim: the latest checkpoint holds AND is final (A1.4); a holding provisional one says so apart.
            "holds": bool(latest and latest["holds"] and latest.get("final")),
            "provisional": bool(latest and latest["holds"] and not latest.get("final")),
            "next_checkpoint": nxt, "gap_measure": GAP_MEASURE,
            "closes": [{"pid": c["pid"], "family": c["family"], "route": c.get("code") or c["route"], "lane": c.get("lane"),
                        "closed_at": _iso(c["closed_at"]), "pnl_usd": _usd(c["pnl_usd"]), "fee_basis": c["fee_basis"],
                        "bh": c.get("bh")} for c in counted]}


# ------------------------------------------------------------------------------------------------- research 24/7
#: The stall causes that are news to the owner, not a step he must take for research to go on (league/ops/stall.py): a
#: Done checkpoint that holds is told at once, and is no owner step WAITING for DONE-RULE item 7.
NEWS_CAUSES = ("done",)
OPS_DB = "ops.sqlite"
#: The operator's edits listed beside item 7 at most (the newest; `edits_count` counts them all).
EDITS_LISTED = 40


def operator_edits(root: Path, first_day: str, last_day: str) -> list[dict[str, Any]]:
    """The operator's edits of `swarm.json` and `budget.json` in the UTC days [first_day, last_day], as their before-copies
    record them (`<file>.before-<what>-<YYYYMMDDTHHMMSSZ>`, the operator's tools' naming): [{file, what, at}], oldest first.
    A hand edit with no before-copy is not seen."""
    import re

    pattern = re.compile(r"^(swarm|budget)\.json\.before-(.*?)-?(\d{8}T\d{6}Z)$")
    out = []
    try:
        names = [p.name for p in Path(root).iterdir() if p.name.startswith(("swarm.json.before", "budget.json.before"))]
    except OSError:
        return []
    for name in names:
        m = pattern.match(name)
        if not m:
            continue
        stamp = m.group(3)
        day = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
        if first_day <= day <= last_day:
            out.append({"file": f"{m.group(1)}.json", "what": m.group(2) or None,
                        "at": f"{day}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"})
    return sorted(out, key=lambda e: e["at"])


class Research247:
    """DONE-RULE ITEM 7, READ (Oct 10, 2026; the readiness audit's M7): "research runs 24/7 at budget with no captain",
    as the pinned rule reads it: births, Gym runs and Validations every UTC day, at the research budget, with no owner step
    waiting. For each UTC day of a window, from the House's own records (read-only):
    - `births`: `swarm.born` events and the learning game's children (families of origin "game", which emit none);
    - `gym_runs`: `runs` rows the Gym evaluated (a trial, neither refused nor an error);
    - `validations`: Validation rows with a verdict (`runs` window "validation", not refused nor an error: the Gym's or
      one read from an identical program) and the verdicts the tournament's rounds judged;
    - `at_budget`: every `budget` receipt of the day (ops.sqlite) has every meter's day figure `limited_by` "ceiling" (no
      taper; None with no receipt that day);
    - `owner`: the causes with an owner step that any `stall` receipt of the day found standing (but the news causes,
      `NEWS_CAUSES`);
    - `stall_receipts`: how many `stall` receipts (status ok) the day has. Since the review of the weekend fixes (Oct 10,
      2026) a day with none is not held ("no stall receipt"), as a day with no budget receipt is not: the stall job
      failing all day (an unreadable swarm store) or missed is a day nobody looked for an owner step, never a day with
      none waiting.
    A day holds when births, Gym runs and Validations are each above 0, `at_budget` is True, the day has a stall receipt
    and `owner` is empty; the window holds when every day does. The operator's edits of swarm.json and budget.json in the
    window are LISTED (`edits`, from their before-copies) beside it: the pinned rule reads "no captain" as no owner step
    waiting, so they are reported, never a bar. Days are cached across checkpoints."""

    def __init__(self, store: Any, root: Path):
        self.store, self.root = store, Path(root)
        self.days: dict[str, dict[str, Any]] = {}
        self._ops: dict[str, list[dict[str, Any]]] | None = None

    def _receipts(self) -> dict[str, list[dict[str, Any]]]:
        """The `budget` and `stall` receipts of ops.sqlite (read-only), {job: rows}; {} with no store."""
        if self._ops is None:
            from . import guard

            path = self.root / OPS_DB
            self._ops = {"budget": [], "stall": []}
            if path.exists():
                try:
                    rows = guard.read(path, lambda db: guard.rows(
                        db, "SELECT job, due_at, finished_at, summary_json FROM runs WHERE job IN ('budget', 'stall') "
                            "AND status='ok' ORDER BY due_at"))
                except Exception:  # noqa: BLE001 - unreadable receipts: the days read unknown, never held
                    rows = []
                for row in rows:
                    self._ops.setdefault(str(row["job"]), []).append(row)
        return self._ops

    def day(self, day: str) -> dict[str, Any]:
        if day in self.days:
            return self.days[day]
        start, end = f"{day}T00:00:00Z", (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat() + "T00:00:00Z"
        one = lambda sql, params: int((self.store._all(sql, params) or [{"n": 0}])[0]["n"] or 0)  # noqa: E731
        marks = ",".join("?" * len(NOT_RUN))
        births = one("SELECT count(*) AS n FROM events WHERE kind='swarm.born' AND at>=? AND at<?", (start, end))
        births += one("SELECT count(*) AS n FROM families WHERE origin='game' AND born_at>=? AND born_at<?", (start, end))
        gym = one(f"SELECT count(*) AS n FROM runs WHERE at>=? AND at<? AND status NOT IN ({marks}) AND trials > 0",
                  (start, end, *NOT_RUN))
        validation_rows = one(f"SELECT count(*) AS n FROM runs WHERE \"window\"='validation' AND at>=? AND at<? AND "
                              f"status NOT IN ({marks})", (start, end, *NOT_RUN))
        judged = 0
        for row in self.store._all("SELECT payload FROM events WHERE kind='swarm.tournament' AND at>=? AND at<?",
                                   (start, end)):
            verdicts = ((_loads(row.get("payload"), {}) or {}).get("validation") or {}).get("judged")
            judged += len(verdicts) if isinstance(verdicts, (Mapping, list)) else 0
        receipts = self._receipts()
        budgets = [r for r in receipts.get("budget", []) if str(r.get("due_at") or "")[:10] == day]
        at_budget = None
        limits: set[str] = set()
        for r in budgets:
            meters = (_loads(r.get("summary_json"), {}) or {}).get("meters") or {}
            for row in meters.values() if isinstance(meters, Mapping) else ():
                limits.add(str((row or {}).get("limited_by")))
        if budgets:
            at_budget = limits == {"ceiling"}
        owner: set[str] = set()
        stalls = 0
        for r in receipts.get("stall", []):
            if str(r.get("due_at") or "")[:10] != day:
                continue
            stalls += 1
            checks = (_loads(r.get("summary_json"), {}) or {}).get("checks") or {}
            for cause, check in checks.items() if isinstance(checks, Mapping) else ():
                if (isinstance(check, Mapping) and check.get("stalled") and check.get("owner_step")
                        and cause not in NEWS_CAUSES):
                    owner.add(str(cause))
        whys = []
        for name, n in (("births", births), ("Gym runs", gym), ("Validations", validation_rows + judged)):
            if n <= 0:
                whys.append(f"no {name}")
        if at_budget is None:
            whys.append("no budget receipt")
        elif not at_budget:
            whys.append(f"research under the ceiling ({', '.join(sorted(limits - {'ceiling'}))})")
        if stalls == 0:
            whys.append("no stall receipt")
        if owner:
            whys.append(f"an owner step waiting ({', '.join(sorted(owner))})")
        out = {"day": day, "births": births, "gym_runs": gym, "validations": validation_rows + judged,
               "validation_rows": validation_rows, "judged": judged, "at_budget": at_budget,
               "limited_by": sorted(limits), "owner": sorted(owner), "stall_receipts": stalls,
               "holds": not whys, "why": "; ".join(whys) or None}
        self.days[day] = out
        return out

    def __call__(self, first_day: str, last_day: str) -> dict[str, Any]:
        days, d = [], datetime.fromisoformat(first_day).date()
        end = datetime.fromisoformat(last_day).date()
        while d <= end:
            try:
                days.append(self.day(d.isoformat()))
            except Exception as exc:  # noqa: BLE001 - a day that cannot be read is not held, never skipped
                days.append({"day": d.isoformat(), "holds": False,
                             "why": f"its records could not be read ({type(exc).__name__}: {str(exc)[:120]})"})
            d += timedelta(days=1)
        failing = [x for x in days if not x["holds"]]
        # The House kept 120 before-copies of swarm.json by Oct 9 (a busy captain): the newest `EDITS_LISTED` are listed.
        edits = operator_edits(self.root, first_day, last_day)
        return {"first_day": first_day, "last_day": last_day, "holds": bool(days) and not failing,
                "why": None if days and not failing else
                ("; ".join(f"{x['day']}: {x['why']}" for x in failing[:6]) + (f"; and {len(failing) - 6} more days"
                                                                              if len(failing) > 6 else "")
                 if failing else "no day in the window"),
                "days": days, "edits": edits[-EDITS_LISTED:], "edits_count": len(edits),
                "note": "DONE-RULE item 7 as pinned: births, Gym runs and Validations every UTC day, at the research "
                        "budget (no taper), with no owner step waiting; the operator's edits of swarm.json and "
                        "budget.json are listed beside it, never a bar"}


# ------------------------------------------------------------------------------------------------- the funnel
def funnel(store: Any, lanes: Lanes, all_closes: Sequence[Mapping[str, Any]], *, now: float, hours: float,
           positions: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Each lane's counts over the last `hours` (the module docstring), from the swarm store opened read-only. Since Oct
    10, 2026 (the readiness audit's m11) the agents' real OPENS by route too (`real_opens`, from the live book's
    `positions`): the first real Probe trade was in no dlane funnel count until it closed."""
    from ..swarm import dlane

    since = _iso(now - hours * 3600.0)
    out: dict[str, Any] = {lane: {"births": 0, "gym_runs": {w: 0 for w in RUN_WINDOWS}, "program_years": 0.0,
                                  "validations": {"judged": 0, "passed": 0}, "reviews": 0, "audits": 0,
                                  "looks": {"taken": 0, "passed": 0, "by_screen": {}},
                                  "band_moves": {"candidate": 0, "probe": 0, "sized": 0},
                                  "real_closes": {":r": 0, ":t": 0, ":i": 0, "other": 0},
                                  "real_opens": {":r": 0, ":t": 0, ":i": 0, "other": 0}}
                           for lane in dlane.LANES}
    for row in store._all("SELECT family, payload FROM events WHERE kind='swarm.born' AND at>=?", (since,)):
        payload = _loads(row.get("payload"), {}) or {}
        lane = payload.get("lane") if isinstance(payload, Mapping) else None
        lane = lane if lane in dlane.LANES else lanes.of(row.get("family"))
        out[lane]["births"] += 1
    for row in store._all('SELECT family, "window" AS w, status, trials, program_years FROM runs WHERE at>=?', (since,)):
        if row["status"] in NOT_RUN or not int(row.get("trials") or 0):
            continue
        lane = lanes.of(row["family"])
        if row["w"] in out[lane]["gym_runs"]:
            out[lane]["gym_runs"][row["w"]] += 1
        out[lane]["program_years"] += float(row.get("program_years") or 0.0)
    # M5 (Oct 10, 2026): the direction lane also counts the verdicts that went to the gate (`entered`: the line, or D2's
    # Validation pre-check; the tournament's verdict row says so from that release on). The alpha lane's counts are as
    # before: `passed` is the line's answer in both lanes.
    out[dlane.DIRECTION]["validations"]["entered"] = 0
    for row in store._all("SELECT payload FROM events WHERE kind='swarm.tournament' AND at>=?", (since,)):
        judged = ((_loads(row.get("payload"), {}) or {}).get("validation") or {}).get("judged")
        for fid, verdict in (judged or {}).items() if isinstance(judged, Mapping) else ():
            lane = lanes.of(fid)
            out[lane]["validations"]["judged"] += 1
            out[lane]["validations"]["passed"] += 1 if isinstance(verdict, Mapping) and verdict.get("passed") is True else 0
            if lane == dlane.DIRECTION and isinstance(verdict, Mapping) \
                    and (verdict.get("passed") is True or verdict.get("entered") is True):
                out[lane]["validations"]["entered"] += 1
    for row in store._all("SELECT family, payload FROM events WHERE kind='swarm.gate' AND at>=?", (since,)):
        action = (_loads(row.get("payload"), {}) or {}).get("action")
        if action in ("review", "audit") and row.get("family"):
            out[lanes.of(row["family"])]["reviews" if action == "review" else "audits"] += 1
    for row in store._all("SELECT family, passed, detail FROM looks WHERE at>=?", (since,)):
        lane = lanes.of(row["family"])
        detail = _loads(row.get("detail"), {}) or {}
        screen = str(detail.get("screen") or (dlane.ALPHA_SCREEN if lane == dlane.ALPHA else "unrecorded"))
        looks = out[lane]["looks"]
        looks["taken"] += 1
        looks["passed"] += 1 if row.get("passed") else 0
        looks["by_screen"][screen] = looks["by_screen"].get(screen, 0) + 1
    for row in store._all("SELECT family, payload FROM events WHERE kind='swarm.band' AND at>=?", (since,)):
        to = (_loads(row.get("payload"), {}) or {}).get("band_to")
        if to in out[dlane.ALPHA]["band_moves"]:
            out[lanes.of(row.get("family"))]["band_moves"][to] += 1
    edge = now - hours * 3600.0
    for c in all_closes:
        if c["house"] or c["closed_at"] < edge:
            continue
        out[c.get("lane") or dlane.ALPHA]["real_closes"][c.get("code") or "other"] += 1
    from .economics import route_of

    for p in positions:
        opened = _num(p.get("opened_at"))
        route = route_of(p)
        if opened is None or opened < edge or route in HOUSE_ROUTES:
            continue
        out[lanes.of(p.get("family"))]["real_opens"][ROUTE_CODES.get(route) or "other"] += 1
    for lane in out.values():
        lane["program_years"] = round(lane["program_years"], 2)
    out[dlane.DIRECTION]["train_bar"] = dlane.failure_counts(store, hours, now=now)
    return out


def bands_now(store: Any, lanes: Lanes) -> dict[str, dict[str, int]]:
    from ..swarm import dlane

    out = {lane: {"gym": 0, "candidate": 0, "probe": 0, "sized": 0, "alive": 0} for lane in dlane.LANES}
    for fam in store.families(alive=True):
        lane = lanes.of(fam["id"], fam)
        out[lane][str(fam.get("band") or "gym")] = out[lane].get(str(fam.get("band") or "gym"), 0) + 1
        out[lane]["alive"] += 1
    return out


# ------------------------------------------------------------------------------------------------- Probes and screens
def probes(store: Any, lanes: Lanes, settings: Mapping[str, Any] | None, positions: Sequence[Mapping[str, Any]] = (),
           losses: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every living Candidate, Probe or Sized family with the screen that admitted it (its banded version's newest
    passing look: the screen the look recorded, else its lane's) and that screen's false-positive rates, the
    world-conditional one (both windows rose) beside the unconditional one (decision 8). Beside each (DONE-RULE-A1 A1.3,
    Oct 10, 2026): its own realized Probe net and closes, its share of the Probe total used, the program loss line
    (`program_losses`), and the trade count at which DM1 can first fire (`dm1_reach`)."""
    from ..swarm import dlane

    by_family = {r["family"]: r for r in (losses or {}).get("programs") or []}

    c = dlane.cfg(settings)
    looks: dict[tuple[str, int], Mapping[str, Any]] = {}
    for look in store.looks():
        if look.get("passed"):
            looks[(str(look["family"]), int(look["version"]))] = look
    out = []
    for fam in store.families(alive=True):
        if fam.get("band") not in ("candidate", "probe", "sized"):
            continue
        lane = lanes.of(fam["id"], fam)
        n = (fam.get("state") or {}).get("banded_version")
        look = looks.get((fam["id"], int(n))) if isinstance(n, int) else None
        detail = (look or {}).get("detail") or {}
        screen = detail.get("screen") or (dlane.ALPHA_SCREEN if lane == dlane.ALPHA else c["screen"])
        figures = c["screens"].get(screen) or {}
        row = {"family": fam["id"], "band": fam["band"], "lane": lane, "version": n, "look_at": (look or {}).get("at"),
               "screen": screen, "receipt": detail.get("receipt"), "screen_recorded": bool(detail.get("screen")),
               "fp_unconditional": figures.get("fp_unconditional"),
               "fp_both_windows_rose": figures.get("fp_both_windows_rose")}
        if look is not None:  # release D-1b: the lane rates of the screen that admitted it (`dlane.fp_of_look`)
            row.update({k: v for k, v in dlane.fp_of_look(detail, settings).items() if k.startswith("fp_")})
        if screen == dlane.ALPHA_SCREEN:
            row["fp_why"] = "the alpha screen's (S-B) rates are FAST_LANE_SCREEN_1's receipt (docs/benchmarks), not the lane's"
            row.update(ALPHA_FP)
        if lane == dlane.DIRECTION:
            row["label"] = dlane.LABEL
        own = by_family.get(fam["id"]) or {}
        row.update(probe_net_usd=own.get("probe_net_usd", 0.0), probe_closes=own.get("probe_closes", 0),
                   probe_unpriced=own.get("unpriced", 0), share_of_probe_total=own.get("share_of_total", 0.0),
                   program_loss_line_usd=(losses or {}).get("line_usd"), dm1=dm1_reach(store, fam, positions))
        out.append(row)
    return out


def program_losses(positions: Sequence[Mapping[str, Any]], corrections: Mapping[int, Decimal], store: Any,
                   settings: Mapping[str, Any] | None, *, since: float) -> dict[str, Any]:
    """ONE PROGRAM CANNOT DRAIN THE SHARED BUDGET (DONE-RULE-A1 A1.3, pinned Oct 9, 2026; the readiness audit's M11). Each
    agent program's own realized PROBE net: its closed Probe-marked positions on the Probe/Sized route (`:r`, not
    tuition, `info.probe` true, as the money table's Probe tally marks them) since `since`, the book's cash plus the
    broker's posted fee correction, beside its open Probe positions' maximum loss. A program is DUE when it is alive, every
    Probe close of it is priced (an unpriced one may still be a gain: it waits for the House's reconciliation) and that
    net is at or below the program loss line (`dlane.program_loss_usd`, -$300 since Oct 10, 2026). The `dlane` job
    retires a due program swarm-side (`run`): a tightening, never a trade; its real positions exit by the House's rules.
    Every lane: the pinned rule names one program, whatever its lane, and the line holds with the direction lane off too
    (`lane_off`). {line_usd, total_usd, programs: [...], due}."""
    from ..live import money as M
    from ..swarm import dlane
    from .economics import route_of

    line = dlane.cfg(settings)["program_loss_usd"]
    total = float(M.Table.from_constitution().probe_loss_total)
    rows: dict[str, dict[str, Any]] = {}
    for p in positions:
        if route_of(p) != "d2_real" or int(p.get("tuition") or 0):
            continue
        if (_loads(p.get("info"), {}) or {}).get("probe") is not True:
            continue
        opened = _num(p.get("opened_at"))
        if opened is None or opened < since:
            continue
        fid = str(p.get("family") or "")
        row = rows.setdefault(fid, {"family": fid, "probe_closes": 0, "unpriced": 0, "net": Decimal(0), "open": 0,
                                    "open_max_loss_usd": 0.0})
        status = str(p.get("status") or "")
        if status == "open":
            row["open"] += 1
            row["open_max_loss_usd"] += (_num(p.get("max_loss_share")) or 0.0) * 100.0 * int(p.get("qty") or 0)
            continue
        cash = _dec(p.get("cash"))
        if status == "closed" and cash is not None and int(p.get("qty") or 0) == 0:
            row["probe_closes"] += 1
            row["net"] += cash + corrections.get(int(p["pid"]), Decimal(0))
        else:
            row["unpriced"] += 1  # an unpriced close or one awaiting its expiry's reconciliation
    out = []
    for fid, row in sorted(rows.items()):
        try:
            fam = store.family(fid)
        except Exception:  # noqa: BLE001 - an unreadable family is retired by no one
            fam = None
        alive = bool(fam is not None and not fam.get("retired_at"))
        net = float(row["net"])
        out.append({"family": fid, "alive": alive, "band": (fam or {}).get("band"), "probe_closes": row["probe_closes"],
                    "unpriced": row["unpriced"], "probe_net_usd": round(net, 2), "open": row["open"],
                    "open_max_loss_usd": round(row["open_max_loss_usd"], 2),
                    "share_of_total": round(max(0.0, -net) / total, 4) if total > 0 else None,
                    "due": alive and row["unpriced"] == 0 and row["probe_closes"] > 0 and net <= line})
    return {"line_usd": line, "total_usd": total, "programs": out, "due": [r["family"] for r in out if r["due"]],
            "rule": "DONE-RULE-A1 A1.3: a program whose own realized Probe net is at or below the line is retired "
                    "swarm-side by this job; exits go on"}


#: A long single's (or a debit vertical's) return on maximum loss is bounded below near -1: the whole premium plus the
#: fees. Without a position to read it from, -1 itself (DM1's first n is then the earliest it could be).
R_FLOOR_DEFAULT = 1.0


def dm1_reach(store: Any, fam: Mapping[str, Any], positions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """WHEN DM1 CAN FIRST FIRE for a banded program (DONE-RULE-A1 A1.3; the readiness audit's M11), beside its Probe row.
    DM1 (league/live/money.py `demotion`, read here, never changed) demotes when the version's `DM1_MIN_REAL_TRADES`+
    real trades' returns on maximum loss sum below -`DM1_Z` x sigma x sqrt(n). A trade's return is bounded below by
    -r_floor (the premium plus the fees, over the maximum loss: about 1.0012 for a $0.43 call), so the sum of n trades
    is at least -n x r_floor, and DM1 can fire only once n x r_floor > z x sigma x sqrt(n): n > (z x sigma / r_floor)^2.
    Sigma is DM1's own (`money.dm1_sigma`: the banded version's Validation sd of r, else the forward record's, else 2.0).
    r_floor is the largest (premium x 100 x lots + fees) / maximum loss over the program's Probe/Sized positions.
    {version, sigma, sigma_source, r_floor, real_trades, real_r_sum, line_now, first_fire_at, trades_to_first_fire}."""
    from ..live import money as M
    from ..live.families import validation_r_sd

    n = (fam.get("state") or {}).get("banded_version")
    out: dict[str, Any] = {"version": n}
    if not isinstance(n, int):
        return {**out, "why": "no banded version"}
    try:
        fwd = M.forward_stats(store.forward(fam["id"]), M.Table.from_constitution().sized_confidence, version=n)
    except Exception as exc:  # noqa: BLE001 - an unreadable record: no figure, never an invented one
        return {**out, "why": f"the forward record could not be read ({type(exc).__name__})"}
    sigma, source = M.dm1_sigma(fwd, validation_r_sd(fam.get("state") or {}, n))
    floors = []
    for p in positions:
        if str(p.get("family") or "") != fam["id"] or not str(p.get("instance") or "").endswith(":r"):
            continue
        lots, share, entry = int(p.get("opened_qty") or 0), _num(p.get("max_loss_share")), _num(p.get("entry"))
        loss = (share or 0.0) * 100.0 * lots
        if lots > 0 and loss > 0 and entry is not None:
            floors.append((entry * 100.0 * lots + (_num(p.get("fees")) or 0.0)) / loss)
    r_floor = max([R_FLOOR_DEFAULT, *floors])
    first = max(M.DM1_MIN_REAL_TRADES, math.floor((M.DM1_Z * sigma / r_floor) ** 2) + 1)
    return {**out, "sigma": round(sigma, 6), "sigma_source": source, "r_floor": round(r_floor, 6),
            "real_trades": fwd.real_n, "real_r_sum": round(fwd.real_r_sum, 4),
            "line_now": round(-M.DM1_Z * sigma * math.sqrt(fwd.real_n), 4) if fwd.real_n else None,
            "first_fire_at": first, "trades_to_first_fire": max(0, first - fwd.real_n),
            "note": f"DM1 cannot fire before n = {first} real trades of this version (league/live/money.py, read only)"}


#: The alpha screen's (S-B) false-positive figure, stated beside an alpha program's Probe trade (release D-1b): it has no
#: lane rate; its pre-registered benchmark's acceptance bound held (FAST_LANE_SCREEN_1, Oct 7, 2026).
ALPHA_FP = {"fp_upper_bound": 0.02,
            "fp_source": "FAST_LANE_SCREEN_1 (docs/benchmarks/fast_lane_screen_1.json): the per-program rate's one-sided 95% "
                         "upper bound at most 2% in every null world"}


def trade_screens(store: Any, lanes: Lanes, settings: Mapping[str, Any] | None, positions: Sequence[Mapping[str, Any]],
                  all_closes: Sequence[Mapping[str, Any]], *, since: float) -> dict[str, Any]:
    """THE FALSE-POSITIVE RATE BESIDE EVERY PROBE TRADE AND EVERY REAL CLOSE (release D-1b; the owner's goal of Oct 9,
    item 4: "a pre-registered screen whose false-positive rate you have measured ... stated beside every Probe trade").
    `probe_trades`: every real position on the Probe/Sized route `:r` opened since `since`, open or closed; `closes`:
    every agent real close (every route, the Done rule's set), each with its program's screen (the passed holdout look of
    the version the position trades: its recorded line) and that screen's rates at zero edge, {screen, fp_lane_mixed,
    fp_lane_2224, receipt} (`dlane.fp_of_look`), the alpha screen's bound beside an S-B row (`ALPHA_FP`), the lane's
    label beside a direction row. Only a Probe/Sized trade (`d2_real`) opened at or after its version's passed look carries
    that look's screen (the review's finding 5): a tuition or incubator close, a close with no passed look on record, and
    a position opened before the look say so (`fp_why`), never an invented screen. The contamination statement rides
    beside them."""
    from ..swarm import dlane
    from .economics import route_of

    passed: dict[tuple[str, int], Mapping[str, Any]] = {}
    for look in store.looks():
        if look.get("passed"):
            passed[(str(look["family"]), int(look["version"]))] = look

    def screen_of(family: str, version: int | None, route: str, opened_at: float | None) -> dict[str, Any]:
        # A SCREEN ADMITS A PROBE TRADE ONLY (release D-1b, the review's finding 5, Oct 9, 2026): a passed look's screen is
        # stated beside a close or a position only when it is on the Probe/Sized route (`d2_real`, `:r`) and opened at
        # or after that look. A tuition or incubator close of a version that LATER passed its look was admitted by no
        # screen (tuition runs while a validated version waits in the gate), so it keeps the no-screen row.
        look = passed.get((family, int(version))) if isinstance(version, int) else None
        lane = lanes.of(family)
        look_at = _epoch(look.get("at")) if look is not None else None
        why = None
        if route != "d2_real":
            why = (f"the {route} route: no screen admits it (tuition and the incubator trade beside the gate, never by "
                   "its look)")
        elif look is None:
            why = "no passed holdout look of this version is on record"
        elif opened_at is None or look_at is None or look_at > opened_at:
            why = "its version's passed holdout look is not on record before this position opened"
        if why is not None or look is None:
            out = {"screen": None, "fp_lane_mixed": None, "fp_lane_2224": None, "receipt": None, "look_at": None,
                   "fp_why": why}
        else:
            detail = look.get("detail") or {}
            out = {**dlane.fp_of_look(detail, settings), "look_at": look.get("at"),
                   "screen_recorded": bool(detail.get("screen"))}
            if out["screen"] == dlane.ALPHA_SCREEN:
                out.update(ALPHA_FP)
        out["lane"] = lane
        if lane == dlane.DIRECTION:
            out["label"] = dlane.LABEL
        return out

    probe_trades = []
    for p in positions:
        opened = _num(p.get("opened_at"))
        if route_of(p) != "d2_real" or opened is None or opened < since:
            continue
        family, version = str(p.get("family") or ""), version_of(p.get("instance"))
        probe_trades.append({"pid": int(p["pid"]), "family": family, "instance": str(p.get("instance") or ""),
                             "version": version, "status": str(p.get("status") or ""), "opened_at": _iso(opened),
                             "closed_at": _iso(_num(p.get("closed_at"))), "root": str(p.get("root") or "").upper(),
                             "type": str(p.get("type") or ""), **screen_of(family, version, "d2_real", opened)})
    closes_rows = [{"pid": c["pid"], "family": c["family"], "route": c.get("code") or c["route"], "version": c["version"],
                    "closed_at": _iso(c["closed_at"]), "pnl_usd": _usd(c["pnl_usd"]), "fee_basis": c["fee_basis"],
                    **screen_of(c["family"], c["version"], str(c["route"]), _num(c.get("opened_at")))}
                   for c in all_closes if not c["house"]]
    return {"probe_trades": probe_trades, "closes": closes_rows, "contamination": CONTAMINATION,
            "note": "each row's rates are its screen's per program at zero edge, measured on historical worlds (a property "
                    "of the procedure, not a guarantee in this world); reported, never a bar"}


# ------------------------------------------------------------------------------------------------- the envelope
def probe_envelope(live_path: Path, positions: Sequence[Mapping[str, Any]], *, today: str, unit_usd: float | None
                   ) -> dict[str, Any]:
    """THE PROBE LOSS BUDGET as the money table in force reads it (release L-D, live since 09:04Z Oct 9, 2026; THE ROLLING
    PROBE BUDGET): the constitution's `options_money.probe` row through `money.Table` (`constitution`: `loss_basis`,
    `loss_budget_usd` over the last `loss_window_sessions` New York sessions, `loss_total_usd` from inception, `max_open`,
    `demotion`), never a figure of its own, and the realized figures `real.probe_figures` gives `money.plan_open` (through
    `RealBook.exposure`), each read in one read-only transaction of the live book with the basis named:
    - `in_force`: the fast lane report's own figure (`fast_lane.probe_budget`: the basis in force, the window's and the
      total's figures, `room_usd` and the envelope that binds);
    - `by_basis`: under each basis ("gross" and "net"; `basis_in_force` is the table's, the other rides beside it), the
      window's figure (`window_usd`: `real.probe_realized` from `window_start`, under "net" the window's WORST NET
      STRETCH), the total's (`total_usd`: `real.probe_tally`, from inception), both rooms (`fast_lane.probe_rooms`: each
      envelope's budget less its figure less every real position's open maximum loss), the room left (the tighter
      envelope's, floored at $0), which envelope binds, and that room in units of today's cap;
    - `window_<basis>_usd`, `realized_<basis>_usd` (the total, from inception, as before release L-D's window),
      `room_<basis>_usd` and `room_<basis>_units` repeat each basis's figures (alarm A4 reads the basis in force).
    `probe_closes` counts the closed Probe-marked `:r` positions. A book that is absent leaves every figure None; one
    that cannot be read (the House box has numpy; a test or a laptop may not) is an `error` entry."""
    from dataclasses import replace

    from ..live import money as M

    table = M.Table.from_constitution()
    marked = sum(1 for p in positions
                 if p.get("status") == "closed" and str(p.get("instance") or "").endswith(":r")
                 and not int(p.get("tuition") or 0) and (_loads(p.get("info"), {}) or {}).get("probe") is True)
    out: dict[str, Any] = {
        "constitution": {"loss_basis": table.probe_loss_basis, "loss_budget_usd": _usd(table.probe_loss_budget),
                         "loss_window_sessions": table.probe_loss_window, "loss_total_usd": _usd(table.probe_loss_total),
                         "max_open": table.probe_max_open, "demotion": table.probe_demotion},
        "basis_in_force": table.probe_loss_basis, "budget_usd": _usd(table.probe_loss_budget),
        "window_sessions": table.probe_loss_window, "total_budget_usd": _usd(table.probe_loss_total),
        "max_open": table.probe_max_open, "probe_closes": marked, "unit_usd": unit_usd, "in_force": None,
        "window_start": None, "at_risk_usd": None, "open": None, "binding": None, "by_basis": None}
    for basis in M.LOSS_BASES:
        for key in ("window", "realized", "room"):
            out[f"{key}_{basis}_usd"] = None
        out[f"room_{basis}_units"] = None
    path = Path(live_path)
    if not path.exists():
        return out
    try:
        from . import fast_lane

        out["in_force"] = fast_lane.probe_budget(path, today)
    except Exception as exc:  # noqa: BLE001 - the House box has numpy; a test or a laptop may not
        out["in_force"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    try:
        from ..live.real import probe_figures
        from . import guard

        def read(db: Any) -> dict[str, tuple]:
            def rows(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
                return guard.rows(db, sql, params)

            # The table in force with each basis in turn: the code path `RealBook.exposure` takes, the basis named.
            return {basis: probe_figures(rows, day=today, table=replace(table, probe_loss_basis=basis))
                    for basis in M.LOSS_BASES}

        figures = guard.read(path, read)
    except Exception as exc:  # noqa: BLE001 - as above: no figure, never an invented one
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return out
    from .fast_lane import probe_rooms

    by_basis: dict[str, Any] = {}
    for basis, (open_n, window, total, at_risk, since) in figures.items():
        rooms, binding = probe_rooms(table, window, total, at_risk)
        room = max(M.ZERO, rooms[binding])
        units = round(float(room) / unit_usd, 2) if unit_usd else None
        by_basis[basis] = {"window_usd": _usd(window), "total_usd": _usd(total), "room_window_usd": _usd(rooms["window"]),
                           "room_total_usd": _usd(rooms["total"]), "room_usd": _usd(room), "binding": binding,
                           "room_units": units}
        out[f"window_{basis}_usd"], out[f"realized_{basis}_usd"] = _usd(window), _usd(total)
        out[f"room_{basis}_usd"], out[f"room_{basis}_units"] = _usd(room), units
    open_n, _, _, at_risk, since = figures[table.probe_loss_basis]
    out.update(by_basis=by_basis, window_start=since, at_risk_usd=_usd(at_risk), open=open_n,
               binding=by_basis[table.probe_loss_basis]["binding"])
    return out


# ------------------------------------------------------------------------------------------------- the account
def _health(root: Path) -> dict[str, Any]:
    try:
        doc = json.loads((root / HEALTH_FILE).read_text(encoding="utf-8"))
        stops = ((doc.get("options_live") or {}).get("stops") or {}) if isinstance(doc, Mapping) else {}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}
    last = stops.get("last_reading") if isinstance(stops, Mapping) else None
    out: dict[str, Any] = {"sod_equity_usd": _num(stops.get("sod_equity")) if isinstance(stops, Mapping) else None}
    if isinstance(last, (list, tuple)) and len(last) >= 2:
        out["equity_usd"], out["equity_at"] = _num(last[1]), _iso(_num(last[0]))
    return out


E0_BASIS = ("the first equity reading this report saw, kept from report to report; not release L-D's deploy reading "
            "(the plan's E0)")


def account(root: Path, all_closes: Sequence[Mapping[str, Any]], activity: Mapping[str, Any],
            previous: Mapping[str, Any] | None, *, now: float) -> dict[str, Any]:
    """The account beside the trading figures (the module docstring)."""
    health = _health(root)
    equity, at = health.get("equity_usd"), health.get("equity_at")
    e0 = ((previous or {}).get("account") or {}).get("e0") if isinstance(previous, Mapping) else None
    if not (isinstance(e0, Mapping) and _num(e0.get("usd")) is not None and e0.get("at")):
        e0 = {"usd": equity, "at": at or _iso(now)}
    # THE BASIS SAID AS IT IS (Oct 10, 2026; the readiness audit's m11): E0 is the first equity reading this report saw,
    # kept from report to report. The old words read as if it were release L-D's deploy reading, the plan's E0; it is
    # not (the House's E0 here is 2026-10-08T19:54Z, before L-D's deploy at 09:04Z Oct 9). A kept E0 is relabelled.
    e0 = {**dict(e0), "basis": E0_BASIS}
    out: dict[str, Any] = {"e0": e0, "equity_usd": equity, "equity_at": at, "sod_equity_usd": health.get("sod_equity_usd"),
                           "change_usd": None, "agents_usd": None, "house_usd": None, "other_activity": activity.get("other"),
                           "other_as_of": activity.get("as_of"), "unexplained_usd": None}
    start = _epoch(e0.get("at"))
    if equity is None or _num(e0.get("usd")) is None or start is None:
        out["why"] = "no equity reading in health.json"
        return out
    out["change_usd"] = round(equity - float(e0["usd"]), 2)
    since = [c for c in all_closes if c["closed_at"] >= start]
    agents = [c["pnl_usd"] for c in since if not c["house"]]
    house = [c["pnl_usd"] for c in since if c["house"]]
    if all(x is not None for x in agents):
        out["agents_usd"] = _usd(sum(agents, Decimal(0)))
    if all(x is not None for x in house):
        out["house_usd"] = _usd(sum(house, Decimal(0)))
    if out["agents_usd"] is not None and out["house_usd"] is not None:
        out["unexplained_usd"] = round(out["change_usd"] - out["agents_usd"] - out["house_usd"], 2)
    out["note"] = ("unexplained = the equity change less the realized closes since E0: open positions' marks, fees no "
                   "position carries, interest and anything else the account holds")
    return out


def costs(store: Any, *, since: float, lane_since: float | None) -> dict[str, Any]:
    """The swarm's research spend by meter (`funnel.METER_KINDS`) since `since` and since the lane started."""
    from .funnel import METER_KINDS

    def spent(start: float | None) -> dict[str, float] | None:
        if start is None:
            return None
        meters = {m: 0.0 for m in METER_KINDS}
        for row in store._all("SELECT kind, coalesce(sum(usd), 0) AS usd FROM spend WHERE epoch>=? GROUP BY kind", (start,)):
            for m, kinds in METER_KINDS.items():
                if row["kind"] in kinds:
                    meters[m] += float(row["usd"] or 0.0)
        return {**{m: round(v, 2) for m, v in meters.items()}, "total": round(sum(meters.values()), 2)}

    return {"since_inception": spent(since), "since_lane_start": spent(lane_since),
            "basis": "comparison only: the swarm's BOOKED research spend (`spend` rows); the Net beside the meter is "
                     "`net_after_costs`, on the close economics' billed and metered basis (every input cost, the gateway's "
                     "Claude meter included)",
            "note": "LTCM's profit is trading net minus every cost: see net_after_costs"}


#: A close economics summary older than this is said stale beside Net after costs (the job runs after every close).
ECONOMICS_STALE_SECONDS = 4 * 86400.0


def net_after_costs(root: Path, all_closes: Sequence[Mapping[str, Any]], *, now: float) -> dict[str, Any]:
    """NET AFTER COSTS BESIDE THE METER (DONE-RULE item 2: "Reported as the account shows it, with Net after costs
    (research, Sail, gateway spend over the same days) beside it"; the readiness audit's M9, Oct 10, 2026). From the
    newest close economics summary (`economics.latest`: every input cost since T0 2026-09-26T06:23:14Z on its stated,
    conservative basis: Sail billed or metered, the larger; Claude through the gateway's meter; OpenAI; the market data;
    TypeSafe's gateway meter; any the owner declared), over the same days as the meters (the Done rule's inception is
    06:23Z the same morning): each meter's realized net of the closes up to the economics cutoff, the costs, and their
    difference; the economics Net (every route, the House's included) beside it. The swarm's booked spend (`costs`) is
    comparison only."""
    from ..swarm import dlane
    from . import economics

    out: dict[str, Any] = {
        "label": "Net after costs: a meter's realized net (after fees) to the economics cutoff less every input cost "
                 "since T0 (research, Sail, Claude through the gateway, OpenAI, market data, TypeSafe) on the close "
                 "economics' basis",
        "cutoff": None, "cost_start": None, "costs_usd": None, "costs_by_service": [], "economics_net_usd": None,
        "economics_realized_usd": None, "stale": None, "done_all": None, "done_screen": None, "why": None}
    try:
        summary = economics.latest(root)
    except Exception as exc:  # noqa: BLE001 - no figure, never an invented one
        summary, out["why"] = None, f"the close economics could not be read ({type(exc).__name__})"
    if not isinstance(summary, Mapping) or _epoch(summary.get("cutoff")) is None:
        out["why"] = out["why"] or "no close economics summary yet (the economics job runs ten minutes after each close)"
        return out
    cut = float(_epoch(summary["cutoff"]))
    costs = _dec(summary.get("total_costs_usd"))
    out.update(cutoff=summary.get("cutoff"), cost_start=summary.get("cost_start"), costs_usd=_usd(costs),
               costs_by_service=[{"service": c.get("service"), "usd": c.get("usd")} for c in summary.get("costs") or []
                                 if isinstance(c, Mapping)],
               economics_net_usd=(summary.get("net") or {}).get("net_usd"),
               economics_realized_usd=(summary.get("realized") or {}).get("realized_options_pnl_usd"),
               stale=now - cut > ECONOMICS_STALE_SECONDS)
    for name, key in (("done_all", "routes_all"), ("done_screen", "routes_screen")):
        rows = [c for c in all_closes if not c["house"] and c.get("code") in dlane.DONE[key] and c["closed_at"] <= cut]
        known = all(c.get("pnl_usd") is not None for c in rows)
        net = sum((c["pnl_usd"] for c in rows if c.get("pnl_usd") is not None), Decimal(0))
        out[name] = {"closes_to_cutoff": len(rows), "net_usd_to_cutoff": _usd(net) if known else None,
                     "net_after_costs_usd": _usd(net - costs) if known and costs is not None else None}
    if costs is None:
        out["why"] = "the economics summary carries no total cost"
    return out


# ------------------------------------------------------------------------------------------------- contamination
def contamination_meters(root: Path, lanes: Lanes) -> dict[str, Any]:
    """M-D (a)-(c) per lane, from the fast lane report (`fast-lane-report.json`, written daily at 01:00Z after the
    `direction` job): its looks' head-minus-tail Sharpe gaps pooled per lane, the excess over the same-risk buy-and-hold
    on Validation (a known window) against live (unknown), and each band's live against its holdout."""
    from ..swarm import dlane
    from .fast_lane import pooled_contamination

    try:
        doc = json.loads((root / FAST_LANE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"why": "no fast lane report yet"}
    screen = doc.get("screen") or []
    bands = doc.get("bands") or []
    out: dict[str, Any] = {"fast_lane_report_at": doc.get("at"), "reported_only": True}
    for lane in dlane.LANES:
        rows = [r for r in screen if lanes.of(r.get("family")) == lane]
        known = [float(r["pnl"]) - float(r["bh"]["usd"]) for r in rows
                 if r.get("window") == "validation" and _num(r.get("pnl")) is not None
                 and _num((r.get("bh") or {}).get("usd")) is not None]
        live = [float(b["live"]["realized_usd"]) - float(b["live"]["bh"]["usd"]) for b in bands
                if lanes.of(b.get("family")) == lane and _num(((b.get("live") or {}).get("bh") or {}).get("usd")) is not None
                and _num((b.get("live") or {}).get("realized_usd")) is not None]
        excess_known = statistics.fmean(known) if known else None
        excess_live = statistics.fmean(live) if live else None
        out[lane] = {
            "a_head_minus_tail": pooled_contamination(rows),
            "b_excess_over_bh": {"known_validation_mean_usd": None if excess_known is None else round(excess_known, 2),
                                 "known_n": len(known),
                                 "unknown_live_mean_usd": None if excess_live is None else round(excess_live, 2),
                                 "unknown_n": len(live),
                                 "known_minus_unknown_usd": (round(excess_known - excess_live, 2)
                                                             if excess_known is not None and excess_live is not None
                                                             else None)},
            "c_live_vs_holdout": [{"family": b.get("family"), "band": b.get("band"), **(b.get("live_vs_holdout") or {})}
                                  for b in bands if lanes.of(b.get("family")) == lane]}
        if lane == dlane.DIRECTION:
            out[lane]["label"] = dlane.LABEL
    return out


# ------------------------------------------------------------------------------------------------- the alarms
def _sessions_back(today: str, n: int) -> str:
    """The NYSE session `n` sessions before `today` (ISO), counting `today` when it is one."""
    from .direction import sessions

    first = (datetime.fromisoformat(today) - timedelta(days=3 * n + 10)).date().isoformat()
    days = sessions(first, today)
    return days[-n] if len(days) >= n else first


def alarms(store: Any, settings: Mapping[str, Any] | None, lanes: Lanes, book: Mapping[str, Any],
           all_closes: Sequence[Mapping[str, Any]], envelope: Mapping[str, Any], done: Mapping[str, Any],
           k5: Mapping[str, Any], unit: Mapping[str, Any], previous: Mapping[str, Any] | None, *, now: float,
           today: str, losses: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """A1-A9, PL1 and K5 (HARNESS section 5 as amended; the module docstring): [{id, level, text, ...}]. Each names counts
    and family ids, never a hidden-year figure."""
    from ..live import money as M
    from ..swarm import dlane

    c = dlane.cfg(settings)
    out: list[dict[str, Any]] = []
    alive = [f for f in store.families(alive=True) if lanes.of(f["id"], f) == dlane.DIRECTION]
    # A1: no direction birth in `lane_only_hours`, the quota open (the lane on and under `max_alive`).
    edge = _iso(now - c["lane_only_hours"] * 3600.0)
    started = store.get(dlane.STARTED_KEY)
    births = [r for r in store._all("SELECT family, at, payload FROM events WHERE kind='swarm.born' ORDER BY at, seq")
              if ((_loads(r.get("payload"), {}) or {}).get("lane") == dlane.DIRECTION
                  or lanes.of(r.get("family")) == dlane.DIRECTION)]
    last = births[-1]["at"] if births else None
    if (dlane.mode_effective(store, settings) != "off" and isinstance(started, str) and started <= edge
            and (last is None or last <= edge) and len(alive) < c["max_alive"]):
        out.append({"id": "A1", "level": "warning", "last_birth": last,
                    "text": f"A1: no direction birth in {c['lane_only_hours']:g} h with the quota open "
                            f"({len(alive)} direction families alive of {c['max_alive']}): the architect's next pass asks "
                            "for direction proposals only (lane_only)"})
    counts48 = dlane.failure_counts(store, 48.0, now=now)
    # A2: a direction version cleared every Train bar 24 h ago or more, and no direction Validation try or look since.
    cleared = []
    for fam in alive:
        versions = (((fam.get("state") or {}).get(dlane.STATE_KEY) or {}).get("versions") or {})
        for n, v in versions.items() if isinstance(versions, Mapping) else ():
            if ((v or {}).get("robust") or {}).get("passed") and ((v or {}).get("train") or {}).get("eligible"):
                cleared.append((fam, int(n), str(v.get("at") or "")))
    day_ago = _iso(now - A2_HOURS * 3600.0)
    if cleared and min(at for _, _, at in cleared) <= day_ago:
        ids = {f["id"] for f, _, _ in cleared}
        tries = sum(1 for r in store._all("SELECT family FROM runs WHERE \"window\"='validation' AND purpose='validation' "
                                          "AND at>=?", (day_ago,)) if r["family"] in {f["id"] for f in alive})
        looks = sum(1 for r in store._all("SELECT family FROM looks WHERE at>=?", (day_ago,))
                    if lanes.of(r["family"]) == dlane.DIRECTION)
        if not tries and not looks:
            out.append({"id": "A2", "level": "warning", "families": sorted(ids)[:12],
                        "text": f"A2: {len(cleared)} direction versions in {len(ids)} families cleared every Train bar "
                                f"24 h ago or more, and no direction Validation try or holdout look since (plumbing; "
                                f"48 h: {counts48['eligible']} eligible, {counts48['robust_passed']} passed at 1.5x)"})
    # A3: a cleared best waits for Validation over 6 h; a direction Validation pass waits for its look over 12 h.
    waits_val, waits_gate = [], []
    looked = {(str(r["family"]), int(r["version"])) for r in store.looks()}
    for fam, n, at in cleared:
        if fam.get("best_version") != n or fam.get("band") != "gym" or at > _iso(now - A3_VALIDATION_HOURS * 3600.0):
            continue
        if not [r for r in store.version_runs(fam["id"], n, window="validation", stress=1.0, limit=5)]:
            waits_val.append(fam["id"])
    # M5 (Oct 10, 2026): a version that ENTERED the gate waits for its look as a line pass does. Under D2 a direction
    # version enters by the Validation pre-check with its line failed, so this leg read `passed` alone and could never
    # fire for the lane: the verdict's `entered` (from that release), and the lineage's try (`dlane.TRY_KEY` `entered`:
    # every D2 entry before it, eqp-realcalm-drift-call's v17 among them), count too. A version the gate refused (a
    # `refusals` row: the review, the audit, the rations) waits for nothing and is never counted.
    refused = {(str(r["family"]), int(r["version"])) for r in store.refusals() if r.get("version") is not None}
    for fam in alive:
        state = fam.get("state") or {}
        verdicts = state.get("validation_verdicts") or {}
        entries = [(n, v.get("at")) for n, v in (verdicts.items() if isinstance(verdicts, Mapping) else ())
                   if isinstance(v, Mapping) and (v.get("passed") is True or v.get("entered") is True)]
        held = state.get(dlane.TRY_KEY)
        if isinstance(held, Mapping) and held.get("entered") is True and held.get("version") is not None:
            entries.append((held["version"], held.get("at")))
        for n, at in entries:
            if (fam.get("band") == "gym" and str(at or "9") <= _iso(now - A3_GATE_HOURS * 3600.0)
                    and str(n).isdigit() and (fam["id"], int(n)) not in looked and (fam["id"], int(n)) not in refused):
                waits_gate.append(fam["id"])
    if waits_val or waits_gate:
        out.append({"id": "A3", "level": "warning", "validation": sorted(set(waits_val))[:12],
                    "gate": sorted(set(waits_gate))[:12],
                    "text": f"A3: {len(set(waits_val))} direction bests wait for Validation over "
                            f"{A3_VALIDATION_HOURS:g} h and {len(set(waits_gate))} direction versions that entered the "
                            f"gate (the line or D2's pre-check) wait for their holdout look over {A3_GATE_HOURS:g} h "
                            "(a stall)"})
    # A4: room under one unit while a direction Candidate or Probe has fewer than 5 real closes.
    real_n: dict[str, int] = {}
    for cl in all_closes:
        if cl.get("code") == ":r":
            real_n[cl["family"]] = real_n.get(cl["family"], 0) + 1
    young = sorted(f["id"] for f in alive if f.get("band") in ("candidate", "probe") and real_n.get(f["id"], 0) < 5)
    # The room is the tighter of release L-D's two envelopes under the basis in force (`probe_envelope`: the
    # constitution's `loss_budget_usd` over `loss_window_sessions` sessions and `loss_total_usd` in total, `loss_basis`).
    basis = str(envelope.get("basis_in_force") or "gross")
    units = envelope.get(f"room_{basis}_units")
    if young and units is not None and units < 1:
        binding = ((envelope.get("by_basis") or {}).get(basis) or {}).get("binding")
        which = {"window": (f"the window's: ${_num(envelope.get('budget_usd')) or 0:,.2f} in any "
                            f"{envelope.get('window_sessions')} sessions binds"),
                 "total": f"the total's: ${_num(envelope.get('total_budget_usd')) or 0:,.2f} in total binds"}.get(binding)
        out.append({"id": "A4", "level": "warning", "families": young[:12], "basis": basis, "binding": binding,
                    "text": f"A4: the Probe loss budget has under one unit of room ({basis} basis"
                            + (f"; {which}" if which else "") + f") while {len(young)} direction Candidates or "
                            "Probes have fewer than 5 real closes: no path to Sized (a Probe gain, or under the "
                            "window a loss leaving its sessions, frees room)"})
    # A5: a direction Probe or Sized program's live fills below its replay by more than 0.10 over 5+ matched closes.
    table = M.Table.from_constitution()
    gaps = []
    for fam in alive:
        n = (fam.get("state") or {}).get("banded_version")
        if fam.get("band") not in ("probe", "sized") or n is None:
            continue
        try:
            fwd = M.forward_stats(store.forward(fam["id"]), table.sized_confidence, version=n)
        except Exception:  # noqa: BLE001 - an unreadable record: no figure, no alarm
            continue
        if fwd.replay_n >= M.REPLAY_GAP_MIN_TRADES and fwd.replay_gap is not None and fwd.replay_gap > dlane.DONE["gap_limit"]:
            gaps.append(fam["id"])
    if gaps:
        # The demotion in force is the constitution's `probe.demotion` (release L-D): D5's replay-gap leg demotes a
        # Candidate or a Probe under "dm0" and "dm1" alike, never a Sized family.
        out.append({"id": "A5", "level": "warning", "families": gaps[:12], "demotion": table.probe_demotion,
                    "text": f"A5: {len(gaps)} direction Probe or Sized programs' live fills run more than "
                            f"{dlane.DONE['gap_limit']:g} a dollar of maximum loss below their replay over "
                            f"{M.REPLAY_GAP_MIN_TRADES}+ matched closes (D5's replay-gap leg demotes a Probe at "
                            f"{M.REPLAY_GAP_BOUND:g} under probe.demotion \"{table.probe_demotion}\")"})
    # A6: under 1 eligible direction version per 50 direction births over 48 h (judged from 50 births).
    born48 = sum(1 for r in births if str(r.get("at") or "") >= _iso(now - A6_HOURS * 3600.0))
    if born48 >= A6_BIRTHS and counts48["eligible"] * A6_BIRTHS < born48:
        out.append({"id": "A6", "level": "warning", "fails": counts48["fails"], "robust": counts48["robust"],
                    "text": f"A6: {counts48['eligible']} eligible direction versions from {born48} direction births in "
                            f"48 h, under 1 per {A6_BIRTHS} (the lane's objective looks unreachable; failure counts E1 "
                            f"{counts48['fails']['E1']}, E3 {counts48['fails']['E3']}, E4 {counts48['fails']['E4']}, E5 "
                            f"{counts48['fails']['E5']}). Never a loosening without a new pinned measurement"})
    # A7: more than half of the versions that clear E1, E3 and E4 fail E5 (the unit).
    unit_only, eligible = counts48["unit_only"], counts48["eligible"]
    if unit_only and unit_only * 2 > unit_only + eligible:
        failing = []
        for fam in alive:
            for v in ((((fam.get("state") or {}).get(dlane.STATE_KEY) or {}).get("versions") or {}).values()):
                train = (v or {}).get("train") or {}
                if train.get("fails") == ["E5"] and _num((train.get("unit") or {}).get("scaled_usd")) is not None:
                    failing.append(float(train["unit"]["scaled_usd"]))
        median = statistics.median(failing) if failing else None
        out.append({"id": "A7", "level": "warning", "cap_usd": unit.get("cap_usd"), "median_failing_usd": median,
                    "text": f"A7: {unit_only} of {unit_only + eligible} direction versions that clear E1, E3 and E4 fail "
                            f"the unit (E5): today's cap is "
                            f"{'unknown' if unit.get('cap_usd') is None else '$' + format(unit['cap_usd'], '.2f')}"
                            + (f", the median failing one lot ${median:.2f}" if median is not None else "")})
    # A8: a FINAL checkpoint holds that no earlier report saw final and holding (info; it stops nothing). Since Oct 10,
    # 2026 (DONE-RULE-A1 A1.4, the readiness audit's M7 and M8): only a final reading (the night's replay landed, the
    # broker's fees posted, the research window ended) can raise it, and a checkpoint holds only when items 3, 4 (A1.1)
    # and 7 all hold; the text names them. A provisional holding reading raises nothing: it may still flip.
    seen = set()
    for meter_name in ("all", "screen"):
        for cp in (((previous or {}).get("done") or {}).get(meter_name) or {}).get("checkpoints") or []:
            if cp.get("holds") and cp.get("final") is True:
                seen.add((meter_name, cp.get("at_close")))
    for meter_name in ("all", "screen"):
        for cp in done[meter_name]["checkpoints"]:
            if cp["holds"] and cp.get("final") is True and (meter_name, cp["at_close"]) not in seen:
                items = cp.get("items") or {}
                held = ", ".join(f"item {k}" for k in ("3", "4", "7") if items.get(k)) or "none named"
                out.append({"id": "A8", "level": "info", "meter": f"done_{meter_name}", "at_close": cp["at_close"],
                            "items": dict(items),
                            "text": f"A8: Done criteria hold for done_{meter_name} at the FINAL checkpoint of close "
                                    f"{cp['at_close']} ({held} of DONE-RULE + A1: the bar, consistency measured on "
                                    f"{cp.get('measured_programs')} programs, research 24/7; read beside the same-risk "
                                    "buy-and-hold, P(Done | zero edge) and Net after costs; it stops nothing)"})
    # A9: every live direction program opened nothing for 10 sessions.
    since_day = _sessions_back(today, A9_SESSIONS)
    live_programs = {i["family"] for i in book.get("instances") or []
                     if not i.get("retired_at") and str(i.get("id") or "").endswith((":r", ":t", ":i"))
                     and lanes.of(i["family"]) == dlane.DIRECTION and (_ny_day(_num(i.get("created_at"))) or "9") <= since_day}
    if live_programs:
        recent = {p["family"] for p in book.get("positions") or [] if str(p.get("opened_day") or "") >= since_day}
        if not live_programs & recent:
            out.append({"id": "A9", "level": "info", "families": sorted(live_programs)[:12],
                        "text": f"A9: every live direction program ({len(live_programs)}) has opened nothing for "
                                f"{A9_SESSIONS} sessions: the lane is flat by design"})
    out += pl1_alarms(losses)
    # K5.
    if k5.get("tripped"):
        out.append({"id": "K5", "level": "warning", "new": bool(k5.get("new")),
                    "text": "K5 tripped: the direction lane's realized net over every route is at or below its line; "
                            "the lane reads shadow (no new direction Candidate, no incubator direction mark) until the "
                            "operator clears it (swarm.json dlane.k5_clear, or the kv dlane_k5)"})
    elif k5.get("cleared"):
        # THE CLEAR'S LOOSENING (the review of Oct 9): while `dlane.k5_clear` is true K5 can neither hold nor trip.
        line = _num(k5.get("line"))
        out.append({"id": "K5", "level": "warning", "new": False, "disarmed": True,
                    "text": "K5 is disarmed: dlane.k5_clear is true in swarm.json, so no loss trips it; "
                            + ("the clear is recorded (the next line is "
                               + ("unknown" if line is None else f"${line:,.2f}") + "): take dlane.k5_clear out"
                               if not k5.get("set") and not k5.get("trip_open") else
                               "the dlane job records the clear on its next run; then take dlane.k5_clear out")})
    return out


def pl1_alarms(losses: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """PL1 (DONE-RULE-A1 A1.3, Oct 10, 2026): a program's own realized Probe net at or below the program loss line. The
    job retires it swarm-side (`run`, which rewrites this text once it has); exits go on. [] when none is due."""
    due = [p for p in (losses or {}).get("programs") or [] if p.get("due")]
    if not due:
        return []
    line = _num((losses or {}).get("line_usd"))
    return [{"id": "PL1", "level": "warning", "families": [p["family"] for p in due][:12], "line_usd": line,
             "text": f"PL1: {len(due)} programs' own realized Probe net is at or below the program loss line "
                     f"(${line or 0:,.2f}, dlane.program_loss_usd; DONE-RULE-A1 A1.3): "
                     + ", ".join(f"{p['family']} ${p['probe_net_usd']:,.2f}" for p in due[:6])
                     + ". The dlane job retires them swarm-side; their real positions exit by the House's rules"}]


def pt1_alarms(roster: Mapping[str, Any] | None, settings: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """PT1 (THE PROBE TOTAL AT $800, PREREG-T, Oct 10, 2026; its review): a warning while the constitution's Probe total
    is above L-D's $400, or the program loss line below L-D's -$200, and the roster (`roster_now`) does not seat
    `PT1_ROSTER`: off, closed or another count. PREREG-T measured the pair at roster 5 alone, and the roster moves by a
    swarm.json setting with no deploy while the pair needs the owner's: the alarm makes them coming apart visible. The
    way out is the pair's rollback (an owner deploy), the roster put back, or a new measurement. Never an action."""
    from ..live import money as M
    from ..swarm import dlane

    total = float(M.Table.from_constitution().probe_loss_total)
    line = dlane.cfg(settings)["program_loss_usd"]
    seats = None if not roster else ("closed" if roster.get("closed") else roster.get("seats"))
    if (total <= PT1_TOTAL_USD and line >= PT1_LINE_USD) or seats == PT1_ROSTER:
        return []
    where = "off" if seats is None else "closed (no new seat)" if seats == "closed" else f"{seats} seats"
    return [{"id": "PT1", "level": "warning", "total_usd": total, "line_usd": line, "roster": seats,
             "text": f"PT1: the Probe total ${total:,.0f} and the program loss line ${line:,.0f} were measured at roster "
                     f"{PT1_ROSTER} alone (PREREG-T), and the roster is {where}: roll the pair back to "
                     f"${PT1_TOTAL_USD:,.0f} and ${PT1_LINE_USD:,.0f} (an owner deploy), put dlane.roster back to "
                     f"{PT1_ROSTER}, or measure the pair at this roster first"}]


def zero_edge(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """P(Done | zero edge) beside the meter (decision 8; DONE-RULE-A1 A1.2, the readiness audit's M10): the setting's
    figure, and when it is one this code names (`dlane.ZERO_EDGES`: 0.024, A1.2's pin under L-D's $400 total; 0.027,
    PREREG-T's under the $800 total, since Oct 10, 2026) what it is: its horizon, holds, the budget variant, its source
    and who named it. A named figure that is not the one for the rules this code ships (`dlane.ZERO_EDGE`) says so;
    another figure is a setting's and says so: the claim states the figure for the rules in force."""
    from ..swarm import dlane

    value = dlane.cfg(settings)["done_zero_edge_p"]
    out: dict[str, Any] = {"value": value, "label": ZERO_EDGE_LABEL}
    named = next((z for v, z in dlane.ZERO_EDGES.items() if abs(value - float(v)) < 1e-9), None)
    if named is not None:
        out.update({k: v for k, v in named.items() if k != "value"})
        if named is not dlane.ZERO_EDGE:
            out["note"] = (f"a setting chose {named['value']} ({named['by']}); the rules this code ships carry "
                           f"{dlane.ZERO_EDGE['value']} ({dlane.ZERO_EDGE['by']})")
    else:
        out["note"] = ("a setting's figure (dlane.done_zero_edge_p), not one this code names ("
                       + "; ".join(f"{z['value']}: {z['by']}" for z in dlane.ZERO_EDGES.values())
                       + "): its horizon and budget are not said here")
    return out


def roster_now(root: str | Path) -> dict[str, Any] | None:
    """THE PROBE ROSTER as it stands (`league/swarm/bands.py` `roster`): {seats, probe, seated, waiting}, None while
    `dlane.roster` is 0 or the store cannot be read. Read only."""
    from ..swarm import bands

    try:
        return bands.roster(root)
    except Exception:  # noqa: BLE001 - the report goes on without it
        return None


# ------------------------------------------------------------------------------------------------- the report
def report(root: str | Path, *, settings: Mapping[str, Any] | None = None, now: float | None = None,
           previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The report (the module docstring), from the state root `root`: the swarm store opened read-only, the live book
    read-only, the closes, health and publish files. `settings` the swarm's (`settings.load(root)` when None). No write."""
    from ..swarm import dlane
    from ..swarm import settings as settings_mod
    from ..swarm.store import SwarmStore
    from . import direction as DIR
    from . import twins as TW

    root = Path(root)
    settings = settings if settings is not None else settings_mod.load(root)
    now = time.time() if now is None else float(now)
    today = _ny_day(now) or time.strftime("%Y-%m-%d", time.gmtime(now))
    start = inception()
    activity = fee_corrections(root)
    book = read_book(root / LIVE_DB)
    closes_doc = DIR.load_closes(root / DIR.FILE)
    unit = dlane.unit_context(root, settings)
    store = SwarmStore(root, readonly=True)
    try:
        lanes = Lanes(store)
        every = closes(book["positions"], activity["by_pid"], since=start, lanes=lanes)
        for c in every:
            if not c["house"]:
                c["bh"] = buy_and_hold(c, closes_doc)
        cache: dict[str, list] = {}
        # A1.4's inputs (Oct 10, 2026): each replayed program's last replayed day (the family's own `forward_replay`
        # target: the nightly replays a Candidate, Probe or Sized family only), and the day of the broker's fee reading.
        replay_days: dict[str, dict[str, Any]] = {}
        for fam in store.families(alive=True):
            if fam.get("band") in ("candidate", "probe", "sized"):
                target = (((fam.get("state") or {}).get("forward_replay") or {}).get("target") or {})
                replay_days[str(fam["id"])] = {"replayed": True, "day": target.get("day")}
        fees_as_of = _ny_day(_epoch(activity.get("as_of"))) if activity.get("as_of") else None
        research = Research247(store, root)
        prev_done = ((previous or {}).get("done") or {}) if isinstance(previous, Mapping) else {}
        # The per-close twins (B1 (c), Oct 10, 2026; `league/ops/twins.py`): read once, matched in each meter's replay gap
        # and, with the switch on, a close's replay is final only once its twin is (A1.4, the integration of Oct 10).
        twins = twin_records(store)
        twins_on = TW.cfg(settings) is not None
        common = dict(store=store, nightly_cache=cache, lanes=lanes, research=research, replay_days=replay_days,
                      fees_as_of=fees_as_of, now=now, twins=twins, twins_on=twins_on)
        done = {"all": meter(every, dlane.DONE["routes_all"], previous=prev_done.get("all"), **common),
                "screen": meter(every, dlane.DONE["routes_screen"], previous=prev_done.get("screen"), **common)}
        losses = program_losses(book["positions"], activity["by_pid"], store, settings, since=start)
        yesterday = datetime.fromisoformat(time.strftime("%Y-%m-%d", time.gmtime(now))).date() - timedelta(days=1)
        other = [c for c in every if not c["house"] and c.get("code") is None]
        direction = [c for c in every if not c["house"] and c.get("lane") == dlane.DIRECTION and c.get("code")]
        known = [c["pnl_usd"] for c in direction if c.get("pnl_usd") is not None]
        lane_net = {"closes": len(direction), "net_usd": _usd(sum(known, Decimal(0))), "unpriced": len(direction) - len(known),
                    "by_route": {code: _usd(sum((c["pnl_usd"] for c in direction if c["code"] == code and c["pnl_usd"]
                                                 is not None), Decimal(0))) for code in dlane.DONE["routes_all"]},
                    "bh": _bh_sum(direction), "label": dlane.LABEL, "k5_line_usd": dlane.k5_line(store, settings)}
        envelope = probe_envelope(root / LIVE_DB, book["positions"], today=today, unit_usd=unit.get("cap_usd"))
        k5 = dlane.k5_state(store, settings)
        started = store.get(dlane.STARTED_KEY)
        out: dict[str, Any] = {
            "schema": SCHEMA, "at": _iso(now), "day": today, "operator_only": True, "reported_only": True,
            "label": dlane.LABEL,
            "rule": {"sha256": dlane.DONE["rule_sha256"], **{k: (list(v) if isinstance(v, tuple) else v)
                                                              for k, v in dlane.DONE.items() if k != "rule_sha256"}},
            "lane": {"mode": dlane.cfg(settings)["mode"], "mode_effective": dlane.mode_effective(store, settings),
                     "started_at": started if isinstance(started, str) else None,
                     "screen": dlane.screen_effective(settings), "always_in_note": dlane.ALWAYS_IN_NOTE},
            "loosened": [dict(r) for r in LOOSENED], "tightened": list(TIGHTENED),
            "contamination": {"statement": CONTAMINATION, "meters": contamination_meters(root, lanes)},
            "funnel": {name: funnel(store, lanes, every, now=now, hours=hours, positions=book["positions"])
                       for name, hours in WINDOWS.items()},
            "bands_now": bands_now(store, lanes),
            "probe_envelope": envelope, "unit": {k: unit.get(k) for k in ("known", "cap_usd", "equity_usd", "closes",
                                                                          "close_day", "why")},
            "done": {**done, "p_done_zero_edge": zero_edge(settings),
                     "net_after_costs": net_after_costs(root, every, now=now),
                     "research_247_last_7_days": research((yesterday - timedelta(days=RESEARCH_FIRST_DAYS - 1)).isoformat(),
                                                          yesterday.isoformat()),
                     "other_routes": [{"pid": c["pid"], "family": c["family"], "instance": c["instance"],
                                       "route": c["route"], "pnl_usd": _usd(c["pnl_usd"])} for c in other],
                     "inception": dlane.DONE["inception"],
                     "fees": {"as_of": activity["as_of"], "why": activity["why"]}},
            "probes": probes(store, lanes, settings, book["positions"], losses),
            "roster": roster_now(root),
            "program_loss": losses,
            "fp_beside_trades": trade_screens(store, lanes, settings, book["positions"], every, since=start),
            "direction_net": lane_net,
            "account": account(root, every, activity, previous, now=now),
            "costs": costs(store, since=start, lane_since=_epoch(started) if isinstance(started, str) else None),
            "replay_twins": replay_twins([c for c in every if not c["house"] and c.get("code") in dlane.DONE["routes_all"]],
                                         twins),
            "k5": dict(k5),
        }
        out["alarms"] = alarms(store, settings, lanes, book, every, envelope, done, k5, unit, previous, now=now,
                               today=today, losses=losses) + pt1_alarms(out["roster"], settings)
    finally:
        store.close()
    return out


# ------------------------------------------------------------------------------------------------- the job
def run(ctx: Any) -> dict[str, Any]:
    """The job: the report written atomically to `<state>/dlane-report.json`, read-only on every store; then K5's writes
    (the operator's clear recorded, `dlane.k5_rearm`, then the trip when its line is crossed, `dlane.k5_trip`), each only
    when due; then the program loss line's retirements (`retire_due`); then each alarm a House alert (warning, or info
    for A8 and A9). With the lane off, the program loss line alone and no report (`lane_off`)."""
    from ..swarm import dlane
    from ..swarm import settings as settings_mod
    from ..swarm.store import SwarmStore
    from . import guard
    from .context import read_json, write_json

    root = Path(ctx.root)
    settings = settings_mod.load(root, config=getattr(ctx, "config", None))
    if not dlane.on(settings):
        return lane_off(ctx, root, settings)
    previous = read_json(root / FILE, None)
    with guard.readonly():
        out = report(root, settings=settings, now=ctx.now(), previous=previous if isinstance(previous, Mapping) else None)
    net = out["direction_net"]["net_usd"]
    tripped = False
    k5 = out["k5"]
    # K5's writes, each only when due (the store is opened writable for nothing else): a clear the operator made since
    # the last run (`k5_clear` true while the kv is set, or the kv deleted while a trip is open), then a trip.
    clear_due = (k5.get("set") and k5.get("cleared")) or (not k5.get("set") and k5.get("trip_open"))
    line = _num(k5.get("line"))
    trip_due = (net is not None and not k5.get("set") and not k5.get("cleared")
                and net <= (line if line is not None else dlane.cfg(settings)["k5_net_usd"]))
    rearmed = None
    if clear_due or trip_due:
        store = SwarmStore(root)
        try:
            rearmed = dlane.k5_rearm(store, settings, net, at=out["at"])
            tripped = dlane.k5_trip(store, settings, net, at=out["at"])
            out["k5"] = {**dlane.k5_state(store, settings), "new": tripped}
            if rearmed is not None:
                out["k5"]["rearmed"] = rearmed
                out["direction_net"]["k5_line_usd"] = dlane.k5_line(store, settings)
        finally:
            store.close()
        if rearmed is not None:
            out["alarms"] = [a for a in out["alarms"] if a["id"] != "K5"]
            if out["k5"].get("cleared"):
                out["alarms"].append({"id": "K5", "level": "warning", "new": False, "disarmed": True,
                                      "text": "K5 is disarmed: dlane.k5_clear is true in swarm.json, so no loss trips "
                                              f"it; the clear is recorded (the next line is ${out['k5']['line']:,.2f}): "
                                              "take dlane.k5_clear out"})
            else:
                out["alarms"].append({"id": "K5", "level": "info", "new": True, "rearmed": True,
                                      "text": f"K5 cleared ({rearmed['cleared']['how']}) and re-armed: its next line is "
                                              f"${out['k5']['line']:,.2f}, "
                                              f"${abs(dlane.cfg(settings)['k5_net_usd']):,.0f} below the lane's net at "
                                              "clearing"})
        if tripped and not any(a["id"] == "K5" for a in out["alarms"]):
            out["alarms"].append({"id": "K5", "level": "warning", "new": True,
                                  "text": "K5 tripped: the direction lane's realized net over every route is at or below "
                                          "its line; the lane reads shadow (no new direction Candidate, no incubator "
                                          "direction mark) until the operator clears it (swarm.json dlane.k5_clear, or "
                                          "the kv dlane_k5)"})
    retired = _retire(root, out, settings)
    write_json(root / FILE, out)
    for alarm in out["alarms"]:
        ctx.alert(alarm["level"], f"dlane: {alarm['text']}")
    if out["done"]["other_routes"]:
        ctx.alert("warning", f"dlane: {len(out['done']['other_routes'])} agent real closes on a route the Done rule does not "
                             "name: listed apart in the report, never counted or dropped silently")
    return {"ok": True, "path": str(root / FILE), "closes_all": len(out["done"]["all"]["closes"]),
            "closes_screen": len(out["done"]["screen"]["closes"]), "alarms": [a["id"] for a in out["alarms"]],
            "k5_tripped": bool(out["k5"].get("tripped")), "k5_new": tripped, "k5_rearmed": rearmed is not None,
            "retired": retired}


#: The public cause of a program-loss retirement (a `swarm.retired` event feeds the site's tape): words, no figure.
PROGRAM_LOSS_PUBLIC = "retired: its own realized Probe losses reached the program loss line"


def retire_due(root: Path, out: dict[str, Any], settings: Mapping[str, Any] | None) -> list[str]:
    """THE PROGRAM LOSS LINE, ACTED ON (DONE-RULE-A1 A1.3, Oct 10, 2026): every program the report found due
    (`program_losses`: alive, every Probe close priced, its own realized Probe net at or below `dlane.program_loss_usd`)
    is retired swarm-side (`SwarmStore.retire`: band "retired", a `swarm.retired` event with words and no figure, a
    notebook line and one private `swarm.dlane` event with the figures), in a writable open of the swarm store AFTER the
    read-only report, as K5's writes. Nothing else: the live path sees the family gone from the bands and puts its real
    instance on exits only, so its open positions close by their own program and the House's rules (exits go on). A
    tightening, never a trade or an order. The report's PL1 alarm and `program_loss.retired` say what was done. Returns
    the families retired by this call ([] when none was due, or each was retired already)."""
    from ..swarm.store import SwarmStore

    losses = out.get("program_loss") or {}
    rows = {r["family"]: r for r in losses.get("programs") or [] if r.get("due")}
    retired: list[str] = []
    if not rows:
        losses["retired"] = retired
        return retired
    line = _num(losses.get("line_usd"))
    store = SwarmStore(root)
    try:
        for fid, row in sorted(rows.items()):
            why = (f"DONE-RULE-A1 A1.3: its own realized Probe net ${row['probe_net_usd']:,.2f} over "
                   f"{row['probe_closes']} Probe closes is at or below the program loss line ${line or 0:,.2f} "
                   "(dlane.program_loss_usd): retired swarm-side by the dlane job; its real positions exit by the "
                   "House's rules")
            if store.retire(fid, why, public_reason=PROGRAM_LOSS_PUBLIC):
                store.note(fid, f"Retired by the dlane job: {why}")
                store.event("swarm.dlane", fid, {"action": "program_loss_retire", "probe_net_usd": row["probe_net_usd"],
                                                 "probe_closes": row["probe_closes"], "line_usd": line,
                                                 "rule": "DONE-RULE-A1 A1.3"})
                retired.append(fid)
    finally:
        store.close()
    losses["retired"] = retired
    for alarm in out.get("alarms") or []:
        if alarm.get("id") == "PL1":
            alarm["retired"] = list(retired)
            alarm["text"] = (f"PL1: retired swarm-side {len(retired)} programs whose own realized Probe net is at or below "
                             f"the program loss line (${line or 0:,.2f}, dlane.program_loss_usd; DONE-RULE-A1 A1.3): "
                             + (", ".join(f"{f} ${rows[f]['probe_net_usd']:,.2f}" for f in retired[:6]) or "none new")
                             + ". Their real positions exit by the House's rules; nothing else is touched")
    return retired


def _retire(root: Path, out: dict[str, Any], settings: Mapping[str, Any] | None) -> list[str]:
    """`retire_due`, never raising: a retirement that fails is a PL1 warning naming why, tried again at the next run."""
    try:
        return retire_due(root, out, settings)
    except Exception as exc:  # noqa: BLE001 - the report is written whatever: the retirement is tried again next run
        why = f"{type(exc).__name__}: {str(exc)[:200]}"
        out.setdefault("program_loss", {})["error"] = why
        out.setdefault("alarms", []).append({
            "id": "PL1", "level": "warning", "error": why,
            "text": f"PL1: a program due at the program loss line could not be retired ({why}); the next run tries "
                    "again"})
        return []


LANE_OFF_WHY = "the direction lane is off (dlane.mode): no report written"


def lane_off(ctx: Any, root: Path, settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """THE PROGRAM LOSS LINE WITH THE LANE OFF (the review of the weekend fixes, Oct 10, 2026). DONE-RULE-A1 A1.3 names
    one program whatever its lane, and `dlane.mode` "off" rolls back the direction lane, not the pinned rule: before this
    the job returned at once, so with the lane rolled back an alpha Probe program (or a direction family gone back to
    alpha) could lose past the line and drain the shared Probe total with no PL1 and no retirement. So the job still
    reads each program's own realized Probe net (`program_losses`, read-only as the report is) and retires a due one
    (`retire_due`), each PL1 a House warning. It writes no report: `dlane-report.json` is left as the lane last wrote it
    (the `stall` job does not read it while the lane is off), and the receipt carries the figures. Nothing due (or no
    swarm store) is the `skipped` receipt it always was."""
    from ..swarm.store import SwarmStore
    from . import guard
    from .funnel import SWARM_DB

    if not (root / SWARM_DB).exists():
        return {"status": "skipped", "why": f"{LANE_OFF_WHY}; no swarm store, so no program loss line to read"}
    with guard.readonly():
        activity = fee_corrections(root)
        book = read_book(root / LIVE_DB)
        store = SwarmStore(root, readonly=True)
        try:
            losses = program_losses(book["positions"], activity["by_pid"], store, settings, since=inception())
        finally:
            store.close()
    if not losses["due"]:
        return {"status": "skipped", "why": f"{LANE_OFF_WHY}; the program loss line (DONE-RULE-A1 A1.3) is read: none due",
                "program_loss": {"line_usd": losses["line_usd"], "due": [], "programs": len(losses["programs"])}}
    out: dict[str, Any] = {"program_loss": losses, "alarms": pl1_alarms(losses)}
    retired = _retire(root, out, settings)
    for alarm in out["alarms"]:
        ctx.alert(alarm["level"], f"dlane: {alarm['text']} (the direction lane is off: no report written)")
    return {"ok": True, "lane": "off", "why": f"{LANE_OFF_WHY}; the program loss line (DONE-RULE-A1 A1.3) acted on",
            "program_loss": {"line_usd": losses["line_usd"], "due": losses["due"], "retired": retired,
                             "error": losses.get("error")},
            "alarms": [a["id"] for a in out["alarms"]], "retired": retired}


__all__ = ["run", "report", "FILE", "CONTAMINATION", "LOOSENED", "TIGHTENED", "closes", "meter", "reading", "replay_gap",
           "replay_twins", "twin_records",
           "buy_and_hold", "entry_delta", "funnel", "probes", "probe_envelope", "alarms", "fee_corrections", "read_book",
           "version_of", "inception", "Lanes", "ZERO_EDGE_LABEL", "trade_screens", "ALPHA_FP", "finality",
           "research_window", "Research247", "operator_edits", "program_losses", "dm1_reach", "net_after_costs",
           "zero_edge", "retire_due", "GAP_MEASURE", "NEWS_CAUSES", "E0_BASIS", "pl1_alarms", "pt1_alarms", "lane_off"]

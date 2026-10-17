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

THE DONE METER (DONE-RULE.md, pinned Oct 9, 2026 before release L-D or D-1 shipped; since THE OWNER'S CHANGE OF THE
PINNED RULE, A50, the goal of Oct 16, 2026, docs/goals/DONE-RULE-A50.md; `dlane.DONE` holds its sha256 and constants,
`dlane.OLD_DONE` the rule as pinned on Oct 9, read by nothing), read exactly as pinned:
- WHAT COUNTS: every real close of an agent program (a swarm family; never a House route: the calibration round trips,
  the House live test, any `house:*` family) closed since 2026-09-26T06:23Z on Probe/Sized `:r`, tuition `:t` or the
  incubator `:i` (`economics.route_of`), the Oct 8 tuition close included. Nothing is dropped after the fact: a close on
  an agent route the rule does not name is listed apart with a House warning, never silently counted or lost.
- P&L: realized after all fees: the book's cash (fees included at the book's estimate) plus the broker's posted fee
  correction where it has posted (`publish.json`'s saved activity reading, `fees_by_pid`: `league/account_activity.py`),
  each close labelled `broker` or `estimate`. A close the book could not price (`unpriced_close`) makes a meter's net
  unknown, never an invented zero.
- TWO METERS: `done_screen` (`:r` only, the evidence route) and `done_all` (`:r` + `:t` + `:i`, the goal's letter).
- THE BAR: at least 15 closes, at least 3 closes from each of at least 2 programs, and net > 0 after fees (A50: were 30
  and 5).
- CONSISTENT WITH REPLAY: every program with 3 or more MATCHED closes (5 before the captain's A50a(2), Oct 16, 2026;
  closes of a version on a day its nightly replay also traded: D5's measure, `money.forward_stats`, read here live
  minus replay and pooled over the program's versions; `GAP_MEASURE` says it is a ratio of sums) has a gap within
  +/-0.10 a dollar of maximum loss, AND (DONE-RULE-A1 A1.1, Oct 10, 2026) at least 2 programs are so measured: zero
  matched closes never passes. Every program is listed with its
  closes, matched closes and gap (each checkpoint's `by_program`, `replay_coverage`), never dropped.
- RESEARCH 24/7 (DONE-RULE item 7; `Research247`, Oct 10, 2026): births, Gym runs and Validations every UTC day of the
  checkpoint's window (its last 3 UTC days for the first, `dlane.DONE["research_first_days"]`, 7 before A50; every day
  since the one before for the rest), at the research
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
- READ ONLY AT CHECKPOINTS: the 15th counted close, then every 5th (A50: the 30th, then every 10th, before), fixed by
  count and never chosen; each reading is over exactly the first K closes in
  close order (`checkpoints`); it holds when items 3, 4 and 7 hold. The running figures between checkpoints are counts,
  never a reading. FINAL READINGS (DONE-RULE-A1 A1.4; `finality`): a reading is final once every counted close's
  replay has landed (its own twin final, with the twins on; else its program's nightly) and its broker fees have posted
  (and the research window has ended); a final reading is frozen (carried from the previous report as it was). A Done claim is a holding FINAL checkpoint (the meter's `holds`);
  A8 (an `info` alert) names one the first time a report sees it final.
- BESIDE IT, ALWAYS: P(Done | zero edge) (`zero_edge`, labelled as a simulation; DONE-RULE-A1 A1.2 and DONE-RULE-A50
  item 6): the figure MEASURED UNDER THE RULE IN FORCE, stated only from the setting `dlane.done_zero_edge_p` written
  as a block (`dlane.ZERO_EDGE_BLOCK_KEYS`) whose `measured_under` is the pinned rule's sha256; until one is, the report
  says plainly that it is not yet measured. Beside it (`beside`), the figure as before with its horizon, holds, budget
  and source, labelled as simulated under the Oct 9 rule: 2.7% since THE PROBE TOTAL AT $800, Oct 10, 2026, PREREG-T's
  at roster 5; 2.4%, A1.2's pin, under L-D's $400 total before it; both kept labelled in `dlane.ZERO_EDGES`. It is
  never stated as the figure under the owner's rule (A50); Net after costs (`net_after_costs`, from the close economics over the same days);
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
  `dlane` and `done` causes). Since the rehearsal of Oct 15, 2026 also DC1 (`dc1_alarms`, a warning): a meter's latest
  checkpoint is final and does not hold, or is still not final at the pre-open of the 2nd session after its last
  close. Before it, a checkpoint that did not hold was told to no one. Its text has no dollar figure, no net and no
  program row, and a reading that is not final names no verdict; it is no owner step.

THE GOAL OF OCT 10, 2026 AND THE EQUITY LANES (release E1; the captain's design 6d and amendment A8):
- DONE IS COUNTED FROM OCT 10, 2026 (the goal: "counted from Oct 10, 2026 (earlier closes reported beside, not
  counted)"; `DONE_FROM`, 00:00 New York): both meters read only the agent closes from then on (`done.counted_from`),
  and every earlier agent close since the rule's inception is listed beside them (`done.earlier`), never counted. The
  Done rule itself was unchanged by it (then 30 closes, 5 from each of 2 programs, net > 0 after fees, consistent with
  replay, research 24/7, read at the 30th close and every 10th; since A50 15 closes, 3 from each of 2 programs, read at
  the 15th close and every 5th, item 7 first over 3 UTC days). A frozen reading is carried only from a report that
  counted from the same instant UNDER THE SAME PINNED RULE (`rule.sha256`: a reading frozen under the Oct 9 rule is
  never carried into the owner's).
- AN EQUITY CLOSE is one lot of the House's EquityBook (`live.sqlite` `eq_lots`, league/equity/live.py) fully closed,
  with its net cash (fees and dividends included: the lot's `cash`), on the route its instance names (`:r`, so both
  meters), its entry notional standing for the maximum loss (a long lot can lose at most what it paid), its key
  `eq:<lid>` (`equity_closes`). It is matched to its own closed-form twin (league/ops/twins.py `equity_twin`, the swarm
  store's kv `equity_twins`): there is no nightly replay of an equity program, so with no final twin its replay has
  not landed (A1.4). Its fees are the broker's once the book marks them posted (the lot's `info.fee_basis` "broker").
- BESIDE EVERY EQUITY CLOSE AND EVERY CHECKPOINT (`equity_beside`): the lane's label (MARKET BETA or EQUITY,
  `league.swarm.elane.LABELS`), the same-risk buy-and-hold over the same sessions (the lot's own symbol, delta one, from
  its twin's record) and MTE (the close's net return less it), the screen's false-positive line recorded at the
  program's look (the pinned receipt's `beside` line, league/equity/screen.py `beside_line`: S2's under the captain's
  A11, with the program's own FP at zero edge, its holdout-only rate and its drift-kept rate at c_H,used; S1's for a
  look judged under receipt 1), "profit from market direction" said plainly (`EQUITY_DIRECTION`), and whether the
  program was seeded by the captain's build agents.
- DONE WITH AND WITHOUT THE THREE SEEDED PROGRAMS (A8.12): `done.without_seeded` repeats both meters over the closes of
  every program but the seeded ones (the swarm store's kv `elane_seeds` and the book's `eq_instances.seeded`).
- THE SHARED BUDGET'S CONSEQUENCE (A8.6): `equity.options_probe_room` says plainly that while the equity lane holds all
  it may (the lower of its Probe sleeves, max_programs x sleeve_share x E, and the invested cap, invested_share x E;
  open risk at the ETF weight) the options Probe lane has only the rest of the $400 window: effectively off. One-ETF
  programs hold half a sleeve each, and the statement says what that is. The seats and the sleeve are the table's
  two numbers (release E5-S: the constitution's `probe` comment): the statement and the figures are read from the
  rows in force (`equity_probe_note`), never written here.
- PRE-REGISTERED BEFORE THE FIRST EQUITY CLOSE (the captain's A14, Oct 10, 2026; `PREREGISTERED`, verbatim in every
  report as `done.preregistered` and in docs/operations.md; the consistency reading computed since release E3): how
  the Done rule's
  "live fills consistent with their replay" is read (`A14_CONSISTENCY`: the mean fill gap against the official-price
  model at most 15 bp a side AND the live and the shadow intents agreeing on at least 95% of the counted sessions, read
  at each Done checkpoint over its counted closes; else "not consistent" beside the P&L; since THE OWNER'S CHANGE, A50,
  the intents also pass with all but one agreeing when fewer than 40 sessions are read: `A50_INTENTS`, beside it as
  `done.preregistered.amended`, read by league/ops/forward_db.py `a14_intents_ok`), what every Done reading is
  reported beside (`A14_BESIDE_DONE`: the number of distinct close dates and a date-clustered t), and the forward
  seat rule, written and inactive (`A14_SEAT_RULE`). ITEM 4 OF A READING THAT HOLDS AN EQUITY CLOSE IS READ BY A14, NEVER
  BY THE OPTIONS MEASURE (`a14_consistency`): the pinned replay gap divides by the maximum loss, which for a long lot is
  its whole notional, so its 0.10 bound would let a thousand basis points of notional through where A14 says 15 a side.
  The fill-gap half is computed (the mean of the counted equity closes' final priced twins' `gap_bp`, at most
  `A14_GAP_BP` in size); a mean past the bound fails item 4 ("not consistent" beside the P&L). CONSISTENCY IS
  COMPUTED SINCE RELEASE E3 (`a14_of`; league/ops/forward_twins.py `a14_reading`; each checkpoint's `a14`): the
  intents-agreement half's reader has landed, so a checkpoint that holds an equity close needs the SIZE of the mean
  fill gap of its priced twins within 15 bp a side, either way, AND the live and the shadow intents agreeing on 95% of
  its counted sessions, beside the pinned rule's own measure (CONSISTENT WITH REPLAY, above). The meter hands each
  checkpoint's reading its A14 (`reading(..., a14=)`); a reading handed none (the running figures, never a Done
  reading) keeps the fill-gap half and is still NOT READ. Unmeasured, unreadable or misshapen, A14 does not hold and
  the reading is not final; a frozen final reading is carried as it was. THE CLOSE-DATE FIGURES ARE COMPUTED SINCE
  RELEASE E4's STEP TWO (`close_dates`; each checkpoint's `close_dates`, beside and never a rule): the distinct close
  dates among the checkpoint's counted closes, all programs, and the date-clustered t of their P&L (the closes of one
  date summed: eight lots of a basket sold at one open are ONE date). No rule reads them, and no forward rule moves a
  seat (`PREREGISTERED["status"]` says so in the report). A reading with no equity close is read by the pinned rule's
  own measure, as before.
- THE SEATS (release E5-A; the captain's A24, `SEAT_RULE`, registered Oct 11, 2026, before the first live share close
  and before any program waited for a seat, and amended by A30, `A30_SEAT_AMENDMENT`, before it went live; it
  replaced A14's forward seat sentence, which was written and never active): `equity.seats` is the EquityBook's own
  seat plan (its kv `eq_seat` in live.sqlite, read with the book: the book is the one source of who holds a seat and
  who waits), as {rule, seats, holders (each with its seat's day, its seated sessions, the sessions left out of them
  because the House refused every open, whether it is flat and idle, and whether it was SEEDED), seeded_seats and its
  sentence (which seats the captain-seeded programs hold: said in every report), waiting (each program's rank
  POSITION, never K, and whether it is flagged idle; under "first-come" the swarm's roster by pass time),
  idle_flagged, left_out (the sessions the idle clock did not run in, each with the House's reason), last_change
  (the last change of hands and why), preregistered (the rule's text, its stated costs and A30's amendment)}. K is
  never in a report.
- THE FORWARD RECORD (release E3; league/ops/forward_report.py): `forward_record` is that job's report as it last wrote
  it (None when absent or stale), and its alarms (FW1-FW8, RR1, RR2, CP1, CP2, MM1: ids, counts and dates only) ride
  this report's `alarms`, so the `dlane` stall cause mails a warning. Read only, and never this report's failure.
  (Release E4, package J: the panel lane's FX1-FX3 ride with them, by their own two switches.)
- P(DONE | ZERO EDGE) AS BEFORE IS THE OPTIONS RULES' FIGURE (`ZERO_EDGE_EQUITY_NOTE`): it was never measured for
  share closes, and a delta-one lane's is far higher. A report that holds an equity close says so on that figure
  (`beside`) and in each checkpoint's `equity` block; no figure for the equity lanes is stated but a measured one.
- THE PANEL LANE (release E4; `panel_section`, `equity.panel`): a panel program's close is an equity close under the
  label EQUITY (PANEL); beside EVERY live panel trade rides XS1's sentence, the line its program's one look recorded
  (`EquityScreens.xs1`); beside its closes the distinct close dates and the date-clustered t (A14: one observation a
  close date), its same-risk buy-and-hold in SPY, its decisions and their morning re-reads, and what reading by date
  costs; and every recorded style-open passer with why it holds no seat (the captain's A22, `style_open_passers`). Its
  residual and its twin's agreement on rebalance sessions are the forward record's (release E4's package J,
  league/ops/forward_xs.py `beside`; `panel_forward` puts them beside the program, `PANEL_OWED` while that record
  holds none of it yet). None of it is a rule.
- THE SPAN BUY-AND-HOLD (C1, A45: the scaling plan's 2.4, the benchmark its script tests a share program against;
  `span_bh`): each checkpoint's `by_program` row of a share program carries `span_bh`, one entry a program version
  among the checkpoint's first K counts: {version, usd, priced, why, basis "adjustment=all", blocked [[from, to]],
  symbols {SYM: {before, last, sessions, close_before, close_last, closes at every segment boundary, exposure_usd,
  usd, sha, ...}}, spy {closes, usd} for a panel}. A single-name program's is the House's own `_bh_pnl` rule
  (league/equity/live.py `span_bh`) with the plan's one change: the sessions the House blocked it from opening, while
  it held nothing in the symbol, are taken out of the span, which splits there; with none it is `_bh_pnl` exactly. The
  blocked sessions are those in which the House let no open go at all (its open note, every entry window refused),
  less every entry day of the version's lots, so a version's are the same at every checkpoint (`SPAN_BLOCKED` says
  what the note does not hold). A panel program's is B10 (`b10_bh`). Every close is the book's own (`eq_bars`,
  adjustment=all, one fetch). Unreadable is `priced` False with `why`, never a figure. It is written with its
  checkpoint and FROZEN WITH IT (a final checkpoint is carried whole, so the field is never recomputed: an
  adjustment=all close a later dividend moves cannot move it). No Done rule, count, checkpoint or rule sha reads it or
  changes with it.

Standard library only, except the Probe envelope's figures (`fast_lane.probe_budget` and `real.probe_figures` read
`league.live.real`, whose Gym legs need numpy, as the House box has): they are an `error` entry where that cannot load.
The span buy-and-hold's rule is league/equity/live.py's, imported inside `span_bh`: where it cannot load, each entry is
`priced` False and says so.
"""
from __future__ import annotations

import json
import math
import re
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
#: DC1 (the rehearsal of Oct 15, 2026; `dc1_alarms`): a meter's latest checkpoint still not final at the pre-open of
#: this many sessions after the New York day of its last counted close (`DC1_PREOPEN_S` before the session's open: the
#: `dlane` job's pre-open run, league/ops/registry.py). By design a close is final at the next session's pre-open (a
#: Friday's at Monday's, one before a holiday at the session after it), so the 2nd session leaves one session of
#: slack. And the item names its text gives (DONE-RULE's items a checkpoint reads).
DC1_SESSIONS = 2
DC1_PREOPEN_S = 1800
DC1_ITEMS = {"3": "item 3 (the bar)", "4": "item 4 (consistent with replay)", "7": "item 7 (research 24/7)"}
#: What no DC1 text may hold: a dollar sign, or a decimal figure (a clause of `final_why` holding one is left out).
_DC1_FIGURE = re.compile(r"\$|\d[.,]\d")
#: The label of the zero-edge figure (decision 8).
ZERO_EDGE_LABEL = "P(Done | zero edge), simulation"
#: THE GOAL OF OCT 10, 2026: Done is counted from Oct 10, 2026, 00:00 New York; every earlier close is reported beside.
DONE_FROM = "2026-10-10T04:00:00Z"
#: An equity close's key: `eq:<lid>` (league/ops/twins.py `equity_key`, the book's export `twin_key`).
EQUITY_PREFIX = "eq:"
#: RELEASE E4, THE PANEL LANE: a panel program's lots carry the panel decision's tag (league/xs/book.py `TAG`), its
#: instance the kind "panel" (`eq_instances.kind`), and every figure of it the label `PANEL_LABEL` (that module's `LABEL`;
#: a test holds the three equal, so this module imports nothing of league/xs to say them).
PANEL_TAG = "xs"
PANEL_KIND = "panel"
PANEL_LABEL = "EQUITY (PANEL)"
#: C1 (A45; the scaling plan's 2.4, `span_bh`): the equity book's open note (league/equity/live.py `OPEN_NOTE_KEY`) and
#: the one basis every span close is read on (its `SPAN_BASIS`); a test holds both equal to the book's.
OPEN_NOTE_KEY = "eq_open_note"
SPAN_BASIS = "adjustment=all"
#: Where a share program's `span_bh.blocked` comes from, and what that source does not hold (said in every entry). The
#: open note (league/equity/live.py `shut_days`, of A30 (2)'s note) gives the sessions in which EVERY entry window the
#: House looked in refused every real equity open: its real-money block (the kill switch, the daily and drawdown stops,
#: the House's pause, the grant, a reconciliation freeze), equity_money off, the stock proof. A session refused in one
#: window and clear in the other is not one (a program could still open in the other: the idle clock's `refused_days`
#: reads it as refused; this does not). Less every entry day of the version's lots in the book. Kept by session in NO
#: House record, so never in `blocked`: the program's own seat lost (the book keeps its last band mark only; band moves
#: are events), the shared loss window's refusals (a buy refused or cut for budget is recorded per intent, and only
#: when one was asked), and a session the House did not run in.
SPAN_BLOCKED = ("the House's open note (eq_open_note): the sessions in which every entry window refused every open, "
                "less every entry day of this version's lots; a seat lost and the loss window's refusals are kept by "
                "session nowhere, so never listed")
#: What a panel program's entry says instead: B10 holds each lot over its own sessions, so nothing is split.
SPAN_B10 = "B10 holds each lot in SPY over its own sessions: there is no span to split"
#: What rides beside a panel program's close dates (the captain's A14; E4-SPEC 10.5).
PANEL_BY_DATE = (
    "A panel program is read ONE OBSERVATION A CLOSE DATE: five lots bought on one date and sold on another share one "
    "market move and one fill minute. Done's meter counts a closed lot as one close; the distinct close dates and the "
    "date-clustered t ride beside it.")
#: What is said wherever the forward record holds no figure of a panel program yet (package J: league/ops/forward_xs.py).
PANEL_OWED = (
    "not recorded yet: a panel program's residual against its matched cells and its shadow twin (the rebalance sessions "
    "agreed) are the forward record's, written by its panel night (the job forward_xs, after each night's panel store). "
    "No figure stands here until that night has written this program's twin; while its twin marker is missing or behind "
    "no panel program takes a live seat (the lane's mode \"live\" reads as \"gate\").")
#: What is said of a recorded style-open passer's forward days (the captain's A22 (1): recorded and shadowed, never seated).
PANEL_SHADOWED = (
    "shadowed: every scored panel version is registered in the forward record with its code frozen and recomputed on "
    "its own forward days each panel night (the job forward_xs), this one too; the forward route is its way to a seat.")
#: THE CAPTAIN'S A22 (1), said beside every recorded style-open passer.
STYLE_OPEN_RULE = (
    "A22: a STYLE-OPEN program takes no live seat on an XS1 pass alone. The House reads each panel program's loadings on "
    "size, beta, 12-1 momentum and volatility from its Train holdings by one fixed rule; a no-skill tilt to a style that "
    "won the holdout passes XS1 far above the owner's wall, so such a passer is recorded and shadowed, never seated. The "
    "forward route is its way to a seat.")
#: PROFIT FROM MARKET DIRECTION, said plainly beside every equity close and checkpoint (the goal of Oct 10, item 4).
EQUITY_DIRECTION = (
    "Profit from market direction counts and is said plainly: a long ETF or stock lot earns what its symbol did over the "
    "sessions it was held. The same-risk buy-and-hold beside each close is that direction (its notional held in its own "
    "symbol over the same sessions, cost-free); MTE is what the program's timing added after costs. A MARKET BETA "
    "program's profit is the market's direction, not alpha, and a delta-one lane can reach Done whenever the market rises: "
    "a Done read on such closes is weak evidence of skill.")
#: A14 (the captain's pre-registration of Oct 10, 2026, written BEFORE the first equity close so that it cannot be read
#: after the fact; text first, its consistency reading computed since release E3): how the Done rule's "live fills consistent with their
#: replay" is read, what every Done reading is reported beside, and the forward seat rule. The three sentences are in
#: every report verbatim (`done.preregistered`) and in docs/operations.md (league/tests/test_dlane_report_equity.py
#: holds the page to these words). The Done rule itself (DONE-RULE.md, `dlane.DONE`) is unchanged.
A14_CONSISTENCY = (
    "Done's \"live fills consistent with their replay\" is read at each Done checkpoint, over its counted closes: the "
    "mean fill gap against the official-price model is at most 15 bp a side AND the live and the shadow intents agree "
    "on at least 95% of the counted sessions. A checkpoint that does not meet both says \"not consistent\" beside its "
    "P&L.")
A14_BESIDE_DONE = (
    "Every Done reading is reported beside the number of distinct close dates among its counted closes and a "
    "date-clustered t of their P&L.")
A14_SEAT_RULE = (
    "The forward seat rule is written and inactive: an incumbent with fewer than 5 real closes is never unseated, "
    "except by EDM1.")
#: A14's two bounds as the sentence above states them: the mean fill gap a side (basis points) and the share of counted
#: sessions on which the live and the shadow intents agree.
A14_GAP_BP = 15.0
A14_AGREEMENT = 0.95
#: THE OWNER'S CHANGE OF A14's INTENTS BOUND (A50, the goal of Oct 16, 2026: "intents agree on >= 95% of sessions, or
#: all but one when fewer than 40 are read"). A14's sentences above stay as the captain registered them on Oct 10, 2026;
#: this one rides beside them in every report (`done.preregistered.amended`) and in docs/operations.md. The bound is
#: read once, by league/ops/forward_db.py `a14_intents_ok` (`A14_ALL_BUT_ONE_UNDER` here is its figure, held equal to
#: `forward_db.A14_ALL_BUT_ONE_UNDER` by league/tests/test_done_a50.py).
A14_ALL_BUT_ONE_UNDER = 40
A50_INTENTS = (
    "Changed by the owner (A50, the goal of Oct 16, 2026): the live and the shadow intents agree on at least 95% of the "
    "counted sessions, or, when fewer than 40 counted sessions are read, on all of them but one. The fill-gap half (at "
    "most 15 bp a side) is unchanged. Its cost: one bad session is forgiven at small counts (under 20 sessions the 95% "
    "bound forgave none; from 20 to 39 the two bounds agree).")
#: A24, THE SEAT RULE (the captain's pre-registration of 13:42Z Oct 11, 2026, BEFORE the first live share close and
#: before any program waited for a seat; release E5-A builds it; the constitution's `equity_money.probe.seat` holds its
#: name and constants, league/equity/bands.py and league/equity/live.py apply it). The sentences are in every report
#: verbatim (`equity.seats.preregistered`) and in docs/operations.md (league/tests/test_equity_seats.py holds the page
#: to these words and the figures in them to the constitution's rows). It REPLACED A14's forward seat sentence
#: (`A14_SEAT_RULE`), which stays above as it was registered: it was written and never active.
A24_SEAT_RULE = (
    "The seat rule is \"activity-1-free\" (the rollback value is \"first-come\"). A free seat goes to the best-ranked "
    "waiting passed program. Its rank K is the smaller of its Validation close days and its Train-era close days per "
    "250 sessions, a day counted only when the lots it closed that day sum to at least 0.25 of its sleeve (read as "
    "0.25 minus 0.0005, the engine's rounding); ties go to the earlier look pass, then the family id. K reads no P&L "
    "and no sealed window, and is never printed in public text. A seated program that is flat and has had no buy "
    "reach the venue, and none cut or refused by the loss budget, for 10 seated sessions is flagged idle: it keeps its "
    "seat while nobody waits and yields it at once when an unflagged program waits. A buy refused by the instrument "
    "cap, the invested cap or cash does not count as asked. A yielded program returns only into a free seat, by the "
    "same rank, with no new look. No trading program is ever stopped by the seat rule: outranking is not adopted. "
    "Seeded and bred programs follow the same rule, and EDM1 covers waiting programs too. The rule only decides who "
    "may open: never a forced or hand-placed trade, and no lot is ever sold by it.")
A24_SEAT_COSTS = (
    "The seat rule's costs, stated: closes concentrate in frequent traders, so Done reached this way is weaker "
    "evidence of skill; a daily slice of a quarter sleeve can buy rank; a slow, non-idle incumbent keeps its seat.")
#: A30, THE SEAT RULE AS AMENDED BEFORE IT WENT LIVE (the captain's amendment of 20:47Z Oct 11, 2026, from release E5-A's
#: independent check; no seat had changed hands by the rule). A24 above stays as it was registered; these sentences
#: ride beside it in every report (`equity.seats.preregistered.amended`) and in docs/operations.md (the same test holds
#: the page to them). A24 with A30 is the rule in force.
A30_SEAT_AMENDMENT = (
    "Amended before the rule was live (A30). Free seats first: a free seat is filled before the idle test, and an idle "
    "seat yields only for an unflagged program that would still wait once every free seat is filled; the study that "
    "measured the rule ran the idle test first, so its gain was measured under that slower order. The idle clock does "
    "not run while the House refuses every open: a session in which the House refused opens for a House-wide reason "
    "(paused, the kill switch, a stop, a freeze, the grant not ratified, the paper proof's BUY stage not passed) is "
    "left out of every program's idle count and of its seated-session count for the idle test. A lost buy is not flat: "
    "a buy whose answer was lost keeps its program from being read flat, and so from yielding, for as long as the book "
    "may still take the lost order back, so no seat change ends in a House sale of a lot that shows up afterwards. "
    "Stated and accepted, not changed: a daily quarter-sleeve slice buys rank and immunity from the idle rule.")
SEAT_RULE = {
    "id": "A24", "registered": "2026-10-11T13:42Z",
    "before": "the first live share close, and before any program waited for a seat",
    "rule": A24_SEAT_RULE, "costs": A24_SEAT_COSTS, "outranking": "not adopted",
    "amended": {"id": "A30", "registered": "2026-10-11T20:47Z",
                "before": "the rule was live: no seat had changed hands by it", "text": A30_SEAT_AMENDMENT},
    "rollback": "equity_money.probe.seat.rule \"first-come\" (one owner deploy, one money-digest move; nobody is unseated)",
    "replaces": "A14's forward seat sentence (`done.preregistered.forward_seat_rule`): written, never active",
}
PREREGISTERED = {
    "id": "A14", "registered": "2026-10-10", "before": "the first equity close",
    "consistency": A14_CONSISTENCY, "beside_done": A14_BESIDE_DONE, "forward_seat_rule": A14_SEAT_RULE,
    # A24 (Oct 11, 2026; release E5-A) replaced the sentence above before any seat could change hands by it.
    "seat_rule": "A24 replaced the forward seat sentence above on Oct 11, 2026, before the first live share close: it "
                 "was written and never active. Since release E5-A the seat rule in force is A24's, as A30 amended "
                 "it before it went live (`equity.seats.preregistered`), under which an idle seated program may yield "
                 "its seat whatever its closes; it reads no P&L of the forward record.",
    "status": "consistency is computed since release E3 (each checkpoint's `a14`: the size of the mean fill gap "
              "either way, and the intents); the close-date figures are computed since release E4's step two (each "
              "checkpoint's `close_dates`, beside and never a rule); no forward rule moves a seat",
    # A50 (Oct 16, 2026): the owner's change of the intents bound, beside A14's sentence, which stays as registered.
    "amended": {"id": "A50", "registered": "2026-10-16T02:10Z", "by": "the owner's goal of Oct 16, 2026",
                "before": "the first Done checkpoint (6 counted closes, none frozen)", "text": A50_INTENTS},
}
#: P(DONE | ZERO EDGE) BESIDE EQUITY CLOSES: the figure the report carries is the options Probe rules' simulation. No
#: figure for the share lanes is stated (none is committed); this sentence rides on the figure and in each checkpoint's
#: `equity` block whenever a counted close is an equity close.
ZERO_EDGE_EQUITY_NOTE = (
    "This P(Done | zero edge) is the options Probe rules' simulation figure only. It was never measured for the MARKET "
    "BETA and EQUITY lanes' share closes: a delta-one lane reaches Done whenever the market rises, so its zero-edge "
    "P(Done) is far higher than this figure, and a Done read on share closes is weak evidence of skill.")
#: A8.6: the shared loss budget's consequence for the options Probe lane, said in the report and the docs. THE
#: SENTENCE, with its figures left open: `equity_probe_note` fills them from the constitution's rows (the seats and
#: the sleeve are two numbers that move together, release E5-S), and `EQUITY_PROBE_NOTE`, below it, is the sentence at
#: the constitution in force.
EQUITY_PROBE_SENTENCE = (
    "THE LOSS BUDGET IS SHARED (A8.6): the equity lane's open Probe risk counts in the same ${window} window and ${total} "
    "total as the options Probe lane. The equity lane holds at most the lower of its Probe sleeves (max_programs x "
    "sleeve_share x E: {seats} x {sleeve} E) and the invested cap (invested_share x E: {invested} E), so its open risk at "
    "the ETF weight ({weight}) is at most {most} x E; {seats} one-ETF programs ask for a lot of {lot} x E each, of which "
    "the lane holds at most {one_held} x E, {one_risk} x E of open risk. The options Probe lane has only the window's "
    "rest (${window} less its realized loss less {weight} x the equity lots), and no room under the invested cap once "
    "the equity lane is invested to it: effectively off.")
#: The same statement for a constitution that has no equity rows to read (a tree before the lane): no figure.
EQUITY_PROBE_BARE = (
    "THE LOSS BUDGET IS SHARED (A8.6): the equity lane's open Probe risk counts in the same window and total as the "
    "options Probe lane, which has only the window's rest and no room under the invested cap once the equity lane is "
    "invested to it: effectively off.")
#: THE PANEL SEATS (release E4 step two; the constitution's `equity_money.panel`): what a panel program holds and what
#: it costs, said beside the panel pool's plan in every report that has one. `equity_panel_note` fills the figures.
EQUITY_PANEL_SENTENCE = (
    "THE PANEL SEATS (equity_money.panel): a panel program holds one of {seats} panel seat(s) of its own, never one of "
    "the {etf_seats} ETF seats, at a sleeve of {sleeve} x E; its whole basket of stocks is {risk} x E of open risk at "
    "the stock weight ({weight}), in the same ${window} window, first come (no slice of it is kept for the panel). "
    "Outside that room a basket bought from flat or rotated whole is scaled to the room and a partial rotation's new "
    "name is refused at the send. ITS COST: one more program on real money at once, and a basket's lots closed at one "
    "open are one market move, so Done counts a panel program's lots closed on one date as ONE close (for the 15th "
    "close, every later checkpoint and its program's 3; the lots and the distinct close dates stand beside).")
#: The same statement for a constitution with no panel row: no figure.
EQUITY_PANEL_BARE = ("THE PANEL SEATS (equity_money.panel): the constitution has no panel row, so no panel program "
                     "holds a seat or a sleeve.")
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
            "gate; its card says \"always-in\" or \"no gate\" and has no ablation) is bound only by the always-in "
            "direction rows on its roots, any class or holding; its birth joins the always-in lineage on each of its "
            "roots and no gated one, ONE Validation try a root, which a living always-in family there claims; it trades "
            "only the roots it was born on and never forks; G1: on each root its program enters on 90% of the Train "
            "sessions it is flat (90% of all of them when it holds several calls at once), with 90% of its entries' "
            "risk within 3x of their median and 90% of its holds a session or more and within 2x of their median, or "
            "its version due for Validation is never validated and it retires; alpha cards and gated direction cards "
            "are judged as before",
     "cost": "at most one always-in Validation try per root (SPY, QQQ, IWM), ever, unless the owner changes "
             "dlane.val_tries (fewer when a family on two roots joins their lineages): each is the lane's D2 lottery at "
             "10.37% per program at zero edge on mixed worlds (12.39% on 2022-24 worlds; higher when the screen windows "
             "rose), so up to three more such lotteries in all; their profit is index beta minus option costs, reported "
             "beside the same-risk buy-and-hold, never alpha; what G1 cannot see is a gate that only tilts inside its "
             "bands (a size that halves, a hold between 4 and 6 sessions, a strike that keeps the risk in band)"},
    # RELEASE E3 (league/swarm/elane_folds.py): the hidden work year.
    {"rule": "the equity Train bar", "was": "the seven Train years 2016-19 and 2022-24 (A15)",
     "now": "six seen years for a family born with a hidden year, each stretch of them a run starting flat (release E3)",
     "cost": "more zero-edge versions pass Train and take a Validation try; the screen's false-positive rate per program "
             "is unchanged (Train is in-sample)"},
    # THE OWNER'S CHANGE OF THE PINNED DONE RULE (A50, the goal of Oct 16, 2026, 02:10Z; docs/goals/DONE-RULE-A50.md,
    # `dlane.DONE`): four loosenings the owner chose, each with its cost as A50 states it, and the captain's A50a(2)
    # after them. Pinned before any checkpoint was reached (6 counted closes, none frozen). Every other rule of Done is
    # unchanged.
    {"rule": "Done's checkpoints (A50, the owner's goal of Oct 16)", "was": "the 30th counted close, then every 10th",
     "now": "the 15th counted close, then every 5th (20, 25, 30, ...), fixed by count, never chosen",
     "cost": "far fewer closes stand behind the sign, so the profit sign is mostly market direction, near a coin flip at "
             "zero edge; a reading every 5th close gives luck more chances (optional stopping)"},
    {"rule": "Done's bar (A50, the owner's goal of Oct 16)", "was": "at least 30 closes, at least 5 from each of at least "
                                                                   "2 programs",
     "now": "at least 15 closes, at least 3 from each of at least 2 programs (net above zero after fees, unchanged)",
     "cost": "A50 states none beyond the checkpoints' (above); plainly, a second program meets the bar on 3 closes and "
             "the sum on 15: less evidence that either program beat zero"},
    {"rule": "A14's intents bound (A50, the owner's goal of Oct 16)", "was": "the live and the shadow intents agree on "
                                                                           "at least 95% of the counted sessions",
     "now": "at least 95% of them, or all but one when fewer than 40 counted sessions are read (forward_db."
            "a14_intents_ok); the fill gap's 15 bp a side unchanged",
     "cost": "one bad session is forgiven at small S: under 20 sessions the 95% bound forgave none; from 20 to 39 the "
             "two bounds agree"},
    {"rule": "Done's research 24/7 window (A50, the owner's goal of Oct 16)",
     "was": "the 7 UTC days ending on the first checkpoint's day; every day since the previous one after it",
     "now": "the 3 UTC days ending on the first checkpoint's day (dlane.DONE research_first_days); every day since the "
            "previous checkpoint's after it",
     "cost": "A50 states none beyond the checkpoints' (above); plainly, research need be clean on 3 days, not 7, "
             "before the first claim: a stall earlier in its week no longer blocks it"},
    # THE CAPTAIN'S A50a(2) (02:31Z Oct 16, 2026; DONE-RULE-A50.md item 4, `dlane.DONE` `gap_min_matched`): A1.1's 5
    # would block the 15th close in about 92% of paths and contradict the owner's ">= 3 each".
    {"rule": "A1.1's matched replay closes (the captain's A50a(2), Oct 16)",
     "was": "at least 2 programs with 5 or more matched replay closes each, every one within the gap",
     "now": "at least 2 programs with 3 or more matched replay closes each, every one within the gap (dlane.DONE "
            "gap_min_matched 3)",
     "cost": "a program's replay gap is judged on 3 closes instead of 5; for ETF lots the +/-0.10 of max loss is far "
             "looser than A14's 15 bp, so the practical cost is small; a program with 3 or 4 matched closes is now "
             "judged, so it can also read inconsistent"},
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
    "DONE-RULE-A1 A1.1: a Done claim also needs 2 programs with 5+ matched replay closes each (3+ since the captain's "
    "A50a(2), a loosening listed with its cost), every one within the gap: zero replay evidence never passes (it did: "
    "B1)",
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
    "A14's fill gap is read as the size of the mean gap, either way (release E3): fills better than the official-price "
    "model by more than 15 bp a side also read not consistent",
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


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
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


def done_from() -> float:
    """Where the Done meters start counting (`DONE_FROM`, the goal of Oct 10, 2026) as epoch seconds: never before the
    rule's inception."""
    return max(inception(), float(_epoch(DONE_FROM)))


# ------------------------------------------------------------------------------------------------- the lanes
class Lanes:
    """Each family's declared lane (`dlane.declared_lane`: its spec's, else its card's), read once a family. An equity-lane
    family (its spec's `lane` one of `league.equity.LANES`, release E1) is in its own lane, "beta" or "equity"."""

    def __init__(self, store: Any):
        self.store = store
        self.cache: dict[str, str] = {}

    def of(self, fid: Any, fam: Mapping[str, Any] | None = None) -> str:
        from ..equity import LANES as EQUITY_LANES
        from ..swarm import dlane

        fid = str(fid or "")
        if fid not in self.cache:
            try:
                fam = fam if fam is not None else self.store.family(fid)
            except Exception:  # noqa: BLE001 - an unreadable family is alpha (the lane's default)
                fam = None
            spec = (fam or {}).get("spec") if isinstance(fam, Mapping) else None
            if isinstance(spec, Mapping) and spec.get("lane") in EQUITY_LANES:
                self.cache[fid] = str(spec["lane"])
            else:
                self.cache[fid] = dlane.declared_lane(self.store, fam) if fam is not None else dlane.ALPHA
        return self.cache[fid]


def every_family(store: Any) -> list[dict[str, Any]]:
    """Every living family of every lane: the swarm's lane filter (`SwarmStore.families(lanes="all")`, release E1) where
    the store has it, else `families(alive=True)`, which then holds every family already."""
    import inspect

    try:
        takes_lanes = "lanes" in inspect.signature(store.families).parameters
    except (TypeError, ValueError):
        takes_lanes = False
    return store.families(alive=True, lanes="all") if takes_lanes else store.families(alive=True)


def all_lanes() -> tuple[str, ...]:
    """The direction lane's two lanes and the equity lanes (release E1), each a key of the funnel and the bands."""
    from ..equity import LANES as EQUITY_LANES
    from ..swarm import dlane

    return (*dlane.LANES, *EQUITY_LANES)


def lane_label(lane: Any) -> str | None:
    """The label every figure of a lane carries: the direction lane's (`dlane.LABEL`), MARKET BETA or EQUITY
    (`elane.LABELS`); None for the alpha lane."""
    from ..swarm import dlane, elane

    if lane == dlane.DIRECTION:
        return dlane.LABEL
    return elane.LABELS.get(str(lane)) if lane else None


# ------------------------------------------------------------------------------------------------- the book
def read_book(live_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """The live book's positions and instances, and (release E1) the EquityBook's lots and instances (`lots`,
    `eq_instances`; empty for a book from before E1), and (release E5-A) its seat plan (`seat_plan`: the kv `eq_seat`,
    None before its first band sync), and (C1, A45) the span buy-and-hold's inputs (`bars`: the adjustment=all rows of
    `eq_bars` of SPY and of every symbol a closed lot of no panel program holds, each with its series sha;
    `open_note`: the kv `OPEN_NOTE_KEY`, {}
    when the book has written none, None when it cannot be read), read-only in one transaction; an absent book is an
    empty one: nothing traded."""
    from . import guard

    path = Path(live_path)
    if not path.exists():
        return {"positions": [], "instances": [], "lots": [], "eq_instances": [], "rebalances": [], "spy": [],
                "seat_plan": None, "bars": [], "open_note": {}}

    def read(db: Any) -> dict[str, list[dict[str, Any]]]:
        tables = set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'"))
        positions = guard.rows(db, "SELECT pid, instance, family, type, root, legs, qty, opened_qty, entry, max_loss_share, "
                                   "fees, cash, opened_at, opened_day, status, closed_at, tuition, info FROM positions "
                                   "ORDER BY pid") if "positions" in tables else []
        instances = guard.rows(db, "SELECT id, family, version, band, tuition, mode, created_at, retired_at FROM instances"
                               ) if "instances" in tables else []
        lots = guard.rows(db, "SELECT lid, instance, family, version, lane, symbol, class, qty, opened_qty, entry_px, "
                              "entry_notional, entry_at, fees, div, mark, opened_at, opened_day, status, exit_px, exit_at, "
                              "exit_day, closed_at, cash, reason, probe, tag, info FROM eq_lots ORDER BY lid"
                          ) if "eq_lots" in tables else []
        eq_instances = guard.rows(db, "SELECT id, family, version, lane, band, seeded, created_at, retired_at FROM "
                                      "eq_instances") if "eq_instances" in tables else []
        # RELEASE E4 (the panel lane; a book from before it has neither): each instance's decider kind, the panel
        # decisions' COUNTS and verdicts (never a target or a symbol of one), and SPY's adjustment=all closes as the
        # book fetched them (the same-risk buy-and-hold of a panel program).
        if eq_instances and guard.rows(db, "SELECT 1 FROM pragma_table_info('eq_instances') WHERE name='kind'"):
            kinds = {r["id"]: r["kind"] for r in guard.rows(db, "SELECT id, kind FROM eq_instances")}
            eq_instances = [{**r, "kind": kinds.get(r["id"])} for r in eq_instances]
        rebalances = guard.rows(db, "SELECT instance, decided_day, called, standing, status, audit, n_sells, n_buys, "
                                    "n_skipped FROM eq_rebalances ORDER BY decided_day, rid"
                                ) if "eq_rebalances" in tables else []
        spy = guard.rows(db, "SELECT day, c, sha FROM eq_bars WHERE symbol='SPY' AND adjustment='all' ORDER BY day"
                         ) if "eq_bars" in tables else []
        # THE SEAT PLAN (release E5-A): the book's own kv, read in the same transaction as its instances.
        plan = guard.ids(db, "SELECT value FROM kv WHERE key='eq_seat'") if "kv" in tables else []
        plan = _loads(plan[0], None) if plan else None
        # C1 (A45; `span_bh`): the closes of the span buy-and-hold as the book fetched them, and its open note: the
        # symbols of the closed lots that are no panel program's (B10 reads SPY alone, never a basket's names), and SPY.
        kinded = "eq_instances" in tables and bool(guard.rows(
            db, "SELECT 1 FROM pragma_table_info('eq_instances') WHERE name='kind'"))
        bars = guard.rows(db, "SELECT day, symbol, c, sha FROM eq_bars WHERE adjustment='all' AND (symbol=? OR "
                              "symbol IN (SELECT DISTINCT symbol FROM eq_lots WHERE status='closed' AND "
                              "COALESCE(tag, '')<>?"
                              + (" AND instance NOT IN (SELECT id FROM eq_instances WHERE kind=?)" if kinded else "")
                              + ")) ORDER BY symbol, day", ("SPY", PANEL_TAG, PANEL_KIND)[:3 if kinded else 2]
                          ) if "eq_bars" in tables and "eq_lots" in tables else []
        note = guard.ids(db, "SELECT value FROM kv WHERE key=?", (OPEN_NOTE_KEY,)) if "kv" in tables else []
        note = _loads(note[0], None) if note else {}
        return {"positions": positions, "instances": instances, "lots": lots, "eq_instances": eq_instances,
                "rebalances": rebalances, "spy": spy, "seat_plan": dict(plan) if isinstance(plan, Mapping) else None,
                "bars": bars, "open_note": dict(note) if isinstance(note, Mapping) else None}

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


def equity_closes(lots: Sequence[Mapping[str, Any]], *, since: float, seeded: Iterable[str] = ()
                  ) -> list[dict[str, Any]]:
    """EVERY EQUITY CLOSE since `since` (epoch), in close order: one EquityBook lot fully closed (`status` "closed"), as
    a close row the meters read like an options close (`closes`): {pid "eq:<lid>", lid, family, instance, version, route
    "d2_real" for a `:r` instance (else "agent_other": listed apart), code, house False, equity True, lane (the lot's),
    label, seeded, closed_at, day (its exit day), opened_day, opened_at, root (its symbol), symbol, class, type
    "equity_lot", entry_at, exit_at, max_loss_usd (its entry notional: a long lot loses at most what it paid),
    notional, fees_usd, div_usd, cash_usd, pnl_usd (its net cash, fees and dividends included; None when it cannot be
    read), return (net cash / notional), fee_basis ("broker" once the book marks the venue's fees posted, the lot's
    `info.fee_basis`; else "estimate"), fees_posted, probe, priced}."""
    seeded = set(seeded or ())
    out = []
    for lot in lots:
        closed_at = _num(lot.get("closed_at"))
        if str(lot.get("status") or "") != "closed" or closed_at is None or closed_at < since:
            continue
        try:
            lid = int(lot["lid"])
        except (KeyError, TypeError, ValueError):
            continue
        instance, family = str(lot.get("instance") or ""), str(lot.get("family") or "")
        real = instance.endswith(":r")
        cash, notional = _dec(lot.get("cash")), _dec(lot.get("entry_notional"))
        info = _loads(lot.get("info"), {}) or {}
        posted = isinstance(info, Mapping) and info.get("fee_basis") == "broker"
        priced = cash is not None and notional is not None and notional > 0
        lane = str(lot.get("lane") or "") or None
        panel = _is_panel_lot(lot)
        out.append({"pid": f"{EQUITY_PREFIX}{lid}", "lid": lid, "family": family, "instance": instance,
                    "version": version_of(instance) if version_of(instance) is not None else _int(lot.get("version")),
                    "route": "d2_real" if real else "agent_other", "code": ROUTE_CODES["d2_real"] if real else None,
                    "house": False, "equity": True, "lane": lane, "panel": panel,
                    "label": PANEL_LABEL if panel else lane_label(lane), "seeded": family in seeded,
                    "closed_at": closed_at, "day": str(lot.get("exit_day") or "") or _ny_day(closed_at),
                    "opened_day": str(lot.get("opened_day") or ""), "opened_at": _num(lot.get("opened_at")),
                    "root": str(lot.get("symbol") or "").upper(), "symbol": str(lot.get("symbol") or "").upper(),
                    "class": lot.get("class"), "type": "equity_lot", "legs": [], "entry": _num(lot.get("entry_px")),
                    "entry_at": lot.get("entry_at"), "exit_at": lot.get("exit_at"), "opened_qty": lot.get("opened_qty"),
                    "max_loss_usd": _usd(notional) if notional is not None else None, "notional": notional,
                    "fees_usd": _usd(_dec(lot.get("fees"))), "div_usd": _usd(_dec(lot.get("div"))),
                    "cash_usd": cash, "pnl_usd": cash if priced else None,
                    "return": round(float(cash / notional), 6) if priced else None,
                    "fee_basis": "broker" if posted else "estimate", "fees_posted": posted,
                    "probe": bool(int(lot.get("probe") or 0)), "priced": priced, "status": "closed"})
    out.sort(key=lambda c: (c["closed_at"], c["lid"]))
    return out


def seeded_families(store: Any, book: Mapping[str, Any]) -> set[str]:
    """The three programs the captain's build agents seeded (A4): the swarm store's kv `elane_seeds` ({seed id: family})
    and the book's `eq_instances` rows marked `seeded`. Empty when neither can be read."""
    from ..swarm import elane

    out: set[str] = set()
    try:
        seeds = store.get(elane.SEEDS_KEY) or {}
    except Exception:  # noqa: BLE001 - no record of seeds read: the book's mark alone
        seeds = {}
    if isinstance(seeds, Mapping):
        out.update(str(f) for f in seeds.values() if f)
    out.update(str(r.get("family")) for r in book.get("eq_instances") or [] if int(r.get("seeded") or 0) and r.get("family"))
    return out


def attach_equity(close: dict[str, Any], twin: Mapping[str, Any] | None, screens: "EquityScreens") -> dict[str, Any]:
    """An equity close with what rides beside it: its twin's verdict and gap, its same-risk buy-and-hold (`bh`, both of
    `_bh_sum`'s ways: a long lot is delta one), MTE (its net return less the buy-and-hold's) and its screen's line."""
    twin = dict(twin or {})
    bh = twin.get("bh") or {}
    usd, ret = _num(bh.get("usd")), _num(bh.get("return"))
    if usd is not None:
        why = None
    elif twin.get("status"):
        why = f"its twin is {twin['status']}: {twin.get('why') or 'no buy-and-hold'}"
    else:
        why = "no twin yet: its buy-and-hold comes with it (league/ops/twins.py, the equity_twins job)"
    close["bh"] = {"delta_usd": usd, "risk_usd": usd, "return": ret, "why": why}
    close["mte"] = round(close["return"] - ret, 6) if close.get("return") is not None and ret is not None else None
    close["twin"] = {k: twin.get(k) for k in ("status", "final", "gap_bp", "entry_slip_bp", "exit_slip_bp", "note")} \
        if twin else None
    close["fp"] = screens.of(close["family"], close.get("version"))
    return close


def _share_text(value: Decimal) -> str:
    """A share of E as the statement writes it: two decimals at least, four at most."""
    text = f"{value.quantize(Decimal('0.0001'))}"
    while len(text.split(".")[1]) > 2 and text.endswith("0"):
        text = text[:-1]
    return text


def equity_probe_note(constitution: Mapping[str, Any] | None = None) -> str:
    """A8.6's statement (`EQUITY_PROBE_SENTENCE`) with the figures of `constitution`'s rows (None: the one in force):
    the seats and the sleeve (`equity_money.probe.max_programs`, `sleeve_share`), the invested share, the ETF weight,
    the lane's most (the lower of the sleeves and the invested cap, at the weight), a one-ETF program's lot (the
    sleeve's own `position_share.etf`) and what the lane holds of the seats' lots (the lower of seats x lot and the
    invested cap), and the options table's window and total. `EQUITY_PROBE_BARE` when a row cannot be read."""
    if constitution is None:
        from ..constitution import CONSTITUTION as constitution  # noqa: N811
    em = (constitution or {}).get("equity_money") or {}
    em = em if isinstance(em, Mapping) else {}
    probe = em.get("probe") if isinstance(em.get("probe"), Mapping) else {}
    budget = ((constitution or {}).get("options_money") or {}).get("probe") or {}
    seats, sleeve = _int(probe.get("max_programs")), _dec(probe.get("sleeve_share"))
    cap, weight = _dec(em.get("invested_share")), _dec((em.get("open_risk_weight") or {}).get("etf"))
    etf = _dec((em.get("position_share") or {}).get("etf"))
    window, total = _dec(budget.get("loss_budget_usd")), _dec(budget.get("loss_total_usd"))
    if None in (seats, sleeve, cap, weight, etf, window, total):
        return EQUITY_PROBE_BARE
    lot = sleeve * etf
    one_held = min(Decimal(seats) * lot, cap)
    return EQUITY_PROBE_SENTENCE.format(
        window=f"{window:f}", total=f"{total:f}", seats=seats, sleeve=_share_text(sleeve), invested=_share_text(cap),
        weight=_share_text(weight), most=_share_text(min(Decimal(seats) * sleeve, cap) * weight), lot=_share_text(lot),
        one_held=_share_text(one_held), one_risk=_share_text(one_held * weight))


#: A8.6's statement at the constitution in force (the report's `equity.options_probe_room.statement`).
EQUITY_PROBE_NOTE = equity_probe_note()


def equity_panel_note(constitution: Mapping[str, Any] | None = None) -> str:
    """`EQUITY_PANEL_SENTENCE` with the figures of `constitution`'s rows (None: the one in force): the panel seats and
    sleeve (`equity_money.panel`), the ETF seats (`probe.max_programs`), a whole basket's open risk at the stock weight
    and the options table's window. `EQUITY_PANEL_BARE` when a row cannot be read."""
    if constitution is None:
        from ..constitution import CONSTITUTION as constitution  # noqa: N811
    em = (constitution or {}).get("equity_money") or {}
    em = em if isinstance(em, Mapping) else {}
    panel = em.get("panel") if isinstance(em.get("panel"), Mapping) else {}
    probe = em.get("probe") if isinstance(em.get("probe"), Mapping) else {}
    seats, sleeve = _int(panel.get("seats")), _dec(panel.get("sleeve_share"))
    etf_seats, weight = _int(probe.get("max_programs")), _dec((em.get("open_risk_weight") or {}).get("stock"))
    window = _dec((((constitution or {}).get("options_money") or {}).get("probe") or {}).get("loss_budget_usd"))
    if None in (seats, sleeve, etf_seats, weight, window):
        return EQUITY_PANEL_BARE
    return EQUITY_PANEL_SENTENCE.format(seats=seats, etf_seats=etf_seats, sleeve=_share_text(sleeve),
                                        risk=_share_text(sleeve * weight), weight=_share_text(weight),
                                        window=f"{window:f}")


#: The panel statement at the constitution in force.
EQUITY_PANEL_NOTE = equity_panel_note()


def options_probe_room(equity_usd: Any, constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A8.6 (`equity_probe_note`) in figures: the equity lane's open risk when it holds all it may, at the ETF weight
    `open_risk_weight.etf`, and what that leaves of the options Probe lane's window
    (`options_money.probe.loss_budget_usd`). What the lane may hold is the LOWER of every Probe sleeve invested
    (`equity_money.probe.max_programs` x `sleeve_share` x E) and THE INVESTED CAP (`invested_share` x E): where the
    sleeves ask for more than the cap (A20's three sleeves of 0.50 x E asked for 1.50 x E) the cap is the bound and
    the open risk is the cap's share at the weight, not the sleeves' (one-ETF programs, half a sleeve each, hold less:
    the figure here is the lane's most). `bound` names what set the figure: "sleeves",
    "invested_cap", or "budget" when that open risk in dollars would pass the window itself (every equity entry is cut
    to the budget's room, so the lane's open risk is never above it). A table with no `invested_share` row is read by
    its sleeves alone (the larger figure). E is the House's sizing equity (`dlane.unit_context`); the constitution's
    rows are read as they stand, the two numbers of release E5-S among them (no `equity_money` block: no figure)."""
    if constitution is None:
        from ..constitution import CONSTITUTION as constitution  # noqa: N811
    em = (constitution or {}).get("equity_money") or {}
    em = em if isinstance(em, Mapping) else {}
    budget = _dec((((constitution or {}).get("options_money") or {}).get("probe") or {}).get("loss_budget_usd"))
    probe = em.get("probe") or {}
    share, weight = _dec(probe.get("sleeve_share")), _dec((em.get("open_risk_weight") or {}).get("etf"))
    programs = _int(probe.get("max_programs"))
    cap = _dec(em.get("invested_share"))
    out: dict[str, Any] = {"statement": equity_probe_note(constitution), "window_budget_usd": _usd(budget),
                           "sleeve_share": None,
                           "max_programs": programs, "invested_share": None, "invested_share_of_e": None, "bound": None,
                           "etf_weight": None, "open_risk_share_of_e": None,
                           "sizing_equity_usd": _num(equity_usd), "equity_open_risk_usd": None,
                           "options_window_room_usd": None}
    if share is None or weight is None or programs is None or budget is None:
        out["why"] = "the constitution has no equity_money probe row yet: the statement stands without figures"
        return out
    sleeves = Decimal(programs) * share
    held = sleeves if cap is None or sleeves <= cap else cap
    risk = held * weight
    out.update(sleeve_share=str(share), etf_weight=str(weight), invested_share=None if cap is None else str(cap),
               invested_share_of_e=float(held), bound="sleeves" if held == sleeves else "invested_cap",
               open_risk_share_of_e=float(risk))
    e = _dec(equity_usd)
    if e is not None:
        dollars = risk * e
        if dollars > budget:
            dollars, out["bound"] = budget, "budget"
        out["equity_open_risk_usd"] = _usd(dollars)
        out["options_window_room_usd"] = _usd(max(Decimal(0), budget - dollars))
    else:
        out["why"] = "no sizing equity read: the share of E stands without dollars"
    return out


def equity_section(book: Mapping[str, Any], every: Sequence[Mapping[str, Any]], twins: Mapping[str, Mapping[str, Any]], *,
                   count_from: float, unit: Mapping[str, Any], seeded: Iterable[str], screens: "EquityScreens",
                   root: str | Path | None = None) -> dict[str, Any]:
    """THE EQUITY LANES in the report (release E1): every equity close with its label, seeded mark, buy-and-hold, MTE,
    twin and screen line, and whether it counts (`count_from`); the lots open now by lane; the twins' verdicts and each
    program's mean gap a side; the seeded programs; profit from market direction; A8.6's options Probe room; and
    (release E5-A) THE SEATS (`equity_seats`: who holds each, which the seeds hold, who waits and in what order)."""
    seeded = set(seeded or ())
    from ..swarm import elane

    rows = [c for c in every if c.get("equity")]
    lots = list(book.get("lots") or [])
    open_lots = [lot for lot in lots if str(lot.get("status") or "") in ("open", "closing")]
    by_lane: dict[str, int] = {}
    for lot in open_lots:
        by_lane[str(lot.get("lane") or "")] = by_lane.get(str(lot.get("lane") or ""), 0) + 1
    statuses: dict[str, int] = {}
    gaps: dict[str, list[float]] = {}
    for c in rows:
        rec = twins.get(c["pid"]) or {}
        status = str(rec.get("status") or "none") if rec.get("final") is True else "pending"
        statuses[status] = statuses.get(status, 0) + 1
        if status == "priced" and _num(rec.get("gap_bp")) is not None:
            gaps.setdefault(c["family"], []).append(float(rec["gap_bp"]))
    return {
        "labels": dict(elane.LABELS), "beta_note": elane.BETA_NOTE, "direction": EQUITY_DIRECTION,
        "counted_from": _iso(count_from),
        "closes": [{"pid": c["pid"], "family": c["family"], "version": c.get("version"), "lane": c.get("lane"),
                    "label": c.get("label"), "seeded": bool(c.get("seeded")), "counted": c["closed_at"] >= count_from,
                    "route": c.get("code") or c["route"], "symbol": c.get("symbol"), "class": c.get("class"),
                    "entry_at": c.get("entry_at"), "exit_at": c.get("exit_at"), "opened_day": c.get("opened_day"),
                    "day": c.get("day"), "closed_at": _iso(c["closed_at"]), "notional_usd": c.get("max_loss_usd"),
                    "pnl_usd": _usd(c.get("pnl_usd")), "return": c.get("return"), "fees_usd": c.get("fees_usd"),
                    "div_usd": c.get("div_usd"), "fee_basis": c.get("fee_basis"), "probe": c.get("probe"),
                    "bh": c.get("bh"), "mte": c.get("mte"), "twin": c.get("twin"), "fp": c.get("fp")} for c in rows],
        "open_lots": len(open_lots), "open_by_lane": dict(sorted(by_lane.items())),
        "twins": {"by_status": dict(sorted(statuses.items())),
                  "mean_gap_bp": {f: round(statistics.fmean(v), 2) for f, v in sorted(gaps.items())},
                  "basis": "live net return less the twin's, basis points a side (league/ops/twins.py equity_twin); "
                           "EDM1 demotes past 15 bp a side over 5 priced closes"},
        "seeded": sorted(seeded), "seeded_note": elane.SEEDED_NOTE,
        "options_probe_room": options_probe_room((unit or {}).get("equity_usd")),
        "seats": equity_seats(root, book, seeded),
        # RELEASE E4: the panel lane's own lines (None while no panel program exists).
        "panel": panel_section(book, twins, screens, unit=unit),
    }


def equity_seats(root: str | Path | None, book: Mapping[str, Any], seeded: Iterable[str]) -> dict[str, Any]:
    """THE SEATS (release E5-A; A24, `SEAT_RULE`): the EquityBook's own seat plan as it last wrote it (`book`'s
    `seat_plan`: the book is the one source), for the owner: {rule, seats, as_of (the decision day of the plan), holders
    [{family, version, band, seeded, since, seated_sessions, quiet_sessions, left_out, flat, idle}], seeded_seats (the
    holders the captain's build agents seeded) and `seeded_statement` (said in every report), waiting [{family, rank,
    seeded, flagged}] in the plan's order (a rank POSITION, never K), idle_flagged, left_out ([{day, why}]: the
    sessions in which the House refused every open, left out of the idle clock: A30), last_change, order,
    preregistered}. Under
    "first-come" the book ranks nobody: `waiting` is the swarm's roster by pass time (`bands.roster(root, lanes=LANES)`),
    and `order` says so. Before the book's first plan the holders are its live instances and `why` says so. Never
    raises: what cannot be read is None with a `why`."""
    seeded = set(seeded or ())
    plan = book.get("seat_plan") if isinstance(book.get("seat_plan"), Mapping) else None
    out: dict[str, Any] = {"rule": None, "seats": None, "as_of": None, "holders": [], "seeded_seats": [],
                           "seeded_statement": None, "waiting": None, "idle_flagged": [], "left_out": [],
                           "last_change": None, "order": None, "why": None, "preregistered": dict(SEAT_RULE)}
    if plan is None:
        holders = [{"family": str(r.get("family")), "version": _int(r.get("version")), "band": r.get("band"),
                    "seeded": bool(int(r.get("seeded") or 0)) or str(r.get("family")) in seeded}
                   for r in book.get("eq_instances") or [] if r.get("retired_at") is None and r.get("band") in ("probe", "sized")]
        out["why"] = "the book has written no seat plan yet: the holders are its live instances"
    else:
        holders = [{**dict(h), "seeded": bool(h.get("seeded")) or str(h.get("family")) in seeded}
                   for h in plan.get("holders") or [] if isinstance(h, Mapping)]
        out.update(rule=plan.get("rule"), seats=_int(plan.get("seats")), as_of=plan.get("day"), order=plan.get("order"),
                   idle_flagged=sorted(str(f) for f in (plan.get("idle") or {})) if isinstance(plan.get("idle"), Mapping) else [],
                   left_out=[{"day": str(x.get("day")), "why": str(x.get("why") or "")[:240]}
                             for x in plan.get("left_out") or [] if isinstance(x, Mapping)]
                   if isinstance(plan.get("left_out"), list) else [],
                   last_change=dict(plan["last"]) if isinstance(plan.get("last"), Mapping) else None)
        if plan.get("held_seats"):
            # THE EVENT HOLD (release 1023a): ETF programs that keep a seat with no row (opens stopped, exits on,
            # nobody seated into it); said beside the holders, which name only the programs with a row.
            out["held_seats"] = sorted(str(f) for f in plan.get("held_seats") or [])
        if isinstance(plan.get("waiting"), list):
            out["waiting"] = [{"family": str(w.get("family")), "rank": _int(w.get("rank")),
                               "seeded": bool(w.get("seeded")) or str(w.get("family")) in seeded,
                               "flagged": bool(w.get("flagged"))} for w in plan["waiting"] if isinstance(w, Mapping)]
    if out["waiting"] is None and root is not None:
        # "first-come" (or no plan yet): the swarm's roster orders the waiting, by pass time.
        try:
            from ..equity import LANES
            from ..swarm import bands

            roster = bands.roster(root, lanes=LANES)
        except Exception:  # noqa: BLE001 - a roster that cannot be read is no list, said so
            roster = None
        if roster is not None:
            out["waiting"] = [{"family": str(f), "rank": None, "seeded": str(f) in seeded, "flagged": False}
                              for f in roster.get("waiting") or []]
            out["order"] = out["order"] or "by pass time: the swarm's roster"
            out["seats"] = out["seats"] if out["seats"] is not None else _int(roster.get("seats"))
    out["holders"] = sorted(holders, key=lambda h: (str(h.get("since") or ""), str(h.get("family"))))
    out["seeded_seats"] = sorted(str(h["family"]) for h in holders if h.get("seeded"))
    pool = plan.get("panel") if isinstance(plan, Mapping) else None
    if isinstance(pool, Mapping):
        # THE PANEL POOL (release E4 step two): the book's own plan of the panel seats, with its statement. Rank
        # positions only, as the ETF pool's; `held_seats`: panel programs holding a seat while a leg of their lane
        # fails (opens stopped, exits on, nobody seated into it).
        out["panel"] = {
            "statement": EQUITY_PANEL_NOTE, "rule": pool.get("rule"), "seats": _int(pool.get("seats")),
            "as_of": pool.get("day"),
            "holders": sorted(({"family": str(h.get("family")), "version": _int(h.get("version")),
                                "band": h.get("band"), "since": h.get("since"),
                                "seated_sessions": _int(h.get("seated_sessions")), "idle": bool(h.get("idle"))}
                               for h in pool.get("holders") or [] if isinstance(h, Mapping)),
                              key=lambda h: (str(h["since"] or ""), h["family"])),
            "waiting": [{"family": str(w.get("family")), "rank": _int(w.get("rank"))}
                        for w in pool.get("waiting") or [] if isinstance(w, Mapping)]
            if isinstance(pool.get("waiting"), list) else None,
            "held_seats": sorted(str(f) for f in pool.get("held_seats") or [])}
    held, of = len(holders), out["seats"]
    names = ", ".join(out["seeded_seats"])
    out["seeded_statement"] = (
        f"{held} of {of if of is not None else 'the'} seats are held; programs seeded by the captain's build agents hold "
        f"{len(out['seeded_seats'])} of them" + (f": {names}" if names else "") + ". Seeded and bred programs follow the "
        "same seat rule.")
    return out


# ------------------------------------------------------------------------------------------------- the panel lane
def _panel_instances(book: Mapping[str, Any]) -> set[str]:
    return {str(r.get("id")) for r in book.get("eq_instances") or [] if str(r.get("kind") or "") == PANEL_KIND}


def _is_panel_lot(lot: Mapping[str, Any], instances: Iterable[str] = ()) -> bool:
    """Whether an `eq_lots` row is a panel program's: its instance is of the panel kind, or its buy carried the panel
    decision's tag (league/xs/book.py `TAG`: a lot keeps its intent's tag)."""
    return str(lot.get("tag") or "") == PANEL_TAG or str(lot.get("instance") or "") in set(instances)


def _look_records(look: Any) -> list[Mapping[str, Any]]:
    """A family state's recorded look as rows: the record itself, or one a version when it is kept by version."""
    if not isinstance(look, Mapping):
        return []
    if "passed" in look or "seat" in look:
        return [look]
    return [{**v, "version": v.get("version", k)} for k, v in look.items() if isinstance(v, Mapping)]


def style_open_passers(store: Any) -> list[dict[str, Any]]:
    """THE CAPTAIN'S A22 (1), reported: every panel program that PASSED its XS1 look and holds no seat because the
    House reads it style-open (the look's record says `seat` "style-open": league/swarm/elane_xs.py `look`), each with
    why (`league.xs.style.seat_refusal` of its Train record's style verdict, `elane_xs.style_of`; the look's own word
    when the rule cannot be read here). Read-only; an unreadable store or lane is an empty list."""
    try:
        from ..swarm import elane_xs
    except Exception:  # noqa: BLE001 - no panel lane in this tree: nobody passed
        return []
    out = []
    try:
        families = every_family(store)
    except Exception:  # noqa: BLE001
        return []
    for fam in families:
        if not isinstance(fam, Mapping) or str(fam.get("structure") or "") != PANEL_KIND:
            continue
        for rec in _look_records((fam.get("state") or {}).get(elane_xs.LOOK_KEY)):
            if not rec.get("passed") or rec.get("seat") != elane_xs.SEAT_STYLE:
                continue
            why = None
            try:
                from ..xs import style

                why = style.seat_refusal(elane_xs.style_of(fam, _int(rec.get("version"))))
            except Exception:  # noqa: BLE001 - the look's own word stands
                why = None
            out.append({"family": str(fam.get("id")), "version": _int(rec.get("version")), "passed": True, "seat": None,
                        "why": str(why or rec.get("why") or rec.get("seat_why") or "style-open"),
                        "look_at": rec.get("at"), "shadow": PANEL_SHADOWED})
    return sorted(out, key=lambda r: (r["family"], r["version"] or 0))


def _one_basis(rows: Sequence[Mapping[str, Any]]) -> dict[str, Decimal] | None:
    """{day: SPY's adjustment=all close} from the book's `eq_bars` rows of ONE fetch (the latest day's series `sha`:
    two fetches straddling an ex-date are not one series); None when there is none."""
    rows = [r for r in rows if r.get("day") and r.get("sha")]
    if not rows:
        return None
    sha = max(rows, key=lambda r: str(r["day"]))["sha"]
    out = {str(r["day"]): _dec(r.get("c")) for r in rows if r["sha"] == sha}
    return {d: c for d, c in out.items() if c is not None and c > 0} or None


def panel_lane(root: Any, settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """THE PANEL LANE'S OWN STATE in the report (release E4; the review's spec-6), while its switch is up: {"panel_lane":
    {"setting", "mode", "why", "roster"}}: `elane.panel.mode` as set, the EFFECTIVE mode and the leg that holds it
    under the setting (`league.swarm.elane_xs.status`: the reason reached no status, so a lane a leg had stopped said
    so nowhere), and the equity roster with why each seatless Candidate holds no seat (`bands.roster(...,
    lanes=LANES)`). {} with the switch off (nothing of E4 is read). Never raises."""
    try:
        from ..equity import LANES
        from ..swarm import bands, elane_xs

        if elane_xs.cfg(settings)["mode"] == "off":
            return {}
        said = elane_xs.status(settings, root)
        try:
            roster = bands.roster(root, lanes=LANES)
        except Exception:  # noqa: BLE001 - the roster is words beside
            roster = None
        return {"panel_lane": {**said, "roster": roster}}
    except Exception as exc:  # noqa: BLE001 - a report never fails on a status
        return {"panel_lane": {"error": type(exc).__name__}}


def panel_forward(out: dict[str, Any], root: Any) -> None:
    """WHAT THE FORWARD RECORD SAYS BESIDE A LIVE PANEL PROGRAM (release E4, package J; never a rule): for each program
    of `out["equity"]["panel"]`, `residual_x` (its shadow twin's residual over the instance's own sessions: the Gym
    sleeve and the model's costs, said in `of`) and `rebalance_sessions_agreed` (its REBALANCE sessions agreed k of n,
    with the days that differ), from league/ops/forward_xs.py `beside`; `owed` is then None. A program the forward
    record holds nothing of keeps `PANEL_OWED`; a record that cannot be read says so in `owed` (never a figure)."""
    panel = (out.get("equity") or {}).get("panel") if isinstance(out.get("equity"), Mapping) else None
    programs = panel.get("programs") if isinstance(panel, Mapping) else None
    if not isinstance(programs, Mapping) or not programs:
        return
    try:
        from . import forward_xs

        found = forward_xs.beside(root)
    except Exception as exc:  # noqa: BLE001 - unread is said, never a zero
        for row in programs.values():
            row["owed"] = f"the forward record could not be read ({type(exc).__name__}): {PANEL_OWED}"
        return
    for key, row in programs.items():
        mine = found.get(key)
        if not isinstance(mine, Mapping):
            continue
        if mine.get("residual") is None and not (mine.get("rebalance") or {}).get("sessions"):
            continue    # the record names the instance and holds no figure of it yet
        row.update(residual_x=mine.get("residual"), rebalance_sessions_agreed=mine.get("rebalance"), owed=None)


def panel_section(book: Mapping[str, Any], twins: Mapping[str, Mapping[str, Any]], screens: "EquityScreens", *,
                  unit: Mapping[str, Any] | None = None, constitution: Mapping[str, Any] | None = None
                  ) -> dict[str, Any] | None:
    """THE PANEL LANE in the report (release E4; E4-SPEC 10.5 and 10.6, the captain's A14 and A22): None while no
    panel program has a lot, an instance or a recorded style-open pass. Else, under the label `PANEL_LABEL`:
    - `programs`: per live or traded panel instance: its lots open and closed, THE DISTINCT CLOSE DATES and THE
      DATE-CLUSTERED t beside them (A14: `league.xs.book.date_record`, `date_t`: one observation a close date, as the
      book's band rules read it), its net P&L, the same-risk buy-and-hold IN SPY over its lots' own sessions on one
      basis (`bh_spy_usd`; None with `bh_why` while the book holds no single SPY series over them), XS1's sentence
      (`xs1`: the line its look recorded, stated beside EVERY live panel trade), its decisions by status and their
      morning re-reads by verdict (`audits`: "none" counts the decisions recorded after 08:30, which have none), and
      10.5's cost sentence (`cost`);
    - `residual_x` and `rebalance_sessions_agreed`: its residual against its matched cells and its twin's agreement on
      rebalance sessions are the forward record's: None here, with `PANEL_OWED` said, until `panel_forward` has put
      that record's own lines beside the program;
    - `style_open`: every recorded style-open passer and why it holds no seat (`style_open_passers`), under A22's rule.
    Never a rule: nothing here is read by a band, a seat or the Done meter."""
    instances = _panel_instances(book)
    lots = [lot for lot in book.get("lots") or [] if _is_panel_lot(lot, instances)]
    passers = style_open_passers(screens.store)
    keys = sorted(instances | {str(lot.get("instance") or "") for lot in lots})
    if not keys and not passers:
        return None
    if constitution is None:
        from ..constitution import CONSTITUTION as constitution  # noqa: N811
    em = (constitution or {}).get("equity_money") or {}
    demotion = em.get("demotion") or {} if isinstance(em, Mapping) else {}
    share = _dec(((em.get("probe") or {}) if isinstance(em, Mapping) else {}).get("sleeve_share"))
    e = _dec((unit or {}).get("equity_usd"))
    sleeve = share * e if share is not None and e is not None else None
    try:
        from ..xs import book as xs_book
    except Exception as exc:  # noqa: BLE001 - a laptop without numpy: the lane's figures are not read, and it is said
        xs_book, unread = None, f"the panel adapter cannot be imported here ({type(exc).__name__}): figures not read"
    else:
        unread = None
    spy = _one_basis(book.get("spy") or [])
    by_instance: dict[str, dict[str, dict[str, int]]] = {}
    for r in book.get("rebalances") or []:
        slot = by_instance.setdefault(str(r.get("instance")), {"decisions": {}, "audits": {}})
        status = str(r.get("status") or "none")
        slot["decisions"][status] = slot["decisions"].get(status, 0) + 1
        if r.get("status") != "failed":
            audit = str(r.get("audit") or "none")
            slot["audits"][audit] = slot["audits"].get(audit, 0) + 1
    programs = {}
    for key in keys:
        mine = [lot for lot in lots if str(lot.get("instance") or "") == key]
        family = str(mine[0].get("family") if mine else key.split("@", 1)[0])
        version = version_of(key)
        row: dict[str, Any] = {
            "family": family, "version": version, "label": PANEL_LABEL,
            "open_lots": sum(1 for lot in mine if str(lot.get("status") or "") in ("open", "closing")),
            "closed_lots": sum(1 for lot in mine if str(lot.get("status") or "") == "closed"),
            "close_dates": None, "date_t": None, "pnl_usd": None, "bh_spy_usd": None, "bh_why": None,
            "residual_x": None, "rebalance_sessions_agreed": None, "owed": PANEL_OWED,
            "xs1": screens.of(family, version),
            "decisions": dict(sorted((by_instance.get(key) or {}).get("decisions", {}).items())),
            "audits": dict(sorted((by_instance.get(key) or {}).get("audits", {}).items())), "cost": None}
        if xs_book is None:
            row["why"] = unread
        else:
            rec = xs_book.date_record(mine, twins, spy)
            t = xs_book.date_t(rec["returns"])
            row.update(close_dates=rec["n"], date_t=None if t is None else round(t, 4), pnl_usd=_usd(rec["pnl"]),
                       bh_spy_usd=_usd(rec["bh_pnl"]) if rec["bh_pnl"] is not None else None,
                       bh_why=None if rec["bh_pnl"] is not None else
                       "the book holds no single SPY series over its lots' sessions yet (the band sync reads one once "
                       "sizing up needs it: 10.5)",
                       cost=xs_book.cost_sentence(min_dates=demotion.get("min_trades", 10),
                                                  loss_usd=demotion.get("program_loss_usd", "-300"), sleeve_usd=sleeve))
        programs[key] = row
    return {"label": PANEL_LABEL, "rule": PANEL_BY_DATE, "programs": programs, "style_open": passers,
            "style_open_rule": STYLE_OPEN_RULE, "owed": PANEL_OWED}


def equity_yield(store: Any, settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """RELEASE E2: the equity lanes' model routes (league/swarm/elane_yield.py `report`): births, Train passes, Validation
    entries, looks passed and live programs per route, each per dollar, and the equity review's own rows. The operator's
    alone: never shown to an agent (A9 D3). An error is named, never raised."""
    from ..swarm import elane_train, elane_yield

    try:
        return elane_yield.report(store, settings, train_key=elane_train.STATE_KEY)
    except Exception as exc:  # noqa: BLE001 - the report goes on without it
        return {"error": type(exc).__name__}


def a14_of(store: Any, counted: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """RELEASE E3, amendment A14 (league/ops/forward_twins.py `a14_reading`): over a checkpoint's counted closes, the size
    of the mean fill gap against the official-price model within 15 bp a side AND live and shadow intents agreeing on
    95% of the counted sessions. With no equity close it does not apply (holds); unreadable, unmeasured or misshapen, it
    does not hold. Never raises, and always carries applies, holds, final and why."""
    # THE SHADOW INTENTS ARE A RE-BASED TWIN'S (the captain's A29, registered before the first real share order): a
    # session that differs is counted, as registered, then the twin's book is set to the live book, so a miss counts
    # once; the bounds are as registered. The reading's `rebase` says, beside and in no rule, how many times each
    # instance's twin was re-based and the un-re-based twin's own agreement over the same sessions.
    if not any(c.get("equity") for c in counted):
        return {"applies": False, "holds": True, "final": True, "why": None}
    try:
        from . import forward_twins
        r = forward_twins.a14_reading(Path(store.root), counted)
        return {**r, "applies": r.get("applies") is not False, "holds": r.get("holds") is True,
                "final": r.get("final") is True, "why": r.get("why")}  # a non-dict raises into the except
    except Exception as exc:  # noqa: BLE001 - unread is not held
        return {"applies": True, "holds": False, "final": False, "why": f"A14 could not be read ({type(exc).__name__})"}


def _order(close: Mapping[str, Any]) -> tuple:
    """Close order across both books: the close time, then an options close before an equity close, then its id."""
    pid = close["pid"]
    return (close["closed_at"], isinstance(pid, str), pid if not isinstance(pid, str) else int(pid[len(EQUITY_PREFIX):]))


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
    out = {"delta_matched_usd": round(sum(d), 2) if d else None, "delta_priced": len(d),
           "dollars_at_risk_usd": round(sum(k), 2) if k else None, "risk_priced": len(k), "closes": len(rows),
           "basis": "approximation: daily closes of the direction job; delta from Black-Scholes at one implied "
                    "volatility solved from the entry value, the entry day's close as the spot"}
    if any(r.get("equity") for r in rows):
        # An equity lot is delta one: both ways are its notional held in its own symbol over its own sessions.
        from .twins import EQUITY_BH_BASIS

        out["equity_basis"] = EQUITY_BH_BASIS
    return out


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
        if status in FINAL or (rec or {}).get("final") is True:
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


def _close_day(c: Mapping[str, Any]) -> str:
    """A close's New York day: its `day`, else the day of its `closed_at`."""
    return str(c.get("day") or "") or _ny_day(_num(c.get("closed_at")))


def done_counts(counted: Sequence[Mapping[str, Any]]) -> list[int]:
    """DONE COUNTS A PANEL PROGRAM'S CLOSES BY DATE (release E4 step two; the review of step two found a basket's lots
    counted one close each, so one rotation of a 0.10 x E basket added 8 to 12 closes of one date and one market move,
    worth cents, pulled the 30th close and every later checkpoint earlier and could meet a second program's "at least
    5" alone). For each close of `counted` (in close order) the number of the Done count it is part of, from 1: every
    close is one count, as before, EXCEPT A PANEL PROGRAM'S (`panel`): its lots closed on one New York day are ONE
    count, placed where the first of them closed. The checkpoints (the 15th count, then every 5th, since the owner's
    A50; the 30th, then every 10th, before) and the per-program 3 (5 before A50) read these counts; the lots stand
    beside (`lots`). A TIGHTENING (fewer counts, never more), until the owner rules otherwise; an ETF or options close
    is counted exactly as before."""
    seen: dict[tuple[str, ...], int] = {}
    out: list[int] = []
    for c in counted:
        key = ("panel", str(c.get("family") or ""), _close_day(c)) if c.get("panel") else ("close", str(c.get("pid")))
        if key not in seen:
            seen[key] = len(seen) + 1
        out.append(seen[key])
    return out


def first_counts(counted: Sequence[Mapping[str, Any]], k: int,
                 counts: Sequence[int] | None = None) -> list[Mapping[str, Any]]:
    """The closes of Done's first `k` counts (`done_counts`), in close order: a panel count's later lots of its day go
    with it. With no panel close it is `counted[:k]`."""
    counts = done_counts(counted) if counts is None else counts
    return [c for c, n in zip(counted, counts) if n <= k]


def reading(counted: Sequence[Mapping[str, Any]], store: Any, *, nightly_cache: dict[str, list] | None = None,
            done: Mapping[str, Any] | None = None, lanes: Lanes | None = None,
            twins: Mapping[str, Mapping[str, Any]] | None = None,
            a14: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The Done rule over exactly `counted` (the meter's closes, in close order): {closes, programs, net_usd, net_known,
    estimate_closes, unpriced, per_program_ok, consistent_ok, holds, why, by_route, by_program, bh}. `a14` (release E3):
    the forward record's A14 reading of exactly these closes (`a14_of`), handed in by the meter at a checkpoint, which
    holds item 4 to it there; with none, a reading that holds an equity close is not read (the running figures)."""
    from ..swarm import dlane

    rule = dict(done or dlane.DONE)
    cache = nightly_cache if nightly_cache is not None else {}
    # THE DONE COUNT (release E4 step two, `done_counts`): `closes`, the reading's and each program's, are Done's
    # counts (a close each, a panel program's lots of one date one), with `lots` beside them where the two differ;
    # `by_route` counts lots.
    n_counts = max(done_counts(counted), default=0)
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
        # An equity program's lane is its lots' (the book's own row), whatever the swarm store still holds.
        lane = rows[0].get("lane") if rows[0].get("equity") else lanes.of(fid) if lanes is not None else rows[0].get("lane")
        counts = max(done_counts(rows), default=0)
        row = {"family": fid, "lane": lane, "closes": counts, "routes": routes,
               "net_usd": _usd(sum(known, Decimal(0))) if len(known) == len(rows) else None,
               "replay": gap, "bh": _bh_sum(rows), **({"lots": len(rows)} if counts != len(rows) else {})}
        if lane == dlane.DIRECTION:
            row["label"] = dlane.LABEL
        elif rows[0].get("equity"):
            row.update(label=lane_label(lane), seeded=bool(rows[0].get("seeded")))
        programs.append(row)
    enough = [p for p in programs if p["closes"] >= int(rule["min_closes_per_program"])]
    per_program_ok = len(enough) >= int(rule["min_programs"])
    # CONSISTENCY MUST BE MEASURED (DONE-RULE-A1 A1.1, pinned Oct 9, 2026; the readiness audit's B1): item 4 alone held
    # with ZERO replay evidence, since a program under 5 matched closes is never inconsistent. Now a reading also needs
    # `min_measured_programs` (2) programs with `gap_min_matched` (3 since the captain's A50a(2), Oct 16, 2026; 5
    # before) or more matched closes and a gap measured, and every such program within the gap. Zero matched closes never passes; every program is listed with its closes, matched
    # closes and gap (`by_program`).
    min_matched = int(rule["gap_min_matched"])
    need_measured = int(rule.get("min_measured_programs", dlane.DONE["min_measured_programs"]))
    measured = [p for p in programs if p["replay"]["matched"] >= min_matched and p["replay"]["gap"] is not None]
    inconsistent = [p["family"] for p in measured if p["replay"]["consistent"] is False]
    measured_ok = len(measured) >= need_measured
    matched_total = sum(int(p["replay"]["matched"]) for p in programs)
    net_known = unpriced == 0
    whys = []
    if n_counts < int(rule["min_closes"]):
        whys.append(f"{n_counts} closes of the {int(rule['min_closes'])} needed")
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
    item3 = n_counts >= int(rule["min_closes"]) and per_program_ok and net_known and net > 0
    item4 = measured_ok and not inconsistent
    # A14 (pre-registered before the first equity close): a reading that holds an equity close reads "consistent with
    # replay" by A14's own measure, never by the gap above alone (a long lot's maximum loss is its notional, so the
    # options bound of 0.10 is a thousand basis points of it). A fill gap past the bound fails item 4. RELEASE E3
    # landed the intents half's reader: a checkpoint's reading is handed its A14 by the meter (`a14`), which holds
    # item 4, the reading and its `why` to it there; a reading handed none is not read and never True.
    read = isinstance(a14, Mapping)
    a14 = a14_consistency(counted, a14 if read else None)
    if a14 is not None and not read:
        whys.append(a14["why"])
        item4 = False
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
    return {"closes": n_counts, **({"lots": len(counted)} if n_counts != len(counted) else {}),
            "programs": len(programs), "programs_with_min_closes": len(enough),
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
            "by_program": programs, "bh": _bh_sum(counted), "equity": equity_beside(counted),
            **({"a14": a14} if a14 is not None else {})}


def a14_consistency(counted: Sequence[Mapping[str, Any]], forward: Mapping[str, Any] | None = None
                    ) -> dict[str, Any] | None:
    """A14's READING OF "CONSISTENT WITH REPLAY" over a reading's EQUITY closes (`A14_CONSISTENCY`), or None when it
    holds none. {closes, priced, unpriced, mean_gap_bp, bound_bp, fill_gap_ok, intents {agreement, bound, status},
    consistent, why}. WITH `forward` (release E3: the forward record's reading of these closes, `a14_of`) BOTH HALVES
    ARE READ: the answer is that reading (applies, holds, final, why, gap, intents, by_instance) with the fill-gap half
    of these rows beside it, `consistent` and `holds` True only when it holds AND the rows' own mean gap is not past
    the bound (two readings of one gap: either saying no is no), and a `why` when they are not. Without it:
    - THE FILL GAP (computed): the mean of `gap_bp` over the counted equity closes whose twin is final and priced
      (league/ops/twins.py `equity_twin`: the live net return less the official-price model's, basis points a side,
      negative when the fills were worse); `fill_gap_ok` is |mean| <= `A14_GAP_BP`, None while no close is priced. Every
      close with no final priced twin is counted in `unpriced`, never dropped silently.
    - THE INTENTS (not read here): the live and the shadow intents agreeing on at least `A14_AGREEMENT` of the
      counted sessions are read at a Done checkpoint, by the forward record's twins (release E3).
      Since the owner's change (A50) all but one of them also passes when fewer than `A14_ALL_BUT_ONE_UNDER` are read.
    - `consistent`: False when the fill gap is past its bound; else None (NOT READ: a half is missing). Never True
      until both halves are read, so `reading` never holds item 4 on equity closes by the options measure."""
    rows = [c for c in counted if c.get("equity")]
    if not rows:
        return None
    gaps = []
    for c in rows:
        twin = c.get("twin") if isinstance(c.get("twin"), Mapping) else {}
        gap = _num(twin.get("gap_bp"))
        if twin.get("final") is True and twin.get("status") == "priced" and gap is not None:
            gaps.append(gap)
    mean = statistics.fmean(gaps) if gaps else None
    fill_ok = None if mean is None else abs(mean) <= A14_GAP_BP
    intents = {"agreement": None, "bound": A14_AGREEMENT, "all_but_one_under": A14_ALL_BUT_ONE_UNDER,
               "status": "not read here: the live and the shadow intents are read at a Done checkpoint (A14's second "
                         "half; release E3)"}
    if fill_ok is False:
        why = (f"not consistent (A14): the mean fill gap is {mean:.1f} bp a side over {len(gaps)} priced equity closes, "
               f"past the {A14_GAP_BP:g} bp bound")
    else:
        measured = (f"the mean fill gap is {mean:.1f} bp a side over {len(gaps)} of {len(rows)} equity closes, inside "
                    f"the {A14_GAP_BP:g} bp bound" if mean is not None else
                    f"no equity close of {len(rows)} has a final priced twin yet")
        why = (f"item 4 is not read for a reading with equity closes outside a Done checkpoint: {measured}; the "
               "intents-agreement half is read at each checkpoint (release E3)")
    if isinstance(forward, Mapping):  # RELEASE E3 (`a14_of`): both halves, the rows' own fill-gap half beside them
        held = forward.get("holds") is True and fill_ok is not False
        if held:
            why = None
        elif fill_ok is not False:
            why = "; ".join(w for w in (None if mean is not None else f"no equity close of {len(rows)} has a final "
                                                                      "priced twin yet",
                                        str(forward.get("why") or "not held")) if w)
        return {**forward, "closes": len(rows), "priced": len(gaps), "unpriced": len(rows) - len(gaps),
                "mean_gap_bp": None if mean is None else round(mean, 2), "bound_bp": A14_GAP_BP, "fill_gap_ok": fill_ok,
                "consistent": held, "applies": True, "holds": held, "final": forward.get("final") is True, "why": why}
    return {"closes": len(rows), "priced": len(gaps), "unpriced": len(rows) - len(gaps),
            "mean_gap_bp": None if mean is None else round(mean, 2), "bound_bp": A14_GAP_BP, "fill_gap_ok": fill_ok,
            "intents": intents, "consistent": False if fill_ok is False else None, "why": why}


def equity_beside(counted: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """WHAT RIDES BESIDE A READING'S EQUITY CLOSES (release E1; the design's 6d): per lane its label, closes, net, the
    same-risk buy-and-hold summed over the priced ones and the mean MTE (each close's net return less its buy-and-hold's);
    per program its label, whether it was seeded and the screen's false-positive line recorded at its look; and profit
    from market direction said plainly. None when the reading holds no equity close."""
    from ..swarm import elane

    rows = [c for c in counted if c.get("equity")]
    if not rows:
        return None
    lanes: dict[str, dict[str, Any]] = {}
    programs: dict[str, dict[str, Any]] = {}
    for c in rows:
        lane = str(c.get("lane") or "")
        slot = lanes.setdefault(lane, {"label": lane_label(lane), "closes": 0, "net": Decimal(0), "unpriced": 0,
                                       "bh": [], "mte": []})
        slot["closes"] += 1
        if c.get("pnl_usd") is None:
            slot["unpriced"] += 1
        else:
            slot["net"] += c["pnl_usd"]
        bh = _num((c.get("bh") or {}).get("delta_usd"))
        if bh is not None:
            slot["bh"].append(bh)
        if _num(c.get("mte")) is not None:
            slot["mte"].append(float(c["mte"]))
        prog = programs.setdefault(c["family"], {"family": c["family"], "lane": lane, "label": lane_label(lane),
                                                 "seeded": bool(c.get("seeded")), "closes": 0, "fp": None})
        prog["closes"] += 1
        if c.get("fp"):
            prog["fp"] = c["fp"]
    return {"closes": len(rows),
            "by_lane": {lane: {"label": v["label"], "closes": v["closes"],
                               "net_usd": None if v["unpriced"] else _usd(v["net"]),
                               "bh_usd": round(sum(v["bh"]), 2) if v["bh"] else None, "bh_priced": len(v["bh"]),
                               "mte_mean": round(statistics.fmean(v["mte"]), 6) if v["mte"] else None,
                               "mte_n": len(v["mte"])} for lane, v in sorted(lanes.items())},
            "programs": [programs[f] for f in sorted(programs)],
            "seeded": sorted(f for f, v in programs.items() if v["seeded"]),
            "seeded_note": elane.SEEDED_NOTE if any(v["seeded"] for v in programs.values()) else None,
            "direction": EQUITY_DIRECTION, "zero_edge_note": ZERO_EDGE_EQUITY_NOTE}


#: THE GAP'S MEASURE, said beside every reading (the readiness audit's done-meter note: the rule says "mean ... gap", D5
#: reads a ratio of sums).
GAP_MEASURE = ("ratio of sums, D5's measure: over the (version, entry day) cells where a counted close and its "
               "version's nightly replay both traded, sum(live P&L) / sum(live maximum loss) - sum(replay P&L) / "
               "sum(replay maximum loss), the live side at the book's cash")
#: The first checkpoint's research window (DONE-RULE item 7): its last `dlane.DONE["research_first_days"]` UTC days, 3
#: since THE OWNER'S CHANGE OF THE PINNED RULE (A50, the goal of Oct 16, 2026: "on each of the 3 UTC days ending on the
#: checkpoint day"; this module's own `RESEARCH_FIRST_DAYS = 7` before it, `dlane.OLD_DONE`'s, read by nothing); a later
#: checkpoint's is every UTC day since the one before it (`research_window`).
#: The report's running view of item 7 beside the meters (`done.research_247_last_7_days`, never a reading): its own
#: span, which the rule's window no longer sets, so the key and its days are as they were.
RESEARCH_BESIDE_DAYS = 7


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
        rec = twins.get(str(c.get("pid"))) or {}
        if rec.get("status") in TWIN_FINAL or rec.get("final") is True:
            pass
        elif twins_on or c.get("equity"):
            # An equity close has no nightly replay: its twin (league/ops/twins.py `equity_twin`) is its replay.
            pending_twin += 1
        else:
            state = replay_days.get(str(c.get("family") or "")) or {}
            if state.get("replayed") and not (state.get("day") and str(state["day"]) >= exit_day):
                pending_replay += 1
        if c.get("equity"):
            # The book marks an equity lot's fees posted once the venue's own (SEC, TAF) are booked on it.
            if not c.get("fees_posted"):
                pending_fees += 1
        elif c.get("fee_basis") != "broker" or not fees_as_of or fees_as_of <= exit_day:
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
    the last `dlane.DONE["research_first_days"]` UTC days ending on the UTC day of the K-th close for the first
    checkpoint (3 since the owner's A50: "on each of the 3 UTC days ending on the checkpoint day"; 7 before); for a
    later one, every UTC day after the previous checkpoint's day through its own (at least its own day: two
    checkpoints on one UTC day read that day). UTC days, so a weekend or a clock change in New York moves nothing."""
    from ..swarm import dlane

    last = time.strftime("%Y-%m-%d", time.gmtime(float(counted[k - 1]["closed_at"])))
    end = datetime.fromisoformat(last).date()
    if previous_k is None:
        first = (end - timedelta(days=int(dlane.DONE["research_first_days"]) - 1)).isoformat()
    else:
        before = datetime.fromisoformat(time.strftime("%Y-%m-%d", time.gmtime(float(counted[previous_k - 1]["closed_at"])))
                                        ).date()
        first = min(end, before + timedelta(days=1)).isoformat()
    return first, last


def close_dates(counted: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """A14's FIGURES BESIDE A DONE READING (`A14_BESIDE_DONE`; release E4 step two), over exactly `counted` (a
    checkpoint's counted closes, every program and lane): {"closes", "dates" (the distinct close dates: a close's New
    York `day`), "date_t" (the date-clustered t of their P&L: each date's priced closes summed in dollars, then mean /
    sd (ddof 1) x sqrt(n) over the dates; None under two dates or with no spread), "unpriced" (closes with no P&L yet:
    their dates count, their dollars do not), "note"}. THE HONESTY LINE FOR LOT-SPLITTING: a basket's eight lots sold at
    one open are eight closes and ONE date. Beside, never a rule: no item of a reading, no hold and no alarm reads it."""
    by_day: dict[str, Decimal] = {}
    unpriced = 0
    for c in counted:
        day = str(c.get("day") or "") or _ny_day(_num(c.get("closed_at")))
        by_day.setdefault(day, Decimal(0))
        if c.get("pnl_usd") is None:
            unpriced += 1
        else:
            by_day[day] += Decimal(str(c["pnl_usd"]))
    values = [float(v) for _, v in sorted(by_day.items())]
    t = None
    if len(values) >= 2:
        mean = math.fsum(values) / len(values)
        sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (len(values) - 1))
        t = round(mean / sd * math.sqrt(len(values)), 4) if sd > 1e-12 else None
    return {"closes": len(counted), "dates": len(by_day), "date_t": t, "unpriced": unpriced,
            "note": "beside, never a rule: the closes of one date are one market move (A14)"}


def _session_ranges(days: Iterable[str]) -> list[list[str]]:
    """Sorted session days as [[from, to], ...], each a run of consecutive sessions (both ends counted)."""
    from ..equity import schedule as ES

    out: list[list[str]] = []
    for day in sorted(set(days)):
        if out and ES.next_session(out[-1][1]).isoformat() == day:
            out[-1][1] = day
        else:
            out.append([day, day])
    return out


def span_bh(counted: Sequence[Mapping[str, Any]], book: Mapping[str, Any], *,
            constitution: Mapping[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """C1 (A45; THE SCALING PLAN's 2.4, its benchmark): EACH SHARE PROGRAM'S SPAN BUY-AND-HOLD over exactly the equity
    closes of `counted` (a checkpoint's first K counts), from the book's own store (`book`: `read_book`'s `bars`,
    `spy`, `open_note` and `lots`): {family: [one entry a version, oldest first]}, where an entry is {version, usd,
    priced, why, basis "adjustment=all", blocked [[from, to], ...], symbols {SYM: {before, last, sessions,
    sessions_used, segments, close_before, close_last, closes {day: close} at every segment boundary, exposure_usd,
    usd, sha}}, spy {closes {day: close}, usd, sha} | None, lots, blocked_from}.

    - A SINGLE-NAME PROGRAM: the House's own `_bh_pnl` rule (league/equity/live.py `span_bh`: per symbol, the mean
      exposure from the close before the first entry to the close of the last exit, at adjustment=all closes of ONE
      fetch), with the plan's ONE CHANGE: a session in `blocked` on which the program held nothing in the symbol is
      taken out of the span, which splits there. With no such session it is `_bh_pnl` exactly.
    - `blocked`: THE SESSIONS IN WHICH THE HOUSE LET NO OPEN GO AT ALL (`shut_days`: every entry window the open note
      names for the session refused; `SPAN_BLOCKED` says what it does not hold), less EVERY ENTRY DAY OF THE VERSION'S
      LOTS IN THE BOOK (open or closed, counted or not: a session it opened in did not block it), inside the span of
      the counted closes. Neither half depends on K, so a version's blocked sessions are the same at every checkpoint:
      each entry lists the ones inside its own span, and one ledger list (or the House's own list) agrees with every
      checkpoint. It is listed whole; the split takes out only the sessions held empty.
    - A PANEL PROGRAM (EQUITY (PANEL)): B10, the House's own panel benchmark (`b10_bh`: per lot, entry notional x SPY's
      move from the close before its entry to its exit day's close); `symbols` is empty and nothing is split.
    A close with no version gives no entry (the plan's script reads an entry with no version as any version's).
    FAIL CLOSED: an unreadable input (the bar store's close missing, off one basis or not a finite price, a figure a
    float cannot hold, a lot without a notional, the open note unreadable, the seat rule "first-come", under which
    the House keeps no note, or any read of the book that raises) is `priced` False with `why`, never a guessed
    figure. Beside the reading, never a rule: no item, hold, count or alarm reads it. Never raises: closes that cannot
    even be grouped by program give no entry ({})."""
    try:
        groups: dict[str, dict[int, list[Mapping[str, Any]]]] = {}
        for c in counted:
            version = c.get("version")
            if c.get("equity") and isinstance(version, int) and not isinstance(version, bool):
                groups.setdefault(str(c["family"]), {}).setdefault(version, []).append(c)
    except Exception:  # noqa: BLE001 - closes that name no program give no entry: the plan's script fails it closed
        return {}
    if not groups:
        return {}
    unread = blocked_why = None
    shut: set[str] = set()
    entry_days: dict[tuple[str, Any], set[str]] = {}
    bars: dict[str, dict[str, tuple]] = {}
    spy: dict[str, tuple] = {}
    try:
        from ..equity import bands as EB
        from ..equity import live as EL
        from ..equity import schedule as ES

        note = book.get("open_note")
        if not isinstance(note, Mapping):
            blocked_why = "the House's open note (eq_open_note) cannot be read: the sessions it blocked are unknown"
        elif EB.seat_settings(constitution).first_come:
            blocked_why = ("the seat rule in force is first-come: the House keeps no open note, so the sessions it "
                           "blocked are unknown")
        else:
            shut = set(EL.shut_days(note))
        for r in book.get("bars") or []:
            bars.setdefault(str(r.get("symbol")), {})[str(r.get("day"))] = (r.get("c"), r.get("sha"))
        spy = {str(r.get("day")): (r.get("c"), r.get("sha")) for r in book.get("spy") or []} or bars.get("SPY") or {}
        for lot in book.get("lots") or []:
            version = version_of(lot.get("instance"))
            key = (str(lot.get("family") or ""), version if version is not None else _int(lot.get("version")))
            entry_days.setdefault(key, set()).add(str(lot.get("opened_day") or "")[:10])
    except Exception as exc:  # noqa: BLE001 - the inputs not read: every entry says so, none has a figure
        unread = f"the span's rule or inputs could not be read ({type(exc).__name__}: {str(exc)[:120]})"
    out: dict[str, list[dict[str, Any]]] = {}
    for family, versions in sorted(groups.items()):
        for version, rows in sorted(versions.items()):
            panel = any(c.get("panel") for c in rows)
            entry: dict[str, Any] = {"version": version, "usd": None, "priced": False, "why": unread,
                                     "basis": SPAN_BASIS, "blocked": [], "symbols": {}, "spy": None, "lots": len(rows),
                                     "blocked_from": SPAN_B10 if panel else SPAN_BLOCKED}
            out.setdefault(family, []).append(entry)
            if unread:
                continue
            try:
                lots = [{"symbol": c.get("symbol"), "opened_day": c.get("opened_day"), "exit_day": c.get("day"),
                         "entry_notional": c.get("notional"), "closed_at": c.get("closed_at"), "lid": c.get("lid")}
                        for c in rows]
                if panel:
                    got = EL.b10_bh(lots, spy)
                    if not got["priced"]:
                        entry["why"] = f"B10 unpriced: {got['why']}"
                        continue
                    entry.update(priced=True, usd=_usd(got["usd"]),
                                 spy={"closes": {d: float(v) for d, v in got["closes"].items()},
                                      "usd": _usd(got["usd"]), "sha": got["sha"]})
                elif blocked_why:
                    entry["why"] = blocked_why
                    continue
                else:
                    own = {str(c.get("opened_day") or "")[:10] for c in rows}
                    start = ES.previous_session(min(own)).isoformat()
                    end = max(str(c.get("day") or "")[:10] for c in rows)
                    opened = own | entry_days.get((family, version), set())
                    blocked = sorted(d for d in shut - opened if start < d <= end and ES.is_session(d))
                    entry["blocked"] = _session_ranges(blocked)
                    got = EL.span_bh(lots, bars, blocked)
                    if not got["priced"]:
                        entry["why"] = f"span buy-and-hold unpriced: {got['why']}"
                        continue
                    entry.update(priced=True, usd=_usd(got["usd"]), symbols={
                        s: {"before": x["before"], "last": x["last"], "sessions": x["sessions"],
                            "sessions_used": x["sessions_used"], "segments": x["segments"],
                            "close_before": float(x["closes"][x["before"]]),
                            "close_last": float(x["closes"][x["last"]]),
                            "closes": {d: float(v) for d, v in x["closes"].items()},
                            "exposure_usd": _usd(x["exposure"]), "usd": _usd(x["usd"]), "sha": x["sha"]}
                        for s, x in got["symbols"].items()})
                if not _all_finite(entry):
                    entry.update(priced=False, usd=None, symbols={}, spy=None,
                                 why="a figure is out of a float's range: no figure")
            except Exception as exc:  # noqa: BLE001 - unread is said, never a figure
                entry.update(priced=False, usd=None, symbols={}, spy=None,
                             why=f"the span could not be read ({type(exc).__name__}: {str(exc)[:120]})")
    return out


def _all_finite(entry: Mapping[str, Any]) -> bool:
    """Whether every figure of a span entry is a finite float (JSON has no Infinity; the plan's script reads none)."""
    figures = [entry.get("usd")]
    for x in (entry.get("symbols") or {}).values():
        figures += [x["close_before"], x["close_last"], x["exposure_usd"], x["usd"], *x["closes"].values()]
    if isinstance(entry.get("spy"), Mapping):
        figures += [entry["spy"]["usd"], *entry["spy"]["closes"].values()]
    return all(isinstance(v, float) and math.isfinite(v) for v in figures)


def meter(all_closes: Sequence[Mapping[str, Any]], routes: Sequence[str], store: Any, *,
          nightly_cache: dict[str, list] | None = None, lanes: Lanes | None = None,
          previous: Mapping[str, Any] | None = None, research: Any = None,
          replay_days: Mapping[str, Mapping[str, Any]] | None = None, fees_as_of: str | None = None,
          now: float | None = None, twins: Mapping[str, Mapping[str, Any]] | None = None,
          twins_on: bool = False, span: Any = None) -> dict[str, Any]:
    """One Done meter (`done_screen` or `done_all`): the agent closes on `routes`, the running figures (never a reading),
    and a reading at every checkpoint reached (the first K closes, K = 15, 20, 25, ...: `dlane.DONE`, the owner's
    rule since A50; K = 30, 40, ... before it).

    Each checkpoint (Oct 10, 2026; DONE-RULE-A1 and the readiness audit's B1, M7 and M8) lists every counted program with
    its closes, matched replay closes and gap (`by_program`), reads DONE-RULE item 7 over its research window
    (`research_247`, from `research(first_day, last_day)`; with none handed in, item 7 is unread and the checkpoint does
    not hold), and says whether its inputs are FINAL (`finality`; `final_why` otherwise). It HOLDS when items 3, 4 (A1.1)
    and 7 all hold; a Done claim is made only on a holding FINAL checkpoint (the meter's `holds`; alarm A8). A final
    reading is FROZEN: when the `previous` report's meter has the checkpoint final, it is carried forward as it was,
    whatever the inputs say now (nightly rows are replaced each night; the reading may not flip after A8).

    C1 (A45; `span_bh`): with `span` (a callable of a checkpoint's counted closes, `report` hands it `span_bh` over the
    book), each share program's `by_program` row of a checkpoint read here also carries `span_bh`, beside the reading
    and never part of it. A frozen checkpoint is carried whole, its field with it: written once, never recomputed.

    A14 (release E3; `a14_of`): a checkpoint's reading also needs A14 over its counted closes (it holds outright with no
    equity close); it is in the checkpoint's `holds`, its item 4 and `consistent_ok`, carried whole as `a14`, and a
    reading whose A14 is not final is not final. The `running` figures are untouched."""
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
    # THE CHECKPOINTS READ DONE'S COUNTS (`done_counts`: a panel program's lots of one date are one count): the K-th
    # count's checkpoint reads the closes of the first K counts (`first_counts`), and its moment is the last of them
    # (`ends`, one a count). With no panel close every count is a close and all of it is as before.
    counts = done_counts(counted)
    last_of: dict[int, int] = {}
    for i, n in enumerate(counts):
        last_of[n] = i
    ends: list[Mapping[str, Any]] = []
    at_most = -1
    for n in range(1, max(counts, default=0) + 1):
        at_most = max(at_most, last_of[n])       # the last close, in close order, of the first n counts
        ends.append(counted[at_most])
    while k <= len(ends):
        if k in frozen:
            checkpoints.append({**frozen[k], "frozen": True})
            prev_k, k = k, k + int(rule["checkpoint_every"])
            continue
        upto = first_counts(counted, k, counts)
        a14 = a14_of(store, upto)
        at = reading(upto, store, nightly_cache=cache, lanes=lanes, twins=twins, a14=a14)
        a14 = at.get("a14") or a14  # with an equity close: that reading, the rows' own fill-gap half beside it
        first_day, last_day = research_window(ends, k, prev_k)
        r247 = {"holds": False, "first_day": first_day, "last_day": last_day, "why": "research 24/7 was not read"}
        if callable(research):
            try:
                r247 = research(first_day, last_day)
            except Exception as exc:  # noqa: BLE001 - unread is not held: the checkpoint does not hold, the report goes on
                r247 = {**r247, "why": f"research 24/7 could not be read ({type(exc).__name__}: {str(exc)[:120]})"}
        fin = finality(upto, replay_days=replay_days, fees_as_of=fees_as_of, twins=twins, twins_on=twins_on)
        day_ended = now is None or now >= _epoch(f"{last_day}T00:00:00Z") + 86400.0
        if not day_ended:
            fin = {**fin, "final": False, "why": "; ".join(w for w in (fin["why"], f"the research window's last day "
                                                                                  f"({last_day}) has not ended") if w)}
        if not a14["final"]:
            fin = {**fin, "final": False, "why": "; ".join(w for w in (fin["why"], "A14: a twin or a shadow session has "
                                                                                  "not landed") if w)}
        item7 = r247.get("holds") is True
        whys = [w for w in (at["why"], None if item7 else f"research 24/7 (item 7): {r247.get('why') or 'not held'}",
                            None if a14["holds"] else f"A14 (live fills consistent with their replay): "
                                                      f"{a14.get('why') or 'not held'}") if w]
        programs = [{"family": p["family"], "lane": p["lane"], "closes": p["closes"], "matched": p["replay"]["matched"],
                     "gap": p["replay"]["gap"], "consistent": p["replay"]["consistent"], "net_usd": p["net_usd"],
                     **({"label": p["label"]} if p.get("label") else {})} for p in at["by_program"]]
        if callable(span):
            # C1 (A45): each share program's span buy-and-hold over exactly these closes; it never fails the meter.
            try:
                spans = span(upto) or {}
            except Exception:  # noqa: BLE001 - no field: the plan's script reads its closes file or fails closed
                spans = {}
            for p in programs:
                if spans.get(p["family"]):
                    p["span_bh"] = spans[p["family"]]
        checkpoints.append({"at_close": k, "closed_at": _iso(ends[k - 1]["closed_at"]),
                            "holds": at["holds"] and item7 and a14["holds"], "why": "; ".join(whys) or None,
                            "items": {**at["items"], "4": at["items"]["4"] and a14["holds"], "7": item7},
                            "final": fin["final"], "final_why": fin["why"],
                            "closes": at["closes"], **({"lots": at["lots"]} if "lots" in at else {}),
                            "programs": at["programs"],
                            "programs_with_min_closes": at["programs_with_min_closes"], "net_usd": at["net_usd"],
                            "consistent_ok": at["consistent_ok"] and a14["holds"], "a14": a14,
                            "close_dates": close_dates(upto),
                            "measured_programs": at["measured_programs"],
                            "replay_coverage": at["replay_coverage"], "by_program": programs,
                            "research_247": r247, "by_route": at["by_route"], "bh": at["bh"],
                            **({"equity": at["equity"]} if at.get("equity") else {}),
                            # A14's reading of item 4 for a checkpoint that holds an equity close (`a14_consistency`).
                            **({"a14": at["a14"]} if at.get("a14") else {})})
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
                        "bh": c.get("bh"),
                        **({"label": c.get("label"), "seeded": bool(c.get("seeded")), "mte": c.get("mte"),
                            "fp": c.get("fp")} if c.get("equity") else {})} for c in counted]}


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
    RELEASE E2, WHICH LANES THE RULE MEANS: the day's three counts are the OPTIONS lanes' (the pinned rule's "Gym runs"
    are the Gym's, and it was written when every birth and Validation was an options one). The equity lanes' births,
    their Train runs on the House and their Validations are reported BESIDE (`equity`), never a part of a count and
    never a bar: an equity row must not make a day hold while the options researchers were paused (the integration
    review's loop-4), and a day without an equity birth fails nothing. Counting the equity lanes in item 7 is the
    owner's change of the pinned rule, not this reader's.
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
        # THE OPTIONS LANES' counts (the class docstring): the stall facts' own filters (league/ops/stall.py).
        from .stall import OPTIONS_BIRTHS, OPTIONS_RUNS

        born = "SELECT count(*) AS n FROM events WHERE kind='swarm.born' AND at>=? AND at<?"
        births = one(f"{born} AND {OPTIONS_BIRTHS}", (start, end))
        births += one("SELECT count(*) AS n FROM families WHERE origin='game' AND born_at>=? AND born_at<?", (start, end))
        ran = f"SELECT count(*) AS n FROM runs WHERE at>=? AND at<? AND status NOT IN ({marks})"
        gym = one(f"{ran} AND trials > 0 AND {OPTIONS_RUNS}", (start, end, *NOT_RUN))
        validation_rows = one(f"{ran} AND \"window\"='validation' AND {OPTIONS_RUNS}", (start, end, *NOT_RUN))
        # THE EQUITY LANES, beside: their births, their Train runs on the House and their Validations.
        equity = {"births": one(f"{born} AND NOT ({OPTIONS_BIRTHS})", (start, end)),
                  "train_runs": one(f"{ran} AND \"window\"='train' AND NOT ({OPTIONS_RUNS})", (start, end, *NOT_RUN)),
                  "validations": one(f"{ran} AND \"window\"='validation' AND NOT ({OPTIONS_RUNS})", (start, end, *NOT_RUN))}
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
               "validation_rows": validation_rows, "judged": judged, "equity": equity, "at_budget": at_budget,
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
                        "budget (no taper), with no owner step waiting; the counts are the options lanes' and the "
                        "equity lanes' are reported beside each day (`equity`), never a bar; the operator's edits of "
                        "swarm.json and budget.json are listed beside it, never a bar"}


# ------------------------------------------------------------------------------------------------- the funnel
def funnel(store: Any, lanes: Lanes, all_closes: Sequence[Mapping[str, Any]], *, now: float, hours: float,
           positions: Sequence[Mapping[str, Any]] = (), lots: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Each lane's counts over the last `hours` (the module docstring), from the swarm store opened read-only. Since Oct
    10, 2026 (the readiness audit's m11) the agents' real OPENS by route too (`real_opens`, from the live book's
    `positions`): the first real Probe trade was in no dlane funnel count until it closed. Since release E1 the equity
    lanes ("beta", "equity") have their own rows: their families' births, Validations, looks and band moves, their
    lots' real opens (`lots`, the EquityBook's) and closes."""
    from ..swarm import dlane

    since = _iso(now - hours * 3600.0)
    every_lane = all_lanes()
    out: dict[str, Any] = {lane: {"births": 0, "gym_runs": {w: 0 for w in RUN_WINDOWS}, "program_years": 0.0,
                                  "validations": {"judged": 0, "passed": 0}, "reviews": 0, "audits": 0,
                                  "looks": {"taken": 0, "passed": 0, "by_screen": {}},
                                  "band_moves": {"candidate": 0, "probe": 0, "sized": 0},
                                  "real_closes": {":r": 0, ":t": 0, ":i": 0, "other": 0},
                                  "real_opens": {":r": 0, ":t": 0, ":i": 0, "other": 0}}
                           for lane in every_lane}
    for row in store._all("SELECT family, payload FROM events WHERE kind='swarm.born' AND at>=?", (since,)):
        payload = _loads(row.get("payload"), {}) or {}
        lane = payload.get("lane") if isinstance(payload, Mapping) else None
        lane = lane if lane in every_lane else lanes.of(row.get("family"))
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
        out[c.get("lane") if c.get("lane") in out else dlane.ALPHA]["real_closes"][c.get("code") or "other"] += 1
    from .economics import route_of

    for p in positions:
        opened = _num(p.get("opened_at"))
        route = route_of(p)
        if opened is None or opened < edge or route in HOUSE_ROUTES:
            continue
        out[lanes.of(p.get("family"))]["real_opens"][ROUTE_CODES.get(route) or "other"] += 1
    for lot in lots:
        opened = _num(lot.get("opened_at"))
        if opened is None or opened < edge or lot.get("lane") not in out:
            continue
        out[lot["lane"]]["real_opens"][":r" if str(lot.get("instance") or "").endswith(":r") else "other"] += 1
    for lane in out.values():
        lane["program_years"] = round(lane["program_years"], 2)
    out[dlane.DIRECTION]["train_bar"] = dlane.failure_counts(store, hours, now=now)
    return out


def bands_now(store: Any, lanes: Lanes) -> dict[str, dict[str, int]]:
    """The living families by lane and band, the equity lanes' included (release E1)."""
    out = {lane: {"gym": 0, "candidate": 0, "probe": 0, "sized": 0, "alive": 0} for lane in all_lanes()}
    for fam in every_family(store):
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
                  all_closes: Sequence[Mapping[str, Any]], *, since: float, lots: Sequence[Mapping[str, Any]] = (),
                  screens: "EquityScreens | None" = None) -> dict[str, Any]:
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
    screens = screens if screens is not None else EquityScreens(store)

    def equity_screen(family: str, version: int | None, lane: Any) -> dict[str, Any]:
        # AN EQUITY TRADE (release E1, A9 and A11): beside it, the screen's line its program's one look recorded. A
        # PANEL TRADE (release E4): XS1's sentence, under the panel's own label.
        row = screens.of(family, version)
        return {**row, "lane": lane, "label": PANEL_LABEL if row.get("panel") else lane_label(lane)}

    closes_rows = [{"pid": c["pid"], "family": c["family"], "route": c.get("code") or c["route"], "version": c["version"],
                    "closed_at": _iso(c["closed_at"]), "pnl_usd": _usd(c["pnl_usd"]), "fee_basis": c["fee_basis"],
                    **(equity_screen(c["family"], c["version"], c.get("lane")) if c.get("equity") else
                       screen_of(c["family"], c["version"], str(c["route"]), _num(c.get("opened_at"))))}
                   for c in all_closes if not c["house"]]
    equity_trades = []
    for lot in lots:
        opened = _num(lot.get("opened_at"))
        if not str(lot.get("instance") or "").endswith(":r") or opened is None or opened < since:
            continue
        family, version = str(lot.get("family") or ""), version_of(lot.get("instance"))
        equity_trades.append({"pid": f"{EQUITY_PREFIX}{lot.get('lid')}", "family": family,
                              "instance": str(lot.get("instance") or ""), "version": version,
                              "status": str(lot.get("status") or ""), "opened_at": _iso(opened),
                              "closed_at": _iso(_num(lot.get("closed_at"))), "symbol": str(lot.get("symbol") or ""),
                              "class": lot.get("class"), "entry_at": lot.get("entry_at"),
                              **equity_screen(family, version, lot.get("lane"))})
    return {"probe_trades": probe_trades, "equity_trades": equity_trades, "closes": closes_rows,
            "contamination": CONTAMINATION,
            "note": "each row's rates are its screen's per program at zero edge, measured on historical worlds (a property "
                    "of the procedure, not a guarantee in this world); reported, never a bar"}


class EquityScreens:
    """THE SCREEN BESIDE EVERY EQUITY TRADE (release E1; the captain's A9: "stated beside every live trade: the
    receipt's line, with the program's own FP, c_used, c_H, the drift-kept rate from its own floor run, the S1-X label
    and the contamination sentence"; under A11 the receipt is S2's: c_R 0, c_H = c_H,used, the program's own FP, its
    holdout-only rate and its drift-kept rate from its own exact floor): the line its version's one passed look recorded
    (the `looks` row's detail, else the family state's `elane_look` of that version; league/swarm/elane.py `look`
    writes both with the look, from league/equity/screen.py `beside_line`), under the screen that judged it (`screen`:
    "S2" or "S1" as recorded, never assumed), read once a program. Never computed here: the look's own figures."""

    #: The verdict's figures a row carries (S1's `c_p` and `c_used`, S2's `c_pF1` and `holdout_only`; None where the
    #: screen that judged the look has none). THE TWO LABELS ARE APART, never one `label`: the look's detail names the
    #: LANE's under `label` ("MARKET BETA" | "EQUITY") and S1-X's under `s1x`, while the verdict names S1-X's under
    #: `label` ("alpha" | "beta"); a row carries `lane_label` and `s1x`.
    KEYS = ("passed", "c_R", "c_p", "c_pF1", "c_H", "c_used", "own_fp", "holdout_only", "drift_kept", "fp_x")

    def __init__(self, store: Any):
        self.store = store
        self.looks: dict[tuple[str, int], Mapping[str, Any]] | None = None
        self.states: dict[str, Mapping[str, Any]] = {}
        self.panels: dict[str, Mapping[str, Any] | None] = {}

    def xs1(self, family: str) -> str | None:
        """RELEASE E4: XS1's sentence of a panel family (the pinned pre-registration's 10.2, filled for the program and
        recorded with its one look: league/swarm/elane_xs.py `beside_line`), or None when it took no look or the lane
        cannot be read here."""
        fam = self.panels.get(family)
        if fam is None:
            return None
        try:
            from ..swarm import elane_xs

            return elane_xs.beside_line(fam) or None
        except Exception:  # noqa: BLE001 - none is stated, and the row says so
            return None

    def of(self, family: str, version: Any) -> dict[str, Any]:
        if self.looks is None:
            self.looks = {}
            try:
                for look in self.store.looks():
                    if look.get("passed"):
                        self.looks[(str(look["family"]), int(look["version"]))] = look
            except Exception:  # noqa: BLE001 - no look read: every row says so
                pass
        if family not in self.states:
            try:
                fam = self.store.family(family)
            except Exception:  # noqa: BLE001 - an unreadable family has no recorded look
                fam = None
            self.states[family] = ((fam or {}).get("state") or {}) if isinstance(fam, Mapping) else {}
            self.panels[family] = fam if isinstance(fam, Mapping) and str(fam.get("structure") or "") == PANEL_KIND \
                else None
        from ..swarm import elane

        lane_labels = set(elane.LABELS.values())
        n = _int(version)
        look = self.looks.get((family, n)) if n is not None else None
        detail = (look or {}).get("detail") or {}
        recorded = self.states[family].get("elane_look") or {}
        if not isinstance(recorded, Mapping) or _int(recorded.get("version")) != n:
            recorded = {}
        verdict = detail.get("verdict") or recorded.get("verdict") or {}
        verdict = verdict if isinstance(verdict, Mapping) else {}
        beside = detail.get("beside") or recorded.get("beside")
        out = {"screen": detail.get("screen") or verdict.get("screen"), "beside": beside,
               "look_at": (look or {}).get("at") or recorded.get("at"),
               "receipt": detail.get("receipt") or verdict.get("receipt"),
               **{k: detail.get(k) if detail.get(k) is not None else verdict.get(k) for k in self.KEYS},
               # S1-X's label (alpha or beta) is the verdict's `label`, the look detail's `s1x`; the detail's own
               # `label` is the lane's.
               "s1x": detail.get("s1x") if detail.get("s1x") is not None else verdict.get("label"),
               "lane_label": detail.get("label") if detail.get("label") in lane_labels else None}
        held = self.states[family].get("elane_forward")
        forward = not beside and isinstance(held, Mapping) and held.get("seated") is True and _int(held.get("version")) == n
        if self.panels.get(family) is not None and forward:
            # A PANEL PROGRAM SEATED ON A FWD1-R FORWARD PASS (the captain's A34, release U: the one panel seat): it
            # took no look; its line is its verdict's, which for a panel pass carries A34's two sentences (the
            # zero-edge rate at its checkpoint, and why there is no historical look: league/ops/fwd1_rule.py
            # `A34_MEMORY`), under the panel's own label.
            from . import forward_screen

            beside = forward_screen.beside_for(getattr(self.store, "root", None), str(held.get("lineage") or ""))
            out.update(screen="FWD1-R", beside=beside, lane_label=PANEL_LABEL, panel=True)
            if not beside:
                out["fp_why"] = ("no FWD1-R sentence is recorded for this panel program's forward pass "
                                 "(league/ops/forward_screen.py records it with the verdict): none is stated")
            return out
        if self.panels.get(family) is not None:
            # A PANEL PROGRAM (release E4): the screen is XS1 and the line is its receipt's sentence, stated beside
            # EVERY live panel trade (the pre-registration's duty 3), under the panel's own label.
            beside = beside or self.xs1(family)
            out.update(screen=out.get("screen") or "XS1", beside=beside, lane_label=PANEL_LABEL, panel=True)
            if not beside:
                out["fp_why"] = ("no XS1 sentence is recorded at this panel program's look (league/swarm/elane_xs.py "
                                 "records it with the look): none is stated")
            return out
        if forward:
            # THE FORWARD SCREEN FWD1-R: a program seated on a forward pass took no look; its sentence is its verdict's
            # (league/ops/forward_screen.py `beside_for`: the operator's, with its t and its shadow P&L)
            from . import forward_screen

            beside = forward_screen.beside_for(getattr(self.store, "root", None), str(held.get("lineage") or ""))
            out.update(screen="FWD1-R", beside=beside)
        if not beside:
            out["fp_why"] = ("no screen line is recorded at this version's look (league/swarm/elane.py records it with the "
                             "look): none is stated")
        return out


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
    """A1-A9, DC1, PL1 and K5 (HARNESS section 5 as amended; the module docstring): [{id, level, text, ...}]. Each
    names counts and family ids, never a hidden-year figure."""
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
    # A report under another pinned rule (the Oct 9 rule, before the owner's A50) saw ITS checkpoints, not this rule's.
    same_rule = isinstance(previous, Mapping) and isinstance(previous.get("rule"), Mapping) \
        and previous["rule"].get("sha256") == dlane.DONE["rule_sha256"]
    for meter_name in ("all", "screen") if same_rule else ():
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
    # DC1: a meter's latest checkpoint is final and does not hold, or is not final 2 sessions after its last close.
    out += dc1_alarms(done, now=now)
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


def _dc1_sessions(closed_at: Any, now: float) -> int | None:
    """DC1: how many sessions after the New York day of `closed_at` have reached their pre-open (`DC1_PREOPEN_S` before
    the open) by `now`. None when the time or the calendar cannot be read."""
    from ..equity import schedule as ES

    at = _epoch(closed_at) if closed_at else None
    if at is None:
        return None
    try:
        day, n = ES.ny_day(at), 0
        while n < 1000:
            day = ES.next_session(day)
            moments = ES.moments(day)
            if moments is None or float(now) < moments.open_at - DC1_PREOPEN_S:
                break
            n += 1
    except (TypeError, ValueError):
        return None
    return n


def dc1_alarms(done: Mapping[str, Any] | None, *, now: float) -> list[dict[str, Any]]:
    """DC1 (the rehearsal of Oct 15, 2026): A DONE CHECKPOINT THAT IS REACHED AND DOES NOT HOLD IS TOLD. Only a final
    holding one was told before (A8 and the stall's `done` cause). Read on each meter's LATEST checkpoint (`done.all`
    and `done.screen`; a later checkpoint takes the place of an earlier one) while it stands:
    - it is final and does not hold (frozen: it stands until the next checkpoint is reached). The text names the items
      that do not hold; or
    - it is not final at the pre-open of the `DC1_SESSIONS`-th session after the New York day of its last counted close
      (`_dc1_sessions`; the review of Oct 15, 2026: sessions, not UTC days, so a Friday's close waiting for Monday's
      twin by design is not told). A session row that never lands keeps it from final for good. A READING THAT IS
      NOT FINAL NAMES NO VERDICT: its text and its row carry neither `holds` nor the items that do not hold (item 3 at
      a checkpoint includes the sign of the net, and a provisional reading may still flip: A8's own rule). Only the
      close count, the sessions since and `final_why`.
    A House warning, never an owner step: the stall job's `dlane` cause names no step for it, so it never fails an
    item-7 day. ITS TEXT HOLDS NO DOLLAR FIGURE, NO NET, NO PROGRAM ROW AND NO BUY-AND-HOLD, and a clause of
    `final_why` with a figure is left out. The verdict and the items come first, so the stall's cut of 160 characters
    keeps them."""
    out: list[dict[str, Any]] = []
    for meter_name in ("all", "screen"):
        meter = (done or {}).get(meter_name)
        checkpoints = meter.get("checkpoints") if isinstance(meter, Mapping) else None
        cp = checkpoints[-1] if isinstance(checkpoints, list) and checkpoints else None
        if not isinstance(cp, Mapping) or cp.get("at_close") is None:
            continue
        final, holds = cp.get("final") is True, cp.get("holds") is True
        head = f"DC1: done_{meter_name} checkpoint at close {int(cp['at_close'])}"
        row = {"id": "DC1", "level": "warning", "meter": f"done_{meter_name}", "at_close": int(cp["at_close"]),
               "final": final}
        if final:
            if holds:
                continue    # A8's
            items = cp.get("items") if isinstance(cp.get("items"), Mapping) else {}
            missed = [DC1_ITEMS[k] for k in sorted(DC1_ITEMS) if items.get(k) is not True]
            text = f"{head} is final and does not hold. Not held: {', '.join(missed) or 'no item named'}"
            row.update(holds=False, not_held=missed)
        else:
            sessions = _dc1_sessions(cp.get("closed_at"), now)
            if sessions is not None and sessions < DC1_SESSIONS:
                continue    # provisional by design
            why = [part for part in str(cp.get("final_why") or "").split("; ") if part]
            kept = [part for part in why if not _DC1_FIGURE.search(part)]
            if len(kept) < len(why):
                kept.append(f"{len(why) - len(kept)} clauses with a figure left out")
            text = (f"{head} is not final {sessions} sessions after its last close" if sessions is not None else
                    f"{head} is not final, and the sessions since its last close cannot be counted")
            text += f". Not final because: {'; '.join(kept) or 'no reason given'}"
            row["sessions"] = sessions
        row["text"] = text + ". A House warning: nothing is paused or stopped"
        out.append(row)
    return out


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


def zero_edge(settings: Mapping[str, Any] | None, *, equity_closes: int = 0) -> dict[str, Any]:
    """P(Done | zero edge) beside the meter (decision 8; DONE-RULE-A1 A1.2, the readiness audit's M10; DONE-RULE-A50 item
    6 and the reviews of A50, Oct 16, 2026). {label, rule_sha256 (the pinned rule in force), measured, value, ...,
    beside}:

    - THE FIGURE UNDER THE RULE IN FORCE comes only from the setting `dlane.done_zero_edge_p` written as a block
      (`dlane.ZERO_EDGE_BLOCK_KEYS`) whose `measured_under` is `dlane.DONE["rule_sha256"]`: then `measured` is True and
      `value`, `horizon`, `source_sha256` and `measured_under` are the block's. Otherwise `measured` is False, `value`
      is None and `note` says plainly that it is not yet measured (`ZERO_EDGE_UNMEASURED`); a block measured under
      another rule, or malformed, is never stated, and `refused` says why.
    - `beside`: the figure as before, `dlane.cfg`'s number (the default when the setting is a block), and when it is one
      this code names (`dlane.ZERO_EDGES`: 0.024, A1.2's pin under L-D's $400 total; 0.027, PREREG-T's under the $800
      total, since Oct 10, 2026) what it is: its horizon, holds, the budget variant, its source, who named it and the
      rule it was simulated under (`measured_under`, the Oct 9 rule's sha). A named figure that is not the one this code
      ships (`dlane.ZERO_EDGE`) says so; another figure is a setting's and says so. It is never the figure under the
      rule in force. `equity_closes`: the counted closes that are equity closes; with any, `beside` says it is the
      options rules' figure only (`ZERO_EDGE_EQUITY_NOTE`: `applies_to`, `equity_closes`, `equity_note`)."""
    from ..swarm import dlane

    c = dlane.cfg(settings)
    rule_sha = dlane.DONE["rule_sha256"]
    value = c["done_zero_edge_p"]
    beside: dict[str, Any] = {"value": value, "label": ZERO_EDGE_LABEL}
    named = next((z for v, z in dlane.ZERO_EDGES.items() if abs(value - float(v)) < 1e-9), None)
    if named is not None:
        beside.update({k: v for k, v in named.items() if k != "value"})
        beside["rule"] = "the Oct 9 rule (DONE-RULE.md), not the rule in force"
        if named is not dlane.ZERO_EDGE:
            beside["note"] = (f"a setting chose {named['value']} ({named['by']}); the rules this code ships carry "
                              f"{dlane.ZERO_EDGE['value']} ({dlane.ZERO_EDGE['by']})")
    else:
        beside["note"] = ("a setting's figure (dlane.done_zero_edge_p), not one this code names ("
                          + "; ".join(f"{z['value']}: {z['by']}" for z in dlane.ZERO_EDGES.values())
                          + "): its horizon, budget and rule are not said here")
    if int(equity_closes) > 0:
        beside.update(applies_to="the options Probe rules only", equity_closes=int(equity_closes),
                      equity_note=ZERO_EDGE_EQUITY_NOTE)
    out: dict[str, Any] = {"label": ZERO_EDGE_LABEL, "rule_sha256": rule_sha}
    block = c.get("done_zero_edge_measured")
    if isinstance(block, Mapping) and "refused" not in block and block.get("measured_under") == rule_sha:
        out.update(measured=True, **{k: block[k] for k in dlane.ZERO_EDGE_BLOCK_KEYS})
    else:
        out.update(measured=False, value=None, note=zero_edge_unmeasured(beside))
        if isinstance(block, Mapping):
            out["refused"] = block.get("refused") or (
                f"dlane.done_zero_edge_p's block was measured under the rule {str(block.get('measured_under'))[:8]}, "
                f"not the rule in force ({rule_sha[:8]}): it is not stated")
    out["beside"] = beside
    return out


#: WHAT THE REPORT SAYS while no figure measured under the rule in force is set (the reviews of A50, Oct 16, 2026):
#: never the Oct 9 rule's figure in its place.
ZERO_EDGE_UNMEASURED = ("P(Done | zero edge) under the rule in force is not yet measured (the {figure} beside it was "
                        "simulated under the Oct 9 rule)")
ZERO_EDGE_UNMEASURED_SETTING = ("P(Done | zero edge) under the rule in force is not yet measured (the {figure} beside it "
                                "is a setting's figure, under no rule this code names)")


def zero_edge_unmeasured(beside: Mapping[str, Any]) -> str:
    """`ZERO_EDGE_UNMEASURED` with the figure beside it (`ZERO_EDGE_UNMEASURED_SETTING` when that figure is no figure
    `dlane.ZERO_EDGES` names, so no rule is claimed for it)."""
    from ..swarm import dlane

    text = ZERO_EDGE_UNMEASURED if beside.get("measured_under") == dlane.OCT9_RULE_SHA256 else ZERO_EDGE_UNMEASURED_SETTING
    return text.format(figure=f"{float(beside['value']):g}")


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
           previous: Mapping[str, Any] | None = None, count_from: float | None = None) -> dict[str, Any]:
    """The report (the module docstring), from the state root `root`: the swarm store opened read-only, the live book
    read-only, the closes, health and publish files. `settings` the swarm's (`settings.load(root)` when None).
    `count_from`: where the Done meters start counting (epoch; `done_from()`, the goal's Oct 10, 2026, when None). No
    write."""
    from ..swarm import dlane, elane
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
        # THE EQUITY CLOSES (release E1): each lot fully closed, beside it its twin's buy-and-hold, MTE and its screen.
        seeded = seeded_families(store, book)
        eq_twins = TW.equity_records(store)
        screens = EquityScreens(store)
        for c in equity_closes(book.get("lots") or [], since=start, seeded=seeded):
            every.append(attach_equity(c, eq_twins.get(c["pid"]), screens))
        every.sort(key=_order)
        # THE GOAL OF OCT 10, 2026: the meters count from `count_from`; every earlier agent close is reported beside.
        count_from = done_from() if count_from is None else float(count_from)
        counted = [c for c in every if c["closed_at"] >= count_from]
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
        if not isinstance(prev_done, Mapping) or (prev_done.get("counted_from") or _iso(start)) != _iso(count_from):
            prev_done = {}  # a frozen reading is carried only from a report that counted from the same instant
        prev_rule = (previous.get("rule") or {}) if isinstance(previous, Mapping) else {}
        if not isinstance(prev_rule, Mapping) or prev_rule.get("sha256") != dlane.DONE["rule_sha256"]:
            # THE OWNER'S CHANGE OF THE PINNED RULE (A50, Oct 16, 2026): a reading frozen under another pinned rule (the
            # Oct 9 rule's 30th close, say) is never carried into this one's checkpoints; each is read afresh.
            prev_done = {}
        # The per-close twins (B1 (c), Oct 10, 2026; `league/ops/twins.py`): read once, matched in each meter's replay gap
        # and, with the switch on, a close's replay is final only once its twin is (A1.4, the integration of Oct 10).
        # The equity twins (release E1) are always on: an equity close has no nightly replay to fall back on.
        twins = {**twin_records(store), **eq_twins}
        twins_on = TW.cfg(settings) is not None
        common = dict(store=store, nightly_cache=cache, lanes=lanes, research=research, replay_days=replay_days,
                      fees_as_of=fees_as_of, now=now, twins=twins, twins_on=twins_on,
                      span=lambda upto: span_bh(upto, book))   # C1 (A45): each checkpoint's span buy-and-hold
        done = {"all": meter(counted, dlane.DONE["routes_all"], previous=prev_done.get("all"), **common),
                "screen": meter(counted, dlane.DONE["routes_screen"], previous=prev_done.get("screen"), **common)}
        # DONE WITH AND WITHOUT THE THREE SEEDED PROGRAMS (A8.12): the same meters over every other program's closes.
        rest = [c for c in counted if c["family"] not in seeded]
        prev_rest = prev_done.get("without_seeded") or {}
        without = {"seeded": sorted(seeded), "note": elane.SEEDED_NOTE,
                   "all": meter(rest, dlane.DONE["routes_all"], previous=prev_rest.get("all"), **common),
                   "screen": meter(rest, dlane.DONE["routes_screen"], previous=prev_rest.get("screen"), **common)}
        earlier = [c for c in every if not c["house"] and c.get("code") and c["closed_at"] < count_from]
        earlier_known = [c["pnl_usd"] for c in earlier if c.get("pnl_usd") is not None]
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
            "funnel": {name: funnel(store, lanes, every, now=now, hours=hours, positions=book["positions"],
                                    lots=book.get("lots") or ())
                       for name, hours in WINDOWS.items()},
            "bands_now": bands_now(store, lanes),
            "probe_envelope": envelope, "unit": {k: unit.get(k) for k in ("known", "cap_usd", "equity_usd", "closes",
                                                                          "close_day", "why")},
            "done": {**done, "counted_from": _iso(count_from), "without_seeded": without,
                     "earlier": {"closes": [{"pid": c["pid"], "family": c["family"], "route": c.get("code"),
                                             "lane": c.get("lane"), "closed_at": _iso(c["closed_at"]),
                                             "pnl_usd": _usd(c["pnl_usd"]), "fee_basis": c["fee_basis"]}
                                            for c in earlier],
                                 "net_usd": _usd(sum(earlier_known, Decimal(0))) if len(earlier_known) == len(earlier)
                                 else None,
                                 "note": "agent closes before the count began: reported beside, never counted (the goal "
                                         "of Oct 10, 2026)"},
                     "preregistered": dict(PREREGISTERED),
                     "p_done_zero_edge": zero_edge(settings, equity_closes=sum(1 for c in counted if c.get("equity"))),
                     "net_after_costs": {**net_after_costs(root, counted, now=now), "counted_from": _iso(count_from),
                                         "counted_note": "the meters' closes count from counted_from; the costs are the "
                                                         "close economics' own, since its cost_start"},
                     "research_247_last_7_days": research(
                         (yesterday - timedelta(days=RESEARCH_BESIDE_DAYS - 1)).isoformat(), yesterday.isoformat()),
                     "other_routes": [{"pid": c["pid"], "family": c["family"], "instance": c["instance"],
                                       "route": c["route"], "pnl_usd": _usd(c["pnl_usd"])} for c in other],
                     "inception": dlane.DONE["inception"],
                     "fees": {"as_of": activity["as_of"], "why": activity["why"]}},
            "probes": probes(store, lanes, settings, book["positions"], losses),
            "roster": roster_now(root),
            "program_loss": losses,
            "fp_beside_trades": trade_screens(store, lanes, settings, book["positions"], every, since=start,
                                              lots=book.get("lots") or (), screens=screens),
            "equity": {**equity_section(book, every, eq_twins, count_from=count_from, unit=unit, seeded=seeded,
                                        screens=screens, root=root), **panel_lane(root, settings)},
            "equity_yield": equity_yield(store, settings),
            "direction_net": lane_net,
            "account": account(root, every, activity, previous, now=now),
            "costs": costs(store, since=start, lane_since=_epoch(started) if isinstance(started, str) else None),
            "replay_twins": replay_twins([c for c in every if not c["house"] and c.get("code") in dlane.DONE["routes_all"]],
                                         twins),
            "k5": dict(k5),
        }
        out["alarms"] = alarms(store, settings, lanes, book, every, envelope, done, k5, unit, previous, now=now,
                               today=today, losses=losses) + pt1_alarms(out["roster"], settings)
        try:  # RELEASE E3: the forward record's section and alarms (league/ops/forward_report.py); never the report's failure
            from . import forward_report
            out["forward_record"] = forward_report.read_section(root)
            out["alarms"] = out["alarms"] + [a for a in forward_report.alarms(root, now=now, settings=settings)
                                             if isinstance(a, dict) and isinstance(a.get("id"), str)
                                             and a.get("level") in ("info", "warning") and isinstance(a.get("text"), str)]
        except Exception:  # noqa: BLE001 - the report goes on without it
            out.setdefault("forward_record", None)
        panel_forward(out, root)    # RELEASE E4 (package J): the forward record's lines beside a live panel program
        # RESEARCH DOLLARS BY MEASURED YIELD (Oct 15, 2026; league/ops/lane_yield.py): each research group's booked
        # dollars against what they bought, over the funnel's own windows; operator-only, never the report's failure.
        try:
            from . import lane_yield
            out["lane_yield"] = lane_yield.section(store, lanes.of, out["funnel"], root=root, now=now, windows=WINDOWS)
        except Exception as exc:  # noqa: BLE001 - the report goes on without it
            out["lane_yield"] = {"error": type(exc).__name__}
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


__all__ = ["run", "report", "FILE", "CONTAMINATION", "PREREGISTERED", "A14_CONSISTENCY", "A14_BESIDE_DONE",
           "close_dates",
           "A14_SEAT_RULE", "A24_SEAT_RULE", "A24_SEAT_COSTS", "A30_SEAT_AMENDMENT", "SEAT_RULE", "equity_seats", "A14_GAP_BP", "A14_AGREEMENT", "a14_consistency", "ZERO_EDGE_EQUITY_NOTE", "LOOSENED",
           "TIGHTENED", "closes", "meter", "reading", "replay_gap",
           "replay_twins", "twin_records",
           "buy_and_hold", "entry_delta", "funnel", "probes", "probe_envelope", "alarms", "fee_corrections", "read_book",
           "version_of", "inception", "Lanes", "ZERO_EDGE_LABEL", "trade_screens", "ALPHA_FP", "finality",
           "research_window", "Research247", "operator_edits", "program_losses", "dm1_reach", "net_after_costs",
           "zero_edge", "ZERO_EDGE_UNMEASURED", "ZERO_EDGE_UNMEASURED_SETTING", "zero_edge_unmeasured", "retire_due", "GAP_MEASURE", "NEWS_CAUSES", "E0_BASIS", "pl1_alarms", "pt1_alarms",
           "dc1_alarms", "DC1_SESSIONS", "lane_off"]

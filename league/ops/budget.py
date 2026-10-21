"""THE BUDGET RULE (LTCM v3, the owner's D4, Oct 2026; RULE_VERSION 3, the owner's goal of Oct 19, 2026, item 4): every
metered compute dollar a day (Sail models and boxes, Claude, OpenAI, market data, Cloudflare) is held to $5 plus half
the trailing week's realized net profit, never above $25; the event lane's verdicts ride the Claude line first and the
old research roles get the remainder; each prefunded meter still tapers by itself as its balance falls, and the desk
asks for a card before the taper starts.

THE COST RULE (RULE_VERSION 3; the goal of Oct 19, 2026, item 4, word for word: "Cost follows profit: metered compute <=
$5 a day plus half the trailing week's realized net profit, never above $25; prepaid credit first"). THE ARITHMETIC, a
day:

    week_net = the realized net profit of EVERY real book (the options book's closed positions, fees in, with the
               broker's posted fee corrections; the equity book's closed ":r" lots, fees and dividends in, which is where
               the event lane's real lots live from release R2) closed from 00:00 New York of the first of the last
               `PROFIT_SESSIONS` (5) NYSE sessions that have closed, to now (`book_net`): THE TRAILING WEEK is one trading
               week; UNKNOWN (an options position closed but unpriced, an order pending or unknown, reconciliation
               frozen, a blocking account reading: `book_p30`'s rules) is no profit
    earned   = PROFIT_SHARE (0.5) x max(0, week_net) / PROFIT_DAYS (7)    HALF the week's profit, spread over the 7
               calendar days a week of compute runs: seven days at the cap spend at most 7 x $5 plus half the week's
               profit, never more; a losing week lifts nothing and takes nothing from the $5
    cap      = min(CEILING_USD_DAY (25), BASE_USD_DAY (5) + earned)       every metered dollar of the day
    fixed    = Sail's fixed boxes (the House box and the data box, as below) + Cloudflare (`CLOUDFLARE_USD_DAY`, the
               Workers plan) + market data (`DATA_USD_DAY`: 0 since the owner cancelled ThetaData and Alpaca's Algo
               Trader Plus on Oct 18, 2026): the fixed costs count INSIDE the cap
    room     = max(0, cap - fixed)
    lane     = min(room, max(LANE_USD_DAY (3), LANE_HEADROOM (1.5) x the lane's heaviest UTC day of verdicts over the
               trailing `LANE_WINDOW_DAYS` (7))): the event lane's verdicts (PREREG-EVL-1 section 4), FIRST on the Claude
               line; a lane held at its line one day has half as much again the next, up to the room
    rest     = room - lane, the old research roles' remainder, split SPLIT: Sail 0.8 (models and Gym boxes), Claude 0.2
               (the gate, the strategist, the post-mortem, the engineer)

so the Claude meter's line is lane + 0.2 x rest and Sail's is 0.8 x rest (each meter's `ceiling_usd_day` in
budget.json: its share of the day's cap), and every line together with the fixed costs is the cap. With no profit and
Sail's fixed cost at $1.50 a day: fixed $1.66, the lane $3.00, research $0.34 (Sail $0.27, the Claude roles $0.07), the
$5 together; THE FLOOR below is exactly these lines.

EVERY LINE IS HELD, so every metered dollar stays under the cap (the review of r1/alarms, its major 1): Sail research by
the Sail guard (`sail_caps`: the day's research and Sail's own meter), the Claude roles by the router (the settings'
`budget` block hands it the ROLES' line only, `claude_usd_day`: 0.2 x rest, so no role can spend the lane's part), and
THE LANE'S VERDICTS by the House's event lane itself (league/events/house.py: a UTC day's verdicts at most the lower of
`events.verdict_usd_day` and `lane_allowance`, the Claude meter's lane part after its taper; over it a READ event waits,
PREREG-EVL-1 section 4). EVERY LINE ON ONE DAY (the review of r2/alarms, its major 1): each holder holds its line on the
UTC day, 00:00-24:00 UTC (the guard and the router from `now - now % 86400`, the lane from 00:00 UTC, this rule's day's
figure, `lane_spend`'s heaviest day), and the cap is judged on that same day (league/ops/metered.py), so the lines and
the fixed costs add up to the cap on the day judged; held on two days (the lane once held New York days), one day could
see two of a line. The fixed costs are measured (Sail's box billing over a week) and cannot be held; a day whose MEASURED
spend goes over its cap anyway (a fixed cost that rose, a line that leaked) is the stall job's `cap_breach`
(league/ops/metered.py measures each day's spend from the meters themselves), and THE CAP BREACH HOLD then holds every
line at 0 for the rest of that UTC day (`cap_hold`: the stall job writes `<state>/cap-hold.json` while what the
readings put inside today for certain is over today's cap; `lane_allowance`, `sail_caps` and `effective`, which the
settings' `budget` block of every swarm step comes from, each read it), so the cap holds after a leak instead of only
raising an alarm. A CHEAP DAY IS NEVER A FAILED DAY: the cap is what may be spent, never what must be (the stall job
raises no `underspend` under this rule, and no Done item reads spend). PREPAID CREDIT FIRST: the runway taper below spends each meter's prefund at most one part in
`RUNWAY_DAYS` a day, and nothing here buys anything.

What RULE_VERSION 2 read and this rule does not: the options-only trailing-30-day p30 (`book_p30` over 30 days, cut by
the close economics) and the no-forward-edge stop (`edge_state`): both are still gathered and written to budget.json's
`inputs` for the record, and neither moves a dollar. The owner's $25 ceiling of the goal of Oct 3 is the cap's upper
bound; its split now applies to the remainder only.

THE RUNWAY (unchanged from RULE_VERSION 2; changed only by the owner's own deploy; this file is FORBIDDEN to the
updater, `league/ci.py`). The `budget` job (after the close economics, and daily at 00:30 UTC) reads, for each meter m
in {sail, claude}:

- balance_m: Sail's balance as the Sail guard last read it well (its provider reading, kv `guard` in the swarm store:
  `last_good`, else `last`, at most `BALANCE_FRESH_SECONDS` old); Claude's funded total left at the gateway
  (`GET /v1/health`: its `remaining_usd`, else cap - spent, the holds in flight already inside spent);
- fixed_m: Sail: the billing of the House box's app over the trailing `FIXED_WINDOW_DAYS` days, a day, every box
  but the Gym pool's (research, booked as `gym_box`): the House, the data box and any other box the swarm books
  nowhere (`_sail_fixed`, since Oct 21, 2026; `SailboxClient.spend(app=...)`, either shape of Sail's response, its
  `cost_usd_nanos` or the legacy `estimated_total_cost_usd_nanos`); the House box's and the data box's own billing alone
  when the app or the pool cannot be read; never below `guard.house_burn_usd_day` (which is also the fallback); Claude: 0;
- reserve_m: never spent. Claude's is `RESERVE_USD`. Sail's is THE SAIL GUARD'S OWN RELEASE LINE
  (league/swarm/guard.py `house_line` over the `guard` settings: two days of the House's burn plus the guard's margin
  and its release margin, $37 at the configured burn), never under `RESERVE_USD`: under its line the guard brakes the
  whole swarm, the gate included, and pre-open fails, so the rule's zero point sits above it and research tapers to
  zero BEFORE the balance meets the brake. A line that cannot be read is no Sail research.

Then, a day:

    ceiling_m  = the meter's share of the day's cap (THE COST RULE above: Sail 0.8 x rest; Claude lane + 0.2 x rest)
    runway_m   = max(0, balance_m - reserve_m - RUNWAY_DAYS * fixed_m) / RUNWAY_DAYS
    research_m = min(ceiling_m, runway_m)            (Claude: the lane first, min(lane, runway_m); the roles get
                                                      min(0.2 x rest, runway_m - that), and `research_usd_day` is theirs)

so research runs at its share of the cap while a meter holds `RUNWAY_DAYS` days of it above its reserve and its fixed
cost, and below that it tapers by itself: each day a meter may spend one part in `RUNWAY_DAYS` of what it holds above
the reserve and `RUNWAY_DAYS` days of the House's own fixed cost, neither of which research ever spends. RULE_VERSION
1's two long terms (a 90-day target and a 60-day card line) are gone: this one short term is the whole runway rule.
Below, "the ceiling" of a meter is its share of the day's cap, and "THE OWNER'S CEILING" the $25 bound.

THE DAY'S FIGURE IS SET ONCE. The job runs twice on a session day, and its second reading has already paid for the
day's research: a taper recomputed from it would put the day's cap under what the day has booked, and the guard would
brake the gate with everything else until 00:00 UTC. So a meter's research for a UTC day is what the first run of that
day that could read the meter gave (`day_figure`). A later run the same day keeps it: it lowers nothing for today, and
records what its own reading would have set (`would_set_usd_day`), which the first run of the next UTC day sets from its
own reading. A meter that cannot be read is still no research at once (FAIL CLOSED); read again the same day, it is back
at the day's figure. Another version of the rule's file sets no day's figure.

THE TOP-UP RAISE (Oct 10, 2026; the no-captain audit's item 2). A later run whose own reading would set MORE than the
day's figure (the owner topped the meter up: on Oct 9 Sail research stayed at its tapered figure for ten hours after a
top-up, until the operator edited budget.json by hand, and the run after the close then put the old figure back) raises the
day's figure to that reading's own: today's research, the knobs and the guard's caps follow at once. It only ever
raises (a reading that would set less leaves the figure as it is, as above), never above the meter's share of the
ceiling, and from the reading as it stands (nothing added back: that reading has paid for the day so far, so the raise
is never more than a first run of the day on the topped-up balance would have set). The day's figure records the
figure it replaced and when (`raised_from`, `raised_at`, the last raise; `set_usd_day`, the day's first figure, and
`raises`, each raise's time and figures, so the stall job's `underspend` prices every hour of the day at the figure
that held then; `set_at` stays the first run's). A raise does not undo the day's earlier receipts: a day whose first
run tapered is still a taper day for DONE-RULE item 7. The House reads a top-up within the hour: the `budget_refresh`
job (`refresh`, hourly and at the House's start) runs this same rule and writes budget.json only when it raises a meter
or sets a day's figure no run has set yet.

A RAISE IS NEVER BOUGHT BY A FALLBACK (the review of the no-captain build, Oct 10, 2026). Sail's fixed cost falls back to
`guard.house_burn_usd_day` when the box spend cannot be read, and its reserve (the guard's release line) moves with it:
a reading made on a lower fallback has more room, and a raise from it would hold for the rest of the day. So the day's
figure keeps the fixed cost and the reserve it was set or last raised on (`fixed_usd_day`, `reserve_usd`; from the last
file's row for a figure written before them), and a raise is computed on the larger of those and this reading's own:
only more money, never a cheaper reading of the same money, raises the day's figure.

THE DAY'S FIRST RUN ADDS BACK WHAT THE DAY ALREADY PAID. When the first run of a UTC day comes late (the 00:30 run
missed, a deploy in the evening, a meter no earlier run could read), its reading has already paid for part of the day's
research, and a figure computed from it would sit under what the day has booked. So the run that SETS the day's figure
computes it from the balance as the day began: the reading plus what the meter has paid since 00:00 UTC
(`paid_today_usd`, `gather`). Sail's is the Sail guard's own meter of the day (the store's `metered_today`: every fall
of the balance since midnight, the research and the fixed cost alike), never more than the swarm's booked Sail
research today plus a day of fixed cost, and nothing when the reading is from before midnight. Claude's is the swarm's
Claude spend booked today, never under 0. Neither is ever more than the meter's share of the ceiling plus its fixed
cost a day, and what cannot be read is nothing added back. So a first run at 20:10 UTC sets the cap a run at 00:30
would have. Only the day's figure reads it: a later run's `would_set_usd_day`, the runway, the card line and the
notice are the reading as it stands.

NEVER ABOVE THE CEILING. Nothing lifts a meter over its share of the day's cap, nor the cap over THE OWNER'S CEILING of
$25: not a budget.json that says more (`read` holds each meter's research to its share of the $25, `ceiling_usd_day`:
Sail 20, the Claude roles 5, the most rule 3 can ever give either), not a setting (the overlay only tightens), not a
`budget` block handed to the Sail guard or the router by any other way (`sail_caps` and `paid_model_room` hold what
they are handed to the same share).

RULE_VERSION 2's PROFIT SHARE (kept for the record in `inputs`; rule 3 reads `week_net` instead, THE COST RULE above). p30 is
the trailing-30-day realized options P&L, fees in, every real route: this file's own read of the
live book's closed positions and the broker's posted fee corrections (`book_p30`), or `league.ops.economics.p30` over the
latest close summary (`economics.latest`) when that module is there, its summary is the latest close (`economics_fresh`)
and its number is SMALLER. The close economics may only cut what was earned, never raise it (it is FORBIDDEN too, a
second wall, not the only one); an unreadable book earns nothing whatever the economics says. Either read is UNKNOWN
(nothing earned, never the other read) while a position is closed but unpriced (`unpriced_close`), an order is pending or
unknown, reconciliation is frozen or the account reading names an event the book has not settled (`blocking`); so is a
fresh summary that cannot be inspected or holds no closes by day (`realized.by_close_day`). With no fresh summary the
book's read stands alone and the job says why (none yet, stale, not a summary, a read that failed). Marks never fund
research. Under RULE_VERSION 2, `earned = PROFIT_SHARE * max(0, p30) / 30` sat INSIDE the ceiling and lifted no meter;
under rule 3 `earned` is THE COST RULE's (from week_net) and lifts the cap, split across the meters as the cap is.

RULE_VERSION 2's NO-FORWARD-EDGE STOP (gathered for the record in `inputs.edge`; RETIRED by rule 3, whose cap follows
realized profit whatever promoted it): once `EDGE_SESSIONS` sessions have closed since `EDGE_START` (or since the day after the last
promotion to Probe, whichever is later) with no promotion to Probe, earned is 0 and the state says "no forward edge"; a
promotion lifts it. A promotion to Probe is one of two, each counted at its band move's time:
- THE LADDER'S: a `ladder_decisions` row (observe.sqlite) with verdict promote, the receipt the ladder settles only once
  its band landed (league/live/ladder.py). The `swarm.band` move to probe whose reason names that receipt (`LADDER_MARK`
  and its id, for the receipt's own family) is that same promotion. A band move whose receipt is pending, void, another
  family's or in no readable record is no promotion.
- THE LOOK'S (the fast lane): the Money table's move of a family from candidate to probe when the swarm's own record
  holds a passed holdout look of that family at or before the move (`looks`, passed): the first such move after each
  passed look. A move to probe from any other band (a demotion from Sized), one with no passed look behind it, and a
  return to Probe on a look already counted are none.

UNKNOWN IS NEVER MONEY. An unreadable balance, fixed cost or reserve gives its meter no research. An unreadable week_net
earns nothing (the cap is the $5); a lane store that cannot be read sizes the lane's part at `LANE_USD_DAY`.

THE WAIT FOR THE GUARD'S NEXT READING (L4, Oct 15, 2026; `_read_waiting`). A job run whose first read finds no fresh
guard reading (a House just started after a long outage, before the guard's first check) waits up to
`GUARD_WAIT_SECONDS` for the guard's next good reading, then reads every input again at a new instant. It never invents
a balance: with no reading by then, Sail is still unreadable, and the gateway's Sail reading is still the card line only.

THE OUTPUT, `<state>/budget.json` (private): the inputs, each meter's research $/day, the knob values, the direction
against the last file (cut, raise or same), each meter's reserve in force, its day's figure, what the run that set it
added back (`added_back_usd`; 0 on a later run) and what this run's own reading would have set, its runway at its
current total rate (fixed + research), its days of research left at the ceiling (`card_runway_days`: what it holds
above its reserve over `demand_usd_day`, its fixed cost plus its share of the ceiling), its next card action date
(`card_date`: when those days fall to `RUNWAY_DAYS`, the day the taper starts), the amount that buys `TOPUP_DAYS` more
days at the ceiling (`topup_usd`) and why. Rule 3 adds `cap` (week_net and its window and source, earned, the cap, each
fixed line, the room, the lane's part and its measured spend, the remainder) and, on the Claude meter, `lane_usd_day`
(the lane's part the meter carries, after its taper), `line_usd_day` (lane + roles, its share of the cap) and
`total_usd_day` (fixed + lane + roles: the rate its runway is read at).

ENFORCEMENT, TIGHTEN-ONLY (`overlay`, the last step of `league.swarm.settings.load` with a state root). The research
$/day become knob values (`knobs`), applied as min() against the configured `researcher.sail_usd_per_hour` (while that is
unset, against `researcher.usd_per_hour`, the combined pace that then governs Sail), `gym.max_boxes`, every
`claude.role_usd_day` line (and a line for each role in `claude.roles`) and `population.ceiling`, and as max() against
`architect.every_seconds` and `architect.refill_seconds` (each its own knob: a refill is faster than a scheduled pass;
while the tightened ceiling holds `population.start` down, every pass is a refill and the refill is held to the
scheduled cadence); `population.start` is held to the tightened ceiling. A configured value that is not a number is left
as it is (its reader already refuses it). The settings' `budget` block carries the $/day to the Sail guard (its daily
cap: the swarm's booked Sail today under the Sail research $/day, Sail's own meter today under that plus fixed;
`sail_caps`) and to the router (`paid_model_room`: Claude's room, and OpenAI's with it, is also capped by the Claude
research $/day less today's Claude and OpenAI spend, each model's counted on the day its hold was booked and never under
0: a hold released after 00:00 UTC lifts no line). A missing, unreadable or malformed budget.json, or one another
version of the format wrote (`SCHEMA`), is the FLOOR: THE COST RULE's own lines at no profit (`floor_lines`: research
$0.34, Sail $0.27 and the Claude roles $0.07, and the lane's verdicts $3.00), what runs until the rule has been read: it
FAILS CLOSED, never above what the rule itself gives a day with no profit. A STALE one (older than `STALE_SECONDS`: the budget job stopped) never loosens: each meter is the
lower of the floor and what the stale file said (0 for a meter it could not read), with a warning. An operator's own
`budget` key in swarm.json is replaced, never read. The ceiling knob never falls below `population.floor + BIRTH_MARGIN`
(a ceiling at the floor would freeze births and forks). OpenAI is not a meter of the rule, so the overlay closes it:
`guard.openai_cap_usd` is tightened to 0 (no OpenAI room) and the block says `openai_usd_day` 0. Handed settings with no
`budget` block, the Sail guard and the router read budget.json from their store's root themselves (`effective`; the
floor without a root): a caller that drops the block never lifts the budget.

THE GATE NEVER WAITS FOR MIDNIGHT (`gate_reserve`, `paid_model_reserve`). The last part of each day's dollars is kept for
the work that turns research into a verdict. On Sail: the last `GATE_RESERVE_SHARE` of the day's research dollars (at
least `GATE_RESERVE_MIN_USD`, never more than the day's) is for the tournament's validation round, the gate round and the
nightly forward; researcher cycles, births and the architect stop when the day's spend reaches the line under it, and
those three go on to the day's cap (league/swarm/guard.py `SailGuard.allows`). On the paid models the day's Claude line
is kept BY STAGE (`GATE_HOLDS_USD`, each sized for the largest hold the router books for it: the larger of the call's
need and its request's own worst case): every role but the gate's two leaves the review's hold and the audit's, and the
review leaves the audit's, so late in the day a review finds its hold and the audit still finds its own after that
review was paid.

THE FUNDING NOTICE. THE TWO-DAY LEAD (release D-1b, Oct 9, 2026; the owner's goal of Oct 9, item 3: "Tell me 2 days
before Sail or Claude runs out and I top it up"): when research on a meter RUNS OUT within `NOTICE_LEAD_DAYS` (2) at its
current burn (`out_in_days`, `_burn`: the burn is the larger of the rate the rule holds it to and the rate it was
spent at over the last `NEED_WINDOW_DAYS`; research runs out when the lower of its runway at that burn and its days of
research left at the ceiling, `card_runway_days`, falls to `RUNWAY_DAYS`, where the taper starts cutting it; at the
ceiling that is the card line `NOTICE_DAYS` = `RUNWAY_DAYS` + 2, the same instant as before), one `POST /v1/notify`
kind `funding` (`notice_facts`: the meter, its balance, the $/day it wants, those days, the amount that buys
`TOPUP_DAYS` more of them and the dates), at most ONCE A DAY per meter (`NOTICE_EVERY_SECONDS`, a day less an hour;
it was once a week; notice id `funding:<meter>:<UTC day>:r<rule version>`, which the gateway dedupes too, so never two
mails on one UTC day; `<state>/budget-notices.json` remembers what this version of the rule sent). The channel, the
facts' names and the gateway's composer are as before; a meter spent faster than the rule holds it states its burn in the
facts the mail reads (`notice_facts`: `current_*` at the burn, and the add-by `card_date` the day research runs out at
it), so the mail never says "nothing stops" or gives a late date while research runs out within the lead. Why "runs out" is
research's and not the balance's: while research tapers each day spends a fifth of what is left above the reserve, so
the balance never reaches it (Claude, with no fixed cost, never would) and a notice at "two days before the balance is
gone" would never be sent. The amount and its days go out under this rule's names (`topup_usd`, `topup_days`)
and, the same values, under RULE_VERSION 1's (`restore_usd`, `restore_days`): the gateway is its own deploy, and a
gateway still on that rule's composer must never mail an amount it could not read.
With no fresh guard reading, Sail's card line is read from the gateway's own Sail reading (`/v1/health`
`sail.balance_usd`): for the notice only, never for research. `drill` sends the same from a synthetic cliff in the
production shape (Claude's fixed cost 0) with `test: true`. A meter that cannot be read, a p30 from the fallback read or
unknown, and a notice not sent are each a House warning (`ctx.alert`).

Nothing here moves money, tops anything up or raises a cap: the owner pays, and the budget only ever tightens the
configured knobs. Standard library only (and `ltcm.data`'s computed NYSE calendar for the session count).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------------------------- the rule's constants
#: budget.json's format. 3 with RULE_VERSION 3 (2 with RULE_VERSION 2): a release on either side of the change reads the
#: other's file as no usable file (the floor) until its own budget job has run, so neither a deploy nor a rollback runs
#: on the other rule's dollars. The House's start runs the refresh, which runs the full job on another rule's file.
SCHEMA = 3
#: The rule's version (the constants below); a change is an owner deploy and a new number here. 3: the goal of Oct 19,
#: 2026, item 5 (THE COST RULE in the module docstring).
RULE_VERSION = 3
METERS = ("sail", "claude")
#: THE OWNER'S CEILING (his goal of Oct 3, 2026, kept by the goal of Oct 19, 2026: "never above $25"): the most every
#: metered compute dollar of a day may be, the fixed costs included (RULE_VERSION 2: research only).
CEILING_USD_DAY = 25.0
#: THE COST RULE (RULE_VERSION 3; the goal of Oct 19, 2026, item 4): the day's cap with no profit, every metered dollar
#: together (the fixed costs inside it); half the trailing week's realized net profit is added on top (`PROFIT_SHARE`):
#: THE TRAILING WEEK is the last `PROFIT_SESSIONS` (5) NYSE sessions that have closed (one trading week), and its half is
#: spread over the `PROFIT_DAYS` (7) calendar days a week of compute runs, so seven days at the cap spend at most half the
#: week's profit beyond the $5 a day.
BASE_USD_DAY = 5.0
PROFIT_SESSIONS = 5
PROFIT_DAYS = 7
#: The fixed metered lines that are not a Sail box (both inside the cap): Cloudflare's Workers plan ($5 a month, the
#: gateway and the site) a day, and market data a day (0: the owner cancelled ThetaData and Alpaca's Algo Trader Plus on
#: Oct 18, 2026; Alpaca's Basic plan is free; league/publish.py `SUBSCRIPTIONS_ENDED_AT` ends their past costs).
CLOUDFLARE_USD_DAY = round(5.0 * 12 / 365, 4)
DATA_USD_DAY = 0.0
#: THE LANE'S PART of the Claude line: the event lane's verdicts (PREREG-EVL-1 section 4; about $3 a day at the peak of
#: earnings season, goal-2026-10-19/EVL-DESIGN.md "Costs"), or `LANE_HEADROOM` times its heaviest UTC day of verdicts
#: over the trailing `LANE_WINDOW_DAYS` when that is more (the lane is held to its part, so its spend can never show a
#: need above the part: a day held at its line gives the next day half as much again); never more than the day's room.
#: The House's lane holds its verdicts to it (`lane_allowance`, league/events/house.py). The lane's store is
#: `<root>/events/events.sqlite` (league/events/store.py; the gateway's settled cost of each verdict in `verdicts.usd`).
LANE_USD_DAY = 3.0
LANE_HEADROOM = 1.5
LANE_WINDOW_DAYS = 7
LANE_STORE = Path("events") / "events.sqlite"
#: THE SPLIT, Sail 0.8 and Claude 0.2 (the operator's decision of Oct 9, 2026, about 16:00Z, an owner deploy; Sail 0.6
#: and Claude 0.4 from RULE_VERSION 2 of Oct 3 until then): the owner's $25 a day is Sail $20 and Claude $5 (it was $15
#: and $10). The ceiling itself does not move. Measured in production (read-only, the House's swarm store, Oct 7 19:30Z
#: to Oct 9 15:37Z): DeepSeek V4 Flash researched as well as Claude Sonnet 5.5 at 38x lower model cost per Train run and
#: 3.3x (95% CI 2.2-5.1) more families reaching the Train bar per research dollar (models plus Gym boxes, both windows
#: pooled); Claude's researchers produced no Validation pass (0 of 3 tries); the first real Probe trade
#: (eqp-realcalm-drift-call v17, 14:26Z Oct 9) was written entirely by Flash. The operator then turned the Claude
#: research band off (swarm.json `researcher.claude_top` 0, `claude.role_usd_day` researcher 0 and architect 0), so
#: Claude's remaining use is the gate's review and audit and the strategist (about $2 a day or less, estimated), with
#: the House's post-mortem and engineer inside the same meter; the unused Claude share moves to Sail, which buys the Gym
#: boxes and the Flash research. THE COST: Sail drains faster (about $21 a day with its fixed cost at the ceiling, from
#: about $16), so for the same balance its funding notice (two days before research runs out) comes sooner; Claude's
#: line is $5 a day, of which the gate's two holds keep $1.95 (`GATE_HOLDS_USD`), so every other Claude role shares at
#: most $3.05; and the floor of RULE_VERSION 2 ($5 split the same way: no usable budget.json, or a stale one) was Sail $4
#: and Claude $1, under the gate's two holds: at the floor the review finds no Claude room and runs on its Sail model,
#: and the audit does too unless its hold is at most the $1 (a large program's is up to $1.30), each stand-in with the
#: gate's own "not the plan's reviewer" alert (at the old floor's $2, one review and one audit of any size fitted on
#: Claude a day). RULE_VERSION 3 (the goal of Oct 19, 2026): the split applies to THE REMAINDER after the fixed costs and
#: the lane's part (`rest`, THE COST RULE), so at the $5 cap with no profit and Sail's fixed $1.50 a day the old research
#: roles share $0.34 a day (Sail $0.27, the Claude roles $0.07); Sail's research is at most 20 and the Claude roles' at
#: most 5 (the $25 ceiling's split, `ceiling_usd_day`). The floor is the rule's own lines at no profit (`floor_lines`).
SPLIT = {"sail": 0.8, "claude": 0.2}
#: The one runway term (days): research runs at the ceiling while a meter holds this many days of it above its reserve and
#: its fixed cost, and below that spends one part in this many of what it holds above them a day.
RUNWAY_DAYS = 5
#: THE FLOOR (the review of r1/alarms: it FAILS CLOSED): with no usable budget.json (none, unreadable, malformed, another
#: rule's) every line is THE COST RULE's own at no profit, on a Sail fixed cost of at least `FLOOR_SAIL_FIXED_USD_DAY`
#: (above the House box's measured $1.29-$1.50 a day, so the floor's lines and the real fixed cost never pass the $5
#: together): research $0.34 (Sail $0.27, the Claude roles $0.07) and the lane $3.00 (`floor_lines`); a STALE file gives
#: the lower of the floor and what it said. The rule's own answer is never held to it.
FLOOR_SAIL_FIXED_USD_DAY = 1.5
#: The share of trailing realized profit written as earned (inside the ceiling: the module docstring), and the window it is
#: read over (calendar days).
PROFIT_SHARE = 0.5
P30_DAYS = 30
#: The close economics' p30 is used while its cutoff is the latest session close (`economics_fresh`): no session closed
#: after it, other than one whose own economics may still be running (closed less than `ECONOMICS_LAG_SECONDS` ago:
#: the job's three-hour grace and its half-hour wall). Measured in sessions, not hours, so a weekend or a holiday keeps
#: Friday's close fresh; a missed close falls back to the book. Without a calendar, `P30_FRESH_SECONDS` of wall time.
ECONOMICS_LAG_SECONDS = 3 * 3600 + 1800
P30_FRESH_SECONDS = 4 * 86400
#: Dollars on each meter research never spends, at the least. Sail's reserve in force is the Sail guard's own release
#: line when that is higher (`gather`: league/swarm/guard.py `house_line`), so the taper ends above the guard's brake.
RESERVE_USD = {"sail": 10.0, "claude": 5.0}
#: The no-forward-edge stop: this many sessions closed since `EDGE_START` (or the last promotion to Probe) without one.
EDGE_START = dt.date(2026, 10, 5)
EDGE_SESSIONS = 60
#: The options record's financial basis (league/config.json `performance.start_at`): nothing opened before it is P&L.
PNL_BASIS = "2026-09-26T06:25:30Z"
#: Windows for Sail's fixed boxes and for each meter's research spend (need), days.
FIXED_WINDOW_DAYS = 7
NEED_WINDOW_DAYS = 7
#: The Sail guard's balance reading older than this is no reading.
BALANCE_FRESH_SECONDS = 6 * 3600
#: THE WAIT FOR THE GUARD'S NEXT READING (L4, Oct 15, 2026; `_read_waiting`). A `budget` run that finds no fresh guard
#: reading waits at most this long from its start for the guard's next good one, looking at the guard's kv every
#: `GUARD_POLL_SECONDS`, then reads every input again at a new instant. The job's wall is 600 s (league/ops/registry.py):
#: the first read, the wait and the second read end well inside it (a test holds the room the wall leaves). Not a rule
#: constant: it decides when the run reads, never what a reading gives.
GUARD_WAIT_SECONDS = 270
GUARD_POLL_SECONDS = 20
#: The ladder's own promotion reason carries this and its receipt's id (league/live/ladder.py: "the forward ladder
#: promoted it (practice receipt N)"); a move to probe without it is not a ladder promotion, and one with it is one only
#: as that receipt's, settled (`_swarm_reads`).
LADDER_MARK = "practice receipt"
_NAMED_RECEIPT = re.compile(re.escape(LADDER_MARK) + r" (\d+)")
#: The look's own promotion (the fast lane): the Money table's move from this band to Probe, for a family with a passed
#: holdout look in the swarm's record (`_swarm_reads`).
LOOK_BAND = "candidate"
#: A budget.json older than this never loosens (`stale_block`: each meter the lower of the floor and what it said).
STALE_SECONDS = 36 * 3600
#: A funding notice per meter at most once a day (release D-1b, Oct 9, 2026; the owner's goal of Oct 9, item 3: "Tell me 2
#: days before Sail or Claude runs out and I top it up"; it was once a week, `7 * 86400`, which could leave a short meter
#: unmentioned for six days after a top-up that fell short): at least this long after the last one (a day less an hour,
#: so the daily 00:30Z run that starts a few seconds earlier than yesterday's still tells), under its UTC day's notice id
#: (which the gateway dedupes: never two mails on one UTC day).
NOTICE_EVERY_SECONDS = 23 * 3600
#: THE TWO-DAY LEAD (release D-1b): a meter is told when research on it at its current burn runs out within this many
#: days (`out_in_days`: the day its days of research left at the burn fall to `RUNWAY_DAYS`, where the rule's taper
#: starts cutting it), so the owner's top-up lands before research falls under the ceiling.
NOTICE_LEAD_DAYS = 2
#: The card line: a meter with fewer days of research left at the ceiling is told (`NOTICE_LEAD_DAYS` before its taper
#: starts at `RUNWAY_DAYS`), and the notice says what buys this many more days.
NOTICE_DAYS = RUNWAY_DAYS + NOTICE_LEAD_DAYS
TOPUP_DAYS = 7
#: THE GATE'S RESERVE on Sail: this share of the day's Sail research dollars, never under the minimum (and never more than
#: the day's), is kept for the tournament's validation round, the gate round and the nightly forward (`gate_reserve`).
GATE_RESERVE_SHARE = 0.10
GATE_RESERVE_MIN_USD = 0.50
#: THE GATE'S HOLDS on the paid models: the most the router books for one review and one audit (league/swarm/models.py:
#: the larger of the call's need, $0.50 and `gate.audit_need_usd`'s $1.00 in league/swarm/gate.py, and its request's
#: own worst case, `league.claude.reservation_ceiling`), sized for the largest program the Gym accepts on the committed
#: policy (about $0.59 and $1.17 at 60,000 characters). Kept inside the day's Claude line by stage (`paid_model_reserve`).
GATE_HOLDS_USD = {"review": 0.65, "audit": 1.30}
#: The gate's stages in their order: a call leaves the holds of the stages after its own.
GATE_STAGES = ("review", "audit")
#: The swarm's Sail spend kinds (league/swarm/guard.py SWARM_SAIL_KINDS) and the paid models' (Claude's line holds
#: OpenAI too: `paid_model_room`).
SAIL_KINDS = ("sail_model", "gym_box")
CLAUDE_KINDS = ("claude", "openai")
#: The spend kind Claude's own meter pays (the gateway's funded total): what THE DAY'S FIRST RUN ADDS BACK on Claude.
PAID_CLAUDE_KIND = "claude"

# ---------------------------------------------------------------------------------------------- the knobs' constants
#: The Sail research dollars that buy Gym boxes (the rest buys Sail models: measured Oct 2, about 60/40).
GYM_SHARE = 0.6
#: A busy Gym box's cost an hour, and the busy hours a day one budgeted box is planned for.
BOX_USD_HOUR = 0.20
BOX_DUTY_HOURS = 8.0
#: Research dollars a day per living family, and the population ceiling's least value.
FAMILY_USD_DAY = 1.0
CEILING_MIN = 8
#: The ceiling knob's least margin over the configured `population.floor`: room for births and forks at the floor.
BIRTH_MARGIN = 4
#: The architect's cadence follows the research dollars a day (both meters together): a scheduled pass every
#: `ARCHITECT_USD_SECONDS` / dollars seconds (4 hours at $5, 48 minutes at $25) and a refill pass (the population under
#: its start) every `REFILL_USD_SECONDS` / dollars seconds (96 minutes at $5, about 19 at $25), never faster than the two
#: minimums, and once a day with no research dollars at all (also the slowest either ever is). RULE_VERSION 1 scaled by
#: the floor, so no dollars made it faster than 4 hours; these constants hold whatever the ceiling is.
ARCHITECT_USD_SECONDS = 72000.0
REFILL_USD_SECONDS = 28800.0
ARCHITECT_MIN_SECONDS = 1800
REFILL_MIN_SECONDS = 900
ARCHITECT_IDLE_SECONDS = 86400

BUDGET_FILE = "budget.json"
NOTICES_FILE = "budget-notices.json"
#: THE CAP BREACH HOLD (release 1019c; the review of r2/alarms, its major 1): the stall job's measured breach of today's
#: cap (league/ops/metered.py `write_hold`: {schema, day, at, since, spent_usd, cap_usd}), read by every line this rule
#: holds (`cap_hold`).
HOLD_FILE = "cap-hold.json"
HOLD_SCHEMA = 1
EPSILON = 0.005
#: THE TOP-UP RAISE: the raises of a day a day's figure keeps (`raises`; the refresh runs hourly, so a day has at most 25).
RAISES_KEPT = 32


# ---------------------------------------------------------------------------------------------- small helpers
def _finite(value: Any) -> float | None:
    """A finite number (a numeric string counts; a bool does not), else None."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _amount(value: Any) -> float | None:
    """A finite, non-negative number, else None."""
    out = _finite(value)
    return out if out is not None and out >= 0 else None


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(float(epoch), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(text: Any) -> float | None:
    try:
        at = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (at if at.tzinfo is not None else at.replace(tzinfo=dt.timezone.utc)).timestamp()


def _day(epoch: float) -> dt.date:
    return dt.datetime.fromtimestamp(float(epoch), dt.timezone.utc).date()


def _day_start(epoch: float) -> float:
    """00:00 UTC of the day `epoch` is in: the Sail guard's and the router's own day."""
    return float(epoch) - float(epoch) % 86400


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _read_only(path: Path) -> sqlite3.Connection:
    """A read-only connection: the caller fetches, then closes before any other I/O."""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def ceiling_usd_day(meter: str) -> float:
    """One meter's share of THE OWNER'S CEILING, dollars a day: the most its research ever is (RULE_VERSION 3: Sail's
    research and the Claude ROLES' line at the $25 cap with nothing fixed; the lane's part rides apart, `cost_rule`)."""
    return round(CEILING_USD_DAY * SPLIT[meter], 4)


def cost_rule(week_net: Any, sail_fixed: Any, lane_peak: Any = None) -> dict[str, Any]:
    """THE COST RULE (RULE_VERSION 3; the module docstring's ARITHMETIC) for one reading, pure: from the trailing week's
    realized net profit of every real book (`week_net`, the last `PROFIT_SESSIONS` sessions', dollars; None is unknown:
    nothing earned), Sail's fixed cost a day and the lane's heaviest UTC day of verdicts over the trailing week
    (`lane_peak`; None reads as none):

        earned = 0.5 x max(0, week_net) / 7;  cap = min(25, 5 + earned);  room = max(0, cap - fixed);
        lane = min(room, max(3, 1.5 x lane_peak));  rest = room - lane, split Sail 0.8 and Claude 0.2

    as {earned_usd_day, cap_usd_day, fixed_usd_day (every fixed line), fixed (each), room_usd_day, lane_usd_day,
    rest_usd_day, line_usd_day: {sail, claude (lane + roles)}, roles_usd_day: {sail, claude}}. A Sail fixed cost that is
    not a number is no room at all (unknown is never money): every line is 0."""
    value = _finite(week_net)
    earned = 0.0 if value is None else PROFIT_SHARE * max(0.0, value) / PROFIT_DAYS
    cap = min(CEILING_USD_DAY, BASE_USD_DAY + earned)
    sail = _amount(sail_fixed)
    fixed = {"sail": None if sail is None else round(sail, 4), "cloudflare": CLOUDFLARE_USD_DAY, "data": DATA_USD_DAY}
    total_fixed = None if sail is None else sail + CLOUDFLARE_USD_DAY + DATA_USD_DAY
    room = 0.0 if total_fixed is None else max(0.0, cap - total_fixed)
    peak = _amount(lane_peak)
    want = max(LANE_USD_DAY, LANE_HEADROOM * (peak or 0.0))
    lane = min(room, want)
    rest = max(0.0, room - lane)
    roles = {m: rest * SPLIT[m] for m in METERS}
    return {"week_net_usd": value, "earned_usd_day": round(earned, 4), "cap_usd_day": round(cap, 4),
            "base_usd_day": BASE_USD_DAY, "fixed_usd_day": None if total_fixed is None else round(total_fixed, 4),
            "fixed": fixed, "room_usd_day": round(room, 4), "lane_usd_day": round(lane, 4),
            "lane_peak_usd_day": None if peak is None else round(peak, 4), "lane_want_usd_day": round(want, 4),
            "rest_usd_day": round(rest, 4), "roles_usd_day": {m: round(roles[m], 4) for m in METERS},
            "line_usd_day": {"sail": round(roles["sail"], 4), "claude": round(lane + roles["claude"], 4)}}


def floor_lines(house_burn: Any = None) -> dict[str, Any]:
    """THE FLOOR (no usable budget.json): THE COST RULE's own lines at no profit, on Sail's fixed cost at the larger of
    `house_burn` (the guard's configured `house_burn_usd_day`, when given) and `FLOOR_SAIL_FIXED_USD_DAY`: never more,
    with the real fixed cost, than the $5 the rule allows a day with no profit (it FAILS CLOSED)."""
    burn = _amount(house_burn)
    return cost_rule(0.0, max(FLOOR_SAIL_FIXED_USD_DAY, burn if burn is not None else 0.0))


def floor_usd_day(meter: str) -> float:
    """The floor's dollars a day for one meter's research (`floor_lines`: the roles' no-profit line): what it runs on with
    no usable budget.json, and the most a stale one gives."""
    return floor_lines()["roles_usd_day"][meter]


def floor_lane_usd_day() -> float:
    """The floor's line for the event lane's verdicts (`floor_lines`): the lane's part a day with no profit."""
    return floor_lines()["lane_usd_day"]


def gate_reserve(research_usd_day: Any) -> float:
    """THE GATE'S RESERVE on Sail for a day of `research_usd_day` dollars: `GATE_RESERVE_SHARE` of them, at least
    `GATE_RESERVE_MIN_USD`, never more than the day's. 0 for a figure that is not a number of zero or more."""
    research = _amount(research_usd_day)
    if research is None:
        return 0.0
    return round(min(research, max(GATE_RESERVE_MIN_USD, GATE_RESERVE_SHARE * research)), 4)


def paid_model_reserve(role: Any) -> float:
    """THE GATE'S HOLDS a paid-model call for `role` leaves inside the day's Claude line, BY STAGE: the audit (the last
    stage) leaves none, the review leaves the audit's (a review never spends the hold of the audit that follows it), and
    every other role leaves both (`GATE_HOLDS_USD`). None (no role named: a reading of the line itself, never an
    admission) leaves none."""
    if role is None:
        return 0.0
    later = GATE_STAGES[GATE_STAGES.index(role) + 1:] if role in GATE_STAGES else GATE_STAGES
    return round(sum(GATE_HOLDS_USD[stage] for stage in later), 4)


# ---------------------------------------------------------------------------------------------- the rule
def edge_state(now: float, promotions: list[float] | None) -> dict[str, Any]:
    """THE NO-FORWARD-EDGE STOP: sessions closed since the later of `EDGE_START` and the day after the last promotion
    to Probe (`promotions`: their epochs, the ladder's and the look's alike; None when the record could not be read,
    counted as none). A calendar that cannot count is the stop (unknown is never money)."""
    from ltcm.data import us_equity_session

    anchor, last = EDGE_START, None
    if promotions:
        last = max(promotions)
        anchor = max(EDGE_START, _ny_day(last) + dt.timedelta(days=1))
    out: dict[str, Any] = {"anchor": anchor.isoformat(), "last_promotion": None if last is None else _iso(last),
                           "promotions_readable": promotions is not None}
    try:
        count, day, end = 0, anchor, _ny_day(now)
        while day <= end:
            session = us_equity_session(day)
            if session is not None and (_epoch(session.close_at) or float("inf")) <= now:
                count += 1
            day += dt.timedelta(days=1)
    except Exception as exc:  # noqa: BLE001 - a calendar that cannot count is the stop
        out.update(sessions=None, stop=True, why=f"the session calendar could not count ({type(exc).__name__}): earned is 0")
        return out
    stop = count >= EDGE_SESSIONS
    out.update(sessions=count, stop=stop,
               why=(f"{count} sessions since {anchor} with no promotion to Probe: no forward edge; nothing earned" if stop
                    else f"{count} of {EDGE_SESSIONS} sessions since {anchor} without a promotion to Probe"))
    if promotions is None:
        out["why"] += " (the promotion record could not be read: counted as none)"
    return out


def _ny_day(epoch: float) -> dt.date:
    from zoneinfo import ZoneInfo

    return dt.datetime.fromtimestamp(float(epoch), ZoneInfo("America/New_York")).date()


def _date_after(today: dt.date, days: float) -> str:
    """The date `days` after `today` (never before it, and at most a century on: a balance no calendar holds is a date
    far away, never an error)."""
    return (today + dt.timedelta(days=min(36500.0, max(0.0, days)))).isoformat()


def _card(balance: float, fixed: float, demand: float, reserve: float, today: dt.date) -> dict[str, Any]:
    """THE CARD LINE of one meter, at the rate it WANTS (`demand`: fixed + its share of the ceiling), never at the rate
    the rule tapered it to (the taper holds that runway near `RUNWAY_DAYS` by construction, so it would hide a short
    prefund): its days of research left at the ceiling (what it holds above its reserve over `demand`), the card action
    date (when those days fall to `RUNWAY_DAYS`: the day the taper starts) and the amount that buys `TOPUP_DAYS` more of
    them (with what a meter under its reserve lacks to reach it)."""
    room = balance - reserve
    # A meter that wants nothing a day (RULE_VERSION 3: its share of a cap the fixed costs fill) lasts a century.
    runway = 0.0 if room <= 0 else (room / demand if demand > 0 else 36500.0)
    return {"demand_usd_day": round(demand, 4), "card_runway_days": round(runway, 1),
            "card_date": _date_after(today, runway - RUNWAY_DAYS), "card_runs_out_on": _date_after(today, runway),
            "topup_usd": round(max(0.0, -room) + TOPUP_DAYS * demand, 2)}


def _burn(room: float, fixed: float, rate: float, need: float, card_days: float, today: dt.date) -> dict[str, Any]:
    """THE CURRENT BURN of one readable meter (release D-1b, the two-day lead): `burn_usd_day`, the larger of the rate the
    rule holds it to today (`rate`: its fixed cost plus the day's research figure) and the rate it was spent at (its fixed
    cost plus its research spend over the trailing `NEED_WINDOW_DAYS` days, a day: a meter spent faster than the rule
    holds it is read at that); `burn_runway_days`, what it holds above its reserve at that burn; and `out_in_days`, the
    days until research on it RUNS OUT at the current burn: until the lower of that runway and its days of research left
    at the ceiling (`card_days`) falls to `RUNWAY_DAYS`, where the taper starts cutting research (0 once it has: research
    is being cut now), with its date `out_on`. While research tapers the balance itself never reaches the reserve (each
    day spends a fifth of what is left above it), so "runs out" is research's, not the balance's."""
    burn = max(rate, fixed + max(0.0, need) / NEED_WINDOW_DAYS)
    runway = 0.0 if room <= 0 else (room / burn if burn > 0 else None)
    left = card_days if runway is None else min(card_days, runway)
    out = max(0.0, left - RUNWAY_DAYS)
    return {"burn_usd_day": round(burn, 4), "burn_runway_days": None if runway is None else round(runway, 1),
            "out_in_days": round(out, 1), "out_on": _date_after(today, out)}


def _reserve(given: Mapping[str, Any], meter: str) -> float | None:
    """The reserve in force for `meter`: `RESERVE_USD`, or the inputs' own `reserve_usd` when that is higher (Sail's: the
    Sail guard's release line, `gather`). None when the inputs name one that is not a number: unknown is never money."""
    if "reserve_usd" not in given:
        return RESERVE_USD[meter]
    said = _amount(given.get("reserve_usd"))
    return None if said is None else max(RESERVE_USD[meter], said)


def _day_figure(previous: Any, meter: str, today: dt.date) -> dict[str, Any] | None:
    """THE DAY'S FIGURE an earlier run of this UTC day set for `meter`, from the last budget.json: {day, usd_day,
    limited_by, set_at}, the dollars never above the meter's share of the ceiling. None when there is none: no file,
    another version of the rule's, another day's, or one that does not read."""
    if not isinstance(previous, Mapping) or previous.get("schema") != SCHEMA or previous.get("rule_version") != RULE_VERSION:
        return None
    meters = previous.get("meters")
    row = meters.get(meter) if isinstance(meters, Mapping) else None
    figure = row.get("day_figure") if isinstance(row, Mapping) else None
    if not isinstance(figure, Mapping) or figure.get("day") != today.isoformat():
        return None
    usd = _amount(figure.get("usd_day"))
    if usd is None or figure.get("limited_by") not in ("ceiling", "runway"):
        return None
    out = {"day": today.isoformat(), "usd_day": round(min(usd, ceiling_usd_day(meter)), 4),
           "limited_by": figure["limited_by"], "set_at": figure.get("set_at")}
    # A RAISE IS NEVER BOUGHT BY A FALLBACK: the fixed cost and the reserve the figure was set or last raised on (a figure
    # written before them: the last file's own row, the reading that wrote it).
    for key in ("fixed_usd_day", "reserve_usd"):
        value = _amount(figure.get(key))
        value = _amount(row.get(key)) if value is None else value
        if value is not None:
            out[key] = round(value, 4)
    # THE TOP-UP RAISE: the figure a raise replaced and when, carried with the day's figure; the day's first figure and
    # every raise of the day (the stall job's `underspend` prices each hour at the figure that held then).
    raised_from = _amount(figure.get("raised_from"))
    if raised_from is not None and isinstance(figure.get("raised_at"), str):
        out.update(raised_from=round(raised_from, 4), raised_at=figure["raised_at"])
        first = _amount(figure.get("set_usd_day"))
        steps = [{"at": r["at"], "from": round(_amount(r.get("from")), 4), "to": round(_amount(r.get("to")), 4)}
                 for r in (figure.get("raises") if isinstance(figure.get("raises"), list) else [])
                 if isinstance(r, Mapping) and isinstance(r.get("at"), str) and _amount(r.get("from")) is not None
                 and _amount(r.get("to")) is not None]
        out.update(set_usd_day=round(first if first is not None else raised_from, 4),
                   raises=steps[-RAISES_KEPT:] or [{"at": figure["raised_at"], "from": round(raised_from, 4),
                                                    "to": out["usd_day"]}])
    return out


def compute(inputs: Mapping[str, Any], *, now: float, previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """budget.json from the rule's inputs (`gather`'s shape):

        {"week_net_usd": float | None, "week_net_source": str, "week_net_since": str | None (RULE_VERSION 3: THE COST
         RULE's trailing week), "lane": {"usd_day": float | None (the lane's measured verdict spend a day, the trailing
         week's mean), "peak_usd_day": float | None (its heaviest UTC day of them), "today_usd": float, "source": str},
         "p30_usd", "p30_source", "edge": RULE_VERSION 2's figures, kept for the record and read by nothing here,
         "meters": {m: {"balance_usd": float | None, "fixed_usd_day": float | None, "need_usd": float,
                        "reserve_usd": float | None (Sail: the Sail guard's release line; absent: `RESERVE_USD`),
                        "paid_today_usd": float | None (what the meter has paid since 00:00 UTC; absent: nothing),
                        "notice_balance_usd": float | None (Sail with no guard reading: the card line only), ...sources}}}

    THE COST RULE (`cost_rule`) sets the day's cap and each meter's share of it (its `ceiling_usd_day`: Sail 0.8 x the
    remainder, Claude the lane's part + 0.2 x the remainder); each meter's runway taper then holds it to what its prefund
    holds (the Claude meter pays the lane's part first; its `research_usd_day` is the roles' line, what the router reads).
    `previous` is the last budget.json: for the direction, and for THE DAY'S FIGURE (a meter an earlier run of this UTC
    day read keeps that run's research: `_day_figure`; THE TOP-UP RAISE lifts it to this run's reading when that is
    more: a top-up, or a close whose profit lifted the cap). The run that sets a meter's figure ADDS BACK what the meter
    has paid since 00:00 UTC (`paid_today_usd`, never more than its share of the cap plus its fixed cost a day): the
    figure is from the balance as the day began, whenever in the day the first run comes. Pure: no I/O."""
    meters_in = inputs.get("meters") or {}
    lane_in = inputs.get("lane") if isinstance(inputs.get("lane"), Mapping) else {}
    sail_fixed = _amount((meters_in.get("sail") or {}).get("fixed_usd_day"))
    cost = cost_rule(inputs.get("week_net_usd"), sail_fixed, lane_in.get("peak_usd_day"))
    week_net, earned = cost["week_net_usd"], cost["earned_usd_day"]
    why: list[str] = []
    if week_net is None:
        why.append("week_net unreadable: nothing earned, the cap is the base")
    elif week_net > 0:
        why.append(f"week_net {week_net:.2f} over the last {PROFIT_SESSIONS} sessions: earned 0.5 x {week_net:.2f} / "
                   f"{PROFIT_DAYS} = {earned:.4f} a day, the cap {cost['cap_usd_day']:.2f}")
    else:
        why.append(f"week_net {week_net:.2f} is not a profit: nothing earned, the cap is the base")
    if cost["fixed_usd_day"] is None:
        why.append("Sail's fixed cost could not be read: no room under the cap")
    why.append(f"the cap {cost['cap_usd_day']:.2f} a day: fixed {cost['fixed_usd_day'] or 0.0:.2f}, the lane's verdicts "
               f"{cost['lane_usd_day']:.2f}, research {cost['rest_usd_day']:.2f}")
    lane_measured = _amount(lane_in.get("usd_day")) or 0.0
    needs = {m: _amount((meters_in.get(m) or {}).get("need_usd")) or 0.0 for m in METERS}
    # The Claude meter's own spend rate includes the lane's verdicts (the swarm books none of them).
    needs["claude"] += lane_measured * NEED_WINDOW_DAYS
    total_need = sum(needs.values())
    shares = {m: needs[m] / total_need for m in METERS} if total_need > 0 else dict(SPLIT)
    today = _day(now)
    meters: dict[str, Any] = {}
    for m in METERS:
        given = meters_in.get(m) or {}
        balance, fixed, reserve = _finite(given.get("balance_usd")), _amount(given.get("fixed_usd_day")), _reserve(given, m)
        ceiling = cost["line_usd_day"][m]       # the meter's share of the day's cap (Claude: the lane's part + roles)
        roles_line = cost["roles_usd_day"][m]   # what research (the old roles) may have of it
        lane = cost["lane_usd_day"] if m == "claude" else 0.0
        kept = _day_figure(previous, m, today)  # what an earlier run of this UTC day set: it stands
        row: dict[str, Any] = {"balance_usd": balance, "fixed_usd_day": fixed, "reserve_usd": reserve,
                               "ceiling_usd_day": round(ceiling, 4), "day_figure": kept,
                               "need_share": round(shares[m], 4), "earned_usd_day": round(earned * shares[m], 4)}
        if m == "claude":
            row["line_usd_day"] = round(ceiling, 4)
        if balance is None or fixed is None or reserve is None:
            # FAIL CLOSED, at once: the day's figure (kept in the row) stands again only when the meter reads again.
            row.update(research_usd_day=0.0, limited_by="unreadable", runway_days=None, card_date=None,
                       total_usd_day=None, topup_usd=None, demand_usd_day=None, card_runway_days=None, would_set_usd_day=None,
                       added_back_usd=None)
            if m == "claude":
                row["lane_usd_day"] = 0.0
            what = "balance" if balance is None else "fixed cost" if fixed is None else "reserve"
            why.append(f"{m}: the {what} could not be read: no research")
            seen = _finite(given.get("notice_balance_usd"))
            if seen is not None and fixed is not None and reserve is not None:
                # The card line only (never research): the owner still hears of a prefund running short.
                row.update(_card(seen, fixed, fixed + ceiling, reserve, today), card_balance_usd=seen,
                           card_balance_source=given.get("notice_balance_source"))
                why.append(f"{m}: its card line is read from {given.get('notice_balance_source') or 'another reading'}")
            meters[m] = row
            continue
        room = balance - reserve
        added = 0.0
        if kept is None:
            # The first run of this UTC day to read the meter sets the day's figure, FROM THE BALANCE AS THE DAY BEGAN:
            # what the meter has paid since 00:00 UTC is added back, so a late first run sets the cap an early one would
            # have. Unknown is nothing added; never more than a day's own most (its share of the cap and its fixed cost).
            added = min(_amount(given.get("paid_today_usd")) or 0.0, ceiling + fixed)
        runway_cap = max(0.0, room + added - RUNWAY_DAYS * fixed) / RUNWAY_DAYS
        # THE LANE FIRST (Claude): the lane's part is paid before any role; the roles get what the taper leaves of theirs.
        lane_paid = min(lane, runway_cap)
        research = min(roles_line, max(0.0, runway_cap - lane_paid))  # never above its share, whatever was earned
        limited = "ceiling" if runway_cap >= ceiling else "runway"  # the taper: under RUNWAY_DAYS days of its share
        would_set = research
        raised = None
        if kept is None:
            kept = {"day": today.isoformat(), "usd_day": round(research, 4), "limited_by": limited, "set_at": _iso(now),
                    "fixed_usd_day": round(fixed, 4), "reserve_usd": round(reserve, 4)}
        else:
            # THE TOP-UP RAISE, NEVER BOUGHT BY A FALLBACK: this reading's room (nothing added back) on the larger of its
            # own fixed cost and reserve and those the day's figure was set or last raised on.
            floor_fixed = max(fixed, _amount(kept.get("fixed_usd_day")) or 0.0)
            floor_reserve = max(reserve, _amount(kept.get("reserve_usd")) or 0.0)
            raise_cap = max(0.0, balance - floor_reserve - RUNWAY_DAYS * floor_fixed) / RUNWAY_DAYS
            lifted = min(roles_line, max(0.0, raise_cap - min(lane, raise_cap)))
            if lifted > kept["usd_day"] + EPSILON:
                # The figure is raised to it, never above its share (`lifted` is held to it), and never lowered.
                raised = kept["usd_day"]
                at_ = _iso(now)
                steps = [dict(r) for r in kept.get("raises") or []]
                research, limited = lifted, "ceiling" if raise_cap >= ceiling else "runway"
                kept = {"day": today.isoformat(), "usd_day": round(research, 4), "limited_by": limited,
                        "set_at": kept.get("set_at"), "fixed_usd_day": round(floor_fixed, 4),
                        "reserve_usd": round(floor_reserve, 4), "raised_from": raised, "raised_at": at_,
                        "set_usd_day": first if (first := _amount(kept.get("set_usd_day"))) is not None else raised,
                        "raises": (steps + [{"at": at_, "from": raised, "to": round(research, 4)}])[-RAISES_KEPT:]}
            else:  # THE DAY'S FIGURE IS SET ONCE: this reading has paid for the day's research, and lowers nothing
                research, limited = kept["usd_day"], kept["limited_by"]
        rate = fixed + lane_paid + research
        if room <= 0:
            runway = 0.0
        elif rate > 0:
            runway = room / rate
        else:
            runway = None  # nothing is spent: no runway to run out
        row.update(runway_cap_usd_day=round(runway_cap, 4), research_usd_day=round(research, 4),
                   would_set_usd_day=round(would_set, 4), day_figure=kept, added_back_usd=round(added, 4),
                   wanted_research_usd_day=round(roles_line, 4), limited_by=limited, total_usd_day=round(rate, 4),
                   runway_days=None if runway is None else round(runway, 1),
                   runs_out_on=None if runway is None else _date_after(today, runway),
                   **_card(balance, fixed, fixed + ceiling, reserve, today))
        if m == "claude":
            row["lane_usd_day"] = round(lane_paid, 4)
        row.update(_burn(room, fixed, rate, needs[m], row["card_runway_days"], today))
        if limited == "runway":
            why.append(f"{m}: under {RUNWAY_DAYS} days of its share of the cap: research {research:.4f} of "
                       f"{roles_line:.2f} a day" + (f", the lane's part {lane_paid:.4f} of {lane:.2f}" if lane else ""))
        if added > EPSILON:
            why.append(f"{m}: the day's first run: the {added:.4f} the meter has paid since 00:00 UTC is added back (the "
                       "day's figure is from the balance as the day began)")
        if raised is not None:
            why.append(f"{m}: the top-up raise: today's figure {raised:.4f} is raised to this run's reading, {research:.4f} "
                       f"a day ({limited}); a raise only, never above its share of the cap")
        if raised is None and abs(would_set - research) > EPSILON:
            why.append(f"{m}: today's figure stands ({research:.4f} a day, set at {kept['set_at']}); this run's reading "
                       f"would set {would_set:.4f}")
        meters[m] = row
    total = round(sum(meters[m]["research_usd_day"] for m in METERS), 4)
    before = _finite((previous or {}).get("research_usd_day")) if isinstance(previous, Mapping) else None
    direction = "same" if before is None or abs(total - before) <= EPSILON else ("raise" if total > before else "cut")
    for m in METERS:
        was = _finite((((previous or {}).get("meters") or {}).get(m) or {}).get("research_usd_day")) \
            if isinstance(previous, Mapping) else None
        now_m = meters[m]["research_usd_day"]
        meters[m]["direction"] = "same" if was is None or abs(now_m - was) <= EPSILON else ("raise" if now_m > was else "cut")
    limits = {meters[m]["limited_by"] for m in METERS}
    if total <= 0:
        state = "no research"  # every meter unreadable or tapered to 0, or the fixed costs and the lane fill the cap
    elif limits == {"ceiling"}:
        state = "research at its share of the day's cap"
    else:
        state = "research under its share of the day's cap"  # a meter tapers (`runway`) or could not be read
    state += (f" (the cap {cost['cap_usd_day']:.2f} a day: fixed {cost['fixed_usd_day'] or 0.0:.2f}, the lane's verdicts "
              f"{cost['lane_usd_day']:.2f}, research {cost['rest_usd_day']:.2f})")
    if before is None:
        why.append("no earlier budget to compare")
    else:
        why.append(f"research {direction} ({before:.4f} -> {total:.4f} a day)")
    cap = {**cost, "week_net_source": inputs.get("week_net_source"), "week_net_since": inputs.get("week_net_since"),
           "sessions": PROFIT_SESSIONS, "lane_today_usd": _amount(lane_in.get("today_usd")),
           "lane_source": lane_in.get("source")}
    return {"schema": SCHEMA, "rule_version": RULE_VERSION, "at": float(now), "at_iso": _iso(now),
            "rule": {"ceiling_usd_day": CEILING_USD_DAY, "base_usd_day": BASE_USD_DAY, "profit_share": PROFIT_SHARE,
                     "profit_sessions": PROFIT_SESSIONS, "cloudflare_usd_day": CLOUDFLARE_USD_DAY,
                     "data_usd_day": DATA_USD_DAY, "lane_usd_day": LANE_USD_DAY, "lane_window_days": LANE_WINDOW_DAYS,
                     "split": dict(SPLIT), "runway_days": RUNWAY_DAYS,
                     "floor_sail_fixed_usd_day": FLOOR_SAIL_FIXED_USD_DAY, "lane_headroom": LANE_HEADROOM,
                     "profit_days": PROFIT_DAYS,
                     "notice_days": NOTICE_DAYS, "topup_days": TOPUP_DAYS, "notice_lead_days": NOTICE_LEAD_DAYS,
                     "reserve_usd": dict(RESERVE_USD)},
            "inputs": {"week_net_usd": week_net, "week_net_source": inputs.get("week_net_source"), "week_net_since": inputs.get("week_net_since"),
                       "lane": dict(lane_in), "p30_usd": _finite(inputs.get("p30_usd")),
                       "p30_source": inputs.get("p30_source"), "edge": inputs.get("edge"),
                       "meters": {m: dict(meters_in.get(m) or {}) for m in METERS}},
            "cap": cap, "earned_usd_day": earned, "cap_usd_day": cost["cap_usd_day"],
            "state": state, "meters": meters, "research_usd_day": total, "direction": direction,
            "knobs": knobs(meters["sail"]["research_usd_day"], meters["claude"]["research_usd_day"]), "why": why}


def _cadence(usd_seconds: float, dollars: float, least: int) -> int:
    """A cadence in seconds for `dollars` a day: `usd_seconds` / dollars, from `least` to once a day (no dollars)."""
    if dollars <= 0:
        return ARCHITECT_IDLE_SECONDS
    return int(min(ARCHITECT_IDLE_SECONDS, max(least, round(usd_seconds / dollars))))


def knobs(sail_usd_day: Any, claude_usd_day: Any) -> dict[str, Any]:
    """The knob values the research dollars a day buy (pre-registered; `overlay` applies them tighten-only)."""
    sail, claude = _amount(sail_usd_day) or 0.0, _amount(claude_usd_day) or 0.0
    total = sail + claude
    gym = sail * GYM_SHARE
    return {"researcher.sail_usd_per_hour": round(sail * (1 - GYM_SHARE) / 24, 6),
            "gym.max_boxes": max(1, int(math.floor(gym / (BOX_USD_HOUR * BOX_DUTY_HOURS) + 1e-9))),
            "claude.role_usd_day": round(claude, 4),
            "population.ceiling": max(CEILING_MIN, int(math.floor(total / FAMILY_USD_DAY + 1e-9))),
            "architect.every_seconds": _cadence(ARCHITECT_USD_SECONDS, total, ARCHITECT_MIN_SECONDS),
            "architect.refill_seconds": _cadence(REFILL_USD_SECONDS, total, REFILL_MIN_SECONDS)}


# ---------------------------------------------------------------------------------------------- enforcement
def floor_block(why: str) -> dict[str, Any]:
    """The settings' `budget` block at the FLOOR (no usable budget.json): THE COST RULE's own lines at no profit
    (`floor_lines`), FAIL CLOSED."""
    return {"source": "floor", "why": why, "at": None, "state": "research at floor (no usable budget.json)",
            "sail_usd_day": floor_usd_day("sail"), "claude_usd_day": floor_usd_day("claude"), "fixed_sail_usd_day": None}


def stale_block(meters: Any, at: float | None, why: str) -> dict[str, Any]:
    """The settings' `budget` block from a STALE budget.json: never looser than it, never looser than the floor. Each
    meter is min(floor, the stale file's research), 0 for a meter the file could not read (or did not say)."""
    meters = meters if isinstance(meters, Mapping) else {}
    values = {}
    for m in METERS:
        row = meters.get(m)
        said = _amount(row.get("research_usd_day")) if isinstance(row, Mapping) else None
        values[m] = 0.0 if said is None else min(floor_usd_day(m), said)  # an unreadable meter's row says 0
    sail = meters.get("sail") if isinstance(meters.get("sail"), Mapping) else {}
    return {"source": "stale budget.json", "why": f"{why}: the lower of the floor and the stale file", "at": at,
            "state": "research at most the floor and the stale budget (the budget job is not running)",
            "sail_usd_day": values["sail"], "claude_usd_day": values["claude"],
            "fixed_sail_usd_day": _amount(sail.get("fixed_usd_day")), "warning": True}


def cap_hold(root: str | Path | None, now: float | None = None) -> dict[str, Any] | None:
    """THE CAP BREACH HOLD (the module docstring, EVERY LINE IS HELD): `<root>/cap-hold.json` (the stall job writes it
    while today's MEASURED metered spend is over today's cap for certain, league/ops/metered.py) when it names the
    current UTC day: {schema, day, at, since, spent_usd, cap_usd}. None with no root, no file, one that does not read, or
    another day's (a new UTC day has no hold). Never raises."""
    import time

    if root is None:
        return None
    try:
        now = time.time() if now is None else float(now)
        data = json.loads((Path(root) / HOLD_FILE).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - no file (the usual case), or one that does not read: no hold
        return None
    if not isinstance(data, Mapping) or data.get("schema") != HOLD_SCHEMA or data.get("day") != _day(now).isoformat():
        return None
    return dict(data)


def _hold_words(hold: Mapping[str, Any]) -> str:
    def usd(value: Any) -> str:
        number = _finite(value)
        return "unknown" if number is None else f"${number:.2f}"
    return (f"the cap breach hold ({HOLD_FILE}): the UTC day {hold.get('day')}'s measured metered spend "
            f"{usd(hold.get('spent_usd'))} is over its cap {usd(hold.get('cap_usd'))}")


def held_block(block: Mapping[str, Any], hold: Mapping[str, Any]) -> dict[str, Any]:
    """The settings' `budget` block under THE CAP BREACH HOLD: no research on either meter (the Sail guard's research, the
    router's Claude roles) for the rest of the UTC day; the rest of `block` as it was (its fixed cost, its warning)."""
    return {**block, "source": f"the cap breach hold ({HOLD_FILE})", "why": _hold_words(hold),
            "state": "no research: today's measured metered spend is over its cap (the cap breach hold, until 00:00 UTC)",
            "sail_usd_day": 0.0, "claude_usd_day": 0.0, "hold": {"day": hold.get("day"), "since": hold.get("since")}}


def effective(root: str | Path, now: float | None = None) -> dict[str, Any]:
    """The budget block `<root>/budget.json` gives now (`read`; the floor when it gives none), under THE CAP BREACH HOLD
    when one stands today (`cap_hold`: no research on either meter): what the Sail guard and the router read for
    themselves, whatever settings they were handed, and what every `settings.load` with a state root hands them
    (`overlay`)."""
    import time

    now = time.time() if now is None else float(now)
    try:
        block, why = read(root, now)
    except Exception as exc:  # noqa: BLE001 - anything unexpected is the floor
        block, why = None, f"budget.json could not be read ({type(exc).__name__})"
    block = block if block is not None else floor_block(why or "no budget.json")
    hold = cap_hold(root, now)
    return block if hold is None else held_block(block, hold)


def read(root: str | Path, now: float) -> tuple[dict[str, Any] | None, str | None]:
    """(the settings' `budget` block from `<root>/budget.json`, None) or (None, why it is not usable). Each meter is
    held to its share of THE OWNER'S CEILING: a file that says more is read as the ceiling."""
    path = Path(root) / BUDGET_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "no budget.json yet"
    except (OSError, ValueError) as exc:
        return None, f"budget.json cannot be read ({type(exc).__name__})"
    if not isinstance(data, Mapping) or data.get("schema") != SCHEMA:
        return None, f"budget.json is not schema {SCHEMA}"  # another rule's file (a deploy or a rollback) is no file
    at = _finite(data.get("at"))
    if at is None:
        return None, "budget.json has no time"
    if at > now + 300:
        return None, "budget.json is dated in the future"
    meters = data.get("meters")
    if now - at > STALE_SECONDS:
        return stale_block(meters, at, f"budget.json is stale ({(now - at) / 3600:.0f} h old)"), None
    if not isinstance(meters, Mapping):
        return None, "budget.json has no meters"
    values = {}
    for m in METERS:
        row = meters.get(m)
        value = _amount(row.get("research_usd_day")) if isinstance(row, Mapping) else None
        if value is None:
            return None, f"budget.json's {m} research is not a number"
        values[m] = min(value, ceiling_usd_day(m))  # NEVER ABOVE THE CEILING, whatever the file says
    sail = meters.get("sail") or {}
    return {"source": BUDGET_FILE, "why": None, "at": at, "state": str(data.get("state") or "")[:200],
            "sail_usd_day": values["sail"], "claude_usd_day": values["claude"],
            "fixed_sail_usd_day": _amount(sail.get("fixed_usd_day"))}, None


def _tighten(block: Any, key: str, value: float, *, larger: bool = False, integer: bool = False) -> None:
    """min() (`larger`: max()) of the configured `block[key]` and `value`; a configured value that is not a number is
    left alone (its reader refuses it already)."""
    if not isinstance(block, dict):
        return
    current = _amount(block.get(key))
    if current is None:
        return
    out = max(current, value) if larger else min(current, value)
    block[key] = int(out) if integer else out


def overlay(settings: dict[str, Any], root: str | Path, *, now: float | None = None) -> dict[str, Any]:
    """Apply the budget to merged settings in place, tighten-only (the module docstring), and set their `budget` block."""
    import time

    block = effective(root, time.time() if now is None else float(now))
    values = knobs(block["sail_usd_day"], block["claude_usd_day"])
    population = settings.get("population")
    least = _amount(population.get("floor")) if isinstance(population, Mapping) else None
    if least is not None:  # never a ceiling at (or under) the floor: births and forks stay possible at the floor's dollars
        values["population.ceiling"] = max(values["population.ceiling"], int(least) + BIRTH_MARGIN)
    block["knobs"] = values
    block["openai_usd_day"] = 0.0
    researcher = settings.get("researcher")
    if isinstance(researcher, dict):
        key = "sail_usd_per_hour" if researcher.get("sail_usd_per_hour") is not None else "usd_per_hour"
        _tighten(researcher, key, values["researcher.sail_usd_per_hour"])
    _tighten(settings.get("gym"), "max_boxes", values["gym.max_boxes"], integer=True)
    _tighten(population, "ceiling", values["population.ceiling"], integer=True)
    if isinstance(population, dict) and _amount(population.get("ceiling")) is not None:
        start = _amount(population.get("start"))
        if start is not None and start > float(population["ceiling"]):
            # The ceiling holds the start down: a population under it is under its start, so every pass is a refill, and
            # the refill is held to the scheduled cadence (never the architect faster than its dollars).
            values["architect.refill_seconds"] = max(values["architect.refill_seconds"], values["architect.every_seconds"])
        # The start under the ceiling: a population under its start refills and reseeds toward it.
        _tighten(population, "start", float(population["ceiling"]), integer=True)
    _tighten(settings.get("architect"), "every_seconds", values["architect.every_seconds"], larger=True, integer=True)
    _tighten(settings.get("architect"), "refill_seconds", values["architect.refill_seconds"], larger=True, integer=True)
    # OpenAI is no meter of the rule: no research dollars for it, so no OpenAI room (models.ModelRouter.openai_room).
    _tighten(settings.get("guard"), "openai_cap_usd", 0.0)
    claude = settings.get("claude")
    if isinstance(claude, dict):
        lines = claude.get("role_usd_day")
        lines = {} if lines is None else lines
        if isinstance(lines, Mapping):  # anything else is read as a line of 0 for every role already
            roles = [r for r in (claude.get("roles") or []) if isinstance(r, str)] \
                if isinstance(claude.get("roles"), (list, tuple)) else []
            out = dict(lines)
            cap = values["claude.role_usd_day"]
            for role in [*lines.keys(), *roles]:
                given = lines.get(role)
                if given is None:
                    out[role] = cap
                elif _amount(given) is not None:
                    out[role] = min(_amount(given), cap)
            claude["role_usd_day"] = out
    settings["budget"] = block
    return settings


def sail_caps(settings: Mapping[str, Any], root: str | Path | None = None, now: float | None = None) -> dict[str, Any]:
    """The Sail guard's daily caps from the settings' `budget` block: `research` (the swarm's own booked Sail a UTC day)
    and `account` (Sail's own meter a UTC day: research + fixed). Settings that never went through a state root's
    `settings.load` (no block) are the guard's own read of `<root>/budget.json` (`effective`) with `root` (the guard's
    store root), else the floor: settings handed in without the budget never lift it. A malformed block is no research.
    `read` is false when the caps are no reading of the rule: a malformed block, or a block whose own `read` is not true
    (the one `settings.load` writes when the rule itself could not run). The dollars are as before either way; the guard
    names that brake apart from the budget's own daily stop. NEVER ABOVE THE CEILING: a block that says more research
    than Sail's share of it, however it came, is read as that share. `gate_reserve` is THE GATE'S RESERVE inside the day
    (`gate_reserve`): researcher cycles, births and the architect stop that far under either cap; the tournament's
    validation round, the gate round and the nightly forward go on to the caps themselves. THE CAP BREACH HOLD
    (`cap_hold`, with `root`): no research while it stands today, whatever the block says."""
    guard = settings.get("guard") if isinstance(settings.get("guard"), Mapping) else {}
    house = _amount(guard.get("house_burn_usd_day"))
    house = 1.0 if house is None else house
    block = settings.get("budget")
    if block is None and root is not None:  # handed settings without the block: the guard reads the budget itself
        block = effective(root, now)
        block = {**block, "source": f"{block.get('source')} (the guard's own read: the settings carried no budget)"}
    read = True
    if block is None:
        research, fixed, source = floor_usd_day("sail"), house, "floor (no budget block)"
    elif not isinstance(block, Mapping) or _amount(block.get("sail_usd_day")) is None:
        research, fixed, source, read = 0.0, house, "malformed budget block: no research", False
    else:
        research = min(_amount(block.get("sail_usd_day")), ceiling_usd_day("sail"))
        measured = _amount(block.get("fixed_sail_usd_day"))
        fixed = max(house, measured) if measured is not None else house
        source = str(block.get("source") or "budget")
        read = block.get("read", True) is True  # the rule's own blocks say nothing; one that says anything else is unread
    hold = cap_hold(root, now) if root is not None else None
    if hold is not None and research > 0:
        # THE CAP BREACH HOLD, at the guard's own check: whatever block it was handed, no Sail research for the rest of
        # the UTC day (the settings of the next swarm step carry it too: `effective`).
        research, source = 0.0, f"the cap breach hold ({HOLD_FILE}, over {source})"
    return {"research": round(research, 4), "fixed": round(fixed, 4), "account": round(research + fixed, 4), "source": source,
            "read": read, "gate_reserve": gate_reserve(research)}


def paid_model_room(block: Any, *spent_today: Any, role: Any = None) -> float | None:
    """THE BUDGET's paid-model dollars left this UTC day, for the router (league/swarm/models.py `claude_budget_room`):
    the settings' `budget` block's `claude_usd_day` (never above Claude's share of THE OWNER'S CEILING, whatever the
    block says) less the swarm's Claude and OpenAI spend today (`spent_today`, holds included: one number a model, each
    floored at 0 on its own, so a hold one model released never pays for the other's spend), and less THE GATE'S HOLDS
    for a call of `role` (`paid_model_reserve`, by stage: the review leaves the audit's hold and every role but the
    gate's two leaves both, so the gate finds them late in the day; no role named reads the line itself).
    None with no block: the router never hands one in (settings with no block are its own read of budget.json,
    the floor without one) and reads a None as no room. 0 for a block that is not a budget, or a spend that is not
    given or not a number (FAIL CLOSED). Here, in the protected rule, so the line's arithmetic changes only by the
    owner's deploy."""
    if block is None:
        return None
    line = _amount(block.get("claude_usd_day")) if isinstance(block, Mapping) else None
    spent = [_finite(usd) for usd in spent_today]
    if line is None or not spent or None in spent:
        return 0.0
    line = min(line, ceiling_usd_day("claude"))
    return max(0.0, line - paid_model_reserve(role) - sum(max(0.0, usd) for usd in spent))


# ---------------------------------------------------------------------------------------------- the inputs
def book_p30(root: str | Path, now: float, *, days: int = P30_DAYS, since: float | None = None) -> tuple[float | None, str]:
    """The live book's own trailing realized options P&L: every closed real position opened at or after `PNL_BASIS` and
    closed in the window (the last `days` days, or from `since`), its cash (fees in) plus the broker's posted fee
    correction for it (the publisher's last activity reading in `<root>/publish.json`, when there is one). UNKNOWN (None),
    as `league.trading_profit` reads Profit, when a closed row cannot be priced, a position since the basis is closed but
    unpriced (`unpriced_close`: its result is real, its number not yet), any order is pending or unknown, reconciliation
    is frozen, or the activity reading names an event the book has not settled (`blocking`)."""
    path = Path(root) / "live.sqlite"
    if not path.exists():
        return 0.0, "no live book: nothing realized"
    since, basis = (now - days * 86400) if since is None else float(since), _epoch(PNL_BASIS) or 0.0
    conn = _read_only(path)
    try:
        conn.execute("BEGIN")  # one read: the rows, the orders and the freeze as of one moment
        rows = [dict(r) for r in conn.execute(
            "SELECT pid, cash, qty, closed_at FROM positions WHERE status='closed' AND closed_at IS NOT NULL "
            "AND closed_at>? AND closed_at<=? AND opened_at>=?", (since, now, basis))]
        unpriced = [r[0] for r in conn.execute(
            "SELECT pid FROM positions WHERE status='unpriced_close' AND opened_at>=? LIMIT 5", (basis,))]
        uncertain = conn.execute("SELECT COUNT(*) FROM orders WHERE status IN ('pending', 'unknown')").fetchone()[0]
        recon = conn.execute("SELECT value FROM kv WHERE key='recon'").fetchone()
        conn.rollback()
    finally:
        conn.close()
    if unpriced:
        return None, f"position {unpriced[0]} is closed but not priced yet (unpriced_close): p30 is unknown"
    if uncertain:
        return None, f"{uncertain} orders are pending or unknown: p30 is unknown"
    try:
        frozen = (json.loads(recon[0]) or {}).get("frozen") if recon else None
    except (TypeError, ValueError, AttributeError):
        return None, "the reconciliation state cannot be read: p30 is unknown"
    if frozen:
        return None, "reconciliation is frozen: p30 is unknown"
    corrections: dict[str, Any] = {}
    note = "no broker fee corrections read"
    try:
        saved = json.loads((Path(root) / "publish.json").read_text(encoding="utf-8")).get("activity") or {}
        reading = saved.get("reading") or {}
        if reading.get("blocking"):
            return None, "the account reading names an event the book has not settled (blocking): p30 is unknown"
        fees = reading.get("fees_by_pid")
        if isinstance(fees, Mapping):
            corrections, note = dict(fees), "with the broker's posted fee corrections"
    except (OSError, ValueError, AttributeError):
        pass
    total = Decimal(0)
    for row in rows:
        try:
            cash = Decimal(str(row["cash"]))
            fix = Decimal(str(corrections.get(str(row["pid"]), "0")))
        except (InvalidOperation, ValueError, TypeError):
            return None, f"position {row['pid']} cannot be priced"
        if not cash.is_finite() or not fix.is_finite() or int(row["qty"] or 0) != 0:
            return None, f"position {row['pid']} cannot be priced"
        total += cash + fix
    return float(round(total, 2)), f"the live book: {len(rows)} closed positions, {note}"


def net_window(now: float, sessions: int = PROFIT_SESSIONS) -> tuple[float, str] | None:
    """THE COST RULE's window (RULE_VERSION 3): 00:00 New York of the first of the last `sessions` NYSE sessions that have
    closed by `now` (the repo's calendar, `ltcm.data.us_equity_session`), as (epoch, ISO day); every real close from it to
    `now` counts (a close earlier today, before today's session has closed, counts too). None when the calendar cannot
    count (unknown is never money)."""
    from zoneinfo import ZoneInfo

    from ltcm.data import us_equity_session

    try:
        day, found, first = _ny_day(now), 0, None
        for _ in range(sessions * 3 + 15):
            session = us_equity_session(day)
            closed = _epoch(session.close_at) if session is not None else None
            if closed is not None and closed <= now:
                found, first = found + 1, day
                if found == sessions:
                    break
            day -= dt.timedelta(days=1)
    except Exception:  # noqa: BLE001 - a calendar that cannot count reads no profit
        return None
    if found < sessions or first is None:
        return None
    start = dt.datetime.combine(first, dt.time(0, 0), tzinfo=ZoneInfo("America/New_York")).timestamp()
    return start, first.isoformat()


def book_equity(root: str | Path, since: float, now: float) -> tuple[float | None, str]:
    """The equity book's realized net in the window: every closed real (":r") lot of `<root>/live.sqlite` `eq_lots` whose
    `closed_at` is in (since, now], its net cash (fees and dividends in, as the book books it; league/equity/live.py), the
    old ETF and panel programs' lots and, from release R2, the event lane's real lots alike. 0 with no live book or no
    eq_lots table (a state from before E1); None when a row cannot be read as a number."""
    path = Path(root) / "live.sqlite"
    if not path.exists():
        return 0.0, "no live book: no equity lot"
    conn = _read_only(path)
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='eq_lots'").fetchone() is None:
            return 0.0, "no equity lots table"
        rows = [dict(r) for r in conn.execute(
            "SELECT lid, cash FROM eq_lots WHERE status='closed' AND substr(instance, -2)=':r' AND closed_at IS NOT NULL "
            "AND closed_at>? AND closed_at<=?", (since, now))]
    finally:
        conn.close()
    total = Decimal(0)
    for row in rows:
        try:
            cash = Decimal(str(row["cash"]))
        except (InvalidOperation, ValueError, TypeError):
            return None, f"equity lot {row['lid']} cannot be priced"
        if not cash.is_finite():
            return None, f"equity lot {row['lid']} cannot be priced"
        total += cash
    return float(round(total, 2)), f"the equity book: {len(rows)} closed real lots"


def book_net(root: str | Path, now: float, *, sessions: int = PROFIT_SESSIONS) -> tuple[float | None, str, str | None]:
    """THE COST RULE's week_net (RULE_VERSION 3): the realized net profit of every real book over the last `sessions` sessions
    (`net_window`): the options book's closed positions (`book_p30` from the window's start, its UNKNOWN rules and the
    broker's fee corrections included) plus the equity book's closed real lots (`book_equity`). (net, source, the
    window's first day); None when either book's figure is unknown or the window cannot be counted."""
    window = net_window(now, sessions)
    if window is None:
        return None, "the session calendar could not count the window: no profit", None
    since, first = window
    options, said = book_p30(root, now, since=since)
    if options is None:
        return None, said, first
    equity, told = book_equity(root, since, now)
    if equity is None:
        return None, told, first
    return round(options + equity, 2), f"{said}; {told} (from {first})", first


#: A verdict whose cost the gateway did not state counts this much (league/events/house.py `VERDICT_USD_UNKNOWN`: the
#: lane's own line counts it so, and so does its measure here).
VERDICT_USD_UNKNOWN = 0.01


def lane_spend(root: str | Path, now: float, *, days: int = LANE_WINDOW_DAYS) -> dict[str, Any]:
    """THE LANE'S MEASURED VERDICT SPEND (RULE_VERSION 3): from `<root>/events/events.sqlite` (league/events/store.py,
    read-only), the gateway's settled cost of every verdict answered over the trailing `days` days, a day (`usd_day`),
    its heaviest UTC day of them (`peak_usd_day`, today's part included: what sizes the lane's part, `cost_rule`), and
    since 00:00 UTC (`today_usd`). A verdict with no cost on record counts `VERDICT_USD_UNKNOWN`, as the lane's own line
    counts it. {usd_day: None, peak_usd_day: None, ...} with no store or one that cannot be read: the lane's part is then
    `LANE_USD_DAY`."""
    path = Path(root) / LANE_STORE
    none = {"usd_day": None, "peak_usd_day": None, "today_usd": 0.0}
    if not path.exists():
        return {**none, "source": "no event lane store"}
    cost = f"COALESCE(SUM(COALESCE(usd, {VERDICT_USD_UNKNOWN})), 0)"
    try:
        conn = _read_only(path)
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='verdicts'").fetchone() is None:
                return {**none, "source": "the event lane store has no verdicts table"}
            window = conn.execute(f"SELECT {cost}, COUNT(*) FROM verdicts WHERE answered_at>=? AND answered_at<=?",
                                  (_iso(now - days * 86400), _iso(now))).fetchone()
            peak = conn.execute(f"SELECT MAX(usd) FROM (SELECT {cost} AS usd FROM verdicts WHERE answered_at>=? AND "
                                "answered_at<=? GROUP BY substr(answered_at, 1, 10))",
                                (_iso(_day_start(now) - (days - 1) * 86400), _iso(now))).fetchone()
            today = conn.execute(f"SELECT {cost} FROM verdicts WHERE answered_at>=? AND answered_at<=?",
                                 (_iso(_day_start(now)), _iso(now))).fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, TypeError, ValueError) as exc:
        return {**none, "source": f"the event lane store could not be read ({type(exc).__name__})"}
    spent, count = _amount(window[0]) or 0.0, int(window[1] or 0)
    return {"usd_day": round(spent / days, 4), "peak_usd_day": round(_amount(peak[0]) or 0.0, 4),
            "today_usd": round(_amount(today[0]) or 0.0, 4),
            "source": f"{count} verdicts answered in the last {days} days, ${spent:.2f}"}


def lane_allowance(root: str | Path, now: float | None = None) -> dict[str, Any]:
    """THE LANE'S ALLOWANCE (the review of r1/alarms, its major 1): what the House's event lane may spend on verdicts a
    day (league/events/house.py holds them to the lower of this and `events.verdict_usd_day`), from `<root>/budget.json`:
    the Claude meter's lane part after its taper (`meters.claude.lane_usd_day`: the rule's own figure, 0 when the rule
    could not read the meter, FAIL CLOSED). With no usable budget.json (none, unreadable, malformed, another rule's, dated
    in the future) it is THE FLOOR's (`floor_lane_usd_day`: the rule's own lane line at no profit); a STALE one gives the
    lower of the floor and what it said. Never above `CEILING_USD_DAY`. Under THE CAP BREACH HOLD (`cap_hold`: today's
    measured metered spend over today's cap) it is 0 until 00:00 UTC, whatever budget.json says. The lane holds it on the
    UTC day, as every other line (EVERY LINE ON ONE DAY). {usd_day, source, at}. Never raises."""
    import time

    now = time.time() if now is None else float(now)
    hold = cap_hold(root, now)
    if hold is not None:
        return {"usd_day": 0.0, "source": _hold_words(hold), "at": None, "hold": True}
    floor = floor_lane_usd_day()
    try:
        data = json.loads((Path(root) / BUDGET_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"usd_day": floor, "source": "the floor (no budget.json yet)", "at": None}
    except (OSError, ValueError) as exc:
        return {"usd_day": floor, "source": f"the floor (budget.json cannot be read: {type(exc).__name__})", "at": None}
    if not isinstance(data, Mapping) or data.get("schema") != SCHEMA or data.get("rule_version") != RULE_VERSION:
        return {"usd_day": floor, "source": f"the floor (budget.json is not schema {SCHEMA}, rule {RULE_VERSION})", "at": None}
    at = _finite(data.get("at"))
    if at is None or at > now + 300:
        return {"usd_day": floor, "source": "the floor (budget.json is undated or dated in the future)", "at": None}
    meters = data.get("meters") if isinstance(data.get("meters"), Mapping) else {}
    row = meters.get("claude") if isinstance(meters.get("claude"), Mapping) else None
    said = _amount(row.get("lane_usd_day")) if row is not None else None
    if now - at > STALE_SECONDS:
        value = 0.0 if said is None else min(floor, said)
        return {"usd_day": round(min(value, CEILING_USD_DAY), 4), "at": at,
                "source": f"the lower of the floor and a stale budget.json ({(now - at) / 3600:.0f} h old)"}
    if said is None:
        return {"usd_day": floor, "source": "the floor (budget.json's Claude meter names no lane part)", "at": at}
    return {"usd_day": round(min(said, CEILING_USD_DAY), 4), "at": at,
            "source": f"budget.json ({row.get('limited_by') or 'the rule'}, cap {_finite(data.get('cap_usd_day')) or 0.0:.2f})"}


def economics_fresh(cutoff: float, now: float) -> bool:
    """The close economics at `cutoff` is the latest one there should be at `now`: no NYSE session closed after it (a
    minute's slack) and at least `ECONOMICS_LAG_SECONDS` before `now`."""
    if not 0 <= now - cutoff:
        return False
    if now - cutoff > 14 * 86400:
        return False
    try:
        from ltcm.data import us_equity_session

        day, end = _ny_day(cutoff), _ny_day(now)
        while day <= end:
            session = us_equity_session(day)
            closed = _epoch(session.close_at) if session is not None else None
            if closed is not None and cutoff + 60 < closed <= now - ECONOMICS_LAG_SECONDS:
                return False
            day += dt.timedelta(days=1)
        return True
    except Exception:  # noqa: BLE001 - without a calendar, wall time decides
        return now - cutoff <= P30_FRESH_SECONDS


def economics_p30(economics: Any, summary: Mapping[str, Any]) -> tuple[float | None, str]:
    """p30 from one close summary (`league.ops.economics.p30(summary)` -> {"usd": "..."}; a loss is a number): UNKNOWN
    (None, never the book's read instead) when its number does not read, the summary holds a position closed but
    unpriced, an order pending at the cutoff or an event the book has not settled (`reconciliation.blocking`), or it
    holds no closes by day (`realized.by_close_day`, the list p30 sums: without it p30 would read 0.00 from nothing). A
    summary too malformed to inspect is unknown too."""
    try:
        recon = summary.get("reconciliation") if isinstance(summary.get("reconciliation"), Mapping) else {}
        if recon.get("blocking"):
            return None, "the close economics: an event the book has not settled (blocking): p30 is unknown"
        if recon.get("pending_orders_at_cutoff"):
            return None, "the close economics: orders were pending at the cutoff: p30 is unknown"
        if any(isinstance(row, Mapping) and row.get("status_at_cutoff") == "unpriced_close"
               for row in summary.get("positions") or []):
            return None, "the close economics: a position is closed but not priced yet (unpriced_close): p30 is unknown"
        realized = summary.get("realized")
        if not isinstance(realized, Mapping) or not isinstance(realized.get("by_close_day"), list):
            return None, "the close economics' summary holds no closes by day (realized.by_close_day): p30 is unknown"
        value = _finite((economics.p30(summary) or {}).get("usd"))
    except Exception as exc:  # noqa: BLE001 - unknown is never money
        return None, f"the close economics' p30 failed ({type(exc).__name__}): p30 is unknown"
    if value is None:
        return None, "the close economics' p30 is not a number: p30 is unknown"
    return value, f"league.ops.economics.p30 (cutoff {summary.get('cutoff')})"


def _p30(root: Path, now: float, errors: list[str]) -> tuple[float | None, str]:
    """p30: the live book's own read (`book_p30`), cut to the close economics' p30 over its latest summary when that
    module is there, the summary is fresh and its number is smaller. The economics (league/ops/economics.py) may lower
    what was earned, never raise it: the book is the wall either way. Unknown from either is unknown, never the other
    read; with no fresh summary (none yet, a stale one, one that is not a summary, a read that failed) the book's read
    stands alone, and the job says so every time."""
    try:
        book, source = book_p30(root, now)
    except Exception as exc:  # noqa: BLE001 - unknown is never money
        errors.append(f"the live book could not be read ({type(exc).__name__}): nothing earned")
        return None, "unreadable"
    if book is None:
        errors.append(source)
        return None, source
    try:
        from . import economics  # league/ops/economics.py (the close economics), when it is there
    except ImportError:
        economics = None
    if economics is not None and callable(getattr(economics, "latest", None)) and callable(getattr(economics, "p30", None)):
        try:
            summary = economics.latest(root)
        except Exception as exc:  # noqa: BLE001 - no summary: the book's own read stands
            errors.append(f"the close economics could not be read ({type(exc).__name__}): the live book's own read is used")
            return book, source
        cutoff = _epoch(summary.get("cutoff")) if isinstance(summary, Mapping) else None
        if cutoff is not None and economics_fresh(cutoff, now):
            value, said = economics_p30(economics, summary)
            if value is None:
                errors.append(said)
                return None, said
            if value < book:
                return value, f"{said}: below the live book's own read, which caps it"
        elif isinstance(summary, Mapping):
            errors.append("the close economics is stale: the live book's own read is used")
        elif summary is None:
            errors.append("no close economics summary yet: the live book's own read is used")
        else:
            errors.append(f"the close economics' summary is not a mapping ({type(summary).__name__}): the live book's own "
                          "read is used")
    return book, source


def ladder_receipts(root: Path, errors: list[str]) -> dict[int, tuple[str, float]] | None:
    """The ladder's own Probe promotions in `<root>/observe.sqlite`: {receipt id: (family, epoch)} of the
    `ladder_decisions` rows with verdict promote (a pending or void receipt is none); {} with no practice record or no
    such table yet, None when it cannot be read."""
    path = root / "observe.sqlite"
    if not path.exists():
        return {}
    try:
        conn = _read_only(path)
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ladder_decisions'").fetchone() is None:
                return {}
            return {int(r[0]): (str(r[1]), float(r[2])) for r in conn.execute(
                "SELECT id, family, at FROM ladder_decisions WHERE verdict IN ('promote', 'promoted') AND at IS NOT NULL")}
        finally:
            conn.close()
    except (sqlite3.Error, TypeError, ValueError) as exc:
        errors.append(f"the ladder's record could not be read ({type(exc).__name__})")
        return None


def ladder_promotions(root: Path, errors: list[str]) -> list[float] | None:
    """The epochs of the ladder's own Probe promotions (`ladder_receipts`); [] with no practice record or no such table
    yet, None when it cannot be read."""
    receipts = ladder_receipts(root, errors)
    return None if receipts is None else [at for _, at in receipts.values()]


def _swarm_reads(root: Path, now: float, errors: list[str]) -> dict[str, Any]:
    """From the swarm store, read-only: the Sail guard's last reading, the ladder's Probe promotions (one epoch a settled
    receipt of `ladder_receipts`: its band move's own time when the store's `swarm.band` event names it, `LADDER_MARK`,
    else the receipt's; None when the ladder's record cannot be read), the Probes a passed look earned (`probes`: the
    time of the first move from `LOOK_BAND` to probe at or after each passed look of that family in the store's `looks`;
    they need no receipt of the ladder's), each meter's research spend, and what THE DAY'S FIRST RUN ADDS BACK: the
    guard's own meter of the UTC day (`metered_today`, the kv record as it is) and the day's own spend rows (`today`:
    (kind, epoch, usd) of the Sail kinds and Claude since 00:00 UTC of `now`'s day))."""
    out: dict[str, Any] = {"guard": None, "promotions": None, "probes": [], "need": {m: 0.0 for m in METERS},
                           "metered_today": None, "today": []}
    path = root / "swarm.sqlite"
    if not path.exists():
        errors.append("no swarm store: no guard reading, no promotion record")
        return out
    try:
        conn = _read_only(path)
        try:
            row = conn.execute("SELECT value FROM kv WHERE key='guard'").fetchone()
            meter = conn.execute("SELECT value FROM kv WHERE key='metered_today'").fetchone()
            kinds = (*SAIL_KINDS, PAID_CLAUDE_KIND)
            today = [(str(r[0]), r[1], r[2]) for r in conn.execute(
                f"SELECT kind, epoch, usd FROM spend WHERE epoch>=? AND kind IN ({','.join('?' * len(kinds))})",
                (_day_start(now), *kinds))]
            bands = [dict(r) for r in conn.execute("SELECT at, family, payload FROM events WHERE kind='swarm.band' "
                                                   "ORDER BY seq")]
            looked = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='looks'").fetchone() is not None
            looks = [dict(r) for r in conn.execute("SELECT family, at FROM looks WHERE passed=1 ORDER BY seq")] if looked else []
            spend = [dict(r) for r in conn.execute("SELECT kind, COALESCE(SUM(usd),0) AS usd FROM spend WHERE epoch>=? "
                                                   "GROUP BY kind", (now - NEED_WINDOW_DAYS * 86400,))]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        errors.append(f"the swarm store could not be read ({type(exc).__name__})")
        return out
    try:
        out["guard"] = json.loads(row["value"]) if row else None
    except (TypeError, ValueError):
        out["guard"] = None
    try:
        out["metered_today"] = json.loads(meter["value"]) if meter else None
    except (TypeError, ValueError):
        out["metered_today"] = None
    out["today"] = today
    receipts = ladder_receipts(root, errors)
    passed: dict[str, list[float]] = {}  # each family's passed looks, oldest first
    for look in looks:
        when = _epoch(look["at"])
        if when is not None:
            passed.setdefault(str(look["family"]), []).append(when)
    moved: dict[int, float] = {}
    counted: dict[str, int] = {}  # how many of a family's passed looks a move to Probe has answered
    for event in bands:
        try:
            payload = json.loads(event["payload"] or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("band_to") != "probe":
            continue
        at = _epoch(event["at"])
        # The ladder's own promotion: a move the ladder made counts only as its receipt's, settled `promote` for that
        # very family: one whose receipt is pending, void, another family's or unread is a promotion to no reader
        # (league/live/ladder.py).
        named = _NAMED_RECEIPT.search(str(payload.get("reason") or ""))
        settled = (receipts or {}).get(int(named.group(1))) if named else None
        if at is not None and settled is not None and settled[0] == str(event["family"]):
            moved[int(named.group(1))] = at
        # The look's own promotion (the fast lane): the Money table's move from candidate, for a family whose passed
        # look the store holds at or before it, once a look. A demotion from Sized, a move with no passed look behind it
        # and a return to Probe on a look already counted are none.
        if at is None or named or payload.get("band_from") != LOOK_BAND:
            continue
        mine, done = passed.get(str(event["family"]), []), counted.get(str(event["family"]), 0)
        if done < len(mine) and mine[done] <= at:
            out["probes"].append(at)
            counted[str(event["family"])] = sum(1 for when in mine if when <= at)
    out["promotions"] = None if receipts is None else [moved.get(n, at) for n, (_, at) in sorted(receipts.items())]
    by_kind = {r["kind"]: float(r["usd"] or 0.0) for r in spend}
    out["need"] = {"sail": sum(by_kind.get(k, 0.0) for k in SAIL_KINDS), "claude": sum(by_kind.get(k, 0.0) for k in CLAUDE_KINDS)}
    return out


def _house_boxes(root: Path, config: Mapping[str, Any]) -> list[str]:
    boxes = []
    pinned = (config.get("backup") or {}).get("box_id") if isinstance(config.get("backup"), Mapping) else None
    house = pinned or os.environ.get("SAILBOX_ID") or os.environ.get("SAIL_SAILBOX_ID")
    if house:
        boxes.append(str(house))
    try:
        data = json.loads((root / "data" / "data_box.json").read_text(encoding="utf-8")).get("box_id")
        if data:
            boxes.append(str(data))
    except (OSError, ValueError, AttributeError):
        pass
    return boxes


def _pool_boxes(root: Path) -> set[str] | None:
    """Every box the swarm's Gym pool has forked, in any state (the swarm store's `boxes` table, read-only;
    league/swarm/pool.py): research, whose time the swarm books as `gym_box` spend, so never Sail's fixed cost. None when
    there is no store or it cannot be read: research cannot be told from fixed then (`_sail_fixed`)."""
    path = root / "swarm.sqlite"
    if not path.exists():
        return None
    try:
        conn = _read_only(path)
        try:
            return {str(row["id"]) for row in conn.execute("SELECT id FROM boxes")}
        finally:
            conn.close()
    except sqlite3.Error:
        return None


class _Unread(Exception):
    """A part of Sail's billing `_sail_fixed` cannot read; its text is the reading's own words, never the provider's."""


def _why(exc: BaseException) -> str:
    return str(exc) if isinstance(exc, _Unread) else type(exc).__name__


def _sail_fixed(sail: Any, boxes: list[str], now: float, house_burn: float, errors: list[str],
                pool: set[str] | None = None) -> tuple[float, str]:
    """Sail's fixed cost a day over `FIXED_WINDOW_DAYS`, never below the configured `guard.house_burn_usd_day` (the
    guard's own rule; also the fallback).

    THE APP'S NON-RESEARCH BOXES (Oct 21, 2026; the audit of the live House, its cost lens): Sail's billing of the
    House box's app (`SailboxClient.spend(app=...)`, one `sailboxes` row a box, each read by league/sailbox.py
    `cost_nanos`, of either shape of the response), every box but the Gym pool's (`pool`, `_pool_boxes`): the House, the
    data box and any other box the swarm books nowhere (an image build, an old box left asleep, the updater's canaries);
    and each of `boxes` (the House box, the data box) the app's rows leave out, by its own billing. When the app or the
    pool cannot be read (`pool` None, as the `sail_read` drill calls it, league/ops/drills.py): the House box's and the
    data box's own billing alone, the reading before, and an error says so. A box row with no cost field is unknown,
    never $0: the reading falls back."""
    if sail is None or not boxes:
        return house_burn, "guard.house_burn_usd_day (no Sail client or no House box id)"
    from league.sailbox import cost_nanos

    since, until = _iso(now - FIXED_WINDOW_DAYS * 86400), _iso(now)

    def billed(spend: Any, box: str) -> float:
        found = cost_nanos(spend)
        if found is None:
            raise _Unread(f"no cost field for {box}")
        return float(found[0]) / 1e9

    total, source = None, ""
    try:
        if pool is None:
            raise _Unread("the Gym pool's boxes could not be read")
        row = sail.get(boxes[0]) or {}
        app = row.get("app_id") or (row["app"].get("id") if isinstance(row.get("app"), Mapping) else None)
        if not app:
            raise _Unread("the House box's row names no app")
        rows = (sail.spend(app=str(app), since=since, until=until) or {}).get("sailboxes")
        if not isinstance(rows, list):
            raise _Unread("the app's spend has no box rows")
        seen: set[str] = set()
        count = research = 0
        total = 0.0
        for entry in rows:
            if not isinstance(entry, Mapping) or entry.get("app_id") not in (None, str(app)):
                continue
            box = str(entry.get("sailbox_id") or "")
            if not box or box in seen:
                raise _Unread("a box row with no id, or one box twice")
            seen.add(box)
            if box in pool:
                research += 1
                continue
            total += billed(entry, box)
            count += 1
        for box in boxes:
            if box not in seen:
                total += billed(sail.spend(sailbox=box, since=since, until=until), box)
                count += 1
        source = (f"measured: the app's {count} non-research box{'es' if count != 1 else ''} over {FIXED_WINDOW_DAYS} "
                  f"days ({research} of the Gym pool's apart)")
    except Exception as exc:  # noqa: BLE001 - the named boxes stand in
        total = None
        errors.append(f"Sail's app billing could not be read ({_why(exc)}): the House and data boxes' own billing is used")
    if total is None:
        try:
            total = sum(billed(sail.spend(sailbox=box, since=since, until=until), box) for box in boxes)
        except Exception as exc:  # noqa: BLE001 - the configured burn stands in
            errors.append(f"Sail's box spend could not be read ({_why(exc)}): guard.house_burn_usd_day is used")
            return house_burn, "guard.house_burn_usd_day (the box spend could not be read)"
        source = (f"measured: the House and data boxes alone ({len(boxes)} box{'es' if len(boxes) != 1 else ''} over "
                  f"{FIXED_WINDOW_DAYS} days)")
    measured = total / FIXED_WINDOW_DAYS
    if measured >= house_burn:
        return measured, source
    return house_burn, f"guard.house_burn_usd_day (over the measured {measured:.4f} a day)"


def _sail_reserve(guard_cfg: Mapping[str, Any], fixed: float, errors: list[str]) -> tuple[float | None, str]:
    """Sail's reserve in force: THE SAIL GUARD'S OWN RELEASE LINE (league/swarm/guard.py `house_line`, the arithmetic
    `SailGuard.check` brakes and releases by; with `guard.measured_burn`, on Sail's fixed cost as the House's burn),
    never under `RESERVE_USD`. None when the line cannot be read: no Sail research."""
    try:
        from league.swarm.guard import house_line

        line = _amount(house_line(guard_cfg, fixed if guard_cfg.get("measured_burn", False) else 0.0)["release"])
    except Exception:  # noqa: BLE001 - unknown is never money
        line = None
    if line is None:
        errors.append("Sail's reserve: the Sail guard's line could not be read: no Sail research")
        return None, "the Sail guard's line could not be read"
    return max(RESERVE_USD["sail"], line), "the Sail guard's release line (league/swarm/guard.py house_line)"


def _claude_balance(health: Any) -> float | None:
    """The funded Claude total left (`/v1/health`'s `claude` block): its `remaining_usd`, else cap - spent, floored at 0
    as `remaining_usd` is (gateway/lib/gate.mjs `claudeStatus`); None when unconfigured or unreadable. The gateway's
    `spent_usd` already counts the holds in flight (gate.mjs `claudeReserve` adds a hold to both `spent` and
    `inflight`), so `inflight_usd` is never subtracted again."""
    block = health.get("claude") if isinstance(health, Mapping) else None
    if not isinstance(block, Mapping) or block.get("configured") is False:
        return None
    if block.get("remaining_usd") is not None:
        remaining = _finite(block.get("remaining_usd"))
        return None if remaining is None else round(remaining, 4)
    cap, spent = _finite(block.get("cap_usd")), _finite(block.get("spent_usd"))
    if cap is None or spent is None:
        return None
    return round(max(0.0, cap - spent), 4)


def _gateway_sail(health: Any, now: float) -> tuple[float | None, str | None]:
    """The gateway watchdog's own Sail balance (`/v1/health` `sail.balance_usd`, at most `BALANCE_FRESH_SECONDS` old by
    its `checked_at`): Sail's card line when the guard has no fresh reading. Never research."""
    block = health.get("sail") if isinstance(health, Mapping) else None
    if not isinstance(block, Mapping):
        return None, None
    balance, checked = _finite(block.get("balance_usd")), block.get("checked_at")
    at = _finite(checked)
    at = (at / 1000.0 if at is not None and at > 1e11 else at) if at is not None else _epoch(checked)
    if balance is None or at is None or not -300 <= now - at <= BALANCE_FRESH_SECONDS:
        return None, None
    return balance, f"the gateway's Sail reading at {_iso(at)} (the card line only)"


def _guard_reading(guard: Any, now: float) -> tuple[float | None, float | None, str]:
    """(Sail's balance, when it was read, the source) from the guard's kv: its last GOOD reading (`last_good`; one failed
    read after it does not erase it), else its last reading, at most `BALANCE_FRESH_SECONDS` old; (None, None, why) when
    there is neither."""
    guard = guard if isinstance(guard, Mapping) else {}
    for key in ("last_good", "last"):
        row = guard.get(key)
        row = row if isinstance(row, Mapping) else {}
        balance, at = _finite(row.get("balance")), _finite(row.get("at"))
        if balance is not None and at is not None and 0 <= now - at <= BALANCE_FRESH_SECONDS:
            return balance, at, f"the Sail guard's {'last good ' if key == 'last_good' else ''}reading at {_iso(at)}"
    return None, None, "the Sail guard has no fresh reading"


def _guard_kv(root: Path) -> Any:
    """The Sail guard's kv record alone, read-only, or None when there is none or it cannot be read: what the wait for
    the guard's next reading looks at (`_read_waiting`). Never an input: the inputs are read again after it."""
    path = root / "swarm.sqlite"
    if not path.exists():
        return None
    try:
        conn = _read_only(path)
        try:
            row = conn.execute("SELECT value FROM kv WHERE key='guard'").fetchone()
        finally:
            conn.close()
        return json.loads(row["value"]) if row else None
    except (sqlite3.Error, TypeError, ValueError):
        return None


def _booked_today(rows: Any, kinds: tuple[str, ...], now: float, until: float) -> float:
    """The dollars of `kinds` in the day's spend rows (`_swarm_reads`' `today`: (kind, epoch, usd)) from 00:00 UTC of
    `now`'s day to `until`, never under 0 (a release of a hold booked the day before lowers no day's spend under 0)."""
    start, total = _day_start(now), 0.0
    for row in rows if isinstance(rows, (list, tuple)) else ():
        try:
            kind, epoch, usd = row[0], _finite(row[1]), _finite(row[2])
        except (TypeError, IndexError, KeyError):
            continue
        if kind in kinds and epoch is not None and usd is not None and start <= epoch <= until:
            total += usd
    return max(0.0, total)


def _sail_paid_today(swarm: Mapping[str, Any], read_at: float | None, now: float, fixed: float) -> tuple[float, str]:
    """WHAT SAIL'S METER HAS PAID since 00:00 UTC of `now`'s day, as of the guard's balance reading at `read_at`: what
    THE DAY'S FIRST RUN ADDS BACK. It is the guard's own meter of the day (the store's `metered_today`, kept at every
    good reading beside the balance: every fall of the balance since midnight, the research and the fixed cost alike,
    in the provider's own dollars), never more than the swarm's booked Sail research today up to the reading plus one
    day of fixed cost: a guard that did not read across midnight meters the hours before it into today, and the Gym's
    booked box time is an estimate above the provider's bill, so each bounds the other. 0 when the reading is from
    before 00:00 UTC or the guard kept no meter of today: nothing known is nothing added back."""
    if read_at is None or read_at < _day_start(now):
        return 0.0, "no reading of today: nothing added back"
    meter = swarm.get("metered_today")
    metered = _amount(meter.get("spent")) if isinstance(meter, Mapping) and meter.get("day") == _day(now).isoformat() else None
    if metered is None:
        return 0.0, "the Sail guard kept no meter of today: nothing added back"
    booked = _booked_today(swarm.get("today"), SAIL_KINDS, now, read_at)
    return min(metered, booked + fixed), (f"the Sail guard's meter today ({metered:.4f}), at most the booked research "
                                          f"({booked:.4f}) and a day of fixed cost")


def _claude_paid_today(swarm: Mapping[str, Any], now: float) -> tuple[float, str]:
    """WHAT CLAUDE'S METER HAS PAID since 00:00 UTC of `now`'s day: the swarm's own Claude spend booked today (the
    store's `claude` rows, holds included, as the gateway's `spent_usd` counts them; never OpenAI's, which this meter
    does not pay), never under 0. What THE DAY'S FIRST RUN ADDS BACK."""
    return _booked_today(swarm.get("today"), (PAID_CLAUDE_KIND,), now, now), "the swarm's Claude spend booked today"


def _gateway(config: Mapping[str, Any]) -> tuple[str | None, str | None]:
    return config.get("gateway_url"), os.environ.get("GATEWAY_TOKEN")


def _health_reader(config: Mapping[str, Any]) -> Callable[[], Any] | None:
    url, token = _gateway(config)
    if not url or not token:
        return None

    def read() -> Any:
        import urllib.request

        request = urllib.request.Request(str(url).rstrip("/") + "/v1/health",
                                         headers={"Authorization": "Bearer " + str(token), "User-Agent": "ltcm-floor/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - https gateway only
            return json.loads(response.read(256_000))
    return read


def _notifier(config: Mapping[str, Any]) -> Callable[[Mapping[str, Any]], Any] | None:
    url, token = _gateway(config)
    if not url or not token:
        return None

    def send(facts: Mapping[str, Any]) -> Any:
        from ltcm.notify import post_json

        return post_json(str(url).rstrip("/") + "/v1/notify", str(token), facts)
    return send


def _config(ctx: Any) -> dict[str, Any]:
    config = _get(ctx, "config")
    if isinstance(config, Mapping):
        return dict(config)
    try:
        return json.loads((REPO / "league" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _root(ctx: Any) -> Path:
    root = _get(ctx, "root") or _get(ctx, "state_root") or getattr(_get(ctx, "house"), "root", None)
    if root is None:
        raise ValueError("the budget job needs the House's state root")
    return Path(root)


def _now(ctx: Any) -> float:
    now = _get(ctx, "now")
    if callable(now):
        now = now()
    if now is None:
        clock = _get(ctx, "clock")
        import time

        now = clock() if callable(clock) else time.time()
    return float(now)


def _clock(ctx: Any) -> Callable[[], float] | None:
    """The job's live clock, the one `_now` reads, or None when `ctx` fixes the job's instant (`now` a number): a run at
    a fixed instant has no later instant to read at, so it never waits (`_read_waiting`)."""
    now = _get(ctx, "now")
    if callable(now):
        return lambda: float(now())
    if now is not None:
        return None
    clock = _get(ctx, "clock")
    if callable(clock):
        return lambda: float(clock())
    import time

    return time.time


def gather(root: Path, now: float, *, config: Mapping[str, Any], settings: Mapping[str, Any], sail: Any = None,
           health: Callable[[], Any] | None = None, errors: list[str]) -> dict[str, Any]:
    """The rule's inputs (`compute`'s shape), every read guarded: what cannot be read is None, never a number."""
    swarm = _swarm_reads(root, now, errors)
    guard_cfg = settings.get("guard") if isinstance(settings.get("guard"), Mapping) else {}
    house_burn = _amount(guard_cfg.get("house_burn_usd_day"))
    house_burn = 1.0 if house_burn is None else house_burn
    balance, read_at, balance_source = _guard_reading(swarm["guard"], now)
    fixed, fixed_source = _sail_fixed(sail, _house_boxes(root, config), now, house_burn, errors, _pool_boxes(root))
    reserve, reserve_source = _sail_reserve(guard_cfg, fixed, errors)
    # What THE DAY'S FIRST RUN ADDS BACK: what each meter has paid since 00:00 UTC, as of its balance's reading.
    sail_paid, sail_paid_source = _sail_paid_today(swarm, read_at, now, fixed)
    claude_paid, claude_paid_source = _claude_paid_today(swarm, now)
    # RULE_VERSION 3: the lane's verdicts are paid by the Claude meter too (the swarm books none of them).
    lane = lane_spend(root, now)
    if _amount(lane.get("today_usd")):
        claude_paid += float(lane["today_usd"])
        claude_paid_source += f" and the event lane's verdicts today ({float(lane['today_usd']):.4f})"
    try:
        week_net, week_net_source, week_net_since = book_net(root, now)
    except Exception as exc:  # noqa: BLE001 - unknown is never money
        week_net, week_net_source, week_net_since = None, f"the books could not be read ({type(exc).__name__}): no profit", None
    if week_net is None:
        errors.append(f"week_net: {week_net_source}")
    claude_balance, claude_source = None, "the gateway's /v1/health could not be read"
    seen, seen_source = None, None
    if health is not None:
        try:
            read = health()
            claude_balance = _claude_balance(read)
            if claude_balance is not None:
                claude_source = "the gateway's /v1/health (cap - spent, holds included)"
            if balance is None:
                seen, seen_source = _gateway_sail(read, now)
        except Exception as exc:  # noqa: BLE001 - unknown is never money
            errors.append(f"the gateway's /v1/health could not be read ({type(exc).__name__})")
    if balance is None:
        errors.append(f"Sail's balance: {balance_source}: no Sail research" +
                      ("" if seen is None else "; the card line reads the gateway's Sail reading"))
    if claude_balance is None:
        errors.append(f"Claude's balance: {claude_source}: no Claude research")
    p30, p30_source = _p30(root, now, errors)
    try:
        # Both routes to Probe: the ladder's settled receipts and the Probes a passed look earned. The look's are the
        # swarm's own record and stand when the ladder's cannot be read (it could only add promotions, never take one).
        promoted = swarm["promotions"]
        if swarm["probes"]:
            promoted = [*(promoted or []), *swarm["probes"]]
        edge = edge_state(now, promoted)
        if swarm["promotions"] is None and promoted is not None:
            edge["promotions_readable"] = False
            edge["why"] += " (the ladder's record could not be read: only the Probes a look earned are counted)"
    except Exception as exc:  # noqa: BLE001 - the stop stands when it cannot be judged
        edge = {"stop": True, "why": f"the forward edge could not be judged ({type(exc).__name__}): earned is 0"}
    return {"week_net_usd": week_net, "week_net_source": week_net_source, "week_net_since": week_net_since, "lane": lane,
            "p30_usd": p30, "p30_source": p30_source, "edge": edge,
            "meters": {"sail": {"balance_usd": balance, "balance_source": balance_source, "fixed_usd_day": round(fixed, 4),
                                "fixed_source": fixed_source, "need_usd": round(swarm["need"]["sail"], 4),
                                "reserve_usd": None if reserve is None else round(reserve, 4), "reserve_source": reserve_source,
                                "paid_today_usd": round(sail_paid, 4), "paid_today_source": sail_paid_source,
                                "notice_balance_usd": seen, "notice_balance_source": seen_source},
                       "claude": {"balance_usd": claude_balance, "balance_source": claude_source, "fixed_usd_day": 0.0,
                                  "fixed_source": "none", "need_usd": round(swarm["need"]["claude"], 4),
                                  "paid_today_usd": round(claude_paid, 4), "paid_today_source": claude_paid_source}}}


# ---------------------------------------------------------------------------------------------- the funding notice
def _week(now: float) -> str:
    year, week, _ = _day(now).isocalendar()
    return f"{year}-W{week:02d}"


def short(doc: Mapping[str, Any]) -> list[str]:
    """THE TWO-DAY LEAD (release D-1b): the meters on which research runs out within `NOTICE_LEAD_DAYS` at the current
    burn (`out_in_days`, `_burn`), or, for a meter whose burn could not be read (its card line read from another balance,
    or a budget.json from before D-1b), whose days of research left at the ceiling (`card_runway_days`) are under
    `NOTICE_DAYS` (= `RUNWAY_DAYS` + `NOTICE_LEAD_DAYS`: the same instant at the ceiling)."""
    out = []
    for m in METERS:
        row = (doc.get("meters") or {}).get(m) or {}
        lead = _finite(row.get("out_in_days"))
        runway = _finite(row.get("card_runway_days"))
        if (lead is not None and lead < NOTICE_LEAD_DAYS) or (lead is None and runway is not None and runway < NOTICE_DAYS):
            out.append(m)
    return out


def notice_facts(doc: Mapping[str, Any], meter: str, now: float, *, test: bool = False) -> dict[str, Any]:
    """The `funding` notice's facts (the gateway composes the words): decimals as strings. The $/day, the runway and the
    date it runs out are at the rate the meter WANTS (fixed + its share of the ceiling: `usd_day`, `research_usd_day`,
    `runway_days`, its days of research left at the ceiling, `runs_out_on`); `current_*` are at the rate the rule holds
    it to now (the same while it runs at the ceiling, less once it tapers), or AT THE CURRENT BURN when the meter is spent
    faster than that (release D-1b, the review's finding 4: `burn_usd_day`, `burn_runway_days`). `topup_usd` buys
    `topup_days` more days at the wanted rate; `card_line_days` is the line those days are under; `card_date` is the day
    the taper starts, or the day research runs out at the current burn when that is earlier (`out_on`: the two-day
    lead's own date). `restore_usd` and `restore_days` are the same amount and days under RULE_VERSION 1's names: a
    gateway still on that rule's composer reads only those, and must never mail "add unknown"."""
    row = (doc.get("meters") or {}).get(meter) or {}

    def money(value: Any) -> str | None:
        number = _finite(value)
        return None if number is None else f"{number:.2f}"

    def days(value: Any) -> str | None:
        number = _finite(value)
        return None if number is None else f"{number:.1f}"
    fixed, demand = _finite(row.get("fixed_usd_day")), _finite(row.get("demand_usd_day"))
    balance = row.get("balance_usd") if _finite(row.get("balance_usd")) is not None else row.get("card_balance_usd")
    # A drill's id is its own minute's (the gateway remembers funding ids for 8 days, and a second drill in the same week
    # must reach the owner again, not be answered `duplicate`). A notice's id names the rule's version: the first notice
    # under a new rule (other days, another amount) is never answered `duplicate` for the old rule's of the same week.
    # Release D-1b: a notice's id is its UTC day's (at most once a day per meter; it was the ISO week's), so the gateway,
    # which remembers funding ids for 8 days, delivers each day's and answers a second one the same day `duplicate`.
    notice_id = (f"funding-test:{meter}:{_week(now)}:{int(now // 60)}" if test
                 else f"funding:{meter}:{_day(now).isoformat()}:r{RULE_VERSION}")
    # THE BURN IN THE MAIL (release D-1b, the review's finding 4, Oct 9, 2026). The two-day lead fires on the CURRENT BURN
    # (`_burn`), and a meter spent faster than the rule holds it (`burn_usd_day` above `total_usd_day`) can be short while
    # its card line still reads weeks. The gateway composes the mail from these facts alone and is its own deploy (not
    # touched here), so the facts it reads say the burn: `current_*` (the mail's "now" sentence and its no-card sentence)
    # are the burn's dollars a day, research share and days above the reserve, and `card_date` (the subject's and the
    # body's "add it by") is the day research runs out at the burn when that comes first (`out_on`). The figures at the
    # rate the rule WANTS (`usd_day`, `runway_days`, `runs_out_on`, `topup_usd`) are unchanged and true. So the mail never
    # says "Nothing stops if no card is added" (it needs the current runway at the card line or over) nor gives a late
    # date while research runs out within the lead. The fact NAMES are unchanged: the gateway's own test holds its
    # composer to exactly this key set (gateway/test/funding-notice.test.mjs), so the burn's own names (`burn_usd_day`,
    # `out_on`, ...) wait for a composer that words the burn as a spend (a gateway release). Its one imprecision until
    # then: the mail's "held to" sentence reads the burn's dollars a day, which the desk spends rather than is held to.
    current_usd, current_research = row.get("total_usd_day"), row.get("research_usd_day")
    current_days = row.get("runway_days")
    burn, rate = _finite(row.get("burn_usd_day")), _finite(row.get("total_usd_day"))
    over = burn is not None and rate is not None and fixed is not None and burn > rate + EPSILON
    if over:
        current_usd, current_research, current_days = burn, burn - fixed, row.get("burn_runway_days")
    card_date = row.get("card_date")
    if isinstance(row.get("out_on"), str) and (not isinstance(card_date, str) or row["out_on"] < card_date):
        card_date = row["out_on"]
    return {"kind": "funding", "notice_id": notice_id, "meter": meter,
            "balance_usd": money(balance), "usd_day": money(demand), "fixed_usd_day": money(fixed),
            "research_usd_day": money(None if demand is None or fixed is None else demand - fixed),
            "runway_days": days(row.get("card_runway_days")), "runs_out_on": row.get("card_runs_out_on"),
            "current_usd_day": money(current_usd), "current_research_usd_day": money(current_research),
            "current_runway_days": days(current_days),
            "topup_usd": money(row.get("topup_usd")), "topup_days": TOPUP_DAYS, "card_line_days": NOTICE_DAYS,
            "restore_usd": money(row.get("topup_usd")), "restore_days": TOPUP_DAYS,
            "card_date": card_date, "at": _iso(now), "test": bool(test)}


def _sent(answer: Any) -> bool:
    return isinstance(answer, Mapping) and (answer.get("sent") is True or answer.get("duplicate") is True)


def send_notices(doc: Mapping[str, Any], root: Path, now: float, notify: Callable[[Mapping[str, Any]], Any] | None,
                 errors: list[str]) -> list[dict[str, Any]]:
    """One `funding` notice per short meter (`short`: the two-day lead), at most once per meter a day (release D-1b,
    `NOTICE_EVERY_SECONDS`; it was once every 7 days): a meter is recorded as told only when the gateway says the notice was sent (or already
    was). What another version of the rule told (a record with no `rule_version`, or another one) is not this rule's
    notice: its days and its amount were another rule's, so the meter is told again."""
    path = root / NOTICES_FILE
    try:
        told = json.loads(path.read_text(encoding="utf-8"))
        told = told if isinstance(told, dict) else {}
    except (OSError, ValueError):
        told = {}
    out: list[dict[str, Any]] = []
    changed = False
    for meter in short(doc):
        mine = told.get(meter) if isinstance(told.get(meter), Mapping) and told[meter].get("rule_version") == RULE_VERSION \
            else {}
        last = _finite(mine.get("sent_at"))
        if last is not None and 0 <= now - last < NOTICE_EVERY_SECONDS:
            out.append({"meter": meter, "sent": False, "why": f"told at {_iso(last)}: at most once a day"})
            continue
        facts = notice_facts(doc, meter, now)
        if notify is None:
            out.append({"meter": meter, "sent": False, "why": "no gateway to notify through"})
            errors.append(f"funding notice for {meter} not sent: no gateway")
            continue
        try:
            answer = notify(facts)
        except Exception as exc:  # noqa: BLE001 - not told: the next run tries again
            out.append({"meter": meter, "sent": False, "why": f"the notice failed ({type(exc).__name__})"})
            errors.append(f"funding notice for {meter} failed ({type(exc).__name__})")
            continue
        if _sent(answer):
            told[meter] = {"sent_at": now, "notice_id": facts["notice_id"], "rule_version": RULE_VERSION}
            changed = True
            out.append({"meter": meter, "sent": True, "notice_id": facts["notice_id"]})
        else:
            reason = str((answer or {}).get("reason") or "the gateway did not send it")[:200] if isinstance(answer, Mapping) \
                else "the gateway did not send it"
            out.append({"meter": meter, "sent": False, "why": reason})
            errors.append(f"funding notice for {meter} not sent: {reason}")
    if changed:
        _write_json(path, told)
    return out


# ---------------------------------------------------------------------------------------------- the job
def _settings(root: Path, config: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from league.swarm import settings as settings_mod

        return settings_mod.load(root, config=config)
    except Exception:  # noqa: BLE001 - the defaults' guard burn stands in
        return {}


def _alert(ctx: Any, text: str) -> None:
    """A House warning through the job's context (`ctx.alert(level, text)`, league/ops/context.py), when it has one."""
    try:
        alert = _get(ctx, "alert")
        if callable(alert):
            alert("warning", text[:900])
    except Exception:  # noqa: BLE001 - the receipt still carries the errors
        pass


def _job_inputs(ctx: Any, root: Path, now: float, config: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    """The rule's inputs as the job reads them (`gather`), with the job's Sail client and gateway health reader."""
    try:
        sail = _get(ctx, "sail")  # the ops context builds its client on first use: that may fail
    except Exception as exc:  # noqa: BLE001 - the configured burn stands in
        sail = None
        errors.append(f"no Sail client from the job's context ({type(exc).__name__})")
    if sail is None and not errors:
        try:
            from league.sailbox import SailboxClient

            sail = SailboxClient()
        except Exception as exc:  # noqa: BLE001 - the configured burn stands in
            errors.append(f"no Sail client ({type(exc).__name__})")
    health = _get(ctx, "gateway_health") or _health_reader(config)
    return gather(root, now, config=config, settings=_settings(root, config), sail=sail, health=health, errors=errors)


def _read_waiting(ctx: Any, root: Path, config: Mapping[str, Any]) -> tuple[float, dict[str, Any], list[str],
                                                                               dict[str, Any] | None]:
    """The `budget` job's instant, its inputs (`_job_inputs`), their errors and its wait (None when it did not wait).

    THE WAIT FOR THE GUARD'S NEXT READING (L4, Oct 15, 2026). A run that starts just after the House does reads the
    guard's kv before the guard's first check: after an outage of 6 h or more that reading is stale, and the run wrote
    Sail "unreadable" (Oct 15: 03:27:22Z against the guard's reading at 03:27:25Z). Every `budget` receipt of a UTC day
    must read the ceiling for that day to count. So when the first read finds no fresh guard reading (`_guard_reading`),
    the run looks at the guard's kv every `GUARD_POLL_SECONDS`, at most `GUARD_WAIT_SECONDS` from its start. Once the
    guard has a good reading, the run takes a NEW instant, after that reading, and reads EVERY input again at it (the
    guard's kv, its `metered_today`, the day's spend, the box spend, the gateway): `_guard_reading` refuses a reading
    newer than the instant it is read at, and the day's meter moves with each reading. Only the guard's own reading ends
    the wait: the gateway's Sail reading stays the card line, never research. With no reading by the end, the run goes on
    as before: Sail "unreadable" at the run's start, and one more error, first in the list, says how long it waited after
    its first read (or, when the first read alone used the whole wait, that it never looked). The sleeps asked add up to
    at most `GUARD_WAIT_SECONDS` too, so a clock that does not move cannot stretch the wait. A fresh reading at the start
    is no wait at all. A run at a fixed instant (`now` a number: no clock) never waits. Only the job's own run waits: the
    refresh's full-job path does not (`refresh`)."""
    now = _now(ctx)
    errors: list[str] = []
    inputs = _job_inputs(ctx, root, now, config, errors)
    clock = _clock(ctx)
    if clock is None or _finite(inputs["meters"]["sail"].get("balance_usd")) is not None:
        return now, inputs, errors, None
    sleep = _get(ctx, "sleep")
    if not callable(sleep):
        import time

        sleep = time.sleep
    first = clock()  # the first read ends here: the wait is counted from it
    deadline, polls, slept = now + GUARD_WAIT_SECONDS, 0, 0.0
    # Two bounds besides the clock's: the time asked of the sleeper (a clock that never moves, with the real sleeper,
    # still sleeps at most GUARD_WAIT_SECONDS) and the number of looks.
    while polls < math.ceil(GUARD_WAIT_SECONDS / GUARD_POLL_SECONDS):
        left = min(deadline - clock(), GUARD_WAIT_SECONDS - slept)
        if left <= 0:
            break
        step = min(float(GUARD_POLL_SECONDS), left)
        sleep(step)
        slept, polls = slept + step, polls + 1
        if _guard_reading(_guard_kv(root), clock())[0] is None:
            continue
        again = clock()  # the new instant, after the guard's reading
        fresh: list[str] = []
        read = _job_inputs(ctx, root, again, config, fresh)
        if _finite(read["meters"]["sail"].get("balance_usd")) is not None:
            return again, read, fresh, {"first_read_seconds": round(first - now, 1),
                                        "waited_seconds": round(again - first, 1), "polls": polls, "read": True}
        # No reading at the second read (the guard wrote a newer one after the new instant): look again.
    took, waited = round(first - now, 1), round(clock() - first, 1)
    # First in the list, so the House alert (cut at 900 characters) carries it before the errors it explains.
    if polls:
        errors.insert(0, f"waited {waited:.0f} s ({polls} look{'s' if polls != 1 else ''}) for the Sail guard's next reading: "
                         "none came")
    else:
        errors.insert(0, f"no look for the Sail guard's next reading: the first read took {took:.0f} s of the "
                         f"{GUARD_WAIT_SECONDS} s")
    return now, inputs, errors, {"first_read_seconds": took, "waited_seconds": waited, "polls": polls, "read": False}


def _previous(root: Path) -> dict[str, Any] | None:
    """The last budget.json, parsed, or None."""
    try:
        previous = json.loads((root / BUDGET_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return previous if isinstance(previous, dict) else None


def run(ctx: Any) -> dict[str, Any]:
    """The `budget` job (league/ops: after the close economics, and daily at 00:30 UTC). `ctx` gives `root` (the House's
    state root; or `state_root`, or `house.root`), and optionally `now` or `clock`, `config` (league/config.json),
    `sail` (a `SailboxClient`), `gateway_health` (a callable returning `/v1/health`'s JSON) and `notify` (a callable
    posting one notice's facts to `/v1/notify`); each one absent is built from the House's own config and environment.
    Writes `<root>/budget.json` and returns the receipt. With no fresh guard reading it first waits for the guard's next
    one (`_read_waiting`, at most `GUARD_WAIT_SECONDS`; `ctx` may give `sleep`, else `time.sleep`)."""
    return _run(ctx, wait=True)


def _run(ctx: Any, *, wait: bool) -> dict[str, Any]:
    """The job (`run`); `wait` False is the refresh's full-job path, which reads once at its own instant, as before."""
    root, config = _root(ctx), _config(ctx)
    waited = None
    if wait:
        now, inputs, errors, waited = _read_waiting(ctx, root, config)
    else:
        now, errors = _now(ctx), []
        inputs = _job_inputs(ctx, root, now, config, errors)
    notify = _get(ctx, "notify") or _notifier(config)
    previous = _previous(root)
    doc = compute(inputs, now=now, previous=previous)
    if waited is not None:
        doc["guard_wait"] = dict(waited)
    doc["errors"] = list(errors)
    _write_json(root / BUDGET_FILE, doc)
    notices = send_notices(doc, root, now, notify, errors)
    if notices:
        doc["notices"], doc["errors"] = notices, list(errors)
        _write_json(root / BUDGET_FILE, doc)
    if errors:
        # Fail-closed is quiet by design (no research, no notice): a House warning says so (a stale guard, a paused
        # swarm, an unread gateway, a p30 from the fallback read or unknown, a notice not sent).
        _alert(ctx, "budget: " + "; ".join(errors))
    out = {"state": doc["state"], "direction": doc["direction"], "research_usd_day": doc["research_usd_day"],
           "earned_usd_day": doc["earned_usd_day"],
           "meters": {m: {k: doc["meters"][m].get(k) for k in ("research_usd_day", "would_set_usd_day", "limited_by",
                                                              "runway_days", "card_date", "direction")} for m in METERS},
           "notices": notices, "errors": errors, "warning": bool(errors)}
    if waited is not None:
        out["guard_wait"] = dict(waited)
    return out


# ---------------------------------------------------------------------------------------------- the refresh
def refresh_unusable(previous: Any, now: float) -> str | None:
    """Why the last budget.json gives the refresh nothing to build on (the full job runs in its place), or None: none,
    another format's or another version of the rule's (a deploy that changed the rule: Oct 7, 2026, the operator ran the
    job by hand because nothing ran it at the House's start), undated, dated in the future, stale or without meters."""
    if not isinstance(previous, Mapping):
        return "no budget.json"
    if previous.get("schema") != SCHEMA or previous.get("rule_version") != RULE_VERSION:
        return "budget.json is another version of the rule's"
    at = _finite(previous.get("at"))
    if at is None:
        return "budget.json has no time"
    if at > now + 300:
        return "budget.json is dated in the future"
    if now - at > STALE_SECONDS:
        return f"budget.json is stale ({(now - at) / 3600:.0f} h old)"
    if not isinstance(previous.get("meters"), Mapping):
        return "budget.json has no meters"
    return None


def refresh_changes(previous: Mapping[str, Any], doc: Mapping[str, Any], now: float) -> tuple[dict[str, str], str | None]:
    """What a refresh would write ({meter: "raise" | "first"}) and, when it writes nothing, why. Pure.

    It writes only when every meter reads (an unreadable meter is the full job's FAIL CLOSED, never the refresh's: the
    file stands as the last full run left it), no meter would fall under the file's figure but on the day's first figure
    (a lower figure on a day already set is a hand edit or the full job's: the refresh never lowers one), and some meter
    is RAISED (THE TOP-UP RAISE, or a meter read again after a run that could not read it) or gets the day's FIRST
    figure (no run of this UTC day has set one: the 00:30 run missed, or a meter it could not read). On the Claude meter
    THE LANE'S PART counts as its figure does (release R1's review: a run that could not read the meter left the lane no
    verdicts, `lane_allowance`, until the next full run; the refresh gives them back within the hour, and never lowers
    them)."""
    today = _day(now).isoformat()
    changes: dict[str, str] = {}
    for m in METERS:
        new = (doc.get("meters") or {}).get(m) or {}
        old = (previous.get("meters") or {}).get(m)
        old = old if isinstance(old, Mapping) else {}
        if new.get("limited_by") not in ("ceiling", "runway"):
            return {}, f"{m} could not be read: budget.json stands as the last full run left it"
        figure = old.get("day_figure")
        first = not (isinstance(figure, Mapping) and figure.get("day") == today)
        was, now_m = _amount(old.get("research_usd_day")), float(new.get("research_usd_day") or 0.0)
        lane_was, lane_now = _amount(old.get("lane_usd_day")), _amount(new.get("lane_usd_day"))
        lane_up = m == "claude" and lane_now is not None and (lane_was is None or lane_now > lane_was + EPSILON)
        if not first and m == "claude" and lane_now is not None and lane_was is not None and lane_now < lane_was - EPSILON:
            return {}, (f"the lane's part would fall from {lane_was:.4f} to {lane_now:.4f} a day: the refresh never lowers "
                        "it (the full job's runs do)")
        if first:
            changes[m] = "first"
        elif was is None or now_m > was + EPSILON or lane_up:
            changes[m] = "raise"
        elif now_m < was - EPSILON:
            return {}, (f"{m} would fall from {was:.4f} to {now_m:.4f} a day on a day already set: the refresh never "
                        "lowers a figure (the full job's runs do)")
    if not changes:
        return {}, "no meter to raise and every day's figure set: budget.json stands"
    return changes, None


def refresh(ctx: Any) -> dict[str, Any]:
    """THE `budget_refresh` JOB (Oct 10, 2026; the no-captain audit's item 2): hourly and at the House's start, the rule
    as `run` reads it, written only when it RAISES a meter or sets a day's FIRST figure (`refresh_changes`), so a top-up
    reaches the day's research, the knobs (`population.ceiling`, `gym.max_boxes`, the architect's cadence, the pace)
    and the guard's caps within the hour, never at the next 00:30 run. With no usable budget.json (`refresh_unusable`:
    none, another rule's after a deploy, stale) it is the full job (`run`, its funding notice included).

    Otherwise it sends no notice and raises no House warning (the full job's runs do both), and it never writes a
    figure lower than the file's on a day already set, nor a meter it could not read: it can only bring research up to
    what the rule itself sets, never past the owner's ceiling. A run that writes nothing leaves budget.json untouched
    (its receipt says why). Writes `<root>/budget.json` at most; moves no money."""
    root, now, config = _root(ctx), _now(ctx), _config(ctx)
    previous = _previous(root)
    unusable = refresh_unusable(previous, now)
    if unusable is not None:
        out = _run(ctx, wait=False)  # the refresh never waits for the guard (the job's own run does)
        out.update(written=True, refresh=f"the full job: {unusable}")
        return out
    errors: list[str] = []
    inputs = _job_inputs(ctx, root, now, config, errors)
    doc = compute(inputs, now=now, previous=previous)
    changes, why = refresh_changes(previous or {}, doc, now)
    meters = {m: {k: doc["meters"][m].get(k) for k in ("research_usd_day", "would_set_usd_day", "limited_by")}
              for m in METERS}
    if why is not None:
        return {"written": False, "why": why, "meters": meters, "errors": errors, "warning": False}
    doc["errors"] = list(errors)
    doc["refreshed"] = {"at": _iso(now), "meters": dict(changes)}
    _write_json(root / BUDGET_FILE, doc)
    return {"written": True, "changes": changes, "state": doc["state"], "research_usd_day": doc["research_usd_day"],
            "was_usd_day": _finite((previous or {}).get("research_usd_day")), "meters": meters, "errors": errors,
            "warning": False}


#: The drill's synthetic fixed cost a day per meter: the production shape (Claude has none). Its cliff holds this many
#: days of the wanted rate above the reserve: under `NOTICE_DAYS` and under `RUNWAY_DAYS`.
DRILL_FIXED = {"sail": 1.0, "claude": 0.0}
DRILL_DAYS = 3


def drill(ctx: Any, meter: str = "sail") -> dict[str, Any]:
    """The funding drill (league/ops drills, monthly; one call per meter): (1) a synthetic cliff on `meter` in the
    production shape (its fixed cost `DRILL_FIXED`, Claude's 0; its balance `DRILL_DAYS` days of fixed + its share of
    the ceiling above the reserve: under the card line and under `RUNWAY_DAYS`, so the rule itself tapers its research)
    goes through `compute` and is sent as the real notice would be, with `test: true` and its own notice id; (2) the
    same meter with an unreadable balance must give no research. Writes nothing to budget.json or to the notices'
    record."""
    if meter not in METERS:
        raise ValueError(f"no meter {meter!r}")
    root, now, config = _root(ctx), _now(ctx), _config(ctx)
    # The meter's wanted rate under THE COST RULE at no profit (fixed + its share of the $5 cap): the cliff holds
    # `DRILL_DAYS` of it above the reserve.
    wanted = cost_rule(0.0, DRILL_FIXED["sail"])["line_usd_day"][meter] + DRILL_FIXED[meter]
    synthetic = {"week_net_usd": 0.0, "week_net_source": "drill", "lane": {"usd_day": None, "today_usd": 0.0, "source": "drill"},
                 "meters": {m: {"balance_usd": RESERVE_USD[m] + (DRILL_DAYS * wanted if m == meter else 10_000.0),
                                "fixed_usd_day": DRILL_FIXED[m], "need_usd": 0.0} for m in METERS}}
    doc = compute(synthetic, now=now)
    unreadable = compute({**synthetic, "meters": {**synthetic["meters"],
                                                  meter: {"balance_usd": None, "fixed_usd_day": DRILL_FIXED[meter]}}},
                         now=now)
    checks = {"cliff_seen": meter in short(doc),
              "throttled_and_still_seen": doc["meters"][meter]["limited_by"] == "runway",
              "unreadable_gives_no_research": unreadable["meters"][meter]["research_usd_day"] == 0.0}
    facts = notice_facts(doc, meter, now, test=True)
    notify = _get(ctx, "notify") or _notifier(config)
    answer, error = None, None
    if notify is None:
        error = "no gateway to notify through"
    else:
        try:
            answer = notify(facts)
        except Exception as exc:  # noqa: BLE001 - the drill's receipt says so
            error = f"{type(exc).__name__}"
    # Only a mail sent now counts for the drill: a `duplicate` answer proves nothing about the mail path today.
    sent = isinstance(answer, Mapping) and answer.get("sent") is True and answer.get("duplicate") is not True
    return {"drill": "funding", "meter": meter, "root": str(root), "checks": checks, "notice_id": facts["notice_id"],
            "sent": sent, "error": error, "ok": sent and all(checks.values())}


__all__ = ["compute", "knobs", "overlay", "read", "effective", "stale_block", "floor_block", "BIRTH_MARGIN", "sail_caps",
           "paid_model_room", "paid_model_reserve", "gate_reserve", "edge_state", "book_p30", "economics_p30",
           "economics_fresh", "ladder_promotions", "gather", "ladder_receipts", "notice_facts", "send_notices", "short",
           "run", "refresh", "refresh_unusable", "refresh_changes", "drill", "floor_usd_day", "ceiling_usd_day", "METERS",
           "RULE_VERSION", "SCHEMA", "CEILING_USD_DAY", "BASE_USD_DAY", "PROFIT_SESSIONS", "CLOUDFLARE_USD_DAY",
           "DATA_USD_DAY", "LANE_USD_DAY", "LANE_WINDOW_DAYS", "LANE_STORE", "cost_rule", "net_window", "book_net",
           "book_equity", "lane_spend",
           "SPLIT", "RUNWAY_DAYS", "NOTICE_DAYS", "TOPUP_DAYS", "GATE_RESERVE_SHARE", "GATE_RESERVE_MIN_USD",
           "GATE_HOLDS_USD", "GATE_STAGES", "FLOOR_SAIL_FIXED_USD_DAY", "floor_lines", "floor_lane_usd_day",
           "lane_allowance", "LANE_HEADROOM", "PROFIT_DAYS", "PROFIT_SHARE", "RESERVE_USD", "EDGE_START", "EDGE_SESSIONS",
           "STALE_SECONDS", "BUDGET_FILE", "NOTICES_FILE", "LADDER_MARK", "LOOK_BAND", "P30_FRESH_SECONDS",
           "cap_hold", "held_block", "HOLD_FILE", "HOLD_SCHEMA"]

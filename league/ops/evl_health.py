"""THE EVENT LANE'S OWN STALL CAUSES (release 1019c; the owner's goal of Oct 19, 2026, item 5: "Self-running: alarms on
stalls, missed events, fill gaps and cap breaches"), judged for the `stall` job (league/ops/stall.py), which raises them
like any cause. Each judges PROGRESS, never a receipt's status alone (the review of r1/alarms, its major 2: a record pass
that read nothing and a score pass that settled nothing both said `ok`).

Every cause reads the lane's own store, `<state>/events/events.sqlite` (league/events/store.py; every open `mode=ro`,
inside `guard.readonly()`), on the House's NYSE calendar (`ltcm.data.us_equity_session`), with no recursion into a judge
(no program is run, no verdict asked, no outcome computed), against the receipts the House's lane writes
(league/events/house.py, league/events/run.py; their contract is league/events/__init__.py, THE EVENT LANE'S RECEIPTS):

- `evl_record`: no CLEAN record pass finished in the last `RECORD_MINUTES` (30). A pass is clean when it finished `ok`
  and its three reads ran without error: EDGAR's current 8-K feed and its Form 4 feed (each block present, no `error`,
  not every fetch of the pass failed) and Alpaca's news (present, no `error`; a read its bound cut short is no error),
  with a tickers copy to fetch 8-Ks by. The numbers name the feeds that failed in the window's passes. The recorder runs
  round the clock (PREREG-EVL-1 section 3), so this is judged at every hour.
- `evl_decide`: a session's open (09:15 ET) or close (the close - 14 minutes) decision not MADE IN ITS WINDOW (`made`:
  a receipt `decide-<kind>:<day>` finished `ok` or `pending` by `DECIDE_GRACE_MINUTES` (10) after its time, the lane's
  own LIVE_WITHIN: the live decision every real-money auction reads) over the last `DECIDE_LOOKBACK_HOURS` (24):
  missing, failed, cut by the lane's bound, unfinished or finished after its window. One decided later still
  stands (its real-money auction was missed: "missed events"), named so. Which kinds exist comes from the programs' rows.
- `evl_verdicts`: verdicts a decision needs that stay UNANSWERED PAST THE DECISION: a decision whose time has passed and
  whose latest receipt (its tally, run.py's `verdicts: {needed, answered}`, the close decision's included; a receipt from
  before the tally, its `pending` counts) still lacks an answer `VERDICT_GRACE_MINUTES` (15) after the later of the
  decision's time and the start of its run of receipts that lacked one. The numbers say the UTC day's verdict dollars
  and the lane's line (league/events/house.py: the lower of `events.verdict_usd_day` and the budget's allowance, held on
  the UTC day), which holds READ events over it by design: the alarm stands all the same, as their decisions wait.
- `evl_score`: intents due by the latest session whose 23:00 ET has passed (`SCORE_BY`) still `planned` or `entered`:
  the night's score passes left them open. An intent whose exit print the tape showed absent (a `marks` row with no
  price, under one of the score's own labels `TAPE_LABELS`, 'open', 'close' or 'first', at or after its exit day:
  PREREG-EVL-1 section 5's ladder waits on a later session; release 1019h: PREREG-EVL-5's '0930' minute with no trade
  excuses nothing) is waiting by design and is
  counted apart, and so is one a decision WROTE AFTER the night's last score pass started (release 1019f; a catch-up
  decision of an older session, as PREREG-EVL-4's rows decided by themselves: `written_after`, from the decision
  receipts' own counts), which the next pass settles; with no pass after the close nothing is excused. A night with
  nothing due is no stall.
- `evl_fills` (the goal's "fill gaps"): the lane's real fills set beside the shadow's own auction prices (the House's
  EVENT TWINS, league/ops/twins.py `event_twin`, in the swarm store's kv `equity_twins`: `entry_gap_bp` and
  `exit_gap_bp`, signed, positive when the real fill was worse): over the last `FILL_LOOK` (20) priced twins with a
  figure on a side, the signed mean of that side more than `FILL_GAP_BP` (15 bp) from the prints IN EITHER DIRECTION
  (the goal's Done item "fills within 15 bp of replay", PREREG-EVL-3 section 5's signed mean per side, A50's size of
  the mean gap; the review of r2/alarms, its major 3: a gap either way means the fills or the shadow's prices, the
  evidence the screen judges, are mis-measured), with at least `FILL_MIN` (5) of them; the text says which way. Not
  judged before the first real fill is priced.
- `evl_final` (A84, release 1019f; the audit that found A69's fast path never fired): a seatable program's FINAL RECORD
  (league/events/screen.py `final_until`, the horizon every look waits for) more than `FINAL_LAG_SESSIONS` (1) session
  behind what A69 allows (the session before the latest whose open decision has passed: A69 makes a close final once
  the session after it has had its open decision), the program and the judge's own why named (the first lagging the
  most, in the table's order). A program retired, with every look written, or not yet registered is not judged. The
  judge is READ, never run for a look: `final_until` reads the receipts, filings, calendar and meta of the same store
  read-only (league/ops/daily_report.py `ReadOnlyStore`) and computes no outcome.

RELEASE 1019f (the audit of the live House, lens "stalls": alarms that did not exist; the captain's A80 (2)):
- `evl_entries` (the goal's "fill gaps" BEFORE the price: the real buys that never became fills): each auction of the
  last `ENTRY_HOURS` (24) whose cross is `AUCTION_SETTLE_MINUTES` (15) behind, from the book's own rows in
  `<state>/live.sqlite` (`eq_event_intents` buys joined with `eq_intents` and their `eq_orders`, read-only), stands when
  under `ENTRY_FILL_SHARE` (90%) of its planned buys filled, or when any planned buy was NEVER SENT to the venue. Its
  numbers: planned, filled, the VENUE CANCELS (A80: an auction buy the venue ended `canceled` within `VENUE_CANCEL_S`
  (60) seconds of its own `submitted_at`, nothing filled and no cancel of the House's own sent: `venue_cancel_ms`, the
  rule release 1019e's re-send reads), the re-sends that went after one (A80's one re-send, release 1019e: an order
  of the buy after its venue cancel that reached the venue) and how many filled, the never-sent by reason
  (`unsent_reason`: the day order count, cash, the loss budget, the name wall, the invested cap, the program's room, the
  price of one share, the gateway, ...), and the constraint that BOUND the auction most (`BOUND`: cash, budget, room,
  order line, name wall, invested; the decision's room cut and name-wall skips counted with the buys cut or stopped).
  Not judged with no live.sqlite or no event table in it. league/ops/daily_report.py prints the same per auction.
- `evl_backfill` (A82's backfill as an alarm: the screen waits on `evl:backfill:<day>` for every weekday in its
  reach): a weekday of the daily-index backfill's reach (league/events/house.py `BACKFILL_WEEKDAYS`, from the lane's
  registration) not `done` by `BACKFILL_DUE` (12:00 ET) of the next weekday; or a `waiting` or `partial` streak of a
  day's `backfill` receipts (any status but `ok`) lasting more than `BACKFILL_STREAK_HOURS` (6); or a done day whose
  passes failed to fetch any filing (with release 1019f's backfill, which tries a failed fetch again `FETCH_TRIES`
  times and marks its receipts `retrying`, the day's own count in its last receipt: the filings past their last try;
  with an earlier release's receipts, `failed` > 0 summed over them: that backfill did not try a filing it had
  seen again). The text names the day and the counts.
- `evl_decide` ALSO stands for PREREG-EVL-4's rows still to decide by themselves: a close in the judge's own
  `made_without` (league/events/screen.py, read only) for more than `FOUR_REFILL_HOURS` (2: two of the House's hourly
  refills) since the stall job first saw it there and since its latest `decide-close` receipt finished, whose latest
  `decide-close-evl4` receipt is not `ok` (none, failed, cut, running, pending), or is `ok` but older than that close's
  latest decision (decided again by a release without the rows). The first sight is kept in stall.json (`evl_kept`).
  `evl_verdicts` reads the `decide-close-evl4` receipts' tallies too (each such receipt is a backfill: read while its
  latest one started inside the last 24 h). RELEASE 1019h (the review of release 1019g): THE SAME FOR PREREG-EVL-5'S
  ROWS (`FILE_WAITS`): `evl_decide` stands on a close in `made_without(prereg=5)` (a release without its rows decided
  it, or its part for them failed or ran past its own bound: PREREG-EVL-5 section 3) whose `decide-close-evl5` is not
  `ok` or is stale, on the same clock (its first sight kept apart, `evl_kept` `five`; the numbers `five_*` beside
  `four_*`, the text naming the file), and `evl_verdicts` reads the `decide-close-evl5` receipts' tallies.
- `evl_handback`: every real event fill the book has made (`eq_orders` of an event lot with `filled_qty` > 0) set
  beside the lane's `real_fills` (the rows the book hands back, league/equity/live.py `_event_fills`: a buy once its
  intent has ended, a sale once its lot is closed): it stands on any fill due to the lane more than `HANDBACK_HOURS` (1)
  and not in it. The lane computes Sized, demotion and retirement from those rows (PREREG-EVL-3), so a gap is evidence
  the judge never sees.

RELEASE 1019i (PREREG-EVL-7's H4 and PREREG-EVL-8's H1 and H2; its review):
- `evl_fill_rate` and `evl_attempts` (the attempts ledger, league/events/attempts.py): an auction's real buys filled
  under 85% over the last 3 sessions, or more than 10 points under their last 20; an event order with no final state
  an hour after its auction, or one of the book's the ledger lacks.
- `evl_score_parity` (the batched score's parity night FAILS CLOSED, league/events/score.py `latched`): stands while
  the parity latch stands (a sampled intent the batched path and the per-intent path settled differently): the lane
  settles every intent by release 1019h's per-intent path meanwhile, and the captain clears the latch once the flag
  0 is explained (`python3 -m league.events --state /workspace/state/events score-unlatch`). The numbers are the
  night's flags (checked, equal) and the latched intent's identifiers: never a value.
- `evl_px_store` (the price lane's store, league/events/pxstore.py `room`): px.sqlite and its WAL at or over 2 GiB,
  or, with league/config.json `events.px_data` on, the state disk under the PX floor (the swarm guard's 3 GB and 2 GB
  more, 5 GiB) or its free space unreadable: the recorders write nothing while it stands (every run `disk`). Judged
  while `events.px_data` is on or px.sqlite exists; read by `stat` and the disk's usage alone.

IDLE BY DESIGN: while `<state>/events/STOP` stands (the lane records, decides and asks nothing) the causes are not judged,
nor for `RESUME_MINUTES` after it goes (the lane's first passes); a decision whose window fell inside it is excused for
good. While the House's maintenance `<state>/PAUSE` stands (no paid call: no verdict) `evl_verdicts` is not judged, and a
run of unanswered receipts is counted from the pause's end; `evl_final` is judged through a pause (its why then names
the decision that waits on a verdict: the looks wait all the same). The stall job keeps the windows it saw (`idle_windows`,
stall.json `evl_idle`). WHEN THEY ARE JUDGED AT ALL: only while the lane runs on the House (league/config.json
`events.enabled` true) and `<state>/ops.json` `stall.evl` is not false. A store that cannot be read is "Not judged" and an
entry of the job's `errors` (`evl_final` reads apart: its failure leaves the others judged); a lane switched on with no
store yet has recorded nothing (`evl_record` stands). All are INFO with no owner step: each is the House's to fix (a
release or the captain).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from . import guard
from . import schedule as S

CAUSES = ("evl_record", "evl_decide", "evl_verdicts", "evl_score", "evl_fills", "evl_final", "evl_entries",
          "evl_backfill", "evl_handback", "evl_learner", "evl_fill_rate", "evl_attempts", "evl_score_parity", "evl_px_store",
          "evl_price")
#: The stall job's key in `<state>/ops.json` that switches these off: `{"stall": {"evl": false}}`.
SWITCH = "evl"
#: The lane's state under the House's state root (league/events/store.py `DB_NAME`), its idle switch and the House's pause.
STORE = Path("events") / "events.sqlite"
STOP = Path("events") / "STOP"
PAUSE = "PAUSE"
NY = ZoneInfo("America/New_York")
RECORD_MINUTES = 30
DECIDE_GRACE_MINUTES = 10
DECIDE_LOOKBACK_HOURS = 24.0
VERDICT_GRACE_MINUTES = 15
RESUME_MINUTES = 30
#: The decisions' times (league/events/calendar.py): 09:15 ET, and the close - 14 minutes.
OPEN_DECIDE = dt.time(9, 15)
CLOSE_DECIDE_BEFORE = dt.timedelta(minutes=14)
SCORE_BY = dt.time(23, 0)
#: THE TAPE'S OWN WORD OF NO PRINT (`evl_score`'s excuse, `_waiting_on_tape`): a `marks` row with no price under one of
#: the score's own labels (league/events/score.py `tape_print`: the listing exchange's opening cross 'open', its closing
#: cross 'close', the first trade on any venue 'first'). No other label is a print the score waits on: release 1019g's
#: PREREG-EVL-5 stores its gap's 09:30 minute with no price ('0930', league/events/run.py `GAP_LABEL`) when the tape
#: served the name and that minute had no trade, which says nothing of an exit print (release 1019h, the review of
#: release 1019g: it excused an unrelated stuck intent of the name).
TAPE_LABELS = ("open", "close", "first")
#: THE FILL GAP (`evl_fills`): the priced event twins read, the most a side's signed mean may be worse than the shadow's
#: auction prices (the goal's Done item: "fills within 15 bp of replay"), and the fewest that judge it.
FILL_LOOK = 20
FILL_GAP_BP = 15.0
FILL_MIN = 5
TWINS_KEY = "equity_twins"
#: THE FINAL RECORD (`evl_final`, A84): the most sessions a seatable program's final record may lag what A69's fast path
#: allows before the cause stands (one: a day's backfill or one late decision; A66's three-session wait alone is two).
FINAL_LAG_SESSIONS = 1
#: The record pass's three reads (league/events/house.py `_record_steps`: the summary's blocks), and their names here.
FEEDS = (("8-K", "8k"), ("4", "form4"), ("news", "news"))
#: The idle windows the stall job keeps (`idle_windows`): this many of each kind, none older than this.
IDLE_KEEP = 8
IDLE_DAYS = 3
#: THE ENTRIES (`evl_entries`, release 1019f): the book's state (league/equity/live.py, read-only), the auctions read, how
#: long after its cross an auction is judged (the book ends its intents 2 minutes after it: `EVENT_SETTLE_S`), the share
#: of its planned buys that must fill.
LIVE_DB = "live.sqlite"
ENTRY_HOURS = 24.0
AUCTION_SETTLE_MINUTES = 15
ENTRY_FILL_SHARE = 0.90
#: THE CAPTAIN'S A80: a venue cancel is an auction buy the venue ended `canceled` within this many seconds of its own
#: submission, nothing filled, no cancel of the House's own sent (league/equity/live.py `venue_cancel_ms` from release
#: 1019e reads the same rule); the venue stamps `canceled_at` to the millisecond, so a cancel inside the order's own
#: millisecond can read this much before it.
VENUE_CANCEL_S = 60.0
VENUE_STAMP_SLACK_S = 0.001
#: Orders that never reached the venue: refused by the House's own rate or the gateway, or lost (the venue never showed
#: its client id).
UNSENT_ORDERS = ("refused", "lost")
#: The constraints `bound` names, in the order a tie is named.
BOUND = ("cash", "budget", "room", "order_line", "name_wall", "invested")
#: The size rule's bindings (league/equity/sizing.py `Sized.binding`) and the gateway's caps (gateway/lib/*.mjs), as the
#: constraint each is.
SIZING_BINDS = {"cash": "cash", "sleeve_cash": "cash", "cash_negative": "cash", "budget": "budget",
                "instrument": "name_wall", "sleeve_cap": "name_wall", "invested": "invested", "min_order": "min_order"}
GATEWAY_CAPS = {"buying_power": "cash", "stock_position": "name_wall", "stock_total": "invested",
                "day_orders": "order_line", "day_open_orders": "order_line"}
#: Every reason `unsent_reason` names, in the order the numbers list them.
UNSENT = ("order_line", "cash", "budget", "name_wall", "invested", "room", "price", "min_order", "gateway", "sale",
          "busy", "blocked", "unreadable", "other")
#: THE BACKFILL (`evl_backfill`, release 1019f): a weekday's daily index is due `done` by this New York time of the next
#: weekday; a run of receipts that are not `ok` this long stands.
BACKFILL_DUE = dt.time(12, 0)
BACKFILL_STREAK_HOURS = 6.0
#: PREREG-EVL-4's rows still to decide by themselves stand on `evl_decide` once this long (two of the House's hourly
#: refills, league/events/house.py `REDECIDE_EVERY`) after the stall job first saw the close so and its decision
#: finished.
FOUR_REFILL_HOURS = 2.0
#: THE HAND-BACK (`evl_handback`, release 1019f): a real fill due to the lane's `real_fills` this long and not there
#: stands.
HANDBACK_HOURS = 1.0
#: What the stall job keeps for these causes in stall.json (`evl_kept`): {"four": {close day: first seen}, "five": the
#: same for PREREG-EVL-5's rows (release 1019h)}.
KEPT_FOUR = "four"
KEPT_FIVE = "five"
#: THE FILES WHOSE ROWS A CLOSE DECISION CAN LEAVE TO THEIR OWN DECISION (release 1019h, the review of release 1019g:
#: release 1019f's two readers were PREREG-EVL-4's alone): {prereg: (its facts' key, its kept key, its words)}, each read
#: by the judge's own `made_without(prereg=)` and its kind (league/events/screen.py `FILE_KINDS`: `decide-close-evl4`,
#: `decide-close-evl5`).
FILE_WAITS = {4: ("four", KEPT_FOUR, "PREREG-EVL-4"), 5: ("five", KEPT_FIVE, "PREREG-EVL-5")}
DOING = {
    "not_judged": "Nothing: the cause is not judged while it reads so.",
    "evl_record": ("The House's tick runs a record pass every 2 minutes (EDGAR's current 8-K and Form 4 feeds, Alpaca's "
                   "news through the gateway), each bounded; a filing a pass could not fetch is tried again at the next "
                   "passes and then by the daily-index backfill, and the shadow record decides every event by its "
                   "knowable time whenever it was stored (PREREG-EVL-1 section 3): an outage removes nothing from the "
                   "shadow record, but real money can use only what was stored before its decision."),
    "evl_decide": ("The House's tick runs a due decision before any other task of the lane, again a minute after one that "
                   "failed while it is live, and decides a missed one later from what was knowable at its time (the "
                   "shadow rule). A decision not made in its window missed its auction: real money took none of its "
                   "events. PREREG-EVL-4's rows of a close a release without them decided are decided by themselves "
                   "(decide-close-evl4, once, as a backfill) from the House's hourly refill, and PREREG-EVL-5's rows of "
                   "such a close, or of one whose part for them failed or ran past its own bound, the same way "
                   "(decide-close-evl5; that close's events of theirs are never traded); until then that close is not "
                   "final for them."),
    "evl_verdicts": ("The lane asks each verdict as soon as its event is recorded and eligible, and again before each "
                     "decision, at most 3 calls a pass; a call with no answer stores nothing and is asked again "
                     "(PREREG-EVL-1 section 4). Reading programs wait (pending) until every verdict they need is stored, "
                     "then decide by the shadow rule; over the lane's daily line (the budget's allowance, held on the UTC "
                     "day) they wait for the next UTC day's."),
    "evl_score": ("The lane's nightly score settles every due intent at the listing exchange's auction prints once the tape "
                  "is 16 minutes old (league/events/score.py), resumable pass by pass; the next night's passes try again "
                  "what this one left. The screen's looks wait for every block they cover (PREREG-EVL-1 section 7)."),
    "evl_final": ("The screen job writes each look as soon as its close is FINAL for the program: by A69's fast path "
                  "once the session after it has had its open decision, when each feed was read whole (A84: the 8-K, "
                  "Form 4 and news feeds each read cleanly at most 15 minutes apart), no filing of its windows is left "
                  "listed or failed, the daily-index backfills have run and every decision through it is made; else by "
                  "A66's three sessions. The record passes, their retries and the backfill fill most gaps by "
                  "themselves; one that stays is the House's to fix (a release or the captain). A late look keeps its "
                  "as-of date and its record: only the band move it makes comes later."),
    "evl_fills": ("Each real event lot buys at the opening or closing auction with a limit-on-open or limit-on-close order "
                  "and sells at its own auction; the House sets every closed lot beside the shadow's auction print (the "
                  "equity_twins job, daily and before each open). Once real fills exist PREREG-EVL-1 section 5 checks the "
                  "cost allowance against the signed mean gap per side (raised, never lowered, when the fills are worse); "
                  "the goal's Done asks fills within 15 bp of replay either way, so a gap either way is the House's to "
                  "explain: the fills or the shadow's auction prices are mis-measured."),
    "evl_entries": ("Each planned event buy goes at its auction's window through every gate of a real open, the day's "
                    "order count, the program's room and the size rule (cash, the loss budget, the 10% a name, the "
                    "invested cap); a buy the venue cancels at once goes again once from release 1019e (A80); a buy never "
                    "sent or not filled is missed, and its full-size shadow keeps the event: real settled events come "
                    "slower by that share. The House moves no wall to fill more."),
    "evl_backfill": ("The lane reads each weekday's EDGAR daily index from 05:00 ET the next day, hourly until it is "
                     "complete, filing by filing (A82), and decides again the sessions the filings it fetches enter; the "
                     "screen's looks wait for every weekday of its reach to be done (A66, A69 (iii)), so a day not done "
                     "holds every look that covers it."),
    "evl_fill_rate": ("Each planned event buy goes at its auction with every gate of a real open (A80's one re-send after a "
                      "venue cancel at once included); the attempts ledger (release 1019i) keeps every order sent with "
                      "the venue's own states, so the House reads the fill rate by auction over 3 and 20 sessions. A "
                      "fall is the venue's or the House's to explain (cancels at once, limits off the cross, a gate); "
                      "its full-size shadow keeps every event, so real settled events only come slower. No wall moves."),
    "evl_attempts": ("The book writes every event order it sends, and every planned buy that ended unsent, into the lane's "
                     "attempts ledger each minute, from the venue's own order states (it never sends or changes an "
                     "order); the venue ends an auction order at its cross and a day sale at the close, so an order with "
                     "no final state an hour after its auction, or one the ledger lacks, is a gap in the fill evidence "
                     "COST-7 measures, for the House to read again or fix."),
    "evl_score_parity": ("On the batched score's parity night a 5% sample of the intents is settled twice in memory, by "
                         "the batched path and by the per-intent path, before anything is written; a difference sets "
                         "the parity latch, and from that intent on the lane settles every intent by release 1019h's "
                         "per-intent path (no outcome is written from the batched path while it stands). The captain "
                         "reads why the two paths differed (the vendor's adjustment, the cache) and clears the latch "
                         "(score-unlatch) or keeps events.score_batch false. No wall moves."),
    "evl_px_store": ("The price lane's recorders write px.sqlite only while it holds under 2 GB and the state disk keeps "
                     "the PX floor free (the swarm guard's 3 GB and 2 GB more); a run without room writes nothing, so "
                     "the lane's and the book's ledgers keep their disk. No decision reads px.sqlite yet: the gap is "
                     "warm-up data only, for the captain to make room (prune px.sqlite, grow the disk) or to switch "
                     "events.px_data off."),
    "evl_learner": ("PREREG-EVL-7's learners decide after the House's own decision of each auction, under their own "
                    "bound; a part that fails or expires is decided later by itself (never traded); the nightly recompute "
                    "alarms on a mismatch; the training follows the evening score (league/ops/evl_learner.py)."),
    "evl_price": ("PREREG-EVL-8's price lane and meta-learners run by themselves at their section 4.6 times under their own "
                "bounds (league/ops/evl_price.py); a run that fails or expires is never traded at that auction and is "
                "decided later by a catch-up; the recorders feed the morning pass; the placebo audit is a report line."),
    "evl_handback": ("The book writes each real event fill back into the lane's store every minute until the store takes "
                     "it (league/equity/live.py `_event_fills`: a buy once its intent has ended, a sale once its lot is "
                     "closed); the lane computes Sized, demotion and retirement from those rows, so a fill missing there "
                     "is evidence the judge never sees."),
}


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


def switched_off(ctx: Any) -> bool:
    """THE OWNER'S SWITCH (`<state>/ops.json` `stall.evl` false): the causes are not judged; absent, they are."""
    settings = _get(ctx, "settings")
    block = settings.get("stall") if isinstance(settings, Mapping) else None
    return isinstance(block, Mapping) and block.get(SWITCH) is False


def lane_on(ctx: Any) -> bool:
    """The lane runs on the House: league/config.json `events.enabled` true (release R1; default false)."""
    config = _get(ctx, "config")
    block = config.get("events") if isinstance(config, Mapping) else None
    return isinstance(block, Mapping) and block.get("enabled") is True


def _not_judged(why: str) -> dict[str, Any]:
    return {"stalled": False, "judged": False, "what": f"Not judged: {why}.", "numbers": {"judged": False},
            "doing": DOING["not_judged"], "owner_step": None, "onset": None}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _loads(text: Any) -> Any:
    try:
        return json.loads(text) if isinstance(text, str) and text else None
    except ValueError:
        return None


def _hhmm(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, NY).strftime("%H:%M")


# ---------------------------------------------------------------------------------------------- idle by design
def idle_windows(kept: Any, root: str | Path, now: float) -> dict[str, list[list[float | None]]]:
    """The lane's STOP and the House's PAUSE as the stall job has seen them: {"stop": [[start, end], ...], "pause": ...},
    `end` None while the file stands. A file seen now opens a window at its mtime (or keeps the open one); a window
    open at the last run and gone now ends now (the file went between the two runs: the later end excuses more). Kept:
    the last `IDLE_KEEP` of each, none ended more than `IDLE_DAYS` ago."""
    kept = kept if isinstance(kept, Mapping) else {}
    out: dict[str, list[list[float | None]]] = {}
    for kind, path in (("stop", Path(root) / STOP), ("pause", Path(root) / PAUSE)):
        rows = [[_num(r[0]), _num(r[1])] for r in kept.get(kind) or [] if isinstance(r, (list, tuple)) and len(r) == 2
                and _num(r[0]) is not None]
        try:
            since = path.stat().st_mtime
        except OSError:
            since = None
        if since is not None:
            if not rows or rows[-1][1] is not None:
                rows.append([min(since, now), None])
        elif rows and rows[-1][1] is None:
            rows[-1][1] = now
        horizon = now - IDLE_DAYS * 86400
        out[kind] = [r for r in rows if r[1] is None or r[1] >= horizon][-IDLE_KEEP:]
    return out


def _within(at: float, windows: list[list[float | None]], now: float) -> bool:
    return any(start <= at <= (now if end is None else end) for start, end in windows)


def _open(windows: list[list[float | None]]) -> bool:
    return bool(windows) and windows[-1][1] is None


def _ended_lately(windows: list[list[float | None]], now: float) -> float | None:
    """When the latest window ended, when that was under `RESUME_MINUTES` ago; else None."""
    if windows and windows[-1][1] is not None and now - float(windows[-1][1]) < RESUME_MINUTES * 60:
        return float(windows[-1][1])
    return None


# ---------------------------------------------------------------------------------------------- the calendar
def sessions(first: dt.date, last: dt.date) -> list[dict[str, Any]]:
    """The House's NYSE sessions from `first` to `last`: [{day, open_at, close_at}] (epochs), oldest first."""
    from ltcm.data import us_equity_session

    out, day = [], first
    while day <= last:
        try:
            session = us_equity_session(day)
        except Exception:  # noqa: BLE001 - a year the calendar does not hold has no session here
            session = None
        if session is not None:
            out.append({"day": day, "open_at": S.epoch(session.open_at), "close_at": S.epoch(session.close_at)})
        day += dt.timedelta(days=1)
    return out


def _ny(day: dt.date, wall: dt.time) -> float:
    return dt.datetime.combine(day, wall, tzinfo=NY).timestamp()


def decisions(now: float, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    """The scheduled decisions whose window (`DECIDE_GRACE_MINUTES` after their time) has ended, their time inside the
    last `DECIDE_LOOKBACK_HOURS`: [{kind, day, at, ends}] (epochs), oldest first."""
    today = dt.datetime.fromtimestamp(now, NY).date()
    out = []
    for s in sessions(today - dt.timedelta(days=4), today):
        for kind in kinds:
            if kind == "open":
                at = _ny(s["day"], OPEN_DECIDE)
            elif s["close_at"] is not None:
                at = s["close_at"] - CLOSE_DECIDE_BEFORE.total_seconds()
            else:
                continue
            ends = at + DECIDE_GRACE_MINUTES * 60
            if now - DECIDE_LOOKBACK_HOURS * 3600 <= at and ends <= now:
                out.append({"kind": kind, "day": s["day"].isoformat(), "at": at, "ends": ends})
    return sorted(out, key=lambda d: d["at"])


def entry_kinds() -> tuple[str, ...]:
    """The decisions the registered programs need (league/events/programs.py `PROGRAMS`: each row's `entry_at`)."""
    try:
        from ..events import programs as P

        kinds = {str(p.entry_at) for p in P.PROGRAMS}
    except Exception:  # noqa: BLE001 - both, when the table cannot be read
        kinds = {"open", "close"}
    return tuple(k for k in ("open", "close") if k in kinds)


# ---------------------------------------------------------------------------------------------- the reads
class _Db:
    """A read-only connection as the judge's readers read a store (`db`): league/events/screen.py `made_without`."""

    def __init__(self, db: Any):
        self.db = db


def empty_facts() -> dict[str, Any]:
    """`facts` of a lane with no store yet."""
    return {"record": [], "decide": {}, "score": [], "open_due": [], "none_marks": set(), "backfill": [],
            "backfill_meta": {}, "four": {}, "five": {}}


def facts(root: str | Path, now: float, score_day: str | None) -> dict[str, Any]:
    """Every receipt the causes read, and the intents due by `score_day` still open, in one read-only transaction:
    {record: [...], decide: {job: [...]}, score: [...], open_due: [...], none_marks: {(symbol, day)}, backfill: [...],
    backfill_meta: {day: value}, four: {close day: {stale, closed_at, status}}, five: the same} (`four`:
    league/events/screen.py `made_without` over the store, the judge's own reading of the closes PREREG-EVL-4's rows
    still wait on; `five`, release 1019h: PREREG-EVL-5's, `made_without(prereg=5)`)."""
    since = S.iso(now - 5 * 86400)
    today = dt.datetime.fromtimestamp(now, NY).date()

    def read(db: Any) -> dict[str, Any]:
        rows = guard.rows(db, "SELECT id, job, started_at, finished_at, status, summary FROM receipts WHERE started_at>=? "
                              "AND (job='record' OR job LIKE 'decide-%' OR job='score' OR job='backfill') ORDER BY id",
                          (since,))
        out: dict[str, Any] = empty_facts()
        for r in rows:
            job = str(r["job"])
            if job == "record":
                out["record"].append(r)
            elif job == "score":
                out["score"].append(r)
            elif job == "backfill":
                out["backfill"].append(r)
            else:
                out["decide"].setdefault(job, []).append(r)
        out["backfill_meta"] = {str(r["key"])[len("evl:backfill:"):]: str(r["value"]) for r in guard.rows(
            db, "SELECT key, value FROM meta WHERE key LIKE 'evl:backfill:%'")}
        out["four"] = four_waiting(db, today)
        out["five"] = four_waiting(db, today, prereg=5)
        if score_day is not None:
            out["open_due"] = guard.rows(db, "SELECT i.program, i.version, i.event, i.symbol, i.entry_day, i.entry_at, "
                                             "i.exit_day, i.exit_at, (SELECT u.bench FROM universe u WHERE u.day=i.entry_day AND "
                                             "u.symbol=i.symbol) AS bench FROM intents i WHERE i.status IN ('planned', "
                                             "'entered') AND i.exit_day<=?", (score_day,))
            symbols = sorted({str(r["symbol"]) for r in out["open_due"]} | {str(r["bench"]) for r in out["open_due"]
                                                                            if r["bench"]})
            if symbols:
                first = min(str(r["entry_day"]) for r in out["open_due"])
                # (release 1019h: the score's own auction labels only, `TAPE_LABELS`; PREREG-EVL-5's '0930' minute
                # with no trade is no print the score waits on)
                marks = guard.batched(db, "SELECT symbol, day FROM marks WHERE px IS NULL AND label IN ("
                                          + ", ".join("?" * len(TAPE_LABELS)) + ") AND day>=? AND symbol IN ({marks})",
                                      symbols, params=(*TAPE_LABELS, first))
                out["none_marks"] = {(str(m["symbol"]), str(m["day"])) for m in marks}
        return out
    return guard.read(Path(root) / STORE, read)


def four_waiting(db: Any, today: dt.date, *, prereg: int = 4) -> dict[str, dict[str, Any]] | None:
    """THE CLOSES PREREG-EVL-4'S ROWS STILL WAIT ON: league/events/screen.py `made_without` over the store (the judge's own
    reading, read only: no program is run), {close day: {stale, closed_at (the finish of the close's latest
    `decide-close` receipt, epoch), status (its latest `decide-close-evl4` receipt's, None when there is none)}}; None
    when the judge's reading cannot be made (the cause says so). `prereg` 5 (release 1019h): PREREG-EVL-5's, by
    `made_without(prereg=5)` and its own kind's receipts (`decide-close-evl5`: a close a release without its rows
    decided, or whose part for them failed or ran past its own bound)."""
    try:
        from ..events import screen as SC

        waiting = SC.made_without(_Db(db), today, prereg=prereg)
        kind = SC.FILE_KINDS[int(prereg)]
    except Exception:  # noqa: BLE001 - not read: said, never a stall by itself
        return None
    out: dict[str, dict[str, Any]] = {}
    for day, stale in sorted(waiting.items()):
        key = day.isoformat()
        close = db.execute("SELECT finished_at FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                           (f"decide-close:{key}",)).fetchone()
        four = db.execute("SELECT status FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                          (f"decide-{kind}:{key}",)).fetchone()
        out[key] = {"stale": bool(stale), "closed_at": None if close is None else S.epoch(close[0]),
                    "status": None if four is None else str(four[0] or "")}
    return out


def event_twins(root: str | Path) -> list[dict[str, Any]]:
    """The House's PRICED event twins (league/ops/twins.py `event_twin`; the swarm store's kv `equity_twins`, read-only),
    oldest exit first; [] with no swarm store or no such record."""
    path = Path(root) / "swarm.sqlite"
    if not path.exists():
        return []

    def read(db: Any) -> Any:
        row = db.execute("SELECT value FROM kv WHERE key=?", (TWINS_KEY,)).fetchone()
        return None if row is None else row[0]
    raw = guard.read(path, read)
    records = _loads(raw) if isinstance(raw, str) else None
    rows = [dict(r) for r in (records or {}).values() if isinstance(r, Mapping) and r.get("kind") == "event"
            and r.get("status") == "priced"] if isinstance(records, Mapping) else []
    return sorted(rows, key=lambda r: (str(r.get("exit_day") or ""), str(r.get("judged_at") or ""), str(r.get("key"))))


def fill_gaps(twins: list[Mapping[str, Any]], look: int = FILL_LOOK) -> dict[str, Any]:
    """The signed mean gap per side (bp, positive when the real fill was worse than the shadow's auction print) over the
    last `look` priced event twins with a figure on that side: {entry_n, entry_mean_bp, exit_n, exit_mean_bp}."""
    out: dict[str, Any] = {}
    for side in ("entry", "exit"):
        values = [v for v in (_num(t.get(f"{side}_gap_bp")) for t in twins) if v is not None][-look:]
        out[f"{side}_n"] = len(values)
        out[f"{side}_mean_bp"] = None if not values else round(math.fsum(values) / len(values), 2)
    return out


# ---------------------------------------------------------------------------------------------- the causes
def _fills(now: float, twins: list[Mapping[str, Any]]) -> dict[str, Any]:
    """`evl_fills` (the module docstring): a side whose signed mean gap is more than `FILL_GAP_BP` from the shadow's
    auction prints IN EITHER DIRECTION (the review of r2/alarms, its major 3: the Done item and PREREG-EVL-3 section 5 ask
    fills WITHIN 15 bp, the signed mean per side, and A50 reads the SIZE of the mean gap; a gap either way says the fills
    or the shadow's prices, the evidence the screen judges, are mis-measured), with at least `FILL_MIN` twins on it."""
    if not twins:
        return _not_judged("no real fill of the event lane is priced beside its auction yet (the equity_twins job)")
    gaps = fill_gaps(twins)

    def mean(side: str) -> float | None:
        return gaps[f"{side}_mean_bp"] if gaps[f"{side}_n"] >= FILL_MIN else None
    off = [side for side in ("entry", "exit") if mean(side) is not None and abs(mean(side)) > FILL_GAP_BP]

    def said(side: str) -> str:
        value, n = gaps[f"{side}_mean_bp"], gaps[f"{side}_n"]
        if value is None:
            return f"{side} n/a (no priced fill)"
        if n < FILL_MIN:
            return f"{side} {value:+.1f} bp over {n} (too few to judge: {FILL_MIN} at least)"
        if abs(value) <= FILL_GAP_BP:
            return f"{side} {value:+.1f} bp over {n} (within {FILL_GAP_BP:g} bp)"
        return f"{side} {value:+.1f} bp over {n} ({'worse' if value > 0 else 'better'} than the prints by more than " \
               f"{FILL_GAP_BP:g} bp)"
    if off:
        what = (f"The event lane's real fills strayed from the shadow's auction prices: the signed mean gap "
                f"{', '.join(said(s) for s in off)}, over the last {FILL_LOOK} priced fills (the Done item asks within "
                f"{FILL_GAP_BP:g} bp a side, either way)"
                + "".join(f"; {said(s)}" for s in ("entry", "exit") if s not in off) + ".")
    else:
        what = (f"The event lane's real fills against the shadow's auction prices, the signed mean gap over the last "
                f"{FILL_LOOK} priced fills: {said('entry')}; {said('exit')}.")
    worse = [s for s in off if (mean(s) or 0.0) > 0]
    better = [s for s in off if (mean(s) or 0.0) < 0]
    return {"stalled": bool(off), "judged": True, "what": what,
            "numbers": {**gaps, "off": ",".join(off) or "none", "worse": ",".join(worse) or "none",
                        "better": ",".join(better) or "none", "last_exit_day": twins[-1].get("exit_day")},
            "doing": DOING["evl_fills"], "owner_step": None, "onset": None}


def final_lags(root: str | Path, now: float) -> list[dict[str, Any]]:
    """`evl_final`'s reads: for each seatable program (league/events/programs.py `SEATING`, in its order) registered by
    `now`, neither retired (league/events/bands.py `bands`) nor with every look written (league/events/screen.py
    `written_v2`), its final record (`screen.final_until` at `now`) beside what A69 allows: [{program, version, horizon,
    allowed, lag, why, onset}], `lag` the sessions after `horizon` (from the program's registration day when none is
    final) through `allowed`, `onset` when that lag first exceeded `FINAL_LAG_SESSIONS` (the open decision of the session
    two after the last allowed within it). A program with no session A69 can make final yet is left out. Read-only.
    WITH R3'S BIRTHS (release 1019e; release 1019f's integration): the stall job runs in its own process, where no lane
    has loaded the registered births, so the births are loaded here from the same read-only store
    (league/events/programs.py `load_births`) and a seatable birth is judged like any seating program; the table is
    left as this process had it (unloaded again when it held none)."""
    from ..events import bands as BA
    from ..events import calendar as C
    from ..events import programs as P
    from ..events import screen as SC
    from .daily_report import ReadOnlyStore

    at = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    today = at.astimezone(NY).date()
    out: list[dict[str, Any]] = []
    with guard.readonly():
        store = ReadOnlyStore(Path(root) / STORE.parent)
        had = tuple(P.BIRTHS)
        try:
            if not had:
                P.load_births(store)
            band = BA.bands(store)
            for prog in P.SEATING:
                if prog.registered_at > at or band.get((prog.id, prog.version)) == "retired":
                    continue
                # (release 1019i: a PREREG-EVL-6 version's looks are keyed by run or stay and its S, never PREREG-EVL-3's
                # ten: its runs always have a next look while it is not retired, so its record is always watched)
                if not getattr(prog, "evl6", False) and SC.written_v2(store, prog.id, prog.version)["next"] is None:
                    continue
                first = prog.registered_at.astimezone(NY).date()
                opened = [x for x in C.sessions(store, first, today) if x.open_decide <= at]
                before = [y for y in C.previous(store, opened[-1].day, 1) if y.day >= first] if opened else []
                if not before:
                    continue        # (A69 can make no close final yet: the session after one has had no open decision)
                allowed = before[-1].day
                horizon, why = SC.final_until(store, prog.id, prog.version, today, at)
                after = C.sessions(store, first if horizon is None else horizon + dt.timedelta(days=1), today)
                lag = len([x for x in after if x.day <= allowed])
                onset = after[FINAL_LAG_SESSIONS + 1].open_decide.timestamp() \
                    if lag > FINAL_LAG_SESSIONS and len(after) > FINAL_LAG_SESSIONS + 1 else None
                out.append({"program": prog.id, "version": int(prog.version), "horizon": horizon, "allowed": allowed,
                            "lag": lag, "why": str(why), "onset": onset})
        finally:
            if not had:
                P.load_births(None)
            store.close()
    return out


def _final(now: float, rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """`evl_final` (the module docstring): a seatable program's final record more than `FINAL_LAG_SESSIONS` behind what
    A69 allows, the one lagging most (the first in the table's order among them) named with the judge's why."""
    if not rows:
        return _not_judged("no seatable program has a close A69's fast path could make final yet")
    lagging = [r for r in rows if int(r["lag"]) > FINAL_LAG_SESSIONS]
    worst = max(lagging, key=lambda r: int(r["lag"]), default=None)    # (max keeps the first of equal lags)
    allowed = max(r["allowed"] for r in rows)

    def day(value: Any) -> str | None:
        return None if value is None else value.isoformat()
    if worst is None:
        what = (f"Every seatable program's final record is within {FINAL_LAG_SESSIONS} session of what A69's fast path "
                f"allows ({allowed.isoformat()}; {len(rows)} programs).")
    else:
        what = (f"The event lane's final record of {worst['program']} v{worst['version']} reaches "
                f"{day(worst['horizon']) or 'no session'} while A69's fast path allows {worst['allowed'].isoformat()}: "
                f"{worst['lag']} sessions behind, so its looks wait"
                + (f" ({len(lagging)} programs lag more than {FINAL_LAG_SESSIONS} session)" if len(lagging) > 1 else "")
                + f". The judge: {str(worst['why'])[:220]}.")
    onsets = [float(r["onset"]) for r in lagging if r.get("onset") is not None]
    return {"stalled": worst is not None, "judged": True, "what": what,
            "numbers": {"programs": len(rows), "lagging": len(lagging),
                        "program": None if worst is None else str(worst["program"]).lower(),
                        "version": None if worst is None else worst["version"],
                        "final_through": None if worst is None else day(worst["horizon"]),
                        "a69_allows": allowed.isoformat() if worst is None else worst["allowed"].isoformat(),
                        "lag_sessions": None if worst is None else worst["lag"],
                        "max_lag_sessions": max(int(r["lag"]) for r in rows)},
            "doing": DOING["evl_final"], "owner_step": None, "onset": min(onsets) if onsets else None}


def _failing(row: Mapping[str, Any]) -> list[str]:
    """The feeds a finished record pass did not read cleanly (`FEEDS`' names), [] for a clean pass."""
    summary = _loads(row.get("summary"))
    summary = summary if isinstance(summary, Mapping) else {}
    bad = []
    for key, name in FEEDS:
        block = summary.get(key)
        if not isinstance(block, Mapping) or block.get("error"):
            bad.append(name)
        elif key != "news" and (_num(block.get("failed")) or 0) > 0 and not (_num(block.get("fetched")) or 0):
            bad.append(name)   # every fetch of the pass failed: the feed reads, its documents do not
    tickers = summary.get("tickers")
    if isinstance(tickers, Mapping) and tickers.get("error") and "8k" not in bad:
        bad.insert(0, "8k")    # no tickers copy: no 8-K can be fetched
    return bad


def _record(now: float, f: Mapping[str, Any]) -> dict[str, Any]:
    window = now - RECORD_MINUTES * 60
    finished = [r for r in f["record"] if r.get("finished_at") and S.epoch(r["finished_at"]) is not None]
    passes = [r for r in finished if str(r.get("status") or "") == "ok"]
    clean = [r for r in passes if not _failing(r)]
    last = max((S.epoch(r["finished_at"]) for r in clean), default=None)
    recent = [r for r in finished if S.epoch(r["finished_at"]) >= window]
    failed = [r for r in recent if str(r.get("status") or "") != "ok"]
    seen = [r for r in recent if str(r.get("status") or "") == "ok"] or passes[-1:]
    feeds: list[str] = []
    for r in seen:
        for name in _failing(r):
            if name not in feeds:
                feeds.append(name)
    stalled = last is None or last < window
    words = {"8k": "the 8-K feed", "form4": "the Form 4 feed", "news": "the news"}
    named = " and ".join(words[n] for n in feeds) if feeds else None
    if last is None and not finished:
        what = "The event lane has finished no record pass on record (none in the last 5 days)."
    elif stalled:
        what = (f"The event lane finished no clean record pass in the last {RECORD_MINUTES} minutes"
                + (f": {named} could not be read" if named else (": its passes failed" if failed else ""))
                + ("" if last is None else f" (the last clean one ended {_hhmm(last)} ET, "
                                           f"{round((now - last) / 60)} minutes ago).")
                + ("." if last is None else ""))
    else:
        what = f"The event lane's last clean record pass ended {_hhmm(last)} ET."
        if named:
            what += f" Some passes of the last {RECORD_MINUTES} minutes could not read {named}."
    return {"stalled": stalled, "judged": True, "what": what,
            "numbers": {"last_clean_at": None if last is None else S.iso(last),
                        "minutes_since_clean": None if last is None else round((now - last) / 60.0, 1),
                        f"passes_{RECORD_MINUTES}m": len([r for r in recent if str(r.get('status') or '') == 'ok']),
                        f"clean_{RECORD_MINUTES}m": len([r for r in clean if S.epoch(r["finished_at"]) >= window]),
                        f"failed_{RECORD_MINUTES}m": len(failed), "failing": ",".join(feeds) or "none"},
            "doing": DOING["evl_record"], "owner_step": None, "onset": last if stalled else None}


def made(rows: list[Mapping[str, Any]], ends: float) -> bool:
    """A decision MADE IN ITS WINDOW: a receipt that finished `ok` or `pending` by `ends` (its time and the lane's own
    LIVE_WITHIN: what the real-money decision of that auction waits for, league/events/book.py `decided`)."""
    return any(str(r.get("status") or "") in ("ok", "pending") and r.get("finished_at")
               and (S.epoch(r["finished_at"]) or float("inf")) <= ends for r in rows)


FOUR_WORDS = {"never": "was never run", "failed": "failed", "cut": "was cut by the lane's time bound",
              "unfinished": "never finished", "pending": "waits on its verdicts",
              "stale": "is older than the close's latest decision (decided again by a release without the rows)"}


def four_kept(kept: Any, four: Mapping[str, Any] | None, now: float) -> dict[str, str]:
    """The stall job's FIRST SIGHT of each close PREREG-EVL-4's rows still wait on (`four_waiting`), {day: ISO time}, kept
    in stall.json (`evl_kept` `four`; PREREG-EVL-5's under `five`, release 1019h): a close seen now keeps its first sight
    (or takes now), one that no longer waits is dropped; with nothing read (None) what was kept stays."""
    seen = kept if isinstance(kept, Mapping) else {}
    if four is None:
        return {str(k): str(v) for k, v in seen.items() if S.epoch(v) is not None}
    return {day: str(seen[day]) if S.epoch(seen.get(day)) is not None else S.iso(now) for day in four}


def _four_state(row: Mapping[str, Any]) -> str:
    status = row.get("status")
    if status is None:
        return "never"
    if status == "ok":
        return "stale"
    return status if status in ("failed", "cut", "pending") else "unfinished"


def _four(now: float, four: Mapping[str, Any] | None, seen: Mapping[str, Any], idle: Mapping[str, list]) -> list:
    """PREREG-EVL-4's (or PREREG-EVL-5's: `FILE_WAITS`) rows still to decide by themselves (the module docstring): each
    close of `four` waiting `FOUR_REFILL_HOURS` since the later of the stall job's first sight (`seen`), the finish of its
    latest `decide-close` receipt and the end of the last STOP or PAUSE, oldest first. None while the House's PAUSE
    stands (no verdict is asked: a decision waiting on them waits by design)."""
    if not four or _open(list(idle.get("pause") or [])):
        return []
    quiet = max([float(end) for start, end in (idle.get("stop") or []) + (idle.get("pause") or []) if end is not None],
                default=None)
    out = []
    for day, row in sorted(four.items()):
        first = S.epoch(seen.get(day))
        start = max([t for t in (now if first is None else first, _num(row.get("closed_at")), quiet) if t is not None])
        if now - start >= FOUR_REFILL_HOURS * 3600:
            out.append({"day": day, "state": _four_state(row), "since": start})
    return out


def _decide(now: float, f: Mapping[str, Any], kinds: tuple[str, ...], stops: list, *,
            idle: Mapping[str, list] | None = None, seen: Mapping[str, Any] | None = None) -> dict[str, Any]:
    due = decisions(now, kinds)
    missed, excused = [], 0
    for d in due:
        rows = f["decide"].get(f"decide-{d['kind']}:{d['day']}", [])
        if made(rows, d["ends"]):
            continue
        if _within(d["at"], stops, now) or _within(d["ends"], stops, now):
            excused += 1
            continue
        tried = [r for r in rows if (S.epoch(r["started_at"]) or float("inf")) <= d["ends"]]
        if not tried:
            state = "missing"
        else:
            status, done = str(tried[-1].get("status") or ""), tried[-1].get("finished_at")
            state = ("late" if done and status in ("ok", "pending") else "unfinished" if not done or status == "running"
                     else status if status in ("failed", "cut") else "failed")
        later = any(str(r.get("status") or "") in ("ok", "pending") and r.get("finished_at") for r in rows)
        missed.append({**d, "state": state, "later": later})
    windows = idle if isinstance(idle, Mapping) else {"stop": stops}
    seen = seen or {}
    # (release 1019h: PREREG-EVL-5's rows too, each file by its own kind, kept apart: `FILE_WAITS`)
    by_file = {n: _four(now, f.get(key), seen.get(kept) if isinstance(seen.get(kept), Mapping) else {}, windows)
               for n, (key, kept, _) in FILE_WAITS.items()}
    waits = by_file[4]
    first = missed[0] if missed else None
    if first is None:
        what = (f"Every scheduled decision of the last {DECIDE_LOOKBACK_HOURS:g} h was made in its window ({len(due)})."
                if due else f"No decision was due in the last {DECIDE_LOOKBACK_HOURS:g} h.")
    else:
        words = {"missing": "was never started", "failed": "failed", "cut": "was cut by the lane's time bound",
                 "unfinished": "never finished", "late": "finished after its window"}
        what = (f"The event lane's {first['kind']} decision of {first['day']} ({_hhmm(first['at'])} ET) was not made in "
                f"its {DECIDE_GRACE_MINUTES}-minute window: it {words.get(first['state'], first['state'])}"
                + ("; it was decided later, for the shadow record only" if first["later"] else "")
                + (f". {len(missed)} decisions of the last {DECIDE_LOOKBACK_HOURS:g} h were missed in all." if len(missed) > 1
                   else "."))
    for n, (key, _, name) in FILE_WAITS.items():
        found = by_file[n]
        if found:
            w = found[0]
            how = ("a release decided it without them" if n == 4 else
                   "a release decided it without them or their part of it failed")
            text = (f"{name}'s rows of the close of {w['day']} are still to decide by themselves "
                    f"{_hours_of(now - w['since'])} h after {how}: its decide-close-evl{n} "
                    f"{FOUR_WORDS[w['state']]}" + (f" ({len(found)} closes in all)" if len(found) > 1 else "") + ".")
            what = text if first is None and not any(by_file[m] for m in FILE_WAITS if m < n) else f"{what} {text}"
        elif f.get(key) is None:
            what += f" {name}'s closes could not be read (league/events/screen.py made_without)."
    fives = by_file[5]
    onsets = [w["since"] for found in by_file.values() for w in found[:1]]
    return {"stalled": bool(missed) or any(by_file.values()), "judged": True, "what": what,
            "numbers": {"decisions_due": len(due), "missed": len(missed), "excused_stop": excused,
                        "first_missed": None if first is None else f"{first['kind']}:{first['day']}",
                        "first_missed_at": None if first is None else S.iso(first["at"]),
                        "first_state": None if first is None else first["state"],
                        "decided_later": sum(1 for m in missed if m["later"]),
                        "four_waiting": len(waits), "four_first": waits[0]["day"] if waits else None,
                        "four_state": waits[0]["state"] if waits else None,
                        "four_hours": round((now - waits[0]["since"]) / 3600.0, 1) if waits else None,
                        "five_waiting": len(fives), "five_first": fives[0]["day"] if fives else None,
                        "five_state": fives[0]["state"] if fives else None,
                        "five_hours": round((now - fives[0]["since"]) / 3600.0, 1) if fives else None},
            "doing": DOING["evl_decide"], "owner_step": None,
            "onset": first["ends"] if first is not None else (min(onsets) if onsets else None)}


def _hours_of(seconds: float) -> str:
    return f"{max(0.0, seconds) / 3600.0:.1f}"


def tally(row: Mapping[str, Any]) -> tuple[int | None, int] | None:
    """(needed, unanswered) of one decision receipt: its tally (run.py `verdicts`), else, for a receipt from before the
    tally, (None, the sum of its `pending` counts) when it waits; None when it says nothing of verdicts."""
    summary = _loads(row.get("summary"))
    summary = summary if isinstance(summary, Mapping) else {}
    counts = summary.get("verdicts")
    if isinstance(counts, Mapping):
        n, a = _num(counts.get("needed")), _num(counts.get("answered"))
        if n is not None and a is not None and n >= 0 and 0 <= a <= n:
            return int(n), int(n - a)
    pending = summary.get("pending")
    if isinstance(pending, Mapping):
        waiting = [_num(v) for v in pending.values()]
        if all(v is not None and v >= 0 for v in waiting):
            return None, int(sum(waiting))
    return None


def four_decisions(now: float, f: Mapping[str, Any], *, prereg: int = 4) -> list[dict[str, Any]]:
    """PREREG-EVL-4's own decisions (`decide-close-evl4:<day>`, each a backfill of its close: league/events/run.py
    `decide_close` with `evl4_only`) whose latest receipt started inside the last `DECIDE_LOOKBACK_HOURS`, as
    `decisions` gives the scheduled ones: [{kind, day, at, ends}], `at` the close's decision time. `prereg` 5 (release
    1019h): PREREG-EVL-5's (`decide-close-evl5:<day>`, `decide_close` with `evl5_only`)."""
    try:
        from ..events.screen import FILE_KINDS
        FOUR_KIND = FILE_KINDS[int(prereg)]
    except Exception:  # noqa: BLE001 - the judge's name for it, as releases 1019d and 1019g ship it
        FOUR_KIND = f"close-evl{int(prereg)}"
    head = f"decide-{FOUR_KIND}:"
    out = []
    for job, rows in (f.get("decide") or {}).items():
        if not str(job).startswith(head) or not rows:
            continue
        started = S.epoch(rows[-1].get("started_at"))
        if started is None or started < now - DECIDE_LOOKBACK_HOURS * 3600:
            continue
        try:
            day = dt.date.fromisoformat(str(job)[len(head):])
        except ValueError:
            continue
        found = sessions(day, day)
        if not found or found[0]["close_at"] is None:
            continue
        at = found[0]["close_at"] - CLOSE_DECIDE_BEFORE.total_seconds()
        if at <= now:
            out.append({"kind": FOUR_KIND, "day": day.isoformat(), "at": at, "ends": at + DECIDE_GRACE_MINUTES * 60})
    return sorted(out, key=lambda d: d["at"])


def _verdicts(now: float, f: Mapping[str, Any], kinds: tuple[str, ...], idle: Mapping[str, list],
              line: Mapping[str, Any] | None) -> dict[str, Any]:
    due = decisions(now, kinds) + [d for n in FILE_WAITS for d in four_decisions(now, f, prereg=n)]
    held, needed_all, unanswered_all, read = [], 0, 0, 0
    quiet_until = max([float(end) for start, end in (idle.get("stop") or []) + (idle.get("pause") or [])
                       if end is not None], default=None)
    for d in due:
        rows = [r for r in f["decide"].get(f"decide-{d['kind']}:{d['day']}", []) if r.get("finished_at")]
        counted = [(r, tally(r)) for r in rows]
        counted = [(r, t) for r, t in counted if t is not None]
        if not counted:
            continue
        read += 1
        latest, (needed, missing) = counted[-1]
        if needed is not None:
            needed_all += needed
        unanswered_all += missing
        if missing <= 0:
            continue
        streak = latest
        for r, t in reversed(counted):
            if t[1] <= 0:
                break
            streak = r
        since = max(d["at"], S.epoch(streak["started_at"]) or d["at"])
        if quiet_until is not None and since <= quiet_until:
            since = max(since, quiet_until)
        if _within(d["at"], idle.get("stop") or [], now):
            continue
        if now - since >= VERDICT_GRACE_MINUTES * 60:
            held.append({**d, "missing": missing, "needed": needed, "since": since})
    first = held[0] if held else None
    spent, limit = (None, None) if not line else (_num(line.get("spent_usd")), _num(line.get("line_usd")))
    at_line = spent is not None and limit is not None and spent >= limit - 1e-9
    if first is None:
        what = (f"No verdict a decision of the last {DECIDE_LOOKBACK_HOURS:g} h needed is unanswered past it." if read
                else f"No decision of the last {DECIDE_LOOKBACK_HOURS:g} h carries a verdict tally.")
    else:
        own = {f"close-evl{n}": name for n, (_, _, name) in FILE_WAITS.items()}
        kind = (f"close decision of {own.get(first['kind'], 'PREREG-EVL-4')}'s rows"
                if first["kind"] != "open" and first["kind"] != "close" else f"{first['kind']} decision")
        what = (f"{first['missing']} verdicts the event lane's {kind} of {first['day']} needs have no "
                f"answer {round((now - first['since']) / 60)} minutes past it"
                + (f" ({len(held)} decisions in all)" if len(held) > 1 else "")
                + ("; the lane's verdict line for the day is reached" if at_line else "") + ".")
    return {"stalled": bool(held), "judged": True, "what": what,
            "numbers": {"decisions_read": read, "held": len(held), "unanswered": unanswered_all, "needed": needed_all,
                        "first_held": None if first is None else f"{first['kind']}:{first['day']}",
                        "unanswered_since": None if first is None else S.iso(first["since"]),
                        "verdict_usd_today": None if spent is None else round(spent, 4),
                        "verdict_line_usd": None if limit is None else round(limit, 4), "at_line": at_line},
            "doing": DOING["evl_verdicts"], "owner_step": None, "onset": None if first is None else first["since"]}


def score_session(now: float) -> dict[str, Any] | None:
    """The latest session whose 23:00 ET (`SCORE_BY`) has passed, within the last 10 days."""
    today = dt.datetime.fromtimestamp(now, NY).date()
    for s in reversed(sessions(today - dt.timedelta(days=10), today)):
        if _ny(s["day"], SCORE_BY) <= now:
            return s
    return None


def _waiting_on_tape(row: Mapping[str, Any], marks: set) -> bool:
    """An open intent whose exit print, or its benchmark's print, the tape showed absent (a `marks` row with no price on
    its entry day or at or after its exit day; `marks` holds only the score's own labels, `TAPE_LABELS`, as `facts`
    reads them): PREREG-EVL-1 section 5's ladder waits on a later session by design."""
    for symbol in (str(row["symbol"]), str(row.get("bench") or "")):
        if not symbol:
            continue
        if any(m_symbol == symbol and (m_day >= str(row["exit_day"]) or (symbol != str(row["symbol"])
                                                                           and m_day == str(row["entry_day"])))
               for m_symbol, m_day in marks):
            return True
    return False


#: A decision receipt's job: its entry kind and day (`decide-<kind>:<day>`, and the later rows' own receipts of it,
#: `decide-close-evl4:<day>`, `decide-open-births:<day>`, `decide-close-births:<day>`).
DECIDE_JOB = re.compile(r"^decide-(open|close)(?:-[a-z0-9]+)?:(\d{4}-\d{2}-\d{2})$")


def written_after(f: Mapping[str, Any], since: float) -> set[tuple[str, str, str]]:
    """RELEASE 1019f's INTEGRATION (`evl_score`'s false alarm of Oct 21, 2026: a catch-up decision, PREREG-EVL-4's rows
    decided by themselves for an older close once release 1019d was live, wrote intents due by the night's session
    after that night's score pass had run): {(program key, entry kind, entry day)} that a decision receipt STARTED after
    `since` wrote new intents for (its summary's counts under the program's key, league/events/run.py `_key`, with
    `planned` > 0). Those intents wait for the next score pass by design."""
    out: set[tuple[str, str, str]] = set()
    for job, rows in (f.get("decide") or {}).items():
        match = DECIDE_JOB.match(str(job))
        if match is None:
            continue
        for r in rows:
            started = S.epoch(r.get("started_at"))
            if started is None or started <= since:
                continue
            summary = _loads(r.get("summary"))
            for key, counts in (summary.items() if isinstance(summary, Mapping) else ()):
                if isinstance(counts, Mapping) and (_num(counts.get("planned")) or 0) > 0:
                    out.add((str(key), match.group(1), match.group(2)))
    return out


def _score(now: float, f: Mapping[str, Any], latest: Mapping[str, Any]) -> dict[str, Any]:
    from ..events.screen import program_key

    day = latest["day"].isoformat()
    open_due = list(f["open_due"])
    waiting = [r for r in open_due if _waiting_on_tape(r, f["none_marks"])]
    stuck = [r for r in open_due if r not in waiting]
    after = latest["close_at"] + 16 * 60
    passes = [r for r in f["score"] if (S.epoch(r["started_at"]) or 0.0) >= after]
    last = passes[-1] if passes else (f["score"][-1] if f["score"] else None)
    # (Release 1019f's integration: an intent a decision wrote after the night's last score pass started is the next
    # pass's to settle, never a stall of this one; with no pass after the close, nothing is excused.)
    fresh = written_after(f, S.epoch(passes[-1]["started_at"]) or 0.0) if passes else set()
    new = [r for r in stuck if (program_key(str(r["program"]), int(r["version"])), str(r.get("entry_at") or ""),
                                str(r["entry_day"])) in fresh]
    stuck = [r for r in stuck if r not in new]
    summary = _loads(last.get("summary")) if last else None
    summary = summary if isinstance(summary, Mapping) else {}
    errors = int(_num(summary.get("errors")) or 0) if not isinstance(summary.get("errors"), list) else len(summary["errors"])
    stalled = bool(stuck)
    if stalled:
        what = (f"{len(stuck)} intents due by the session of {day} are still open after the night's score "
                + (f"passes (the last at {_hhmm(S.epoch(last['started_at']))} ET, {str(last.get('status') or 'running')}, "
                   f"{errors} errors)." if passes else "passes: no score pass ran after its close."))
    elif new or waiting:
        what = (f"Every intent due by the session of {day} is settled but "
                + " and ".join(x for x in ((f"{len(waiting)} the tape keeps waiting (no print)" if waiting else ""),
                                           (f"{len(new)} a decision wrote after the night's last score pass (the next "
                                            "pass settles them)" if new else "")) if x) + ".")
    else:
        what = f"Every intent due by the session of {day} is settled."
    return {"stalled": stalled, "judged": True, "what": what,
            "numbers": {"day": day, "open_due": len(stuck), "waiting_on_tape": len(waiting), "after_last_pass": len(new),
                        "passes": len(passes),
                        "last_pass_at": None if last is None else last["started_at"],
                        "last_pass_status": None if last is None else str(last.get("status") or "running")[:20],
                        "last_pass_errors": errors},
            "doing": DOING["evl_score"], "owner_step": None,
            "onset": _ny(latest["day"], SCORE_BY) if stalled else None}


# ---------------------------------------------------------------------------------------------- the entries (1019f)
#: The book's words for a buy held from its send (league/equity/live.py `_event_work_entry`, `_count_refusal`,
#: `_open_block`, `_symbol_busy`, `_size_event`), lower case, and the reason each is; the first that matches names it.
UNSENT_WORDS = (("order count", "order_line"), ("has on order more than its", "room"), ("eligible list", "gateway"),
                ("the refused buy", "gateway"), ("a sale of", "sale"), ("one order a symbol", "busy"),
                ("could not be read", "unreadable"), ("cannot be read", "unreadable"), ("no sizing equity", "unreadable"),
                ("kill switch", "blocked"), ("paper proof", "blocked"), ("exits only", "blocked"),
                ("reconciliation", "blocked"), ("not at probe or sized", "blocked"), ("real-money block", "blocked"))
#: RELEASE 1019g: PREREG-EVL-5's buys held for the lane's own close decision (league/events/book.py `part_hold`: it
#: waited for that decision to name its program, its words `book.PART_WAIT`, or the decision finished without its
#: rows: never traded) are held by a gate of real opens, as its section 1.3 states it, not another reason; FIRST, so a
#: wait whose receipt "cannot be read" is that gate too. (A later buy that waits for the room kept for them,
#: live.py `HELD_ROOM`, is named by its own sizing's binding, as any buy no whole share fits.)
PART_WAIT_WORDS = "waits for the lane's own close decision"
UNSENT_WORDS = ((PART_WAIT_WORDS, "blocked"), ("prereg-evl-5's", "blocked"), *UNSENT_WORDS)
UNSENT_SAID = {"order_line": "the day order count", "cash": "cash", "budget": "the loss budget",
               "name_wall": "the 10% a name", "invested": "the invested cap", "room": "the program's room",
               "price": "one share too dear", "min_order": "under the minimum order", "gateway": "the gateway",
               "sale": "a sale of the name at the same cross", "busy": "a working order of the name",
               "blocked": "a gate of real opens", "unreadable": "a figure unread", "other": "another reason"}


def venue_cancel_ms(order: Mapping[str, Any]) -> int | None:
    """THE CAPTAIN'S A80: the milliseconds THE VENUE took to cancel this order (an `eq_orders` row) after its own
    submission, read off the venue's own stamps the book keeps (`answer.submitted_at`, `answer.canceled_at`, RFC 3339,
    league/live/venue.py `parse_time`), when it is an AUCTION BUY the venue ended `canceled` within `VENUE_CANCEL_S` of its
    submission with nothing filled and no cancel of the House's own sent (`answer.cancel_sent`); None otherwise (a sale,
    a day order, a fill, an order the House cancelled or the venue replaced, a stamp missing or unreadable, a cancel
    later than that: the auction's own end of an unfilled order). The rule release 1019e's re-send reads
    (league/equity/live.py `venue_cancel_ms`)."""
    from ..live.venue import parse_time

    answer = order.get("answer")
    answer = answer if isinstance(answer, Mapping) else _loads(answer)
    answer = answer if isinstance(answer, Mapping) else {}
    if (str(order.get("side") or "") != "buy" or str(order.get("tif") or "") not in ("opg", "cls")
            or str(order.get("status") or "") != "canceled" or answer.get("final") != "canceled"):
        return None
    if (_num(order.get("filled_qty")) or 0.0) > 0 or "cancel_sent" in answer:
        return None
    submitted, canceled = parse_time(answer.get("submitted_at")), parse_time(answer.get("canceled_at"))
    if submitted is None or canceled is None:
        return None
    took = canceled - submitted
    if not -VENUE_STAMP_SLACK_S <= took <= VENUE_CANCEL_S:
        return None
    return max(0, int(round(took * 1000)))


def unsent_reason(why: Any, refused: Mapping[str, Any] | None = None) -> str:
    """Why an event buy never reached the venue, one of `UNSENT`: the gateway's cap on the order it refused
    (`GATEWAY_CAPS`, else "gateway"), else the size rule's binding when no whole share fit (`SIZING_BINDS`; "price" when
    one share at the limit was above the band's one-share cap), else the book's own words on the intent (`UNSENT_WORDS`:
    the last reason a gate held it by, `_event_finish`'s "never sent: ..."); "other" for anything else."""
    cap = str((refused or {}).get("cap") or "")
    if cap:
        return GATEWAY_CAPS.get(cap, "gateway")
    text = str(why or "")
    bound = re.search(r"no whole share fits \(([a-z_]+)\)", text)
    if bound:
        return SIZING_BINDS.get(bound.group(1), "other")
    if "no whole share fits" in text:
        return "price"
    low = text.lower()
    return next((reason for needle, reason in UNSENT_WORDS if needle in low), "other")


def sent_binding(why: Any) -> str | None:
    """The constraint that cut a SENT event buy below its band's target (its order's `why`: "event entry at the open (N
    shares at learning (cash): ..."), one of `BOUND`; None when the target was bought whole or the words say no cut."""
    found = re.search(r"\d+ shares at [a-z]+ \(([a-z_]+)\)", str(why or ""))
    name = SIZING_BINDS.get(found.group(1)) if found else None
    return name if name in BOUND else None


def auctions(now: float, hours: float = ENTRY_HOURS) -> list[dict[str, Any]]:
    """The auctions (the opening and closing crosses of the House's NYSE sessions) inside the last `hours` whose cross is
    `AUCTION_SETTLE_MINUTES` behind: [{day, at, t}] (`t` the cross, epoch), oldest first."""
    today = dt.datetime.fromtimestamp(now, NY).date()
    out = []
    for s in sessions(today - dt.timedelta(days=4), today):
        for at, t in (("open", s["open_at"]), ("close", s["close_at"])):
            if t is not None and now - hours * 3600 <= t and t + AUCTION_SETTLE_MINUTES * 60 <= now:
                out.append({"day": s["day"].isoformat(), "at": at, "t": float(t)})
    return sorted(out, key=lambda a: a["t"])


def auctions_of(day: str) -> list[dict[str, Any]]:
    """The two auctions of New York day `day` ([] with no session that day)."""
    on = dt.date.fromisoformat(day)
    return [{"day": day, "at": at, "t": float(t)} for s in sessions(on, on)
            for at, t in (("open", s["open_at"]), ("close", s["close_at"])) if t is not None]


def decision_room(decision: Mapping[str, Any] | None) -> dict[str, Any]:
    """What the book's decision of an auction (`eq_event_decisions` summary: each program's picks, room, planned and
    skipped) left out before any buy was planned: the picks beyond the programs' room (`room_cut`), the programs that
    read nothing for having no room (`programs_full`), and the picks the real-money rules skipped whatever the room
    (league/events/book.py `allocate`: the 10% a name, one share too dear, a sale of the name at the same cross)."""
    summary = _loads(decision.get("summary")) if isinstance(decision, Mapping) else None
    programs = summary.get("programs") if isinstance(summary, Mapping) else None
    picks = room_cut = full = 0
    skipped: dict[str, int] = {}
    for p in (programs.values() if isinstance(programs, Mapping) else ()):
        if not isinstance(p, Mapping):
            continue
        skip = p.get("skipped") if isinstance(p.get("skipped"), Mapping) else {}
        passed = 0
        for name, n in skip.items():
            skipped[str(name)] = skipped.get(str(name), 0) + int(_num(n) or 0)
            passed += int(_num(n) or 0)
        wanted = _num(p.get("picks"))
        if wanted is None:
            full += int(_num(p.get("room")) == 0)
            continue
        picks += int(wanted)
        room_cut += max(0, int(wanted) - int(_num(p.get("planned")) or 0) - passed)
    return {"decided": isinstance(decision, Mapping) and str(decision.get("status") or "") == "done", "picks": picks,
            "room_cut": room_cut, "programs_full": full, "skipped_name_wall": skipped.get("name_wall", 0),
            "skipped_price": skipped.get("one_share", 0), "skipped_sale": skipped.get("sale", 0),
            # (release 1019i, PREREG-EVL-6 section 6: a pick of its versions no whole-share count brings to Done's
            # size bar inside the band's envelope, counted beside one share too dear: A98 (5))
            "skipped_under_bar": skipped.get("under_bar", 0)}


def auction_entries(rows: list[Mapping[str, Any]], orders: Mapping[int, list[Mapping[str, Any]]],
                    decision: Mapping[str, Any] | None) -> dict[str, Any]:
    """One auction's real event buys (`rows`: its `eq_event_intents` buys with their `eq_intents` status and why;
    `orders`: each buy's `eq_orders` in send order) and its decision (`decision_room`): planned, filled, the venue's
    cancels at once (A80) and the re-sends after one (and how many of those filled), the buys never sent by reason
    (`unsent_reason`), sent and not filled (`unfilled`), still to finish (`unfinished`), cut below target by a
    constraint (`cut`), and the constraint that bound the auction most (`bound`, of `BOUND`, "none": the buys stopped
    or cut by each, the decision's room cut and its name-wall skips with them)."""
    never: dict[str, int] = {}
    cut: dict[str, int] = {}
    filled = venue = resent = resent_filled = unfilled = unfinished = 0
    for r in rows:
        mine = list(orders.get(int(r["iid"]), []))
        reached = [o for o in mine if str(o.get("status") or "") not in UNSENT_ORDERS]
        got = math.fsum(_num(o.get("filled_qty")) or 0.0 for o in mine) > 0
        cancels = [o for o in mine if venue_cancel_ms(o) is not None]
        if cancels:
            venue += 1
            if any(int(o["eid"]) > int(cancels[0]["eid"]) for o in reached):
                resent += 1
                resent_filled += int(got)
        live = str(r.get("status") or "") in ("planned", "sent")
        if got:
            filled += 1
        elif not reached:
            last = mine[-1] if mine else None
            answer = _loads(last.get("answer")) if last is not None else None
            refused = answer if isinstance(answer, Mapping) and str(last.get("status") or "") == "refused" else None
            reason = unsent_reason(r.get("why"), refused)
            never[reason] = never.get(reason, 0) + 1
        elif live:
            unfinished += 1
        elif not cancels:
            unfilled += 1
        binding = sent_binding(reached[0].get("why")) if reached else None
        if binding is not None:
            cut[binding] = cut.get(binding, 0) + 1
    room = decision_room(decision)
    tally = {"cash": never.get("cash", 0) + cut.get("cash", 0), "budget": never.get("budget", 0) + cut.get("budget", 0),
             "room": room["room_cut"] + never.get("room", 0), "order_line": never.get("order_line", 0),
             "name_wall": never.get("name_wall", 0) + cut.get("name_wall", 0) + room["skipped_name_wall"],
             "invested": never.get("invested", 0) + cut.get("invested", 0)}
    top = max(tally.values())
    return {"planned": len(rows), "filled": filled, "venue_cancels": venue, "resent": resent,
            "resent_filled": resent_filled, "never_sent": sum(never.values()),
            "never": {k: never.get(k, 0) for k in UNSENT}, "unfilled": unfilled, "unfinished": unfinished,
            "cut": {k: cut.get(k, 0) for k in BOUND}, **room,
            "bound": next(k for k in BOUND if tally[k] == top) if top > 0 else "none"}


def entry_facts(root: str | Path, wanted: list[Mapping[str, Any]]) -> list[dict[str, Any]] | None:
    """Each auction of `wanted` ([{day, at, t}], `auctions` or `auctions_of`) as the book's own rows in
    `<state>/live.sqlite` tell it (read-only, one transaction): [{day, at, t, **`auction_entries`}], in `wanted`'s order;
    None with no live.sqlite or no event table in it (the book has planned no event buy on this House)."""
    path = Path(root) / LIVE_DB
    if not path.exists():
        return None
    days = sorted({str(w["day"]) for w in wanted})

    def read(db: Any) -> dict[str, Any] | None:
        names = {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if not {"eq_event_intents", "eq_intents", "eq_orders"} <= names:
            return None
        if not days:
            return {"intents": [], "orders": [], "decisions": []}
        intents = guard.batched(db, "SELECT e.iid, e.program, e.version, e.day, e.at, e.band, i.status, i.why FROM "
                                    "eq_event_intents e JOIN eq_intents i ON i.iid=e.iid WHERE e.side='buy' AND e.day IN "
                                    "({marks}) ORDER BY e.iid", days)
        iids = [int(r["iid"]) for r in intents]
        orders = guard.batched(db, "SELECT * FROM eq_orders WHERE iid IN ({marks}) ORDER BY eid", iids) if iids else []
        made = guard.batched(db, "SELECT day, at, status, summary FROM eq_event_decisions WHERE day IN ({marks})",
                             days) if "eq_event_decisions" in names else []
        return {"intents": intents, "orders": orders, "decisions": made}
    got = guard.read(path, read)
    if got is None:
        return None
    by_iid: dict[int, list[Mapping[str, Any]]] = {}
    for o in got["orders"]:
        by_iid.setdefault(int(o["iid"]), []).append(o)
    made = {(str(d["day"]), str(d["at"])): d for d in got["decisions"]}
    return [{**w, **auction_entries([r for r in got["intents"] if str(r["day"]) == w["day"] and str(r["at"]) == w["at"]],
                                    by_iid, made.get((str(w["day"]), str(w["at"]))))} for w in wanted]


def entry_totals(found: list[Mapping[str, Any]]) -> dict[str, Any]:
    """The auctions' counts added up (the `never` reasons and `cut` constraints too)."""
    keys = ("planned", "filled", "venue_cancels", "resent", "resent_filled", "never_sent", "unfilled", "unfinished",
            "room_cut", "skipped_name_wall", "skipped_price", "skipped_under_bar")
    out: dict[str, Any] = {k: sum(int(a.get(k) or 0) for a in found) for k in keys}
    for group, order in (("never", UNSENT), ("cut", BOUND)):
        out[group] = {k: sum(int((a.get(group) or {}).get(k) or 0) for a in found) for k in order}
    out["auctions"] = len(found)
    return out


def short_of(a: Mapping[str, Any]) -> bool:
    """An auction whose real buys fell short: under `ENTRY_FILL_SHARE` of its planned buys filled, or one never sent."""
    planned = int(a.get("planned") or 0)
    return planned > 0 and (int(a.get("filled") or 0) < ENTRY_FILL_SHARE * planned - 1e-9 or int(a.get("never_sent") or 0) > 0)


def _pct(part: int, whole: int) -> int | None:
    return None if not whole else int(round(100.0 * part / whole))


def _entries(now: float, found: list[dict[str, Any]] | None) -> dict[str, Any]:
    """`evl_entries` (the module docstring)."""
    if found is None:
        return _not_judged("no event table in live.sqlite (the book has planned no real event buy on this House)")
    total = entry_totals(found)
    short = [a for a in found if short_of(a)]
    pct = _pct(total["filled"], total["planned"])
    reasons = ", ".join(f"{UNSENT_SAID[k]} {n}" for k, n in total["never"].items() if n)
    if not total["planned"]:
        what = (f"No real event buy was planned at the {len(found)} auctions of the last {ENTRY_HOURS:g} h."
                if found else f"No auction's cross of the last {ENTRY_HOURS:g} h is {AUCTION_SETTLE_MINUTES} minutes behind.")
    else:
        first = short[0] if short else None
        what = ((f"Real event buys fell short at {len(short)} of {len(found)} auctions of the last {ENTRY_HOURS:g} h: "
                 if short else f"Real event buys at the {len(found)} auctions of the last {ENTRY_HOURS:g} h: ")
                + f"{total['filled']} of {total['planned']} planned filled ({pct}%, the bar {ENTRY_FILL_SHARE:.0%})"
                + (f"; the venue cancelled {total['venue_cancels']} at once (A80)" if total["venue_cancels"] else "")
                + (f", {total['resent']} went again once ({total['resent_filled']} filled)" if total["resent"] else "")
                + (f"; {total['never_sent']} never sent ({reasons})" if total["never_sent"] else "; none never sent")
                + (f"; {total['unfilled']} sent and not filled at the cross" if total["unfilled"] else "")
                + (f"; {total['unfinished']} not finished yet" if total["unfinished"] else "")
                + (f". The {first['at']} of {first['day']} bound most on {UNSENT_SAID.get(first['bound'], first['bound'])}"
                   if first is not None and first["bound"] != "none" else "") + ".")
    first = short[0] if short else None
    numbers: dict[str, Any] = {"auctions": len(found), "planned": total["planned"], "filled": total["filled"],
                               "fill_pct": pct, "venue_cancels": total["venue_cancels"], "resent": total["resent"],
                               "resent_filled": total["resent_filled"], "never_sent": total["never_sent"],
                               "unfilled": total["unfilled"],
                               "short_first": None if first is None else f"{first['at']}:{first['day']}",
                               "bound": (first or (found[-1] if found else {})).get("bound") or "none"}
    numbers.update({f"never_{k}": n for k, n in total["never"].items() if n})
    return {"stalled": bool(short), "judged": True, "what": what, "numbers": numbers, "doing": DOING["evl_entries"],
            "owner_step": None, "onset": None if first is None else first["t"] + AUCTION_SETTLE_MINUTES * 60}


# ---------------------------------------------------------------------------------------------- the backfill (1019f)
def backfill_reach(now: float) -> list[dt.date]:
    """The weekdays the House's daily-index backfill reads (league/events/house.py `_backfill_due`: the last
    `BACKFILL_WEEKDAYS` weekdays before today, none before the lane's registration), oldest first."""
    try:
        from ..events import house as H

        weekdays = int(H.BACKFILL_WEEKDAYS)
    except Exception:  # noqa: BLE001 - the judge's own reach, as release 1019d ships it
        weekdays = 3
    try:
        from ..events import programs as P

        start: dt.date | None = P.registered().astimezone(NY).date()
    except Exception:  # noqa: BLE001 - no registration read: every weekday of the reach
        start = None
    day, out = dt.datetime.fromtimestamp(now, NY).date(), []
    while len(out) < weekdays:
        day -= dt.timedelta(days=1)
        if day.weekday() < 5:
            out.append(day)
    return sorted(d for d in out if start is None or d >= start)


def backfill_due(day: dt.date) -> float:
    """When the backfill of weekday `day` is due done: `BACKFILL_DUE` (12:00 ET) of the next weekday."""
    nxt = day + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return _ny(nxt, BACKFILL_DUE)


def _backfill(now: float, f: Mapping[str, Any], reach: list[dt.date]) -> dict[str, Any]:
    """`evl_backfill` (the module docstring), from the lane's `backfill` receipts and its `evl:backfill:<day>` meta."""
    meta = f.get("backfill_meta") or {}
    by_day: dict[str, list[Mapping[str, Any]]] = {}
    for r in f.get("backfill") or []:
        said = _loads(r.get("summary"))
        if isinstance(said, Mapping) and said.get("day"):
            by_day.setdefault(str(said["day"]), []).append(r)
    found = []
    for day in reach:
        key = day.isoformat()
        rows = by_day.get(key, [])
        summaries = [s for s in (_loads(r.get("summary")) for r in rows) if isinstance(s, Mapping)]
        counts = {k: sum(int(_num(s.get(k)) or 0) for s in summaries) for k in ("failed", "fetched", "known", "unlisted")}
        counts["filings"] = max([int(_num(s.get("filings")) or 0) for s in summaries], default=0)
        # RELEASE 1019f's BACKFILL (fix/backfill-robust: a failed fetch is tried again, FETCH_TRIES in all, and its
        # receipts carry `retrying`): a receipt's `failed` is then the DAY's count of filings failed so far, not that
        # pass's, so the latest receipt's is the figure (a done day's: the filings past their last try, named in its
        # `unfetched`); an earlier release's receipts (no `retrying`) count each pass's own failures, which it never
        # tried again: summed, as before.
        retried = any("retrying" in s for s in summaries)
        if retried:
            counts["failed"] = next((int(_num(s.get("failed")) or 0) for s in reversed(summaries) if "failed" in s), 0)
        last = rows[-1] if rows else None
        base = {"day": key, "passes": len(rows), "last_status": None if last is None else str(last.get("status") or ""),
                "last_at": None if last is None else S.epoch(last.get("finished_at") or last.get("started_at")), **counts}
        if meta.get(key) == "done":
            if counts["failed"] > 0:
                found.append({**base, "state": "failed", "since": None, "hours": None, "retried": retried})
            continue
        run = []
        for r in reversed(rows):
            if str(r.get("status") or "") == "ok":
                break
            run.append(r)
        start = S.epoch(run[-1].get("started_at")) if run else None
        streak = None if start is None else (now - start) / 3600.0
        due = backfill_due(day)
        if now >= due:
            found.append({**base, "state": "late", "since": due, "hours": (now - due) / 3600.0, "streak": streak})
        elif streak is not None and streak > BACKFILL_STREAK_HOURS:
            found.append({**base, "state": "streak", "since": start, "hours": streak, "streak": streak})
    done = sum(1 for d in reach if meta.get(d.isoformat()) == "done")
    first = found[0] if found else None
    if first is None:
        what = (f"The daily-index backfill's reach ({', '.join(d.isoformat() for d in reach)}): {done} done, the rest not "
                "yet due." if reach else "No weekday is in the daily-index backfill's reach yet.")
    else:
        counted = (f"{first['passes']} passes; {first['filings']} filings, {first['known']} known, {first['fetched']} "
                   f"fetched, {first['failed']} failed, {first['unlisted']} unlisted")
        last = ("" if first["last_at"] is None else
                f"its last pass read '{first['last_status']}' at {_hhmm(first['last_at'])} ET; ")
        if first["state"] == "late":
            what = (f"The daily-index backfill of {first['day']} is not done {_hours_of(now - first['since'])} h after it "
                    f"was due (12:00 ET of the next weekday): {last or 'no pass on record; '}{counted}.")
        elif first["state"] == "streak":
            what = (f"The daily-index backfill of {first['day']} has read waiting or partial for "
                    f"{_hours_of(first['hours'] * 3600)} h: {last}{counted}.")
        else:
            what = (f"The daily-index backfill of {first['day']} is done, but {first['failed']} filings failed to fetch "
                    + ("after their last try (named in its last receipt's `unfetched`)" if first.get("retried") else
                       "in its passes (the backfill does not try a filing it has seen again)") + f": {counted}.")
        if len(found) > 1:
            what += f" {len(found)} days of the reach stand in all."
    return {"stalled": bool(found), "judged": True, "what": what,
            "numbers": {"reach": len(reach), "done": done, "standing": len(found),
                        "first_day": None if first is None else first["day"],
                        "state": None if first is None else first["state"],
                        "hours": None if first is None or first["hours"] is None else round(first["hours"], 1),
                        "passes": None if first is None else first["passes"],
                        "last_status": None if first is None else (first["last_status"] or None),
                        **({k: first[k] for k in ("filings", "known", "fetched", "failed", "unlisted")} if first else {})},
            "doing": DOING["evl_backfill"], "owner_step": None,
            "onset": None if first is None else first["since"]}


# ---------------------------------------------------------------------------------------------- the hand-back (1019f)
def handback_facts(root: str | Path) -> dict[str, Any] | None:
    """The real event fills the book owes the lane (`<state>/live.sqlite`, read-only: every `eq_orders` row of a real event
    lot with `filled_qty` > 0, its lot and its buy's intent) set beside the lane's `real_fills` (read-only):
    {due: {(program, version, event, side): since}, handed: {...}, table: bool}; None with no live.sqlite or no event
    lot. Due as the book hands them back (league/equity/live.py `_event_fills`): a buy once its intent has ended or its
    lot is no longer open, from the later of its last fill and that end; a sale once its lot is closed, from the close."""
    live = Path(root) / LIVE_DB
    if not live.exists():
        return None

    def read(db: Any) -> list[dict[str, Any]] | None:
        names = {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if not {"eq_orders", "eq_lots", "eq_intents"} <= names:
            return None
        fill = "(SELECT MAX(f.at) FROM eq_fills f WHERE f.eid=o.eid)" if "eq_fills" in names else "NULL"
        return guard.rows(db, f"SELECT o.side, o.updated_at, {fill} AS fill_at, l.family, l.version, l.status AS lot, "
                              "l.opened_at, l.closed_at, l.info, (SELECT i.status FROM eq_intents i WHERE i.iid=l.iid) "
                              "AS buy_status, (SELECT i.updated_at FROM eq_intents i WHERE i.iid=l.iid) AS buy_at FROM "
                              "eq_orders o JOIN eq_lots l ON l.lid=o.lid WHERE l.lane='event' AND substr(l.instance, -2)="
                              "':r' AND CAST(o.filled_qty AS REAL) > 0 ORDER BY o.eid")
    rows = guard.read(live, read)
    if rows is None:
        return None
    due: dict[tuple[str, int, str, str], float] = {}
    for r in rows:
        info = _loads(r.get("info"))
        evl = info.get("evl") if isinstance(info, Mapping) else None
        if not isinstance(evl, Mapping) or not evl.get("event"):
            continue
        side = str(r.get("side") or "")
        key = (str(r["family"]), int(r["version"]), str(evl["event"]), side)
        if side == "buy":
            ended = str(r.get("buy_status") or "") not in ("planned", "sent")
            if str(r.get("lot") or "") == "open" and not ended:
                continue    # its auction is not over: the book hands the buy back once it is
            times = [_num(r.get("fill_at")), _num(r.get("buy_at")) if ended else None, _num(r.get("opened_at"))]
        elif side == "sell":
            if str(r.get("lot") or "") != "closed":
                continue    # a sale of a lot not closed: handed back once it is (the ladder may still sell the rest)
            times = [_num(r.get("closed_at")), _num(r.get("fill_at"))]
        else:
            continue
        since = max([t for t in times if t is not None], default=_num(r.get("updated_at")) or 0.0)
        due[key] = max(due.get(key, since), since)
    if not due:
        return {"due": {}, "handed": set(), "table": True}
    path = Path(root) / STORE
    if not path.exists():
        return {"due": due, "handed": set(), "table": False}

    def lane(db: Any) -> set | None:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='real_fills'").fetchone() is None:
            return None
        return {(str(r["program"]), int(r["version"]), str(r["event"]), str(r["side"]))
                for r in guard.rows(db, "SELECT program, version, event, side FROM real_fills")}
    handed = guard.read(path, lane)
    return {"due": due, "handed": handed or set(), "table": handed is not None}


def _handback(now: float, found: Mapping[str, Any] | None) -> dict[str, Any]:
    """`evl_handback` (the module docstring)."""
    if found is None:
        return _not_judged("no real event lot in live.sqlite (the book has filled no real event buy on this House)")
    due = found["due"]
    if not due:
        return {"stalled": False, "judged": True, "what": "No real event fill is on record in live.sqlite yet.",
                "numbers": {"fills_due": 0, "handed": 0, "missing": 0}, "doing": DOING["evl_handback"],
                "owner_step": None, "onset": None}
    missing = sorted(((since, key) for key, since in due.items() if key not in found["handed"]), key=lambda x: x[0])
    late = [(since, key) for since, key in missing if now - since > HANDBACK_HOURS * 3600]
    first = late[0] if late else None
    buys = sum(1 for _, k in late if k[3] == "buy")
    if first is None:
        what = (f"Every real event fill due to the lane is in its real_fills ({len(due) - len(missing)} of {len(due)}"
                + (f"; {len(missing)} under {HANDBACK_HOURS:g} h old" if missing else "") + ").")
    else:
        since, key = first
        what = (f"{len(late)} real event fills are not in the lane's real_fills more than {HANDBACK_HOURS:g} h after the "
                f"book owed them ({buys} buys, {len(late) - buys} sales)"
                + ("" if found["table"] else ": the lane's store holds no real_fills table")
                + f"; the oldest, a {'buy' if key[3] == 'buy' else 'sale'} of {key[0]} version {key[1]}, owed since "
                f"{_hhmm(since)} ET {dt.datetime.fromtimestamp(since, NY).date().isoformat()}, {_hours_of(now - since)} h ago.")
    return {"stalled": bool(late), "judged": True, "what": what,
            "numbers": {"fills_due": len(due), "handed": len(due) - len(missing), "missing": len(missing),
                        "missing_late": len(late), "missing_buys": buys, "missing_sales": len(late) - buys,
                        "table": bool(found["table"]),
                        "oldest_hours": None if first is None else round((now - first[0]) / 3600.0, 1),
                        "oldest_program": None if first is None else first[1][0].lower(),
                        "oldest_side": None if first is None else first[1][3]},
            "doing": DOING["evl_handback"], "owner_step": None, "onset": None if first is None else first[0]}


# ---------------------------------------------------------------------------------------------- release 1019i
def attempt_facts(root: str | Path, now: float) -> dict[str, Any] | None:
    """THE ATTEMPTS LEDGER as the two causes read it (release 1019i, PREREG-EVL-7's H4; league/events/attempts.py), each
    store read-only: the lane's `real_attempts` (its fill rates through the New York day of `now`, its attempts with no
    final state, every row's state by client id) and the book's own rows of live.sqlite beside it (`book_rows`; None with
    no live.sqlite). None when the lane's store holds no ledger yet (a lane not opened by release 1019i)."""
    from ..events import attempts as AT

    path = Path(root) / STORE
    if not path.exists():
        return None
    moment = dt.datetime.fromtimestamp(now, dt.timezone.utc)

    def lane(db: Any) -> dict[str, Any] | None:
        store = _Db(db)
        if not AT.has_table(db):
            return None
        return {"rates": AT.fill_rates(store, moment.astimezone(NY).date()), "open": AT.open_attempts(store, moment),
                "held": {str(r["client_id"]): {"state": r["state"]}
                         for r in guard.rows(db, f"SELECT client_id, state FROM {AT.TABLE}")}}
    found = guard.read(path, lane)
    if found is None:
        return None
    live = Path(root) / LIVE_DB
    book = None
    if live.exists():
        try:    # (live.sqlite that cannot be read blinds only the ledger's completeness, never its own states)
            book = guard.read(live, lambda db: AT.book_rows(lambda sql, params=(): guard.rows(db, sql, params))[0])
        except Exception:  # noqa: BLE001 - evl_entries and evl_handback say live.sqlite could not be read
            book = None
    return {**found, "book": book}


def _fill_rate(now: float, found: Mapping[str, Any] | None) -> dict[str, Any]:
    """`evl_fill_rate`: an auction's real buys filled under 85% of those sent over the last 3 sessions (at least 5 sent),
    or more than 10 points under their last 20 (league/events/attempts.py `fill_drop`)."""
    from ..events import attempts as AT

    if found is None:
        return _not_judged("the lane's store holds no attempts ledger yet (release 1019i)")
    rates = found.get("rates") or {}
    drops = AT.fill_drop(rates)
    by = rates.get("auctions") or {}
    numbers: dict[str, Any] = {}
    for auction in ("open", "close"):
        for n in ("3", "20"):
            c = (by.get(auction) or {}).get(n) or {}
            numbers[f"{auction}_sent_{n}"] = int(c.get("buys_sent") or 0)
            numbers[f"{auction}_filled_{n}"] = int(c.get("buys_filled") or 0)
        c3 = (by.get(auction) or {}).get("3") or {}
        numbers[f"{auction}_venue_cancels_3"] = int(c3.get("venue_cancels") or 0)
    if not drops:
        what = "The real event buys' fill rates hold: " + "; ".join(
            f"{a} {numbers[f'{a}_filled_3']} of {numbers[f'{a}_sent_3']} over 3 sessions, "
            f"{numbers[f'{a}_filled_20']} of {numbers[f'{a}_sent_20']} over 20" for a in ("open", "close")) + "."
        return {"stalled": False, "judged": True, "what": what, "numbers": numbers, "doing": DOING["evl_fill_rate"],
                "owner_step": None, "onset": None}
    said = []
    for d in drops:
        rate3 = "n/a" if d["rate3"] is None else f"{d['rate3'] * 100:.0f}%"
        rate20 = "n/a" if d["rate20"] is None else f"{d['rate20'] * 100:.0f}%"
        said.append(f"the {d['auction']}'s {rate3} of {d['sent3']} sent over 3 sessions "
                    + (f"is under {AT.FILL_LOW:.0%}" if d["why"] == "low"
                       else f"is more than {AT.FILL_FALL * 100:.0f} points under its {rate20} of {d['sent20']} over 20"))
    numbers["dropped"] = ",".join(d["auction"] for d in drops)
    return {"stalled": True, "judged": True, "what": "Real event buys fill less often: " + "; ".join(said) + ".",
            "numbers": numbers, "doing": DOING["evl_fill_rate"], "owner_step": None, "onset": None}


def _attempts(now: float, found: Mapping[str, Any] | None) -> dict[str, Any]:
    """`evl_attempts`: an order sent with no final state in the ledger an hour after its auction ended, or a row of the
    book's the ledger lacks (or holds in another state) an hour after its last change (league/events/attempts.py
    `open_attempts`, `missing`)."""
    from ..events import attempts as AT

    if found is None:
        return _not_judged("the lane's store holds no attempts ledger yet (release 1019i)")
    opened = list(found.get("open") or [])
    gaps = AT.missing(found["book"], found.get("held") or {}, now) if found.get("book") is not None else []
    numbers = {"open": len(opened), "missing": sum(1 for g in gaps if g["ledger"] is None),
               "stale": sum(1 for g in gaps if g["ledger"] is not None), "rows": len(found.get("held") or {}),
               "book_read": found.get("book") is not None}
    if not opened and not gaps:
        return {"stalled": False, "judged": True,
                "what": f"Every event order in the attempts ledger has its final state ({numbers['rows']} rows)"
                        + ("" if numbers["book_read"] else "; no live.sqlite to set beside it") + ".",
                "numbers": numbers, "doing": DOING["evl_attempts"], "owner_step": None, "onset": None}
    parts = []
    onset = None
    if opened:
        first = opened[0]
        parts.append(f"{len(opened)} order{'s' if len(opened) != 1 else ''} sent with no final state an hour after the "
                     f"auction; the first, a {first['kind']} of {str(first['program']).lower()} version {first['version']} "
                     f"at the {first['at']} of {first['day']}, is {first['state']}")
        onset = S.epoch(first["ended"]) + AT.OPEN_GRACE.total_seconds()
        numbers["first_day"] = str(first["day"])
    if gaps:
        parts.append(f"{numbers['missing']} of the book's orders are not in the ledger and {numbers['stale']} are there "
                     f"in an older state, an hour after their last change")
    return {"stalled": True, "judged": True, "what": "The attempts ledger is incomplete: " + "; ".join(parts) + ".",
            "numbers": numbers, "doing": DOING["evl_attempts"], "owner_step": None, "onset": onset}


def px_on(ctx: Any) -> bool:
    """The price lane's recorders run (league/config.json `events.px_data` true; a missing key or false is off)."""
    config = _get(ctx, "config")
    block = config.get("events") if isinstance(config, Mapping) else None
    return isinstance(block, Mapping) and block.get("px_data") is True


def score_latch(root: str | Path) -> dict[str, Any] | None:
    """THE PARITY LATCH as `evl_score_parity` reads it (league/events/score.py `latched`, read-only): {latch: the
    latched intent's identifiers or None, flags: {checked, equal} of the latch's night}; None when the lane's store
    does not exist."""
    from ..events import score as SCO

    path = Path(root) / STORE
    if not path.exists():
        return None

    def read(db: Any) -> dict[str, Any]:
        held = SCO.latched(_Db(db))
        flags = {"checked": 0, "equal": 0}
        night = (held or {}).get("night")
        has = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='score_parity'").fetchone()
        if night and has:
            row = db.execute("SELECT COUNT(*), COALESCE(SUM(equal), 0) FROM score_parity WHERE night=?",
                             (str(night),)).fetchone()
            flags = {"checked": int(row[0] or 0), "equal": int(row[1] or 0)}
        return {"latch": held, "flags": flags}
    return guard.read(path, read)


def _score_parity(now: float, found: Mapping[str, Any] | None) -> dict[str, Any]:
    """`evl_score_parity`: the parity latch stands (`score_latch`)."""
    if found is None:
        return _not_judged("the event lane has no store yet")
    held = found.get("latch")
    flags = found.get("flags") or {}
    numbers: dict[str, Any] = {"latched": held is not None, "checked": int(flags.get("checked") or 0),
                               "equal": int(flags.get("equal") or 0)}
    if held is None:
        return {"stalled": False, "judged": True, "what": "The batched score has no parity latch: it settles as switched.",
                "numbers": numbers, "doing": DOING["evl_score_parity"], "owner_step": None, "onset": None}
    program = re.sub(r"[^A-Za-z0-9._-]", "", str(held.get("program") or ""))[:40]
    night = str(held.get("night") or "")[:10]
    numbers.update(night=night, program=program, version=held.get("version") if isinstance(held.get("version"), int)
                   else None)
    what = (f"The batched score's parity check found a difference on the night of {night or 'unknown'} "
            f"({numbers['equal']} of {numbers['checked']} sampled intents equal; the first difference "
            f"{program.lower() or 'a program'} version {numbers['version']}): the batched score is OFF and every intent "
            "settles by the per-intent path until the captain clears the latch (score-unlatch).")
    at = _parse_ts(held.get("at"))
    return {"stalled": True, "judged": True, "what": what, "numbers": numbers, "doing": DOING["evl_score_parity"],
            "owner_step": None, "onset": at}


def px_store_facts(ctx: Any, root: str | Path) -> dict[str, Any] | None:
    """THE PRICE LANE'S STORE as `evl_px_store` reads it (league/events/pxstore.py `room`, by `stat` and the disk's usage
    alone): the room and whether the recorders run; None while they are off and px.sqlite does not exist."""
    from ..events import pxstore as PXS

    events = Path(root) / STORE.parent
    on = px_on(ctx)
    if not on and not PXS.path_of(events).exists():
        return None
    return {"on": on, **PXS.room(events)}


def _px_store(now: float, found: Mapping[str, Any] | None) -> dict[str, Any]:
    """`evl_px_store`: px.sqlite at or over its line, or (the recorders on) the state disk under the PX floor."""
    if found is None:
        return _not_judged("the price lane's recorders are off (events.px_data) and px.sqlite does not exist")
    size, free = int(found.get("size_bytes") or 0), found.get("free_bytes")
    numbers = {"px_data": bool(found.get("on")), "size_mb": round(size / 2 ** 20, 1),
               "free_gb": None if free is None else round(int(free) / 2 ** 30, 1),
               "line_gb": round(int(found["line_bytes"]) / 2 ** 30, 1),
               "floor_gb": round(int(found["floor_bytes"]) / 2 ** 30, 1)}
    over, low = bool(found.get("over")), bool(found.get("on")) and bool(found.get("low"))
    if not over and not low:
        return {"stalled": False, "judged": True,
                "what": f"px.sqlite holds {numbers['size_mb']:.0f} MB of its {numbers['line_gb']:.0f} GB line; the state "
                        f"disk has {numbers['free_gb']} GB free (the PX floor {numbers['floor_gb']} GB).",
                "numbers": numbers, "doing": DOING["evl_px_store"], "owner_step": None, "onset": None}
    parts = []
    if over:
        parts.append(f"px.sqlite holds {numbers['size_mb']:.0f} MB, at or over its {numbers['line_gb']:.0f} GB line")
    if low:
        parts.append("the state disk's free space could not be read" if free is None
                     else f"the state disk has {numbers['free_gb']} GB free, under the PX floor of {numbers['floor_gb']} GB")
    return {"stalled": True, "judged": True,
            "what": "The price lane's store has no room: " + " and ".join(parts) + "; the PX recorders write nothing.",
            "numbers": numbers, "doing": DOING["evl_px_store"], "owner_step": None, "onset": None}


def _parse_ts(text: Any) -> float | None:
    try:
        return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def checks(ctx: Any, root: str | Path, now: float, *, errors: list[str] | None = None, idle: Any = None,
           line: Mapping[str, Any] | None = None, kept: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """THE STALL JOB'S CALL (league/ops/stall.py `run`): the causes' checks (the module docstring). `idle` is
    `idle_windows`' answer (None: read now, with nothing kept); `line` the lane's verdict line and the day's spend
    ({line_usd, spent_usd}, `verdict_line`); `kept` what the stall job keeps for them in stall.json (`evl_kept`), updated
    in place when the store is read (`KEPT_FOUR`: `four_kept`). Never raises: a store that cannot be read is "Not
    judged" and an entry of `errors`; live.sqlite that cannot be read leaves `evl_entries` and `evl_handback` "Not
    judged" (an entry of `errors`) and the rest judged."""
    try:
        if switched_off(ctx):
            return {c: _not_judged(f"switched off (ops.json stall.{SWITCH} is false)") for c in CAUSES}
        if not lane_on(ctx):
            return {c: _not_judged("the event lane does not run on the House (league/config.json events.enabled)")
                    for c in CAUSES}
        idle = idle if isinstance(idle, Mapping) else idle_windows(None, root, now)
        stops, pauses = list(idle.get("stop") or []), list(idle.get("pause") or [])
        if _open(stops):
            return {c: _not_judged("the lane is stopped by events/STOP") for c in CAUSES}
        back = _ended_lately(stops, now)
        if back is not None:
            return {c: _not_judged(f"the lane came back from events/STOP at {_hhmm(back)} ET, under {RESUME_MINUTES} "
                                   "minutes ago") for c in CAUSES}
        latest = score_session(now)
        if not (Path(root) / STORE).exists():
            f: dict[str, Any] = empty_facts()
        else:
            with guard.readonly():
                f = facts(root, now, None if latest is None else latest["day"].isoformat())
        kinds = entry_kinds()
        seen = {}
        for key, held, _ in FILE_WAITS.values():
            got = (kept or {}).get(held) if isinstance(kept, Mapping) else None
            seen[held] = got if isinstance(got, Mapping) else {}
        out = {"evl_record": _record(now, f),
               "evl_decide": _decide(now, f, kinds, stops, idle={"stop": stops, "pause": pauses}, seen=seen)}
        if kept is not None:
            for key, held, _ in FILE_WAITS.values():
                kept[held] = four_kept(seen[held], f.get(key), now)
        if _open(pauses):
            out["evl_verdicts"] = _not_judged("the House is paused (PAUSE): no verdict is asked while it stands")
        elif _ended_lately(pauses, now) is not None:
            out["evl_verdicts"] = _not_judged(f"the House's PAUSE ended under {RESUME_MINUTES} minutes ago")
        else:
            out["evl_verdicts"] = _verdicts(now, f, kinds, idle, line)
        out["evl_score"] = (_not_judged("no session in the last 10 days has passed its 23:00 ET") if latest is None
                            else _score(now, f, latest))
        out["evl_fills"] = _fills(now, event_twins(root))
        if not (Path(root) / STORE).exists():
            out["evl_final"] = _not_judged("the event lane has no store yet")
        else:
            try:    # (its own reader: a failure here blinds no other cause)
                out["evl_final"] = _final(now, final_lags(root, now))
            except Exception as exc:  # noqa: BLE001 - the judge's horizon could not be read: said, not raised
                if errors is not None:
                    errors.append(f"the event lane's final records could not be read ({type(exc).__name__}): evl_final "
                                  "is not judged")
                out["evl_final"] = _not_judged(f"the final records could not be read ({type(exc).__name__})")
        out["evl_backfill"] = _backfill(now, f, backfill_reach(now))
        # (Release 1019i: the batched score's parity latch and the price lane's store, each on its own reader.)
        for cause, judge in (("evl_score_parity", lambda: _score_parity(now, score_latch(root))),
                             ("evl_px_store", lambda: _px_store(now, px_store_facts(ctx, root)))):
            try:
                with guard.readonly():
                    out[cause] = judge()
            except Exception as exc:  # noqa: BLE001 - said, and the other causes stand as judged
                if errors is not None:
                    errors.append(f"{cause} could not be judged ({type(exc).__name__})")
                out[cause] = _not_judged(f"it could not be read ({type(exc).__name__})")
        try:    # (PREREG-EVL-7's learners, league/ops/evl_learner.py: its own reader, blinding no other cause)
            from . import evl_learner as LRN

            out["evl_learner"] = LRN.check(root, now)
        except Exception as exc:  # noqa: BLE001 - said, and the other causes stand as judged
            if errors is not None:
                errors.append(f"the learners' records could not be read ({type(exc).__name__}): evl_learner is not judged")
            out["evl_learner"] = _not_judged(f"the learners' records could not be read ({type(exc).__name__})")
        try:    # (PREREG-EVL-8, release 1019j, league/ops/evl_price.py: its own reader, blinding no other cause)
            from . import evl_price as PX8

            out["evl_price"] = PX8.check(root, now)
        except Exception as exc:  # noqa: BLE001 - said, and the other causes stand as judged
            if errors is not None:
                errors.append(f"PREREG-EVL-8's records could not be read ({type(exc).__name__}): evl_price is not judged")
            out["evl_price"] = _not_judged(f"PREREG-EVL-8's records could not be read ({type(exc).__name__})")
        # THE BOOK'S OWN ROWS (live.sqlite, read-only), each read on its own: one that cannot be read blinds only itself.
        # (Release 1019i: the attempts ledger's two causes read the lane's ledger and the book's rows beside it.)
        ledger: dict[str, Any] = {}

        def attempts_read() -> dict[str, Any] | None:
            if "found" not in ledger:
                ledger["found"] = attempt_facts(root, now)
            return ledger["found"]
        for cause, judge in (("evl_entries", lambda: _entries(now, entry_facts(root, auctions(now)))),
                             ("evl_handback", lambda: _handback(now, handback_facts(root))),
                             ("evl_fill_rate", lambda: _fill_rate(now, attempts_read())),
                             ("evl_attempts", lambda: _attempts(now, attempts_read()))):
            try:
                with guard.readonly():
                    out[cause] = judge()
            except Exception as exc:  # noqa: BLE001 - said, and the other causes stand as judged
                if errors is not None:
                    errors.append(f"live.sqlite could not be read for {cause} ({type(exc).__name__}): it is not judged")
                out[cause] = _not_judged(f"live.sqlite could not be read ({type(exc).__name__})")
        return out
    except Exception as exc:  # noqa: BLE001 - an alarm that cannot see says so, and the rest of the job goes on
        if errors is not None:
            errors.append(f"the event lane's store could not be read ({type(exc).__name__}): its causes are not judged")
        return {c: _not_judged(f"the event lane's store could not be read ({type(exc).__name__})") for c in CAUSES}


def verdict_line(ctx: Any, root: str | Path, now: float) -> dict[str, Any] | None:
    """The lane's verdict line of the UTC day (league/events/house.py: the lower of `events.verdict_usd_day` and the
    budget's allowance, league/ops/budget.py `lane_allowance`, held on the UTC day: `verdict_day`) and the day's verdict
    dollars so far: {line_usd, spent_usd, source}, or None when the store cannot be read."""
    from . import budget as B
    from ..events.house import VERDICT_USD_DAY, verdict_day   # the House's own default and day: read where they are set

    config = _get(ctx, "config")
    block = config.get("events") if isinstance(config, Mapping) else None
    configured = _num((block or {}).get("verdict_usd_day")) if isinstance(block, Mapping) else None
    configured = float(VERDICT_USD_DAY) if configured is None else configured
    allowance = B.lane_allowance(root, now)
    line = min(configured, float(allowance["usd_day"]))
    path = Path(root) / STORE
    if not path.exists():
        return {"line_usd": line, "spent_usd": 0.0, "source": allowance["source"]}
    _, (lo, hi) = verdict_day(dt.datetime.fromtimestamp(now, dt.timezone.utc))
    try:
        with guard.readonly():
            row = guard.read(path, lambda db: db.execute(
                f"SELECT COALESCE(SUM(COALESCE(usd, {B.VERDICT_USD_UNKNOWN})), 0) FROM verdicts WHERE answered_at>=? "
                "AND answered_at<?", (lo, hi)).fetchone()[0])
    except Exception:  # noqa: BLE001 - the line alone
        return None
    return {"line_usd": line, "spent_usd": float(row or 0.0), "source": allowance["source"]}


__all__ = ["CAUSES", "SWITCH", "STORE", "STOP", "PAUSE", "checks", "facts", "switched_off", "lane_on", "decisions",
           "entry_kinds", "sessions", "idle_windows", "made", "tally", "score_session", "verdict_line", "event_twins",
           "fill_gaps", "FILL_LOOK", "FILL_GAP_BP", "FILL_MIN", "final_lags", "FINAL_LAG_SESSIONS", "venue_cancel_ms",
           "unsent_reason", "sent_binding",
           "auctions", "auctions_of", "decision_room", "auction_entries", "entry_facts", "entry_totals", "short_of",
           "backfill_reach", "backfill_due", "handback_facts", "four_waiting", "four_kept", "four_decisions",
           "empty_facts", "LIVE_DB", "ENTRY_HOURS", "ENTRY_FILL_SHARE", "AUCTION_SETTLE_MINUTES", "VENUE_CANCEL_S",
           "BOUND", "UNSENT", "BACKFILL_DUE", "BACKFILL_STREAK_HOURS", "FOUR_REFILL_HOURS", "HANDBACK_HOURS", "KEPT_FOUR",
           "KEPT_FIVE", "FILE_WAITS",
           "written_after", "DECIDE_JOB",
           "RECORD_MINUTES", "DECIDE_GRACE_MINUTES", "DECIDE_LOOKBACK_HOURS", "VERDICT_GRACE_MINUTES", "RESUME_MINUTES",
           "SCORE_BY", "FEEDS", "TAPE_LABELS"]

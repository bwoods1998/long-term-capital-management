"""The event lane on the House (release R1, WP1): the desktop's passes as one bounded scheduler beside the House's tick.

PHASE 2 of goal-2026-10-19/EVL-DESIGN.md: the functions blake-desktop ran from systemd timers run inside the House's
process, on its state root (`<state>/events/`: events.sqlite and docs/, the same store), with the House's gateway token
and its SEC contact. `league/service.py` attaches the lane when `config.json` `events.enabled` is true, on the House
box's own loop only (never a canary, never a `tick` or `status` beside the loop).

THE HOOK. The lane is NOT `House.feeds`: a non-None `feeds` also wakes the House's legacy feed paths (the agents'
`ctx["feeds"]`, the replay tapes' feeds and coverage, `_require_feeds`' refusals, research_capabilities'
`observations.feeds`, the tool requests' fulfilment), and research_capabilities answers differently for any non-None
`feeds` whatever it holds (league/tests/test_events_house.py shows it). So the lane takes the other unprotected hook the
spec names: `house.publisher` is wrapped (`LanePublisher`), and on each of the tick's publishes (every
`publish_seconds`, 60 s) the original publisher runs exactly as before and then, when the lane is due, its turn is
started on the House's one-slot feeds lane with `house._background("feeds:evl", lane.run)`. `house.feeds` stays None,
so every legacy path behaves as it does today.

ONE TURN, ONE TASK, BOUNDED. `run()` does the single most urgent due task, never raises (a failure is a warning at most
once an hour per task, so the House's repeat rule never turns it into an error), and keeps its time. One exception
(PREREG-EVL-5 section 1.3, release 1019g's money review): from `HOLD_LEAD` before today's live close decision a turn
keeps going, runs each task that falls due but another decision (none starts inside the lead, `_lead`; every other
task is still bounded to end before the decision), waits between them and starts the decision at its time
(`_close_hold`, `_wait_until`), and when a task returns at or after that time (a network read can outlast its bound)
starts it at once in the same turn (`_close_owed`), because real money buys that file's rows only once the decision
has finished, by the close - 11 minutes. THE LEAD ENDS only when a run of the live decision has finished `ok` or
`pending` (release 1019h, `LEAD_ENDS`), or once it is no longer live: after a FAILED run the turn keeps going (a task
that raises inside the lead never ends it), no other decision starts, every other task is bounded to end before the
run's retry (its start + DECIDE_RETRY), and the retry starts at its time in the same turn. The order of the tasks:
1. a DECISION due: the open at 09:15 ET, the close's at the close - 14 minutes (a minute later, for the 15:30 minute
   bar); live within 10 minutes of its time, a backfill after (the judge's rule: league/events/run.py `live_run`); then
   a missed one, then a pending
   one again (the hourly re-decision of the last three sessions, as the desktop's catchup, waits for the record pass;
   so does PREREG-EVL-4'S ROWS' OWN DECISION, `decide-close-evl4`, of every older close a release without them decided:
   release 1019c's review, `_refill_redecide`; PREREG-EVL-5'S ROWS' OWN DECISION, `decide-close-evl5`, of every close a
   release without them decided or whose PREREG-EVL-5 part failed or ran past its own bound: PREREG-EVL-5 section 3;
   and THE BIRTHS' OWN DECISION, `decide-open-births` and `decide-close-births`, of every older decision a release or a
   turn without the registered births made: release 1019e's review);
2. VERDICTS for a decision within 30 minutes (today's open or close), or for a decision that is pending (a close
   decision waiting on verdicts only its session's OPEN decision asks, PREREG-EVL-4's PM rows, has those asked by the
   open decision's own code; a wait no call of the pass could answer backs off like one the gateway refused); and
   PREREG-EVL-5's PRE-PASS (its section 1.3): today's close's verdict pass is also due from D's 09:30 minute on the
   Basic plan's tape (09:47 ET, league/events/run.py `pre_from`) while meta `evl5:pre:<day>` is not stored, whatever
   the verdicts, and once more inside the last 30 minutes once the earlier rows' verdicts are all stored, so the close
   decision's PREREG-EVL-5 part reads EVL-NEWS-NIGHT2-ON's eligibility and 09:30 minutes as stored (`_pre_due`; a pass
   whose pre-read failed waits VERDICT_BACKOFF; one its own bound cut goes on at once, from what it stored);
3. the RECORD pass every 2 minutes: EDGAR's current feeds and the news, at most 90 s, resumable (a new filing is stored
   `listed` at once and fetched in order, so a pass cut short loses nothing), then today's verdicts with the time
   left (its open decision's, then its close decision's: PREREG-EVL-2's day news is read through the session);
4. NIGHTLY: the account equity after the close, the score at 20:30 ET, the screen (with PREREG-EVL-3's band review
   of the real fills: demotion and Sized, league/events/bands.py `review`, then THE DONE READER of the goal V2,
   league/events/done.py `run`: `<state>/events/done.json` and a `done` receipt) and the report after it, KEYED ON THE
   SESSION (release 1019f): the night is today's session from 20:30 ET, else the session before today, so a score that
   ran past midnight ET (or a House that was down that evening) still gets that session's screen and report the next
   day; then, on a session night with `events.births` on, R3's BIRTHS job at 21:15 ET (league/events/births.py
   `night`: the outcome-free facts, the architect's one call (Claude Opus 5.5 from release 1019h, A109; Haiku 4.5 before
   it) under $0.25 a night and inside what is left of the lane's line, below, the validator, the registration through
   the gateway's docs route), once a night (keyed on the
   calendar day, as release 1019e built it), and ONCE MORE for a night whose births receipt accepted and registered
   none under an older reading of the grammar and prompt than the running one (A95: `births.PARSE_VERSION` in the
   receipt; `births.rerun_due`), never from 12:55Z of the session day after it; then THE SCREEN AFTER THE OPEN
   (release 1019f, `screen-open`): from 09:40 ET of a session whose open decision is made, until 5 minutes before its
   close decision, whenever the judge's final
   horizon (league/events/screen.py `final_until`) of any seating version moved since the last screen receipt, the
   screen's looks of the seating versions run again (never the band review nor the Done reader, which stay nightly),
   so a look the judge makes final at the open is written that morning and its Probe move trades from that session's
   close (PREREG-EVL-3 section 2: "the first decision after a passed look"; the House's event book reads the bands
   again at the close decision when the lane's `band_history` moved since its morning sync, league/equity/live.py
   `_event_decide`);
5. the TICKER snapshot at 07:00 ET;
6. EARLY VERDICTS from 07:30 ET (the session's universe is fixed then: its tickers copy is the latest before 07:30 ET),
   for its open decision and then its close decision;
7. the daily-index BACKFILL of the last weekdays, for anything the live pass missed or failed (a filing whose fetch fails
   in it is tried again on the record pass's backoff, its day done after its last try with the filing named; a federal
   holiday's missing index is done: `SEC_HOLIDAYS`).
A backlog (missed decisions, a long verdict queue) never holds the record pass past a second cadence: then only a live
decision goes before it. A task ends early when a decision falls due; a decision's and a verdict task's network reads
stop at their bound and the next turn goes on from what was stored (universe rows, cik_info, bars and verdicts are kept
as they are read). `<state>/events/STOP` idles the lane without a deploy: the lane only, never the House's event book,
which still decides each auction on the store as it stands (the instant stop of event buys is the gateway's
`STOCK_EVENT_BUYS` off or `equity_money.event.enabled` False: docs/operations.md, release 1019b's Rollback).

Paid work: a verdict is asked only while the House is not paused (`PAUSE`), and only under THE LANE'S LINE of a UTC
day (00:00-24:00 UTC: budget rule 3's day, on which the Sail guard, the router and the cap breach judge theirs; the
review of r2/alarms, its major 1: held on New York days, the lane could spend one day's line after 20:00 ET and the next
day's from 00:00 ET, two lines in one UTC day): the lower of `events.verdict_usd_day` ($3, the default too: release
1019b's second review, the goal's cost rule, the House box's about $1.29 a day and the verdicts inside its $5 base) and
the budget rule's allowance for the lane's verdicts (league/ops/budget.py `lane_allowance`: the Claude meter's lane part
in `<state>/budget.json`, its no-profit floor when the file is not usable, 0 under the cap breach hold), so the verdicts
and every other metered dollar stay under the day's cap (budget rule 3; release 1019c). Over it, READ events wait
(PREREG-EVL-1 section 4), as they do for any call with no answer. R3's births call is the lane's too (release 1019e's
review): its stored cost counts in the line (`_spend_today`, `birth_usd`), and it is made only when its worst case fits
under what is left of the line (`line_left`).
Market-data reads are spaced `DATA_INTERVAL` apart (Alpaca's Basic plan is shared
with the House's own book).
"""

from __future__ import annotations

import collections
import dataclasses
import datetime as dt
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import bands as BA
from . import calendar as C
from . import done as DN
from . import edgar as E
from . import gw as G
from . import news as N
from . import programs as P
from . import pxdata as PX
from . import pxstore as PXS
from . import report as RP
from . import run as R
from . import score as SC
from . import screen as SN
from . import store as S
from . import universe as U
from . import verdicts as V

UTC = dt.timezone.utc
ROOT_NAME = "events"
HEALTH_FILE = "lane.json"
STOP_FILE = "STOP"                            # <state>/events/STOP: the lane idles while it exists (no deploy needed)
BACKGROUND_KEY = "feeds:evl"

RECORD_EVERY = dt.timedelta(minutes=2)
RECORD_BUDGET = 90.0
NEWS_BUDGET = 30.0
DECIDE_BUDGET = 150.0
VERDICT_BUDGET = 90.0
SCORE_BUDGET = 120.0
BACKFILL_BUDGET = 90.0
#: A task never runs into a decision: it ends this long before one falls due.
DECISION_MARGIN = 5.0
#: The verdict step of a record pass starts only with this much of its bound left.
VERDICT_STEP_MIN = 10.0

#: A decision run this soon after its time is live: THE JUDGE'S (release 1019b's third review: each run's rule fixes its
#: session's eligibility for good), defined once in league/events/run.py behind the wall; every live-or-backfill choice
#: here is `R.live_run`'s.
LIVE_WITHIN = R.LIVE_WITHIN
CLOSE_GRACE = dt.timedelta(minutes=1)         # C1 runs a minute after its time: the 15:30 bar is on the tape at 15:46
PENDING_RETRY = dt.timedelta(minutes=5)       # a decision waiting on verdicts is tried again this often
STALE_RETRY = dt.timedelta(minutes=10)        # a decision whose run never finished, when it is not this lane's
DECIDE_RETRY = dt.timedelta(minutes=1)        # a decision that FAILED (an error, not its bound) is tried again this soon
REDECIDE_EVERY = dt.timedelta(hours=1)
#: THE RE-DECISION REACH IS THE JUDGE'S (release 1019b's second review): a look waits until its close is out of the
#: sessions the House still decides again (league/events/screen.py `final_until`), so the House takes its reach from
#: the protected judge (league/events/screen.py, behind league/ci.py's wall), defined there once: a change of this file
#: the updater ships by itself can only use the reach, never widen it (and `final_until` waits out the larger reach if
#: one ever did). REDECIDE_SESSIONS: the last sessions decided again every hour (league.events.__main__'s catchup too);
#: LOOKBACK: decisions older than this are the CLI's (`catchup`); BACKFILL_WEEKDAYS: the daily-index backfill's reach.
REDECIDE_SESSIONS = SN.FINAL_SESSIONS
LOOKBACK = SN.FINAL_LOOKBACK
#: PREREG-EVL-4'S ROWS DECIDED BY THEMSELVES (release 1019c's review): the decision kind (its receipt
#: `decide-close-evl4:<day>`, league/events/run.py `decide_close` with `evl4_only`) the lane runs, once and as a
#: backfill, for every close since PREREG-EVL-4's registration that a release without its rows decided and the hourly
#: re-decision no longer reaches (league/events/screen.py `made_without`, the judge's: until it is made the close is not
#: final for those programs). The earlier rows of such a close are never decided again by it.
FOUR_KIND = SN.FOUR_KIND
#: R3'S BIRTHS DECIDED BY THEMSELVES (release 1019e's review): the decision kinds (their receipts
#: `decide-open-births:<day>` and `decide-close-births:<day>`, league/events/run.py `decide_open` / `decide_close` with
#: `births_only`) the lane runs, once and as a backfill, for every decision a release or a turn without the registered
#: births made and the hourly re-decision no longer reaches (league/events/screen.py `births_made_without`, the judge's:
#: until it is made the session is not final for those births). Its PREREG rows are never decided again by it.
BIRTH_KINDS = dict(SN.BIRTHS_KIND)
#: PREREG-EVL-5'S ROWS DECIDED BY THEMSELVES (its section 3): the decision kind (receipt `decide-close-evl5:<day>`,
#: league/events/run.py `decide_close` with `evl5_only`) the lane runs, once and as a backfill, oldest first, for every
#: close since PREREG-EVL-5's registration that a release without its rows decided, or whose PREREG-EVL-5 part failed or
#: ran past its own bound (league/events/screen.py `made_without(prereg=5)`, the judge's), and the hourly re-decision no
#: longer reaches; such a close's events of these rows are never traded (league/events/book.py `part_hold`).
FIVE_KIND = SN.FIVE_KIND
BACKFILL_KINDS = (FOUR_KIND, *BIRTH_KINDS.values(), FIVE_KIND)
URGENT_BEFORE = dt.timedelta(minutes=30)
#: PREREG-EVL-5 section 1.3, THE LANE KEEPS ITS TURN FOR ITS LIVE CLOSE DECISION (the money review of release 1019g):
#: real money buys this file's rows only once the lane's close decision of D has finished (league/events/book.py
#: `part_hold`) and only until the close - 11 minutes, while a turn starts only on the House's publishes (a minute or
#: more apart in session), so the decision could start a publish after its time (the close decision + CLOSE_GRACE) and
#: leave the book no minute to send them. From HOLD_LEAD before that time a turn keeps going instead of ending: it runs
#: every task that falls due meanwhile, waits between them (HOLD_STEP a look; the House closing, the STOP file or a
#: clock that does not move ends the wait, and the turn), and starts the decision at its time; `due()` looks again no
#: later than HOLD_LEAD before it, so the publish that starts the turn falls inside the lead. Only while PREREG-EVL-5
#: has programs, at most HOLD_TURNS tasks a turn.
#: INSIDE THE LEAD NO OTHER DECISION STARTS (the money re-review of PREREG-EVL-5, wf_03d60ddf-1c3; `_lead`): a decision
#: task runs with the whole DECIDE_BUDGET (`_deadline` bounds every other task by the next decision, never a decision),
#: so from HOLD_LEAD before the live close decision until it has started, every other decision waits (a missed, cut,
#: pending or failed one, today's open included, the hourly re-decision and the backfill kinds, `BACKFILL_KINDS`); each
#: is due again once the live decision has a run finished `ok` or `pending` (release 1019h: a failed run keeps the lead,
#: `LEAD_ENDS`; a deferred decision runs whole, never cut by the hold). Every other task is bounded to
#: end DECISION_MARGIN before the decision, as before; none starts inside that margin. A BOUND IS NOT A PROMISE: a task
#: checks its bound before each network read, and one read can return after it (the gateway's timeout is 45 s); a
#: decision started before the lead ends by the decision's time only if no read overruns (HOLD_LEAD >= DECIDE_BUDGET).
#: So a task that returns at or after the decision's time never ends the turn while today's live close decision has
#: no receipt and is still live (`_close_owed`): the turn starts it at once, in the same turn.
HOLD_LEAD = dt.timedelta(seconds=150)
#: THE LEAD ENDS when a run of today's live close decision has finished with one of these (release 1019h, the review of
#: release 1019g: the book's own reading of a made decision, league/events/book.py `decided` and `part_hold`). A FAILED
#: run keeps it (a run that raised, a gateway 429 say: before, any receipt ended it, so another decision could start
#: with the whole DECIDE_BUDGET inside the retry's minute and push the live decision past the book's cut-off, the close
#: - 11 minutes): no other decision starts before the live decision's retry (its start + DECIDE_RETRY), every other task
#: is bounded to end DECISION_MARGIN before that retry (`_deadline`), and the held turn waits for the retry and starts it
#: at its time in the same turn (`_close_hold`, `_live_next`; a task that raised inside the lead never ends the turn),
#: so the retry lands before the cut-off when it can. A run cut by the lane's bound, or still running, keeps it too. The
#: lead ends at the latest once the decision is no longer live (`R.live_run`: LIVE_WITHIN after its time, its last
#: retry).
LEAD_ENDS = ("ok", "pending")
HOLD_STEP = 1.0
HOLD_TURNS = 40
VERDICT_BACKOFF = dt.timedelta(minutes=10)    # verdicts that got no answer (refused, failed, paused, over the line)
UNIVERSE_AT = dt.time(7, 30)
TICKERS_AT = dt.time(7, 0)
TICKERS_RETRY = dt.timedelta(minutes=5)
SCORE_AT = dt.time(20, 30)
#: RELEASE 1019i, THE BATCHED SCORE (`_score`): a pass prefetches the daily bars of this many of its intents at a time
#: (their symbols and both benchmarks in about two requests a 200 symbols), so a pass its bound cuts has read no bars
#: for intents it never reached.
PREFETCH_WINDOW = 400
REPORT_AT = dt.time(21, 5)                    # a day with no session: its report at this time
#: R3's births job (R3-SPEC section 5: "nightly after the report (20:30 ET + 45 min)"), on a session night, once. Its
#: bound holds the architect's STREAMED call (release 1019h's fix round; league/events/births.py `STREAM`): the call
#: starts only with its whole `CALL_LIMIT` (150 s) and one `STREAM_GAP` (60 s) left before the bound (`LaneGateway`
#: `post_stream`, `room`), so its last read returns before it; a whole Haiku night took about 10 s on the House (A95,
#: A109), so the facts before the call leave it its 210 s.
BIRTHS_AT = dt.time(21, 15)
BIRTHS_BUDGET = 240.0
#: THE SCREEN AFTER THE OPEN (release 1019f; the audit's "bands move a session late"). The judge makes a close X final
#: (league/events/screen.py `final_until`: A66's three sessions, A69's fast path once the session after X has had its
#: open decision), and the intents a look as of X covers were settled by X's own score, so the look can be written the
#: morning after X; the nightly screen alone wrote it at 20:30 ET, after that session's close decision. So from
#: SCREEN_OPEN_AT of a session whose open decision is made until SCREEN_CLEAR before its close decision, the lane reads
#: the final horizon of every seating version at most every SCREEN_OPEN_EVERY and runs the screen's looks of the
#: seating versions (`SCREEN_OPEN_JOB`, a receipt of its own: the daily report's nightly `screen` stays the nightly's)
#: whenever any moved since the last screen receipt (nightly or not), so nothing is screened twice for the same
#: horizons. A look is written once (screen.py `write_look`, INSERT OR IGNORE; version 2 resumes after the last look
#: on record) and its band move in its own transaction, whichever run writes it; the band review of the real fills
#: (demotion, Sized) stays the nightly's. No rule moves: the judge says when a close is final, the House only reads it
#: sooner.
SCREEN_OPEN_AT = dt.time(9, 40)
SCREEN_OPEN_EVERY = dt.timedelta(minutes=10)
SCREEN_OPEN_JOB = "screen-open"
SCREEN_JOBS = ("screen", SCREEN_OPEN_JOB)
#: A screen (CPU only, no bound: `Task.budget` None) never starts this close to the lane's next decision.
SCREEN_CLEAR = dt.timedelta(minutes=5)
#: What a screen receipt keeps of the screen's `waiting` (program, version, k, why), so the record says why a look waits.
WAITS_KEPT = 60
WHY_CHARS = 300
EQUITY_AFTER = dt.timedelta(minutes=3)
EQUITY_RETRY = dt.timedelta(minutes=10)
BACKFILL_WEEKDAYS = SN.FINAL_BACKFILL_WEEKDAYS
BACKFILL_AT = dt.time(5, 0)                   # a weekday's daily index is read from 05:00 ET the next day
BACKFILL_RETRY = dt.timedelta(hours=1)
#: SEC HOLIDAYS (release 1019f): EDGAR accepts no filings on a US federal holiday and publishes no daily index for it,
#: so such a weekday's index is never there, and its backfill waited every hour while the day was in reach (every look
#: across Wed Nov 11, 2026, Veterans Day, on which NYSE trades). SEC answers a daily index that does not exist with 403
#: or 503 (its archive's answer to a missing file), never 404 (the independent check of fix/backfill-robust): so a
#: weekday IN THIS TABLE whose index read fails, WHATEVER THE STATUS, is done, "no index: SEC holiday" (EDGAR accepts no
#: filing that day, so done is right even when the read failed for another reason); a failed read on any other weekday,
#: whatever its status, waits as an unpublished index does, and a holiday's index that exists is read as any day's.
#: THE TABLE IS THE JUDGE'S (release 1019f's review, lens judges): league/events/screen.py `SEC_HOLIDAYS`, behind the
#: wall, as the reach above is, since a look reads it too: a holiday's eve's late 8-Ks are in the index of the next
#: weekday EDGAR is open, so a holiday NYSE trades is final only once that index is backfilled as well
#: (screen.py `index_through`; the judge reads this name too, `_sec_holidays`, so a day only this copy lists still has
#: the index after it waited for).
SEC_HOLIDAYS: dict[dt.date, str] = SN.SEC_HOLIDAYS
SEC_HOLIDAY_WHY = "no index: SEC holiday"
CALENDAR_EVERY = dt.timedelta(hours=20)
CALENDAR_RETRY = dt.timedelta(minutes=10)
CALENDAR_BACK = dt.timedelta(days=60)
CALENDAR_AHEAD = dt.timedelta(days=120)
IDLE_LOOK = dt.timedelta(minutes=5)           # nothing due: look again at the latest this soon
FAIL_BACKOFF = dt.timedelta(minutes=10)       # a task that failed (record, nightly, tickers, backfill) waits this long
WAIT_LOOK = 60.0                              # no store yet: look again this often (seconds of the House clock)
FETCH_WINDOW = dt.timedelta(days=2)           # listed filings the record pass still fetches
FETCH_TRIES = 6                               # ... and a failed fetch is tried this many times in all,
#: ... again at the first record pass this long after its FIRST failure (release 1019b's second review: tried at every
#: pass, an SEC outage of about 12 minutes, or SEC's 10-minute rate-limit block, spent every try): 2, 4, 8, 16 and 32
#: minutes, then left to the daily-index backfill. The backfill tries a daily-index filing by the same two (release
#: 1019f: `_backfill`), with its own count.
FETCH_BACKOFF = tuple(dt.timedelta(minutes=2 ** k) for k in range(1, FETCH_TRIES))

#: RELEASE 1019i, THE PRICE LANE'S RECORDERS (PREREG-EVL-8's harness plan H2; league/events/pxdata.py), behind
#: league/config.json `events.px_data` (a missing key or false is OFF; on, they only WARM px.sqlite: no decision reads
#: it). Each is a task of its own, the LAST of the plan's (`_px_due`): never inside the live close decision's lead,
#: never within `PX_CLEAR` of the next decision, bounded by `PX_BUDGET` (and, as every task, to end DECISION_MARGIN
#: before the next decision), its reads cut at the bound (`PX.PxGateway`) and through the lane's bucket after the lane's
#: own (`PX.TokenBucket`, THE LANE FIRST), its failure its own (a warning; that recorder waits FAIL_BACKOFF, every other
#: task goes on), at most one run every `PX_EVERY`. The recorders' windows (New York times): the universe of today's
#: session from `PX_UNIVERSE_AT` to `PX_FLAGS_AT`; FLAGGED from `PX_FLAGS_AT` until `PX_FLAGS_BEFORE_CLOSE` before the
#: close; the premarket marks from `PX_PM_AT` (after the open window's sends) and the 15:30 marks from `PX_1530_AFTER`
#: after the close (each once its span is whole on the Basic plan's tape); the nightly bars once the night's score
#: has run; the 270-session backfill and the operating-company cache at night (`PX_NIGHT`) and on days with no session.
#: THE STORE'S ROOM (release 1019i's review; league/events/pxstore.py `room`): no run without it (`_px`: `disk`, nothing
#: opened), no request of a run without it (`PX.PxRoom`), and every PX run waits FAIL_BACKOFF after one that found none.
PX_BUDGET = 60.0
PX_CLEAR = dt.timedelta(minutes=10)
PX_EVERY = dt.timedelta(minutes=1)
PX_UNIVERSE_AT = dt.time(7, 40)
PX_FLAGS_AT = dt.time(9, 0)
PX_FLAGS_BEFORE_CLOSE = dt.timedelta(minutes=30)
PX_PM_AT = dt.time(9, 35)
PX_1530_AFTER = dt.timedelta(minutes=5)
PX_NIGHT = (dt.time(21, 30), dt.time(7, 0))
WARN_EVERY = 3600.0
DATA_INTERVAL = 0.5
ASSETS_TTL = 1800.0
VERDICT_USD_DAY = 3.0                         # league/config.json events.verdict_usd_day (the goal's cost rule)
VERDICT_USD_UNKNOWN = 0.01                    # a verdict whose cost the gateway did not state
#: R3's births call stored with no cost (league/events/births.py `propose` stores its worst case then; a NULL counts the
#: night's whole cap, `births.NIGHT_USD`).
BIRTH_USD_UNKNOWN = 0.25


class LaneCut(G.NotSent):
    """A Claude call the lane refused itself (past its bound, the House paused, the day's line reached; a streamed call
    with less than its limit and gap left before the bound, `room`): no answer and nothing sent, so the verdict is asked
    again later (league.events.verdicts.ask treats it as a transport failure; an OSError, through `G.NotSent`)."""


class LaneDeadline(R.Deadline):
    """A network read past the task's bound: the task stops, and the next turn goes on from what it stored (a
    `run.Deadline`, so a decision's isolated part never takes it for its own failure)."""


def events_enabled(config: Mapping[str, Any], *, canary: bool = False) -> bool:
    """`config.json` `events.enabled` (a missing key is OFF), never on a canary."""
    return not canary and (config.get("events") or {}).get("enabled") is True


@dataclasses.dataclass
class Task:
    name: str
    run: Callable[["LaneContext", float], dict[str, Any]]
    budget: float | None
    cut: bool = False   # network reads stop at the bound (their progress is kept in the store)


@dataclasses.dataclass
class VerdictLook:
    at: dt.datetime     # when the session's verdicts were last looked at (the House's clock)
    missing: int
    stalled: bool       # nothing stored and something refused or failed: wait VERDICT_BACKOFF


# ---------------------------------------------------------------------------------------------------- the gateway
class LaneGateway:
    """The lane's gateway for one task: market-data reads spaced and (`cut`) stopped at the bound; Claude calls refused
    (`LaneCut`) past the bound, while the House is paused or over the day's line, and counted."""

    def __init__(self, inner: Any, lane: "EventLane", deadline: float | None, *, cut: bool):
        self.inner, self.lane, self.deadline, self.cut = inner, lane, deadline, cut
        self.counts: collections.Counter[str] = collections.Counter()

    @property
    def last_headers(self) -> Mapping[str, str]:
        return getattr(self.inner, "last_headers", {}) or {}

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        if self.cut and self.lane.late(self.deadline):
            raise LaneDeadline(f"the task's bound passed before {path}")
        self.lane.throttle()
        return self.inner.get_json(path, params)

    def post_json(self, path: str, body: Any, headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        if path != V.PATH:
            return self.inner.post_json(path, body, headers)
        why = self.lane.claude_refusal(self.deadline)
        if why:
            self.counts[f"cut_{why}"] += 1
            raise LaneCut(why)
        self.counts["asked"] += 1
        try:
            code, payload = self.inner.post_json(path, body, headers)
        except OSError:
            self.counts["failed"] += 1
            raise
        if 200 <= code < 300:
            self.counts["answered"] += 1
            self.lane.spent(self.last_headers.get(V.COST_HEADER))
        elif 400 <= code < 500 and code != 429:
            self.counts["refused"] += 1
        else:
            self.counts["failed"] += 1
        return code, payload

    def post_stream(self, path: str, body: Any, headers: Mapping[str, str] | None = None, *, limit: float,
                    gap: float) -> tuple[int, Any]:
        """A STREAMED Claude call (R3's births call, release 1019h's fix round; league/events/gw.py `post_stream`):
        refused and counted as `post_json`'s, and refused (`room`) unless its whole `limit` and one `gap` (a read that
        returns at the gap's end) are left before the task's bound, so it never runs past the bound. A stream lost
        after it began is counted `failed`; its cost is the caller's to store (league/events/births.py `propose`), and
        the next task's `_spend_today` reads it from the store."""
        why = self.lane.claude_refusal(self.deadline)
        if why is None and self.deadline is not None and self.deadline - self.lane._mono() < float(limit) + float(gap):
            why = "room"
        if why:
            self.counts[f"cut_{why}"] += 1
            raise LaneCut(why)
        self.counts["asked"] += 1
        try:
            code, payload = self.inner.post_stream(path, body, headers, limit=limit, gap=gap)
        except OSError:
            self.counts["failed"] += 1
            raise
        if 200 <= code < 300:
            self.counts["answered"] += 1
            if str(self.last_headers.get(G.COST_KNOWN_HEADER) or "").lower() != "false":
                self.lane.spent(self.last_headers.get(V.COST_HEADER))
        elif 400 <= code < 500 and code != 429:
            self.counts["refused"] += 1
        else:
            self.counts["failed"] += 1
        return code, payload


class LaneContext(R.Context):
    """league.events.run's Context with the lane's caches: the asset list (`ASSETS_TTL`) and the parsed ticker
    snapshots outlive one turn, so a turn does not download either again."""

    def __init__(self, lane: "EventLane", store: S.Store, gw: LaneGateway, sec: Callable[[str], bytes],
                 now: Callable[[], dt.datetime], deadline: float | None = None):
        super().__init__(store, gw, sec, now=now)
        self._lane = lane
        self.deadline = deadline        # (the task's bound: PREREG-EVL-5's part never runs past it, run.py `part_until`)
        self.mono = lane._mono

    def _parsed(self, sha: str) -> dict[str, list[tuple[str, str]]]:
        cache = self._lane._tickers
        if sha not in cache:
            data = self.store.get_document(sha)
            while len(cache) >= 2:
                cache.pop(next(iter(cache)))
            cache[sha] = U.sec_tickers(lambda url: data)
        return cache[sha]

    def assets(self, live: bool = True) -> dict[str, Mapping[str, Any]]:
        return self._lane.assets(self.gw, "active" if live else "all")


# ---------------------------------------------------------------------------------------------------- the lane
class EventLane:
    """The event lane's scheduler on the House (see the module docstring). `due()`, `run()`, `shipped()` (False) and
    `health()`, the feeds lane's interface; `turn(house)` is what the wrapped publisher calls."""

    def __init__(self, house: Any, root: str | os.PathLike[str], *, gateway: Any = None,
                 sec: Callable[[str], bytes] | None = None, settings: Mapping[str, Any] | None = None,
                 monotonic: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.house = house
        self.root = Path(root)
        self.settings = dict(settings or {})
        self.verdict_usd_day = float(self.settings.get("verdict_usd_day", VERDICT_USD_DAY))
        self._line = {"usd_day": 0.0, "source": "not read yet"}   # THE LANE'S LINE (`_spend_today`): none before it is read
        #: R3's births job: `events.births` true in league/config.json (a missing key or false is off).
        self.births_on = self.settings.get("births") is True
        #: RELEASE 1019i: the PX recorders, `events.px_data` true (a missing key or false is off), and the bucket the lane's
        #: own market-data reads share with them (`throttle`: the lane first); no bucket while they are off.
        self.px_on = self.settings.get("px_data") is True
        self._bucket = PX.TokenBucket(clock=monotonic, sleep=sleep) if self.px_on else None
        self._px_last: dt.datetime | None = None
        #: ... THE STORE'S ROOM (release 1019i's review; league/events/pxstore.py `room`): the last check before a PX run
        #: (lane.json `px_store`) and when a run last found none (`_px_due` then waits FAIL_BACKOFF before the next).
        self._px_room: dict[str, Any] | None = None
        self._px_disk: dt.datetime | None = None
        self._gateway = gateway
        self._sec_base = sec
        self._mono = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._running: str | None = None
        self._next_look = float("-inf")        # House clock: due() says nothing before this
        self._ready = False
        self._stopped = False
        self._waiting_told = False
        self._stop_told = False
        self._started_told = False
        self._born = self.now()
        self._last_get = float("-inf")
        self._asset_cache: dict[str, tuple[float, dict[str, Mapping[str, Any]]]] = {}
        self._tickers: dict[str, dict[str, list[tuple[str, str]]]] = {}
        self._warned: dict[str, float] = {}
        self._warnings = 0
        self._tasks: dict[str, dict[str, Any]] = {}
        self._last: dict[str, Any] | None = None
        self._cut: set[tuple[str, dt.date]] = set()
        self._redecide: set[tuple[str, dt.date]] = set()
        self._redecide_next = self._born
        self._four: set[dt.date] = set()        # closes whose PREREG-EVL-4 rows wait for their own decision
        self._five: set[dt.date] = set()        # closes whose PREREG-EVL-5 rows wait for their own decision
        self._pre_failed: dict[dt.date, dt.datetime] = {}     # PREREG-EVL-5's pre-reads that failed (VERDICT_BACKOFF)
        self._births_redo: set[tuple[str, dt.date]] = set()   # decisions whose births wait for their own (`BIRTH_KINDS`)
        self._looks: dict[tuple[str, dt.date], VerdictLook] = {}
        self._events_at = self._born            # when a record pass last stored something new
        self._universe_told: set[dt.date] = set()
        self._attempts: dict[str, dt.datetime] = {}
        self._score_seen: dict[dt.date, set[tuple[str, int, str]]] = {}
        self._open_checked: dt.datetime | None = None   # when the screen after the open last read the horizons
        self._backfill_seen: dict[dt.date, set[str]] = {}
        # day -> accession -> (the backfill's fetches tried, when the first failed, form, the last error): a failed
        # daily-index filing, this process's (`_backfill`); and day -> when its next retry is due (`_backfill_due`)
        self._backfill_failed: dict[dt.date, dict[str, tuple[int, dt.datetime, str, str]]] = {}
        self._backfill_wait: dict[dt.date, dt.datetime] = {}
        self._index_rows: dict[dt.date, list[dict[str, Any]]] = {}
        self._usd = {"day": None, "usd": 0.0}
        self._paused = False
        self._failed: dict[str, dt.datetime] = {}
        # accession -> (the fetches tried, when the first one failed), this process's (`_record_steps`)
        self._fetch_tries: dict[str, tuple[int, dt.datetime | None]] = {}

    # -- the feeds lane's interface ---------------------------------------------------------------------------------
    def shipped(self) -> bool:
        """Nothing the House's tool requests could read: the lane answers none of them (the feeds interface)."""
        return False

    def due(self) -> bool:
        """Cheap and on the tick's thread: whether a turn is worth starting. Never raises."""
        try:
            with self._lock:
                if self._running is not None or self.house.clock() < self._next_look:
                    return False
            if not self.ready():
                self._tell_stopped() if self._stopped else self._tell_waiting()
                with self._lock:
                    self._next_look = self.house.clock() + WAIT_LOOK
                return False
            self._stop_told = False
            return True
        except Exception:  # noqa: BLE001 - the tick never pays for the lane
            return False

    def turn(self, house: Any) -> None:
        """Start a turn on the House's feeds lane when one is due (the wrapped publisher's call). Never raises."""
        try:
            if self.due():
                house._background(BACKGROUND_KEY, self.run)
        except Exception as exc:  # noqa: BLE001
            self.warn("turn", exc)

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {"enabled": True, "ready": self._ready, "stopped": self._stopped, "root": str(self.root),
                    "running": self._running,
                    "next_look": _iso_epoch(self._next_look), "last": dict(self._last) if self._last else None,
                    "tasks": {k: dict(v) for k, v in sorted(self._tasks.items())},
                    "verdict_usd_today": round(float(self._usd["usd"]), 4), "verdict_usd_day": self.verdict_usd_day,
                    "verdict_line_usd": round(float(self._line["usd_day"]), 4), "verdict_line_source": self._line["source"],
                    "warnings": self._warnings, "px_data": self.px_on,
                    "px_bucket": None if self._bucket is None else dict(self._bucket.taken),
                    "px_store": None if self._px_room is None else dict(self._px_room)}

    def ready(self) -> bool:
        """The store exists (the migration, scripts/evl_migrate.py, made it, or the operator did; the lane never makes
        its own root, so it cannot race the migration that fills it) and no `STOP` file is in it."""
        self._ready = (self.root / S.DB_NAME).is_file()
        self._stopped = self._ready and (self.root / STOP_FILE).exists()
        return self._ready and not self._stopped

    # -- clocks, bounds and paid work -------------------------------------------------------------------------------
    def now(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(float(self.house.clock()), UTC)

    def closing(self) -> bool:
        flag = getattr(self.house, "_closing", None)
        return bool(flag is not None and flag.is_set())

    def late(self, deadline: float | None) -> bool:
        return self.closing() or (deadline is not None and self._mono() >= deadline)

    def throttle(self) -> None:
        wait = self._last_get + DATA_INTERVAL - self._mono()
        if wait > 0:
            self._sleep(wait)
        self._last_get = self._mono()
        if self._bucket is not None:
            self._bucket.take_lane()    # (release 1019i: the lane's token of the bucket it shares with the PX recorders)

    def claude_refusal(self, deadline: float | None) -> str | None:
        if self.closing():
            return "closed"
        if deadline is not None and self._mono() >= deadline:
            return "deadline"
        if self._paused:
            return "paused"
        if self._usd["usd"] >= self._line["usd_day"]:
            return "cap"
        return None

    def spent(self, header: Any) -> None:
        try:
            usd = float(header) if header not in (None, "") else VERDICT_USD_UNKNOWN
        except (TypeError, ValueError):
            usd = VERDICT_USD_UNKNOWN
        self._usd["usd"] += max(0.0, usd)

    def _spend_today(self, st: S.Store, now: dt.datetime) -> None:
        """The day's Claude dollars of the lane so far, from the store, and the line the next call is held to
        (`verdict_line`). THE DAY is the UTC day (`verdict_day`: budget rule 3's, every other line's and the cap
        breach's). Its Claude dollars are its verdicts' and R3's births call's (`birth_usd`: the births job's one call a
        night, Claude Opus 5.5 from release 1019h, goes through this lane's gateway, on the same Claude meter, so it is
        inside the same line; release 1019e's review), each at its stated cost (a verdict with none at
        `VERDICT_USD_UNKNOWN`, a births call at `BIRTH_USD_UNKNOWN`)."""
        day, (lo, hi) = verdict_day(now)
        row = st.db.execute("SELECT COALESCE(SUM(usd), 0), COALESCE(SUM(usd IS NULL), 0) FROM verdicts WHERE "
                            "answered_at>=? AND answered_at<?", (lo, hi)).fetchone()
        usd = float(row[0]) + VERDICT_USD_UNKNOWN * int(row[1]) + birth_usd(st.db, lo, hi)
        self._usd = {"day": day, "usd": usd}
        self._line = self.verdict_line(now)

    def line_left(self) -> float:
        """What is left of the lane's line today (`_spend_today`'s line less its spend, never below 0)."""
        return max(0.0, float(self._line["usd_day"]) - float(self._usd["usd"]))

    def verdict_line(self, now: dt.datetime) -> dict[str, Any]:
        """THE LANE'S LINE (the module docstring): {usd_day, source}, the lower of `events.verdict_usd_day` and the budget
        rule's allowance (league/ops/budget.py `lane_allowance`, which never raises and falls back to the rule's own
        no-profit line). Anything else that goes wrong is no line at all: no paid call (FAIL CLOSED)."""
        try:
            from ..ops import budget as B

            got = B.lane_allowance(self.root.parent, now.timestamp())
            allowance, source = max(0.0, float(got["usd_day"])), str(got.get("source") or "budget.json")
        except Exception as exc:  # noqa: BLE001 - no allowance read is no paid verdict
            return {"usd_day": 0.0, "source": f"the budget's allowance could not be read ({type(exc).__name__})"}
        if self.verdict_usd_day <= allowance:
            return {"usd_day": self.verdict_usd_day, "source": "events.verdict_usd_day"}
        return {"usd_day": allowance, "source": f"the budget's allowance: {source}"}

    def assets(self, gw: Any, key: str) -> dict[str, Mapping[str, Any]]:
        """Alpaca's asset list (`key` "active" for the live rule, "all" for the backfill rule), kept ASSETS_TTL. An
        EMPTY answer is never kept (release 1019b's third review): league/events/run.py `eligibility` decides nothing on
        it, so the next turn asks Alpaca again, inside the live decision's window, instead of failing on it for half an
        hour."""
        have = self._asset_cache.get(key)
        if have is not None and self._mono() - have[0] < ASSETS_TTL:
            return have[1]
        rows = U.alpaca_assets(gw, key)
        keep = ("symbol", "class", "exchange", "status", "tradable")
        slim = {sym: {k: a.get(k) for k in keep} for sym, a in rows.items()}
        if slim:
            self._asset_cache[key] = (self._mono(), slim)
        else:
            self._asset_cache.pop(key, None)
        return slim

    def gateway(self) -> Any:
        if self._gateway is None:
            from ..service import secret  # the House's own token source, as league/service.py gives the live path

            self._gateway = G.Gateway(lambda: secret("GATEWAY_TOKEN"))
        return self._gateway

    def sec(self) -> Callable[[str], bytes]:
        if self._sec_base is None:
            self._sec_base = G.sec_getter()   # ltcm.data CONTACT_USER_AGENT, one transport: one SEC rate
        return self._sec_base

    def _sec_for(self, deadline: float | None, cut: bool) -> Callable[[str], bytes]:
        base = self.sec()

        def get(url: str) -> bytes:
            if cut and self.late(deadline):
                raise LaneDeadline(f"the task's bound passed before {url[:80]}")
            return base(url)
        return get

    # -- warnings ---------------------------------------------------------------------------------------------------
    def warn(self, task: str, exc: BaseException | str) -> None:
        """A warning at most once an hour per task: never ten of one text in 30 minutes, so never an error alert."""
        try:
            clock = float(self.house.clock())
            if clock - self._warned.get(task, float("-inf")) < WARN_EVERY:
                return
            self._warned[task] = clock
            self._warnings += 1
            what = exc if isinstance(exc, str) else f"{type(exc).__name__}: {str(exc)[:200]}"
            self.house.alert("warning", f"the event lane's {task} failed ({what}); it is tried again on its schedule "
                                        "(league/events/house.py)")
        except Exception:  # noqa: BLE001 - a warning that cannot be written costs nothing more
            pass

    def _info(self, text: str) -> None:
        try:
            self.house.alert("info", text)
        except Exception:  # noqa: BLE001
            pass

    def _tell_stopped(self) -> None:
        if not self._stop_told:
            self._stop_told = True
            self._info(f"the event lane is stopped by {self.root / STOP_FILE}; it records, decides and asks nothing "
                       "until the file is removed")

    def _tell_waiting(self) -> None:
        if not self._waiting_told:
            self._waiting_told = True
            self._info(f"the event lane is switched on and waits for its store at {self.root} (scripts/evl_migrate.py "
                       "copies the desktop's there); it records nothing until then")

    # -- one turn ---------------------------------------------------------------------------------------------------
    def run(self) -> None:
        """One turn: the single most urgent due task, bounded. Never raises (a failure is `warn`'s)."""
        with self._lock:
            if self._running is not None:
                return
            self._running = "planning"
        began = self._mono()
        name = "turn"
        next_look = self.house.clock() + WAIT_LOOK
        try:
            if not self.ready():
                return
            with S.Store(self.root) as st:
                P.load_births(st)       # (R3: the registered births, after every PREREG program, for every task)
                if not self._started_told:
                    self._started_told = True
                    self._info(f"the event lane runs on the House: store {self.root} (league/events/house.py)")
                for _ in range(HOLD_TURNS):
                    now = self.now()
                    self._maintain(st, now)
                    task, _ = self._plan(st, now)
                    if task is not None:
                        name = task.name
                        with self._lock:
                            self._running = name
                        try:
                            status, summary = self._do(st, task)
                        except Exception as exc:  # noqa: BLE001 - outside the lead, the turn's failure as before
                            if self._lead(st, self.now()) is None:
                                raise
                            # (release 1019h: INSIDE THE LEAD a task that raised, a failed run of today's live close
                            # decision among them, is the turn's failure as before (noted, warned) but never ends the
                            # turn: the live decision's retry starts at its time in this turn, `_close_hold`)
                            self._failed[name] = self.now()
                            self._note(name, "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, began)
                            self.warn(name, exc)
                        else:
                            self._note(name, status, summary, began)
                    now = self.now()
                    follow, at = self._plan(st, now)
                    next_look = self.house.clock() if follow is not None else \
                        self.house.clock() + max(0.0, (at - now).total_seconds())
                    hold = self._close_hold(st, now)
                    if hold is None and follow is not None and self._close_owed(st, now):
                        # (a task of the lead returned at or after the decision's time: the decision in this turn,
                        # at once, never at the next publish)
                        hold = now
                    if hold is None:
                        lead = self._hold_from(st, now)
                        if lead is not None:
                            next_look = min(next_look, self.house.clock() + max(0.0, (lead - now).total_seconds()))
                        break
                    # (PREREG-EVL-5 section 1.3: the turn is kept for the live close decision, HOLD_LEAD)
                    step = dt.timedelta(seconds=HOLD_STEP)
                    if follow is None:
                        wake = min(max(at, now + step), hold)      # (the next task due, or the decision)
                    elif now >= hold - dt.timedelta(seconds=DECISION_MARGIN):
                        wake = hold                                 # (inside the decision's margin: the decision first)
                    elif task is not None and self._mono() - began < HOLD_STEP:
                        wake = now + step                           # (a task that took no time is not run again at once)
                    else:
                        wake = now
                    if not self._wait_until(wake):
                        break
                    began, name = self._mono(), "turn"
                    with self._lock:
                        self._running = "planning"
        except Exception as exc:  # noqa: BLE001 - a turn's failure is a warning, never the tick's
            self._failed[name] = self.now()
            self._note(name, "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, began)
            self.warn(name, exc)
        finally:
            with self._lock:
                self._running = None
                self._next_look = next_look
            self._write_health()

    def _close_hold(self, st: S.Store, now: dt.datetime) -> dt.datetime | None:
        """When today's LIVE CLOSE DECISION starts next (`_live_next`: its time + CLOSE_GRACE, or after a FAILED run its
        retry, release 1019h), while that is at most HOLD_LEAD ahead of `now`, the lead stands (`_lead`) and PREREG-EVL-5
        has programs (their real money waits for it, `book.part_hold`); else None."""
        start = self._live_next(st, now)
        return start if start is not None and now < start <= now + HOLD_LEAD else None

    def _live_next(self, st: S.Store, now: dt.datetime,
                   latest: Mapping[str, tuple[str, dt.datetime]] | None = None) -> dt.datetime | None:
        """WHEN TODAY'S LIVE CLOSE DECISION IS NEXT DUE while the lead stands (`_lead`; release 1019h, the review of
        release 1019g): its time (+ CLOSE_GRACE) while no run of it has started; the latest run's start + DECIDE_RETRY
        when that run FAILED (`_due_decision`'s retry of a live decision); None otherwise (no lead, or a run cut by the
        lane's bound or never finished: due at once, or waiting as `_due_decision` says). `latest` as `_lead`'s."""
        at = self._lead(st, now, latest)
        if at is None:
            return None
        job = f"decide-close:{now.astimezone(C.NY).date().isoformat()}"
        if latest is not None:
            status, last = latest.get(job, (None, None))
        else:
            row = st.db.execute("SELECT status, started_at FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                                (job,)).fetchone()
            status, last = (None, None) if row is None else (str(row["status"] or ""), S.parse_iso(row["started_at"]))
        if status is None:
            return at
        return last + DECIDE_RETRY if status == "failed" and last is not None else None

    def _hold_from(self, st: S.Store, now: dt.datetime) -> dt.datetime | None:
        """When a turn should start to keep itself for today's live close decision (HOLD_LEAD before it), when that is
        still ahead of `now`; else None."""
        at = self._hold_at(st, now)
        return at - HOLD_LEAD if at is not None and now < at - HOLD_LEAD else None

    def _close_owed(self, st: S.Store, now: dt.datetime) -> bool:
        """True when today's live close decision's time (+ CLOSE_GRACE) has come while PREREG-EVL-5 has programs, the
        decision is still live (`R.live_run`) and no run of it has finished `ok` or `pending` (`_lead`): a task of the
        lead that returned at or after its time (a network read past its bound) leaves it to this turn, never to the
        next publish."""
        at = self._lead(st, now)
        return at is not None and now >= at

    def _lead(self, st: S.Store, now: dt.datetime,
              latest: Mapping[str, tuple[str, dt.datetime]] | None = None) -> dt.datetime | None:
        """THE LEAD (HOLD_LEAD's comment): today's live close decision's time (its time + CLOSE_GRACE) from HOLD_LEAD
        before it until a run of it has FINISHED `ok` or `pending` (the book's own reading of a made decision,
        league/events/book.py `decided` and `part_hold`: release 1019h, the review of release 1019g; a run that failed,
        was cut or is still running keeps the lead), while it is still live (`R.live_run`: its last retry is within
        LIVE_WITHIN of its time) and PREREG-EVL-5 has programs; else None. Inside it no other decision starts
        (`_due_decision`). `latest`: the decisions' receipts as `_decide_receipts` reads them (its latest status
        `ok` or `pending` ends the lead; any other, or none, is read again in the store, so an earlier finished run of
        the decision ends it too)."""
        at = self._hold_at(st, now)
        if at is None or now < at - HOLD_LEAD or not R.live_run(at - CLOSE_GRACE, now):
            return None
        job = f"decide-close:{now.astimezone(C.NY).date().isoformat()}"
        if latest is not None and latest.get(job, ("", None))[0] in LEAD_ENDS:
            return None
        made = st.db.execute("SELECT 1 FROM receipts WHERE job=? AND finished_at IS NOT NULL AND status IN (?, ?) LIMIT 1",
                             (job, *LEAD_ENDS)).fetchone() is not None
        return None if made else at

    @staticmethod
    def _hold_at(st: S.Store, now: dt.datetime) -> dt.datetime | None:
        if not R.five_programs():
            return None
        session = C.session(st, now.astimezone(C.NY).date())
        return None if session is None else session.close_decide + CLOSE_GRACE

    def _wait_until(self, when: dt.datetime) -> bool:
        """Wait on the House's clock until `when`, HOLD_STEP a look (`sleep`). False, at once, when the House is closing,
        the STOP file is there or the store is gone, or a look found the clock where it was (a clock that does not move:
        nothing could come due)."""
        while True:
            now = self.now()
            if now >= when:
                return True
            if self.closing() or not self.ready():
                return False
            self._sleep(min(HOLD_STEP, max(0.0, (when - now).total_seconds())))
            if self.now() <= now:
                return False

    def _do(self, st: S.Store, task: Task) -> tuple[str, dict[str, Any]]:
        """Run `task` under its bound; its Claude calls are counted into a `verdicts` receipt."""
        now = self.now()
        deadline = self._deadline(st, now, task)
        gw = LaneGateway(self.gateway(), self, deadline, cut=task.cut)
        self._paused = bool(self._house_paused())
        self._spend_today(st, now)
        ctx = LaneContext(self, st, gw, self._sec_for(deadline, task.cut), self.now, deadline)
        try:
            out = task.run(ctx, deadline) or {}
            status = str(out.pop("_status", "ok"))
        except LaneDeadline as exc:
            out, status = {"cut": str(exc)[:200]}, "cut"
        finally:
            self._verdict_receipt(st, task.name, gw)
        return status, out

    def _house_paused(self) -> Any:
        paused = getattr(self.house, "paused", None)
        try:
            return paused() if callable(paused) else None
        except Exception:  # noqa: BLE001 - an unreadable PAUSE file pauses nothing new here
            return None

    def _deadline(self, st: S.Store, now: dt.datetime, task: Task) -> float | None:
        if task.budget is None:
            return None
        bound = float(task.budget)
        if not task.name.startswith("decide"):
            nxt = self._next_decision(st, now)
            # (release 1019h: inside the lead, also the live close decision's next start once its time has passed: a
            # failed run's retry, which `_next_decision` skips as a time already passed)
            live = self._live_next(st, now)
            if live is not None and live > now and (nxt is None or live < nxt):
                nxt = live
            if nxt is not None:
                bound = min(bound, max(1.0, (nxt - now).total_seconds() - DECISION_MARGIN))
        return self._mono() + bound

    def _note(self, name: str, status: str, summary: Mapping[str, Any], began: float) -> None:
        row = {"at": S.iso(self.now()), "status": status, "seconds": round(self._mono() - began, 3)}
        brief = {k: v for k, v in summary.items() if isinstance(v, (int, float, str, bool)) or v is None}
        with self._lock:
            self._tasks[name] = row | ({"summary": brief} if brief else {})
            self._last = {"task": name, **row}

    def _verdict_receipt(self, st: S.Store, task: str, gw: LaneGateway) -> None:
        """A `verdicts` receipt for every task that asked: asked, answered, refused, failed and each kind of the lane's
        own refusal (WP2's evl_verdicts reads the day's)."""
        if not gw.counts:
            return
        try:
            rid = st.start_receipt("verdicts", now=self.now())
            st.finish_receipt(rid, "ok", {"task": task, **dict(gw.counts)}, now=self.now())
        except Exception:  # noqa: BLE001 - the counts are a report, never the task's outcome
            pass

    def _write_health(self) -> None:
        if not self._ready:
            return
        try:
            path = self.root / HEALTH_FILE
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(self.health(), sort_keys=True, default=str) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001
            pass

    # -- the calendar ----------------------------------------------------------------------------------------------
    def _maintain(self, st: S.Store, now: dt.datetime) -> None:
        """The NYSE calendar from Alpaca, about once a day and whenever it does not reach 30 days ahead."""
        last = st.meta("evl:lane:sessions_at")
        tried = self._attempts.get("sessions")
        today = now.astimezone(C.NY).date()
        row = st.db.execute("SELECT max(day) FROM sessions").fetchone()
        short = row[0] is None or dt.date.fromisoformat(row[0]) < today + dt.timedelta(days=30)
        stale = last is None or now - S.parse_iso(last) >= CALENDAR_EVERY
        if not (short or stale) or (tried is not None and now - tried < CALENDAR_RETRY):
            return
        self._attempts["sessions"] = now
        gw = LaneGateway(self.gateway(), self, None, cut=False)
        try:
            n = C.refresh(st, gw, today - CALENDAR_BACK, today + CALENDAR_AHEAD)
            st.set_meta("evl:lane:sessions_at", S.iso(now))
            self._note("sessions", "ok", {"sessions": n}, self._mono())
        except Exception as exc:  # noqa: BLE001 - the stored calendar serves until the next try
            self._note("sessions", "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, self._mono())
            self.warn("calendar refresh", exc)

    def _next_decision(self, st: S.Store, now: dt.datetime) -> dt.datetime | None:
        today = now.astimezone(C.NY).date()
        for s in C.sessions(st, today, today + dt.timedelta(days=10)):
            for at in (s.open_decide, s.close_decide + CLOSE_GRACE):
                if at > now:
                    return at
        return None

    # -- the plan ---------------------------------------------------------------------------------------------------
    def _plan(self, st: S.Store, now: dt.datetime) -> tuple[Task | None, dt.datetime]:
        """The most urgent due task (or None) and, when there is none, when to look again."""
        soon: list[dt.datetime] = [now + IDLE_LOOK]
        today = now.astimezone(C.NY).date()
        session = C.session(st, today)
        latest = self._decide_receipts(st, now)
        if now >= self._redecide_next:
            self._refill_redecide(st, now, today, latest)
        last_record = self._last_started(st, "record")
        record_due = last_record is None or now >= last_record + RECORD_EVERY
        # a backlog (missed decisions, a long verdict queue) never starves the record pass past a second cadence
        starved = record_due and (last_record is None or now >= last_record + 2 * RECORD_EVERY) and \
            not self._quiet("record", now, [])
        decision = self._due_decision(st, now, latest, soon)
        if decision is not None and (decision[0] == 0 or (decision[0] < 3 and not starved)):
            return self._decision_task(decision), now
        urgent, early = self._verdict_targets(st, now, today, session, latest, soon)
        if urgent is not None and not starved:
            kind, day, live = urgent
            return Task("verdicts", lambda ctx, deadline: self._verdicts(ctx, kind, day, live), VERDICT_BUDGET,
                        cut=True), now
        if not record_due:
            soon.append(last_record + RECORD_EVERY)
        elif not self._quiet("record", now, soon):
            return Task("record", self._record, RECORD_BUDGET), now
        if decision is not None and decision[0] < 3:   # the record pass could not run (it failed lately)
            return self._decision_task(decision), now
        if urgent is not None:
            kind, day, live = urgent
            return Task("verdicts", lambda ctx, deadline: self._verdicts(ctx, kind, day, live), VERDICT_BUDGET,
                        cut=True), now
        if decision is not None:   # the hourly re-decision, and the backfill's: after the record pass
            return self._decision_task(decision), now
        nightly = self._nightly(st, now, today, session, soon)
        if nightly is not None:
            return nightly, now
        screen = self._screen_open_due(st, now, today, session, soon)
        if screen is not None:
            return screen, now
        if self._tickers_due(st, now, today, soon) and not self._quiet("tickers", now, soon):
            return Task("tickers", self._snapshot, None), now
        if early is not None:
            kind, day, live = early
            return Task("verdicts", lambda ctx, deadline: self._verdicts(ctx, kind, day, live), VERDICT_BUDGET,
                        cut=True), now
        backfill = self._backfill_due(st, now, today, soon)
        if backfill is not None and not self._quiet("backfill", now, soon):
            return Task("backfill", lambda ctx, deadline: self._backfill(ctx, backfill, deadline), BACKFILL_BUDGET), now
        px = self._px_due(st, now, today, session, soon)     # (release 1019i: the PX recorders, last of all)
        if px is not None:
            return px, now
        return None, min(soon)

    def _decision_task(self, decision: tuple[int, dt.datetime, str, dt.date, bool]) -> Task:
        _, _, kind, day, live = decision
        return Task(f"decide-{kind}", lambda ctx, deadline: self._decide(ctx, kind, day, live), DECIDE_BUDGET, cut=True)

    def _quiet(self, name: str, now: dt.datetime, soon: list[dt.datetime]) -> bool:
        """True while task `name` failed less than FAIL_BACKOFF ago (a failing task never retries every minute)."""
        at = self._failed.get(name)
        if at is not None and now < at + FAIL_BACKOFF:
            soon.append(at + FAIL_BACKOFF)
            return True
        return False

    def _decide_receipts(self, st: S.Store, now: dt.datetime) -> dict[str, tuple[str, dt.datetime]]:
        """job -> (status, started_at) of each decision's latest receipt in the look-back."""
        since = S.iso(now - LOOKBACK - dt.timedelta(days=1))
        out: dict[str, tuple[str, dt.datetime]] = {}
        for row in st.db.execute("SELECT job, status, started_at FROM receipts WHERE job LIKE 'decide-%' AND started_at>=? "
                                 "ORDER BY id", (since,)):
            out[str(row["job"])] = (str(row["status"] or ""), S.parse_iso(row["started_at"]))
        return out

    def _decision_times(self, st: S.Store, first: dt.date, last: dt.date) -> Iterable[tuple[C.Session, str, dt.datetime, dt.datetime]]:
        """(session, kind, scheduled time, the time it is run from) for every decision of the sessions in [first, last],
        PREREG-EVL-4's rows' own decision (`FOUR_KIND`) of each close that waits for it (`_four`), PREREG-EVL-5's
        (`FIVE_KIND`, `_five`) and the births' own decision (`BIRTH_KINDS`) of each decision whose births wait for it
        (`_births_redo`)."""
        for s in C.sessions(st, first, last):
            yield s, "open", s.open_decide, s.open_decide
            if ("open", s.day) in self._births_redo:
                yield s, BIRTH_KINDS["open"], s.open_decide, s.open_decide
            yield s, "close", s.close_decide, s.close_decide + CLOSE_GRACE
            if s.day in self._four:
                yield s, FOUR_KIND, s.close_decide, s.close_decide + CLOSE_GRACE
            if s.day in self._five:
                yield s, FIVE_KIND, s.close_decide, s.close_decide + CLOSE_GRACE
            if ("close", s.day) in self._births_redo:
                yield s, BIRTH_KINDS["close"], s.close_decide, s.close_decide + CLOSE_GRACE

    def _refill_redecide(self, st: S.Store, now: dt.datetime, today: dt.date,
                         latest: Mapping[str, tuple[str, dt.datetime]] | None = None) -> None:
        """Once an hour: the last REDECIDE_SESSIONS sessions' decisions again (late events still get their decision).

        Then PREREG-EVL-4'S ROWS (release 1019c's review): every older close since its registration, back to LOOKBACK,
        that a release without its rows decided last (league/events/screen.py `made_without`) gets their own decision,
        `FOUR_KIND`, once, as a backfill: release 1019b's closes from 16:01:05Z Oct 19 to this release's deploy that
        the hourly re-decision no longer reaches. A close it still reaches is decided again whole by it, and a close
        whose latest decision is pending is decided again whole by its retry: each names their rows then. One decided
        by themselves and then again by such a release (stale) is decided again.

        PREREG-EVL-5'S ROWS (its section 3) the same way (`FIVE_KIND`, `made_without(prereg=5)`): every close since its
        registration that a release without its rows decided, or whose PREREG-EVL-5 part failed or ran past its own
        bound, and the hourly re-decision no longer reaches, gets their own decision, once, as a backfill, oldest first.

        THE BIRTHS' OWN DECISIONS (release 1019e's review) the same way: every older open and close decision that a
        release or a turn without the registered births made last (league/events/screen.py `births_made_without`) gets
        the births' own decision (`BIRTH_KINDS`), once, as a backfill; one whose births-only receipt is stale, or named
        not every birth (a birth's part failed), is decided again, once an hour."""
        self._redecide_next = now + REDECIDE_EVERY
        start = P.registered().astimezone(C.NY).date()
        due = [s for s in C.sessions(st, max(start, today - dt.timedelta(days=14)), today) if s.open_decide <= now]
        recent = due[-REDECIDE_SESSIONS:]
        for s in recent:
            self._redecide.add(("open", s.day))
            if s.close_decide + CLOSE_GRACE <= now:
                self._redecide.add(("close", s.day))
        reached = {s.day for s in recent}
        latest = self._decide_receipts(st, now) if latest is None else latest
        four: set[dt.date] = set()
        for day, stale in SN.made_without(st, today, first=(now - LOOKBACK).astimezone(C.NY).date()).items():
            status = latest.get(f"decide-close:{day.isoformat()}", (None, None))[0]
            if day in reached or status != "ok":
                continue
            four.add(day)
            if stale:
                self._redecide.add((FOUR_KIND, day))
        self._four = four
        five: set[dt.date] = set()
        for day, stale in SN.made_without(st, today, first=(now - LOOKBACK).astimezone(C.NY).date(), prereg=5).items():
            status = latest.get(f"decide-close:{day.isoformat()}", (None, None))[0]
            if day in reached or status != "ok":
                continue    # (decided again whole, by the hourly re-decision or its pending retry: naming them then)
            five.add(day)
            if stale:
                self._redecide.add((FIVE_KIND, day))
        self._five = five
        births: set[tuple[str, dt.date]] = set()
        for (kind, day), again in SN.births_made_without(st, today, first=(now - LOOKBACK).astimezone(C.NY).date()).items():
            status = latest.get(f"decide-{kind}:{day.isoformat()}", (None, None))[0]
            if day in reached or status != "ok":
                continue    # (decided again whole, by the hourly re-decision or its pending retry: naming them then)
            births.add((kind, day))
            if again:
                self._redecide.add((BIRTH_KINDS[kind], day))
        self._births_redo = births

    def _due_decision(self, st: S.Store, now: dt.datetime, latest: Mapping[str, tuple[str, dt.datetime]],
                      soon: list[dt.datetime]) -> tuple[int, dt.datetime, str, dt.date, bool] | None:
        """The most urgent decision: (0) a live one (within LIVE_WITHIN of its time) not yet made, (1) a missed one, oldest
        first, (2) one cut by the lane's bound, pending on verdicts or never finished, (3) the hourly re-decision (and
        the backfill's), which waits for the record pass. None when none is due.

        INSIDE THE LEAD (`_lead`, HOLD_LEAD's comment: from HOLD_LEAD before today's live close decision until a run of
        it has finished `ok` or `pending`, `LEAD_ENDS`, or it is no longer live) only that decision is ever due: every
        other one waits, whatever its rank, and is due again as soon as the live one is made (it is due at its time, so
        `soon` holds that time already); a failed run of the live one is retried at its own retry time first."""
        today = now.astimezone(C.NY).date()
        start = max(P.registered().astimezone(C.NY).date(), (now - LOOKBACK).astimezone(C.NY).date())
        best: tuple[int, dt.datetime, str, dt.date, bool] | None = None
        lead = self._lead(st, now, latest)
        for s, kind, scheduled, at in self._decision_times(st, start, today + dt.timedelta(days=7)):
            if at > now:
                soon.append(at)
                continue
            if lead is not None and (kind, s.day) != ("close", today):
                continue        # (the lead: no decision but the live close decision starts before it has)
            key = (kind, s.day)
            status, last = latest.get(f"decide-{kind}:{s.day.isoformat()}", (None, None))
            live = kind not in BACKFILL_KINDS and R.live_run(scheduled, now)   # (their rows' own: always a backfill)
            # (Release 1019b's second review: the receipt's own status first, then this lane's cut: a decision cut once
            # and failing since waits as a failed one does, never every turn.)
            if status is None:
                rank = 3 if kind in BACKFILL_KINDS else (0 if live else 1)   # (a re-decision: after the record pass)
            elif status == "ok":
                if key not in self._redecide:
                    continue
                rank = 3
            elif status == "pending":
                look = self._looks.get(key)
                if look is not None and look.at >= last and look.missing == 0:
                    retry = now                      # every verdict it waited for is stored now: decide at once
                elif look is not None and look.stalled:
                    retry = max(last + PENDING_RETRY, look.at + VERDICT_BACKOFF)   # its verdicts get no answer
                else:
                    retry = last + PENDING_RETRY
                if now < retry:
                    soon.append(retry)
                    continue
                rank = 0 if live else 2
            elif status == "failed":   # a run that raised (`_decide`): again a minute later while live, else STALE_RETRY
                retry = last + (DECIDE_RETRY if live else STALE_RETRY)
                if now < retry:
                    soon.append(retry)
                    continue
                rank = 0 if live else 2
            elif key in self._cut:     # cut by this lane's bound: it goes on at once
                rank = 0 if live else 2
            else:  # 'running' (a run that never finished), 'cut' or anything else
                if last >= self._born and now < last + STALE_RETRY:
                    soon.append(last + STALE_RETRY)
                    continue
                rank = 0 if live else 2
            candidate = (rank, at, kind, s.day, live)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        return best

    def _decide(self, ctx: LaneContext, kind: str, day: dt.date, live: bool) -> dict[str, Any]:
        key = (kind, day)
        self._redecide.discard(key)
        before = self._stored_verdicts(ctx.store)
        try:
            if kind == "open":
                out = R.decide_open(ctx, day, backfill_run=not live)
            elif kind == FOUR_KIND:
                out = R.decide_close(ctx, day, backfill_run=True, evl4_only=True)
            elif kind == FIVE_KIND:
                out = R.decide_close(ctx, day, backfill_run=True, evl5_only=True)
            elif kind == BIRTH_KINDS["open"]:
                out = R.decide_open(ctx, day, backfill_run=True, births_only=True)
            elif kind == BIRTH_KINDS["close"]:
                out = R.decide_close(ctx, day, backfill_run=True, births_only=True)
            else:
                out = R.decide_close(ctx, day, backfill_run=not live)
        except LaneDeadline:
            self._cut.add(key)
            self._close_running(ctx.store, f"decide-{kind}:{day.isoformat()}", "the lane's time bound; it goes on next turn")
            raise
        except Exception as exc:
            # (Release 1019b's review: a run that raised, one gateway 429 in its eligibility reads say, was left
            # `running` and waited STALE_RETRY, past LIVE_WITHIN: the session's live decision became a backfill. It is
            # closed `failed` and tried again after DECIDE_RETRY, live while within LIVE_WITHIN; it is no longer a cut
            # one, whatever it was before: the second review.)
            self._cut.discard(key)
            self._close_running(ctx.store, f"decide-{kind}:{day.isoformat()}",
                                f"{type(exc).__name__}: {str(exc)[:160]}", status="failed")
            raise
        self._cut.discard(key)
        if out.get("evl4_error"):   # (A83 (3)(i): PREREG-EVL-4's part failed alone; its own decision or the next whole one)
            self.warn("PREREG-EVL-4 part of a close decision", f"{day.isoformat()}: {out['evl4_error']}")
        if out.get("evl5_error"):   # (PREREG-EVL-5 section 1.3: its part failed alone; decide-close-evl5, never traded)
            self.warn("PREREG-EVL-5 part of a close decision", f"{day.isoformat()}: {out['evl5_error']}")
        missing = sum((out.get("pending") or {}).values())
        self._look(key, missing, self._stored_verdicts(ctx.store) - before, ctx.gw)
        return {"day": day.isoformat(), "live": live, "pending": missing,
                "_status": "pending" if out.get("pending") else "ok"}

    @staticmethod
    def _close_running(st: S.Store, job: str, why: str, *, status: str = "cut") -> None:
        row = st.db.execute("SELECT id FROM receipts WHERE job=? AND status='running' ORDER BY id DESC LIMIT 1",
                            (job,)).fetchone()
        if row is not None:
            st.finish_receipt(int(row["id"]), status, {"why": why})

    # -- verdicts ---------------------------------------------------------------------------------------------------
    def _verdict_targets(self, st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None,
                         latest: Mapping[str, tuple[str, dt.datetime]], soon: list[dt.datetime]
                         ) -> tuple[tuple[str, dt.date, bool] | None, tuple[str, dt.date, bool] | None]:
        """(urgent, early), each (kind, day, live) or None: a decision within URGENT_BEFORE of its time or pending, and
        today's next one before that (from 07:30 ET), only while its verdicts may still be missing."""
        urgent = early = None
        if session is not None:
            ready = session.at(UNIVERSE_AT)
            for kind, decide_at in (("open", session.open_decide), ("close", session.close_decide)):
                status = latest.get(f"decide-{kind}:{today.isoformat()}", (None, None))[0]
                if status == "ok":
                    continue
                if now < ready:
                    soon.append(ready)
                    continue
                if not self._verdicts_due((kind, today), now, soon, fresh=True) and \
                        not (kind == "close" and self._pre_due(st, session, now, soon)):
                    continue
                live = R.live_run(decide_at, now)
                if status == "pending" or now >= decide_at - URGENT_BEFORE:
                    urgent = urgent or (kind, today, live)
                else:
                    early = early or (kind, today, live)
                    soon.append(decide_at - URGENT_BEFORE)
        if urgent is None:
            pending = sorted((dt.date.fromisoformat(job.split(":", 1)[1]), job[len("decide-"):].split(":", 1)[0])
                             for job, (status, _) in latest.items() if status == "pending")
            for day, kind in pending:
                if kind == FOUR_KIND and day not in self._four:
                    continue    # (its close was decided again whole since: that decision's own wait is the one read)
                if kind == FIVE_KIND and day not in self._five:
                    continue    # (the same for PREREG-EVL-5's rows' own decision)
                if kind in BIRTH_KINDS.values() and (_base_kind(kind), day) not in self._births_redo:
                    continue    # (the same for the births' own decision)
                if day != today and self._verdicts_due((kind, day), now, soon, fresh=False):
                    urgent = (kind, day, False)
                    break
        return urgent, early

    def _pre_due(self, st: S.Store, session: C.Session, now: dt.datetime, soon: list[dt.datetime]) -> bool:
        """PREREG-EVL-5'S PRE-PASS (its section 1.3; the module docstring's step 2): whether today's close verdict pass
        is due for EVL-NEWS-NIGHT2-ON's heavy reads alone. From D's 09:30 minute on the tape (run.py `pre_from`) while
        meta `evl5:pre:<day>` is not stored; inside URGENT_BEFORE of the close decision only once the earlier rows'
        verdicts of the decision are all stored (the last pass saw no wait), once more when the stored cut is earlier
        than that mark. Never for a session none of whose attention articles of P can be an event (T29 of P at or
        before the registration time), nor while a written look of its group keeps EVL-NEWS-NIGHT2-ON (it is asked and
        fetched nothing, A74 (5)); a pre-read that failed waits VERDICT_BACKOFF (one its own bound cut goes on at once)."""
        start = R.pre_from(session)
        if now < start:
            soon.append(start)
            return False
        failed = self._pre_failed.get(session.day)
        if failed is not None and now < failed + VERDICT_BACKOFF:
            soon.append(failed + VERDICT_BACKOFF)
            return False
        night2 = [p for p in R.five_programs() if p.family == "news-night2"]
        try:
            last = P.attention_window(st, session.day)[1]
        except LookupError:
            return False
        if not night2 or all(last <= p.registered_at for p in night2):
            return False        # (no attention article of P can be an event: every one predates the registration)
        kept = R._scope(st, "close", session.day, now)
        if all(kept(p) is not None for p in night2):
            return False
        raw = st.meta(f"{R.PRE_KEY}{session.day.isoformat()}")
        late = session.close_decide - URGENT_BEFORE
        if now < late:
            if raw is not None:
                soon.append(late)
            return raw is None
        look = self._looks.get(("close", session.day))
        if look is None or look.missing > 0:
            return False
        if raw is None:
            return True
        try:
            cut = S.parse_iso(json.loads(raw)["cut"])
        except (TypeError, ValueError, KeyError):
            return False
        return cut < late

    def _verdicts_due(self, key: tuple[str, dt.date], now: dt.datetime, soon: list[dt.datetime], *, fresh: bool) -> bool:
        look = self._looks.get(key)
        if look is None or (fresh and self._events_at > look.at):
            return True
        if look.missing == 0:
            return False
        if look.stalled and now < look.at + VERDICT_BACKOFF:
            soon.append(look.at + VERDICT_BACKOFF)
            return False
        return True

    def _verdicts(self, ctx: LaneContext, kind: str, day: dt.date, live: bool) -> dict[str, Any]:
        """Every verdict the `kind` decision of session `day` will read, asked now: league.events.run's own decision
        code with `ask_only` (no intent, no receipt), so what is stored is what the decision reads. A close decision
        that waits on verdicts only the session's OPEN decision asks (PREREG-EVL-4's EVL-NEWSPM-READ-ON and its control
        read EVL-NEWS-READ-O1's PROMPT-NEWS verdicts and ask none of their own: `run.waits_on_open`) has that open
        decision's own asks made now (`decide_open` with `ask_only`), then is counted again: such a wait is never left
        to the hourly re-decision."""
        key = (kind, day)
        before = self._stored_verdicts(ctx.store)
        gw = ctx.gw
        if kind == "open":
            decide = R.decide_open
        elif kind == FOUR_KIND:     # PREREG-EVL-4's rows' own decision (a backfill): their verdicts alone
            def decide(ctx: Any, day: dt.date, *, backfill_run: bool, ask_only: bool) -> dict[str, Any]:
                return R.decide_close(ctx, day, backfill_run=True, ask_only=ask_only, evl4_only=True)
        elif kind == FIVE_KIND:     # PREREG-EVL-5's rows' own decision (a backfill): their verdicts alone
            def decide(ctx: Any, day: dt.date, *, backfill_run: bool, ask_only: bool) -> dict[str, Any]:
                return R.decide_close(ctx, day, backfill_run=True, ask_only=ask_only, evl5_only=True)
        elif kind in BIRTH_KINDS.values():      # the births' own decision (a backfill): their verdicts alone
            whole = R.decide_open if kind == BIRTH_KINDS["open"] else R.decide_close

            def decide(ctx: Any, day: dt.date, *, backfill_run: bool, ask_only: bool) -> dict[str, Any]:
                return whole(ctx, day, backfill_run=True, ask_only=ask_only, births_only=True)
        else:
            decide = R.decide_close
        try:
            out = decide(ctx, day, backfill_run=not live, ask_only=True)
            if kind in ("close", FOUR_KIND, BIRTH_KINDS["close"], FIVE_KIND) and R.waits_on_open(out):
                session = C.session(ctx.store, day)
                opened = R.live_run(session.open_decide, ctx.now()) if session is not None else False
                R.decide_open(ctx, day, backfill_run=not opened, ask_only=True)
                out = decide(ctx, day, backfill_run=not live, ask_only=True)
        except LaneDeadline:
            had = self._looks.get(key)
            self._looks[key] = VerdictLook(self.now(), max(1, had.missing if had else 1), False)
            raise
        except Exception:
            had = self._looks.get(key)
            self._looks[key] = VerdictLook(self.now(), max(1, had.missing if had else 1), True)
            raise
        pre = out.get("evl5_pre") if isinstance(out.get("evl5_pre"), Mapping) else None
        if pre is not None and pre.get("status") == "error":
            self._pre_failed[day] = self.now()      # (PREREG-EVL-5's pre-read failed: tried again after VERDICT_BACKOFF)
            self.warn("PREREG-EVL-5 pre-pass", f"{day.isoformat()}: {pre.get('why')}")
        elif pre is not None and pre.get("status") == "stored":
            self._pre_failed.pop(day, None)
        missing = sum((out.get("pending") or {}).values())
        stored = self._stored_verdicts(ctx.store) - before
        stalled = self._look(key, missing, stored, gw)
        if gw.counts.get("cut_cap"):
            self.warn("verdict line", f"the day's ${self._line['usd_day']:.2f} line for verdicts is reached "
                                      f"({self._line['source']}); READ events wait for the next day's")
        if kind not in BACKFILL_KINDS and day not in self._universe_told and isinstance(out.get("events"), Mapping):
            self._universe_told.add(day)
            self._receipted(ctx.store, "universe", "ok", {"day": day.isoformat(), "decision": kind,
                                                          **dict(out["events"])})
        return {"day": day.isoformat(), "decision": kind, "missing": missing, "stored": stored, "stalled": stalled}

    def _look(self, key: tuple[str, dt.date], missing: int, stored: int, gw: LaneGateway) -> bool:
        """Note what a decision's verdicts look like now; True (stalled) when some are missing, none was stored and
        the calls got no answer (refused, failed, the House paused, the day's line) rather than running out of time,
        or no call was made at all (every missing verdict is one this pass does not ask: PREREG-EVL-4's PM rows wait on
        the open decision's asks), so the same pass would only find them missing again: then neither the verdict task
        nor the pending decision asks again for VERDICT_BACKOFF."""
        cut_time = gw.counts.get("cut_deadline", 0) + gw.counts.get("cut_closed", 0)
        no_answer = (gw.counts.get("refused", 0) + gw.counts.get("failed", 0) + gw.counts.get("cut_paused", 0)
                     + gw.counts.get("cut_cap", 0))
        asked = gw.counts.get("asked", 0) + sum(n for k, n in gw.counts.items() if str(k).startswith("cut_"))
        stalled = missing > 0 and stored == 0 and cut_time == 0 and (no_answer > 0 or asked == 0)
        self._looks[key] = VerdictLook(self.now(), missing, stalled)
        return stalled

    @staticmethod
    def _stored_verdicts(st: S.Store) -> int:
        return int(st.db.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0])

    # -- recording --------------------------------------------------------------------------------------------------
    def _last_started(self, st: S.Store, job: str) -> dt.datetime | None:
        row = st.db.execute("SELECT max(started_at) FROM receipts WHERE job=?", (job,)).fetchone()
        return S.parse_iso(row[0]) if row and row[0] else None

    def _record(self, ctx: LaneContext, deadline: float) -> dict[str, Any]:
        """EDGAR's current feeds (8-K and 4) and the news, bounded and resumable; then the next session's verdicts.

        Every new feed entry is stored at once as `listed` (so the next poll stops at it), then fetched oldest first,
        8-Ks before Form 4s, while the bound lasts: a pass cut short leaves `listed` rows the next pass fetches. An
        unlisted filer's 8-K stays `listed`, as in league.events.run.record_pass."""
        st = ctx.store
        rid = st.start_receipt("record", now=ctx.now())
        try:
            out, new, cut = self._record_steps(ctx, deadline)
        except BaseException as exc:
            st.finish_receipt(rid, "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, now=ctx.now())
            raise
        st.finish_receipt(rid, "ok", out, now=ctx.now())
        return {"new": new, "cut": cut}

    def _record_steps(self, ctx: LaneContext, deadline: float) -> tuple[dict[str, Any], int, bool]:
        st = ctx.store
        now = ctx.now()
        out: dict[str, Any] = {}
        try:
            listed: set[str] | None = set(ctx.tickers)
        except Exception as exc:  # noqa: BLE001 - no tickers copy at all (an empty store, SEC down): 8-Ks wait, the rest goes on
            listed = None
            out["tickers"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        new = 0
        for form in E.FORMS:
            known = [r[0] for r in st.db.execute("SELECT accession FROM filings WHERE form=? ORDER BY accepted_at DESC "
                                                 "LIMIT 2000", (form,))]
            try:
                entries = E.poll_current(ctx.sec, form, known, prefer=listed)   # (co-registered: a listed filer's)
            except LaneDeadline:
                raise
            except Exception as exc:  # noqa: BLE001 - one feed's outage never stops the other or the news
                out[form] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
                continue
            with st.tx():   # listed at once, in one commit (record_filing with fetch=False only inserts)
                for entry in entries:
                    E.record_filing(st, ctx.sec, entry, source="current", now=ctx.now(), fetch=False)
            out[form] = {"new": len(entries), "fetched": 0, "failed": 0, "unlisted": 0}
        out["news"] = self._news(ctx, min(deadline, self._mono() + NEWS_BUDGET))
        new += int((out["news"] or {}).get("stored") or 0)
        cut = False
        # The listed filings, and those whose fetch FAILED (release 1019b's review: one transient SEC error lost the
        # filing's live decision, as nothing fetched it again before the next day's daily-index backfill), each tried
        # again FETCH_BACKOFF after its first failure, FETCH_TRIES tries in all (`_fetch_tries`, kept by this process);
        # new ones first. (A form whose feed failed this pass holds its error in `out`: its counts go beside it, the
        # second review's KeyError.)
        rows = st.db.execute("SELECT accession, form, cik, company, items, accepted_at, index_url, status FROM filings "
                             "WHERE (status='listed' OR status LIKE 'failed:%') AND source='current' AND received_at>=? "
                             "ORDER BY form='4', status!='listed', accepted_at, accession",
                             (S.iso(now - FETCH_WINDOW),)).fetchall()

        def bump(counts: dict[str, Any], key: str) -> None:
            counts[key] = int(counts.get(key) or 0) + 1

        for row in rows:
            counts = out.setdefault(str(row["form"]), {"new": 0, "fetched": 0, "failed": 0, "unlisted": 0})
            if row["form"] == "8-K" and (listed is None or row["cik"] not in listed):
                bump(counts, "unlisted" if listed is not None else "waiting")
                continue
            accession = str(row["accession"])
            again = str(row["status"]).startswith("failed")
            tries, first = self._fetch_tries.get(accession, (1 if again else 0, None))
            if again and tries >= FETCH_TRIES:
                continue    # (left to the daily-index backfill)
            if again and first is not None and now < first + FETCH_BACKOFF[tries - 1]:
                continue    # (its next try is not due yet: the tries-th after the first failure)
            if self.late(deadline):
                cut = True
                break
            self._fetch_tries[accession] = (tries + 1, first or now)    # (counted before it is tried: a raise counts)
            entry = {"form": row["form"], "cik": row["cik"], "accession": row["accession"], "company": row["company"],
                     "items": json.loads(row["items"] or "[]"), "accepted_at": S.parse_iso(row["accepted_at"]),
                     "index_url": row["index_url"]}
            status = E.record_filing(st, ctx.sec, entry, source="current", now=ctx.now(), fetch=True)
            if again:
                bump(counts, "retried")
            if status == "fetched":
                bump(counts, "fetched")
                new += 1
                self._fetch_tries.pop(accession, None)
            elif status.startswith("failed"):
                bump(counts, "failed")
        out["cut"] = cut
        if new:
            self._events_at = self.now()
        out["verdicts"] = self._verdict_step(ctx, deadline)
        return out, new, cut

    def _news(self, ctx: LaneContext, deadline: float) -> dict[str, Any]:
        """New Alpaca news since the newest stored (less 5 minutes), oldest first, page by page until `deadline`: a
        pass cut short has stored its pages, and the next goes on from the newest."""
        st = ctx.store
        gw = LaneGateway(ctx.gw.inner, self, deadline, cut=True)
        try:
            since = N.latest_created(st) or (ctx.now() - dt.timedelta(hours=2))
            return dict(N.record(st, gw, since - dt.timedelta(minutes=5), ctx.now(), now=ctx.now()))
        except LaneDeadline:
            return {"cut": True}
        except Exception as exc:  # noqa: BLE001 - the news failing never stops the filings
            return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}

    def _verdict_step(self, ctx: LaneContext, deadline: float) -> list[dict[str, Any]]:
        """The record pass's last step: today's verdicts with the time left, once its universe is fixed (07:30 ET):
        its open decision's until that is made, then its close decision's."""
        out: list[dict[str, Any]] = []
        now = ctx.now()
        today = now.astimezone(C.NY).date()
        session = C.session(ctx.store, today)
        if session is None or now < session.at(UNIVERSE_AT):
            return out
        latest = self._decide_receipts(ctx.store, now)
        for kind, decide_at in (("open", session.open_decide), ("close", session.close_decide)):
            if deadline - self._mono() < VERDICT_STEP_MIN:
                break
            if latest.get(f"decide-{kind}:{today.isoformat()}", (None,))[0] == "ok":
                continue
            if not self._verdicts_due((kind, today), now, [], fresh=True):
                continue
            # its reads stop at the pass's bound too (the eligibility it reads is kept as it is read)
            step = LaneGateway(ctx.gw.inner, self, deadline, cut=True)
            bounded = LaneContext(self, ctx.store, step, self._sec_for(deadline, True), self.now, deadline)
            try:
                out.append(self._verdicts(bounded, kind, today, R.live_run(decide_at, now)))
            except LaneDeadline:
                out.append({"decision": kind, "cut": True})
                break
            except Exception as exc:  # noqa: BLE001 - the record pass is the feeds': its verdict step never fails it
                # (Release 1019b's third review: an Alpaca outage in the eligibility it reads, or an empty asset list,
                # failed the whole record pass, and FAIL_BACKOFF then cut EDGAR's and the news' polling from every 2
                # minutes to every 10. `_verdicts` marks the decision's verdicts stalled, so they wait VERDICT_BACKOFF by
                # themselves; the pass goes on to the other decision and ends ok.)
                out.append({"decision": kind, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
                self.warn("record pass's verdict step", exc)
            finally:
                ctx.gw.counts.update(step.counts)
        return out

    # -- nightly ----------------------------------------------------------------------------------------------------
    def _nightly(self, st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None,
                 soon: list[dt.datetime]) -> Task | None:
        evening = _wall(today, SCORE_AT)
        if session is not None:
            close_after = session.close_at + EQUITY_AFTER
            if st.meta(SC.equity_key(today)) is None:
                if now < close_after:
                    soon.append(close_after)
                elif self._retry_ok("equity", now, EQUITY_RETRY, soon) and not self._quiet("equity", now, soon):
                    return Task("equity", self._equity, None)
        # THE NIGHT IS A SESSION'S, NOT A CALENDAR DAY'S (release 1019f): today's session from 20:30 ET, else the session
        # before today. Its score is made when an `ok` score receipt started at or after its 20:30 ET (a later pass
        # settles everything an earlier one would), its screen when a nightly `screen` receipt did (the screen after the
        # open writes `screen-open`, never this one). A score that ran past midnight ET, or a House down that evening,
        # finishes that session's score, then its screen and its report, the next day.
        night = self._night(st, now, today, session, soon)
        if night is not None:
            since = _wall(night, SCORE_AT)
            if not self._receipt_since(st, "score", since, status="ok"):
                if not self._quiet("score", now, soon):
                    return Task("score", lambda ctx, deadline: self._score(ctx, deadline, night), SCORE_BUDGET)
                return None
            if not self._receipt_since(st, "screen", since):
                if not self._quiet("screen", now, soon) and self._clear_of_decision(st, now, soon):
                    return Task("screen", lambda ctx, deadline: self._screen(ctx, deadline, night), None)
                return None
            if night != today and not (st.root / "reports" / f"{night.isoformat()}.txt").exists() and \
                    not self._quiet("report", now, soon):
                return Task("report", lambda ctx, deadline: self._report(ctx, deadline, night), None)
        report_at = evening if session is not None else _wall(today, REPORT_AT)
        if now < report_at:
            soon.append(report_at)
        elif (session is None or self._receipt_since(st, "screen", evening)) and \
                not (st.root / "reports" / f"{today.isoformat()}.txt").exists() and \
                not self._quiet("report", now, soon):
            return Task("report", self._report, None)
        if self.births_on and session is not None:
            births_at = _wall(today, BIRTHS_AT)
            if now < births_at:
                soon.append(births_at)
            elif (st.root / "reports" / f"{today.isoformat()}.txt").exists() and \
                    not self._receipt_since(st, "births", births_at) and not self._quiet("births", now, soon):
                return Task("births", self._births, BIRTHS_BUDGET)
        if self.births_on:
            # THE ONE RE-RUN OF AN EMPTY NIGHT (A95; league/events/births.py `rerun_due`): a night whose births receipt
            # accepted and registered none, written by an older reading of the grammar and prompt than the running one,
            # runs once more, before 12:55Z of the session day after it (a weekend's Friday night until Monday's)
            from . import births as BI

            try:
                again = BI.rerun_due(st, now)
            except Exception as exc:  # noqa: BLE001 - a read error here never stops the plan's later tasks
                self.warn("births re-run", exc)
                again = None
            if again is not None and (st.root / "reports" / f"{again['night']}.txt").exists() and \
                    not self._quiet("births", now, soon):
                night_of = dt.date.fromisoformat(str(again["night"]))
                return Task("births", lambda ctx, deadline: self._births(ctx, deadline, night_of, again),
                            BIRTHS_BUDGET)
        return None

    @staticmethod
    def _night(st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None,
               soon: list[dt.datetime]) -> dt.date | None:
        """The session whose nightly score and screen are due (release 1019f): today's from its 20:30 ET, else the last
        session before today (None when the calendar holds none)."""
        if session is not None:
            evening = _wall(today, SCORE_AT)
            if now >= evening:
                return today
            soon.append(evening)
        before = C.previous(st, today, 1)
        return before[-1].day if before else None

    def _clear_of_decision(self, st: S.Store, now: dt.datetime, soon: list[dt.datetime]) -> bool:
        """Whether a screen (CPU only, unbounded) may start now: not within SCREEN_CLEAR of the lane's next decision."""
        nxt = self._next_decision(st, now)
        if nxt is not None and nxt - now < SCREEN_CLEAR:
            soon.append(nxt)
            return False
        return True

    def _retry_ok(self, what: str, now: dt.datetime, every: dt.timedelta, soon: list[dt.datetime]) -> bool:
        tried = self._attempts.get(what)
        if tried is not None and now < tried + every:
            soon.append(tried + every)
            return False
        return True

    @staticmethod
    def _receipt_since(st: S.Store, job: str, since: dt.datetime, *, status: str | None = None) -> bool:
        sql = "SELECT 1 FROM receipts WHERE job=? AND started_at>=?" + (" AND status=?" if status else "") + " LIMIT 1"
        args: tuple[Any, ...] = (job, S.iso(since)) + ((status,) if status else ())
        return st.db.execute(sql, args).fetchone() is not None

    def _receipted(self, st: S.Store, job: str, status: str, summary: Mapping[str, Any]) -> None:
        rid = st.start_receipt(job, now=self.now())
        st.finish_receipt(rid, status, summary, now=self.now())

    def _equity(self, ctx: LaneContext, deadline: float | None) -> dict[str, Any]:
        self._attempts["equity"] = ctx.now()
        out = SC.record_equity(ctx.store, ctx.gw, now=ctx.now())
        self._receipted(ctx.store, "equity", "ok", {k: v for k, v in out.items() if k != "equity"})
        return {k: v for k, v in out.items() if k != "equity"}

    def _score(self, ctx: LaneContext, deadline: float, night: dt.date | None = None) -> dict[str, Any]:
        """The score job (league.events.score.settle), resumable: each due intent is tried once a night, in order,
        while the bound lasts; the night's pass is `ok` once every one has been tried. The night is the SESSION's
        (`night`, `_night`; release 1019f): a pass that runs past midnight ET goes on with the same night, each intent
        still tried once, and its receipt's `day` is that session.
        RELEASE 1019i, THE BATCHED SCORE (PREREG-EVL-8's harness plan H1; league/events/score.py's docstring), while
        league/config.json `events.score_batch` is not false (`score.batch_on`): the seating versions and their controls
        first (`score.order_due`), and before each `PREFETCH_WINDOW` intents of the pass the daily bars of their
        symbols and both benchmarks in one read (`score.prefetch`, stopped at the bound), so each settles with no bar
        request of its own (`settle_one(prefetched=...)`: a cache that lives only for the pass; `bars` receives exactly
        the rows release 1019h's two fetches an intent would have written); on the parity night (`score.parity_due`) a
        5% sample of each prefetch's intents is settled twice in memory, before any of them is written, by the batched
        and the per-intent path (`score.parity_window`), and only its equality flags kept (`score_parity`). A FLAG 0
        FAILS CLOSED: it sets the parity latch (`score.latched`), and from that intent on every pass settles by the
        per-intent path until the captain clears it (`evl_score_parity` stands meanwhile). False: release 1019h's
        per-intent path. The receipt carries the pass's requests by kind, its seconds, the flags and the latch (the
        daily report's settle-pace line)."""
        st, now = ctx.store, ctx.now()
        began = self._mono()
        day = night or now.astimezone(C.NY).date()
        for other in [d for d in self._score_seen if d != day]:
            self._score_seen.pop(other)
        seen = self._score_seen.setdefault(day, set())
        counts = {"due": 0, "settled": 0, "skipped": 0, "waiting": 0, "errors": 0}
        errors: list[str] = []
        complete = True
        batch = SC.batch_on(self.settings) and SC.latched(st) is None
        gw = SC.Counted(ctx.gw)
        pending = [i for i in SC.due(st, now)
                   if (str(i["program"]), int(i["version"]), str(i["event"])) not in seen]
        if batch:
            pending = SC.order_due(pending)
        check = batch and SC.parity_due(st, day, self.settings)
        flags = {"sampled": 0, "checked": 0, "equal": 0}
        waits: dict[tuple[str, int, str], str] = {}
        pre: SC.Prefetch | None = None
        fetched = {"requests": 0, "rows": 0, "windows": 0, "done": True, "served": 0}
        on = batch      # (the batched path until the parity latch, if it is set in this pass)
        for n, intent in enumerate(pending):
            key = (str(intent["program"]), int(intent["version"]), str(intent["event"]))
            if self.late(deadline):
                complete = False
                break
            if on and n % PREFETCH_WINDOW == 0:
                window = pending[n:n + PREFETCH_WINDOW]
                pre = SC.prefetch(st, gw, window, now=now, late=lambda: self.late(deadline))
                fetched["requests"] += pre.requests
                fetched["rows"] += pre.rows
                fetched["windows"] += 1
                fetched["done"] = fetched["done"] and pre.done
                if check and pre.symbols:
                    got = SC.parity_window(st, gw, window, pre, day, now=now, late=lambda: self.late(deadline))
                    for k in flags:
                        flags[k] += int(got[k])
                    waits.update(got["waits"])
                if SC.latched(st) is not None:
                    on, pre = False, None       # (a flag 0: the rest of the pass by the per-intent path)
            seen.add(key)
            counts["due"] += 1
            try:
                use = pre if on and pre is not None and pre.symbols else None    # (nothing prefetched: nothing to skip)
                if key in waits:        # (a sampled intent the parity check saw wait: not read again this pass)
                    status = f"waiting:{waits[key]}"
                else:
                    status = SC.settle_one(st, gw, intent, now=now, **({"prefetched": use} if use is not None else {}))
            except Exception as exc:  # noqa: BLE001 - one intent's failure is its own (as score.settle)
                counts["errors"] += 1
                errors.append(f"{key[0]}:{key[2]}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            kind = status.split(":")[0]
            counts[kind] = counts.get(kind, 0) + 1
            if kind == "settled" and use is not None:
                fetched["served"] += int(key in use.hits)
        summary = {"day": day.isoformat(), "complete": complete, **counts, "errors_seen": errors[:5],
                   "batched": batch, "requests": dict(gw.counts), "seconds": round(self._mono() - began, 3)}
        if batch:
            summary["prefetch"] = fetched
        if check:
            summary["parity"] = flags
        held = SC.latched(st)
        if held is not None:
            summary["latched"] = True
            if batch:
                self.warn("score parity", f"the batched score's parity check found a difference ({held.get('program')} "
                                          f"version {held.get('version')}, the night of {held.get('night')}): the "
                                          "per-intent path settles every intent until the captain clears the latch")
        self._receipted(st, "score", "ok" if complete else "partial", summary)
        if errors:
            self.warn("score", f"{len(errors)} intents could not be settled this pass, the first: {errors[0]}")
        return summary | {"_status": "ok" if complete else "partial"}

    def _screen(self, ctx: LaneContext, deadline: float | None, night: dt.date | None = None) -> dict[str, Any]:
        """The screen (league.events.screen.run: the looks, and the band moves a look makes in its own transaction:
        Probe, retired), then PREREG-EVL-3's review of the real fills the House's book wrote back
        (league.events.bands.review: demotion to learning, Sized), WHATEVER THE SCREEN DID (release 1019b's review: a
        failing look stopped every program's demotion and Sized). A program whose looks failed, or a review that failed,
        is a warning and the screen's receipt says so (`partial`); it runs again next night. The screen is as of the
        night's SESSION (`night`, `_night`; release 1019f), whenever it runs; its receipt keeps the final horizons it
        read (`horizons`, the screen after the open compares them) and why each look waits (`waits`)."""
        now = ctx.now()
        day = night or now.astimezone(C.NY).date()
        status, summary = self._looks_pass(ctx.store, day, now, "screen", None, self._horizons(ctx.store, day, now))
        summary["run"] = "night"
        try:
            moved = BA.review(ctx.store, now=now)
        except Exception as exc:  # noqa: BLE001 - the looks are written; the review is read again next night
            status = "partial"
            summary["review"] = f"failed: {type(exc).__name__}: {str(exc)[:160]}"
            self.warn("bands", exc)
        else:
            summary["review"] = [{k: c.get(k) for k in ("program", "version", "band")} for c in moved]
        self._receipted(ctx.store, "screen", status, summary)
        try:   # THE DONE READER (goal V2, docs/goals/DONE-RULE-EVL-2.md): after the band review, read-only but done.json
            done = DN.receipt(DN.run(ctx.store, now=now))
        except Exception as exc:  # noqa: BLE001 - the screen stands; the reader is read again next night
            self.warn("done", exc)
        else:
            self._receipted(ctx.store, DN.JOB, "ok", done)
        return summary | {"_status": status}

    def _births(self, ctx: LaneContext, deadline: float | None, night: dt.date | None = None,
                rerun: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """R3's births job of the night (league/events/births.py `night`, its own receipt `births`): its Claude call goes
        through the lane's gateway (refused while the House is paused or over the day's line, and counted), and is made
        only when its worst case fits under what is left of the lane's line today (`line_left`, release 1019e's review:
        the births call is inside the lane's line, as every verdict, never beside it), as well as under the night's own
        $0.25 cap. Its stored cost counts in the lane's line from then on (`_spend_today`), a lost call's too (release
        1019h's fix round: births.py `LOST`). A night that ends anything but `ok` warns: `unanswered` with the call's
        status, seconds, cost and why (a call lost, cut or refused, or no answer), `partial` with its registration. The night is today's, or
        (`night`, `rerun`: A95's one re-run of an empty night, `births.rerun_due`) the earlier night it runs again."""
        from . import births as BI

        now = ctx.now()
        out = BI.night(ctx.store, ctx.gw, today=night or now.astimezone(C.NY).date(), now=ctx.now,
                       line_left=self.line_left(), rerun=rerun)
        status = str(out.pop("_status", "ok"))
        if status != "ok":
            call = out.get("call") or {}
            told = out.get("error") or out.get("registration") or \
                f"the architect's call ended {call.get('status')} after {call.get('seconds')} s at " \
                f"${float(call.get('usd') or 0):.4f}: {call.get('why') or ''}"
            self.warn("births", f"the births job of {out.get('night')} ended {status}: {told}"[:300])
        brief = {k: v for k, v in out.items() if isinstance(v, (int, float, str, bool)) or v is None}
        brief["accepted"] = len(out.get("accepted") or [])
        brief["proposed"] = int(out.get("proposed") or 0)
        brief["rerun"] = rerun is not None
        return brief | {"_status": status}

    def _screen_open_due(self, st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None,
                         soon: list[dt.datetime]) -> Task | None:
        """THE SCREEN AFTER THE OPEN (release 1019f; `SCREEN_OPEN_AT`'s comment): due from SCREEN_OPEN_AT of a session
        whose open decision is made (its receipt `ok` or `pending`) until SCREEN_CLEAR before its close decision, when
        the final horizons of the seating versions (`_horizons`, read at most every SCREEN_OPEN_EVERY) differ from those
        the last screen receipt kept, nightly or not (`_last_horizons`): the same horizons are never screened twice.
        PLANNING CHANGES NO STATE WHEN IT RETURNS THE TASK (fix/screen-after-open's check: `run` plans again after every
        task and drops what that plan returns): the 10-minute clock (`_open_checked`) is set here only when the
        horizons are unchanged, and by `_screen_open` when the task runs, so a screen that falls due in the dropped plan
        is returned again by the next turn's."""
        if session is None:
            return None
        start, until = _wall(today, SCREEN_OPEN_AT), session.close_decide - SCREEN_CLEAR
        if now < start:
            soon.append(start)
            return None
        if now >= until or not self._open_made(st, today):
            return None
        if self._open_checked is not None and now < self._open_checked + SCREEN_OPEN_EVERY:
            soon.append(self._open_checked + SCREEN_OPEN_EVERY)
            return None
        if self._quiet(SCREEN_OPEN_JOB, now, soon) or not self._clear_of_decision(st, now, soon):
            return None
        horizons = self._horizons(st, today, now)
        if horizons == self._last_horizons(st):
            self._open_checked = now     # (unchanged: read again in SCREEN_OPEN_EVERY)
            soon.append(now + SCREEN_OPEN_EVERY)
            return None
        return Task(SCREEN_OPEN_JOB, lambda ctx, deadline: self._screen_open(ctx, deadline, today, horizons), None)

    def _screen_open(self, ctx: LaneContext, deadline: float | None, day: dt.date,
                     horizons: Mapping[str, Any]) -> dict[str, Any]:
        """The screen's looks of the seating versions as of session `day` (league.events.screen.run, its own `final_until`
        and every rule as the nightly screen reads them), receipted `screen-open` with the horizons that made it due.
        No band review (the real fills' demotion and Sized stay nightly). The 10-minute clock starts here, when it runs."""
        now = ctx.now()
        self._open_checked = now
        status, summary = self._looks_pass(ctx.store, day, now, SCREEN_OPEN_JOB, self._seating(), dict(horizons))
        summary["run"] = "open"
        self._receipted(ctx.store, SCREEN_OPEN_JOB, status, summary)
        return summary | {"_status": status}

    def _looks_pass(self, st: S.Store, day: dt.date, now: dt.datetime, task: str,
                    programs: list[tuple[str, int]] | None, horizons: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        """One run of the screen's looks as of session `day` (every program the store holds when `programs` is None),
        and its receipt's summary: the counts, the looks written (`looks`), why each look waits (`waits`: program,
        version, k, why) and the final horizons read before it (`horizons`)."""
        try:
            out = SN.run(st, day, programs=programs, now=now)
        except Exception as exc:  # noqa: BLE001 - the caller's receipt says so
            out = {"written": [], "waiting": [], "errors": [{"error": f"{type(exc).__name__}: {str(exc)[:200]}"}]}
        written, waiting = list(out.get("written") or []), list(out.get("waiting") or [])
        summary: dict[str, Any] = {
            "day": day.isoformat(), "written": len(written), "waiting": len(waiting),
            "looks": [{k: w.get(k) for k in ("program", "version", "k", "held", "passed", "band")} for w in written],
            "waits": [{"program": w.get("program"), "version": w.get("version"), "k": w.get("k"),
                       "why": str(w.get("why") or "")[:WHY_CHARS]} for w in waiting[:WAITS_KEPT]],
            "horizons": dict(horizons)}
        status = "ok"
        if out.get("errors"):
            status = "partial"
            summary["errors"] = list(out["errors"])[:5]
            self.warn(task, f"{len(out['errors'])} program(s) could not be screened, the first: {out['errors'][0]}")
        return status, summary

    @staticmethod
    def _seating() -> list[tuple[str, int]]:
        """(program, version) of every version that may seat (league/events/programs.py `SEATING`, read at each call)."""
        return [(p.id, int(p.version)) for p in P.SEATING if p.can_seat]

    def _horizons(self, st: S.Store, day: dt.date, now: dt.datetime) -> dict[str, str | None]:
        """{program key: the last close the judge holds final for it (league/events/screen.py `final_until` as of
        session `day` at `now`), ISO, or None} for every seating version; a version whose horizon cannot be read is
        `error: <type>` (a stable mark, so one that keeps failing is not screened again for it)."""
        out: dict[str, str | None] = {}
        for program, version in self._seating():
            key = SN.program_key(program, version)
            try:
                until = SN.final_until(st, program, version, day, now)[0]
            except Exception as exc:  # noqa: BLE001 - the screen itself says why that program waits
                out[key] = f"error: {type(exc).__name__}"
                continue
            out[key] = None if until is None else until.isoformat()
        return out

    @staticmethod
    def _last_horizons(st: S.Store) -> dict[str, Any] | None:
        """The final horizons the latest finished screen receipt (nightly or after the open) kept, or None (none kept)."""
        row = st.db.execute("SELECT summary FROM receipts WHERE job IN (?, ?) AND finished_at IS NOT NULL ORDER BY id DESC "
                            "LIMIT 1", SCREEN_JOBS).fetchone()
        try:
            body = json.loads(row[0] or "{}") if row is not None else None
        except (TypeError, ValueError):
            return None
        horizons = body.get("horizons") if isinstance(body, dict) else None
        return horizons if isinstance(horizons, dict) else None

    @staticmethod
    def _open_made(st: S.Store, day: dt.date) -> bool:
        """Whether session `day`'s open decision is made (a receipt finished `ok` or `pending`)."""
        return st.db.execute("SELECT 1 FROM receipts WHERE job=? AND status IN ('ok', 'pending') LIMIT 1",
                             (f"decide-open:{day.isoformat()}",)).fetchone() is not None

    def _report(self, ctx: LaneContext, deadline: float | None, day: dt.date | None = None) -> dict[str, Any]:
        """The daily one-screen report into `<root>/reports/<day>.txt` and `.json`, as the CLI's `report` writes it: of
        today, or of the night's session when its nightly jobs finished after midnight ET (`day`, release 1019f)."""
        now = ctx.now()
        day = day or now.astimezone(C.NY).date()
        rep = RP.build(ctx.store, day, now=now)
        folder = ctx.store.root / "reports"
        folder.mkdir(exist_ok=True)
        (folder / f"{day.isoformat()}.json").write_text(json.dumps(rep, default=str, sort_keys=True), encoding="utf-8")
        (folder / f"{day.isoformat()}.txt").write_text(RP.render(rep) + "\n", encoding="utf-8")
        self._receipted(ctx.store, "report", "ok", {"day": day.isoformat()})
        return {"day": day.isoformat()}

    # -- the PX recorders (release 1019i) ---------------------------------------------------------------------------
    def _px_due(self, st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None,
                soon: list[dt.datetime]) -> Task | None:
        """THE PX RECORDERS' TASK, the plan's last (`PX_BUDGET`'s comment): None while `events.px_data` is off, inside
        the live close decision's lead, within `PX_CLEAR` of the next decision, within `PX_EVERY` of the last PX run, or
        when no recorder is due (`_px_job`)."""
        if not self.px_on:
            return None
        hold = self._hold_from(st, now)
        if self._lead(st, now) is not None or (hold is not None and hold - now < PX_CLEAR):
            return None
        nxt = self._next_decision(st, now)
        if nxt is not None and nxt - now < PX_CLEAR:
            soon.append(nxt + dt.timedelta(seconds=DECISION_MARGIN))
            return None
        if self._px_last is not None and now < self._px_last + PX_EVERY:
            soon.append(self._px_last + PX_EVERY)
            return None
        if self._px_disk is not None and now < self._px_disk + FAIL_BACKOFF:     # (no room: looked at again later)
            soon.append(self._px_disk + FAIL_BACKOFF)
            return None
        job = self._px_job(st, now, today, session, soon)
        if job is None:
            return None
        name, fn = job
        return Task(f"px-{name}", lambda ctx, deadline: self._px(ctx, deadline, name, fn), PX_BUDGET, cut=True)

    def _px_job(self, st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None,
                soon: list[dt.datetime]) -> tuple[str, Callable[..., dict[str, Any]]] | None:
        """Which recorder is due now (the windows of `PX_BUDGET`'s comment), in order: today's universe, FLAGGED, the
        premarket and 15:30 marks, the night's bars, the backfill, the operating cache; each once done is not due again
        (px.sqlite `px_meta`), and one that failed waits FAIL_BACKOFF."""
        path = PXS.path_of(self.root)
        px = _PxRead(path) if path.exists() else None    # (read-only: the plan never writes px.sqlite)
        try:
            meta = (lambda key: px.meta(key)) if px is not None else (lambda key: None)
            t = _ny_time(now)
            backfilled = meta("px:backfill:done") is not None
            if session is not None and backfilled:
                d = today.isoformat()
                if PX_UNIVERSE_AT <= t < PX_FLAGS_AT and meta(f"px:universe:{d}") is None and \
                        not self._quiet("px-universe", now, soon):
                    return "universe", lambda ctx, px_, gw, run, dl: self._px_universe(ctx, px_, run, dl, today)
                have = px is not None and px.has_universe(today)
                if have and t >= PX_FLAGS_AT and now < session.close_at - PX_FLAGS_BEFORE_CLOSE and \
                        meta(f"px:flags:{d}") is None and not self._quiet("px-flags", now, soon):
                    return "flags", lambda ctx, px_, gw, run, dl: self._px_flags(ctx, px_, gw, run, today)
                if have and t >= PX_PM_AT and meta(f"px:pm:{d}") is None and \
                        not self._quiet("px-pm", now, soon):
                    return "pm", lambda ctx, px_, gw, run, dl: self._px_minutes(ctx, px_, gw, run, session, "pm")
                if have and now >= session.close_at + PX_1530_AFTER and meta(f"px:px1530:{d}") is None and \
                        not self._quiet("px-px1530", now, soon):
                    return "px1530", lambda ctx, px_, gw, run, dl: self._px_minutes(ctx, px_, gw, run, session, "px1530")
            night = self._px_night(st, now, today, session)
            if night is not None and backfilled and meta(f"px:bars:{night.isoformat()}") is None and \
                    not self._quiet("px-daily", now, soon):
                return "daily", lambda ctx, px_, gw, run, dl: self._px_daily(ctx, px_, gw, run, night)
            quiet_hours = session is None or _night(t)
            if quiet_hours and not backfilled and not self._quiet("px-backfill", now, soon):
                return "backfill", lambda ctx, px_, gw, run, dl: self._px_backfill(ctx, px_, gw, run, dl, today)
            if quiet_hours and backfilled and meta(f"px:ops:{today.isoformat()}") is None and \
                    not self._quiet("px-ops", now, soon):
                return "ops", lambda ctx, px_, gw, run, dl: self._px_ops(ctx, px_, run, dl, today)
            return None
        finally:
            if px is not None:
                px.close()

    def _px_night(self, st: S.Store, now: dt.datetime, today: dt.date, session: C.Session | None) -> dt.date | None:
        """The session whose nightly bars are due: today's once its night's score has run (an `ok` score receipt since
        its 20:30 ET), else the session before today once its own did."""
        nights = ([today] if session is not None else []) + [s.day for s in C.previous(st, today, 1)]
        for night in nights:
            if self._receipt_since(st, "score", _wall(night, SCORE_AT), status="ok"):
                return night
        return None

    def _px(self, ctx: LaneContext, deadline: float | None, name: str, fn: Callable[..., dict[str, Any]]) -> dict[str, Any]:
        """ONE PX RECORDER RUN, ISOLATED: px.sqlite opened for it, a run id kept (`px_runs`), its reads through
        `PX.PxGateway` (the SIP bars route, the bucket after the lane, cut at the bound), its SEC reads through the
        lane's bounded reader. Never raises: a cut ends it `cut` (the next run goes on from what it stored), any failure
        is `failed`, a warning at most once an hour, and that recorder waits FAIL_BACKOFF; nothing else waits on it.
        THE STORE'S ROOM (release 1019i's review; league/events/pxstore.py `room`: px.sqlite under its 2 GB line and
        the state disk above the PX floor) is checked BEFORE THE RUN, which without room is `disk` and opens nothing
        (no row written, px.sqlite not even made), and before every request of it (`PX.PxRoom`: the run ends `disk`
        before its next page); every PX run then waits FAIL_BACKOFF, a warning says why at most once an hour, the last
        check is in lane.json (`px_store`), and league/ops/evl_health.py raises `evl_px_store`."""
        now = ctx.now()
        self._px_last = now
        room = PXS.room(self.root)
        self._px_room = {k: room[k] for k in ("size_bytes", "free_bytes", "ok", "why")} | {"at": S.iso(now)}
        if not room["ok"]:
            self._px_disk = now
            self.warn("px store", f"the PX recorders write nothing: {room['why']}")
            return {"why": room["why"], "size_bytes": room["size_bytes"], "free_bytes": room["free_bytes"],
                    "requests": 0, "_status": "disk"}
        gw = PX.PxGateway(self.gateway(), self._bucket or PX.TokenBucket(clock=self._mono, sleep=self._sleep),
                          until=deadline, late=lambda: self.late(deadline), room=lambda: PXS.room(self.root)["why"])
        status, out = "ok", {}
        px = None
        run = None
        try:
            px = PXS.PxStore(self.root)
            run = px.start_run(name, now=now, free_bytes=room["free_bytes"])
            out = dict(fn(ctx, px, gw, run, deadline) or {})
            status = str(out.pop("_status", "ok"))
        except PX.PxRoom as exc:
            status, out = "disk", {"why": str(exc)[:200]}
            self._px_disk = self.now()
            self.warn("px store", f"the PX recorders stop: {exc}")
        except (PX.PxCut, LaneDeadline) as exc:
            status, out = "cut", {"cut": str(exc)[:200]}
        except Exception as exc:  # noqa: BLE001 - a recorder's failure is its own
            status, out = "failed", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            self._failed[f"px-{name}"] = self.now()
            self.warn(f"px {name}", exc)
        finally:
            if px is not None:
                try:
                    if run is not None:
                        px.finish_run(run, status, now=self.now(), requests=gw.requests,
                                      rows=int(out.get("rows") or out.get("written") or 0), summary=out)
                except Exception:  # noqa: BLE001 - the run's record is a report
                    pass
                px.close()
        brief = {k: v for k, v in out.items() if isinstance(v, (int, float, str, bool)) or v is None}
        return {**brief, "requests": gw.requests, "_status": status}

    def _px_late(self, deadline: float | None) -> bool:
        """A PX recorder's `late`: the bound passed, or the store has no room (`PXS.room`: its next write waits)."""
        return self.late(deadline) or not PXS.room(self.root)["ok"]

    def _px_listed(self, ctx: LaneContext, day: dt.date | None = None) -> dict[str, list[str]] | None:
        """{cik: listed tickers} from the lane's ticker copy for `day` (the latest with None) and the live asset list;
        None when the lane holds no ticker copy yet (the recorder waits for the lane's own snapshot)."""
        if not ctx._snapshots():
            return None
        return PX.listed_tickers(ctx.tickers_for(day), ctx.assets(True))

    def _px_backfill(self, ctx: LaneContext, px: PXS.PxStore, gw: Any, run: str, deadline: float | None,
                     today: dt.date) -> dict[str, Any]:
        listed = self._px_listed(ctx)
        if listed is None:
            return {"why": "no ticker copy yet", "_status": "waiting"}
        out = PX.backfill(px, gw, {t for ts in listed.values() for t in ts}, ctx.store, today, now=ctx.now(), run=run,
                          late=lambda: self._px_late(deadline))
        return out | {"_status": "ok" if out.get("done") else "partial"}

    def _px_daily(self, ctx: LaneContext, px: PXS.PxStore, gw: Any, run: str, night: dt.date) -> dict[str, Any]:
        listed = self._px_listed(ctx)
        if listed is None:
            return {"why": "no ticker copy yet", "_status": "waiting"}
        return PX.daily(px, gw, {t for ts in listed.values() for t in ts}, ctx.store, night, now=ctx.now(), run=run)

    def _px_ops(self, ctx: LaneContext, px: PXS.PxStore, run: str, deadline: float | None,
                today: dt.date) -> dict[str, Any]:
        listed = self._px_listed(ctx)
        if listed is None:
            return {"why": "no ticker copy yet", "_status": "waiting"}
        out = PX.operating_fill(px, listed, today, ctx.sec, now=ctx.now(), late=lambda: self._px_late(deadline))
        if not out["left"]:
            px.set_meta(f"px:ops:{today.isoformat()}", S.iso(ctx.now()))
        return out | {"_status": "ok" if not out["left"] else "partial"}

    def _px_universe(self, ctx: LaneContext, px: PXS.PxStore, run: str, deadline: float | None,
                     day: dt.date) -> dict[str, Any]:
        if not ctx._snapshots():
            return {"why": "no ticker copy yet", "_status": "waiting"}
        out = PX.universe(px, ctx.store, day, tickers=ctx.tickers_for(day), assets=ctx.assets(True), now=ctx.now(),
                          run=run, late=lambda: self._px_late(deadline))
        if "why" in out:
            return out | {"_status": "waiting"}
        if not out["left"]:
            px.set_meta(f"px:universe:{day.isoformat()}", S.iso(ctx.now()))
        return out | {"_status": "ok" if not out["left"] else "partial"}

    def _px_flags(self, ctx: LaneContext, px: PXS.PxStore, gw: Any, run: str, day: dt.date) -> dict[str, Any]:
        out = PX.flags(px, gw, PX.names(px, day), ctx.store, day, now=ctx.now(), run=run)
        px.set_meta(f"px:flags:{day.isoformat()}", S.iso(ctx.now()))
        return out

    def _px_minutes(self, ctx: LaneContext, px: PXS.PxStore, gw: Any, run: str, session: C.Session,
                    label: str) -> dict[str, Any]:
        symbols = PX.pm_names(px, session.day) if label == "pm" else PX.names(px, session.day)
        out = PX.minutes(px, gw, symbols, session, label, now=ctx.now(), run=run)
        if out.get("waiting"):
            return out | {"_status": "waiting"}
        px.set_meta(f"px:{label}:{session.day.isoformat()}", S.iso(ctx.now()))
        return out

    # -- the ticker snapshot ----------------------------------------------------------------------------------------
    def _tickers_due(self, st: S.Store, now: dt.datetime, today: dt.date, soon: list[dt.datetime]) -> bool:
        at = _wall(today, TICKERS_AT)
        if today.weekday() >= 5:
            soon.append(_wall(today + dt.timedelta(days=7 - today.weekday()), TICKERS_AT))
            return False
        if now < at:
            soon.append(at)
            return False
        if st.db.execute("SELECT 1 FROM meta WHERE key>=? AND key<? LIMIT 1",
                         (f"tickers@{S.iso(at)}", "tickers@~")).fetchone() is not None:
            return False
        return self._retry_ok("tickers", now, TICKERS_RETRY, soon)

    def _snapshot(self, ctx: LaneContext, deadline: float | None) -> dict[str, Any]:
        self._attempts["tickers"] = ctx.now()
        sha = ctx.snapshot_tickers()
        self._receipted(ctx.store, "tickers", "ok", {"sha": sha})
        return {"sha": sha}

    # -- the backfill -----------------------------------------------------------------------------------------------
    def _backfill_due(self, st: S.Store, now: dt.datetime, today: dt.date, soon: list[dt.datetime]) -> dt.date | None:
        start = P.registered().astimezone(C.NY).date()
        day, days = today, []
        while len(days) < BACKFILL_WEEKDAYS:
            day -= dt.timedelta(days=1)
            if day.weekday() < 5:
                days.append(day)
        for day in sorted(days):
            if day < start or st.meta(f"evl:backfill:{day.isoformat()}") == "done":
                continue
            at = _wall(day + dt.timedelta(days=1), BACKFILL_AT)
            if now < at:
                soon.append(at)
                continue
            wait = self._backfill_wait.get(day)
            if wait is not None and now < wait:   # only failed filings left, their next try not due: a later day goes on
                soon.append(wait)
                continue
            if self._retry_ok(f"backfill:{day.isoformat()}", now, BACKFILL_RETRY, soon):
                return day
        return None

    def _backfill(self, ctx: LaneContext, day: dt.date, deadline: float) -> dict[str, Any]:
        """Every 8-K (of a listed filer) and Form 4 in EDGAR's daily index of `day` that the store has not fetched,
        fetched now (league.events.run.backfill, bounded and resumable); the sessions they enter are decided again."""
        st = ctx.store
        if day not in self._index_rows:
            try:
                self._index_rows[day] = E.parse_daily_index(ctx.sec(E.daily_index_url(day)), E.FORMS)
            except G.GatewayError as exc:
                holiday = SEC_HOLIDAYS.get(day)
                if holiday is not None:   # EDGAR was closed: no index, ever (SEC answers 403 or 503, whatever the status)
                    st.set_meta(f"evl:backfill:{day.isoformat()}", "done")
                    summary = {"day": day.isoformat(), "complete": True, "why": SEC_HOLIDAY_WHY, "holiday": holiday,
                               "status": getattr(exc, "status", None)}
                    self._receipted(st, "backfill", "ok", summary)
                    return summary | {"_status": "ok"}
                # not published yet: tried again within the hour, said in the receipt
                self._attempts[f"backfill:{day.isoformat()}"] = ctx.now()
                self._receipted(st, "backfill", "waiting", {"day": day.isoformat(), "why": str(exc)[:120]})
                return {"day": day.isoformat(), "waiting": str(exc)[:120], "_status": "waiting"}
        rows = self._index_rows[day]
        seen = self._backfill_seen.setdefault(day, set())
        failed = self._backfill_failed.setdefault(day, {})
        now = ctx.now()
        listed = set(ctx.tickers)
        # ONE FILING, ONE ROW EACH FILER (A82): EDGAR's daily index lists a filing once per filer, so a Form 4 stands
        # under its issuer and its reporting owner and an 8-K under each co-registrant (Oct 19, 2026: 1,189 rows, 665
        # filings). The backfill goes filing by filing and is complete when every filing is seen; an 8-K is a listed
        # filer's when any of its filers is listed, under that filer's CIK (a Form 4's issuer is read from its document).
        filings: dict[str, dict[str, Any]] = {}
        for row in rows:
            first = filings.setdefault(row["accession"], row)
            if row["form"] == "8-K" and first["cik"] not in listed and row["cik"] in listed:
                filings[row["accession"]] = row
        # A FAILED FETCH IS NOT SEEN (release 1019f): a filing whose fetch failed is tried again FETCH_BACKOFF after its
        # first failure, FETCH_TRIES tries in all, across passes, as the record pass tries a live one (its own count:
        # `_backfill_failed`, kept by this process); the day is done only when every filing is fetched, known or
        # unlisted, or past its last try: those are named in the receipt (`unfetched`: accession, form, tries, error)
        # and the day is done with `failed` > 0, so one dead document never holds a look for good.
        counts = {"rows": len(rows), "filings": len(filings), "known": 0, "fetched": 0, "unlisted": 0, "retried": 0}
        entered: set[tuple[str, dt.date]] = set()
        cut = False
        for row in filings.values():
            accession = str(row["accession"])
            if accession in seen:
                continue
            if self.late(deadline):
                cut = True
                break
            if row["form"] == "8-K" and row["cik"] not in listed:
                seen.add(accession)
                failed.pop(accession, None)   # (an 8-K whose filer is unlisted since its failed fetch is no event)
                counts["unlisted"] += 1
                continue
            have = st.db.execute("SELECT status FROM filings WHERE accession=?", (accession,)).fetchone()
            if have is not None and have["status"] == "fetched":   # (the record pass may have fetched a failed one)
                seen.add(accession)
                failed.pop(accession, None)
                counts["known"] += 1
                continue
            tried = failed.get(accession)
            if tried is not None and now < tried[1] + FETCH_BACKOFF[tried[0] - 1]:
                continue    # (its next try is not due yet: the tries-th after the first failure)
            # (`listed`: a co-registered 8-K the live pass stored under an unlisted co-registrant is moved to this
            # listed filer's CIK before it is fetched, release 1019f's review)
            status = E.record_filing(st, ctx.sec, row | {"accepted_at": None, "index_url": None, "items": []},
                                     source="daily-index", now=ctx.now(), fetch=True, listed=listed)
            if tried is not None:
                counts["retried"] += 1
            if status.startswith("failed"):
                tries = (tried[0] if tried is not None else 0) + 1
                failed[accession] = (tries, tried[1] if tried is not None else now, str(row["form"]), status)
                if tries >= FETCH_TRIES:
                    seen.add(accession)    # (past its last try: named below, the day goes on without it)
                continue
            seen.add(accession)
            failed.pop(accession, None)
            if status == "fetched":
                counts["fetched"] += 1
                entered |= self._entry_sessions(st, accession)
        retrying = {acc: f for acc, f in failed.items() if acc not in seen}
        complete = len(seen) >= len(filings)
        if complete:   # (a filing past its last try that the record pass has fetched since is not named)
            for acc in list(failed):
                have = st.db.execute("SELECT status FROM filings WHERE accession=?", (acc,)).fetchone()
                if have is not None and have["status"] == "fetched":
                    failed.pop(acc)
        today = ctx.now().astimezone(C.NY).date()
        self._redecide |= {(kind, session_day) for kind, session_day in entered if session_day <= today}
        summary = {"day": day.isoformat(), "complete": complete, **counts, "failed": len(failed),
                   "retrying": len(retrying), "redecide": len(entered)}
        next_try = min((f[1] + FETCH_BACKOFF[f[0] - 1] for f in retrying.values()), default=None)
        if next_try is not None:
            summary["next_try"] = S.iso(next_try)
        if complete and failed:
            summary["unfetched"] = [{"accession": acc, "form": f[2], "tries": f[0], "error": f[3][:120]}
                                    for acc, f in sorted(failed.items())]
        if complete:
            st.set_meta(f"evl:backfill:{day.isoformat()}", "done")
            self._index_rows.pop(day, None)
            self._backfill_seen.pop(day, None)
            self._backfill_failed.pop(day, None)
            self._backfill_wait.pop(day, None)
        elif next_try is not None and not cut:   # nothing left but failed filings: the day waits for the next try
            self._backfill_wait[day] = next_try
        else:                          # cut by its bound: the next turn goes on from what was seen
            self._backfill_wait.pop(day, None)
        status = ("done-failed" if failed else "ok") if complete else "partial"
        self._receipted(st, "backfill", status, summary)
        return summary | {"_status": status}

    @staticmethod
    def _entry_sessions(st: S.Store, accession: str) -> set[tuple[str, dt.date]]:
        row = st.db.execute("SELECT knowable_at FROM filings WHERE accession=?", (accession,)).fetchone()
        if row is None:
            return set()
        knowable = S.parse_iso(row["knowable_at"])
        out = set()
        first = C.first_open_entry(st, knowable)
        if first is not None:
            out.add(("open", first.day))
        close = C.first_close_decision(st, knowable)
        if close is not None:
            out.add(("close", close.day))
        return out


# ---------------------------------------------------------------------------------------------------- the hook
class _PxRead:
    """px.sqlite opened READ-ONLY for the plan (`EventLane._px_job`): its progress marks and whether a session's
    universe holds a row; every read error reads as nothing (the recorder that would write it is then due)."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)

    def meta(self, key: str) -> str | None:
        try:
            row = self.db.execute("SELECT value FROM px_meta WHERE key=?", (key,)).fetchone()
        except sqlite3.Error:
            return None
        return None if row is None else str(row[0])

    def has_universe(self, day: dt.date) -> bool:
        try:
            return self.db.execute("SELECT 1 FROM px_universe WHERE day=? LIMIT 1", (day.isoformat(),)).fetchone() is not None
        except sqlite3.Error:
            return False

    def close(self) -> None:
        self.db.close()


def _ny_time(now: dt.datetime) -> dt.time:
    return now.astimezone(C.NY).time()


def _night(t: dt.time) -> bool:
    start, end = PX_NIGHT
    return t >= start or t < end


class LanePublisher:
    """`house.publisher`, wrapped: the original publisher's `publish(house)` exactly as before (its failure is still
    the House's "publishing failed" warning), then the lane's turn (`EventLane.turn`, which never raises). Every other
    attribute is the original publisher's."""

    def __init__(self, inner: Any, lane: EventLane):
        self.inner = inner
        self.lane = lane

    def publish(self, house: Any) -> None:
        try:
            if self.inner is not None:
                self.inner.publish(house)
        finally:
            self.lane.turn(house)

    def __getattr__(self, name: str) -> Any:
        inner = self.__dict__.get("inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)


def attach(house: Any, state_root: str | os.PathLike[str], config: Mapping[str, Any], *,
           token: Callable[[], str] | str) -> EventLane:
    """The lane on `house` (league/service.py, when `events_enabled(config)`): its store at `<state>/events/`, its
    gateway calls with the House's token source, `house.publisher` wrapped. `house.feeds` is left as it is (None)."""
    gateway = G.Gateway(token, url=str(config.get("gateway_url") or G.GATEWAY_URL))
    lane = EventLane(house, Path(state_root) / ROOT_NAME, gateway=gateway, settings=config.get("events") or {})
    house.publisher = LanePublisher(house.publisher, lane)
    return lane


def _wall(day: dt.date, at: dt.time) -> dt.datetime:
    return dt.datetime.combine(day, at, tzinfo=C.NY).astimezone(UTC)


def _iso_epoch(value: float) -> str | None:
    if value in (float("inf"), float("-inf")):
        return None
    try:
        return S.iso(dt.datetime.fromtimestamp(value, UTC))
    except (OverflowError, OSError, ValueError):
        return None


def _base_kind(kind: str) -> str:
    """The entry kind ("open" | "close") of a births-only decision kind (`BIRTH_KINDS`)."""
    return next(base for base, born in BIRTH_KINDS.items() if born == kind)


def birth_usd(db: Any, lo: str, hi: str) -> float:
    """R3's births calls answered in [lo, hi) (`birth_calls`, league/events/births.py `propose`: its stated cost, or its
    worst case when the gateway stated none; a NULL at `BIRTH_USD_UNKNOWN`), 0 when the store has no such table."""
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='birth_calls'").fetchone() is None:
        return 0.0
    row = db.execute("SELECT COALESCE(SUM(COALESCE(usd, ?)), 0) FROM birth_calls WHERE answered_at>=? AND answered_at<?",
                     (BIRTH_USD_UNKNOWN, lo, hi)).fetchone()
    return float(row[0] or 0.0)


def verdict_day(now: dt.datetime) -> tuple[dt.date, tuple[str, str]]:
    """THE DAY THE LANE'S LINE IS HELD ON (the module docstring): the UTC day of `now` and its [00:00, 24:00) UTC as the
    store's strings, the day budget rule 3 holds every line on and the cap breach is judged on (league/ops/metered.py
    `day_bounds`)."""
    day = now.astimezone(UTC).date()
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=UTC)
    return day, (S.iso(start), S.iso(start + dt.timedelta(days=1)))


__all__ = ["EventLane", "LanePublisher", "LaneGateway", "LaneContext", "LaneCut", "LaneDeadline", "attach",
           "events_enabled", "verdict_day", "birth_usd", "ROOT_NAME", "BACKGROUND_KEY"]

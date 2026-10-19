# The event lane (EVL)

The lane the owner's goal of Oct 19, 2026 funds: long-only, whole-share trades in US-listed common stocks, entered and
exited in the listing exchange's opening and closing auctions, triggered by public events newer than any model's
training (SEC EDGAR 8-K and Form 4 filings, Alpaca news). The rules are pre-registered and frozen; this page says where
they are and how the code runs them. When this page and a pre-registration disagree, the pre-registration wins.

## The rules

- [PREREG-EVL-1](prereg/PREREG-EVL-1.md), registered 2026-10-19T01:08:38Z (tag `prereg-evl-1`): the universe, events
  and knowable times, the Claude Haiku 4.5 verdicts (temperature 0, stored once, replayed), the auction execution model
  and costs, the four first seatable programs, THE SCREEN (the judge for every program), real money, Done and Kill.
- [PREREG-EVL-2](prereg/PREREG-EVL-2.md), registered 2026-10-19T03:04:07Z (tag `prereg-evl-2`): the second wave, five
  seatable programs, three records and one control, judged by PREREG-EVL-1's screen unchanged.
- [PREREG-EVL-3](prereg/PREREG-EVL-3.md), registered 2026-10-19T05:23:06Z (tag `prereg-evl-3`, under the owner's goal
  of 05:15Z Oct 19): VERSION 2 of the nine seatable programs (the same events and rules, the limit at entry for all
  nine) trades REAL money at learning size from its first event; promotion, demotion and retirement by looks counted
  in settled events. Version 1 of every program stays a shadow record and never trades.
- [PREREG-EVL-4](prereg/PREREG-EVL-4.md), registered 2026-10-19T16:01:05Z (tag `prereg-evl-4`, the captain's births
  under the same goal; amendment A71): three NEW seatable programs, each entering at D's CLOSE and exiting at the next
  session's OPEN, at PREREG-EVL-3's learning band from birth (their VERSION 1 is their seating version), and two
  controls; judged by PREREG-EVL-3's screen unchanged ("PREREG-EVL-4" below).
- An event counts for a program only when it is knowable after that program's own registration time. A change to a
  registered program is a new version with a new registration time. Expected false passes: 1.2 (0.10 x 12 seatable
  versions: the nine version 2 rows and PREREG-EVL-4's three) of the lane's stated lifetime budget of 3.0
  (PREREG-EVL-4 section 3; 1.8 left for later births, each later file stating its draw).

## The programs

| program | file | seatable | event | entry | exit |
|---|---|---|---|---|---|
| EVL-ERN-READ-O1 | 1 | yes | earnings 8-K (item 2.02), verdict score >= 2 | next open | that close |
| EVL-ERN-REACT-C1 | 1 | yes | earnings 8-K, day-0 move >= +4% at 15:29 ET | day-0 close | next close |
| EVL-8K-READ-O1 | 1 | yes | 8-K items 1.01, 2.01, 7.01, 8.01 (no 2.02), score >= 2 | next open | that close |
| EVL-NEWS-READ-O1 | 1 | yes | pre-market single-stock news, score >= 2 | open | that close |
| EVL-ERN-REACT-ON | 2 | yes | C1's events and rule | day-0 close | next OPEN |
| EVL-ERN-GUIDE-O1 | 2 | yes | earnings 8-K, guidance "raised" and score >= 1 | next open | that close |
| EVL-INS-BUY-O1 | 2 | yes | Form 4: director/officer open-market buys >= $50k | next open | that close |
| EVL-NEWS-READ-ON | 2 | yes | single-stock news 09:00-15:29 ET, score >= 2 | that close | next OPEN |
| EVL-NEWS-REACT-ON | 2 | yes | the same news, move >= +4% at 15:29 ET | that close | next OPEN |
| EVL-8K-REACT-ON | 4 | yes (version 1) | F8K(D): 8-K items 1.01, 2.01, 7.01, 8.01 (no 2.02) in D's close window, issuer not EXCLUDED, move >= +4% at T29 | D's close | next OPEN |
| EVL-8K-READ-ON | 4 | yes (version 1) | the same filings, stored PROMPT-DOC score >= 2 | D's close | next OPEN |
| EVL-NEWSPM-READ-ON | 4 | yes (version 1) | PM(D): pre-market single-stock news, issuer not EXCLUDED and with no F8K(D) filing, stored PROMPT-NEWS score >= 2 | D's close | next OPEN |

Records (never seated): EVL-ERN-READ-O3, EVL-INS-CLUSTER-O5 (file 1); EVL-INS-BUY-O5, EVL-ERN-REACT-READ-C1,
EVL-ERN-READ3-O1 (file 2). Controls (what the verdicts add): EVL-CTRL-ERN-ALL-O1, EVL-CTRL-8K-ALL-O1,
EVL-CTRL-NEWS-ALL-O1 (file 1), EVL-CTRL-NEWS-DAY-ON (file 2), EVL-CTRL-8K-ON and EVL-CTRL-NEWSPM-ON (file 4). File 2's
and file 4's programs (and every version 2) are not filled when the entry auction is above 1.25 x the previous close
(real money's limit).

## Bands (the seating versions: real money)

The versions that may seat (`programs.Program.can_seat`, the one gate in the lane and the House's book): version 2 of
the nine seatable programs of files 1 and 2 (PREREG-EVL-3) and version 1 of PREREG-EVL-4's three. Version 1 of the
earlier files' programs, every record and every control never seat.

| band | size | how a program gets there |
|---|---|---|
| learning | 2% of equity a position (whole shares; one share up to 5%), at most 8 open | from its first event |
| probe | 5%, at most 6 open | the first decision after a passed look |
| sized | 10%, at most 8 open | >= 150 settled real-money events at Probe size or above, 80% session-block lower bound > 0 |
| retired | none (shadow only) | a held look with mean a < 0 and the reversed sign-flip p <= 0.05 |

Back to learning from probe or sized: the last 50 Probe+ events lost more than $150 net, or the last 100 have a
negative mean, both counted over the program's CURRENT Probe stay (its events bought after its latest move to Probe in
`band_history`; release 1019b's second review), so a program the next passed look returns to Probe is not demoted again
on the events that demoted it; Sized's 150 events and its bound count the current Probe stay too (release 1019b's third
review, the reading that trades less), so a program demoted from Sized earns Sized again only on its new stay. LOOKS
(version 2): at 60, 90, 135, 200, 300, 450, 675,
1000, 1500 and 2250 settled TRADABLE events, each needing at least 40 issuers and 8 session blocks; thresholds first
reached at the same close are one look; the skew check starts and caps at 0.018 (A65). Room when short: Sized, then
Probe, then learning (how the book gives it out: "Real money" below). The lane writes the
bands (`league/events/bands.py`, tables `bands` and `band_history`, CLI `bands`); the House's event book reads them
with the same module's `bands(store)` and writes every real fill to `real_fills` with its `record_fill` (a posted fee
updates its row); on the House the lane reviews the real fills after each night's screen (`bands.review`: demotion and
Sized), whatever the screen did.

A LOOK READS A FINAL RECORD (release 1019b's review; `screen.final_until`, version 1 and version 2 alike): a look as of
a close is computed once nothing more can be added to the sessions it covers: the hourly re-decision of the last three
sessions has passed that close, every decision of the program's entry kind through it is made (a reading program's
session that waits on a verdict has no intent yet), and the EDGAR daily-index backfill of the weekdays through it that
the House still backfills has run. Late data delays the computation, never its as-of date (PREREG-EVL-1 section 7),
so a look is written about three sessions after its close. A version 2 look on record is never derived again: the
schedule resumes after the last one at the k after every k written or merged into it (the merged ks are in the look's
detail), and the band move a look makes (Probe, retired) is written in the look's own transaction. The re-decision reach
a look waits out (three sessions, the 45-day look-back, three backfill weekdays) is defined once, in the judge
(`screen.py` `FINAL_SESSIONS`, `FINAL_LOOKBACK`, `FINAL_BACKFILL_WEEKDAYS`, behind the wall), and the House's lane
takes its own from there (`house.py` imports them; release 1019b's second review): a House change the updater ships by
itself can use the reach but not widen it, and a wider one would only delay a look (`screen._reach` waits out the
larger).

ELIGIBILITY IS DECIDED ONCE PER (ENTRY SESSION, CIK), BY THE RULE THAT MADE IT (release 1019b's second review;
PREREG-EVL-1 section 2: a live decision reads Alpaca's `status=active` and `tradable: true`, a backfilled one
`status=all` and the previous session's closing-print exchange). Every result, eligible or not, is kept in the store's
`eligibility` table with its rule (`live` or `backfill`). A live decision reads the live rule's result and checks under
the live rule a CIK that has none; a backfill decision (the House's hourly re-decision of the last three sessions among
them) reads whatever result the session has, eligible only when none is ineligible, and checks under the backfill rule
only a CIK no decision has judged (a late event). So the re-decision of a live session never admits a name the live
decision refused (a `tradable: false` one, say), and a row only the backfill rule made never serves a live decision,
real money's picks or the eligible list the gateway checks. A run is live when it runs within 10 minutes of its
scheduled time, else a backfill: the judge's rule (`run.py` `LIVE_WITHIN`, `live_run`, behind the wall), which the
House's lane and the CLI's catchup call. A store from before the table (the desktop's, migrated) first keeps the
desktop's live refusals (amendment A67: each meta `elig-no:<day>:<cik>` = "live" becomes that CIK's live result,
ineligible, for that session; release 1019b's third review), then labels each universe row with the rule of its
session's first decision run (live when it started within 10 minutes of its time, else backfill). So a re-decision of
either kind never admits a CIK the desktop's live rule refused. For a session from before the table WITHOUT markers, a
re-decision reads a CIK with no result as the live rule found it, ineligible, when this decision's first event of it
was FETCHED before the session's first finished live decision of either kind (a filing only listed before it was never
seen by it, and is judged as a late event is).

## PREREG-EVL-4: three overnight programs from births, seatable at version 1

[PREREG-EVL-4](prereg/PREREG-EVL-4.md) (registered 2026-10-19T16:01:05Z) holds the night after an attention day, for
the issuer-days no earlier close-to-open row trades. For entry session D (P the session before it):

- THE CLOSE WINDOW of D: knowable at or after P's close decision time and before D's close decision time (C1's day 0
  is D). F8K(D): the fetched 8-Ks of that window with any of items 1.01, 2.01, 7.01, 8.01 and no 2.02 (EVL-8K-READ-O1's
  family). ERN(D): the issuers of the window's item 2.02 8-Ks. DAY(D): the issuers of PREREG-EVL-2's day-news window
  (after 09:00 ET of D, at or before T29) whose one symbol is their eligible ticker. PM(D): EVL-NEWS-READ-O1's window
  of D (after P's close, at or before 09:00 ET of D).
- EXCLUDED on D: an issuer in ERN(D) or DAY(D); every program and control of the file skips it, WHATEVER THE KNOWABLE
  TIMES of the rows that put it there relative to any registration time (the sets are read with no registration floor:
  `programs.filings_window`, `programs.news_rows`, `programs.close_rows_4`; the earlier files' readers `filings_in` and
  `news_in` are unchanged). EVL-NEWSPM-READ-ON and its control also skip an issuer with any F8K(D) filing.
- EVL-8K-REACT-ON: C1's reaction (the T29 minute close of D over the raw daily close of the last session that closed
  before the filing's acceptance) >= 1.04, ranked by it; EVL-8K-READ-ON: the stored PROMPT-DOC verdict of
  `8k:<accession>`, `ok` with score >= 2 (the very verdict EVL-8K-READ-O1 reads: asked once, stored once; a filing
  knowable during D is asked during D's session by the close decision's verdict asks; a TEXT under 200 characters has
  no verdict); both one event per issuer per D, the earliest knowable filing the rule takes. EVL-NEWSPM-READ-ON: the
  stored PROMPT-NEWS verdict of `news:<id>`, `ok` with score >= 2, the highest score then the earliest; it ASKS NO
  VERDICT OF ITS OWN (EVL-NEWS-READ-O1 asks it for its open decision of D) and waits for it.
- Each enters at D's close (decided at the close - 14 minutes) and exits at the next session's open auction, with the
  fallback ladder; the limit at entry (1.25 x the previous close) binds shadow and real alike. Only events knowable
  after 16:01:05Z Oct 19 count, for every purpose.
- THE SCREEN is PREREG-EVL-3's (event-counted looks 60 ... 2250 with >= 40 issuers and >= 8 blocks, alpha 0.018,
  retirement, demotion, Sized), with version 1 in place of version 2: the seed strings are `{id}|v1|look{k}`;
  EVL-8K-READ-ON must beat EVL-CTRL-8K-ON and EVL-NEWSPM-READ-ON must beat EVL-CTRL-NEWSPM-ON over their own block
  sessions; EVL-8K-REACT-ON has no control condition.
- REAL MONEY (section 1.3): the three seat at the learning band from birth (2% of equity, whole shares, one share up
  to 5%, at most 8 open), after every row of files 1 and 2 in ROOM's order within a band. A real-money decision is the
  shadow rule over the rows STORED before D's close decision time, EXCLUDED and the F8K(D) skip read from those rows
  too (`book.rows_4`); a row stored later counts in the shadow only. EVL-8K-REACT-ON and EVL-8K-READ-ON NEVER BUY for
  a filing knowable at or after 09:00 ET of D whose stored PROMPT-DOC verdict is `ok` with score >= 2, or is not yet
  answered, at the decision time (`book.next_open_event`, `NEXT_OPEN_GUARD`): that filing is EVL-8K-READ-O1's event
  at the next open, whose buy this row's sale there would take. The sale gate keeps these rows out of a name an event
  lot sells at the same close (an EVL-8K-READ-O1 or EVL-NEWS-READ-O1 lot bought at D's open, say).
- WHAT IS COUNTED, NOT PREVENTED: an earlier row's real-money buy lost at the next open to the sale of this file's
  overnight lot of the same name is in the book's decision summary and its `equity.event_decide` record
  (`sale_to_later`: {skipped program: {selling program: n}}, any later row's sale in the tables' order); the shadow's
  difference from real money by storage time is in the lane's report (`report.late_rows`: events whose row was stored
  after their decision, intents a later row excluded).

How the lane runs them (league/events/run.py `decide_close`): the earlier close rows are decided first, exactly as
before (their reads, eligibility call, verdicts and intents); then this file's rows read their own: every 8-K of the
close window, the day-news window and PM(D), EXCLUDED and the F8K(D) skip (`_rows_4`), and the eligibility of the
issuers of their events, judged once per (entry session, CIK) by the decision's rule like every other result (an
issuer EXCLUDED or skipped is never judged for them). A re-decision marks an intent of these rows that has not settled
`skipped:excluded` when a row stored after the decision puts its issuer in EXCLUDED or the F8K(D) skip
(`_skip_excluded`); a settled one keeps its record. The T29 minutes of EVL-8K-REACT-ON's names are read in batches of
100 (`_marks_1530`, the same rule as `_mark_1530`). On the House, a close decision waiting on PM verdicts has the
session's open decision's own asks made (`run.waits_on_open`; league/events/house.py `_verdicts`), and a verdict wait
no call of a pass could answer backs off (`_look`). THE PROOF that no earlier program changes: league/tests/
test_events_evl4.py decides a synthetic week (league/tests/evl4_world.py) with and without these rows, and the same
week decided by release 1019b's code gives every earlier program the same intents and real-money picks.

## The code

`league/events/` (standard library only): `store.py` (one SQLite file and a document store; the schema is pinned),
`edgar.py` and `news.py` (the recorders), `calendar.py` (sessions and decision moments), `universe.py` (eligibility),
`verdicts.py` (the recorded Haiku verdicts), `programs.py` (the programs as data rows and their selection rules),
`run.py` (the open and close decisions, backfill), `score.py` (settlement at the auction prints and the exit ladder),
`screen.py` (the judge), `report.py` (the daily one-screen report), `house.py` (the lane on the House: its scheduler),
`__main__.py` (the CLI: `record`, `backfill`, `decide-open`, `decide-close`, `catchup`, `tickers`, `equity`, `score`,
`screen`, `report`). The judges (`programs.py`, `verdicts.py`, `score.py`, `screen.py`) and `docs/prereg/` are behind
`league/ci.py`'s FORBIDDEN wall from release R1: no role changes them and the House's updater never ships one. Release
R2's real-money side: `book.py` (the equity book's event kind's rules: the money rows, the bands, the real-money picks,
the limit, the size target, the open-risk weight, the exit plan, the eligible list) and `proof.py` (the auction paper
proof). Release 1019b adds `bands.py` and the modules holding the rules' inputs: `universe.py` (eligibility, the
benchmark), `calendar.py` (the windows and decision times), `edgar.py` and `news.py` (the knowable lag, the TEXT a
verdict reads), `run.py` (which program gets which rows, the shadow's 15:30 reaction) and `store.py` (the record's
schema); `house.py`, `gw.py` and `report.py` stay outside, so their fixes can ship through the updater.

## Where it runs (shadow)

Until release R1 moves the lane onto the House, it runs on the captain's workstation as systemd user timers
(`ltcm-evl-record` every 2 minutes; `ltcm-evl-tickers` 07:00 ET; `ltcm-evl-decide` at 09:16 and 15:47 ET plus an
hourly catchup; `ltcm-evl-equity`; `ltcm-evl-score` 20:30 and 08:30 ET; `ltcm-evl-screen` 20:50 ET; `ltcm-evl-report`
21:05 ET), reading Alpaca and Claude through the LTCM gateway. Nothing in shadow sends an order. Real money (PREREG-EVL-3:
learning size from the first event) comes with release 1019b: the lane on the House, the gateway's event-buy branch,
the equity book's event kind, the auction order types and the paper proof; then the desktop's timers stop and its
store moves to the House (`scripts/evl_migrate.py`).

## On the House (release R1)

With `league/config.json` `events.enabled` true, the same functions run inside the House's process
(`league/events/house.py`), on its state root (`<state>/events/`, the same store), with the House's gateway token and
SEC contact; the desktop's timers stop. The House's tick publishes the site every minute, and the lane's turn rides on
it (the publisher is wrapped; `house.feeds` stays None so none of the House's old feed paths wakes): one bounded task a
turn, the most urgent due first.

| order | task | when | bound |
|---|---|---|---|
| 1 | a decision: the open, C1's close (a minute after its time), then one pending on verdicts | 09:15 ET; close - 14 min; pending every 5 min | 150 s, then the next turn goes on |
| 2 | verdicts a decision will read | its decision within 30 min, or pending | 90 s |
| 3 | the record pass: EDGAR's current feeds, the news, then today's verdicts with the time left | every 2 min, 24/7 | 90 s, resumable |
| - | the hourly re-decision of the last three sessions (late events) | hourly, after the record pass | 150 s |
| 4 | nightly: the account equity, the score, the screen (then the band review of the real fills), the report | close + 3 min; 20:30 ET | the score 120 s, resumable |
| 5 | the ticker snapshot | 07:00 ET, weekdays | one read |
| 6 | early verdicts (today's open decision's, then its close decision's) | from 07:30 ET | 90 s |
| 7 | the backfill of a weekday's EDGAR daily index | from 05:00 ET the next day | 90 s, resumable |

A task ends before a decision falls due. A filing whose fetch failed (a transient SEC error) is fetched again at the
first record pass 2, 4, 8, 16 and 32 minutes after its first failure, six tries in all, then left to the daily-index
backfill (an SEC outage of half an hour, or SEC's 10-minute rate-limit block, no longer spends every try); a record
pass whose feed failed counts its retried rows beside the feed's error; a decision that raised is closed `failed` and
run again a minute later while it is live, then every 10 minutes (a cut one goes on at the next turn; one cut and then
failing waits as a failed one). Verdicts are asked from
07:30 ET because a session's universe is fixed then
(its tickers copy is the latest before 07:30 ET), with the decision's own code (`decide_open` / `decide_close`
`ask_only`), so the 09:15 decision finds them stored and asks none. Verdicts wait while the House is paused (`PAUSE`) and
over the lane's own line (`events.verdict_usd_day`, $3 a New York day from release 1019b's second review: the goal's
cost rule, metered compute at most $5 a day plus half the trailing week's realized net profit, with the House box at
about $1.29 a day, until budget rule 3 ships): a READ event then waits, as PREREG-EVL-1 section 4 lets it. The lane writes a receipt for every task in the store and its health to `<state>/events/lane.json`.
How to switch it on, migrate the desktop's store (`scripts/evl_migrate.py`) and stop it:
[operations](operations.md), "The event lane on the House".

## Real money (release R2, shipped switched on in release 1019b; not yet deployed)

[PREREG-EVL-3](prereg/PREREG-EVL-3.md) (the owner's goal as re-set at 05:15Z Oct 19, 2026): VERSION 2 of each of the
nine seatable programs trades real money from its first event at LEARNING size, with the full-size shadow beside it;
version 1 is a shadow record and never trades. [PREREG-EVL-4](prereg/PREREG-EVL-4.md)'s three seatable programs trade
at version 1 the same way, after the nine in ROOM's order (above: "PREREG-EVL-4"). The bands are the lane's (its store's `bands` table: learning from birth,
Probe after a passed look, Sized, retired), counted in settled events from its looks and the real fills the House writes
back (`real_fills`). The House trades them through its EquityBook (its event kind: league/equity/live.py `_event_step`,
the rules in `book.py`), on the money rows `equity_money.event` of league/constitution.py: learning 2% of equity a
position (one share at most 5%), Probe 5%, Sized 10%, at most 8 open a learning program (Probe 6, Sized 8), the
book-wide 10% a name, whole shares, entries limit-on-open / limit-on-close at 1.25 x the previous SIP close, exits
market-on-close (market-on-open for the three overnight rows) with PREREG-EVL-1 section 5's fallback ladder, open risk
value x max(0.10, 1.65 x sigma60 x sqrt(h)) in the one loss budget ($400 net in any 20 sessions, $800 net in total),
ROOM in the order Sized, Probe, learning, then the tables' order. The real-money decision reads the lane's store, and
only events stored and verdicts answered before its decision time (PREREG-EVL-1 section 3). The old lanes'
`equity_money.enabled` stays False; nothing goes until the gateway's `STOCK_EVENT_BUYS` is on and the auction paper
proof on the practice account has passed its BUY stage (filled, or accepted and ended unfilled at the open: the
practice venue simulates no auction, amendment A68) (release 1019b ships the gateway's switch `on` and the lane's
`events.enabled` true; deploy order: the gateway, then the House, then the migration with the desktop's timers
stopped). How it runs, is read, is deployed and is rolled back:
[operations.md](operations.md), **The event lane's real money on the House (release R2)**. Each real fill is set beside
the shadow's own auction price, per side (league/ops/twins.py `event_twin`).

How the book meets the auctions (release 1019b's review): each decision plans its EXITS before it reads anything of the
lane, and a failing decision never stops that minute's sends; THE SALES GO BEFORE THE DECISION (the third review): for
each auction inside its window the exits due are planned, its sales are sent, then its decision is made (the picks, the
close's T29 reads), then its buys are sent, so a decision that reads for a long time never holds a sale past the
window's cut-off; two programs' lots of one name due at one
auction are both sold in its cross (the book's own sales at that auction do not stop each other; anything else working
on the name does); the equity day's order count keeps one order for each event lot's exit and none once its sale is
sent; the close decision reads each name's T29 minute once, all the day's names in batched requests, and the lane's
own 15:30 marks are used where they exist (on the House the lane's close decision runs a minute after the book's); a
gateway refusal that it holds no eligible list of the day publishes the list again.

How the book gives out the room (release 1019b's second review). ROOM IN ITS ORDER: at each decision the programs go
Sized, then Probe, then learning, then the tables' order; each takes ITS OWN ranked picks whose name no earlier program
was given at that auction, until its room (its open positions left) is full, and only a name given to a program is
taken (`book.allocate`): REACT-ON takes the C1 events C1 has no room for, GUIDE-O1 the READ-O1 events READ-O1 has no
room for. SIZE BEFORE SLOTS: before a pick takes a slot, the book skips (the shadow keeps the event) one that no whole
share of fits by price, on the figures the send sizes on (E the equity at the previous close; the name's book-wide
value): one share at the limit above the book-wide 10% a name (above 10% of E for a name held nowhere: not TRADABLE),
or, at learning, a 2% target that buys no whole share with one share above 5% of E; and one whose name an event lot
sells at that same auction. AN EXIT NEVER WAITS ON AN ENTRY: no buy of a name goes in the cross that sells it (a sale
the gateway refused for a reading, a 424 or 409, goes again the next minute, never held by a buy sent in between). THE
T29 READS ARE BOUNDED BY THE WINDOW (the third review): the close decision's batched T29 read sends a failed request
again once, never after a timeout and never in the window's last minute (from 15:48 ET at a full day's close), and
starts no request in that minute. A T29 BATCH FAILURE DROPS ONLY THE REACT ROWS' PICKS: a name whose T29 minute was not
read has no reaction, so a REACT row of it (C1, REACT-ON, NEWS-REACT-ON) is not taken, while every other pick goes
(NEWS-READ-ON's included) and the decision is made with what was read, its errors in its summary and the minute's
`errors`; only an E that cannot be read leaves a decision `failed`, made again the next minute of its window and never
at or after the cut-off.

THE READINGS THAT TRADE LESS (PREREG-EVL-3 section 6; the captain's amendments A67 and A70), every one the House's code
takes: the equity day's order count (event entries are bounded by 60 orders a day less one kept for each event lot's
unsent exit, two for an old-lane lot; an exit is never stopped by it; release 1019c gives the lane its own line); a
program's room counts what it is selling at that same cross; no buy of a name in the cross that sells it; a T29 batch
failure (the REACT rows of the names not read are not taken); a decision that cannot read E (none at or after the
cut-off: that auction's events are not entered); eligibility (a live refusal stands for its session, the desktop's
markers included, and a backfill decision reads a CIK eligible only when no rule refused it); Sized over the current
Probe stay; one position per issuer for real money (a lot open or closed within the last 5 sessions, a buy planned or
sent, or an earlier decision's shadow intent of the issuer); the limit rounded down to the cent. The shadow keeps every
event real money skips.

STOPPING IT: `<state>/events/STOP` idles the LANE only (no record pass, decision or verdict ask); the House's event book
still decides each auction on the store as it stands, so buys from events and verdicts already stored can still go.
The instant stop of event buys is the gateway's `STOCK_EVENT_BUYS` off or `equity_money.event.enabled` False
([operations.md](operations.md), **Release 1019b**, Rollback).

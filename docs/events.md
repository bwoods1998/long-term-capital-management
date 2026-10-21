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
| probe | 3.5% (whole shares; one share up to 5%), at most 8 open (the captain's A86; PREREG-EVL-3's 5% and 6 before) | the first decision after a passed look |
| sized | 10%, at most 8 open | >= 150 settled real-money events at Probe size or above, 80% session-block lower bound > 0 |
| retired | none (shadow only) | a held look with mean a < 0 and the reversed sign-flip p <= 0.05 |

THE PROBE BAND'S SHAPE (the captain's A86, Oct 21, 2026, recorded before any Probe event; branch
`fix/a86-probe-more-smaller`, the captain decides whether it ships): cash at the auction binds first at Probe, so
PREREG-EVL-3's 5% with at most 6 open fitted about 9-11 Probe buys an auction; at 3.5% with at most 8 open more,
smaller Probe lots fit the same cash, and Done counts Probe events. One share at Probe (the 3.5% target buys no whole
share) goes only when it is at most 5% of equity, as at learning: a Probe program's dollars are at most 8 x 3.5% =
28% of equity at target (30% before) and 8 x 5% = 40% in the worst case (6 lots up to the 10% wall, 60%, before). A
name whose one share at the limit is above 5% of equity is skipped at Probe, where PREREG-EVL-1 bought one share (the
shadow keeps it). It is a sizing rule: no judge, look, alpha or false-positive rate moves, and the screen's cost
allowance keeps its 5% notional.

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
larger). A decision's receipt NAMES the programs it decided or left pending (their keys in its summary); for a program
of PREREG-EVL-4 a decision whose receipt does not name it (made by a release without its rows) is NOT MADE for it until
a later receipt of its rows' own decision names it (`screen.names`, `made_without`; release 1019c's review, below
under "PREREG-EVL-4"), so no look reads a record its rows never decided; the earlier files' programs read their
receipts as before.

THE FAST PATH TO A FINAL RECORD (the captain's amendment A69; release 1019c, not yet deployed): the three sessions' wait
is for late data, so when there is provably none a close X is final for a program as soon as the session after X has
had its open decision, if (i) every record pass from the start of the earliest window that feeds X's decisions (09:00 ET
of the session before X, never before the program's registration) through that open decision finished `ok` with its
8-K, Form 4 and news reads whole (no `error` in any, the news read not cut, the tickers copy read) and the passes ran
at most 15 minutes apart (`screen.FAST_RECORD_GAP`: a pass that never ran proves nothing); (ii) no filing knowable in
those windows that the lane would fetch is still `listed` or `failed` (a failed one, a listed Form 4, a listed 8-K of a
filer in X's tickers copy; an unlisted filer's 8-K is never fetched and never an event of X); (iii) the daily-index
backfill of every weekday from the session before X through X has run; and (iv) every decision of the program's entry
kind through X is made (`ok`, or `pending` only on another program's verdicts) and the next session's open decision is
made. Otherwise A66's rules apply unchanged, and finality stays contiguous: X is final by the fast path only when every
session before it is final. The record receipts the House already writes prove (i) (league/events/house.py `_record`:
a failed feed read is an `error` in its part of the summary, a news read cut short is `cut`, a pass that raised is
`failed`, one that never finished stays `running`), so no new record was added. A clean record is final one session
after its close, about two sessions sooner than A66's; the as-of date, the record and the look are the same.

WHAT A RE-DECISION WRITES (A66's owed rule and A69; release 1019c, `run._scope`): no decision ever writes an intent
under a look already written, and A LOOK FREEZES ITS WHOLE GROUP (release 1019c's judges review, A74 (5);
`run._group`): once a look of any version of a program is written as of the exit of the session's intents or later,
every version of that program's id, its control, and every version of every READ program of that control are left as
they were, inside the House's re-decision window (where A69 can make a close final while the House still decides it
again every hour) and outside it, pending or not, so version 2 keeps taking version 1's events word for word
(PREREG-EVL-3 section 1) and every READ program's control comparison stays even (READ-O1 and GUIDE-O1 share
CTRL-ERN-ALL-O1). A kept run writes no `pending` for a kept program, so its session is made (A66's second rule). Every
other program is decided whole, whoever decides the session again and however old it is: the hourly re-decision, a
decision pending on verdicts, THE DAILY-INDEX BACKFILL's (which A66's third rule makes a look wait for) and the CLI's
catchup. Release 1019c's fix round WITHDREW A74 (6), which wrote again outside the window only the programs the last
finished receipt was pending on: after an outage of three sessions or more (or an index two days late) it threw away
the very events the backfill a look waits for brings, against PREREG-EVL-1 section 3 ("an outage removes nothing";
backfilled events "are read afterwards and count"), gave a late event to a READ program that was pending and not to its
control, and hid the shadow's holding from real money's one position per issuer; the group freeze alone keeps every
written look's record as the look read it (for the captain to record before release 1019c deploys: A74 (6) never ran
on the House, so no record changes).
THE LATE SHARE IS RECORDED (PREREG-EVL-1 section 3: an outage removes nothing, the late share is reported): the
summary's `kept` names each program a decision left as it was, with why (and the look that froze it), the `events` its
rule takes on the verdicts and prices already stored that its record does not hold, and the `unjudged` ones it would
take only on a verdict or price no one has stored (a kept program is never asked a verdict and never fetched a price;
`run._left_out`); the daily report counts both for each program, each event once ("kept out n (+m unjudged)"); and a
look's detail records when it was written (`written_at`, meta `look:<program>:<version>:<k>`). The
cost: an event stored after a look of its group was written over its session is not added to that program's record; it
is listed and counted instead.

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

THE CLOSES BEFORE THE DEPLOY (release 1019c's review; section 2: "for every event after the registration time that
comes before it (backfill included), the programs are decided by the same rules in shadow only"): releases 1019b and
1019c decide the closes from 16:01:05Z Oct 19 until release 1019d runs, and their receipts name none of these rows. The judge reads such
a close as not made for them (`screen.final_until`), and the lane decides THESE ROWS BY THEMSELVES for it, once, as a
backfill (`run.decide_close` with `evl4_only`, its receipt `decide-close-evl4:<day>`): the House's lane for every such
close its hourly re-decision no longer reaches, after the record pass, oldest first (`house.py` `_refill_redecide`;
a close the re-decision still reaches is decided again whole, as before), and the CLI's `catchup` (or `decide-close
--day D --evl4-only`). The earlier rows of such a close are never decided again: their receipts, intents and finality
stay release 1019b's, even for an event of theirs stored after the close left the reach. An issuer's eligibility reads
all 20 of the entry session's sessions' bars and fetches any one missing (`run.eligibility`; before, only the last was
checked, so an issuer judged first for a later session, an 8-K of D being EVL-8K-READ-O1's at D+1's open, read as
ineligible for D).

WITH RELEASE 1019c's RULES (release 1019d, the merge): these rows' groups are release 1019c's over their controls
(EVL-8K-READ-ON with EVL-CTRL-8K-ON, EVL-NEWSPM-READ-ON with EVL-CTRL-NEWSPM-ON, EVL-8K-REACT-ON alone), and a written
look of a group freezes it in every re-decision of its sessions, their own decision `decide-close-evl4` included
(asked nothing, written nothing, no `skipped:excluded` move; the events left out named in the receipt's `kept` and
counted by the report). A receipt names a program it kept (`screen.names` reads `kept` too), so the freeze never
reads as "made without its rows". Their closes are final by A66's rules or A69's fast path as every close-entry
program's, once named; their verdicts are in each decision's tally (the stall job's `evl_verdicts`). The event kind's
day order count stays 150 with the twelve seatable programs (A78): on a day that needs more, entries stop in ROOM's
order, so these rows are refused first; exits never.

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

Until release 1019b moved the lane onto the House (deployed 21:00Z Oct 19, 2026; the store migrated at 21:11Z), it
ran on the captain's workstation as systemd user timers
(`ltcm-evl-record` every 2 minutes; `ltcm-evl-tickers` 07:00 ET; `ltcm-evl-decide` at 09:16 and 15:47 ET plus an
hourly catchup; `ltcm-evl-equity`; `ltcm-evl-score` 20:30 and 08:30 ET; `ltcm-evl-screen` 20:50 ET; `ltcm-evl-report`
21:05 ET), reading Alpaca and Claude through the LTCM gateway. Nothing in shadow sends an order. Real money (PREREG-EVL-3:
learning size from the first event) came with release 1019b: the lane on the House, the gateway's event-buy branch,
the equity book's event kind, the auction order types and the paper proof; the desktop's timers are stopped and its
store, copied to the House (`scripts/evl_migrate.py`), stays on the desktop as the backup (one writer: never
restart its timers while the House lane runs).

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
| - | PREREG-EVL-4's rows decided by themselves (`decide-close-evl4`) for each older close a release without them decided | from the first turn after the record pass, once each | 150 s |
| 4 | nightly: the account equity, the score, the screen (then the band review of the real fills), the report | close + 3 min; 20:30 ET | the score 120 s, resumable |
| 5 | the ticker snapshot | 07:00 ET, weekdays | one read |
| 6 | early verdicts (today's open decision's, then its close decision's) | from 07:30 ET | 90 s |
| 7 | the backfill of a weekday's EDGAR daily index | from 05:00 ET the next day | 90 s, resumable |

THE BACKFILL GOES FILING BY FILING (A82, release 1019c): EDGAR's daily index lists a filing once per filer (a Form 4
under its issuer and its reporting owner, an 8-K under each co-registrant: Oct 19, 2026's index had 1,189 rows and 665
filings), so a day is complete when every filing is seen, and an 8-K is a listed filer's when any of its filers is
listed. Before it, a day counted rows and never completed, every look waited the full A66 reach and A69's fast path
never ran.

A task ends before a decision falls due. A filing whose fetch failed (a transient SEC error) is fetched again at the
first record pass 2, 4, 8, 16 and 32 minutes after its first failure, six tries in all, then left to the daily-index
backfill (an SEC outage of half an hour, or SEC's 10-minute rate-limit block, no longer spends every try); a record
pass whose feed failed counts its retried rows beside the feed's error; a decision that raised is closed `failed` and
run again a minute later while it is live, then every 10 minutes (a cut one goes on at the next turn; one cut and then
failing waits as a failed one). Verdicts are asked from
07:30 ET because a session's universe is fixed then
(its tickers copy is the latest before 07:30 ET), with the decision's own code (`decide_open` / `decide_close`
`ask_only`), so the 09:15 decision finds them stored and asks none. Verdicts wait while the House is paused (`PAUSE`) and
over the lane's own line of a day: from release 1019c the lower of `events.verdict_usd_day` ($3, from release
1019b's second review: the goal's cost rule, metered compute at most $5 a day plus half the trailing week's realized
net profit, with the House box at about $1.29 a day) and budget rule 3's
allowance for the lane (league/ops/budget.py `lane_allowance`: the Claude meter's lane part in `<state>/budget.json`,
$3 a day at no profit, half as much again after a day held at it, never more than the cap's room, 0 under the cap
breach hold; `lane.json` `verdict_line_usd`), held on the UTC day (00:00-24:00 UTC, 20:00 ET to 20:00 ET in summer),
the day every other line of the rule is held and the cap judged on (New York days before 1019c): a READ event then
waits, as PREREG-EVL-1 section 4 lets it. The lane writes a receipt
for every task in the store (their contract with the House is league/events/__init__.py, THE EVENT LANE'S RECEIPTS) and
its health to `<state>/events/lane.json`. How to switch it on, migrate the desktop's store (`scripts/evl_migrate.py`)
and stop it: [operations](operations.md), "The event lane on the House".

## Alarms and the daily report (release 1019c)

The House's `stall` job (every 30 minutes, league/ops/stall.py) judges the lane's PROGRESS from its store, read-only
(league/ops/evl_health.py), never a receipt's status alone; each cause is INFO (no owner step) and goes in the stall
mail at its pace:

| cause | stands when |
|---|---|
| `evl_record` | no clean record pass in 30 minutes: one finished `ok` whose 8-K, Form 4 and news reads ran without error (the failing feeds are named) |
| `evl_decide` | a session's open or close decision not made in its 10-minute window (missing, failed, cut, unfinished or finished late); one decided later still stands, its auction missed |
| `evl_verdicts` | verdicts a decision needs (its receipt's tally `verdicts: {needed, answered}`, the close decision's reading programs included) unanswered 15 minutes past it; the day's verdict dollars and the lane's line in the numbers |
| `evl_score` | intents due by the latest session still `planned` or `entered` at 23:00 ET (an exit the tape showed absent waits by design and is counted apart) |
| `evl_fills` | the real fills off the shadow's own auction prints by more than 15 bp either way (worse or better, said), the signed mean of a side over the last 20 priced fills (the House's event twins) |
| `cap_breach` | today's measured metered compute so far, or yesterday's, over the cap the rule set for that UTC day (league/ops/metered.py: the meters themselves), or a meter unread for 6 hours (the cap cannot be judged); while today is over it, the cap breach hold (`cap-hold.json`) holds the lane's verdict line, Sail research and the Claude roles at 0 until 00:00 UTC |

None is judged while `<state>/events/STOP` stands, nor for 30 minutes after it goes; `evl_verdicts` is not judged while
the House's `PAUSE` stands (no verdict is asked then).

THE DAILY ONE-SCREEN REPORT goes to the owner by mail once a New York day, after the lane's own nightly report job
(league/ops/daily_report.py, the gateway's `report` notice): account-shown profit first and Net after the measured
metered costs beside it, by program and band (to date as far as `metered.json` covers it: "since <day>, partly
measured" when it began after the first fill); the measured costs of the UTC day of the same date against its cap with
its lines labelled the allowance; the events by family, the verdicts, the shadow intents by program and version, the real fills (buys, sells,
fees, the fill gap against the auction prints); for each version 2 program its band, settled n (shadow TRADABLE and real), next look and events to go, its
market-direction share and benchmark mean and its same-risk buy-and-hold ("n/a until real fills"); the records and
controls in one line, the expected false passes and the alarms open. Figures only: no headline, document text, symbol
or price leaves the House. How to read it: [operations](operations.md), **THE DAILY ONE-SCREEN REPORT BY MAIL**.

## Real money (release R2, shipped switched on in release 1019b; deployed 21:00Z Oct 19, 2026)

[PREREG-EVL-3](prereg/PREREG-EVL-3.md) (the owner's goal as re-set at 05:15Z Oct 19, 2026): VERSION 2 of each of the
nine seatable programs trades real money from its first event at LEARNING size, with the full-size shadow beside it;
version 1 is a shadow record and never trades. [PREREG-EVL-4](prereg/PREREG-EVL-4.md)'s three seatable programs trade
at version 1 the same way, after the nine in ROOM's order (above: "PREREG-EVL-4"). The bands are the lane's (its store's `bands` table: learning from birth,
Probe after a passed look, Sized, retired), counted in settled events from its looks and the real fills the House writes
back (`real_fills`). The House trades them through its EquityBook (its event kind: league/equity/live.py `_event_step`,
the rules in `book.py`), on the money rows `equity_money.event` of league/constitution.py: learning 2% of equity a
position (one share at most 5%), Probe 3.5% (A86; one share at most 5%), Sized 10%, at most 8 open a program in each band, the
book-wide 10% a name, whole shares, entries limit-on-open / limit-on-close at 1.25 x the previous SIP close, exits
market-on-close (market-on-open for the three overnight rows) with PREREG-EVL-1 section 5's fallback ladder, open risk
value x max(0.10, 1.65 x sigma60 x sqrt(h)) in the one loss budget ($400 net in any 20 sessions, $800 net in total),
ROOM in the order Sized, Probe, learning, then the tables' order. The real-money decision reads the lane's store, and
only events stored and verdicts answered before its decision time (PREREG-EVL-1 section 3). The old lanes'
`equity_money.enabled` stays False; nothing goes until the gateway's `STOCK_EVENT_BUYS` is on and the auction paper
proof on the practice account has passed its BUY stage (filled, or accepted and ended unfilled at the open: the
practice venue simulates no auction, amendment A68) (release 1019b, deployed 21:00Z Oct 19, 2026, shipped the
gateway's switch `on` and the lane's `events.enabled` true; it was deployed in that order: the gateway, then the
House, then the migration with the desktop's timers stopped). How it runs, is read, is deployed and is rolled back:
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

THE EVENT KIND'S OWN DAY ORDER COUNT (release 1019c, not yet deployed): the kind's auction orders of a day count against
their own line, `equity_money.event.max_orders_day` (150: 2 x the open positions of the live bands, at least 150; nine
programs at learning hold at most 72 lots, a buy and a sale each in one day, 144 orders), and no longer against the
equity book's 60, which the old lanes keep (`order_path.max_orders_day`). An event entry goes only while it and its own
exit leave room for the exit of every event lot not yet sold that day and of every event buy still working that is
sold the same day (an auction buy is no lot until its cross: the open window's buys of an open-entry program are sold
at that day's close), so the line bounds the kind's whole day; an exit is never stopped by a lane's line, only by
the House-wide one (`options_money.order_path.max_orders_day`, 250, every book's orders together), and every ENTRY
meets that one with room left for the options book's exits and every equity exit, its own included (the money
review: without it the open window's buys and their sales could reach the House-wide line together and the close's
sales be refused there). The constitution holds the two equity lines' sum under the House-wide line and the event
line under the gateway's day line (300). Under
release 1019b's one count of 60, entries stopped at about 30 open-entry lots sold the same day: a day of 40 open-entry
learning lots left that day's close entries no room (league/tests/test_events_1019c.py sends all 40 and a Probe close
entry). The row moves the money digest (`285fa7af` -> `055e5313`) and the constitution's (`fd38e4e1` -> `a8d4cbd9`).

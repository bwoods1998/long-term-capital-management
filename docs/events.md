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
- An event counts for a program only when it is knowable after that program's own registration time. A change to a
  registered program is a new version with a new registration time. Expected false passes over both files: 0.9
  (0.10 x 9 seatable versions).

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

Records (never seated): EVL-ERN-READ-O3, EVL-INS-CLUSTER-O5 (file 1); EVL-INS-BUY-O5, EVL-ERN-REACT-READ-C1,
EVL-ERN-READ3-O1 (file 2). Controls (what the verdicts add): EVL-CTRL-ERN-ALL-O1, EVL-CTRL-8K-ALL-O1,
EVL-CTRL-NEWS-ALL-O1 (file 1), EVL-CTRL-NEWS-DAY-ON (file 2). File 2's programs are not filled when the entry auction is
above 1.25 x the previous close (real money's limit).

## Bands (version 2: real money)

| band | size | how a program gets there |
|---|---|---|
| learning | 2% of equity a position (whole shares; one share up to 5%), at most 8 open | from its first event |
| probe | 5%, at most 6 open | the first decision after a passed look |
| sized | 10%, at most 8 open | >= 150 settled real-money events at Probe size or above, 80% session-block lower bound > 0 |
| retired | none (shadow only) | a held look with mean a < 0 and the reversed sign-flip p <= 0.05 |

Back to learning from probe or sized: the last 50 Probe+ events lost more than $150 net, or the last 100 have a
negative mean. LOOKS (version 2): at 60, 90, 135, 200, 300, 450, 675, 1000, 1500 and 2250 settled TRADABLE events,
each needing at least 40 issuers and 8 session blocks; thresholds first reached at the same close are one look; the
skew check starts and caps at 0.018 (A65). Room when short: Sized, then Probe, then learning. The lane writes the
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
detail), and the band move a look makes (Probe, retired) is written in the look's own transaction.

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
next record passes, six passes in all, then left to the daily-index backfill; a decision that raised is closed
`failed` and run again a minute later while it is live (a cut one goes on at the next turn). Verdicts are asked from
07:30 ET because a session's universe is fixed then
(its tickers copy is the latest before 07:30 ET), with the decision's own code (`decide_open` / `decide_close`
`ask_only`), so the 09:15 decision finds them stored and asks none. Verdicts wait while the House is paused (`PAUSE`) and
over the lane's own line (`events.verdict_usd_day`, $5 a New York day): a READ event then waits, as PREREG-EVL-1
section 4 lets it. The lane writes a receipt for every task in the store and its health to `<state>/events/lane.json`.
How to switch it on, migrate the desktop's store (`scripts/evl_migrate.py`) and stop it:
[operations](operations.md), "The event lane on the House".

## Real money (release R2, shipped switched on in release 1019b; not yet deployed)

[PREREG-EVL-3](prereg/PREREG-EVL-3.md) (the owner's goal as re-set at 05:15Z Oct 19, 2026): VERSION 2 of each of the
nine seatable programs trades real money from its first event at LEARNING size, with the full-size shadow beside it;
version 1 is a shadow record and never trades. The bands are the lane's (its store's `bands` table: learning from birth,
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
proof on the practice account has passed its BUY stage (release 1019b ships the gateway's switch `on` and the lane's
`events.enabled` true; deploy order: the gateway, then the House, then the migration with the desktop's timers
stopped). How it runs, is read, is deployed and is rolled back:
[operations.md](operations.md), **The event lane's real money on the House (release R2)**. Each real fill is set beside
the shadow's own auction price, per side (league/ops/twins.py `event_twin`).

How the book meets the auctions (release 1019b's review): each decision plans its EXITS before it reads anything of the
lane, and a failing decision never stops that minute's sends (sales first); two programs' lots of one name due at one
auction are both sold in its cross (the book's own sales at that auction do not stop each other; anything else working
on the name does); the equity day's order count keeps one order for each event lot's exit and none once its sale is
sent; the close decision reads each name's T29 minute once, all the day's names in batched requests, and the lane's
own 15:30 marks are used where they exist (on the House the lane's close decision runs a minute after the book's); a
gateway refusal that it holds no eligible list of the day publishes the list again.

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
- [PREREG-EVL-5](prereg/PREREG-EVL-5.md), registered 2026-10-21T21:26:21Z (tag `prereg-evl-5`, commit `b73f205f`, the
  captain's hand births under the same goal; amendment A92, the latest of the commit's time, GitHub's activity time for
  the branch push and the pushing client's clock after the tag push returned): three NEW seatable programs (an earnings
  fall, a muted earnings read, a second news night), each entering at D's CLOSE and exiting at the next session's OPEN,
  at PREREG-EVL-3's learning band from birth (VERSION 1 their seating version), and one control; judged by
  PREREG-EVL-3's screen unchanged ("PREREG-EVL-5" below). Code in release 1019g (`rel/1019g`: release 1019f with
  `feat/evl-5` merged in, A94), live since 05:36Z Oct 22, 2026 (House `20261022T053527Z-05c3dc2f4422`, main
  `b374d862`, PR 595; A108).
- An event counts for a program only when it is knowable after that program's own registration time. A change to a
  registered program is a new version with a new registration time. Expected false passes: 1.5 (0.10 x 15 seatable
  versions: the nine version 2 rows, PREREG-EVL-4's three and PREREG-EVL-5's three) of the lane's stated lifetime
  budget of 3.0 (PREREG-EVL-4 section 3, PREREG-EVL-5 section 3; 1.5 left for later births with none registered
  before PREREG-EVL-5, each seatable birth 0.10, as SEATING sums them).
- [R3's births](#births-r3-live-since-release-1019e) (goal-2026-10-19/R3-SPEC.md): programs born from outcome-free
  facts by the architect (Claude Opus 5.5 from release 1019h, the captain's A109; Claude Haiku 4.5 before it) or the
  captain, each registered as one line of `docs/births/<night>.jsonl`,
  judged by PREREG-EVL-3's screen unchanged, rationed by the lane's stated false-pass budget (A81: 0.10 a seatable
  birth, 3.0 in all, counted from SEATING's own sum: 1.5 used by PREREG-EVL-1 to -5's fifteen seatable versions, plus
  0.10 for each seatable birth registered; at most 3 a night: at most fifteen seatable births).

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
| EVL-ERN-DROP-ON | 5 | yes (version 1) | ERN(D): an earnings 8-K of D's close window, issuer not TAKEN AT D'S CLOSE BY AN EARLIER ROW, move <= -4% at T29 (ranked by the fall) | D's close | next OPEN |
| EVL-ERN-UNDER-ON | 5 | yes (version 1) | the same filings, issuer also with no fall, move above -4% and below +4% at T29 and stored PROMPT-DOC score >= 2 (ranked by the score, +0.5 when guidance "raised") | D's close | next OPEN |
| EVL-NEWS-NIGHT2-ON | 5 | yes (version 1) | the attention articles of P (single-stock news after P''s close and by T29 of P), issuer with NO NEW INFORMATION on D, D's 09:30 gap >= +2% (ranked by it) | D's close | next OPEN |

Records (never seated): EVL-ERN-READ-O3, EVL-INS-CLUSTER-O5 (file 1); EVL-INS-BUY-O5, EVL-ERN-REACT-READ-C1,
EVL-ERN-READ3-O1 (file 2). Controls (what the verdicts add): EVL-CTRL-ERN-ALL-O1, EVL-CTRL-8K-ALL-O1,
EVL-CTRL-NEWS-ALL-O1 (file 1), EVL-CTRL-NEWS-DAY-ON (file 2), EVL-CTRL-8K-ON and EVL-CTRL-NEWSPM-ON (file 4),
EVL-CTRL-ERN-UNDER-ON (file 5). File 2's, file 4's and file 5's programs (and every version 2) are not filled when the
entry auction is above 1.25 x the previous close (real money's limit).

## Bands (the seating versions: real money)

The versions that may seat (`programs.Program.can_seat`, the one gate in the lane and the House's book): version 2 of
the nine seatable programs of files 1 and 2 (PREREG-EVL-3), version 1 of PREREG-EVL-4's three and version 1 of
PREREG-EVL-5's three. Version 1 of the earlier files' programs, every record and every control never seat.

| band | size | how a program gets there |
|---|---|---|
| learning | 2% of equity a position (whole shares; one share up to 5%), at most 8 open | from its first event |
| probe | 3.5% (whole shares, rounded up to Done's size bar inside 5% (A97, release 1019h); one share up to 5%), at most 6 open (the captain's A86 REVISED; PREREG-EVL-3's 5% before) | the first decision after a passed look |
| sized | 10%, at most 8 open | >= 150 settled real-money events at Probe size or above, 80% session-block lower bound > 0 |
| retired | none (shadow only) | a held look with mean a < 0 and the reversed sign-flip p <= 0.05 |

THE PROBE BAND'S SIZE (the captain's A86 REVISED, 20:30Z Oct 21, 2026, replacing A86's proposal, decided before any
Probe event; branch `fix/a86-probe-more-smaller`, integrated in release 1019f ONLY in this form): cash at the auction
binds first at Probe, so PREREG-EVL-3's 5% with at most 6 open fitted about 9-11 Probe buys an auction; at 3.5%, still
at most 6 open, smaller Probe lots fit the same cash, and Done counts Probe events. `position_share.probe` 0.035 sits
inside its bound [0, 0.05] (the pre-registered value is the loose end: a change may only trade less); `max_open.probe`
stays 6, its bound [0, 6] (A86's proposed 8 lay outside it and would have failed the event kind closed; a slot rise
needs a reviewed bounds change and a new version, not taken). One share at Probe (the 3.5% target buys no whole share)
goes only when it is at most 5% of equity, as at learning (`one_share_max.probe` 0.05, its own bounds row [0, 0.05],
held under the name's wall): a Probe program's dollars are at most 6 x 3.5% = 21% of equity at target (30% before) and
6 x 5% = 30% in the worst case (6 lots up to the 10% wall, 60%, before). ITS COSTS, stated: Probe events carry 30%
fewer dollars each; total Probe dollars are unchanged while cash binds; Done's "Probe size" is 3.5% from here; a name
whose one share at the limit is above 5% of equity is skipped at Probe, where PREREG-EVL-1 bought one share (the shadow
keeps it). It is money management inside the frozen envelope, not a new version: no program's rule, judge, look,
alpha, false-positive rate or Done rule moves (looks count shadow events, which do not depend on size), and the
screen's cost allowance keeps its 5% notional.

AT DONE'S SIZE (S2, the captain's A97 and A100, release 1019h, before any promotion; `feat/done-speed`): Done counts a
Probe+ buy only when the dollars its send asked reach 0.8 of its band target (`done.at_size`), and whole-share flooring
left about a third of Probe buys under that bar (a $40 name at E $1,898: one share, $40, of a $66.43 target). A Probe or
Sized buy that flooring took under the bar now buys the fewest whole shares that reach it (`book.round_up`, judged by
the Done reader's own comparison), the bar being the band's money row `equity_money.event.reach_bar` (0.8, pinned equal
to the Done reader's line; bound 0-0.8; 0 is release 1019f's floor rounding, the tighten-only switch), when those shares are at most the band's frozen PREREG-EVL-1 section 8 target (the loose
end of its `position_share` bounds row: Probe 5%, Sized 10%) of the walls' equity, only when rounding (not a cap) caused
the shortfall, and only when `size_entry` asked again for them still gives every share (the name wall, the 100% book,
cash, the loss budget at the lot's weight). So a Probe buy is never more shares than PREREG-EVL-1 section 8's own count
at its 5% target, and a Sized buy never rounds up (its envelope is its target). At E $1,898: $40 -> 2 shares ($80), $47
-> 2 ($94), $50 -> 1 (two would be $100, over 5%: under size, reported beside), $90 -> 1 (one share), $96 skipped. A cap
that refuses the round-up is the buy's recorded binding (the report counts the cut); `target_usd` stays the band's
target; learning never rounds up. A85's reservation stays share x E a buy, so a round-up the reservation's cash leaves
short is refused and recorded, never a wall moved. While a PREREG-EVL-5 Probe buy waits for the lane's close decision,
`HeldAhead` keeps its rounded-up dollars from the buys after it ($80, not $40, at a $40 limit and E $2,000: the round-up
sits inside the sizing its dry run reads). The two rows move both digests (money `c2f0a478` -> `8e63ce64`,
constitution `24f73f18` -> `c3026eba`): the standing grant re-ratifies at the deploy.

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
with the same module's `bands(store)` at each session's first decision, and again at the close decision when the
lane's `band_history` moved since (release 1019f, below: "The screen after the open"), and writes every real fill to
`real_fills` with its `record_fill` (a posted fee updates its row; from release 1019f a buy's row also keeps its band
target and what cut it, below: "THE PROBE SIZE'S RECORD"); on the House the lane reviews the real fills after each
night's screen (`bands.review`: demotion and Sized), whatever the screen did.

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

THE FAST PATH TO A FINAL RECORD (the captain's amendment A69, release 1019c; (i) as A84 reads it, release 1019f): the
three sessions' wait is for late data, so when there is provably none a close X is final for a program as soon as the
session after X has had its open decision, if (i) EACH FEED WAS READ WHOLE from the start of the earliest window that
feeds X's decisions (09:00 ET of the session before X, never before the program's registration) through that open
decision: as the captain's A84 reads it (19:58Z Oct 21, 2026, recorded before any look; release 1019f), for each of the
8-K, Form 4 and news feeds separately, that feed's CLEAN reads (a record pass finished `ok` whose read of it has no
`error`; the 8-K read with the tickers copy read, the news read not cut) at most 15 minutes apart
(`screen.FAST_RECORD_GAP`) from before that start through that decision; a pass whose read of a feed errored, was cut or
had no tickers copy is a missing read of THAT feed, not a broken span, and a pass that raised or never finished reads
none (a pass that never ran proves nothing). Sound because EDGAR's current feeds page back to the newest known accession
and the news read restarts from the newest stored less 5 minutes, so a clean read after a missing one recovers what it
missed. (A69 first read "every pass whole": SEC's getcurrent feed times out in about four passes a night, 45 seconds
each and a clean pass 2-4 minutes later, so no span was ever whole and every look waited A66's three sessions;
`screen._fast_passes`, `_feed_problems`); (ii) no filing knowable in those windows that the lane would fetch is still
`listed` or `failed` (a failed one, a listed Form 4, a listed 8-K of a filer in X's tickers copy; an unlisted filer's
8-K is never fetched and never an event of X); (iii) the daily-index backfill of every weekday from the session before X
through X has run, and, when X is an SEC holiday NYSE trades (Columbus Day, Veterans Day), through the next weekday EDGAR
is open: EDGAR dates an 8-K accepted after 17:30 ET as filed on the next day it is open, so the 8-Ks of the holiday's
eve are in that day's index (`screen.index_through`; release 1019f's review: A66's reach reads it the same way); and (iv) every decision of the program's entry kind through X is made (`ok`, or `pending` only on
another program's verdicts) and the next session's open decision is made. Otherwise A66's rules apply unchanged, and
finality stays contiguous: X is final by the fast path only when every session before it is final. The record receipts
the House already writes prove (i) (league/events/house.py `_record`: a failed feed read is an `error` in its part of
the summary, a news read cut short is `cut`, a pass that raised is `failed`, one that never finished stays `running`),
so no new record was added. A clean record is final one session after its close, about two sessions sooner than A66's;
the as-of date, the record and the look are the same. When a seatable program's final record falls more than one session
behind what A69 allows, the stall job's `evl_final` says so, naming the program and the judge's why (Alarms, below).

THE SCREEN AFTER THE OPEN (release 1019f, live since 05:36Z Oct 22, 2026 in release 1019g; the audit of the live House,
"bands move a session late"):
the judge makes a close final at an OPEN decision (A69's fast path once the next session's open decision is made; A66's
three sessions likewise move at an open), and the intents a look as of that close covers were settled by that close's
own score, but the lane ran the screen only after the 20:30 ET score and the House's book read the bands once a
session, at its first decision: a look the open made final was written that evening, so a close-entry program reached
Probe at the next session's close instead of that day's. Now, on the House, from 09:40 ET of a session whose open
decision is made (its receipt `ok` or `pending`) until 5 minutes before its close decision, the lane reads the final
horizon (`screen.final_until`) of every seating version at most every 10 minutes, and when any differs from the
horizons the last screen receipt kept (the nightly's or the morning's) it runs the screen's looks of the seating
versions (`house.py` `_screen_open`, receipt `screen-open`); the band review of the real fills (demotion, Sized) stays
nightly. A look is written once (`write_look`, INSERT OR IGNORE; version 2 resumes after the last look on record) and
its band move in its own transaction, whichever run writes it, so the night's screen writes nothing the morning wrote,
and the same horizons are never screened twice. The House's book reads the bands again at the close decision when the
lane's band mark (`book.band_mark`: the newest `band_history` id) is not the one its morning sync kept (kv
`eq_event_band_mark`; an unreadable mark reads them again, fail closed): PREREG-EVL-3 section 2's "Probe from the first
decision after a passed look" is that session's close. The decision's summary says why it synced (`band_sync`: `first`,
or `moved` at the close). No rule moves: the judge says when a close is final; the House reads it sooner. Open-entry
programs still trade a morning look from the next session's open, the first decision after it.

THE NIGHT IS THE SESSION'S (release 1019f): the nightly score, screen and report are keyed on the session, not the
calendar day. The night is today's session from 20:30 ET, else the session before today: a score that ran past midnight
ET goes on as that session's night (each due intent still tried once) and that session's screen and report follow the
next day; a House down that evening makes the night's jobs the next morning (no screen within 5 minutes of a decision).
Each screen receipt keeps the horizons it read (`horizons`), the looks it wrote (`looks`) and why each look waits
(`waits`: program, version, k, why).

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
  VERDICT OF ITS OWN (EVL-NEWS-READ-O1 asks it for its open decision of D) and waits for it. Once a written look of
  EVL-NEWS-READ-O1's group freezes that group over D, its open decision asks nothing, so D's close decision asks the
  verdicts these rows need itself (A83 (3)(ii), release 1019e: no new prompt, the same stored PROMPT-NEWS and the article
  rendered as the open decision renders it, one verdict an event, stored once; the frozen group is still asked nothing
  and written nothing).
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
no call of a pass could answer backs off (`_look`). THIS FILE'S PART FAILS ALONE (A83 (3)(i), release 1019e): an
exception in it (its reads, `_skip_excluded`, the 15:30 marks, its verdicts, its intents) that is not the task's time
bound finishes the close decision with the earlier rows' results (their receipt `ok`, or `pending` on their own
verdicts), the error in the summary's `evl4_error` (the House warns), and none of this file's programs named in it, so
the judge reads that close as made without their rows and their own decision (`decide-close-evl4`, below) or the next
whole re-decision decides them; the earlier rows' looks never wait on it. A time bound stops the whole task as before
(the next turn decides the close again), and a failure of their own decision is that decision's. THE PROOF that no earlier program changes: league/tests/
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

## PREREG-EVL-5: three programs from births (a fall, a muted read, a second night), seatable at version 1

[PREREG-EVL-5](prereg/PREREG-EVL-5.md) (registered 2026-10-21T21:26:21Z, A92) holds the two earnings nights the earlier
overnight rows leave (after a large fall, and after a positive release the price has not followed) and the SECOND night
after a news attention day. For entry session D, P the session before it and P' the one before P (league/events/
programs.py; every set that skips an issuer read with NO registration floor, the events each program's own, knowable
after 21:26:21Z Oct 21):

- ERN(D) FILINGS: the fetched 8-Ks (form exactly `8-K`) of D's close window with item 2.02 (`filings_window`). THE
  REACTION of one: C1's (the T29 minute close of D over the raw daily close of the last session that closed before its
  acceptance); none when a price is missing (not taken). DAY(D): PREREG-EVL-2's day-news window of D (single-symbol,
  the issuer's eligible ticker, after 09:00 ET and by T29, the non-live exclusion applied); the DAY-NEWS REACTION of an
  issuer: the T29 close of D over the universe row's previous close.
- TAKEN AT D'S CLOSE BY AN EARLIER ROW (`taken_close_5`): an issuer (a) with an ERN(D) filing whose reaction is >= 1.04,
  (b) with a DAY(D) article whose stored PROMPT-NEWS verdict is `ok` with score >= 2, or (c) in DAY(D) with a day-news
  reaction >= 1.04; an answer `unparsed`, `refused` or under 2 is no (b). A DAY(D) article with NO stored answer makes
  the issuer's events WAIT in the shadow (the program's decision is `pending`) and skips the issuer in real money.
- EVL-ERN-DROP-ON: an ERN(D) filing of an eligible issuer not TAKEN, reaction <= 0.96 (no model), the earliest knowable
  filing the rule takes, ranked by the fall (1 - reaction), then ADV. EVL-ERN-UNDER-ON: the same filings of issuers with
  NO ERN(D) filing whose reaction is <= 0.96 (`dropped_ciks`), reaction above 0.96 and below 1.04 and the stored
  PROMPT-DOC verdict of `8k:<accession>` `ok` with score >= 2 (the very verdict EVL-ERN-READ-O1 and
  EVL-ERN-REACT-READ-C1 read; a TEXT under 200 characters has none), one an issuer (the highest score, then the
  earliest), ranked by the score plus 0.5 when its guidance is "raised". EVL-CTRL-ERN-UNDER-ON: every such muted filing,
  with or without a verdict, by the same order (a filing with no stored `ok` score after every one with it); it waits for
  the scores it ranks by, never for a TEXT that gets none. The three reaction ranges part every ERN(D) filing.
- THE ATTENTION ARTICLES OF P (`attention_window`): single-symbol articles, that symbol the issuer's eligible ticker for D,
  knowable after P''s close and at or before T29 of P. NO NEW INFORMATION on D (`no_new_info`): (i) no article of ANY
  source with ANY number of symbols naming a ticker SEC's copy of D maps to the issuer, knowable after T29 of P and at or
  before D's close decision (`news_named`: a live article counts; a backfilled one only when edited at most 10 minutes
  after its creation, exactly as `news_rows`); (ii) no 8-K of the issuer, any items, knowable at or after P''s close
  decision and before D's (the close windows of P and of D); (iii) no Form 4 of the issuer with PREREG-EVL-2's INSIDER
  BUY knowable at or after 09:00 ET of P and before D's close decision (`ins_buys_window`, `ins_buys`' rule).
  EVL-NEWS-NIGHT2-ON: the issuer's earliest attention article knowable after the registration time (event `news:<id>`),
  taken when THE GAP (the open of D's regular-session SIP 1-minute bar starting at 09:30:00 ET, raw, over P's close: the
  universe row's previous close) is >= 1.02 (no model; no trade in that minute: no gap, not taken), ranked by the gap.
- Each enters at D's close (decided at the close - 14 minutes) and exits at the next session's open auction, with the
  fallback ladder; the limit at entry (1.25 x the previous close) binds shadow and real alike. The three share no
  (issuer, D) with one another and no (issuer, entry, exit) with any seatable program of files 1 to 4.
- NO NEW PROMPT AND NO SECOND VERDICT (section 1.2): a PROMPT-DOC verdict of an eligible ERN(D) filing, or a PROMPT-NEWS
  verdict of a DAY(D) article, that these rows read and no row has stored by their decision is asked by it with the same
  event id, prompt and rendering as the earlier row that reads it (`doc_verdict`, `news_verdict`), stored once; the asks
  are in the decision's verdict tally. A verdict already stored is never asked again.
- THE SCREEN is PREREG-EVL-3's with version 1 in place of version 2 (seed strings `{id}|v1|look{k}`); EVL-ERN-UNDER-ON
  must beat EVL-CTRL-ERN-UNDER-ON over its own block sessions; the other two have no control condition. THE FINAL RECORD
  for these rows (section 2; `screen._fast_block` for prereg 5 only): A69's span begins at P''s close decision (where the
  close window of P, which (ii) reads, begins; the attention articles begin at P''s close), with no registration floor
  (the skips it feeds carry none: the reading that waits), A74 (3)'s daily-index backfill must have run for every weekday
  from P' through X, and the passes are judged by `screen._fast_passes` from before that start through the span's end
  by A84's per-feed clean reads (release 1019g carries both: A84 changed `_fast_passes` and `_feed_problems`, this file
  `_fast_block`, and they merged without a conflict): a pass that missed a feed inside that span, with clean reads of
  the feed at most 15 minutes apart around it, is a missing read, not a broken span; a feed with no clean read for
  longer breaks the span and the why names the feed (league/tests/test_events_1019g.py `FinalRecord`); otherwise A66's
  wait. A close decided at or before 21:26:21Z Oct 21 is made for them.
- REAL MONEY (section 1.3; league/events/book.py `rows_5`, `picks`): the three seat at learning from birth (2% of equity,
  whole shares, one share up to 5%, at most 8 open), in ROOM's order after PREREG-EVL-4's rows and before R3's births.
  A real-money decision is the shadow rule over the rows STORED, and the verdicts ANSWERED, before D's close decision
  time: TAKEN, the <= 0.96 skip and NO NEW INFORMATION read from those rows (NO NEW INFORMATION's (i) maps symbols by
  the lane's tickers copy of D, `lane_tickers`), and a DAY(D) article with no PROMPT-NEWS answer by then skips its
  issuer. The reactions are the book's (`reaction_reader`); the gap is the lane's stored 09:30 mark (label `0930`, made
  by the pre-passes and the decisions; a stored minute with no trade is no gap), else the book's own batched read of
  that minute (`gap_reader`, league/equity/live.py `_event_open_minutes`; a price it cannot read is not bought). EVL-ERN-DROP-ON and
  EVL-ERN-UNDER-ON NEVER BUY for a filing knowable at or after 09:00 ET of D whose stored PROMPT-DOC verdict is `ok`
  with score >= 2, or `ok` with score >= 1 and guidance "raised", or not yet answered, at the decision time
  (`next_open_event` with `raised`, `RAISED_GUARD`: EVL-ERN-READ-O1's or EVL-ERN-GUIDE-O1's event at the next open;
  PREREG-EVL-4's guard is unchanged); for UNDER that is every such filing. The sale gate keeps them out of a name an
  event lot sells at the same close. WITH RELEASE 1019f (release 1019g): A85's tiers, round-robin and send order place
  them after PREREG-EVL-4's rows and before the births (at Probe or Sized they round-robin with the earlier files' rows,
  each pass in the tables' order); a learning buy of theirs at D's close leaves the next open's PREREG Probe and Sized
  programs A85's reservation, and at Probe or Sized they are reserved for by the open's learning buys; A86 REVISED
  moves only Probe (3.5% of E, one share up to 5%, six open): their learning rows are as frozen (2%, one share up to 5%,
  eight open). ROOM'S ORDER WHILE THEIR BUYS WAIT (release 1019g; the next item): the
  book's close decision waits only 60 s for the lane's, so a buy of these rows can wait for `part_hold` while the buys
  after it in A85's send order go (a learning buy behind one at Probe, a birth behind one at any band); the waiting buy
  keeps its room from them (`HeldAhead`), sized dry with A85's reservation and A86's Probe size in it, and a dry sizing
  writes no release 1019f record (`target_usd`, `binding`, `sized_usd` stay the sizing a send reads). (Release 1019g's
  first build had its own form of this, `ahead`; its fix round kept `HeldAhead` alone.)
- THE EARLIER ROWS' DECISION COMES FIRST (section 1.3; league/events/run.py `decide_close`): the part that decides these
  rows runs LAST, after every earlier row and PREREG-EVL-4's part, under its own time bound (`EVL5_BUDGET` 45 s, never
  past the close task's own bound less `EVL5_FINISH` 15 s: `part_until`, `bounded`, `PartDeadline`, which is not the
  task's `Deadline`). Its bound's expiry, or any failure in it, is its own: the receipt finishes with the earlier rows'
  results (PREREG-EVL-1 to -4 and the births, whole), the error in the summary's `evl5_error` (the House warns), none of
  these rows named, so the judge reads that close as made without them and `decide-close-evl5` decides them later by
  themselves; and REAL MONEY NEVER TRADES THAT CLOSE FOR THEM: their buys are planned at the book's close decision and
  go only once the lane's first finished close decision of D names their program (`book.part_hold`; a buy waits while
  there is none, sent again each minute of the window, and is refused when it does not name it). The task's own bound
  inside the part stops the whole task as before (the next turn decides the close again). ROOM HOLDS WHILE IT WAITS
  (release 1019g's money review): a waiting buy that every other gate lets go keeps its room from every buy after it in
  ROOM's order at that auction (league/equity/live.py `HeldAhead`, `_event_keep_room`: its whole shares at its limit as
  `_size_event` would size them now, out of their cash, invested room and name wall, those at its own weight out of
  their loss budget, and its send and its exit out of the event line and the House-wide line, `_count_refusal`'s
  `held`), so R3's births, and every learning row behind one of these rows at Probe or Sized, never take what ROOM gives
  it; a later buy that fits only without that room waits too (`HELD_ROOM`) instead of being refused. Made afresh each
  minute: a buy the lane's decision names, or never will, keeps nothing the next. ONCE THE LANE'S RECEIPT IS OVERDUE
  (THE CAPTAIN'S DECISION on PREREG-EVL-5's money re-review, its option 1; release 1019h; league/equity/live.py
  `HELD_OVERDUE_S`, `HeldAhead.for_buy`, league/events/book.py `room_free_overdue`): from one book minute before the close
  window's cut-off (15:48:00 ET on a full day, while the lane's close decision is still unfinished) a waiting buy keeps
  its room only from R3's births after it (and these rows' own), never from a row of PREREG-EVL-1 to -4: so the cost of
  a late part (its 45 s bound, a failure) never falls on an earlier file's real money at that minute, as it could once a
  row of this file reached Probe (a learning PREREG-EVL-1 row behind it ended unsent). Before that minute ROOM holds as
  above. THE LANE STARTS THAT DECISION AT ITS
  TIME (league/events/house.py `HOLD_LEAD`): a turn from 150 s before the live close decision (the close decision + a
  minute, 15:47:00 ET) keeps going, running what falls due and waiting between, and starts the decision at 15:47:00, not
  at the next House publish; `due()` looks again no later than the lead's start. INSIDE THE LEAD NO OTHER DECISION
  STARTS (release 1019g, PREREG-EVL-5's money re-review; `_lead`): a decision runs with the whole 150 s budget, never
  bounded by the next decision as the other tasks are, so a missed, cut, pending or failed decision (today's
  open included), the hourly re-decision and the rows' own backfill decisions (`decide-close-evl4`, `decide-close-evl5`, the
  births') wait until a run of the live one has finished `ok` or `pending` (release 1019h, `LEAD_ENDS`: the book's own
  reading of a made decision; release 1019g ended the lead at any receipt, so after one failed live run another decision
  could start with its whole budget and push the retry past the cut-off), and then run whole. A FAILED LIVE RUN (a
  gateway 429, say) keeps the lead: the turn keeps going (a task that raises inside the lead never ends it), no other
  decision starts before the run's retry (its start + `DECIDE_RETRY`, a minute), every other task is bounded to end 5 s
  before that retry (`_deadline`, `_live_next`), and the held turn starts the retry at its time (`_close_hold`), so it
  lands before the book's 15:49:00 cut-off when it can; the lead ends at the latest once the decision is no longer live
  (10 minutes after its time). A bound is checked before each network read, so a task's last read (the gateway's timeout
  is 45 s) can return after it: a task that returns at or after 15:47:00 never ends the turn while the live decision is
  owed (not made, still live): the turn starts it at once (`_close_owed`).
- THE PRE-PASS (section 1.3): EVL-NEWS-NIGHT2-ON's heavy reads (its attention articles of P, (ii) and (iii) so far, the
  eligibility of the issuers that survive them by the live rule, and their 09:30 minutes, `_marks_0930`, batched: A
  BATCH STORES ONLY A PRICE, so an empty or partial answer stores nothing and removes nothing, PREREG-EVL-1 section 3;
  a decision, never a pre-pass, reads each survivor still unmarked BY ITSELF once over 09:30-09:35 ET and stores "no
  trade" only when the tape served the name, a later minute's bar with none at 09:30; an answer with no bar stores
  nothing, no gap at that decision, and the next decision reads it again) are
  made by the session's close verdict pre-passes (`decide_close` with `ask_only`, the same part under `EVL5_PRE_BUDGET`
  60 s) from 09:47 ET of D (`pre_from`: the 09:30 bar on the Basic plan's tape), each stored as it is read, meta
  `evl5:pre:<day>` ({cut, survivors, ...}) written last; inside the last 30 minutes only once the earlier rows'
  verdicts are all stored, and the House schedules it (`house._pre_due`). The close decision reads every window whole
  from the store (the pre-pass's reads and what came after its cut: the tails of (i) to (iii) and any attention article
  stored late) and the network reads the pre-pass made as stored (eligibility results, marks), so it decides exactly
  what one computation at the close decides (league/tests/test_events_evl5.py `ThePrePass`); its summary's `evl5`
  counts the funnels and `pre` what the close added and removed. A75's known edge, restated: the pre-pass's live
  checks become the session's one eligibility result for every program (A70 (8)).
- THE RECORD BEFORE THE RELEASE (section 3): every close from 21:26:21Z Oct 21 that a release without these rows
  decided (releases 1019e and 1019f), and every later close whose part failed or ran past its bound, gets these rows
  decided BY THEMSELVES, once, oldest first, as a backfill (`decide_close` with `evl5_only`, receipt
  `decide-close-evl5:<day>`, `screen.made_without(prereg=5)`): the House's lane for each such close its hourly
  re-decision no longer reaches (`house._refill_redecide`, `_five`; a close it still reaches is decided again whole),
  and the CLI's `catchup` (or `decide-close --day D --evl5-only`). No earlier row is decided again; none of those
  events is ever traded. A re-decision marks an unsettled intent of these rows `skipped:taken` when a row stored later
  puts its issuer in TAKEN, the <= 0.96 skip or NO NEW INFORMATION (`_skip_taken_5`, as A75 (2) reads it for file 4).
- WHAT IS COUNTED, NOT PREVENTED (the lane's report, `report.evl5`): each row's funnel at the day's close (ERN(D) issuers
  -> eligible -> TAKEN -> the falls and the muted band; attention issuers -> (i) -> (ii) -> (iii) -> survivors -> eligible
  -> gaps read -> >= 1.02), the closes whose part failed, and section 1.3's two room effects from the House's event book
  (`room_effects`, read-only: this file's buys the event kind's day order line refused, its lots' exits that use the
  next session's line, and the earlier rows' open-entry learning buys at the next open that sizing refused for cash,
  invested or loss-budget room while this file's overnight lots were open), and THE COST OF THE WAIT for the lane's
  close decision (`held_unsent`: this file's buys at the close that ended unsent waiting for it; `room_waited`: the
  later buys that ended unsent waiting for the room kept for them); the House's event book says such a close after it
  ends (`equity.alert`, info; a WARNING when another close of the last five sessions had one too: the lane's close
  decision finishes too late for the window, so read its `decide-close` seconds in `lane.json`; and, release 1019h, a
  WARNING whenever a later buy that ended unsent waiting for that room is a PREREG row, any file's, not a birth's:
  `room_waited_prereg`, `book.prereg_row`); the shadow's
  difference from real money by
  storage time (`late_rows`, `skipped:taken` counted with `skipped:excluded`); an earlier row's buy lost to this file's
  sale at the same auction (the book's `sale_to_later`).
- THE PROOF that no earlier program changes: league/tests/test_events_evl5.py decides a synthetic week
  (league/tests/evl5_world.py: every family of files 1, 2 and 4, two registered births and this file's events) with
  and without these rows, and every earlier program's shadow intents and real-money picks are the same; the same week
  decided by release 1019e's own code gives them too (`python league/tests/evl5_world.py OUT.json`). On release
  1019g's tree the week gives the earlier programs (files 1, 2 and 4 and the two births) the same 126 shadow intents and
  the same real-money picks (28 program-sessions) as release 1019f's and release 1019e's trees; and release 1019f's own
  proof, the House's lane driven through four sessions of invented 8-Ks and news, writes on release 1019g the same 111
  intents, 16 outcomes, 18 verdicts, 9 filings, 12 eligibility rows, 468 decision receipts and earlier programs' final
  records as on release 1019f.

## The code

`league/events/` (standard library only): `store.py` (one SQLite file and a document store; the schema is pinned),
`edgar.py` and `news.py` (the recorders), `calendar.py` (sessions and decision moments), `universe.py` (eligibility),
`verdicts.py` (the recorded Haiku verdicts), `programs.py` (the programs as data rows and their selection rules),
`run.py` (the open and close decisions, backfill), `score.py` (settlement at the auction prints and the exit ladder),
`screen.py` (the judge), `report.py` (the daily one-screen report), `done.py` (the Done reader of the goal V2, a judge),
`house.py` (the lane on the House: its scheduler), `births.py` (R3: the births' grammar, the outcome-free facts, the
validator and its budget, the proposer, the registration), `__main__.py` (the CLI: `record`, `backfill`, `decide-open`,
`decide-close`, `catchup`, `tickers`, `equity`, `score`, `screen`, `report`, `births`, `facts`). The judges
(`programs.py`, `verdicts.py`, `score.py`, `screen.py`) and `docs/prereg/` are behind
`league/ci.py`'s FORBIDDEN wall from release R1: no role changes them and the House's updater never ships one. Release
R2's real-money side: `book.py` (the equity book's event kind's rules: the money rows, the bands, the real-money picks,
the limit, the size target, the open-risk weight, the exit plan, the eligible list) and `proof.py` (the auction paper
proof). Release 1019b adds `bands.py` and the modules holding the rules' inputs: `universe.py` (eligibility, the
benchmark), `calendar.py` (the windows and decision times), `edgar.py` and `news.py` (the knowable lag, the TEXT a
verdict reads), `run.py` (which program gets which rows, the shadow's 15:30 reaction) and `store.py` (the record's
schema); `house.py`, `gw.py` and `report.py` stay outside, so their fixes can ship through the updater. R3 adds
`births.py` behind the wall (the grammar a seated birth's rule is read by, the validator's budget, the facts' wall); the
registered lines under `docs/births/` are data the House appends, never read back from the tree, and stay outside.

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
| - | PREREG-EVL-5's rows decided by themselves (`decide-close-evl5`) for each close a release without them decided, or whose part for them failed or ran past its own bound | from the first turn after the record pass, once each, oldest first | 150 s |
| 2/6 | PREREG-EVL-5's pre-pass: today's close verdict pass, for EVL-NEWS-NIGHT2-ON's heavy reads | from 09:47 ET (D's 09:30 minute on the tape) until meta `evl5:pre:<day>` is stored; once more inside the last 30 minutes once the earlier rows' verdicts are stored | 90 s (the part's own 60 s inside it) |
| 1 | PREREG-EVL-5's hold for the live close decision: a turn from `HOLD_LEAD` (150 s) before it keeps going, runs what falls due but another decision (none starts in the lead; every other task is bounded to end 5 s before the decision), waits between, and starts the decision at 15:47:00 ET, or at once when a task's last read returns after that; release 1019h: the lead ends only when a run of it has finished `ok` or `pending`, so after a failed run the turn keeps going and starts the retry at its time (the run's start + 1 minute) | each session, while PREREG-EVL-5 has programs | at most 40 tasks a turn; the House closing, STOP or a clock that does not move ends it; the lead ends 10 minutes after the decision's time at the latest |
| 4 | nightly, keyed on the session: the account equity, the score, the screen (then the band review of the real fills), the report; the night is the session before today until today's 20:30 ET; then R3's births job (`events.births`) | close + 3 min; 20:30 ET, or the next day for a night not finished; births 21:15 ET, a session night, once, and once more for a night an older reading of the grammar left empty, before 12:55Z of the session day after it (A95) | the score 120 s, resumable; births 240 s |
| - | the screen after the open (`screen-open`): the seating versions' looks when the judge's final horizon of any moved since the last screen receipt | from 09:40 ET after the open decision until 5 min before the close decision; horizons read every 10 min | none (CPU only); never within 5 min of a decision |
| 5 | the ticker snapshot | 07:00 ET, weekdays | one read |
| 6 | early verdicts (today's open decision's, then its close decision's) | from 07:30 ET | 90 s |
| 7 | the backfill of a weekday's EDGAR daily index | from 05:00 ET the next day | 90 s, resumable |

THE BACKFILL GOES FILING BY FILING (A82, release 1019c): EDGAR's daily index lists a filing once per filer (a Form 4
under its issuer and its reporting owner, an 8-K under each co-registrant: Oct 19, 2026's index had 1,189 rows and 665
filings), so a day is complete when every filing is seen, and an 8-K is a listed filer's when any of its filers is
listed. The current feed lists a co-registered 8-K once per filer too: the live pass keeps it under a listed filer
whichever the feed lists first (`edgar.poll_current`'s `prefer`), and the backfill moves one stored under an unlisted
co-registrant to the listed filer's CIK before it fetches it (`edgar.record_filing`'s `listed`; release 1019f's review:
kept under the first filer seen, such an 8-K was never an event of the listed issuer). Before it, a day counted rows and never completed, every look waited the full A66 reach and A69's fast path
never ran.

A FAILED FETCH HOLDS ITS DAY, ONE DEAD DOCUMENT NEVER HOLDS IT FOR GOOD (`fix/backfill-robust`, release 1019f): a
daily-index filing whose fetch fails is not seen. It is tried again at the first backfill pass 2, 4, 8, 16 and 32
minutes after its first failure, six tries in all, as the record pass tries a live one (its own count), and the day
is complete only when every filing is fetched, known or unlisted, or past its last try. Meanwhile the receipt is
`partial` with `failed`, `retrying` and `next_try`, and a later day is backfilled while the day waits. A filing past
its last try is named in the day's last receipt (`unfetched`: accession, form, tries, error), whose status is
`done-failed`; the day is done with `failed` above 0. That filing stays `failed:` in the store, so A69's condition (ii)
still waits on it for the closes whose windows hold it, and A66's reach does not. Before this fix a failed fetch
counted as seen and the day was done at once: one transient SEC error lost the filing. SEC HOLIDAYS: EDGAR is closed on
a federal holiday and publishes no daily index for it (Wed Nov 11, 2026, Veterans Day, is a trading day), so its index
is never there; SEC answers a daily index that does not exist with 403 or 503, never 404 (the branch's independent
check). A weekday in `SEC_HOLIDAYS` (league/events/screen.py, behind the wall, which house.py takes: OPM's 2026 and
2027 federal holidays, and Fri Dec 31, 2027, New Year's Day 2028 observed) whose index read FAILS, WHATEVER THE STATUS, is done as `no index: SEC holiday` (receipt `ok`, `why`,
`holiday`, `status`: EDGAR accepts no filing that day, so done is right even when the read failed for another reason).
A failed read on any other weekday, 403, 503 or any status, waits an hour as before, and a holiday's index that
exists is read as any day's. A closure by executive order is not in the table: add its day
before it falls. A holiday NYSE trades is final only once the index after it is backfilled too (A69 (iii), above).

A task ends before a decision falls due. A filing whose fetch failed (a transient SEC error) is fetched again at the
first record pass 2, 4, 8, 16 and 32 minutes after its first failure, six tries in all, then left to the daily-index
backfill, which tries it again by the same steps from release 1019f (an SEC outage of half an hour, or SEC's 10-minute rate-limit block, no longer spends every try); a record
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
| `evl_decide` | a session's open or close decision not made in its 10-minute window (missing, failed, cut, unfinished or finished late); one decided later still stands, its auction missed. Since release 1019f also PREREG-EVL-4's rows of a close still to decide by themselves (the judge's `screen.made_without`) 2 hours after the stall job first saw it and after its latest `decide-close` finished, while its latest `decide-close-evl4` is not `ok` (or is older than that close's latest decision); since release 1019h PREREG-EVL-5's rows the same (`made_without(prereg=5)`: a close decided without them, or whose part for them failed or ran past its bound, while its latest `decide-close-evl5` is not `ok` or is stale; `five_*` beside `four_*` in the numbers, the file named in the text) |
| `evl_verdicts` | verdicts a decision needs (its receipt's tally `verdicts: {needed, answered}`, the close decision's reading programs included; since release 1019f the `decide-close-evl4` receipts' too, since release 1019h the `decide-close-evl5` receipts') unanswered 15 minutes past it; the day's verdict dollars and the lane's line in the numbers |
| `evl_score` | intents due by the latest session still `planned` or `entered` at 23:00 ET (an exit the tape showed absent waits by design and is counted apart, read from the score's own marks alone, 'open', 'close' and 'first': release 1019h, so PREREG-EVL-5's '0930' minute with no trade excuses no intent; so, from release 1019f, does an intent a decision wrote after the night's last score pass started, such as a catch-up decision of an older session, PREREG-EVL-4's `decide-close-evl4` or, release 1019g, PREREG-EVL-5's `decide-close-evl5`: the next pass settles it, `after_last_pass`) |
| `evl_fills` | the real fills off the shadow's own auction prints by more than 15 bp either way (worse or better, said), the signed mean of a side over the last 20 priced fills (the House's event twins) |
| `evl_final` | a seatable program's final record (`screen.final_until`, what every look waits for) more than 1 session behind what A69's fast path allows (the session before the latest whose open decision has passed): the program lagging most named, with the judge's own why (A84, release 1019f; read-only, the judge read and never run for a look; judged through a `PAUSE`; a registered seatable birth judged like any seating program; release 1019g: PREREG-EVL-5's three by their own span from P''s close decision, and a close a release decided without them, or whose part for them failed, as not made for them until their own `decide-close-evl5` names them) |
| `evl_entries` (release 1019f) | an auction of the last 24 hours (judged 15 minutes after its cross) at which under 90% of the planned real buys filled, or one was never sent: from the book's own rows in `live.sqlite` (`eq_event_intents` buys, `eq_intents`, `eq_orders`). The numbers: planned, filled, the venue's cancels at once (A80: an auction buy ended `canceled` within 60 s of its own `submitted_at`, nothing filled), the re-sends after one and how many filled, the never-sent by reason (the day order count, cash, the loss budget, the 10% a name, the invested cap, the program's room, one share too dear, the gateway, a gate of real opens (release 1019g: a PREREG-EVL-5 buy `part_hold` held, waiting for the lane's close decision or never traded after its part failed), ...), and the constraint that bound the auction most (cash, budget, room, order line, name wall, invested) |
| `evl_backfill` (release 1019f) | a weekday of the daily-index backfill's reach not `done` by 12:00 ET of the next weekday, a run of its passes that are not `ok` (`waiting`, `partial`) lasting over 6 hours, or a done day whose passes failed to fetch a filing; the day and its counts named. The screen's looks wait for every weekday of the reach, so this says why one waits |
| `evl_handback` (release 1019f) | a real event fill the book made (`eq_orders` of a real event lot with `filled_qty` > 0) owed to the lane's `real_fills` over an hour and not there (a buy once its intent ended, a sale once its lot closed: as the book hands them back): the lane computes Sized, demotion and retirement from those rows |
| `cap_breach` | today's measured metered compute so far, or yesterday's, over the cap the rule set for that UTC day (league/ops/metered.py: the meters themselves), or a meter unread for 6 hours (the cap cannot be judged); while today is over it, the cap breach hold (`cap-hold.json`) holds the lane's verdict line, Sail research and the Claude roles at 0 until 00:00 UTC |

None is judged while `<state>/events/STOP` stands, nor for 30 minutes after it goes; `evl_verdicts` is not judged while
the House's `PAUSE` stands (no verdict is asked then), nor PREREG-EVL-4's part of `evl_decide`.

Since release 1019f a told owner cause no longer holds these back: while an owner cause stands and was mailed inside its
12 hours, a cause needing nothing that no notice told in the last 24 hours is mailed at once, as an INFO notice of those
causes alone that names the owner causes still waiting. The daily report carries the day's real buys (planned and
filled, the venue's cancels and A80's re-sends, the never-sent by reason, the room cut, and per auction the constraint
that bound it: the captain's A80 (2)) and, once a Probe buy exists, THE BREAK-EVEN EDGE of Done's compute clause: the
metered compute per session since the first Probe buy over the Probe dollars bought per session, in basis points.
Since release 1019h (SUP-4, the captain's A97; report only) it carries THE DONE SUPPLY LINE after the Done line: each
program at Probe or Sized, its counted Probe+ events, its MEASURED real picks a session over the last 5 sessions (the
picks ROOM gave it at the book's decisions), its Probe+ buys under Done's size bar with the cap most often recorded on
them, and the session its projection reaches Done's 50 at the STATED season multipliers (earnings x0.2 and news x0.6
after Nov 20, 2026, stated and never measured: the line says so beside every projection); and a FLAG when fewer than 3
rows reach 50 by the checkpoint Done is first read at (the larger of the next checkpoint and 300).

THE DAILY ONE-SCREEN REPORT goes to the owner by mail once a New York day, after the lane's own nightly report job
(league/ops/daily_report.py, the gateway's `report` notice): account-shown profit first and Net after the measured
metered costs beside it, by program and band (to date as far as `metered.json` covers it: "since <day>, partly
measured" when it began after the first fill); the measured costs of the UTC day of the same date against its cap with
its lines labelled the allowance; the events by family, the verdicts, the shadow intents by program and version, the real fills (buys, sells,
fees, the fill gap against the auction prints); for each program that may trade real money (version 2 of the nine, version 1
of PREREG-EVL-4's three, then each seatable birth of R3, which the report loads from the lane's store: release 1019f's
review) its band, settled n (shadow TRADABLE and real), next look and events to go, its
market-direction share and benchmark mean and its same-risk buy-and-hold ("n/a until real fills"); the records and
controls in one line, the expected false passes and the alarms open. Figures only: no headline, document text, symbol
or price leaves the House. How to read it: [operations](operations.md), **THE DAILY ONE-SCREEN REPORT BY MAIL**.

## On the public site (WP4, Oct 19, 2026; live since Oct 21, 2026: release 1019e publishes `lane_v1`)

The House publishes the lane under one versioned key, `lane_v1` (`league/site_lane.py` reads it read-only;
`league/publish.py` `site_lane` allowlists it; the contract is `league/tests/fixtures/site_contract.md`): each program
as the lane loads it (release 1019e: the seating version of each seatable one, version 2 of the nine, version 1 of
PREREG-EVL-4's three and of each seatable birth of R3, and the records and controls of every file and R3's records and
controls as "shadow"; a birth's name is its family's, "birth" and its place in registration order), with a short plain
name, its band, its settled events real and shadow and its next look's events to go; the funnel of the lane's steps;
the goal's checkpoint
(settled real-money events at Probe size or above, read every 100); the verdicts' spend, which also joins Claude's part
of the costs; and the equity book's lots as positions, which add up with the options rows and the account's other
activity to the account's Profit to the cent. The page (personal-site branch `capital/event-lane`) draws the Agents board
as Shadow, Learning, Probe and Sized with the gold line under Learning, lists the lots among the positions and counts the
checkpoint in events beside the Agents heading; an older page and an older site see nothing new.

## The Done reader (the goal V2)

The owner's Done is read by `league/events/done.py` under the pinned rule
[docs/goals/DONE-RULE-EVL-2.md](goals/DONE-RULE-EVL-2.md) (its sha256 is `done.RULE_SHA256`; a test fails while the two
differ; amended by A84 before any promotion). What counts: a settled real-money round trip of a seating program
(`real_fills`, a buy and a sale) whose buy's band is probe or sized and whose buy came after the program's PROMOTION,
its EARLIEST move to probe (`done.promoted_at`): a demotion and a return to Probe drop nothing, since a demotion fires
only on losses; and AT PROBE SIZE OR ABOVE (release 1019f, amended before any promotion): the buy's `real_fills` row's
`sized_usd` (the whole shares its send asked x its limit) at least 0.8 x its `target_usd` (its band's share of E: Probe
3.5% from A86 REVISED, Sized 10%) (`done.at_size`, `PROBE_SIZE_SHARE`), so a full, uncut buy counts whatever the
open's gap and one cut under 0.8 by a wall, the cash, the budget or the floor to whole shares, or with no record, does
not (`under_size`, reported beside). Learning events are reported beside, never counted; a Probe+ buy with no
promotion on record is a guard (`before_promotion`, read before the size) that fails `after_promotion`. It is read at every 100th such event: checkpoint c (100, 200,
300, ...) reads exactly the first c events in sale order and is never rewritten: it is appended to
`<state>/events/done-history.jsonl` before `done.json` is written, and when a Done record exists that cannot be read
(done.json at another schema or cut, a cut log line, a checkpoint a `done` receipt names that neither file holds) the
reader writes nothing and the House warns (`done.Unreadable`).

| item | passes when |
|---|---|
| `events` | c >= 300 |
| `programs` | >= 3 programs with >= 50 of the c events each |
| `after_promotion` | every Probe+ event of the span was bought after its program's promotion: no `before_promotion` event sold within it |
| `pnl` | the c events' realized after-fee P&L > $0 |
| `bound` | the 95% issuer-block bootstrap lower bound of r (10,000 resamples, seed `DONE-RULE-EVL-2\|done\|issuer`, `screen.bootstrap_bounds`) > 0 |
| `profit_vs_compute` | the lane's realized profit (every band) since the first promotion >= the metered compute over the span (`metered.since` over `metered.json`; partly measured fails) |
| `fills` | the signed mean gap per side against the shadow's auction prices in `outcomes` (made raw again) within 15 bp |
| `no_captain` | NEVER from the House's records alone (A84): `fail` when they show a step in the last 100's span (any `.before` copy or swarm.json, ops.json, PAUSE, swarm.stop by stamp, mtime or ctime; a stall run's owner step, pause or kill switch; a UTC day with no stall run), else `unverifiable`, and Done at c waits on the captain's attestation of that exact span in `<state>/events/done-attest.jsonl` with `steps` 0 (a deploy's hand steps count; the ship script's own run does not) |

Beside: the benchmark-net figure (a = r - the shadow's b, its mean and bound), learning events (count, P&L). THE PIVOT:
from checkpoint 400, the one-sided 95% upper bound of r below zero says retire the lane and move its budget. THE $800
STOP: the loss budget's total realized plus open risk (`fast_lane.probe_budget` on `live.sqlite`) at $800 says stop all
spend and report. The reader decides nothing and moves nothing: it reports. The House runs it in the nightly screen
task, after the band review: `<state>/events/done.json` (every figure, the current reading, the checkpoints), the
append-only `done-history.jsonl` and a `done` receipt; a failing reader is a warning and never fails the screen. The
reader is behind `league/ci.py`'s wall (`PENDING_GATEWAY`), so only an owner deploy changes how Done is read. The daily report carries
its line (Probe+ events toward 300 by program, the next checkpoint, the bound and the benchmark-net bound). The old
`dlane` Done meter (DONE-RULE-A50) keeps running beside and is never read for this Done.

## Real money (release R2, shipped switched on in release 1019b; deployed 21:00Z Oct 19, 2026)

[PREREG-EVL-3](prereg/PREREG-EVL-3.md) (the owner's goal as re-set at 05:15Z Oct 19, 2026): VERSION 2 of each of the
nine seatable programs trades real money from its first event at LEARNING size, with the full-size shadow beside it;
version 1 is a shadow record and never trades. [PREREG-EVL-4](prereg/PREREG-EVL-4.md)'s three seatable programs trade
at version 1 the same way, after the nine in ROOM's order (above: "PREREG-EVL-4"). The bands are the lane's (its store's `bands` table: learning from birth,
Probe after a passed look, Sized, retired), counted in settled events from its looks and the real fills the House writes
back (`real_fills`). The House trades them through its EquityBook (its event kind: league/equity/live.py `_event_step`,
the rules in `book.py`), on the money rows `equity_money.event` of league/constitution.py: learning 2% of equity a
position (one share at most 5%), Probe 3.5% (A86 REVISED; one share at most 5%), Sized 10%, at most 8 open a program
(6 at Probe), the
book-wide 10% a name, whole shares, entries limit-on-open / limit-on-close at 1.25 x the previous SIP close, exits
market-on-close (market-on-open for the three overnight rows) with PREREG-EVL-1 section 5's fallback ladder, open risk
value x max(0.10, 1.65 x sigma60 x sqrt(h)) in the one loss budget ($400 net in any 20 sessions, $800 net in total),
ROOM in the order Sized, Probe, learning, then the tables' order (round-robin inside Sized and inside Probe, and a
learning buy leaves the next auction's Probe and Sized programs their cash: the captain's A85, below). The real-money decision reads the lane's store, and
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
room for. ROUND-ROBIN INSIDE SIZED AND INSIDE PROBE (the captain's A85, Oct 21, 2026, recorded before the first Probe
auction): inside each of those two bands the picks are given one a program a pass (the tables' order inside a pass)
until every program is full or out of picks, and the auction's buys are SENT in the same passes (`book.send_key`: every
Probe program's first buy before any Probe program's second), so when the cash runs short inside one auction the last
Probe row in the tables is not left only what the earlier rows did not take; learning keeps the tables' order. With
R3's births (release 1019f's integration; R3-SPEC section 4 as the captain's A97 amends it, PL-2, release 1019h): the
round-robin is the Sized and Probe tiers (`book.ROUND_ROBIN_TIERS`); a birth AT LEARNING keeps its own tier after
every PREREG program (`BIRTH_ROOM`), in registration order, as release 1019e gave it; a PROMOTED birth (Probe or Sized)
takes its band's tier after that band's PREREG rows and before every learning row (PREREG-EVL-5 section 1.3: within a
band the tables' order, R3's births after every file's rows), round-robins with them (last in each pass), A85 reserves
for it and its buys leave no reservation, as a PREREG program of its band. Before it, a promoted birth's Probe buys
came after every PREREG learning buy and sized less A85's reservation, so they rarely reached Done's size; while no
birth is promoted nothing changes (league/tests/test_events_1019h_done_speed.py decides an invented week both ways and
finds every PREREG program's picks, sends, passes and A85 reads identical). THE NEXT AUCTION'S RESERVATION (A85): the book is
1x cash, every buy holds its limit, and a lot sold in an auction still holds its cash in that auction, so a learning lot
bought at one auction (the overnight rows' close buys) holds cash at the next one; ROOM's order alone held only inside
one auction (A83 (2)(b)). A LEARNING buy is therefore sized on the cash, the invested room and the loss budget less R:
for each live PREREG Probe or Sized program whose entry is the OTHER auction, min(its room there, max_open less what it
holds and has on order, its lots sold at this auction not counted; the median of its real-money picks at its last 5
decisions of that auction, its whole room with none yet) x its band's share x E, and that x the median open-risk weight
of its buys there (0.40 with none) for the budget; less what this auction's event sales give back by then (each lot
sold here: its value, and its value x its weight), never below 0 (league/equity/live.py `_event_reserve`,
`book.reservation`). A birth at learning is never reserved for (`book.reserved_for`), and its buy leaves R as a PREREG
learning buy does (`book.leaves_room`: its tier comes after the Probe tier); a promoted birth is reserved for and its
buys leave none (A97, PL-2); A80's one re-send is sized
again, R included, like any entry. A buy it cuts says so ("A85 holds $X ...") and the shadow keeps a skipped event. R
is 0 while no PREREG program of the other auction is at Probe or Sized: learning sizes as it did. No wall moves and no
money row changes: the reservation only makes such a buy smaller. SIZE BEFORE SLOTS: before a pick takes a slot, the
book skips (the shadow keeps the event) one that no whole share of fits by price, on the figures the send sizes on (E
the equity at the previous close, the 10% a name on the lower of E and the account's current equity from release
1019f; the name's book-wide value): one share at the limit above the book-wide 10% a name (above 10% of E for a name
held nowhere: not TRADABLE),
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

A BUY THE VENUE CANCELLED AT ONCE GOES AGAIN ONCE (the captain's amendment A80 of Oct 21, 2026; on
`fix/venue-cancel-retry`, live since release 1019e, 21:17Z Oct 21, 2026). About a quarter of the lane's limit-on-open entries of Oct 20-21 ended
"canceled", and a few limit-on-close ones: the venue accepted each and cancelled it 5-6 ms later, with no reason and
nothing filled (not the price, the buying power, the size, the account or the gateway; the cause is the venue's and
unknown). Each was an event real money missed (the shadow kept it), so real settled events came about 25% slower. Now an
event ENTRY whose last order the venue cancelled within 60 s of that order's own submission (the venue's own
`submitted_at` and `canceled_at`), nothing filled, is sent again ONCE: the same name, side, size rule, limit, time in
force and type under a new client id, through every gate, the sizing, the day's order count (the re-send is one more
order) and the window's cut-off again (the open's sends end at 09:27 ET, the close's at 15:49 on a full day), and the
gateway judges every cap again (league/equity/live.py `_event_last`, `venue_cancel_ms`). A second cancel at once, or a
cancel later than 60 s (the venue ends every unfilled auction order at its cross, minutes after it was sent), leaves the
buy missed at the auction's end as before, its why naming the cancels; a sale is never re-sent so (its ladder carries
it). The re-sent order's why says it is A80's one re-send and how many ms the venue took; the House says the session's
count once, as an info alert after the close.

STOPPING IT: `<state>/events/STOP` idles the LANE only (no record pass, decision or verdict ask); the House's event book
still decides each auction on the store as it stands, so buys from events and verdicts already stored can still go.
The instant stop of event buys is the gateway's `STOCK_EVENT_BUYS` off or `equity_money.event.enabled` False
([operations.md](operations.md), **Release 1019b**, Rollback).

THE PROBE SIZE'S RECORD (release 1019f, on `fix/probe-target-honesty`, live since 05:36Z Oct 22, 2026 in release 1019g;
the read-only audit of the live
House, its capacity and probe lenses). A Probe or Sized buy that cash, the loss budget or a wall cut below its band's
target was still labelled `probe` in `real_fills`, with no record of the target, so a reader of "Probe size or above"
could not tell a full Probe event from a cut one. Now every event buy's side row in the House's `eq_event_intents` and
its row in the lane's `real_fills` keep `target_usd`, the dollars its band's target asked (`position_share` x E at the
previous close, as the sizing was asked them), and `binding`, which constraint cut it below that: `cash` (the House-wide
cash), `budget` (the loss budget at the lot's weight), `invested` (the 100% book), `name_wall` (the book-wide 10% a
name), `whole_shares` (no cap cut the dollars; the floor to whole shares did), `gateway` (the gateway's final refusal:
no fill) or `venue` (the cross filled less than the order asked); NULL when none did, the buy at its target or one share
above it. Both are nullable columns, added in place to a state or store from before them (idempotent); a sale's row and
every older row read NULL. A record only: the band rules count a fill by its band label as PREREG-EVL-3 section 2 has
it, and the Done reader reads the record. Reading it: the size is set AT THE LIMIT (1.25 x the previous close), so a
full Probe buy's cost at a print near the previous close is about 0.8 x `target_usd`; so (release 1019f's integration,
the branch's independent check) both rows also keep `sized_usd`, THE DOLLARS THE SEND ASKED: the whole shares sent x
the limit (0 when it sent none; A80's one re-send is sized again and writes its own), and the Done reader counts a
Probe+ event only when `sized_usd` >= 0.8 x `target_usd` (DONE-RULE-EVL-2 item 1: a full, uncut buy counts whatever the
open's gap; a buy cut by a wall, the cash, the budget or the floor to whole shares below 0.8 does not).

THE WALLS' EQUITY (release 1019f, the same audit; the reading that trades less). The House sized the 10% a name on E
(`last_equity`, never above its sizing equity) while the gateway judges the account's CURRENT equity, so a one-share
buy near 10% on a day the account was down met the gateway's final refusal (`stock_position`). The decision's name-wall
skip and the send's caps of the name (book-wide and the program's own) and of the 100% book now read the lower of E and
the account's current equity as the House last read it (league/equity/live.py `wall_equity`); the band's target and its
one-share rule stay on E at the previous close. A current equity above E moves nothing; one that cannot be read leaves E.

THE EVENT KIND'S OWN DAY ORDER COUNT (release 1019c, live since 20:06Z Oct 21, 2026 with release 1019d, A88): the
kind's auction orders of a day count against
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

## Births (R3; live since release 1019e)

The owner's goal V2 item 2: "Births come from your architect agents and from you, using outcome-free facts, rationed by
an expected-false-pass budget you state". The spec is `goal-2026-10-19/R3-SPEC.md`; the code is
`league/events/births.py` (behind league/ci.py's wall); the tests are `league/tests/test_events_births.py` and
`gateway/test/births.test.mjs`. PREREG-EVL-1/2/3 are the captain's hand births; R3 makes births continuous and cheap
with the judges untouched.

**A birth is data, never code.** A spec is a JSON object of exactly these fields: `id` (`EVL-B-...`, new), `version`
(1), `family` (one the lane already reads: `ern`, `ern-react`, `8k` with an item set, `ins`, `ins-buy` with value and
role filters, `news`, `news-day`, `news-react`), `rule` (the family's own fields only: `items`; `score_min` /
`score_max` on the STORED PROMPT-DOC or PROMPT-NEWS score and `guidance` on the stored PROMPT-DOC guidance, never a new
prompt; `react_min` / `react_max`; `value_min` (>= $50,000) and `roles` (director | officer; a one-role list such as
`["officer"]` reads as its role, any other list is refused); `sources` and `hours`, the news windows), `entry` (the
family's: open or close), `exit` (close of session h, or a close entry's next open), `hold` (1..5; ONE for a seatable
birth, whose screen blocks are one-session blocks, as every seatable PREREG program's), `rank`
(score, reaction, value or none) and `seatable`. Anything else is refused. Its canonical form (sorted keys, no spaces)
and that form's sha256 name it. A READ birth (a verdict threshold, a guidance filter or a score ranking) carries a
CONTROL derived from it, `<id>-CTRL` (its rule with every verdict condition removed, a record), registered with it, so
PREREG-EVL-1 section 7's "a READ program beats its control" holds for births too. A READ birth of the `8k` family names
only items whose verdicts the lane asks (1.01, 2.01, 7.01, 8.01), so its verdicts are stored before its decision.
A NAME IS NOT PART OF THE RULE (A95): an id that lacks the `EVL-B-` prefix is named canonically by the House
(`births.canonical_name`: a leading `EVL-` becomes `EVL-B-`, any other id takes `EVL-B-` in front), every check of an id
(the pattern, 40 characters, never ending `-CTRL`, never registered) applies to that name, the canonical line and sha
carry it, and the candidate row keeps the proposed id beside it (`figures.named` {from, to}; the receipt's `named`).

**Born from outcome-free facts.** Each night the lane builds the facts of the last 20 sessions (`births.Facts`): event
counts by family, 8-K item, news source and knowable hour; the stored verdict scores and guidance; which families and
items no program selects; every registered program's selection count; a candidate rule's selection count, each through
the lane's own `select` over the same windows (registration set aside: what a rule WOULD have selected). A SQLite
authorizer refuses the facts every read of `bars`, `marks`, `outcomes`, `looks`, `bands`, `band_history`, `real_fills`,
`universe` and `meta` for the whole build, so no price after an event, return, P&L, look's p or band reaches the
architect. A react family's reaction is a price after the event: never read, so its counts are upper bounds.
PREREG-EVL-4'S AND -5'S ROWS ARE COUNTED TOO (release 1019h; PREREG-EVL-5 section 7, "births.py's facts for the new
families"; release 1019g's facts windowed none of their families, so all nine rows selected 0 and no birth's Jaccard
was computed against them): `births.Facts` windows `close_rows_4` and `close_rows_5` as their close decision reads them
(`FILE_FAMILIES`), every price unread, so a count that reads one is an upper bound as a react family's (EVL-8K-REACT-ON's
reaction; PREREG-EVL-5's reaction passes each row's own band and its gap passes; TAKEN (a) and (c) and the <= 0.96 skip
skip nothing, TAKEN (b) reads the stored PROMPT-NEWS verdicts, an issuer waiting on an unanswered article is counted, and
NO NEW INFORMATION (i) names an issuer by the kept eligibility's ticker, never SEC's copy, which lives in `meta`); the
rows that read no price (EVL-8K-READ-ON, EVL-NEWSPM-READ-ON and their controls) count as decided. Each row's count is
therefore at least what it selected, and the validator's Jaccard reads them; the grammar and the rates are unchanged
(more Jaccard targets can only refuse more), and so was `births.PARSE_VERSION` until A109's architect (4, below).

**The architect and the validator.** One gateway call a night (`births.propose`): claude-opus-5-5 from release 1019h
(the captain's A109: release 1019e to 1019g asked claude-haiku-4-5-20251001 at temperature 0 with max_tokens 3,000,
whose proposals were narrow rules and duplicates; the verdict reader stays Haiku 4.5). Claude Opus 5.5 takes no
sampling parameter (a `temperature` is Anthropic's 400, and a 4xx is never asked again) and always thinks, its thinking
counted in `max_tokens`, so the body (`births.request_body`) carries no temperature, effort `low` (`births.EFFORT`: short
thinking, and an unstreamed answer well inside Cloudflare's 100-second wait in front of Anthropic) and max_tokens 6,000
(room for the six specs after the thinking); an answer cut at max_tokens is stored `cut`, never parsed. Its prompt's
sha256 and its answer are stored in `birth_calls` like a verdict (a night's answer is read again, never asked again,
under the same prompt sha and model), at most 6 specs a night, under a cost cap of $0.25 a night: the call's worst case
must fit, AT THE MODEL'S OWN PRICES (`births.PRICES`, held equal to the gateway's CLAUDE_MODELS row of the model by a
test: Opus 5.5's $4 input and $20 output a million tokens, at the row's dearest inference geography, US-only at 1.1x,
so $4.40 and $22, as the gateway reserves): every prompt character at a token every 3 and the whole 6,000 tokens out,
about $0.14 on an ordinary night and $0.16 on the fullest night the facts can describe (Haiku's was about $0.02). What
a night is billed is the gateway's stated cost: not yet measured on Opus 5.5 (an estimate with its thinking at effort
low: $0.05-0.10 a night, against A109's $0.03 and Haiku's measured $0.008). The prompt shows two valid specs (`births.EXAMPLES`: an 8k spec over items outside the four
READ items with no score or guidance field, and a news spec) and says that an 8k spec may carry `score_min`,
`score_max` or `guidance` only when every item is among the four, and that `guidance` is a list (A95: the first night's
6 specs were all refused, for ids without the prefix, `"guidance": {"verdict": "none"}`, READ fields on other items and
`"roles": ["officer"]`). That moved the prompt's sha (release 1019e's `2203fda3` to `8294fe77`): an answer stored under
the old sha is never read by this code (it stays stored and counted), and a night this code runs asks under the new one.
On the House the call is INSIDE THE LANE'S LINE (release 1019e's review): its worst case must also fit under what is
left of the lane's line that UTC day, and its stored cost counts in that line (the next verdict is refused once births
and verdicts reach it), in the budget rule's measure of the lane (`budget.lane_spend`: its window, its heaviest day and
today) and in the site's Claude bill (`site_lane.verdict_usd`).
The validator is code (`births.validate`): the grammar; a new id and sha; THE RATE: a SEATABLE birth at least 20
selected events a session over the sessions of the last 20 that hold a COMPLETE RECORD PASS (SUP-3's rate rule, the
captain's A97, release 1019h: `births.recorded_sessions`, the session's whole event span from the prior session's 09:00
ET to its close decision recorded by clean record passes, `evl_record`'s reading, with no gap over 30 minutes; an
outage session is left out, never counted at a low count; at least 3 such sessions), so a seatable birth can fill a
Probe row's slots after the real-money funnel through the season (a react family's count is an upper bound, so the
floor barely binds it); a RECORD at least 3 a session over the last 20 sessions by selection count, as before; Jaccard < 0.8 of the last 20 sessions' selected events against every registered
program (records, controls and births included: stricter than "every live program", and it reads no band) and against
every birth accepted before it that night; and THE FALSE-PASS BUDGET, stated: each seatable birth adds 0.10 expected
false passes (the measured zero-edge pass rate of PREREG-EVL-3's screen is at most 8.4%; 0.10 is the stated charge), at
most the lane's stated lifetime budget, 3.0 (A81, the captain's, 16:25Z Oct 21, 2026: A71's budget,
`screen.LANE_BUDGET`, not R3's draft 2.0), over every seatable version ever registered in the lane, counted from
SEATING's own sum as the report counts it (`screen.expected_false_passes`: PREREG-EVL-1 to -5's fifteen seatable
versions use 1.5, so 1.5 used plus 0.10 for each seatable birth, at most fifteen seatable births ever; a retired program
stays counted), at most 3 seatable births a night; records are free. The captain's births go through the same
validator and registration with no model call: `python -m league.events --state DIR births --specs FILE` (a JSON list
of `{spec, why}`; `--dry-run` validates only); `facts [--specs FILE]` prints the night's facts, with each spec's
selection count by session. Every candidate's verdict and figures (its count, its highest Jaccard and with whom) are
kept in `birth_candidates`.

**Registration.** The accepted specs' canonical lines are appended to `docs/births/<night>.jsonl` on main through the
gateway's docs route (`POST /v1/github/docs`, gateway/lib/desk.mjs: that path pattern only, appends of JSON lines only,
at most 12 lines of 8 KB a post and a 256 KB file, no credential, the runtime token, one of the day's six docs
commits). A birth's REGISTRATION TIME is the later of GitHub's commit time (the answer's `committed_at`) and the
House's receipt of the answer, kept in the store's `births` table; it counts only events knowable after it. An answer
that never came leaves the night `unknown`, posted again with the same lines the next night: the route then answers
`unchanged` with the file's latest commit, whose time is no earlier than the true one.

**In the lane.** One loader (league/events/programs.py `load_births`, at every turn of the House's lane, every CLI
command and every opening of the lane by the House's event book) adds each registered birth as a Program row with its
own registration time and PREREG-EVL-3's learning band, screen and minimums (prereg 3: the limit at entry too), AFTER
every PREREG program; no PREREG program's selection, judge or constant moves (a test decides a week of invented events
with and without births and finds every PREREG program's intents identical). The lane decides a birth like any program
(its rows are the family's), the score settles it, the screen judges a seatable birth by PREREG-EVL-3's looks unchanged
(events counted, alpha 0.018, >= 40 issuers and 8 session blocks; a record or a control is never screened), its band
moves by PREREG-EVL-3's rules, and the House's event book (which reads `SEATING` and `BY_KEY`) trades a seated birth at
learning size from its first event at its own version 1, like any version 2 program. When room is short, every PREREG
program goes first (Sized, Probe, learning, then the tables' order) and the births at learning after them, in
registration order (R3-SPEC section 4); a promoted birth takes its band's tier after that band's PREREG rows (A97, PL-2,
release 1019h: **Real money**, below). The proposer is told the rate rule and to propose no earnings-only family (ern,
ern-react) after Nov 6, 2026 (A97; no steering toward any family otherwise). Expected false passes in the report count every seatable birth. A birth's failure is its own: a
birth whose part of a decision raises is kept in the decision's `births_failed` (the decision is made for every other
program, as before) and the screen holds that birth's looks until a later pass decides it; a READ birth's look waits
the same way when its control's part raised or is pending (the look compares the two records). A DECISION MADE WITHOUT
A BIRTH IS NOT MADE FOR IT (release 1019e's review): a decision after the birth's registration whose receipt does not
name the birth (and its control), made by a release without births or in a turn whose loader had none, leaves the
birth's looks waiting until the births' own decision (`decide-open-births:<day>` or `decide-close-births:<day>`,
`run.decide_open`/`decide_close` with `births_only`, a backfill that decides the births alone, never a PREREG row)
names it; the House's lane runs it once for every such decision older than its hourly re-decision's reach, and the
CLI's `catchup` too (`screen.births_made_without`). A read error of the births table keeps the births last read from
that store (never unloading them mid-run), and the score applies the limit at entry to any program the process does not
know (only a birth can be one). The House's book reads every family a seatable birth can have
(a test trades a seatable birth of each of the seven and finds its real-money picks equal to its shadow's intents at
every auction); an `ins` (Form 4 cluster) birth is a record only (A89: its cluster reads Form 4s that may be stored
after a decision), so the book reads no `ins` rows and the grammar refuses a seatable one.

**On the House.** `league/config.json` `events.births` true runs the job on a session night at 21:15 ET after the
report (league/events/house.py), once a night, its Claude call through the lane's gateway (refused while the House is
paused or over the day's verdict line, made only when its worst case fits under what is left of that line, and counted
in it). THE ONE RE-RUN OF AN EMPTY NIGHT (A95, `births.rerun_due`): every births receipt records the running
`births.PARSE_VERSION` (4 from release 1019h: its SUP-3 rate rule and prompt lines moved the prompt's sha `8294fe77` ->
`890806ff`, version 3, and its A109 architect, whose model, temperature, effort and max_tokens are in the sha's spec,
moved it again to `0cae215b`, version 4, the one release 1019h runs; 2 before it; release 1019e's receipts record none,
read as 1). When the latest night's receipts accepted
none and registered none (no accepted id, no candidate row accepted, unknown or registered, no birth of the night) and
were all written by an older version, the House runs that night's job once more, its receipt marked `rerun` (written
when it starts, so a re-run that dies is still the one), never from 12:55Z of the session day after the night (a
Friday night's until Monday's 12:55Z). The re-run reads the night's stored answer again when its prompt sha is the
running one (no call), else makes the night's call inside the night's $0.25 (its first call counts) and the lane's line.
Its births register like any, at the later of GitHub's commit time and the House's receipt, so they count only events
knowable after the re-run, are charged to the budget and to that night's three; the line goes to the night's own file.
Before 12:55Z the re-run starts at least 5 minutes (65 in standard time) before the session's 09:00 ET cut-off and 20
(80) before its 09:15 ET open decision; from then the session's decisions run until its close (the deploy-blocked
window), and a birth registered among them would begin part-way through a session it cannot fairly count, so the
night stays empty and the next night's job proposes again: either way no event before a birth's registration is
counted. It ships false: switching it on needs the gateway release with the births
route. The switch stops new births only; registered births trade whatever it says. Not built here: R3-SPEC's Sonnet
fallback after two failing nights of Haiku proposals (moot since A109's Opus architect), and a ranking of learning
room by look statistics (a later, pre-registered version).

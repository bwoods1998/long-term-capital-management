# PREREG-EVL-4: three new seatable event programs, real money at learning size from birth

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6f078599) under the owner's goal as he re-set it at 05:15Z
Mon Oct 19, 2026 (`goal-2026-10-19/GOAL-MESSAGE-V2.txt`): "Births come from your architect agents and from you, using
outcome-free facts, rationed by an expected-false-pass budget you state." Written 15:15-16:10Z Mon Oct 19, 2026 (the judge's draft 15:15-15:43Z; the adversarial check's one major and four minors taken by the captain 16:00-16:10Z). Designed from outcome-free
counts only (`goal-2026-10-19/evl4/FACTS.json`: filings, items, Form 4 rows, articles, verdict scores and Monday's
shadow intents, counted; no price), the frozen rules of PREREG-EVL-1, -2 and -3, the lane's code at release 1019b and
the published literature. Three independent designers proposed sixteen candidates, a judge scored them and wrote this
file, and an adversarial check read it, each under the rule that no price after any event, and no return, P&L, look,
band or mark of the lane, is read, queried or computed; the judge read none.

REGISTRATION TIME: the later of this file's commit time and GitHub's receipt of the push of the tag `prereg-evl-4` (read
from the GitHub API and recorded in the captain's amendment that pins it as `REGISTERED_AT_4`); the tag never moves. A
program of this file counts only events knowable after THIS registration time (not PREREG-EVL-1's, -2's or -3's).
Nothing here changes for a registered program: a change is a new version with its own registration time.

## 1. The programs

This file adds three seatable programs and two controls (free records) to the lane of PREREG-EVL-1 (frozen
2026-10-19T01:08:38Z), PREREG-EVL-2 (03:04:07Z) and PREREG-EVL-3 (05:23:06Z), which it never edits. It changes no
program, record, control, verdict, prompt, judge, band rule or wall of those files. It adds no prompt and no form: every
verdict read here is a PROMPT-DOC or PROMPT-NEWS verdict asked and stored as PREREG-EVL-1 section 4 says, and a verdict
already stored for an event is the verdict of every program that reads it.

### 1.1 Terms (every program and control of this file)

- D is the entry session and P the session before it (the lane's session calendar). Knowable times are PREREG-EVL-1
  section 3's: EDGAR filings at acceptance + 10 minutes, ENEWS articles at `created_at` + 2 minutes. An issuer is
  ELIGIBLE when PREREG-EVL-1 section 2 makes its stock eligible for entry session D; its ELIGIBLE TICKER is that stock's
  symbol.
- THE CLOSE WINDOW of D: knowable at or after P's close decision time (P's close - 14 minutes) and before D's close
  decision time. These are exactly the events whose day 0, as EVL-ERN-REACT-C1 defines it (PREREG-EVL-1 section 6: the
  first session whose close decision time is after the knowable time), is D.
- F8K(D): the E8K filings (form type exactly `8-K`; `8-K/A` excluded) with any of items 1.01, 2.01, 7.01, 8.01 and
  without item 2.02 (EVL-8K-READ-O1's family, PREREG-EVL-1 section 6) knowable in the close window of D. Items are the
  filing's own (its EDGAR index page), as the lane stores them; F8K(D) and ERN(D) are read from the fetched filings, as
  every 8-K rule of the lane.
- ERN(D): the issuers (CIK) of the E8K filings with item 2.02 knowable in the close window of D, whatever their verdict
  or reaction.
- DAY(D): the issuers of the articles of PREREG-EVL-2's day-news window of D (ENEWS with exactly one symbol, that symbol
  the eligible ticker of its issuer, knowable after 09:00 ET of D and at or before T29 of D; PREREG-EVL-1 section 3's
  non-live exclusion applied), whatever their verdict or reaction.
- PM(D): the articles of EVL-NEWS-READ-O1's window of D (ENEWS with exactly one symbol, that symbol the eligible ticker
  of its issuer, knowable after P's close and at or before 09:00 ET of D; the non-live exclusion applied).
- EXCLUDED on D: an issuer in ERN(D) or in DAY(D). Every program and control of this file skips it, whatever the
  knowable times of the filings and articles that put it there relative to any registration time. Its close-to-open
  trade on D belongs to the earnings rows (EVL-ERN-REACT-ON) or to PREREG-EVL-2's day-news rows (EVL-NEWS-READ-ON,
  EVL-NEWS-REACT-ON), so no row of this file repeats an (issuer, entry auction, exit auction) that an earlier seatable
  row can trade.
- THE REACTION of an F8K(D) filing: PREREG-EVL-2 section 2's reaction of an 8-K event with day 0 = D, which is
  EVL-ERN-REACT-C1's: the close of the regular-session SIP 1-minute bar starting at T29 of D (15:29:00 ET on a full day,
  12:29:00 ET on a 13:00 close; if that minute has no trade, the last earlier regular-session minute bar of D) over the
  raw SIP daily close of the last session that closed before the filing's acceptance time. There is no reaction when
  either price is missing, and the event is then not taken.
- ENTRY, EXIT AND HOLD: every program and control here enters at the CLOSE auction of D (PREREG-EVL-1 section 5: decided
  at the close - 14 minutes from events knowable before it, the order sent by the close - 11 minutes) and exits at the
  OPEN auction of the next session (PREREG-EVL-2 section 2's exit at the open, with PREREG-EVL-1 section 5's fallback
  ladder unchanged). It holds one session in the screen's sense: its block is D, its first settled exit is session 1,
  and its blocks never overlap. THE LIMIT AT ENTRY (PREREG-EVL-2 section 2), shadow and real alike: an entry auction
  above 1.25 x the raw SIP close of P is not filled and the event is skipped.
- UNCHANGED FROM PREREG-EVL-1: the universe (section 2), backfill and the shadow rule (section 3), the verdicts (section
  4), auction prices, costs, r, b, a and TRADABLE (section 5: 1.25 x the previous SIP close at most 10% of the account
  equity at the previous close), and one position per issuer per program (section 5: an issuer the program holds, or
  held within the last 5 sessions, is skipped).

### 1.2 The programs

Seatable from birth (section 2). Each enters at the CLOSE of D and exits at the OPEN of the next session (hold 1):

| id | events of D | rule | one event per issuer per D | ranking (real money) |
|---|---|---|---|---|
| EVL-8K-REACT-ON | F8K(D) filings of eligible issuers not EXCLUDED on D | the reaction >= 1.04 (no model) | the earliest knowable filing the rule takes | the reaction, higher first, then ADV |
| EVL-8K-READ-ON | F8K(D) filings of eligible issuers not EXCLUDED on D | the stored PROMPT-DOC verdict `ok` with score >= 2 | the earliest knowable filing the rule takes | the verdict score, higher first, then ADV |
| EVL-NEWSPM-READ-ON | PM(D) articles of eligible issuers not EXCLUDED on D and with no F8K(D) filing | the stored PROMPT-NEWS verdict `ok` with score >= 2 | the highest score, then the earliest | the verdict score, higher first, then ADV |

- EVL-8K-READ-ON reads the PROMPT-DOC verdict of event `8k:<accession>`: the one verdict EVL-8K-READ-O1 reads for the
  same filing, asked once and stored as PREREG-EVL-1 section 4 says. A filing knowable before 09:00 ET of D is asked for
  EVL-8K-READ-O1's open decision of D; a filing knowable during D is asked during D's session (the same verdict
  EVL-8K-READ-O1's next open decision reads). A TEXT shorter than 200 characters has no verdict and is not taken. READ
  events wait for their verdict (the shadow rule).
- EVL-NEWSPM-READ-ON reads the PROMPT-NEWS verdict of event `news:<id>`: the one verdict EVL-NEWS-READ-O1 asks for the
  same article for its open decision of D, stored once as PREREG-EVL-1 section 4 says; this row asks no verdict of its
  own. READ events wait for it.
- EVL-NEWSPM-READ-ON skips an issuer with any F8K(D) filing, whatever that filing's verdict, reaction or knowable time
  relative to any registration time: that issuer-day is the 8-K rows'. EVL-NEWSPM-READ-ON therefore shares no (issuer,
  D) with either 8-K row; EVL-8K-REACT-ON and EVL-8K-READ-ON share the filings that pass both rules.
- A filing or an article is an EVENT of a program only when its knowable time is after this file's registration time.
  The sets ERN(D), DAY(D) and F8K(D) that skip an issuer carry no such condition.

### 1.3 Real money (PREREG-EVL-1 sections 3 and 8, PREREG-EVL-3 section 2)

- A real-money decision is the shadow rule over the events STORED, and the verdicts ANSWERED, before D's close decision
  time. It applies EXCLUDED and the F8K(D) skip to the filings and articles stored before that time; a row stored later
  counts in the shadow only, and the report counts the difference.
- ROOM: Sized programs first, then Probe, then learning; within a band the tables' order, which is PREREG-EVL-1's rows,
  then PREREG-EVL-2's, then this file's in the order of section 1.2; within a program its ranking above. When two
  programs want the same name at one auction, the earlier in that order takes it.
- The House's book skips a buy of a name that an event lot sells at the same auction (its "sale" gate, the reading that
  trades less; the shadow keeps the event). So a name any event lot sells at D's close (for instance one EVL-8K-READ-O1
  or EVL-NEWS-READ-O1 bought at D's open) is not bought at that close by this file's rows.
- NO REAL-MONEY TAKING FROM AN EARLIER ROW: IN REAL MONEY ONLY, EVL-8K-REACT-ON and EVL-8K-READ-ON do not buy for a
  filing knowable at or after 09:00 ET of D whose stored PROMPT-DOC verdict is `ok` with score >= 2, or is not yet
  answered, at D's close decision time: such a filing is EVL-8K-READ-O1's event at the next open, and this file's sale
  at that open would take the name from that earlier row (the sale gate). The shadow keeps the event, and every
  program's shadow record is as section 1.2 says. A rarer case is not prevented and is stated: an issuer this file's
  row bought at D's close that an earlier open-entry row wants again at the next open (for instance fresh pre-market
  news of the same issuer the next morning) loses that earlier row's real-money buy to this file's sale (the sale gate);
  the report counts each such case. No rule and no shadow record of any earlier program changes.

## 2. Seatable from birth, under PREREG-EVL-3 unchanged

- Version 1 of each program of section 1.2 is its seating version. (PREREG-EVL-3 registered version 2 of the earlier ids
  because real money from birth was a change to programs already registered, and a change is a new version; these ids
  are new, and their version 1 is registered with PREREG-EVL-3's bands.) Each program is SEATABLE at PREREG-EVL-3's
  LEARNING band from birth: every TRADABLE event that fits the walls is entered with real money at a target of 2% of the
  account equity at the previous close, in whole shares at the limit (1.25 x the previous SIP close), one share when
  that rounds to none and one share at the limit is at most 5% of equity and fits every wall, at most 8 open learning
  positions a program. Real money starts at the first decision after the House release that carries this file's programs
  is live and the auction paper proof's BUY stage has passed (PREREG-EVL-3 section 2); until then, and for every event
  after the registration time that comes before it (backfill included), the programs are decided by the same rules in
  shadow only.
- PREREG-EVL-3 sections 2, 3, 5 and 6 apply to this file's programs word for word, with version 1 in place of version 2
  (seed strings `{id}|v1|look{k}`); PREREG-EVL-3 section 4's count is replaced by section 3 here: PROBE from the first decision after a passed look (target 5%, at
  most 6 open); SIZED (>= 150 settled real-money events at Probe size or above with the 80% session-block bootstrap
  lower bound of the per-event after-cost return above zero: target 10%, at most 8 open); DEMOTION to learning (the last
  50 settled real-money events at Probe size or above lost more than $150 net, or the last 100 have a negative mean
  after-cost return; back to Probe at the next passed look); RETIREMENT at a held look whose mean a of the TRADABLE
  events is below zero with the reversed one-sided sign-flip p at most 0.05; the open-risk weight max(0.10, 1.65 x sigma
  x sqrt(h)).
- THE SCREEN is PREREG-EVL-3 section 3's, unchanged: look k (k = 1..10) at the first session close with at least N_k =
  60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250 settled TRADABLE events, at least 40 distinct issuers among them and
  at least 8 session blocks, covering every block whose scheduled exits are at or before that close (looks in order, at
  most one a close; thresholds first reached at one close are one look); the skew check from alpha = 0.018, which only
  tightens; PASS when the session-block sign-flip p and the issuer-block p are each at most their alpha, the mean a of
  the TRADABLE events > 0 and their mean raw after-cost r > 0, and, for EVL-8K-READ-ON and EVL-NEWSPM-READ-ON, the mean
  block value exceeds its control's (section 4) over the same sessions. The seed strings are `{id}|v1|look{k}` (with
  `|issuer`, `|skew` and `|skewflip` appended as PREREG-EVL-1 section 7 says).
- Only events knowable after this file's registration time count, for the screen, the bands, Sized, demotion, retirement
  and Done. Done, pivot and reporting are PREREG-EVL-3 section 5's, unchanged: these programs' events at Probe size or
  above count toward Done like any program's, and only after their own promotion.

## 3. Expected false passes, and the lane's budget

- 0.10 x every version that can seat: PREREG-EVL-3's nine version 2 programs (0.9) and this file's three (0.3), 1.2 in
  all. The two controls never seat and cost nothing.
- MEASURED FALSE-POSITIVE RATE at this file's event rates (synthetic, PREREG-EVL-3's model and schedule,
  `prereg/evl-4/calib_evl4.py`, seeds 41-43, with `prereg/evl-3/calibrate_events.py`'s sign-flip; the session-block test
  alone): a zero-edge program passes any look within 400 sessions 7.9% of the time at a mean of 5 events a session
  (7.4% with 5% per-event noise in place of 3%), 7.6% at 19 and 8.2% at 25; with every one of the ten looks reachable
  (a horizon of 1200 sessions, `prereg/evl-4/calib_evl4_horizon.py`, seed 41) 9.7% at a mean of 5 and 8.4% at a mean
  of 2; all under the 0.10 charged and the goal's 15%. The issuer-block test,
  the skew check, the beat-the-control rule and the TRADABLE count can only lower it.
- POWER (same model): an edge of 0.4% an event passes about 82% of the time at 5 events a session (median session 98),
  93% at 19 (median 37) and 93% at 25 (median 33); 0.2% about 42%, 51% and 49% (medians 116, 51 and 45); 0.8% about 98%,
  99.7% and 99.9% (medians 39, 14 and 13). The issuer-block test, the skew check, the beat-the-control rule and TRADABLE
  lower these and are not measured.
- THE LANE'S LIFETIME BUDGET, STATED: 3.0 expected false passes for the event lane (thirty seatable versions at 0.10).
  Why 3.0: a false pass promotes a zero-edge program to Probe (5% of equity a position, about $95, at most 6 open),
  where it loses about the round trip (14-24 bp, about $0.13-0.23 a position) plus noise, and PREREG-EVL-3's demotion
  returns it to learning once its last 50 Probe events lost more than $150 or its last 100 have a negative mean (in
  expectation they do, by the cost): a Probe stay of about 100 events, about $13-23 in expectation, bounded by demotion
  and far inside the $400 / $800 loss budget. The binding cost is dilution of the Done pool: a false pass's Probe events
  count toward Done's 300, and Done's 95% issuer-block bootstrap lower bound over all of them (with >= 3 programs of >=
  50 events each) prices that dilution in, since a zero-edge program's events pull the bound toward zero and never lift
  it. Used with this file: 1.2. Left for later births: 1.8, each later file stating its draw against it.

## 4. Controls (free records)

- EVL-CTRL-8K-ON: every EVL-8K-READ-ON event before its verdict rule: the F8K(D) filings of eligible issuers not
  EXCLUDED on D, with or without a verdict, one per issuer per D (the earliest knowable); entry and exit as section 1.2.
  It is EVL-8K-READ-ON's control. Its figures also give EVL-8K-REACT-ON's family base rate in the report; they are never
  a condition of EVL-8K-REACT-ON's pass.
- EVL-CTRL-NEWSPM-ON: every EVL-NEWSPM-READ-ON event before its score rule (the PM(D) articles of eligible issuers not
  EXCLUDED on D and with no F8K(D) filing), one per issuer per D by the same order (the highest stored score, then the
  earliest); entry and exit as section 1.2. It is EVL-NEWSPM-READ-ON's control.
- Controls are shadow records: they never seat, never trade, cost no expected false pass, and are compared over the READ
  program's own block sessions (PREREG-EVL-1 section 7: the control's TRADABLE events of each of those sessions
  averaged, then the sessions averaged).
- EVL-8K-REACT-ON reads no verdict and has no control condition, as PREREG-EVL-2's REACT rows.

## 5. What is unchanged

Everything this file does not state is PREREG-EVL-1's, -2's and -3's, word for word: the universe, the events, the
knowable times, backfill and the shadow rule; the verdicts, their model, prompts (PROMPT-DOC and PROMPT-NEWS and their
SHA-256), parsing and the rule that the first stored answer is final; the execution model, auction prices, the fallback
ladder, costs, per-event returns and TRADABLE; the screen; the nine version 2 programs, every version 1 record and every
control of those files, and their place in ROOM ahead of this file's rows; the bands, Sized, demotion and retirement;
the money walls (<= 10% of equity a name, <= 100% invested, no margin, no shorts), the loss budget ($400 net in any 20
sessions, $800 net total, realized plus open risk), the open-risk rule, the kill switch and the stops; Done, pivot and
reporting.

## 6. Why these three, and their rates (the judge's prior, stated before any outcome)

- THE MECHANISM all three hold: the night after an attention day. Berkman, Koch, Tuttle and Zhang (2012, JFQA 47(4)):
  stocks that drew investors' attention on a day (proxied by a large absolute return, among other measures) earn
  positive returns from that close to the next open, which reverse during the next session; the pattern is strongest in
  small stocks with heavy individual-investor trading, the stocks one share of which fits a learning position. Barber
  and Odean (2008, RFS 21(2)): individual investors are net buyers of attention-grabbing stocks. Aboody, Even-Tov,
  Lehavy and Trueman (2018, JFQA 53(2)) and Lou, Polk and Skouras (2019, JFE 134(1)): overnight returns persist in the
  short term, and overnight and intraday clienteles persist. The entry is at D's close, after the event and D's reaction
  are public; the exit at the next open keeps the overnight leg and skips the next session's reversal.
- EVL-8K-REACT-ON: a rise of 4% or more on a material non-earnings filing is an attention proxy in Berkman et al.'s
  sense (a large absolute return). Chan (2003, JFE 70(2)) and Savor (2012, JFE 106(3)): price moves that come with
  public information continue rather than reverse, over weeks to months and mainly after bad news; Jiang, Li and Wang
  (2021, JFE 141(2)): returns drift after news-driven jumps. It is EVL-ERN-REACT-ON's hypothesis on a disjoint
  population (no item 2.02, no earnings issuer, no day news): if both pass, the effect is not earnings-only. Strength:
  weak to moderate.
- EVL-8K-READ-ON: the same night, after a filing the frozen reading calls positive. For a filing knowable before 09:00
  ET of D it holds the night after EVL-8K-READ-O1's day for the same filing, so the two rows read opposite legs of
  Berkman et al.'s pattern; for a filing knowable during D it holds the first night. Lopez-Lira and Tang (2023, arXiv
  2304.07619): language-model scores of news predict next-day returns, mostly in small stocks and after bad news (the
  long side is the weaker). Its control measures what the reading adds. Strength: weak to moderate.
- EVL-NEWSPM-READ-ON: the night after single-stock pre-market news, for the names no other close-to-open row trades (no
  earnings release, no day news, no family filing that day). It reads only verdicts already stored for EVL-NEWS-READ-O1.
  Strength: weak to moderate.
- AGAINST: Berkman et al. find the effect smaller in their later years; Heston and Sinha (2017, FAJ 73(3)) find positive
  news priced within about a day; the round trip is 14-24 bp of a position. All three rows share one mechanism with
  PREREG-EVL-2's three close-to-open rows, so their errors are correlated: a false pass of one makes a false pass of
  another likelier, which the 0.10 a program already charges in expectation.
- RATES (before any was counted for these rows; FACTS.json, counts only). 8-K: 398 listed-filer 8-Ks were fetched over
  Oct 15-19 (188 on Oct 15 and 148 on Oct 16, the two full weekdays; 61 on Oct 19 to the snapshot), about 170 a full
  weekday; the item sets the facts list put 214 of the 398 (54%) in the family, and up to 263 (66%) with the sets they
  do not list: about 90-110 a weekday; 144 of the 219 issuers considered at Monday's open were eligible (66%, all event
  kinds): about 60-75 eligible family 8-Ks a session, about 45-60 after EXCLUDED (the share it removes is not in the
  facts; assumed 20-30%). EVL-8K-READ-ON: 11 of the 26 stored PROMPT-DOC verdicts scored >= 2 (42%), and Monday's open
  had 10 EVL-8K-READ-O1 intents against 22 of its control (45%): about 19-27 a session. EVL-8K-REACT-ON: the share of
  family filings whose stock is 4% or more above its base at T29 is a price and was not counted; assumed 7-10%: about
  3-6 a session (a rise above 25% fails the limit at entry). DAY(D) (single-stock news during D) and a T29 rise are
  likely positively correlated, so EXCLUDED may remove far more of the risers than of the family: the row may run nearer
  1.5-3 events a session (power about 54% at a 0.4% edge, median first pass near session 136, same model), and its first
  weeks fall in peak earnings season. It is kept: it costs 0.10 either way and is the only row of the lane that tests
  the overnight mechanism off earnings and off news. EVL-NEWSPM-READ-ON: Monday's open had 54 EVL-NEWS-READ-O1
  intents (eligible pre-market issuers with a score >= 2; 57 of the 153 news verdicts scored >= 2) and 135 of its
  control, from news recorded from Sunday 20:00 ET only, a shorter window than a weekday's 17 hours; EXCLUDED and the
  F8K(D) skip are assumed to remove 40-55%: about 20-30 a session, fewer at the peak of earnings season, when ERN(D)
  grows. Controls: EVL-CTRL-8K-ON about 45-60 a session, EVL-CTRL-NEWSPM-ON about 60-80. Most of these are TRADABLE (a
  previous close up to about $150 at today's equity), so the first look's minimums (60 TRADABLE events, 40 issuers, 8
  blocks) come at about session 8 for the two READ rows and about session 12-22 for EVL-8K-REACT-ON.
- STATED RISKS: real money at learning takes what the earlier rows leave (ROOM's order, the 100% book at the close
  auction, the sale gate), so its picks rank lower than the shadow's best; at about 3-6 events a session EVL-8K-REACT-ON
  has power only for edges near 0.4% or more; a verdict outage or the day's verdict line leaves a READ decision pending;
  the assumed shares (EXCLUDED, the T29 rise) are not in the facts and the report will count them.

## 7. What is not decided here

The code (league/events/programs.py's rows and rule kinds, run.py's close decision, book.py's seating and rows,
screen.py's registries), the site and the docs, built after this file to these rules; the build's plan is a guide and
this file wins. If an implementation finds a rule here ambiguous, it takes the reading LESS LIKELY TO PASS (screen
rules) or that trades less (trading rules), fixed before the program's first settled event and recorded as an amendment;
a later resolution is a new version.

# PREREG-EVL-5: three new seatable event programs, real money at learning size from birth

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6e6a85b9) under the owner's goal as he re-set it at 05:15Z
Mon Oct 19, 2026 (`goal-2026-10-19/GOAL-MESSAGE-V2.txt`): "Births come from your architect agents and from you, using
outcome-free facts, rationed by an expected-false-pass budget you state." Written 19:55-21:40Z Wed Oct 21, 2026 (the design workflow wf_b90edd7b-00a, the check's fixes applied 21:20-21:38Z). Designed from outcome-free
counts only (`goal-2026-10-19/evl5/HOUSE-FACTS.json`: the House's store over Oct 19-21, filings by form and day, 8-K
items, Form 4 codes, articles by hour, day and source, the universe's size, each program's selection counts, headline
keyword counts; `goal-2026-10-19/evl5/EDGAR-FORMS.json`: EDGAR's daily-index rows by form over four weekdays;
`goal-2026-10-19/evl4/FACTS.json`), the frozen rules of PREREG-EVL-1 to -4, the lane's code at release 1019d and the
published literature. Four independent designers (analyst actions in the recorded news, EDGAR forms the lane does not
record, a stronger reader of earnings releases, combinations of signals the lane records) proposed seventeen
candidates, a judge scored them and wrote this file, and an adversarial check read it, each under the rule that no
price after any event, and no return, P&L, look, band or mark of the lane, is read, queried or computed; the judge read
none. The registering captain session (6e6a85b9) had read, on Oct 21, the per-program means of the shadow record of the
lane's existing programs over its first two entry sessions (Oct 19-20) and the lane's aggregate real-money figures; it
took no part in proposing, choosing or wording these rules, which four designers, a judge and an adversarial check wrote
without reading any outcome; it changed nothing in them but the fixes the check stated, WRITTEN_AT and the registration
fields. The calibration of section 3 is synthetic (`docs/prereg/evl-5/calib_evl5.py` and `calib_evl5.out`).

REGISTRATION TIME: the latest of three times, all three recorded in the captain's amendment A92, which pins it as
`REGISTERED_AT_5`: this file's commit time; the pushing client's own clock read after the push of the tag
`prereg-evl-5` returns (A77's later bound); and GitHub's activity time for the push of the branch `prereg/evl-5`. The
tag never moves. A program of this file counts only events knowable after THIS registration time (not PREREG-EVL-1's,
-2's, -3's or -4's). Nothing here changes for a registered program: a change is a new version with its own
registration time.

## 1. The programs

This file adds three seatable programs and one control (a free record) to the lane of PREREG-EVL-1 (frozen
2026-10-19T01:08:38Z), PREREG-EVL-2 (03:04:07Z), PREREG-EVL-3 (05:23:06Z) and PREREG-EVL-4 (16:01:05Z), which it never
edits. It changes no program, record, control, verdict, prompt, judge, band rule or wall of those files. It adds no
prompt, no form and no recorder: every verdict read here is a PROMPT-DOC or PROMPT-NEWS verdict asked and stored as
PREREG-EVL-1 section 4 says, and a verdict already stored for an event is the verdict of every program that reads it.
Its one new input, the gap of section 1.1, is a SIP minute bar of the entry session read from history, as the lane
reads PREREG-EVL-2's reactions.

### 1.1 Terms (every program and control of this file)

- D is the entry session, P the session before it and P' the session before P (the lane's session calendar). Knowable
  times are PREREG-EVL-1 section 3's: EDGAR filings at acceptance + 10 minutes, ENEWS articles at `created_at` + 2
  minutes. An issuer is ELIGIBLE when PREREG-EVL-1 section 2 makes its stock eligible for entry session D; its ELIGIBLE
  TICKER is that stock's symbol. An 8-K's issuer is PREREG-EVL-1 section 2's (the first filer with a ticker), as the
  lane stores it.
- THE CLOSE WINDOW of a session X: knowable at or after the close decision time of the session before X (its close - 14
  minutes) and before X's close decision time (PREREG-EVL-4 section 1.1). The close window of D holds exactly the events
  whose day 0, as EVL-ERN-REACT-C1 defines it (PREREG-EVL-1 section 6), is D. T29 of a session is PREREG-EVL-2 section
  2's (15:29:00 ET on a full day, 12:29:00 ET on a 13:00 close).
- ERN(D) FILINGS: the E8K filings (form type exactly `8-K`; `8-K/A` excluded) with item 2.02 knowable in the close
  window of D, read from the fetched filings with their own items (their EDGAR index page) as every 8-K rule of the
  lane, with NO registration floor.
- THE REACTION of an ERN(D) filing: PREREG-EVL-2 section 2's reaction of an 8-K event with day 0 = D, which is
  EVL-ERN-REACT-C1's: the close of the regular-session SIP 1-minute bar starting at T29 of D (if that minute has no
  trade, the last earlier regular-session minute bar of D) over the raw SIP daily close of the last session that closed
  before the filing's acceptance time. There is no reaction when either price is missing, and the event is then not
  taken.
- DAY(D): PREREG-EVL-4 section 1.1's: the articles of PREREG-EVL-2's day-news window of D (ENEWS with exactly one
  symbol, that symbol the eligible ticker of its issuer for D, knowable after 09:00 ET of D and at or before T29 of D;
  PREREG-EVL-1 section 3's non-live exclusion applied), whatever their verdict or reaction, with NO registration floor.
  THE DAY-NEWS REACTION of an issuer on D (EVL-NEWS-REACT-ON's): the T29 close of D, as above, over the raw SIP daily
  close of P (the last session closed before every DAY(D) article's knowable time; the universe row's previous close for
  D).
- TAKEN AT D'S CLOSE BY AN EARLIER ROW, read with NO registration floor: an issuer (a) with an ERN(D) filing whose
  reaction is >= 1.04 (EVL-ERN-REACT-C1's and EVL-ERN-REACT-ON's), or (b) with a DAY(D) article whose stored PROMPT-NEWS
  verdict is `ok` with score >= 2 (EVL-NEWS-READ-ON's), or (c) in DAY(D) with a day-news reaction >= 1.04
  (EVL-NEWS-REACT-ON's). A DAY(D) article of the issuer with no stored PROMPT-NEWS answer makes the issuer's events WAIT
  in the shadow (the shadow rule; the verdict is EVL-NEWS-READ-ON's own, event `news:<id>`, asked as section 1.2's NO
  NEW PROMPT AND NO SECOND VERDICT says) and skips the issuer in real money (section 1.3); an answer that is `unparsed`
  or `refused`, or `ok` with a score under 2, does not make it taken under (b).
- THE ATTENTION ARTICLES OF P for entry session D: ENEWS articles with exactly one symbol, that symbol the eligible
  ticker of its issuer for D, knowable after the close of P' and at or before T29 of P (EVL-NEWS-READ-O1's window of P
  joined to PREREG-EVL-2's day-news window of P), PREREG-EVL-1 section 3's non-live exclusion applied.
- NO NEW INFORMATION for an issuer on D, read with NO registration floor: (i) no ENEWS article of any source and with
  any number of symbols, PREREG-EVL-1 section 3's non-live exclusion applied (a live article counts; a non-live,
  backfilled article counts only when its `updated_at` is at most 10 minutes after its `created_at`), whose symbols
  include a ticker that SEC's `company_tickers.json` (the copy D's decision reads, PREREG-EVL-1 section 2) maps to the
  issuer's CIK, is knowable after T29 of P and at or before D's close decision time; (ii) no E8K filing of the issuer
  (form type exactly `8-K`, any items, the fetched filings as for ERN(D)) is knowable in the close window of P or of D
  (at or after the close decision time of P' and before D's close decision time); (iii) no EF4 filing (form type exactly
  `4`) of the issuer with PREREG-EVL-2's INSIDER BUY is knowable at or after 09:00 ET of P and before D's close decision
  time.
- THE GAP of an issuer on D: the open of the regular-session SIP 1-minute bar (raw) starting at 09:30:00 ET of D, for
  its eligible ticker, over the raw SIP daily close of P (the universe row's previous close for D). There is no gap when
  that minute has no trade or either price is missing, and the event is then not taken. The bar is on the Basic plan's
  tape from about 09:46 ET, long before the close decision.
- ENTRY, EXIT AND HOLD: every program and control here enters at the CLOSE auction of D (PREREG-EVL-1 section 5: decided
  at the close - 14 minutes from events knowable before it, the order sent by the close - 11 minutes) and exits at the
  OPEN auction of the next session (PREREG-EVL-2 section 2's exit at the open, with PREREG-EVL-1 section 5's fallback
  ladder unchanged). It holds one session in the screen's sense: its block is D, its first settled exit is session 1,
  and its blocks never overlap. THE LIMIT AT ENTRY (PREREG-EVL-2 section 2), shadow and real alike: an entry auction
  above 1.25 x the raw SIP close of P is not filled and the event is skipped.
- UNCHANGED FROM PREREG-EVL-1: the universe (section 2), backfill and the shadow rule (section 3), the verdicts (section
  4), auction prices, costs, r, b, a and TRADABLE (section 5: 1.25 x the previous SIP close at most 10% of the account
  equity at the previous close), and one position per issuer per program (section 5, as A72 reads it).

### 1.2 The programs

Seatable from birth (section 2). Each enters at the CLOSE of D and exits at the OPEN of the next session (hold 1):

| id | events of D | rule | one event per issuer per D | ranking (real money) |
|---|---|---|---|---|
| EVL-ERN-DROP-ON | ERN(D) filings of eligible issuers not TAKEN AT D'S CLOSE BY AN EARLIER ROW | the reaction <= 0.96 (no model) | the earliest knowable filing the rule takes | the fall, 1 - reaction, larger first, then ADV |
| EVL-ERN-UNDER-ON | ERN(D) filings of eligible issuers not TAKEN AT D'S CLOSE BY AN EARLIER ROW and with no ERN(D) filing whose reaction is <= 0.96 | the stored PROMPT-DOC verdict `ok` with score >= 2, AND a reaction above 0.96 and below 1.04 | the highest score, then the earliest knowable | the score, plus 0.5 when that verdict's guidance is "raised", higher first, then ADV |
| EVL-NEWS-NIGHT2-ON | the attention articles of P of eligible issuers with NO NEW INFORMATION on D | the gap >= 1.02 (no model) | the earliest knowable attention article | the gap, higher first, then ADV |

- EVL-ERN-DROP-ON's and EVL-ERN-UNDER-ON's event is `8k:<accession>`. The reaction's three ranges (<= 0.96 for
  EVL-ERN-DROP-ON, above 0.96 and below 1.04 for EVL-ERN-UNDER-ON, >= 1.04 for EVL-ERN-REACT-C1 and EVL-ERN-REACT-ON)
  part every ERN(D) filing that has a reaction, and the issuer skips above keep the issuer sets apart.
- EVL-ERN-UNDER-ON reads the PROMPT-DOC verdict of event `8k:<accession>`: the one verdict EVL-ERN-READ-O1 (for a filing
  knowable before 09:00 ET of D) and the record EVL-ERN-REACT-READ-C1 (for every eligible ERN(D) filing) read, asked
  once and stored as PREREG-EVL-1 section 4 says. A TEXT shorter than 200 characters has no verdict and is not taken.
  READ events wait for their verdict (the shadow rule).
- NO NEW PROMPT AND NO SECOND VERDICT: a PROMPT-DOC verdict of an eligible ERN(D) filing, or a PROMPT-NEWS verdict of a
  DAY(D) article, that this file's rows read and that no row has stored by this file's decision is asked by that
  decision, with the same event id, prompt and rendering as the earlier row that reads it (PREREG-EVL-1 section 4: asked
  once, stored once, the first stored answer final), so a row whose own decisions are kept (a written look of its
  group, A74 (5)) never leaves this file's events waiting for good.
- EVL-NEWS-NIGHT2-ON's event is `news:<id>`, the issuer's earliest knowable attention article of P that is knowable
  after this file's registration time. It holds the issuer's SECOND night after the attention day: the first night (P's
  close to D's open) belongs to PREREG-EVL-2's and -4's overnight rows and is never traded here. NO NEW INFORMATION
  removes every issuer a close-entry row of D can take (DAY(D) and PM(D) by (i); ERN(D) and F8K(D) by (ii)) and every
  issuer an earlier row sells at D's close (EVL-NEWS-READ-O1's PM(D) articles by (i); the open-window 8-Ks of
  EVL-ERN-READ-O1, EVL-ERN-GUIDE-O1 and EVL-8K-READ-O1 and EVL-ERN-REACT-C1's lots of P by (ii); EVL-INS-BUY-O1's Form
  4s by (iii)).
- A filing or an article is an EVENT of a program only when its knowable time is after this file's registration time.
  The sets that skip an issuer (ERN(D), DAY(D), TAKEN AT D'S CLOSE BY AN EARLIER ROW, NO NEW INFORMATION) carry no such
  condition.
- So the three programs share no (issuer, D) with one another and no (issuer, entry auction, exit auction) with any
  seatable program of PREREG-EVL-1 to -4.
- SHARED ELIGIBILITY, A75's KNOWN EDGE, restated for this file's rows (stated, not a reading): eligibility stays one
  result per (entry session, CIK, rule), shared by every program (A70 (8)). This file's rows judge only the issuers of
  their own events, after the earlier rows' own unchanged eligibility call, but EVL-NEWS-NIGHT2-ON's many live checks
  of its surviving attention issuers for D (made from about 09:47 ET of D, section 1.3) and the earnings rows' checks
  become that one result. So a check made for this file's rows can decide, by the live rule, a late-stored event that
  an earlier program's backfill re-decision would otherwise have judged by the backfill rule.

### 1.3 Real money (PREREG-EVL-1 sections 3 and 8, PREREG-EVL-3 section 2, PREREG-EVL-4 section 1.3)

- A real-money decision is the shadow rule over the events STORED, and the verdicts ANSWERED, before D's close decision
  time. It applies TAKEN AT D'S CLOSE BY AN EARLIER ROW and NO NEW INFORMATION to the filings and articles stored before
  that time, and a DAY(D) article with no PROMPT-NEWS answer before that time skips its issuer; a row stored later
  counts in the shadow only, and the report counts the difference. The reactions and the gap are read from SIP minute
  bars as the House's book reads PREREG-EVL-2's reactions (the lane's stored mark when it holds one); a price the book
  cannot read is not bought.
- ROOM: Sized programs first, then Probe, then learning; within a band the tables' order, which is PREREG-EVL-1's rows,
  then PREREG-EVL-2's, then PREREG-EVL-4's, then this file's in the order of section 1.2 (R3's births come after every
  file's rows); within a program its ranking above. When two programs want the same name at one auction, the earlier in
  that order takes it.
- The House's book skips a buy of a name that an event lot sells at the same auction (its sale gate, the reading that
  trades less; the shadow keeps the event). So an earnings name an open-entry row bought at D's open (EVL-ERN-READ-O1,
  EVL-ERN-GUIDE-O1 or EVL-NEWS-READ-O1, for instance) is not bought at D's close by EVL-ERN-DROP-ON or EVL-ERN-UNDER-ON.
  NO NEW INFORMATION keeps every such name out of EVL-NEWS-NIGHT2-ON.
- NO REAL-MONEY TAKING FROM AN EARLIER ROW (PREREG-EVL-4 section 1.3's rule, with A75 (1)'s readings): IN REAL MONEY
  ONLY, EVL-ERN-DROP-ON and EVL-ERN-UNDER-ON do not buy for a filing knowable at or after 09:00 ET of D whose stored
  PROMPT-DOC verdict is `ok` with score >= 2, or `ok` with score >= 1 and guidance "raised", or is not yet answered, at
  D's close decision time: such a filing is EVL-ERN-READ-O1's event (score >= 2) or EVL-ERN-GUIDE-O1's event (guidance
  "raised" and score >= 1, PREREG-EVL-2) at the next open, and this file's sale at that open would take the name from
  that earlier row (the sale gate). For EVL-ERN-UNDER-ON that is every such filing. The guard applies to the issuer's
  one event; no later filing of the issuer replaces a barred one. The shadow keeps the event. A rarer case is not
  prevented and is stated, for all three rows: an issuer bought at D's close that an earlier open-entry row wants at
  the next open (for instance fresh pre-market news the next morning) loses that earlier row's real-money buy to this
  file's sale (the sale gate); the report counts each such case. No rule and no shadow record of any earlier program
  changes.
- TWO MORE WAYS THIS FILE'S LOTS TAKE REAL-MONEY ROOM FROM EARLIER ROWS, stated effects, not prevented, each counted in
  the report: (a) THE DAY ORDER LINE: the event kind's line of 150 orders a day (A74 (7), A78) refuses entries in ROOM's
  order, so on a day that would need more, this file's rows are refused first among the PREREG rows; and each of their
  lots keeps one order of the next session's line for its exit at that open, so their exits use D+1's line and leave
  less of it for D+1's entries. (b) CASH AND ROOM AT THE NEXT OPEN: their overnight lots hold cash, invested room and
  loss-budget room at D+1's open, which the earlier open-entry learning rows need there (A83 (2)(b), as PREREG-EVL-2's
  and -4's overnight lots already do); A85 reserves the next auction's cash only for Probe and Sized programs, so an
  earlier open-entry learning row can lose a real buy at D+1's open to this file's lots.
- THE EARLIER ROWS' DECISION COMES FIRST (the reading of A83 (3)(i)'s isolation of PREREG-EVL-4's part, taken for this
  file's part). The part of a close decision that decides this file's rows runs after every earlier row is decided,
  under its own time bound inside the close task; that bound's expiry, or any failure in the part, is the part's alone
  and never cuts or fails the earlier rows' decision: the decision finishes with the earlier rows' results and names
  none of this file's rows, which `decide-close-evl5` then decides by themselves as a backfill (section 3), so that
  close's events of this file's rows are shadow only and never traded (the reading that trades less). To keep the part
  short, EVL-NEWS-NIGHT2-ON's heavy reads (its attention articles of P, (ii) and (iii) so far, the eligibility of the
  issuers that survive them, and the 09:30 bars of the gap) are made and stored by the session's verdict pre-passes (the
  close decision's own reads made ahead of it, with no intent and no receipt) from about 09:47 ET of D, once the 09:30
  bar is on the Basic plan's tape; the close decision reads them as stored and adds only what came after them (the tails
  of (i), (ii) and (iii) to D's close decision time, and any attention article stored after them) and the reads of TAKEN
  AT D'S CLOSE BY AN EARLIER ROW. Every rule above is unchanged by where it is read: what counts is the stored record at
  D's close decision time.

## 2. Seatable from birth, under PREREG-EVL-3 unchanged

- Version 1 of each program of section 1.2 is its seating version (its id is new, as PREREG-EVL-4 section 2 reads it for
  that file's ids). Each program is SEATABLE at PREREG-EVL-3's LEARNING band from birth: every TRADABLE event that fits
  the walls is entered with real money at a target of 2% of the account equity at the previous close, in whole shares
  at the limit (1.25 x the previous SIP close), one share when that rounds to none and one share at the limit is at most
  5% of equity and fits every wall, at most 8 open learning positions a program. Real money starts at the first decision
  after the House release that carries this file's programs is live (PREREG-EVL-3 section 2; the auction paper proof's
  BUY stage passed on Oct 20, A68 bis); until then, and for every event after the registration time that comes before
  it (backfill included), the programs are decided by the same rules in shadow only (section 3).
- PREREG-EVL-3 sections 2, 3, 5 and 6 apply to this file's programs word for word, with version 1 in place of version 2
  (seed strings `{id}|v1|look{k}`); PREREG-EVL-3 section 4's count is replaced by section 3 here: PROBE from the first
  decision after a passed look (PREREG-EVL-1 section 8: a target of 5%, at most 6 open; the money table's smaller Probe
  share since A86 revised trades less inside that envelope); SIZED (>= 150 settled real-money events at Probe size or
  above with the 80% session-block bootstrap lower bound of the per-event after-cost return above zero: target 10%, at
  most 8 open); DEMOTION to learning (the last 50 settled real-money events at Probe size or above lost more than $150
  net, or the last 100 have a negative mean after-cost return; back to Probe at the next passed look); RETIREMENT at a
  held look whose mean a of the TRADABLE events is below zero with the reversed one-sided sign-flip p at most 0.05; the
  open-risk weight max(0.10, 1.65 x sigma x sqrt(h)).
- THE SCREEN is PREREG-EVL-3 section 3's, unchanged: look k (k = 1..10) at the first session close with at least N_k =
  60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250 settled TRADABLE events, at least 40 distinct issuers among them and
  at least 8 session blocks, covering every block whose scheduled exits are at or before that close (looks in order, at
  most one a close; thresholds first reached at one close are one look); the skew check from alpha = 0.018, which only
  tightens (A65); PASS when the session-block sign-flip p and the issuer-block p are each at most their alpha, the mean
  a of the TRADABLE events > 0 and their mean raw after-cost r > 0, and, for EVL-ERN-UNDER-ON, the mean block value
  exceeds its control's (section 4) over the same sessions. The seed strings are `{id}|v1|look{k}` (with `|issuer`,
  `|skew` and `|skewflip` appended as PREREG-EVL-1 section 7 says). A look waits for a final record as the lane's
  recorded readings of PREREG-EVL-1 section 7 make every program's look wait (A66, A69, A74 and A84's per-feed fast
  path), this file's own decisions (section 3) included. FOR THIS FILE'S ROWS, A69's span begins at the earliest window
  that feeds their decision of a close X: the close decision time of P', two sessions before X (where the close window
  of P, read by NO NEW INFORMATION (ii), begins; the attention articles of P begin at P''s close), not 09:00 ET of the
  session before X (A74 (1)). A84's per-feed clean-read rule then applies from before that start through the span's end,
  and A74 (3)'s daily-index backfill must have run for every weekday from P' through X; otherwise A66's wait applies.
- Only events knowable after this file's registration time count, for the screen, the bands, Sized, demotion,
  retirement and Done. Done, pivot and reporting are PREREG-EVL-3 section 5's, unchanged: these programs' events at
  Probe size or above count toward Done like any program's, and only after their own promotion.

## 3. Expected false passes, the lane's budget, and the record before the release

- 0.10 x every version that can seat: PREREG-EVL-3's nine version 2 programs (0.9), PREREG-EVL-4's three (0.3), this
  file's three (0.3), and 0.10 for each seatable birth of R3 registered before REGISTERED_AT_5: 1.2 + 0.3 + 0.10 x
  those births in all (1.5 when there are none), as SEATING sums them. The control never seats and costs nothing.
- THE LANE'S LIFETIME BUDGET, as PREREG-EVL-4 section 3 states it and A71 and A81 restate it: 3.0 expected false passes
  (thirty seatable versions at 0.10). Used with this file: 1.2 + 0.3 + 0.10 for each seatable birth registered before
  REGISTERED_AT_5, as SEATING sums them; the registering amendment A92 records that count and the sum. Left for R3's
  later births and any later file: 3.0 less that (fifteen seatable versions at 0.10 when no birth came first), at most
  three seatable births a night (A81); R3's validator reads the lane's own SEATING sum. UNTIL THE RELEASE CARRYING
  THESE ROWS IS LIVE, that sum does not yet hold this file's three, so R3's count is 0.3 lower than the used total
  above; at three seatable births a night that cannot take the true total past 3.0 until more than fifteen seatable
  births are registered before that release (the sixth night at three a night: R3's count 1.2 + 0.10 x births, the
  true total 1.5 + 0.10 x births), and A92 checks it. This file is a hand birth: A81 says the captain registers none by
  hand while R3 runs, and the captain's amendment that registers this file (A92) records the exception and why: none
  of its three rules is in R3's GRAMMAR 1 (a reaction range inside 0.96-1.04 joined to a verdict; a second-night window
  with a gap read at the entry session's open; and for EVL-ERN-DROP-ON, whose reaction bound alone a birth could state,
  the skips of the issuers earlier rows take at D's close, the ranking by the fall and the real-money guard of section
  1.3).
- MEASURED FALSE-POSITIVE RATE at this file's event rates (synthetic, PREREG-EVL-3's model and schedule,
  `docs/prereg/evl-5/calib_evl5.py` with `docs/prereg/evl-3/calibrate_events.py`'s sign-flip; the session-block test
  alone): a zero-edge program passes any look within 400 sessions 6.7% of the time at a mean of 3 events a session (seed
  51), 8.0% at 6 and 7.6% at 12; 8.4% at 6 with 5% per-event noise in place of 3% (seed 52); with every one of the ten
  looks reachable (a horizon of 1200 sessions, seed 54) 9.05% at 6; all under the 0.10 charged and the goal's 15%. The
  issuer-block test, the skew check and the TRADABLE count can only lower it, and for EVL-ERN-UNDER-ON the
  beat-the-control rule too.
- POWER (same model, seed 53): an edge of 0.4% an event passes about 84% of the time at 6 events a session (median first
  pass at session 88) and 92% at 12 (median 55); 0.8% about 98% at 6 (median 34) and 99% at 12 (median 20); 0.2% about
  45% and 50% (medians 120 and 72). The issuer-block test, the skew check, the beat-the-control rule and TRADABLE lower
  these and are not measured. Stated plainly: these rows reach Done's pool soon only if their edge is near 0.8% an event
  or more; a smaller real edge passes, but late.
- THE RECORD BEFORE THE RELEASE: every close decision from the registration time to the first one that the House release
  carrying this file's code makes is decided for this file's programs BY THEMSELVES, once each, oldest first, as a
  backfill (a receipt of its own kind, `decide-close-evl5:<day>`, as PREREG-EVL-4's rows were decided by
  `decide-close-evl4`): the shadow rule of PREREG-EVL-1 section 3 over the stored record (knowable times; filings,
  articles, verdicts and prices whenever stored); no earlier row is decided again and no intent of an earlier row is
  written. Real money for this file's programs starts at the first close decision after that release is live, with
  every wall; no event decided before then is ever traded. A close after the release whose part for this file's rows
  failed or ran past its own time bound (section 1.3) is decided the same way, by themselves, and that close's events
  of this file's rows are never traded.

## 4. Controls (free records)

- EVL-CTRL-ERN-UNDER-ON: every EVL-ERN-UNDER-ON event before its verdict rule: the ERN(D) filings knowable after this
  file's registration time, of eligible issuers not TAKEN AT D'S CLOSE BY AN EARLIER ROW and with no ERN(D) filing whose
  reaction is <= 0.96, whose reaction is above 0.96 and below 1.04, with or without a verdict, one per issuer per D by
  the same order (the highest stored score, then the earliest knowable; a filing without a stored `ok` score ranks
  after every one with it); entry and exit as section 1.2. It is EVL-ERN-UNDER-ON's control; it waits for the stored
  scores it ranks by (as EVL-CTRL-NEWSPM-ON, A75 (5)), never for a filing whose TEXT gets no verdict. Its figures also
  give the family's base rate in the report: the night after an earnings day on which the price did not move 4%.
- EVL-ERN-DROP-ON and EVL-NEWS-NIGHT2-ON read no verdict and have no control condition, as PREREG-EVL-2's and -4's REACT
  rows.
- Controls are shadow records: they never seat, never trade, cost no expected false pass, and are compared over the READ
  program's own block sessions (PREREG-EVL-1 section 7: the control's TRADABLE events of each of those sessions
  averaged, then the sessions averaged).

## 5. What is unchanged

Everything this file does not state is PREREG-EVL-1's, -2's, -3's and -4's, word for word: the universe, the events,
the knowable times, backfill and the shadow rule; the verdicts, their model, prompts (PROMPT-DOC and PROMPT-NEWS and
their SHA-256), parsing and the rule that the first stored answer is final; the execution model, auction prices, the
fallback ladder, costs, per-event returns and TRADABLE; the screen; the nine version 2 programs, PREREG-EVL-4's three,
every version 1 record and every control of those files, and their place in ROOM ahead of this file's rows; the bands,
Sized, demotion and retirement; the money walls (<= 10% of equity a name, <= 100% invested, no margin, no shorts), the
loss budget ($400 net in any 20 sessions, $800 net total, realized plus open risk), the open-risk rule, the kill switch
and the stops; Done, pivot and reporting.

## 6. Why these three, and their rates (the judge's prior, stated before any outcome)

- WHAT THEY ADD. The lane's six overnight rows hold the FIRST night after an earnings rise, a day-news article, a
  material 8-K or pre-market news. This file holds the two earnings nights those rows leave (after a large fall, and
  after a positive release the price has not followed) and, off earnings and all year, the SECOND night after a news
  attention day, which no row holds. Two of the three read no model; the third reads only verdicts the lane already
  asks, so the file adds no verdict cost, and its only new price read is one minute bar a candidate.
- EVL-ERN-DROP-ON. FOR: Berkman, Koch, Tuttle and Zhang (2012, JFQA 47(4)) proxy attention by the previous day's
  ABSOLUTE return, among other measures: high-attention stocks earn positive returns from that close to the next open,
  which reverse during the next session, strongest in small, volatile stocks traded by individuals. Barber and Odean
  (2008, RFS 21(2)): individual investors are net buyers of attention-grabbing stocks, on days of extreme negative
  returns as on extreme positive ones. Nagel (2012, RFS 25(7)): short-term reversal is the return to supplying
  liquidity, larger when volatility is high; a buy in the closing cross of a stock that fell 4% or more on its release
  supplies it. Bogousslavsky and Muravyev (2023, "Who trades at the close? Implications for price discovery and
  liquidity"): demand concentrated in the closing auction leaves temporary pressure in the closing price that partly
  reverses afterwards (the judge's confidence in that paper's exact figures is moderate). It is EVL-ERN-REACT-ON's
  attention night on the falling side, with the opposite liquidity prediction (a rise's close is bid up, a fall's
  pressed down). AGAINST: price moves that come with public information continue rather than reverse, mainly after bad
  news (Chan 2003, JFE 70(2); Savor 2012, JFE 106(3)); post-earnings drift follows bad news as well as good (Bernard and
  Thomas 1989, JAR 27), though Martineau (2022, Critical Finance Review 11) finds it largely gone by day 1 outside
  micro-caps; Cox and Peterson (1994, JF 49(1)) find the rebound after large one-day declines mostly bid-ask bounce,
  which auction prices remove only in part. If attention or liquidity drives the night, this row and EVL-ERN-REACT-ON
  pass together; if the information continues, this one fails. Strength: weak to moderate.
- EVL-ERN-UNDER-ON. FOR: when attention is scarce the immediate response to earnings news is weaker and the later drift
  larger: on days with many announcements (Hirshleifer, Lim and Teoh 2009, JF 64(5)), the case of this season's peak
  (134 item-2.02 filings over Oct 19-21 in the facts), and on Fridays (DellaVigna and Pollet 2009, JF 64(2)). Engelberg
  (2008, working paper, "Costly information processing: evidence from earnings announcements"): the soft, textual
  content of earnings news predicts returns over a longer horizon than the numbers do, because it costs more to process;
  a positive reading of the release text that the price has not followed by T29 is that case. These three measure the
  later drift over about 60-75 trading days from day 2 after the announcement, so they support a slow response to the
  release but do not test this row's one-night leg (D's close to the next open), which falls inside their announcement
  window. Lopez-Lira and Tang (2023, arXiv 2304.07619): language-model readings of news predict next-day returns, more
  in small stocks. The leg is the first night after the earnings day (Berkman et al. 2012), which no row holds for these
  issuers. The control asks whether the reading adds anything to the night of every muted earnings issuer. AGAINST: a
  muted move may mean the release met the consensus the reader cannot see; Heston and Sinha (2017, FAJ 73(3)) find
  positive news priced within about a day; Lopez-Lira and Tang find the long side the weaker; Martineau (2022). It reads
  EVL-ERN-READ-O1's verdicts on the next leg (as PREREG-EVL-4's EVL-8K-READ-ON reads EVL-8K-READ-O1's), so a false pass
  of one makes the other's likelier. Strength: weak to moderate.
- EVL-NEWS-NIGHT2-ON. FOR: overnight returns persist. Lou, Polk and Skouras (2019, JFE 134(1)): a stock's past overnight
  returns predict its future overnight returns, and overnight and intraday clienteles persist; Aboody, Even-Tov, Lehavy
  and Trueman (2018, JFQA 53(2)): overnight returns measure firm-specific investor sentiment, persist in the short term
  and reverse over longer horizons. Attention-driven demand outlasts one day: Da, Engelberg and Gao (2011, JF 66(5)):
  abnormal attention predicts higher prices over the next two weeks and a reversal within the year, in small,
  retail-held stocks; Seasholes and Wu (2007, JEF 14(5)), on Shanghai stocks that hit the upper price limit:
  individuals' attention-driven buying lasts a few days and the price reverses within days, which argues as much against
  a second-night hold as for it. A first-night gap of 2% or more is the footprint of the next-open buying Berkman et al.
  (2012) find; this row buys at D's close, after D's intraday reversal, and holds the second night, with no new article,
  8-K or insider buy to carry information. AGAINST: Berkman et al.'s reversal may run on into the second night; Chan
  (2003) and Savor (2012) also find that price moves WITHOUT public news reverse, and this row's gap at D's open comes
  by design with no new article, 8-K or insider buy, which is that case; no paper the judge knows tests a second night
  after a news gap at a one-session horizon; a gap often comes from news outside Alpaca's feed; gap days cluster on
  market-wide moves (the benchmark and the session blocks absorb the level). Strength: weak.
- AGAINST, ALL THREE: one mechanism family with the lane's six overnight rows (the night after attention), so their
  errors are correlated with those rows' and with one another's; the 0.10 each already charges that in expectation. The
  round trip is 14-24 bp of a position.
- RATES (before any was counted for these rows; FACTS files, counts only). Earnings: 134 item-2.02 filings over Oct
  19-21 (8k_items_oct19_21, Oct 21 to the snapshot), against 57 over Oct 15-19 (evl4 8k_by_item); EVL-CTRL-ERN-ALL-O1,
  every eligible earnings issuer at an open, selected 43 and 58 on Oct 20 and 21: about 40-60 eligible ERN(D) issuers a
  session now (the close window and the open window hold nearly the same filings: P's after-close releases and D's
  pre-market ones). EVL-ERN-READ-O1 selected 18 and 26 (score >= 2): the reading's share is 42-45%. The decision-time
  selection counts of EVL-ERN-REACT-C1 (11 and 4) and EVL-ERN-REACT-READ-C1 (8 and 3), reactions >= 1.04, are the facts'
  only reaction counts; they count a decision input, never a return after an entry. EVL-ERN-DROP-ON: the share 4% or
  more down at T29 is not in the facts; assumed within the rising share's range, 7-26%, less about 10% for the skips:
  about 3-13 a session, central 6. EVL-ERN-UNDER-ON: score >= 2 with a reaction below 1.04 is about 10-23 a session (18
  less 8, 26 less 3); less the fallers (assumed 10-20%) and the issuers TAKEN by a day-news row (assumed 25-50%: the
  share of muted earnings names with a day article scoring >= 2 is not in the facts): about 5-14, central 7; its control
  about 15-30. News: eligible pre-market issuers a session (EVL-CTRL-NEWS-ALL-O1) 135, 248 and 515 and eligible day-news
  issuers (EVL-CTRL-NEWS-DAY-ON) 235, 219 and 550 on Oct 19-21 (news_per_day 917, 1,174 and 2,255; the facts count 1,560
  fiscal.ai articles over Oct 19-21 without their days: that they begin about Oct 20 and lift Oct 21 is an inference,
  not a count): about 300-800 attention issuers a session. EVL-NEWS-NIGHT2-ON: the share gapping 2% or more at D's open
  is a price and was not counted, assumed 8-15%; the share with NO NEW INFORMATION through D's close decision was not
  counted, assumed 25-50% (news names draw follow-ups, and (i) reads every source and every multi-symbol article): about
  6-60, central 12. Most events are TRADABLE (a previous close up to about $150 at today's equity), so the first look's
  minimums (60 TRADABLE events, 40 issuers, 8 blocks) come at about session 8 for EVL-NEWS-NIGHT2-ON, 9 for
  EVL-ERN-UNDER-ON and 10 for EVL-ERN-DROP-ON. SEASON: the two earnings rows run at these rates only to about
  mid-November (the general earnings calendar, not the facts) and then at perhaps a fifth of them until mid-January;
  EVL-NEWS-NIGHT2-ON runs all year.
- STATED RISKS: real money at learning takes what the earlier rows leave (ROOM's order, the cash at the close auction,
  the sale gate: the two earnings rows lose the names the open-entry rows bought at D's open), so its picks rank lower
  than the shadow's best; this file's lots also take real-money room from earlier rows in the two ways section 1.3
  states (the event kind's day order line refuses these rows first and their exits use the next session's line; their
  overnight lots hold cash and room at the next open that the earlier open-entry learning rows need, and A85 reserves it
  only for Probe and Sized), both counted in the report; at 6 events a session only an edge near 0.8% passes before the
  season ends; EVL-ERN-DROP-ON buys large losers into the night (a crash tail: the skew check only tightens, the
  open-risk weight, demotion and the loss budget bound the money); EVL-ERN-UNDER-ON buys a reading the price disagreed
  with; EVL-NEWS-NIGHT2-ON's rate may be far below 12 if (i) catches most gappers (fiscal.ai's coverage is new and
  unmeasured), and (i) cannot see news outside Alpaca's feed; a verdict outage or the day's verdict line leaves
  EVL-ERN-UNDER-ON, and the day-news skip of both earnings rows, pending; the assumed shares are not in the facts, and
  the report counts each row's funnel.

## 7. What is not decided here

The code (league/events/programs.py's rows, families and rule kinds, run.py's close decision and its
`decide-close-evl5`, book.py's rows, picks and guard, screen.py's registries and the final-record rule for this file's
receipts, births.py's facts for the new families), the site and the docs, built after this file to these rules; the
build's plan is a guide and this file wins. If an implementation finds a rule here ambiguous, it takes the reading LESS
LIKELY TO PASS (screen rules) or that trades less (trading rules), fixed before the program's first settled event and
recorded as an amendment; a later resolution is a new version.

# PREREG-EVL-7: two pre-registered online learners, judged on their forward picks at an honest cost

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6e6a85b9) under the owner's goal as he re-set it at 05:15Z
Mon Oct 19, 2026 (`goal-2026-10-19/GOAL-MESSAGE-V2.txt`): "Births come from your architect agents and from you, using
outcome-free facts, rationed by an expected-false-pass budget you state ... Promotion to Probe and Sized, demotion and
retirement are pre-registered sequential tests counted in settled events, never days, at a false-positive rate <= 15%
by issuer-block permutation. Capital follows evidence across the swarm", and under his request of Oct 22 for a game
design and harness that become more profitable over time, not only faster (the captain's A96).
Written 02:45Z-@@WRITTEN_END@@ Oct 22, 2026 (the design workflow wf_d6f108bd-400: four designers from 02:45Z, the judge
from 04:37Z, two adversarial checks after the judge; from 12:30Z the fix workflow wf_9ff83a61-b88 applied both checks'
findings under the captain's decisions E1-E11 of A110 against PREREG-EVL-6 AS FROZEN and recalibrated the learners on
fresh synthetic seeds; its two re-checks read this text before the freeze).

HOW IT WAS MADE. The captain's A96 (02:40Z Oct 22) opened this design before any design existed. Four independent
designers (pre-registered online learners; a second reader and model tiering; costs, execution and hold structure;
allocation) each wrote one design and calibrated it on synthetic returns; a judge chose among them and wrote a draft
(`goal-2026-10-19/evl7/PREREG-EVL-7.draft.md`, kept beside this file); two adversarial checks read the draft and re-ran
its calibration on fresh seeds (`evl7/EDGE-RESULT.json`, keys `judge`, `check-1`, `check-2`, `design-*`). Both said
FIX: the draft was calibrated against PREREG-EVL-6's superseded draft screen. After PREREG-EVL-6 froze
(REGISTERED_AT_6 = 2026-10-22T12:24:50Z, A116), the fix round applied every finding of both checks under the
captain's decisions E1-E11 and re-measured the learners under the frozen screen on its frozen plausible grid (section
5). Each of them worked under the rule that no price after any event, and no return, P&L, look, band or mark of the
lane, is read, queried or computed; none was.

PROVENANCE. The design workflow ran from `goal-2026-10-19/workflows/edge_engine.js` (sha256
b5612f425526c2cd640fae9e0d2f7419c94c7378fac90a456fd6cc4ec972c3dd) and the fix round from
`goal-2026-10-19/workflows/evl7_fix.js` (sha256 1245cce5d071afe6875e170afbc9deefa88380f3e30357a04a6792c8097261f1).
Both scripts' prompts carried only outcome-free counts (`goal-2026-10-19/speed/SPEED-FACTS.md`,
`goal-2026-10-19/speed/EXECUTION-FACTS.md`), the frozen texts, the drafts and the code, and pointed to the captain's
amendments record (`scratch/eqlane-1010/CAPTAIN-AMENDMENTS.md`). That record also holds the captain's outcome-derived
A96 line (three sessions of shadow showed no program clear of noise: no figure, the same for every program), which no
designer, judge, checker or fixer was asked to use and no constant here reads. The registering captain session
(6e6a85b9) had read, on Oct 21, the per-program means of the shadow record of the lane's programs over its first two
entry sessions (Oct 19-20) and the lane's aggregate real-money figures. It wrote both workflows' prompts and the
decisions E1-E11, and it chose no rule parameter: E1-E11 adopt the blind checks' stated fixes and set E1's measurement
protocol (the frozen screen, its plausible grid, both lags, fresh seeds, at least 4,000 programs at the worst cells,
the charge as the larger of PREREG-EVL-6's and the measured worst rounded up); every constant of sections 1-3 was
proposed by the blind designers or the judge, fixed by the checks, or measured by the blind recalibration of section 5.
For these reasons every record of this file counts only events knowable after REGISTERED_AT_7 (as PREREG-EVL-6 does,
A91), and only decisions the House makes live (section 1.7).

REGISTRATION TIME: the latest of three times, all three recorded in the captain's amendment that pins it as
`REGISTERED_AT_7` (A92's method): this file's commit time; the pushing client's own clock read after the push of the
tag `prereg-evl-7` returns (A77's later bound); and GitHub's activity time for the push of the branch `prereg/evl-7`.
The tag never moves. IF REGISTERED_AT_6 IS NOT EARLIER THAN REGISTERED_AT_7, OR PREREG-EVL-6 WAS NEVER FROZEN, THIS FILE
REGISTERS NOTHING: its programs never decide, trade or draw any charge (section 3.3; E3). A program of this file counts
only events knowable after REGISTERED_AT_7. Nothing here changes for a registered program: a change is a new version
with its own registration time.

## 0. The findings that shaped this file

- SLOTS BIND, NOT SUPPLY (A94; SPEED-FACTS): on Oct 21 the controls shadowed about 2,438 intents, about 1,500 of which
  settle each night with an after-cost return, while real money took about 24 buys a session. Every seatable program
  of PREREG-EVL-1 to -6 is a FIXED filter: its selection never improves however many outcomes settle. A program whose
  rule is a fixed LEARNING ALGORITHM, refit at each decision on outcomes settled and stored before it, chooses which
  of several hundred candidates fill its 8 slots, and its choices can improve as the labelled stream grows. Because
  the controls shadow every eligible event, it sees every candidate's outcome, picked or not: this is full-information
  online regression, not a bandit, and it needs no exploration. Using settled outcomes at run time is a forward test:
  every pick is made before its own outcome exists. Only its DESIGN must be blind, and it is fixed here.
- JUDGED EQUALS TRADED. `book.picks` sorts a program's real-money picks by (rank_key, then adv20): a READ program with
  165 score >= 2 shadow intents for 8 learning slots (EVL-NEWS-READ-O1, Oct 21) buys the 8 LARGEST names among its
  ties, while its screen judges all 165. A learner's shadow record IS its at most 8 ranked picks, and real money takes
  them in the same order: the evidence that promotes it is the evidence real money earns.
- THE REPLAY ASSUMES EVERY FILL AND NO IMPACT. All 84 real fills of Oct 20-21 printed at exactly the replay's auction
  price (EXECUTION-FACTS), while PREREG-EVL-1 section 5's replay charges 14.2 bp a round trip (ADV >= $10M) or 24.2 bp
  (thinner) at today's equity (league/events/score.py `cost_bp`); it also assumes every shadow event is filled, while
  the venue cancelled about a quarter of the auction buys (A80). Done counts realized after-fee P&L. So this file's
  versions are judged on COST-7 (section 2): fees at their Probe size, a margin and a modelled square-root impact at
  Sized size whose volatility is the name's own (E9), PLUS two measured terms that only ever rise: a slippage margin
  from the real fills and a selection charge from the real non-fills. At today's equity and at its warm-up
  (`final/cost7_w7.py`, `cost7_w7.out`), replay minus COST-7 averages +1.0 to -2.4 bp for ADV >= $10M and +8.6 to -4.7
  bp for thinner names as sigma runs from 0.02 to 0.10; on the learner's own picks in the generator (mean sigma
  0.045-0.057 in the null cells, 0.065-0.081 when the features carry information) COST-7 is 1.3-1.9 bp (the null cells)
  to 3.0-4.2 bp (the alternative's higher-volatility picks) a round trip STRICTER than the replay; at $30k it is
  stricter for thin names by 10.9 to 50.4 bp a round trip at sigma 0.04-0.10, as the square-root law says it must be,
  and stricter again whenever real execution is worse than the print. It is an honesty and scale lever, not a speed
  lever (sections 5.6-5.7).
- WHAT THE FIX ROUND CHANGED (the captain's E1-E11, each a blind check's stated fix): the screen is PREREG-EVL-6's AS
  FROZEN, cited by its sha256, and the learners are re-measured under it on its frozen plausible grid at both training
  lags on fresh seeds (E1; section 5); a learner version's RUNS are PREREG-EVL-6's, at most three for an id's life, each
  charged when it starts, in place of re-entry by new versions (E2; section 1.10); no fallback screen (E3); the
  decisions made before the release are the learner's TRAINING STATE and a reported shadow, never its judged record,
  decided once by code whose sha is pinned, with this file's implementation choices pinned here (E4; sections 1.7,
  1.11); eligibility read only as decided by the House's own decision of the auction (E5); EVL-LRN-ON's '1530' mark
  read by its bar time (E6); the label is the GROSS abnormal return, so the replay's cost enters a pick once (E7);
  EVL-LRN-O1 does not buy an ERN(D) issuer in real money (E8); COST-7's impact reads the name's own sig20 (E9);
  EVL-LRN-ON's real-money 8-K guard reads every 8-K of the issuer (E10); and every minor of both checks (E11).
- WHAT WAS NOT TAKEN, AND WHY (the judge's decisions):
  - READER-2 and its two slot-rule programs (the reader lens): NOT REGISTERED. They cost about $0.88 a day more (the
    lens's `cost_model.py`), A102 prices each metered dollar a session at about 6 sessions of time-to-Done in the best
    scenario, their structured-output path through the gateway is untested, and their gain rests on an assumed rise in
    the reader's information (rho 0.3 to 0.45). Kept for a later file, which must register READER-2 TOGETHER WITH the
    programs and the learner version that read its fields, before any READER-2 read exists, so that no designer can
    see a READER-2 field beside an outcome. The lens's FREE, model-less features (its 16 frozen headline flags and the
    headline-staleness measure) ARE taken into the learners here (section 1.4).
  - Re-costing every current seat on COST-7 ("Option 0" of the cost lens): NOT TAKEN. It would change what
    PREREG-EVL-6's fifteen new versions are judged on hours after their registration. A later file may re-cost seats
    when they are next re-versioned, with a trigger that reads execution records only.
  - CAPITAL FOLLOWS EVIDENCE's ROOM-by-evidence and its faster demotion and retirement (the allocation lens): NOT TAKEN
    as money rules. Reordering ROOM by evidence changes what a registered version trades (the ground on which A97
    refused Probe room 14 for registered versions); PREREG-EVL-6 retires a version at its lower tail (RETIRE), ends a
    run at its 60th block and demotes a Probe stay by its fixed reads, its money stop and its lower tail. The lens's
    evidence ledger and learning curve become reports (the harness list), outcome-derived and never shown to a designer.
  - Slot turnover, multi-session drift holds, reaction-conditioned close entries and the auction-participation cap
    (the cost lens): NOT TAKEN here. No program of this file holds more than one auction span or needs them; the cap
    never binds at today's sizes and becomes a capacity report.

## 1. The learners

### 1.1 Terms

- D is the entry session; n(s) is the lane's session index (calendar.py's sessions in order); tau is the learner's
  decision time of D (section 1.2). E_prev is the account equity at the previous session's close as score.py reads it
  (`equity_on`). TRADABLE at decision: 1.25 x the universe row's `prev_close` of D <= 10% of E_prev (PREREG-EVL-1
  section 5's rule read at the decision).
- STORED BEFORE TAU, the cut-off every input of a decision obeys: a filing whose documents were stored before tau
  (A72: the latest `documents.stored_at` of its raw and text documents); an article whose `received_at` is before tau;
  a verdict whose `answered_at` is before tau; an outcome whose `status` is 'settled' and whose `settled_at` is before
  tau. A universe row of D and the daily bars of sessions BEFORE D are read as stored whatever their write time (their
  values are made from sessions before D's open and carry no information about D or later). `cik_info.sic` is read as
  stored (a static attribute).
- ELIGIBILITY (E5): the LIVE rule's ELIGIBLE result for (D, CIK) (PREREG-EVL-1 section 2, A70 (8); the `eligibility`
  row with `rule` 'live' and `eligible` 1, as real money reads it) whose `eligibility.decided_at` is AT OR BEFORE THE
  FINISH OF THE HOUSE'S OWN DECISION OF THAT AUCTION: the earliest `finished_at` of a receipt `decide-open:<D>`
  (EVL-LRN-O1) or `decide-close:<D>` (EVL-LRN-ON) with status 'ok' or 'pending' (the receipts `book.decided` reads as
  the lane's own decision having run), and never later than the learner's entry auction of D (09:30 ET of D for
  EVL-LRN-O1, D's close for EVL-LRN-ON), the earlier of the two checks' bounds. A result written later, or none, makes
  the issuer not a candidate. The same cut-off holds in the live decision, the catch-up and a
  failed part's later decision (section 1.7), the reconstruction (section 1.5) and the nightly recompute (section 1.8).
  The learner's part never writes an eligibility result.
- THE '1530' MARK (EVL-LRN-ON's item 15; E6): m1530 = the lane's '1530' mark of D for the ticker (`marks` label '1530':
  the close of the last SIP minute bar ending at or before 15:30 ET, or close - 30 minutes on an early close), ITS OWN
  BAR TIME BEFORE TAU, READ WHATEVER ITS FETCH TIME. The close decision fetches the marks of EVL-LRN-ON's candidates in
  its batched requests (run.py `_marks_1530`, `MARK_BATCH` 100) as its first read at or after 15:46 ET (`_marks_1530`
  reads nothing before 15:30 ET + `U.SIP_DELAY`). A mark not stored by the end of the learner's part is missing at the
  live decision (`dmove_missing` 1). A price stamped 15:29 carries no information after tau; the catch-up, a failed
  part's later decision and the reconstruction read the mark as stored.
- A learner's POOL is a fixed, ordered list of version 1 programs of PREREG-EVL-1 to -5 (section 1.2). A POOL OUTCOME of
  (session s, issuer i) is the outcomes row of the first pool program, in pool order, that holds an intent of issuer i
  entering at s at the learner's own entry and exit auctions. The entry and exit prices, the benchmark and the costs of
  an issuer's event at those two auctions are the issuer's, whichever of its events the row is, so a pool outcome is the
  issuer's outcome at the learner's auctions. A pool outcome whose raw entry print was above 1.25 x the previous SIP
  close (PREREG-EVL-2's LIMIT AT ENTRY, which some version 1 controls do not apply) is not a pool outcome: the learner
  could never have held it, so it is neither a training label (section 1.5) nor a POOL value (section 6).

### 1.2 The programs

Version 1 of each id below is seatable at PREREG-EVL-3's LEARNING band from birth. Each holds one session in the
screen's sense (its block is D; blocks never overlap). PREREG-EVL-2's LIMIT AT ENTRY applies, shadow and real alike:
an entry auction above 1.25 x the raw SIP close of the session before D is not filled and the event is skipped. This
file registers no other version of either id (section 1.10).

| id | entry -> exit | tau | pool (each at version 1, in this order) | candidates a session (SPEED-FACTS, Oct 20-21, before merging by issuer) |
|---|---|---|---|---|
| EVL-LRN-O1 | OPEN of D -> CLOSE of D | D's open decision time (09:15 ET) | EVL-CTRL-NEWS-ALL-O1, EVL-CTRL-8K-ALL-O1, EVL-CTRL-ERN-ALL-O1, EVL-INS-BUY-O1 | about 340-620 |
| EVL-LRN-ON | CLOSE of D -> OPEN of D+1 | D's close decision time (the close - 14 minutes) | EVL-CTRL-NEWS-DAY-ON, EVL-CTRL-NEWSPM-ON, EVL-CTRL-8K-ON, EVL-ERN-REACT-ON, EVL-ERN-DROP-ON, EVL-CTRL-ERN-UNDER-ON | about 420-850 |

- A pool program not yet live contributes no candidate (EVL-ERN-DROP-ON and EVL-CTRL-ERN-UNDER-ON are PREREG-EVL-5's,
  live from the release carrying PREREG-EVL-5's code and its catch-up).
- The two learners use disjoint auctions (the open and the close) and disjoint pools, so they are two tests.
- Each has a free derived control (section 6): EVL-LRN-O1-POOL and EVL-LRN-ON-POOL.

### 1.3 Candidates at tau

- For each pool program p, in pool order: the events p's own rule takes for entry session D, read as real money reads
  them (PREREG-EVL-1 section 3's real-money reading; `book.picks(lane, p, D, decided_at=tau)`): rows stored before
  tau, verdicts answered before tau (a verdict not answered before tau reads as no score), the eligible universe rows
  of section 1.1 only, p's own one-position rule, and for EVL-ERN-REACT-ON and EVL-ERN-DROP-ON the book's own reaction
  reading of the SIP minute bars.
- ONE CANDIDATE PER ISSUER (CIK): its POOL FAMILIES are the pool programs selecting the issuer; its PRIMARY EVENT is the
  event of the first of them in pool order, and the learner's intent, if picked, is that event. An event with no CIK is
  no candidate.
- A candidate is KEPT for the fit's centring (section 1.6) when it is TRADABLE at decision.
- A kept candidate is ELIGIBLE TO BE PICKED when also (ii) its primary event is knowable after REGISTERED_AT_7, and
  (iii) the learner holds no intent of the issuer entered before D that exits within the last 5 sessions or later, nor
  a written, non-skipped intent of the issuer entering within the 5 sessions after D (PREREG-EVL-1 section 5 as A72
  reads it). (iii) counts every written, non-skipped intent of the learner's id and version, the catch-up's and a
  failed part's later decision's included (section 1.7), so a session's picks are the same however it was decided.

### 1.4 Features

Every input is stored before tau (section 1.1). A missing input reads 0 and sets its own indicator where one is listed.
Definitions, order and scaling never change within a version. The vector x of a candidate is, in this order:

1. Primary pool program dummies, the first pool program the baseline (EVL-LRN-O1: 3; EVL-LRN-ON: 5).
2. `multi`: two or more pool programs select the issuer.
3. From the BEST `ok` verdict answered before tau among the candidate's pool events (PROMPT-NEWS for an article,
   PROMPT-DOC for an 8-K; best = the highest score, then the earliest knowable, then the lowest event id): `s_num` =
   score / 3; `s>=2`; `s=3`; `s<=-1`; `no_score` (no such verdict: the four before read 0). Five columns.
4. `s_num` x each primary dummy of item 1 (3; 5).
5. That PROMPT-DOC verdict's guidance "raised"; "lowered" (2).
6. The primary 8-K's items 1.01, 2.01, 7.01, 8.01 (4; 0 for a primary that is not an 8-K).
7. `src_benzinga`: the primary article's `source` contains "benzinga".
8. `n_art` = ln(1 + the single-symbol articles of the ticker knowable in the primary pool program's window and stored
   before tau); `n_att20` = ln(1 + such articles knowable in the 20 sessions before that window); `first20`: the issuer
   is in none of this learner's KEPT candidate sets of the previous 20 sessions (3).
9. `mon`, `fri`: D is the first / the last session of its calendar week (2).
10. Issuer, from D's universe row and `cik_info`: ln(adv20 / 1e7); ln(prev_close / 20); ln(sig20 / 0.03); `bench_iwm`;
    SIC groups bio (2833-2836, 8731), tech (3570-3579, 3600-3699, 7370-7379), fin (6000-6799), energy (1000-1499,
    2900-2999) (8). sig20 is the standard deviation of the 19 daily log changes of the issuer's 20 latest stored raw SIP
    daily closes of sessions before D, floored at 0.005 and capped at 0.25.
11. r1 = clip(ln(c1 / c2), +-0.5), r5 = clip(ln(c1 / c6), +-1), r20 = clip(ln(c1 / c20), +-1.5), c1 the latest of those
    closes (the previous close), c2 the one before it, and so on (3).
12. `hist_missing`: fewer than 20 such closes are stored; then sig20 is 0.03, and items 10's ln(sig20 / 0.03) and 11
    read 0 (1).
13. THE FREE HEADLINE FEATURES (taken from the reader lens, `goal-2026-10-19/evl7/reader/features_spec.py`, copied into
    `docs/prereg/evl-7/` at the freeze with its sha256), for a primary that is an article and 0 otherwise: the 16
    `KEYWORDS` flags (case-insensitive regular expressions over the stored `headline`: kw_upgrade, kw_downgrade,
    kw_initiate, kw_pt, kw_raise, kw_cut, kw_beat, kw_miss, kw_fda, kw_deal, kw_offering, kw_buyback, kw_dividend,
    kw_contract, kw_guidance, kw_move), and `dup72` = the largest `jaccard(words(h), words(h'))` (that file's tokenizer
    and STOP list) between the headline h and the headline h' of every stored article naming the ticker (any number of
    symbols) knowable in [k - 72 hours, k) and stored before tau, k the primary article's knowable time; 0 when there is
    none (17).
14. EVL-LRN-O1 only, the primary event's knowable time (ET): `overnight` = any knowable time from 20:00 to 04:00 ET, and
    any hour of a day that is not a session; `pre` = 04:00-07:00 ET of D; `late` = 07:00-09:00 ET of D; every other
    knowable time is the baseline; `ln_ins` = ln(1 + purchase value / $50,000) of an EVL-INS-BUY-O1 event, 0 otherwise
    (4).
15. EVL-LRN-ON only: `morning` (the primary knowable 09:00-12:00 ET of D) and `before` (knowable before 09:00 ET of D;
    the baseline: after 12:00 ET of D); `dmove` = clip(ln(m1530 / prev_close), +-0.5), m1530 the ticker's '1530' mark of
    D as section 1.1 reads it; `dmove_missing` (no such mark: `dmove`, |dmove| and `s_num` x `dmove` read 0); |dmove|;
    `s_num` x `dmove` (6).

So D = 57 columns for EVL-LRN-O1 and 63 for EVL-LRN-ON.

### 1.5 Training rows and the fit

- TRAINING ROWS at tau: every kept candidate (s, i) of every earlier entry session s of the learner (at most 250
  sessions back by n(s)) whose (s, i) has a POOL OUTCOME with status 'settled', `tradable` 1 and `settled_at` before
  tau. Its features are the ones stored for it as of its own decision tau_s (`learner_cands`), never recomputed. For
  entry sessions before REGISTERED_AT_7 (the lane's sessions from Oct 19), the candidate sets are RECONSTRUCTED ONCE, as
  of each session's own tau_s, by sections 1.3-1.4 from stored times, and written (section 1.8); for the sessions from
  REGISTERED_AT_7 to the release they are written by the catch-up (section 1.7). Neither is ever rebuilt.
- LABEL (E7): y = clip(a_g / sig20, -5, 5), a_g = exit_px / entry_px - bench_exit / bench_entry, the pool outcome's
  GROSS abnormal return (the outcomes row's prices, adjusted as in score.py; no cost), and sig20 the candidate's own
  (item 10 or 12). The replay's cost enters a pick once, through c_i in section 1.6. A test pins that the label reads
  no `cost_entry_bp`, `cost_exit_bp`, `r` or `a` column.
- WEIGHTS: w_s = 2^(-(n(D) - n(s)) / 40) (a half-life of 40 sessions).
- WITHIN-SESSION DEMEANING: within each session s, x~ = x - mean_s(x) and y~ = y - mean_s(y) over its training rows (a
  session with one row adds nothing). The day shock common to a session, the pool's drift and the benchmark cancel.
- A = sum_s w_s sum_i x~ x~', b = sum_s w_s sum_i x~ y~, N_w = sum_s w_s n_s, every sum a `math.fsum` in (entry day,
  CIK) order. d_j = sqrt(A_jj / N_w); a column with d_j < 1e-9 has d_j := 1 and its row and column of A and its entry
  of b set to 0. M = diag(d)^-1 A diag(d)^-1 + 8000 I, beta = diag(d)^-1 M^-1 diag(d)^-1 b, M solved by Cholesky in
  float64 (ridge on standardized columns with lambda = 8,000 weighted rows).
- A CACHE of per-session sufficient statistics, if the code keeps one, is keyed by (program, version, session, the
  sha256 of that session's ordered training keys, the code sha): a session settled further since it was cached is a
  new key.

### 1.6 Prediction and picks

- xbar_D = the mean of x over D's kept candidates. For each kept candidate: e_i = (x_i - xbar_D) . beta (its predicted
  vol-scaled gross return beyond D's pool); c_i = the replay's round trip for it (score.py `cost_bp`, entry plus exit,
  at its adv20 and E_prev), as a return; z_i = e_i - c_i / sig20_i; ahat_i = sig20_i x z_i, its predicted after-cost
  abnormal return. The LEVEL is the fixed prior that the pool's gross abnormal mean is zero: it is never learned, so no
  pick can time a drift common to the pool.
- PICKS: the candidates eligible to be picked (section 1.3) with z_i > 0, ranked by ahat_i (higher first), then adv20
  (higher first, a missing adv20 as 0), then event id (ascending); the first 8 are the learner's intents of D
  (`intents.rank_key` = ahat_i, the order `book.picks` and PREREG-EVL-6's top-14 guard read). No other pick exists; a
  decision may pick fewer than 8 or none.

### 1.7 Warm-up, failure, and the decisions before the release

- WARM-UP: no pick until the training rows at tau number at least 2,000 from at least 3 sessions (rows of sessions
  before REGISTERED_AT_7 count).
- FAIL CLOSED: a decision that cannot read its pool, its outcomes or its features, or whose fit is not finite or whose
  Cholesky fails, picks nothing and its receipt says why.
- ISOLATION: the learner's part of a decision runs after every earlier row of that decision is decided (PREREG-EVL-1 to
  -6, as PREREG-EVL-5 section 1.3 isolates its own part), under its own time bound (90 seconds at the open, 120 at the
  close). Its failure or expiry never cuts or fails an earlier row: the decision finishes with the earlier rows'
  results and names no learner, and that auction is decided for the learner BY ITSELF later, exactly as of tau (every
  cut-off read from stored times), in shadow only and never traded; that later decision is training state and a
  reported shadow, never part of the judged record (section 3.1).
- THE DECISIONS BEFORE THE RELEASE (E4; check 1's text): every decision from REGISTERED_AT_7 up to the first one the
  House release carrying this file's code makes live is decided by the learners in a CATCH-UP, oldest first, exactly as
  of its tau, with receipts `decide-open-lrn:<day>` and `decide-close-lrn:<day>`, and written. Its candidates, fits and
  picks are the learner's TRAINING STATE and a reported shadow. They are never part of the judged RECORD: never a
  block, never a control session, never traded. The learner code's commit sha is pinned in the release before the
  catch-up runs, and every `learner_fits` row records it. The catch-up runs once, and no builder of it reads any
  outcome of a session after REGISTERED_AT_7. The reconstruction of section 1.5 runs once, before it, by the same code.
- REAL MONEY AND THE RECORD start at the first decision the release makes live; no event decided before then is ever
  traded or judged.
- A written decision is never decided again.

### 1.8 What is written

Additive tables (SCHEMA_VERSION stays 1): `learner_fits` (program, version, day, tau, n_rows, n_sessions, beta, d,
xbar, the sha256 of the ordered training keys, the code sha, the receipt kind) and `learner_cands` (program, version,
day, cik, event, families, features, e, z, ahat, eligible, picked, rank). The written picks are the record (section
3.1 names which decisions count). A NIGHTLY RECOMPUTE re-decides the last decisions as of their tau and compares beta
and the picks only on decisions whose stored inputs are unchanged since the decision (the pool programs' intents and
their statuses, the universe rows, the marks, the verdicts and the outcomes it reads); it alarms on any other mismatch
with its cause, and it never rewrites a decision.

### 1.9 Real money

- BANDS. PREREG-EVL-3 section 2's learning band from birth (a target of 2% of E, whole shares at the limit, one share
  when that rounds to none and one share is at most 5% of E and fits every wall, at most 8 open). Probe and Sized are
  PREREG-EVL-6's: by its section 6, clause (4), A99's clauses hold for this file's versions, which state nothing
  otherwise: at Probe AT MOST 14 OPEN (clause 1), and a Probe or Sized buy takes the fewest whole shares whose value at
  the limit reaches 0.8 of its band's target, never above 5% of equity at Probe nor the name's 10% wall at Sized, that
  ask judged again by every cap (clause 2: the name wall, the 100% book, cash, the loss budget at the lot's weight and
  A85's reservation; a pick no such count reaches is skipped before it takes a slot, the shadow keeps it). A learner has
  at most 8 intents a decision, so 8 bounds it in every band.
- The book's picks of a learner are its intents of that decision in rank order, less the book's own skips: a name given
  to an earlier program at the auction, the sale gate (no buy of a name an event lot sells in the same cross), no whole
  share, cash, A85's reservation, the walls, the day's order line, the guards below, and section 1.3 (iii) read on real
  lots.
- ROOM: at learning, after every row of PREREG-EVL-1 to -6 and before R3's births (A101); inside the Probe and Sized
  tiers each learner takes part in A85's round-robin as the LAST program of each pass (after the band's PREREG-EVL-1 to
  -6 rows, before the band's births); EVL-LRN-O1 at the open, EVL-LRN-ON at the close. The event kind's day order line
  (150 orders, A74 (7), A78) refuses this file's entries after every earlier PREREG row's; an exit is never stopped by
  it. At most 16 entries and 16 exits a day.
- THE WINDOW: a learner pick not sent before its auction's order cut-off (the closing cross's 15:49 ET, A80) is a
  planned pick with binding 'window' (section 2.3's ledger).
- A learner version that cannot start a run (section 1.10) or is RETIRED buys nothing more; its decisions continue as
  a shadow record (PREREG-EVL-6 section 1.4), reported beside, and its open lots exit by their rules.
- EVL-LRN-O1'S ERN GUARD (E8), IN REAL MONEY ONLY: EVL-LRN-O1 does not buy an issuer that has an 8-K with item 2.02
  knowable in D's close window (programs.py `close_window`) and stored before tau (an ERN(D) issuer, which earlier rows
  buy at D's close and which this learner's sale there would take). The shadow keeps the pick.
- EVL-LRN-ON'S 8-K GUARD (E10), IN REAL MONEY ONLY: the guard reads EVERY 8-K of the issuer (form exactly '8-K')
  knowable at or after 09:00 ET of D and stored before tau, whatever the learner's primary event (never the primary
  event's accession). The issuer is not bought when any of them has a stored PROMPT-DOC verdict `ok` with score >= 2, or
  `ok` with score >= 1 and guidance "raised", or no answer by tau (PREREG-EVL-4 and -5 section 1.3, with A75 (1)'s
  readings): such a filing is an earlier row's event at the next open, which the learner's sale there would take. An
  issuer with no such 8-K is not barred by this guard. The shadow keeps every pick.
- STATED EFFECTS, not prevented, each counted in the report (book `sale_to_later`): an EVL-LRN-O1 lot sold at D's close
  takes the name from an earlier close-entry row that wants it for reasons knowable only after tau (day news, for
  instance); EVL-LRN-ON's sale at D+1's open does the same to an earlier open row with fresh pre-market news (the rarer
  case). Both learners' lots hold cash, invested room and loss-budget room at the auction where they are sold, which
  earlier learning rows need there (A85 reserves only for Probe and Sized). The day order line refuses this file's
  entries first.
- Every wall, the open-risk weight max(0.10, 1.65 x sigma x sqrt(h)), the loss budget, the kill switch and the stops
  are unchanged and judge every buy.

### 1.10 Runs, not re-entry (E2; check 1's text)

- RUNS, NOT RE-ENTRY. A learner version's runs, Probe stays, demotion and re-promotion are PREREG-EVL-6's as frozen
  (its sections 2-3): exhaustion at a run's 60th block ends the run, never the version. Each run after a version's
  first is charged c7 (section 4) when it starts. It does not start when the lane's count cannot hold it; the version
  then continues as a shadow record, never seats again, and its open lots exit by their rules. A learner id has at most
  THREE runs over its life (a run after a demotion counts among them; when the third ends without a pass, or a fourth
  would be due, the version continues as a shadow record only, as above). A version retired by the lower tail is not
  re-registered. So this file draws at most 6 x c7.
- This file registers no version 2 or 3 of either id. A later file may register a new version of a learner, with its
  own registration time and charge.

### 1.11 The implementation choices, pinned here (E4)

Every choice below is fixed by this text, before any code exists, so no choice is made after an outcome is stored and
none can differ between the live decision and the catch-up. Where a choice is not listed, sections 1.1-1.10 state it.
1. ORDER. Pool programs in section 1.2's order; within a decision, candidates in (pool order of the primary family,
   CIK) order; training rows in (entry day, CIK) order; every sum a `math.fsum` in that order; every value float64.
2. AS-OF READING. Every decision of a learner (live, catch-up, a failed part's later decision, the reconstruction, the
   recompute) reads only the store, with "now" set to its tau for every stored-time cut-off of section 1.1; it makes no
   network read except the live close decision's '1530' marks (section 1.1).
3. CANDIDATES. `book.picks` of each pool program at `decided_at=tau`, merged by the stored CIK string; ties of the best
   verdict by (score desc, knowable asc, event id asc); single-symbol articles = `news` rows whose symbol list has one
   entry; windows are the primary pool program's own (programs.py).
4. PRICES. The closes of items 10-12 are the `bars` rows with `adj` 'raw' of sessions before D for the symbol of D's
   universe row, the latest 20 by day; sig20 (items 10-12 and section 2.1) is their 19 log changes' SAMPLE standard
   deviation (divisor 18), then floored and capped as stated where it is read.
5. THE POOL OUTCOME. The first pool program in pool order holding an intent of the issuer entering at s with the
   learner's entry and exit auctions whose outcomes row is 'settled', `tradable` 1, `settled_at` before tau and whose
   raw entry print is at most 1.25 x the previous SIP close; its label is section 1.5's.
6. THE FIT. Section 1.5's d_j, M and beta; `numpy.linalg.cholesky` on M then two triangular solves; a non-finite beta
   or a Cholesky error fails the decision closed.
7. THE PICK. Section 1.6's z_i > 0 and its three-key order; at most 8; `intents.rank_key` = ahat_i.
8. TIME BOUNDS. 90 seconds at the open, 120 at the close, measured from the start of the learner's part; past it the
   part stops and section 1.7's isolation applies.
9. RECEIPTS. A live decision's learner part is recorded under the House's `decide-open:<D>` / `decide-close:<D>`
   receipt; the catch-up and a failed part's later decision under `decide-open-lrn:<D>` / `decide-close-lrn:<D>`.
10. AMBIGUITY. If an implementation finds a rule here ambiguous, it takes the reading LESS LIKELY TO PASS (screen rules)
    or that TRADES LESS (trading rules), recorded as an amendment BEFORE the release that carries the code and before
    the catch-up runs; a later resolution is a new version. The catch-up is never judged, so no reading made after an
    outcome is stored can reach a judged block.

## 2. COST-7: the cost basis of this file's versions

Every constant below is fixed at REGISTERED_AT_7. It applies to the versions of PREREG-EVL-7's two ids only (an
explicit set in screen.py, never "prereg >= 7") and to a later file's versions only when that file says so. No frozen
judge, no frozen program's cost, no column of `outcomes` and no line of score.py's frozen costs changes.

### 2.1 The per-event cost

For an event e with entry session D, entry auction and exit auction, its a7 and r7 are:

- r7 = exit_px x (1 - (M_out + FEE_out + IMP) / 1e4) / (entry_px x (1 + (M_in + FEE_in + IMP) / 1e4)) - 1 - G / 1e4,
  with the prices adjusted as in score.py; a7 = r7 - b, with b as in PREREG-EVL-1 section 5.
- IMP (bp, each side) = 1e4 x 1.0 x sigma x sqrt(0.10 x E_prev / ADV20): the square-root law with coefficient 1.0 at
  Sized size (10% of E_prev); SIGMA (E9) = the event's sig20 of section 1.4 item 10 (the standard deviation of the 19
  daily log changes of its 20 latest stored raw SIP closes of sessions before D), FLOORED AT 0.02 AND CAPPED AT 0.25,
  and 0.04 when fewer than 20 closes are stored (the universe row's `sigma60` is never read); ADV20 the universe row's
  adv20; an event with no E_prev or no ADV20 is not TRADABLE.
- FEE (bp, each side), the larger of (i) and (ii):
  (i) THE PENNY CEILING at the event's Probe size: n_ref = max(1, floor(PS x E_prev / (1.25 x prev_close))), PS = 0.035
  (FIXED HERE, never read from the money table), N_in = n_ref x the raw entry print, N_out = n_ref x the raw exit print
  (N_in when the exit print is 0); FEE_in = 1e4 x $0.01 / N_in (CAT); FEE_out = 1e4 x ($0.01 + ceilcent($27.80e-6 x
  N_out) + ceilcent(min($0.000166 x n_ref, $8.30))) / N_out (CAT, the SEC fee at the rate the equity book uses, FINRA
  TAF);
  (ii) THE MEASURED RATE: 1.25 x Fbar_side, Fbar_side = the running maximum over nights of 1e4 x (sum of posted fees)
  / (sum of qty x price) over the lane's real event fills of that side of lots BOUGHT AT PROBE SIZE OR ABOVE in the
  trailing 20 sessions whose fee is posted; 0 until 50 such fills of a side exist; never lowered.
- M_in, M_out and G: the lane-wide measured terms of section 2.2.
- AT EACH LOOK the whole record (the version's events and its control's) is re-costed with THE LATEST `cost_basis` ROW
  WRITTEN BEFORE THE LOOK IS COMPUTED. M, G and Fbar only rise and the penny ceiling of an event is fixed at its own
  entry, so no later look is easier because of a later row. A written look is never recomputed.

### 2.2 The measured terms, appended nightly to `cost_basis` after the score and before the screen

- (a) SLIPPAGE. The gap of a real event fill as done.py measures it: entry (fill / raw shadow print - 1) x 1e4, exit
  (1 - fill / raw shadow print) x 1e4 (a fallback-ladder exit against the shadow's ladder print). Over the trailing 250
  real event fills of a side (every program, every band) by fill time, once there are at least 100 over at least 5
  sessions: UCB = mean + 1.645 x SE, SE the standard deviation of the session means over sqrt(sessions). M_side =
  max(2.5 bp, the previous M_side, UCB). Before 100 fills: 2.5 bp.
- (b) SELECTION. Population: every BUY ATTEMPT (the first send of an event buy; a re-send under A80 is the same
  attempt) of any seating program since the lane's first real buy (Oct 20, 2026), recorded in the attempt ledger
  (section 2.3), whose shadow intent of the same program, version and event settled TRADABLE (shadow skips are left
  out). An attempt is FILLED when real_fills holds its buy. a_g = exit_px / entry_px - bench_exit / bench_entry (the
  shadow outcome's prices). Per entry session s: n_s attempts, k_s fills, mA_s and mF_s the means of a_g over the
  attempts and over the fills, v_s the population variance of a_g over the attempts. G_w = (1 / n_F) x sum_s k_s (mA_s
  - mF_s); SE = sqrt(sum over sessions with 0 < k_s < n_s of k_s (n_s - k_s) / (n_s - 1) x v_s) / n_F (the exact
  within-session permutation sd; the cost lens's `check_gvar.py` matched it to a brute-force shuffle within 0.3 bp).
  CHECKPOINTS at n_A = 100, 200, 400, 800, 1,600, 3,200, 6,400 settled attempts and every doubling after, each computed
  once every attempt through the n_A-th's entry session has settled, and only when the unfilled attempts number at
  least 10: G = max(G, max(0, G_w - 0.84 x SE)). G starts at 0 and is never lowered.
- (c) A session whose attempt record is incomplete (any event buy the House sent that day not in the ledger) is left
  out of (b), and its fills out of (a); the terms in force are kept and an alarm fires.
- (d) NO ROW FOR THE NIGHT, or one that cannot be read: every look of this file's versions WAITS (A66: late data delays
  a look, never its as-of close; the run's end, section 1.10, waits with it).
- The row: at, m_in, m_out, g_bp, ucb_in, ucb_out, n_fill_in, n_fill_out, fbar_in, fbar_out, n_att, n_unf, g_w, g_se,
  why. It is outcome-derived (b reads shadow outcomes): R3's facts authorizer refuses it.
- THE BACKFILL: `costs7` rows are backfilled once, from stored fields only, for every outcome settled since
  REGISTERED_AT_7 before the score's post-settle hook shipped.

### 2.3 The attempt ledger (the measurement COST-7 needs)

The House writes one `real_attempts` row per real event order it sends (buy LOO/LOC, sell MOO/MOC, the ladder's day
sales, A80's re-send), idempotent per (program, version, event, side, client id), as it writes `real_fills`: program,
version, event, side, tif, auction, day, decided_at, sent_at, client_id, venue_id, resend, qty, limit_px, status
(filled, partial, venue_cancel, expired, rejected, gateway_refused), filled_qty, fill_px, cancel_ms, why; and one row
for each pick the book planned and did not send, with its binding (cash, budget, invested, name_wall, line, room,
one_share, sale_gate, ern_guard, k8_guard, window). Sessions before the ledger existed enter section 2.2 (b) only where
the House's own order records give every attempt's terminal state; otherwise they are left out.

## 3. The judge

### 3.1 The screen (E1; check 2's text)

- THE SCREEN: PREREG-EVL-6 sections 1-3 AS FROZEN (`docs/prereg/PREREG-EVL-6.md` on the tag `prereg-evl-6`, commit
  4ae9017aaac964503a0dc8ad71965d38a08cc18d, sha256 0f67f94ecac93f6b5542654e33ce5180fdbac254238badd571a37bcb0950f057),
  word for word, with a7 and r7 (section 2) in place of a and r wherever they read an event's return. A learner is a
  READ version whose control is its POOL record (section 6), and its own ranking for every top-CAP guard is rank_key =
  ahat. Nothing of PREREG-EVL-6 is restated here; where the two differ, PREREG-EVL-6 wins. (For the reader: its first
  look is at a run's 22nd settled block, its looks at 22, 25, 30, 35, 40, 50 and 60 blocks with alpha 0.020, 0.006 and
  0.001, its block values min(n_s, 14) x (B_s - 10 bp), its runs end at the 60th block, its seed strings carry the
  version's id and version.)
- ITS RECORD is its forward picks only: its settled TRADABLE intents OF DECISIONS MADE LIVE BY THE HOUSE (receipts
  `decide-open:<D>` / `decide-close:<D>` of the release carrying this file's code or a later one; never the catch-up's
  nor a failed part's later decision, section 1.7), knowable after its registration.
- The code never edits the judge that judges it.

### 3.2 What the judge never reads

The learner's outcome-derived state (learner_fits, learner_cands, realized IC, the cost basis) is reported beside the
looks (the harness list), never an input to a look other than through a7, r7 and the record.

### 3.3 If PREREG-EVL-6 was not frozen first (E3; check 2's text)

If REGISTERED_AT_6 is not earlier than REGISTERED_AT_7, or PREREG-EVL-6 was never frozen, this file registers nothing:
its programs never decide, trade or draw any charge. There is no fallback screen: PREREG-EVL-3's screen, the draft's
fallback, breaks the goal's 15% on the learner lens's own figures (check 1).

## 4. Expected false passes and the lane's budget

- PER RUN (E1; check 1's text): the learner's worst false-pass rate W7 is one run's rate within 120 sessions. It is
  measured on the learner lens's generator and learner (section 5.2), with the screen exactly as PREREG-EVL-6 froze it
  (its first look at the 22nd block, its alpha pieces, values y_s = min(n_s, 14) x (B_s - 10 bp), the top-14 guard, the
  control and issuer guards, RETIRE and the 60-block run), over PREREG-EVL-6's frozen plausible grid as a learner meets
  it (section 5.3): rho_day <= 0.15; phi_day 0.10, 0.15 and 0.20; symmetric days, crash days with a normal or a t(3)
  body, clustered in high-volatility regimes or not; symmetric or left-skewed events; a drift of 0, 10 or 20 bp (AR
  0.97); issuer effects of 0 or 1%; pool counts independent of the day or following its size; pools of 300 and 800;
  training lag 1 and 2; the no-information and the knife-edge nulls. MEASURED (section 5.3; `final/select_w7.py`,
  `select_w7.w7.out`): W7 = 0.0870 (SE 0.0045, 4,000 programs on fresh seeds that searched and chose nothing) at
  t(3)-body crash days clustered in high-volatility regimes, left-skewed events, a 20 bp drift, 1% issuer effects,
  rho_day 0.15, phi_day 0.20, pool 300, lag 1 (0.0860 at lag 2; pooled with the search seeds 0.0882 +- 0.0042). The
  other six cells re-run on fresh seeds read 0.060-0.084; every search cell reads at most 0.100 (a search-seed figure at
  rho_day 0.05, 0.0707 on fresh seeds), the median search cell 0.066, the base model 0.0175 (lag 1) and 0.0240 (lag 2)
  on fresh seeds (`w7.sens.jsonl`, 2,000 programs each). The learner's column count and E7's label move nothing that
  matters: at the worst cell D = 40 reads 0.0840 and D = 63 0.0855, and the draft's after-replay-cost label 0.0805
  (2,000 each, fresh seeds).
- THE CHARGE: each learner run is charged c7 = max(c, W7 rounded up to 0.01), c = 0.13, PREREG-EVL-6's frozen per-run
  charge (its section 5): c7 = max(0.13, 0.09) = 0.13. The learner's worst plausible per run is under a fixed program's
  under the same rule (PREREG-EVL-6: 0.129 on its selection seeds, 0.1305 fresh), so each learner run is charged exactly
  as every other seatable version or run. W7 is under the goal's 15%, so the learners are seatable (had it exceeded 0.15
  they would have been registered as shadow records only, check 1; check 2: not frozen).
- PER TEST, NOT PER VERSION: PREREG-EVL-6's reading (its D11) applies to this file's runs as to its own: each run is one
  pre-registered sequential test, at most W7 at the worst plausible cell and charged when it starts. THE OWNER MAY
  OVERRULE THIS READING. Beside it, as PREREG-EVL-6 prints its own: PER VERSION within 120 sessions (its two runs, the
  second cut short) 0.164 and 0.168 at the two worst fresh cells (lags 1 and 2; `select_w7.w7.out`) and 0.170 and 0.1645
  on the life run's seeds (section 5.4), against PREREG-EVL-6's 0.240 for a fixed program at its worst cell.
- FOR THE OWNER (check 2): a learner id's false-pass probability over its up to 3 runs is 24.5% at lag 1 and 24.0% at
  lag 2 at the worst plausible cell (measured: `w7.life.jsonl`, 200 sessions, 2,000 fresh programs each; 17.0% / 16.5%
  within 120 sessions), each run held under 15% (at most 0.0955 on any fresh seed set) and charged 0.13 when it starts
  (section 5.4).
- THE LANE'S BUDGET, on PREREG-EVL-6's frozen basis (`final/fp_w7.py`, `fp_w7.out`; lifetime budget 3.9 = 30 x 0.13).
  USED BEFORE THIS FILE = the SEATING sum of every seatable version and run registered or started before REGISTERED_AT_7
  (any file, births included), as R3's validator reads it at registration: 1.95 for PREREG-EVL-6's fifteen versions,
  plus 0.13 for each seatable birth registered before REGISTERED_AT_7 (none had registered when this was written: A109)
  and the charges of any other file frozen first (PREREG-EVL-8 is being fixed in parallel). THIS FILE ADDS 2 x c7 =
  0.26 (the two learners' run 1). USED AFTER = USED BEFORE + 2 x c7 (2.21 of 3.9 with no birth and no other file
  first). LEFT = 3.9 - USED BEFORE - 2 x c7 (1.69 then). At most 4 x c7 = 0.52 more for this file's later runs, each
  drawn when it starts and only when the budget holds it: this file draws at most 6 x c7 = 0.78. When the budget cannot
  hold every run, re-entry or birth due the same night, they are drawn in registration order, earlier files first
  (PREREG-EVL-6 section 3); PREREG-EVL-8 and every later file are validated against what is left after
  REGISTERED_AT_7. R3's validator and the House's start of a run count this file's versions and runs with every other.
- EVERY REPORT shows the lane's expected false passes three ways, as PREREG-EVL-6 asks: its count (c7 = 0.13 a learner
  run), the base model (0.03 a learner run: the base figure rounded up) and the stresses' worst (0.13 a learner run:
  the worst named stress rounded up), and beside them the per-version and per-id figures above.

## 5. The calibration record (synthetic only)

### 5.1 Files (copied flat with their sha256, `SHA256SUMS`, into `docs/prereg/evl-7/` at the freeze)

Paths are relative to `goal-2026-10-19/evl7/`; the copy for the freeze is `goal-2026-10-19/prereg/evl-7/`. This file's
own calibration keeps its names; the lenses', the judge's and the checks' files carry the prefixes `learner__`,
`judge__`, `check1__`, `check2__`, `exec__` and `reader__`, except the two the scripts import (`calib_learner.py`,
`cost7_today.py`) and the one the rule reads (`features_spec.py`), which keep their names. Every figure of sections 0,
4 and 5 comes from one of them.
- THIS FILE'S CALIBRATION (`final/`): `calib_w7.py` (the generator's additions, the frozen screen, the grids and the
  report; `validate` reproduces check 1's figures, `validate_w7.out`); `select_w7.py` (the protocol of section 5.3:
  `select_w7.select.out`, `w7.selected.json`, `select_w7.w7.out`); `sens_w7.py`; `daylaw_w7.py` and `daylaw_w7.out`;
  `repro_w7.py` and `repro_w7.out`; `table_w7.py` and `table_w7.md`; the runners in the order they ran, `run_w7.sh`
  (the search's first 20 cells, stopped when the machine became shared), `run_w7c.sh` (the rest of the search; its
  fresh stage failed at once on a missing cell spec and its power stage was stopped and discarded, as its last lines
  record) and `run_w7e.sh` (the fresh cells, the sensitivities, power, life, the stresses, the validation and the
  reports), with their logs; the outputs `w7.search.jsonl`, `w7.fresh.jsonl`,
  `w7.power.jsonl`, `w7.life.jsonl`, `w7.stress.jsonl`, `w7.sens.jsonl` with their `.log` and `w7.report.txt`;
  `cost7_w7.py` and `cost7_w7.out`; `fp_w7.py` and `fp_w7.out`; `ev_w7.py` and `ev_w7.out`.
- THE LEARNER LENS (`learner/`): `calib_learner.py` (the generator and the learner, imported unchanged), and as records
  its `report_learner.py`, `run_all.sh`, `run_rank.sh`, `run_final.sh` and their outputs.
- THE JUDGE (`calib/`): `calib_evl7.py`, `run_evl7.sh`, `run_evl7b.sh`, `calib_evl7.*.jsonl` and logs,
  `calib_evl7.report.txt`, `fp_accounting.py`, `ev_evl7.py` (+ `.out`), and `cost7_today.py` (+ `.out`), which
  `cost7_w7.py` imports (records of the superseded draft screen, section 5.8).
- THE CHECKS: check 1 (`check1/calib_check1.py`, `run_check1.sh`, `sigma_pool.py`, `warmup_counts.py`, `check1.*.jsonl`,
  their logs and `check1.report.txt`); check 2 (`check2/check2_phi.py`, `check2_cost.py`, `check2_phi.jsonl`,
  `check2_phi.log`, `check2_cost.out`).
- THE COST LENS (`exec/`): `simlib.py`, `cal_cost7.py`, `cal_cost7_ref.py`, `check_gvar.py`, `cal_capacity7.py` and
  their outputs.
- THE READER LENS: `reader/features_spec.py` (the frozen `KEYWORDS`, `words`, `STOP`, `jaccard` of section 1.4 item 13).

### 5.2 The generator and the learner (the learner lens's, with the frozen grid's structures; synthetic)

The learner lens's generator and learner (`evl7/learner/calib_learner.py`, imported unchanged): 3,000 issuers in 11
sectors, Zipf(0.8) repeats, sigma log-uniform 1-10% a session, three style factors, a volatility regime (AR 0.9, sd
0.3), t(3) tails and +-30% jumps at 0.5% an event; a session-correlated day shock (sd from rho_day, its persistence
phi_day); left-skewed events (two-piece t(3)); a stream-wide persistent drift (AR 0.97, sd 0, 10 or 20 bp); persistent
issuer effects (sd 1%). A pool of Poisson(nbar x Gamma(3, 1/3)) candidates a session (nbar 300 or 800) with the lens's
40 features (5 family dummies, 5 score features, 5 score x family, 13 binaries, 7 issuer, 5 event continuous) PLUS 17
pure-noise columns (the 16 headline flags and dup72 of section 1.4 item 13, drawn as `calib_evl7.py`'s D57 draws
them): D = 57 throughout (63 and 40 as sensitivities). The learner is sections 1.5-1.6's: session-demeaned weighted
ridge, lambda 8,000, half-life 40, z = e - c_rep / sig20, ranked by ahat, K = 8, warm-up 2,000 rows from 3 sessions
(3 pre-registration sessions), training lag 1 (EVL-LRN-O1) or 2 (EVL-LRN-ON, or EVL-LRN-O1 behind a late score chain).
`final/calib_w7.py` adds, behind switches that draw nothing when off (`repro_w7.py`: the final script redraws a search
job exactly):
- E7'S GROSS LABEL AND THE TWO COSTS: each candidate's gross abnormal return a_g; c_rep, the replay's round trip at E =
  $1,898 (14.2 bp at ADV >= $10M, else 24.2 bp: score.py `cost_bp`), the learner's hurdle; c7, COST-7 at its warm-up
  at E = $1,898 (2.5 bp a side, the penny-ceiling fees at PS 0.035 on the issuer's price, impact at Sized size with E9's
  sigma = sig20 floored at 0.02), what the screen charges (ADV = $10M x exp(ln adv), price = $20 x exp(ln px) from the
  lens's issuer columns). The label is a_g / sig20 (E7); the screen reads a7 = a_g - c7 and r7 = a7 + b.
- THE NULLS IN THE SCREEN'S UNITS: N1 (the features carry nothing: E[a7] = 0 for every candidate, so E[a_g] = c7 and the
  gross label carries the cost differential the fit may learn; whatever it learns, its picks' mean a7 is exactly 0) and
  N2, the knife edge (E[a7] = sigma x ic x min(u - u95, 0): the top 5% by the true index have mean exactly 0, every
  other event worse). The alternative A states the GROSS mean: E[a_g] = sigma x ic x u (the pool's gross mean about 0,
  the fixed level's prior), so the pool loses its cost.
- PREREG-EVL-6'S FROZEN PLAUSIBLE GRID's structures (its sections 4.2-4.3, D1, D14), each day of mean 0 and variance 1
  (`daylaw_w7.py`, `daylaw_w7.out`): crash days with a normal body (the lens's: 5% of sessions N(-3, 1)), with a t(3)
  body, clustered in high-volatility regimes (p_t = 0.05 exp(2 x_t) / E[exp(2 x)], at most 0.09, on the lens's own
  regime: a mean crash share of 4.66%, as PREREG-EVL-6's), or both; phi_day 0.10, 0.15 and 0.20; counts that follow the
  size of the day shock (the POOL's count x exp(0.3 min(|eps_t|, 4)) / its mean). A learner picks at most 8 a session,
  so the frozen rule's money weights min(n_s, 14) are n_s throughout and its top-14 guard reads every pick.
- THE SCREEN is PREREG-EVL-6 sections 1-3 as frozen, applied to the picks' record (section 3.1), with its Monte Carlo
  shortcuts (its section 4.2): exact p for S <= 16 (no look is below 22), else 19,999 fixed sign vectors; the issuer
  guard over 999; p or q computed only where z >= 1.0. The control is the pool's mean a7 of the same sessions. A run
  ends at its 60th block and the next starts with the next block (the budget assumed to hold it); RETIRE ends the
  version. VALIDATION (`calib_w7.py validate`, `validate_w7.out`): the same screen code with check 1's ev6d_w rule
  reproduces check 1's figures on the judge's own paths exactly (run 1 0.1185, every run by 120 sessions 0.2230, 2,000
  programs).
- LAG. EVL-LRN-O1's real lag is 1 and EVL-LRN-ON's 2. On the pure null lag 1 was lower under the draft's rule (check 1:
  10.9% against 14.4% at phi_day 0.20), and under a learnable drift it was higher (family drift 16.5% at lag 1), so W7
  is measured at both lags (section 5.3) and the learnable drifts at both (section 5.5).

### 5.3 False passes per run: the protocol and W7 (E1)

THE PROTOCOL (`final/select_w7.py`, fixed before any fresh figure existed): (1) SEARCH seeds (from 201,000,001): 146
cells of PREREG-EVL-6's plausible grid as a learner meets it: the corner's full factorial (the four crash-day shapes x
phi_day 0.10 / 0.15 / 0.20 x drift 0 / 10 / 20 bp x lag 1 / 2, at rho_day 0.15, left-skewed events, 1% issuer effects,
pool 300), and each other factor varied from the corner (symmetric days; symmetric events; no issuer effect; pool counts
that follow the day, at phi_day 0.20 and 0.15; pool 800; rho_day 0.05; the knife edge at ic 0.03 and 0.05; the base
model at phi_day 0.10 and 0.20), 1,000 programs a cell for grid cells 0-19 and 500 for the rest (the machine became
shared with another workflow during the search: `run_w7.sh`, `run_w7c.sh`); (2) the cells within 3 points of the
search maximum, at most 8, highest first (`select_w7.select.out`, `w7.selected.json`); (3) those cells on FRESH seeds
(from 202,000,001) that searched and chose nothing, 4,000 programs each (`w7.fresh.jsonl`); W7 = the maximum fresh
figure (`select_w7.w7.out`). Per-run rate = P(a pass at any look of the learner's first run), within 120 sessions (a
learner's first run ends at its 60th block, about its 62nd session).

THE SEARCH (`table_w7.py`, `table_w7.md`; per-run rate on the search seeds, the fresh figure in parentheses where the
cell was re-run):

| day shape | lag | phi 0.10: drift 0 / 10 / 20 bp | phi 0.15: drift 0 / 10 / 20 bp | phi 0.20: drift 0 / 10 / 20 bp |
|---|---|---|---|---|
| crash days, normal body | 1 | 0.057 / 0.056 / 0.056 | 0.061 / 0.069 / 0.057 | 0.063 / 0.082 / 0.078 |
| crash days, normal body | 2 | 0.056 / 0.061 / 0.060 | 0.052 / 0.060 / 0.072 | 0.062 / 0.071 / 0.076 |
| crash days, t(3) body | 1 | 0.054 / 0.044 / 0.082 | 0.050 / 0.062 / 0.058 | 0.078 / 0.082 / 0.068 |
| crash days, t(3) body | 2 | 0.065 / 0.054 / 0.054 | 0.056 / 0.062 / 0.096 (fresh 0.079) | 0.050 / 0.076 / 0.064 |
| clustered crash days | 1 | 0.078 / 0.046 / 0.058 | 0.080 / 0.056 / 0.086 | 0.080 / 0.062 / 0.080 |
| clustered crash days | 2 | 0.058 / 0.086 / 0.070 | 0.094 (fresh 0.060) / 0.066 / 0.062 | 0.088 / 0.082 / 0.070 |
| t(3)-body clustered crash days | 1 | 0.082 / 0.074 / 0.088 | 0.072 / 0.058 / 0.072 | 0.072 / 0.080 / 0.098 (fresh 0.087) |
| t(3)-body clustered crash days | 2 | 0.084 / 0.076 / 0.080 | 0.070 / 0.056 / 0.068 | 0.070 / 0.070 / 0.096 (fresh 0.086) |

| varied from the corner (phi_day 0.20, 20 bp drift unless stated) | normal-body crash | t(3)-body crash | clustered crash | t(3)-body clustered crash |
|---|---|---|---|---|
| symmetric events, lag 1 | 0.060 | 0.070 | 0.068 | 0.080 |
| symmetric events, lag 2 | 0.060 | 0.076 | 0.066 | 0.084 |
| no issuer effect, lag 1 | 0.076 | 0.084 | 0.096 (fresh 0.084) | 0.072 |
| no issuer effect, lag 2 | 0.084 | 0.076 | 0.096 (fresh 0.073) | 0.076 |
| counts follow the day, lag 1 | 0.068 | 0.092 | 0.076 | 0.078 |
| counts follow the day, lag 2 | 0.062 | 0.060 | 0.066 | 0.094 (fresh 0.083) |
| counts follow the day, phi_day 0.15, lag 1 | 0.064 | 0.066 | 0.064 | 0.080 |
| counts follow the day, phi_day 0.15, lag 2 | 0.078 | 0.088 | 0.076 | 0.078 |
| pool 800, lag 1 | 0.074 | 0.056 | 0.080 | 0.080 |
| pool 800, lag 2 | 0.072 | 0.082 | 0.072 | 0.068 |
| rho_day 0.05, lag 1 | 0.068 | 0.100 (fresh 0.071) | 0.052 | 0.058 |
| rho_day 0.05, lag 2 | 0.060 | 0.048 | 0.066 | 0.052 |
| knife edge, ic 0.03, lag 1 | 0.058 | 0.066 | 0.058 | 0.048 |
| knife edge, ic 0.03, lag 2 | 0.048 | 0.050 | 0.050 | 0.070 |
| knife edge, ic 0.05, lag 1 | 0.024 | 0.048 | 0.054 | 0.058 |
| knife edge, ic 0.05, lag 2 | 0.046 | 0.050 | 0.054 | 0.048 |

- lag 1: symmetric t(3) days at the corner, phi_day 0.10 / 0.15 / 0.20: 0.050 / 0.040 / 0.044; BASE (symmetric days and
  events, rho_day 0.05, phi_day 0.10, no drift, no issuer effect): 0.020; the base at phi_day 0.20: 0.032
- lag 2: symmetric t(3) days at the corner, phi_day 0.10 / 0.15 / 0.20: 0.040 / 0.062 / 0.044; BASE (symmetric days and
  events, rho_day 0.05, phi_day 0.10, no drift, no issuer effect): 0.030; the base at phi_day 0.20: 0.026
- 146 cells; search maximum 0.100 (N1-crasht3-skew-rho05-phi20-dr20-tau1-n300-lag1-D57); median 0.066; programs a cell:
  1,000 for grid cells 0-19, 500 for the rest

THE FRESH CELLS (`select_w7.w7.out`; 4,000 programs each; per run, SE about 0.004; per version within 120 sessions; the
share of ALL programs whose passing record's true conditional mean a7 is <= 0 and <= 10 bp):

| cell (rho_day 0.15, left-skewed events, pool 300 unless stated) | lag | fresh per run | search | per version, 120 sessions | true mean <= 0 / <= 10 bp |
|---|---|---|---|---|---|
| t(3)-body clustered crash days, phi_day 0.20, 20 bp drift, issuer effects 1% | 1 | **0.0870** (0.0045) | 0.098 | 0.164 | 0.021 / 0.036 |
| the same | 2 | 0.0860 (0.0044) | 0.096 | 0.168 | 0.019 / 0.036 |
| clustered crash days, phi_day 0.20, 20 bp drift, no issuer effect | 1 | 0.0835 | 0.096 | 0.145 | 0.024 / 0.043 |
| t(3)-body clustered crash days, phi_day 0.20, 20 bp, 1%, counts follow the day | 2 | 0.0830 | 0.094 | 0.153 | 0.019 / 0.033 |
| t(3)-body crash days, phi_day 0.15, 20 bp, 1% | 2 | 0.0793 | 0.096 | 0.143 | 0.019 / 0.035 |
| clustered crash days, phi_day 0.20, 20 bp, no issuer effect | 2 | 0.0727 | 0.096 | 0.144 | 0.022 / 0.039 |
| t(3)-body crash days, rho_day 0.05, phi_day 0.20, 20 bp, 1% | 1 | 0.0707 | 0.100 | 0.132 | 0.014 / 0.025 |
| clustered crash days, phi_day 0.15, no drift, 1% | 2 | 0.0602 | 0.094 | 0.127 | 0.020 / 0.045 |

- W7 = 0.0870 (SE 0.0045) at t(3)-body crash days clustered in high-volatility regimes, left-skewed events, a 20 bp
  drift, 1% issuer effects, rho_day 0.15, phi_day 0.20, pool 300, lag 1; 0.0860 at lag 2. Pooled with its search seeds
  0.0882 (SE 0.0042). The life run's own 2,000 fresh programs at the same cell (seeds from 204,000,001; its first run is
  the same test) read 0.0955 (SE 0.0066) at lag 1 and 0.0875 at lag 2 (`w7.life.jsonl`), so 0.090 pooled over 6,000
  fresh programs at lag 1. Every figure rounds up to at most 0.10; c7 = 0.13 (section 4).
- The search maxima (0.094-0.100 at 500 programs) fell by 1-3 points on fresh seeds: the selection's winner's curse.
- THE BASE MODEL (symmetric days and events, rho_day 0.05, phi_day 0.10, no drift, no issuer effect; fresh seeds,
  `w7.sens.jsonl`, 2,000 each): 0.0175 (SE 0.0029) at lag 1, 0.0240 (SE 0.0034) at lag 2.
- SENSITIVITIES at the worst cell (lag 1; fresh seeds from 206,000,001, 2,000 each, `w7.sens.jsonl`): D = 40 (the lens's
  own columns) 0.0840; D = 63 (EVL-LRN-ON's count) 0.0855; the draft's after-replay-cost label in place of E7's gross
  label 0.0805. Neither the 17 or 23 noise columns nor the label moves the rate beyond its noise.
- FOR COMPARISON: PREREG-EVL-6's fixed programs read up to 0.129 (selection seeds) and 0.1305 (fresh) at their worst
  cell under the same rule; check 1 measured this learner at 0.109-0.144 at comparable cells under the draft's
  superseded rule (section 5.8). This file does not decompose the difference (the learner's blocks of about 8
  higher-volatility picks, its control and issuer guards, the frozen rule's first look at the 22nd block).

### 5.4 Per version and per id (runs, section 1.10)

On the worst cell over 200 sessions (`w7.life.jsonl`, fresh seeds from 204,000,001, 2,000 programs each lag), with
PREREG-EVL-6's runs (each run ends at its 60th block; RETIRE ends the version):
- PER VERSION within 120 sessions (two runs): 0.170 (lag 1) and 0.1645 (lag 2).
- PER ID, AT MOST THREE RUNS (this file's cap): 0.245 (lag 1) and 0.2395 (lag 2) by the 200th session (0.095 / 0.086
  by the 60th, 0.170 / 0.165 by the 120th, 0.243 / 0.238 by the 180th); runs started 2.64-2.66 on average; 8.7-8.8% of
  programs are retired by their lower tail. Close to 1 - (1 - W7)^3 = 0.239.

### 5.5 Named stresses and learnable structure (not binding; check 1's list)

`w7.stress.jsonl` (seeds from 205,000,001, 1,000 programs a cell, D = 57; per run within 120 sessions; for each
learnable structure the share of ALL programs whose passing record's TRUE conditional mean a7 was <= 0 and <= 10 bp):

| stress | lag | per run | per version, 120 sessions | true mean <= 0 / <= 10 bp |
|---|---|---|---|---|
| rho_day 0.30 (crash days, skewed events, 20 bp drift, 1% issuer effects, phi_day 0.10) | 2 | 0.062 | 0.119 | |
| day momentum 0.25 at rho_day 0.30 (phi_day 0.25, the same) | 2 | 0.091 | 0.167 | |
| day momentum 0.40 at rho_day 0.30 (phi_day 0.40, the same) | 2 | **0.125** (0.0105) | 0.228 | |
| phi_day 0.25 at rho_day 0.15, t(3)-body clustered crash days, skewed events, 20 bp, 1% | 1 / 2 | 0.089 / 0.098 | 0.165 / 0.174 | |
| a 30 bp drift at the worst cell | 2 | 0.088 | 0.162 | |
| loading-correlated features (0.7) with factor momentum 0.25 (check 2's cell; phi_day 0.20) | 2 | 0.049 | 0.119 | |
| a LEARNABLE 20 bp family drift (AR 0.97; crash days, skewed events, rho_day 0.15, phi_day 0.10) | 1 / 2 | 0.087 / 0.069 | 0.168 / 0.127 | 0.008 / 0.020; 0.009 / 0.019 |
| a LEARNABLE 20 bp sector drift (through the four SIC dummies; phi_day 0.20) | 1 / 2 | 0.108 / 0.080 | 0.180 / 0.165 | 0.020 / 0.032; 0.015 / 0.027 |

- Every named stress is under 0.13 a run; the worst, day momentum AR 0.40 at rho_day 0.30, is 0.125, as it is the worst
  for every program (PREREG-EVL-6 section 4.4: up to 0.161 for a fixed program under the same rule).
- LEARNABLE STRUCTURE (A112): a learner that follows a persistent family or sector drift can pass more often (the sector
  drift at lag 1, 0.108, is the highest of the learnable cells), but most such passes carry a real forward mean: of the
  learnable-drift passes, 9-19% had a record whose true conditional mean was <= 0 and 23-34% one <= 10 bp (the shares
  above over the pass rates). The bound is empirical, measured here, never asserted.

### 5.6 Power and the learning curve (E1)

P(promoted) under the frozen screen on a7 (this file's judge), the alternative A of section 5.2 (the pool's gross mean
about 0, the features carrying an information coefficient ic), the base model unless stated, D = 57, 1,000 programs a
cell on seeds from 203,000,001 (`w7.power.jsonl`, `w7.report.txt`); the same paths judged on the replay's a in brackets;
and the picks' TRUE expected a7 (the learning curve) in sessions 1-10, 51-60 and 111-120:

| ic | pool, lag | run 1 by session 10 / 20 / 40 / 60 | run 1 | per version by 120 | picks' true a7 edge, bp |
|---|---|---|---|---|---|
| 0.03 | 800, 2 | 0 / 0 / 0.020 / 0.021 | 0.021 [0.025] | 0.049 [0.062] | -0.5, 9.7, 13.6 |
| 0.05 | 800, 2 | 0 / 0 / 0.077 / 0.090 | 0.094 [0.111] | 0.230 [0.262] | 25.9, 47.7, 54.3 |
| 0.05 | 800, 1 | 0 / 0 / 0.092 / 0.097 | 0.098 [0.112] | 0.255 [0.286] | 27.4, 47.5, 54.4 |
| 0.05 | 300, 2 | 0 / 0 / 0.049 / 0.052 | 0.053 [0.058] | 0.154 [0.168] | 17.7, 29.8, 35.3 |
| 0.05, the worst corner (t(3)-body clustered crash days, skewed events, rho_day 0.15, phi_day 0.20, 20 bp drift, no issuer effect) | 800, 2 | 0 / 0 / 0.108 / 0.118 | 0.123 [0.132] | 0.278 [0.292] | 19.0, 35.1, 40.9 |
| 0.08 | 800, 2 | 0 / 0 / 0.358 / 0.393 | 0.431 [0.455] | 0.745 [0.771] | 76.4, 111.2, 118.1 |

- NOTHING IS PROMOTED BY THE 10TH OR THE 20TH SESSION, at any edge: the frozen rule's first look is the 22nd block.
- THE LEARNING CURVE: at ic 0.05 (pool 800) the picks' true after-COST-7 edge rises from +26-27 bp in the first ten
  sessions to +48 by sessions 51-60 and +54 by 111-120; at ic 0.08 from +76 to +118 bp; at ic 0.03 from -0.5 to +14 bp.
  The learner improves with every settled session, as designed; the screen's session-block evidence is what limits
  promotion (8 picks a session, an event sd of about 5-8%, a day shock: the block, not the event, is the unit,
  PREREG-EVL-6 section 4.5's physics).
- THE PLAIN READING. One run at a plausible information coefficient (0.03-0.05) rarely promotes: 2-12% by its end, 5-28%
  over a version's two runs within 120 sessions. Promotion comes at 0.08 and above (43% the first run, 75% within 120
  sessions). At 0.05 a promoted learner's picks carry +45-55 bp after COST-7 at pool 800 (+28-35 at pool 300), so a
  promotion, when it comes, is worth Probe room (section 5.9's dollars).
- COST-7 COSTS POWER, IT DOES NOT BUY IT: judged on the replay's a the same paths promote 0.4-2.4 points more by the end
  of run 1, because COST-7 with E9's sigma is 3.0-4.2 bp a round trip stricter than the replay on the learner's picks
  when the features carry information (their mean sigma 0.065-0.081; section 5.7). The draft's "COST-7 adds 1-5 points"
  assumed the NULL sigma60 and is withdrawn.

### 5.7 The cost basis

- E9'S SIGMA, AT TODAY'S EQUITY (`final/cost7_w7.py`, `cost7_w7.out`, arithmetic only, on `calib/cost7_today.py`'s
  formulas and grid): replay minus COST-7 for ADV >= $10M averages +1.0 / +0.2 / -0.7 / -1.5 / -2.4 bp a round trip at
  sigma 0.02 / 0.04 / 0.06 / 0.08 / 0.10, and for thinner names +8.6 / +5.3 / +2.0 / -1.4 / -4.7 bp; at $30k, thinner
  names -10.9 to -50.4 bp at sigma 0.04-0.10 (COST-7 the stricter). A flat 0.04, the NULL `sigma60` the draft read,
  would have under-charged an 8%-sigma name 9.0 bp a round trip at E = $1,898 and ADV $1.5M, and 35.8 bp at $30k. ON THE
  LEARNER'S OWN PICKS in the generator (mean sigma 0.046-0.056, against the pool's issuers' unweighted means): COST-7
  19.1-20.9 bp against the replay's 17.8-19.0 bp, so COST-7 is 1.3-1.9 bp a round trip stricter than the replay on what
  the learner buys (0.9 bp looser on the pool's average issuer); under the alternative of section 5.6 the picks' mean
  sigma is 0.065-0.081 and COST-7 is 23.0-26.5 bp against the replay's 20.0-22.3 bp, 3.0-4.2 bp stricter (`ev_w7.out`).
- THE COST LENS'S RUNS (its records, on its own screen proxy: PREREG-EVL-6's search candidate SB-SEQ at c = 0.09,
  without the issuer and control guards, so each rate is an upper bound for that proxy): against the real-money null
  (the true after-real-cost mean exactly 0), worst cell (rho_day 0.15, crash days, 20 bp drift), 30 events a session,
  margin 10 bp (`exec/cal_cost7_ref.out.jsonl`): a judge charging COST-7 (5 bp above the true cost) passes 6.85%; one
  charging exactly the true cost 8.7%; the replay's liquid overcharge (12 bp) 4.95%; its thin one (20 bp) 3.85%. THE
  RATCHETS (`exec/cal_cost7.py`, `cal_cost7.out.jsonl`, worst cell, 30 events a session, no margin; false passes by 120
  sessions with / without the ratchet): hidden adverse selection of non-fills 10 bp: 11.85% / 15.3%; 20 bp: 13.95% /
  21.75%; 40 bp: 16.65% / 38.6%; a slippage episode of 9 bp a round trip from session 20: 10.4% / 13.4%; the impact
  model short by 5 bp: 11.35% / 13.1%. z = 0.84 for the selection charge. The lane's cancels came 5-6 ms after
  acceptance with nothing filled (A80), which carries no price information, so a selection as large as 40 bp is not in
  the plausible set. Under no adverse selection 51% of paths get a spurious charge, 4.5 bp on average by session 119:
  the price of the protection, paid in power only. THE SELECTION STANDARD ERROR (`exec/check_gvar.py`): the exact
  within-session permutation sd matched a 20,000-shuffle brute force within 0.3 bp in five trials. FEES AND IMPACT AT
  SIZE (`exec/cal_capacity7.out.txt`, a synthetic universe): at E = $1,898 the penny ceiling is 8.6 bp a round trip at
  Probe ($66) and 2.9 bp at Sized ($190); at $30k 0.7 bp and 0.5 bp; the impact figures there used the lens's own sigma.
- These runs were made on screen proxies, not PREREG-EVL-6's frozen screen; the learners' own figures under the frozen
  screen, with COST-7 inside the generator, are sections 5.3-5.6's.

### 5.8 History: the figures the checks found stale

Kept only as history (check 1): the draft's figures were measured under PREREG-EVL-6's superseded DRAFT screen
(looks from the 6th block, alpha 0.016 / 0.004, unweighted values, exhaustion retiring the version), on a grid with
phi_day 0.10 only and lag 2 only, with the draft's after-replay-cost label: 11.8% (SE 0.7) per version at the draft's
worst corner (`calib/calib_evl7.py`, `calib_evl7.null.jsonl`), 4.95% at its base, 23.2% for a chain of three versions
within 120 sessions. Under that superseded rule check 1 measured 12.7% at phi_day 0.15, 14.4% at 0.20, 10.9% at lag 1
and 16.5% with a learnable family drift at lag 1 (`check1/check1.phi.jsonl`, `check1.drifts.jsonl`), and check 2 14.2%
at phi_day 0.20 with the issuer effect (`check2/check2_phi.jsonl`). PREREG-EVL-3's screen, the draft's fallback, read
15.6% at the draft's worst corner (`learner/calib_learner.final_null.log`). None of these is this file's rule.

### 5.9 What the learners can expect (synthetic; stated assumptions)

`final/ev_w7.py`, `ev_w7.out`: the judge's method and constants (`calib/ev_evl7.py`) on this file's power cells: E =
$1,898; a learning lot 2% of E, a Probe lot 0.9 x 3.5% of E; 7.9 picks a session; real money buys a share F_L =
0.25-0.50 of a learner's picks at learning (ROOM last, cash binding) and 0.75 at Probe; each real pick earns the picks'
true replay a of its session decile plus 8 bp (the replay's overcharge less the real fees at learning size); a promoted
version stays at Probe; abnormal return only. Per learner over 120 sessions (its runs within 120 sessions):

| scenario | P(promoted by 120) | $ per learner, F_L 0.25 / 0.50 | expected Probe events | first session the expected cumulative Probe events reach 50 |
|---|---|---|---|---|
| ic 0 (the features carry nothing; the pool's gross mean 0) | false promotion only (W7 a run) | -$6 to -$29 (check 2's line, below) | about none | none |
| ic 0.03, pool 800 | 0.049 | +$21 / +$39 | 17 | none |
| ic 0.05, pool 300 | 0.154 | +$45 / +$79 | 45 | none |
| ic 0.05, pool 800 | 0.230 (lag 2), 0.254 (lag 1) | +$75 / +$120 (lag 2) | 76-86 | 96-101 |
| ic 0.05, the worst corner, pool 800 | 0.278 | +$63 / +$98 | 97 | 92 |
| ic 0.08, pool 800 | 0.745 | +$281 / +$342 | 291 | 49 |

- THE NULL LINE (E11; check 2's text, by its method, `check2/check2_cost.py` and `ev_w7.out`): ic 0: about -$6 to -$29
  per learner over 120 sessions at learning (a pick earns minus the replay cost plus the 8 bp gap: -6.2 bp liquid,
  -16.2 bp thin), plus a false promotion's Probe lots at the same rate, all inside the loss budget.
- Two learners roughly double each line (disjoint auctions and pools). Metered compute: $0 a day (no model call).
- THE HONEST BOTTOM LINE: the learners make the swarm improve with every settled session at no compute cost and align
  what is judged with what is traded; they reach Probe inside a version's two runs only if the lane's stored fields
  carry an information coefficient of about 0.08 or more for these pools (75%), and at 0.05 a quarter of the time. At
  0.03-0.05 they mostly earn small learning-size profit and spend runs of the budget.

## 6. The controls (free records)

- EVL-LRN-O1-POOL and EVL-LRN-ON-POOL: for each decision of their learner MADE LIVE BY THE HOUSE (section 3.1), every
  candidate kept by section 1.3 whose primary event is knowable after the learner version's registration time, with the
  POOL OUTCOME of its (D, issuer) valued on a7. They have no intents and no settlement of their own; they never seat,
  never trade and cost no expected false pass. Compared over the learner's own block sessions (PREREG-EVL-6 section
  1.4's control rule: PREREG-EVL-1 section 7's, block values unweighted: the control's TRADABLE values of each of those
  sessions averaged, then the sessions averaged).

## 7. What is unchanged

Everything this file does not state is PREREG-EVL-1's to -6's and R3's, word for word: the universe, the events, the
knowable times, backfill and the shadow rule; the verdicts, their model, prompts (PROMPT-DOC and PROMPT-NEWS and their
SHA-256), parsing and the rule that the first stored answer is final; the execution model, auction prices, the fallback
ladder, score.py's costs and per-event returns and TRADABLE for every earlier program; every earlier program's rule,
record, control and judge; the band sizes; ROOM's order for every earlier row, the sale gate, A85's cash reservation
and every real-money guard; the money walls (<= 10% of equity a name, <= 100% invested, no margin, no shorts), the loss
budget ($400 net in any 20 sessions, $800 net total, realized plus open risk at the 95% holding-period loss), the
open-risk rule, the kill switch and the stops; Done, pivot and reporting (Done counts these programs' events at Probe
size or above like any program's, only after their own promotion, at realized after-fee P&L; Done is read by
`league/events/done.py`, unchanged). It adds no prompt, no verdict, no model call and no recorder.

## 8. Why these, and their rates (the judge's prior, stated before any outcome)

- WHAT THE LEARNERS ADD. The lane's fifteen seatable rules each read one or two fields of a verdict and fix their
  selection forever. A learner ranks the whole pool of an auction on every field the lane already stores, and its
  estimate improves as the labelled stream grows (about 1,500 settled pool outcomes a session across both pools,
  EXECUTION-FACTS). By the fundamental law of active management (Grinold 1989, Journal of Portfolio Management 15(3);
  Grinold and Kahn 2000, Active Portfolio Management, 2nd ed.), the excess of a top-q selection is about IC x sigma x
  E[z | top q]; picking 8 of 300-850 (the top 1-3%) turns a weak, many-feature signal into a large edge a slot, which
  no fixed filter of a 7-level score can do (its ties are broken by ADV). Estimation error falls like sqrt(d / N) as N
  grows, so the realized information coefficient and the picks' edge rise session by session (section 5.6).
- WHY THIS ALGORITHM. Ridge regression for many weak return predictors (Hoerl and Kennard 1970, Technometrics 12(1);
  Gu, Kelly and Xiu 2020, Review of Financial Studies 33(5); Kelly, Malamud and Zhou 2024, Journal of Finance 79(1));
  online ridge has logarithmic regret against the best fixed linear predictor (Vovk 2001, International Statistical
  Review 69(2); Azoury and Warmuth 2001, Machine Learning 43(3); Cesa-Bianchi and Lugosi 2006, Prediction, Learning,
  and Games). Demeaning within the session is the cross-sectional idea of Fama and MacBeth (1973, Journal of Political
  Economy 81(3)): the day shock, the pool's drift and the benchmark cancel, so the learner learns only who beats whom on
  the same day. Exponential forgetting (half-life 40 sessions) tracks effects that decay or shift: earnings seasons
  end, published anomalies decay (McLean and Pontiff 2016, Journal of Finance 71(1)), markets adapt (Lo 2004, Journal
  of Portfolio Management 30(5)). No exploration (LinUCB, Li, Chu, Langford and Schapire 2010, WWW; Thompson sampling,
  Agrawal and Goyal 2013, ICML) is needed, because the controls give the outcome of every candidate, picked or not.
  The label is the GROSS abnormal return (E7) and the replay's cost is subtracted once, at the pick, as the fixed level
  states: a label after cost would teach the fit the cost differential of thin names through ln adv20 and charge it
  again in z.
- WHAT THE FEATURES CARRY. The lane's own verdicts (Lopez-Lira and Tang 2023, arXiv 2304.07619: language-model readings
  of news headlines predict next-day returns, more in small stocks; Tetlock 2007, Journal of Finance 62(3); Tetlock,
  Saar-Tsechansky and Macskassy 2008, Journal of Finance 63(3)); staleness and reprints (Tetlock 2011, Review of
  Financial Studies 24(5): stale news is followed by reversals), which `dup72`, `first20` and `n_att20` measure;
  analyst actions and price targets in headlines (Womack 1996, Journal of Finance 51(1); Brav and Lehavy 2003, Journal
  of Finance 58(5)); attention and the overnight-intraday split (Berkman, Koch, Tuttle and Zhang 2012, Journal of
  Financial and Quantitative Analysis 47(4); Lou, Polk and Skouras 2019, Journal of Financial Economics 134(1));
  short-term reversal (Lehmann 1990, Quarterly Journal of Economics 105(1); Jegadeesh 1990, Journal of Finance 45(3));
  size and volatility. "price target" alone appears in 1,117 of 4,346 headlines of Oct 19-21 (HOUSE-FACTS.json, as
  the reader lens counted it): a kind of item a 7-level score cannot tell from an upgrade, and a headline flag can.
- WHY A COST BASIS OF ITS OWN. Auction orders trade at the one auction price; at today's learning size the lane's 84
  real fills printed at exactly the replay's price, while the replay charges 14.2-24.2 bp a round trip and nothing
  for size. Impact follows a square-root law in participation (Almgren, Thum, Hauptmann and Li 2005, Risk 18(7); Toth,
  Lemperiere, Deremble, de Lataillade, Kockelkoren and Bouchaud 2011, Physical Review X 1; Frazzini, Israel and
  Moskowitz 2018, working paper, "Trading Costs"), and in proportion to the name's own volatility, which the learner's
  ranking by ahat concentrates (E9); limit orders that do not fill can be adversely selected (Handa and Schwartz 1996,
  Journal of Finance 51(5); Harris and Hasbrouck 1996, Journal of Financial and Quantitative Analysis 31(2); Linnainmaa
  2010, Journal of Finance 65(4)), and a quarter of the lane's auction buys were cancelled by the venue (A80). COST-7
  charges what is known (fees at Probe size), models what cannot be measured from our own prints (impact at Sized
  size), and measures what the replay assumes away (slippage and non-fill selection), each only tightening. A learner
  is judged on what real money keeps.
- RATES (counts only; SPEED-FACTS). Candidates before merging by issuer: EVL-LRN-O1 about 340 (Oct 20) and 620 (Oct 21);
  EVL-LRN-ON about 430 and 840. The warm-up (2,000 rows from 3 sessions, the lane's sessions from Oct 19 counted) is met
  in the training state before the release (check 1's `warmup_counts.py`: EVL-LRN-ON cannot pick before the Oct 26
  decision, EVL-LRN-O1 before Oct 23's), so a release live after those dates picks from its first live decision. THE
  FIRST LOOK is at the 22nd block of live picking decisions (PREREG-EVL-6's schedule; the minimums of 30 events and 30
  issuers hold long before at about 8 picks a session): NO LEARNER CAN BE PROMOTED BEFORE ITS 22ND LIVE PICKING SESSION
  after the release. Earnings season raises the pools to mid-November; news runs all year.
- AGAINST. (1) POWER: section 5.6 measures it plainly: one run at a plausible information coefficient (0.03-0.05) rarely
  promotes (2-12% by its end, 5-28% over a version's two runs within 120 sessions), promotion comes mostly at ic >= 0.08
  (43% the first run, 75% within 120 sessions), and nothing is promoted before the 22nd live block. (2) A learner
  exploits whatever persists, including transient issuer, family or sector effects (A112; section 5.5's learnable
  drifts); forgetting, the 30-issuer minimum, the issuer-block guard and Done's issuer bootstrap bound the damage, and
  section 5.5 reports what share of such passes had no real edge. (3) Language-model predictability decays as adoption
  spreads and is strongest on negative news, which a long-only lane can only avoid (Lopez-Lira and Tang 2023). (4) The
  learners' picks overlap the fixed READ programs' names and verdicts, so their false passes are correlated with those
  programs'; expected false passes add regardless. (5) Real money at learning takes what every earlier row leaves (ROOM
  last, cash binds): few real fills before promotion; the shadow record is complete and promotion reads only it. (6) The
  reconstructed pre-registration candidate sets and the catch-up's hold fewer '1530' marks and fewer answered verdicts
  than live ones (a distribution shift in the first training rows, which forgetting removes; none of them is judged).
  (7) A late evening score chain (A95) makes a decision train on older rows (a lag of 2 for EVL-LRN-O1: section 5
  measures both lags): honest, slower; an alarm watches it. (8) COST-7 on the learner's own picks is a little stricter
  than the replay at today's equity (section 0), so it buys no power; it is there to keep a promotion honest at Probe
  and Sized size and at the $30k plan.

## 9. Honesty

- BLIND DESIGN. Every designer (the four lenses), the judge, the two adversarial checks and the fix round worked under
  the rule that no price after any event, and no return, P&L, look, band of evidence, mark or bar of any event or
  program, is read, queried or computed, from the House, the gateway, events.sqlite, live.sqlite, `~/Work/ltcm-evl-run`,
  `~/Work/.ltcm-main/evl`, `~/Work/.ltcm-main/scratch/goal-check-1021` or any run record. None was. They read the
  frozen rules, the drafts, the code, outcome-free counts (SPEED-FACTS, HOUSE-FACTS), the execution facts and the
  literature, and they ran synthetic simulations only. Every hyperparameter (the pool, the 57 and 63 features, the
  half-life 40, lambda 8,000, K = 8, the ranking by ahat, the fixed level, the warm-up) was chosen on synthetic paths
  (`evl7/learner/calib_learner.*`, `evl7/calib/calib_evl7.*`) before the fix round, which changed none of them: it
  re-measured their false passes and power under the frozen screen (`evl7/final/`).
- THE ONE EXECUTION FACT. Section 2 was shaped by EXECUTION-FACTS: the lane's real fills printed at the replay's
  auction prices, and the venue cancelled about a quarter of the auction buys (A80). That is a fact about the venue's
  prices and fills against the shadow's, the same for every program; it says nothing about which program or event
  earns. COST-7 applies to this file's versions only, and its measured terms only tighten.
- THE CAPTAIN (the provenance paragraph above): the registering session had read, on Oct 21, the per-program shadow
  means of Oct 19-20 and the lane's aggregate real-money figures; it wrote the workflows' prompts and E1-E11, which
  adopt the blind checks' stated fixes, and it chose no rule parameter. For that reason every record of this file counts
  only events knowable after REGISTERED_AT_7, and only decisions the House makes live after the release.
- OUTCOMES AT RUN TIME. The learners read outcomes: every pool outcome settled and stored before each decision,
  including those of Oct 19-22, before this file's registration. That is the forward test this file registers, not a
  look: each pick is made before its own outcome exists, the training rows are fixed by stored times, and the record
  counts only picks of events knowable after registration, decided live. A pre-registration outcome can make a
  learner's first picks better or worse; it cannot put a settled outcome into its own record.
- THE DECISIONS BEFORE THE RELEASE ARE NEVER JUDGED (E4). The catch-up and the reconstruction are run by code written
  after those sessions' outcomes were stored. Their candidates, fits and picks are training state and a reported
  shadow only: never a block, never a control session, never traded. Their code's sha is pinned in the release before
  they run, they run once, no builder of them reads an outcome of a session after REGISTERED_AT_7, and every choice they
  make is pinned in section 1.11 before any code exists.
- THE COST BASIS READS OUTCOMES TOO, BY A FIXED FORMULA. Section 2.2's selection charge compares the shadow outcomes
  of filled and unfilled buy attempts of every seating program since Oct 20, before this file's registration included.
  It measures the venue (whether its cancels pick losers), not a program; its formula is fixed here, it can only
  tighten a look, and no one chooses anything from it.
- THE LEARNERS' OWN STATE IS OUTCOME-DERIVED. Their coefficients, candidates, realized IC and learning curves, and the
  cost basis (its selection charge reads shadow outcomes), are shown to the captain and the owner only; R3's facts
  authorizer refuses their tables (a test pins that R3's Facts never read intents, outcomes or any learner table of this
  file's ids), and no designer of a later file reads them.
- IMPLEMENTATION LEAKS, AND THE GUARDS. A feature input stored after tau, an outcome settled after tau, an eligibility
  result written after the House's own decision of the auction (E5), or a row rewritten after the decision would leak.
  Guards: the stored-time cut-offs of section 1.1, read from stored columns only; the '1530' mark read by its bar time
  before tau (E6); features written once at the decision; the reconstruction and the catch-up run once and never judged;
  the nightly recompute that alarms on any mismatch of a decision whose inputs are unchanged; the tests of section 10.
- A LEARNER CAN FOLLOW PERSISTENT STRUCTURE THAT IS NOT AN EDGE (A112). Its bound is EMPIRICAL, measured at the worst
  plausible cells and under named learnable-drift stresses (section 5), never asserted; section 5 reports with each
  learnable-drift figure the share of its passes whose record's true conditional mean is <= 0 and <= 10 bp.

## 10. What is not decided here

The code (league/events/learner.py; league/events/costs7.py; run.py's isolated learner part, its catch-up kinds and the
close decision's '1530' marks for EVL-LRN-ON's candidates; book.py's rows, ROOM key, the ERN guard of EVL-LRN-O1 and the
8-K guard of EVL-LRN-ON; screen.py's a7 path for this file's explicit set of versions, the POOL control over live
decisions and the registries; programs.py's rows and REGISTERED_AT_7; births.py's authorizer; the House's start of a
learner's run when the budget holds it; store.py's additive tables; the House's attempt ledger; the report and alarms),
the site and the docs, built after this file to these rules; the build's plan is a guide and this file wins. The tests
it must carry: as-of determinism (rows stored, settled, answered or decided after tau, and '1530' marks of a later bar
time, leave a decision unchanged; an eligibility result inserted after the House's decision receipt leaves it unchanged;
an EVL-LRN-O1 decision made after the fact excludes an issuer whose only live result was written by D's close decision);
the label reads no cost column; reconstruct-once and catch-up-once; failure isolation (a raising learner leaves every
earlier row's intents byte-identical); every earlier program's intents identical with and without the learners; ROOM
order; the ERN guard; the 8-K guard (a news primary without an 8-K is bought; an issuer with an `ok` score 2 8-K after
09:00 ET is not); the feature spec's sha; a run refused when the budget cannot hold it; R3's Facts never read intents,
outcomes or any learner table of this file's ids; the learner never edits screen.py. An ambiguity is resolved by section
1.11 item 10.


# PREREG-EVL-6: one money-weighted session-block screen for every seat, looked at in settled blocks

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6e6a85b9) under the owner's goal as he re-set it at 05:15Z
Mon Oct 19, 2026 (`goal-2026-10-19/GOAL-MESSAGE-V2.txt`): "No deadlines, no waiting periods: speed is settled events and
iterations, never calendar time ... Promotion to Probe and Sized, demotion and retirement are pre-registered sequential
tests counted in settled events, never days, at a false-positive rate <= 15% by issuer-block permutation."
Written 03:58Z-12:24:36Z Oct 22, 2026 (the judge's draft finished 03:58Z; from 04:55Z the two adversarial checks'
findings applied under the captain's decisions D1-D9 of A107 and the rule recalibrated on synthetic seeds; from 09:24Z
the two re-checks' findings applied under the captain's further decisions D10-D16, the plausible grid widened and the
rule re-chosen on new synthetic seeds; all by workflow wf_529214ff-cc4).

HOW IT WAS MADE. The captain's A91 (21:12Z Oct 21) opened this design before any design result existed. Three
independent designers wrote three tests (a control-relative within-session permutation beside a session-block absolute
test; an anytime-valid betting e-process; a universe-referenced stratified sign-flip), three calibrators measured each
by Monte Carlo on synthetic correlated returns, a judge re-measured all three and PREREG-EVL-3's own screen on ONE
generator that holds every risk any of them had found, searched 2,457 candidate rules on it and wrote a draft, and two
adversarial checks read the draft and re-ran its generator on fresh seeds (workflow wf_560ee5dd-ef8, script
`goal-2026-10-19/workflows/fast_screen.js`, sha256 1cfcb26b68dfec459775326e43bb6ee911e261169c8f71f6e7f692cb2b424903).
A fix workflow (wf_529214ff-cc4) applied every finding of both checks under the captain's decisions D1-D9, widened
the plausible grid, searched 5,380 candidate schedules, chose one by the rule D1 states, recalibrated demotion and
wrote a draft of this file (its fix round ran from the script `goal-2026-10-19/workflows/evl6_fix.js` at sha256
0dd86d3c38b9e28949dd521ee76fe2a342f6c3b1ccbf4c5362ef480fb0bdf7de, kept as `workflows/evl6_fix.v1.js`). Two blind
re-checks of that draft (re-check 1 rebuilt the figures on its own generator and seeds; re-check 2 read the text
against the code) found that crash days with fat-tailed ordinary days, crash days clustered in high-volatility
regimes and event counts that follow the day's move break 0.13 inside the plausible grid's stated bounds. Under the
captain's decisions D10-D16 the same workflow (its final round from the same script extended with D10-D16, sha256
56ed9514272d0d974392a93122ad84444b9fdcff963ce1b4442dfdb5780f996a) widened the plausible grid by those structures,
searched again on new search seeds, chose on new selection seeds, measured the chosen rule on fresh seeds that never
searched, shortlisted or chose (section 4.3), recalibrated demotion, and wrote this file. Each worked under the rule
that no price after any event, and no return, P&L, look, band or mark of the lane, is read, queried or computed; none
was.

PROVENANCE. Both workflows' prompts carried only outcome-free counts (`goal-2026-10-19/evl5/HOUSE-FACTS.json`,
`goal-2026-10-19/evl4/FACTS.json`), the frozen texts and the code, and pointed to the blind judge's and checks'
reports (`evl6/JUDGED.json`, `evl6/CHECK-FINDINGS.json`), the done-speed synthesis (`goal-2026-10-19/speed/
SYNTHESIS.json`) and the captain's amendments record (`scratch/eqlane-1010/CAPTAIN-AMENDMENTS.md`, for A99-A105). That
record also holds the captain's outcome-derived A96 line (three sessions of shadow showed no program clear of noise:
no figure, the same for every program), which no designer, fixer or checker was asked to use and no constant here
reads. The registering captain session (6e6a85b9) had read, on Oct 21, the per-program means of the shadow record of
the lane's programs over its first two entry sessions (Oct 19-20) and the lane's aggregate real-money figures. It
wrote both workflows' prompts and the decisions D1-D16, and it chose no rule parameter: D1-D16 adopt the blind checks'
and re-checks' proposals and set targets (a worst plausible false-positive rate <= 0.13 per run, a false-demotion rate
<= 0.15, A99's 14 Probe slots, itself designed blind; the widened grid, the reads' 0.15 and the 10% money stop are
the re-checks' and the fixer's named options), and every constant of sections 1-3 was proposed by the blind judge,
checks or re-checks or fixed by the blind recalibration of section 4. REPLACING the existing versions, not adding a
path beside them as A91 first asked, follows the blind judge's false-positive finding (section 0) and applies to every
program alike; the captain used no discretion per program. For these reasons this file judges ONLY events knowable
after its own registration time.

REGISTRATION TIME: the latest of three times, all recorded in the captain's amendment that pins it as
`REGISTERED_AT_6` (A92's method): this file's commit time; the pushing client's own clock read after the push of the tag
`prereg-evl-6` returns; and GitHub's activity time for the push of the branch `prereg/evl-6`. The tag never moves. A
version this file registers counts only events knowable after REGISTERED_AT_6. Nothing here changes for a registered
program: a change is a new version with its own registration time.

## 0. Why this file replaces PREREG-EVL-3's screen, and what it buys

- A91 asked for a second promotion path BESIDE PREREG-EVL-3's screen, with both paths' false-positive rate accounted.
  Measured on the judge's common generator (section 4), PREREG-EVL-3's screen ALONE, exactly as registered (its skew
  check and its retirement rule included), passes a program with no edge 14.3-15.2% of the time within 120 sessions at
  its worst plausible cell (crash days, a 20 bp persistent drift, rho_day 0.15, 30 events a session) on two seed sets
  (the judge's 0.1525 +- 0.0080; check 2's 0.1435 +- 0.0055 on 4,000 fresh programs), and 0.199 at a day-shock
  persistence phi_day of 0.25 (check 2). Its own 5-8.4% calibration (PREREG-EVL-1 and -3) used a 0.4% t(4) day shock, no
  persistent drift and no crash days. A second path only adds to it: beside the judge's draft screen the union reaches
  0.199 at the worst plausible cell of the judge's grid (0.088 at the base), and more at phi_day 0.25, where
  PREREG-EVL-3 alone is already 0.199. The replacement rests on that union and on the widened grid of section 4.3, not
  on the 15.2% alone: no second path can hold a program's test to the owner's 15%.
- So this file does what PREREG-EVL-3 did to PREREG-EVL-1's programs: it registers a NEW VERSION of every seatable
  program, judged by this file's screen ALONE (section 1.1). The version it supersedes stays a shadow record: its
  PREREG-EVL-3 looks are computed, written and reported beside, and from REGISTERED_AT_6 on they move no band, whatever
  the release date (section 1.1). No superseded version has held a look (PREREG-EVL-3's first look needs 8 session
  blocks: the Oct 28 close at the earliest), so none has spent any false-positive probability, and the lane's count
  drops them as PREREG-EVL-3 dropped version 1 (section 5).
- WHAT THE CHECKS AND RE-CHECKS CHANGED (the captain's D1-D9 and D10-D16, A107): the day shock's persistence phi_day
  0.15 and 0.20 joins the plausible grid (D1), and so do crash days with a t(3) body, crash days clustered in
  high-volatility regimes, both together, and event counts that follow the size of the day's move (D14); the schedule
  is re-chosen on that grid (sections 1.3, 4.3); the sign-flip reads money's weights and a pass needs the events money
  buys to have made money (sections 1.2, 1.4); a run that reaches its 60th block without a pass ENDS and the next run
  starts when the lane's budget holds it, so no version is retired without a test and the budget bounds every charge
  (sections 2, 3, 5; D2, D11); the Probe stay's fixed reads are a session-block test that demotes at p <= 0.15, and the
  money stop is a catastrophe stop at 10% of the whole stay's buy cost, since PREREG-EVL-3's $150 demotes a real edge
  about half the time once A99's slots and Sized lots enter (section 3; D10, D15); the goal's 15% is read per test, per
  run, with the per-version figure stated beside it (D11); the lane's budget is restated and called a relaxation
  (section 5).
- WHAT IT BUYS, on synthetic paths (section 4). PER RUN (each run one pre-registered sequential test, D11): a worst
  plausible false-positive rate of 0.129 on the selection seeds that chose the rule (0.1290 +- 0.0053 on 4,000 programs
  at the widened grid's worst cell: t(3)-body crash days clustered in high-volatility regimes, left-skewed events, a
  10 bp drift, rho_day 0.15, phi_day 0.20, counts that follow the day's move at 3 events a session), and at most 0.131
  on fresh seeds that never chose it (0.1308 +- 0.0053 at the worst of the same 16 cells, 0.1305 at that cell; 0.130
  +- 0.004 pooled over both sets, 8,000 programs), for section 4.2's generator over section 4.3's grid. PER VERSION,
  within 120 sessions (two runs): 0.240 at that cell on both seed sets. MEASURED DEPARTURES ABOVE 0.13 (section 4.4):
  day momentum AR 0.40 at rho_day 0.30, 0.138-0.161 at 13-85 a session; a 30 bp drift with crash days and skewed events
  at rho_day 0, 0.148; phi_day 0.25 with t(3)-body clustered crash days, 0.131-0.147. On the same paths the previous
  round's rule reads up to 0.179 (its 0.130 held only for crash days with a normal body) and the judge's draft rule up
  to 0.241. At the old corner (crash days with a normal body, skewed events, a 20 bp drift, rho_day 0.15, phi_day 0.20)
  this rule reads at most 0.091, where PREREG-EVL-3 alone, one test for a version's life, reads 0.18 (0.1845 +- 0.0087
  at 30 events a session; 0.180 with crash days alone; 0.143 at 85; `evl3_corner.out`) and was not measured on the new
  day shapes. Beside these: 0.013-0.025 at the base model (symmetric, rho_day 0.05, no drift); a test of the population
  real money buys (D4); no version retired without a test (D2); and a demotion that keeps a real 60 bp edge at Probe at
  least 88% of the time to its 1,000th, 2,000th and 3,000th Probe+ event at every plausible cell measured, where the
  stays reach them (section 3).
- WHAT IT COSTS: speed. The first look is at the 22nd settled block (the previous round's rule had the 9th, the draft
  the 6th; PREREG-EVL-3 has the 8th with 60 events), so NOTHING IS PROMOTED BEFORE THE 22ND SESSION of a run, at any
  edge. At a true 60 bp edge, rho_day 0.05, the mean over the five rates, the expected sessions to the first promotion
  within 60 sessions are 45.5 (the previous round's rule 43.7; PREREG-EVL-3 alone, on the judge's seeds, 39.5), and
  P(promoted by the 10th / 20th / 25th / 40th / 60th session) is 0 / 0 / 0.302 / 0.412 / 0.437 (the previous rule by the
  10th / 20th / 40th / 60th: 0.109 / 0.274 / 0.371 / 0.468; PREREG-EVL-3: 0.135 / 0.290 / 0.474 / 0.571); at 100 bp 0 /
  0 / 0.599 / 0.742 / 0.775 and 33.1 sessions (the median 22 at 13 to 85 events a session). The 17 shortlisted schedules
  faster by that measure read 0.1305-0.1792 on the selection seeds, every one above 0.13; no shortlisted schedule with a
  first look before the 22nd block that holds 0.13 is as fast (section 4.3). About 56% of the first runs of a real 60 bp
  edge end unpassed at their 60th block (0.31 at 85 events a session to 0.78 at 3), and those versions go on in learning
  with a fresh run when the budget holds it (D2, D11). The twelve programs of PREREG-EVL-3 and -4 restart their count at
  REGISTERED_AT_6, three sessions after theirs began (four if it falls after the Oct 22 open; A91: no event the captain
  could have seen is judged by a new test).

## 1. The test

### 1.1 Who it judges

- THE NEW VERSIONS. For every seatable version registered before REGISTERED_AT_6, this file registers the next version
  of the same id, and that version is the id's SEATING version from REGISTERED_AT_6 on:

  | superseded (its file) | new version |
  |---|---|
  | EVL-ERN-READ-O1, EVL-ERN-REACT-C1, EVL-8K-READ-O1, EVL-NEWS-READ-O1, EVL-ERN-REACT-ON, EVL-ERN-GUIDE-O1, EVL-INS-BUY-O1, EVL-NEWS-READ-ON, EVL-NEWS-REACT-ON: version 2 (PREREG-EVL-3) | version 3 |
  | EVL-8K-REACT-ON, EVL-8K-READ-ON, EVL-NEWSPM-READ-ON: version 1 (PREREG-EVL-4) | version 2 |
  | EVL-NEWS-NIGHT2-ON, EVL-ERN-DROP-ON, EVL-ERN-UNDER-ON: version 1 (PREREG-EVL-5) | version 2 |
  | every seatable birth of R3 registered before REGISTERED_AT_6: version 1 | version 2, same id and spec |

  Each new version takes its superseded version's events and rule word for word: family, windows, selection rule,
  verdicts (prompts, model, parsing, the first stored answer final), one event per issuer per D, EXCLUDED and every
  skip, entry, exit and hold (one session), ranking, costs, per-event returns, TRADABLE, the LIMIT AT ENTRY, its
  control (the same control record), its band SIZES, its place in ROOM's order, and every real-money rule of its file
  (the sale gate; PREREG-EVL-4 section 1.3; PREREG-EVL-5 section 1.3). It differs in exactly these things: its
  registration time is REGISTERED_AT_6 (it counts only events knowable after it); its promotion, Sized, demotion,
  run and retirement rules are this file's (sections 1-3), in place of PREREG-EVL-3 sections 2 (its moves; its sizes
  stay) and 3; and its Probe band and at-size buys are section 6's (A99).
- THE NEW VERSIONS' RECORD BEFORE THE RELEASE (D8). For every session decided before the House release that carries
  this file, a new version's intents are exactly its superseded version's intents for that session whose events are
  knowable after REGISTERED_AT_6, with the same skips, cooldown and live or backfill rule as decided at the time
  (copied, never re-decided). From the release on it is decided by itself. Its one position per issuer (PREREG-EVL-1
  section 5, with A72) and its 5-session cooldown (`programs.ISSUER_GAP_SESSIONS`) count its own intents and, in
  addition, the superseded version's intents for every session decided BEFORE the release, including those whose
  events were knowable before REGISTERED_AT_6 (D12). No intent the superseded version writes for a session decided
  from the release on ever counts against the new version. From then on the two keep separate records, the superseded
  one as a shadow record. So the new record continues the superseded one without a gap or a doubled issuer, and the
  order in which the two versions are decided changes nothing. THE TEST (section 7's code carries it): on the
  release's first session, when the superseded version and the new version both select issuer X and neither the new
  version nor the superseded version before the release holds X within the cooldown, the new version writes its
  intent for X (never `skipped:issuer-held`), whichever version is decided first; when the superseded version held X
  on a session decided before the release, within the cooldown, the new version skips X.
- LATER VERSIONS. Every seatable version registered after REGISTERED_AT_6 (R3's births from then on, and every later
  file's seatable programs unless that file registers another screen) is judged by sections 1-3 alone, from its own
  registration time.
- NEVER CHOSEN PER PROGRAM. The screen, its constants and its seeds are the same for every version; nothing in them
  depends on a program's id, family, rate, early figures or band.
- SUPERSESSION IN MONEY. A superseded version keeps trading at learning size until the House release that carries this
  file is live; from then its new version holds the seat (in `learning`) and the superseded version is a record (its
  open lots exit by their rules). Until the release the new versions are records only (no real money).
- SUPERSEDED VERSIONS ARE NON-PROMOTING FROM REGISTERED_AT_6 (D7), whatever the release date: their PREREG-EVL-3 looks
  are written and reported and move no band (no promotion, no retirement, no demotion). The code guard ships in release
  1019h (section 7), before the first close at which any superseded version's first PREREG-EVL-3 look can be held (the
  Oct 28 close for the nine). If that guard is not live before that close, the captain stops the superseded versions'
  seats before it (a seat kill), so no test choice depends on when the release lands.

### 1.2 The record, the blocks and the values

- A version's RUN RECORD at a look as of the close X: its settled events (outcomes `status = 'settled'`) whose knowable
  time is after its registration time, that belong to the run (section 3), and whose scheduled exit is at or before X
  (PREREG-EVL-1 section 7's covered blocks); for each: entry session D, issuer (CIK, else symbol), a, r and TRADABLE
  (PREREG-EVL-1 section 5; an event whose tradability is unknown is not TRADABLE). Only TRADABLE events enter any
  figure below.
- BLOCKS: every entry session holding at least one TRADABLE event of the record is one block (every seatable version
  holds one session, so blocks never overlap; a session with no event adds no block, so the count is of settled events
  grouped by their session, never of days); block s = 1, 2, ..., S in session order; n_s is its count of TRADABLE
  events and B_s their mean a (`math.fsum`).
- THE VALUES (D4): y_s = min(n_s, 14) x (B_s - 0.0010). 14 is this file's Probe open cap (section 6, A99).
- THE ESTIMAND (D4, D13). The null this screen rejects is "the MONEY-WEIGHTED mean after-cost abnormal return of ALL
  the record's TRADABLE events, each block's mean B_s weighted by min(n_s, 14), is at most 10 bp an event". It equals
  the mean a Probe of this file earns (at most 14 positions a session, each for one session) only when the program's
  own ranking inside a session tells nothing about a, as the calibration's generator assumes (section 4.2: the
  ranking is the draw order). Where the ranking does, the statistic still reads every TRADABLE event's block mean,
  and what money buys is read only by section 1.4's top-14 guard; that guard is a sign condition on pooled means, not
  a test, and its rate for a program whose edge sits below its 14th pick is not calibrated here. At 14 or more events
  a session the weights are equal (y_s = 14 x (B_s - 0.0010)); at fewer, a session counts the events money can buy.
  The event-weighted mean a is reported beside every look. The weights stand while every band caps its open
  positions a session (learning 8, Probe 14, Sized 8).
- THE MARGIN: 10 bp. A persistent drift of the event basket against its benchmark for weeks (section 4.3) must exceed
  10 bp a session to pass for an edge.

### 1.3 The statistics

- p, the screen's p: the one-sided sign-flip p of mean(y) > 0:
  - S <= 16, EXACT over all 2^S sign vectors: p = #{b in 0 .. 2^S - 1 : sum_j s_bj y_j >= sum_j y_j - S x 1e-12} /
    2^S, with s_bj = +1 when bit j of the integer b is set (bit 0 is block 1), else -1 (screen.py `_count` over
    `b.to_bytes(width, "little")` for every b counts exactly these vectors with today's 8-bit tables).
  - S >= 17, Monte Carlo as PREREG-EVL-1 section 7: p = (1 + #{v : sum_j s_vj y_j >= sum_j y_j - S x 1e-12}) /
    (1 + 99,999) over 99,999 vectors `random.Random(seed).getrandbits(S)` (bit j set = +1 for value j), seed =
    int.from_bytes(sha256(seed string).digest()[:8], "big"), seed string f"{id}|v{version}|evl6|{tag}S{S}".
  - THE TAG: "" for the version's run 1, f"run{n}|" for its run n >= 2, f"stay{n}|" for its n-th Probe stay (n >= 1).
- q, the lower tail (retirement and the stay's demotion): the same count on the values -min(n_s, 14) x B_s (no
  margin), over the same vectors (the same exact count, or the same seed string).
- p_I, the issuer-block p (a guard: section 2): PREREG-EVL-1 section 7's issuer-block sign-flip p of the record's
  TRADABLE events (each issuer's events averaged into one value, values in ascending issuer order, no margin), 99,999
  vectors, seed string f"{id}|v{version}|evl6|{tag}S{S}|issuer".
- alpha(S), by the record's own S (D14): 0.020 for 22 <= S <= 30, 0.006 for 31 <= S <= 40, 0.001 for 41 <= S <= 60;
  no look below the 22nd block (section 2). (Every look is at S >= 17, so every p is the Monte Carlo p; its floor is
  1 / 100,000.)
- THE SUMS: every sum is a `math.fsum`; the one tolerance in a sum is the sign-flip count's (a signed sum at or above
  the observed sum less S x 1e-12 counts against the program). The comparisons are section 1.4's.

### 1.4 RETIRE, PASS, and the move a look makes

- At every look of a RUN (section 3; a Probe stay's looks act as section 3 says), in this order:
  1. RETIRE when the record's mean a < 0 and q <= alpha(S) + 1e-12: the version goes to `retired` (no more real money;
     the shadow continues as a record; a new version is the only way back). Nothing else is checked at that look.
  2. PASS when ALL hold: p <= alpha(S), with no tolerance (as `screen.judge_look`); the record has >= 30 TRADABLE events
     and >= 30 distinct issuers; its mean a > 0 and its mean r > 0 (a long-only program must make money after cost,
     beside its benchmark and in raw terms); THE MONEY'S EVENTS (D4): in each block take its top 14 TRADABLE events by
     the program's own ranking, the order `book.picks` gives a session's picks before ROOM and the sale gate
     (`intents.rank_key` descending, a missing key last; then the issuer's `adv20` on the entry session descending, a
     missing `adv20` counting as 0 as in `book.picks`; then the event id), all of a block's events when it has 14 or
     fewer: pooled over the record their mean a > 0 and their mean r > 0; for a READ version (one with a control:
     screen.CONTROLS, or a READ birth's derived control), its mean block value exceeds its control's over the same
     sessions (PREREG-EVL-1 section 7's rule, block values unweighted; the control's TRADABLE events of those sessions
     whose knowable time is after the version's registration time); and p_I <= 0.10.
  MEAN a AND MEAN r, here and everywhere in this file, are event-weighted means over the TRADABLE events named
  (`math.fsum`).
- A PASS moves a `learning` version to `probe` from the first decision after the look is written (PREREG-EVL-3 section
  2's PROBE, with section 6's room and at-size buys); in any other band it moves nothing. The move is written in the
  look's own transaction (screen.write_look's `apply`), so a look on record has always made its move.
- Written with every look: p, alpha, q, p_I, every guard and its figures (the top-14 means, the event-weighted and
  money-weighted means), the counts, the run or stay and its tag, and PREREG-EVL-1 section 7's figures beside (the
  all-event figures, the raw-r test, the half-spread stress, the market-direction share, the control's figures, the
  late-verdict share).

## 2. Looks and minimums, counted in independent units

- THE UNIT is the session block. A day-level residual shock common to every event of a session (news days; factor days:
  momentum, value, size, sector rotations; beta mismatch to SPY or IWM) makes one session's events one draw. A
  sign-flip over session blocks holds its level exactly when the blocks' values are independent across sessions and
  each is symmetric about the null (Fisher 1935; Lehmann and Romano, Testing Statistical Hypotheses, 4th ed., ch. 17;
  Canay, Romano and Shaikh 2017, Econometrica 85(3), for the approximate version), and then it holds whatever the day
  shock's size, its loading across names, or the sector clustering and issuer repeats inside a session. The lane's
  blocks depart from those conditions in measured ways: left-skewed days (crash days, with a normal or a fat-tailed
  body, clustered in high-volatility regimes or not) and left-skewed events, a persistent family drift, persistence of
  the day shock itself (phi_day), and event counts that move with the day. Section 4 measures the rate under each and
  their combinations; the margin, the schedule and alpha(S) hold it at 0.13 at the worst plausible cell of section
  4.3's widened grid of section 4.2's generator, not at its nominal level (0.129 per run on the selection
  seeds that chose the rule, at most 0.131 on fresh seeds: section 4.4). The departures section 4.4 measures beyond
  that grid reach 0.131-0.161: day momentum AR 0.40 at rho_day 0.30, a 30 bp drift, phi_day 0.25 with t(3)-body
  clustered crash days.
- WHICH TEST CARRIES THE RATE. This file's false-positive rate is carried by the session-block test: a session is a
  block of issuers, and this file reads the goal's "by issuer-block permutation" as a permutation over those blocks,
  the one that holds its level under a common day shock. The issuer-block permutation itself (one value an issuer,
  PREREG-EVL-1 section 7), which PREREG-EVL-1 and -3 held at the screen's alpha, is kept as a guard at p_I <= 0.10:
  ALONE it cannot carry the rate here, since with a day-shock share rho of event variance and m events a session it
  understates the variance by 1 + rho (m - 1) (5.2 at rho 0.05 and 85 a session). The owner sees this reading here and
  in the registering amendment (A107).
- PER TEST, NOT PER VERSION (D11). This file reads the goal's "false-positive rate <= 15%" PER TEST: each run is one
  pre-registered sequential test, at most 0.13 at the worst plausible cell, charged when it starts. Under D2 a version
  that never passes is tested again from its 61st block (when the budget holds the run: section 3), so PER VERSION its
  chance of a false pass grows with each run: 0.240 within 120 sessions at the worst plausible cell (two
  runs, on the selection and the fresh seeds alike; section 4.4), about 1 - 0.87^n after n runs. PREREG-EVL-3 gave a
  version one finite sequence of ten looks (60 to 2,250 events), so its rate per test was its rate per version; here
  it is not. No shortlisted schedule holds a version's two runs within 120 sessions to 0.13 (the strictest reads
  0.154: `two_runs_v2.out`). The design brief and D1 said per program; the reading per
  test is the captain's (D11), stated here and in the registering amendment, and the owner may overrule it.
- LOOKS: look k is at the first session close X at which the run's record (covered at X) holds at least S_k blocks
  AND the minimums hold, with S_k = 22, 25, 30, 35, 40, 50, 60 (7 looks: the judge's list from the 22nd block on,
  D14). Looks happen in order, at most one at a close; every S_k reached by the
  close of a look is consumed by that look (thresholds reached together are one look, the lowest k; the others are
  recorded as merged into it); its alpha is alpha(S) at the record's own S. No other look exists; no look is held after
  the run's 60th block.
- MINIMUMS at a look: 30 TRADABLE events and 30 distinct issuers (no issuer more than 1/30 of the issuer-block
  statistic), and 6 blocks (fewer independent sessions can certify a mean only by assuming the size and shape of the
  day shock, Bahadur and Savage 1956, Ann. Math. Statist. 27), which every look meets, the first being at the 22nd
  block. None is a calendar wait: at 3 or more events a session every minimum holds well before the 22nd block, and at
  1.3 a session at about the 15th block (about the 23rd session).
- THE HORIZON ENDS THE RUN, NOT THE VERSION (D2). At the close at which the run's 60th block is covered, a version
  still in `learning` whose run has not passed stays in `learning` (real money at learning size continues) and its run
  ENDS; RUN n + 1 starts with the next block once the lane's budget holds it (section 3). The end is decided with
  that close's look (after its RETIRE and PASS), or, when no look is held there, once that close is final, and
  written in the same kind of transaction.
- FINALITY AND FREEZING (today's machinery, unchanged): a look as of the close X is computed once X is final for the
  version (screen.final_until: A66, A69, A84's per-feed fast path, and each file's own windows) and every intent of the
  version and of its control scheduled to exit by X has settled; it is written once (INSERT OR IGNORE) and never
  recomputed from a record that grew later; once written it freezes its group's records over the sessions it covers
  (run.py `_scope`, as every look); late data delays a look, never its as-of close. A look is identified by (id,
  version, its run or stay tag, S), and its stored key carries the tag, so a later run's or a stay's look is never
  dropped as a duplicate of an earlier one.
- OPTIONAL STOPPING is inside the calibration: every look the schedule can make, to the 60th block, is in the measured
  false-positive rate (section 4); a deferred or merged look only removes a chance to pass.

## 3. Runs, Sized, demotion, re-promotion and retirement (the same framework)

- RUNS AND STAYS. A version's RUN 1 is its record from its registration time. A run ends at its PASS, its RETIRE, or
  its 60th block (section 2). RUN n + 1 starts at the first block after the end of run n by its 60th block, or at the
  first decision after a demotion (its record: the TRADABLE events whose entry decision is at or after that decision),
  in either case once the lane's budget holds it (below). A Probe STAY n begins at the version's n-th move to `probe`
  (bands.probe_since); its STAY RECORD holds the version's TRADABLE events whose entry decision is at or after the
  first decision made at Probe, and a REAL-MONEY event belongs to the stay when its buy decision is at or after that
  first decision and before the stay's demotion. Every run and stay is tested by sections 1.2-2 on its own record,
  its looks counted from its own first block, with its own tag (section 1.3). A stay's looks last while the stay does,
  to its own 60th block (after that only the money stop and the fixed reads below apply to it).
- FRESH RUNS AND THE BUDGET (D11). A FRESH RUN is a version's run n >= 2, after an end at its 60th block or after a
  demotion; a version's run 1 is charged with its version when the version is registered. Every fresh run is charged
  when it starts (section 5), and it STARTS ONLY WHEN THE LANE'S BUDGET HOLDS ITS CHARGE: at the first block after the
  end (or the demotion) and after a close at which the budget's room holds it. When the room cannot hold every run
  waiting at a close, the waiting runs start in their versions' registration order (the earliest REGISTERED_AT first,
  then the id), and a birth registers only when the room left after every waiting run holds the birth's charge. A
  version waiting for room stays in `learning` (real money at learning size, as its band allows) with no run: no look,
  no pass and no retirement until its run starts. So the budget of section 5 bounds every charge the lane ever makes.
- SIZED (`probe` -> `sized`: PREREG-EVL-1 section 8's size, a target of 10% of equity a position, at most 8 open, with
  section 6's at-size buys), at the first stay look at which ALL hold: the stay record PASSes section 1.4 (p <=
  alpha(S), the minimums, the money conditions, the top-14 guard, the control, p_I); the stay holds >= 30 settled
  real-money events bought at Probe size or above whose SUMMED realized after-fee P&L (bands.real_events' pnl,
  `math.fsum`) is > 0; and the signed mean gap per side between those fills and the shadow auction prices is within
  15 bp (the Done reader's fill rule).
  PREREG-EVL-3's 150-event bootstrap route does not apply to this file's versions.
- DEMOTION (`probe` or `sized` -> `learning`), at the first of the three below. THE ORDER at each close, once that
  session's real-money events have settled: first the fixed reads (3) that those settlements cross, in the reads'
  order; then the money stop (1); then the stay's look, if one is held at that close (its lower tail (2), then
  Sized). The stay's REAL-MONEY EVENTS are its settled real-money events at Probe size or above (section 3, RUNS AND
  STAYS), ORDERED by scheduled exit close, then entry decision time, then event id.
  1. THE MONEY STOP (D10; over the whole stay): the stay's real-money events so far, ALL of them from the stay's first,
     have lost, net, more than 10% of their summed BUY COST: net = the `math.fsum` of their realized after-fee P&L
     (bands.real_events' pnl); buy cost = the `math.fsum` over the stay's buys of filled shares x fill price. It is a
     catastrophe stop; the reads carry the test (at Probe's mean at-size lot of $67.9 it is $6.79 for every event
     bought). PREREG-EVL-3's "$150 net over the last 50" is not this file's: with A99's 14 slots and at-size lots, and
     Sized lots of $152-190, it demoted a real 60 bp edge 51-57% of the time by its 1,000th Probe+ event at the old
     corner and 25-35% at the base model, beside the earlier reads at 0.20 (section 4.8). The owner's walls bind on top
     of it and are never weakened: the loss budget ($400 net in any 20 sessions and $800 net total, realized plus open
     risk at the 95% holding-period loss), the daily and drawdown stops and the kill switch;
  2. THE STAY'S LOWER TAIL: at a stay look, the stay record's mean a < 0 and its q <= alpha(S) + 1e-12;
  3. THE STAY'S FIXED READS (D3, D15): at the stay's 100th, 200th, 300th ... real-money event, the one-sided
     session-block sign-flip p for a mean BELOW zero over ALL the stay's real-money events so far is <= 0.15 + 1e-12;
     the read at the k-th takes the first k in the order above. Block = entry session; value = the mean of its
     events' fill-based after-fee r (bands.real_events' r); the last block may be partial. Exact over all sign vectors
     for <= 16 blocks, else 99,999 vectors with seed string f"{id}|v{version}|evl6|stay{n}|read{k}". It replaces
     PREREG-EVL-3's rolling "last 100 negative mean" for this file's versions.
  THE FALSE-DEMOTION RATE, all three together (D15): P(a real 60 bp edge is demoted, by any of the three, by its
  stay's 1,000th / 2,000th / 3,000th Probe+ event), with A99's 14 slots and at-size lots, the move to Sized and its
  lots inside, at the worst plausible cells of the widened grid (rho_day 0.15, phi_day 0.20, a 20 bp drift, crash days
  of every shape, either event shape): at most 0.111 / 0.113 / 0.113 (crash days with a normal body, symmetric events,
  85 events a session: 0.111 +- 0.005 on 4,000 stays; 0.109 / 0.112 / 0.112 at 30 a session); 0.080-0.107 by the
  1,000th with t(3)-body or clustered crash days; at most 0.088 at 8 and 3 a session and 0.058 with counts that follow
  the day; 0.041-0.043 at the base model and 0.023 at rho_day 0 (section 4.8, `demotion_v2.json`). The reads carry
  0.07-0.10 of it at 13 or more events a session, the money stop 0.004-0.024, the stay's lower tail at most 0.005. It
  is <= 0.15 (D3) with room; reads at 0.20 would demote 0.130-0.136 by the 3,000th at the new corners
  (`demotion_v2_read20.json`). A program with
  no edge that passed falsely is demoted 0.244-0.265 of the time by its 300th Probe+ event, 0.386-0.409 by its
  1,000th and 0.46-0.51 by its 3,000th; a cost-only one (-15 bp) 0.36-0.38 and 0.55-0.57. The owner's walls bind on
  top of all three (section 3, DEMOTION 1).
- RE-PROMOTION after a demotion: RUN n + 1's PASS (a fresh test on the record after the demotion).
- RETIREMENT (any band -> `retired`, for good; the shadow continues as a record): ONLY section 1.4's RETIRE at a look of
  the current run, or of a stay (where it demotes instead: DEMOTION 2). The end of a run by its 60th block is never a
  retirement.
- PREREG-EVL-3 section 2's retirement (a held look with the reversed p <= 0.05), its Sized rule, its money stop and its
  rolling demotion do not apply to this file's versions; its band SIZES (as section 6 states), ROOM and the open-risk
  weight do.

## 4. The calibration record (synthetic only)

### 4.1 Files

Paths are relative to `goal-2026-10-19/evl6/`. The scripts and outputs below are copied flat into `docs/prereg/evl-6/`
at the freeze, this file's (from `final/`) under their own names and the judge's, the checks' and the re-checks' with
the prefixes `judge__`, `check1__`, `check2__`, `recheck1__` and `recheck2__`, with `SHA256SUMS`; every figure in
sections 0 and 3-5 comes from one of them.
- THIS FILE'S CALIBRATION ON THE WIDENED GRID (`final/`, D14; the rule, every figure of sections 0-5 unless named
  otherwise): `calib_v2.py` (D14's cells: the new day shapes, the day-following counts and their knife, the other
  structures; its `pilot` and `wpilot.log`); `search_v2.py` (the widened plausible set, the two search passes and the
  edge check, on `search_final.py`'s evaluation, unchanged); `select_v2.py` (the protocol of section 4.3:
  `shortlist_v2.log` / `shortlist_v2.json`, `plan_v2.log` / `w2.cells.json`, `plan_v2x.log` / `w2x.cells.json`,
  `choose_v2.log` / `chosen_v2.json`, `replicate_v2.log` / `w3x.cells.json`; the first choice, before the edge check,
  kept as `shortlist_v2.pass12.*`, `choose_v2.pass12.log`, `chosen_v2.pass12.json`, `replicate_v2.pass12.log`,
  `w3.cells.pass12.json`); `report_v2.py` and `report_v2.txt` (every table of sections 4.4-4.6), `power_v2.py` and
  `power_v2.txt` (section 4.5), `two_runs_v2.py` and `two_runs_v2.out` (per version), `table_v2.py` and
  `table_v2.md` (section 4.4's table); `demotion_v2.py` and `demotion_v2.json` / `.out`, `demotion_v2_nostop.*`,
  `demotion_v2_read20.*` (section 4.8); `chain_v2.sh` and `chain_v2b.sh` (the order the stages ran in; the first was
  stopped after `w3` for the edge check); the run indexes `calib_v2.<phase>.index.jsonl` and the searches
  `search_v2.jsonl`, `search_v2b.jsonl`, `search_v2c.jsonl`; the per-job arrays stay in
  `final/arrays_v2/` (`final/arrays_v2/SHA256SUMS`), reproducible from the seeds in the indexes.
- THE PREVIOUS ROUND'S CALIBRATION (`final/`, the generator and evaluation the above build on, and the record of its
  rule): `calib_final.py` (the generator, D4's values and guard, run 2, the prefilter `pilot` and its `pilot.log`;
  `pilot_any.py` and `pilot_any.log`); `search_final.py` (looks, alpha(S), PASS, RETIRE, the end of a run, the
  candidates and their evaluation); `select_final.py` (the selection protocol of section 4.3: `shortlist.log` /
  `shortlist.json`, `plan.log` / `s2null.cells.json` (its selection seeds), `choose.log` / `chosen.json`);
  `report_final.py` and its `report_final.txt` (the previous round's tables), with `s3_check.out` (its unselected
  replicate); `demotion_final.py` and its outputs (the previous round's demotion, and the 10% level's choice);
  `evl3_corner.py` and `evl3_corner.out` (PREREG-EVL-3 alone at the old corner, on the judge's code); `verify_cited.py`
  and `verify_cited.out` (the judge's and the checks' figures this file cites, recomputed from their stored outputs);
  the run indexes `calib_final.<phase>.index.jsonl` (seeds, cells, timings) and the searches `search_s1.jsonl`,
  `search_s1b.jsonl`. The per-job arrays stay on disk in `final/arrays/` (`final/arrays/SHA256SUMS`) and are
  reproducible from the seeds in the indexes.
- THE JUDGE'S RECORD (`judge/`): `calib_judge.py` (the generator this file's copies), `search_judge.py`,
  `report_judge.py`, `chosen_rule_tables.txt` (the draft rule's every cell beside PREREG-EVL-3's), `demotion_check.py`
  and its `.out`, and `search_alone_L0_main.jsonl` (section 4.7's WSP-IUT figures, copied as
  `judge__search_alone_L0_main.jsonl`); its arrays stay in `judge/arrays/` (`SHA256SUMS`).
- THE CHECKS' RECORDS: check 1 (`check1/calib_c1.py`, `calib_c1m.py`, `demotion_c1.py`, `demotion_c1b.py` and their
  `.out`, `eval_c1.*.out`, `eval_pw.out`, `judge_grid_pw.out`, `exhaustion_c1.out`); check 2 (`check2/check2.py`,
  `check3.py`, `rules2.py`, the plans `plan1-7.json`, and the runs this file reads, `run1.jsonl`, `run3.jsonl` and
  `run7.jsonl`; its other runs stay in `check2/`).
- THE RE-CHECKS' RECORDS: re-check 1 (`recheck1/rc_sim.py`, `mkplans.py`, `rc_pool.py`, `rc_pool_dem.py`,
  `mech_t3body.py`, `theirs_run.py`, `theirs_eval.py`, `demotion_alt.py`, `demotion_long.py`, and `out/POOLED.txt`,
  `out/POOLED_DEMOTION.txt`, `out/mech_t3body.out`, `out/plan[A-E].report.txt`); re-check 2 (`recheck2/two_runs_rc2.py`
  and `.out`).
- The three designs' own calibrations stay as their records: `evl6/calib_within.py`, `evl6/calib_evalue.py`,
  `evl6/calib_strata.py` with their outputs.

### 4.2 The generator

The judge's generator (`judge/calib_judge.py`), copied into `final/calib_final.py` with every risk it held unchanged: it
holds at once every risk the three calibrators found, each missed by at least one of them.
- Issuers: 3,000 in 11 sectors (weights .22 .14 .12 .11 .09 .08 .07 .06 .04 .04 .03), Zipf(0.8) popularity (the same
  names recur); sigma_i log-uniform from 1% to 10% a session; three style factors (momentum-, value- and size-like)
  with loadings N((.2, -.1, .2), .5^2); one position per issuer per program with the 5-session cooldown; on half the
  sessions one hot sector draws four times its weight (sector clustering of news days).
- Events: the control holds Poisson(nbar / 0.30 x Gamma(3, 1/3)) events a session (count CV 0.58); the program holds
  each control event with probability 0.30; nbar = 85, 30, 13, 8 and 3 program events a session. THE PROGRAM'S RANKING
  inside a session is the draw order (popularity plus Gumbel noise: liquid names first, uninformative about returns);
  the top-14 guard reads its first 14.
- Per event: a = mu_family + D_t + h_t (c_t + s_sector,t + beta_i . f_t + sigma_i e_it) + jump + skill x [the
  program's], floored at -100%; r = a + b_t with b_t ~ N(4 bp, 1%).
  - c_t, the residual DAY shock common to every event of the session: sd_c z_t, z_t = phi_day z_(t-1) + sqrt(1 -
    phi_day^2) eps_t, eps_t of unit variance: symmetric t(3), or CRASH DAYS (5% of sessions N(-3, 1), the rest N(m,
    s): skew -1.6); sd_c^2 = rho_day / (1 - rho_day) x V0, V0 = 0.0027 (event sd 5.2%), so rho_day 0, 0.05, 0.15,
    0.30 gives sd_c 0, 1.2%, 2.2%, 3.4% a session. phi_day (the judge held it at 0.10) is a cell parameter here.
  - s: 11 sector shocks, sd 1.0%, t(3); f: the style factors' day returns, sd 0.6%, t(3); e_it unit t(3), or LEFT
    SKEWED (two-piece t(3), scales 1.4 / 0.6); +-30% jumps at 0.5% an event, half down, or 80% down in the skewed
    shapes, mean-compensated so the null mean is exact; h_t a volatility regime exp(x_t - .09), x AR(0.9), sd 0.3.
  - D_t, a PERSISTENT FAMILY DRIFT shared by the program and its control: AR(1) at 0.97 (half-life 23 sessions) with
    stationary sd 0, 10 or 20 bp a session (about +-4% a month at 20 bp for weeks at a time).
- ADDED (the checks' structures): check 1's counts that follow the size of the day shock (the control's count x
  exp(0.3 min(|eps_t|, 4)), about twice on a crash day) with the knife edge set on MONEY weights min(n_t, 14); check 2's
  count-residual coupling (a session at twice its intensity carries a lower residual: kappa 1-2%, event-weighted mean
  exactly 0), its volatility-coupled drift (lam) and its crash days at 10% of sessions at -2.5 sd; check 1's drift at
  AR 0.70-0.90 with the judge's monthly yardstick.
- ADDED BY D14 (re-check 1's structures; `final/calib_v2.py`, which generates only these cells: every earlier cell
  comes from `calib_final.py` unchanged), each day still of mean 0 and variance 1:
  - t(3)-BODY CRASH DAYS: 5% of sessions N(-3, 1), the ordinary days m + s x unit t(3) (the tails the symmetric days
    already use) instead of N(m, s);
  - CRASH DAYS CLUSTERED IN HIGH-VOLATILITY REGIMES: the crash probability of session t is p_t = 0.05 exp(2 x_t) /
    E[exp(2 x)], at most 0.09, x_t the volatility regime's log state (its mean 4.66%), with m and s set from p_t;
  - both together;
  - counts that follow the size of the day shock (check 1's structure, above) on every day shape, the knife edge set
    on money weights min(n, 14) from the joint law of the regime and the day shock;
  - OTHER STRUCTURES (reported, not in the grid): the drift's innovation correlated 0.3 with the day shock's
    innovation; the volatility regime at AR 0.97; the corner at 110 and 150 events a session; the drift at AR 0.95;
    check 2's count-residual coupling with the knife set on money weights.
  `calib_v2.py pilot` (`wpilot.log`): the prefilter below holds on four of these cells (no disagreement), and the
  day laws have mean 0, variance 0.99-1.00, skew -1.5 to -1.6 and a mean crash probability of 4.66% when clustered;
  the realized money-weighted mean a of the knife edge is -1 to +2.4 bp over the selection cells (section 4.4), as in
  the earlier cells.
- NULLS: N3, THE KNIFE EDGE (skill 60 bp, mu_family -60 bp): every event's mean a is exactly zero, so its
  money-weighted and event-weighted means are zero, while it beats its control by 42 bp, so the control condition never
  protects; it is also exactly the null of a program WITHOUT a control (REACT, INS-BUY and their births). N1 (no reading
  skill: the program a random 30% of its family, mean zero). N2+ (no skill, +30 bp common drift: a false "beats its
  control", not an owner false positive, its mean a being positive).
- RUN 2: in every selection, fresh and stress cell of `calib_v2.py` (and the previous round's fresh cells) the record
  after the 60th block is a second run, tested on its own (D2).
- MONTE CARLO SHORTCUTS, each leaving a rule's level unchanged (as in the judge's file): S <= 16 exact; S >= 17 over
  19,999 fixed sign vectors (a valid Monte Carlo p at each look; the rule draws a fresh seed per S); the issuer guard
  over 999 vectors; p computed only where z = sum y / sqrt(sum y^2) >= 1.0 and the guards hold, q only where mean a <
  0 and z(-y) >= 1.0 (`calib_final.py pilot` and `pilot.log`: on four cells no first pass at any alpha from 0.003 to
  0.020 differs from full computation; `pilot_any.py` and `pilot_any.log`: at every program and session at which the
  full p or q is <= 0.020 with its guards, the prefiltered value is the full one, so the shortcut holds for any
  schedule).
- THE SEEDS: SEARCH seeds from 111,000,001 (`s1null`, 1,000 programs a cell over 120 sessions; `s1power`, 1,000 a
  cell) and 121,000,001 (`w1`, D14's cells, 1,000 a cell); SELECTION seeds from 122,000,001 (`w2`) and 122,500,001
  (`w2x`); FRESH seeds, which never searched, shortlisted or chose, from 123,000,001 (`w3`) and 123,500,001 (`w3x`);
  POWER seeds from 114,000,001 (`s2power`, 2,000 a cell over 120 sessions); stresses from 115,000,001 (`stress`) and
  126,000,001 (`wstress`); demotion from 124,000,001, 125,000,001 and 125,500,001 (and the previous round's
  118,000,001 and 119,000,001). The previous round's selection seeds (113,000,001, `s2null`)
  and its replicate (116,000,001, `s3null`) are kept as records of its rule; PREREG-EVL-3 at the old corner from
  117,500,001. None was used by the judge (81-89 million), the checks (91-99 million) or re-check 1 (150-166 million).

### 4.3 The worst plausible set, the choice, and why

- THE PLAUSIBLE GRID (D1, widened by D14), every combination of: rho_day 0, 0.05, 0.15; day-shock persistence phi_day
  0.10, 0.15, 0.20 (at rho_day > 0); days symmetric t(3), crash days with a normal body or, by D14 (at rho_day > 0),
  crash days with a t(3) body, crash days clustered in high-volatility regimes, or both; symmetric or left-skewed
  events (crash days and skewed events together: the corners); persistent drift 0, 10 or 20 bp (AR 0.97); 85, 30, 13,
  8 or 3 events a session, or, by D14 (at rho_day > 0, on every day shape), counts that follow the size of the day
  shock at 8, 5 or 3 a session; the knife-edge null throughout, the no-skill null on the earlier shapes; left-skewed
  events alone at 20 bp; persistent issuer effects of 1%. The WORST PLAUSIBLE figure is the maximum over that whole
  grid: 1,495 cells, the earlier 415 (`s1null`) and D14's 1,080 (`w1`).
- WHY phi_day 0.20 IS IN IT AND 0.25 IS A STRESS (D1): no outcome-free record measures the day shock's persistence; the
  judge held it at 0.10 without a reason for that ceiling, and both checks showed the rate climbing steeply with it
  where days are left-skewed (check 1: 0.156 at 0.20, 0.166-0.178 at 0.25 on the corner; check 2: 0.163 at 0.20, 0.183
  at 0.25, for the draft rule). The captain put 0.15 and 0.20 into the grid in every shape and drift and named 0.25 a
  stress.
- WHY THE NEW DAY SHAPES AND COUNTS ARE IN IT (D14): fat tails and volatility clustering are stylized facts of real
  markets. The grid's symmetric days already had t(3) tails, so crash days with a normal body were its thin-tailed
  exception, and crashes come when volatility is high. Re-check 1 measured both inside the grid's stated bounds: the
  previous round's rule read 0.155 with t(3)-body crash days and 0.160 with clustered ones at the corner, 0.176 with
  both, and 0.140 at 3-5 events a session with counts that follow the day's move (the REACT and DROP rows are selected
  by the size of the move) at phi_day 0.20 (`recheck1/out/POOLED.txt`). The captain put all four into the grid, in
  every drift at phi_day <= 0.20 and rho_day <= 0.15.
- WHY rho_day 0.15 IS THE CEILING: c_t is the whole event basket's session return beyond its own benchmark. At 0.15 it
  is 2.2% a session, about 10% a month of tracking error against SPY or IWM for a basket that changes every session,
  with crash days at -6.6%: beyond what diversified small- and mid-cap baskets show against IWM, whose own session sd
  is about 1.5%. 0.30 (3.4% a session, crash days at -10% about once a month) is a stress.
- WHY 20 bp: a 20 bp-a-session drift at AR 0.97 is about +-4% a month of abnormal return of the event basket for weeks
  at a time (a speculative, high-volatility or attention regime); the e-process calibration named it the worst
  plausible and 30 bp a stress.
- STRESSES (named, reported, not binding): phi_day 0.25 at rho_day 0.15 (also with the new day shapes); rho_day 0.30
  in every shape and drift; drift 30 bp, and 20 bp at AR 0.99; day momentum AR 0.40 at rho_day 0.30; stronger crash
  days (3% at -4.5 sd) with 90% of jumps down at 1% an event; crash days at 10% of sessions at -2.5 sd. OTHER
  STRUCTURES (reported): counts coupled to the session's residual, a volatility-coupled drift, the drift at AR
  0.70-0.95, and re-check 1's: the drift's innovation correlated with the day shock's, the volatility regime at AR
  0.97, the corner at 110 and 150 events a session.
- THE CHOICE (D1's protocol, re-run on the widened grid by D14: the FASTEST schedule, by the expected first promotion
  of a true 60 bp edge, among those whose worst plausible rate within 120 sessions is <= 0.13; the 10 bp margin, the
  minimums and the guards kept). Three kinds of seeds: SEARCH seeds searched and shortlisted, SELECTION seeds chose,
  and FRESH seeds never searched, shortlisted or chose.
  1. SEARCH SEEDS (`s1null` and `w1`, 1,000 programs a cell over 120 sessions; `s1power` for the speed). Two passes and
     an edge check (`search_v2.py`): 5,073 schedules (`search_v2.jsonl`: a first look at the 9th to the 16th block, then
     the judge's list; alpha in three pieces, a1 (0.006-0.016) to S = s1, a2 (0.003-0.012) to S = 20, a3 (0.001-0.004)
     to S = 60; the previous round's shortlist and named rules) and, since that pass's frontier sat on its grid's edge
     (a first look at the 16th block with a1 0.016 and a2 0.012, the largest values searched), 6,834 more
     (`search_v2b.jsonl`: first looks at the 14th, 15th, 16th, 18th or 20th block; a1 up to 0.020, the largest alpha the
     arrays' issuer guard covers; the middle piece to S = 20, 25 or 30 with a2 up to 0.016). The selection then chose a
     first look at the 20th block, again the largest searched (`chosen_v2.pass12.json`, `choose_v2.pass12.log`: looks
     from 20, alpha 0.016 to S = 30, 0.002 after, E[min(T, 60)] 45.63), so an EDGE CHECK measured 2,106 more on the same
     search seeds (`search_v2c.jsonl`: first looks at the 22nd and 25th block, a1 0.014-0.020 to S = 22, 25 or 30, the
     middle piece to S = 30, 35 or 40), and steps 2-4 were run again on all 14,013. No alpha above 0.020 was searched:
     the arrays compute the issuer guard only where p <= 0.020.
  2. THE SHORTLIST (`select_v2.py shortlist`, `shortlist_v2.log`): the 54 schedules on the search seeds' frontier
     (none both faster and no worse) with a search-seed worst <= 0.155 (the maximum over 1,495 cells of 1,000 programs
     reads high by two to three standard errors, so the cap sits above 0.13), and three named rules (re-check 1's
     candidate, the previous round's rule, the previous shortlist's strictest).
  3. SELECTION SEEDS (`w2`, seeds from 122,000,001; `select_v2.py plan`, `plan_v2.log`, `w2.cells.json`): every
     plausible cell within 3.5 points of any shortlisted schedule's search-seed worst, 175 cells, 4,000 programs at the
     63 nearest the worst and 2,000 at the rest, and, for the rules the edge check added, the 56 such cells w2 lacked
     (`w2x`, seeds from 122,500,001, `plan_extra`, `plan_v2x.log`, `w2x.cells.json`, 2,000 programs each); the speed on
     the power seeds (`s2power`: 30, 60 and 100 bp at rho_day
     0, 0.05 and 0.15, 2,000 programs a cell over 120 sessions). These seeds CHOSE the rule in step 4, so their figure
     at the chosen rule's worst cell is a selected figure.
  4. THE RULE (`select_v2.py choose`, `choose_v2.log`, `chosen_v2.json`): the shortlisted schedule with the smallest
     E[min(T, 60)], T the session of the first promotion of a true 60 bp edge at rho_day 0.05 (the mean over the five
     rates), among those whose worst plausible rate within 120 sessions is <= 0.13, the worst being the maximum of the
     selection seeds' rates and, for every cell not re-run, its search-seed rate: A FIRST LOOK AT THE 22ND BLOCK; ALPHA
     0.020 FOR S 22-30, 0.006 FOR 31-40, 0.001 FOR 41-60. Its selection worst is 0.1290 (+- 0.0053, 4,000 programs:
     `choose_v2.log`) at t(3)-body crash days clustered in high-volatility regimes, left-skewed events, a 10 bp drift,
     rho_day 0.15, phi_day 0.20 and counts that follow the day at 3 a session; the cells not re-run read <= 0.093 on the
     search seeds. Its E[min(T, 60)] is 45.48 sessions. The 17 shortlisted schedules faster than it read 0.1305-0.1792
     on the selection seeds (the three nearest, 45.18-45.36 sessions: 0.1305-0.1323); re-check 1's candidate (looks from
     12) reads 0.1440 and expects 46.51; the previous round's rule 0.1792 and 43.71.
  5. FRESH SEEDS (`w3`, seeds from 123,000,001, run for the first choice's 16 worst cells, and `w3x`, seeds from
     123,500,001, for the 5 of the chosen rule's 16 worst cells that `w3` lacked; `select_v2.py replicate`,
     `replicate_v2.log`, `w3x.cells.json`; `report_v2.txt`): the chosen rule's 16 worst cells on the selection seeds
     (with the first choice's other 5, 21 cells), 4,000 programs each, on seeds that never searched, shortlisted or
     chose (no figure of `w3` was read before the second choice): 0.1308 +- 0.0053 at the worst (t(3)-body clustered
     crash days, skewed events, a 10 bp drift, rho_day 0.15, phi_day 0.15, counts that follow the day at 3 a session)
     and 0.1305 at the selection worst cell, above 0.13 by less than a sixth of their standard error; pooled with the
     selection seeds those two cells read 0.1293 and 0.1298 +- 0.0038 over 8,000 programs, and every other of the 21
     cells reads <= 0.1283 fresh (<= 0.1254 pooled). Two runs (per version within 120 sessions): at most 0.2400 fresh.
     These are the only false-positive figures at the worst cells that no choice selected; section 4.4 cites them beside
     the selected ones.
- WHY THE FIRST LOOK MOVED FROM THE 9TH TO THE 22ND BLOCK: a look over few blocks is where fat-tailed and clustered
  crash days most distort a sign-flip (re-check 1: one exact look at S = 9-16 at alpha 0.010-0.012 has size
  0.025-0.027 with t(3)-body crash days, against 0.016-0.020 with a normal body; `recheck1/out/mech_t3body.out`),
  and at 3 events a session a block's value is a few events' mean. On the selection seeds the fastest shortlisted
  schedules with a first look at the 9th, 12th, 16th or 18th block read 0.1792, 0.1440, 0.1515 and 0.1445-0.1470; a
  schedule that holds 0.13 with early looks spends so little alpha in them that it is slower (the previous shortlist's
  strictest, looks from 12 at 0.010 / 0.005 / 0.0015: 0.1187 and 48.70 sessions). Alpha 0.020 at three looks between
  the 22nd and the 30th block buys more power by the 40th session than looks from the 9th block did (0.412 against
  0.371 at 60 bp, section 4.5), at the price of no promotion before the 22nd block.

### 4.4 False-positive rates

P(promotion at any look of the first run within 120 sessions) at zero edge, the maximum over the rates of each row
(85, 30, 13, 8 and 3 events a session; with counts that follow the day, 8, 5 and 3); the selection seeds (`w2`,
`w2x`) where the cell was re-run, else the search seeds (`s1null`, `w1`, 1,000 programs); the rows D14 added show the
maximum over the three drifts, the drift at it in brackets (bp); `table_v2.py`, `table_v2.md`; every figure in
`report_v2.txt`.

| null, shape, drift | rho_day 0 | rho_day 0.05: phi 0.10 / 0.15 / 0.20 | rho_day 0.15: phi 0.10 / 0.15 / 0.20 |
|---|---|---|---|
| N3 symmetric, none | .022 | .025 / .029 / .029 | .033 / .037 / .041 |
| N3 symmetric, 10 bp | .021 | .032 / .024 / .038 | .036 / .047 / .046 |
| N3 symmetric, 20 bp | .048 | .055 / .052 / .060 | .041 / .052 / .052 |
| N3 symmetric, issuer effects 1% |  | .024 |  |
| N3 skewed events, 20 bp |  |  | .049 / .055 / .068 |
| N3 crash days, none | .026 | .039 / .030 / .045 | .053 / .068 / .077 |
| N3 crash days, 10 bp | .028 | .047 / .048 / .053 | .061 / .080 / .077 |
| N3 crash days, 20 bp | .050 | .058 / .073 / .078 | .086 / .080 / .079 |
| N3 crash days + skewed events, none | .043 | .047 / .045 / .061 | .069 / .074 / .081 |
| N3 crash days + skewed events, 10 bp | .053 | .051 / .049 / .070 | .070 / .074 / .080 |
| N3 crash days + skewed events, 20 bp | .068 | .065 / .068 / .077 | .080 / .074 / .091 |
| N3 t(3)-body crash days, every drift |  | .061 [20] / .065 [20] / .076 [20] | .079 [20] / .106 [20] / .101 [20] |
| N3 t(3)-body crash days + skewed events, every drift |  | .077 [20] / .069 [20] / .092 [20] | .085 [20] / .091 [10] / .117 [20] |
| N3 clustered crash days, every drift |  | .073 [20] / .070 [20] / .077 [20] | .101 [20] / .100 [20] / .106 [20] |
| N3 clustered crash days + skewed events, every drift |  | .080 [20] / .066 [20] / .093 [20] | .091 [20] / .106 [20] / .109 [10] |
| N3 t(3)-body clustered crash days, every drift |  | .070 [20] / .074 [20] / .080 [20] | .093 [20] / .110 [20] / .115 [20] |
| N3 t(3)-body clustered crash days + skewed events, every drift |  | .074 [20] / .071 [20] / .101 [20] | .103 [20] / .116 [20] / .121 [20] |
| N3 symmetric, counts follow the day (8, 5, 3 a session), every drift |  | .041 [20] / .042 [10] / .049 [20] | .034 [20] / .050 [10] / .053 [20] |
| N3 skewed events, counts follow the day (8, 5, 3 a session), every drift |  | .052 [20] / .053 [10] / .059 [20] | .048 [20] / .059 [0] / .057 [20] |
| N3 crash days, counts follow the day (8, 5, 3 a session), every drift |  | .063 [20] / .067 [20] / .060 [20] | .084 [10] / .084 [10] / .089 [20] |
| N3 crash days + skewed events, counts follow the day (8, 5, 3 a session), every drift |  | .073 [0] / .080 [20] / .084 [20] | .108 [20] / .102 [0] / .110 [20] |
| N3 t(3)-body crash days, counts follow the day (8, 5, 3 a session), every drift |  | .069 [20] / .056 [10] / .069 [20] | .086 [10] / .087 [20] / .100 [20] |
| N3 t(3)-body crash days + skewed events, counts follow the day (8, 5, 3 a session), every drift |  | .077 [20] / .088 [0] / .085 [0] | .109 [20] / .113 [20] / .119 [20] |
| N3 clustered crash days, counts follow the day (8, 5, 3 a session), every drift |  | .063 [10] / .066 [20] / .061 [20] | .097 [20] / .096 [0] / .102 [10] |
| N3 clustered crash days + skewed events, counts follow the day (8, 5, 3 a session), every drift |  | .085 [0] / .096 [20] / .081 [20] | .112 [20] / .118 [10] / .118 [0] |
| N3 t(3)-body clustered crash days, counts follow the day (8, 5, 3 a session), every drift |  | .077 [20] / .058 [20] / .062 [0] | .108 [10] / .112 [10] / .116 [20] |
| N3 t(3)-body clustered crash days + skewed events, counts follow the day (8, 5, 3 a session), every drift |  | .091 [10] / .085 [20] / .090 [0] | .128 [20] / .128 [10] / **.129** [10] |
| N1 symmetric, none | .020 | .029 / .025 / .028 |  |
| N1 symmetric, 20 bp | .040 | .044 / .044 / .053 |  |
| N1 crash days + skewed events, none | .046 | .052 / .060 / .059 |  |
| N1 crash days + skewed events, 20 bp | .067 | .065 / .067 / .069 |  |

- WORST PLAUSIBLE, PER RUN: 0.129 (t(3)-body crash days clustered in high-volatility regimes, left-skewed events, a
  10 bp drift, rho_day 0.15, phi_day 0.20, counts that follow the day at 3 a session: 0.1290 +- 0.0053 on the selection
  seeds, a selected figure). On fresh seeds that never chose: 0.1305 +- 0.0053 at that cell and 0.1308 +- 0.0053 at the
  fresh worst (the same at phi_day 0.15); pooled 0.1298 and 0.1293 +- 0.0038 over 8,000 (section 4.3 step 5). Every
  plausible cell not re-run reads <= 0.093 on the search seeds. Without counts that follow the day the worst is 0.1215
  (the same day and event shapes, a 20 bp drift, 85 events a session; 0.1215 fresh); on the earlier grid (crash days of
  a normal body, counts independent of the day) at most 0.091; at phi_day 0.10 (the judge's grid) 0.128. BASE
  (symmetric, rho_day 0.05, phi_day 0.10, no drift): 0.023 / 0.017 / 0.023 / 0.013 / 0.025 at 85 / 30 / 13 / 8 / 3
  events a session (search seeds). No reading skill (N1): at most 0.069. The realized money-weighted mean a of the
  knife-edge cells is -1 to +2.4 bp (the -100% floor), so these rates read slightly high.
- THE SAME PATHS UNDER OTHER RULES (selection seeds, `report_v2.txt`): at the worst cell the previous round's rule
  reads 0.1730 (its own worst 0.1792), re-check 1's candidate 0.1373 (its worst 0.1440), the judge's draft rule 0.2228
  (up to 0.2405), the first choice before the edge check (looks from the 20th block) 0.1295; this file's schedule with
  unweighted values and no top-14 guard 0.1515. D4's weights and guard bind where counts follow the day (0.1290 against
  0.1515 at 3 a session, 0.1200 against 0.1295 at 8) and change little at 85 a session (0.1215 against 0.1207).
- PREREG-EVL-3 ALONE (as registered, its skew check and retirement included; the judge's generator): 14.3-15.2% at the
  worst cell of the judge's grid on two seed sets (`verify_cited.out`: 0.1525 +- 0.0080 on the judge's arrays, 0.1435 +-
  0.0055 on check 2's fresh seeds), 0.199 at phi_day 0.25 (check 2's `run3.jsonl`), and 0.1845 +- 0.0087 at the old
  corner at 30 events a session (0.180 with crash days alone, 0.143 at 85 a session: `evl3_corner.py`,
  `evl3_corner.out`); not measured on D14's day shapes. The union with the judge's draft rule: 0.199 at the judge's
  worst cell (lag 3, `verify_cited.out`), higher at phi_day 0.25.
- PER VERSION OVER 120 SESSIONS (D2, D11): a version that never passes has two runs within 120 sessions (the second cut
  short at low rates), and the probability that either falsely passes is 0.2400 at the worst cell on the selection and
  the fresh seeds alike, 0.20-0.24 at every cell of section 4.3's step 5 (`two_runs_v2.py`, `two_runs_v2.out`,
  `report_v2.txt`). Each run is charged when it starts (section 5).
- THE GUARDS AND RETIREMENT: the control condition and p_I never bind at the knife edge (it beats its control and has
  no issuer concentration); the top-14 guard and the money's weights bind under count coupling (above). The lower-tail
  RETIRE retires at most 0.3% of 60 bp programs and at most 1.3% of 30 bp programs within 120 sessions (`s2power`,
  `report_v2.txt`).
- STRESSES AND OTHER STRUCTURES (`stress`, 1,000 programs a cell: this file | its schedule unweighted without the
  top-14 guard | the judge's draft rule | the previous round's rule; `wstress`, 2,000 programs a cell: this file, the
  previous round's rule in brackets):
  - rho_day 0.30, every shape and drift: 0.020-0.090 | 0.025-0.094 | 0.044-0.149 | 0.031-0.109; with D14's day shapes
    and skewed events at a 20 bp drift: 0.080-0.109 [0.099-0.182].
  - a 30 bp drift (rho_day 0 and 0.05), symmetric / crash days with skewed events: up to 0.129 / 0.148 | 0.130 / 0.148 |
    0.160 / 0.194 | 0.135 / 0.166; with D14's day shapes at rho_day 0.05: up to 0.107 [0.135].
  - a 20 bp drift at AR 0.99: up to 0.070 | 0.071 | 0.090 | 0.068.
  - phi_day 0.25 at rho_day 0.15: the old corner up to 0.122, crash days alone 0.105, symmetric with a 20 bp drift 0.077
    | 0.123, 0.103, 0.074 | 0.188, 0.169, 0.119 | 0.146, 0.123, 0.089; with D14's day shapes and skewed events: t(3)-body
    clustered crash days 0.147 at 85 a session, 0.118 at 30, 0.131 with counts that follow the day at 3 [0.207, 0.160,
    0.186]; clustered 0.122, t(3)-body 0.124 at most [0.172, 0.162].
  - day momentum AR 0.40 at rho_day 0.30 (crash days, skewed events): 0.097-0.161 | 0.112-0.163 | 0.164-0.265 |
    0.125-0.221.
  - stronger crash days (3% of sessions at -4.5 sd, 90% of jumps down at 1% an event), rho_day 0.30: 0.079-0.112 |
    0.075-0.121 | 0.143-0.176 | 0.106-0.128.
  - crash days at 10% of sessions at -2.5 sd (check 2) with skewed events and a 20 bp drift, rho_day 0.15: 0.079-0.099,
    without them 0.084 | 0.077-0.100, 0.083 | 0.166-0.196, 0.178 | 0.122-0.146, 0.127.
  - a drift tied to the volatility regime (check 2's lam 0.5%) at the old corner's other risks: 0.075-0.106 |
    0.086-0.104 | 0.134-0.155 | 0.100-0.126.
  - the drift at AR 0.70-0.90 at the judge's monthly yardstick (check 1): 0.072-0.076 | 0.072-0.074 | 0.132-0.149 |
    0.092-0.104.
  - check 1's counts that follow the size of the day shock at phi_day 0.10 (now inside the grid): 0.058-0.094 |
    0.055-0.108 | 0.100-0.178 | 0.070-0.121. These programs' event-weighted mean a is -1 to -30 bp and their
    money-weighted mean 0: they earn nothing on what money buys, and the test rejects only what money earns.
  - a session at twice its intensity carrying a lower residual (check 2's kappa 1-2%, event-weighted mean exactly 0):
    0.039-0.076 | 0.063-0.169 | 0.080-0.225 | 0.035-0.101; with the knife set on money weights (re-check 1) at the old
    and the new corner, 3-8 events a session: 0.079-0.107 [0.106-0.153].
  - RE-CHECK 1'S OTHER STRUCTURES (D14), at the old corner / at the new corner (t(3)-body clustered crash days, skewed
    events, a 20 bp drift, rho_day 0.15, phi_day 0.20): the drift's innovation correlated 0.3 with the day shock's
    innovation, 0.096 / 0.124 at 85 a session and 0.092 / 0.117 at 30 [0.128 / 0.181]; the volatility regime at AR
    0.97, 0.097 / 0.118 [0.121 / 0.176]; the corner at 110 and 150 events a session, 0.100 and 0.097 / 0.129 and 0.128
    [0.125 / 0.177-0.189]; the drift at AR 0.95 (20 bp), 0.091 / 0.113 [0.111 / 0.177].
  - N2+ (no skill, a +30 bp common drift: its mean a is positive, so not an owner false positive) passes 0.122 (8 a
    session) and 0.163 (85) within 60 sessions: no test can tell a drifting family's positive mean from the reading's
    skill; Done reads realized money (section 6).

### 4.5 Power and speed

P(promoted by the h-th session of its record), lag 0, a true edge on the program's events only (its control's other
events at zero), symmetric shapes, no drift, phi_day 0.10, rho_day 0.05; the power seeds (`s2power`, 2,000 programs a
cell over 120 sessions; `power_v2.py`, `power_v2.txt`); PREREG-EVL-3 alone on the judge's power seeds of the same
generator in brackets (`verify_cited.out`). No look exists before the 22nd block, so nothing is promoted by the 21st
session.

| edge | events a session | by 22 | by 25 | by 30 | by 40 | by 60 | E[min(T, 60)] | median | run 1 ended unpassed |
|---|---|---|---|---|---|---|---|---|---|
| 60 bp | 85 | .456 | .529 | .607 | .642 [.693] | .689 [.693] | 36.9 [29.0] | 25 | .311 |
| 60 bp | 30 | .322 | .382 | .454 | .490 [.641] | .530 [.787] | 42.6 [31.9] | 60 | .468 |
| 60 bp | 13 | .215 | .304 | .375 | .407 [.485] | .427 [.612] | 45.6 [39.2] | beyond | .569 |
| 60 bp | 8 | .118 | .216 | .266 | .309 [.367] | .321 [.494] | 49.1 [44.6] | beyond | .668 |
| 60 bp | 3 | .006 | .080 | .167 | .208 [.186] | .217 [.271] | 53.1 [52.6] | beyond | .777 |
| 60 bp | mean | .223 | .302 | .374 | .412 [.474] | .437 [.571] | 45.5 [39.5] | | .559 |
| 100 bp | 85 | .811 | .862 | .909 | .933 [.933] | .959 [.933] | 25.4 [15.3] | 22 | .042 |
| 100 bp | 30 | .693 | .777 | .852 | .887 [.908] | .922 [.967] | 27.5 [18.1] | 22 | .077 |
| 100 bp | 13 | .508 | .650 | .733 | .782 [.835] | .818 [.914] | 31.7 [23.0] | 22 | .169 |
| 100 bp | 8 | .285 | .506 | .588 | .650 [.690] | .687 [.837] | 36.6 [29.8] | 25 | .286 |
| 100 bp | 3 | .018 | .199 | .372 | .456 [.410] | .488 [.543] | 44.6 [44.1] | 67 | .483 |
| 100 bp | mean | .463 | .599 | .691 | .742 [.755] | .775 [.839] | 33.1 [26.1] | | .211 |

- RUN 1 ENDED UNPASSED (D2's false-end rate): the share of real edges whose first run reaches its 60th block without a
  pass, beside the power it leaves; those versions stay in learning and start run 2 when the budget holds it.
  Counting run 2, P(promoted within 120 sessions) at 60 bp is .907 / .791 / .653 / .546 / .397 at 85 / 30 / 13 / 8 / 3
  events a session, at 100 bp 1.000 / .995 / .966 / .903 / .745.
- THE PREVIOUS ROUND'S RULE on the same paths (looks from the 9th block), 60 bp, the mean over the five rates: by the
  10th / 20th / 40th / 60th session .109 / .274 / .371 / .468, E[min(T, 60)] 43.7; at 100 bp .288 / .566 / .712 / .803,
  28.0 (`report_v2.txt`). This file's rule is slower to the first promotion and promotes more by the 40th session at
  60 bp (.412 against .371), at the price of nothing before the 22nd.
- AT OTHER CORRELATIONS, 60 bp, the mean over the five rates, by the 22nd / 25th / 40th session: rho_day 0 .357 / .453
  / .571 (E[min(T, 60)] 39.5; PREREG-EVL-3 by the 20th / 40th .419 / .594, 33.5); rho_day 0.15 .130 / .188 / .263 (50.8;
  PREREG-EVL-3 .207 / .349, 45.0). At 30 bp and rho_day 0.05: .056 / .085 / .126 (55.7).
- LAG 3 (the twelve programs of PREREG-EVL-3 and -4, whose own count began three sessions before REGISTERED_AT_6): by
  their own 10th / 20th / 40th session, 85 events a session, rho_day 0.05: at 60 bp 0 / 0 / .614 (PREREG-EVL-3 kept:
  .274 / .518 / .693); at 100 bp 0 / 0 / .916 (.559 / .824 / .933). That is the price of the restart, of A91's rule
  and of the first look at the 22nd block.
- THE PHYSICS: a session's block carries the whole day shock, so the evidence is the number of sessions, not of events.
  At rho_day 0.05 and 85 events a session a block's sd is about 1.3% and a 60 bp edge about 0.45 sd a block: no test
  that holds its level passes it reliably in fewer than about 10-20 sessions, a 30 bp edge is barely detectable within
  60 sessions at any rate, by this file or any other, and with fat-tailed, clustered crash days in the grid a level
  held at 0.13 leaves no room for a look before about the 20th block (section 4.3).

### 4.6 What the seats can expect (from outcome-free counts only)

Rates are the selected intents a session in `evl5/HOUSE-FACTS.json` (Oct 19-21; Oct 21 was a 2,255-article news day and
earnings season runs to about mid-November) or, for rows not yet counted there, their file's own estimate. FIRST LOOK is
the first block at which the schedule and every minimum allow one; its date assumes REGISTERED_AT_6 before the Oct 22
open and a block every session (as-of the close of Fri Nov 20 for an open-to-close row, Mon Nov 23 for a close-entry
row, whose block exits at the next open or close; a later registration moves every date by the sessions it misses); a
pass moves the band from the first decision after the look is written, about one session later under A69's fast
path. P(by 25 / 40 / 60) is section 4.5's at a true 60 bp edge, rho_day 0.05, at the nearest simulated rate.

| new version | events a session | first look | P(promoted by its 25th / 40th / 60th session) |
|---|---|---|---|
| EVL-NEWS-READ-O1 v3 | 54-165 (about 100) | block 22, Nov 20 | .53 / .64 / .69 (85) |
| EVL-NEWS-READ-ON v3 | 54-142 (about 80) | block 22, Nov 23 | .53 / .64 / .69 (85) |
| EVL-NEWS-REACT-ON v3 | 29-83 (about 50) | block 22, Nov 23 | between .38 / .49 / .53 (30) and .53 / .64 / .69 (85) |
| EVL-ERN-READ-O1 v3 | 18-26 (about 22, earnings season) | block 22, Nov 20 | .38 / .49 / .53 (30) to .30 / .41 / .43 (13) |
| EVL-8K-READ-ON v2 | 19-27 (PREREG-EVL-4) | block 22, Nov 23 | .38 / .49 / .53 (30) to .30 / .41 / .43 (13) |
| EVL-NEWSPM-READ-ON v2 | 20-30 (PREREG-EVL-4) | block 22, Nov 23 | .38 / .49 / .53 (30) |
| EVL-8K-READ-O1 v3 | 7-12 (about 10) | block 22, Nov 20 | .30 / .41 / .43 (13) to .22 / .31 / .32 (8) |
| EVL-ERN-GUIDE-O1 v3 | 10-11 | block 22, Nov 20 | .30 / .41 / .43 (13) to .22 / .31 / .32 (8) |
| EVL-NEWS-NIGHT2-ON v2 | 6-60 (central 12, PREREG-EVL-5) | block 22, Nov 23 | .30 / .41 / .43 (13) |
| EVL-ERN-UNDER-ON v2 | 5-14 (central 7, PREREG-EVL-5) | block 22, Nov 23 | .22 / .31 / .32 (8) |
| EVL-ERN-DROP-ON v2 | 3-13 (central 6, PREREG-EVL-5) | block 22 | .22 / .31 / .32 (8) |
| EVL-ERN-REACT-C1 v3, EVL-ERN-REACT-ON v3 | 4-11 (about 5-8) | block 22 | .22 / .31 / .32 (8) to .08 / .21 / .22 (3) |
| EVL-8K-REACT-ON v2 | 1.5-6 (PREREG-EVL-4) | block 22 | .08 / .21 / .22 (3) or less |
| EVL-INS-BUY-O1 v3 | 1-2 (about 1.3) | block 22 (more sessions than blocks) | under .08 / .21 / .22: little power at any edge below 1% |

At a 100 bp edge the same rows read .86 / .93 / .96 (85 a session), .78 / .89 / .92 (30), .65 / .78 / .82 (13), .51 /
.65 / .69 (8) and .20 / .46 / .49 (3). Rows above 85 a session (the news rows, 54-165) read 0.128-0.129 per run at
the new corner at 110-150 events a session (section 4.4, re-check 1's structure), on the cap.

### 4.7 Why not the three designs as written, and what was taken

- WSP-IUT (the control-relative design; `evl6/calib_within.py`): its absolute part is this file's statistic with a look
  at every block and alpha = c / S, no margin. On the judge's grid (phi_day 0.10), with the persistent drift its own
  generator lacked, it reads 0.212 at c = 0.125 and 0.183 at c = 0.09; at c = 0.03, where it reads 0.132, it
  promotes a 60 bp edge by the 20th session 0.219 of the time, the mean over the five rates (the judge's
  `search_alone_L0_main.jsonl`, read by `verify_cited.py`), where this file's rule, held on the wider grid, promotes
  none before the 22nd session and 0.412 by the 40th; WSP-IUT was not measured on D14's day shapes. Its
  within-session permutation never carries the owner's false positive (the intersection-union bound is the absolute
  test's), cannot speed promotion past the absolute test (its designer's own finding), and is anti-conservative under
  factor-loading selection.
- EVL-EPROC-1 (the e-process; `evl6/calib_evalue.py`): anytime-valid only under its own supermartingale null; a
  persistent zero-mean drift makes that null false for weeks and left skew beats its clip allowance; its own fix, a 20
  bp margin, cut its power at 60 bp by about a third (the judge's record).
- SFE-SWITCH (the stratified design; `evl6/calib_strata.py`): its fast part holds its level only if a residual loading
  mismatch it cannot measure is small, and its reference fit is the largest implementation surface of the three.
- PREREG-EVL-3's screen kept as a second path (A91's request): section 0.
- WHAT WAS TAKEN: the session block as the unit and the exact small-S sign-flip (WSP-IUT); the margin against a
  persistent drift (the e-process calibration's own fix); a front-loaded schedule of looks counted in settled blocks
  with little alpha late (the judge's search); money's weights and the top-14 guard (check 2); the end of a run in place
  of exhaustion, the fixed reads as a test (check 1); phi_day in the grid and fresh seeds (both checks); t(3)-body and
  clustered crash days and day-following counts in the grid, the reads at 0.15 and the selected and unselected seed
  sets kept apart (re-check 1); the cross-version issuer rule, the per-test reading stated and the budget's gate on
  fresh runs (re-check 2).
- THE 10% TARGET (A91) IS NOT MET: the fastest shortlisted schedule with a selection-seed worst <= 0.10 (a first look
  at the 25th block; alpha 0.014 to S = 30, 0.006 to 35, 0.001 after) reads 0.099 and expects its first promotion of a
  60 bp edge at 48.5 sessions against this file's 45.5 (`choose_v2.log`). The captain's D1 set the cap at 0.13 for the
  owner's speed demand.

### 4.8 Demotion (section 3), all three triggers together

A Probe stay of one program on this file's generator, its edge on all its events (`demotion_v2.py` on `calib_v2.py`'s
day shapes; seeds from 124,000,001; `demotion_v2.json` / `.out`): real money buys the top min(n_s, 14) events at
Probe (A99, the mean at-size lot $67.9) and the top min(n_s, 8) at Sized ($190 lots, conservative), the stay moves to
Sized by section 3's rule (its control and issuer guards taken as holding: more Sized, larger lots), and the stay is
demoted at the first of the three triggers in section 3's order: the fixed reads at p <= 0.15, the money stop at 10%
of the whole stay's buy cost, the stay's lower tail at the chosen schedule's alpha(S). A true edge with counts that
follow the day earns its edge on what money buys (the knife of calib_v2 plus the edge). All cells at rho_day 0.15,
phi_day 0.20 and a 20 bp drift unless named. P(demoted by the stay's 300th / 1,000th / 2,000th / 3,000th Probe+
event), "+" where 60-99% of stays reach that event within the sessions simulated (the figure is then a lower bound),
"-" where fewer do:

| stay, cell | events a session | 300 / 1,000 / 2,000 / 3,000 | at the 1,000th: reads / money stop / lower tail |
|---|---|---|---|
| 60 bp, crash days with a normal body, symmetric events | 85 / 30 / 13 | .095 / .111 / .113 / .113; .092 / .109 / .112 / .112; .083 / .098 / .100 / .100+ | .104 / .007 / .000 at 85 |
| 60 bp, crash days with a normal body, skewed events (the old corner) | 85 | .089 / .107 / .111 / .111 | .102 / .005 / .000 |
| 60 bp, t(3)-body crash days, symmetric / skewed events | 85 | .082 / .098 / .101 / .102; .083 / .104 / .105 / .105 | .094 / .004 / .000; .096 / .008 / .000 |
| 60 bp, clustered crash days, symmetric events | 85 / 30 / 13 | .083 / .102 / .104 / .104; .077 / .093 / .096 / .096; .089 / .107 / .110 / .110+ | .093 / .009 / .000 at 85 |
| 60 bp, clustered crash days, skewed events | 85 | .077 / .094 / .096 / .096 | .087 / .007 / .000 |
| 60 bp, t(3)-body clustered crash days, symmetric events | 85 / 30 / 13 | .074 / .095 / .098 / .098; .080 / .092 / .094 / .094; .070 / .080 / .082 / .082+ | .088 / .007 / .000 at 85 |
| same, skewed events | 85 / 30 / 13 | .083 / .095 / .097 / .097; .073 / .087 / .090 / .090; .071 / .082 / .083 / .083+ | .087 / .007 / .000 at 85 |
| same, symmetric / skewed events | 8 | .077 / .088 / .088 / .088+; .071 / .080 / .081 / .081+ | .078 / .011 / .000; .068 / .012 / .000 |
| same, symmetric / skewed events | 3 | .059 / .066 / - / -; .065 / .068 / - / - | .042 / .018 / .005; .043 / .023 / .003 |
| same, counts that follow the day, symmetric / skewed events | 8 / 3 | .051 / .058 and .037 / .037; .051 / .058 and .037 / .038 by the 300th / 1,000th | |
| 60 bp, base (symmetric, rho_day .05, no drift) | 85 / 13 | .038 / .041 / .041 / -; .042 / .043 / .043 / - | |
| 60 bp, rho_day 0 | 85 / 13 | .021 / .023 / .023 / -; .021 / .023 / .023 / - | |
| 100 bp, t(3)-body clustered crash days, symmetric events | 85 / 13 | .034 / .037 / .037 / -; .032 / .034 / .034 / - | |
| STRESS 60 bp, phi_day .25, t(3)-body clustered crash days | 85 / 13 | .087 / .109 / .112 / -; .092 / .107 / .110 / - | |
| STRESS 60 bp, rho_day .30, phi_day .10, crash days, skewed events | 85 / 13 | .105 / .136 / .141 / .141+; .097 / .120 / .125 / - | |
| no edge (the knife edge): t(3)-body clustered crash days / the old corner / base | 85 | .265 / .409 / .482 / .514+; .264 / .402 / .481 / .509+; .244 / .386 / .437 / .462 | |
| cost only (-15 bp), base | 85 / 13 | .359 / .570 / .674 / .734; .379 / .552 / .661 / .723+ | |

- THE STOP AND THE READS: on 2,000 stays a cell at the new corners (t(3)-body clustered crash days, symmetric /
  skewed events, 85 a session; seeds from 125,000,001 and 125,500,001), with no money stop the rate by the 1,000th /
  3,000th Probe+ event is .083 / .088 and .094 / .095 (`demotion_v2_nostop.json`), against .095 / .098 and .095 / .097
  with it (each variant on its own seeds, so differences under about 0.015 are noise); with the reads at 0.20 instead,
  .133 / .136 and .127 / .130 (`demotion_v2_read20.json`). THE 10% LEVEL was chosen by the previous round's
  calibration of the stop over the last 50 events, on the same seeds that measured it (`demotion_stop.json`, seeds
  from 118,000,001: with reads at 0.20, .129 / .142 / .137 at 10% of the summed cost against .573 / .544 / .509 at
  PREREG-EVL-3's $150 by the 1,000th event at 85 / 30 / 13 a session); D10 applies it to the whole stay, and the table
  above measures that form on seeds that chose nothing.
- A FALSE PASS'S STAY (PREREG-EVL-4 section 3's cost of a false pass, restated): a program with no edge that passed
  holds about 725-740 Probe+ events of its first 1,000 before a demotion or the horizon (its realized P&L near zero:
  +$56 to +$75 over the stay, its r carrying the benchmark's 4 bp), a cost-only one (-15 bp) about 615-620 (about
  -$90); PREREG-EVL-4 assumed a stay of about 100 events. The dollars stay far inside the $400 / $800 loss budget; the
  cost is Done's dilution, which Done's issuer-block bound prices.

## 5. False positives per program and for the lane

- PER RUN, the unit the goal's 15% is read in (D11; any rate, any family, READ or not; a run that starts three sessions
  later, as the twelve restarted programs' do, is the same test on a later stretch of the same stationary paths): 0.129
  at the worst plausible cell on the selection seeds that chose the rule, at most 0.131 on fresh seeds that never chose
  it (0.1308 and 0.1305 +- 0.0053 at two cells, above 0.13 by less than a sixth of their standard error; 0.1293 and
  0.1298 +- 0.0038 pooled over 8,000), 0.013-0.025 at the base model, at most 0.069 with no reading skill. THE GENERATOR
  IT HOLDS FOR: section 4.2's, over section 4.3's widened grid: crash days with a normal or a t(3) body, clustered in
  high-volatility regimes or not, symmetric or left-skewed events, a drift of up to 20 bp at AR 0.97, rho_day <= 0.15,
  phi_day <= 0.20, counts independent of the day or following its size at 3-8 events a session. At or under 0.13 at
  every plausible cell on the selection seeds; above 0.12 only with t(3)-body clustered crash days and skewed events at
  rho_day 0.15. MEASURED DEPARTURES ABOVE IT (section 4.4): day momentum AR 0.40 at rho_day 0.30, up to 0.161; a 30 bp
  drift with crash days and skewed events at rho_day 0, 0.148; phi_day 0.25 with t(3)-body clustered crash days, 0.147
  at 85 a session and 0.131 with counts that follow the day at 3. One path only: no union.
- PER VERSION (D16; re-check 1's text): the goal's 15% is read PER TEST, that is per run. A version that never passes
  is re-tested every 60 blocks (each fresh run when the budget holds it, section 3), so its chance of ever passing
  falsely grows with each run: 0.24 within 120 sessions at the worst plausible cell (0.2400 on the selection and the
  fresh seeds; 0.20-0.24 at every cell of section 4.3's step 5), about 1 - 0.87^n after n runs. Each run is charged
  0.13. In PREREG-EVL-3 a version had one finite sequence of ten looks, so its rate per test was its rate per version;
  here it is not. This reading is the captain's (D11) and the owner may overrule it; the registering amendment carries
  the same sentence.
- RE-PROMOTION AND SIZED: each fresh run, after an end or a demotion, is another test at the same rate, charged when it
  starts and started only when the budget holds it (section 3). Sized needs a false Probe and then a false stay test;
  a persistent drift correlates the two, so a false Sized is bounded by a false Probe and charged nothing more.
- THE LANE'S COUNT (D6): 0.13 expected false passes (the recalibrated worst plausible per-run rate, 0.129 on the
  selection seeds and 0.130 pooled with the fresh ones, rounded up to two decimals) for every seatable version this
  file registers or judges (its run 1) and for every fresh run when it starts; 0 for a superseded version (none can
  make a look that moves a band after REGISTERED_AT_6, and none has held one: section 1.1). A FRESH RUN is a version's
  run n >= 2; run 1 is charged with its version, never twice.
- THE LANE'S LIFETIME BUDGET, RESTATED: 3.9 expected false passes, 30 x 0.13. This is a RELAXATION of PREREG-EVL-4
  section 3's 3.0 (thirty seatable versions at 0.10) by 0.9, 30% in the budget's own unit, which the captain accepts by
  amendment (D6, A107). The reason: the same thirty seats, re-measured on a harsher generator. PREREG-EVL-4's 0.10 a
  version came from PREREG-EVL-3's own 0.4% day-shock model, under which that screen measured 5-8.4%; on this file's
  generator the same screen reads 14.3-15.2% on the judge's grid and more on the widened one (section 4.4), so the
  thirty seats the budget priced were never 3.0 on this basis. At the base model the same thirty expect about 0.75.
- A TRUE LIFETIME BOUND (D11): every charge, a version's registration or a fresh run's start, is made only when the
  budget holds it, so the lane's expected false passes never exceed 3.9: at most thirty charges in the lane's life.
  R3's validator and the House's start of a fresh run count versions and fresh runs together; a birth registers only
  when the room left after every waiting run holds it (section 3).
- USED AT REGISTRATION: the fifteen new versions, 15 x 0.13 = 1.95, plus 0.13 for each seatable birth registered
  before REGISTERED_AT_6 (its version 2). LEFT: 1.95 less those births, fifteen charges at most, at most three seatable
  births a night (A81).
- WHAT D2 COSTS THE BUDGET, stated: a version whose run reaches its 60th block unpassed waits for a fresh run charged
  0.13. More than half the first runs of a real 60 bp edge end that way (0.559, section 4.5), and most of a zero-edge
  program's do. If none of the fifteen passes, their second runs (from about the 60th session after REGISTERED_AT_6 at
  5 or more events a session, later at fewer) would cost 15 x 0.13 = 1.95, the whole remainder: they start in
  registration order while the room holds them, then no birth registers and no further run starts. A version whose
  run ends with no room left stays in learning at learning size, untested, until the captain restates the budget by
  amendment.
- EVERY REPORT shows the lane's expected false passes three ways: this file's count (0.13 a version or run), the base
  model (0.03: 0.025 rounded up) and the stresses' worst (0.17: 0.161 rounded up); and beside them the per-version
  figure (0.24 within 120 sessions at the worst plausible cell).

## 6. What is unchanged, and the new versions' Probe band (A99)

- A99'S CLAUSES (D5; the done-speed synthesis of wf_15782c13-759, designed blind, its A97 (1)-(4)), for this file's
  versions and every seatable version registered at or after REGISTERED_AT_6 (R3's births from then on included,
  judged by this file under section 1.1's LATER VERSIONS; A100's row reads the version's registration time; D13):
  1. SLOTS: Probe is PREREG-EVL-1 section 8's envelope of 5% with the money table's 3.5% since A86 revised, AT MOST 14
     OPEN for this file's versions and every seatable version registered at or after REGISTERED_AT_6 (PREREG-EVL-1
     section 8 had 6; every version registered before REGISTERED_AT_6 keeps its frozen 6, and a superseded version
     never moves a band again).
  2. AT-SIZE BUYS: a Probe or Sized buy takes the fewest whole shares whose value at the limit reaches 0.8 of its band's
     target (Done's bar, `done.PROBE_SIZE_SHARE`). It is never above 5% of equity at Probe, nor above the name's 10%
     wall at Sized, and that ask is judged again by every cap: the name wall, the 100% book, cash, the loss budget at
     the lot's weight and A85's reservation. A pick that no such count reaches is skipped before it takes a slot; the
     shadow keeps it. The recorded target stays the band's share x E. The shares bought never exceed floor(5% E / limit)
     at Probe, PREREG-EVL-1 section 8's own count.
  3. ROOM: a promoted birth takes its band's ROOM tier after the band's PREREG rows and before every learning row,
     with A85's reservation (A101); a birth at learning stays after every PREREG row.
  4. LATER FILES: the same holds for every later file's seatable programs (PREREG-EVL-7's and -8's included) unless
     that file states otherwise.
- Everything this file does not state is PREREG-EVL-1's to -5's and R3's, word for word: the universe, the events, the
  knowable times, backfill and the shadow rule; the verdicts, their model, prompts (PROMPT-DOC and PROMPT-NEWS and their
  SHA-256), parsing and the rule that the first stored answer is final; the execution model, auction prices, the
  fallback ladder, costs, per-event returns and TRADABLE; every program's rule, record and control; the band SIZES
  (learning: a target of 2% of equity, whole shares, one share up to 5%, at most 8 open; Probe as clause 1; Sized: 10%,
  at most 8 open, with clause 2); ROOM's order (Sized, then Probe, then learning; the tables' order; each program's
  ranking; clause 3 for births), the sale gate, A85's cash reservation and every real-money guard; the money walls (<=
  10% of equity a name, <= 100% invested, no margin, no shorts), the loss budget ($400 net in any 20 sessions, $800 net
  total, realized plus open risk), the open-risk rule, the kill switch and the stops; pivot and reporting.
- DONE is read by the current Done reader, `league/events/done.py` (its rule file pinned there by sha256), not restated
  here; this file changes nothing in it.
- A superseded version's record and its PREREG-EVL-3 looks continue as a shadow record, reported beside.

## 7. What is not decided here

The code, the site and the docs, built after this file to these rules: release 1019h's money rows
`event.max_open_v6.probe` 14 (bound 0-14, read only for versions registered at or after REGISTERED_AT_6;
`event.max_open.probe` stays 6 with its bound) and `event.reach_bar.probe` / `.sized` 0.8 (bounds 0-0.8) with their code
(A100: book.Settings, live._size_event's round-up, the 'under_bar' skip); D7's guard (bands.on_look moves no band for a
version this file supersedes, from REGISTERED_AT_6) in release 1019h before the Oct 28 close; and the screen
(league/events/screen.py's judge of this file: the weighted values, the top-14 guard, the schedule and alpha, runs and
stays and their tags, q, looks keyed by their tag), bands.py's moves (no retirement at a run's end; the fixed reads at
0.15; the money stop over the whole stay, in section 3's order), programs.py's rows, the copied record of section 1.1
(D8) and its issuer rule with section 1.1's test (D12), births.py's superseding versions, run.py's and house.py's
decisions of the new rows, the lane's expected-false-pass count with every fresh run (section 5), the House's start of a
fresh run only when the budget holds it, in registration order (D11), R3's validator counting versions and fresh runs
together, and the report. If an implementation finds a rule here ambiguous, it takes the reading LESS LIKELY TO PASS
(screen rules) or that trades less (trading rules), fixed before the new versions' first look and recorded as an
amendment; a later resolution is a new version.

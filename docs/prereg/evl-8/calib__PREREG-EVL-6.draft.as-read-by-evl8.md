# PREREG-EVL-6: one session-block screen for every seat, looked at in settled blocks from the 6th

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6e6a85b9) under the owner's goal as he re-set it at 05:15Z
Mon Oct 19, 2026 (`goal-2026-10-19/GOAL-MESSAGE-V2.txt`): "No deadlines, no waiting periods: speed is settled events and
iterations, never calendar time ... Promotion to Probe and Sized, demotion and retirement are pre-registered sequential
tests counted in settled events, never days, at a false-positive rate <= 15% by issuer-block permutation." Written
WRITTEN_AT. The captain's A91 (21:12Z Oct 21) opened this design before any design result existed. Three independent
designers wrote three tests (a control-relative within-session permutation beside a session-block absolute test; an
anytime-valid betting e-process; a universe-referenced stratified sign-flip), three calibrators measured each by Monte
Carlo on synthetic correlated returns, and a judge re-measured all three, and PREREG-EVL-3's own screen, on ONE
generator that holds every risk any of them had found (section 4), searched 2,457 candidate rules on it, chose, and
wrote this file; two adversarial checks read it (workflow wf_560ee5dd-ef8). Each worked under the rule that no price
after any event, and no return, P&L, look, band or mark of the lane, is read, queried or computed; none was. The
registering captain session (6e6a85b9) had read, on Oct 21, the per-program means of the shadow record of the lane's
programs over its first two entry sessions (Oct 19-20) and the lane's aggregate real-money figures; it took no part in
designing, calibrating or choosing these rules, and for that reason this file judges ONLY events knowable after its own
registration time.

REGISTRATION TIME: the latest of three times, all recorded in the captain's amendment that pins it as
`REGISTERED_AT_6` (A92's method): this file's commit time; the pushing client's own clock read after the push of the tag
`prereg-evl-6` returns; and GitHub's activity time for the push of the branch `prereg/evl-6`. The tag never moves. A
version this file registers counts only events knowable after REGISTERED_AT_6. Nothing here changes for a registered
program: a change is a new version with its own registration time.

## 0. The judge's finding that shaped this file

- A91 asked for a second promotion path BESIDE PREREG-EVL-3's screen, with both paths' false-positive rate accounted.
  Measured on the common generator (section 4), PREREG-EVL-3's screen ALONE, exactly as registered (its skew check and
  its retirement rule included), passes a program with no edge 15.2% (+-0.8) of the time within 120 sessions at the
  worst plausible cell (crash days, a 20 bp persistent drift, rho_day 0.15, 30 events a session) and up to 6.7% at the
  base cell; its 5-8.4% calibration (PREREG-EVL-1 and -3) used a 0.4% t(4) day shock, no persistent drift and no
  crash days. A second path only adds to that: beside this file's screen the union reaches 19.9% at the worst
  plausible cell and 8.8% at the base. No second path can hold a program to the owner's 15%.
- So this file does what PREREG-EVL-3 did to PREREG-EVL-1's programs: it registers a NEW VERSION of every seatable
  program, judged by this file's screen ALONE (section 1.1). The version it supersedes stays a shadow record: its
  PREREG-EVL-3 looks are still computed and written by today's code path, unchanged, and reported beside, and they
  never move a band again. No superseded version has held a look (PREREG-EVL-3's first look needs 8 session blocks: the
  Oct 28 close at the earliest), so none has spent any false-positive probability, and the lane's count drops them as
  PREREG-EVL-3 dropped version 1 (section 5).
- What this buys, on the same synthetic paths (section 4): a worst plausible false-positive rate of 13.1% against
  PREREG-EVL-3's 15.2%, a base rate of 4.3-5.0% against 3.9-6.7%, a first possible promotion at the 6th settled block
  against the 8th (and at 30 events, not 60), and more promotions of real edges by the 20th session at every event
  rate (at a 100 bp edge and 8 events a session 51% against 45%; at 3 a session 32% against 12%). What it costs: the
  twelve programs of PREREG-EVL-3 and -4 restart their count at REGISTERED_AT_6, three sessions after theirs began
  (A91: no event the captain could have seen is judged by a new test); and after about the 30th session it promotes a
  60 bp edge at 8-30 events a session less often than PREREG-EVL-3 (it spends little alpha late, where a persistent
  drift manufactures false passes). Its faster parts after promotion are Sized and demotion (section 3): Sized from a
  fresh test of the Probe stay's own blocks instead of 150 real events, and a fixed-count demotion read that demotes a
  real 60 bp edge 13-16% of the time where PREREG-EVL-3's rolling rule demotes it 31-83%.

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
  (the sale gate; PREREG-EVL-4 section 1.3; PREREG-EVL-5 section 1.3). It differs in exactly two things: its
  registration time is REGISTERED_AT_6 (it counts only events knowable after it), and its promotion, Sized, demotion
  and retirement are this file's (sections 1-3), in place of PREREG-EVL-3 sections 2 (its moves; its sizes stay) and 3.
- LATER VERSIONS. Every seatable version registered after REGISTERED_AT_6 (R3's births from then on, and every later
  file's seatable programs unless that file registers another screen) is judged by sections 1-3 alone, from its own
  registration time.
- NEVER CHOSEN PER PROGRAM. The screen, its constants and its seeds are the same for every version; nothing in them
  depends on a program's id, family, rate, early figures or band.
- SUPERSESSION IN MONEY. A superseded version keeps trading at learning size until the House release that carries this
  file is live; from then its new version holds the seat and the superseded version is a record (its open lots exit by
  their rules). That release must be live before the first close at which any superseded version's first PREREG-EVL-3
  look can be held (the Oct 28 close for the nine). If it is not, every PREREG-EVL-3 look held before the release
  stands with the move it made and is charged (section 5), the captain's amendment records it, and at the release the
  superseded version stops seating whatever its band and its new version starts at learning. Until the release, the
  new versions are decided in shadow only, by the same rules, for every event after REGISTERED_AT_6.

### 1.2 The record, the blocks and the values

- A version's RECORD at a look as of the close X: its settled events (outcomes `status = 'settled'`) whose knowable time
  is after its registration time and whose scheduled exit is at or before X (PREREG-EVL-1 section 7's covered blocks);
  for each: entry session D, issuer (CIK, else symbol), a, r and TRADABLE (PREREG-EVL-1 section 5; an event whose
  tradability is unknown is not TRADABLE). Only TRADABLE events enter any figure below.
- BLOCKS: every entry session holding at least one TRADABLE event of the record is one block (every seatable version
  holds one session, so blocks never overlap; a session with no event adds no block, so the count is of settled events
  grouped by their session, never of days); block s = 1, 2, ..., S in session order; its value B_s is the mean a of its
  TRADABLE events (`math.fsum`).
- THE MARGIN: x_s = B_s - 0.0010. The money null this screen rejects is "the program's mean after-cost abnormal return
  is at most 10 bp an event, session by session", not "at most 0": a persistent drift of the event basket against its
  benchmark for weeks (section 4.3) must exceed 10 bp a session to pass for an edge.

### 1.3 The statistics

- p, the screen's p: the one-sided sign-flip p of mean(x) > 0, ties counted against the program:
  - S <= 16, EXACT over all 2^S sign vectors: p = #{b in 0 .. 2^S - 1 : sum_j s_bj x_j >= sum_j x_j - S x 1e-12} /
    2^S, with s_bj = +1 when bit j of the integer b is set (bit 0 is block 1), else -1 (screen.py `_count` over
    `b.to_bytes(width, "little")` for every b counts exactly these vectors with today's 8-bit tables).
  - S >= 17, Monte Carlo as PREREG-EVL-1 section 7: p = (1 + #{v : sum_j s_vj x_j >= sum_j x_j - S x 1e-12}) /
    (1 + 99,999) over 99,999 vectors `random.Random(seed).getrandbits(S)` (bit j set = +1 for value j), seed =
    int.from_bytes(sha256(seed string).digest()[:8], "big"), seed string f"{id}|v{version}|evl6|{run}S{S}" ({run} is ""
    for the version's first run, "run{n}|" for its n-th run, "stay{n}|" for its n-th Probe stay: section 3).
- q, the lower tail (retirement and the stay's demotion): the same p computed on the values -B_s (no margin), over the
  same vectors (the same exact count, or the same seed string).
- p_I, the issuer-block p (the goal's issuer-block permutation): PREREG-EVL-1 section 7's issuer-block sign-flip p of
  the record's TRADABLE events (each issuer's events averaged into one value, values in ascending issuer order, no
  margin), 99,999 vectors, seed string f"{id}|v{version}|evl6|{run}S{S}|issuer".
- alpha(S) = 0.016 for S <= 20 and 0.004 for S >= 21 (at S = 6 a pass needs all six blocks above the margin:
  2^-6 = 0.015625 <= 0.016).
- Every sum is a `math.fsum`; every comparison carries the 1e-12 tolerance in the program's disfavour.

### 1.4 RETIRE, PASS, and the move a look makes

- At every look of a RUN (section 3; a Probe stay's looks act as section 3 says), in this order:
  1. RETIRE when the record's mean a < 0 and q <= alpha(S) + 1e-12: the version goes to `retired` (no more real money;
     the shadow continues as a record; a new version is the only way back). Nothing else is checked at that look.
  2. PASS when ALL hold: p <= alpha(S) + 1e-12; the record has >= 30 TRADABLE events and >= 30 distinct issuers; its
     mean a > 0 and its mean r > 0 (a long-only program must make money after cost, beside its benchmark and in raw
     terms); for a READ version (one with a control: screen.CONTROLS, or a READ birth's derived control), its mean block
     value exceeds its control's over the same sessions (PREREG-EVL-1 section 7's rule; the control's TRADABLE events
     of those sessions whose knowable time is after the version's registration time); and p_I <= 0.10.
- A PASS moves a `learning` version to `probe` from the first decision after the look is written (PREREG-EVL-3 section
  2's PROBE, its sizes unchanged); in any other band it moves nothing. The move is written in the look's own transaction
  (screen.write_look's `apply`), so a look on record has always made its move.
- Written with every look: p, alpha, q, p_I, the guards, the counts, and PREREG-EVL-1 section 7's figures beside (the
  all-event figures, the raw-r test, the half-spread stress, the market-direction share, the control's figures, the
  late-verdict share).

## 2. Looks and minimums, counted in independent units

- THE UNIT is the session block. A day-level residual shock common to every event of a session (news days; factor days:
  momentum, value, size, sector rotations; beta mismatch to SPY or IWM) makes one session's events one draw; sessions
  are the independent units of that shock, and a sign-flip over session blocks holds its level whatever the shock's
  size, its loading across names, or the sector clustering and issuer repeats inside a session (Fisher 1935; Lehmann
  and Romano, Testing Statistical Hypotheses, 4th ed., ch. 17; Canay, Romano and Shaikh 2017, Econometrica 85(3)).
  Issuers are the independent units of the idiosyncratic noise: p_I and the 30-issuer minimum use them. An issuer-block
  test ALONE cannot carry the false-positive rate here: with a day-shock share rho of event variance and m events a
  session it understates the variance by 1 + rho (m - 1) (5.2 at rho 0.05 and 85 a session).
- LOOKS: look k (k = 1 .. 20) is at the first session close X at which the record (covered at X) holds at least S_k
  blocks AND the minimums hold, with S_k = 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60.
  Looks happen in order, at most one at a close; every S_k reached by the close of a look is consumed by that look
  (thresholds reached together are one look, the lowest k; the others are recorded as merged into it); its alpha is
  alpha(S) at the record's own S. No other look exists.
- MINIMUMS at a look: 6 blocks (the fewest at which a sign-flip p can reach the threshold; fewer independent sessions
  can certify a mean only by assuming the size and shape of the day shock, Bahadur and Savage 1956, Ann. Math. Statist.
  27), 30 TRADABLE events and 30 distinct issuers (no issuer more than 1/30 of the issuer-block statistic). None is a
  calendar wait: at 5 or more events a session every minimum holds at about the 6th block, at 3 a session at the
  10th, at 1.3 a session at about the 23rd.
- THE HORIZON is the 60th block. At the close at which the record's 60th block is covered, a version still in
  `learning` whose run has not passed is retired (EXHAUSTED: section 3), whether or not its minimums ever held. The
  exhaustion is decided with that close's look (after its RETIRE and PASS), or, when no look is held there, once that
  close is final, and written in the same kind of transaction.
- FINALITY AND FREEZING (today's machinery, unchanged): a look as of the close X is computed once X is final for the
  version (screen.final_until: A66, A69, A84's per-feed fast path, and each file's own windows) and every intent of the
  version and of its control scheduled to exit by X has settled; it is written once (INSERT OR IGNORE) and never
  recomputed from a record that grew later; once written it freezes its group's records over the sessions it covers
  (run.py `_scope`, as every look); late data delays a look, never its as-of close.
- OPTIONAL STOPPING is inside the calibration: every look the schedule can make, to the 60th block, is in the measured
  false-positive rate (section 4); a deferred or merged look only removes a chance to pass.

## 3. Sized, demotion, re-promotion and retirement (the same framework)

- RUNS AND STAYS. A version's first RUN is its record from its registration time. A Probe STAY n begins at its n-th move
  to `probe` (bands.probe_since); its STAY RECORD is the version's settled TRADABLE events entering after that move.
  After the n-th demotion, RUN n + 1 is the record entering after the demotion. Every run and stay is tested by
  sections 1.2-2 on its own record, its looks counted from its own first block, with its own seed strings (section
  1.3). A run's looks end at its PASS, its RETIRE or its exhaustion; a stay's looks last while the stay does, to its
  own 60th block (after that only the money stop and the fixed reads below apply to it).
- SIZED (`probe` -> `sized`: PREREG-EVL-1 section 8's size, a target of 10% of equity a position, at most 8 open), at
  the first stay look at which ALL hold: the stay record PASSes section 1.4 (p <= alpha(S), the minimums, the money
  condition, the control, p_I); the stay holds >= 30 settled real-money events bought at Probe size with realized
  after-fee P&L > 0 (bands.real_events); and the signed mean gap per side between those fills and the shadow auction
  prices is within 15 bp (Done's fill rule). PREREG-EVL-3's 150-event bootstrap route does not apply to this file's
  versions.
- DEMOTION (`probe` or `sized` -> `learning`), at the first of:
  1. THE MONEY STOP (PREREG-EVL-3 section 2, unchanged): the stay's last 50 settled real-money events at Probe size or
     above lost more than $150 net;
  2. THE STAY'S LOWER TAIL: at a stay look, the stay record's mean a < 0 and its q <= alpha(S) + 1e-12;
  3. THE STAY'S FIXED READS: at the stay's 100th, 200th, 300th ... settled real-money event at Probe size or above, the
     mean after-cost r of those events is below zero. It replaces PREREG-EVL-3's rolling "last 100 negative mean" for
     this file's versions: with t(3) event noise of 5.3%, a 1% market day and 6 Probe events a session, the rolling
     rule demotes a real 60 bp edge 31% of the time within 150 Probe events, 62% within 300 and 83% within 500; the
     fixed reads 13%, 15% and 16%, and a zero-edge program 47%, 65% and 72% (`judge/demotion_check.py`, 20,000
     synthetic paths, seed 1).
- RE-PROMOTION after a demotion: RUN n + 1's PASS (a fresh test on the record after the demotion). Each fresh run is a
  new chance of a false pass and is counted in the lane's expected false passes when it starts (section 5).
- RETIREMENT (any band -> `retired`, for good; the shadow continues as a record), at the first of:
  1. section 1.4's RETIRE at a look of the current run;
  2. EXHAUSTION: the current run's 60th block is covered while the version is in `learning` and the run has not passed.
- PREREG-EVL-3 section 2's retirement (a held look with the reversed p <= 0.05), its Sized rule and its rolling
  demotion do not apply to this file's versions; its band SIZES, ROOM and the open-risk weight do.

## 4. The calibration record (synthetic only)

### 4.1 Files

- `goal-2026-10-19/evl6/judge/calib_judge.py` (the generator, PREREG-EVL-3's screen as registered, and every
  candidate's raw per-session arrays), `judge/run_all.sh` (seeds from 81,000,001 by phase), `judge/report_judge.py`,
  `judge/search_judge.py`, `judge/table_judge.py`, `judge/mini.py` and `judge/grid4.py` (the offline search over
  schedules, thresholds, margins, guards and retirement: 2,457 rules in `judge/search_alone_L0_main.jsonl`,
  `judge/search2_alone_L0_mainpower.jsonl`, `judge/search3_alone_L0.jsonl` and `judge/search4.jsonl`), the run logs and
  indexes (`judge/calib_judge.*.index.jsonl`, `judge/noskill.log`, `judge/power120.log`),
  `judge/chosen_rule_tables.txt` (every cell and power row for this file's rule at lag 0 and lag 3, beside
  PREREG-EVL-3's), and `judge/demotion_check.py` with its `.out`; all copied with their sha256 into docs/prereg/evl-6/ at
  the freeze. The per-cell arrays stay on disk in `judge/arrays/` (372 files; `judge/arrays/SHA256SUMS`, itself sha256
  a5eccf48...) and are reproducible from the seeds.
- The three designs' own calibrations, kept as their records: `evl6/calib_within.py` (+ .out.jsonl, .report.txt),
  `evl6/calib_evalue.py` (+ .out / .extra / .life / .fix jsonl, .report.txt), `evl6/calib_strata.py` (+ _out.json,
  _report.txt, _adjust.txt).

### 4.2 The generator

One generator for every rule compared (numpy, seeded, vectorized over programs). It holds at once every risk the three
calibrators found, each missed by at least one of them: calib_within.py had crash days and factor momentum but no
persistent drift; calib_evalue.py had the persistent drift but no crash days or momentum; calib_strata.py had day-shock
momentum up to AR 0.40.
- Issuers: 3,000 in 11 sectors (weights .22 .14 .12 .11 .09 .08 .07 .06 .04 .04 .03), Zipf(0.8) popularity (the same
  names recur); sigma_i log-uniform from 1% to 10% a session; three style factors (momentum-, value- and size-like)
  with loadings N((.2, -.1, .2), .5^2); one position per issuer per program with the 5-session cooldown; on half the
  sessions one hot sector draws four times its weight (sector clustering of news days).
- Events: the control holds Poisson(nbar / 0.30 x Gamma(3, 1/3)) events a session (count CV 0.58); the program holds
  each control event with probability 0.30 (its events a subset of its control's, same sessions, same window); nbar =
  85, 30, 13, 8 and 3 program events a session.
- Per event: a = mu_family + D_t + h_t (c_t + s_sector,t + beta_i . f_t + sigma_i e_it) + jump + skill x [the
  program's], floored at -100%; r = a + b_t with b_t ~ N(4 bp, 1%).
  - c_t, the residual DAY shock common to every event of the session: sd_c z_t, z_t = 0.10 z_(t-1) + sqrt(1 - 0.10^2)
    eps_t (factor momentum, in every cell), eps_t of unit variance: symmetric t(3), or CRASH DAYS (5% of sessions
    N(-3, 1), the rest N(m, s): skew -1.6); sd_c^2 = rho_day / (1 - rho_day) x V0, V0 = 0.0027 (event sd 5.2%), so
    rho_day 0, 0.05, 0.15, 0.30 gives sd_c 0, 1.2%, 2.2%, 3.4% a session.
  - s: 11 sector shocks, sd 1.0%, t(3); f: the style factors' day returns, sd 0.6%, t(3); e_it unit t(3), or LEFT
    SKEWED (two-piece t(3), scales 1.4 / 0.6); +-30% jumps at 0.5% an event, half down, or 80% down in the skewed
    shapes, mean-compensated so the null mean is exact; h_t a volatility regime exp(x_t - .09), x AR(0.9), sd 0.3.
  - D_t, a PERSISTENT FAMILY DRIFT shared by the program and its control: AR(1) at 0.97 (half-life 23 sessions) with
    stationary sd 0, 10 or 20 bp a session. Its long-run variance is 66 times its one-session variance: at 85 events a
    session a 20 bp drift has a long-run variance about eight times the block noise's, the risk that breaks any test
    that treats sessions as independent over a long horizon.
- NULLS: N3, THE KNIFE EDGE (skill 60 bp, mu_family -60 bp): the program's mean a is exactly zero while it beats its
  control by 42 bp, so the control condition never protects; it is also exactly the null of a program WITHOUT a
  control (REACT, INS-BUY and their births), so every N3 figure is also the no-control figure. N1 (no reading skill:
  the program a random 30% of its family, mean zero). N2+ (no skill, +30 bp common drift: a false "beats its control",
  not an owner false positive, its mean a being positive).
- Every rule is judged on the same paths: PREREG-EVL-3's screen exactly as registered (looks at 60 ... 2,250 TRADABLE
  events with >= 40 issuers and >= 8 blocks; the session-block and issuer-block p each at most its skew-checked alpha
  from 0.018; mean a > 0; mean r > 0; beats its control; its retirement rule) and every candidate at LAG 0 (a birth, or
  PREREG-EVL-5's three: both start together) and LAG 3 (the nine and PREREG-EVL-4's three: this file's record starts
  three sessions after theirs). Monte Carlo shortcuts, each leaving a rule's level unchanged: for S >= 17 the sign
  vectors are 19,999 fixed vectors carried across looks (each look's p a valid Monte Carlo p; the rule draws a fresh
  seed per S); the issuer guard uses 999 vectors and PREREG-EVL-3's issuer test 4,999; a p is computed only where z =
  sum x / sqrt(sum x^2) >= 1.0 (checked: no decision at any alpha up to 0.03 changes on full computation).
- Counts: 2,000 programs a knife-edge cell and 1,000 a no-skill cell over 120 sessions (SE <= 0.008 at 15%); 1,000 a
  power cell over 60 sessions, and over 120 for 13, 8 and 3 events a session. 372 cells in all.

### 4.3 The worst plausible set, and why

- THE PLAUSIBLE GRID, every combination of: rho_day 0, 0.05, 0.15; symmetric days or crash days; symmetric or
  left-skewed events; persistent drift 0, 10 or 20 bp (AR 0.97); factor momentum AR 0.10 always; 85, 30, 13, 8 or 3
  events a session; the knife-edge and no-skill nulls; persistent issuer effects of 1%. The WORST PLAUSIBLE figure is
  the maximum over that whole grid, its corner included (crash days AND left-skewed events AND a 20 bp drift AND
  rho_day 0.15 AND momentum, all at once).
- WHY rho_day 0.15 is the ceiling: c_t is the whole event basket's session return beyond its own benchmark. At 0.15 it
  is 2.2% a session, about 10% a month of tracking error against SPY or IWM for a basket that changes every session,
  with crash days at -6.6%: beyond what diversified small- and mid-cap baskets show against IWM, whose own session sd
  is about 1.5%. 0.30 (3.4% a session, crash days at -10% about once a month) is a stress, reported, not the
  calibration point.
- WHY 20 bp: a 20 bp-a-session drift at AR 0.97 is about +-4% a month of abnormal return of the event basket for weeks
  at a time (a speculative, high-volatility or attention regime); the e-process calibration named it the worst
  plausible and 30 bp a stress.
- STRESSES (named, not binding): rho_day 0.30 in every shape; drift 30 bp, and 20 bp at AR 0.99; day momentum AR 0.25
  and 0.40 at rho_day 0.30; stronger crash days (3% at -4.5 sd) with 90% of jumps down at 1% an event.

### 4.4 False-positive rates

P(promotion at any look within 120 sessions) at zero edge; the maximum over 85, 30, 13, 8 and 3 events a session.

| null, shape, drift | rho_day | this file, lag 0 | lag 3 | PREREG-EVL-3 alone | the union (A91's second path, lag 3) |
|---|---|---|---|---|---|
| N3 symmetric, none | 0 / .05 / .15 | .040 / .049 / .064 | .037 / .050 / .064 | .042 / .067 / .098 | .064 / .088 / .117 |
| N3 symmetric, 10 bp | 0 / .05 / .15 | .043 / .059 / .068 | .045 / .058 / .075 | .060 / .084 / .093 | .075 / .104 / .124 |
| N3 symmetric, 20 bp | 0 / .05 / .15 | .081 / .074 / .081 | .095 / .081 / .081 | .112 / .117 / .102 | .141 / .141 / .128 |
| N3 crash days, none | 0 / .05 / .15 | .040 / .077 / .117 | .035 / .074 / .114 | .042 / .088 / .130 | .061 / .115 / .170 |
| N3 crash days, 10 bp | 0 / .05 / .15 | .049 / .079 / .111 | .048 / .080 / .112 | .059 / .100 / .127 | .077 / .131 / .174 |
| N3 crash days, 20 bp | 0 / .05 / .15 | .081 / .114 / .130 | .076 / .108 / .131 | .112 / .132 / .152 | .130 / .159 / .199 |
| N3 crash days + skewed events, none | 0 / .05 / .15 | .087 / .093 / .115 | .090 / .093 / .114 | .079 / .092 / .139 | .128 / .131 / .181 |
| N3 crash days + skewed events, 10 bp | 0 / .05 / .15 | .099 / .098 / .124 | .099 / .112 / .121 | .079 / .112 / .140 | .133 / .154 / .181 |
| N3 crash days + skewed events, 20 bp | 0 / .05 / .15 | .096 / .128 / **.131** | .102 / .124 / .130 | .128 / .141 / .148 | .155 / .171 / .194 |
| N3 skewed events, 20 bp | .15 | .099 | .097 | .117 | .147 |
| N3 symmetric, issuer effects 1% | .05 | .044 | .045 | .058 | .083 |
| N1 symmetric, none / 20 bp | 0 / .05 | .032, .049 / .086, .064 | .038, .053 / .072, .067 | .041, .075 / .105, .106 | .057, .094 / .123, .134 |
| N1 crash days + skewed events, none / 20 bp | 0 / .05 | .083, .094 / .115, .104 | .084, .110 / .122, .121 | .071, .101 / .120, .123 | .112, .147 / .175, .173 |
| STRESS: every shape and drift at rho_day .30 | .30 | .063 - .149 | .063 - .146 | .083 - .157 | .117 - .213 |
| STRESS: drift 30 bp, symmetric / crash + skewed | 0, .05 | .164, .111 / .173, .157 | .168, .114 / .169, .156 | .181, .156 / .189, .182 | .217, .175 / .212, .212 |
| STRESS: drift 20 bp at AR 0.99 | 0, .05 | .097, .081 | .093, .075 | .121, .117 | .142, .141 |
| STRESS: day momentum AR .25 / .40 | .30 | .200 / .263 | .201 / .262 | .221 / .281 | .268 / .339 |
| STRESS: crash days 3% at -4.5 sd, 90% of jumps down at 1% | .30 | .176 | .172 | .203 | .249 |

- WORST PLAUSIBLE, this file: 0.131 (crash days, left-skewed events, a 20 bp drift, rho_day 0.15, 85 events a session;
  SE 0.0075), at lag 0 and at lag 3. BASE (symmetric, rho_day 0.05, no drift): 0.043 / 0.046 / 0.049 / 0.044 / 0.043
  at 85 / 30 / 13 / 8 / 3 events a session. PREREG-EVL-3 alone: 0.152 worst plausible (crash days, 20 bp, rho_day
  0.15, 30 a session), 0.039-0.067 base.
- THE GUARDS: removing the control condition and p_I leaves the worst at 0.131 (the knife edge is the binding null);
  they cost 0.3-0.5 points of power. This file's retirement retires 5-8% of zero-edge programs within 120 sessions
  (PREREG-EVL-3's rule 12-20%) and at most 0.9% of 60 bp programs within 60.
- N2+ (no reading skill, a +30 bp common drift, mean a positive): this file passes 10-24% within 60 sessions,
  PREREG-EVL-3 9-28%: neither test can tell a drifting family's positive mean from the reading's skill, and the money
  condition is met; Done reads realized money (section 6).
- THE ALTERNATIVES, worst plausible on the same grid: WSP-IUT's absolute part (a look at every block, c / S to 120
  blocks, no margin) 0.214-0.222 at c = 0.125 and 0.185-0.188 at c = 0.09; c / S to 60 blocks with this file's margin
  and guards 0.119 at c = 0.125 and 0.091 at c = 0.09; PREREG-EVL-3's looks without its skew check 0.184; this file's
  looks at alpha 0.012 / 0.003 with the 10 bp margin 0.106; at 0.016 / 0.004 with a 15 bp margin 0.116.

### 4.5 Power and speed

P(promoted by the h-th session of its record), lag 0, a true edge on the program's events only (its control's other
events at zero); PREREG-EVL-3 alone on the same paths in brackets.

| edge, rho_day | events a session | by 8 | by 10 | by 15 | by 20 | by 40 | by 60 |
|---|---|---|---|---|---|---|---|
| 60 bp, 0.05 | 85 | .20 [.23] | .28 [.27] | .42 [.42] | .50 [.52] | .62 [.69] | .74 [.69] |
| 60 bp, 0.05 | 30 | .15 [.15] | .21 [.19] | .33 [.31] | .41 [.39] | .50 [.64] | .61 [.79] |
| 60 bp, 0.05 | 13 | .13 [.10] | .17 [.13] | .27 [.22] | .32 [.28] | .39 [.48] | .46 [.61] |
| 60 bp, 0.05 | 8 | .10 [.05] | .14 [.09] | .20 [.15] | .26 [.21] | .31 [.37] | .35 [.49] |
| 60 bp, 0.05 | 3 | .01 [.00] | .04 [.00] | .12 [.01] | .17 [.06] | .21 [.19] | .25 [.27] |
| 100 bp, 0.05 | 85 | .50 [.49] | .61 [.56] | .76 [.72] | .84 [.82] | .94 [.93] | .99 [.93] |
| 100 bp, 0.05 | 30 | .40 [.37] | .51 [.45] | .67 [.62] | .76 [.71] | .88 [.91] | .94 [.97] |
| 100 bp, 0.05 | 13 | .29 [.25] | .39 [.32] | .52 [.47] | .63 [.58] | .76 [.83] | .87 [.91] |
| 100 bp, 0.05 | 8 | .22 [.11] | .29 [.19] | .43 [.36] | .51 [.45] | .62 [.69] | .72 [.84] |
| 100 bp, 0.05 | 3 | .03 [.00] | .09 [.00] | .24 [.02] | .32 [.12] | .42 [.41] | .51 [.54] |

- AT OTHER CORRELATIONS, 60 bp, by the 10th / 20th / 40th session at 85 / 30 / 13 / 8 / 3 events a session: rho_day 0:
  .54 .32 .22 .19 .07 / .82 .58 .40 .32 .21 / .94 .70 .49 .38 .26; rho_day 0.15: .21 .15 .14 .12 .04 / .34 .28 .24 .21
  .16 / .41 .34 .29 .25 .20. At 30 bp and rho_day 0.05: .08 .08 .08 .07 .03 / .16 .15 .14 .13 .08 / .20 .18 .15 .13 .10.
- MEDIANS at 100 bp and rho_day 0.05: 9, 10, 14, 20 and 58 sessions at 85, 30, 13, 8 and 3 events a session
  (PREREG-EVL-3: 9, 12, 16, 24 and 49); at 60 bp, 20 sessions at 85 (19.5), not reached by the 60th at 13 or fewer.
- LAG 3 (the twelve programs that restart), by the 10th and 20th session of THEIR OWN count (Oct 19 = 1), 85 events a
  session, rho_day 0.05: at 60 bp .18 and .46 (PREREG-EVL-3 kept: .27 and .52); at 100 bp .39 and .78 (.56 and .82).
  That is the price of the restart and of A91's rule.
- THE PHYSICS: a session's block carries the whole day shock, so the evidence is the number of sessions, not of events.
  At rho_day 0.05 and 85 events a session a block's sd is about 1.3% and a 60 bp edge is about 0.45 sd a block: no test
  that holds its level passes it reliably in fewer than about 10-20 sessions, and a 30 bp edge is barely detectable
  within 60 sessions at any rate, by this file or any other.

### 4.6 What the seats can expect (the judge's prior, from outcome-free counts only)

Rates are the selected intents a session in `evl5/HOUSE-FACTS.json` (Oct 19-21; Oct 21 was a 2,255-article news day and
earnings season runs to about mid-November) or, for rows not yet counted there, their file's own estimate. FIRST LOOK is
the first block at which every minimum can hold; its date assumes REGISTERED_AT_6 before the Oct 22 open and a block
every session (as-of the close of Oct 29 for an open-to-close row, Oct 30 for a close-entry row: its block exits at the
next open or close); a pass moves the band from the first decision after the look is written, about one session later
under A69's fast path. P(by 10 / 20 / 40) is section 4.5's at a true 60 bp edge, rho_day 0.05, at the nearest simulated
rate (rho_day 0 and 0.15 bracket it).

| new version | events a session | first look | P(promoted by its 10th / 20th / 40th session) |
|---|---|---|---|
| EVL-NEWS-READ-O1 v3 | 54-165 (about 100) | block 6, Oct 29 | .28 / .50 / .62 (85) |
| EVL-NEWS-READ-ON v3 | 54-142 (about 80) | block 6, Oct 30 | .28 / .50 / .62 (85) |
| EVL-NEWS-REACT-ON v3 | 29-83 (about 50) | block 6, Oct 30 | between .21 / .41 / .50 (30) and .28 / .50 / .62 (85) |
| EVL-ERN-READ-O1 v3 | 18-26 (about 22, earnings season) | block 6, Oct 29 | .21 / .41 / .50 (30) to .17 / .32 / .39 (13) |
| EVL-8K-READ-ON v2 | 19-27 (PREREG-EVL-4) | block 6, Oct 30 | .21 / .41 / .50 (30) to .17 / .32 / .39 (13) |
| EVL-NEWSPM-READ-ON v2 | 20-30 (PREREG-EVL-4) | block 6, Oct 30 | .21 / .41 / .50 (30) |
| EVL-8K-READ-O1 v3 | 7-12 (about 10) | block 6, Oct 29 | .17 / .32 / .39 (13) to .14 / .26 / .31 (8) |
| EVL-ERN-GUIDE-O1 v3 | 10-11 | block 6, Oct 29 | .17 / .32 / .39 (13) to .14 / .26 / .31 (8) |
| EVL-NEWS-NIGHT2-ON v2 | 6-60 (central 12, PREREG-EVL-5) | block 6, Oct 30 | .17 / .32 / .39 (13) |
| EVL-ERN-UNDER-ON v2 | 5-14 (central 7, PREREG-EVL-5) | block 6-7, Oct 30-Nov 2 | .14 / .26 / .31 (8) |
| EVL-ERN-DROP-ON v2 | 3-13 (central 6, PREREG-EVL-5) | block 6-8 | .14 / .26 / .31 (8) |
| EVL-ERN-REACT-C1 v3, EVL-ERN-REACT-ON v3 | 4-11 (about 5-8) | block 6-8 | .14 / .26 / .31 (8) to .04 / .17 / .21 (3) |
| EVL-8K-REACT-ON v2 | 1.5-6 (PREREG-EVL-4) | block 6-20 | .04 / .17 / .21 (3) or less |
| EVL-INS-BUY-O1 v3 | 1-2 (about 1.3) | block about 23 | under .04 / .17 / .21: little power at any edge below 1% |

At a 100 bp edge the same rows read .61 / .84 / .94 (85 a session), .51 / .76 / .88 (30), .39 / .63 / .76 (13), .29 /
.51 / .62 (8) and .09 / .32 / .42 (3).

### 4.7 Why not the three designs as written, and what was taken

- WSP-IUT (the control-relative design; `evl6/calib_within.py`): its absolute part is this file's statistic with a look
  at every block and alpha = c / S to 250 blocks, no margin. Its own calibration put its worst at 0.168 at c = 0.125
  (fails) and 0.130 at c = 0.09; with the persistent drift its generator lacked, 0.214-0.222 and 0.185-0.188. Its
  within-session permutation R never carries the owner's false positive (the intersection-union bound is the absolute
  test's), cannot speed promotion past the absolute test (its designer's own finding), and is anti-conservative under
  factor-loading selection (7-33% false "beats its control"): a per-session residualization with sigma60 and SIC groups
  for no speed. A look at every block also spends alpha thinly: with this file's margin and guards, c / S rules promote
  a 60 bp edge by the 20th session 0.266 of the time on average over the five rates at a 0.119 worst and 0.219 at 0.091;
  this file's looks 0.332 at 0.131 and 0.287 at 0.106 (PREREG-EVL-3: 0.290 at 0.152).
- EVL-EPROC-1 (the e-process; `evl6/calib_evalue.py`): anytime-valid only under its own supermartingale null. A
  persistent zero-mean drift makes that null false for weeks (24.0% at a 30 bp drift and 16.3% at 20 bp, 85 events a
  session), and left skew beats its clip allowance (13.6-19.9%); its own fix, a 20 bp margin, cuts its power at 60 bp
  and 85 events a session from .77 to .52 by session 40, and its bets saturate (a 30 bp edge is barely detectable).
- SFE-SWITCH (the stratified design; `evl6/calib_strata.py`): its fast part, the hybrid sign-flip before 7 blocks
  against a fixed-effect fit on the lane's whole universe, holds its level only if the residual loading mismatch it
  cannot measure is small; its worst cell was 18.45% (day momentum AR 0.40) and 15.25% over its lifetime; the hybrid
  made 3-35% of its passes; and its reference fit (weighted least squares on every program's rows, FF12 industries,
  shrinkage, virtual blocks, two variants) is the largest implementation surface of the three.
- PREREG-EVL-3's screen kept as a second path (A91's request): section 0; the union is 0.199 at the worst plausible
  cell and 0.088 at the base.
- WHAT WAS TAKEN: the session block as the unit and the exact small-S sign-flip (WSP-IUT); the margin against a
  persistent drift (the e-process calibration's own fix); a front-loaded schedule of looks counted in settled blocks,
  with a short horizon and little alpha late (the search: front-loaded lists beat c / S, and a margin beat lower alpha,
  at every worst-case level). THE 10% TARGET IS NOT MET: the fastest rule found at a 0.10 worst plausible promotes a
  60 bp edge by the 20th session less often than PREREG-EVL-3 does (0.287 against 0.290); the owner asked for speed
  under a 15% cap, and 0.131 keeps about 2.5 standard errors under it.

## 5. False positives per program and for the lane

- PER PROGRAM (any rate, any family, READ or not, lag 0 or 3): 0.131 at the worst plausible correlation, 0.043-0.050 at
  the base model, 0.032-0.053 with no reading skill and no drift; stresses up to 0.173 (30 bp drift) and 0.263 (day
  momentum AR 0.40 at rho_day 0.30). Under 15% at every plausible cell; above 10% in the left-skewed cells (crash days,
  alone or with skewed events) at rho_day 0.05-0.15 or with a 10-20 bp drift, 13.1% at the corner. One path only: no
  union.
- RE-PROMOTION AND SIZED: each fresh run after a demotion is another test at the same rate, so a version demoted d
  times has had d + 1 tests, each counted. Sized needs a false Probe and then a false stay test; a persistent drift
  correlates the two, so a false Sized is bounded by a false Probe and charged nothing more.
- THE LANE'S COUNT, on this file's worst-plausible basis: 0.14 expected false passes (0.131 rounded up) for every
  seatable version this file registers or judges and for every fresh run when it starts; 0 for a superseded version
  that never held a PREREG-EVL-3 look; 0.16 (PREREG-EVL-3's 0.152 on the same basis, rounded up) for a superseded
  version whose PREREG-EVL-3 look was held before the release (section 1.1).
- THE LANE'S LIFETIME BUDGET, restated on the same basis: 4.2 expected false passes, PREREG-EVL-4 section 3's "thirty
  seatable versions" at 0.14 (its 3.0 was thirty at 0.10, the charge PREREG-EVL-3's own 0.4% day-shock model
  supported; on this generator that screen measures 0.152, so the same thirty seats were already about 4.6 on this
  basis). At the base model the same thirty expect about 1.5. Used at registration: the fifteen new versions, 15 x
  0.14 = 2.10, plus 0.14 for each seatable birth registered before REGISTERED_AT_6 (its version 2).
  Left: 2.10 less those births: fifteen seatable versions or fresh runs, at most three seatable births a night (A81).
  R3's validator counts versions (thirty at most), the same rule in integers.
- EVERY REPORT shows the lane's expected false passes three ways: this file's count (0.14 a version or run), the base
  model (0.05) and the stresses' worst (0.27).

## 6. What is unchanged

Everything this file does not state is PREREG-EVL-1's to -5's and R3's, word for word: the universe, the events, the
knowable times, backfill and the shadow rule; the verdicts, their model, prompts (PROMPT-DOC and PROMPT-NEWS and their
SHA-256), parsing and the rule that the first stored answer is final; the execution model, auction prices, the fallback
ladder, costs, per-event returns and TRADABLE; every program's rule, record and control; the band SIZES (learning: a
target of 2% of equity, whole shares, one share up to 5%, at most 8 open; Probe: PREREG-EVL-1 section 8's envelope of
5% with the money table's 3.5% since A86 revised, at most 6 open; Sized: 10%, at most 8 open); ROOM's order (Sized,
then Probe, then learning; the tables' order; each program's ranking), the sale gate, A85's cash reservation and every
real-money guard; the money walls (<= 10% of equity a name, <= 100% invested, no margin, no shorts), the loss budget
($400 net in any 20 sessions, $800 net total, realized plus open risk), the open-risk rule, the kill switch and the
stops; Done, pivot and reporting (PREREG-EVL-3 section 5: Done is read at every 100th settled real-money event at Probe
size or above, >= 300 such events from >= 3 programs with >= 50 each, all after their program's promotion, realized
after-fee P&L positive, the 95% issuer-block bootstrap lower bound of the per-event after-cost return above zero,
realized profit since the first promotion >= metered compute, fills within 15 bp, the last 100 with no captain step).
A superseded version's record and its PREREG-EVL-3 looks continue as a shadow record, reported beside.

## 7. What is not decided here

The code (league/events/screen.py's judge, bands.py's moves, programs.py's rows, births.py's superseding versions,
run.py's and house.py's decisions of the new rows, the report), the site and the docs, built after this file to these
rules. If an implementation finds a rule here ambiguous, it takes the reading LESS LIKELY TO PASS (screen rules) or
that trades less (trading rules), fixed before the new versions' first look and recorded as an amendment; a later
resolution is a new version.

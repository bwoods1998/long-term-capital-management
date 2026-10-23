# PREREG-EVL-8: a price-event lane (PX) and two meta-learners, real money at learning size from birth

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6e6a85b9) under the owner's goal as he re-set it at 05:15Z
Mon Oct 19, 2026 (`goal-2026-10-19/GOAL-MESSAGE-V2.txt`): "Open any other US-stock lane on Alpaca that yields more
independent events per dollar", "Every seatable program trades REAL money at learning size from its first event" and
"Promotion to Probe and Sized, demotion and retirement are pre-registered sequential tests counted in settled events,
never days, at a false-positive rate <= 15% by issuer-block permutation"; and his words of Oct 22 that opened this
design (A98): "keep pushing hard until you strike a gusher of recursive improvement in profitable trading through the
game design and agent harness". Written 03:12Z-18:43:16Z Oct 22, 2026.

HOW IT WAS MADE. The design workflow wf_1cfc229e-0d4 (script `goal-2026-10-19/workflows/gusher.js`, sha256
e4f97634b5d4be433586419f38c921d4d3547822bc1db83de9643f21ed11b55a): from 03:12Z four independent designers (a price-event
lane; meta-learners over rule families; the captain-free nightly flywheel; a red-team pre-mortem) wrote designs with
synthetic calibrations (`goal-2026-10-19/evl8/price/`, `evl8/meta/`, `evl8/flywheel/`, `evl8/redteam/`); from 04:18Z a
judge re-measured the seatable parts against PREREG-EVL-6's then draft, chose, and wrote a draft
(`evl8/PREREG-EVL-8.draft.md`, kept beside this file) and its calibration (`evl8/calib/`); from 06:00Z two adversarial
checks read it (`evl8/GUSHER-RESULT.json`, keys `check-1` and `check-2`: one blocker, eleven majors, thirteen minors,
both "fix"). PREREG-EVL-6 froze at REGISTERED_AT_6 = 2026-10-22T12:24:50Z (A116). The fix round (workflow
wf_36aa484c-852, script `goal-2026-10-19/workflows/evl8_fix.js`, sha256
b95ee78955e32b64b5ba055733d59bc94157937b36d9b168c375fb42b0e21eef, from 12:25Z) applied every finding of both checks
under the captain's decisions F1-F13, recalibrated the PX seats, their demotion, the meta-learners and the placebo audit
against PREREG-EVL-6 AS FROZEN on new synthetic seeds (`evl8/final/`), and wrote this file. From 14:32Z two re-checks
read it (statistics and leakage, `evl8/recheck1/`; text and money path, `evl8/recheck2/`): both "fix", with six majors
between them (the clock's reads for the PX-to-META bridge and for the shadow's re-decision, one member cutoff, the
timing table on the code's own cadence, PX-ON's money path against PREREG-EVL-7's rows, and the meta-learners' false
passes counted to a horizon rather than to the run's end, with a day-shock loading the META generator omitted) and
eleven minors. From 16:17Z the same workflow's final step made the least change that closes each (section 17),
re-measured the meta-learners to the run's end with that loading, the two ON seats sharing every day-level shock and
the PX demotion's corners on fresh seeds (`evl8/final/`: `meta_life8.py`, `px_shared8day.py`,
`px_demotion8.s184.json`), and restated the charges and the budget. Each of them worked under the rule that no price
after any event, and no return, P&L, look, band or mark of the lane, is read, queried or computed; none was.

PROVENANCE. Both workflows' prompts carried only the frozen texts (PREREG-EVL-1 to -6), PREREG-EVL-7's text as it was
being written, the code (releases 1019g and 1019h), outcome-free counts (`goal-2026-10-19/speed/SPEED-FACTS.md`,
`speed/EXECUTION-FACTS.md`), SEC's public `company_tickers_exchange.json` (counts only), the published literature, the
designers', judge's, checks' and re-checks' synthetic records and text findings (the final step's prompt is the fix
round's with the two re-checks' findings appended), and the captain's amendments record
(`scratch/eqlane-1010/CAPTAIN-AMENDMENTS.md`, A60-A117). That record also holds the captain's outcome-derived A96 line
(three sessions of shadow showed no program clear of noise: no figure, the same for every program), which no designer,
judge, check or fixer was asked to use and no constant here reads. The registering captain session (6e6a85b9) had
read, on Oct 21, the per-program means of the shadow record of the lane's existing programs over its first two entry
sessions (Oct 19-20) and the lane's aggregate real-money figures. It wrote both workflows' prompts and the decisions
F1-F13, and it chose no rule parameter: F1-F13 adopt the checks' proposals or set targets (the PX seats' first look as
the earliest that holds PREREG-EVL-6's 0.13 on fresh seeds; a false-demotion rate <= 0.15; the money population's cap;
one clock; a timing table; runs as PREREG-EVL-6's), and every constant of this file was proposed by a blind designer,
the judge, a check or a re-check, or fixed by the blind recalibration of section 6 (the final step chose, among the
re-checks' stated options, the late passes by time and births' exclusion of this file's rows; in place of re-check 2's
two options for the members, which need a record of which run wrote an intent that no stored row keeps, it fixed the
members by stored times as PREREG-EVL-7 reads its pools; and it set no new constant but the timing table's arithmetic
bounds, 15:46:45 for the last PX read and 15:46:50 for its timeout).

REGISTRATION TIME: the latest of three times, all recorded in the captain's amendment that pins it as
`REGISTERED_AT_8` (A92's method): this file's commit time; the pushing client's own clock read after the push of the
tag `prereg-evl-8` returns; and GitHub's activity time for the push of the branch `prereg/evl-8`. The tag never moves.
This file is frozen only after PREREG-EVL-6 (REGISTERED_AT_6 < REGISTERED_AT_8, which holds: PREREG-EVL-6 is frozen);
it may freeze before or after PREREG-EVL-7, and sections 4.2 and 6.6 say what holds either way. A program, control,
record or placebo of this file counts only events knowable after REGISTERED_AT_8. Nothing here changes for a registered
program: a change is a new version with its own registration time.

## 0. What this file adds, and what the fix round changed

- THE PX LANE (part A): a second lane of the House's event book whose events are defined from SIP prices and volumes,
  with no model call, no new feed and no new gateway route: three seatable programs (PX-DROP-ON, PX-SURGE-ON,
  PX-GAP-O1), two controls (free records), a pinned grid of 528 free records settled on a write-once panel of the
  whole liquid universe, and 16 placebo records with a control canary (the red team's audit). It is the goal's "other
  US-stock lane", with its own pivot count (section 9).
- THE META-LEARNERS (part B): two seatable programs, EVL-META-O1 and EVL-META-ON, whose fixed algorithm (an
  empirical-Bayes lower-confidence ranker over a family of 720 / 969 conjunction sub-rules, one expert for every hold-1
  program, control and record at its auction, and one for each of part A's 184 / 173 price records at its window)
  fills their slots each session from outcomes settled and stored before the decision. Their false-pass charge is paid
  per run, not per idea; the family grows by rule as later programs register, never past the 1,535 sub-rules the
  calibration measured. This is the file's recursion: free price records and every new program's record become,
  forward only and with no person in the loop, the evidence that fills real-money slots.
- THE SCREENS (F1, F4): PREREG-EVL-6 sections 1-3 AS FROZEN (`docs/prereg/PREREG-EVL-6.md` at tag `prereg-evl-6`, commit
  4ae9017aaac964503a0dc8ad71965d38a08cc18d, sha256 0f67f94ecac93f6b5542654e33ce5180fdbac254238badd571a37bcb0950f057)
  judge every seat of this file, word for word, with the money weights' and the top guard's cap read as the open cap of
  the version's band (F4: learning 4 for the PX seats, 8 for the meta-learners; Probe 14; Sized 8). The meta-learners
  take the frozen schedule unchanged. For the PX seats F1 asked for the EARLIEST first look (nothing else changed) whose
  worst plausible per-run false-pass rate within 120 sessions is <= 0.13 on fresh seeds (>= 4,000 programs) under
  PREREG-EVL-6's frozen plausible grid carried onto the PX designer's generator: that is the FROZEN 22nd BLOCK ITSELF
  (worst plausible 0.119 +- 0.005 on fresh seeds; section 6.2), so the PX seats too take PREREG-EVL-6's schedule with no
  change at all. The judge's earlier PX screen (looks from the 15th block at alpha 0.016 / 0.004) is withdrawn.
- WHAT THE FIX ROUND CHANGED, by the captain's decisions (each a finding of a check; section 17 maps every finding):
  F1 the frozen screen and the PX first look (section 5); F2 runs, never retirement by exhaustion, for every version of
  this file (section 5.1, 7.7); F3 the frozen demotion, calibrated for a true +40 bp PX edge with up to 14 buys a
  session (section 6.4); F4 money's population: money-weighted blocks and the top-CAP guard at the band's cap, PX
  recalibrated with them (sections 5, 6); F5 ONE CLOCK (section 1.2); F6 one catch-up cutoff (section 7.2); F7 a timing
  table that fits every isolated part without delaying or cutting an earlier file's row (section 4.6); F8 no sub-rule
  figure outside the mrl_* tables (sections 7.5, 10); F9 one member outcome with PREREG-EVL-2's limit at entry (section
  7.2); F10 PX writes its own px_eligibility and px_universe, never the lane's (section 4.4); F11 corporate actions read
  only as stored before tau, one adjustment basis a window (section 1.3); F12 every run charged when it starts, the
  lane's budget as R3's SEATING sum, registration order (section 6.6); F13 every minor (section 17).
- WHAT THE FINAL STEP CHANGED (the two re-checks; section 17's last rows): the clock's reads (c) and (d), so the
  PX-to-META bridge and the shadow's re-decision are read as written (section 1.2); MEMBERS fixed by stored times
  alone, each source only through its live decision (section 7.2); the timing table on release 1019h's own cadence,
  with each PX read's timeout capped at its run's end and the pre-passes yielding (section 4.6); every buy of this file
  in a late pass, by time, at the close only after PREREG-EVL-7's rows (section 4.2); the meta-learners' false passes
  measured to the run's end with a day-shock loading spread, and their charge (sections 6.5, 6.6); births' exclusion
  of this file's rows (section 4.4); CAP a constant (section 5.1).
- WHAT IT COSTS. No PX or META version is promoted before the 22nd settled block of a run, at any edge. A true +40 / +60
  bp PX edge (judged, after the replay's 14.16 bp) is promoted within 120 sessions 0.485 / 0.870 of the time at the PX
  designer's base with about 27 names a session and 0.341 / 0.466 at the worst plausible corner (0.736 / 0.983 and 0.548
  / 0.701 counting run 2); a +40 / +60 bp sub-rule only the meta-learners can find, 0.207 / 0.657 (section 6.3, 6.5).
  PREREG-EVL-6's frozen demotion, kept, falsely demotes a true +40 bp PX edge with up to 14 buys a session at most
  0.168 by its 1,000th Probe+ event, above F3's 0.15 at about half the corners measured (section 6.4); a PX seat
  whose bought names earn nothing while its unbought ones earn can still pass (section 6.2, F4's guard). The
  meta-learners' false passes per run TO THE RUN'S END, with a day-shock loading spread the earlier generator omitted,
  are 0.098 at the worst plausible cell (0.117 the largest figure at any horizon), 2-3 times the fix round's 120-session
  figure and under PREREG-EVL-6's 0.13, which each run is charged (sections 6.5, 6.6). Every buy of this file is
  planned in a late pass, so PX-DROP-ON, PX-SURGE-ON and EVL-META-ON buy real money at D's close only when the lane's
  close run ends before the book's 15:48 tick (within 63 s; 48 s for EVL-META-ON), which a lane run at PREREG-EVL-7's
  and -5's bounds does not; the judged records, the live shadow, do not depend on it (section 4.6). After this file,
  PREREG-EVL-7, A117's PREREG-EVL-9 and A104's births about three charges are left for every later run of every file
  (six without the births), so this file's second runs start only if room is left after the earlier files' (section
  6.6).

## 1. Terms and THE CLOCK (part A; section 7.2 for part B)

### 1.1 Terms

- D is the entry session, P the session before it, Pn the nth session before D (the lane's session calendar). Times
  are New York times. The open decision time of D is 09:15:00 ET; its close decision time is its close - 14 minutes
  (15:46:00 ET on a full day) (PREREG-EVL-1 section 5). An early close moves every close-side time of this file by
  (close - 16:00).
- c_X: the SIP 1Day close of session X with adjustment=all on section 1.3's basis; c_X(raw) the raw close; o_X the open
  likewise. c*_P: P's adjustment=all close READ BY THE MORNING PASS OF D (section 4.6: after 09:00 ET of D, stored
  before the decision time tau of each auction of D it serves). cb, ob, cb*_P: the same for the issuer's benchmark (IWM when ADV20 < $50,000,000,
  else SPY: PREREG-EVL-1 section 2).
- FLAGGED(D): |c*_P / c_P(raw) - 1| > 0.001 (a split, a dividend or a correction effective D), or no c*_P stored before
  the decision time. A FLAGGED issuer is not in PXU(D).
- sigma60: the sd of the 60 adjusted close-to-close returns c_t / c_(t-1) - 1 ending at P. sigma_on60: the sd of the
  60 adjusted overnight returns o_t / c_(t-1) - 1 ending at P. Both on ONE adjustment basis (section 1.3). ADV20:
  PREREG-EVL-1 section 2's (the mean raw close x volume over the 20 sessions before D). ADV20sh: the mean raw share
  volume of those 20 sessions.
- THE PX1530 MARK x_D: the close of the last raw regular-session SIP 1Min bar of D that starts in [15:00, 15:29] ET and
  ends by 15:30 ET; on an early close the span is [close - 60 min, close - 31 min], ending by close - 30 minutes. None:
  no value. It is a new label (`px1530`) in px.sqlite; the lane's `1530` marks are untouched.
- THE PREMARKET INDICATION pm_D: the close of the last raw SIP 1Min bar of D starting in [08:00, 08:58] ET, when at
  least 3 bars of that span have volume; else none.
- V_D: the sum of D's raw regular-session SIP 1Min volumes through the bar ending at 15:30 ET (at the close - 30
  minutes on an early close), over ADV20sh.
- NO STORED ITEM in a span, for an issuer (read with NO registration floor, PREREG-EVL-5's "NO NEW INFORMATION"
  pattern): (i) no ENEWS article, of any source and any number of symbols, whose symbols include a ticker that SEC's
  `company_tickers.json` (the copy D's decision reads) maps to the issuer's CIK, PREREG-EVL-1 section 3's non-live
  exclusion applied; (ii) no E8K of the issuer (form type exactly `8-K`, any items); (iii) no EF4 of the issuer with
  PREREG-EVL-2's INSIDER BUY; each knowable in the span. THE SHADOW reads every such item by its knowable time,
  whenever stored (section 3.4's hourly re-decision); A REAL-MONEY DECISION reads the items stored before its decision
  time (PREREG-EVL-1 section 3; a filing stored when its documents are fetched, A72).
- THE ON SPAN of D: [P's close decision time, D's close decision time). THE O1 SPAN of D: [P's close decision time,
  09:00 ET of D).
- PXU(D), THE PX UNIVERSE of entry session D, decided once by the morning pass of D (section 4.6; written whole at its
  end, and serving an auction of D only when stored before that auction's tau) under PREREG-EVL-1
  section 2's LIVE rule (`universe.eligible_core`, written to px.sqlite's `px_eligibility` and `px_universe` only:
  section 4.4): every CIK of SEC's `company_tickers.json` whose stock is eligible for D, AND c_P(raw) >= $5.00, AND
  ADV20 >= $10,000,000, AND SIP daily bars (adjustment=all, section 1.3's basis) stored on each of the 61 sessions
  before D, AND not FLAGGED(D), AND whose operating-company test was cached within the 30 days before D (the cache
  refreshes at most 1/25 of the CIKs a night; a CIK with no such cached test is not in PXU(D)). The bound is 6,041
  issuers with a plain 1-5 letter ticker on NYSE, Nasdaq or Cboe (`price/count_universe.py`, SEC's public file; no price
  read); the House counts N_U on its first pass.
- WRITE-ONCE VALUES: every value of section 2 is written ONCE, by the run that decides its auction, into px.sqlite
  `px_features` (INSERT OR IGNORE) with that run's receipt id (`run`), `decided_at` (the wall time of the write),
  `as_of` (the decision time tau), `inputs_at` (the latest `fetched_at` of its inputs) and `bar_end` (the latest bar end
  of its inputs), and never recomputed; the bars table's upsert can never move a decided value.

### 1.2 THE CLOCK (F5): one rule for every decision of this file

- THE DECISION TIME tau of an auction (D, X): 09:15:00 ET of D for the O1 programs (PX-GAP-O1, CTRL-PX-ALL-O1,
  EVL-META-O1); D's close decision time for the ON programs (PX-DROP-ON, PX-SURGE-ON, CTRL-PX-ALL-ON, EVL-META-ON).
  tau bounds what is KNOWABLE: every input of section 2 is knowable before tau by its own definition (x_D and V_D at
  15:30 ET, pm_D at 08:59 ET, items at their knowable times, P's bars at P's close, c*_P at 09:00 ET of D).
- STORED: a row is stored when it is written; every px.sqlite row carries `fetched_at` (the vendor read), `run` (the
  receipt id of the run that wrote it) and, for a bar, `bar_end`.
- THE RULE. A decision of auction (D, X), live or catch-up, shadow or real money, reads exactly:
  (a) rows STORED BEFORE tau: the lane's items by `book._stored_before`, verdicts answered before tau, px_bars of
      sessions before D (the nightly pass), px_universe and px_eligibility of D, c*_P, FLAGGED(D), sigma60, sigma_on60,
      ADV20 and ADV20sh (the morning pass), and, for a meta-learner, outcomes settled before its state time sigma
      (section 7.4);
  (b) the rows ITS OWN RUN wrote after tau from SIP 1Min bars whose `bar_end` is at or before the value's knowable time
      (x_D and V_D: 15:30 ET, or the close - 30 minutes; pm_D: 08:59 ET), all of which end before tau. The Basic plan
      serves a bar 16 minutes after it ends (`universe.SIP_DELAY`), so these bars can only be fetched after tau:
      fetching them inside the decision's own run, storing them write-once with that run's id, and reading them in that
      run's real-money decision IS this file's rule, not a departure from "stored before the decision time";
  (c) for a meta-learner, exactly the rows that section 7.2's MEMBERS rule reads, as stored: its sources' real-money
      readings of (D, X) at tau and their intents where 7.2 names them; THE LIVE PX RUN OF (D, X)'s px_features and
      px_marks rows (that run wrote them after tau under (b), write-once with its `run` id; THE LIVE PX RUN OF (D, X) is
      `decide-close-px8:<D>` for X = ON and the PX-GAP-O1 part of `decide-open-px8:<D>` for X = O1, when it finished
      and wrote its px_features; no catch-up is ever a meta-learner's PX run); the lane's eligibility results of D
      under section 7.2's ELIGIBLE TO PICK cut-off only, with the universe rows of D they admit (values made from
      sessions before D's open, read as stored whatever their write time: PREREG-EVL-7 section 1.1's reading); and D's
      `1530`, `px1530` and `0930` marks as section 7.2 reads them.
  (d) a SHADOW RE-DECISION of (D, X) (the lane's hourly re-decision of a PX seat, control or placebo, section 3.4)
      reads the px_features rows of THE PX RUN THAT DECIDED (D, X) (the live PX run of (D, X), else its `decide-px`
      catch-up), never recomputed and never written again, and the NO STORED ITEM items whenever stored (THE SHADOW,
      section 1.1).
  Nothing else: no row another run wrote after tau beyond (c) and (d), no bar ending after its knowable time, no later
  adjusted series (section 1.3). A real-money decision of a PX seat reads only px_features rows written by its own
  decision run; a meta-learner's reads only those of the live PX run of (D, X) named in (c) (for EVL-META-O1 that is
  a part of its own run). Every intent carries `decided_at = tau`, as run.py writes every intent.
- THE TIE-BREAK DOES NOT REACH THE CLOCK. Section 15's ambiguity rule (the reading that trades less) applies to what
  this section does not state. Reads (b), (c) and (d) ARE stated: no reading of this file turns PX real money, the
  PX-to-META bridge or the shadow's re-decision off on the ground that their inputs were written after tau or by
  another run.
- TEST (a coder checks it): on a synthetic session D whose 15:29 1Min bars are fetched at 15:46:05 ET by run
  `decide-close-px8:<D>` and whose rule selects at least one name, (i) PX-DROP-ON's real-money picks of D are that
  run's ranked names after the book's skips (non-empty); (ii) EVL-META-ON's members of D include PX-DROP-ON's and
  CTRL-PX-ALL-ON's selections of D by that run, and its `x:` experts on D read that run's px_features rows, in its live
  decision `decide-close-meta8:<D>` and in a `decide-meta:close:<D>` catch-up alike (the same `mrl_pool` rows); (iii)
  a px_features row of any run other than the decision's own run and, for a meta-learner, the live PX run of (D, X)
  named in (c) and, for a shadow re-decision, the PX run that decided (D, X) named in (d), or one whose `bar_end` is
  after its knowable time, is never read; (iv) with that run cut before it wrote D's rows, PX-DROP-ON buys nothing at
  D's close, its catch-up is never a judged block, and EVL-META-ON's members of D hold no PX selection, live and in a
  catch-up alike; (v) with an item of D's ON span stored after tau for an issuer the live run took, the hourly
  re-decision removes that issuer from PX-DROP-ON's K 40 and takes the next qualifying name in the same run's stored
  ranking, and PX-DROP-ON's judged block of D is the re-decided one (section 3.4).

### 1.3 Corporate actions and the adjustment basis (F11)

- THE BASIS OF A WINDOW. Every adjusted value (sigma60, sigma_on60, the records' z1, z5, z20, h52 and zs, c_t and o_t
  in them) reads px_bars rows (adjustment=all) STORED BEFORE tau, all of one window on ONE adjustment basis: the
  issuer's adjusted history from its latest FULL re-read (the 270-session read of the first night, or the full
  re-read the House makes after 09:00 ET of a session on which the issuer is FLAGGED, before that session's first
  decision when it can) together with the nightly rows written since that re-read. A value whose window holds a FLAGGED
  session with no full re-read stored before tau does not exist (its event is not taken), and an issuer FLAGGED on any
  of the 61 sessions before D without such a re-read is not in PXU(D).
- c*_P, FLAGGED(D) and PXU(D) are the morning pass's, stored before tau; c*_P's basis is its own read.
- A CATCH-UP (section 3.4) reads every adjusted value, c*_P, FLAGGED(D) and PXU(D) AS STORED BEFORE tau, never a later
  adjusted series: no corporate action effective after D can flag D, enter PXU(D) or move a value. The only bars a
  catch-up may fetch are RAW 1Min bars of D ending by the value's knowable time (a raw bar carries no later corporate
  action). A value whose adjusted inputs were not stored before tau does not exist for any decision.
- What cannot be guarded: an action the vendor adjusts only after the morning pass of D dilutes the seat with a null
  event (its outcome is computed on adjusted ratios by score.py, so it cannot fake an edge).

## 2. The values (part A)

| value | definition | needs |
|---|---|---|
| zd | (x_D / c*_P - xb_D / cb*_P) / sigma60 | x_D, xb_D (the benchmark's px1530 mark) |
| zg | (pm_D / c*_P - pmb_D / cb*_P) / sigma_on60 | pm_D, pmb_D |
| move_d | x_D / c*_P - 1 | |
| move_g | pm_D / c*_P - 1 | |
| V_D | as section 1.1 | D's 1Min volumes |
| the records' z1, z5, z20, z1s, zg, zo, zds, h52, v, zs | the "value" texts of `px_grid8.json` | as stated there |

A value with any input missing does not exist, and its event is not taken.

## 3. The PX programs (part A)

### 3.1 The seats

Seatable from birth (section 4). Each holds one session (its block is D) and takes ONE EVENT PER ISSUER PER D, under
PREREG-EVL-1 section 5's one position per issuer per program (A72's reading: an issuer the program holds, or held
within the last 5 sessions, or holds an intent entering within the 5 sessions after, is skipped), PREREG-EVL-2's LIMIT
AT ENTRY (an entry auction above 1.25 x c_P(raw) is not filled and the event is skipped, shadow and real alike), and
PREREG-EVL-1 section 5's auction prints, fallback ladder, costs, r, b, a and TRADABLE, unchanged.

| id | entry -> exit | events of D | rule | ranking (`intents.rank_key`, higher first) |
|---|---|---|---|---|
| PX-DROP-ON | D's closing cross -> D+1's opening cross | PXU(D) issuers with NO STORED ITEM in the ON SPAN of D | zd <= -2.0 and -0.35 <= move_d <= -0.03 | rank_key = -zd; then ADV20 descending, then CIK |
| PX-SURGE-ON | the same | the same | zd >= +2.0, +0.03 <= move_d <= +0.20 and V_D >= 1.5 | rank_key = zd; then ADV20 descending, then CIK |
| PX-GAP-O1 | D's opening cross -> D's closing cross | PXU(D) issuers with ADV20 >= $20,000,000 and NO STORED ITEM in the O1 SPAN of D | zg <= -2.0 and -0.35 <= move_g <= -0.02 | rank_key = -zg; then ADV20 descending, then CIK |

- THE SHADOW takes the first K = 40 qualifying issuers by the ranking (after every skip above). Real money takes its
  band's room in the same order (section 4). The ranking is the order `book.picks` and PREREG-EVL-6 section 1.4's top
  guard read (rank_key descending, then adv20, then event id).
- EVENT ID `px:<program>:<D>:<cik>`. KNOWABLE TIME: 15:30 ET of D (PX-DROP-ON, PX-SURGE-ON; on an early close, close -
  30 minutes) or 08:59 ET of D (PX-GAP-O1). Decision time tau as section 1.2; decided by the runs of section 4.6.
- READS: the ON seats' run reads x_D for every PXU(D) name with no stored item in the ON span (1Min bars of
  [15:00, 15:30), from 15:46:00 ET) and V_D for the names with zd >= +2 (their 1Min volumes of D through the bar ending
  at 15:30); PX-GAP-O1's run reads pm_D for the PXU(D) names with ADV20 >= $20,000,000 (1Min bars of [08:00, 08:59),
  from 09:15:00 ET). Every other input is the morning pass's (section 1.2 (a)).

### 3.2 The controls (free records, PREREG-EVL-1 section 7)

- CTRL-PX-ALL-ON: the 200 PXU(D) issuers with NO STORED ITEM in the ON SPAN of D (the reading of the decision that
  writes them) with the smallest sha256("PX-CTRL|ON|<D>|<cik>") (lower-case hex compared as text), among issuers the
  control does not skip under A72's rule; held D's close -> D+1's open. CTRL-PX-ALL-O1: the same with "|O1|" among
  PX-GAP-O1's events-of-D population; held D's open -> D's close. Both settle as PREREG-EVL-1 section 5 says, never seat
  and cost nothing; their eligibility and settlement inputs (prev_close, adv20, bench) are px_universe's rows.
- THE CONTROL CONDITION: PX-DROP-ON and PX-SURGE-ON are judged against CTRL-PX-ALL-ON, PX-GAP-O1 against
  CTRL-PX-ALL-O1 (screen.CONTROLS gains these three rows), so a seat cannot pass on the no-news universe's own overnight
  or intraday move against SPY or IWM.
- WHY 200 (the designer had 60): the controls are also the meta-learners' window into the price lane (section 7.2:
  every hold-1 control at an auction is a source), so 200 print-settled no-news names a session give the meta-learners'
  price features a pool to learn on, at no metered cost (about 840 more auction-print reads a night than 60 names would
  need: 2 x 140 more events, 2 prints each, 1.5 pages a print read; `final/timing8.out`). The false-pass figures of
  section 6 are the knife edge's, where the control never protects, so the control's size changes none of them.

### 3.3 The records, the panel and the placebos (free; never seated, never screened as a seat, never reported by figure)

- THE GRID: the 528 rules of `px_grid8.json` (canonical sha256
  bb0d50e47d94e73f677a22bb612ef3f1cf7d23b23e5a51375fe965cf57e3e5a1, copied to `docs/prereg/evl-8/` at the freeze; the
  meta-learners read the O1 and ON records forward as experts, section 7.3): families REV1, REV5, REV20, REV1S
  (windows O1, ON, C1), GAP (O1), OPENGAP, DAY and DAYS (ON, C1), HI52 (O1, ON, C1), VOL (HIUP, HIDN), each crossed with
  a bottom or top decile, news ANY / NONE / SOME (an item in the window's span: the O1 SPAN for O1, the ON SPAN for ON
  and C1), tier ALL / SMALL / LARGE and window; 48 DRIFT rules over the six PREREG-EVL-1 to -4 controls' issuers 1, 2,
  3 or 5 sessions after their exit; 27 UNIV base rates; 3 SEAT mirrors (each seat's own top 40).
- THE PANEL: one row per (D, window O1 | ON | C1, PXU(D) name), settled write-once on the BAR BASIS: the SIP daily bar's
  open or close at the window's ends, the benchmark's same bars, PREREG-EVL-1 section 5's cost allowance at the name's
  ADV20, splits inside the hold through the adjusted ratio. `px_record_days` holds each record's daily n, sum a, sum a^2
  and sum r, written once after the session is settled. A record's values of D are the px_features rows of the run
  that decided D's auction for that window (section 1.2), never recomputed.
- THE BASIS: for every seat and control event the bar-basis return is written beside the print-basis return
  (`px_basis`); measured forward, never a judge input.
- PLACEBOS (the red team's audit, free): PLC-PX-ON-1 .. -8 and PLC-PX-O1-1 .. -8, placebo j taking the 8 events of its
  window's control on D with the smallest sha256("PX-PLACEBO|<window>|<j>|<D>|<cik>"); no new intent (a subset of the
  control's settled outcomes). Each is screened nightly by THE PX SCREEN without its control condition, as if it were a
  PX seat in learning (records only; a placebo never moves a band). THE AUDIT ALARMS when 3 or more of a window's 8
  placebos have passed by their 60th block, or when the control itself passes THE PX SCREEN without its control
  condition (THE CANARY): the pool then carries an edge no selection made (a cost basis too low, a survivorship or
  look-ahead leak, or a real universe-wide drift). An alarm is a report line and an owner-facing warning; it moves no
  band and edits no judge. Its rates under THE PX SCREEN as registered (`final/placebo8f.py`, 200-name pools, 2,000
  paths a cell, seeds from 179,900,001): an honest pool alarms 0.2% of the time, 2.2% with a 10 bp drift and crash days
  and 8.1% with a 20 bp drift and crash days (the canary seeing the drift itself: 7.7%); a pool lifted by 20 / 30 / 50
  bp alarms 19.3% / 65.0% / 98.3% of the time (55.5% / 89.5% at 30 / 50 bp with a 20 bp drift and crash days).

### 3.4 Live decisions, re-decisions and catch-ups

- THE LIVE DECISIONS are the runs of section 4.6: `decide-close-px8:<D>` for the ON programs, `decide-open-px8:<D>`
  for the O1 programs. Each writes its auction's px_features, its seats' and control's intents, and its receipt.
- THE LANE'S HOURLY RE-DECISION re-takes the seats' K 40, the controls' 200 and the placebos' 8 from the stored
  px_features of THE PX RUN THAT DECIDED (D, X) (section 1.2 (d): the live run, else its `decide-px` catch-up; never
  recomputed) under the shadow's NO STORED ITEM reading (an item knowable in the span and stored after the decision
  removes its issuer, and the next qualifying name in the stored ranking takes its place), as it re-decides
  PREREG-EVL-5's rows. It never re-decides a meta-learner, whose decision is written once, and it never changes a
  meta-learner's members (section 7.2 reads the live PX run's selections at tau, not the re-decided ones). A PX look
  as of the close X waits for the finality of the NO STORED ITEM feeds (screen.final_until, as EVL-NEWS-NIGHT2-ON's
  does).
- A CATCH-UP: an auction whose live run did not finish, or wrote none of its px_features, is decided later BY ITSELF by
  `decide-px:<auction>:<D>` under section 1.2's clock and section 1.3's catch-up reading. Its intents are a REPORTED
  SHADOW, NEVER A JUDGED BLOCK, never traded and never a meta-learner's member or `x:` membership (section 7.2 reads
  only the live PX run; PREREG-EVL-7 section 1.7 treats its learners' later decisions the same way): a PX version's
  judged record is the shadow of its LIVE decisions with the hourly re-decision's removals.

## 4. Real money (both parts)

### 4.1 Bands

- LEARNING from the first decision after the House release carrying this file's programs is live: a target of 2% of
  the account equity at the previous close, whole shares at the limit (1.25 x the previous SIP close), one share when
  that rounds to none and one share at the limit is at most 5% of equity and fits every wall. THE PX SEATS hold AT MOST
  4 OPEN LEARNING POSITIONS a program (the money row `event.max_open_v8.learning` = 4 with EQUITY_MONEY_BOUNDS (0, 4),
  read only for PX versions: a lower value trades less and no value above 4 exists for them; the red team's
  `rt_budget.py`: five more programs' full learning books would hold loss-budget and cash room the Probe tier needs).
  THE META-LEARNERS hold PREREG-EVL-3's learning band (at most 8 open), which PREREG-EVL-6 section 6 leaves unchanged
  (F13: slots per PREREG-EVL-6 section 6 clause (4), except PX's learning room 4).
- PROBE (PREREG-EVL-6 section 6, clause (4), A99): PREREG-EVL-1 section 8's envelope at the money table's share (3.5%
  since A86 revised), AT MOST 14 OPEN (`event.max_open_v6.probe`, read for versions registered at or after
  REGISTERED_AT_6), and a Probe or Sized buy takes the fewest whole shares reaching 0.8 of its band's target, never
  above 5% of equity at Probe nor the name's 10% wall at Sized, judged again by every cap; a pick no such count reaches
  is skipped before it takes a slot (A99, A100's `reach_bar` rows). Until A100's rows are live, Probe holds at most 6
  and sizes as today (the reading that trades less).
- SIZED, DEMOTION, RE-PROMOTION, RETIREMENT: section 5's judges (PREREG-EVL-6 section 3 as frozen), with PREREG-EVL-1
  section 8's Sized size (10%, at most 8 open) and the open-risk weight max(0.10, 1.65 x sigma x sqrt(h)).

### 4.2 ROOM

- Sized, then Probe, then learning (Probe and Sized round-robin, A85). In each band, AFTER EVERY ROW OF PREREG-EVL-1 TO
  -7 WHATEVER THE ORDER IN WHICH PREREG-EVL-7 AND THIS FILE ARE FROZEN (check 2's minor 13), in this order: PX-DROP-ON,
  PX-SURGE-ON, PX-GAP-O1, EVL-META-O1, EVL-META-ON; R3's births after them (A101). Inside Probe's and Sized's
  round-robin each of this file's programs takes part as one of the last programs of each pass, after PREREG-EVL-7's
  learners and before the band's births. Within a program its own ranking (section 3.1; section 7.5 for the
  meta-learners). When two programs want one name at one auction, the earlier in that order takes it (`allocate`, with
  every name the main pass gave counted as given): a name a PREREG-EVL-7 learner is given is never also bought for a
  meta-learner at that auction, so no slot is used twice; the shadow keeps every event. The next bullet says how this
  order and the band tiers are read in time.
- EVERY BUY OF THIS FILE IS PLANNED IN A LATE PASS, BY TIME, AND KEEPS NO ROOM (re-check 2's major 4, its first
  option). The book's main pass of an auction plans every earlier file's row exactly as it would without this file.
  Every buy of this file, IN ANY BAND, is planned in that auction's LATE PASS (section 4.6): at the open after the main
  pass; at the close only once the lane's close receipt of D is in, after the book has planned every PREREG-EVL-7 row
  of D's close that the receipt names (in that tick or before), so PX-DROP-ON's and PX-SURGE-ON's buys, whose intents
  are written before 15:47:00, are never planned in the main pass ahead of PREREG-EVL-7's EVL-LRN-ON rows. It takes only the room the rows planned before it leave:
  no pass keeps room for it, and a buy of this file whose late pass does not come inside the window is not sent and is
  never "held" (this file does not use the waiting room release 1019h built for PREREG-EVL-5 section 1.3,
  `book.part_hold`, `live.HeldAhead`, A113; a waiting PREREG-EVL-5 buy keeps its room from this file's rows as from
  R3's births, `book.room_free_overdue`). Inside a late pass, ROOM's order: band (Sized, Probe, learning; Probe and
  Sized round-robin, A85), then the order above. So, AT ITS OWN AUCTION, no earlier file's row ever waits for, keeps
  room for, or is refused for a row of this file, at learning, Probe or Sized alike.
- AT THE OTHER AUCTION a promoted version of this file (Probe or Sized) is, as every PREREG Probe or Sized program is,
  among "the other auction's live Probe and Sized programs" that A85's next-auction reservation keeps cash, invested
  room and loss budget for (book.py `reservation`), so an earlier file's LEARNING buy there sizes on that room less its
  reservation. That is the one way a row of this file reaches an earlier row's room; it is A85's rule for every
  promoted row, unchanged, and stated here (re-check 2's major 4).

### 4.3 The eligible list, the order line and the known edges

- THE HOUSE'S ELIGIBLE LIST of D gains each PX seat's first 40 names (from px_universe's live rows) and each
  meta-learner's picks (at most 152 names, under EVENT_LIST_MAX 5,000); the gateway's event-buy checks ($3 price, $1M
  ADV, the 1.25 x limit, the asset and bar checks) are looser than PX's floors and unchanged.
- THE 150-ORDER LINE refuses this file's entries first among the PREREG rows (after PREREG-EVL-7's), and each overnight
  lot keeps one order of the next session's line; an exit is never stopped by it.
- KNOWN EDGES, STATED AS PREREG-EVL-5 SECTION 1.3 STATES ITS OWN (check 2's minor 14), not prevented, each counted in
  the report by program: PX-GAP-O1 and EVL-META-O1 sell at D's close, so an issuer they hold that an earlier close-entry
  row wants there (a DAY(D) article, an 8-K of D's close window) loses that row's real-money buy to the sale gate;
  PX-DROP-ON, PX-SURGE-ON and EVL-META-ON sell at D+1's open, so fresh overnight news can cost an earlier open-entry row
  its buy there. This file's lots hold cash, invested room and loss-budget room at the auctions where they are held and
  sold, which earlier learning rows need there (A85 reserves only for Probe and Sized). The shadow keeps every event.

### 4.4 PX never changes an earlier program's record (F10)

- PX judges PXU by `universe.eligible_core` into px.sqlite (`px_eligibility`, `px_universe`) and NEVER writes the lane's
  `eligibility` or `universe` tables, for a seat, a control, a record or a placebo. The book reads a PX seat's
  eligibility, prev_close and adv20 from px_universe's live row of D; a meta-learner's pick from the lane's live
  universe row of D or, for a member whose only sources are PX rows, from px_universe's live row (section 7.2).
- BIRTHS (re-check 1's minor 6, its rule (1)): this file's programs, controls, records and placebos, EVL-META-O1 and
  EVL-META-ON included, are EXCLUDED from R3's births' facts (`births.py`: "every registered program's selection
  count") and from its validator's Jaccard "against every registered program": births never read a row of this file,
  whatever its table (their selections are price-derived, and px.sqlite is never attached to a births connection,
  section 10).
- PROOF: no program of PREREG-EVL-1 to -7 or of R3 reads px.sqlite, an mrl_* table or a row of this file's programs
  (R3's births by the exclusion above); this file writes no row of events.sqlite other than its own programs' intents,
  outcomes, looks, bands and band_history rows, its screen.CONTROLS rows, its mrl_* tables and its receipts, none of
  which an earlier program reads, and no row of the lane's `bars`, `marks`, `eligibility` or `universe` (its bars and
  marks are px.sqlite's `px_bars` and `px_marks`). So every earlier program's shadow decision reads the same rows with
  and without this file and writes the same intents. (Its runs can delay, by at most the 55 s of `decide-close-px8`
  and the 60 s of `decide-open-px8`, when a record or verdict pass stores rows that are knowable but stored after tau;
  real money reads only rows stored before tau and the shadow reads them whenever stored, section 4.6, so no
  real-money row or judged record of an earlier file changes.)
- TEST: the lane's decisions of a fixture week, run with this file's programs on and off: every intent (event, skip,
  rank_key, why) of every program of PREREG-EVL-1 to -7 and of R3's births (those registered before REGISTERED_AT_8 and
  any born in the fixture week) is byte-identical, and so are the births job's facts and its validator's Jaccards.
  (Real money: earlier rows come first in ROOM at every auction, section 4.2; the cash and loss-budget room this
  file's lots hold across auctions, and A85's reservation for a promoted version of this file, are sections 4.2's and
  4.3's stated edges.)

### 4.5 Unchanged

Every wall (<= 10% of equity a name, <= 100% invested, no margin, no shorts, borrowing or option sales), the loss budget
($400 net in any 20 sessions, $800 net total, realized plus open risk at the 95% holding-period loss), the kill switch,
the daily and drawdown stops, A85's reservation, the sale gate (a name an event lot sells at an auction is not bought
there), A80's venue-cancel re-send, the fallback ladder.

### 4.6 THE TIMING TABLE (F7; re-check 2's major 3)

Every isolated part fits before the book's send line at the close and at the open WITHOUT delaying or cutting any
earlier file's row, because this file's parts run in their OWN RUNS at stated times outside the lane's decision runs,
read pre-passed data where the data are knowable earlier, yield to every earlier file's task whose rows they could
reach, and keep no room (section 4.2). Constants from release 1019h (`final/timing8b.py`, `final/timing8b.out`, reading
house.py, gw.py, run.py, calendar.py, equity/live.py, live/step.py, constitution.py and universe.py from git): the
lane's tasks run one at a time on the House's ONE SLOT; its market-data reads are spaced DATA_INTERVAL 0.5 s apart (at
most 120 a minute; the 150-a-minute token bucket is new code, section 15); a task checks its bound before each read,
and one read can return after it ("A BOUND IS NOT A PROMISE": the gateway client's timeout is 45 s); DECISION_MARGIN
5 s; the open decision 09:15:00 ET, the book's wait for the lane's open decision 240 s, sends from 09:16:00, the open
cut-off (`open_until`) 09:27:00; the close decision 15:46:00, HOLD_LEAD's lead from 15:44:30, CLOSE_GRACE 60 s (the
lane's live close run starts 15:47:00), DECIDE_BUDGET 150 s, the close cut-off (`close_until`) 15:49:00; SIP_DELAY 16
minutes. THE BOOK makes ONE DECISION AN AUCTION at its minute tick (live/step.py: MINUTE_OFFSET 3 s into each minute,
after the options path's own reads of that minute), waiting for the lane's decision of the auction 240 s at the open
and 60 s at the close (to 15:47:00, when the lane's close run has only just started); this file's buys are planned in
LATE PASSES at the book's later ticks inside the window (new code, section 15). The last tick inside the close window is
the 15:48 tick (15:48:03 or later); the 15:49 tick is past the cut-off. A full day; an early close moves every
close-side row by (close - 16:00).

| time (ET) | run (receipt) | what it does | bound and priority | if it does not finish |
|---|---|---|---|---|
| from 16:20 of P | `px-bars:<P>` | P's 1Day bars, raw and adjustment=all, for PXU candidates; the full adjusted re-read of an issuer FLAGGED at P | the House's lowest priority; it YIELDS: before each read it stops when any other lane task is due (what it stored stays) and goes on at the slot's next free turn | a value that needs it does not exist for D |
| 09:00:00 | `prepass-meta:open:<D>` | EVL-META-O1's state from outcomes settled before 09:00:00 (its state time, section 7.4) into `mrl_state`, write-once at its end | lowest priority; it YIELDS before each step (a source's or a sub-rule block's update, each well under a second) to any other lane task due, writing nothing until it is whole; never past 09:13:00 | the META part computes the same state itself inside its run's bound, else trades nothing at that open (a catch-up) |
| 09:05:00 | `px-am:<D>` (the morning pass) | c*_P (adjustment=all, read after 09:00), FLAGGED(D), PXU(D) into px_universe / px_eligibility (written whole at its end), sigma60, sigma_on60, ADV20, ADV20sh | lowest priority; it YIELDS before each read to any other lane task due (stored reads stay); never inside a decision's margin (house.py `_deadline`); it resumes after the open decisions and runs until 15:30:00 (re-check 2's minor) | PXU(D) stored before 09:15:00 serves both auctions of D; stored in [09:15:00, 15:30:00) only the ON auction (no PX-GAP-O1 event of D); none by 15:30:00: no PX event of D (nothing is computed later from a later series, section 1.3); the report counts the auctions lost |
| 09:15:00 | `decide-open:<D>` (the lane's, unchanged) | every earlier row of PREREG-EVL-1 to -6 and R3's births; PREREG-EVL-7's EVL-LRN-O1 part under its own 90 s | DECIDE_BUDGET 150 s: its receipt by 09:17:30 | as those files say |
| book, on that receipt (or at 09:19:00) | THE OPEN MAIN PASS | every earlier row, as today | as today | as today |
| on that receipt | `decide-open-px8:<D>` | THE FIRST TASK THE LANE RUNS AFTER THE RECEIPT (no live decision is due then; a record or verdict pass due meanwhile waits for it): PX-GAP-O1 (pm_D reads, 1Min 08:00-08:58 of the PXU(D) names with ADV20 >= $20M: 10-31 reads, 5-16 s at DATA_INTERVAL; px_features; the intents of PX-GAP-O1 and CTRL-PX-ALL-O1), then EVL-META-O1 (members by section 7.2, the walk, its intents) | 60 s from its start, never past 09:19:30; each read's timeout min(45 s, the bound - now); each part its own failure | a part not finished trades nothing at that open: `decide-px:open:<D>` / `decide-meta:open:<D>` decide it later (a reported shadow, never judged; a PX part not finished gives EVL-META-O1 no member, section 7.2, and then the META part is decided only by its catch-up) |
| book, the first tick after `decide-open-px8:<D>` finished | THE OPEN LATE PASS | PX-GAP-O1's and EVL-META-O1's buys, once, after every row the main pass planned (every name it gave counted as given), from the room left; sent in the same tick | 8 ticks inside the window when `decide-open-px8` ends by 09:18:30 (a lane receipt at its bound, 09:19:03 to 09:26:03), 7 when it ends at 09:19:30; nothing at or after 09:27:00 | not planned: not sent (the shadow keeps every event) |
| 15:30:00 | `prepass-meta:close:<D>` | EVL-META-ON's state from outcomes settled before 15:30:00 | as the open's; never past 15:43:00 | as the open's |
| 15:44:30 | (HOLD_LEAD's lead: the lane's turn is kept for its live close decision, release 1019g; this file holds the same span whether or not PREREG-EVL-5 has programs) | from here, every record or verdict task the lead's turn starts before 15:46:00 is bounded to END BY 15:46:00 instead of the decision's margin (their rows stored after tau reach no real-money row of D's close: PREREG-EVL-1 section 3; each is resumable, house.py; the shadow reads them whenever stored); PREREG-EVL-5's pre-pass keeps its own bound | | |
| 15:46:00 | `decide-close-px8:<D>` | THE LEAD'S NEXT TASK AT OR AFTER 15:46:00, ahead of every task due but PREREG-EVL-5's pre-pass while meta `evl5:pre:<D>` is not stored (that goes first, under its own bound); a record or verdict pass falling due before `decide-close-px8` ends waits for it. PX-DROP-ON, PX-SURGE-ON, CTRL-PX-ALL-ON: x_D (1Min 15:00-15:29 of every PXU(D) name with no item of the ON span stored before tau), V_D for the zd >= +2 names (<= 300), px_features, px_marks, intents: 32-73 reads at N_U 2,000-6,041, 16-37 s at DATA_INTERVAL when each read returns within 0.5 s | no read sent after 15:46:45; EACH READ'S TIMEOUT min(45 s, 15:46:50 - now); it writes D's px_features and intents only when every read returned, and ends by 15:46:55 (DECISION_MARGIN before 15:47:00) | not started or not finished: PX trades nothing at that close; `decide-px:close:<D>` decides it later (a reported shadow, never judged; no META member) |
| 15:47:00 | `decide-close:<D>` (the lane's, unchanged) | every earlier row; PREREG-EVL-4's and -5's parts (PREREG-EVL-5's 45 s); PREREG-EVL-7's EVL-LRN-ON part under its own 120 s | DECIDE_BUDGET 150 s | as those files say |
| book, the 15:47 tick | THE CLOSE MAIN PASS | every earlier row, as today (PREREG-EVL-5's waiting buys and the room they keep as release 1019h built them, A113); NO BUY OF THIS FILE | as today | as today |
| on the lane's close receipt | `decide-close-meta8:<D>` | THE FIRST TASK THE LANE RUNS AFTER THE RECEIPT: EVL-META-ON: members by section 7.2 (the live PX run's selections; the lane's sources' readings at tau), the walk, its intents | 15 s, never past 15:48:40 | not started or not finished: EVL-META-ON trades nothing at that close; `decide-meta:close:<D>` decides it later (a reported shadow, never judged) |
| book, the 15:47 or the 15:48 tick | THE CLOSE LATE PASS | at the first tick inside the window at which the lane's close receipt of D is in, AFTER the book has planned, in that tick or before, every PREREG-EVL-7 row of D's close that the receipt names (PREREG-EVL-7 section 1.9: a learner's picks are its intents, which that receipt carries; a part the receipt does not name has failed): PX-DROP-ON's and PX-SURGE-ON's buys, once, from the room left after every row planned before them; EVL-META-ON's at the first such tick at which `decide-close-meta8:<D>` has also finished; sent in the same tick | the 15:48 tick (15:48:03 or later) is the last inside the window | not planned: not sent (the shadow keeps every event) |

- WHY IT FITS: this file's close-side bar reads (PX-ON) run in the 45 s between 15:46:00 (when the 15:29 bars reach the
  Basic plan's tape) and 15:46:45, and every read is abandoned by 15:46:50, so the run ends by 15:46:55 and the lane's
  live close run starts at 15:47:00 WHATEVER THE GATEWAY DOES (with the client's own 45 s timeout a read sent at
  15:46:45 could have returned 30 s after it: `final/timing8b.out`). Its state computations (both meta-learners) run at
  their state times and yield; its open-side reads (pm_D reach the tape only at 09:15:00) and both meta-learners' walks
  (which need the lane's decision of the same auction) run in their own runs after the lane's receipt. The earlier
  files' parts keep their own bounds inside the lane's runs, unchanged. What this file's runs move is a record or
  verdict pass by at most 55 s after tau at the close and 60 s after the open's receipt; nothing they would store then
  is read by a real-money row of that auction or changes a judged record (section 4.4).
- TEST (a coder checks it): (i) with a gateway stub that hangs every PX read, `decide-close:<D>` starts at 15:47:00 +- 1
  s and `decide-close-px8:<D>` ends unfinished by 15:46:55; (ii) a record pass due at 15:46:10 starts only after
  `decide-close-px8:<D>` ends, and one started at 15:45:50 ends by 15:46:00; (iii) with meta `evl5:pre:<D>` not stored
  at 15:46:00, PREREG-EVL-5's pre-pass runs before `decide-close-px8:<D>`; (iv) `px-am:<D>` and `prepass-meta` stop
  before their next read or step when a verdict pass falls due, and the verdict pass starts within one read's time;
  (v) with the book's ticks at 15:47:03 and 15:48:03 and the lane's close receipt at 15:47:40, PX-DROP-ON's buys are
  planned at the 15:48 tick after every EVL-LRN-ON buy, and with the receipt at 15:48:20 they are not planned.
- WHAT DOES NOT ALWAYS FIT, stated: PX-DROP-ON's and PX-SURGE-ON's REAL MONEY at D's close needs the lane's close
  receipt before the book's 15:48 tick reads it (the lane's run at most 63 s, less the options path's reads of that
  minute), and EVL-META-ON's needs its own receipt by then too (the lane's run at most 48 s at META's 15 s bound).
  PREREG-EVL-5's part at its 45 s bound with its finish leaves 3 s for every earlier row (PX-ON) and none for META-ON,
  and PREREG-EVL-7's learner part at its 120 s bound leaves none for either (the parts' bounds sum to 180 s against the
  120 s from 15:47:00 to the cut-off). At such closes this file's close rows buy nothing and EVL-META-ON's decision may
  be a catch-up; no earlier row is ever delayed for them. THE JUDGED RECORDS are the shadow of the LIVE decisions
  (sections 3.4, 7.7), which a late receipt does not touch: the power figures of section 6 assume every session's PX
  and META parts are DECIDED LIVE (a session decided by catch-up is never a judged block, so a run with a share q of
  its sessions decided by catch-up needs about 1 / (1 - q) times the sessions to reach a look). The report counts, by
  auction, the parts of this file that were cut, not started or decided by catch-up, and the auctions whose late pass
  did not come (`fw_starve` names them).
- THE REQUEST LOAD (check 2's minor 11): about 1,640-1,790 SIP requests a session at N_U 2,000-6,041 (8.2-8.9 minutes of
  the Basic plan's 200 a minute; `price/fees_and_requests.out` with the controls at 200 names: 520 print-settled events,
  2 prints, 1.5 pages; `final/timing8.out`). Under release 1019h every lane read, this file's included, goes through the
  lane's one slot at DATA_INTERVAL (at most 120 a minute), and this file's reads run only in its own runs on that slot,
  so they never share a moment with the lane's 15:47 reads; the 150-a-minute token bucket over every read of the
  Alpaca data host (score.py, universe.py, run.py's marks, pxdata) is new code (harness H2, section 15), and when it
  ships this file's reads keep the slot's spacing.

## 5. The judges

### 5.1 THE PX SCREEN (PX-DROP-ON, PX-SURGE-ON, PX-GAP-O1)

- PREREG-EVL-6 SECTIONS 1.2, 1.3, 1.4, 2 AND 3 AS FROZEN (sha256 0f67f94e..., section 0), WORD FOR WORD: the run record,
  blocks, values y_s = min(n_s, CAP) x (B_s - 0.0010), the estimand, the 10 bp margin; p (exact at S <= 16, else Monte
  Carlo over 99,999 vectors), q and p_I and their seed strings f"{id}|v{version}|evl6|{tag}S{S}" (with this file's ids
  and versions); alpha(S) = 0.020 for 22 <= S <= 30, 0.006 for 31 <= S <= 40, 0.001 for 41 <= S <= 60; RETIRE first
  (mean a < 0 and q <= alpha(S) + 1e-12), then PASS (p <= alpha(S) with no tolerance, as `screen.judge_look`; >= 30
  TRADABLE events and >= 30 distinct issuers; mean a > 0 and mean r > 0; the money's events' pooled mean a > 0 and mean
  r > 0; the control condition; p_I <= 0.10); the minimums; the horizon that ends the RUN, never the version; finality
  and freezing; runs and stays; Sized; demotion by the fixed reads at p <= 0.15, the 10% whole-stay money stop and the
  stay's lower tail; re-promotion by a fresh run; retirement only by RETIRE. Every run of a PX version is charged when
  it starts and starts only when the lane's budget holds it (section 6.6).
- THE FIRST LOOK (F1): the frozen 22nd block. F1 asked for the earliest first look, nothing else changed, whose worst
  plausible per-run false-pass rate within 120 sessions is <= 0.13 on fresh seeds under the frozen plausible grid; the
  frozen schedule's own first look holds it (0.119 +- 0.005 at the worst cell, section 6.2), so no later look is taken:
  looks at S_k = 22, 25, 30, 35, 40, 50, 60, exactly PREREG-EVL-6 section 2's.
- AND F4's CAP: the frozen text's 14 in the values and in the money's events reads as the open cap of the version's band
  at the look: 4 for a PX version's run (judged in learning: `event.max_open_v8.learning`), 14 for a Probe stay, 8 for a
  Sized stay. So a PX run's values weigh each block by the events learning money can buy (min(n_s, 4)) and its top guard
  reads the top 4 of each block in the seat's ranking. CAP IS A CONSTANT OF THIS TEXT (re-check 2's minor): 4 for a PX
  run, 8 for a META run, 14 for a Probe stay, 8 for a Sized stay, whatever any money row holds (as PREREG-EVL-6 fixes
  its 14); the money row `event.max_open_v8.learning` sizes real money only and never reaches a judge.
- A PROBE STAY (check 2's minor 15): its lower tail (PREREG-EVL-6 section 3, DEMOTION 2) and its Sized PASS are read at
  the frozen looks from the 22nd stay block (S_k = 22, 25, 30, 35, 40, 50, 60), as PREREG-EVL-6 states them: with no
  later first look, the stay's lower tail is not delayed.
- PREREG-EVL-3's screen never judges a PX seat (on the PX designer's generator it passes a null PX seat 0.229 of the
  time at that designer's worst cell: `price/px_calib.report.txt`, its skew check omitted, an upper bound).

### 5.2 THE META SCREEN (EVL-META-O1, EVL-META-ON)

- PREREG-EVL-6 sections 1.2, 1.3, 1.4, 2 and 3 AS FROZEN, word for word, with its own schedule (looks from the 22nd
  block) and F4's cap (8 for a run, judged in learning; 14 for a Probe stay; 8 for a Sized stay): the record is the
  meta-learner's own settled TRADABLE picks (section 7.1), its control its POOL (section 7.1), the money's events each
  block's first CAP picks in `rank_key` order (section 7.5), then adv20, then event id.
- Every run charged when it starts (section 6.6); no successor version (F2: the runs of PREREG-EVL-6 section 3 take the
  draft's successors' place).

### 5.3 What both screens are never

Never chosen per program, per session or per outcome; never fed a record, placebo or sub-rule figure; never edited by
the code they judge (league/events/screen.py stays behind ci.py's wall and its judge code for this file is new code,
PREREG-EVL-1 to -7's paths intact). If PREREG-EVL-6 were ever restated, this file's programs keep sections 1-3 as frozen
at 0f67f94e..., with F4's cap (section 5.1).

## 6. The calibration: false passes, power, demotion and the lane's budget (synthetic only)

Every figure below is synthetic, from the named script and seeds; `final/report8f.py` prints every one of them into
`final/report8f.txt` from the stored outputs. P(...) is a share of simulated programs; "within 120 sessions" counts a
run's looks to its 60th block as PREREG-EVL-6 section 2 holds them.

### 6.1 THE PX PLAUSIBLE GRID AND F1'S PROTOCOL (`final/px_final8.py`, `final/px_select8.py`)

- THE GENERATOR is the PX designer's (`price/px_calib.py` `generate`; `px_final8.py selftest` checks that with no
  addition on it draws exactly that function's arrays): high-beta losers against a crash-prone index benchmark, Zipf
  repeat issuers, hot sectors, a persistent family drift AR(0.97), left-skewed events with distress jumps (80% down),
  persistent issuer effects, counts that follow the volatility regime, a control block. Added, as PREREG-EVL-6's
  `calib_v2.py` builds them (each day still mean 0 and variance 1): crash days with a t(3) body, crash days clustered in
  high-volatility regimes (p_t = 0.05 exp(2 x_t) / E[exp(2 x)], at most 0.09, on the generator's own volatility state),
  both together, the benchmark's crash days in the same shape, and counts that follow the size of the day shock (x
  exp(0.3 min(|eps_t|, 4)) / its mean) with the null set on money weights min(n_t, 4) (the money knife). THE SCREEN is
  run by PREREG-EVL-6's frozen calibration code, imported unchanged: `calib_final.py`'s record (its arrays, its
  sign-flip and issuer p, its prefilters and Monte Carlo shortcuts) and `search_final.py`'s rule evaluation
  (`first_pass`, `two_runs`), with CAP 4 (F4).
- THE PX PLAUSIBLE GRID (1,590 cells): the knife-edge null (every event's mean a exactly 0, its control at -30 bp, so
  "beats its control" never protects: also the no-control figure) with the PX designer's structure at its worst
  plausible levels (loser betas of 1.3 against a benchmark with crash days, issuer effects of 1%, sigma_i 1.5-6%, jumps
  at 0.5% an event) crossed with PREREG-EVL-6's frozen grid: the residual day shock sd_c 0, 1.2% and 2.2% a session
  (PREREG-EVL-6's rho_day 0, 0.05 and 0.15 in the absolute units its section 4.2 states; on the PX generator's own event
  variance rho_day 0.15 would be 1.75%, so the grid reads high); phi_day 0.10, 0.15, 0.20 (at sd_c > 0); days symmetric
  t(3), crash days with a normal or a t(3) body, clustered or not; events symmetric or left-skewed; a drift of 0, 10 or
  20 bp (AR 0.97); 3, 5, 8, 20 or 40 qualifying names a session as the PX designer's Poisson means (about 2.9, 4.8, 7.5,
  13.9 and 26.9 events a session after the K cap and one event per issuer), or counts that follow the day at 3, 5 and 8.
- F1'S PROTOCOL (`px_select8.py`, written before any fresh figure existed): (1) SEARCH SEEDS (from 171,000,001, 1,000
  programs a cell over the whole grid) give each candidate first look F = 22, 25, 30, 35, 40 (the frozen thresholds, the
  looks the frozen list's from F on, nothing else changed) its worst plausible rate; (2) every cell within 3.5 points of
  the search worst of F = 22, 25 and 30 (18 cells) is re-run on FRESH SEEDS (from 172,000,001, 4,000 programs a cell);
  (3) THE RULE: the earliest F whose worst plausible per-run false-pass rate within 120 sessions, the fresh rate where
  re-run and else the search rate, is <= 0.13; (4) the chosen F's 16 worst fresh cells are re-run on CONFIRMATION SEEDS
  (from 173,000,001, 4,000 programs a cell) that chose nothing.

### 6.2 THE PX SEATS' FALSE PASSES (per run, within 120 sessions)

| first look | search seeds' worst | fresh seeds' worst | holds 0.13 |
|---|---|---|---|
| 22 (the frozen) | 0.143 | 0.1190 +- 0.0051 | yes: CHOSEN |
| 25 | 0.125 | 0.1045 +- 0.0048 | yes |
| 30 | 0.103 | 0.0803 +- 0.0043 | yes |
| 35 | 0.067 | 0.0505 +- 0.0035 | yes |
| 40 | 0.049 | 0.0390 +- 0.0031 | yes |

- WORST PLAUSIBLE, PER RUN, at the frozen first look: 0.1190 +- 0.0051 on the fresh seeds that chose it (t(3)-body crash
  days clustered in high-volatility regimes, left-skewed events, a 20 bp drift, sd_c 2.2%, phi_day 0.20, about 27 events
  a session); 0.1165 +- 0.0051 at the same cell on the confirmation seeds that chose nothing; 0.1177 +- 0.0036 pooled
  over 8,000 programs. The search seeds' 0.143 (the same days with symmetric events, the maximum of 1,590 cells of 1,000
  programs, which reads high) is 0.104 fresh and 0.112 on the confirmation seeds. Every plausible cell not re-run reads
  <= 0.105 on the search seeds; every confirmation cell <= 0.1165. RE-CHECK 1 rebuilt it on its own seeds and confirmed
  it (`recheck1__rc_px.py`: worst 0.1090 +- 0.0049 over 103 cells x 4,000 and 0.1091 +- 0.0035 over its 12 worst x
  8,000 on seeds that chose nothing; `recheck1__rc_engine.py`, an independent implementation of the frozen text on the
  same arrays, 0.1105 per run against this pipeline's 0.1095): the frozen first look holds 0.13.
- BY SHAPE (the maximum over the drifts and the count rates; fresh seeds where re-run, else search seeds; rho_day /
  phi_day columns: 0 / 0.10, 0.05 / 0.10, 0.15, 0.20, 0.15 / 0.10, 0.15, 0.20): symmetric days .036-.071; crash days
  with a normal body .038-.093; a t(3) body .042-.103; clustered .043-.107; t(3)-body clustered .049-.119; counts that
  follow the day read at most .098. The rate climbs with the day shock's
  size, its persistence, its fat tails and its clustering, as PREREG-EVL-6 section 4.4 found on its own generator.
- BASE (the PX designer's base: a 0.4% residual day shock, t(3) days, no drift, betas of 1, no issuer effect):
  0.007-0.019 at 3-27 events a session (`px8f.base`, 4,000 programs a cell, seeds from 176,500,001); the knife edge and
  the plain null alike.
- PER VERSION (two runs within 120 sessions, D11's reading): 0.214 at the worst cell on the fresh seeds, 0.206 on the
  confirmation seeds (about 1 - 0.88^2). Each run is charged when it starts (section 6.6).
- STRESSES (`px8f.stress`, 2,000 programs a cell, seeds from 174,000,001; reported, not binding): a 30 bp drift at the
  corner 0.143 (27 events a session) and 0.118 (7.5); phi_day 0.25 at the corner 0.1315, at clustered crash days with a
  normal body 0.1185; rho_day 0.30 (sd_c 3.4%) at the corner 0.125; loser betas of 1.5, 0.100-0.102; the PX designer's
  own worst cell (sd_c 1.5%, phi_day 0.25) 0.066-0.089 and stress cell (2.2%, phi_day 0.25, a 30 bp drift, betas of 1.5,
  1% jumps 90% down) 0.092-0.114. Above 0.13: only the 30 bp drift and phi_day 0.25 at the t(3)-body clustered corner.
- SENSITIVITIES at the corner (`px8f.sens`, 4,000 a cell, seeds from 177,500,001): no issuer effects 0.121, the seat's
  real control at 0 (the control condition able to bind) 0.114, betas of 1.0 0.116: the corner's rate is the day
  shapes' and the drift's, not the PX structure's.
- MONEY'S POPULATION (check 1's attack, `px8f.money`, 2,000 a cell, seeds from 176,000,001; NOT a null of PREREG-EVL-6's
  estimand, whose money-weighted all-event mean is positive here; measured and stated, as F4 keeps the frozen form):
  with the top 4 events of each session at 0 bp and the rest at +40 / +60 bp, the screen passes 0.260 / 0.501 at the
  base and 0.271 / 0.361 at the corner; with the top 14 at 0 bp and the rest at +40 / +60 bp, 0.074 / 0.153 at the base
  and 0.176 / 0.212 at the corner; with the top 4 (14) at -15 bp and the rest at +80, 0.454 (0.119) at the base. The
  frozen top-CAP guard is a sign condition on pooled means, not a test (PREREG-EVL-6 section 1.2 says so): it does not
  hold a seat whose bought names earn nothing while its unbought ones earn. What money then buys at Probe (the top 14)
  is read by the stay's fixed reads on real-money r (section 6.4: a Probe stay whose money earns nothing is demoted
  0.37-0.41 of the time by its 1,000th Probe+ event).
- TWO ON SEATS SHARING ONE NIGHT (check 1's SHARED; re-check 1's minor 3). PX-DROP-ON and PX-SURGE-ON hold the same
  night against the same benchmark. Sharing ONLY the ON universe's drift (`px8f.shared`, 4,000 a cell, seeds from
  176,800,001), at the corner both pass falsely 0.0200 of the time against 0.0129 if they were independent (P(the
  second | the first) 0.18), 0.0307 against 0.0167 with a 30 bp drift. Sharing EVERY DAY-LEVEL SHOCK (the volatility
  regime, the residual day shock, the benchmark's move and crash days, the sector shocks; events, issuers and counts
  independent: `final/px_shared8day.py`, re-check 1's construction, 4,000 a cell, seeds from 183,000,001), both pass
  falsely 0.0715 against 0.0122 (P(the second | the first) 0.63; their session blocks correlate 0.86) at the corner
  with 26.9 events a session, 0.0605 against 0.0121 with 13.9, and 0.061 against 0.0084 with normal-body crash days
  (re-check 1's seeds: 0.0755, 0.0555, 0.0535). A real pair sits between the two (0.020-0.072 at the corner: P(the
  second | the first) 0.18-0.63). The charges add regardless; the report counts two PX seats promoted within 20
  sessions of each other, and EVL-META-ON with a PX ON seat when most of its picks are PX-sourced, as one mechanism
  (section 10).

### 6.3 THE PX SEATS' POWER (`px8f.power`, 2,000 a cell, seeds from 175,000,001; the edge on every event, judged a)

P(promoted) by the 25th / 40th / 60th session of run 1, within 120 sessions (run 1), and within 120 sessions with run 2
(per version), at a true 40 and 60 bp judged edge (54 and 74 bp gross of the replay's 14.16 bp):

| cell | events a session | 40 bp: by 25 / 40 / 60; 120; two runs | 60 bp: by 25 / 40 / 60; 120; two runs |
|---|---|---|---|
| base (the PX designer's) | 26.9 | .332 / .453 / .485; .485; .736 | .676 / .816 / .868; .870; .983 |
| base | 13.9 | .249 / .336 / .348; .351; .561 | .526 / .646 / .694; .703; .901 |
| base | 7.5 | .161 / .229 / .238; .244; .409 | .340 / .465 / .491; .514; .753 |
| rho_day 0.05, symmetric | 26.9 | .238 / .312 / .327; .327; .532 | .460 / .581 / .617; .618; .852 |
| the worst plausible corner | 26.9 | .250 / .322 / .341; .341; .548 | .349 / .441 / .465; .466; .701 |
| the worst plausible corner | 7.5 | .175 / .236 / .245; .249; .440 | .258 / .341 / .356; .371; .599 |

- No PX seat is promoted before the 22nd block of a run, at any edge. At the corner every figure includes its own
  0.12 null rate. At 20 / 30 bp the base passes 0.107 / 0.257 within 120 sessions (26.9 a session); at 80 / 100 bp,
  0.983 / 1.000.
- WHAT THE FROZEN FIRST LOOK COSTS against the judge's withdrawn PX screen (looks from the 15th block, alpha 0.016 /
  0.004, on the designer's seeds: 0.556 / 0.915 at 40 / 60 bp, base, 40 names a session): about 7 and 5 points within
  120 sessions and about seven sessions of the earliest promotion (its first look at the 15th block); that screen's
  own worst, 0.106 / 0.097 on the designer's grid, was measured without PREREG-EVL-6's widened day shapes, and F1 asks
  for PREREG-EVL-6's schedule unless it fails.

### 6.4 THE PX SEATS' DEMOTION (F3; `final/px_demotion8.py`, 2,000 stays a cell, seeds from 178,000,001)

A Probe stay of one PX seat under PREREG-EVL-6 section 3's FROZEN demotion, word for word (the fixed reads at every
100th real-money Probe+ event, one-sided session-block sign-flip p for a mean below zero <= 0.15 on fill-based r; the
money stop at 10% of the whole stay's buy cost; the stay's lower tail at its looks from the 22nd stay block), real money
buying the top min(n_s, 14) events a session at Probe ($67.9 lots) and the top min(n_s, 8) at Sized ($190 lots), the
move to Sized by the stay's PASS (its control and issuer guards taken as holding: more Sized, larger lots), r = a +
the benchmark's move (the judged cost basis). P(a TRUE +40 bp PX edge is demoted by its stay's 300th / 1,000th /
2,000th / 3,000th Probe+ event). Every stay reaches its 2,000th event (or is demoted before it) in the sessions
simulated; only 35-74% reach their 3,000th, so EVERY 3,000TH FIGURE IS A LOWER BOUND, marked "-" (re-check 1's minor 4,
re-check 2's minor; `report8f.py` marks the same figures "+" or "-" by the share reached):

| cell (sd_c 2.2%, phi_day 0.20, a 20 bp drift unless named) | events a session | 300 / 1,000 / 2,000 / 3,000 | at the 1,000th: reads / money stop / lower tail |
|---|---|---|---|
| crash days (normal body), symmetric events | 26.9 / 13.9 / 7.5 | .129 / .168 / .178 / .181-; .108 / .145 / .151 / .153-; .123 / .146 / .150 / .150- | .163 / .004 / .001 at 26.9 |
| crash days, skewed events | 26.9 / 13.9 / 7.5 | .121 / .159 / .167 / .169-; .123 / .163 / .166 / .167-; .111 / .135 / .138 / .138- | .155 / .004 / .000 at 26.9 |
| clustered crash days, symmetric / skewed events | 26.9 | .114 / .160 / .167 / .168-; .117 / .153 / .160 / .162- | .148 / .010 / .001; .143 / .010 / .001 |
| t(3)-body crash days, symmetric / skewed events | 26.9 | .109 / .142 / .148 / .150-; .102 / .131 / .140 / .141- | .139 / .004 / .000; .119 / .011 / .001 |
| t(3)-body clustered crash days, symmetric events | 26.9 / 13.9 / 7.5 | .107 / .143 / .153 / .155-; .108 / .136 / .142 / .144-; .102 / .126 / .132 / .132- | .136 / .007 / .000 at 26.9 |
| t(3)-body clustered crash days, skewed events | 26.9 / 13.9 / 7.5 | .105 / .141 / .145 / .147-; .108 / .142 / .148 / .150-; .085 / .112 / .117 / .117- | .132 / .009 / .000 at 26.9 |
| the PX designer's base (sd_c 0.4%, no drift) | 26.9 / 7.5 | .032 / .035 / .035 / .035-; .035 / .037 / .037 / .037- | .035 / .000 / .000 at 26.9 |
| STRESS: phi_day 0.25 (the corner; the PX designer's worst; its stress) | 26.9 | .130 / .176 / .184 / .188-; .107 / .129 / .133 / .133-; .133 / .197 / .207 / .211- | |

- F3'S TARGET IS NOT MET EVERYWHERE, and the frozen rule is kept (a judge is never changed per program): by its 1,000th
  Probe+ event a true +40 bp PX edge is demoted 0.131-0.168 at the worst plausible corners with 14-27 buys a session
  (0.112-0.146 at 7.5), above 0.15 at ABOUT HALF OF THE CORNERS MEASURED (re-check 1's minor 4): 5 of 16 on these seeds
  (2,000 a cell), 6 of the 8 re-check 1 re-ran on its seeds from 194,000,001 (4,000 a cell, `recheck1__rc_dem.json`)
  and 7 of 16 on the final step's seeds from 184,000,001 (4,000 a cell, `final/px_demotion8.s184.json`: 0.123-0.166
  over the 16, +- 0.006), 0.151-0.168 where above, mostly with crash days of a normal or t(3) body or clustered in high
  volatility; by its 3,000th at least 0.141-0.181 (lower bounds); 0.035-0.041 at the base. WHAT FAILS
  IN THE FROZEN RULE: its fixed reads (0.10-0.16 of the 1,000th-event figure; the money stop adds at most 0.016 and the
  lower tail at most 0.003). A read tests the sign of the stay's mean fill-based r over session blocks at p <= 0.15, ten
  times by the 1,000th event, and a PX block carries the whole basket's day shock (2.2% a session at the corner,
  persistent at phi_day 0.20) plus the benchmark's crash-prone move through the losers' betas, so a 40 bp edge is a
  small fraction of a block's sd. PREREG-EVL-6 calibrated its reads at a 60 bp edge, where this file's PX seats read
  0.080-0.098 by the 1,000th and at least 0.082-0.100 by the 3,000th (lower bounds: 53-61% of stays reach it).
- A FALSE PASS'S STAY (0 bp): demoted 0.367-0.411 by its 1,000th Probe+ event at the corners, 0.33-0.37 at the base; a
  cost-only one (-15 bp) 0.625-0.646 by the 1,000th and 0.80-0.82 by the 3,000th.

### 6.5 THE META-LEARNERS

- THE SIMULATOR (`final/meta_final8.py` on `final/calib_meta_f8.py`, check 1's copy of the META designer's MRL-EB
  learner and generator with PREREG-EVL-6's frozen-grid day shapes added): each session a pool of about 300 (or 800)
  candidate events at one auction with attributes, the family of 369 sub-rules (base) or 1,535 (wide4, the family's
  cap), the learner exactly as section 7 (K 16, H 60, TAU 30 bp, SF 20 bp, Z 3, MINB 3, WARM 10, settlement lag 2); THE
  SCREEN is PREREG-EVL-6 sections 1.2-3 as frozen in runs (`screen_runs`: looks from the 22nd block, alpha 0.020 / 0.006
  / 0.001, values min(n_s, CAP) x (B_s - 10 bp) with CAP 8, the top-8 guard, the control (the pool's session mean), p_I,
  RETIRE first, the run ends at its 60th block and the next starts); CAP 4 is measured beside on the same picks. A
  replicate is NULL when its picks' true mean is <= 0 (a persistent issuer or family effect gives a selector a real
  forward edge); both P(pass) and P(pass | null) are stated; 600 programs a cell; the nulls to 720 sessions (check 1's
  minor 6) and, in the final step, to the run's end (below).
- WITHIN A HORIZON (the fix round's figures; seeds from 179,000,001; the META designer's worst: rho_day 0.15, crash
  days, left-skewed events, a 20 bp drift, issuer effects of 1%), run 1 within 120 sessions / every run within 720
  sessions (P(pass), then | null). THESE ARE NOT PER-RUN RATES and are not the charge's basis (re-check 1's major 2:
  the per-run figures to the run's end follow the table):

| cell | run 1 by 120 | any run by 720 | picks a session (sessions with picks) |
|---|---|---|---|
| the worst, phi_day 0.10, J 369 | .017 (.006) | .037 (.012) | 0.34 (3.2%) |
| the worst, phi_day 0.20 | .012 (.003) | .040 (.006) | 0.41 (3.8%) |
| t(3)-body clustered crash days, phi_day 0.20 | .018 (.010) | .045 (.019) | 0.37 (3.4%) |
| clustered crash days, phi_day 0.20 | .020 (.003) | .048 (.009) | 0.34 (3.1%) |
| t(3)-body crash days, phi_day 0.20 | .013 (.003) | .043 (.006) | 0.33 (3.0%) |
| the worst, phi_day 0.20, J 1,535 | .023 (.004) | .063 (.007) | 0.56 (4.9%) |
| t(3)-body clustered, no issuer effect, J 1,535 | .018 (.009) | .033 (.019) | 0.41 (3.6%) |
| t(3)-body clustered, a pool of 800 | .013 (.003) | .027 (.003) | 0.26 (2.1%) |
| the knife edge (three true rules at exactly 0 after cost) | .013 (.005) | .050 (.026) | 0.44 (4.1%) |
| no edge (every event loses its cost) | .010 (.011) | .025 (.017) | 0.32 (3.0%) |
| style co-movement of the terciles at 0.6%, J 1,535 | .038 (.022) | .063 (.044) | 0.61 (5.0%) |
| the base (rho_day 0.05, t(3) days, no drift) | .007 (.007) | .025 (.025) | 0.36 (3.4%) |
| REFERENCE: 16 random pool events a session as a fixed program | .080 (.085) | .540 (.462) | 16 (100%) |

- WHY THE TABLE ABOVE IS NOT THE PER-RUN RATE (re-check 1's major 2). (a) THE HORIZON: a null meta-learner picks in a
  few percent of sessions, so its run 1 reaches its 22nd block only after a median of 70-740 sessions (the table
  below), and its looks to the 60th block lie mostly beyond 120 and 720 sessions; PREREG-EVL-6 (its D11) reads a charge
  PER TEST, one run with every look it can make. (b) A STRUCTURE THE GENERATOR OMITTED: every pool event loaded exactly
  1 on the residual day shock, so pool-relative scoring cancelled it by construction; real pools mix high- and low-beta
  names, and sub-rules on VOL, on the price family and on `x:` deciles then carry beta x c_t. The reference row shows
  what the frozen screen does with a program that trades every session (0.080 a run within 120 sessions, 0.540 over
  twelve runs in 720 sessions). CAP 4 reads within 0.01 of CAP 8 in every cell (at most 0.072 over 720 sessions).
- TO THE RUN'S END (THE FINAL STEP; `final/meta_life8.py` on `final/calib_meta_b8.py`, seeds from 182,000,001): the
  same learner and screen, with each issuer's loading on the residual day shock clip(1 + beta_day x its volatility
  z-score, 0.2, 2.5) (beta_day 0.3 PLAUSIBLE at the corner: the PX designer's beta_dev sd; 0.5 a STRESS; beta_day 0
  draws exactly as before, `meta8l.selftest.out`), every cell to 2,500 sessions and every plausible cell whose run 1
  was still open in more than 5% of programs at 2,500 again, on its own seeds, to 4,000 (16 years: the run's end for
  every practical purpose). Run 1's pass share by 120 / 720 / 2,500 / 4,000 sessions (given a null pick record), the
  share of run 1s ended (passed, retired or at their 60th block) by the last session, every run by 720 and by the last,
  and CAP 4 beside (CAP 8 is the seats' rule):

| cell (sd_c 2.2%, phi_day 0.20 unless named; programs) | run 1 by 120 / 720 / 2,500 / 4,000 (given a null record) | run 1s ended | every run by 720 / by the last | CAP 4: run 1; every run |
|---|---|---|---|---|
| beta_day 0.3, t(3)-body clustered crash days, no issuer effect, J 1,535 (800) | .055 / .076 / .083 / .083 (.067) | 0.97 | .101 / .280 | .091; .290 |
| beta_day 0.3, t(3)-body clustered crash days, J 369 (600) | .048 / .072 / .083 / .087 (.073); main seeds to 2,500: .117, 0.78 ended | 0.86 | .098 / .282 | .090; .278 |
| beta_day 0.3, style co-movement 0.6%, t(3)-body clustered, J 1,535 (600) | .053 / .087 / .098 / .098 (.104); main seeds to 2,500: .108, 0.92 ended | 0.99 | .110 / .318 | .097; .305 |
| beta_day 0.3, the worst (crash days, issuer effects), J 1,535 (400) | .037 / .060 / .068 / .068 (.057); main seeds to 2,500: .077, 0.85 ended | 0.97 | .095 / .258 | .068; .263 |
| beta_day 0.3, the base (rho_day 0.05, t(3) days, no drift) (400) | .000 / .005 / .010 (.010) | 0.52 | .007 / .025 | .018; .033 |
| beta_day 0, style co-movement 0.6%, t(3)-body clustered, J 1,535 (400) | .025 / .040 / .065 (.056) | 0.60 | .045 / .100 | .062; .100 |
| beta_day 0, the base (400) | .000 / .007 / .013 (.013) | 0.39 | .007 / .025 | .007; .020 |
| STRESS: beta_day 0.5, t(3)-body clustered, no issuer effect, J 1,535 (600) | .088 / .115 / .118 / .118 (.093) | 1.00 | .217 / .522 | .120; .527 |
| STRESS: beta_day 0.5, t(3)-body clustered, J 369 (600) | .065 / .095 / .103 (.098) | 0.98 | .182 / .385 | .097; .385 |
| STRESS: a 20 bp family drift (selection can chase it) (400) | .055 / .077 / .125 (.068) | 0.63 | .085 / .207 | .102; .193 |

- WORST PLAUSIBLE, PER RUN TO THE RUN'S END: 0.098 +- 0.012 (0.104 given a null record), with beta_day 0.3, style
  co-movement of the terciles and t(3)-body clustered crash days at J 1,535, 99% of runs ended by 4,000 sessions; the
  largest run-1 figure of any plausible cell on any seed set at any horizon is 0.117 +- 0.013 (beta_day 0.3, J 369, the
  main seeds by 2,500, 78% of runs ended; 0.087 by 4,000 on its extension's seeds, 86% ended) (`final/budget8b.out`).
  Re-check 1 read 0.122 +- 0.016 by 2,000 at the beta_day 0.3, J 1,535 cell on its own seeds with 21% of runs open
  (`recheck1__rc_meta_attack_long.jsonl`), where this step's 800 programs read 0.083 +- 0.010 to 4,000. Every reading
  is under 0.13, so the meta-learners are charged PREREG-EVL-6's 0.13 a run (section 6.6), and under the goal's 15%,
  so they are seatable. THE DAY-SHOCK LOADING is what moved them: the same corner at beta_day 0 reads 0.065 by 2,500
  (the fix round's 0.038 was 120 sessions of it). THE BASE: 0.010-0.013 by 2,500 (39-52% of runs ended; re-check 1's
  seeds 0.030). PER VERSION, every run counted (D11's reading, beside the per-run figure as PREREG-EVL-6 prints its
  own): 0.095-0.138 within 720 sessions and 0.23-0.32 by the last session measured at the plausible corners; 0.52 by
  4,000 at the beta_day 0.5 stress (4.9 runs started on average in 4,000 sessions).
- STRESSES (not binding): beta_day 0.5, 0.103-0.118 per run (every run ended); a 20 bp family drift (selection can
  chase it, a real persistent edge in that world), 0.125 by 2,500 (0.068 given a null record; 63% ended); and the fix
  round's to 720 sessions (seeds from 179,500,001): style co-movement at 1.2% a session, 0.037 / 0.077 (0.027 / 0.058
  given a null record); phi_day 0.25 at the t(3)-body clustered corner with J 1,535, 0.037 / 0.075 (0.029 / 0.051);
  rho_day 0.30, 0.010 / 0.028.
- POWER (seeds from 179,800,001; one true rule "r1", three "r3", +40 / +60 / +100 bp after cost on the rule's events,
  every other event at -cost), P(promoted within 120 sessions, every run) / within 240: r1 at the base 0.207 / 0.547,
  0.657 / 0.902, 0.977 / 0.998; r3 0.203 / 0.472, 0.533 / 0.870, 0.962 / 0.997; r1 at the t(3)-body clustered corner
  0.257 / 0.562, 0.570 / 0.847, 0.857 / 0.978; r1 with a pool of 800 0.447 / 0.723 and 0.788 / 0.968 at +40 / +60. THE
  ORACLE (the true rule registered as a fixed program on day 1, K 16): 0.480 / 0.703 and 0.808 / 0.965 at +40 / +60. So
  the meta-learner reaches about 0.43 and 0.81 of the oracle's power within 120 sessions at +40 and +60 bp for one
  charge, without anyone knowing the rule; its picks' true mean is +37 bp of a +40 bp rule and +54 bp of +60. No pick
  before the state holds 10 entered sessions, and no promotion before a run's 22nd block. (Measured at beta_day 0 and
  with every session decided live, section 4.6.)

### 6.6 THE CHARGES AND THE LANE'S BUDGET (F12; `final/budget8b.py`, `final/budget8b.out`, superseding `budget8.out`)

- ONE BASIS (check 2's major 8): every seatable version of this file and every later run of it is charged the larger
  of PREREG-EVL-6 section 5's frozen charge, 0.13 a version or a run, and the version's own measured worst plausible
  per-run rate rounded up to 0.01. PX: 0.119 fresh, 0.118 pooled within 120 sessions (PREREG-EVL-6's own per-run
  horizon, which counts a run's looks to its 60th block: section 6's opening), rounds to 0.12, so 0.13. META (re-check 1's major 2): 0.098 per run TO THE RUN'S END at
  the worst plausible cell, 0.117 the largest figure at any horizon on any seed set (section 6.5), round to 0.10 and
  0.12, so 0.13. Run 1 of the five versions: 5 x 0.13 = 0.65 at REGISTERED_AT_8. Every later run (after a run's 60th
  block or a demotion, PREREG-EVL-6 section 3) is charged 0.13 WHEN IT STARTS and starts only when the lane's budget
  holds it.
- THE LANE'S BUDGET is PREREG-EVL-6's frozen 3.9 (30 x 0.13). USED BEFORE THIS FILE is the SEATING sum, at
  REGISTERED_AT_8, of every seatable version and run of every file and of R3's births, as R3's validator reads it: 1.95
  for PREREG-EVL-6's fifteen versions, 0.13 for each seatable birth registered since (none had when this was written:
  A109), and 0.13 for each seat of ANY FILE REGISTERED BEFORE THIS ONE: PREREG-EVL-7's 2 x c7 if it froze first (0.26
  at c7 = 0.13, its text), and A117's PREREG-EVL-9 (two seats, 0.26) if it froze first. THIS FILE ADDS 0.65. With
  PREREG-EVL-7 and no birth: USED AFTER 2.86 of 3.9, LEFT 1.04 (eight charges); with PREREG-EVL-9 as well: 3.12, LEFT
  0.78 (six); with A104's three day-news births too (if registered): 3.51, LEFT 0.39 (three). The registering
  amendment restates USED and LEFT from R3's validator before the tag is pushed, and this file is not frozen if LEFT
  cannot hold 0.65.
- REGISTRATION ORDER: when the budget cannot hold every run or birth due at a close, they are drawn in their versions'
  registration order (the earliest REGISTERED_AT first, then the id; PREREG-EVL-6 section 3). So, whatever the order in
  which PREREG-EVL-7, PREREG-EVL-9 and this file freeze, PREREG-EVL-6's versions' runs come before this file's, and a
  file frozen before this one draws before it.
- WHAT THIS MEANS, stated: if none of PREREG-EVL-6's fifteen versions passes, their second runs (from about the 60th
  session after REGISTERED_AT_6) alone need 1.95, more than will be left; they start first, and then this file's
  versions' second runs never start: a PX or META version whose run 1 ends unpassed stays in learning (real money at
  learning size) with no run until the budget holds one or the captain restates the budget by amendment. This file's
  lifetime draw is 0.65 plus 0.13 for each later run that starts.
- THE FIVE SEATS TOGETHER (check 1's minor 7): at their worst plausible per-run rates the five versions' first runs add
  3 x 0.119 + 2 x 0.098 = 0.55 expected false passes (0.59 at META's largest figure, 0.117; more when the two ON seats
  share one night: section 6.2), 0.65 on the charge basis. The judge's draft priced them on the done-speed simulator's
  normal-block model (its 0.057); that figure is withdrawn with its schedule.
- EVERY REPORT shows the lane's expected false passes three ways, as PREREG-EVL-6 asks: this file's count (0.13 a
  version or run), the base model (0.02 a PX run: 0.019 rounded up; 0.03 a META run: re-check 1's 0.030 by 2,500
  sessions, the larger of the two base measurements, this step's being 0.010-0.013) and the stresses' worst (0.15 a PX
  run: 0.143 rounded up; 0.13 a META run: 0.125 rounded up), and beside them the per-version figures (a PX version's
  two runs within 120 sessions 0.214; a META version's every run 0.10-0.14 within 720 sessions and 0.23-0.32 within
  2,500-4,000 at the plausible corners).

## 7. The meta-learners (part B)

### 7.1 Programs

- EVL-META-O1 v1: seatable; buys at the OPEN auction of D and sells at the CLOSE of D (hold 1).
- EVL-META-ON v1: seatable; buys at the CLOSE of D and sells at the OPEN of the next session (hold 1).
- Both: section 4's bands; PREREG-EVL-2's limit at entry (shadow and real); PREREG-EVL-1 section 5's costs, returns and
  TRADABLE; one position per issuer per program within 5 sessions (A72), as the shadow keeps it.
- EVL-META-O1-POOL and EVL-META-ON-POOL: free records that never seat and write no intents; a session's events are its
  members ELIGIBLE TO PICK at the decision (section 7.2) with their OUTCOMES (section 7.2). Each is its meta-learner's
  control (section 5.2).
- Each meta-learner counts only its own picks, and only events knowable after REGISTERED_AT_8, for the screen, the
  bands, Sized, demotion, retirement and Done. Nothing in sections 7.2-7.6 is chosen per program, per session or per
  outcome.

### 7.2 Pool, sources, members and the one cutoff

- SOURCES(X) at a decision: every program version registered before that decision, other than EVL-META-* and the
  placebos, with hold 1 and X's entry and exit auctions (O1: D's open to D's close; ON: D's close to the next open):
  seatable programs, records and controls of every file and version, R3's births and their controls, this file's PX
  seats and controls, and later files' rows (PREREG-EVL-7's learners among them). On release 1019g that is 14 sources
  for O1 and 16 for ON (`meta/grid_count.py`); PX adds 2 and 3. Holds of 3 and 5, the C1 rows and the derived POOL
  records (they write no intents) are not sources.
- THE MEMBERS RULE, THE ONE CUTOFF (F6; re-check 2's major 2), stated once. The MEMBERS of (D, X) are FIXED BY STORED
  TIMES ALONE, so the live decision and every catch-up read the same members whenever they run (never by the hour at
  which a run happens to start, the House's downtime included). A source s gives members at (D, X) only through ITS
  LIVE DECISION of (D, X):
  - THE LANE'S FIRST FINISHED DECISION of (D, X) is the earliest receipt `decide-open:<D>` (X = O1) or
    `decide-close:<D>` (X = ON) finished with status `ok` or `pending` (`book.decided`'s reading). A source decided in
    the lane's runs gives members only when that receipt names it (`screen.names` on its summary, as `book.part_hold`
    reads PREREG-EVL-5's part): a part that failed or ran past its own bound, and so is decided later by itself, gives
    none at (D, X).
  - A PREREG-EVL-7 learner gives its intents of (D, X), which its live decision writes once under that receipt
    (PREREG-EVL-7 sections 1.7 and 1.11 item 9: a written decision is never decided again).
  - This file's PX seats and controls give the names THE LIVE PX RUN OF (D, X) (section 1.2 (c)) selected: their rules
    over that run's own px_features rows with the NO STORED ITEM reading of items stored before tau (the real-money
    reading; the intents that run wrote, never the hourly re-decision's). With no live PX run of (D, X) finished, they
    give none, live and in every catch-up alike.
  - Every other source gives its REAL-MONEY READING of entry session D at tau, `book.picks(lane, s, D,
    decided_at=tau)` (PREREG-EVL-1 section 3: events stored before tau, verdicts answered before tau, s's own
    one-position rule over the shadow's intents of earlier decisions), over the eligible rows of ELIGIBLE TO PICK's
    cut-off (below), with the REACT rows' reaction and EVL-NEWS-NIGHT2-ON's gap read from THE MARKS (below; a mark
    missing there takes no pick of that row): PREREG-EVL-7 section 1.3's reading of its pool programs, read the same way.
  No other run's intents are members: never an hourly re-decision's, never a by-itself later decision of an earlier
  file's cut part (`decide-close-evl5`, `decide-open-lrn` / `decide-close-lrn`, `decide-open-births` /
  `decide-close-births`), never a `decide-px` catch-up's.
- THE MARKS of a meta decision of (D, X): D's `1530` and `0930` marks (the lane's `marks`) and its `px1530` mark (the live
  PX run's `px_marks`), each read only when its bar ends before tau and it was stored (`fetched_at`) at or before the
  finish of the lane's first finished decision of (D, X) (a `px1530` mark: written by the live PX run of (D, X));
  otherwise missing.
- MEMBERS of D: one per issuer with a pick read by the rule above. Its EVENT: the earliest-knowable such pick's event
  (ties: the lowest id). Its TAGS: the sources giving one. Members, events, tags and features (section 7.3) are written
  once at the decision (`mrl_pool`) and never recomputed. `decide-open-px8:<D>` is the first task the lane runs on its
  open receipt (its META part after its PX-GAP-O1 part) and `decide-close-meta8:<D>` the first on its close receipt
  (section 4.6); a meta decision not made live is decided by `decide-meta:<X>:<D>`, oldest first (the state of section
  7.4 is built in session order), with the same rule and so the same rows.
- TEST (a coder checks it): EVL-META-O1 on a synthetic D with a PX-GAP-O1 pick holds it as a member, live (inside
  `decide-open-px8:<D>`) and in a `decide-meta:open:<D>` catch-up alike; an event stored after tau that the hourly
  re-decision adds to a source's intents after the lane's first run is a member of neither; with PREREG-EVL-5's part of
  `decide-close:<D>` cut, no PREREG-EVL-5 row gives EVL-META-ON a member of D, live or after `decide-close-evl5:<D>`
  has run; a catch-up run a day later writes the same `mrl_pool` rows as the live decision.
- ELIGIBLE TO PICK: a LIVE universe row for D: the lane's LIVE-rule eligible result for (D, CIK) whose
  `eligibility.decided_at` is AT OR BEFORE THE FINISH of the lane's first finished decision of (D, X) AND NEVER LATER
  THAN THE META-LEARNER'S ENTRY AUCTION OF D (09:30 ET of D for EVL-META-O1, D's close for EVL-META-ON), the earlier of
  the two bounds (PREREG-EVL-7 section 1.1's E5, stated here in full; re-check 1's minor 5); a result written later, or
  none, makes the member not eligible to pick; or, for a member whose only sources are PX rows, px_universe's live row
  of D, stored before tau. And: the member's event knowable after REGISTERED_AT_8 (and after the version's
  registration time); TRADABLE at the decision (1.25 x prev_close <= 10% of the equity at P's close); not held by the
  meta-learner within 5 sessions (A72).
- A MEMBER'S OUTCOME (F9; re-check 2's minor, one reading): the settled outcomes row, under the FIRST TAG in programs.py's
  PROGRAMS order and then ascending version that holds one, of THAT TAG'S INTENT OF THE ISSUER entering at D's X auction
  with the member's exit auction (each tag prices the same issuer at the same two auctions; PREREG-EVL-7 section 1.1's
  POOL OUTCOME reading). An outcome whose RAW ENTRY PRINT was above 1.25 x the raw SIP close of the session before D
  (PREREG-EVL-2's LIMIT AT ENTRY, which some controls do not apply) is NO OUTCOME: it is neither a state input (section
  7.4) nor a POOL value. Only TRADABLE outcomes enter any figure. This is PREREG-EVL-7 section 1.1's exclusion for its
  pools, read the same way.

### 7.3 Features and the grid (records, free)

- FEATURES are binary, from rows stored before tau (section 1.2 (a)) and, for the marks, THE MARKS of section 7.2
  (section 1.2 (c)); a missing input switches its group off.
  - FAM: news-on (an article knowable before 09:00 ET of D), news-day, 8k (no item 2.02), ern (item 2.02), ins (Form
    4), price (an event of a PX seat or control).
  - SCORE, from the event's first stored `ok` PROMPT-NEWS or PROMPT-DOC verdict answered before tau: s>=1, s>=2, s=3,
    s<=-1 (nested); else smiss. GUIDE: raised, lowered. SRC (articles; the source lower-cased): bz = "benzinga"; other.
  - HOUR (knowable time): [16:00, 20:00), [20:00, 04:00), [04:00, 08:00), [08:00, 09:30), [09:30, 12:00), [12:00,
    16:00).
  - COV: single-symbol articles naming the symbol, knowable in the 72 hours before the event and stored before tau, the
    event excluded: 0, 1-3, >= 4.
  - LIQ (the universe row's adv20): < $10M, $10M-$100M, >= $100M. PX (prev_close): < $10, $10-$50, >= $50.
  - From the 20 raw closes of the sessions before D (the lane's `bars`, else px.sqlite `px_bars`, READ AS STORED
    WHATEVER THEIR WRITE TIME: PREREG-EVL-7 section 1.1's reading of bars of sessions before D, which carry no
    information about D or later; all present): VOL, the sd of the 19 log returns: < 2%, 2-4%, >= 4%; R5, P's close
    over the close 5 sessions before P, less 1: <= -5%, between, >= +5%; R20, P's close over the first of the 20, less
    1: <= -10%, between, >= +10%.
  - ON only: REACT, D's 15:30 mark (the lane's `1530` label, else the live PX run's `px1530`; THE MARKS, section 7.2)
    over prev_close: <= 0.96, between, >= 1.04; GAP, D's 09:30 mark (`0930`) over prev_close: <= 0.98, between,
    >= 1.02.
- GRID: every feature, and every pair of features from different groups: O1 39 features in 11 groups, 720 sub-rules;
  ON 45 in 13 groups, 969 (`meta/grid_count.py`). Ids `g:<f>` and `g:<f1>&<f2>` (Python string order).
- PROGRAM EXPERTS: each source s is the sub-rule `p:<id>:<version>`, the members tagged s.
- PX RECORD EXPERTS (the bridge from part A's free records to real money): each record of `px_grid8.json` whose window
  is X's (O1 records for EVL-META-O1, ON records for EVL-META-ON; C1 records never) is the sub-rule `x:<record id>`: the
  members whose issuer the record selects on D, read from the record's values in the px_features rows of THE LIVE PX
  RUN OF (D, X) (section 1.2 (c); the deciles over PXU(D), the news filter with items stored before tau, the tier).
  With no live PX run of (D, X) finished, every `x:` sub-rule is empty at (D, X), live and in every catch-up alike. A
  member outside PXU(D) is in no such sub-rule. About 184 records for O1 and 173 for ON.
- LEDGER EXPERTS (only if harness H6's rule ledger ships): each ledger rule whose stream is a source of X, registered
  before the decision, is the sub-rule `l:<rule>:<version>`, joining oldest registration first.
- FAMILY = grid + program experts + PX record experts (+ ledger experts): about 925 for O1 and 1,170 for ON at
  REGISTERED_AT_8, NEVER ABOVE 1,535 (the largest family calibrated). It is defined by rule: a later source joins with
  no change here, asleep until it holds MINB settled blocks. AT THE CAP (check 2's minor 16 (a)) a new program expert
  joins only in place of the newest ledger expert; with none to drop, it never joins; a ledger rule beyond the cap never
  joins. No sub-rule seats, trades, is screened, is reported by figure or costs an expected false pass.

### 7.4 State (forward-only; recomputed at every decision from stored rows)

- THE STATE TIME sigma of a decision: 09:00:00 ET of D (EVL-META-O1) or 15:30:00 ET of D, the close - 30 minutes on an
  early close (EVL-META-ON). The state reads only outcomes settled before sigma; its pre-pass (section 4.6) computes it
  at sigma and stores it write-once (`mrl_state`, with the run id); the META part reads the stored state, or computes
  the same state itself from the same stored times.
- THE STATE'S SESSIONS: every entry session from Oct 20, 2026 (the lane's first full session) on, each with its members
  as of its own decision (for a session before REGISTERED_AT_8, or before the release, by section 7.2's members rule,
  whose inputs are fixed by stored times, decided once by the catch-up of section 8; such a session has no live PX run,
  so no PX member and no `x:` membership). Training on sessions before registration is not
  counting: only picks after REGISTERED_AT_8 are judged (PREREG-EVL-7's learners train the same way).
- Session s ENTERS the state when every due TRADABLE member of s is settled (`settled_at` before sigma) or terminal, or
  once 3 sessions have passed after its scheduled exit; a member still unsettled then counts a = -0.30 until a state
  after it settles (the reading that trades less; the red team's censoring cause).
- Per entered session: P_s = the mean a of its TRADABLE members' outcomes (`math.fsum`); v_s = the sum of
  clip(a - P_s, +-0.10)^2 over (n_s - 1); sigma2 = max(0.015^2, the mean of v_s over the entered sessions).
- Per sub-rule j with n_js >= 1 (features and tags as written at s): R_js = the mean a of its members less P_s;
  V_js = SF^2 + sigma2 / n_js; entered sessions 1..N weigh w_i = 2^(-(N - i)/H); A_j = sum w / V; G_j = sum w R / V;
  NB_j = the sessions with n_js >= 1.
- Posterior: prec_j = A_j + TAU^-2; m_j = G_j / prec_j; LCB_j = m_j - Z prec_j^(-1/2).

### 7.5 Decision

- AWAKE: NB_j >= MINB and j holds an eligible member. QUALIFIED: -cbar_D + LCB_j > HURDLE, cbar_D the mean replay
  round-trip cost (score.py's model) of D's eligible members: the pool's level is taken as gross zero; no level is
  learned (PREREG-EVL-7's V1), so day shocks and drifts cannot time the picks.
- WARM (check 2's minor 10): no pick until the state holds at least 10 ENTERED sessions (section 7.4, counted from Oct
  20, 2026, not in entry sessions after REGISTERED_AT_8; the port calls `meta_spec.walk` with session_index = the number
  of entered sessions), and none before the first decision after REGISTERED_AT_8.
- THE WALK: qualified sub-rules in descending LCB (ties: the larger NB, then the id); each gives its eligible members
  not yet taken, by adv20 descending then event id, until K are taken. Nothing is random.
- WHAT IS WRITTEN (F8): each pick is an intent with `rank_key` = K + 1 - its walk position (an integer, higher first)
  and `why` = "mrl"; NO LCB, sub-rule id or figure is written into `intents.rank_key`, `intents.why`, a receipt summary
  or any table the report, the site, births or the captain read. The walk (each pick's position, the sub-rule that gave
  it as h = sha256("EVL8-MRL|" + id) truncated to 16 hex digits, its LCB, NB and the qualified count) is written to
  `mrl_walk` only; the state to `mrl_stats` and `mrl_state`; the members to `mrl_pool`. Every mrl_* table is on births'
  FACTS_DENY and the report's deny list (section 10).

### 7.6 Constants (fixed now, from the synthetic calibration only)

K = 16; H = 60 sessions; TAU = 0.0030; SF = 0.0020; Z = 3.0; HURDLE = 0; MINB = 3; WARM = 10 entered sessions; the
variance floor 0.015^2; winsorization +-10%; imputation -0.30 after 3 sessions; the family cap 1,535.

### 7.7 Real money, runs, catch-ups

- The book's picks of a meta-learner for D are its intents of D in rank_key order, then adv20, through every book skip
  and ROOM (section 4), in the late pass (section 4.6). A META part that did not finish in its bound is never traded at
  that auction. EVL-META-ON never buys a member barred by PREREG-EVL-4's NEXT_OPEN_GUARD with RAISED_GUARD (every 8-K of
  the issuer knowable at or after 09:00 ET of D and stored before tau with a stored PROMPT-DOC verdict `ok` and score >=
  2, or `ok`, score >= 1 and guidance "raised", or no answer by tau: PREREG-EVL-7's E10 reading); EVL-META-O1 never buys
  an ERN(D) issuer (an 8-K with item 2.02 knowable in D's close window and stored before tau, PREREG-EVL-7's E8
  reading). The shadow keeps every pick.
- RUNS, NOT SUCCESSORS (F2): a meta-learner version's runs, Probe stays, demotion and re-promotion are PREREG-EVL-6
  section 3's as frozen: the 60th block ends the RUN, never the version; RUN n + 1 starts with the next block, judged on
  its own record with its own tag, keeping section 7.4's state (the state is the algorithm's, not the record's), charged
  when it starts and started only when the lane's budget holds it (section 6.6). The draft's successor versions v2 and
  v3 are withdrawn.
- AMBIGUITIES are read as section 15 says, fixed by amendment before the first pick; a later resolution is a new
  version.

## 8. The decisions before the release

- PART A: no PX event of a session before the first session whose inputs the release's recorder stored before its
  decision time exists (section 1.3: nothing is computed from a later adjusted series). The universe's operating-company
  cache (2,000-18,123 SEC reads, `price/fees_and_requests.out`) and the 270-session backfill of daily bars (120-372
  requests) are filled the night before the first live PX decision; the PX record, the records' panel and the placebos
  begin at that session.
- PART B: every session of the state from Oct 20, 2026 up to the first decision the release makes live is decided ONCE
  by a CATCH-UP (`decide-meta:<auction>:<D>`), oldest first, exactly as of its own decision (section 7.2's members rule,
  fixed by stored times; the state as of its sigma), by the release's code, whose commit sha each receipt records, and written once: a session
  before REGISTERED_AT_8 builds the state only (members and their outcomes; no pick, by WARM and section 7.5), a session
  from REGISTERED_AT_8 on is also a reported shadow of picks. THESE DECISIONS ARE NEVER JUDGED AND NEVER TRADED
  (PREREG-EVL-7 section 1.7's rule for its learners' catch-ups: code written after outcomes exist never reaches a judged
  block).
- Real money and every judged record start at the first decision after the release is live, with every wall.

## 9. Pivot (part A is a lane)

Count every settled real-money PX event AT PROBE SIZE OR ABOVE from PX's first fill (PREREG-EVL-3 section 5's "such
events"; check 2's minor 12); learning events are reported beside and never counted. At 400, if the 95% issuer-block
bootstrap upper bound of their per-event after-cost return is below zero, the PX seats take no new entries, their room
goes to the other lane, and the records and placebos continue for free. The meta-learners are judged as programs, not
as a lane.

## 10. Reporting (no leaderboard)

- The daily report gains a PX block and a META block, COUNTS ONLY. PX: N_U, the FLAGGED share, the share with premarket
  bars, panel rows written and settled, each seat's qualifying names, shadow K, real picks, fills, binding constraint
  and venue cancels, the controls' counts, the basis (mean and p90 of |bar - print| per side, in bp: an execution
  fact), requests used against the plan (200 a minute), the pivot count, the audit's state (how many placebos have
  passed: a count), the parts cut, not started or decided by catch-up and the auctions whose late pass did not come
  inside the window (section 4.6), the PX universe's auctions lost to a late morning pass. META: members, members
  eligible to pick, picks written, imputed members, decision status (live, cut, catch-up), the share of each run's
  sessions decided live.
- Every seatable program's own record (its events, intents, fills, settled n, P&L by band, its looks) is reported as
  every program's is (the goal's report).
- NEVER REPORTED BY FIGURE, and never read by any designer, judge or captain of a later file (F8): a record's,
  placebo's, panel's or sub-rule's return, mean, look, LCB, rank, weight, identity or qualified count (`px_record_days`,
  `px_panel` outcomes, `mrl_pool`, `mrl_stats`, `mrl_state`, `mrl_walk`, the placebo screens' p). They are machine-only
  inputs of pre-registered forward-only consumers. births.py's FACTS_DENY gains `mrl_pool`, `mrl_stats`, `mrl_state` and
  `mrl_walk`; births' facts and its validator's Jaccard never read a row of this file's programs, controls, records or
  placebos, EVL-META-* included (section 4.4); px.sqlite is never attached to a births connection.
  THE NO-LEADERBOARD TEST: no report, site page or receipt summary renders an EVL-META intent's sub-rule, hash or LCB or
  any mrl_* figure.
- Beside Done's issuer-block bound the report shows the same bound with SESSION blocks and the market-direction share
  (the red team's `rt_done_beta.py`: a long-only book's issuer-block bound is carried by the market's direction; Done
  itself is the owner's and unchanged), and counts AS ONE MECHANISM beside Done's ">= 3 programs" line (check 1's
  minor 7; re-check 1's minor 3; section 6.2): two PX seats promoted within 20 sessions of each other; and EVL-META-ON
  with a PX ON seat promoted within 20 sessions of it when more than half of EVL-META-ON's run's picks are PX-SOURCED
  (the issuer has an intent of PX-DROP-ON, PX-SURGE-ON or CTRL-PX-ALL-ON of the same (D, ON): read from intents only,
  never from an mrl_* table), and EVL-META-O1 with PX-GAP-O1 the same way. Done itself is unchanged.

## 11. The red team's causes and their guards

The red team (`evl8/redteam/`, synthetic: rt_mde, rt_done_beta, rt_meta, rt_placebo, rt_dilution, rt_budget) assumed
that six weeks from now the swarm has lost money and found nothing, and ranked the causes. Each gets a guard here, or
the reason it cannot be guarded.

| # | cause (the red team's) | guard in this file or its harness | what cannot be guarded |
|---|---|---|---|
| 1 | NO EDGE BIG ENOUGH TO DETECT: a session block carries the basket's day shock, so a 60-block test needs about 45-85 bp judged (rt_mde: 80% power, one look at alpha 0.01, 30-60 blocks, 18-300 events a session) | stated power (section 6.3); the records keep accruing free forward evidence; the meta-learners concentrate slots on any sub-rule that clears its LCB | the physics: no test that holds its level passes a 20-30 bp edge reliably inside 60 blocks |
| 2 | MARKET BETA CARRIES RAW P&L AND DONE'S BOUND: long-only baskets of losers and surgers are high beta; at zero alpha Done's issuer-block items hold 21-31% of the time from the market's direction (rt_done_beta) | every screen needs mean a > 0 AND mean r > 0 and beats its control; the report's session-block bound and market-direction share beside Done's; a false Done also needs three false promotions | Done is the owner's; this file cannot change its bootstrap |
| 3 | COSTS AND FILL RATE AT THE AUCTIONS: about a quarter of opening entries cancelled by the venue (A80); fees of 8-20 bp a round trip on $38 lots (`price/fees_and_requests.out`) | judged cost 14.16 bp a round trip (PREREG-EVL-1 s5) against 0.0 bp measured slippage (EXECUTION-FACTS); A80's re-send; the shadow keeps every event; the report's fill gap by program; Done's 15 bp fill rule; the $5 price floor; fees fall 10-30x at Probe and Sized | the venue's cancel cause is unknown (A80) |
| 4 | ADVERSE SELECTION OF FILLS: a limit-on-close at 1.25 x the previous close fills unless the cross runs above it | PREREG-EVL-2's limit applies to the shadow too (an entry above it is skipped in both) and to every meta-learner member's outcome (section 7.2); the report counts non-fills against the shadow's moves | none needed beyond counting |
| 5 | LONG-ONLY AGAINST OVERREACTION: half of every reversal premium is the short side | the PX seats are the long sides (buy the no-news drop, the attention close, the pre-market drop) | the walls forbid shorts; never weakened |
| 6 | CROWDING AND DECAY: daily contrarian profits fell (Khandani and Lo 2011); published anomalies decay (McLean and Pontiff 2016) | forward-only judges; runs of 60 blocks; the meta-learners' forgetting (H = 60); PX's pivot at 400 Probe+ events | an edge may decay after promotion; the stay's fixed reads and the money stop demote it |
| 7 | SURVIVORSHIP OR LOOK-AHEAD IN THE UNIVERSE OR THE DATA: upserted bars, corporate actions, the SIP clamp | ONE CLOCK (section 1.2); write-once `px_features` with its run, `inputs_at` and `bar_end`; the live rule for PXU(D) decided before tau; ONE ADJUSTMENT BASIS a window and catch-ups that read only what was stored before tau (section 1.3); FLAGGED(D); the 16-minute SIP clamp on every read; THE PLACEBO AUDIT AND THE CONTROL CANARY (section 3.3) | an action the vendor adjusts only after the morning pass dilutes a seat with a null event (its outcome is computed on adjusted ratios, so it cannot fake an edge) |
| 8 | MULTIPLICITY ACROSS SUB-RULES AND LEARNERS: selection from hundreds of noise rules (rt_meta; rt_dilution: S* = 2 ln F (sigma_B / delta)^2) | the meta-learners' shrunk LCB at Z = 3 with MINB and WARM; one charge a run; measured at J up to 1,535 under PREREG-EVL-6 as frozen, per run to the run's end with a day-shock loading spread across issuers (section 6.5: at most 0.098, 0.117 at any horizon); records are never seated by hand and never shown by figure (section 10) | none beyond the measured rate |
| 9 | INFORMATIVE CENSORING BY SETTLEMENT: crash-prone events settle late (rt_meta) | section 7.4's session-complete entry and the -30% imputation after 3 sessions | |
| 10 | BETA SELECTION BY A LEARNER: a learner scoring raw returns drifts to high beta (rt_meta) | the meta-learners score pool-relative abnormal returns (R_js = mean a - P_s); the screens' mean r > 0; picks' beta in the report | |
| 11 | SLOT STARVATION: ROOM puts this file last, so its learning lots rarely fill | promotion reads the shadow, so starvation never slows a look; Probe room 14 and round-robin (A85) once promoted; `fw_starve` names the binding constraint, this file's cut parts and the late passes that did not come (section 4.6) | learning-size real money for this file's rows will be thin while earlier rows use the cash; every buy of this file is planned in a late pass, so PX-DROP-ON, PX-SURGE-ON and EVL-META-ON buy nothing at a close whose lane run ends after the book's 15:48 tick (63 s; 48 s for EVL-META-ON) |
| 12 | THE LOSS BUDGET STOPS THE LANE BEFORE EVIDENCE ACCRUES (rt_budget: P(a Probe entry is cut) 8.3% with a full learning book against 4.2% at a quarter of it, flat market; 29.6-37.7% in a falling one) | the PX seats' learning room is 4, not 8 (section 4.1); A85; the shadow accrues whatever real money does | a long falling market still cuts entries: the walls bind first, by design |
| 13 | THE FALSE-PASS BUDGET RUNS OUT: every seat costs its charge, every run too | 0.13 a version and a run, charged when it starts and only when the budget holds it, in registration order (section 6.6); no restatement of the budget | after this file, PREREG-EVL-7, A117's PREREG-EVL-9 and A104's births about three charges are left for every fresh run of every file (six without the births): this file's second runs start only if room is left after the earlier files' |
| 14 | SETTLEMENT AND DATA LOAD: the nightly score settled 15-25 events a minute (A95); PX adds about 520 print-settled events a session (3 seats x 40 + 2 controls x 200) | the batched score (harness H1) before PX's first live decision; this file's parts in their own bounded runs on the lane's one slot at DATA_INTERVAL 0.5 s, each read's timeout capped at its run's end (section 4.6); the token bucket at 150 requests a minute over every read of the data host is new code (harness H2) | |
| 15 | A CAPTAIN STEP INSIDE DONE'S LAST 100: every operator channel is a step (A84) | the operator log and quiet spans (harness H7) | the attestation stays the captain's until the log covers every channel |

Which designs the red team threatens most: the meta-learners (causes 8-10: selection from noise, censoring and beta
are their whole risk, each guarded and measured) and the PX seats (causes 2, 3 and 7: beta, costs at learning size and
data look-ahead).

## 12. Why these rules (the judge's prior, stated before any outcome)

- WHAT PX ADDS. Events with no reading cost (no model call; about 1,640-1,790 SIP requests a session on the free Basic
  plan, 8.2-8.9 minutes of its 200-a-minute allowance: section 4.6), no earnings season, and issuer sessions disjoint by
  construction from every news, 8-K, Form 4 and earnings row (NO STORED ITEM), so their day shocks diversify Done's
  ">= 3 programs x 50". Its one open-entry seat uses intraday cash the overnight rows leave. Supply is not what binds
  Done (A94 (3)); what PX gives a promoted seat is a full Probe room every session: 4.5-42.7 qualifying names a seat a
  session under stated assumptions (`price/px_supply.out`: N_U 1,500-3,000, a no-news share of 0.3-0.6 among |z| >= 2
  movers; the House measures both).
- PX-DROP-ON. FOR: short-term reversal (Lehmann 1990, QJE 105(1); Jegadeesh 1990, JF 45(3); Lo and MacKinlay 1990, RFS
  3(2)) as the return to supplying liquidity, larger when volatility is high (Nagel 2012, RFS 25(7)); moves without
  public news reverse (Chan 2003, JFE 70(2)), and within-industry moves carry the non-fundamental part (Da, Liu and
  Schaumburg 2014, Management Science 60(3)); a large absolute move draws attention and overnight buying at the next
  open (Berkman, Koch, Tuttle and Zhang 2012, JFQA 47(4); Barber and Odean 2008, RFS 21(2)). A buy in the closing cross
  pays no spread (EXECUTION-FACTS: 84 of 84 fills at the print). AGAINST: daily contrarian profits fell sharply into
  2007 (Khandani and Lo 2011, Journal of Financial Markets 14(1)); reversal profits concentrate in illiquid names and
  are largely consumed by costs (Avramov, Chordia and Goyal 2006, JF 61(5)), which the $10M ADV floor excludes; losers
  rebound with the market in rebounds (Daniel and Moskowitz 2016, JFE 122(2): the beta of cause 2). Strength: weak to
  moderate.
- PX-SURGE-ON. FOR: attention brings overnight buying pressure (Berkman et al. 2012); the high-volume return premium
  (Gervais, Kaniel and Mingelgrin 2001, JF 56(3)); momentum earned overnight (Lou, Polk and Skouras 2019, JFE 134(1)).
  It is the no-news complement of EVL-NEWS-REACT-ON. AGAINST: no-news moves reverse (Chan 2003), and Berkman et al.'s
  overnight gain reverses the next session, outside this hold only by one auction. Strength: weak.
- PX-GAP-O1. FOR: overnight and intraday returns pull against each other (Lou, Polk and Skouras 2019's tug of war);
  opening-cross pressure reverses intraday (Berkman et al. 2012); no-news moves reverse (Chan 2003). AGAINST: a
  pre-market drop with no item in Alpaca's feed or EDGAR may carry news outside both, and news-driven moves continue
  (Chan 2003); pre-market SIP trades are thin outside liquid names (hence ADV20 >= $20M and >= 3 bars with volume).
  Strength: weak.
- THE META-LEARNERS. The feedback is full-information (every sub-rule's record settles in the controls' shadow whether
  or not a meta-learner picks it): prediction with expert advice (Littlestone and Warmuth 1994, Information and
  Computation 108(2); Freund and Schapire 1997, JCSS 55(1); Cesa-Bianchi and Lugosi 2006, Prediction, Learning, and
  Games), with sleeping experts for rules that join later (Freund, Schapire, Singer and Warmuth 1997, STOC) and
  empirical-Bayes shrinkage (Efron and Morris 1975, JASA 70(350)) against the winner's curse; forgetting tracks decay
  (McLean and Pontiff 2016, JF 71(1)); judging only the forward record avoids data snooping (White 2000, Econometrica
  68(5); Hansen 2005, JBES 23(4); Harvey, Liu and Zhu 2016, RFS 29(1)). They complement PREREG-EVL-7's learners (a
  ridge over about 60 event features inside one fixed pool of version-1 controls): model-free over whole rules from
  every lane and over pairwise conjunctions, with PREREG-EVL-7's learners themselves among the experts. AGAINST: at
  20-40 bp a rule is learned slowly (section 6) and a regime break is followed for 20-30 sessions
  (`meta/calib_meta.report.txt`).
- AGAINST, ALL FIVE: the PX seats share one mechanism family (liquidity and attention around large no-news moves) and
  the meta-learners select among other programs' events, so their errors correlate with those programs'. PX-DROP-ON and
  PX-SURGE-ON share one night: both pass falsely 0.020 (the drift alone shared) to 0.072 (every day-level shock shared)
  of the time at the worst plausible corner against 0.012-0.013 if they were independent (section 6.2), and EVL-META-ON
  can stack on the same night through its PX-sourced picks; the report counts two PX seats, or a meta-learner and a PX
  seat of its auction whose picks are mostly PX-sourced, promoted within 20 sessions of each other as one mechanism
  beside Done's ">= 3 programs" line (section 10). The charges add regardless.

## 13. What is unchanged

Everything this file does not state is PREREG-EVL-1's to -6's (and PREREG-EVL-7's where frozen) and R3's, word for
word: the lane's universe, events, knowable times, backfill and the shadow rule; the verdicts, their model, prompts and
parsing; the execution model, auction prices, the fallback ladder, costs, per-event returns and TRADABLE; every earlier
program's rule, record and control and their place in ROOM ahead of this file's rows; the money walls, the loss budget,
the open-risk rule, the kill switch and the stops; Done (read by league/events/done.py), pivot and reporting
(PREREG-EVL-3 section 5). This file edits no file of PREREG-EVL-1 to -7: no program, prompt, verdict, judge, band rule,
wall or Done rule.

## 14. Honesty

- BLIND DESIGN. No designer, calibrator, the judge, a check or the fixer read, queried or computed any price after any
  event, or any return, P&L, look, band, bar or mark of any symbol or program from the House, the gateway,
  events.sqlite, live.sqlite, ~/Work/ltcm-evl-run, ~/Work/.ltcm-main/evl, ~/Work/.ltcm-main/scratch (beyond the
  amendments file) or any run record. The universe bound is a count from SEC's public ticker file; every false-pass,
  power, demotion and money figure is synthetic, from the named scripts and seeds; every supply figure is a stated
  assumption or a count from SPEED-FACTS.md and EXECUTION-FACTS.md, which hold no outcome; every timing figure is
  arithmetic on the code's constants (`final/timing8.py`).
- WHAT THE FIXER READ: PREREG-EVL-1 to -6 (frozen), PREREG-EVL-7's draft and its work text of Oct 22 (rules), the draft
  of this file, the judge's and both checks' records (synthetic), the amendments A60-A116 (rules, decisions, counts and
  synthetic figures), the code of releases 1019g and 1019h, the four designs and their scripts, and the workflows'
  scripts and the start times of their agents. THE FINAL STEP read, in addition, the two re-checks' findings and
  synthetic records (`evl8/recheck1/`, `evl8/recheck2/`), PREREG-EVL-7's text of 08:09 PDT Oct 22, release 1019h's
  house.py, gw.py, book.py, store.py, programs.py, equity/live.py, equity/schedule.py and live/step.py, and the
  amendments to A117.
- THE CAPTAIN. The registering session had read the per-program shadow means of the lane's existing programs over Oct
  19-20 and the lane's aggregate real-money figures. It wrote the prompts and F1-F13 and chose no rule parameter (see
  PROVENANCE). Rules of this file that read other programs' outcomes (the meta-learners' state) do so at run time,
  forward only, by an algorithm and constants fixed now from synthetic data; the state's training sessions include Oct
  20-22 (section 7.4) because the rule says every session from the lane's first full one, not because of anything in
  them; only picks after REGISTERED_AT_8 are judged.
- SELECTION. THE PX SCREEN's first look was chosen among the five frozen thresholds by F1's rule on the fresh seeds,
  whose figure at the chosen look is therefore a selected one (0.1190 at the worst cell); the chosen look is
  PREREG-EVL-6's own, and its 16 worst cells were re-run on confirmation seeds that chose nothing (0.1165 at the same
  cell, every confirmation cell <= 0.1165). `px_select8.py` was written before the fresh seeds ran. Nothing else was
  chosen: the meta-learners' constants are the META designer's, measured here, and the plausible grid is PREREG-EVL-6's,
  carried onto the PX generator before any of its figures existed. The final step's measurements (the meta-learners to
  the run's end, the shared day, the demotion's third seed set) chose nothing: the META charge is the fix round's rule,
  max(0.13, the worst plausible per run rounded up to 0.01), applied to them as they came.
- LIMITS. Every false-pass, power and demotion figure is only as good as its generator; the PX generator's plausible
  grid (section 6.1) is PREREG-EVL-6's frozen grid carried onto the PX designer's generator by this file's fixer, and
  its sd_c ceiling is PREREG-EVL-6's absolute 2.2% a session (a rho_day of 0.15 on the PX generator's own event variance
  would be 1.75%); supply (N_U, the no-news share, the pre-market coverage) is an assumption the House measures; the
  expected-value figures of the judge's draft (its section 6.3-6.4 money lines) were computed under PREREG-EVL-6's
  draft schedule and are not restated here.
- LATER FILES. No designer, judge or captain of a later file reads a record's, placebo's, panel's or sub-rule's
  forward figure (section 10). A later program built from them by hand would be chosen from outcomes and is forbidden;
  a later pre-registered consumer reads them forward only.

## 15. What is not decided here

The code (league/events/pxstore.py, pxdata.py, px.py and mrl.py, new; programs.py's rows; run.py's and house.py's runs
`px-bars`, `px-am`, `prepass-meta`, `decide-open-px8`, `decide-close-px8`, `decide-close-meta8` and the catch-up kinds,
at the times, priorities, yields and bounds of section 4.6 (the lead's bound of a record or verdict task to tau, each
PX read's timeout capped at its run's end, the first-task rule on the lane's receipts); mrl.py's members by section
7.2's rule (`book.picks` at tau, as PREREG-EVL-7's pools); book.py's rows, the OPEN AND CLOSE LATE PASSES at the book's
minute ticks (equity/live.py), ROOM and picks; screen.py's two screens on PREREG-EVL-6's frozen judge with section
5.1's first look and F4's constant cap, CONTROLS rows and the expected-false-pass count with every run; score.py's
event ids; births.py's deny list and its exclusion of this file's rows from the facts and the Jaccard (section 4.4);
the report and alarms; constitution.py's money row `event.max_open_v8.learning` 4 with bounds 0-4; the 150-a-minute
token bucket of harness H2 is new code this file does not need), the site and the docs, built after this file to
these rules; the
judge's code plan (`evl8/GUSHER-RESULT.json`, judge.code_plan) is a guide, superseded where this file differs (its step
4's writes to the lane's eligibility and universe tables, its steps 12-13's screens and successors, its step 11's bound
0-8, its step 9's parts inside the lane's runs), and this file wins. If an implementation finds a rule here ambiguous,
it takes the reading LESS LIKELY TO PASS (screen rules) or that TRADES LESS (trading rules), fixed before the program's
first settled event and recorded as an amendment; a later resolution is a new version. Section 1.2's clock is stated,
not ambiguous: no reading removes its reads (b), (c) and (d).

## 16. The calibration record

### 16.1 Files

Paths are relative to `goal-2026-10-19/evl8/`. At the freeze every file below is copied flat into
`docs/prereg/evl-8/` (staged now in `goal-2026-10-19/prereg/evl-8/`, with `SHA256SUMS`): this round's from `final/`
under their own names, the pinned grid and its builder from `calib/`, and the judge's, the checks' and the designers'
files this text cites with the prefixes `calib__`, `check1__`, `check2__`, `price__`, `meta__` and `redteam__`. Every
figure of sections 0, 3.3, 4.6, 6 and 12 comes from one of them; `final/report8f.py` prints every table of section 6
into `final/report8f.txt`.
- THIS ROUND (`final/`): `px_final8.py` (the PX generator with the frozen grid's additions, its `selftest`, the record
  on PREREG-EVL-6's frozen calibration code, the grids and phases `search`, `fresh`, `confirm`, `base`, `stress`,
  `power`, `money`, `shared`, `sens`) with `px8f.<phase>.jsonl`, `px8f.<phase>.index.jsonl` (every job's seed and info)
  and `px8f.<phase>.log`; `px_select8.py` (F1's protocol) with `px8f.fresh.cells.jsonl`, `px8f.choose.json`,
  `px8f.confirm.cells.jsonl` and `px_select8.{plan,choose,confirm}.log`; `px_demotion8.py` with `px_demotion8.json` and
  `.out`; `meta_final8.py` and `calib_meta_f8.py` (check 1's copy of the META designer's simulator with the frozen
  grid's day shapes added) with `meta8f.{null,stress,power}.jsonl` and `.log`; `placebo8f.py` with
  `placebo8f_F22.out.json` and `placebo8f.log`; `timing8.py` / `timing8.out`; `budget8.py` / `budget8.out`;
  `report8f.py` / `report8f.txt`; `chain8.sh` (the order the stages ran in).
- THE FINAL STEP (`final/`, its order `chain8b.sh`): `calib_meta_b8.py` (calib_meta_f8.py with the one knob beta_day)
  and `meta_life8.py` (the meta-learners to the run's end; its `selftest` in `meta8l.selftest.out`) with
  `meta8l.life.jsonl`, `meta8l.life.index.jsonl` and `meta8l.life.log` (its main phase) and `meta8l.ext.jsonl`,
  `.index.jsonl` and `.log` (its extension to 4,000 sessions); `px_shared8day.py` (re-check 1's `rc_shared.py`
  with its paths moved) with `px8f.sharedday.jsonl` and `.log`; `px_demotion8.s184.json` and `.out` (`px_demotion8.py`
  unchanged, a third seed set); `timing8b.py` / `timing8b.out` (superseding `timing8.out`'s close and open arithmetic;
  its request rows stand); `budget8b.py` / `budget8b.out` (superseding `budget8.out`); `report8f.py`'s three added
  tables. THE RE-CHECKS' RECORDS this text cites, copied with the prefixes `recheck1__` and `recheck2__`: `rc_meta.py`,
  `calib_meta_rc.py`, `rc_meta.jsonl`, `rc_meta_attack.jsonl`, `rc_meta_attack_long.jsonl`, `rc_shared.py`,
  `rc_shared.jsonl`, `rc_dem.json`, `rc_px.py`, `rc_px.A.jsonl`, `rc_px.B.jsonl`, `rc_engine.py`, `rc_engine.jsonl`;
  `timing_rc2.py`, `timing_rc2.out`.
- THE PINNED GRID: `calib/px_grid8.json` (canonical sha256
  bb0d50e47d94e73f677a22bb612ef3f1cf7d23b23e5a51375fe965cf57e3e5a1), its builder `calib/px_grid8.py` and
  `calib/px_grid8.out`.
- IMPORTED UNCHANGED: `price/px_calib.py` (the PX designer's generator); PREREG-EVL-6's `evl6/final/calib_final.py`,
  `search_final.py` and `demotion_final.py` (in `docs/prereg/evl-6/` at the frozen tag, with their sha256 in its
  `SHA256SUMS`); `evl7/learner/calib_learner.py` (the META simulator's helpers).
- THE JUDGE'S AND THE CHECKS' RECORDS (superseded where this round re-measured): `calib/` (`px8.py`, `evl6d.py`,
  `meta8.py`, `placebo8.py`, `ev8_sim.py`, `ev8_drive.py`, `ev8_mix.py` and their outputs, `calib8.report.txt`);
  `check1/` (`px_c1.py`, `px_c1b.py`, `demotion_px_c1.py`, `demotion_px_c1b.py`, `meta_c1.py`, `calib_meta_c1.py` and
  their outputs); `check2/budget_check.py`.
- THE DESIGNERS' RECORDS: `price/` (`px_calib.py`, `px_calib.report.txt`, `fees_and_requests.py` / `.out`,
  `count_universe.py`, `px_supply.py` / `.out`), `meta/` (`calib_meta.py`, `meta_spec.py`, `grid_count.py` / `.out`,
  `calib_meta.report.txt`), `redteam/` (`rt_*.py` and their outputs).

### 16.2 Seeds

Search 171,000,001 on; fresh 172,000,001 on; confirmation 173,000,001 on; stresses 174,000,001 on; power 175,000,001 on;
money's population 176,000,001 on; base 176,500,001 on; the shared drift 176,800,001 on; sensitivities 177,500,001 on;
the PX demotion 178,000,001 on; the meta-learners' nulls 179,000,001 on, stresses 179,500,001 on, power 179,800,001 on;
the placebo audit 179,900,001 on; THE FINAL STEP: the meta-learners to the run's end 182,000,001 on, the shared day
183,000,001 on, the PX demotion's third set 184,000,001 on. None was used by the PX designer, the judge (83-98
million), the checks (61-65 million), the re-checks (191-198 million) or PREREG-EVL-6's calibration (111-126 and
150-166 million). Each phase's index file lists every job's seed.

## 17. Every finding of both checks and where it is closed

| finding | severity | closed by | where |
|---|---|---|---|
| check 1 #1: money buys the first 4 / 14, the screen judged all 40 | major | F4: PREREG-EVL-6's money-weighted values and top-CAP guard at the band's cap (4 in a PX run, 14 at Probe); check 1's "judge only the top 14" is not taken (F4); its attack measured under the guard and stated | 5.1, 6.2 |
| check 1 #2: exhaustion retired real edges | major | F2: the 60th block ends the run, never the version; runs charged when they start | 5.1, 6.6, 7.7 |
| check 1 #3: the copied fixed reads demoted real PX edges | major | F3: PREREG-EVL-6 section 3's frozen demotion (reads at p <= 0.15, the 10% money stop, the lower tail), calibrated for +40 bp with 14 buys a session | 5.1, 6.4 |
| check 1 #4: contradictory storage times void the bridge | major | F5: one clock, reads (a)-(c), the test sentence | 1.2, 7.2, 7.3 |
| check 1 #5: the screens froze PREREG-EVL-6's draft | minor | F1: PREREG-EVL-6 as frozen, sha256 0f67f94e... | 5 |
| check 1 #6: the META rate counted over 120 sessions only | minor | lifetime rates to 720 sessions stated | 6.5 |
| check 1 #7: section 6.3 priced on the normal-block model; PX seats share a drift | minor | the worst-plausible sum stated (the simulator's figure withdrawn); SHARED measured; the report's one-mechanism line | 6.2, 6.6, 10, 12 |
| check 1 #8: look-ahead in the backfill universe | minor | F11: catch-ups read only what was stored before tau | 1.3 |
| check 1 #9: PASS tolerance ambiguous | minor | the frozen text: PASS p <= alpha(S) with no tolerance; RETIRE and the lower tail q <= alpha(S) + 1e-12 | 5.1 |
| check 2 #1: two clocks; the tie-break turned PX money and the bridge off | blocker | F5: tau and the storage time of every input; reads (b) and (c) stated; the tie-break cannot reach them; the test | 1.2, 15 |
| check 2 #2: the catch-up member cutoff contradicted itself | major | F6: one cutoff, stated once | 7.2 |
| check 2 #3: the isolated parts could not all fit | major | F7: this file's parts in their own runs at stated times, pre-passes for the state and the morning values, no room kept; the timing table (restated on release 1019h's cadence by the final step) | 4.2, 4.6 |
| check 2 #4: sub-rule figures leaked through intents | major | F8: rank_key an integer position, why "mrl"; hashed ids and figures in mrl_* only, on both deny lists; the no-leaderboard test | 7.5, 10 |
| check 2 #5: the member outcome was ambiguous and admitted unbuyable entries | major | F9: one outcome rule, PREREG-EVL-2's limit at entry excludes from the state and the POOL; the POOL is the members eligible to pick | 7.1, 7.2 |
| check 2 #6: PX changed earlier records through the shared eligibility table | major | F10: px_eligibility and px_universe only, never the lane's tables (check 2's own fix superseded); the proof and the test | 4.4 |
| check 2 #7: corporate actions after D in the catch-up universe; sigma's basis | major | F11: one adjustment basis a window; catch-ups read stored values only | 1.3 |
| check 2 #8: fresh runs uncharged; two bases; the budget's basis | major | F12: 0.13 a version or run (PREREG-EVL-6's frozen basis, one basis for both parts); every run charged when it starts; the SEATING sum; registration order | 6.6 |
| check 2 #9: the learning money row's bound 0-8 | minor | bounds 0-4; no value above 4 for PX versions | 4.1, 15 |
| check 2 #10: WARM two ways | minor | counted in entered sessions; the port's session_index stated | 7.5 |
| check 2 #11: request figures stale; the bucket partial | minor | 1,640-1,790 a session; 840 more print reads; under release 1019h every read on the lane's one slot at DATA_INTERVAL, the bucket over every data-host read new code (re-check 2) | 3.2, 4.6, 12 |
| check 2 #12: the pivot count departed from PREREG-EVL-3 | minor | PREREG-EVL-3's "such events" (Probe and above), learning reported beside | 9 |
| check 2 #13: order with PREREG-EVL-7 undefined | minor | ROOM after PREREG-EVL-7's rows whatever the freeze order; the budget drawn in registration order (F12) | 4.2, 6.6 |
| check 2 #14: the sale-gate edge unstated | minor | stated as PREREG-EVL-5 section 1.3 states its own | 4.3 |
| check 2 #15: the later first look delayed the stay's lower tail | minor | no later first look is taken (F1's earliest is the frozen 22nd block): the stay's lower tail and its Sized PASS at the frozen looks from the 22nd stay block | 5.1, 6.4 |
| check 2 #16: six rules two ways | minor | (a) the family cap and program experts (7.3); (b) V_D on an early close (1.1); (c) the operating-company cache (1.1); (d) the hourly re-decision, never a meta-learner, a PX look's finality (3.4); (e) "one change": none is left in the schedule (F1's earliest first look is the frozen one); F4's cap is stated; the seed strings stay the frozen text's (5.1); (f) VOL, R5, R20 read as stored (7.3) | 1.1, 3.4, 5.1, 7.3 |
| RE-CHECK 1 #1 and RE-CHECK 2 #1: the clock turned half the PX-to-META bridge off and forbade the shadow's re-decision | major | read (c) names the live PX run's px_features and px_marks for a meta-learner; read (d) the PX run that decided (D, X) for the hourly re-decision; the real-money sentence, tests (ii)-(iii) rewritten and test (v) added; the tie-break covers "by another run" | 1.2, 3.4, 7.3 |
| RE-CHECK 1 #2: the META false passes counted to a horizon, and the generator cancelled the day shock | major | beta_day 0.3 (plausible at the corner) and 0.5 (stress) added; every cell measured to the run's end (T 2,500, the worst cells 4,000) on fresh seeds; the META charge max(0.13, the worst rounded up); budget8b.py re-run | 6.5, 6.6, 0, 11, 12 |
| RE-CHECK 2 #2: the one cutoff read two ways | major | MEMBERS fixed by stored times alone: each source only through its live decision (the lane's first finished decision naming it; the live PX run), lane sources by `book.picks` at tau as PREREG-EVL-7's pools; no other run's intents; the first-task rule on the lane's receipts; the test | 7.2, 8 |
| RE-CHECK 2 #3: the timing table did not fit release 1019h's cadence | major | each PX read's timeout capped at 15:46:50 and the test with a hanging stub; the tasks PX-ON yields to named, record and verdict tasks inside the lead bounded to tau; the pre-passes yield before each read or step; the late passes at the book's minute ticks (the 15:48 tick the last); reads at DATA_INTERVAL 0.5 s; the bucket is new code; the power figures assume live decisions | 4.6, 10, 15 |
| RE-CHECK 2 #4: ROOM and the close's money path against PREREG-EVL-7 | major | every buy of this file in a LATE PASS, by time, at the close only after every PREREG-EVL-7 row is planned or failed; 4.2's guarantee restated for its own auction, A85's reservation at the other auction stated; "-7's waiting buys keep their own room" deleted | 4.2, 4.6 |
| RE-CHECK 1 #3: the ON seats' shared mechanism understated | minor | P(both) stated from the drift only to every day-level shock shared (`px_shared8day.py` on fresh seeds); EVL-META with a PX seat counted as one mechanism when most of its picks are PX-sourced | 6.2, 10, 12 |
| RE-CHECK 1 #4 and RE-CHECK 2 (6.4): the demotion table's lower bounds | minor | every 3,000th figure marked a lower bound; +60 bp stated as lower bounds; the count restated over three seed sets (`px_demotion8.s184.json`) | 6.4 |
| RE-CHECK 1 #5: ELIGIBLE TO PICK cited E5's first bound only | minor | both bounds stated in full | 7.2 |
| RE-CHECK 1 #6: births' facts and Jaccard would read this file's rows | minor | rule (1): this file's rows excluded from both; the test covers births | 4.4, 10, 15 |
| RE-CHECK 2: F4's cap readable as the live money row | minor | CAP a constant of the text | 5.1 |
| RE-CHECK 2: the member outcome two ways | minor | one reading (the first tag's intent of the issuer at the member's auctions) | 7.2 |
| RE-CHECK 2: the eligibility cut two ways | minor | read (c) cites 7.2's cut-off only | 1.2 |
| RE-CHECK 2: citations and the F10 proof | minor | the waiting room cited as release 1019h's (A113); the proof lists every row this file writes | 4.2, 4.4 |
| RE-CHECK 2: a starved morning pass lost both auctions | minor | px-am yields and resumes until 15:30:00 for the ON auction; the loss counted | 4.6, 10 |
| RE-CHECK 2: cross-file wording with PREREG-EVL-7 and A117's PREREG-EVL-9 | minor | this file's budget line counts every file registered before it (PREREG-EVL-9's if first); PREREG-EVL-7's own wording is its file's (an open question to its fix) | 6.6 |

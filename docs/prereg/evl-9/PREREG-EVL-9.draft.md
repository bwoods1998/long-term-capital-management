# PREREG-EVL-9: two warm-started learners that train on five years of public records before their first decision, counted only from the moment their model is fixed

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6e6a85b9) under the owner's goal as he re-set it at 05:15Z
Mon Oct 19, 2026 (`goal-2026-10-19/GOAL-MESSAGE-V2.txt`): "Births come from your architect agents and from you, using
outcome-free facts, rationed by an expected-false-pass budget you state ... Capital follows evidence across the swarm",
and under his request of Oct 22, "do more here and faster and better" (the captain's A106). Written
04:50Z-@@WRITTEN_END@@ Oct 22, 2026 (the design workflow wf_c959cc25-921: a scout of the reachable history from about
04:50Z, a data lens, a learners lens and a leakage and survivorship red team from about 05:30Z, then this judge from
06:53Z). Designed from: the frozen PREREG-EVL-1 to -5; the final working text of PREREG-EVL-6
(`goal-2026-10-19/evl6/final/PREREG-EVL-6.work.md`) and the drafts of PREREG-EVL-7 and -8; the lane's code at release
1019g (`origin/rel/1019g`, b374d862); the outcome-free facts of `goal-2026-10-19/speed/SPEED-FACTS.md`,
`EXECUTION-FACTS.md` and `SYNTHESIS.json`; the captain's amendments A60 to A109; record COUNTS of the public archives
(the scout's `evl9/scout/*.out.json`: how many 8-Ks and Form 4s a year, how many symbols, request limits; never a price);
SEC and Alpaca API documentation; the published literature; and synthetic Monte Carlo only. The scout counted the
reachable history; the data lens specified the dataset and its labels; the learners lens specified the learners and
the protocol and calibrated them; the red team tried to break the claim that history cannot raise a forward judge's
false-pass rate, and wrote guards; the judge chose among them, re-measured the learners under PREREG-EVL-6's final rule
(`evl9/judge/`), and wrote this file. Every one of them worked under the rule that no price, return, look, band, bar or
P&L of any event, symbol or program, historical or live, is read, queried or computed, from any source; none was. The
registering captain session (6e6a85b9) had read, on Oct 21, the per-program means of the shadow record of the lane's
existing programs over its first two entry sessions (Oct 19-20) and the lane's aggregate real-money figures; it took no
part in proposing, choosing or wording these rules (it set the workflow's lenses in A106 before any design existed), and
it changes nothing in them but the fixes a check states, WRITTEN_AT and the registration fields (section 13).

THE FOUR TIMES. Each is the latest of three clocks, all recorded in the captain's amendment that pins it (A92's
method): the commit time; the pushing client's own clock read after the push of the tag returns (A77's later bound); and
GitHub's activity time for the branch push. Tags never move.
- `REGISTERED_AT_9` (T_F): this file's commit on branch `prereg/evl-9`, tag `prereg-evl-9`. This file is frozen only
  after PREREG-EVL-6 (REGISTERED_AT_6 < REGISTERED_AT_9).
- `CODE_PIN_9`: the commit on `prereg/evl-9` tagged `prereg-evl-9-code` that holds the code of section 6.2 with CI green
  on its exact head, never earlier than T_F (it may be the same commit). The amendment that pins it lists the sha256 of
  every pinned file. No price-bearing request of section 3.1 is ever made before it.
- `MODEL_AT` (T_M) of a version: the commit of its training receipt (section 5.4) on `prereg/evl-9`.
- `COUNT_FROM_9` of a version = its T_M (always later than CODE_PIN_9 and T_F). A program of this file counts ONLY events
  knowable after its COUNT_FROM_9 (PREREG-EVL-1 section 3's knowable times), and no decision of it exists before that
  time. The owner's "judged only on events after its registration" is read as "after COUNT_FROM_9", which is never
  earlier. Nothing here changes for a registered version: a change is a new version with its own four times.

## 0. The judge's findings that shaped this file

- A FILE OF ITS OWN, NOT A SECTION OF PREREG-EVL-7. PREREG-EVL-7's learners are in their adversarial checks
  (`evl7/check1/`, `evl7/check2/`) and count from their own registration. Carrying a history prior inside them would
  either re-open those checks and delay their freeze, or leave a counted record whose procedure (prior or no prior)
  depends on when a later model arrives: an option a person could exercise after seeing outcomes. So the warm learners
  are their own two seatable programs with their own registration, their own gates and their own charge, on PREREG-EVL-7's
  pools and its forward-learning formula, and they reuse its code where it exists.
- COUNTING STARTS WHEN THE MODEL IS FIXED. The learners lens counted from T_F and let a VOID (no model within ten
  sessions) return the charge; the red team counted from max(T_F, T_M). A version counted from T_F whose model could
  still be voided gives whoever runs the build the option to abandon it after seeing the first counted sessions, and a
  persistent day shock or family drift makes those sessions predict the next ones. This file takes the red team's
  reading: nothing counts before T_M, nothing voids a version after T_M, and the build job commits the receipt in the
  same process that trains (no person between the model and its timestamp). The price of that honesty is build time,
  so the build is arranged to cost about no session: everything that carries no price is fetched before T_F, the code
  is pinned before any price is fetched, the job starts right after a close and its whole price fetch is 4.3-10.1 hours
  at 100 requests a minute (`judge/fetch_budget_judge.py`), so T_M can land before the next morning's 09:15 ET decision.
- HISTORY BUYS SPEED ONLY WHEN ITS STRUCTURE IS LIVE'S. Under PREREG-EVL-6's final rule, at a live information
  coefficient of 0.05, P(promoted within 60 sessions) is 0.205 for a warm learner whose history has the live
  structure (rho 1), 0.120 at rho 0.7 and 0.040 when history is unrelated (rho 0), against 0.090 cold
  (`judge/calib_evl9_final.power.jsonl`); at 0.08, 0.583 / 0.505 / 0.100 against 0.355. When history is
  unrelated the warm learner is worse than cold for its first weeks; the prior weight (25,000 rows) was chosen blind on
  synthetic paths as one the forward stream can still overrule (at rho 0 the picks' edge in sessions 111-120 was +33 bp
  at 25,000 rows against +8 at 100,000 and -4 at 400,000, `learners/calib_evl9.tune.jsonl`).
- THE FORWARD JUDGE HOLDS. Measured on 1,000 synthetic programs a cell under PREREG-EVL-6's final rule (first look at the
  9th block, alpha 0.012 / 0.010 / 0.004, money-weighted values, the guards), a warm learner with no forward edge passes
  its first run within 120 sessions 0.029-0.104 of the time across noise history, a decayed history edge (ic 0.05 and
  0.08), the knife edge, a drift along its own pick direction of 10-20 bp, phi_day 0.20, with and without 1% issuer
  effects, against 0.082-0.115 for PREREG-EVL-7's cold learner on the same generator
  (`judge/calib_evl9_final.report.txt`). History changes which events are picked, never what the forward record must
  show.
- ONE WAY HISTORY DOES BREAK THE JUDGE: ISSUER IDENTITY. A feature that encodes an issuer's own past labels passes
  0.9475 of the time where the null holds a 1% persistent issuer effect (`redteam/rt_warm.report.txt`, W-TE-tau1, under
  the drafted rule). So no feature here names, hashes or encodes an issuer, no label is grouped by issuer, and every leaf
  of the tree model holds at least 200 distinct issuers (section 4, section 5.1).
- THE LABEL'S BASIS MATTERS ONLY IF IT IS BIASED. Random bar-versus-print noise of 25-200 bp costs 0-3% of a top-8
  picker's value; a bias of 2 / 5 / 10 bp per standard deviation of liquidity costs 4% / 18% / 39%
  (`data/sim_basis.py`). So history is labelled at the listing exchange's auction prints, the judge's own basis, once the
  gateway admits `v2/stocks/auctions` (one reviewed row), with a flagged daily-bar fallback (section 3.6).
- THE SESSION BLOCK BINDS. With 8 picks a session, promotion needs a large edge a pick whatever the learner knows: even
  at an information coefficient of 0.08 with history of the live structure, P(promoted by session 40) is 0.448 (its
  picks' true edge about +112 bp) under the final rule. History moves the first look's edge from weak to strong; it does
  not remove the 9-block wait.
- WHAT WAS NOT TAKEN, AND WHY: the data lens's own event families (8-Ks of every item, Form 4 buys from $10,000): the
  forward stream labels only what a control shadows, so a learner can only learn forward on pool programs' candidates;
  ten years of history and the red team's 2016-2019 years: the equity lane's reserve years 2020-2021 sit between them
  (`league/swarm/elane_folds.py` RESERVE_YEARS), the build would take 20-46 hours of Alpaca requests, and at a prior
  weight of 25,000 rows more history did not help on synthetic paths (150,000 against 500,000 rows: 0.280 against 0.265
  by session 60, `learners/calib_evl9.tune2.jsonl`); pre-market minute features for the open learner: a new read inside
  the open decision's last minutes; the red team's forward half-life of at least 120 sessions: its own figures split
  (half-life 40 passes 0.055 against 0.075 for 120 under a plausible 15 bp sector drift, 0.105 against 0.060 under the
  30 bp stress, `redteam/rt_warm.report.txt` SEL rows; at its worst corner with noise history, 0.128 at 40 against 0.085
  at 500, WST-W-NOISE-HL40, all under the drafted rule, which reads 1.06-1.6 times the final rule's figure on the
  learners' paths here), every warm cell under the final rule is at most 0.104 at 40, and 40 unlearns a wrong prior
  faster, so PREREG-EVL-7's 40 stands; COST-7: it is PREREG-EVL-7's and binds a later file only when that file says so,
  and the replay is the stricter basis at today's equity; 14 picks a session (no gain on synthetic paths); any verdict
  or text feature (no history twin without a model call); a public model file (it is a function of history labels, which
  later designers must not see).

## 1. The protocol (A106), in order

### 1.1 The order

0. BEFORE T_F, ONLY WHAT CARRIES NO PRICE. The fetcher of section 6.2 may fetch the price-free sources of section 3.1
   (SEC files, EDGAR's Atom and headers, Alpaca's news metadata and calendar) into the vault at any commit; each
   response is written with its manifest row (section 3.1). A price-free vault can produce no fit: it holds no label.
1. T_F: this text, with every constant, is committed and tagged.
2. CODE_PIN_9: the code of section 6.2, written to this text by implementers who read no price, label or outcome
   (counts-only logs, synthetic fixtures), is committed and tagged with CI green on its exact head. Any reading of an
   ambiguity is recorded as an amendment BEFORE CODE_PIN_9, taking the reading LESS LIKELY TO PASS (screen rules) or that
   TRADES LESS (trading rules).
3. THE JOB (`scripts/warm/run_job.sh`, blake-desktop, started once by the captain after CODE_PIN_9, at or after a
   session's close): it reads `prereg-evl-9-code` with `git ls-remote` and refuses to run any other commit; fetches the
   price-bearing sources of section 3.1 into the vault; builds the history store and the canonical tables (section 3);
   runs the gates (section 6.1); trains each learner twice (section 5); writes the model files and the training receipt;
   and commits and pushes the receipt itself (T_M), in the same process, with no step for a person between the model and
   the commit. Its standard output and every file it writes outside the vault are counts, hashes, flags and the model
   files' schema (a test pins the whitelist).
4. T_M: the receipt's commit. COUNT_FROM_9 = T_M. The model files reach the House by `floor_box.py put-data` (section
   6.2), which verifies MODEL_SHA.
5. THE HOUSE decides each learner from the first decision whose events can be knowable after COUNT_FROM_9; decisions
   before the release carrying the code and the verified model are decided by that release, once each, oldest first,
   exactly as of their decision times, in shadow only (section 7.3).

### 1.2 VOID (only before T_M)

- A version is VOID when any gate of section 6.1 fails, or when its T_M is not on GitHub by the close of the 5th NYSE
  session after CODE_PIN_9. A VOID version never decides, never seats, is never judged, and its reserved charge is
  returned. The registering amendment writes the gate, its counts and the reason.
- At most two VOIDs per id: a third registration of an id draws its charge at its own T_F whatever happens.
- After T_M nothing voids a version. A fault found later holds its real money (section 7.5) and is fixed only by a new
  version.

### 1.3 Changes

Any change after CODE_PIN_9 to the code of section 6.2, a source, the window, a constant, a feature, the vault's content
beyond a re-fetch of an identical response, or the model is a NEW VERSION with its own T_F, CODE_PIN, T_M and
COUNT_FROM_9 and its own charge, counting only events knowable after its own COUNT_FROM_9. A re-run of the same code on
the same vault is not a change and must reproduce MODEL_SHA. A version that PREREG-EVL-6 RETIRES is not re-entered by
this file: a learner whose history taught it the wrong thing is replaced, if ever, by a new blind design.

### 1.4 What nobody reads

Nobody reads any fit of the history, in-sample or out-of-sample, before or after any of the four times: no
coefficient, tree, chosen number of rounds, zeroed column, information coefficient, label mean, quantile or score
distribution, and no figure derived from the vault's price files. The receipt carries counts, hashes and flags only.
The model files, the history store, the canonical tables, the label files and the House's warm state (section 7.4) are
MACHINE-ONLY: no designer, architect brief, birth prompt, R3 facts file or report reads or prints them; R3's facts
authorizer refuses their paths and tables; a captain read of any of them is written in the amendments with its time,
and a session that made one takes no part in designing a later warm procedure.

## 2. The programs

### 2.1 Terms

- D is the entry session, P the session before it, n(s) the lane's session index (calendar.py's sessions in order); tau
  is the learner's decision time of D (section 2.2). E_prev is the account equity at the previous session's close as
  score.py reads it (`equity_on`). TRADABLE at decision: 1.25 x the universe row's `prev_close` of D <= 10% of E_prev.
- STORED BEFORE TAU (PREREG-EVL-7 section 1.1, restated): a filing whose documents were stored before tau (A72); an
  article whose `received_at` is before tau; an outcome whose `status` is 'settled' and whose `settled_at` is before tau.
  ELIGIBILITY is the live rule's result for (D, CIK) as real money reads it; a universe row of D and the daily bars of
  sessions before D are read as stored whatever their write time; `cik_info.sic` as stored.
- MARKET DATA KNOWABLE AT TAU: a SIP minute bar that ended at least 16 minutes (`universe.SIP_DELAY`) before tau. It
  carries no information after tau, so a decision (live, catch-up or history) reads it whenever it was stored; the live
  decision's pre-passes store it before tau. An event (filing, article, Form 4) is never read by this rule: only as
  stored before tau.
- A learner's POOL is a fixed, ordered list of version 1 programs of PREREG-EVL-1 to -5 (section 2.2), PREREG-EVL-7's
  pools word for word. A POOL OUTCOME of (session s, issuer i) is the outcomes row of the first pool program, in pool
  order, holding an intent of issuer i entering at s at the learner's own entry and exit auctions; one whose raw entry
  print was above 1.25 x the previous SIP close is not a pool outcome (PREREG-EVL-7 section 1.1).
- THE LIMIT AT ENTRY (PREREG-EVL-2 section 2) applies, shadow and real: an entry auction above 1.25 x the raw SIP close of
  P is not filled and the event is skipped.

### 2.2 The two learners

Version 1 of each id is seatable at PREREG-EVL-3's LEARNING band from its first counted decision. Each holds one session
in the screen's sense (its block is D; blocks never overlap).

| id | entry -> exit | tau | pool (each at version 1, in this order) |
|---|---|---|---|
| EVL-WL-O1 | OPEN of D -> CLOSE of D | D's open decision time (09:15 ET) | EVL-CTRL-NEWS-ALL-O1, EVL-CTRL-8K-ALL-O1, EVL-CTRL-ERN-ALL-O1, EVL-INS-BUY-O1 |
| EVL-WL-ON | CLOSE of D -> OPEN of D+1 | D's close decision time (the close - 14 minutes) | EVL-CTRL-NEWS-DAY-ON, EVL-CTRL-NEWSPM-ON, EVL-CTRL-8K-ON, EVL-ERN-REACT-ON, EVL-ERN-DROP-ON, EVL-CTRL-ERN-UNDER-ON |

- The two learners use disjoint auctions and disjoint pools: two tests. They share their pools and auctions with
  PREREG-EVL-7's EVL-LRN-O1 and EVL-LRN-ON, whose rows come before them in ROOM (section 8): their errors are correlated
  with those learners' and the charges add regardless (section 10).
- Free derived controls: EVL-WL-O1-POOL and EVL-WL-ON-POOL (section 2.4).

### 2.3 Candidates at tau

- For each pool program p, in pool order, the events p's own rule takes for D as real money reads them:
  `book.picks(lane, p, D, decided_at=tau)` (rows stored before tau, verdicts answered before tau, the live eligibility, p's
  own one-position rule, and for the REACT, DROP and UNDER rows the book's reading of the SIP minute bars).
- ONE CANDIDATE PER ISSUER (CIK). Its POOL FAMILIES are the pool programs selecting the issuer; its PRIMARY EVENT is the
  event of the first of them in pool order, and the learner's intent, if picked, is that event.
- Its FEATURE EVENT is the event that its primary pool program's own selection takes for the issuer with every verdict
  read as missing: `programs.select` with `verdict` returning None, which for every pool program is the issuer's
  earliest knowable event of that program's rows (then the lowest event id). Features read the feature event, so no
  feature depends on a verdict (section 4).
- KEPT (the fit's centring): TRADABLE at decision.
- ELIGIBLE TO BE PICKED: kept, and (i) its primary event is knowable after COUNT_FROM_9 of the version; (ii) the learner
  holds no intent of the issuer entered before D that exits within the last 5 sessions or later, nor a written,
  non-skipped intent of it entering within the 5 sessions after D (PREREG-EVL-1 section 5 as A72 reads it); (iii) THE
  SHAPE GUARD: its sig20 (section 4, item 7) is at least 0.015. A candidate below the guard stays in the pool, the fit,
  the centring and the control.

### 2.4 Controls (free records)

EVL-WL-O1-POOL and EVL-WL-ON-POOL: for each decision of their learner, every kept candidate whose primary event is
knowable after the version's COUNT_FROM_9, valued by its POOL OUTCOME's a (PREREG-EVL-1 section 5). No intents, no
settlement of their own; they never seat, never trade and cost no expected false pass. Compared over the learner's own
block sessions (PREREG-EVL-1 section 7: the control's TRADABLE values of each session averaged, then the sessions
averaged).

## 3. The data spec (history)

### 3.1 Sources, their vintage, and the vault

Every source is public, structured and free of metered compute: no language model reads any historical document, and no
verdict, summary, article body or filing text enters the history.

PRICE-FREE (may be fetched before T_F):
- (a) S1, SEC `submissions.zip` (https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip), THE SCOUT'S
  COPY: 1,570,500,398 bytes, sha256 b6534bf3efaca6ea2a0a9509deb9eb4c612cb9aa12d4913fdb641a526cc4b033, fetched about 04:50Z
  Oct 22 (`evl9/scout/submissions.zip.sha256`). Read: each filing's accession, form, filingDate and 8-K `items` (equal to
  the filing's own `.hdr.sgml` ITEMS on 120 of 120 sampled, `scout/check_items.py`); the periodic filing dates; the
  current SIC (a stated fallback only); a CIK's filing dates for ALIVE (section 3.7).
- (b) S2, SEC Insider Transactions Data Sets 2021q1-2026q3 (23 quarterly zips;
  `www.sec.gov/files/structureddata/data/insider-transactions-data-sets/` and, for 2026q2-q3,
  `/files/datastandardsinnovation/data/insider-transactions-data-sets/`): SUBMISSION, REPORTINGOWNER and NONDERIV_TRANS
  of original Form 4s (DOCUMENT_TYPE exactly `4`), written into the history store's `form4_owners` and `form4_tx` columns;
  ISSUERTRADINGSYMBOL as the issuer's symbol as of that filing (section 3.4).
- (c) the full submission `<accession>.txt` of every Form 4 in EDGAR's daily form index of 2026-10-01 to 2026-10-16
  (12,952, `data/count_gap.py`) and of the overlap sessions (section 6.1, G2), parsed by `league.events.edgar.parse_form4`.
- (d) EDGAR company browse Atom (`cgi-bin/browse-edgar?action=getcompany`): `type=8-K` per filer CIK and `type=4` with
  `owner=only` per issuer CIK, paged with `dateb`; `<updated>` is the acceptance time (equal to the `.hdr.sgml`
  acceptance on 24 of 24 sampled, `scout/check_browse_atom.py`).
- (e) `.hdr.sgml` of an accession Atom lacks (counted).
- (f) SEC Financial Statement Data Sets `sub.txt` 2021q1-2026q3 by HTTP range reads: the SIC recorded with each periodic
  filing (section 3.4).
- (g) Alpaca `v1beta1/news` through the gateway, `include_content=false`, 50 a page, from 2021-11-15 through the overlap
  sessions: id, created_at, updated_at, source, headline, symbols (the lane's `news` columns; a summary returned is
  stored and never read).
- (h) Alpaca `v2/calendar` for 2021-2026.

PRICE-BEARING (only after CODE_PIN_9; the fetcher reads the code tag and refuses otherwise):
- (i) `v2/stocks/bars` 1Day, `feed=sip`, `adjustment=raw` and `adjustment=all`, for every symbol of section 3.4, from
  2021-11-01 through the overlap sessions, each requested with `asof` set inside the period in which it was the issuer's
  point-in-time symbol, grouped by `asof`, 200 symbols a request.
- (j) `v2/stocks/bars` 1Min raw for the ON learner's pool issuers on each D: the 09:30 minute, and the '1530' rule's span
  ([15:00, 15:30) ET, then the session's open to 15:00 for names with no bar in the first span; 30 minutes earlier on an
  early close), exactly `league/events/run.py` `_mark_1530`'s and `_marks_0930`'s selections.
- (k) `v2/stocks/auctions`, `feed=sip`, for P, D and D+1 of every candidate and for SPY and IWM, when the gateway admits
  the path at the job's start (section 6.2, B1).

THE VAULT: `~/Work/.ltcm-main/evl9-vault/`, outside the repository and every designer directory: `free/` for the
price-free sources (fetched before or after T_F) and `price/<CODE_PIN_9 short sha>/` for the price-bearing ones. Every
response is stored gzipped with its row in `MANIFEST.jsonl`: url, params, fetched_at, status, bytes, sha256. RAW_SHA
is the sha256 of the sorted manifest. Files are mode 0600. The model is built from the vault only, never from a live
re-fetch. SIP data and Benzinga headlines are licensed (`league/events/news.py`: "Headlines are licensed: they stay in the
private store"), so the vault stays private: "anyone can recompute" means anyone the owner gives the vault to, and the
public can verify the hashes.

### 3.2 Window, clamp, reserve and the lane's sessions

- HISTORY ROWS: EVL-WL-O1 entry sessions 2022-01-03 to 2026-10-16 (1,202 sessions); EVL-WL-ON entry sessions 2022-01-03 to
  2026-10-15 (1,201), whose exits are at or before the open of 2026-10-16 (`judge/count_sessions.py`, the repo's
  `league.equity.store.nyse_sessions`; by year 251, 250, 252, 250 and 199 sessions for 2022 to 2026).
- THE CLAMP: no record timed after 2026-10-16T20:00-04:00 enters any training table; the builder refuses such a row and a
  test pins it. The clamp is the close of the last session before the lane's first (2026-10-19).
- THE LANE'S SESSIONS (2026-10-19 on) are never history rows. They enter only as forward rows, from the House's own
  store (section 7.1), so no session is trained on twice and no counted session is ever in the prior.
- THE RESERVE: no 2020 or 2021 session is an entry or exit session of any row (`league/swarm/elane_folds.py`
  RESERVE_YEARS = (2020, 2021), A15; `league/xs/config.py` RESERVE_YEARS = (2020,)). Records of late 2021 enter only as
  look-back, as the equity Train reads the reserve's bars (`league/swarm/elane_train.py`): daily bars from 2021-11-01
  (sig20, r20, ADV20 and the 20-bar listing test of early January 2022), SEC metadata from 2021-01-01 (the 365-day
  look-backs of section 4 and section 3.4), news from 2021-11-15. No 2020 record is read.

### 3.3 Knowable times (PREREG-EVL-1 section 3)

- 8-K: the Atom `<updated>` + 10 minutes; else the `.hdr.sgml` ACCEPTANCE-DATETIME (Eastern) + 10 minutes. S1's
  `acceptanceDateTime` is never read: against the header it is the Eastern wall time labelled Z on 54 of 88 filings, true
  UTC on 19 and shifted twice on 15 (`scout/check_accept_offset.py`), with no per-filing decode.
- Form 4: the issuer's `owner=only` Atom `<updated>` + 10 minutes; else the `.txt` header's acceptance + 10 minutes; else
  FILING_DATE 22:00 ET + 10 minutes (a Form 4's acceptance date equalled its filing date on 398 of 398 sampled,
  `scout/sample_accept_times.py`); each fallback counted.
- News: created_at + 2 minutes. An article whose updated_at is more than 10 minutes after created_at is excluded
  (`programs.news_rows`' non-live exclusion: every history article is stored with `live` 0).
- In the history store `received_at` and `documents.stored_at` equal the knowable time, so A72's stored-before reads and
  knowable-time reads coincide. A decision for D reads daily bars of sessions before D only, and minute bars by section
  2.1's rule. Auction prints enter labels only.
- Every feature row records `inputs_at`, the latest time of any input it read; a row with `inputs_at` >= its tau is an
  error (section 6.1, G3).

### 3.4 The point-in-time universe of D

- SYMBOL(i, D): the latest ISSUERTRADINGSYMBOL among issuer i's Form 4s (S2, and (c) for October 2026) with FILING_DATE in
  [D - 365 days, D), normalised (upper case; an exchange prefix stripped; '/', '-' and ' ' to '.'; kept when it matches
  `^[A-Z]{1,5}(\.[A-Z]{1,2})?$`, else none). A symbol two CIKs hold on D maps to neither (counted). An issuer with no
  SYMBOL on D is not a candidate on D. Today's `company_tickers.json` is never read: it would drop 48.5% of 2016's,
  37.6% of 2019's, 29.0% of 2022's and 12.1% of 2025's insider-active issuers (`scout/count_survivorship.py`).
- An article's single symbol maps to the CIK whose SYMBOL it is on D, else to none.
- ELIGIBLE on D (PREREG-EVL-1 section 2, read point in time, with `league/events/universe.py`'s constants): a raw SIP
  1Day bar on each of the 20 sessions before D; raw close of P >= $3.00 (MIN_PRICE); ADV20 >= $1,000,000 (MIN_ADV, the
  universe's formula); a filing of `universe.PERIODIC` dated in the 15 months before D (S1 dates); the SIC as of D (the
  SIC of the issuer's latest FSDS `sub.txt` record accepted before D, else S1's current SIC) neither 6221 nor 6770; no
  class separator '.' in the symbol (the live rule, `universe.eligible`, looks each SEC ticker up in Alpaca's asset
  list, where SEC's dash form, BRK-B, is not Alpaca's dot form, BRK.B, so it admits no class share). The benchmark is
  IWM when ADV20 < $50,000,000 (BENCH_SPLIT), else SPY. prev_close and adv20 of the history universe row are
  `universe.eligible`'s formulas over raw bars; sigma60 is left NULL, as the live rule writes it.
- What the live rule reads that history cannot (Alpaca's tradable flag, asset class and listing exchange) is replaced
  by "20 SIP bars exist" (Alpaca serves SIP bars for an exchange-listed span only); G2 counts the difference.
- TRADABLE at the history reference equity E_REF = $2,000: 1.25 x prev_close <= $200. A row not TRADABLE is not kept.

### 3.5 The history twin of the pools

For each D and each pool program p: `league/events/programs.py`'s own windows and family rules (`open_window`,
`news_window`, `close_window`, `day_news_window`, `filings_window`, `news_rows`, `family_8k`, `close_rows_4`,
`taken_close_5`, `dropped_ciks`, `close_rows_5`, `_insider_buy`, `select`) over the history store, with `eligible` the
universe of section 3.4, `verdict` returning None, `reaction` and `gap` by the '1530' and '0930' rules from the vault's
minute bars, p's own one-position and 5-session rules over p's own history intents, and the registration floor replaced
by 2021-01-01 (an optional `since` argument of `select`, section 6.2, B2). Then sections 2.3's union, primary event,
feature event and KEPT. THE ONE READING THAT DIFFERS FROM LIVE, stated: PREREG-EVL-5's TAKEN (b) (a DAY(D) article
answered `ok` with score >= 2), its WAIT, and the real-money guard of `book.RAISED_GUARD` read verdicts no history holds;
in history they never apply. Every DAY(D) issuer is an EVL-CTRL-NEWS-DAY-ON candidate first in pool order, so this
changes the candidate set only for ERN(D) issuers with a reaction <= 0.96, no DAY(D) article and a filing the guard bars
live; it changes `multi` more often. G2 checks containment for those two programs (section 6.1).

### 3.6 Labels (read only by the trainer)

- y = clip(G / sig20, -5, 5), G the GROSS abnormal return of the one-session hold at the learner's own auctions:
  G = (P_out x k_out) / (P_in x k_in) - (B_out x kB_out) / (B_in x kB_in); k the adjusted-over-raw close ratio of the
  day as `score._ratio`; B the benchmark (SPY or IWM by the row's universe) at the same auctions. Cost enters once, at the
  pick hurdle (section 7.2), as a known function: it is never learned.
- PRICES: EVL-WL-O1, P_in the opening print of D and P_out the closing print of D; EVL-WL-ON, P_in the closing print of D
  and P_out the opening print of D+1. The print is the listing exchange's record with condition O (else Q) at the open,
  6 (else M) at the close (`score.CONDITIONS`); the listing exchange is the exchange of the first condition-6 record in
  P's closing auctions (`universe.closing_print_exchange`'s rule); the benchmarks' exchange is ARCA (`score.BENCH_CODE`).
- THE LIMIT AT ENTRY: P_in above 1.25 x the raw close of P: no row (status `limit`).
- BAR BASIS: when the gateway does not admit `v2/stocks/auctions` at the job's start, or a row lacks a print on either
  leg, both legs come from the SIP 1Day bars (raw open and close), with `basis_bar` 1. A row with no exit print and no
  exit bar within 5 sessions is dropped (status `no-exit`, counted: delistings, mergers and halts inside a one-session
  hold).
- TRAINING ROWS: the print-basis rows when a learner has at least 200,000 of them over at least 500 sessions; otherwise
  every labelled row, with `basis_bar` as a column (0 at every decision). A learner with fewer than 100,000 labelled rows
  or 500 sessions fails G1.

### 3.7 Row weights

- Each calendar year of D carries equal total weight (2026's rows, 199 sessions, as much as a full year's).
- ALIVE: the issuer filed any form with a filingDate in the 365 days before the clamp (S1, filing dates at or before
  2026-10-16). Within a year, a cell's COVERAGE is its labelled rows over its issuer-sessions with a pool-family event and
  a SYMBOL; when one cell's coverage is more than 10 points below the other's, its rows are weighted by the ratio of the
  two coverages (at most 3). This corrects in part for names whose bars stop when they leave the exchange (survivors are
  over-represented otherwise); ALIVE is a weight, never a feature.

### 3.8 Never read

`company_tickers.json` and `company_tickers_exchange.json`; Alpaca's asset status, tradable flag and exchange; S1's current
tickers, exchanges and former names; S1's `acceptanceDateTime`; any verdict, summary, article body, filing text or model
call; 8-K/A and Form 4/A; any XBRL value; any outcome, mark, look or band of the House; any 2020 record; any record timed
after the clamp in a training table. S1's current SIC is read only as section 3.4's fallback.

## 4. Features

Every input is read by one stdlib function, `league/events/warm/features.py` `features(cand, store, tau)`, over a store of
the House's schema: the history store (section 3) or the House's own (section 7). Inputs obey section 2.1 (stored before
tau; market data by the 16-minute rule). A missing input reads 0 and sets its listed indicator. Order, definitions and
scaling never change within a version; `FEATURES_SHA` is the sha256 of the canonical JSON of the ordered column names,
their definitions' version string and the sha256 of `features_spec.py`. WITHIN-SESSION RANK: (rank - 0.5) / n over the
session's kept candidates that have the quantity, ties at their mean rank, 0 for a candidate without it. No column
names, hashes or encodes an issuer, and no column groups past labels or returns by issuer or by any group of fewer than
200 issuers.

COMMON, in this order:
1. Primary pool program dummies, the first pool program the baseline (EVL-WL-O1: 3; EVL-WL-ON: 5).
2. `multi`: two or more pool programs select the issuer (1).
3. 8-K item groups over the issuer's E8K filings (form exactly `8-K`) knowable in the learner's EDGAR window (EVL-WL-O1: D's
   open window, [09:00 ET of P, 09:00 ET of D); EVL-WL-ON: D's close window, [P's close decision time, D's close decision
   time)): `it101`, `it201`, `it202`, `it502`, `it701`, `it801`, `it901`; `it_distress` (any of 1.03, 2.04, 2.05, 2.06,
   3.01, 4.02); `it_capital` (any of 2.03, 3.02, 3.03) (9).
4. For a feature event that is an article: `src_benzinga` (its `source` contains "benzinga"); `hl`, the within-session
   rank of its headline's characters (2).
5. `n_art` and `n_att20`, within-session ranks of PREREG-EVL-7 section 1.4 item 8's counts (single-symbol articles naming
   the ticker knowable in the primary pool program's window; in the 20 sessions before it); `first20`: the issuer is in
   none of this learner's kept candidate sets of the 20 previous sessions (3).
6. `mon`, `fri`: D is the first / the last session of its calendar week (2).
7. ln(adv20 / 1e7); ln(prev_close / 20); ln(sig20 / 0.03); `bench_iwm`; SIC groups as of D: bio (2833-2836, 8731), tech
   (3570-3579, 3600-3699, 7370-7379), fin (6000-6799), energy (1000-1499, 2900-2999) (8). sig20: the standard deviation of
   the 19 daily log changes of the issuer's 20 latest raw SIP daily closes of sessions before D, floored at 0.005 and
   capped at 0.25 (PREREG-EVL-7 section 1.4 item 10).
8. r1, r5, r20 and `hist_missing`, PREREG-EVL-7 section 1.4 items 11-12 word for word (raw closes; when fewer than 20 are
   stored, sig20 is the universe row's sigma60 when stored, else 0.03, and those columns read 0) (4).
9. The 16 `KEYWORDS` flags of the feature article's headline and `dup72`, PREREG-EVL-7 section 1.4 item 13 word for word
   (`goal-2026-10-19/evl7/reader/features_spec.py`, sha256
   b2f3aaaacccff9194b142b51e13e6a926cc1c18ff1b00682c87e9f97ecdcab85, copied into `docs/prereg/evl-9/`) (17).
10. From the issuer's SEC history: `ern_sched` (an item-2.02 8-K in the window whose issuer's previous item-2.02 8-K was
    accepted 70-110 days earlier); `ern_first` (an item-2.02 8-K in the window and none in the 365 days before it);
    `n8k365`, the within-session rank of the issuer's 8-Ks accepted in the 365 days before the window (3).
11. `g`: the frozen tree score of section 5.1, standardised by its out-of-fold mean and standard deviation (1).
12. `basis_bar`: 1 for a history row labelled on daily bars, 0 otherwise and at every decision (1).
EVL-WL-O1 ADDS: the feature event's knowable hour (ET) in `overnight` [20:00, 04:00), `pre` [04:00, 07:00), `late` [07:00,
09:00) (the baseline: 09:00-20:00 of P) (3); `ln_ins` = ln(1 + V / $50,000), V the INSIDER BUY sum without its floor (a
director or officer reporting owner; shares x price of P/A transactions dated in the 10 calendar days ending on the
acceptance date, Eastern, each once, a missing price 0) over the issuer's Form 4s knowable in D's open window; `ins_top`:
such a Form 4 has a reporting owner whose officer title matches the regular expression
`(?i)\b(chief executive|ceo|chief financial|cfo|president)\b` (2). Form 4's 10b5-1 flag is never read.
EVL-WL-ON ADDS: `morning` (feature event knowable 09:00-12:00 ET of D) and `before` (before 09:00 ET of D) (2); `dmove` =
clip(ln(m1530 / prev_close), +-0.5), `dmove_missing`, |`dmove`| (3); `gap` = clip(ln(m0930 / prev_close), +-0.5),
`gap_missing` (2); m1530 and m0930 the '1530' and '0930' marks of D by `run._mark_1530`'s and `run._marks_0930`'s rules.

So D = 59 columns for EVL-WL-O1 and 63 for EVL-WL-ON.

## 5. The trainer (sealed, on blake-desktop)

The trainer runs inside the job (section 1.1), on blake-desktop (x86-64, Python 3.14.7, numpy 2.5.3, the reference
environment pinned in the receipt), outside `league/` (numpy is allowed there; the House stays stdlib). WHY THE DESKTOP:
S1 is 1.57 GB while the House's SEC reader caps a body at 30 MB (`league/events/gw.py`); the desktop's SEC requests do
not share the House's 10-a-second limit; and nothing heavy runs on the box that trades.

### 5.1 The tree score g

- Target: y minus its session's weighted mean; row weights of section 3.7 (normalised to mean 1).
- Columns: section 4's, without `g`.
- Bins: 32 table quantiles a continuous column (`np.quantile`, linear, duplicate edges dropped); binaries 2.
- Shape: depth 3, learning rate 0.05, leaf value sum(w r) / (sum(w) + 2,000); gain sum(w r)_L^2 / (sum(w)_L + 2,000) +
  sum(w r)_R^2 / (sum(w)_R + 2,000) - sum(w r)^2 / (sum(w) + 2,000); a split needs at least 2,000 rows AND at least 200
  distinct issuers on each side (the issuer count is checked for the best split; when it fails the node is a leaf); ties
  to the lowest column, then the lowest bin; sums by `np.bincount` in table order.
- Rounds R*: fitted on the first 80% of sessions and scored on the last 20% at 25, 50, 100, 150 and 200 rounds by the mean
  within-session Spearman correlation of score and y; the best wins, ties to fewer. Nobody reads R*.
- Cross-fit: five contiguous session folds give the out-of-fold score g_oof; G_full is fitted on all rows at R*; g is
  standardised by g_oof's weighted mean and standard deviation.

### 5.2 The ridge prior

- Columns: section 4's, with g = g_oof. Within each session, x~ and y~ are the weighted deviations from the session's
  weighted means. A_h = sum w x~ x~', b_h = sum w x~ y~, W_h = sum w (float64, in table order).
- A_0 = (N_EQ / W_h) A_h, b_full = (N_EQ / W_h) b_h, N_0 = N_EQ = 25,000 rows.
- beta_full: section 7.2's solve on (A_0, b_full, N_0). SIGN STABILITY (the red team's registered inner procedure): the
  same solve on each era fold (sessions of 2022, 2023, 2024, and 2025-2026), each scaled to N_EQ; Z = the columns whose
  fold coefficient's sign differs from beta_full's (a zero differs) in 2 or more of the 4 folds; beta' = beta_full with Z
  set to 0; b_0 = A_0 beta'. The prior says "about N_EQ rows with E[y | x] = x . beta'"; it never decays.

### 5.3 Determinism

The trainer runs twice in the job from the same canonical tables. Equal: that model. Unequal only in the tree part: the
FALLBACK, g := 0, its column dropped and the prior refitted without it (the flag in the receipt). Unequal in the ridge
part beyond 1e-12 relative in any number: no model (G4). Sums in a fixed order, explicit sort keys, PYTHONHASHSEED=0,
floats written as repr, JSON with sorted keys.

### 5.4 The model files and the receipt

- MODEL FILE (one a learner; machine-only): the columns and FEATURES_SHA, the bin edges and trees (or the fallback flag),
  g's mean and standard deviation, A_0, b_0, N_0, Z, TABLE_SHA, CODE_PIN_9's sha, and META: the outcome-free records the
  House's look-backs need before its own store's `complete_from` (per CIK, the 8-K acceptance times and item-2.02 flags
  from 2025-10-01; per ticker and session, the single-symbol article counts of the 20 sessions before the lane's store
  begins; the history twin's kept (session, CIK) sets of the 20 sessions before the clamp). MODEL_SHA is its sha256.
- RECEIPT (`docs/prereg/evl-9/TRAINING-RECEIPT-<id>-v<n>.json`, public): CODE_PIN_9's sha and the pinned files' sha256;
  RAW_SHA; CANON_SHA, TABLE_SHA, LABEL_SHA and MODEL_SHA; FEATURES_SHA; rows by year, pool program and ALIVE cell; dropped
  rows by cause; the print and bar basis counts; every gate's flag and counts; the fallback flag; times and the
  environment. It holds NO fit statistic, coefficient, R*, Z, quantile, information coefficient or label summary. Its
  commit is T_M, and a committed receipt binds the version to its model.

## 6. Gates, code and build

### 6.1 The gates (run by the job, in order; any failure is a VOID, section 1.2)

- G1 COVERAGE: per learner at least 100,000 labelled rows over at least 500 sessions; at least 2,000 rows in every calendar
  year; label coverage (labelled over kept) at least 0.80 overall and at least 0.50 in every (year, ALIVE) cell.
- G2 PARITY on the overlap sessions (every lane session from 2026-10-19 through the last session closed before
  CODE_PIN_9; at least 3): the history builder over the vault's records of those sessions (feature data only, never a
  label, never in a training table) against the same function over a read-only copy of the House's store taken by the
  captain (the job reads only `filings`, `documents`, `form4_owners`, `form4_tx`, `news`, `sessions`, `universe`,
  `cik_info`, `eligibility`, `bars`, `marks` and the pool programs' `intents`; a lint test proves it). Per pool program
  pooled over the sessions: Jaccard of the (session, CIK) candidate sets at least 0.90, except EVL-ERN-DROP-ON and
  EVL-CTRL-ERN-UNDER-ON, whose live sets must be at least 0.95 contained in history's (section 3.5); on matched
  candidates, every feature column equal within 1e-9 (relative) on at least 90% of rows, and primary events' knowable
  times within 1 second on at least 99%. The counts are in the receipt.
- G3 LEAKAGE: static, the builder, label, universe and trainer modules name no source of section 3.8 and import nothing
  from `league.events.verdicts`, `screen`, `bands` or score's outcome writers; dynamic, no training-table record timed
  after the clamp, no row with `inputs_at` >= its tau, no label exit after 2026-10-16, no 2020 or 2021 entry or exit
  session, and the TRUNCATION AUDIT: 20,000 sampled candidates a learner and every candidate with an event within 15
  minutes of a window edge recomputed from tables cut at their tau must match byte for byte (it caught every planted
  boundary, latest-version, adjusted-level and window-end leak with 26-45 mismatches or more and gave no false alarm on a
  clean builder, `data/sim_truncation_audit.py`).
- G4 DETERMINISM (section 5.3). G5 FINITE: every model number finite and the House's solve of section 7.2 on (A_0, b_0,
  N_0) finite with a positive-definite system.

### 6.2 The code (pinned at CODE_PIN_9) and the build

THE PINNED CODE: `league/events/warm/` (stdlib: `spec.py` constants and the column list; `features.py`; `label.py`;
`pit.py` the universe of section 3.4; `twin.py` the history twin of section 3.5; `gates.py`; `model.py` load and verify;
`house.py` the scorer of section 7) and `scripts/warm/` (desktop: `fetch_sec.py`, `fetch_news.py`, `fetch_price.py`,
`hist_store.py`, `build_table.py`, `train.py` (numpy), `receipt.py`, `run_job.sh`), with their tests. The House release
carries `league/events/warm/` byte-identical to CODE_PIN_9 (a test compares each file's sha256 with the pinning
amendment's list). Integration outside the pinned files (run.py's hook, book.py's rows, store.py's tables, programs.py's
rows, screen.py's registry, the report) is tested, not pinned: a change there that changes any decision of this file's
programs is a new version.

THE BUILD ITEMS (the captain's ship list; this file wins over it):
- B0 probes (count-only, `scout/probe_counts.py` P1-P4, and P5 for auctions after B1): article ids a day, delisted bar
  coverage, the paper keys' minute budget, assets by status; counts only.
- B1 `gateway/lib/caps.mjs`: one row `['GET', /^v2\/stocks\/auctions$/]` in `VENUE_PATHS.alpaca` (DATA_PREFIXES already
  routes `v2/stocks/` to the data host; the path is not admitted today, as PREREG-EVL-8's FINDING 3 also found) and its
  tests (GET admitted, POST refused, a per-symbol path refused).
- B2 `programs.select` gains an optional `since` (default the program's registration time, unchanged), used only by the
  history twin; a test shows every earlier program's intents identical with and without it.
- B3-B5 the pinned code above; `floor_box.py put-data <file> --sha256 <MODEL_SHA>` (new: uploads one file into the House's
  `state/warm/` and verifies its hash; no such command exists at rel/1019g).
- B6 the House release: run.py's isolated warm part at the open and the close with its catch-up kinds
  (`decide-open-warm:<day>`, `decide-close-warm:<day>`) and the pre-pass for the ON learner's '0930' and '1530' marks;
  book.py's rows in ROOM; store.py's additive tables (section 7.4); programs.py's rows (prereg 9, COUNT_FROM_9 read from the
  pinning amendment's registry); screen.py's PREREG-EVL-6 registry with the POOL control; R3's authorizer refusing the
  warm tables and the vault; the report's lines (section 11.6); the docs and the site's lane_v1, evolved, not redesigned.

SHIP ORDER (deploy windows: never 12:55-20:05Z on a trading day, never with an order in flight, CI green on the exact
head): B0 and the price-free fetch now, on the desktop; B1 in the next gateway window (20:05Z Oct 22 with release 1019h,
or earlier if reviewed); T_F the hour PREREG-EVL-6 is frozen and a check of this file says freeze; B2-B5 and their tests
built against this text the same day, CODE_PIN_9 right after a close; the job that night, T_M before 13:15Z if it runs
clean; B6 in the next House window after T_M (real money from the first counted decision after it; the catch-up covers
COUNT_FROM_9 to the release); `put-data` outside the blocked window.

## 7. The House: forward refits and picks (stdlib)

### 7.1 The forward stream

- Nightly after the score, for each entry session s of the learner whose pool outcomes are all terminal, `warm_stats`
  (A_s, b_s, n_s) is written ONCE from the candidates and features written at tau_s (section 7.4) and FORWARD LABELS:
  y = clip(G / sig20, -5, 5), G = exit_px / entry_px - bench_exit / bench_entry of the candidate's pool outcome (its
  stored prices, status settled, `tradable` 1), within-session demeaned, every sum a `math.fsum` in (entry day, CIK)
  order.
- The lane's sessions from 2026-10-19 to COUNT_FROM_9 are RECONSTRUCTED ONCE, each as of its own tau_s (stored-before
  reads; market data by section 2.1's rule), written with `eligible` 0: they train and never count.

### 7.2 The fit and the picks at tau

- A = A_0 + sum_s 2^(-(n(D) - n(s)) / 40) A_s over `warm_stats` rows written before tau with n(D) - n(s) <= 250; b likewise;
  N_w = N_0 + sum_s 2^(-(n(D) - n(s)) / 40) n_s.
- d_j = sqrt(A_jj / N_w); when d_j < 1e-9, d_j := 1 and row j and column j of A and entry j of b are set to 0. beta =
  diag(d)^-1 (diag(d)^-1 A diag(d)^-1 + 8,000 I)^-1 diag(d)^-1 b, solved by Cholesky in float64 (PREREG-EVL-7 section 1.5's
  ridge with the prior added).
- xbar_D = the mean of x over D's kept candidates; e_i = (x_i - xbar_D) . beta; c_i = (score.cost_bp(adv20, E_prev,
  'entry') + score.cost_bp(adv20, E_prev, 'exit')) / 1e4; z_i = e_i - c_i / sig20_i; ahat_i = sig20_i x z_i, the predicted
  after-cost abnormal return. The level is the fixed prior that the pool's gross abnormal mean is zero: never learned.
- PICKS: the candidates eligible to be picked (section 2.3) with z_i > 0, ranked by ahat_i (higher first), then adv20
  (higher first), then event id (ascending); the first K = 8 are the learner's intents of D (rank_key = ahat_i). Fewer
  or none is allowed.

### 7.3 Failure, isolation and the record before the release

- NO WARM-UP beyond a verified model: a version picks from its first counted decision.
- FAIL CLOSED: a decision with no model whose sha256 is MODEL_SHA, a model whose clamp is not before its first counted
  session, an unreadable pool, outcome or input, or a non-finite fit picks nothing; its receipt says why.
- ISOLATION: the warm part of a decision runs after every row of PREREG-EVL-1 to -8 (PREREG-EVL-7's learners included)
  is decided, under its own bound (90 seconds at the open, 120 at the close); its failure or expiry never cuts an earlier
  row, and that decision is then made for the learner BY ITSELF later, exactly as of tau, in shadow only.
- THE RECORD BEFORE THE RELEASE: every decision from COUNT_FROM_9 to the first one the House release carrying the pinned
  code and the verified model makes is decided by that release, once each, oldest first, exactly as of its tau, with its
  receipt kind; none is ever traded and none is decided again. A written decision is never decided again.

### 7.4 What is written (additive; SCHEMA_VERSION stays 1)

`warm_models` (program, version, model_sha, count_from, verified_at); `warm_cands` (program, version, day, tau, cik, event,
feature_event, families, features, inputs_at, e, z, ahat, eligible, picked, rank), written once; `warm_stats` (program,
version, day, A, b, n, keys_sha), written once; `warm_fits` (program, version, day, tau, n_sessions, N_w, keys_sha,
beta_sha). The coefficients themselves stay in the machine-only `warm_state`. A nightly recompute of the last decisions
alarms on any mismatch and never rewrites.

### 7.5 The money hold

When the nightly recompute alarms on a written decision, or a decision fails closed for a model or input fault, the
learner's real money is HELD (no new buys; exits by their rules) until the captain's amendment records the cause; the
shadow continues unedited. A fix that changes any decision is a new version.

## 8. Real money

- LEARNING from the first counted decision after both (a) the House release carrying the pinned code is live and (b) the
  House holds the verified model: a target of 2% of E_prev, whole shares at the limit (1.25 x the previous SIP close), one
  share when that rounds to none and one share is at most 5% of E_prev and fits every wall, at most 8 open (PREREG-EVL-3
  section 2). The full-size shadow beside it is the record: every pick, at its auctions, whatever real money buys.
- PROBE and SIZED as PREREG-EVL-6 gives its later versions, with A99's clauses (its section 6): Probe at most 14 open,
  a Probe or Sized buy the fewest whole shares reaching 0.8 of its band's target, never above 5% of equity at Probe nor
  the name's 10% wall at Sized, judged again by every cap; Sized a target of 10%, at most 8 open. A learner never has more
  than 8 intents a decision, so 8 bounds it in every band.
- The book's picks of a learner are its intents in rank order less the book's skips (a name given to an earlier program at
  the auction, the sale gate, no whole share, cash, A85's reservation, the walls, the day's order line, section 2.3 (ii)
  read on real lots).
- ROOM: in each band, after every row of PREREG-EVL-1 to -8 and before R3's births of that band (A101); EVL-WL-O1 at the
  open, EVL-WL-ON at the close. The event kind's day order line refuses this file's entries after every earlier PREREG
  row's; an exit is never stopped by it. At most 16 entries and 16 exits a day for the two learners.
- IN REAL MONEY ONLY, EVL-WL-ON keeps PREREG-EVL-4 and -5 section 1.3's 8-K guard
  (`book.next_open_event(..., raised=True)`); the shadow keeps every pick.
- A RETIRED version buys nothing more; its decisions continue as a shadow record and its open lots exit by their rules.
- Every wall is unchanged and judges every buy: <= 10% of equity a name, <= 100% invested, no margin, no shorts; the
  loss budget ($400 net in any 20 sessions, $800 net total, realized plus open risk at the 95% holding-period loss); the
  open-risk weight max(0.10, 1.65 x sigma x sqrt(h)); the kill switch, the daily stop and the drawdown stop.

## 9. The judge

- PREREG-EVL-6 sections 1-3 AS FROZEN, word for word, for each version of this file from its COUNT_FROM_9: its record the
  version's settled TRADABLE intents whose events are knowable after COUNT_FROM_9, valued by PREREG-EVL-1 section 5's a
  and r (the replay); its blocks, money-weighted values, margin, p, q and p_I; its minimums, looks, alpha(S), RETIRE and
  PASS with every guard; runs, stays, Sized, demotion and re-promotion; seed strings f"{id}|v{version}|evl6|{tag}S{S}"
  with this file's ids.
- A learner is a READ version wherever a rule names one: its CONTROL is its POOL record (section 2.4).
- RUNS: a run that reaches its 60th block unpassed ends and the next run starts (PREREG-EVL-6 section 2), each charged
  when it starts (section 10). A RETIRE retires the version for good (section 1.3).
- The code never edits the judge that judges it. If PREREG-EVL-6 is not frozen, this file is not registered.

## 10. Expected false passes, the charge, and the lane's budget

- PER RUN (section 11.2; under PREREG-EVL-6's final rule, 1,000 synthetic programs a cell, within 120 sessions): a warm
  learner with no forward edge passes its first run 0.029-0.104 of the time over every cell measured (noise history; a
  decayed history edge at ic 0.05 and 0.08; the knife edge; its own pick direction drifting 10 or 20 bp a unit; phi_day
  0.20; with and without 1% persistent issuer effects; pools of 300 and 600), the worst 0.104 (SE 0.010: a drift of 20
  bp a unit along its own pick direction, with 1% issuer effects; 0.103 at phi_day 0.20 without them); the base model
  0.029-0.033. A version that never passes is tested twice within 120 sessions; either run passes 0.127-0.201 of the
  time (0.201 at that drift with phi_day 0.20), and over 300 sessions, about 3.8 runs, 0.330-0.363.
- THE CHARGE c9 of each run: the larger of PREREG-EVL-6's frozen per-version and per-run charge c6 (0.13 in its final
  text, its worst plausible 0.130 rounded up) and this file's own worst plausible first-run rate under PREREG-EVL-6's
  frozen constants rounded up to 0.01 (0.11: 0.104 rounded up under its final text). So c9 = 0.13 if PREREG-EVL-6
  freezes its final text; if it freezes other constants, the freeze of this file re-runs `judge/run_final.sh`'s null and
  char grids under them and takes the result.
- RESERVED AT T_F, DRAWN AT T_M: 2 x c9 (0.26) is reserved in the lane's count at T_F and drawn at T_M; a VOID returns it.
  Every later run draws c9 when it starts, whatever the room left (PREREG-EVL-6 section 3).
- THE LANE'S BUDGET, on PREREG-EVL-6's basis (its final text: a lifetime of 30 x c6 = 3.9; used at REGISTERED_AT_6, 15 x
  c6 = 1.95 plus c6 for each seatable birth registered before it): before this file, 1.95 + PREREG-EVL-7's draw (2 x
  0.13 = 0.26 on that basis) + PREREG-EVL-8's draw (3 x 0.11 + 2 x 0.13 = 0.59 on that basis) + 0.13 x B, B the seatable
  births and fresh runs registered before REGISTERED_AT_9 (A104's three day-news births among them if registered): 2.80 +
  0.13 B. THIS FILE: 0.26. AFTER: 3.06 + 0.13 B of 3.9; LEFT: 0.84 - 0.13 B (six versions or fresh runs, less B). The
  registering amendment computes the actual sum from SEATING and the frozen files' own draws; if what is left cannot hold
  0.26 but holds 0.13, only EVL-WL-ON (the larger pool) is registered; if it cannot hold 0.13, this file is not registered.
- EVERY REPORT shows the lane's expected false passes three ways (PREREG-EVL-6 section 5): the count (c9 a run), the base
  model (0.04: 0.033 rounded up a run) and the stresses' worst (0.15: 0.149 at day-shock momentum 0.40 with rho_day
  0.30, rounded up).

## 11. The calibration record (synthetic only)

### 11.1 Files (copied with their sha256 into `docs/prereg/evl-9/` at the freeze)

- The scout (`evl9/scout/`): `count_submissions.py`, `count_edgar_index.py`, `count_form345.py`, `count_listed_events.py`,
  `count_survivorship.py`, `check_items.py`, `check_accept_offset.py`, `check_browse_atom.py`, `sample_accept_times.py`,
  `fetch_budget.py`, `probe_counts.py` and their outputs (counts only).
- The data lens (`evl9/data/`): `budget_data.py`, `count_gap.py`, `fsds_members.py`, `sim_basis.py`,
  `sim_truncation_audit.py` and their outputs.
- The learners lens (`evl9/learners/`): `calib_evl9.py` (imports PREREG-EVL-7's learner-lens generator
  `evl7/learner/calib_learner.py` unchanged), `run_all.sh`, `run_rest3.sh`, `run_phi.sh`, the outputs
  `calib_evl9.{tune,null,null2,char,phi,life,power,powerw,tune2}.jsonl` and `calib_evl9.report.txt`; `fetch_budget9.py`,
  `house_cost9.py`, `gbt_cost9.py` and their outputs; `draft_prereg.txt`.
- The red team (`evl9/redteam/`): `rt_warm.py` (sha256 d61f0cae...), `rt_skew.py` (sha256 2c155bc5...), `run_all.sh`,
  `run_rest.sh`, their outputs and `rt_warm.report.txt`, `PREREG-EVL-9-clauses.redteam.txt`, `build.redteam.txt`.
- The judge (`evl9/judge/`): `calib_evl9_final.py` (sha256 5996d0cc...; the learners lens's paths screened by
  PREREG-EVL-6's final rule: looks from the 9th block, alpha 0.012 / 0.010 / 0.004, values min(n_s, 14) x (B_s - 10 bp),
  RETIRE, the guards, runs), `run_final.sh`, `calib_evl9_final.{null,char,power,life,stress}.jsonl` and
  `calib_evl9_final.report.txt` (sha256 a2082be3...); `rt_skew_final.py` (sha256 e077585a...) and its output;
  `count_sessions.py` (run on an archive of rel/1019g); `fetch_budget_judge.py` and its output.

### 11.2 False passes (one run within 120 sessions unless stated; final rule / drafted rule on the same paths)

The generator is PREREG-EVL-7's learner lens's (3,000 issuers in 11 sectors, Zipf repeats, sigma 1-10% a session,
t(3) tails and jumps, a session-correlated day shock with persistence phi_day, a pool of about 300 candidates a session
with 40 features), with the learners lens's history prior: A_0 = 25,000 x the within-session feature covariance and b_0 =
A_0 x a history slope drawn from its sampling law over 500,000 history rows (`learners/calib_evl9.py`). WORST: rho_day
0.15, crash days, left-skewed events, a 20 bp AR 0.97 pool drift and 1% persistent issuer effects; NO TAU: the same
without the issuer effects. N1: every candidate's mean a is exactly 0; the decayed edge: history carried an information
coefficient ic_h that the live stream does not; N2, the knife edge: the features rank the pool for real and the best 5%
have mean exactly 0; CHAR: a zero-mean AR 0.97 drift along the learner's own history index. 1,000 programs a cell (SE
about 0.009), fresh seeds from 191,000,001.

| cell | warm, run 1: final rule / draft rule | either of two runs within 120 sessions (final rule) |
|---|---|---|
| N1, noise history (ic_h 0), worst | 0.092 / 0.098 | 0.148 |
| N1, decayed edge ic_h 0.05, worst | 0.075 / 0.109 | 0.143 |
| N1, decayed edge ic_h 0.08, worst | 0.069 / 0.102 | 0.150 |
| the same, no tau | 0.077 / 0.104 | 0.144 |
| the same, no tau, pool 600 | 0.078 / 0.111 | 0.134 |
| the same with tau, phi_day 0.20 | 0.091 / 0.123 | 0.171 |
| the same, no tau, phi_day 0.20 | 0.075 / 0.103 | 0.140 |
| N2 knife edge ic 0.08, history the same structure, worst | 0.064 / 0.093 | 0.127 |
| CHAR 10 bp a unit, decayed edge 0.08, worst | 0.088 / 0.107 | 0.158 |
| CHAR 20 bp a unit, decayed edge 0.08, worst | **0.104** / 0.131 | 0.184 |
| CHAR 10 bp, no tau, phi_day 0.20 | 0.083 / 0.121 | 0.164 |
| CHAR 20 bp, no tau, phi_day 0.20 | 0.103 / 0.133 | **0.201** |
| BASE (rho_day 0.05, symmetric, no drift), decayed edge 0.08 | 0.029 / 0.047 | 0.069 |
| BASE, noise history | 0.033 / 0.038 | 0.064 |
| COLD learner (PREREG-EVL-7's), worst | 0.084 / 0.117 | 0.161 |
| COLD, no tau, phi_day 0.20 | 0.082 / 0.118 | 0.168 |
| COLD with CHAR 10 bp, no tau, phi_day 0.20 | 0.115 / 0.144 | 0.190 |
| LIFE (400 programs, 300 sessions): decayed edge, no tau, phi_day 0.20 | run 1 0.080 / 0.110 | any run within 300 sessions 0.330 (3.88 runs started on average) |
| LIFE with CHAR 10 bp | run 1 0.098 / 0.150 | 0.363 (3.74 runs) |
| STRESS (named, not binding; PREREG-EVL-6's stress list), rho_day 0.30, crash days, skewed events, 20 bp drift, phi_day 0.20 | 0.098 / 0.135 | 0.183 |
| STRESS, the same at day momentum phi_day 0.40: warm / COLD | 0.149 / 0.191; cold 0.166 / 0.197 | 0.267; cold 0.271 |
| STRESS, phi_day 0.25, worst without tau | 0.080 / 0.112 | 0.158 |
| STRESS, CHAR 30 bp, no tau, phi_day 0.20 | 0.120 / 0.161 | 0.236 |

(Seeds from 195,000,001 for the stresses, `judge/calib_evl9_final.stress.jsonl`.) The one cell above 0.13 for a warm
learner is day-shock momentum at rho_day 0.30, which is a property of the day shock (the cold learner reads 0.166 on it,
and PREREG-EVL-6 states its own stresses for any program).

- The warm learner's rates sit with the cold learner's on the same paths and under PREREG-EVL-6's own worst plausible
  0.130 for a fixed program: history does not raise the forward judge's false-pass rate. A stable picker exposed to a
  drift along its own pick direction adds at most about 0.03 (0.104 against 0.069; 0.103 against 0.075 at phi_day
  0.20) at 20 bp a unit.
- THE BREAKS THE RED TEAM FOUND (under the drafted rule, `redteam/rt_warm.report.txt`): an issuer target encoding passes
  0.9475 (0.8975 at the worst corner) where the null holds a 1% persistent issuer effect: section 4 forbids it. A
  training snapshot holding the first 10 forward sessions' outcomes, which those sessions are then decided with, passes
  0.095 generic and 0.135 at a forward half-life of 10: the clamp and COUNT_FROM_9 forbid it. A person choosing the best
  of six procedures by their last 60 history sessions passes 0.048-0.080 against 0.033-0.065 blind: one procedure is
  fixed here and nobody reads a fit. A history taught the wrong sign (FLIP) trades at about -106 bp a pick and is retired
  at its lower tail in 65.7% of paths, its run ending on average at session 35. A look-ahead column in history costs
  power, not false passes: trained on it, the picks' true forward edge was +6.9 bp against +43.9 clean and the learner
  promoted 0.077 against 0.143 (PWR-leak-ic05, PWR-clean-ic05), which is why G3's audit protects the owner's sessions as
  much as the judge.

### 11.3 Power and the learning curve (P(promoted) by session 20 / 40 / 60 / 120, 400 paths a cell, pool 600, the
alternative of the pool losing 0.04 sigma beside an information coefficient ic; the picks' true edge in sessions 1-10
and 51-60)

| information coefficient, history | P(promoted) by session 20 / 40 / 60 / 120 | picks' true edge, sessions 1-10 -> 51-60 (bp) |
|---|---|---|
| 0.03, cold | 0.028 / 0.028 / 0.028 / 0.055 | -4.3 -> +3.3 |
| 0.03, warm rho 1 | 0.045 / 0.053 / 0.058 / 0.098 | +15.9 -> +12.9 |
| 0.03, warm rho 0.7 | 0.020 / 0.020 / 0.025 / 0.058 | +7.1 -> +8.5 |
| 0.03, warm rho 0 | 0.020 / 0.023 / 0.023 / 0.050 | -12.3 -> -0.9 |
| 0.05, cold | 0.058 / 0.078 / 0.090 / 0.220 | +21.2 -> +39.6 |
| 0.05, warm rho 1 | 0.115 / 0.165 / 0.205 / 0.340 | +55.8 -> +53.1 |
| 0.05, warm rho 0.7 | 0.088 / 0.105 / 0.120 / 0.230 | +39.2 -> +45.6 |
| 0.05, warm rho 0 | 0.018 / 0.030 / 0.040 / 0.115 | +1.0 -> +25.9 |
| 0.08, cold | 0.178 / 0.255 / 0.355 / 0.680 | +69.3 -> +97.7 |
| 0.08, warm rho 1 | 0.338 / 0.448 / 0.583 / 0.830 | +114.1 -> +111.4 |
| 0.08, warm rho 0.7 | 0.263 / 0.380 / 0.505 / 0.755 | +86.6 -> +99.9 |
| 0.08, warm rho 0 | 0.050 / 0.075 / 0.100 / 0.428 | +21.3 -> +68.5 |
| 0.05, worst corner without tau: cold / rho 1 / rho 0.7 | 0.070 / 0.098 / 0.103 / 0.270; 0.143 / 0.180 / 0.198 / 0.340; 0.140 / 0.165 / 0.178 / 0.335 | +14.7 -> +30.0; +54.4 -> +48.7; +37.2 -> +40.9 |
| 0.08, worst corner without tau: cold / rho 1 / rho 0.7 | 0.173 / 0.233 / 0.285 / 0.598; 0.325 / 0.445 / 0.553 / 0.813; 0.230 / 0.308 / 0.393 / 0.698 | +57.0 -> +86.2; +112.9 -> +109.0; +85.5 -> +96.4 |

rho is the correlation of history's true index with live's (1: the live structure; 0: unrelated). Promotion counts any
run (the second starts after the first's 60th block). `judge/calib_evl9_final.power.jsonl`, seeds from 194,000,001.

- THE PLAIN READING. At a plausible information coefficient (0.03-0.05) one run rarely promotes, warm or cold.
  A warm learner whose history has the live structure doubles the chance of a promotion by session 40 (0.165 against
  0.078 cold at 0.05; 0.448 against 0.255 at 0.08), because its first picks already carry the edge a cold learner reaches
  only after about 50 sessions (+55.8 bp against +21.2 in sessions 1-10 at 0.05). At rho 0.7 it gains less (0.105 and
  0.380). When history is unrelated it loses (0.030 and 0.075 by session 40) and recovers only by forgetting (+25.9 bp
  in sessions 51-60 against +39.6 cold at 0.05). So this file is a bet on rho, which no outcome-free count can measure;
  its charge is the same 0.13 a run whatever rho is, and its money is learning-size until its forward record passes.

### 11.4 Shape and skew (the red team's steamroller)

The red team's generator (`redteam/rt_skew.py`, imported unchanged: 3-8 picks a session from 800 issuers, every event's
mean a exactly 0) screened by PREREG-EVL-6's final rule, run 1 within 120 sessions, 1,500 programs a cell
(`judge/rt_skew_final.py`, seeds from 196,000,001):

| pick population | final rule | draft rule (`redteam/rt_skew.out*.jsonl`) |
|---|---|---|
| symmetric, sigma 3-8% | 0.021 | 0.051 |
| steamroller (a steady gain, a 1% chance of -30% a session), sigma 1% | **0.259** | 0.324 |
| the same, sigma 1-1.5% | **0.185** | 0.226 |
| the same, sigma 1.5-2.5% | 0.088 | 0.135 |
| the same at a 0.5% chance, sigma 1.5-2.5% | 0.048 | 0.061 |
| the same at a 0.5% chance, sigma 1-1.5% | 0.063 | 0.073 |
| sigma 2%, a 2% chance of -20% | 0.089 | 0.131 |
| sigma 3-8%, a 1% chance of -30% | 0.046 | 0.073 |
| a quarter / a half of the picks steamrollers at sigma 1% | 0.035 / 0.046 | 0.054 / 0.065 |

- A mean-zero pick set of low-volatility names with a rare large loss passes a one-sided sign-flip over session blocks
  far above the cap, under the final rule too, and a learner trained on years of history is the kind of program that can
  concentrate on it (a merger target after its 8-K item 1.01 is the type). Below sigma20 = 1.5% the rate reaches
  0.185-0.259 at a 1% chance of the loss (0.063 at 0.5%); at and above it every cell measured is at most 0.089. Hence
  THE SHAPE GUARD of section 2.3, and the report's tail line (section 11.6).
- THE OWNER AND THE CAPTAIN SHOULD SEE: this is a property of the screen, not of learning. PREREG-EVL-6's plausible grid
  holds left-skewed events but not this shape, so any program whose events are low-volatility steamrollers is exposed;
  this file guards only its own versions.

### 11.5 The label basis and the leak audit (the data lens)

- `sim_basis.py` (1,454 training sessions x 450 events, 60 features of which 10 carry signal, true expected abnormal
  return sd 6 bp, idiosyncratic sd 300 bp with t(4) tails, day shock 60 bp; scored forward on print-basis truth): trained
  on the print label, the top 8 a session earn 13.58 bp (oracle 14.70); on a bar label with random basis noise of 25 /
  100 / 200 bp, 13.59 / 13.42 / 13.14; with a basis bias correlated with liquidity of 2 / 5 / 10 bp per standard
  deviation, 13.00 / 11.14 / 8.32.
- `sim_truncation_audit.py` (a toy store with 30% edited articles and random 2:1 splits): the clean builder gave 0
  mismatches in 3 x 20,000; planted leaks gave 26-32 (knowable boundary within 5 minutes), 37-45 (latest headline
  version), 5,345-5,365 (an adjusted level) and 20,000 (a window ending a session late), each caught in every audit; at
  2,000 candidates the rare leaks showed only 1-5, hence 20,000 a learner plus every edge case.

### 11.6 Reported beside, never a judge input

Candidates, picks, N_w, the money hold, the parity and coverage counts, the share of picks with a below -15% beside the
pool's (the red team's tail line), and the basis counts, in the daily report; the realised information coefficient and
the learning curve to the captain and the owner only (outcome-derived: never to a designer).

### 11.7 What is not calibrated

The tree score's value (under every null it is one more column); real feature distributions; the real size of any edge;
the real history-to-live correlation rho (the one number that decides whether this file helps); the share of history
rows on print basis; Alpaca's coverage of names delisted 2022-2025 (probe P2).

## 12. The red team's causes and their guards

| cause | guard in this file | residual |
|---|---|---|
| Look-ahead inside history: restated fields, latest-version news, today's tickers, adjusted levels, S1's acceptanceDateTime, window edges | sections 3.3-3.8; the clamp; ratios from raw closes only; G3's lint and the 20,000-candidate truncation audit | late-print restatements in daily bars |
| Survivorship: today's map drops 29.0% of 2022's and 12.1% of 2025's insider-active issuers | point-in-time symbols from S2 only; `asof` bars; ALIVE coverage weights; G1's cells; counts by year | names whose bars Alpaca lacks after delisting (probe P2) |
| Choosing whether or how to register after seeing a fit | no price in the vault before CODE_PIN_9; the sealed job; a receipt of counts and hashes; machine-only model; COUNT_FROM_9 = T_M; VOID only by mechanical gates before T_M, at most two | a person can choose WHEN to start the job, as when to register any file |
| Training on counted sessions (BRK-OVL: 0.095-0.135) | the clamp at the close before the lane's first session; forward rows only from outcomes settled before tau; nothing counted before T_M | none |
| Issuer identity (W-TE-tau1: 0.9475) | no identity column; no label grouped by issuer or by fewer than 200 issuers; tree leaves of at least 200 issuers | none measured |
| Selection among procedures (SEL) | one procedure fixed blind; R* and Z chosen inside the sealed run; nobody reads them | none |
| History taught the wrong thing (FLIP; decayed edges) | prior weight 25,000 rows; forgetting at a half-life of 40; sign-stability zeroing; RETIRE, demotion, the loss budget | weeks of learning-size losses (section 11.2) |
| Steamroller picks: small steady gains, rare large losses | the shape guard (sig20 >= 0.015); the tail line in the report | section 11.4's remaining cells |
| Bar-versus-print label bias | auctions after B1; print-only training at >= 200,000 rows; `basis_bar` | a bias in the bar rows if prints are scarce |
| Train/serve skew | one features function over one schema; the history twin calls programs.py; G2 on the overlap sessions; the nightly recompute and the money hold | news versions, late storage, the tradable flag (counted) |
| Rate collision with the House | at most 100 Alpaca requests a minute on the shared keys with X-RateLimit-Remaining backoff below 120 and pauses 13:00-13:45Z, 19:30-20:20Z, 22:25-22:45Z and around the 01:40Z / 01:55Z jobs; at most 6.67 SEC requests a second from the desktop's own address | a slower build |
| Outcome-derived artefacts reaching later designers | machine-only model, tables and warm state; R3's authorizer; captain reads recorded | none |

THE RED TEAM'S CLAUSES (`redteam/PREREG-EVL-9-clauses.redteam.txt`), as this file takes them:
- R1 (times and counting): taken, with a fourth time (CODE_PIN_9) and the VOID deadline counted in sessions after it (5)
  in place of 96 hours after T_F.
- R2 (the vintage): taken, with the price-bearing fetch moved from "after T_F" to "after CODE_PIN_9"; the point-in-time
  SIC of FSDS added (the data lens's), so S1's current SIC is only a fallback.
- R3 (knowable times): taken word for word.
- R4 (the label): taken, with two changes: TRADABLE at a fixed E_REF of $2,000 (a constant, not a reading of the account),
  and, when the auctions endpoint is not admitted, the flagged daily-bar basis for both legs (the data lens's) in place of
  "no version entering or exiting at an opening auction is registered": both learners use an opening auction, a bar
  basis costs power only (`data/sim_basis.py`), never a false pass, and B1 should ship first.
- R5 (features): taken; R5 (d)'s one function is section 4's.
- R6 (training): taken in part: equal year weights, the ALIVE coverage weights and the era-fold sign stability are
  section 3.7 and 5.2's; the 2016-2019 years and the half-life of at least 120 are not (section 0).
- R7 (the sealed run): taken, with numpy allowed for the trainer on the pinned environment (two runs must agree, section
  5.3) and the receipt committed by the job itself.
- R8 (gates and VOID): taken, with the per-year symbol-coverage threshold dropped (most 8-K filers are not listed, so its
  denominator is undefined) and G2's thresholds set at 0.90 (Jaccard) and 90% of rows (features) in place of 0.95 and
  99%, because four skews are known and cannot be removed (news versions, late storage, the tradable flag, the two pool
  members' verdict reads); a failed G2 costs one night and one re-registration, never a charge.
- R9-R11, R13: taken. R11's re-entry: none after a RETIRE (section 1.3); PREREG-EVL-6's runs carry the unpassed.
- R12 (the shape guard): taken, measured again under the final rule (section 11.4).
- The red team's build list and tests (`redteam/build.redteam.txt`) are section 6.2's.

## 13. Honesty

- BLIND DESIGN. The scout, the data lens, the learners lens, the red team and the judge read code, documentation, the
  frozen and drafted rules, the facts files, record COUNTS of the public archives, API documentation and the literature,
  and ran synthetic simulations; none read, queried or computed any price, return, look, band, bar or P&L of any event,
  symbol or program, historical or live, from the House, the gateway, events.sqlite, live.sqlite, any run record or any
  market-data API. The scout fetched `submissions.zip` (filings metadata, no price) and counted it. Every constant here
  (the pools, the 59 and 63 columns, N_EQ 25,000, lambda 8,000, the half-life 40, K = 8, the ranking by ahat, the fixed
  level, the tree's shape, the shape guard, the window) was chosen on synthetic paths or from counts.
- THE CAPTAIN. The registering captain session (6e6a85b9) had read, on Oct 21, the per-program means of the shadow record
  of the lane's existing programs over Oct 19-20 and the lane's aggregate real-money figures; earlier lanes' agents read
  index-ETF, options and S&P 500 cross-sectional outcomes of 2016-2019 and 2021-2024. The captain chose none of these
  rules; every session of the window enters by rule, not by choice; the lane's own sessions enter only forward.
- NOBODY READS IN-SAMPLE FIT, before or after registration (section 1.4). Before CODE_PIN_9 none can exist: the vault
  holds no price. After it, the job prints counts and hashes only.
- OUTCOMES AT RUN TIME. The learners read pool outcomes settled and stored before each decision, the lane's sessions from
  Oct 19 included. That is the forward test this file registers, not a look: each pick is made before its own outcome
  exists and the record counts only events knowable after COUNT_FROM_9.
- WHAT THE PUBLIC CAN CHECK: the receipt's hashes against this text, the pinned code and the House's `warm_models` row;
  the record and its looks as for every program. What it cannot: the vault's content (licensed).

## 14. Cost

- METERED COMPUTE: $0.00 a day added. No model call, no paid feed, no new host; so A102 prices nothing, and no owner money
  step is needed.
- UNMETERED, ONCE, on blake-desktop (`judge/fetch_budget_judge.py`): SEC 40,023 requests, 1.67 hours at 6.67 a second;
  news 5,391 / 17,970 / 53,910 / 107,820 pages at 130 / 500 / 1,500 / 3,000 articles a day (0.9 / 3.0 / 9.0 / 18.0 hours at
  100 a minute; probe P1 fixes the rate), both before T_F; price-bearing data after CODE_PIN_9, 25,522-60,310 requests,
  4.3-10.1 hours at 100 a minute (2.2-5.3 hours at 190 if probe P3 finds a separate budget on the paper keys); the tree
  model about 1.3 hours a run at R* = 200 (1,400 rounds at 3.289 seconds, `learners/gbt_cost9.out`), the two runs and the
  two learners in parallel. Storage about 10-20 GB in the vault.
- THE HOUSE: seconds of CPU a decision (`learners/house_cost9.out`: a session's statistics 0.196 s, a decision's fit and
  predictions over 250 sessions 0.060 s, a 600-tree score 0.129 s, on synthetic data); a few data requests a decision for
  the ON learner's '0930' and '1530' marks; the gateway's Worker requests inside its $5 a month plan.

## 15. What is unchanged

Everything this file does not state is PREREG-EVL-1's to -6's (and -7's and -8's where frozen) and R3's, word for word:
the universe, the events, the knowable times, backfill and the shadow rule; the verdicts, their model, prompts,
parsing and the rule that the first stored answer is final; the execution model, auction prices, the fallback ladder,
score.py's costs and per-event returns and TRADABLE; every earlier program's rule, record, control and judge; the band
sizes; ROOM's order for every earlier row, the sale gate, A85's cash reservation and every real-money guard; the money
walls, the loss budget, the open-risk rule, the kill switch and the stops; Done, pivot and reporting (Done counts these
programs' events at Probe size or above like any program's, only after their own promotion, at realized after-fee P&L).
It adds no prompt, no verdict, no model call and no recorder.

## 16. Why these, and what argues against them (the judge's prior, stated before any outcome)

- WHY START WARM. A forward-only learner's early picks are its weakest (PREREG-EVL-7 section 5.4: at an information
  coefficient of 0.05 its picks' true edge rises from +25.8 bp in sessions 1-10 to +44.5 by 51-60), and PREREG-EVL-6's
  first look is at the 9th block, so the first look judges the weakest picks. Cross-sectional return prediction from many
  weak signals is learned best from many periods (Fama and MacBeth 1973, JPE 81(3); Gu, Kelly and Xiu 2020, RFS 33(5);
  Kelly, Malamud and Zhou 2024, JF 79(1)); a prior fitted on five years and shrunk to 25,000 rows gives the first picks
  that knowledge while the forward stream can still overrule it (ridge as a Bayesian prior: Hoerl and Kennard 1970,
  Technometrics 12(1)). Boosted trees capture interactions a linear score misses (Friedman 2001, Annals of Statistics
  29(5)); cross-fitting keeps their score honest as a column (Chernozhukov et al. 2018, Econometrics Journal 21(1)).
- WHAT THE STRUCTURED FIELDS CARRY. 8-K items differ in their price response (Lerman and Livnat 2010, Review of
  Accounting Studies 15(4)); opportunistic insider purchases predict returns where routine ones do not (Lakonishok and
  Lee 2001, RFS 14(1); Cohen, Malloy and Pomorski 2012, JF 67(3)); attention, staleness and timing of news and earnings
  move the next sessions (Tetlock 2011, RFS 24(5); DellaVigna and Pollet 2009, JF 64(2); Berkman, Koch, Tuttle and Zhang
  2012, JFQA 47(4)); short-term reversal and volatility (Lehmann 1990, QJE 105(1); Nagel 2012, RFS 25(7)).
- AGAINST. (1) Published and historical effects decay (McLean and Pontiff 2016, JF 71(1)); if rho is low the prior is a
  handicap for weeks (section 11.3). (2) Data-snooping is the classic failure of history-trained rules (Lo and MacKinlay
  1990, RFS 3(3); White 2000, Econometrica 68(5); Harvey, Liu and Zhu 2016, RFS 29(1)); here it is held by the forward
  judge, the clamp and the sealed run, not by any in-sample test. (3) Survivorship biases history toward names that
  lived (Brown, Goetzmann, Ibbotson and Ross 1992, RFS 5(4); Shumway 1997, JF 52(1)): partly corrected (sections 3.4,
  3.7), not removed. (4) Long-only: half of most event premia are on the short side. (5) The learners share pools and
  auctions with PREREG-EVL-7's, so their false passes correlate. (6) The session block binds: 8 picks a session need a
  large edge a pick to pass inside the first run (section 11.3). (7) The build is the largest the lane has run; a fault
  costs a VOID and a night.
- RATES (counts only; SPEED-FACTS): candidates before merging by issuer about 340-620 a session for the open pool and
  420-850 for the close pool (Oct 20-21); history rows about 408,000-745,000 for EVL-WL-O1 and 504,000-1,020,000 for
  EVL-WL-ON over the window (`learners/fetch_budget9.py`, before eligibility and labels).

## 17. What is not decided here

The code (section 6.2's files and their integration), the site and the docs, built after this file to these rules; the
build's plan is a guide and this file wins. If an implementation finds a rule here ambiguous, it takes the reading LESS
LIKELY TO PASS (screen rules) or that TRADES LESS (trading rules), recorded as an amendment before CODE_PIN_9; a later
resolution is a new version.

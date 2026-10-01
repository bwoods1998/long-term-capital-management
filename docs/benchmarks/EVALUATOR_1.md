# Evaluator benchmark suite 1: false promotions, missed signals and contract proofs

`evaluator-suite-1` measures how often the evaluator promotes a program that has no edge and how often it misses one
that has an edge, on cases whose answer is known in advance. It runs known-answer synthetic programs through the real
Gym engine and the real evidence lines, so it tests the execution contract (what a program can see, how it fills, what
survives between runs) as well as the statistics. It is a benchmark of the harness, never evidence about a strategy:
every world is invented, every edge is planted, and no model, market data, sealed day or production state is read.

This report scores main's evaluator at release A (`777b894f`, `gym-engine-4`, release B's base) on two independent
cohorts: the development cohort, on which the threshold variants were chosen, and a confirmation cohort drawn afterwards
from independent streams. **No threshold was changed, and none is recommended for adoption now** (the last section says
why). The owner's rule (Sept 30) allows an eligibility or scoring change only when fixed benchmarks show false
promotions do not rise and missed signals fall; the sealed holdout, the multiple-testing control and the forward
requirement never loosen, and prior evidence keeps its prior verdicts.

The machine-readable receipts are [evaluator_1.json](evaluator_1.json) (development) and
[evaluator_1_confirmation.json](evaluator_1_confirmation.json): the suite hash, the tree and fixture fingerprints, the
library versions, every aggregate below and a digest of every world's figures. The CLI writes them (`--receipt`).

## Running it

```sh
python -m league.swarm.benchmarks --suite evaluator --json --output full.json --receipt receipt.json
python -m league.swarm.benchmarks --suite evaluator --cohort confirmation --frozen receipt.json --json --output conf.json
python -m league.swarm.benchmarks --suite evaluator --json --compare docs/benchmarks/evaluator_1.json
```

One run takes 11 to 25 minutes on one laptop core, depending on load: eight engine worlds and 128 search lineages for
each of ten search cases. What releases are compared on is the report's `headline`, a per-case vector: promotions of
each negative, misses of each positive, the cases the static check refuses, impossible fills and stress-contaminated
runs per case, the review contract's two answers per case, each proof's held count, each ablation's detections and
each variant's owner-rule verdict. `--compare OLD` lists regressions and improvements case by case (a review-contract
answer that stops holding is a regression) and exits 4 when there is a regression or the runs are not comparable (a
different suite, cohort or world fixture, or a run off the full protocol). A different Python, numpy or pyarrow is
noted, since the synthetic streams may shift with them. Exit 3 means the suite file is not the pinned suite; exit 5
means the tree lacks an interface the suite calls (main at `f082cf5e` is the oldest tree that has them all;
production's release before it cannot be scored); exit 2 means a confirmation run named no admissible development
report.

`--tree CHECKOUT` runs this suite file against another checkout's `league` package in a child process. It guards
against accidental drift of the cases (a tree's own copy of the suite is never used), not against a hostile tree: the
tree's code runs in the suite's interpreter with the operator's environment. It is an operator tool for trusted trees,
not a harness-lane judge.

**Pinned.** `PINNED_SUITE_SHA` is the hash of the protocol, the world, the channels, every case and template, the
search tier, the variants and the module's own source, read from the file on disk. A run whose hash differs reports
`pinned: false` and exits 3, so the cases cannot be quietly redefined; a new question is a new suite id with a new
report. The world's option prices (Bachelier with the Abramowitz-Stegun normal) and the Clopper-Pearson bounds are
computed inside the suite, not by the scored tree. The store writer and the fill model must match the tree's own store
and engine, so they come from its `league/gym/synth.py`; that file's hash is the report's `fixture_sha`, and runs with
different fixtures are not compared.

**Cohorts.** Development's worlds and search streams are the suite's first ones. Confirmation's hash the cohort's name
in, and a confirmation run is admitted only against the frozen development receipt of the same pinned suite,
execution fingerprint, evaluator sources, fixture and sample counts. A variant chosen on development is then judged on
data it was not chosen on, and only a variant whose development and confirmation verdicts are both met
(`met_and_confirmed`) meets the owner's rule.

## What the suite runs

### The world

One synthetic underlying on a thinned weekday calendar (every fourth weekday: 195 Train sessions over 2022-2024, 65 in
Validation 2025 and 48 in a synthetic 2026 holdout the suite generates itself). Each minute moves by a Gaussian step
with a small upward drift. Between 10:00 and 10:40 nine "tells" jump the price by a fixed amount in a random
direction; a tell is fully visible from its minute on. Nine 30-minute windows follow from 10:50. In a window with a
planted edge, the price drifts further in its tell's direction by a fixed amount; in the others it does not. Options
(one-day expiry, 21 strikes around the 10:45 price) are quoted from 10:45 at a fixed half-spread around the Bachelier
price of the rest of the path, which is exactly fair when nothing is planted: any profit beyond the spread is the
planted edge or a leak. After the last window the world plants impossible prices: a stale quote at a jump, a vertical's
leg blown out so its natural leaves the payoff range on a close and on an open, and crossed quotes. The world writes
no open interest.

A passive fill model with a uniform hazard is on, so patient orders can fill and the adverse-selection and stress rules
are exercised. Runs are made in one process (as a one-worker batch makes them).

### The pipeline as scored

Each case's program goes through the stages the swarm uses, with the real functions: the static contract
(`check_experiment`), Train and its 1.5x-stress run, the robust Train objective's eligibility (`train_score`), the drift
screen, Validation and its 1.5x twin (`validation_line`, one validated version), the review, and one synthetic holdout
look (`holdout_line`, Holm over a fixed history of two failed looks). A case is **promoted** when every stage passes.

The review is a model call, which the suite does not make. It scores a **blind reviewer** that passes everything, so a
promotion here is one the mechanical stages allow. A case that only the review can stop by design is marked
*review-dependent*; for each case with a known defect line the suite checks that the review contract can carry the
right rejection (a grounded finding stays a failure, the same claim without a real excerpt falls to unclear).

### The cases

- **Signal controls** (negatives): an absent signal, an edge smaller than the spread, drift-only calls, and an edge
  that is real in Train and Validation and gone in the holdout. **Planted edges** (positives), built to carry about
  the same Validation t (about 3.5): dense (every session), medium (about 48 trades a year: Train-eligible, one
  Validation floor short), sparse (about 13 a year), a conditional regime (only after a large overnight gap), and a
  year regime (absent in the first Train year).
- **Leakage**: each probe trades the absent window, taking its direction from what it tried to read of the future,
  else from a coin. Paths: indexing past now; an array's base; the engine's greek cache (it holds the whole day's
  underlying) behind a private attribute; a date table reached by reconstructing each session's date (a recognized
  window start plus a session count); the greeks (solved in blocks that include later minutes); prior-session bars
  (closes, highs, lows and opens join the history together at a day's close, so one probe on the last close covers the
  mechanism); historical bar volume without publication receipts (the world writes a volume column that encodes the
  day's later move); and a process-global numpy dict (`np.typecodes`)
  carrying one run's realized moves into a later run of the same days. Next-session event flags are a **smoke test**,
  kept out of the rates: the world's moves do not depend on the calendar, so that probe cannot profit whatever the
  engine does.
- **Memorized tables** (review-dependent negatives): a program that carries the realized direction of every session
  keyed by the session's opening price level; the same table kept only for the sessions whose window moved most (about
  13 a year, trading nowhere else); and a direction list indexed by a session counter from a recognized window start
  (the up/down signs of the day's first twenty minutes and its tells), which has no date literal and nothing keyed to
  the price level. The sparse table is the suite's **sensitivity control**: a negative today's activity floors are known
  to stop, so a variant that lowers them shows what it lets through.
- **Invalid fills**: buying the stale quote at the jump minute, closing a vertical while its long leg's bid is blown
  out above the width, opening one while its short leg's bid makes it pay a credit, buying a crossed ask to sell the
  crossed bid, and passive spread capture at the touch.
- **State** (contract proofs): module STATE starts fresh each run; parameter lists are copied per run; a split Train run
  matches the unsplit one day for day and Validation is never split; no process-global object carries a run's decisions
  into the next run, and a batch-mate cannot change what another program sees or does, each proved separately through
  numpy's two mutable public dicts (`np.typecodes` and `np.sctypeDict`); the static check refuses every mutable public
  numpy container (enumerated at run time from the scored process's numpy, top level and one submodule down); and a
  batch-mate cannot write into the ctx objects another program is handed.
- **Broken ablations**: a `signal_on` switch wired six ways (through `ctx.params`, a helper default capturing `PARAMS`, a
  module alias, a shadow copy that never reads `PARAMS`, a read defeated by a wrong comparison, and a computed key with
  a wrong test). Detection by the static contract and by a behavioral probe (the off variant over Validation).
- **Search tier**: generated daily outcomes (no Gym, no drift figures) through the same lines with lineage selection:
  thirty-two noise variants per lineage ranked on Train, up to five candidates validated in rank order with the
  lineage's validated-version count feeding the deflated Sharpe, and the holdout with Holm. Noise is net zero after base
  costs (a demanding null), Gaussian and fat-tailed (Student-t, three degrees of freedom), in every band a floor variant
  opens: 12, 42 and 48 trades a year sit under today's floors (Train 40 a year, Validation 50), 126 above them. Planted
  lineages carry a fixed net edge at 12, 48 and 126 trades a year.

## Results: main's evaluator at release A

Tree: main at `777b894f` (release A) with this branch, `gym-engine-4`, execution fingerprint `2d3d02847e7d` (release
A's; this branch changes nothing it covers), evaluator sources `7305b9e199b3` (the evidence, gate, researcher,
review-contract, experiment, results and stats modules), fixture `1ee0e716bc8d`, suite `ce1617764510`; Python 3.14.7,
numpy 2.5.3, pyarrow 25.0.1. Each cohort: eight worlds and 128 search lineages per search case. Development took
1200 s and confirmation 1453 s on one core of a loaded shared machine. The first draft scored main at `f082cf5e`
(before release A): every case, search band, ablation and variant figure it shares with this run is identical in both
cohorts; this run adds three numpy proofs.

### Headline

| Rate | Development | Confirmation |
| --- | ---: | ---: |
| False promotion, every negative case-world | 16/160 (10.0%; 95% 5.8–15.7%) | 16/160 (10.0%; 95% 5.8–15.7%) |
| False promotion, what the mechanical stages are meant to stop | 0/136 (95% upper 2.7%) | 0/136 (95% upper 2.7%) |
| Negative cases promoted in any world | 2/20 | 2/20 |
| Negative cases promoted, mechanical scope | 0/17 (one-sided 95% upper 16.2%) | 0/17 (one-sided 95% upper 16.2%) |
| Missed signal, planted case-worlds | 23/40 (57.5%; 95% 40.9–73.0%) | 22/40 (55.0%; 95% 38.5–70.7%) |
| Planted cases missed in at least one world | 4/5 | 4/5 |

Read the case counts, not only the case-world counts. Outcomes cluster by case: every negative goes 0/8 or 8/8, so
the 136 case-worlds behave like 17 trials, and the Clopper-Pearson interval on 136 assumes an independence they do not
have. What the suite supports is that none of the 17 negatives the mechanical stages are meant to stop was promoted in
any world of either cohort (one-sided 95% bound 16% per case), conditional on this fixed case mix.

All 16 false promotions in each cohort are two review-dependent memorized tables, each promoted in every world with a
99-100% hit rate: the table keyed by opening price level and the session-indexed list. Nothing mechanical can stop a
dense memorized table by design. The review contract names both (`calendar`: hard-coded absolute price regimes and
reconstructed historical dates), and a grounded rejection of each survives the contract's check. That is the load the
review carries. The sparse memorized table is stopped in every world, by the Train activity floors alone: it trades
about 13 sessions a year.

| Case | Answer | Development | Confirmation |
| --- | --- | --- | --- |
| `absent_signal` | no edge | 0/8 (Train stress 8) | 0/8 (Train stress 8) |
| `cost_erased` | no edge | 0/8 (Train stress 6, drift 2) | 0/8 (Train stress 7, drift 1) |
| `drift_only` | no edge | 0/8 (drift 7, Validation 1) | 0/8 (drift 8) |
| `edge_disappears` | no edge | 0/8 (holdout 8) | 0/8 (holdout 8) |
| `planted_dense` | edge | 7/8 (Validation 1, t 1.90) | 6/8 (holdout 2) |
| `planted_medium` | edge | 2/8 (Validation 4, holdout 2) | 4/8 (Validation 3, holdout 1) |
| `planted_regime_gap` | edge | 0/8 (Train eligibility 8) | 0/8 (Train eligibility 8) |
| `planted_regime_years` | edge | 8/8 | 8/8 |
| `planted_sparse` | edge | 0/8 (Train eligibility 8) | 0/8 (Train eligibility 8) |

Most missed signals are the activity floors, not weak evidence: the sparse and gap-regime edges never pass Train's
per-year floor (6 to 28 trades in a Train year), and every Validation stop of the medium edge is the trade floor alone,
at 39-49 trades. Planted edges that reach Validation show a t of about 2 to 6. The year-regime
edge, absent in the first Train year, is promoted in every world: the robust Train objective (the worst year's t) only
ranks a family's versions, and a single version's negative score does not stop it. Among several versions it would rank
below any version with a positive worst year.

### Leakage

| Path | Result (both cohorts) |
| --- | --- |
| An array's `.base`; the greek cache behind a private attribute; a date table reached by reconstructing the date | refused by the static check, 8/8 each |
| Indexing past now, the greeks, prior-session bars, bar volume without receipts | no information: direction hit rates 0.48–0.52; stopped at Train stress (the greeks once at drift) |
| A process-global numpy dict carrying one run's moves into a later run of the same days | normal runs learn nothing (hit 0.51–0.52; stopped by the drift screen), but the 1.5x-stress runs, made after the normal runs over the same days, are contaminated in 8/8 worlds |
| Memorized tables: by price level; session-indexed; sparse by price level | promoted 8/8; promoted 8/8; stopped at Train eligibility 8/8 (review-dependent, above) |
| Next-session event flags (smoke test, out of the rates) | hit 0.51–0.52; never promoted |

On the paths tested, nothing in the ctx leaks the future: the arrays end at the current minute, the greeks are handed
out one row at a time, the prior-session bars end yesterday, and historical bar volume without first-observation
receipts is hidden even when the file holds it. The static check refuses three probes. A unit test opens it for them
on one validation world: the greek-cache probe (it reaches the cache through the snapshot's greeks source) and the
date-table probe then read the window's future (65 of 65 directions right, t 7.4), so the check is what stops them.
The array-base probe learns nothing even opened (30 of 65 right, and it loses money): the engine hands a program a copy
whose base is a bytes copy of today so far, a second guard. The headline's refusal list flags a release that stops refusing any of the
three. Not tested: open interest (the world writes none), and highs, lows and opens separately (they join the history
on the same path as the closes). The holes the suite found let programs or runs pass information to each other
instead: see State.

### Invalid fills

Zero impossible fills in 32 checked program-worlds per cohort (four probes with a detector, each over five runs): no
stale quote bought at the decision minute (orders meet the next minute's quotes), no crossed quote filled (the store
drops them), no vertical opened at or below zero or closed above its width while a leg was blown out (the package's
payoff bounds hold on open and close). The passive spread-capture probe has no fill detector and is judged on P&L: it
loses under adverse selection. Every fill probe loses money and stops at the Train stress run.

### State and the review contract's facts

| Proof | Fact | Held (both cohorts) | Observed (trades: alone or first run, then mated or second run) |
| --- | --- | ---: | --- |
| Module STATE starts fresh every run | state | 8/8 | 5, 5 |
| Parameter lists are copied per run | parameters | 8/8 | 1, 1 |
| A split Train run matches the unsplit run day for day; Validation is never split | state | 8/8 | 195 = 195 days, Validation split 1 |
| No process-global object carries a run into the next: `np.typecodes` | state | **0/8** | 65, then 0 |
| The same through `np.sctypeDict` | state | **0/8** | 65, then 0 |
| A batch-mate cannot change another program's result through a process-global object: `np.typecodes` | state | **0/8** | 65, then 0 |
| The same through `np.sctypeDict` | state | **0/8** | 65, then 0 |
| The static check refuses every mutable public numpy container | state | **0/8** | reachable: `np.sctypeDict`, `np.typecodes` |
| A batch-mate cannot write into the ctx objects another program is handed | context | **0/8** | 65, then 0 |

The first three rebuild the state-reset proof Codex ran on Sept 30 and lost: STATE resets between runs, and the
engine-4 parameter binding holds (see Ablations). The rest are three defects, proved six ways. numpy exposes two mutable
module-level dictionaries that pass the static check, `np.typecodes` and `np.sctypeDict` (the only mutable public
containers numpy 2.5.3 has at its top level or one public submodule down). A program can write either, and a later run
or a batch-mate in the same process reads what it wrote. numpy itself consults `sctypeDict` when it resolves dtype
names, so a write there can change what another program computes, not only what it knows. And the underlying's view is
built once a minute and shared by every batch-mate with the same history, with a plain dict inside it. These contradict
two of the review contract's facts (`state`: never across independent replay runs; `context`: read-only copies), so a
reviewer who cites them today has a concrete route and is right.

Scope: production Gym boxes run each batch unit in its own process, which isolates runs from each other but not the
programs of one unit. The House's live decider holds every live program instance in one child process
(`league/live/decider.py`), so the batch-mate channels exist between whatever programs it runs together. Release A's
batch isolation contains a failing program's errors; it does not separate this state. The fixes are small but belong to
`league/gym` (a Gym change resets evidence): refuse numpy's mutable module attributes in the safety check (an allowlist
of numpy names is the robust form) and make the view's coverage mapping read-only. They are listed for release B, the
planned reset, and are not in this change.

When they land, the probes are refused (or the writer's write fails) and the proofs hold with no edit to the suite (a
unit test runs the refused path through the whole report). The suite certifies the numpy fix only when it is whole:
each dictionary is proved on its own, and the reach proof enumerates, at run time, every mutable public numpy container
(dict, list, set or bytearray, at numpy's top level and one public submodule down, in the scored process's numpy) and
holds only when the static check refuses them all. A fix that refuses `typecodes` alone leaves the `sctypeDict` proofs
and the reach proof failing; a unit test simulates the partial and the whole fix. The pipeline's numpy memo probe
reaches `typecodes` only, so its refusal alone says nothing about `sctypeDict`.

### Broken ablations

| Switch wiring | Broken | Static contract refuses the off override | Off variant still trades |
| --- | --- | ---: | ---: |
| through `ctx.params` | no | 0/8 | 0/8 |
| a helper default capturing `PARAMS` (engine-3's bug) | no | 0/8 | 0/8 |
| a module-level alias of `PARAMS` | no | 0/8 | 0/8 |
| a shadow copy that never reads `PARAMS` | yes | 8/8 | 8/8 |
| read, then defeated by a wrong comparison | yes | 0/8 | 8/8 |
| a computed key with a wrong test | yes | 0/8 | 8/8 |

Identical in both cohorts. The static contract detects 8/24 broken switches (33%, 95% 16%–55%) with no false alarm;
the behavioral probe (does the off variant still trade over the 65-session Validation?) detects 24/24 (95% lower bound
86%) with no false alarm in 24 working ones. Engine-4's binding works: every correctly wired switch removes every trade.

### The review contract

For all four cases with a known defect line (the numpy memo and the three memorized tables), a grounded rejection (a
real excerpt, a contract fact, a counterexample) stays a failure through `grounded_answer`, and the same claim with an
excerpt not in the program falls to unclear, which can never open a holdout. That checks the receipt's shape; whether a
model finds the defect is not measured here.

## The owner's rule, measured (no change proposed)

Each variant re-judges the same recorded outcomes. It meets the owner's rule only if, against `current`: engine false
promotions are not higher; search false promotions are not higher; engine negatives that pass Validation (and would
spend a holdout look) are not higher; noise lineages that spend a holdout look are not higher in ANY of the seven noise
bands; and missed signals fall. The look counts carry the power. End-to-end false promotion on noise cannot see a floor
change at all: the holdout with Holm stops every noise lineage even under two-trade floors. The verdict must reject the
`no_floors` reference, and it does in both cohorts, on the engine promotions (the sparse memorized table), the engine
looks and the noise looks.

| Variant | Rule | Engine false (sparse table) | Engine missed | Search false | Noise looks | Search missed | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `current` | Train 40 trades on 20 days every year; Validation 50 on 25 | 16 (0) / 16 (0) | 23 / 22 | 0 / 0 | 3 / 2 | 269 / 263 | reference |
| `aligned_floors` | Validation 40 on 20 | 16 (0) / 16 (0) | 20 / 19 | 0 / 0 | 14 / 26 | 165 / 161 | not met: looks rise |
| `sparse_floors` | Train 6 on 5 every year and 30 on 20 pooled; Validation 10 on 8 | 21 (5) / 23 (7) | 7 / 9 | 0 / 0 | 24 / 41 | 64 / 62 | not met |
| `pooled_train` | sparse floors, ranked on the pooled Train t | 21 (5) / 23 (7) | 7 / 9 | 1 / 1 | 26 / 40 | 64 / 62 | not met |
| `pooled_validation` | Validation over the last Train year and Validation | 16 (0) / 16 (0) | 18 / 19 | 2 / 0 | 47 / 68 | 141 / 149 | not met |
| `no_floors` | reference: two trades | 23 (7) / 24 (8) | 6 / 8 | 0 / 0 | 24 / 41 | 64 / 62 | not met (sensitivity) |

Each cell is development / confirmation. Engine counts are of 160 negative and 40 planted case-worlds; search counts
are of 896 noise and 384 planted lineages.

Noise lineages that spent a holdout look, by band (of 128), and the planted 48-a-year class promoted:

| Band | `current` dev | `aligned_floors` dev | `current` conf | `aligned_floors` conf |
| --- | ---: | ---: | ---: | ---: |
| noise, 12 a year (Gaussian; t3) | 0; 0 | 0; 0 | 0; 0 | 0; 0 |
| noise, 42 a year (Gaussian; t3) | 0; 0 | 3; 2 | 0; 0 | 5; 5 |
| noise, 48 a year (Gaussian; t3) | 0; 0 | 0; 6 | 0; 0 | 4; 10 |
| noise, 126 a year (Gaussian) | 3 | 3 | 2 | 2 |
| planted, 48 a year: promoted | 0 | 104 | 0 | 102 |

**No variant meets the rule in either cohort, and no threshold change is proposed from this suite.** A single cohort's
verdict is never cited alone: the confirmation receipt records, per variant, whether the frozen development verdict
and its own were both met (`met_and_confirmed` in the headline's `owner_rule`; a development receipt leaves it unset).
No variant is met and confirmed.

- **`aligned_floors`: withdrawn.** An earlier draft of this report recommended it, on the development cohort's four
  original noise bands, where its look spend did not rise. With nulls in the band it opens (42 and 48 trades a year,
  Gaussian and fat-tailed), the look spend rises on development (3 to 14 of 896) and on the independent confirmation
  cohort (2 to 26); a reviewer's own fresh seeds showed the same (Gaussian 48-a-year noise, 0 to 8 of 128). It is a
  loosening of a Validation guard (50 trades on 25 days to 40 on 20), not only the removal of a mismatch with Train.
  What it buys is real: the 48-a-year planted class goes from 0 to about 103 of 128 lineages, and engine misses fall by
  3. What it costs: noise in the opened band spends a holdout look in up to 8% of lineages (0 to 10 of 128 per band),
  against 2–3 of 128 for dense noise today, and each look is charged in Holm for every later one. The rule as written is not met;
  whether the trade is worth making anyway is the owner's decision, and this benchmark does not certify it.
- **`sparse_floors`, `pooled_train`, `no_floors`.** Beyond the look spend in every band under today's floors, they let
  the sparse memorized table reach and pass the holdout in 5–8 of 8 worlds. Today the Train floors are the only
  mechanical stop for a sparse memorized strategy; lowering them moves that load onto the review. `pooled_train` also
  promoted one noise lineage in each cohort.
- **`pooled_validation`** spends the most looks (47 and 68 of 896) and promoted two noise lineages on development:
  pooling the last Train year, which chose the version, into Validation reuses selection data.
- A change that could meet the rule would need a compensating guard that holds the look spend flat in the band it
  opens (for example, a stricter Validation t for versions under the current floor), designed on development and
  confirmed on a fresh cohort under a new suite id. None is measured here.

### Cheap stages the suite measured (proposals, not applied)

- **Behavioral ablation.** Measured as the off variant over the full 65-session Validation, with switches that remove
  every trade when off: 24/24 broken switches caught, 0/24 false alarms (the static contract catches 8/24). A cheaper
  probe over a few Train days, on real filters that often do not bind on a given day, is not measured; its false-alarm
  rate would be higher.
- **Level-invariance probe.** Replay Validation on a store with every price scaled. It flags the level-keyed tables in
  every world, with 1 false alarm in 40 planted-edge runs (a program with a dollar threshold), and misses the
  session-indexed list by construction: it detects 8 of the 16 promoted memorized runs in each cohort. Cost: one extra
  Validation replay per candidate, plus a scaled store the Gym must build (a `league/gym` change, so an evidence reset).
  A session-permutation or calendar-shift replay would target session-indexed memory; it is not measured.
- **Stress-contamination flag.** A version that does better at 1.5x the spread than at 1x over the same days learned
  something between the runs: 8/8 on the numpy memo in both cohorts, 0 elsewhere. A flag, not proof: a program whose
  losses come from passive fills can gain when the stress run halves them.

## Limitations

- Invented worlds: an arithmetic random walk, planted edges that are deliberately strong, options fair by construction.
  These rates bound the evaluator's errors on these cases only, not on real markets or model-written research.
- The review is not called. The false-promotion rate is the mechanical pipeline's; review-dependent cases show the load
  the review carries.
- Runs are made in one process, as a one-worker batch makes them; production units each have their own process.
- The synthetic holdout is the suite's own (48 sessions); its Holm history is fixed at two failed looks.
- The search tier has no drift figures, Gaussian or Student-t noise with no serial dependence, and a fixed
  five-candidate schedule. It is not a simulation of model research.
- Eight worlds and 128 lineages per case: a zero count supports an exact bound, not a claim of zero. Case-worlds
  cluster by case, and every bound is conditional on this case mix.
- These figures score main at release A (`777b894f`). Release A changed `league/gym` (batch error isolation, a compile
  check) but not the world's fixture, and moved no figure the first draft (main at `f082cf5e`) shares with this run.
  The integrated release B tree should be scored with the same pinned suite before it deploys
  (`--compare docs/benchmarks/evaluator_1.json`); main at `f082cf5e` is the oldest tree the suite can score.

## Reproduction

```sh
python -m league.swarm.benchmarks --suite evaluator --cohort development --json --output dev.json --receipt evaluator_1.json
python -m league.swarm.benchmarks --suite evaluator --cohort confirmation --frozen evaluator_1.json --json \
  --output conf.json --receipt evaluator_1_confirmation.json
python -m unittest league.tests.test_swarm_evaluator_benchmarks league.tests.test_swarm_benchmarks
```

A pinned suite is deterministic on the same Python, numpy and pyarrow: worlds, fills and bootstraps are seeded by
hashes. Both cohorts reproduced the earlier drafts' figures exactly on every case, search band, ablation and variant
they share, across the re-pins and release A. Each receipt's `replication_rows_sha256` is the digest of every world's figures (per-world seconds excluded),
recomputed from a saved full report by `receipt()`.

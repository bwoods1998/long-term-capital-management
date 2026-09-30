# Evaluator benchmark suite 1: false promotions, missed signals and contract proofs

`evaluator-suite-1` measures how often the evaluator promotes a program that has no edge and how often it misses one
that has an edge, on cases whose answer is known in advance. It runs known-answer synthetic programs through the real
Gym engine and the real evidence lines, so it tests the execution contract (what a program can see, how it fills, what
survives between runs) as well as the statistics. It is a benchmark of the harness, never evidence about a strategy:
every world is invented, every edge is planted, and no model, market data, sealed day or production state is read.

This report scores main's evaluator (`gym-engine-4`, the tree of release B's base) and measures five threshold
variants on the same outcomes. **No threshold was changed.** The owner's rule (Sept 30) allows an eligibility or scoring
change only when fixed benchmarks show false promotions do not rise and missed signals fall; the sealed holdout, the
multiple-testing control and the forward requirement never loosen. The last section is the measured proposal.

The [machine-readable receipt](evaluator_1.json) holds the suite hash, the tree fingerprint and every aggregate below.

## Running it

```sh
python -m league.swarm.benchmarks --suite evaluator --json --output report.json
python -m league.swarm.benchmarks --suite evaluator --json --tree /path/to/candidate/checkout
```

The suite takes about ten minutes on one laptop core (583 s for this report): eight engine worlds (about 40 s each) and 128 search lineages for each of
seven search cases. `--tree` runs this trusted suite file against another checkout's `league` package in a child
process, so a harness candidate is judged by cases it cannot edit (`playbooks/harness-improvement.md`). The report's
`headline` is what releases are compared on: the two rates, the failed proofs, the contradicted contract facts, the
ablation detection rates and the tree's execution fingerprint.

**Pinned.** `PINNED_SUITE_SHA` is the hash of the protocol, the world, the channels, every case and template, the search
tier, the variants and the module's own source. A run whose hash differs reports `pinned: false` and exits 3, so the
cases cannot be quietly redefined; a new question is a new suite id with a new report. A run at other than the default
replication counts reports `full_protocol: false` and is not comparable either.

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
leg blown out so its natural leaves the payoff range on a close and on an open, and crossed quotes.

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
  else from a coin. Paths: indexing past now, an array's base, a private attribute, a date literal, the greeks (solved
  in blocks that include later minutes), next-session event flags, historical bar volume without publication receipts
  (the world writes a volume column that encodes the day's later move), a process-global numpy dict carrying one run's
  realized moves into a later run of the same days, and a memorized table keyed by the session's opening price level.
- **Invalid fills**: buying the stale quote at the jump minute, closing a vertical while its long leg's bid is blown
  out above the width, opening one while its short leg's bid makes it pay a credit, buying a crossed ask to sell the
  crossed bid, and passive spread capture at the touch.
- **State** (contract proofs): module STATE starts fresh each run; parameter lists are copied per run; a split Train run
  matches the unsplit one day for day and Validation is never split; no process-global object carries a run's decisions
  into the next run; a batch-mate cannot change what another program sees or does.
- **Broken ablations**: a `signal_on` switch wired six ways (through `ctx.params`, a helper default capturing `PARAMS`, a
  module alias, a shadow copy that never reads `PARAMS`, a read defeated by a wrong comparison, and a computed key with
  a wrong test). Detection by the static contract and by a behavioral probe (the off variant over Validation).
- **Search tier**: generated daily outcomes (no Gym, no drift figures) through the same lines with lineage selection:
  thirty-two noise variants per lineage ranked on Train, up to five candidates validated in rank order with the
  lineage's validated-version count feeding the deflated Sharpe, and the holdout with Holm. Noise is net zero after base
  costs (a demanding null), including one fat-tailed (Student-t, three degrees of freedom) sparse case; positives carry
  a fixed net edge at 12, 48 and 126 trades a year.

## Results: main's evaluator

Tree: `gym-engine-4`, execution fingerprint `f1515bd98bfb`, evaluator sources `0c4cc7ad582a` (the evidence, gate, researcher,
review-contract, experiment, results and stats modules), suite `c853a5cff1a0`, eight worlds and 128 search lineages per case.

### Headline

| Rate | Count | Rate | Exact 95% interval |
| --- | ---: | ---: | --- |
| False promotion, every negative case | 8/144 | 5.6% | 2.4%–10.7% |
| False promotion, the cases the mechanical stages are meant to stop | 0/136 | 0% | 0%–2.7% (one-sided 2.2%) |
| Missed signal, planted edges | 23/40 | 57.5% | 40.9%–73.0% |

All eight false promotions are one case, the memorized price-level table: a program that carries the realized direction
of every session keyed by the session's opening level passes every mechanical stage in every world, with a 99% hit rate.
Nothing mechanical can stop it by design; the review contract names it (`calendar`: hard-coded absolute price regimes),
and a grounded rejection of it survives the contract's check. It is the load the review carries. Every other negative
case is stopped in every world.

Most missed signals are the activity floors, not weak evidence: planted edges that reach Validation show a t of about 2
to 6.

| Case | Answer | Promoted | Stopped at |
| --- | --- | ---: | --- |
| `absent_signal` | no edge | 0/8 | Train stress 8 |
| `cost_erased` | no edge | 0/8 | Train stress 6, drift 2 |
| `drift_only` | no edge | 0/8 | drift 7, Validation 1 |
| `edge_disappears` | no edge | 0/8 | holdout 8 |
| `planted_dense` | edge | 7/8 | Validation 1 (t 1.90) |
| `planted_medium` | edge | 2/8 | Validation 4 (the 50-trade floor alone, at 39-49 trades), holdout 2 (Holm) |
| `planted_regime_gap` | edge | 0/8 | Train eligibility 8 (the per-year floor) |
| `planted_regime_years` | edge | 8/8 | none |
| `planted_sparse` | edge | 0/8 | Train eligibility 8 (the per-year floor) |

The year-regime edge, absent in the first Train year, is promoted in every world: the robust Train objective (worst
year's t) only ranks a family's versions, and a single version's negative score does not stop it. Among several
versions it would rank below any version with a positive worst year.

### Leakage

| Path | Result |
| --- | --- |
| An array's `.base`, a private attribute, a date literal | refused by the static check (8/8 each) |
| Indexing past now, the greeks, next-session events, bar volume without receipts | no information: direction hit rate 0.51-0.52; stopped at Train stress |
| A process-global numpy dict carrying one run's moves into a later run of the same days | normal runs learn nothing (hit 0.52; stopped by the drift screen), but the 1.5x-stress runs, made after the normal runs over the same days, are contaminated in 8/8 worlds |
| A memorized table keyed by the opening price level | promoted 8/8 (review-dependent, above) |

Nothing in the ctx leaks the future: the arrays end at the current minute, the greeks are handed out one row at a time,
and historical bar volume without first-observation receipts is hidden even when the file holds it. The holes the suite
found let programs or runs pass information to each other instead: see State.

### Invalid fills

Zero impossible fills in 40 program-worlds, each over five runs: no stale quote bought at the decision minute (orders
meet the next minute's quotes), no crossed quote filled (the store drops them), no vertical opened at or below zero or
closed above its width while a leg was blown out (the package's payoff bounds hold on open and close), and passive spread
capture at the touch loses under adverse selection. Every probe loses money and stops at the Train stress run.

### State and the review contract's facts

| Proof | Fact | Held | Observed (trades: alone or first run, then mated or second run) |
| --- | --- | ---: | --- |
| Module STATE starts fresh every run | state | 8/8 | 5, 5 |
| Parameter lists are copied per run | parameters | 8/8 | 1, 1 |
| A split Train run matches the unsplit run day for day; Validation is never split | state | 8/8 | 195 = 195 days, Validation split 1 |
| No process-global object carries a run into the next | state | **0/8** | 65, then 0 |
| A batch-mate cannot change another program's result through a process-global object | state | **0/8** | 65, then 0 |
| A batch-mate cannot write into the ctx objects another program is handed | context | **0/8** | 65, then 0 |

The first three rebuild the state-reset proof Codex ran on Sept 30 and lost: STATE resets between runs, and the
engine-4 parameter binding holds (see Ablations). The last three are defects. numpy exposes mutable module-level
dictionaries that pass the static check; a program can write them, and a later run or a batch-mate in the same process
reads what it wrote. numpy itself consults one of them when it resolves dtype names, so a write can change what another
program computes, not only what it knows. And the underlying's view is built once a minute and shared by every
batch-mate with the same history, with a plain dict inside it. These contradict two of the review contract's facts
(`state`: never across independent replay runs; `context`: read-only copies), so a reviewer who cites them today has a
concrete route and is right.

Scope: production Gym boxes run each batch unit in its own process, which isolates runs from each other but not the
programs of one unit. The House's live decider holds every live program instance in one child process
(`league/live/decider.py`), so the batch-mate channels exist between whatever programs it runs together. The fixes are
small but belong to `league/gym` (a Gym change resets evidence): refuse numpy's mutable module attributes in the safety
check (an allowlist of numpy names is the robust form) and make the view's coverage mapping read-only. They are listed
for release B, the planned reset, and are not in this change. When either lands, its probes are refused or hold, and
the suite reports the proof as held without any change to the suite.

### Broken ablations

| Switch wiring | Broken | Static contract refuses the off override | Off variant still trades |
| --- | --- | ---: | ---: |
| through `ctx.params` | no | 0/8 | 0/8 |
| a helper default capturing `PARAMS` (engine-3's bug) | no | 0/8 | 0/8 |
| a module-level alias of `PARAMS` | no | 0/8 | 0/8 |
| a shadow copy that never reads `PARAMS` | yes | 8/8 | 8/8 |
| read, then defeated by a wrong comparison | yes | 0/8 | 8/8 |
| a computed key with a wrong test | yes | 0/8 | 8/8 |

The static contract detects 8/24 broken switches (33%, 95% 16%-55%) with no false alarm; a behavioral probe (does the off
variant still trade?) detects 24/24 (95% lower bound 86%) with no false alarm in 24 working ones. Engine-4's binding
works: every correctly wired switch removes every trade.

### The review contract

For both cases with a known defect line, a grounded rejection (a real excerpt, a contract fact, a counterexample) stays a
failure through `grounded_answer`, and the same claim with an excerpt not in the program falls to unclear, which can
never open a holdout. That checks the receipt's shape; whether a model finds the defect is not measured here.

## A measured proposal (not applied)

Each variant re-judges the same recorded outcomes. The engine tier holds the eight worlds' single-version cases; the
search tier adds selection: 512 noise lineages (sparse, fat-tailed sparse, medium, dense; 32 variants each) and 384
planted lineages (sparse, medium, dense). "Noise looks" counts noise lineages that passed Validation and spent a
holdout look: a leading indicator, since the holdout is the last guard and every look is charged in Holm.

| Variant | Rule | Engine false (mech.) | Engine missed | Search false | Noise looks | Search missed |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `current` | Train 40 trades on 20 days every year; Validation 50 on 25 | 8/144 (0/136) | 23/40 | 0/512 | 3/512 | 269/384 |
| `aligned_floors` | Validation 40 on 20, Train's own yearly rate | 8/144 (0/136) | 20/40 | 0/512 | 3/512 | 165/384 |
| `sparse_floors` | Train 6 on 5 every year and 30 on 20 pooled; Validation 10 on 8 | 8/144 (0/136) | 7/40 | 0/512 | 13/512 | 64/384 |
| `pooled_train` | sparse floors, ranked on the pooled Train t | 8/144 (0/136) | 7/40 | 0/512 | 10/512 | 64/384 |
| `pooled_validation` | Validation over the last Train year and Validation, floors unchanged | 8/144 (0/136) | 18/40 | 0/512 | 12/512 | 141/384 |
| `no_floors` | reference: two trades | 8/144 (0/136) | 6/40 | 0/512 | 13/512 | 64/384 |

Search false promotions are 0/512 under every variant (one-sided 95% bound 0.6%). By search case (promoted, then noise
looks spent):

| Variant | Noise dense | Noise medium | Noise sparse | Noise sparse, fat tails | Signal dense | Signal medium | Signal sparse |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `current` | 0 (3) | 0 (0) | 0 (0) | 0 (0) | 115/128 | 0/128 | 0/128 |
| `aligned_floors` | 0 (3) | 0 (0) | 0 (0) | 0 (0) | 115/128 | 104/128 | 0/128 |
| `sparse_floors` | 0 (3) | 0 (0) | 0 (4) | 0 (6) | 115/128 | 104/128 | 101/128 |
| `pooled_train` | 0 (2) | 0 (1) | 0 (3) | 0 (4) | 115/128 | 104/128 | 101/128 |
| `pooled_validation` | 0 (9) | 0 (3) | 0 (0) | 0 (0) | 123/128 | 120/128 | 0/128 |
| `no_floors` | 0 (3) | 0 (0) | 0 (4) | 0 (6) | 115/128 | 104/128 | 101/128 |

**Recommendation 1: `aligned_floors` now.** Ask Validation for 40 trades on 20 days, the rate Train already requires in
every year. On these fixed benchmarks false promotions do not rise (0/136 mechanical, 0/512 search), the noise look spend
does not rise (3/512), and missed signals fall (engine 23 to 20 of 40; search 269 to 165 of 384, the medium class
recovered from 0/128 to 104/128). It removes a mismatch rather than loosening a guard: a version Train accepts at 40 a
year can today fail Validation at the same rate for the floor alone (4 of the 6 engine-tier medium misses). It satisfies
the owner's rule of Sept 30 as written. The deflated Sharpe, t >= 2, the quarters, the stress, the drift screen, the
holdout line, Holm and the look rations are unchanged; prior verdicts stand.

**Recommendation 2: `sparse_floors` only after a larger search benchmark.** It meets the rule as written (no false
promotion; engine misses 23 to 7, search 269 to 64) but spends more holdout looks on noise: 13/512 lineages against 3,
most in the sparse and fat-tailed sparse cases. The holdout caught every one here, but each look is charged in Holm for
every later look and uses a lineage's ration, so the cost falls on real signals. It should be judged by a pinned
`evaluator-suite-2` with more variants per lineage, serial dependence and heavier tails before it is proposed.

**Not recommended.** `pooled_train` gives the same misses as `sparse_floors` on these cases (the objective only ranks).
`pooled_validation` triples the dense-noise look spend (3 to 9): the last Train year was selection data, so pooling it
into Validation reuses the evidence that chose the version. `no_floors` is a reference.

Mechanics, if adopted: `MIN_TRADES` 50 to 40 and `MIN_DAYS` 25 to 20 in `league/swarm/evidence.py` (D2c's numbers;
the researcher's text and the progress counts read the constants). That module is research-side, but the live path loads
it through `gate.py`, so it deploys after a close (D8); it is not under `league/gym` or `league/live` and moves no
evaluator fingerprint. Validations already judged keep their verdicts. Re-run this suite on the changed tree: its
headline rates (which use the tree's own lines) must then equal this report's `aligned_floors` engine row, while the
variant rows, whose floors are fixed in the suite, stay as they are.

### Cheap stages the suite measured (proposals, not applied)

- **Behavioral ablation before replay:** run a changed switch's off variant over a few Train days and refuse it when the
  trades do not change. 24/24 broken switches caught, 0/24 false alarms; the static contract catches 8/24.
- **Level-invariance probe:** replay Validation on a store with every price scaled. It caught the memorized table in 8/8
  worlds, with 1 false alarm in 40 planted-edge runs (a program with a dollar threshold); it needs a Gym-side transform.
- **Stress-contamination flag:** a version that does better at 1.5x the spread than at 1x over the same days learned
  something between the runs (8/8 on the numpy memo, 0 elsewhere). A flag, not proof: a program whose losses come from
  passive fills can gain when the stress run halves them.

## Limitations

- Invented worlds: an arithmetic random walk, planted edges that are deliberately strong, options fair by construction.
  These rates bound the evaluator's errors on these cases only, not on real markets or model-written research.
- The review is not called. The false-promotion rate is the mechanical pipeline's; review-dependent cases show the load
  the review carries.
- Runs are made in one process, as a one-worker batch makes them; production units each have their own process.
- The synthetic holdout is the suite's own (48 sessions); its Holm history is fixed at two failed looks.
- The search tier has no drift figures, Gaussian or Student-t noise with no serial dependence, and a fixed five-candidate
  schedule. It is not a simulation of model research.
- Eight worlds and 128 lineages per case: a zero count supports an exact bound, not a claim of zero.

## Reproduction

```sh
python -m league.swarm.benchmarks --suite evaluator --json --output evaluator_1_full.json
python -m unittest league.tests.test_swarm_evaluator_benchmarks league.tests.test_swarm_benchmarks
```

The run is deterministic for a pinned suite: worlds, fills and bootstraps are seeded by hashes, and two runs of the
suite here (before and after an edit that changed only its fingerprinting code) gave identical figures. The receipt
beside this file keeps the aggregates, the tree fingerprint, the suite hash and a digest of every world's figures
(`replication_rows_sha256`, per-world timings excluded); the full report is reproduced by the command above.

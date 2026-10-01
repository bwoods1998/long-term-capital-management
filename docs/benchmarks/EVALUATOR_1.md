# Evaluator benchmark suite 1: false promotions, missed signals and contract proofs

`evaluator-suite-1` measures how often the evaluator promotes a program that has no edge and how often it misses one
that has an edge, on cases whose answer is known in advance. It runs known-answer synthetic programs through the real
Gym engine and the real evidence lines, so it tests the execution contract (what a program can see, how it fills, what
survives between runs) as well as the statistics. It is a benchmark of the harness, never evidence about a strategy:
every world is invented, every edge is planted, and no model, market data, sealed day or production state is read.

This report scores release B's evaluator (main at `3eaf4d06`, release B as it deploys, merged into this branch as
`2d028fa8`) on two independent cohorts: the development cohort, on which the threshold variants were chosen, and a
confirmation cohort drawn afterwards from independent streams. **No threshold was changed, and none is recommended for
adoption now** (the last section says why). The owner's rule (Sept 30) allows an eligibility or scoring change only when
fixed benchmarks show false promotions do not rise and missed signals fall; the sealed holdout, the multiple-testing
control and the forward requirement never loosen, and prior evidence keeps its prior verdicts.

The machine-readable receipts are [evaluator_1.json](evaluator_1.json) (development) and
[evaluator_1_confirmation.json](evaluator_1_confirmation.json): the suite hash, the tree and fixture fingerprints, the
library versions, every aggregate below and a digest of every world's figures. The CLI writes them (`--receipt`). Every
table in this report is rendered from the two receipts, and a unit test checks that it still is
(`ReportDocument.test_the_reports_tables_are_its_receipts`); every other figure is a field of a receipt, named where it
is quoted.

## Running it

```sh
python -m league.swarm.benchmarks --suite evaluator --json --output full.json --receipt receipt.json
python -m league.swarm.benchmarks --suite evaluator --cohort confirmation --frozen receipt.json --json --output conf.json
python -m league.swarm.benchmarks --suite evaluator --json --compare docs/benchmarks/evaluator_1.json
```

One run takes 16 minutes here (development 930 s, confirmation 973 s) on one core of a shared laptop, depending on load:
eight engine worlds and 128 search lineages for each of ten search cases. What releases are compared on is the report's
`headline`, a per-case vector: promotions of each negative, misses of each positive, the cases the static check refuses,
impossible fills and stress-contaminated runs per case, the review contract's two answers per case, each proof's held
count, each ablation's detections and each variant's owner-rule verdict. `--compare OLD` lists regressions and
improvements case by case (a review-contract answer that stops holding is a regression) and exits 4 when there is a
regression or the runs are not comparable (a different suite, cohort or world fixture, or a run off the full protocol).
A different Python, numpy or pyarrow is noted, since the synthetic streams may shift with them. Exit 3 means the suite
file is not the pinned suite; exit 5 means the tree lacks an interface the suite calls (main at `f082cf5e` is the oldest
tree that has them all; production's release before it cannot be scored); exit 2 means a confirmation run named no
admissible development report.

`--tree CHECKOUT` runs this suite file against another checkout's `league` package in a child process. It guards against
accidental drift of the cases (a tree's own copy of the suite is never used), not against a hostile tree: the tree's
code runs in the suite's interpreter with the operator's environment. It is an operator tool for trusted trees, not a
harness-lane judge.

**Pinned.** `PINNED_SUITE_SHA` is the hash of the protocol, the world, the channels, every case and template, the reach
walk's settings, the search tier, the variants and the module's own source, read from the file on disk. A run whose hash
differs reports `pinned: false` and exits 3, so the cases cannot be quietly redefined; a new question is a new suite id
with a new report. The world's option prices (Bachelier with the Abramowitz-Stegun normal) and the Clopper-Pearson
bounds are computed inside the suite, not by the scored tree. The store writer and the fill model must match the tree's
own store and engine, so they come from its `league/gym/synth.py`; that file's hash is the report's `fixture_sha`, and
runs with different fixtures are not compared.

**Cohorts.** Development's worlds and search streams are the suite's first ones. Confirmation's hash the cohort's name
in, and a confirmation run is admitted only against the frozen development receipt of the same pinned suite, execution
fingerprint, evaluator sources, fixture and sample counts. A variant chosen on development is then judged on data it was
not chosen on, and only a variant whose development and confirmation verdicts are both met (`met_and_confirmed`) meets
the owner's rule.

## What the suite runs

### The world

One synthetic underlying on a thinned weekday calendar (every fourth weekday: 195 Train sessions over 2022-2024, 65 in
Validation 2025 and 48 in a synthetic 2026 holdout the suite generates itself). Each minute moves by a Gaussian step
with a small upward drift. Between 10:00 and 10:40 nine "tells" jump the price by a fixed amount in a random direction;
a tell is fully visible from its minute on. Nine 30-minute windows follow from 10:50. In a window with a planted edge,
the price drifts further in its tell's direction by a fixed amount; in the others it does not. Options (one-day expiry,
21 strikes around the 10:45 price) are quoted from 10:45 at a fixed half-spread around the Bachelier price of the rest
of the path, which is exactly fair when nothing is planted: any profit beyond the spread is the planted edge or a leak.
After the last window the world plants impossible prices: a stale quote at a jump, a vertical's leg blown out so its
natural leaves the payoff range on a close and on an open, and crossed quotes. The world writes no open interest.

A passive fill model with a uniform hazard is on, so patient orders can fill and the adverse-selection and stress rules
are exercised. Runs are made in one process (as a one-worker batch makes them).

### The pipeline as scored

Each case's program goes through the stages the swarm uses, with the real functions: the static contract
(`check_experiment`), Train and its 1.5x-stress run, the robust Train objective's eligibility (`train_score`), the drift
screen, Validation and its 1.5x twin (`validation_line`, one validated version), the review, and one synthetic holdout
look (`holdout_line`, Holm over a fixed history of two failed looks). A case is **promoted** when every stage passes.

The review is a model call, which the suite does not make. It scores a **blind reviewer** that passes everything, so a
promotion here is one the mechanical stages allow. A case that only the review can stop by design is marked
*review-dependent*; for each case with a known defect line the suite checks that the review contract can carry the right
rejection (a grounded finding stays a failure, the same claim without a real excerpt falls to unclear).

### The cases

- **Signal controls** (negatives): an absent signal, an edge smaller than the spread, drift-only calls, and an edge that
  is real in Train and Validation and gone in the holdout. **Planted edges** (positives): dense (every session), medium
  (a big tell on about three sessions in four), sparse (a big tell on about one in five), a conditional regime (only
  after a large overnight gap), and a year regime (absent in the first Train year).
- **Leakage**: each probe trades the absent window, taking its direction from what it tried to read of the future, else
  from a coin. Paths: indexing past now; an array's base; the engine's greek cache (it holds the whole day's underlying)
  behind a private attribute; a date table reached by reconstructing each session's date (a recognized window start plus
  a session count); the greeks (solved in blocks that include later minutes); prior-session bars (closes, highs, lows
  and opens join the history together at a day's close, so one probe on the last close covers the mechanism); historical
  bar volume without publication receipts (the world writes a volume column that encodes the day's later move); and a
  process-global numpy dict (`np.typecodes`) carrying one run's realized moves into a later run of the same days. Every
  probe the static check refuses is also run with the check opened (in the suite's own process, for that load only), so
  the report says whether the check is what stops it. Next-session event flags are a **smoke test**, kept out of the
  rates: the world's moves do not depend on the calendar, so that probe cannot profit whatever the engine does.
- **Memorized tables** (review-dependent negatives): a program that carries the realized direction of every session
  keyed by the session's opening price level; the same table kept only for the sessions whose window moved more than
  $1.40 (`sparse_move`), trading nowhere else; and a direction list indexed by a session counter from a recognized
  window start (the up/down signs of the day's first twenty minutes and its tells), which has no date literal and
  nothing keyed to the price level. The sparse table is the suite's **sensitivity control**: a negative today's activity
  floors are known to stop, so a variant that lowers them shows what it lets through.
- **Invalid fills**: buying the stale quote at the jump minute, closing a vertical while its long leg's bid is blown out
  above the width, opening one while its short leg's bid makes it pay a credit, buying a crossed ask to sell the crossed
  bid, and passive spread capture at the touch.
- **State** (contract proofs): module STATE starts fresh each run; parameter lists are copied per run; a split Train run
  matches the unsplit one day for day and Validation is never split; no process-global object carries a run's decisions
  into the next run, and a batch-mate cannot change what another program sees or computes, each proved separately
  through `np.typecodes`, `np.sctypeDict` and np.polynomial's arrays (`polyx`; `Polynomial.domain`); a program's
  decisions repeat on two runs of the same days (a program that draws its side from `np.matlib.rand`); the **reach
  proof** (below), which walks everything a program can reach from its imports and writes every writable object it
  finds; and a batch-mate cannot write into the ctx objects another program is handed.
- **Broken ablations**: a `signal_on` switch wired six ways (through `ctx.params`, a helper default capturing `PARAMS`,
  a module alias, a shadow copy that never reads `PARAMS`, a read defeated by a wrong comparison, and a computed key
  with a wrong test). Detection by the static contract and by a behavioral probe (the off variant over Validation).
- **Search tier**: generated daily outcomes (no Gym, no drift figures) through the same lines with lineage selection:
  thirty-two noise variants per lineage ranked on Train, up to five candidates validated in rank order with the
  lineage's validated-version count feeding the deflated Sharpe, and the holdout with Holm. Noise is net zero after base
  costs (a demanding null), Gaussian and fat-tailed (Student-t, three degrees of freedom), in every band a floor variant
  opens: 12, 42 and 48 trades a year sit under today's floors (Train 40 a year, Validation 50), 126 above them. Planted
  lineages carry a fixed net edge at 12, 48 and 126 trades a year.

## Results: release B's evaluator

Tree: main at `3eaf4d06` (release B, #454, with #456) merged into this branch and committed as `2d028fa8`;
`gym-engine-4`, execution fingerprint `47587e22c5af`, evaluator sources `771b675df22a` (the evidence, gate, researcher,
review-contract, experiment, results and stats modules), fixture `1ee0e716bc8d`, suite `c78a85148343`; Python 3.14.7,
numpy 2.5.3, pyarrow 25.0.1 (each receipt's `tree` and `runtime`). Each cohort: 8 worlds and 128 search lineages per
search case. Development took 930 s and confirmation 973 s on one core of a shared machine. Against this suite's
previous receipts (suite `0e9badba` on release B at `5f2c4282`, in this file's history at `bfc01650`; suite `ce161776`
on release A, `777b894f`, at `cb9fac40`), every case, search band, ablation and variant figure the runs share is
identical in both cohorts: neither release B nor this revision's walk moved any of them. This revision adds the draws
proof and widens the reach proof's walk to the names no `dir()` lists; the previous one added the two np.polynomial
proofs, the walk-based reach proof, the opened routes and the per-case figures.

### Headline

| Rate | Development | Confirmation |
| --- | --- | --- |
| False promotion, every negative case-world | 16/160 (10.0%; 95% 5.8–15.7%) | 16/160 (10.0%; 95% 5.8–15.7%) |
| False promotion, what the mechanical stages are meant to stop | 0/136 (95% upper 2.7%) | 0/136 (95% upper 2.7%) |
| Negative cases promoted in any world | 2/20 | 2/20 |
| Negative cases promoted, mechanical scope | 0/17 (one-sided 95% upper 16.2%) | 0/17 (one-sided 95% upper 16.2%) |
| Missed signal, planted case-worlds | 23/40 (57.5%; 95% 40.9–73.0%) | 22/40 (55.0%; 95% 38.5–70.7%) |
| Planted cases missed in at least one world | 4/5 | 4/5 |

Read the case counts, not only the case-world counts. Outcomes cluster by case: every negative goes 0/8 or 8/8, so the
136 case-worlds behave like 17 trials, and the Clopper-Pearson interval on 136 assumes an independence they do not have.
What the suite supports is that none of the 17 negatives the mechanical stages are meant to stop was promoted in any
world of either cohort (one-sided 95% bound 16% per case), conditional on this fixed case mix.

All 16 false promotions in development and 16 in confirmation are two review-dependent memorized tables, each promoted
in every world with a direction hit rate of 0.99 to 1.00: the table keyed by opening price level and the session-indexed
list. Nothing mechanical can stop a dense memorized table by design. The review contract names both (`calendar`:
hard-coded absolute price regimes and reconstructed historical dates), and a grounded rejection of each survives the
contract's check. That is the load the review carries. The sparse memorized table is stopped in every world, by the
Train activity floors alone: it trades 6 to 22 sessions a Train year in development and 6 to 20 in confirmation
(`figures.train_trades_per_year`), against a floor of 40.

| Case | Answer | Development | Confirmation |
| --- | --- | --- | --- |
| `absent_signal` | no edge | 0/8 (Train stress 8) | 0/8 (Train stress 8) |
| `cost_erased` | no edge | 0/8 (Train stress 6, drift 2) | 0/8 (Train stress 7, drift 1) |
| `drift_only` | no edge | 0/8 (drift 7, Validation 1) | 0/8 (drift 8) |
| `edge_disappears` | no edge | 0/8 (holdout 8) | 0/8 (holdout 8) |
| `planted_dense` | edge | 7/8 (Validation 1) | 6/8 (holdout 2) |
| `planted_sparse` | edge | 0/8 (Train eligibility 8) | 0/8 (Train eligibility 8) |
| `planted_medium` | edge | 2/8 (Validation 4, holdout 2) | 4/8 (Validation 3, holdout 1) |
| `planted_regime_gap` | edge | 0/8 (Train eligibility 8) | 0/8 (Train eligibility 8) |
| `planted_regime_years` | edge | 8/8 | 8/8 |

Most missed signals are the activity floors, not weak evidence: the sparse and gap-regime edges never pass Train's
per-year floor of 40 trades (sparse 6 to 19 and gap 14 to 32 trades in a Train year in development, 8 to 20 and 16 to 25
in confirmation), and every Validation stop of the medium edge is the trade floor alone
(`validation_stops.failed_checks`), at 39 to 49 trades in development and 45 to 48 in confirmation. The dense edge's one
Validation stop in development is its t alone (1.90). Across both cohorts the planted edges' Validation t runs from 1.9
to 7.3 (per-case medians 3.2 to 4.7; `figures.validation_t`). The year-regime edge, absent in the first Train year, is
promoted in every world: the robust Train objective (the worst year's t) only ranks a family's versions, and a single
version's negative score does not stop it. Among several versions it would rank below any version with a positive worst
year.

### Leakage

Each cell: promotions in eight worlds and where the others stopped; the probe's direction hit rate over its Train runs
(about 0.5 when it learned nothing); for a probe the static check refuses, what it did with the check opened (direction
hit rate, Validation t across the worlds, and the worlds in which it made money).

| Probe | Development | Confirmation |
| --- | --- | --- |
| `leak_future_index` | 0/8 (Train stress 8); hit 0.52 | 0/8 (Train stress 8); hit 0.51 |
| `leak_array_base` | 0/8 (static 8); opened: hit 0.48, t -3.1 to 1.0, profitable in 1/8 | 0/8 (static 8); opened: hit 0.53, t -1.8 to 0.7, profitable in 2/8 |
| `leak_private_attr` | 0/8 (static 8); opened: hit 1.00, t 6.5 to 10.3, profitable in 8/8 | 0/8 (static 8); opened: hit 1.00, t 5.9 to 8.4, profitable in 8/8 |
| `leak_date_literal` | 0/8 (static 8); opened: hit 1.00, t 6.5 to 10.3, profitable in 8/8 | 0/8 (static 8); opened: hit 1.00, t 5.9 to 8.4, profitable in 8/8 |
| `leak_greeks_block` | 0/8 (Train stress 8); hit 0.51 | 0/8 (Train stress 7, drift 1); hit 0.52 |
| `leak_events_next` (smoke) | 0/8 (Train stress 8); hit 0.52 | 0/8 (Train stress 7, Validation 1); hit 0.51 |
| `leak_daily_bars` | 0/8 (Train stress 8); hit 0.48 | 0/8 (Train stress 8); hit 0.50 |
| `leak_volume_bars` | 0/8 (Train stress 8); hit 0.52 | 0/8 (Train stress 8); hit 0.51 |
| `leak_numpy_memo` | 0/8 (drift 8); hit 0.52; stress run contaminated 8/8 | 0/8 (drift 8); hit 0.51; stress run contaminated 8/8 |
| `leak_memorized_levels` | 8/8; hit 0.99 | 8/8; hit 0.99 |
| `leak_memorized_sparse` | 0/8 (Train eligibility 8); hit 0.99 | 0/8 (Train eligibility 8); hit 0.98 |
| `leak_memorized_sessions` | 8/8; hit 1.00 | 8/8; hit 1.00 |

On the paths tested, nothing in the ctx leaks the future: the arrays end at the current minute, the greeks are handed
out one row at a time, the prior-session bars end yesterday, and historical bar volume without first-observation
receipts is hidden even when the file holds it (direction hit rates 0.48 to 0.52). The static check refuses three
probes, and the suite opens it for each, in every world: the greek-cache probe (it reaches the cache through the
snapshot's greeks source) and the date-table probe then read the window's future (hit rate 1.00, Validation t 5.9 to
10.3, profitable in every world), so the check is what stops them. The array-base probe learns nothing even opened (hit
0.48 in development and 0.53 in confirmation, profitable in 1 and 2 of 8 worlds): the engine hands a program a copy
whose base is a bytes copy of today so far, a second guard. The headline's refusal list flags a release that stops
refusing any of the three. The numpy memo's normal runs learn nothing, but its 1.5x-stress runs, made after the normal
runs over the same days, are contaminated in every world. Not tested: open interest (the world writes none), and highs,
lows and opens separately (they join the history on the same path as the closes). The holes the suite found let programs
or runs pass information to each other instead: see State.

### Invalid fills

Impossible fills: 0 in development and 0 in confirmation, over 32 checked program-worlds per cohort (4 probes with a
detector, each over five runs; `impossible_fills_by_case`): no stale quote bought at the decision minute (orders meet
the next minute's quotes), no crossed quote filled (the store drops them), no vertical opened at or below zero or closed
above its width while a leg was blown out (the package's payoff bounds hold on open and close). The passive
spread-capture probe has no fill detector and is judged on P&L: it loses under adverse selection. Every fill probe loses
money (Validation t at most -1.0 in any world) and stops at the Train stress run in every world.

### State and the review contract's facts

| Proof | Fact | Development | Confirmation | Observed (development, first world) |
| --- | --- | --- | --- | --- |
| `state_fresh_runs` | state | 8/8 | 8/8 | 5, 5 |
| `state_params_copied` | parameters | 8/8 | 8/8 | 1, 1 |
| `state_numpy_runs` | state | 0/8 | 0/8 | 65, 0 |
| `state_numpy_batchmates` | state | 0/8 | 0/8 | 65, 0 |
| `state_numpy_runs_sctypedict` | state | 0/8 | 0/8 | 65, 0 |
| `state_numpy_batchmates_sctypedict` | state | 0/8 | 0/8 | 65, 0 |
| `state_numpy_runs_polynomial` | state | 0/8 | 0/8 | 65, 0 |
| `state_numpy_batchmates_polynomial` | state | 0/8 | 0/8 | 65, 0 |
| `state_numpy_draws` | state | 0/8 | 0/8 | 65, 65 |
| `state_numpy_reachable` | state | 0/8 | 0/8 | 52 reachable: 14 through `np.matrixlib`, 36 through `np.polynomial`, `np.sctypeDict`, `np.typecodes`; setters `np.dtypes.register_dlpack_dtype`, 3 through `np.matrixlib`, `np.polynomial.set_default_printstyle`; draws `np.matlib.rand`, `np.matlib.randn` |
| `state_ctx_batchmates` | context | 0/8 | 0/8 | 65, 0 |
| `state_split_segments` | state | 8/8 | 8/8 | 195, 195 |

`state_fresh_runs`, `state_params_copied` and `state_split_segments` rebuild the state-reset proof Codex ran on Sept 30
and lost: STATE resets between runs, the engine-4 parameter binding holds (see Ablations), and splitting Train does not
change an intraday program's days. The other nine proofs fail in every world of both cohorts, and release B fixes none
of them. They are three defects: numpy objects a program can write (seven proofs, the reach proof among them), numpy's
shared generator a program can draw from (`state_numpy_draws`), and the ctx view batch-mates share
(`state_ctx_batchmates`).

**What a program can reach and write.** The reach proof walks everything a program can reach from `import numpy` and
`import math` without calling anything: every public attribute, mapping value and key, and sequence and set element,
through modules, classes and instances, transitively, as the scored tree's own static check admits each read. A module's
names are not only what `dir()` lists. The walk also reads the module's own dict (numpy's `__dir__` hides `matrixlib`),
its package's submodules as importlib finds them, and every name its module `__getattr__` can resolve (numpy's resolves
`np.matlib`, which no `dir()` lists), and it repeats until a pass imports nothing new. On numpy 2.5.3 that is 1,913
objects, 9,377 reads, 8 deep, and the walk finished (`complete`; `walk` in the receipt's reach proof). Every writable
object it finds (a dict, list, set or bytearray, a writable numeric array, anything with item assignment) is written by
one loaded program through the engine, and the suite checks what the write left behind after the run and whether a
reader sees it on a later run and beside the writer in one batch. The proof also requires the check to refuse attribute
writes (assignment, `del`, `setattr`, `delattr`) on every reached object, no global setter (a callable named `set_*`,
`register_*`, `seterr*` or `setbufsize`) to be reachable, and no function that draws from numpy.random's process-global
generator (`draws`). It holds only when all of that does. A fix that refuses the reads makes it hold. So does one that
keeps the writes from outliving a program, provided the setters and the draws are still refused: a unit test runs an
engine that isolates each program, and the proof holds with every writable object still reachable once the setters and
draws are refused, and fails without that.

It finds 52 writable objects, and a program's write to every one of them is still there after its run (`reachable`); a
reader that checks every mark trades 65 sessions alone, 0 after the writer's run and 0 beside the writer in one batch
(`trades`). The 52:
- two module-level dicts, `np.typecodes` and `np.sctypeDict`;
- 36 arrays in `np.polynomial`: each basis module's `*domain`, `*one`, `*x` and `*zero` constants (`polyx`, `chebx`,
  `hermdomain`, ...) and the six classes' default `domain` and `window` (`Polynomial.domain`, ...);
- 14 registries of numpy's core, through `np.matrixlib`: its `defmatrix` module binds `numpy._core.numeric` as `N`, and
  through it a program reaches `multiarray.typeinfo`, `numerictypes.allTypes`, `numerictypes.genericTypeRank`,
  `numerictypes.sctypes` and the five lists in it, `overrides.ARRAY_FUNCTIONS`, and the `keywords` dicts of four of
  numpy's dispatch decorators (`array_function_dispatch` and its kin).

numpy itself consults `sctypeDict` when it resolves dtype names, and a polynomial built with the defaults is evaluated
through its class's `domain`, so a write there changes what another program computes, not only what it knows: the
polynomial batch-mate proof's reader stands aside whenever `Polynomial([0, 1])(0.5)` is not 0.5, and it trades 65
sessions alone and 0 beside a writer that sets `Polynomial.domain[1] = 3.0` (`state_numpy_batchmates_polynomial`).

Five reachable functions change state every caller shares (`setters`), by their names and documentation (the suite lists
them and does not call them): `np.polynomial.set_default_printstyle` (how every polynomial prints),
`np.dtypes.register_dlpack_dtype` (a process-wide registry that, its documentation says, raises on a conflicting second
registration of a key), and, through np.matrixlib, `set_typeDict` (it replaces the dictionary numpy's C code looks array
types up in), `set_datetimeparse_function` (undocumented) and `set_module`, a decorator that rewrites a function's
`__module__`. Two more draw from numpy.random's process-global generator: `np.matlib.rand` and `np.matlib.randn`
(`draws`). numpy seeds that generator from the operating system and every caller advances it, which is what
`NUMPY_BANNED`'s `random` exists to close (a program is deterministic). The draws proof's program takes each session's
side from `np.matlib.rand`: in the first world it trades 65 sessions on each of two runs of the same days, and the two
runs' trades differ in every world of both cohorts (`state_numpy_draws`). The four setters numpy has at its top level
(`seterr`, `seterrcall`, `setbufsize`, `set_printoptions`) are refused today (`refused_containers`). And the walk
reaches seven standard-library modules outside the import allowlist without an import (`foreign_modules`): `functools`
through `np.polynomial.polyutils`, and `abc`, `ast`, `collections`, `collections.abc`, `contextlib` and `itertools`
through np.matrixlib. Nothing in them is writable, and the walk follows them.

The underlying's view is built once a minute and shared by every batch-mate with the same history, with a plain dict
inside it (`state_ctx_batchmates`). These contradict two of the review contract's facts (`state`: never across
independent replay runs; `context`: read-only copies), so a reviewer who cites them today has a concrete route and is
right.

Scope: production Gym boxes run each batch unit in its own process, which isolates runs from each other but not the
programs of one unit. The House's live decider holds every live program instance in one child process
(`league/live/decider.py`), so the batch-mate channels exist between whatever programs it runs together. Release A's
batch isolation contains a failing program's errors; it does not separate this state. The fixes belong to `league/gym`
(a Gym change resets evidence) and are not in this change:
- **numpy.** Refusing `typecodes` and `sctypeDict` is not a whole fix: it leaves np.polynomial's arrays, np.matrixlib's
  registries, the setters and np.matlib's draws open, and the suite says so (the dicts' four proofs hold; the two
  polynomial proofs, the draws proof and the reach proof still fail; a unit test simulates it). This report's previous
  revision recommended four names (the two dicts, `polynomial` and `register_dlpack_dtype`); its walk read only what
  `dir()` lists, and those four still leave np.matrixlib's registries and setters and np.matlib's draws open (a unit
  test simulates it). The smallest denylist that closes everything the walk finds adds six names to `NUMPY_BANNED`:
  `typecodes`, `sctypeDict`, `polynomial`, `register_dlpack_dtype`, `matlib` (its `rand` and `randn` read numpy.random's
  process-global generator, so two runs of the same days differ) and `matrixlib` (its `defmatrix` module hands out
  numpy's core and modules outside the import allowlist). A unit test simulates it on both CI jobs' numpy, 2.4.4 and
  2.5.3: every numpy proof holds, and the walk reaches nothing writable, no setter, no draw and no module outside the
  allowlist. Refusing a name is not refusing an object: with `sctypeDict` refused, the same dict is still reachable as
  `numerictypes.typeDict` through np.matrixlib, which is why `matrixlib` has to go with it. `NUMPY_BANNED`'s
  `polynomial_utils` names nothing numpy has (the module is `polyutils`). The robust form is an allowlist of the numpy
  names programs use, since a numpy upgrade can add objects a denylist has never seen; the reach proof re-checks
  whatever numpy the scored process has.
- **ctx.** Make the view's coverage mapping read-only.

When they land, the probes are refused (or the writes stop outliving a program) and the proofs hold with no edit to the
suite; a unit test runs the refused path through the whole report. The pipeline's numpy memo probe reaches `typecodes`
only, so its refusal alone says nothing about the other 51 objects.

### Broken ablations

| Switch | Broken | Static contract refuses the off override | Off variant still trades |
| --- | --- | --- | --- |
| `ablation_ctx_params` | no | 0/8 | 0/8 |
| `ablation_default_capture` | no | 0/8 | 0/8 |
| `ablation_module_alias` | no | 0/8 | 0/8 |
| `ablation_shadow_config` | yes | 8/8 | 8/8 |
| `ablation_read_ignored` | yes | 0/8 | 8/8 |
| `ablation_dynamic_key` | yes | 0/8 | 8/8 |

Identical in both cohorts. The static contract detects 8/24 broken switches (33%, 95% 16%–55%) with 0 false alarms in 24
working ones; the behavioral probe (does the off variant still trade over the 65-session Validation?) detects 24/24 (95%
lower bound 86%) with 0 false alarms in 24 (`ablation_rates`). Engine-4's binding works: every correctly wired switch
removes every trade.

### The review contract

For all four cases with a known defect line (the numpy memo and the three memorized tables), a grounded rejection (a
real excerpt, a contract fact, a counterexample) stays a failure through `grounded_answer`, and the same claim with an
excerpt not in the program falls to unclear, which can never open a holdout (`review_contract` in each receipt's
headline). That checks the receipt's shape; whether a model finds the defect is not measured here.

## The owner's rule, measured (no change proposed)

Each variant re-judges the same recorded outcomes. It meets the owner's rule only if, against `current`: engine false
promotions are not higher; search false promotions are not higher; engine negatives that pass Validation (and would
spend a holdout look) are not higher; noise lineages that spend a holdout look are not higher in ANY of the seven noise
bands; and missed signals fall. The look counts carry the power. End-to-end false promotion on noise cannot see a floor
change at all: the holdout with Holm stops every noise lineage even under two-trade floors. The verdict must reject the
`no_floors` reference, and it does in both cohorts (`verdict_sensitivity`: the rejection shows on the engine promotions,
through the sparse memorized table, on the engine looks and on the noise looks).

The rules: `current` is Train 40 trades on 20 days every year and Validation 50 on 25; `aligned_floors` lowers
Validation to 40 on 20; `sparse_floors` is Train 6 on 5 every year and 30 on 20 pooled, Validation 10 on 8;
`pooled_train` is the sparse floors ranked on the pooled Train t; `pooled_validation` validates over the last Train year
and Validation together; `no_floors` is the reference (two trades).

| Variant | Engine false (sparse table) | Engine missed | Search false | Noise looks | Search missed | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `current` | 16 (0) / 16 (0) | 23 / 22 | 0 / 0 | 3 / 2 | 269 / 263 | reference |
| `aligned_floors` | 16 (0) / 16 (0) | 20 / 19 | 0 / 0 | 14 / 26 | 165 / 161 | not met: noise looks rise |
| `sparse_floors` | 21 (5) / 23 (7) | 7 / 9 | 0 / 0 | 24 / 41 | 64 / 62 | not met: engine false promotions rise, engine looks rise, noise looks rise |
| `pooled_train` | 21 (5) / 23 (7) | 7 / 9 | 1 / 1 | 26 / 40 | 64 / 62 | not met: engine false promotions rise, search false promotions rise, engine looks rise, noise looks rise |
| `pooled_validation` | 16 (0) / 16 (0) | 18 / 19 | 2 / 0 | 47 / 68 | 141 / 149 | not met: search false promotions rise, noise looks rise / not met: noise looks rise |
| `no_floors` | 23 (7) / 24 (8) | 6 / 8 | 0 / 0 | 24 / 41 | 64 / 62 | not met: engine false promotions rise, engine looks rise, noise looks rise |

Each cell is development / confirmation. Engine counts are of 160 negative and 40 planted case-worlds; search counts are
of 896 noise and 384 planted lineages.

Noise lineages that spent a holdout look, by band, and the planted 48-a-year class promoted:

| Band (128 lineages each) | `current` dev | `aligned_floors` dev | `current` conf | `aligned_floors` conf |
| --- | --- | --- | --- | --- |
| noise, 12 a year | 0 | 0 | 0 | 0 |
| noise, 48 a year | 0 | 0 | 0 | 4 |
| noise, 126 a year | 3 | 3 | 2 | 2 |
| noise, 12 a year, t3 | 0 | 0 | 0 | 0 |
| noise, 42 a year | 0 | 3 | 0 | 5 |
| noise, 42 a year, t3 | 0 | 2 | 0 | 5 |
| noise, 48 a year, t3 | 0 | 6 | 0 | 10 |
| planted, 48 a year: promoted | 0 | 104 | 0 | 102 |

**No variant meets the rule in either cohort, and no threshold change is proposed from this suite.** A single cohort's
verdict is never cited alone: the confirmation receipt records, per variant, whether the frozen development verdict and
its own were both met (`met_and_confirmed` in the headline's `owner_rule`; a development receipt leaves it unset). No
variant is met and confirmed (0 of 6).

- **`aligned_floors`: withdrawn.** An earlier draft of this report recommended it, on the development cohort's four
  original noise bands, where its look spend did not rise. With nulls in the band it opens (42 and 48 trades a year,
  Gaussian and fat-tailed), the look spend rises on development (3 to 14 of 896) and on the independent confirmation
  cohort (2 to 26). It is a loosening of a Validation guard (50 trades on 25 days to 40 on 20), not only the removal of
  a mismatch with Train. What it buys is real: the 48-a-year planted class goes from 0 to 104 and 102 of 128 lineages,
  and engine misses fall by 3. What it costs: noise in the opened bands spends a holdout look in up to 10 of 128
  lineages a band, against 2 to 3 of 128 for dense noise today, and each look is charged in Holm for every later one.
  The rule as written is not met; whether the trade is worth making anyway is the owner's decision, and this benchmark
  does not certify it.
- **`sparse_floors`, `pooled_train`, `no_floors`.** Beyond the look spend in every band under today's floors, they let
  the sparse memorized table reach and pass the holdout in 5 to 8 of 8 worlds. Today the Train floors are the only
  mechanical stop for a sparse memorized strategy; lowering them moves that load onto the review. `pooled_train` also
  promoted noise lineages (1 in development, 1 in confirmation).
- **`pooled_validation`** spends the most looks (47 and 68 of 896) and promoted 2 noise lineages on development: pooling
  the last Train year, which chose the version, into Validation reuses selection data.
- A change that could meet the rule would need a compensating guard that holds the look spend flat in the band it opens
  (for example, a stricter Validation t for versions under the current floor), designed on development and confirmed on
  a fresh cohort under a new suite id. None is measured here.

### Cheap stages the suite measured (proposals, not applied)

- **Behavioral ablation.** Measured as the off variant over the full 65-session Validation, with switches that remove
  every trade when off: 24/24 broken switches caught, 0/24 false alarms (the static contract catches 8/24). A cheaper
  probe over a few Train days, on real filters that often do not bind on a given day, is not measured; its false-alarm
  rate would be higher.
- **Level-invariance probe.** Replay Validation on a store with every price scaled. It flags the level-keyed tables in
  every world, with 1 false alarm in 40 planted-edge runs in development and 1 in confirmation (a program with a dollar
  threshold), and misses the session-indexed list by construction: it detects 8/16 of the promoted memorized runs in
  development and 8/16 in confirmation (`level_invariance_probe`). Cost: one extra Validation replay per candidate, plus
  a scaled store the Gym must build (a `league/gym` change, so an evidence reset). A session-permutation or
  calendar-shift replay would target session-indexed memory; it is not measured.
- **Stress-contamination flag.** A version that does better at 1.5x the spread than at 1x over the same days learned
  something between the runs: the numpy memo (8/8 worlds in development, 8/8 in confirmation), and no other case
  (`stress_contaminated`). A flag, not proof: a program whose losses come from passive fills can gain when the stress
  run halves them.

## Limitations

- Invented worlds: an arithmetic random walk, planted edges that are deliberately strong, options fair by construction.
  These rates bound the evaluator's errors on these cases only, not on real markets or model-written research.
- The review is not called. The false-promotion rate is the mechanical pipeline's; review-dependent cases show the load
  the review carries.
- Runs are made in one process, as a one-worker batch makes them; production units each have their own process.
- The synthetic holdout is the suite's own; its Holm history is fixed at two failed looks.
- The search tier has no drift figures, Gaussian or Student-t noise with no serial dependence, and a fixed
  five-candidate schedule. It is not a simulation of model research.
- Eight worlds and 128 lineages per case: a zero count supports an exact bound, not a claim of zero. Case-worlds cluster
  by case, and every bound is conditional on this case mix.
- The reach proof covers what a program reaches without a call, in the scored process's numpy (2.5.3 here; a unit test
  checks the same 52 objects and the same draws on numpy 2.4.4, which the CI's Python 3.11 job runs). Objects reachable
  only through a call's result, names a class or instance resolves only in its own `__getattr__`, and state a call
  changes through a function neither named as a setter nor reading numpy.random, are not covered.
- These figures score main at `3eaf4d06`, the release B that is deploying. If main moves, or carries a Gym fix, score it
  with the same pinned suite and `--compare docs/benchmarks/evaluator_1.json`; main at `f082cf5e` is the oldest tree the
  suite can score.

## Reproduction

```sh
python -m league.swarm.benchmarks --suite evaluator --cohort development --json --output dev.json --receipt evaluator_1.json
python -m league.swarm.benchmarks --suite evaluator --cohort confirmation --frozen evaluator_1.json --json \
  --output conf.json --receipt evaluator_1_confirmation.json
python -m unittest league.tests.test_swarm_evaluator_benchmarks league.tests.test_swarm_benchmarks
```

A pinned suite is deterministic on the same Python, numpy and pyarrow: worlds, fills and bootstraps are seeded by
hashes. Each receipt's `replication_rows_sha256` is the digest of every world's figures (per-world seconds excluded),
recomputed from a saved full report by `receipt()`.
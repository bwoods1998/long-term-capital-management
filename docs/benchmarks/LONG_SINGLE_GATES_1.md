# Long-single frequency and drift diagnostic

This experiment measures the sensitivity of the current statistical rules to invented one-contract
option payoffs. It does not execute a strategy, consult market data, call a model, change a threshold,
or promote a family. A statistical pipeline pass here is synthetic evidence about the harness,
not qualification evidence for trading.

The generator was frozen in commit `2fe5037cd555e99f8c9c537c1046c0d88281ebc6`, based on
`54bbcdea`. Development and confirmation each contain 64 independent synthetic worlds per case.
The source and protocol remained unchanged between the two runs. The confirmation command checks
the development report's generator, evaluator, protocol, Python runtime and sample count before
generating any confirmation outcomes. The development and confirmation random streams are separate.

## What the experiment tests

Each replay window starts with $1,500. A policy buys at most one ATM call or put on an active day,
then closes that day. The normalized spot and strike are $100; the contract multiplier is 100.
Entry stops when the premium and all modeled costs cannot fit in remaining cash. There is no
compounding of contract count and no overlap. The premium cap is $75; the ordinary invented fair
premium is about $25.98. The declared maximum cash loss includes the premium and both sides' costs.

The root return is `0.001 + uniform(-sqrt(3), sqrt(3)) * 0.006 + signal * forecast_side` on
active signal days, and the first two terms on other days. The public forecast and entry schedule
precede an independent future shock. Terminal payoffs are exactly `10000 * max(side * return, 0)`.
Pricing uses the exact expectation of this payoff under the same uniform shock and zero drift.
Trading costs are $1.50 round-trip spread plus $1.30 fees; stress multiplies the spread by 1.5.

The positive controls use a deliberately large signal of 0.007. Their expected incremental P&L
after modeled costs is $43.99 per trade. This is an intentionally strong sensitivity control,
not a forecast of available returns. Twelve such signals imply roughly $528 of incremental annual
trading P&L under these invented assumptions, before project and service expenses.

The drift-only control always buys calls without a signal. Its expected raw net P&L is positive
because of the market drift, but its incremental edge over that exposure is negative after costs.
The cost-erased signal is only 0.0004: its incremental expectation is approximately minus $0.76
per trade after costs. The demanding zero-edge noise controls use each side's physical expected
payoff as its premium and an explicit invented credit offsetting base costs. That credit is a
null-control device, not an asserted trading opportunity. Their base-cost net expectation is zero.

There are five Train years, 2020–2024, and separate Validation and synthetic holdout windows.
Each year has 252 synthetic weekdays; this is not an exchange-calendar simulation.

## Actual rules and accounting

The benchmark calls `results.summarize`, `results.by_year`, `results.drift`, `evidence.train_score`,
`evidence.drift_screen`, `researcher.robust_at_stress`, `evidence.validation_line`, and
`evidence.holdout_line`. It preserves negative but otherwise eligible Train scores; positivity
is not an additional Train admission rule. Current thresholds remain unchanged:

- Train: 40 trades on 20 distinct days in **every** included year; rank by the actual worst-year objective.
- Drift: pooled alpha t at least 1 and positive alpha in all but one Train year.
- Validation: 50 trades on 25 days, positive mean, daily t at least 2, deflated Sharpe at least 0.95,
  three positive quarters and positive P&L under 1.5 spread stress.
- Holdout: actual moving-block bootstrap, Holm history, positive lower bound and required Sharpe retention.

Adaptive noise searches 64 predeclared random policies against the same market path. Train ranks
the versions that pass frequency and drift, then at most five candidates are tried in rank order.
The next candidate is tried after a failure; a pass or the actual look limits stops the search.
No Validation or holdout number chooses the Train ranking. The baseline noise case uses variant
zero from the same market and policy streams, making the comparison paired.

Every world uses a real temporary `SwarmStore`. All 64 versions belong to one lineage. Every
computed Train, mid-price, stress, Validation, diagnostic and holdout outcome is recorded as a
trial. The deflated Sharpe uses the actual count and history of validated versions, including
the current one. Each world starts with two explicitly invented failed global looks; subsequent
failed looks remain in that world's Holm history. The three-look lineage cap and leakage-alarm
function are called. A world cannot reach the ten-look alarm with this experiment's small history.
Different Monte Carlo worlds are independent experiments, not extra attempts by one real swarm.

Fixed policies also receive a separately seeded frequency diagnostic after the selection process.
It asks which Validation checks a hypothetical first validation would fail. These probes are
counted as trials, cannot enter the candidates, and cannot open a holdout look. No synthetic
holdout is read for a policy blocked on Train.

## Results

The [machine-readable receipt](long_single_gates_1.json) preserves protocol and source hashes,
aggregate counts, and hashes of the full receipts. Each table denominator is 64 independent worlds.

| Control | Trades/year | Development passes | Confirmation passes | Confirmation worlds with a Train/drift candidate |
| --- | ---: | ---: | ---: | ---: |
| Sparse planted edge | 12 | 0/64 | 0/64 | 0/64 |
| Train/Validation frequency gap | 48 | 0/64 | 0/64 | 64/64 |
| Incremental signal after drift | 126 | 64/64 | 64/64 | 64/64 |
| Drift-only calls | 252 | 0/64 | 0/64 | 0/64 |
| Cost-erased signal | 126 | 0/64 | 0/64 | 0/64 |
| One unselected noise policy | 126 | 0/64 | 0/64 | 1/64 |
| Search over 64 noise policies | 126 each | 0/64 | 0/64 | 51/64 |

The frequency floors exclude every sparse positive control in both cohorts. All 12-trade controls
pass the drift screen and retain sufficient cash, but none is Train-eligible. The independent
frequency diagnostic fails **only** the frequency checks in 46/64 development worlds and 55/64
confirmation worlds; some others also lack enough t, deflated Sharpe or quarter evidence. Every
48-trade control reaches actual Validation and fails **only** its 50-trade floor. The stronger
126-trade control passes every statistical stage in both cohorts. This demonstrates a deliberate
admission constraint that can reject a positive incremental expectation; it does not demonstrate
a profitable sparse mechanism in actual market data or justify changing the constraint.

The drift screen rejects every drift-only and cost-erased control in both cohorts. Raw Train
P&L is positive in 64/64 development drift-only worlds and 63/64 confirmation worlds. Rejecting
these is consistent with a goal of incremental timing alpha, even though directional exposure
has positive expected raw P&L in this invented market. The benchmark does not show excessive
rejection of the strong incremental signal. It is not a power study near the minimum useful edge.
Cash exhaustion affects 11/64 development and 13/64 confirmation cost-erased paths, and one
confirmation drift-only path; these are distinct from a policy's intended annual frequency.

Train selection makes noise look better. Candidate worlds rise from 5/64 to 48/64 in development,
and from 1/64 to 51/64 in confirmation. In confirmation, the unselected baseline's median Train
score is -1.538; the selected candidates' median is +0.083, conditional on having a candidate.
The adaptive search makes 136 development and 138 confirmation Validation attempts. None passes
in development; one passes in confirmation and is stopped by the holdout.

The confirmation counterexample is world 14, variant 11. Its Validation t is 2.9084, deflated
Sharpe 0.99896, and all four quarters are positive. Its synthetic holdout also has positive P&L
($657.89), but the bootstrap lower bound is negative and p=0.051 exceeds the actual Holm threshold
of 0.01667. The failed look stays charged. Four later validations increase the same lineage's
validated-version count to five; none passes. That world finishes with 85 trials, one lineage
look and three global looks including the seeded history. The receipt contains this full row.

There are no false statistical pipeline passes in either cohort for any negative control. For
each case separately, 0/64 confirmation passes still permits a one-sided exact 95% upper bound
of **4.57%** on this experiment's pass probability. The paired noise cases are not independent
and their counts are not pooled to claim a tighter bound. This is insufficient evidence for a
very small production false-qualification rate.

The two runs recorded 12,769 computed trials and 129 newly generated synthetic holdout looks
across their independent worlds. All accounting totals reconcile with their `SwarmStore` rows.
The ten new mechanism/protocol tests and four existing benchmark tests pass. The generator was
not revised after examining confirmation.

## Reproduction and limits

Run from the frozen source revision, under Python 3.14 as recorded in the receipt. Output files
must not already exist. Changing any fingerprint requires a new development report; the old
confirmation result remains evidence only for its recorded source revision.

```sh
python -m league.swarm.long_single_benchmarks --cohort development --replications 64 --output development.json
python -m league.swarm.long_single_benchmarks --cohort confirmation --replications 64 --frozen development.json --output confirmation.json
python -m unittest league.tests.test_swarm_long_single_benchmarks league.tests.test_swarm_benchmarks
```

This panel is deliberately narrow. It excludes realistic chains, fills, liquidity, assignments,
exercise, settlement constraints, overnight gaps, changing volatility, serial dependence, regime
changes, model code review and independent forward evidence. It does not implement a research model
that invents new policies in response to feedback. Project expenses can exceed the sparse control's
trading profit. Cash exhaustion is reported separately from direct frequency failures. The
positive signal is much stronger than an unproven market mechanism, and the null pricing credit
is artificial. Finite synthetic false-pass counts cannot establish a production error rate.

These findings can motivate a separately preregistered comparison of evidence designs, with
independent null and positive controls. They do not authorize loosening an eligibility rule,
splitting one decision into trades to meet a count, recycling a look, or forcing qualification.

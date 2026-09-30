# Continuous-learning run — September 30, 2026

This continues T0 `2026-09-26T06:23:14Z` and the existing financial reset. Objective and acceptance
evidence: [continuous learning](../goals/LTCM_CONTINUOUS_LEARNING.md). The goal is **not achieved**.

## Reconciliation at 04:32 UTC

- Origin/main: `a6bee4be`; deployed House: `20260929T134303Z-8366493c614c` (R11a).
- House and supervisor verified alive. Health fresh with no failures. Real money enabled; restored
  House real experiment still incorrectly reports `observe: "live"`.
- 55 live Gym families; 1,627 retired; two holdout looks, zero passes; qualified forward table empty.
- Real ledger: nine completed calibration round trips, approximately $18 loss. Calibration is not
  family-performance evidence. No qualified real strategy has established profitability.
- Sail funded balance about $197.88; Claude funded total $200, remaining $55.72. OpenAI roles are
  intentionally disabled and September's allowance is not renewed. No provider/model migration or
  funding increase is part of this run.
- The prior night's forward checkpoint exists. Next nightly job is scheduled for 06:00 UTC.

## Work in progress

- Restoration: reviewed and merged PR #429 as `87af7a62`; 82 local House/live tests pass with pinned
  Gym dependencies, and CI passed on Python 3.11 and 3.14. Deployment remains outstanding.
- Research efficiency: preserve R11b, fix normal/diagnostician retirement, replace repeated paid
  hold polling with durable waits, and integrate practice-feedback wake events.
- Experiment contract: enforce effective parameter overrides, fast preflight, runtime-state
  invariants, and grounded reviewer context. Any execution-semantics change must invalidate the
  appropriate caches/images/evidence before research/live adoption.
- Practice: build on PR #430 with bounded persistent immutable cohorts, feedback, and fresh
  post-revision evaluation. No practice observation is an automatic real-money promotion.
- Input coverage, economic reconciliation, and persistent measured harness self-improvement remain
  incomplete. Engineering and calibration progress do not establish positive Net.

Private operator evidence lives under the owner's `Work/ltcm-goal-ops/`; no raw quotes, program
parameters, credentials, or licensed data are committed with this record.

## Initial statistical benchmark

`python -m league.swarm.benchmarks --replications 32` exercised the actual summary, Train,
Validation and holdout arithmetic with generated cash outcomes. Protocol SHA:
`aa434f1015839bf98bd0fd4e6d038977bf29bb0933854e891e87e92e82f256ab`.
Evaluator SHA: `2783ee61c3d627754cdfa563ac8e9991fd70f7cda2154b223a35d6a5c911e0fe`.
The development and independent confirmation cohorts each produced:

| Generated case | Pipeline passes / 32 | Finding |
| --- | --- | --- |
| Absent signal | 0 | Rejected before holdout |
| Planted edge | 32 | Detected by the tested statistical path |
| Costs erase gross edge | 0 | Rejected before holdout |
| Edge disappears on unseen data | 0 | 32 holdout looks, all rejected |
| Positive low-frequency edge | 0 | Existing annual trade-count requirement rejects it |

Zero of 32 gives a one-sided 95% upper pass-rate bound of 8.94%, so these controls do not establish
a 5% false-promotion guarantee. This benchmark does not test adaptive search, drift screening,
code review, actual fills, or live promotion. It establishes no market edge. The sparse-case
result motivates an independent study of eligibility rules; no threshold was changed.

The published compute feed also omitted Claude charges while retaining historical OpenAI charges.
The fix uses the existing `other_usd` field, with an end-to-end checkpoint assertion; 63 publishing
tests pass. Complete all-input accounting remains outstanding.

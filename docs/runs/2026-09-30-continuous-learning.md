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

- Restoration: reviewed PR #429; 82 local House/live tests pass with pinned Gym dependencies. The
  previously cancelled Python 3.11 CI job has been restarted. Deployment remains outstanding.
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

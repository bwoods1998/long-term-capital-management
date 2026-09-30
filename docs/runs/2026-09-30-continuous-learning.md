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
  Gym dependencies, and CI passed on Python 3.11 and 3.14. Release
  `20260930T045038Z-cb6035693ef4` promoted at 04:51:15 UTC and completed its ten-minute health watch
  at 05:01:20 UTC. The restored real instance reports `observe: false`, saved mode `live`; the
  money digest is unchanged. Source hashes confirmed this release changed only the restoration fix
  and its regression test from the previously deployed tree.
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

## Integration and remaining adoption checks

The integration tree combines R11b, durable research waits/retirement, the practice league and
immutable cohorts, parameter binding, grounded gate reviews, and the existing history-window
controller (PR #413). The combined initial swarm suite passed 779 tests (one existing skip);
the cohort delta passed 247 focused tests; the merged data tools passed 158 data tests. These
changes are not yet deployed. Engine adoption must invalidate old selection caches, reject late
old-evaluator results, and require current qualification for entries while preserving exits,
historical trials and consumed holdout looks.

Read-only adoption audit: all living families are still Gym; no qualified real strategy. The real
House experiment reads `ctx.params` rather than global `PARAMS`, so binding global defaults does
not change that frozen program's decisions. The residual practice program has no overrides.

At 05:00 UTC the historical collector was alive, with eleven failing tasks left in optional older
history blocks. The base stages are complete. The runner's confirmed quiet cutoff is 05:20 UTC;
the next forward job is due at 06:00 UTC. Historical SIP completion has reached March 2022 but
waits while that collector is running. No vendor failure was relabeled valid data.

Cost reconciliation found another distinction to preserve: at approximately 04:56 UTC the Sail
provider reported $71.90 for all 307 project boxes since T0, whereas the swarm had booked $121.81
of estimated Gym-box usage. These are alternative measures, not additive charges. Recorded model
charges were Sail $197.70, OpenAI $50.23 and Claude $144.69. These were booked totals; that reading
did not establish settlement coverage, and the later journal audit identified outstanding holds.
Data subscriptions and any unallocated standalone work still need reconciliation; none of
these readings establishes complete project Net. Existing ledgers and financial baselines remain
unchanged.

## Release candidate at 05:25 UTC

The candidate now also includes evaluator-scoped adoption, executable qualification proofs,
causal optional share-volume inputs, and PR #425's two-sided single-option families. Adoption
archives old selections, requires current replay evidence, and preserves every trial, holdout
look and reservation. Colliding worker run IDs across evaluator bundles retain separate metrics
and result files. The declared `long_single` family still submits concrete call or put orders;
its joined lineages retain both sides' search history. Constitution and money digests are unchanged.

The combined Gym/live/swarm/data/publishing run exercised 1,599 tests. Its one failing integration
fixture constructed a live band without the newly required qualification proof; the fixture was
corrected and all 36 targeted proof tests passed. The adoption branch separately passed 382 live
and 123 final store/cache/sweep tests. Final combined swarm and hosted CI checks remain required
before promotion of this candidate. The complete final swarm rerun passed 816 tests (one existing
skip), and all 16 integrated harness-controller tests passed, including sandboxed comparisons of
two actual commits. These checks are engineering evidence, not trading returns.

At 05:20:54 UTC the historical runner stopped for its scheduled quiet window, with no requests in
flight and the eleven vendor failures preserved. The collector is clear for the 06:00 UTC nightly
forward job. An audit of the active Train image found volume in 991 of 21,349 underlying sessions;
891 of those sessions contain every expected minute. These historical values lack publication/as-of
receipts: a bar revised after its minute cannot be backdated into the original live decision. The
candidate therefore withholds those minute values and daily sums from strategies. Live first
observations remain available with explicit provenance and restart persistence. The correction's
115 targeted tests passed, including the concrete late-revision counterexample; final integrated
volume checks remain required. Raw coverage does not establish point-in-time input availability.

## Foundation merged; observation through 06:13 UTC

PR #431 passed the gateway job and both complete hosted Python 3.11/3.14 jobs on
`9249c470b48432f4f1116e07d7a7845aced256db`, then merged at 05:59:25 UTC as `ed545499`.
The final local volume/live/qualification checks passed 103 tests. The actual House remains on
`20260930T045038Z-cb6035693ef4`; none of the broader foundation changes has been deployed or
verified in production. The prepared adoption audit must compare the new evaluator, current
entry proofs, trials, consumed looks, frozen exit paths and persistent practice state before
deployment can be described as successful.

Read-only observations at 05:31, 06:05 and 06:13 UTC show a fresh House/swarm heartbeat and no
reported health failures. At the last reading there are 66 living Gym families and 1,676 retired
families, two failed holdout looks, zero passed looks and no qualified forward rows. Those are
research activity counts, not profits. The September 29 nightly forward job has completed and
published its checkpoint; the September 28 checkpoint remains recorded. No trade, allocation,
capital, provider-budget or live-release change was made during this follow-up.

Historical SIP completion still retries March 8, 2022. A read-only probe of the existing provider
endpoint found only the 21:00 UTC close-stamped PLTR bar and zero regular-session bars, both when
requested alone and with the full stock universe. BABA and TSM had one regular-session bar each;
most peers had 390. This establishes a source-coverage gap, not a calendar correction or permission
to synthesize bars. The missing day remains incomplete. Raw response prices are not in this record.

## Research supervision and evidence follow-up

The separate follow-up adds a release-bound read-only harness observer with an explicit private
policy, a lifetime lock, verified recovery after an interrupted process-record write, nonblocking
transition waits, pidfd-bound stop signals, and visible capture/reconciliation errors. The observer
does not author patches, call paid models, evaluate candidates, deploy code or place orders. No
production policy or observer was activated. The combined runtime/hook/lab tests passed 75 cases;
the final nested-error correction passed all 23 runtime/CLI cases. Independent review reproduced
the original failures and confirmed the corrections. Its runbook distinguishes exception handling
from a hard latency bound on synchronous House filesystem work.

Researchers and the Architect also receive cached metadata for the exact active Train image.
Missing, malformed or differently imaged cards remain unknown. Raw volume coverage never grants
point-in-time volume access; publication receipts are still absent from the historical reader.

The [frozen long-single diagnostic](../benchmarks/LONG_SINGLE_GATES_1.md) adds two independent
64-world cohorts using the actual frequency, drift, Validation, holdout and lineage functions.
Both cohorts reject all 12- and 48-trade positive controls, while the deliberately strong
126-trade signal passes in every world. Searching 64 noise policies produces many more attractive
Train candidates; one confirmation candidate passes Validation and is rejected by holdout. Failed
looks and later validations remain counted. No negative control completes the statistical path,
but zero of 64 permits a 4.57% one-sided 95% upper bound per case. This is a synthetic sensitivity
study, not evidence of a market edge, complete pipeline calibration or permission to lower a gate.

The private economic reporter now preserves source receipts and separates booked reservations,
priced charges, finalized box costs and estimates. Independent review caught unknown Claude
gateway settlements being mistaken for priced bills and missing fee/liability coverage being
treated as complete. Corrected schema 2 keeps these unresolved, rejects inconsistent position
counts, and settles a later verified bill exactly once. The 83 accounting regressions pass,
including 28 focused cases independently rechecked. Earlier reports remain historical snapshots;
they are not silently upgraded. External engineering attribution, outstanding reservations and
different billing cutoffs still prevent complete project Net. Fees already present in position
cash are not charged again, and provider box bills replace rather than add to Gym estimates.

The combined follow-up checks passed 178 tests. A final correction for the real book's explicit
reconciliation reason string passed all 28 economics tests; a missing reason remains unknown.
Content checks pass, and the execution fingerprint, model configuration and capital permissions
match the merged foundation. The schema 2 report captured at 06:16:22 UTC has $469.55 of known
inputs, excluding unresolved reservations and unknown external costs. Complete Net remains null.
Its live reconciliation receipt was 619 seconds old, so that snapshot also refuses to certify
broker-adjusted cash from a stale reading; the raw closed book cash remains minus $17.80.

These follow-up changes still require hosted CI. Repeated independently
retained harness improvements, qualified forward strategy profits and positive all-input project
Net have not been demonstrated. The production-profitability goal remains unmet.

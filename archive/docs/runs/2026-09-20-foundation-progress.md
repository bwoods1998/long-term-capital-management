# Foundation progress — September 20, 2026

The later [two-hour evening watch](2026-09-20-evening-watch.md) tracks current observations,
including a premature displacement and the paper-screen cadence bug found after this snapshot.

Latest verified runtime snapshot: **6:32 PM Pacific / September 21, 01:32 UTC**.
The foundation is producing reproducible experiments. The API chief architect cannot yet
repair the whole harness autonomously, and no profitable forward edge has been established.
The [handoff design](../design/2026-09-20-chief-architect-handoff.md) specifies the next build,
with separate engineering and financial acceptance criteria.

## Deployed work

| Change | Resulting behavior |
|---|---|
| [PR #16](https://github.com/bwoods1998/long-term-capital-management/pull/16) | Persistent $500/48-hour campaign, blocked new live allocation, exact experiment archives and corrected replay clocks/coverage |
| [PR #17](https://github.com/bwoods1998/long-term-capital-management/pull/17) | Research sessions, accepted provider identities and tool receipts survive restart; current-capability checks |
| [PR #18](https://github.com/bwoods1998/long-term-capital-management/pull/18) | Invalid mutations rejected before funding experiments; existing records preserved |
| [PR #19](https://github.com/bwoods1998/long-term-capital-management/pull/19) | Candidate input coverage and durable blocked engineering requests |
| [PR #20](https://github.com/bwoods1998/long-term-capital-management/pull/20) | Priced Astra, Sol, Terra and Luna routes through the protected gateway |
| [PR #22](https://github.com/bwoods1998/long-term-capital-management/pull/22) | Nonrenewable Luna startup grants and constrained repair of invalid legacy parameters |
| [PR #23](https://github.com/bwoods1998/long-term-capital-management/pull/23) | Registry-path normalization and shared test fixtures repaired |
| [PR #21](https://github.com/bwoods1998/long-term-capital-management/pull/21) | Architect's sports candidate merged after those external repairs |
| Jev integration and receipt precision | Metered Jev lane, completed semantic comparison, and correction of cent-rounded Luna receipts that falsely tripped campaign admission |

House release `20260921T004957Z-75888ab3f8c4`, based on `b1cc5fb`, passed its three-tick
canary at 5:54 PM Pacific and ten-minute production watch at 6:04 PM. Twenty changed shipped
implementation files matched the inspected source. Jev changes the gateway; it does not
require restarting the House or resetting the campaign.

At 6:32 PM:

- 36 agents alive, 19 retired; 72 completed research summaries in the phase.
- 19 replay trials, all linked to manifests; two historical passes.
- Meriwether-8 was the only phase promotion to paper. No new live capital was released.
- All four books reconciled; no new operational alerts since the House release.
- One Luna startup grant completed for Meriwether-14, returning strategy code for $0.007397
  at the gateway tariff. This verifies the grant path, not the strategy's quality or profit.
- Original campaign start/expiry and $500 cap intact; zero reservation breaches after the
  precision correction below. All model meters ready.

## Replay proof and its limits

Meriwether-8 passed historical replay at 5:19 PM Pacific and entered paper at 5:21 PM.
A fresh credential-free, sealed Sailbox reproduced both the complete result and evaluator
judgment exactly: **2,634 steps, 70 trades, 50 blocks**. The proof box was then terminated.

| Artifact | SHA-256 |
|---|---|
| Manifest | `6a6ffda55f67ba8af8cb9d72c9ac1781f8f89c6e19d39aea61a765d054d90297` |
| Result | `42d33b7ebac1cd85271d72abaab9be493d7c59bd07dee576ea951f288affc98d` |
| Evaluation | `03a3e810871a349e31ec36ebf57af8b6dfb28afb4a4bd98fc918773cc3b33fca` |

This reproduces a development-data result; it is not independent validation of a market edge.
The private archive retains source, parameters, inputs, evaluator and preceding trials.
The [phase guide](../phase-one.md#inspect-and-reproduce) explains isolated reproduction.

Huang-5 produced a second historical pass with 210 trades, including 208 wins. Its researcher
alleged a timing leak; that is not a confirmed diagnosis. A read-only timestamp audit found no
future-visible bars and all 236 eligible signal rows at least five minutes before close.
That narrow check does not establish quote freshness, source-clock accuracy, point-in-time
metadata or realistic fills. Its child admission was deferred; this was not a second paper
promotion. Investigate the suspicious result before treating it as useful evidence.

## Model routing and Jev

The [coding comparison](2026-09-20-model-routing.md) used actual blocked research tasks.
Production-setting Sail Pro Flex passed three structural checks cheaply in 264–598 seconds;
Astra passed all three in 55–98 seconds. Luna, Terra and Sol each passed two initially; a
bounded Luna feedback repair succeeded. These are program checks, not trading scores.

Jev's `POST /v1/typesafe/systemone` uses the existing Worker secret `TYPE_SAFE_TOKEN` and pins
`jev-1.13.0`. Its lifetime allowance is $10 and at most 100,000 accepted calls, expiring
September 22 at 1:22 PM Pacific. The initial $1/200-call restriction was expanded for the
proposed shared semantic workload, within the existing phase. Accepted request IDs persist;
the live duplicate probe returned 409 with unchanged counters and no additional inference.

| Development probe | Frozen labels matched | Median elapsed | Estimated model charge |
|---|---:|---:|---:|
| Jev, 12 cases | 9/12 | 0.416 seconds | $0.000241 |
| Luna, same 12 cases | 11/12 | 1.871 seconds | $0.001124 |

After the probe Jev reported 12 calls, $0.000241, zero pending and zero breaches. Costs
exclude hosting and are tariff estimates, not invoices. Full sanitized inputs, labels and
responses are in the [artifact](data/2026-09-20-typesafe-probe.json); the
[Jev design](../design/2026-09-20-typesafe-pilot.md) explains limitations and next evaluation.

The intended larger role is a shared semantic feature service: OpenAI proposes and improves
question sets, Jev evaluates recorded text, code/statistical models combine the results, and
independent tests decide which workflows survive. Versioned features are shared across agents.
This recursive feature-discovery service is specified, not yet connected to production trading.

### Bug found by cheap-call testing

The gateway stored OpenAI costs in microdollars but returned `X-LTCM-Cost-USD` rounded up to
cents. Three small Luna calls each reserved roughly $0.0053 and received a $0.01 cost header.
The campaign recorded apparent overruns and correctly stopped further paid admission. Nine
remaining comparison calls were refused before network transmission.

The fix returns exact six-decimal receipts while preserving the cent-rounded aggregate health
display. A regression exercises the sub-cent Luna case. Only the three confirmed pilot records
were reconciled using saved usage and the campaign's conservative premium rates: $0.030000
became $0.000445. Original rows and receipts remain in a transactional `cost_reconciliations`
audit table and private reconciliation artifact. No unknown charge, original reservation,
phase limit, start or expiry changed. The nine pre-network refusals then ran once; no accepted
or ambiguous request was repeated.

Gateway version `ca154764-aeea-409a-961d-061f6e50ded0` contains the precision fix and expanded
Jev lane. Post-fix Luna comparisons and the real startup grant returned sub-cent receipts.
This is a concrete regression case for the eventual API repair worker.

## Money and validation

The phase remains **$500 including external reserves**, not $500 of recorded spend. At 6:32 PM,
OpenAI-labelled commitments totaled $368.918157 including the $350 external engineering reserve
and $10 Jev earmark. Sail commitments/meter coverage totaled $11.433980 including its $5 reserve.
Infrastructure retained its $50 external reserve. Available automated headroom was approximately
$31.08 for foundation model work and $38.57 for Sail, subject to daily limits and later
commitments. None of these figures is a vendor invoice.

The full Jev earmark stays held until the route closes/expires and billing is reconciled.
Its internal allocation name is OpenAI for compatibility with the installed immutable policy;
actual Jev usage is separate. The broader plan remains $3,000 conditional R&D, $2,000 conditional
trading capital including existing balances, and $5,000 uncommitted reserve. No new deposit or
subscription is needed for the next engineering step.

Local validation: **123 gateway tests**, syntax checks and Cloudflare deploy. The preceding
House release passed 1,326 league and 1,773 retained-runtime tests on both Python 3.11 and 3.14,
plus its live canary/watch. New gateway checks cover authentication, credentials, schemas,
expiry, concurrency, durable identities, unknown bills, incompatible answers, pricing overruns
and microdollar receipts. GitHub also runs these suites on each proposed merge.

Private evidence retains deployment/watch captures, replay proof, provider responses, retired
box receipts, campaign reconciliation and runtime acceptance. The sanitized Jev artifact is
committed; raw account payloads, credentials and strategy source are not in this report.

## Five priorities

1. **Separate authority before core self-editing.** Move Sail credentials and aggregate resource
   admission outside the mutable House; protect release verification and trading mandates.
2. **Close the API engineering loop.** Durable jobs must reproduce, patch, repair failed checks,
   canary, deploy, verify the unblocked operation and recover from interruption.
3. **Make shared knowledge useful.** Build the versioned Jev feature/evidence service and measure
   improvements in completed experiments and model time, then independent market outcomes.
4. **Make selection survive aggressive search.** Preserve related hypotheses across founders,
   isolate independent evaluation and calibrate false discoveries under correlated trials.
5. **Reward verified marginal value, then scale.** Separate engineering and trading rewards,
   retain useful negative findings, and expand logical candidates with bounded concurrency.
   Additional data/model spend must beat an existing-data/model baseline.

The [handoff design](../design/2026-09-20-chief-architect-handoff.md) supplies acceptance tests,
capital tranches and target windows. Births, calls and PR counts alone are not success metrics.

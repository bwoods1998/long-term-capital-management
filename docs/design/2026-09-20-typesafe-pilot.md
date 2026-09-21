# Jev: shared semantic features and measured workflow decisions

September 20, 2026. The owner installed `TYPE_SAFE_TOKEN` as a Worker secret. The deployed
gateway now admits a **$20 lifetime allowance and up to 500,000 calls**, backed by retained
phase commitments and ending September 21 at **11:01:16 UTC / 4:01 AM Pacific**. The initial $1/200-request restriction was expanded
after considering fleet-wide semantic workloads. The owner requested using the full $20 for useful
classification work; the queue targets unique evidence and measured feature experiments. The first live comparison is complete. No production trading or promotion
decision consumes these answers yet.

Jev provides typed choices, rubric scores and yes/no probabilities over supplied text/state.
Its intended role is frequent semantic processing shared across the swarm, including candidate
market-text features and research/engineering decisions. The architect composes and evolves
these questions and uses generative models for code and difficult reasoning.
[TypeSafe introduction](https://docs.typesafe.ai/introduction).

## Larger role in the harness

The implemented shared lab consumes recorded public Kalshi market states and bounded research
results. Eight atomic market questions classify contract semantics, related exposure, missing
context and execution concerns; six research questions classify failures and unsupported claims.
One request shares its state across these questions. Content/model/rubric hashes deduplicate
work across agents. Each request has a durable intent and receipt; interrupted calls retain
their identity and are not automatically repurchased. A bounded worker queue, request pacing,
disk reserve and error cooldown support an unattended run.

Recent classifications become fallible evidence in researchers' `runtime_status` and the
architect's context. Labels cannot change budgets, submit orders, approve capital or merge code.
The lab separately matches labels to later recorded quotes, requires each label to precede its
outcome, and compares a fixed numerical baseline with added Jev features on later unseen events.
The target is a five-minute sampled midpoint direction, **not net profit or fill quality**.
Training and evaluation must have sufficient forward rows and distinct events before scoring.

The first real batch produced 128 typed market labels across 16 requests for **$0.001616**, with
no unconfirmed calls. It also retained 1,184 additional market packets and 25 research packets.
This verifies the queue/provider path; it does not validate label correctness or economic value.
At the published token price, $20 is approximately 476 million input tokens. Available distinct
inputs and productive rubric experiments determine actual spend. Repeating unchanged evidence
only to empty the account would not create independent observations.

| Candidate role | A question on our existing evidence | What a useful result would change |
|---|---|---|
| Shared semantic features | Does this timestamped report describe an unexpected disruption, an official resolution, or a change relevant to this contract? | Produce reusable features for independently tested strategies |
| Instrument/event matching | Do these descriptions refer to the same outcome and resolution condition? | Propose links for shared evidence; code checks venue identifiers, strikes and dates |
| Research/engineering routing | Given the request, error and capability snapshot, which existing tool or engineering queue best addresses this blocker? | Reduce wasted researcher turns and unnecessary frontier escalations |
| Related-work retrieval | Which of these recorded experiments or failed requests is relevant to this hypothesis? | Put the right past evidence in the next worker's context and avoid repeating failed ideas |
| Evidence relevance | Does this supplied, timestamped source support, contradict or fail to address this specific claim? | Filter context before a larger-model research call |

These are proposed uses, not established trading capabilities. Existing deterministic
validators remain the first choice for symbol coverage, numeric rules, fees, dates and budget
arithmetic. A model adds value only for the semantic part they do not already resolve.

The relevance classifier must not delete historical trials, determine a fresh selection
identity, certify novelty, close an engineering issue or authorize capital. It can suggest
relevant records; the independent checks still decide acceptance. Low-confidence, contradictory
or missing-input results go to an existing model or a dormant job with an explicit missing
prerequisite. No routine human review is necessary for that fallback.

The recursive loop should be:

1. OpenAI proposes or revises a versioned set of atomic semantic questions from observed
   research bottlenecks or a trading hypothesis. Each proposal states the baseline and the
   independent result that would justify retaining it.
2. Jev evaluates those questions on timestamped, source-identified records. Batch independent
   questions sharing the same state; keep dependent decisions in separate stages. Cache by
   source content, model version, question set and input-availability time. Record both cache
   hits and costs. One shared feature computation can serve many agents.
3. Deterministic code combines the outputs; a small statistical model may fit their weights
   using development data. Jev's probabilities are semantic features, not automatically market
   win probabilities. The strategy still prices fees, spread, execution and available capital.
4. Compare the frozen challenger with the existing system on untouched chronological/grouped
   data and then forward observations. Include all attempts in the search history. Promote a
   workflow only when it improves the relevant held-out metric and cost/latency tradeoff.
5. Feed development errors and operational outcomes back to the architect. Final evaluation
   labels do not become the next prompt's tuning set while still being called a holdout.

TypeSafe's feature-discovery cookbook demonstrates a generative proposer, Jev-derived features
and a downstream supervised model on wine descriptions. It is a useful design pattern, not
trading evidence. We would use point-in-time market inputs and chronological/grouped evaluation.
[Feature-discovery example](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery).
The API supports evaluating multiple questions against shared state, which can avoid repeated
state processing. Measure the benefit on our own workload.
[Parallel questions](https://docs.typesafe.ai/patterns/fan-out).

## What the vendor currently documents

The versioned model is `jev-1.13.0`. Published pricing is $0.042 per million input tokens and
free output. Text/JSON state goes to `POST https://api.typesafe.ai/v1/systemone`; this can be
called from our Sail-hosted orchestration through a credential-holding gateway. Pin the version
for an evaluation and record the version actually returned. The service advertises changing
early-access rate limits, so admission needs a bounded queue and fallback.
[Models and pricing](https://docs.typesafe.ai/models),
[HTTP API](https://docs.typesafe.ai/api).

For scale intuition only, 10,000 calls at 2,000 total billable input tokens each would cost
about $0.84 at that rate, before retries or other services. Actual token usage and account
billing must be measured. At today's workload, engineering time is likely a larger integration
cost than Jev inference. Cheap calls do not justify adding an unnecessary dependency.

TypeSafe documents weaknesses with numeric precision, time comparisons, indirect reasoning,
large irrelevant contexts and adversarial content; generation belongs with a generative
model. Its claim of type-safe output does not guarantee correct decisions.
[Documented model limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

The API's `confidence` for Choice/Score is derived from the returned probability distribution.
It is not independent evidence that the output is correct or that a market outcome has that
probability. Set routing thresholds from held-out task results and examine calibration before
using them operationally. [Confidence documentation](https://docs.typesafe.ai/confidence).

## First live development probe

Twelve frozen claim/evidence cases came from inspected project failures: missing input
coverage, a passing replay being called a live edge, an unimplemented tool, registry paths,
test isolation, timing allegations, deployment, budget renewal, request recovery, fills,
startup grants and event identity. Only the state and rubric were sent to providers; labels
were frozen first and scored locally. Three workers bounded concurrency.

| Route | Agreement with 12 frozen labels | Median / range elapsed | Estimated model cost |
|---|---:|---:|---:|
| Jev 1.13.0 | 9/12 | 0.416 s / 0.352–0.522 s | $0.000241 |
| Luna, low effort, 1,500 output-token cap | 11/12 | 1.871 s / 1.206–3.799 s | $0.001124 |

Elapsed time includes the gateway and network. Cost uses Jev usage and the gateway's
conservative Luna tariff; it excludes hosting and is not an invoice. Three early Luna headers
rounded to cents; the figure above reconstructs their microdollar estimates from preserved
usage. The resulting precision bug and operational reconciliation are in the
[foundation report](../runs/2026-09-20-foundation-progress.md).

Jev was about 4.5 times faster by median and 4.7 times cheaper on this probe. This small,
curated development set is not a held-out benchmark. Label boundaries also matter: the fill
and timing cases deliberately distinguish unconfirmed evidence from a definite negation.
Jev confused those distinctions and misread the registry-path case. Luna treated the
not-yet-deployed case as insufficient rather than contradicted. Jev gave high confidence to
some disagreements, so a high-confidence cutoff alone cannot certify correctness.

Keep this original result when improving the rubric. Do not retune on these cases and present
the subsequent score as independent validation. Full sanitized inputs, labels, responses,
usage and timings are in the [probe artifact](../runs/data/2026-09-20-typesafe-probe.json).
Packet SHA-256: `7621de1f897827b60400fe0776a4ba929e8b478b78c05ec5d2645bf0f1905058`.

## Next evaluation and acceptance

1. Build 50–100 additional research/tool/CI and event-relevance cases. Label outcomes using the actual
   capability snapshot, reproduction and accepted repair, not another model's confidence.
   Use only information available at the original decision time as inputs; later outcomes
   supply labels. Group related requests together so near-duplicates cannot cross the split.
2. Compare deterministic routing, Luna, the existing Sail route and Jev on the same held-out
   cases. Use a development partition to write criteria and thresholds, then freeze them.
   Include explicit insufficient-evidence/none-of-these outcomes and conflicting source text.
3. Measure wrong routes, useful coverage at each abstention rate, relevant-evidence retrieval,
   p50/p95 latency, total API/hosting cost and downstream repair completion. Calibration
   should use observed labels, not agreement with an expensive model alone.
4. Run Jev in shadow first. It earns a production route if it preserves or improves routing
   quality and materially reduces end-to-end cost or elapsed time. Small samples justify
   another test, not broad claims about reliability or trading performance.
5. Use the installed $10 Jev envelope; the first Luna comparison has its own $2 cumulative
   reservation ceiling inside foundation-review. Both are within the existing phase, not new
   capital. Later provider comparisons come from the $250 challenger allocation in the
   overall $10,000 plan. Judge spend by downstream benefit, not request count.

At 2,000 total billable input tokens per request, 100,000 requests would cost approximately
$8.40 at the published rate. Larger inputs cost more; the dollar ceiling can bind before the
call ceiling. The $10 lane is enough for meaningful throughput experiments without depositing
hundreds of dollars. Account access worked in the live probe; no additional setup is needed now.

The $10 is backed by two retained commitments ($1 plus a $9 expansion) in foundation-review.
The existing allocation is internally named OpenAI; this is a cross-provider earmark, not an
OpenAI invoice or extra phase money. The gateway reports actual Jev usage separately. Keep the
entire backing reservation until the route closes/expires and billing is reconciled; releasing
it while Jev can still spend would double-allocate the money. The phase cap and expiry are unchanged.

## Credential and integration placement

The owner has stored the key as the private Worker secret `TYPE_SAFE_TOKEN`,
outside the repository and agent sandboxes. Do not paste it into the chat. Production placement
is the protected gateway/resource broker. The installed route pins the endpoint and model,
limits state/question size, atomically reserves money, validates typed answers and records
request identities before forwarding. Repeated identities return 409, including after restart;
ambiguous calls retain their full reservation. No automatic SDK retries are enabled. The route
currently accepts choice and noul; score is not implemented. See the
[gateway contract](../../gateway/README.md#jev-shadow-pilot).

Jev can become a useful low-cost component of the autonomous architect's tools. It does not
remove the need for the durable repair loop, external spending enforcement, independent
evaluation or a real trading edge described in [the architect handoff](2026-09-20-chief-architect-handoff.md).

# Sail in Portfolio Agent

Sail supplies inference, persistent compute, caching, and workflow traces. Our
code supplies financial evidence, memory, orchestration, measurement, and the
public record. [Current results](CURRENT-STATE.md) distinguish working components
from experiments and future integration.

| Product | Applied use | What it does not establish |
|---|---|---|
| Inference + completion windows | Research, independent critique, candidate methods, and paired evaluations | Model agreement is not factual verification |
| Supercache | One shared issuer-evidence corpus, followed by separate company questions | Cheap reads alone do not recover the write cost |
| Sailboxes | Isolated source-reading and calculation tools with disk receipts across sleep/resume | The full controller is not yet hosted there |
| Voyages | Correlated inference/tool stages and durable workflow identities | A trace is not proof that a financial conclusion is correct |

## Latest applied run

The [nine-company campaign](NIGHT-SHIFT.md) completed 80 requests across DeepSeek V4 Pro, Kimi K2.6 and Kimi K3. Pro and Kimi built independent cases; a critic challenged them; revisions faced mechanical checks and anonymous paired judges. The run cost an estimated **$1.859159992** in inference.

- **Supercache:** nine new questions reused 129,024 tokens from the existing corpus. These calls cost $0.10770169; repricing the same usage with ordinary cached input gives $0.11931385. That $0.01161216 difference is a counterfactual, not an observed alternate run or recovery of the earlier write cost.
- **Sailbox:** the frozen verifier checked all nine cases, matched local results, slept and resumed with its receipts intact. Finalized compute was $0.005157369. The full controller remains local.
- **Voyages:** one recorded workflow ties together the dependent requests and stages. Private trace links and drafts stay off the website.

The benefit is inspectable disagreement and reusable execution, not proof that adding models improves accuracy. Eight final cases passed mechanical checks; one did not. Model judges preferred a failing NVIDIA revision. The public measurements (`experiments/public/overnight-sail-metrics.json`) preserve that distinction.

A separate presentation review used Kimi K3 to check the nine cash bridges against source excerpts. It found no numerical mismatch in those excerpts and flagged four presentation risks: combined capital deductions, annual and trailing-year period lengths, and Constellation’s acquisition scope. The page now shows period lengths, labels deductions explicitly and surfaces the Calpine scope change. An earlier Pro attempt exhausted its output limit without a usable review; both calls remain in the private ledger. Model review supplemented source-table and arithmetic checks rather than replacing them.

## What to test next

Use fresh disclosures to test whether remembered evidence and explicit opposing checks catch changes a first-pass analyst misses. Measure source correctness, missed changes, cost and time on held-out tasks. Expand the task set before trying prompt promotion or model training; more requests alone are not progress.

## Inference and completion windows

Each request freezes its model, reasoning setting, completion window, evidence,
and dated prices before submission. Known response IDs survive local restarts.
Pro Flex handles bounded research; Kimi K3 has served as an independent critic.
The shared-corpus trial uses Kimi K2.6 Flex. Different windows are measured as
latency/cost choices, not assumed to improve financial accuracy.
[Sail pricing](https://docs.sailresearch.com/pricing)

Completed work now releases unused conservative holds through an immutable
[settlement receipt](BUDGET.md). Uncertain requests retain their full allowance.
All new research and evaluation share the original $96 inference ceiling;
compute has a separate $4 envelope. These controls do not limit unrelated account
usage, and token estimates are not reconciled invoices.

## Shared context and Supercache

The [shared-context experiment](SHARED-RESEARCH-CONTEXT.md) freezes a 53,234-byte
prefix: profiles and selected issuer passages covering nine public AI-stack
companies. One explicit write precedes nine distinct company questions. Every
read preserves the exact prefix; no replacement write is allowed.

All nine questions completed with 14,336 Supercache tokens each. The initial
generation hit its output limit; a recorded continuation allowed read attempts,
and their counters verified reuse. Total estimated expense was $0.58887954,
including $0.51841595 for the original write request. The failed generation
remains in the record.

The request ledger records ordinary cached input, Supercache reads, and written
tokens separately. The documented write charge is 100 times normal input; reads
cost one tenth of ordinary cached input. The experiment measures these actual
counters and the total cost. Its alternative-cache comparisons reprice observed
usage; they are not measured alternate runs.
[Supercache documentation](https://docs.sailresearch.com/supercache)

At Kimi K2.6 Flex rates, a fixed prefix needs 385 subsequent Supercache reads to
match a comparison with one ordinary miss followed by ordinary hits, assuming
identical outputs. Nine reads are a product experiment, not a break-even claim.
The earlier Pro Flex model has a different threshold: 3,300 subsequent reads.
The full daily lifetime has not been tested.

## Sailboxes: tools that survive interruption

The [live worker trial](CLOUD-WORKER.md) verified six remote source/calculation
operations, sleep, fresh-process resume, and matching deterministic receipts.
Sail reported $0.00504778 finalized compute cost after termination. The final
report failed its original JSON-format contract and remains withheld.

The VM received frozen public code and evidence only. The MacBook retained keys,
inference transport, and the authoritative request ledger. Network egress and
listeners were disabled and checked before work. Earlier isolated trials used
synthetic recovery state; their $0.010 combined cost remains separately recorded.
[Persistent compute](https://docs.sailresearch.com/sailboxes) ·
[Sleep semantics](https://docs.sailresearch.com/sailboxes-autosleep)

## Voyages: trace the work that actually ran

The tracing adapter saves a workflow identity and attaches to it after restart.
It correlates each existing Responses request with its Voyage, agent, and span;
fixed, allowlisted events record stages and counters. A controller marks a trace
complete only when the logical workflow finishes, and fails rejected workflows.
An uncertain trace creation is preserved instead of blindly duplicated.
[Raw-client correlation](https://docs.sailresearch.com/voyages-sdk-inference)

Custom telemetry omits credentials, full sources, tool arguments, private prompts,
and exception text. Inference content still goes to Sail for its intended
processing and can appear in its inference dashboard. The public website receives
selected saved measurements, not private trace links or raw model drafts.

Python SDK: `sail==0.11.4`. API shapes are validated against observed readback;
older SDK field names are not assumed equivalent without verification.
[Historical integration detail](../SAIL-PRODUCTS-2026-09-12.md)

## Later: change model weights

The current improvement experiment selects prompts. It does not train a model.
Sail also serves [LoRA adapters](https://docs.sailresearch.com/loras) and supports
[Tinker training rollouts](https://docs.sailresearch.com/tinker-rl): Tinker owns
optimization while Sail generates samples. Neither has been used here. A useful
next prerequisite is a much larger, checked financial-evidence task set with
separate validation; sixteen synthetic cases are not a training program.

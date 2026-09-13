# First thesis: development results

September 12, 2026. Read [Lesson 2](02-thesis-with-memory.md) and make your own prediction first.

Five paid attempts produced two locally valid drafts and one reviewed publication. The published draft observes that company-wide operating cash flow grew, but cash PP&E spending increased by more. It keeps a watch stance because those totals cannot isolate AI-specific returns. The original [evidence packet](../../../experiments/data/thesis/msft-ai-infrastructure.json) contains the dated facts and sources.

## What happened

| Attempt | Model / window | Output ceiling | Provider outcome | Local outcome | Estimated USD |
|---|---|---:|---|---|---:|
| 1 | GLM-5.3 / Balanced | 4,096 | Incomplete | Repetitive output; no draft | 0.01075650 |
| 2 | GLM-5.3 / Balanced | 8,192 | Completed | Rejected: numerical prose; summary also ended mid-sentence | 0.00210318 |
| 3 | DeepSeek V4 Pro / Flex | 8,192 | Incomplete | Repetitive output; no draft | 0.01703262 |
| 4 | DeepSeek V4 Pro / Flex | 16,384 | Completed | Locally valid; withheld after source review | 0.00447348 |
| 5 | DeepSeek V4 Pro / Flex | 16,384 | Completed | Locally valid; reviewed for publication | 0.00708048 |
| **Total** | | | | **One accepted thesis** | **0.04144626** |

The first three requests used constrained JSON-schema output. The fourth and fifth asked for a JSON document through ordinary text output, with the same required local validation before a draft could exist. The fourth passed structural checks, but review caught an AI attribution overclaim and an overly broad description of finance leases. Our prompt contributed to that wording. We corrected it and generated a fresh draft; the earlier revision remains private and unreviewed. The original requests, responses, evidence packets, configurations, and dated rates remain in the private run ledger.

These were debugging iterations: prompts, format, model, reasoning effort, and token limits changed. This does **not** establish a model ranking or prove which change caused the improvement. There is one accepted result, not a benchmark. A controlled next experiment should change one variable at a time on the same evidence and measure source support as well as cost.

## Reproduce the accepted run's cost

The fifth run reported 1,506 input tokens, no cached input, and 3,074 output tokens. Its 2,698 reasoning tokens are included within output, not added again. The request used `deepseek-ai/DeepSeek-V4-Pro-0813`, Flex, and medium reasoning.

At the [September 12 listed rates](https://docs.sailresearch.com/pricing):

`(1,506 × $0.66 + 3,074 × $1.98) / 1,000,000 = $0.00708048`

The accepted call itself cost less than one cent at list prices. Development cost per accepted thesis was about 4.14 cents because the unpublished attempts also count. Neither amount is a reconciled provider bill. The local ledger permanently reserved $1.00 across the five attempts; that allowance is not an additional charge.

## What to check yourself

Find the first published entry in the [research ledger](https://blakewoods.us/portfolio/). Open one financial fact and follow its source. Then open the reasoning and find a conclusion that the evidence cannot establish. Explain why a provider-completed response, a locally valid draft, and a reviewed publication are three separate states.

The initial review is labeled **AI Builder**. It records a source check performed during implementation, not an independent human investment review. You can inspect and challenge it before we expand the agent's scope. There is no brokerage connection, position, or performance result behind this thesis.

# Completion-window and prefix-reuse pilot

This protocol tests a practical routing question: what happens when the same
research task runs through Balanced or Flex, and when its exact prompt is reused?
The replacement freezes twelve intended Kimi-K2.6 tasks before execution, with
**$2.40** in reservations. Together with the rejected pilot's retained $0.20,
that fits the original sixteen-admission / $3.20 cap. No Supercache writes are
enabled.

The implementation is [policy_experiment.py](../../../experiments/policy_experiment.py). This is a
counterbalanced engineering pilot, not an independent accuracy benchmark or a
general latency ranking.

## Preserved compatibility finding

The original protocol planned sixteen Pro0813 tasks comparing ASAP and Flex with
background mode enabled on both. Its first ASAP request was rejected with HTTP
400. The provider reported that a requested feature could not be used with ASAP
and required a supported non-ASAP window. It did not identify the feature.
Background mode is a plausible explanation, not an established cause; this also
does not show that the model itself lacks ASAP support.

Five submission attempts used the same original request and idempotency key.
There was no provider response ID or completed output. An append-only operator
closure stops further attempts; it does not fabricate a provider terminal result
or modify the immutable protocol. The original charge remains unknown and its
$0.20 hold remains reserved. Fifteen unadmitted tasks are explicitly reported as
not run. See the [archived rejected pilot](../../../experiments/public/experiments/rejected-asap/policy-experiment.json).

The replacement has a distinct protocol version, model and frozen rate card.
It does not use a modified request under the original task key or present the
failed configuration as a successful comparison.

## Fixed design

Three existing financial-evidence questions cover a cash-flow calculation, an
unsupported lease-accounting implication, and missing AI-return evidence.
They were selected after the initial evaluation to exercise
useful distinctions; they are not a hidden holdout. The same deterministic grader
is used, with its source hash frozen alongside cases, prompts, rate cards and
the evidence packet.

Each question has four tasks: Balanced first-use, its exact repeat, Flex first-use,
and its exact repeat. Two blocks put Balanced first and one puts Flex first.
This three-block order is intentionally reported as imbalanced. All tasks
execute sequentially. A repeat cannot be admitted until its first-use task is
terminal. A failed or malformed output remains in the record; a scheduled repeat
is never substituted for it.

The replacement model is `moonshotai/Kimi-K2.6` throughout, with medium reasoning,
`background: true`, text output and a 16,384 output-token ceiling. Requests are
limited to 48,000 serialized bytes. These settings match across windows. Flex
requires background responses; the probe explicitly requests the window on both
arms rather than relying on defaults. [Completion-window documentation](https://docs.sailresearch.com/completion-windows)

The shared evidence library precedes each question. Only the evidence IDs named
by that question are eligible; expected labels and grading notes are excluded
from the prompt. Each window arm receives a distinct 64-character opaque marker
near the start of its prefix and a matching `prompt_cache_key`. This limits
cross-arm prefix reuse. It does not establish a cold cache, and marker tokenization
can differ slightly. Input-token counts remain measured rather than assumed.
Within an arm, the first-use and repeat request bodies are **identical**, including
the marker and routing hint. They have separate intended task keys. The routing
hint can be overridden by available capacity; a repeat does not guarantee a hit.
[Prompt-cache routing](https://docs.sailresearch.com/support#prompt-cache-routing)

## Price contract and spending bound

Rates checked September 12, 2026, in USD per million tokens:

| Window | Input | Ordinary cached input | Output |
| --- | ---: | ---: | ---: |
| Balanced | $0.45 | $0.20 | $3.00 |
| Flex | $0.35 | $0.10 | $2.00 |

Source: [Sail pricing](https://docs.sailresearch.com/pricing).

Each task reserves $0.20. A conservative byte-based uncached estimate at the
higher Balanced rates is `(48,000 × 0.45 + 16,384 × 3.00) / 1,000,000 = $0.070752`.
The reservation leaves additional room for request formatting. Twelve new tasks
reserve $2.40; existing reservations remain intact, and the global ledger cap
still applies. The dedicated policy admission cap counts orphan and outside
policy reservations too. No new budget database is created.

For every completed response, the export shows actual estimated cost and the
cost of **that same observed token usage** under both rate cards. This holds token
counts and cache usage fixed for the repricing calculation. It separates the
documented price difference from different output lengths and hit rates; it is
not evidence that different calls produce identical outputs. Supercache response
counters are respected even though no write is requested. Unknown or malformed
usage retains its allowance rather than becoming zero-cost work.

The separate [cache economics calculation](SAIL-PRODUCTS.md#cache-economics-before-enabling-another-product)
explains why a Supercache write is not justified by demonstrated daily reuse.

## Timing and interpretation

Preflight occurs before timed execution. Each task records monotonic elapsed time
from its first attempted submission to its first observed terminal response.
The controller polls on the same two-second cadence for both windows. This is
client-observed completion time, including queueing, network and polling—not
provider execution time or time to first token.

Unconfirmed submissions, retrieval errors, process interruptions and detected
wall-clock discontinuities exclude a task from timing comparisons. Cross-window
pairs must also come from the same controller, return format-valid completed outputs,
have no Supercache reads and have cache-hit fractions within two percentage
points. These rules are fixed before execution. Every sample, exclusion, error
and cache count remains in the export. Format validity does not require the
verdict to pass the separate semantic grader.

That filter is descriptive, not a causal adjustment: cache behavior can itself
depend on scheduling. Shared capacity, cache residency and time-of-day load are
not fully controlled. Three imbalanced blocks cannot establish a universal speed advantage.
The useful result is a visible set of matched observations, uncertainty, and
cost arithmetic to guide the next experiment.

## Session procedure and recovery

These commands document the completed September 12–13 pilot and its single
permitted replacement. That replacement has already run. New admissions also
stop at September 13, 05:10 UTC; a later deadline argument cannot extend the
window. The [saved results](../../../experiments/public/policy-experiment.json) and offline tests
remain available without paid requests. A future comparison needs a new bounded
protocol that preserves both existing attempts and their spending history.

Creation is local. A replacement is allowed only after the original v1 protocol
has an explicit closure, and only if prior admissions plus the new tasks fit the
original global cap. Only one replacement is allowed:

```bash
python3 policy_experiment.py create --version v2
python3 policy_experiment.py status EXPERIMENT_ID
```

After reviewing the frozen protocol, run with private Voyage attribution:

```bash
.venv/bin/python policy_experiment.py --voyage run EXPERIMENT_ID --seconds 900
python3 policy_experiment.py export EXPERIMENT_ID public/policy-experiment.json
python3 -m unittest tests.test_policy_experiment tests.test_research_tasks
```

Resume the same experiment ID. Known provider responses use GET; an ambiguous
submission keeps its original request, reservation and idempotency key. A local
timeout does not cancel accepted work. Frozen deadlines are not silently
extended. Publication uses only an explicit metrics allowlist, and exports must
be named `policy-experiment.json` to avoid replacing another public artifact.

## Observed results — September 13, 2026 UTC

The [finished replacement export](../../../experiments/public/policy-experiment.json) contains all
twelve distinct completed provider responses, observed from 00:11:01 to 00:19:29
UTC by one uninterrupted controller. Voyage delivery was confirmed. There were
189 controller attempts, including GET polling; these were twelve intended tasks,
not 189 new inference requests. Estimated inference cost was **$0.053526**, against
$2.40 reserved. The separate rejected v1 still has unknown cost and its $0.20
hold; the replacement's measured cost does not settle that earlier attempt.

| Window / phase | Strict passes | Input tokens | Ordinary cached tokens | Output tokens | Estimated cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Balanced / first use | 3/3 | 3,776 | 16 | 4,099 | $0.01399220 |
| Balanced / repeat | 1/3 | 3,776 | 3,773 | 5,201 | $0.01635895 |
| Flex / first use | 2/3 | 3,768 | 22 | 4,240 | $0.00979330 |
| Flex / repeat | 3/3 | 3,768 | 3,765 | 6,502 | $0.01338155 |
| Total | **9/12** | **15,088** | **7,576** | **20,042** | **$0.05352600** |

All three failures remain in the official results:

- Balanced cash-proxy repeat wrapped its JSON in Markdown fences. A diagnostic
  fence-only removal passes, but the recorded strict-format failure is unchanged.
- Flex missing-AI-return first use also used fences. A diagnostic parse additionally
  reveals `unsupported` where the fixture requires `insufficient`.
- Balanced missing-AI-return repeat returned valid JSON but the same incorrect
  `unsupported` label. Both explanations recognized that the supplied company-wide
  numbers did not establish AI-specific ROIC; they missed the required distinction
  between missing evidence and contradiction.

Ten outputs are format-valid; nine pass every grading condition. This small pilot
does not establish a quality advantage for either window, and a repeated prompt
does not promise identical output.

Ordinary cached input increased from **0.50%** on first use to **99.92%** on exact
repeats, weighted by input tokens. All Supercache read/write counters were zero.
For the same observed token counts, ordinary caching saved **$0.001894** compared
with billing all input as uncached. Output tokens still accounted for **92.3%** of
estimated cost. Repeats generated more output in aggregate and cost more despite
their cached prefixes; this is why a cache hit alone is not a total-cost forecast.

Repricing **all twelve responses' fixed usage** at Balanced yields **$0.06502160**;
the same usage at Flex yields **$0.04347080**, a **33.14%** reduction. This is
rate-card arithmetic, not a claim that rerunning all tasks on Flex would reproduce
these tokens, verdicts or cache hits.

Four of six cross-window pairs satisfy the predeclared timing filter. Their
Flex-minus-Balanced client durations were **−2.36, +2.69, +5.39 and +20.01 seconds**.
The two fenced-output pairs were excluded. The last admitted pair contains the
format-valid but semantically incorrect Balanced verdict; the filter checks
format, not a full grading pass. No filter was changed after observing results.
Output lengths also differ, so these observations cannot isolate scheduler or
generation speed. Every response exposes `created_at`; none exposes
`completed_at`. The recorded durations therefore remain client observations,
including queueing, network and polling, rather than provider execution times.

The practical lessons are to budget output as well as input, validate machine
output before acting, and measure cache reuse instead of assuming it. A larger
task set and a checked structured-output contract would be more useful next than
a Supercache write for a prefix reused only once. Under the earlier ordinary-cache
baseline, the documented Kimi rates require **248** subsequent reads at Balanced
or **386** at Flex within 24 hours for a Supercache write to become cheaper; that
is far beyond this pilot's reuse. These thresholds are calculations from the
[published rates](https://docs.sailresearch.com/pricing) and
[Supercache multipliers](https://docs.sailresearch.com/supercache), not a measured
Supercache experiment.

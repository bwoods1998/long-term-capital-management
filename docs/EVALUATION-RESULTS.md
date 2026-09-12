# Evidence-critic development evaluation

These experiments ask whether models preserve accounting scope, distinguish an
unsupported inference from an unknown fact, and cite only evidence available at
the specified date. They test a small authored regression suite, not investment
skill or the reliability of an unconstrained research agent.

The machine-readable record is [research-evaluation.json](../public/research-evaluation.json).
It preserves every scheduled case, including failures and unfinished responses.
The [sixteen fixtures](../data/evals/research-cases.json) and prompts were frozen
before each campaign. Expected answers and grading notes were excluded from
model requests.

## Design

The model comparison schedules two repetitions of all sixteen cases for DeepSeek
V4 Pro, Kimi K3, and DeepSeek V4 Flash: 96 calls. A separate paired experiment
schedules one Pro answer and one Kimi review for every case: 32 more calls.
The reviewer sees the initial answer and the same evidence; it reviews every
case, including initially correct answers. This avoids buying a second attempt
only after seeing the answer key. The paired experiment is distinct from the
three-model comparison, so its fresh Pro answers are not replacement samples.

Pro uses Sail Flex with background responses; Kimi and Flash use ASAP. Results
therefore describe these model-and-service configurations. They do not isolate
the effect of the service tier from model choice. All requests use the same
shared budget ledger, with stable task and idempotency keys across interruptions.
The two campaigns have separate resumable Sail Voyages.

The case set contains six supported claims, seven unsupported claims, and three
claims requiring abstention. Strict passing requires valid JSON, the expected
verdict, known citations, publication-date eligibility, and coverage of the
fixture's required evidence groups. Citation existence is not enough. The
deterministic grader does not independently establish the semantic truth of every
sentence in a model's explanation.

## Model comparison result

All 96 scheduled tasks completed on September 12, 2026. No completed answer was
replaced and no fixture or expected verdict was changed after seeing the outputs.

| Configuration | Strict passes | Abstentions correct | Estimated inference cost | Cached input tokens |
| --- | ---: | ---: | ---: | ---: |
| DeepSeek V4 Pro 0813, Flex | 32/32 | 6/6 | $0.025353988 | 9,544 |
| Kimi K3, ASAP | 32/32 | 6/6 | $0.153837 | 0 |
| DeepSeek V4 Flash 0731, ASAP | 31/32 | 5/6 | $0.00407376 | 0 |

The comparison cost **$0.183264748** in estimated inference usage. All outputs
passed format, citation-membership, publication-cutoff, and required-evidence
checks. There was one incorrect verdict:

| Case | Model / repetition | Expected | Returned |
| --- | --- | --- | --- |
| `insufficient-ai-return` | Flash / first | `insufficient` | `unsupported` |

The claim concerned an AI-only incremental return on invested capital that the
supplied company-wide figures did not measure. Flash's explanation identified
that missing evidence, but its machine-readable verdict rejected the claim
instead of abstaining. Under the frozen contract, evidence that cannot determine
whether an underlying proposition is true requires `insufficient`. This differs
from rejecting a claim that the packet itself *proves* a proposition. The error
was retained even though the explanation recognized much of the distinction.
The second repetition answered the same case correctly. One error is a useful
regression example, not an estimate of Flash's general financial error rate.

## Paired reviewer result

All 32 calls completed. Pro passed 16/16 cases; Kimi's subsequent review also
passed 16/16. The reviewer corrected zero cases and introduced zero measured
errors. There was **no measured quality improvement** on this suite.

| Condition | Strict passes | Estimated inference cost | Cached input tokens |
| --- | ---: | ---: | ---: |
| Pro baseline, Flex | 16/16 | $0.008506828 | 9,544 |
| Additional Kimi reviewer, ASAP | 16/16 | $0.071598 | 0 |
| Whole paired workflow | 32/32 model outputs | $0.080104828 | 9,544 |

This is useful evidence against assuming a more expensive reviewer always helps.
The suite has a ceiling effect for these configurations. The result supports
testing harder, independently authored cases before deciding when an extra
review is worthwhile; it does not establish that review is unnecessary for
open-ended research.

## Complete run accounting

The 128 scheduled tasks produced 128 distinct completed provider responses,
with **$0.263369576** total estimated inference usage: 85,155 input tokens
(including 19,088 reported cached tokens) and 34,322 output tokens. No evaluation
cost remains unknown in the local ledger. The cumulative evaluation reservation
is $60.80; that is a conservative spending allowance, not the bill.

The controller recorded 182 execution attempts for these 128 stable tasks.
Attempts include retrieving accepted Flex responses and resubmitting unconfirmed
requests with their existing idempotency keys. Four Flash tasks needed more than
one submission attempt; three resolved on their second attempt, and one on its
fourth. There are no replacement task keys or discarded completed answers.
This is a demonstrated interruption-and-reconciliation path rather than an
uninterrupted service-latency benchmark.

Both campaign Voyages are marked complete and their final event flushes were
confirmed by the SDK. This verifies the local telemetry delivery path; it does
not imply that every dashboard aggregate was independently reconciled with an
invoice. Public results omit the private trace identifiers.

## Measurement boundaries

Costs are estimates from returned input, cached-input, and output token usage and
the request's frozen rate card. They are not itemized provider invoices. Budget
reservations cover maximum permitted usage and remain distinct from estimated
spending. A queued response's zero token counters are not treated as a completed
zero-cost call. Failed or unconfirmed calls stay in the record and retain their
reservations until reconciled.

Reported cached tokens demonstrate that some input was served from Sail's cache.
These experiments reuse shared instructions and repeated case inputs; they do
not hold cache state, model, load, and timing constant. The cache counts therefore
do not establish a causal speedup or justify attributing a specific comparison
outcome to caching. Usage reports do let us price cached and uncached input
separately.

All 128 provider responses expose a creation timestamp; none exposes a completion
timestamp. Local observation durations include queueing, polling cadence, and an
operator-requested pause. They are not provider execution latency or time to
first token, so this report makes no model-speed ranking. A future latency
experiment needs continuous observation and explicit timing boundaries.

Two repetitions from one company and closely related supplied excerpts are too
small and correlated to support general accuracy claims or a universal model
ranking. Prompts explicitly teach several distinctions measured by the cases;
this is a development regression set, not a hidden holdout. No return, trade, or
investment decision was evaluated.

## Reproduce the report

Status and export reconcile the existing local ledger without provider calls:

```bash
python3 evaluation_campaign.py status 88228d0c-275c-44a8-bd3c-d8fb7f4d1110
python3 evaluation_campaign.py status 53e5e9bb-89d6-4b86-90c0-8cd614992c99
python3 evaluation_campaign.py export-all public/research-evaluation.json \
  88228d0c-275c-44a8-bd3c-d8fb7f4d1110 \
  53e5e9bb-89d6-4b86-90c0-8cd614992c99
python3 -m unittest tests.test_evaluation_campaign tests.test_research_eval
```

The committed public JSON can be read without credentials or the private ledger.
Raw provider responses, internal response IDs, credentials, and private Voyage
handles are not exported.

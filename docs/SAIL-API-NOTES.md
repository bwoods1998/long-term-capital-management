# Sail API review

## September 12, 2026 update

Portfolio Agent V1 adds a checked evidence packet, reviewed memory, and a public export; see [V1](V1.md). Its first reviewed thesis uses DeepSeek V4 Pro, Flex, medium reasoning, and ordinary text output with an explicit JSON contract and strict local validation. Initial constrained-output attempts exposed incomplete responses and local validation failures. A structurally valid draft also failed substantive review; all attempts count toward cost. See the [development results](../lessons/02-result.md), or run `python3 portfolio.py preview` for the current request.

Current documentation says ASAP-only models reject background requests. The legacy DeepSeek extraction now uses foreground ASAP; the September 7 result remains a historical observation. Models and rates have also changed. Check the [catalog](https://docs.sailresearch.com/models), [pricing](https://docs.sailresearch.com/pricing), and [completion windows](https://docs.sailresearch.com/completion-windows) before changing configuration. The notes below preserve the September 7 review, not a claim that every contract remains current.

## September 7, 2026 review

## Review scope

Downloaded all 117 pages and both specifications listed in Sail's documentation index, plus the linked idempotency guide (120 sources). The source manifest records URLs, sizes, and SHA-256 hashes; original files are in ignored `.data/sail-docs/2026-09-07/`.

Read the core inference support matrix, scheduling, retries, rate limits, usage accounting, agent loop, webhooks, and relevant sandbox billing/lifecycle documentation. Examined the inference specification and the sandbox endpoint/field contracts. The generated Python/TypeScript/Rust SDK references and advanced training integrations are archived for implementation-time consultation; this is not a claim that every SDK example has been read line by line or that every endpoint has been tested. Documentation and runtime behavior must still be checked against one another.

## V1 decisions

- Local Python and SQLite, with inference through Sail. No Sailboxes, paid search, fine-tuning, or agent framework needed initially.
- Start with `deepseek-ai/DeepSeek-V4-Flash-0731`, explicitly using `asap`, after checking the account's model catalog.
- Use `POST /v1/responses`, with structured `text.format.type=json_schema`. JSON shape is not proof of financial correctness: validate values, units, periods, and evidence against reference answers.
- Download and extract public filing text locally. File/document input and hosted file-search tools are not available through this inference interface. Web-search tool declarations can be silently removed for compatibility, so do not assume they performed research.
- Begin with one request, then a bounded evaluation set. Reserve a conservative per-request allowance before submission; the initial experiment budget is $1 of the user's $5 credit. The v1 runner now holds a permanent one-cent allowance per logical trial in SQLite, with atomic reservations against $1; this is a local control, not a provider-enforced account cap.
- Use a fresh persisted UUID per intended trial and reuse it only for retries of that same trial. Persist the response ID and resume polling rather than resubmitting.
- Keep pricing estimates and provider-reported spending separate; reconcile them after billing catches up.

## Inference and reliability

Base URL: `https://api.sailresearch.com/v1`. Authenticate with a Bearer key.

The Responses interface supports background execution and structured outputs. `background=true` returns HTTP 202; retrieve by ID. Stop polling on completed, incomplete, failed, or cancelled. An incomplete response can contain billed usage and partial output. The normalized max_output_tokens reason can also reflect a context limit, so it does not necessarily mean only the requested output cap was reached.

Flex requires background Responses or Batch. It has no time-to-first-token or tokens-per-second target. A client timeout does not cancel accepted work; Responses delete/cancel endpoints are not implemented. No unlimited retry loops.

Idempotency is scoped to organization, API key, and request key, retained for 24 hours. Changing credentials changes the reservation scope. Changed request bodies can cause an idempotency error. The Sail inference SDK does not attach keys automatically. Do not retry old uncertain submissions after the retention window without reconciliation.

Rate limits are input-token based per organization/model with global model limits. Respect Retry-After for 429/529 and temporary 503 capacity failures. A prompt exceeding the entire token allowance cannot be fixed by waiting. Batch has separate behavior and supports Responses items only.

There is no server-side conversation chaining. An agent sends the full history each turn and executes its own tools. Longer histories create recurring input cost. Streaming differs between interfaces: Messages SSE is emitted after generation and cannot be treated as incremental token timing.

Sources: [support](https://docs.sailresearch.com/support), [idempotency](https://docs.sailresearch.com/idempotency), [completion windows](https://docs.sailresearch.com/completion-windows), [limits](https://docs.sailresearch.com/rate-limits), [agents](https://docs.sailresearch.com/agents), [webhooks](https://docs.sailresearch.com/webhooks).

## Accounting and experiment design

The v2 Usage API monetary amounts are fractional **cents**, while sandbox spend endpoints report USD **nanodollars**. Normalize units explicitly with decimal arithmetic. A displayed balance of 500 cents is $5, not $500.

Billing metrics can lag operational metrics. Missing or unavailable balances must not be treated as zero spend or unlimited credit. Unknown range parameters can silently fall back to defaults. Balanced usage can appear under the legacy label standard.

Cached input is a subset of input. Do not add it again when counting total tokens. Separate uncached input, cached input, output, and any applicable surcharge. Keep reasoning-token counters without assuming the visible response text accounts for all usage.

Regular prefix caching is implicit. Supercache is different: 24-hour prefix reuse, a write priced at 100 times normal input, and reads at 10% of regular cached-input price. It is unsuitable as a default for a tiny experiment. Repeated evaluation prompts can warm caches; record cached tokens and distinguish first-run versus repeated-run costs.

Sources: [usage](https://docs.sailresearch.com/usage), [accounting reference](https://docs.sailresearch.com/usage-endpoints), [pricing](https://docs.sailresearch.com/pricing), [Supercache](https://docs.sailresearch.com/supercache).

## Later learning opportunities

Sailboxes are persistent Linux VMs, separate from model inference. Usage charges reflect observed CPU, RAM, and disk while running, plus a creation fee. Sleeping and paused time is not billed. Periodic polling/timers can keep a machine awake; a wake can also be a cold start, so durable state still matters.

This creates a useful experiment: compare the full cost of an agent waiting on inference with different scheduling and sleep policies. Distinguish our costs as a Sail customer from modeled provider infrastructure economics.

Voyages record agent traces, steps, model calls, and execution. They do not plan tasks or replace the agent loop, and the docs explicitly advise against adding one for a single inference call.

Sandbox retry semantics differ from inference. A sandbox create error can occur after allocation: reconcile the resource list before creating again. Network policies, port allowlists, and credential injection provide later lessons in isolation and safe execution. Credential injection still requires trusted destinations that do not reflect secrets back in responses.

Sources: [Sailboxes](https://docs.sailresearch.com/sailboxes), [billing](https://docs.sailresearch.com/sailboxes-billing), [autosleep](https://docs.sailresearch.com/sailboxes-autosleep), [HTTP API](https://docs.sailresearch.com/sailboxes-http-api), [Voyages](https://docs.sailresearch.com/voyages), [credential injection](https://docs.sailresearch.com/sailboxes-credentials).

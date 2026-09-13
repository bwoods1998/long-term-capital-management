# Sail product record — September 12, 2026

Historical checkpoint. Current integrations: [Sail products](../SAIL-PRODUCTS.md).

Checked against Sail documentation and Python SDK `sail==0.11.4` on September 12, 2026.

## Inference: bounded research steps

`portfolio.build_task_request()` builds text and client function-tool requests for four
explicit model profiles. `reserve_task()` saves each step once by stable task key,
along with its exact request, evidence, pricing and allowance. The existing transport
continues to own credential binding, idempotency and background response polling.
Raw investigations, critiques, evaluations, and replay responses remain private.
Explicitly reviewed thesis revisions and investigation reports can enter their
respective publication chains; evaluation exports contain deterministic metrics.

The budget is a cumulative reservation limit shared with earlier thesis calls. Raising
it does not erase reservations. Prices were checked against Sail's current
[inference pricing](https://docs.sailresearch.com/pricing).

## Cache economics before enabling another product

The completed 128-task evaluation reported 19,088 cached input tokens. Its
Supercache read and write counters were present and zero in every response, so
ordinary cached-input pricing applies to those results. Sail's
[routing hint](https://docs.sailresearch.com/support#prompt-cache-routing) can
improve locality but does not guarantee a hit.

[Supercache](https://docs.sailresearch.com/supercache) preserves a written prefix
for 24 hours. Its documented write price is 100 times normal input, while its
read price is one tenth of ordinary cached input. That makes the expected number
of reuses central to the decision.

For a fixed prefix of `N` million tokens, suppose the first ordinary request is
uncached, every subsequent ordinary request hits cache, all reads occur within
24 hours, and output usage is identical. Let `I` be the normal input rate, `C`
the cached rate, and `R` the number of subsequent reads:

```text
ordinary cost = N × (I + R × C)
Supercache cost = N × (100 × I + R × 0.1 × C)
break-even R = 99 × I / (0.9 × C)
```

At the current [Pro Flex rates](https://docs.sailresearch.com/pricing), `I = $0.66`
and `C = $0.022` per million tokens. Break-even is **3,300 subsequent reads**;
the next read produces a saving under these assumptions. This treats the
documented write price as the total input charge for written tokens. If the
ordinary comparison would also hit cache on the initial request, the threshold
is higher: `(100 × I − C) / (0.9 × C)`, or 3,333 whole subsequent reads. Ordinary
cache misses would lower the threshold, while unused or changing prefixes can
make the upfront write cost unrecoverable.

This workload has not demonstrated that level of reuse within a day. No
Supercache write was enabled. Before any future activation, its distinct token
counters and write charges must enter the same reservation and cost ledger.

## Voyages: a trace of the actual investigation

Install the optional dependency with `.venv/bin/python -m pip install -r requirements-sail.txt`.
Without explicit `enabled=True`, the instrumentation imports no SDK, reads no key,
creates no telemetry files and sends no events.

```python
import sail_tracking as tracking

with tracking.run(workflow_id, enabled=True) as trace:
    with tracking.stage("investigate", agent="Investigator"):
        tracking.event("model.started", {"model": model, "round": round_number})
        result = portfolio.execute(db, reserved_run_id, poll_seconds=0)
        tracking.event("model.finished", {"status": result["runs"][0]["status"]})
    # Call this only when the whole durable workflow has finished.
    if workflow_is_complete:
        trace.complete()
    dashboard_url = trace.dashboard_url
```

The module carries current Voyage, agent and span headers into each existing
Responses HTTP request, so the dashboard can associate real inference activity with
the named stage. Tool stages and numeric outcomes are recorded by explicit events.
This uses Sail's supported [raw-client correlation interface](https://docs.sailresearch.com/voyages-sdk-inference);
it does not move retries or planning into the SDK.

One trace identifier is saved under ignored `.data/voyages/` and reused through
`attach()` when a workflow resumes in another invocation. An ordinary exit while
waiting flushes current events and leaves the logical workflow running. Explicit
`complete()`/`fail()` marks the workflow terminal. An interrupted invocation records
a sanitized interruption event and leaves the durable workflow resumable. Only the
caller determines terminal workflow status. A terminal trace can be reopened for
inspection, but cannot record another stage or attribute new inference. The dashboard
URL and confirmed-delivery flag are private operational
state. A process crash between trace creation and recording its identifier leaves an
uncertain-create journal: the next invocation requires reconciliation, preventing a
blind duplicate create. An OS lock prevents two local controllers from recording the
same workflow concurrently.

We use the SDK's create/attach primitives because its standard `run()` helper creates
a new trace every time and copies exception messages into failure events. Our stage
and failure wrappers pass fixed error text instead. Event payloads accept only a small
allowlist of counters and bounded identifiers. Prompts, source text, tool arguments,
private workflow names, exception messages and credentials are not custom telemetry
payloads. Inference content is still sent to Sail for its intended processing and may
be visible through its inference dashboard. See [Voyage lifecycle and delivery
semantics](https://docs.sailresearch.com/voyages-sdk).

Tests cover the real installed SDK's offline span attribution and sanitized failures,
create/attach resume, uncertain-create handling, credential consistency, immutable
transport authentication/idempotency headers, and event delivery failure. These are
local contract tests; an actual recorded workflow and dashboard inspection are needed
to claim successful live telemetry.

At 01:04 UTC on September 13, a [read-only lifecycle reconciliation](../../experiments/data/experiments/voyage-reconciliation-2026-09-13.json)
confirmed all thirteen known Voyages on the server: ten completed and three failed,
with matching identities, workflow hashes, and local status. All known traces had
confirmed local delivery flags. The check sent only lifecycle GETs and left the
private journals unchanged. Completion describes the workflow, not the correctness
of its conclusions.

One earlier creation remains unconfirmed without a returned identifier or saved
startup diagnostic. The checked SDK and official reference provide attachment by
known ID, but no supported listing or metadata-search operation was found to
recover this identity. Its journal remains preserved; creation was not blindly
retried. This trace uncertainty is separate from inference usage and billing.

## Observed Sailbox validation — September 12, 2026

The clean-VM experiment completed. The public-safe result artifact is
[`data/experiments/sailbox-validation-2026-09-12.json`](../../experiments/data/experiments/sailbox-validation-2026-09-12.json).
The controller and guest runner are `sail_sandbox.py` and
`scripts/sandbox_validation.py`. Preparation freezes an exact file allowlist and
SHA-256 manifest; it never copies the working directory recursively.

The successful private size-S VM had one vCPU, 2 GiB memory, 8 GiB disk, no
volumes, no listeners, and an explicit no-network policy. It received application
code, public financial fixtures, and frozen public Microsoft source captures.
The controller retained credentials locally. The stock Python environment passed
86 offline tests with zero failures or errors; one optional SDK test was skipped.
It also retrieved the useful-lives passage, calculated the checked FY2026 cash-flow
proxy of USD 66,987 million, and passed sixteen authored grader-oracle fixtures.
Those oracle checks validate the grader; they are not model-quality measurements.

The controller saved a checkpoint, confirmed sleep, pause and resume, and launched
a fresh Python process. The process verified the unchanged manifest, public source
files, saved request and known response ID. It retained one research reservation,
retrieved the synthetic accepted response once, and made zero new submissions.
This is evidence that disk-backed state supports recovery without replaying a paid
step. It does not establish whether the platform wake was warm or cold, and no
live inference ran inside this VM.

The first attempt exposed an API compatibility issue: the current documentation's
`egress_policy` field did not produce any explicit policy in live readback. The
controller stopped before uploading files and terminated the VM. Dedicated policy
endpoints returned 404. The second attempt requested the same restrictive policy
through both the documented field and the installed SDK's older `network_policy`
field. Live readback explicitly confirmed `network_policy.mode == "no_network"`.
Missing policy metadata never counts as confirmation. Creation contracts and SDK
versions must be checked against the [live configuration](https://docs.sailresearch.com/api-reference/lifecycle/create-a-sailbox.md).

Both VMs were confirmed terminated. Immediately afterward, Sail reported $0.005
finalized cost for each and zero active estimated cost: $0.010 combined against a
shared $0.25 allowance. The controller also checked current returned rates before
creation, held an aggregate thirty-minute deadline, and used a separate local
watchdog for cleanup. These observations are not a provider-enforced account cap.
The [spend API](https://docs.sailresearch.com/api-reference/usage/get-sailbox-spend.md)
reports nanodollars; the inference usage API reports cents. A later read-only
reconciliation at 23:29 UTC confirmed both resources remained terminated and the
reported costs were unchanged: $0.010 combined finalized cost and zero active
estimated cost. No additional resource was created.

The checkpoint had a five-minute TTL. Its eventual expiry was not separately
observed. A longer running-versus-sleeping cost comparison remains unperformed;
this short validation supports persistence and isolation claims only. Sail's
[autosleep documentation](https://docs.sailresearch.com/sailboxes-autosleep) says
periodic timers can prevent sleep and any wake can be cold, which motivates that
separate comparison.

SDK provenance: the inspected Linux x86-64 `sail==0.11.4` PyPI wheel has SHA-256
`7f1a27c40d8b95ca8ced4430761369234379ac5a7cc3ab0ac11392743a19af52`.
The [published package](https://pypi.org/project/sail/0.11.4/) identifies
`sailresearchco/sail` as its source repository, although that repository was not
publicly accessible during this review.

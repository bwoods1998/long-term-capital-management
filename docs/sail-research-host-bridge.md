# Sail host bridge

`league.swarm.sail_research_host.build_sail_host_adapters` supplies the existing
`HostAdapters` interface with real allowlisted Sail HTTPS clients and the stock
GymDriver. This is host code. The controller receives only authenticated IPC and
the broker's permitted Train/Validation results. Importing the bridge creates no
client, reads no credential and sends no request.

The operator's owner-private, independently hash-reviewed adapter file implements
`build_host_adapters(config)`. It calls the bridge with an explicit credential
callable and `SailBridgeInputs`. There is no environment/default-key fallback.
Receipt resolvers must return independently approved `ReviewedFile` objects;
they must not calculate approval hashes from the unreviewed bytes they just read.
Context returns `HostContextEvidence`. All receipt paths remain outside the
controller artifact/state mounts. The loaded bridge bytes must match the actual
reviewed artifact manifest. Add the bridge to the repository's protected host
module rules before release.

```python
from league.swarm.sail_research_host import SailBridgeInputs, build_sail_host_adapters

def build_host_adapters(config):
    # These are explicit host-owned capabilities from the reviewed operator file.
    # Every resolver verifies actual underlying evidence and independently approved
    # hashes; none returns an assumed zero baseline, current-price guarantee or True.
    inputs = SailBridgeInputs(
        checkpoint=approved_checkpoint_file,
        models=approved_model_file,
        billing=fresh_approved_billing_file,
        context=fresh_approved_host_context,
        ancestry=reviewed_original_ancestry_file_or_none,
        bill=reviewed_original_actual_bill_file_or_none,
    )
    return build_sail_host_adapters(config, inputs=inputs, key_source=private_sail_key)
```

The names in this template are required external inputs, with no production
defaults. The test fixtures are clearly synthetic and do not satisfy these gates.
The bridge never initializes a budget, changes account settings, fences old
writers, constructs a checkpoint, touches brokerage or supplies financial authority.

## Required receipt schemas

Every JSON receipt includes `schema: 1`, the exact `scope` and nonempty `provenance`.
Duplicate fields and nonfinite JSON are refused. `ReviewedFile` enforces plain
absolute owner-private paths and the independently approved content hash.

* Checkpoint: `checkpoint_id`, `source_sailbox_id`, `app_id`, `image_id`,
  `source_checkpoint_generation`, exact `resource_bound` dataclass fields,
  `gym_bundle`, `gym_execution`, `store_root`, `remote_root`, `python`, and reviewed
  `train_validation_only`, `guest_credentials_absent`, `no_live_processes`,
  `no_network` evidence. The checkpoint may retain memory/process state, so safe
  code/data labels alone do not prove it is free of live processes or credentials.
  Resource ceilings and inclusive creation fees must equal the broker policy.
  The real creation response and subsequent GET must match its app/image/name,
  checkpoint generation and capacities. Volumes are refused by this adapter.
* Models: `profiles`, each containing exact `ModelPolicy` dataclass fields,
  `max_request_bytes`, `billable_input_ceiling`, `completion_window: "asap"` or `"balanced"`,
  `agreement`. The input ceiling equals the policy's maximum and covers all
  formatting, histories, tools and other billable input. The entire maximum is
  reserved for every request. A heuristic such as bytes divided by three is not
  used. Output has an explicit wire cap; there are no server tools or fallback.
* Billing: `observed_at`, `valid_until`, exact `tariff` and `inventory` dataclass
  fields, `agreement`. Observation and inventory freshness are at most five
  minutes. Compute maximum rates cover the whole UTC day when the original
  DailyBudget has any resource history, including canceled and terminal rows.
  A ledger with only model obligations needs no unrelated compute-day price
  interval; model charge and accepted-liability evidence remain required. First
  resource admission independently requires the full-day compute tariff. The
  existing DailyBudget must already contain the complete current-day baseline
  and all unresolved liabilities; an empty current inventory never resets it.
  Normal billing reads the existing journal/cache without creating or migrating
  SQLite. The provider-free initializer may explicitly request passive
  `initialization_preflight=True` billing before creating its original allowance;
  that path opens no database and retains the full-day compute requirement. It
  conveys no model-only or paid authority. The initializer must reject retained
  initialization/OPEN markers or ledger artifacts when the database is missing.
  Every in-scope paid writer, key, application and relevant Gate/audit/forward
  research fee must be jointly accounted or have separately guaranteed bounded
  inclusion. An ordinary research fence alone does not prove this scope exclusive.
* Agreement: `kind: "binding_maximum_rates"` for resources, or
  `"binding_maximum_billable_tokens_and_rates"` for models, reviewed `path` and
  `sha256`, and reviewed `inclusive_fees_taxes`, `ongoing_liability_covered` facts.
  Its actual bytes are verified. This is an independently reviewed contractual
  interpretation, not a guarantee inferred from a GET rate. Liability coverage
  must persist until permanent termination or accepted-request final billing;
  merely expiring the ability to admit new work does not stop existing charges.
* Context: the existing HostContextEvidence schema binds the real broker root,
  policy digest, runbook and operator file to fresh actual host facts. Its broker,
  data, credential and joint-budget facts must come from real evidence, not a
  fixture, caller claim or static success literal.
* Recovery ancestry: `name`, `checkpoint_id`, `provider_response`, reviewed
  provenance. The original provider response includes `sailbox_id`, exact name,
  checkpoint and `source_checkpoint_generation`. Exact-name GET is candidate
  discovery; the published Sailbox GET lacks checkpoint ancestry and cannot
  approve attachment by itself. Absence, ambiguity and lost response keep the
  original resource liability and never authorize another creation POST.
* Actual model bill: `request_key`, `response_id`, exact `model`, `body_sha256`,
  exact-string `actual_usd`, authoritative `accrued_day`, `final: true` and trusted
  provenance. It must describe the original accepted request and all its billable
  products. Neither token usage times today's price nor response creation time
  establishes this invoice/day. Missing bills retain the full unknown hold.

## Dispatch and recovery

Before a mutation, the bridge replays the private broker journal, checks its cache,
checks the original shared-budget dispatch slot and verifies fresh evidence. Its
extra `swarm.research_host` intent commits with SQLite `synchronous=FULL`, flushing
prior shared-ledger reservations before the POST. This event kind is already
excluded from House/public mirrors. Raw provider responses are content-addressed,
owner-private files under `broker_root/sail-bridge-results`, fsynced before their
immutable journal reference. Corrupt, missing or symlinked receipts fail closed.

GymDriver uses one attempt. Approved code is installed from the exact artifact
bytes on each original request, without trusting inherited READY markers. Each
request has a separate original-key directory. Existing request directories are
unresolved evidence and are refused, so inherited results cannot become new trials.
There is no provider ID or command capability over controller IPC. Only Train and
whole-window Validation enter the driver; Gate, unseen and forward routes fail.

The model sends exactly one foreground Responses POST with a stable idempotency
key and a timeout bounded by the model policy. Provider redirects are refused by
the existing transport. A lost or nonterminal reply keeps the original intent and
hold. Terminal replies with unknown cost remain usable but do not release money.
The broker terminal receipt records `cost_usd: null`, `accrued_day: null` and a separate
`cost_upper_usd` from the original dispatched reservation, with `cost_status:
unknown`. The research router, researcher and architect reports preserve actual
cost and reservation as separate fields, including
failed or cancelled terminal requests. Unknown invoices create no vendor-actual
spend row. Cached replies never submit another request, reprice the original
reservation or rewrite the captured response; older replies obtain a read-only
cost view from their original durable reservation. An asynchronous rewrite records
its own cost event instead of adding its charge to the calling cycle.

The [published Responses schema](https://docs.sailresearch.com/openapi.json)
provides token usage rather than a final per-request USD invoice. Published
[usage endpoints](https://docs.sailresearch.com/usage-endpoints) provide delayed
aggregate metered spending and per-task token counts. A usable terminal response
therefore does not require a per-request invoice that the standard API has not
documented. Aggregate usage alone does not settle an individual request or release
its reservation.

The host can call `adapters.provider.reconcile_model_bill(original_key)` after a
later reviewed actual invoice arrives. This performs no provider POST, settles
the same DailyBudget once and preserves the immutable original controller reply.
It does not invent an actual bill from the usage dashboard.

A separately selected private cleanup factory may pass `cleanup_only=True`.
It retains original immutable checkpoint/model identity and journal ownership,
and permits only recorded sleep/termination controls and readbacks when current
pricing/context evidence has expired. It rejects creation, resume, Gym work and
model sends. The existing HostRuntime cleanup still owns controller quiescence
and matching permanent terminal observation; the bridge does not erase a resource
reservation from a shutdown, sleep or control request.

The published [pricing](https://docs.sailresearch.com/pricing),
[Sailbox schemas](https://docs.sailresearch.com/sailbox-openapi.json) and
[Responses schemas](https://docs.sailresearch.com/openapi.json) define the transport
shapes. [Terms 7.2–7.3](https://www.sailresearch.com/terms) allow prospective price changes
and additional taxes. Current observed rates and prepaid exhaustion do not alone
establish the required inclusive daily maximum-charge guarantee.

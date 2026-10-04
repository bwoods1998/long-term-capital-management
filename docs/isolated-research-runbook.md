# Operating the standalone research host

This release adds a separate research controller, host broker and daily obligation ledger.
It does not activate financial execution. The existing website design stays unchanged.
The House, gateway, brokerage credentials and financial state have separate release procedures.

The controller uses the existing Researcher, Tournament and Architect for Train and Validation.
It has no Gate, forward scheduler, provider credential, environment-file loader or publishing route.
Bubblewrap gives it separate user, PID, mount and network namespaces. Its only host capability is
an authenticated Unix broker socket. A disposable isolation probe does not authorize paid research.

## Prepare the exact artifact

Use a committed head whose gateway, Python 3.11, Python 3.14 and content checks all passed.
Keep the explicit controller configuration and research policy free of credentials and sealed data.
The configuration documents are part of the approved artifact manifest.

```sh
python3 scripts/research_release.py pack \
  --repo /absolute/reviewed-checkout --head EXACT_40_CHARACTER_HEAD \
  --output /private/research/releases/candidate \
  --config /private/research/reviewed-controller.json \
  --policy /private/research/reviewed-policy.json
python3 scripts/research_release.py verify \
  --receipt /private/research/releases/candidate/release.json \
  --receipt-sha256 APPROVED_CANDIDATE_RECEIPT_SHA256
```

Packing reads immutable Git blobs, rather than working-tree edits. It exports code and the Gym
contract, excludes tests, Git history, runtime databases and market datasets, and records every
artifact file hash. Retain the receipt SHA256 from the reviewed pack output independently;
verification refuses a changed head or rewritten self-manifest. It makes no provider calls
and does not deploy anything. Keep the artifact,
controller state and host ledger in disjoint directories. The host directory and state directory
must be owner-only. The controller never mounts the host ledger or raw source archive.

Import survivors through `research_state.capture_snapshot` and `import_snapshot`. The source
snapshot, original evaluator identity, metadata digest, approved program hashes and approved Train
run identities are explicit inputs. The importer retains lineage, trial counts, consumed looks,
retirements and failure inheritance while excluding raw Validation, unseen and forward payloads.
For an existing large corpus, pass an explicit `CaptureSelection` to `capture_snapshot` with
reviewed program SHA256 values and Train run IDs. This selects artifact bytes while retaining the
entire coherent SQLite history and metadata digest, including pruned runs and owed failure bars.
It grants no export approval. Missing or changed selected bytes refuse capture; non-Train or
unseen run IDs are refused. Review and pin a separate `ExportApproval` before importing.
A historical pass is historical evidence; it does not qualify the new evaluator. Never copy a
production database directly into the controller mount or initialize an empty replacement ledger
to avoid its existing obligations.

## Prove the daily authority before paid work

The host reuses one durable `DailyBudget` store. Initialization needs complete current UTC-day
prior-cost evidence, including an asserted zero. Pricing inputs must cover the entire UTC day.
Inventory must be complete, fresh, scoped and supported by an exclusive-writer check. An account
inventory snapshot alone cannot prove no other process can spend.

Every nonterminated resource reserves its complete 24-hour resource ceiling on every future UTC
day. Sleeping boxes, uncertain creations and missed stop replies retain their commitments. Model
requests reserve a trusted full token ceiling before dispatch; unknown outcomes retain the hold.
Only matching permanent termination ends future runtime obligations. None of these bounds is a
vendor invoice. A new day's missing tariff or inventory evidence closes admission.

The existing swarm's daily unbrake, model roles and adopted Gym dispatchers must be fenced or
accounted through the same authority first. Setting the new controller to $25, setting the old
pool's box cap to zero, or copying a billing database does not establish a shared $25 ceiling.
Do not use `failed`, a missing list row or elapsed TTL as proof that a box terminated.

The host adapter is a separate owner-only, hash-reviewed Python file. Its
`build_host_adapters` factory returns scoped provider and Gym capabilities, approved model
profiles, and fresh context and billing callbacks. It has no brokerage client. The context callback
supplies an exact private receipt for the shared ledger, Train/Validation-only Gym image, reviewed
runbook and reviewed adapters. These observations expire within five minutes and must be refreshed
from real evidence throughout operation. The controller cannot provide these facts in its request.

## Check and start

The private host configuration pins the head, full artifact manifest, three disjoint roots, socket
basename, explicit research policy, tariff and inventory evidence, deployment receipt and adapter
file hash. The deployment receipt identifies successful checks on the same head and artifact,
and the completed rollback and runbook evidence. `check` and `status` do not import the adapter
or call a provider.

```sh
python3 -m league.swarm.research_host check \
  --config /private/research/host.json --config-sha256 EXACT_CONFIG_SHA256
python3 -m league.swarm.research_host status \
  --config /private/research/host.json --config-sha256 EXACT_CONFIG_SHA256
python3 -m league.swarm.research_host serve \
  --config /private/research/host.json --config-sha256 EXACT_CONFIG_SHA256
```

Run these commands from the exact reviewed checkout. Startup checks the US session calendar and
refuses the session and the 90 minutes before open; it also keeps a five-minute margin after close.
A calendar read error refuses deployment. Startup binds the private socket and launches only the
fixed `league.swarm.research_controller` entry. Each broker request rechecks the captured process,
kernel peer identity, cleared environment, mount bindings, network namespace and fresh host facts.
Missing evidence holds paid work. The IPC client does not retry uncertain dispatches.

Watch the private controller heartbeat and daily funnel. Count actual completed Train and
Validation evaluations, trials, verdicts and holds. The controller's unseen evaluation and financial
execution counts are zero by construction; qualification and financial operator steps remain
separate. A cached result adds no new paid job or trial. Late results reconcile against their
original requests after restart, including when new paid work is held for budget room.

## Rollback and cleanup

First rehearse source restoration in a disposable directory using quiescent copied synthetic
state, then rehearse the host's real controller stop/start lifecycle with synthetic adapters.
The source-pointer drill alone does not satisfy the lifecycle requirement.

```sh
python3 scripts/research_release.py drill \
  --previous /private/research/releases/previous/release.json \
  --candidate /private/research/releases/candidate/release.json \
  --previous-sha256 APPROVED_PREVIOUS_RECEIPT_SHA256 \
  --candidate-sha256 APPROVED_CANDIDATE_RECEIPT_SHA256 \
  --state /private/research/drill-state --output /private/research/drill-output
```

The drill records both heads, observes candidate code, restores previous code and verifies all
state bytes are unchanged. It cannot write inside either artifact or durable state directory.
Its receipt explicitly says that production deployment and controller lifecycle were not rehearsed.

For an operating host, send SIGTERM to its recorded host process. The host stops only its captured
controller and listener. Preserve the host ledger and private controller database across release
changes. Shutdown is not a refund or termination receipt. Restore the reviewed previous artifact
and configuration, refresh admission evidence, and start through the same host gates. Never restore
a pre-spend database over the current ledger or erase pending requests and failed evidence.

Use the host's separate cleanup operation for its one journal-owned resource when required:

```sh
python3 -m league.swarm.research_host cleanup \
  --config /private/research/host.json --config-sha256 EXACT_CONFIG_SHA256
```

Cleanup persists stop intent before calling the provider and accepts only matching terminal
readback. It accepts no arbitrary resource ID. A lost unbound creation remains unresolved until
authoritative recovery. Recheck inventory and the ledger after cleanup; keep invoice uncertainty
separate from confirmed runtime termination.

## Report each UTC day and session

Record the deployed isolated head, controller uptime, family dispositions, fresh evaluation funnel,
budget room, outstanding resource and inference obligations, and itemized daily costs. Distinguish
settled amounts, estimates and unknown invoices. Do not add overlapping rolling-day and UTC-day
meters, or count Gym estimates twice alongside the provider's box bill.

Read the existing House's health, preopen receipts and brokerage activity without changing financial
execution. Report actual agent trades or the exact qualification reason for none. A planned preopen
job is not a passing receipt. Include Monday's report only after that session's data exist, and never
claim profit the account does not show.

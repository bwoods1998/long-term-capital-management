# Resumable research tools

The first live trial ran **six evidence operations** in an isolated Sailbox: two
source reads and four calculations. The worker slept, resumed from a new local
controller process, and returned results matching local deterministic checks.
Five Sail model calls cost an estimated **$0.050270584**. Sail reported
**$0.00504778** finalized compute cost and zero active cost after termination.
Measured record (`experiments/data/experiments/cloud-research-tools.json`)

The final report remained private: the critic wrapped its JSON in a Markdown
fence, which the trial's frozen strict parser rejected. New investigations record
`json-envelope-v1`, accepting an exact optional wrapper before enforcing the same
content checks. Replaying that response offline now parses successfully. The
original failed investigation was not rewritten or counted as a successful run.

## What runs where

The MacBook owns credentials, inference requests, Voyages tracing, and the single
SQLite request/budget ledger. Sailbox receives only a frozen public-evidence and
code bundle. It has no credentials, network egress, listeners, or account access.
This is a cloud tool worker, not a fully hosted research controller.

Every upload is read back and hashed before research begins. Each model-selected
tool has a stable identity, frozen arguments, and a disk receipt. The guest checks
its manifest before execution; the host independently checks the returned result.
A retry reuses its original operation identity. An uncertain VM creation cannot
silently become a second creation.

## Local use

Requires the private Sail setup and captured registered sources. These commands
are not required to explore the public repository.

```bash
# Freeze an offline bundle; this does not create a resource.
.venv/bin/python cloud_research.py prepare example-case

# These commands can incur Sail charges within the frozen limits.
.venv/bin/python cloud_research.py create .data/cloud-research/example-case
.venv/bin/python cloud_research.py step .data/cloud-research/example-case
.venv/bin/python cloud_research.py sleep .data/cloud-research/example-case
.venv/bin/python cloud_research.py step .data/cloud-research/example-case

# Terminate and reconcile the known resource, even after its work deadline.
.venv/bin/python cloud_research.py finish .data/cloud-research/example-case
```

Each step advances one saved research request or retrieves its existing result.
The controller permits eight research turns, a two-hour resource deadline, and
at most a $1 compute allowance inside the shared $4 compute envelope. Inference
uses the [existing ledger](BUDGET.md). A separate local watchdog handles cleanup;
it cannot operate while the MacBook is powered off. These are local controls,
not a provider-enforced account spending cap. Unknown cleanup or cost remains
unresolved and prevents admission of another cloud session.

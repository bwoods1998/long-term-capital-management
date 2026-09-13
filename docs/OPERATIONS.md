# Operations

The active implementation is [`portfolio_runtime/`](../portfolio_runtime/). Earlier experiment runners are preserved under [`experiments/`](../experiments/).

## Local setup

Python 3.11 or newer. The ledger and model transport use the standard library. Install the optional Sail SDK for hosted runtime and trace integration:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-sail.txt
```

Save a Sail key with the local hidden prompt if it is not already configured:

```sh
python3 scripts/setup_key.py
```

Private keys, raw evidence, request journals and portfolio databases stay under ignored local paths. A public clone contains source and approved projections, not the private run state.

## Verify and capture

```sh
python3 -m unittest discover -s tests -v
python3 -m portfolio_runtime.evidence --directory .data/runtime/evidence
```

The second command makes public-source requests and saves a dated universe and SEC facts. It does not run inference. Existing same-cutoff captures are reused. Check `capture.json` for failures before preparing a run; do not treat a partial source bank as complete coverage.

## Sustained run

Freeze a private configuration only when ready to launch. This does not make provider requests:

```sh
python3 scripts/prepare_runtime.py --hours 5 --budget 90 --start-in-minutes 10 --with-forks
```

The first run uses `.data/runtime/five-hour/run.json`. For a local run:

```sh
python3 -m portfolio_runtime.runner prepare --config .data/runtime/five-hour/run.json
python3 -m portfolio_runtime.runner status --config .data/runtime/five-hour/run.json
python3 -m portfolio_runtime.runner run --config .data/runtime/five-hour/run.json
```

`prepare` initializes paper state without provider requests. `status` reads the saved report. `run` starts or resumes paid work under the configuration's original deadline. `run --once` can admit paid requests; it is not a dry run. Do not start a local runner beside an active hosted coordinator.

A launch must preserve the chosen evidence cutoff, model profiles, request allowance, paper mandate and end time. The hosted coordinator owns the live journals. A research branch receives distinct task identities and a reserved sub-allowance; it cannot publish or control the portfolio.

For Sailbox hosting, `scripts/host_runtime.py provision --app-id <your-app-id>` creates the restricted host, installs the frozen bundle and records a Voyage. It does not start inference. `start` launches the managed cloud process; `monitor` runs the external recovery watchdog until the saved deadline. Run the monitor under a persistent local service. A stopped terminal is not a reliable watchdog.

`scripts/fork_runtime.py` prepares and runs the separate, bounded context experiment after the main host is installed. Its two $2 allocations must already be reserved inside the main inference ceiling. Its monitor collects receipts and terminates the seed and branch VMs; branches cannot publish or control the portfolio.

## Inspect and recover

The website's checkpoint contains its publication time. It refreshes once a minute while visible. A saved “running” checkpoint is an observation, not proof that a process is still healthy.

The first hosted deployment uses local user services `portfolio-sail-five-hour` and `portfolio-sail-forks-v2`. They survive a terminal disconnect; the computer must remain on for recovery and timely cloud cleanup. Inspect them with `systemctl --user status <service>`. Private observations and backups live beside the frozen configuration under `host/` and `forks-v2/`; `forks/` retains the initial pre-inference failure.

The website's separate Cloudflare alarm watches terminal states and missing heartbeats. Email delivery requires a verified notification destination; its private delivery journal distinguishes acceptance, pending configuration and an unconfirmed send. A configured binding alone is not proof that email arrived.

On interruption, recover the same run and accepted response IDs. Do not create a second portfolio or resend an uncertain request under a new key. Unknown terminal usage remains unsettled. An expired admission window ends new work; it does not erase unfinished requests or waive their cost.

The Sail host adapter can stop its managed process and take hash-verified, compressed SQLite backups into a private local directory. It snapshots each database consistently; stop the runtime first when a cross-database point-in-time backup is needed. The final watchdog backup preserves request, research, portfolio and Voyage journals. Raw filing captures remain on the cloud disk. Credentials and journals must not be placed in public site assets.

After the next market session opens, `python3 -m portfolio_runtime.runner paper --config <config>` can advance a stopped local paper ledger using actual delayed daily bars. It makes no inference requests. Run against the authoritative state, with one writer; an old backup is not a second portfolio.

## Brokerage

Schwab integration is paused while the account is unavailable. The existing [private connection guide](SCHWAB-SETUP.md) covers credentials and consent only. Live order execution and reconciliation are a later milestone.

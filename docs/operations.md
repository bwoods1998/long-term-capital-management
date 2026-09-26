# Operations

Wave 2b is prepared as a draft. Merge and deployment wait until Monday 2026-09-28 20:05Z, after the close. Production status comes from the running release and private records, not the branch's existence. Do not deploy from 13:25 to 20:05Z on a trading day except an emergency rollback.

## State and credentials

The House uses `/workspace/current` for code, `/workspace/releases/` for immutable releases, `/workspace/state` for state and `/workspace/.env` for three credentials: `SAIL_API_KEY`, `GATEWAY_TOKEN`, `CAPITAL_PUBLISH_TOKEN`. The owner environment is mode 600. Broker, OpenAI and GitHub credentials remain in the gateway. The owner-only gateway admin token remains in local `.data/ltcm/keys/gateway-admin.token`; it never goes to a box. The retained `.data/ltcm/` directory is operator state, not the deleted Python package.

Keep `ledger.sqlite`, `live.sqlite`, `live-grant.sqlite`, `swarm.sqlite`, programs, notebooks, backups and image records intact across a release. Never restore an old database over a running writer. The old pre-options state is archived separately; it is not the new House's rollback root.

On an owner checkout, read private environment files without echoing them. `floor_box.py` reads the retained `.data/ltcm/box.json` record. Isolated worktrees may use a private symlink to that state; preserve its target and `.env`. The checkout's configuration names the gateway, while keys remain outside git.

## Inspect

```sh
python3 scripts/floor_box.py status --json
python3 scripts/floor_watch.py --since 2026-09-26T06:25:30Z --json
python3 scripts/gateway_admin.py status
python3 scripts/live_trading.py
```

The floor watch reads SQLite read-only and reports per-store errors. It includes trial/run counts, bands, lineage looks, spend, live inventory, paper status, heartbeat ages and nightly readiness. It does not fetch private programs or quote files. On the House, `python -m league status --root /workspace/state` reads health and heartbeats; `scripts/economics.py --root /workspace/state --json` reports all closed-book cashflows and known costs. Open inventory is unknown in that quote-free economics command; the live publisher provides coherent current marks.

Use the source-of-truth records together: current release, latest completed tick and ledger sequence, swarm heartbeat, gateway kill/caps, paper proof day and status, reconciliation freeze, and grant digest/capital. A merged commit, running process or green historical run alone is not readiness.

## Pause, stop and recover

`floor_box.py maintenance on --reason ...` writes maintenance intent for the House. PAUSE prevents new live entries and starting new paid workers while the live path continues reconciliation and exits. A running swarm keeps training; use `<state>/swarm.stop` and verify its lifetime lock is released to quiesce research. `maintenance off` releases that intent. `gateway_admin.py kill` engages the external switch; `unkill` uses the owner's separate credential. A kill prevents new risk; inspect outstanding orders and inventory while exits continue.

`floor_box.py stop --reason ...` stops the runtime. Use a hard stop only when the resulting loss of active exit supervision is intended. Before restart or rollback inspect actual venue inventory, unknown/partial orders and current paper proof. Never clear a reconciliation freeze or delete an order record to obtain a clean status. Resolve the broker/state disagreement and keep the evidence.

The data worker can be stopped with `<state>/data/nightly.stop`; the supervisor enable file is `<state>/data-nightly.json`. Do not launch a second collector by hand while its lifetime lock is held. A process restart must match PID, Linux start ticks and exact argv before signalling it. A stale PID file alone is not permission to kill a process.

## Paper readiness

With `real_money: false`, no enabled grant and real gateway opens off, the paper route proof runs from 09:35 ET without a real-account client or eligible family. Unfinished attempts retain their identity and owned contracts through restarts. A witnessed paper open and close records route evidence; it never changes real-money flags, enables a grant or sends a real order. Real admission still requires the verified receipt and every independent money gate.

## Owner releases

1. Review the exact commit and all money-code changes independently. Run Python, gateway and content checks and inspect the private checkpoint readiness metadata. Confirm the latest W5 order, paper and accounting fixes are present.
2. Keep `auto_update: false`. The prune changes release trees, CI pins and the constitution digest, so the automatic updater cannot carry it. Verify `floor_box.py status` and `gateway_admin.py status` from the pruned tree first.
3. Use `floor_box.py deploy --help` for the current owner CLI. The uploader carries `league`, `scripts` and `deploy`, never `.data` or credentials. Bootstrap verifies numpy in the House interpreter. An isolated canary runs a synthetic program, resolves/quotes its structure and validates the money table before the release can be promoted.
4. The deployed copy of `league/config.json` controls `real_money`, live/paper requirements and publish settings; `<state>/swarm.json` controls swarm throughput and image selection. Verify those explicit values, the current broker account, gateway caps and grant before considering a release ready.
5. Ratify `options-swarm-20260928` after this prune changes the money digest, and after funded capital changes: `python3 scripts/live_trading.py --ratify options-swarm-20260928`. This is an owner money action, never part of a canary or automatic updater. The report command without arguments is read-only. A revoked grant cannot be silently reactivated.
6. Inspect the release watch and record exact deployed commit, money digest, grant receipt, image/model identities and checks in `CHANGELOG.md`. CI success proves code checks, not live profitability.

Rollback must retain a release that understands `live.sqlite`, current order states and the paper proof. The deploy guard refuses an older release while live inventory, unknown orders, an unfinished/contradictory proof or frozen reconciliation needs the current exit owner. Inspect `floor_box.py rollback --help`; do not bypass this guard to complete a routine rollback. Re-ratify if the restored money digest differs from the grant. Never roll back the new state to a pre-options House.

## Store completion and image activation

The trusted data controller's seed under `/workspace/state/data` contains `data_box.json`, `universe.json`, `calendar.json`, `images.json` and recorded backfill arguments. It contains no ThetaData, brokerage or model-provider credential. Enable supervision with `<state>/data-nightly.json` containing `{"enabled": true}`. Enable full historical completion separately with `<state>/data/completion-config.json` containing `{"enabled": true, "version": "<unique-version>"}`.

The daemon waits for all six ThetaData stages with no failing requests, relays historical SIP bars in chunks of at most 31 days, builds staged Gym and gate images, fits Train-only calibration inside the sealed Gym, copies the same private model to the sealed gate and checkpoints each twice. It records resumable phases in `completion.json`, builds under `next-images/`, and atomically emits `images-ready.json`. It does not switch the swarm's active images.

The data account supports one ThetaData session. Do not log in from another machine while backfill runs. Use the data tools' remote lease and identity-checked stop/restart, not manual concurrent image or data mutations. A lost lease or session restart failure is fatal to that attempt and cannot publish success. No `--force` is used to pretend missing historical coverage is complete.

Before selecting staged images, inspect coverage, both sealed policies, both checkpoint pairs, matching private model identity, and the recorded engine/data versions. Install the same model privately for live shadow and restart the House outside the protected session window. While both researcher and collector processes are quiesced, adopt the staged `images.json` and `calibration.json` together with the matching `swarm.json` pointers. Retain completion receipts and active-record backups. Check that `gym-forward.json` is absent or refers to the new model and complete forward lineage: a valid manifest overrides the configured gate pointer when the gate is enabled. Restart the pool against the new checkpoint IDs and keep the gate disabled until verification is complete. Re-run evidence against the resulting identity rather than transferring old passes.

The actual fitted table, quotes and trained programs stay private. The public run record may contain hashes, aggregate counts and conclusions only. Paper route fills must never feed calibration.

## Nightly forward collector

The first due job is Tuesday 2026-09-29 at 06:00Z, collecting Monday's session. Later jobs run at **02:00 America/New_York**, including the UTC shift at daylight-saving changes. A missed due job retries; a failed/no-data day cannot advance the successful watermark.

The supervised command is:

```sh
python3 scripts/data/nightly.py daemon --state /workspace/state/data --ready-file /workspace/state/gym-forward.json
```

The daemon holds `nightly.lock` for its lifetime and refreshes `nightly.heartbeat` during long jobs. The supervisor adopts the same identity after a restart, waits for useful work at a release change and never duplicates a locked process. The controller serializes with backfill, ingests completed underlying bars, extends the gate and publishes an atomic ready manifest only after successful checkpointing.

`gym-forward.json` contains schema 1, the completed session day and gate checkpoint. Ownership/mode checks authenticate the local handoff. The swarm consumes it only while the gate is enabled, requires the returned data identity and day coverage, and keys successful results by family, program version, day and checkpoint. Failures remain retryable. Training images do not change through this forward manifest.

## Pre-open and post-close record

Before admission opens, inspect cash/equity and funded caps, grant digest/capital, live/market data freshness, model identity, empty or fully reconciled inventory, order reservations and the validated paper-proof receipt or pending session proof. A Candidate without complete proof stays in shadow. A deadline never replaces a failed gate or routing check.

After close, reconcile every fill and remaining position, preserve unknowns, report whole-book real P&L after fees and all known input costs separately, and record promotions, demotions, holds and failures. Monday's result decides what actually happened; the draft cleanup can be reviewed for merge afterward.

## Research pacing

In `swarm.json`, `researcher.usd_per_hour` keeps the combined Sail-model and OpenAI trailing-hour pace. The optional `researcher.sail_usd_per_hour` sets an independently funded Sail pace; absent or null keeps the combined behavior. OpenAI holds still count against the separate burst cap and funded gateway month. Invalid, nonfinite or negative limits pause research. `swarm.heartbeat` reports `status.researcher_pace` with scope, limit, spend and reason, so a paced loop can be distinguished from a publication delay.

A Gym researcher can call `retire(reason)` to abandon its whole family. Retirement stops queued research, keeps the best programs and every trial/look, and leaves existing positions under their exit owner. Researchers and the tournament share the same atomic population-floor check. A floor refusal ends the cycle and uses the existing increasing error cooldown (up to thirty minutes); it does not retire the family. The raw reason stays private in its notebook and graveyard; the public event carries only filtered prose.

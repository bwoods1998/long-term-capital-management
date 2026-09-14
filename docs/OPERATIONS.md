# Operations

The [cloud supervisor](../control-plane/) manages a persistent [weekday service](../portfolio_runtime/service.py) on Sail. The Sailbox owns one paper ledger and a sequence of bounded research sessions. Cloudflare checks funding and progress, recovers the process, stores private backups, and emails the owner. The Mac is a development terminal once the cloud deployment is enrolled and verified.

## Prepare and verify

Python 3.11 or newer. Research and accounting use the standard library; hosted deployment and Voyage integration use the pinned Sail SDK.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-sail.txt
python3 scripts/setup_key.py
.venv/bin/python -m unittest discover -s tests -v
node --test control-plane/test/*.test.mjs
```

The key prompt is hidden. Credentials, raw responses, evidence and databases remain under ignored private paths. Public clones contain source and validated projections. Never put credentials in commands, URLs, Git, or site assets.

Capture dated public sources without inference:

```sh
python3 -m portfolio_runtime.evidence --directory .data/runtime/evidence
```

Inspect `capture.json` before launch. A partial source bank is not complete coverage. The weekday service refreshes constituent membership and SEC facts by evidence date, retains prior research, and fetches actual research prices separately from paper-execution observations.

## Enroll a cloud week

[`scripts/week_host.py`](../scripts/week_host.py) separates preparation, provisioning, and enrollment. Use `--help` for its current arguments. Preparation freezes an explicit service window, spending policy, evidence and a stopped seed. Provisioning installs the reviewed code and verifies the seed; enrollment arms the independent supervisor only after a readiness receipt matches the installed manifest.

Preparation defaults to `spending_mode: available_credit`: no fixed daily, session, rehearsal or weekly inference cap, and no gradual release of request dollars. Each session records its initial credit snapshot for audit; every new request checks the live grant and actual outstanding reservations. The snapshot does not cap that hour. Top-ups and released reservations become available within the current session. Useful new research and decision reviews determine work; balance alone is not evidence of value. Explicit `--spending-mode capped --budget …` remains available for a deliberately bounded experiment.

An optional rehearsal adds a timed research window before the scheduled week, using the same paper ledger and credit policy. Set `--rehearsal-starts-at` and `--rehearsal-ends-at`; available-credit mode takes no dollar caps. Sunday research cannot create Sunday market fills. After the window ends, accepted requests settle before one completion email; the service then waits for the original weekday start. The rehearsal does not shorten the week or create another portfolio.

The supervisor's private secrets are `SAIL_API_KEY`, `ADMIN_TOKEN` and `BACKUP_TOKEN`. The guest receives route-scoped credential injection for inference, publication and backup uploads. It cannot read private backups, change supervisor settings, access brokerage credentials, or make live orders. The site has its own private publication token and accepts only the public schema.

Weekday Sailboxes use 1 vCPU, 2 GiB memory and a 32 GiB disk ceiling; one-off experiments retain 8 GiB. Before freezing an available-credit host, provisioning replaces the offline cloud estimate with a reserve calculated from current provider rates through the final deadline and shutdown grace. This funds the resource commitment; it is not an inference-spending cap. Below 1 GiB of free disk, the service stops admitting new research while continuing receipt recovery.

Inspect or control the enrolled service through its private API:

| Endpoint | Effect |
|---|---|
| `GET /v1/status` | Saved health, spending authority and notification receipts. |
| `POST /v1/pause` | Close new admission and stop the service with a bounded grace period. |
| `POST /v1/resume` | Resume the same enrolled service and journals within its existing window and authority. |
| `POST /v1/release` | Verify a reviewed runtime update on the same paused, backed-up Sailbox; retain its configuration and journals. |

Use the local `week_host.py status`, `pause`, and `resume` commands with the deployment directory. A terminal disconnect does not stop the cloud service. Do not start a second local coordinator against a copy of its portfolio.

For a runtime update, pause and verify a fresh backup before installing reviewed code and its new manifest. The private release operation checks both manifests, unchanged service configuration and a stopped process before recording the new version; it leaves the service paused for verification. Resume then recovers the existing request identities and paper ledger. Release does not change the schedule, resources, source evidence or spending policy.

## Funding, progress and notifications

The [completed September 13 rehearsal](runs/2026-09-13-rehearsal-complete.md) records settled results, launch corrections and remaining limits before the scheduled paper week. The [earlier audit](runs/2026-09-13-rehearsal-audit.md) preserves what was known during the test.

Cloudflare checks actual Sail billing, reserves for unsettled requests and cloud usage, and grants short-lived spending authority. Missing or stale authority prevents new requests. The guest also enforces the grant at request reservation, preserving existing commitments rather than pretending failed or unfinished work was free.

Service heartbeat and main-thread progress are separate. A live heartbeat thread cannot conceal a stalled research controller. Recovery first requests a graceful stop; a verified bootstrap and its specific service child can be terminated after the recovery grace period. Restart reuses saved request identities and the same portfolio. Unknown create or request outcomes are not permission to start duplicates.

Email reports low funding, billing failures, unrecovered progress failures, backup problems and week completion. Routine research sessions do not each send another completion email. Provider acceptance is recorded separately from inbox delivery; ambiguous sends are retained without automatic duplication. The previously tested one-off run notifier remains separate from the weekday supervisor.

A low-funding pause recovers automatically after a top-up. Inference retains cloud funding and a small balance floor; accepted requests retain their conservative cost reservations until settled. Owner pauses, the service deadline and accounting problems still require their respective resolution. Shutdown has a fixed boundary. If outstanding requests or backups remain unresolved, the alert reports that reconciliation is needed instead of claiming a clean completion.

## Public record

The [portfolio page](https://blakewoods.us/portfolio/) reads saved checkpoints and refreshes once a minute while visible. It distinguishes running research, deliberate waiting and a service needing attention. Visitors cannot start inference or submit trades.

Coverage counts retained, source-checked research for current constituents; it does not imply every review uses today's disclosures. Request counts and costs accumulate across the service. The latest reviewed allocation persists across hourly boundaries. A checkpoint with no admitted work reports waiting, including an explicit credit wait when funding prevents the queued work.

[Research history](https://blakewoods.us/portfolio/research/) contains immutable final investment explanations, exact filing references, open questions and proposed decisions. Unsuccessful adjacent requests share a collapsed row; each individual record and timestamp remains accessible. Only settled terminal observations enter the journal. Admission and observed completion times are not hidden model-stage timestamps. Raw prompts, internal reasoning and account details stay private.

Paper accounting remains authoritative. A proposal is not a fill; fills require subsequent market-session observations. Portfolio returns use the S&P 500 Total Return benchmark and exclude deposits. Research and hosting costs are tracked separately. Missing market data or unresolved corporate actions must not be replaced with fabricated prices or returns.

Observed ordinary cash dividends accrue on the ex-date using shares held before that date. They enter portfolio value as receivables, not spendable cash or deposits. Payment requires separate dated evidence; the current market adapter does not supply payment dates. Splits, special distributions and ambiguous actions still suspend affected accounting until an explicit adapter can reconcile them.

## Private recovery

The guest periodically uploads SQLite snapshots and JSON state to private R2 storage. Each artifact has compressed and uncompressed hashes, and the manifest is uploaded last. The upload token cannot list or read backups. The frozen source evidence is retained for request recovery; large re-fetchable raw-source caches are excluded.

Each SQLite snapshot is internally consistent. The manifest explicitly records that independently copied databases are **not a simultaneous transaction across the whole service**. A healthy backup is not authority to run a second account.

For recovery after loss of the Sail disk:

1. Pause the supervisor and confirm all portfolio writers are stopped.
2. Download the private manifest and artifacts using the administrative credential. Verify hashes, sizes, schema and SQLite integrity before replacing state.
3. Restore into one isolated service. Reconcile accepted provider request IDs, commitments, paper events and publication receipts before admitting new work.
4. Review unresolved orders, costs or inconsistent journals; retain their reservations. Resume only the recovered authority.

Restore and reconciliation are deliberately manual in this version. Replaying a request with a new identity or treating an old snapshot as another portfolio can duplicate spending or corrupt the performance record.

## What improves automatically

The next investment review can revisit the original thesis against actual paper outcomes. A dated outcome journal preserves proposed allocations and measures executed holdings through recorded closing marks, net of trading costs and excluding deposits. Allocation and critic reviews receive only feedback observed by their cutoff. Missing benchmark observations stay missing; later data appends a new receipt without rewriting what an earlier review knew.

A separate policy experiment compares the same research task with up to three prior company reviews versus fresh context. Prospective dated pairs, an untouched audit set, source checks and recorded cost govern promotion. Results cannot rewrite their evaluator, benchmark, portfolio mandate or spending authority. This version permits one qualifying promotion and one rollback; it does not train model weights or autonomously edit production code.

See [evaluation](EVALUATION.md) for the sample, independence assumptions and promotion rules. Outcome feedback is not a trained trading policy, proof of skill or automatic permission to expand spending. Better source reliability is not demonstrated investment skill. Outperformance requires an accumulating forward portfolio record.

## Earlier runs and brokerage

The September 13 five-hour configuration was stopped early and preserved before the cloud-service refactor. Its Mac-hosted watchdogs are retired; [the dated record](runs/2026-09-13.md) separates completed research, errors and actual cost. `prepare_runtime.py`, `host_runtime.py` and `fork_runtime.py` remain useful for explicitly bounded experiments. Their `run` commands can incur charges; they are not dry runs.

Schwab integration remains paused while the brokerage account is unavailable. The [connection guide](SCHWAB-SETUP.md) covers private credentials and consent. Live execution and reconciliation are a later milestone.

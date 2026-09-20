# Phase one: funded, reproducible experiments

This is the first 48-hour foundation phase of the accelerated plan accepted September 20, 2026.
It starts on the first production activation of `league/campaigns.json`. The start and end are
persisted in `state/campaigns.sqlite`; restarting, redeploying, topping up an account or changing
the calendar cannot renew the allowance. Canaries have separate state and do not activate it.

## Released capital and account setup

| Allocation | Phase ceiling | What the running House may use |
|---|---:|---|
| OpenAI | $400 | $50 for automated architect, consultation and audit calls; $350 reserved for external engineering/Codex usage |
| Sail | $50 | Up to $45 after a $5 operating headroom commitment; the account expenditure meter includes inference, agent boxes and hosting |
| Shared infrastructure | $50 | Held as an external reserve; no new purchase is required |
| **Total** | **$500** | No later-phase allowance is automatically released |

The automated model admission limits are $25 per vendor per UTC day, within the phase limits.
Existing gateway and account caps remain additional ceilings. Allowances are ceilings, not
spending targets. Unused money does not accelerate tomorrow's calls. Model roles cannot edit
campaign policy, accounting or the experiment archive.

At the pre-deployment check Sail had approximately **$79** in credit and the gateway had
approximately **$85** remaining under its $100 September OpenAI cap. Those existing allowances
are sufficient for this phase. The gateway number is a cap, **not an OpenAI billing balance**:
ensure the connected OpenAI API project has at least $50 of usable credit/billing capacity.
No Kalshi or Alpaca top-up, SIP upgrade, data subscription or new provider account is needed now.
Keep the remaining capital outside agent-accessible accounts.

External coding and infrastructure bills are not visible to the House. Their $400 combined
reserves are commitments, not reported expenditure or a technical cap on interactive Codex use.
Reconcile actual project-attributable bills against them before releasing phase two. Existing
pre-phase expenditure remains historical expenditure and is not erased or called a new deposit.

## What is running

- **Durable model commitments.** Sail requests reserve conservative token costs before POST;
  detached response identities and eventual costs survive restarts. Frontier calls also reserve
  before transmission. Frontier usage is booked at conservative premium rates when that exceeds
  the gateway's cost estimate, so a missing pricing premium cannot release too much budget.
  Unknown costs, timeouts and rejected responses without confirmed billing
  keep their holds. Over-reservation costs or a decreasing vendor expenditure counter close new
  admission. The Sail period expenditure counter includes non-model costs and cannot be hidden
  by a top-up. Missing/stale meter readings stop new paid research and paper wakes.
- **No new live capital.** Phase one blocks promotions into live rungs and new live buy intents.
  Existing position polling, reconciliation and exits continue. At expiry, new paid campaigns and
  paper wakes stop; essential hosting and existing risk management continue. This is application
  admission control, not a provider-enforced cap on every hosting/storage invoice. The operating
  reserve covers meter lag and work already running.
- **Reproducible experiments.** Before a paid replay starts, the House saves exact strategy,
  parameters, declared inputs, tape bytes, evaluator/safety/helper source, limits and runtime
  metadata. Each artifact has a SHA-256 content identity and is atomically published as compressed
  private JSON. Results and selection rows link to those identities. Query aliases are not data
  identities. Each selection decision also archives the judge/statistics source, constitution,
  prior trial Sharpes, exact result and verdict. Interrupted attempts remain visible. Corrupt or oversized artifacts and exhausted
  disk reserve stop archival work; artifacts are never silently overwritten or evicted.
- **Replay clocks and coverage.** Alpaca warmup history precedes scoring. Equity daily signal history
  becomes available after its New York day ends, including DST (crypto uses UTC days); separate five-minute bars supply
  execution times/prices. Kalshi trading close stops orders, while reported `settlement_ts`
  controls cash release. Missing settlement times keep cash locked and unresolved positions
  cannot qualify. `hours_to_resolve` reaches the strategy. Observed bars use the live
  `NEEDS.bars` timeframe and limit; missing inputs or windows exceeding supported capacity are
  explicitly unsupported. Legacy tapes without the new settlement contract remain readable;
  their old evaluation is not evidence of the corrected production behavior.
- **Shared observations and latency.** Newly fetched REST snapshots are recorded once with
  request/receipt times and a digest, using the requests the House already makes. Retention is
  seven days and at most 256 MiB of compressed payload; evictions are counted. SQLite overhead
  is additional. Exact trial data remains in the separate experiment archive. Job starts and
  finishes record queue, execution and end-to-end time, including failures and unmatched starts.
- **Evidence-directed research.** Research prompts require a question, baseline, artifact and
  acceptance check. Missing-data findings and measurable abstention triggers are valid outputs.
  Unpriced paid Sail web search is disabled in this phase; the existing news fallback remains.
- **Resumable research.** Queued sessions, frozen prompts/settings, accepted model requests,
  tool receipts, paid charges and candidate outcomes survive restarts in private
  `state/research.sqlite`. One active session per agent and OS execution locks prevent concurrent
  copies. An accepted flex timeout yields the worker and later polls the same response; it does
  not buy an ASAP replacement. Six-hour-old unfinished conversations expire. Retired or changed
  strategies cannot resume old work, and completed jobs preserve cooldowns even if `house.json`
  was not saved. Existing campaign and credit controls still apply on resume.
- **Current capability and coverage reports.** Researchers, consultants and Merton's roles see
  deployed replay/data support with an implementation digest. `runtime_status` refreshes it;
  `replay_coverage` inspects actual input dates/counts for the agent's current NEEDS using the
  normal tape cache. Coverage inspection runs no strategy or sandbox and adds no selection
  trial. Research summaries now distinguish counted trials from smoke checks and unavailable inputs. Requested window length is kept distinct from returned coverage, and settlement-only
  events are kept distinct from market observations. Historical journals are preserved.
- **Valid parameter experiments.** Births, adoptions and replays reject nonfinite values,
  impossible probability bands, crossed ranges and declared parameter-rule violations.
  Automatic mutations change one numeric knob within its standard or declared bounds and
  reject duplicate living configurations before buying a probe or granting an endowment.
  Unspecified numeric units stay fixed. A population replacement is selected before retiring
  its resident, and the newcomer cadence also governs displacement. Existing legacy records
  remain intact; health and current-capability reports identify their invalid parameters for
  research. Options smoke checks use the candidate's parameters and declared inputs.

These recordings are sampled REST views, not a tick/order-book archive. Alpaca replay execution
still uses bar prices and a modeled spread, not historical queue position or observed fills.
Historical tails are reused development data, not independent forward validation. This release
does not establish a profitable edge, autonomous House engineering or
calibrated selection across correlated strategy families; those are subsequent milestones.

Recovery has a deliberate boundary: a tool interrupted after its intent but before its receipt
has an **unconfirmed outcome**. It is not automatically repeated. The pass ends with that reason,
and any candidate already retained on the ledger is recovered. Likewise an interrupted
adoption/fork commit is not retried; its outcome remains archived and is flagged
`commit_unconfirmed`. This does not claim exactly-once execution across external services.
Research conversations begun before this release cannot be reconstructed retroactively. Merton's
independent architect/toolsmith/etc. passes are not yet resumable engineering jobs.

## Inspect and reproduce

On the House, with its installed Python and the current release as working directory:

```sh
/workspace/.venv/bin/python -m league.phase1 --root /workspace/state
/workspace/.venv/bin/python -m league.experiments MANIFEST_HASH --root /workspace/state
```

The progress command is read-only. It reports the policy, booked model costs (including the
frontier's conservative pricing bound),
unresolved commitments, vendor counters, archived trial coverage, unfinished jobs, latency
percentiles, durable research state, session conclusions and recorder coverage. Housekeeping
`merton:follow` polls are separate from model-pass latency. Worker latency counts attempts,
including deferred resumptions; completed research sessions are counted from summary receipts.
Costs ending in `micro_usd` are millionths of a dollar.
Unmatched job starts may represent either running or interrupted work.

To execute an archived replay, copy its archive into an **isolated offline environment** with
the recorded Python major/minor version, then run:

```sh
python -m league.experiments MANIFEST_HASH --root COPIED_STATE --reproduce --expected-result RESULT_HASH
python -m league.experiments --root COPIED_STATE --evaluation EVALUATION_ARTIFACT_HASH
```

This uses the archived evaluator source. The local subprocess reproducer is not a filesystem or
network sandbox for untrusted code; production candidate execution stays in sealed Sailboxes.
State, including the SQLite databases and artifacts, is covered by the existing House checkpoint
workflow. Check checkpoint success and available disk in the normal operational review.

## Acceptance before phase two

1. The same archived code/data/evaluator reproduces an identical result.
2. Concurrent admissions, restart, timeout, stale meter and phase expiry do not release money.
3. Warmup, daily availability, delayed settlement and unsupported input checks pass.
4. The deployed canary and production watch pass, books reconcile, and recordings accumulate.
5. A measured queue/completion/failure baseline is retained before any model or concurrency pilot.

The next engineering work adds a protected repair worker and matched model pilots, building on
the resumable research queue. The later-phase allowance is gated by evidence and a ledger/billing reconciliation, not the passage
of 48 hours. More market data or capital is purchased only for a demonstrated constraint.

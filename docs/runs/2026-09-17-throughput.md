# Faster research and complete position management

One-hour build beginning September 17, 2026 at 05:42 UTC. This release improves research
throughput, execution lifecycle and observability. It does not establish profitable alpha.

## Architecture and changes

1. **Observe:** Coinbase Level 2 snapshots and absolute updates maintain bounded books for
   subscribed markets. Strategies receive fresh top-of-book, depth, imbalance and fee-tier
   context. Depth expires after five seconds and is invalidated on disconnect. Account fills
   and resolutions wake the main loop; market ticks do not cause an uncontrolled wake storm.
2. **Generate:** Foundry rotates Kimi K3, DeepSeek V4 Pro and GLM 5.3 across six concurrent
   code candidates, alongside eighteen parameter variants. Directions now include inventory
   exits, fee-aware execution and regime adaptation. Normal eligibility is five minutes;
   four new independent outcomes can trigger eligibility after two minutes. These are
   scheduling thresholds, not a guarantee that a long-running cycle finishes that quickly.
3. **Test:** Twelve isolated Sail research sandboxes, per-desk provisioning locks instead
   of a global network lock, exact successful-result caching, and first-ready candidate
   testing. Cache identity includes source, parameters, historical window, fill model, seed,
   split policy and engine/runner code. Reuse is explicitly labelled, never new evidence.
4. **Remember:** SQLite retains source, parameters, hypotheses, results and failures across
   restarts. Recent distinct experiments feed subsequent prompts. Interrupted validated
   candidates are saved before testing. Errors are retained as lessons, not cached successes.
5. **Graduate:** A new crypto code challenger may replace a paused house baseline only
   after the existing replay gates AND positive independent forward evidence: at least 25
   grouped outcomes over three days with the configured confidence assessment. The losing
   baseline stays paused. Source hashes, frozen sizing, lifecycle and kill-switch gates bind.
6. **Manage:** Agents explicitly request reduce-only trims/closes. Both tool and risk engine
   verify held direction and quantity. Reductions cannot flip exposure, and depleted desk
   accounting equity no longer traps holdings. The kill switch still applies. Strategy
   cancellation/replacement waits for confirmed cancellation; racing fills require fresh
   inventory before another decision. Entry pauses and redeployments are rechecked after runs.
7. **Explain:** The website distinguishes execution monitoring from Foundry research and
   reports live fills, sell fills, enabled/paused strategies and shadow testing by venue.
   Health includes notification status. These are factual milestones, not private model
   reasoning traces or invented trades.

## Reliability fixes

- Sail provisioning network calls no longer serialize unrelated sandboxes. Shutdown sleeps
  distinct boxes with eight workers. CodeRun records the executed source hash, not the hash
  of supporting engine files.
- Unknown executions reserve their sandbox until the command's hard-timeout lease expires,
  including across floor restarts. A disconnected execution stream is reconciled against
  the same execution with bounded transient retries; commands are not blindly resubmitted.
  The authoritative output tail replaces incomplete streamed output. Errors expose categories.
- Coinbase market-feed frames permit a bounded 16 MiB snapshot; the previous 4 MiB limit
  could reject a full BTC book. User-feed limits are unchanged.
- Missing retired desks no longer force committee allocation on every tick.
- Email gateway Durable Object methods are exported and awaited. Stable notice identities
  deduplicate acknowledged retries; the floor retains delivered event identities across a
  partially failed batch. An explicit mail refusal cannot advance the cursor. This does not
  guarantee exactly-once email across a provider-send/ack crash or simultaneous send requests.
- Backtest counters now count completed, error-free measurements rather than every partial
  report containing an evidence object.

## Observed during the build

- Live Coinbase strategies were all paused: four strategy rows across two live desks, with
  sixteen enabled shadow rows. Lack of real fills was not evidence of a disconnected API.
- The account's read-only fee endpoint reported 0.5% maker and 0.9% taker fees. Historical
  replay remains conservative and does not backdate today's fee tier.
- The repaired Coinbase feed held seventeen depth books with all three venue/account feeds
  connected. A separate public-feed probe had no sequence gaps.
- Expanded crypto cycle 14 ran in 169.6 seconds, generated six valid code candidates and
  reported 21 backtests plus five failed runs. No candidate qualified; the best reported
  out-of-sample return was still negative. Subsequent cycles exposed unconfirmed Sail runs
  and partial engine-error reports; this motivated reconciliation and counter fixes.
- A clearly labelled notification test was accepted by the mail service. No artificial trade
  was placed to create a notification. The old counter bug is not proof earlier mail never sent.
- One Kalshi desk's accounting cash was negative after allocation changes under held inventory;
  its gross-exposure and cash constraints were real blockers. This release does not conceal
  losses, inject capital, bypass those entry limits or claim to repair historical allocations.

## Budgets and boundaries

Foundry's model budget is raised from $25 to $60/day. The overall floor spending fuse,
credit reserve, real-money learning sizes and external gateway trading caps are unchanged;
the research budget does not override those limits. Independent forward evidence takes time.
More experiments or emails are not profit, and selection on repeated historical windows can
overfit. No candidate found during this build established an exponential profit claim.

## Verification and deployment

- Python: 1,552 tests pass; existing resource/deprecation warnings remain.
- Gateway: 78 tests pass; syntax checks pass.
- Website: 62 tests pass; syntax checks pass, including execution-line presentation.
- Production event-chain audit checked 59,424 events without a mismatch; deployed Python
  sources matched local sources at 06:25 UTC. Final runtime health is checked separately.
- At 06:27 UTC the restarted floor reported no tick error, all three feeds connected and
  seventeen depth books. Cycle 17 successfully measured both Kalshi baselines and proceeded
  to six model candidates. Research memory held seventeen experiments and the result cache
  fifty-two entries (including earlier engine identities); these counts are not profits.
- A repeated delivery test returned `sent: true, duplicate: true`. The live public events
  endpoint returned HTTP 200 and the frontend projected its execution heartbeat correctly.
- Gateway version: `1aa549d0-65cc-477e-8ccc-c00dd2f00376`.
- Website version: `c8c13e9b-17c8-42e0-8689-e836d3eeb552`.

Official contracts consulted: [Sail exec wait](https://docs.sailresearch.com/api-reference/exec/wait-for-an-exec),
[Coinbase WebSockets](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/guides/websocket),
[Kalshi rate limits](https://docs.kalshi.com/getting_started/rate_limits). Parallel research
retains aggregate history-request pacing instead of multiplying unbounded venue traffic.

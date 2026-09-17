# Overnight assessment and no-runway-throttle policy

Audit performed September 17, 2026, approximately 14:11 UTC / 07:11 PDT.
Read-only venue-account checkpoints and the production SQLite event log were used;
no manual orders, funding transfers, strategy re-enablement or risk-limit changes.
The deployed Python files matched the checkout and 74,528 event-chain records
verified without a hash-chain error at the initial inspection.

## Measured result

Account marks at 07:10:06.786–14:08:44.205 UTC:

| Measure | Start | End | Change |
| --- | ---: | ---: | ---: |
| Kalshi + Coinbase equity | $914.26618649 | $909.22509690 | −$5.04108959 (−0.55%) |
| Recorded total Sail spending | $55.87 | $76.38 | $20.51 |

Funding verification reported zero net external flows since the chart's audited
opening mark. Approximate overnight account change less incremental recorded Sail
cost: **−$25.55**. This is marked account value, including open positions, not
realized-only P&L or guaranteed liquidation proceeds. It is not evidence of
exponential profitability.

The event audit was bounded to 07:10:06.786–14:10:28.047 UTC:

- 3 new live Kalshi buy-fill records (one a partial fill); 24 Kalshi settlement
  records allocated across desks. Settlements are not newly executed sell orders.
- 0 Coinbase live fills. Both live crypto starters (`hourly_reversion` and
  `spot_quotes`) were disabled before the overnight window after fee-inclusive
  tests failed. Their shadow variants continued testing; they remain disabled.
- 84 session starts, 780 provider request events, 9 spawned variants, no
  `evolution.promoted` events.
- Foundry cycles 23–44: 479 candidates, 519 completed backtests including
  baselines, 4 failed backtests, 83 valid code mutations, 29 cache hits,
  **0 qualified/deployed winners**. Recorded Foundry model cost: $12.86102833.
- The Firm Mind's latest pass read 299 outcomes with 87 held out; it had **0
  admitted rules**. More activity has not yet yielded an admitted predictive edge.

## Why throughput fell

The old three-day policy first throttled at 09:48:24 UTC, oscillated around its
threshold, and throttled again at 11:05:06 UTC. Last Foundry cycle start was
11:00:05 UTC. New Foundry work, shadow sessions, seeding and model-assisted Mind
proposals were gated by `live_only`.

It also converted about $193 of remaining credit into a roughly $39 daily ceiling
after about $43 had already been recorded that day. 21 session endings in the
bounded audit (23 by the first unbounded read a few minutes later) reported
`provider_floor_cap_exceeded`. This affected live sessions too.

There was a second accounting issue even in open mode: the provider compares
*cumulative daily spend* against its ceiling, but the policy supplied *remaining
credit*. Already-paid costs therefore consumed the allowance a second time.

## Changes

- Default and deployed `throttle_days` are now **0**. Short runway is advisory;
  research and shadow/live sessions remain eligible above the $10 reserve.
- In open mode the provider ceiling is settled charges today plus remaining
  spendable credit. Outstanding reservations remain counted, so concurrent calls
  cannot reclaim each other's pending allocations.
- Low-credit emails now describe an advisory runway and no runway-based throttle;
  they no longer promise a three-day slowdown or an exact one-minute recovery.
- The $10 reserve pause, per-desk runaway fuses, trading controls, evidence gates,
  API limits and fee-negative strategy disables remain intact. Legacy opt-in
  throttle arithmetic remains testable but is not enabled in the owner policy.

## Next architectural work (not implemented by this policy change)

1. **Evidence coverage before another mutation batch.** Leading Kalshi candidates
   often have 2–8 total positions, versus 60 required. Acquire a broader historical
   sample and independent forward observations; report evidence deficits explicitly.
2. **Comparable, adequately sampled baselines.** `Foundry.rank` can set the hurdle
   from a baseline with one out-of-sample position (+9.89% in the sampled cycle).
   That is an unstable reference. Use paired candidate/control evidence with enough
   independent observations; do not merely remove the improvement requirement.
3. **Crypto research that can overcome actual fees.** The last crypto cycle's top
   candidate returned −1.29% out of sample with a negative lower confidence bound.
   Restoring compute is not a reason to re-enable that strategy with real funds.
4. **Execution and publication accounting.** Audit Kalshi shard cash constraints,
   repeated rejected intents, event publication conflicts and held email notices.
   Email count and raw request/backtest count are not profit measures.

The useful target is independently validated, fee-positive strategies reaching
forward testing faster—not spending credits or executing orders for their own sake.

## Deployment verification

- 1,567 runtime tests and 79 gateway tests passed.
- Gateway email update deployed as version
  `82898359-9615-4831-9291-fb4de3ad5bce`.
- Runtime restarted cleanly into the policy change. At 14:19:26 UTC, its budget
  event reported `mode=open`, about $192 spendable, with runway still 2.9 days.
- Fourteen new sessions started following restart.
- Public Foundry progress at 14:22:31–14:22:36 UTC confirmed **cycle 45 resumed**:
  two baselines and 18 parameter variants testing across 12 Sail sandboxes.
  This verifies resumed work, not a newly qualified strategy or a profit claim.

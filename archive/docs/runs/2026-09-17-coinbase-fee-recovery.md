# Coinbase fee and execution recovery

Owner request: fix the inactive Coinbase path; do not move money to Kalshi.

## Findings

- Authenticated Coinbase transaction summary returned maker `0.005`, taker `0.009`.
  Backtest defaults, shadow defaults and model instructions still used taker `0.012`.
- Both live desks (`hilibrand`, `hilibrand-3`) had both house strategies disabled.
  This was an explicit strategy pause, not evidence of a disconnected API.
- `hourly_reversion` had no round-trip fee hurdle, could duplicate working buys,
  and rounded marketable buys to the nearest cent (sometimes below the ask).
- Restoring an exit-only strategy would previously suppress recovery research into
  the paused entry strategy: recovery subjects were included only when *no* strategy
  was enabled.

## Changes

- The Foundry snapshots the authenticated fee tier once per crypto research cycle.
  Prompts, all candidates, replay contexts and result-cache keys use that snapshot.
  An unavailable/stale tier blocks crypto scoring, not Kalshi research.
- Coinbase shadow fills read the cached authenticated tier at execution time.
  Historical fills and fees are not rewritten. Offline backtest defaults are an
  explicitly dated 0.5%/0.9% snapshot, not a promise that the tier never changes.
- Reversion entries require a fresh tier and a target net of both taker fees that
  clears 1% plus the book spread and a 0.2% slippage cushion. Working buys and held
  assets are skipped; marketable prices round upward to the product tick; entry
  orders expire after 120 seconds. Missing fees are not interpreted as zero.
- Spot quoting uses the current maker tier and exact compounded fee/margin math.
  Unknown fees stop bids, not exits. Held assets outside the entry universe are
  still considered for exits; sells are explicitly reduce-only.
- Recovery research continues alongside an enabled exit-only strategy, but an
  active replacement lineage takes priority over its old parent.
- House-code refresh resets the forward-evidence epoch and invalidates old runs
  still in flight. The old version's outcomes cannot qualify the revised code.
- Narrow, stopped-process-only migration resumes **exit-only** spot quoting on the
  two audited live desks, backs up the strategy state, preserves all other desks
  and keeps the unqualified reversion entry rule disabled. Re-running it cannot
  undo a later owner pause.

No new-entry evidence gate, risk limit, allocation or venue balance was changed.
There is no transfer to Kalshi and no manual live test trade.

## Replay evidence

30 days, August 18–September 17 at 15:00 UTC; BTC, ETH, SOL; 15-minute decisions;
$10 simulated lots; conservative fill model; **today's fee tier as a fixed cost
scenario**, not a reconstruction of historical fee tiers. Six completed round
trips, twelve fills, zero engine errors, no outstanding positions or expired buys.

- Net simulated P&L: **−$0.8356** on $59.9964 entry notional (−1.39%).
- Fees: $1.0822; all six round trips lost after costs.
- Out-of-sample: two trades, −$0.4703 (−2.35% on their entry notional).

This is a small, negative sample, not sufficient evidence to deploy a new entry
strategy or promise profits. The first replay, before correcting buy-price tick
rounding, had 19 expiries and only two completed trades; it is not the final result.

Reproduction:

```sh
python scripts/backtest.py --strategy hourly_reversion \
  --params '{"symbols":["BTC-USD","ETH-USD","SOL-USD"]}' \
  --days 30 --end 2026-09-17T15:00:00Z --step-minutes 15 --max-seconds 300 --json-only
```

## Verification

- Final full runtime suite: **1,582 tests passed**; existing resource/deprecation warnings.
- Pre-deployment Sail checkpoint: `sbcp_e3d421fe-60da-4b73-9da9-c6205c977e59`.
- Exit-only recovery applied with backup at
  `/workspace/.data/ltcm/strategies.before-coinbase-fee-recovery-2026-09-17-20260917T152218430207Z.json`.
- At 15:28:53 UTC both live Coinbase quote strategies ran without errors:
  `bids off: params`, zero target orders. This is restored execution of the
  position-management loop, **not a new live trade or an entry-strategy promotion**.
- Public event stream confirmed two enabled live Coinbase strategies, two paused
  entry strategies and sixteen enabled shadow strategies. The summary checkpoint
  was still older; event-stream freshness and summary freshness differ.
- Supervised final restart completed at **15:34:38 UTC**, with no kill switch or
  stop latch left engaged. At 15:36:06 UTC the live and shadow crypto house rows
  carried the new code hashes and fresh forward-evidence epochs. All production
  runtime Python hashes matched the checkout.
- At **15:36:24.993 UTC**, crypto Foundry cycle 52 published its authenticated
  **0.5% maker / 0.9% taker** snapshot. It launched two baselines, eighteen parameter
  candidates and six code-generation jobs; this confirms the repaired research
  path, not qualification of a winner.
- As of the 15:37 UTC review the website summary checkpoint still showed the older
  15:18 state, while the public event stream and private runtime state were current.
  Summary publication latency is an outstanding separate operational issue.

# Check lineage eligibility before paying for a duplicate

## What was tried

Three crypto-reversion descendants each obtained a development replay pass:

| Agent | Generation | Replay Sharpe | Closed trades | Reported compute |
|---|---:|---:|---:|---:|
| rosenfeld-42 | 26 | -0.035107 | 53 | $0.00 |
| rosenfeld-43 | 25 | -0.035855 | 45 | $0.01 |
| rosenfeld-44 | 23 | -0.031746 | 46 | $0.01 |

Each ran one replay and zero forward blocks. Each died as **redundant**, not from a measured forward loss. The recorded refusal was identical: the lineage had spent its three holdout evaluations, and the same program already traded on paper as **rosenfeld-35**.

## Why this failed

A development pass did not create an eligible holdout evaluation or a distinct program. Different agent names, generations, trade counts, and replay scores did not overcome the House's recorded identity decision. The three retries bought no new forward observations.

The incumbent already supplies a forward record: rosenfeld-35 has 16 blocks and total log growth of **-0.003781**. That does not establish why the strategy lost, but it is evidence to inspect before duplicating its research. Its remaining research credits are not trading returns.

## Before the next research purchase

1. Identify the existing paper program and compare the proposed strategy's code, configuration, and intended behavior with it. Do not infer novelty from an agent name or generation.
2. Inspect the lineage's recorded holdout usage and latest refusal. If eligibility is unclear, resolve that uncertainty before paying for another replay. The three-evaluation limit here is a recorded lineage refusal, not a newly inferred universal rule.
3. If the proposal is unchanged and still ineligible, stop. Observe the incumbent; do not request another identical descendant.
4. For a substantive revision, write down the changed decision rule, the failure evidence it addresses, and the eligible evaluation route. A revision does not automatically reset lineage history or the holdout budget.

## Check the result

For this unchanged lineage and refusal, the target is **zero additional paid duplicate replays**. A follow-up is justified only by documented new behavior or evidence and confirmed evaluation eligibility—not another development pass. This check needs no new market-data feed or House engine change.

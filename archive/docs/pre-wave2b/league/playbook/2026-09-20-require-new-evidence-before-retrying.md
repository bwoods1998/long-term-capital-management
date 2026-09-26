# Require new evidence before retrying a failed replay

## The expensive repeat

Meriwether-3, a sports-favorites agent, died displaced after four replay trials, $0.48 of compute, and one forward block with total log growth of 0.0000.

| Replay trial count | Closed trades | Return | Sharpe | Deflated score |
|---|---:|---:|---:|---:|
| 2 | 2 | 1.13685% | 0.201861 | 0.956481 |
| 3 | 2 | 0.89555% | 0.191619 | 0.841048 |
| 4 | 2 | 0.89555% | 0.191619 | 0.726521 |

Every run failed the 20-closed-trade minimum. The last two had identical reported trade counts, returns, and raw Sharpe, but the final deflated score also failed the 0.75 requirement. The records do not identify code changes or prove identical trade identities; they do show no improvement in those raw metrics. Re-evaluation did not cure the sample shortage, and accumulated trials accompanied a lower adjusted score.

This is not confined to the dead agent: Meriwether-7 reported a 0.836261 deflated score but only one trade. That is still a failed replay, not a near-approved strategy.

## Diagnose the right failure

More trades are not a universal remedy. Hilibrand died after 12 forward blocks at -0.1093 total log growth; its last replay had 189 trades but a 0.781730 deflated score against its stated 0.90 requirement. Rosenfeld-2 had 28 replay trades, -1.060824% return, nonpositive out-of-sample growth, and a 0.005495 deflated score against 0.75. Its 13 flat forward blocks did not overturn that failure.

These deaths distinguish missing evidence from adverse evidence. Do not infer that fees, entry thresholds, or execution caused the losses: those details are absent.

## Before spending another credit

1. **Name the blocker.** Record sample count, out-of-sample growth result, adjusted score, and the threshold actually applicable to that run.
2. **For sparse samples, inspect existing coverage first.** Count eligible events, signals, orders, fills, and closures where logs permit. State whether a retry adds independent opportunities or fixes a documented pipeline defect. Do not loosen entries merely to reach 20 trades.
3. **For adequate but failing samples, require a distinct hypothesis.** Specify the mechanism being changed and the held-out result that would falsify it. Another similar aggregate return is not the objective.
4. **Preserve trial history.** Do not present repeated evaluation as independent confirmation or reset the evidence by renaming an agent.

## How to judge the next attempt

A retry proposal must identify its failed gate and concrete evidence-producing change. A resulting replay must clear all applicable gates—not just produce positive headline return. Keep forward block counts and log growth separate from replay results; zero forward growth alone establishes neither inactivity nor safety. If no new evidence can be named, defer the paid retry.

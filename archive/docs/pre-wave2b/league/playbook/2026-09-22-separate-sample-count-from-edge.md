# Separate sample count from evidence of an edge

## What was tried

Sports-props favourites produced attractive replay scores on small samples:

- **hufschmid-27:** a replay returned +3.25%, Sharpe 0.4451 and deflated Sharpe 0.8155, but only 15 closed trades. Its last replay had deflated Sharpe 0.5940 and seven trades. It spent $0.27 across three trials, then was displaced with no forward blocks.
- **hufschmid-28:** +3.30%, Sharpe 0.4459 and deflated Sharpe 0.8164, also rejected solely for 15 closed trades.
- **leahy-29**, attention favourites: +2.30%, deflated Sharpe 0.5777, rejected solely for eight closed trades.

The replay minimum was then **20 closed trades** (10 since Sept 22, 2026 21:25 UTC; read `qualification_policy.replay`), alongside the other gates. These scores did not waive it.

Conversely, hufschmid-29 recorded 22 trades but returned -10.20%, failed positive out-of-sample growth and had deflated Sharpe 0.00000376. Hufschmid-30 reached exactly 20 trades but had deflated Sharpe 0.0298, below 0.5.

## What this establishes

Sample sufficiency and performance quality are separate requirements. A high score on seven or fifteen trades is not qualification; twenty trades with a failed quality gate is not qualification either. The supplied records do not identify parameter changes, so they do not prove that loosening a particular filter caused the losses.

## Before buying another test

1. Record the complete failure vector: closed trades, replay blocks, out-of-sample coverage and growth, and deflated Sharpe. Use the current policy, not an older journal threshold.
2. If count is the only failure, preserve the exact configuration. Check whether genuinely additional eligible history exists using `replay_coverage` with the complete proposed NEEDS. More coverage does not guarantee more qualifying trades.
3. If coverage is unavailable, record that dependency and stop count-only parameter searches. Do not force turnover merely to reach the trade minimum.
4. If quality also fails, specify a separate, falsifiable edge hypothesis. Additional trades alone do not address that failure.

## Acceptance check

A follow-up must identify its new observations or changed hypothesis and pass every current replay gate. Repeated history remains development evidence; a pass still requires forward evaluation. Report unresolved settlements separately rather than counting them as completed trades.

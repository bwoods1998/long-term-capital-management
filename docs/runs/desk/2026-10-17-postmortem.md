# Desk post-mortem, the week to 2026-10-17

Written by the House at 14:00Z from its own records for the seven days to 2026-10-17T14:00:00Z. Counts and dollar figures only.

## The reading (Claude)

**A losing week that measured nothing about real fills: the House ran zero calibration round trips, so the Gym's fill rules went unchecked while the books lost 149.52 USD on 3 closes on top of 135.30 USD of running costs.**

- FILLS: the calibration log shows 0 attempts and no real slippage against the midpoint, yet the house test route shows 3 fills and 1 cancel; that gap is unexplained, and the receipts cannot say which way the Gym is wrong or by how much.
- Under the Gym's rules, practice fills averaged 0.91 USD a contract better than the midpoint: opens 0.35 worse, closes 2.82 better. Only 0.3684 of fills came at the natural price, so the Gym looks generous on closes, but no real fills exist to confirm it.
- ORDERS: practice saw 1067 rejections against 148 orders. 390 were holding caps, including 116 where 3 structures sat open under a cap of 1, which suggests positions outlived a cap change. Another 53 hit the expiry cutoff, 32 could not close because a leg was missing from the day's chain, and 12 failed sizing; 580 have no listed reason.
- Real orders filled 5 of 6, with 0.42 USD in fees.
- RESEARCH: 829 programs were retired against 15 promotions. One was demoted because execution rules changed and it needed fresh qualification. 17 harness releases were promoted while 3 engineer journal rows closed failed.
- The House missed 43 jobs, led by 13 stall checks and 7 engineer runs.

Next week:

1. Restore the one-lot calibration round trips so attempts are above zero by cell, and compare real slippage against the midpoint with the practice figures of 0.35 USD worse on opens and 2.82 USD better on closes.
2. Fix the cap bookkeeping behind the 116 rejections where 3 structures sat under a cap of 1, measured by that count falling to zero.
3. Handle positions whose leg leaves the chain, measured by the 32 missing-leg close rejections falling and every such position getting a recorded exit.

The week cost 135.30 USD, mostly models and boxes at 92.14, and with realized losses of 149.52 the net was -284.82. It bought research churn but no real fill measurements, the one thing the desk most needs.

## Real orders

| Placed | Filled | Cancelled or expired | Rejected by the venue | Refused before the venue | Fill rate of ended orders |
|---|---|---|---|---|---|
| 6 | 5 | 1 | 0 | 0 | 0.8333 |

## Fills against the Gym

| Book | Fills | Mean slippage a contract, USD (against the midpoint at the decision) |
|---|---|---|
| Real (the House's one-lot calibration round trips) | 0 | n/a |
| Practice (the Gym's fill rules on live market data) | 148 | -0.91 |

Practice rejections: 1067.

## Research

Demotions: 1; promotions: 15; retirements: 829.

## Harness changes

Self-deployed releases: promoted 1; owner deploys: promoted 16.

## The House's jobs

missed 43, ok 1199, skipped 30; failed: none; missed: budget_refresh 6, economics 1, engineer 7, equity_data 1, fill_minutes 1, forward_register 6, game 1, grant 6, scoreboard 1, stall 13.

## What the week cost

| Service | USD |
|---|---|
| Sail (models + boxes) | 92.14 |
| Claude (Anthropic via the gateway) | 5.60 |
| OpenAI | 0.00 |
| ThetaData | 18.39 |
| Alpaca market data (Algo Trader Plus) | 19.17 |
| TypeSafe/Jev (gateway meter) | 0.00 |
| **Total** | **135.30** |

Realized options P&L of the week (all routes, fees in): -149.52 over 3 closes; the week's Net: -284.82.

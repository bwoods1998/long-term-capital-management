# Desk post-mortem, the week to 2026-10-10

Written by the House at 14:00Z from its own records for the seven days to 2026-10-10T14:00:00Z. Counts and dollar figures only.

## The reading (Claude)

**The Gym charges about five times the real cost of a fill, so this week's practice results look worse than live trading would, and the desk lost money on both trading and running costs.**

- FILLS: The House's 28 real one-lot calibration fills cost on average 0.27 USD a contract worse than the midpoint, while the practice book under the Gym's rules paid 1.30 USD (1.12 on opens, 1.43 on closes), so the Gym is too pessimistic by roughly 1.03 USD a contract.
- Fill odds depend on the order type: closing orders resting at the midpoint filled only 7 of 14 times, and opening orders at the midpoint filled 8 of 10. Every order that gave up one tick filled, at about 0.75 to 1.00 USD a contract worse than the midpoint. The receipts do not show whether the Gym models any of this by order type.
- ORDERS: Real orders had no rejections; the 11 cancellations were 9 calibration orders and 2 house tests that did not fill. Practice had 543 rejections against 177 orders, and 292 of those came from programs sending orders while already at the cap of three open structures.
- Another 49 practice rejections came from missing market data (25 with no option chain, 24 with a leg lacking data), 28 hit the expiry cutoff, and 15 were structures whose risk exceeded the 100 USD loss limit.
- RESEARCH: 385 programs were retired, 2 were promoted and none were demoted. On the engineering side, 16 owner deploys were promoted, 1 was rolled back, nothing was self-deployed and one engineer journal item closed as failed. The House ran 482 jobs with none failed or missed.

Next week:

1. Lower the Gym's assumed slippage toward the 0.27 USD a contract measured on real fills, separately for opens and closes, and measure next week's gap between practice slippage and calibration slippage against this week's 1.03 USD.
2. Set the Gym's fill odds by order type from the calibration cells (closes at the midpoint filled half the time, one-tick concessions always filled), add calibration attempts on midpoint closes where only 14 attempts exist, and compare practice fill rates against calibration fill rates for each order type.
3. Have programs check the three-structure cap and the loss limit before sending orders, and measure practice rejections per order against this week's 543 for 177.

Running costs were 59.28 USD over a partial 4 days, and with -128.90 USD of realized options losses over 10 closes the net was -188.18 USD. That bought 28 real calibration fills that expose the Gym's fill error and 2 promotions, but no earnings, and the receipts do not split the realized losses between strategy trades and calibration round trips.

## Real orders

| Placed | Filled | Cancelled or expired | Rejected by the venue | Refused before the venue | Fill rate of ended orders |
|---|---|---|---|---|---|
| 43 | 32 | 11 | 0 | 0 | 0.7442 |

## Fills against the Gym

| Book | Fills | Mean slippage a contract, USD (against the midpoint at the decision) |
|---|---|---|
| Real (the House's one-lot calibration round trips) | 28 | 0.27 |
| Practice (the Gym's fill rules on live market data) | 156 | 1.3 |

Practice rejections: 543.

## Research

Demotions: 0; promotions: 2; retirements: 385.

## Harness changes

Self-deployed releases: none; owner deploys: promoted 16, rolled_back 1.

## The House's jobs

ok 482, skipped 12; failed: none; missed: none.

## What the week cost

| Service | USD |
|---|---|
| Sail (models + boxes) | 26.40 |
| Claude (Anthropic via the gateway) | 11.41 |
| OpenAI | 0.00 |
| ThetaData | 10.52 |
| Alpaca market data (Algo Trader Plus) | 10.95 |
| TypeSafe/Jev (gateway meter) | 0.00 |
| **Total** | **59.28** |

Realized options P&L of the week (all routes, fees in): -128.90 over 10 closes; the week's Net: -188.18 (a partial week: the close economics start inside it).

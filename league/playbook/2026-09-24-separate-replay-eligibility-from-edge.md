# A replay pass establishes eligibility, not an edge

## What was tried

The crypto-major desk submitted several strategies that passed replay but did not establish positive forward economics:

| Agent / strategy | Last replay evidence | Forward record | Compute |
|---|---|---|---|
| rosenfeld-h642872 / settlement-clock-bid | Sharpe -0.132868; deflated 1.46e-10; 146 trades; passed | 4 blocks; +0.0000 total log growth | $0.03 |
| rosenfeld-h030d59 / BTC-quality-rotation | Sharpe -0.072533; deflated 0.000140; 104 trades; passed; replay return -8.688459% | 2 blocks; +0.0000 | $0.05 |
| rosenfeld-hf9e14d / upside-gamma-hedging | Sharpe -0.099983; deflated 6.60e-13; 110 trades; passed | 21 blocks; -0.0021 | $0.27 |

Each died by **displacement**, not a recorded performance-death trigger. The repeated sentences in each post-mortem are not additional observations.

## Why the apparent contradiction is not a contradiction

Current replay policy requires 10 closed trades and sets minimum deflated Sharpe to **0.0**. Its out-of-sample growth floor is **-0.0005 per block**, or -0.050%. Passing these conditions does not imply positive expected profit. Overall replay return is also not the same statistic as out-of-sample block growth.

The failed inference is “passed, therefore worth another fork.” These summaries do not identify the trading mechanism behind the losses. Nor does zero reported forward growth establish inactivity, breakeven after costs, or successful risk control: fills, active blocks, and unresolved exposure are not supplied here.

## Before buying the next test

1. Attach the exact strategy version, NEEDS, replay window, and gate result. If the linkage is unavailable, do not treat an agent's last replay as validation of every version it ran forward.
2. Separately report overall replay return, after-cost out-of-sample growth, closed trades, active blocks, and forward total log growth. Mark unavailable fields as unknown rather than reconstructing them from “passed.”
3. For a zero-growth forward record, inspect existing decision and execution records first: eligible opportunities, orders, fills, completed positions, and still-open exposure. Do not loosen entries merely to generate activity.
4. Fund another mutation only with a named failure hypothesis and a test that adds information. An unchanged historical rerun does not supply a new forward observation. Model turns also spend credits.

## Check the next proposal

It must distinguish **eligibility**, **economic evidence**, and **administrative displacement**, and specify what result would falsify its proposed repair. Missing attribution calls for an audit of existing records, not immediate paid tuning. This lesson neither changes House thresholds nor proves these families cannot work.

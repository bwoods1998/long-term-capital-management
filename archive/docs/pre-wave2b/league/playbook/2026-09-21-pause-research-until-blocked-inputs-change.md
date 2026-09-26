# Pause research until blocked inputs change

## What happened

Rosenfeld (crypto-reversion, crypto majors) died **stuck**, not from a reported trading-loss limit: 59 consecutive wakes with a live market and no action, followed by insufficient credits to research its way out.

Its record was seven replay trials, $1.30 total compute, and +0.0009 total forward log growth over 34 blocks. The final replay had 22 closed trades, Sharpe -0.051176, and deflated Sharpe 0.003967 against seven trials; out-of-sample growth was not above zero. Reaching the 20-trade minimum did not repair the failed edge tests.

The family's funding-contrarian proposal requested BTC/ETH perpetual funding, history, open interest, and settlement timing. That request remains blocked. Current runtime capabilities explicitly do not supply perpetual funding/open interest; spot bars and quotes are not substitutes.

The record does not identify the reason for every idle wake or how much of the $1.30 was spent while idle. It does establish that a tiny positive forward result did not preserve enough research capacity to escape inactivity. Model turns themselves spend credits, even without a replay purchase.

## Before spending again

When a proposal depends on an unavailable input, leave a short dependency record:

- **Required observation:** exact field, source, timestamp requirement, and whether historical availability is needed.
- **Verified blocker:** cite current runtime capabilities or the relevant blocked engineering request. Advice is not implementation.
- **Reopening condition:** an implementation/coverage change that makes the proposed test executable, or a different hypothesis using inputs already available.
- **Next test:** one falsifiable comparison, its required observations, and its credit budget.

Pause unchanged discretionary research while that condition remains false. Do not spend another turn merely to restate the same request, clone the same blocked thesis, or rerun it without the required input. Where scheduling is controllable, prefer a dependency-change notification to polling; this lesson does not claim such controls are implemented.

On an unavoidable wake, use the dependency record rather than restarting the investigation. A genuinely different available-data hypothesis may justify research, but write down what changed first.

## How to judge the change

Audit the next research expenditure against the dependency record: did the input become available, or did the test materially change? If neither occurred, the pause rule failed.

After a dependency is fulfilled, verify actual coverage before buying a selection replay. Existing replay and forward gates still apply. Do not loosen entries, shorten holdings without an after-fee rationale, or force turnover to avoid a stuck classification. Conserving credits cannot guarantee survival, but spending on an unchanged blocker cannot supply the missing observation.

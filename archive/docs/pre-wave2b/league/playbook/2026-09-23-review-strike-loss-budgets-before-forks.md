# A downside-insurance name is not a loss budget

## What happened

`hilibrand-hc4567e`, the crypto-strikes-downside-insurance-s strategy, died **of evidence**, not seat displacement: its reported drawdown reached **43%**, beyond the **40%** death limit. It spent $0.59 on compute, ran two replay trials, and accumulated **-0.5659 total log growth over 10 forward blocks**. That log growth corresponds to approximately **-43.2% cumulative return**; cumulative return and peak-to-trough drawdown remain different measurements.

Its last replay supplied no rescue: Sharpe **-0.06218**, deflated score **0.09851**, and **9 closed trades versus 10 required**. It also failed the out-of-sample growth floor of **-0.050% per block**. The record does not establish whether that replay preceded the damaging positions.

The opposite-sounding `hilibrand-h6ca596` volatility-shock-upside strategy is not a demonstrated alternative: its forward total is **-0.359321 log growth over 11 blocks**. Its supplied trial 17 still says `passed: true` despite **-2.285% replay return**, Sharpe **-0.14141**, and 58 trades. A replay pass is not a profitability certificate.

## What this establishes—and does not

The insurance strategy failed to contain account losses within the terminal boundary. The supplied summaries do **not** identify whether settlement errors, directional losses, fees, sizing, or overlapping contracts caused that failure. Do not claim a specific defect or repair from the strategy name.

This is additional to settlement verification: even correctly settled contracts need an exposure budget. The current 25% paper-screen drawdown threshold and 40% death limit are evaluation boundaries, not recommended loss allowances.

## Before purchasing another strike trial

1. Reconcile the dead agent's fills, fees, marks, and reported settlements to its equity path. Separate realized losses from remaining inventory marks and identify the positions present during the drawdown.
2. For a proposed successor, document a dollar loss budget **before** choosing size. For purchased binary contracts, include premium at risk and fees. Group simultaneous positions by underlier and settlement window; evaluate joint spot outcomes across the ladder rather than treating every contract as independent protection.
3. Check both an immediate adverse move and inability to exit before settlement. Do not assume a stop fills at its trigger price. Skip an entry if its stressed portfolio loss breaches the chosen budget.
4. If the attribution cannot be completed, defer the fork. Another threshold sweep cannot diagnose an unexplained 43% drawdown.

## How to judge a successor

Require a reconciled loss report, an explicit budget, and reproducible examples showing rejected over-budget entries before another paid replay. These are proposed strategy checks, not claims of new House functionality. A repair must then earn fresh forward evidence with bounded exposure; neither a new name nor a development pass restores the dead parent's credibility.

# Crypto-15m: matching replays are not independent confirmation

## What was tried and what happened

Two differently named families produced exactly matching headline replay results:

| Agent / family | Replay Sharpe | Trades | Replay return_pct | Forward total log growth | Blocks |
|---|---:|---:|---:|---:|---:|
| huang-l435160 / crypto-15m-lab-0492e4 | 0.1287817413 | 240 | 26.86465 | -0.0471 | 7 |
| huang-h427345-2 / crypto-15m-prior-window-reset | 0.1287817413 | 240 | 26.86465 | -0.0737 | 11 |

Both passed replay. Their deflated Sharpe values differed: 0.182287 versus 0.211481. Compute spending was $0.21 and $0.71 respectively. Both deaths were administrative displacement, not recorded risk-limit deaths.

The living huang-hd8ff7c-3, in spot-impulse-lag, provides a related warning: replay return_pct 26.53095, 496 trades, Sharpe 0.074092 and deflated Sharpe 0.196044; forward total log growth -0.210687 over 10 blocks. Meanwhile the original huang-hd8ff7c is +0.010030 over 25 blocks. Family membership is not interchangeable evidence.

Replay percentage returns and forward log-growth totals are different measures over different samples; do not subtract them as a performance shortfall.

## What this establishes—and does not

The historical passes did not establish reliable forward profitability. Matching aggregates flag possible shared trades or reused historical evidence; they do **not** prove identical code, identical exposures, leakage, or a particular execution defect. Different deflated scores do not establish independent observations.

The available records do not explain the losses. Runtime limitations make execution worth checking: fills are bar-based, historical queue position and adverse selection are not calibrated, and historical Kalshi selection is limited to returned settled markets. These are audit targets, not diagnosed causes.

## Before spending on another related variant

1. Inspect existing archived artifacts first. Record code/configuration identity, replay interval, market universe, and entry/exit/settlement timestamps where available. Compare the two 240-trade results for shared market-time exposures. If artifacts cannot establish independence, mark it unverified rather than counting two confirmations.
2. Reconcile forward losses by market and completed exposure: signal timestamp, observed quote, simulated versus forward fill, fees, sizing, and reported settlement timing. Do not fill missing execution evidence with assumptions.
3. Fund a change only with a named discrepancy and a falsifiable prediction—for example, a timestamp correction must remove specifically identified stale entries. Renaming a family or rerunning the same history is not that prediction.
4. Freeze the selected version and evaluate new forward observations separately from development history. Use the existing completed-exposure schedule: at least 10 episodes, with looks every 5; retain all applicable House risk and promotion gates. Deduplicate shared exposures when assessing replication.

**Judgment:** another replay pass is not success. Report overlap, new completed exposures, after-fee results and concentration of losses. If the archive supplies neither a testable correction nor independent evidence, defer the fork rather than purchasing another historical confirmation.

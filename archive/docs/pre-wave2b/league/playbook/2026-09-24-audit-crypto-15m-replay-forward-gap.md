# Audit the crypto-15m impulse gap before another fork

## What was tried and what happened

The spot-impulse-lag descendant **huang-hd8ff7c-3** passed its reported replay with **496 trades, +26.53095% return, Sharpe 0.07409, and deflated Sharpe 0.19604**. Its post-mortem reports **11 forward blocks and -0.2550 total log growth**, with $0.38 compute spent. That log growth corresponds to approximately **-22.5% compounded return**; it is not a -25.5% simple return.

The living family does not rescue that result:

| Agent | Forward blocks | Total log growth |
|---|---:|---:|
| huang-hd8ff7c | 26 | +0.010030 |
| huang-hd8ff7c-2 | 11 | -0.017757 |
| huang-hd8ff7c-4 | 9 | -0.118596 |
| huang-hd8ff7c-5 | 2 | -0.009840 |

These are different members with potentially overlapping exposures, not independent replications. The two-block record is particularly immature. Nevertheless, the older member’s modest positive result is not evidence that its descendants retained an edge.

## What failed—and what remains unknown

A passing replay did not transfer into profitable forward performance for -3. It died by **displacement**, not a recorded loss-rule trigger; do not rewrite the cause of death.

The supplied summaries cannot establish whether the discrepancy arose from changed code, different market opportunities, execution assumptions, concentrated settlement losses, or a weak signal. Historical fills are bar-based, without historical queue-position or adverse-selection calibration. Those limitations warrant inspection, not an unsupported claim that execution caused the loss.

## Before spending more credits

1. **Inspect existing archives first.** Match the passing replay to its exact code, NEEDS, sizing, tape, and forward deployment version. If that linkage cannot be established, label the replay-forward comparison unverified; do not buy a parameter sweep to explain it.
2. **Reconcile completed exposures.** For -3 and the negative living descendants, tabulate contract, decision timestamp, underlying observation age, side, quoted and filled price, fees, size, settlement timestamp, and net outcome wherever recorded. Mark unavailable fields explicitly. Separate unresolved positions from completed losses.
3. **Identify shared losses.** Group by underlying and settlement window. Several descendants losing on the same event do not provide several independent observations. Do not add their log-growth figures into a fictional portfolio return.
4. **Require a falsifiable correction.** Name the observed failure and change one relevant mechanism. Without an identifiable correction or genuinely new evidence, defer another fork.

## How to judge the next justified test

Freeze the candidate and its expected effect before collecting new forward observations. Report after-fee completed-exposure results, concentration, and the measured discrepancy the correction was intended to reduce. Use the existing completed-exposure minimum of 10 episodes and applicable ladder gates; ten episodes alone do not establish profitability. Another pass on reused history is development evidence, not confirmation.
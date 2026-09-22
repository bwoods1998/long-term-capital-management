# Diagnose the failed gate before buying more trades

## What the records show

- **Leahy-16:** two replay trials, $0.36 compute, six closed trades, +1.75% reported replay return, deflated Sharpe **0.523**. The only reported replay failure was **six trades versus 20 required**. It was displaced at rung 0 without forward blocks—not killed by a forward trading loss.
- **Leahy-21:** seven trades, +1.95% return, deflated Sharpe **0.569**; again, only the trade-count gate failed. This is insufficient evidence, not a qualified edge.
- **Hufschmid-16:** two trials and $0.32 compute ended with 19 trades, negative out-of-sample growth and deflated Sharpe **0.001264**. One additional trade would address only one of three failures.
- **Hufschmid-17:** supplied replay results show **five trades, -8.2% return** and **58 trades, -63.11545% return**. Both fail out-of-sample growth and deflated Sharpe. The records omit parameter differences, so they do not establish that loosening a filter caused the loss. They do establish that exceeding 20 trades did not fix qualification.
- **Hilibrand-24:** **172 trades, +6.15% reported return**, yet out-of-sample growth was not above zero and deflated Sharpe was **0.01467**. Neither abundant trades nor positive headline return substitutes for the failed gates.

## Before the next paid experiment

1. **List every failure from the actual replay result.** Separate execution errors, insufficient blocks/trades, nonpositive out-of-sample growth, and inadequate deflated Sharpe. Do not diagnose from headline return or semantic research labels.
2. **For a count-only failure, preserve the candidate's rules.** Specify additional independent coverage that could test the same hypothesis. Use `replay_coverage` with complete proposed NEEDS before a sandbox replay. Coverage support does not promise enough closures or profitability; pending engineering requests are not available data.
3. **For economic failures, name a falsifiable economic change.** State what observable result would reject it. A proposal whose only target is “reach 20 trades” does not address negative out-of-sample growth or deficient deflated Sharpe.
4. **Do not manufacture closures.** Shorter holding or settlement opportunities are candidates only with an after-fee rationale, not a way to bypass evidence requirements. Never expose future settlement labels to decisions.

## Acceptance check

The next research proposal must identify the binding failures, the new information it will obtain, and its rejection condition. Replay qualification still requires 20 trades, 20 blocks, the required out-of-sample coverage and positive growth, and deflated Sharpe at least 0.5 under current policy. The separate five-trade policy field does not replace the replay minimum. A replay pass permits only the next authorized evaluation stage; it does not establish forward profitability.

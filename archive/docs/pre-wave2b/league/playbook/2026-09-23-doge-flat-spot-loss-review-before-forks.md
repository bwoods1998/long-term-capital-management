# DOGE flat-spot NO: review the loss before funding another fork

## What was tried and observed

`huang-h51fdd3`, family `crypto-15m-doge-flat-spot-no`, ran four replay trials and spent $0.67 on compute. Its last replay reported Sharpe 0.167023 and deflated Sharpe 0.500196, but only **five closed trades; ten were required**. That score did not cure the sample failure.

Forward, it accumulated **-0.2125 log growth over 11 blocks**. Its death record specifies **19.1% paper loss after six active blocks**, triggering the paper-loss rule. Eleven reported blocks and six active blocks are different denominators.

The living descendant, `huang-h51fdd3-2`, is at rung 2 with **-0.114182 log growth over 11 blocks**, approximately **-10.79% cumulative return**. The table does not give its active-block count, current gate, or trade ledger; it cannot establish that a particular death rule should already have fired.

## What this teaches

The parent's failure is an observed forward loss, not just a replay rejection. The descendant's negative record does not provide evidence that the approach has recovered. Neither record identifies whether signal calibration, entry prices, fees, exposure concentration, or execution caused the loss; do not invent that diagnosis from the family name.

Do not confuse the current **25% paper drawdown screen** with the separate **10% paper-loss death threshold after at least six active blocks**. The general death settings of 20 active blocks and 40% drawdown are not permission to wait through a paper-loss breach.

## Before spending more credits

1. Pause new forks and parameter searches in this family pending a loss review. A replay score near 0.5 or a rung-2 label is not contrary loss evidence.
2. Reconcile the descendant's current gate, active-block count, capital baseline, marks, fees, and reported settlements against the applicable controls. Escalate unexplained discrepancies rather than assuming the league table proves a control failure.
3. Use existing trade records to identify a falsifiable correction. Separate completed exposures from unresolved positions; document entry price, size, outcome, and net contribution.
4. Retest only with a named correction and new evidence. Meet current replay requirements, including ten closed trades, then judge fresh forward observations under unchanged risk limits. Reused history is development evidence, not recovery.

**Check:** no additional fork research without the reconciliation and correction hypothesis. If the available records cannot explain the loss, preserve credits; another replay cannot supply the missing ledger.

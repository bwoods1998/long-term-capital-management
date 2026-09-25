# Check the family record before buying another replay

## What was tried

Three Huang families contain profitable survivors alongside failed siblings:

| Family | Living agent: total log growth / blocks | Allocator's pooled family growth / active blocks |
|---|---|---|
| crypto-15m-doge-flat-spot-no | huang-h51fdd3-7: +0.058272 / 21 | -0.732450 / 55 |
| crypto-15m-lab-335592 | huang-l5aa23e: +0.176569 / 31 | -0.240716 / 44 |
| crypto-15m-spot-impulse-lag | huang-hd8ff7c-10: +0.034548 / 21 | -0.514808 / 71 |

These are separate reported aggregates, not matched-window comparisons. The September 25 promotion holds explicitly refuse new probes from these losing families. A clear pre-audit did not remove the holds.

The graveyard explains why selecting only survivors is unsafe:

- **huang-h51fdd3-4:** replay passed with Sharpe 0.1343 and 247 trades; forward total log growth was -0.0624 over 25 blocks. It died because its completed-exposure growth upper bound was below zero; compute cost was $0.15.
- **huang-l0c6f38:** nine replay trials, $0.58 compute, last replay passed with 775 trades. Forward total log growth was -0.0840 over 27 blocks; the separate paper screen reported a 10.1% loss after eight active blocks and killed it. Do not equate those two accounting windows.
- **huang-hd8ff7c-11:** last replay had four closed trades and no active out-of-sample block; forward growth was -0.0722 over 16 blocks. It spent $0.62 and was displaced, not killed by an evidence bound.

## What failed

Replay admission and sibling success did not establish transferable forward edge. Even huang-hd8ff7c-8's supplied trials include a passing -9.375% return, a failing +3.19% return because of OOS growth, and a passing +43.0452% return. The pass flag is a gate result, not a profitability ranking.

These summaries do not identify a particular entry-rule defect. They justify an evidence-allocation correction, not reversing trades or banning an entire niche.

## Before spending credits

1. Read the current promotion hold. Record its stage, pooled family growth, active blocks, and any reset time. Do not substitute a survivor's lifetime result.
2. For a losing-family hold, do not buy another replay merely to obtain a pass or unlock promotion. State a specific mechanism to test and what genuinely new observation would distinguish it from the failed variants. Otherwise defer spending.
3. Keep historical development results separate from new forward observations. Freeze the evaluated version; retain losses and displaced siblings in the evidence ledger. A renamed child does not erase family history.
4. Let the allocator judge eligibility. Its stated losing-family rule blocks probes at nonpositive pooled growth after six active blocks; clearing that blocker alone does not establish promotion readiness.

**Check:** Every funded proposal should name its blocker, evidence window, and falsifiable new observation. Repeated replay passes without new forward evidence must not be reported as family recovery.

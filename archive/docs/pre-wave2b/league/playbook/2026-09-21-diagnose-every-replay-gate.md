# Diagnose every replay gate before buying another variant

## What the records show

- **hilibrand-13:** two replay trials, $0.38 compute, no forward blocks before displacement. Its last replay had **190 trades, +10.7% reported return, Sharpe 0.0363, deflated Sharpe 0.0127**. It failed both out-of-sample growth and the **0.5** deflated threshold. Trade count was not the obstacle.
- **leahy-10:** two trials, $0.38 compute, no forward blocks before displacement. Its last replay had **four trades**, Sharpe **0.2178**, and deflated Sharpe **0.6284**. The historical threshold was 0.75; lowering it to that day's 0.5 would still have left the 20-trade requirement unmet (since Sept 22, 2026 21:25 UTC there is no deflated-Sharpe minimum and 10 trades are required).
- **hawkins-7:** a current replay reached deflated Sharpe **0.6945** and reported **+0.58%**, yet failed with **seven trades** and nonpositive out-of-sample growth. Earlier 0.5726 and 0.5728 scores also failed on trade count: four and eleven trades.
- **meriwether-25:** **+23.06215%**, 121 trades, and deflated Sharpe **0.2633** failed; another replay with **+19.42815%**, 73 trades, and deflated Sharpe **0.5255** passed. The supplied records do not identify the parameter changes, so they establish no recipe for reproducing that improvement.

These are gate diagnoses, not explanations of trading losses. Displacement is not an evidence-based trading death, and zero forward blocks mean no forward validation.

## Before spending again

Write a failure checklist from the actual replay report:

1. Closed trades: minimum **10** since Sept 22, 2026 21:25 UTC (**20** when this lesson was written).
2. Replay blocks: current minimum **20**; out-of-sample blocks: **8**.
3. Out-of-sample growth: must be above zero. Do not substitute the reported overall return.
4. Deflated Sharpe: no minimum since Sept 22, 2026 21:25 UTC (**0.5** when this lesson was written; reports using 0.75 describe an earlier gate). The trial count is still recorded. Read `qualification_policy.replay` for the rules in force.

For every failed item, state what new evidence the proposed expenditure could produce. More trades alone cannot repair hilibrand-13's measured out-of-sample failure. A higher deflated score alone cannot repair hawkins-7's insufficient sample. Do not widen entries merely to manufacture qualifying trades.

When coverage is the suspected constraint, check the complete proposed NEEDS with `replay_coverage` before paying for a selection trial. Coverage support does not guarantee enough trades or an edge.

## Acceptance check

Fund no rerun justified solely by positive reported return, a single passing statistic, or an obsolete threshold. Require a plan addressing every binding failure, then judge the result against all current gates. Meriwether-25 still has **zero forward blocks** in this snapshot: passing development evidence is permission to seek eligible forward observations, not proof of profitability or authority to scale.
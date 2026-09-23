# Stop replaying merely to obtain a pass

## What was tried

- **scholes-23, equity-overnight:** 11 replay trials, $1.29 compute. Its last replay had Sharpe 0.03855, 176 trades, and deflated Sharpe 0.28526 against a then-required 0.5. It recorded **-0.0006 total forward log growth over 28 blocks** before displacement.
- **scholes-22, equity-trend:** 13 agent replay trials, $1.02 compute. Its last replay had 348 trades but deflated Sharpe 0.000820 against **61 counted trials**, below the recorded 0.5 requirement. One forward block returned -0.0001 log growth. The agent-local trial count was not the entire selection burden.
- **krasker-5, options-breakout:** reported trials 15–19 all failed. Replay returns were -93.1%, -94.545%, -26.85%, -60.85%, and -50.875%. Trial 20 passed with 47 trades and +9.1%, but deflated Sharpe was only **0.001858**. Its forward table shows two blocks and zero total log growth—not corroboration of that selected replay gain.
- **scholes-h7dd043-2, morning-range-stops:** trials 7 and 11 reported the same Sharpe 0.068542, 59 trades, and +1.485850% return. Deflated Sharpe fell from **0.539669 to 0.347012**. Matching summaries do not prove identical code, but they do not establish independent confirmation either.

## What failed

Repeated historical selection did not produce convincing new evidence. More replay trades did not rescue scholes-22's selection-adjusted result; scholes-23's longer forward record did not corroborate a profitable edge. Their recorded death reason was displacement, not proof that every related strategy is unprofitable.

A current replay pass is a screening result. Today's policy allows deflated Sharpe as low as 0.0 and out-of-sample growth above -0.0005 per block, alongside coverage and trade requirements. Do not import the historical 0.5 gate as today's rule, or interpret today's pass as a profitability certificate. The runtime explicitly treats reused history as development evidence.

## Before spending another credit

1. Write down the proposed information gain: a specific code repair, mechanism change, new eligible coverage, or a reproducibility discrepancy. A desire for another passing result is insufficient.
2. Keep the failed trials, program version, data window, and available selection-wide trial count beside the selected result. Do not report only the winning run.
3. If nothing relevant changed, retain the candidate without another confirmation replay. Model turns also cost credits.
4. For an adopted candidate, freeze the version and collect new forward observations under existing gates. Separate elapsed blocks from active blocks and completed exposures; zero aggregate growth alone cannot identify inactivity or establish safety.

**Check:** the next research request must identify what new information it buys. Success is fewer redundant tests and auditable new forward evidence—not another green replay label. No forced turnover or automatic capital increase follows from this lesson.

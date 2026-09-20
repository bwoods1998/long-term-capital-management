# A replay pass qualifies a test, not an increase in risk

## What the records show

- **huang-4, crypto-15m-favorites:** replay passed at trial count 5 with 119 trades, 39.6585% return, Sharpe 0.215541 and deflated Sharpe 0.853355. Its forward record is **-0.156133 total log growth in seven blocks**.
- **huang-3, same family:** a supplied passing replay has 184 trades, 46.475% return and deflated Sharpe 0.876310 at trial count 4. Forward growth is **+0.016759 in nine blocks**. This does not validate huang-4; the horizons and possibly configurations differ.
- **haghani, crypto-alts-reversion:** forward growth is **+0.038542 in 20 blocks**, but its supplied replay failed with seven trades, -1.196090% return and deflated Sharpe approximately 0.000000298. Forward profitability does not erase replay failure either.
- In the graveyard, **hilibrand** had 189 replay trades but missed its recorded deflated-Sharpe requirement: 0.781730 versus 0.9. It subsequently accumulated -0.1093 forward log growth over 12 blocks and was displaced. That establishes a failed qualification followed by losses—not that passing would have prevented losses.

Replay returns above are percentages; forward figures are cumulative log growth. Do not subtract them or compare them as matched returns.

## What failed—and what remains unknown

Huang-4 is a direct counterexample to treating a statistical replay pass as sufficient evidence for successful forward deployment. The records do not establish whether the discrepancy comes from sampling, exposure, execution, market conditions or a changed implementation. They contain no configuration identifiers or matched replay/forward windows. Do not diagnose overfitting or an execution bug from these summaries alone.

## Before spending or increasing risk

1. Link the replay to the deployed configuration: code and parameter version, instruments, sizing, costs and evaluation window. If the link cannot be established, label the comparison **unmatched**, not validated.
2. For huang-4, do not use its replay pass to justify increased exposure. First inspect existing forward fills, fees, settlement outcomes and position concentration, and check for changes since the passing replay. This is a diagnosis request, not permission for another parameter sweep.
3. Keep huang-3's gains and haghani's gains attached to their actual deployed configurations. Neither family membership nor a positive agent-level total transfers validation to another version.

## Check

Every proposal to increase risk must show configuration-matched replay and forward evidence, including forward block count, exposure and losses. If matching or execution records are unavailable, defer the increase rather than buy another replay to manufacture confidence. No additional paid test is prescribed by this lesson.

# A replay pass is not profitability evidence

## Check the actual numbers

The current replay policy permits deflated Sharpe of 0.0 and out-of-sample growth above -0.0005 per block. Passing those minimums is not a positive-edge certificate.

- haghani-ra6e0c5 passed with 540 trades, Sharpe -0.08700, deflated Sharpe 0.0, and replay return -41.9448%.
- rosenfeld-h030d59 passed with 46 trades and replay return -8.9362%.
- In the graveyard, haghani-55 passed its last replay with 540 trades and Sharpe -0.08645, then recorded -0.0366 total forward log growth over 14 blocks. It died by displacement; the record does not establish a causal connection between its replay and forward losses.

Conversely, a positive aggregate replay return can conceal an out-of-sample failure: meriwether-laa6e18 returned +40.64165% across 64 trades but failed the out-of-sample growth gate. Aggregate replay return and out-of-sample growth are different measurements.

## Repetition is not replication

Three crypto-alts candidates—haghani-rfc8131, haghani-r64a707, and haghani-r71f56f—each reported 207 trades, Sharpe approximately -0.0353313, and return approximately -9.357035%. Their trial counters were 132, 133, and 135. These summaries are effectively identical, though the supplied records do not prove identical code or trades.

A directly repeated result also appears for hilibrand-h6ca596-2: trials 24 and 25 both show 34 trades, Sharpe 0.1670296, and +4.64% return. The deflated score changed from 0.01999 to 0.01650; no additional observations are established by those summaries.

## Research spending rule

Before another paid rerun, record the candidate version, data window, declared inputs, and the specific difference from the previous test. If nothing material changed, reuse the archived result. If results are numerically indistinguishable, inspect available trades and configuration before claiming a new experiment.

Report qualification status separately from aggregate return, out-of-sample growth, and forward completed-exposure results. Where out-of-sample details are missing, request the existing result breakdown rather than infer profitability from `passed: true`.

A negative aggregate replay does not alone prove every possible future use fails. It does mean that a pass alone cannot justify additional research or capital. Any proposed retest must state what changed and how fresh observations could falsify the proposed improvement.

Judge compliance by fewer unchanged reruns and explicit evidence separation. Do not change House gates, force turnover to meet trade counts, or treat renamed siblings as independent confirmation.

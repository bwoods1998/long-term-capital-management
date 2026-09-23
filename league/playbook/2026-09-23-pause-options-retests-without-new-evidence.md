# Pause options retests until the evidence changes

## What was tried

The latest options-pullback deaths were not merely short samples:

| Agent | Replay trials | Last replay trades | Sharpe | Forward log growth |
|---|---:|---:|---:|---:|
| krasker-7 | 3 | 100 | -0.26446 | 0.0000 / 1 block |
| krasker-8 | 2 | 144 | -0.02282 | -0.0566 / 1 block |
| krasker-9 | 1 | 21 | -0.22718 | -0.0151 / 1 block |

All three last replays failed the reported requirement for positive out-of-sample growth. Together they spent $3.42 of compute. Their recorded death reason was displacement, not a statistically established trading failure; nevertheless, these records provide no positive basis for another similar research purchase.

The surviving options-breakout agent krasker-5 continued testing. Trial counters 14–17 reported returns of -7.2%, -93.1%, -94.545% and -26.85%, respectively. Trials 15 and 16 had no active out-of-sample block despite 14 and 19 total trades. Trials 14 and 17 failed the newer out-of-sample growth floor of -0.050% per block. Its two forward blocks total zero log growth, which does not counter those failures or establish that executable opportunities occurred.

## What failed—and what remains unknown

More total trades did not produce acceptable out-of-sample results. Other attempts lacked out-of-sample activity entirely: these are different failure modes, not reasons to keep sweeping the same parameters.

The current runtime explicitly has **no historical option-chain replay**. Do not interpret a replay's trade count as proof that historical contract selection, option quotes or executable spreads were validated. This limitation does not prove what caused the reported losses. The supplied summaries cannot separate signal error, sizing, costs and execution assumptions.

## Before spending again

1. Inspect the existing failed run. Record the out-of-sample dates, active blocks, closed trades, costs and the option-pricing/execution assumptions actually used. Label unavailable diagnostics as unavailable.
2. State one falsifiable change addressing an observed failure. Another threshold sweep without a diagnosis is not new evidence. Missing activity calls for checking eligible opportunities and coverage, not automatically loosening entry rules.
3. Check the complete proposed NEEDS with `replay_coverage` before a sandbox replay. Coverage support does not add historical option chains. Separate an underlying-signal test from any claim about option-contract profitability.
4. Resume only when the proposed test can evaluate the stated change on supported inputs. If it depends on missing chain history, document that dependency and stop; do not claim it has been implemented.

## How to judge the next attempt

Require the diagnosis, changed hypothesis and coverage result before approving another replay purchase. Judge the outcome against the current out-of-sample activity and growth requirements, retaining unsuccessful trials in the research record. Any permitted paper observation must separately establish actual contract selection and execution; neither a smoke pass nor zero forward growth earns additional capital.

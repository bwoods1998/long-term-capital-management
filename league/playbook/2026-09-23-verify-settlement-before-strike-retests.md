# Verify settlement before more crypto-strike retests

## What was tried

The crypto-strikes-vol-shock-upside agent, **hilibrand-h6ca596**, has three supplied replay records:

| Trial counter | Reported trades | Replay return | Rejection |
| --- | ---: | ---: | --- |
| 7 | 0 | 0.0% | Too few trades; no active out-of-sample block; undefined deflated Sharpe |
| 8 | 2 | +0.2% | Fewer than 10 closed trades |
| 9 | 48 | -3.895% | Positions lack a completed settlement within the recorded scoring window |

These records do not establish that the same code ran each time. They do establish that increasing the reported trade count did not resolve settlement eligibility. The agent's forward record is **-0.359321 total log growth over seven blocks**; that is neither a drawdown statistic nor proof that missing settlements caused its losses.

The graveyard also contains **hilibrand-37**: 175 replay trades and positive Sharpe of 0.01875, yet out-of-sample growth failed the -0.050%-per-block floor. Volume, positive aggregate Sharpe, and completed settlement are separate questions.

## Why the latest evaluation failed

The House waits for reported `settlement_ts` before releasing Kalshi cash. Unknown settlements remain unresolved and cannot qualify. A reported trade count therefore does not, by itself, establish enough completed settlement evidence for the exposure being evaluated.

The supplied records do not identify whether the latest failure came from late settlement, absent settlement records, or a scoring window ending too early. Do not choose a repair before distinguishing these cases.

## Before spending again

1. Inspect existing records for each affected position: market identifier, entry time, scheduled close, reported settlement timestamp, scoring-window end, and unresolved status. If these records are unavailable, name that missing evidence rather than infer settlement from market close.
2. Count qualifying closed trades, active out-of-sample blocks, and completed exposure episodes separately. Current replay requirements include 10 trades, 20 blocks, and eight out-of-sample blocks; the completed-exposure policy separately requires at least 10 episodes. Do not substitute one count for another.
3. Only rerun after identifying a supported window that includes the required settlements, or documenting a concrete strategy change that addresses the failure. Do not force turnover. Shorter settlement opportunities are useful only if their after-fee edge survives.
4. Treat DVOL availability separately: BTC/ETH volatility history is already replayable, but this does not supply missing strike settlements. Do not request a redundant volatility adapter or assume an unimplemented daily-ladder request has been fulfilled.

## How to judge the next result

Freeze the candidate and record the settlement-coverage finding before testing. Require documented completed exposures and the applicable replay gates; then judge profitability on new forward evidence. Another high trade count, smoke pass, or replay return alone does not resolve this failure.

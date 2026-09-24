# Check sports opportunity before tuning entry thresholds

## What was tried

Sports-central-under-demand agent meriwether-h42bdbb-2 spent $1.62 across 18 replay trials. Its last replay passed with ten trades, Sharpe 0.531476 and deflated score 0.953426. Forward, it recorded only one block and +0.0005 total log growth. It died stuck: 30 consecutive wakes with a live market present, no action, and too few credits to research its way out.

Its predecessor spent $3.66 across five trials, passed with 31 trades, and recorded -0.0372 forward log growth over two blocks before displacement.

The living meriwether-h42bdbb-3 has one forward block at zero growth. Its supplied replay fails with only three closed trades against ten required, despite +1.3282% return and Sharpe 0.201081.

## What failed

The second agent qualified historically but did not sustain actionable forward opportunities before its budget ran low. The records do not reveal whether this was correct abstention, missing inputs, event matching, restrictive filters or an order-path fault. A live market is not necessarily an eligible trade.

Consequently, paying to improve Sharpe or loosening filters to manufacture ten trades is the wrong next diagnostic.

## Before spending again

Inspect existing wake records and the current strategy's complete input requirements. Account for the funnel from listed markets to:

- supported series and matched event;
- available, sufficiently fresh inputs;
- valid event phase and settlement horizon;
- entry signal after costs;
- permitted order, submission and fill.

Record counts and explicit rejection reasons. If the records cannot distinguish these stages, the next change should add that visibility rather than change the signal. Do not force an order when no after-fee opportunity exists.

Use `replay_coverage` with the complete proposed `NEEDS` before a paid replay. Current sports scoreboard recording began September 23 and has about 25.2 hours of history. Hour-horizon feed replay is now possible subject to declared-key coverage; day-horizon eligibility is listed for October 13. This does not supply an in-season historical price/settlement panel, guarantee eligible events, or fulfill the blocked sports-data requests.

## How to judge it

A further research proposal must identify the binding stage and predict what its change will alter. A coverage deficiency calls for recording or waiting; an implementation fault calls for a reproducible repair; correctly rejected prices call for abstention.

Evaluate a repaired candidate with a frozen configuration, reporting eligible events, rejection reasons, fills, settlements and after-fee results. Zero growth alone proves neither inactivity nor safety. Diagnose the inactivity run before repeating the predecessor's 30-wake failure, while preserving the House's actual qualification rules.

# Audit runline losses before funding another fork

## What was tried

The sports-runline-leverage-tax family has four negative forward records:

| Agent | Forward blocks | Total log growth |
| --- | ---: | ---: |
| meriwether-hadd32b | 2 | -0.3011 |
| meriwether-hadd32b-2 | 1 | -0.0482 |
| meriwether-42 | 1 | -0.065511 |
| meriwether-hadd32b-3 | 1 | -0.003650 |

The first agent spent $1.90 across six replay trials. Its last replay passed with Sharpe 0.169954, deflated score 0.452120 and 60 trades. The second spent $0.23 across two trials; its last replay had only one closed trade against ten required. Both died by displacement, not a recorded performance-death trigger.

The living third-generation-name successor, meriwether-hadd32b-3, moved from a zero-trade failed replay at trial 7 to a passing trial 8: 13 trades, +3.44265% return, Sharpe 0.436975 and deflated score 0.993684. Its forward result remains negative after one block.

## What failed—and what remains unknown

A replay pass did not protect the ancestor from a large forward loss. The newer high deflated score does not explain or repair that loss.

These short, potentially overlapping records do not prove the entire family lacks an edge. Aggregate results also cannot distinguish bad pricing, correlated exposure, excessive sizing, execution mismatch or settlement effects. Do not claim any one of those causes without the trade records.

## Before spending again

Pause additional runline forks and parameter searches until the existing records can answer:

1. Which settled positions and marks account for each agent's loss?
2. What were entry price, side, size, fees and event identity?
3. How much exposure shared the same game or outcome driver?
4. Which recorded forward conditions differ from the replay assumptions?

House replay has no historical queue-position or adverse-selection calibration. A maker-fill explanation therefore needs forward evidence, not another bar-based replay alone.

Fund a successor only with a named observed failure and a change designed to address it. Freeze its configuration and evaluation plan before observing new outcomes. Retain all House gates; this lesson grants no additional capital.

## How to judge it

Require a reconciled loss breakdown and a testable repair before another paid trial. Judge the repair on new, event-grouped, after-fee forward results and exposure concentration. Another favorable score on reused history is not evidence that the original loss mechanism disappeared.

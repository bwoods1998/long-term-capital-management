# Audit runline losses before funding another fork

## What was tried

The sports-runline-leverage-tax family produced these records:

| Agent | Replay evidence | Forward total log growth | Blocks |
|---|---|---:|---:|
| meriwether-hadd32b | Last replay passed: Sharpe 0.16995, deflated 0.45212, 60 trades | -0.3011 | 2 |
| meriwether-hadd32b-2 | Last replay had only 1 closed trade; 10 required | -0.0482 | 1 |
| meriwether-42 | Replay not supplied here | -0.065511 | 1 |
| meriwether-hadd32b-3 | Replay not supplied here | -0.003650 | 1 |

The first two died by displacement, not by a demonstrated statistical rejection. They spent $1.90 and $0.23 of compute respectively. The first agent's -0.3011 log growth corresponds to approximately -26.0% compounded growth, not -30.11% arithmetic return.

## What failed—and what remains unknown

A passing replay did not protect the original candidate from a large forward loss. Its successor supplied too little replay trading to substantiate a repair. Both currently listed family members also have negative forward growth.

This warrants pausing additional forks, not declaring the mechanism universally unprofitable. The records do not identify entry prices, fees, correlated positions, settlements, or which code version generated each exposure. One- and two-block records do not satisfy the current family evidence requirement of at least five active blocks per qualifying member. Do not pool these agents as independent experiments or sum their log growth into a portfolio return.

## Before spending again

1. Reconstruct the original loss from existing order and settlement records: event, side, entry price, size, fees, exit or settlement, and strategy version. Separate realized losses from open marks.
2. Attribute loss by event and by exposure size. Check whether several positions depended on the same game. Concentration, execution error, and signal failure are hypotheses to test—not established causes.
3. Name one repair and the observations that would falsify it. A renamed fork, wider price band, or higher replay Sharpe is not a repair.
4. If the necessary records are unavailable, record that dependency and defer further optimization rather than inventing an explanation.

## How to judge a repair

Keep the repaired version fixed and use only House-authorized risk. Log newly completed exposures, event concentration, fees, and total forward growth. Use the existing completed-exposure review schedule: minimum 10 episodes, then looks every five. That minimum permits assessment; it does not establish an edge or override other gates. Do not scale from another replay pass alone.

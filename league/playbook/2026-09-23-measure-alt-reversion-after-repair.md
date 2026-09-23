# Alt reversion: the repaired child still needs an economic case

## What was tried

The graveyard identifies `haghani-51` (`haghani_venue_grid_child`) as the correction for the defect carried by `haghani-38` and `haghani-45`. Both predecessors were superseded for that reason; their forward records were zero cumulative log growth over two and one blocks respectively.

The corrected child now has its own evidence:

| Agent | Last replay | Forward record | Compute |
|---|---|---|---|
| haghani-51 | Passed; 540 trades; Sharpe -0.08645; deflated 0.00006769 | 12 blocks; log growth -0.0436 | $0.38 |
| haghani-52 | Passed; 570 trades; Sharpe -0.08766 | 12 blocks; log growth -0.0417 | $0.44 |
| haghani-53 | Passed; 539 trades; Sharpe -0.08632 | 12 blocks; log growth -0.0375 | $0.37 |

The latter two are related family observations, not identified venue-grid controls. All three died by displacement, not a recorded risk-limit breach. Repeated paragraphs in their post-mortems are not additional observations.

## What this establishes—and does not

Haghani-51's forward loss is approximately 4.27%, using `exp(-0.0436) - 1`. Fixing the identified implementation defect did not demonstrate profitability. A replay pass also did not establish positive expected growth: its reported Sharpe was negative.

There is no matched before/after experiment here. The predecessors' short, flat records do not prove they were safer, inactive, or economically superior. Nor can these summaries identify whether fees, signal direction, execution, or position sizing caused the repaired child's loss.

Do not generalize this into a universal family rejection. Living `haghani-56` has +0.016472 log growth over four blocks, while `haghani-55` has -0.036551 over six. Different candidates and short, potentially overlapping records are not independent confirmations.

## Before buying another experiment

1. Start with existing haghani-51 records. Attribute gross trading P&L, fees, execution costs where observable, and open-position marks by symbol and completed exposure. If those records are unavailable, mark the cause unresolved; do not invent a diagnosis.
2. State whether the proposal fixes execution or changes the economic hypothesis. An execution repair must pass its regression check, but that is not evidence of alpha.
3. For another economic test, specify the observed loss component it addresses and freeze the comparison window, sizing, cost assumptions, and stopping rule before spending. Do not rerun unchanged logic merely to obtain another pass.

**Judgment:** a repair is successful when its defect is demonstrably removed. Further research funding requires a separate, falsifiable economic case. Positive after-fee forward evidence must come from the corrected candidate's own record; it cannot be inherited from a repair name or replay status.

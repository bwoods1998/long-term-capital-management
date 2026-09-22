# Check replay duplicates before spending

## What was tried

Repeated descendants in the attention-favorites, crypto-15m-favorites and crypto-reversion families produced matching failed replay summaries:

| Agents | Matching evidence | Reported compute |
|---|---|---|
| leahy-20 / leahy-24 | 9 trades; Sharpe −0.07042300094; deflated Sharpe 0.01172880656 | $0.31 / $0.21 |
| huang-17 / huang-18 | 45 trades; Sharpe −0.02817298817; deflated Sharpe 9.070242168e−9 | $0.28 / $0.27 |

All four died by displacement with zero forward blocks. Count each agent once: repeated prose inside a post-mortem is not another experiment. These costs are total reported agent compute, not isolated replay fees or proven avoidable spending.

The pattern continues among living agents. Leahy-25 matches leahy-24's replay: 9 trades, −2.2% return and the same Sharpe and deflated score. Rosenfeld-26 and rosenfeld-27 each produced 6 trades, −0.2282171031% return and Sharpe −0.01168633705. Their deflated scores were 0.01040791 and 0.00994872 against 25 and 26 trials; neither qualified.

## Why this did not establish progress

A new agent name or generation does not make reused history new evidence. These results still fail the same gates: insufficient trades where applicable, nonpositive out-of-sample growth and deflated Sharpe below 0.5. None of the four dead agents supplied forward validation.

Matching aggregates do **not** prove identical code, decisions or tape. They justify checking archived experiments before buying another test. The records do not reveal which parameter changes, if any, generated these matches.

## Before the next paid experiment

1. Compare the proposed candidate with the closest archived failure: code/configuration, complete NEEDS, tape/window, execution assumptions and available decision or trade records. Agent identity alone is not a meaningful difference.
2. If inputs and behavior are equivalent, reuse the recorded result. Do not present it as an independent observation or reset selection accounting by creating a descendant.
3. If inputs differ but outputs match, identify whether the changed branch ever affected an eligible decision. Fund another replay only with a written hypothesis about a specific behavioral difference, genuinely new coverage, or a necessary reproducibility check.
4. For rosenfeld-26/27, explain how the proposed test addresses six closed trades versus twenty required **and** nonpositive out-of-sample growth. A smaller loss alone solves neither gate. Do not force turnover to fill the quota.

## Check next pass

Every funded rerun should identify its nearest archived result and why reuse was insufficient. Record equivalent tests skipped, actual credits spent and distinct observations obtained. Success is less spending on redundant failures—not a higher generation number or an unchanged historical result labeled as new evidence.

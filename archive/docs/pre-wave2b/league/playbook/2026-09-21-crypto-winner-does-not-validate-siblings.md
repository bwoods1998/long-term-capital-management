# A crypto-15m winner does not validate its siblings

## Forward evidence, not just displacement

Three crypto-15m-favorites agents died on paper evidence:

| Agent | Paper loss at death | Active blocks | Total forward blocks | Compute spent |
|---|---:|---:|---:|---:|
| huang | 10.7% | 21 | 45 | $2.89 |
| huang-3 | 13.0% | 11 | 34 | $1.34 |
| huang-5 | 16.7% | 10 | 28 | $1.05 |

Their total log growth was -0.1130, -0.1392, and -0.1823 respectively. These are trading failures, unlike a displaced candidate with no forward observations. Active blocks and total forward blocks are not interchangeable.

The living siblings disagree sharply: Huang-6 has +0.206767 total log growth over 15 blocks and is on rung 2; Huang-7 has -0.142786 over 16 blocks. The table does not supply matching configurations, active-block counts, or exposure histories, so it cannot establish which design difference caused the divergence.

## Replay search has not repaired Huang-7

Its listed trials 24–26 returned -95.514%, -97.30265%, and -97.72635%. Trial 27 produced zero trades. Trial 29 returned +19.6045% across 338 trades, but deflated Sharpe was only 0.000051, so it still failed. Trial 31 returned -4.1% with 110 trades and deflated Sharpe about 7.39e-11, far below that day's 0.5 threshold (there is no deflated-Sharpe minimum since Sept 22, 2026 21:25 UTC; out-of-sample growth must still be positive).

Neither a zero-trade configuration nor one positive historical return establishes a recovery. These records do not identify whether forecasts, entry prices, sizing, or execution caused the losses.

## What to do differently

Before funding another crypto-15m variant, write one candidate-specific repair hypothesis and the observation that would reject it. Do not justify the expense solely with Huang-6's family membership or another threshold sweep.

For a candidate that earns forward eligibility, freeze the tested configuration and record its own after-fee results, active blocks, completed exposures, and loss-limit checks. Use existing House risk gates; this lesson grants no live allocation and does not relax the paper-death rule of 10% loss after at least ten active blocks. Do not infer a missed enforcement action from Huang-7's aggregate table alone.

**Judgment:** a repair must clear current replay requirements and then produce new, separately attributed forward observations without breaching applicable risk limits. A profitable sibling, an inactive variant, or a selected positive replay does not satisfy that test.
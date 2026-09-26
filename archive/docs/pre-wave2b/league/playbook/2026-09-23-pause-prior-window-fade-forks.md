# Pause prior-window fade forks until forward losses are explained

## What was tried

`huang-h6d3302`, the ETH prior-window-fade agent, ran three replay trials and spent $0.71 on compute. Its last replay passed: 151 trades, Sharpe 0.032013, deflated Sharpe 0.331593. It then recorded **-0.0603 total forward log growth over nine blocks**. Its recorded death reason was displacement, not a statistical finding that the strategy was irreparable.

The living records reinforce the research concern:

| Agent | Family | Blocks | Total log growth |
|---|---|---:|---:|
| huang-h6d3302-2 | ETH prior-window fade, generation 2 | 9 | -0.049818 |
| huang-h609d6f | Prior-window fade | 11 | -0.058859 |

These are log-growth figures, not percentage returns. The records do not establish independent samples, matched exposure, or identical code. Do not pool their blocks into a significance claim.

## What failed—and what remains unknown

A passing historical replay did not establish a profitable forward fade. The child also has negative forward evidence; another generation number is not a remedy.

The supplied summaries cannot distinguish a genuinely unprofitable signal from timestamp mistakes, stale inputs, expensive execution, or settlement handling. They also do not establish that buying the opposite side would win after costs.

This is not a verdict against the entire niche: spot-impulse-lag has +0.004669 over eleven blocks and prior-window-reset has +0.001470 over ten. Those small positives are not proof of an alternative edge. Reset also has a supplied replay with -89.4201% return and an out-of-sample-growth failure.

## Before spending another research credit

1. Pause parameter-only forks of the prior-window fade. First inspect existing records; do not buy another replay merely to recover a pass.
2. Reconstruct the completed trades: prior-window boundaries, signal availability time, target contract window, entry quote and fill, fees, and reported settlement. Check explicitly that the prior window was complete and observable before entry.
3. Name one falsifiable explanation. A timing repair must demonstrate the offending timestamps and the corrected ordering. An execution explanation must reconcile quoted opportunity with realized after-cost results. If the necessary records are absent, report that gap rather than inventing a cause.
4. Only then propose a materially justified revision. Retain the losing baseline and predeclare the comparison before gathering new observations.

## How to judge the next attempt

Require distinct forward completed exposures, with after-fee results and unresolved positions reported separately. Follow the House's applicable gates; its completed-exposure path requires at least ten episodes. Shared contracts across siblings are not independent confirmations. Another development pass, a renamed child, or zero-growth blocks do not resolve this failure.

## Lab prior

The Alpha Lab reads this block (`league/lab.py` `priors`, Sept 23, 2026): no parameter-only fork of a lineage grown from this family until the lineage's own forward window is positive. Luna's and Sol's rewrites, which change the mechanism, still come.

```lab-prior
{"rule": "pause-param-forks", "family": "prior-window-fade", "until": "forward-positive"}
```

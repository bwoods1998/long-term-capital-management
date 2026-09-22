# Options: establish a validation route before buying another variant

## What happened

| Agent | Family | Replay trials | Forward blocks | Total log growth | Compute spent |
|---|---|---:|---:|---:|---:|
| krasker | options-breakout | 0 | 3 | -0.0101 | $2.07 |
| krasker-2 | options-pullback | 0 | 3 | -0.0050 | $2.66 |
| krasker-3 | options-pullback | 0 | 1 | -0.0151 | $2.43 |

Together they spent **$7.16 in compute**, separate from trading losses. All three were displaced with the explanation that a replay-passing deferred candidate had priority over an untested mutation. These were not performance-threshold deaths. Their short forward records do not establish that either family is structurally unprofitable.

The records do not expose their exact strategy changes or show attempted replay errors. Do not invent a failed parameter experiment or attribute every dollar to replay.

## The capability constraint

The current runtime explicitly reports **no historical option-chain replay**. An OPRA feed is configured, but feed configuration does not establish historical chain coverage. Implemented Alpaca warmup and daily execution clocks do not supply missing option contracts, quotes, or execution histories.

Thus, zero replay trials are not automatically a problem another parameter mutation can solve. Replaying the underlying alone would not validate the option contract's execution or returns.

## Before spending again

1. Check current runtime support. If proposing a replay, submit the complete proposed NEEDS to `replay_coverage` before a paid sandbox or selection trial. A coverage check does not override the documented chain-replay limitation.
2. State precisely what can be tested: underlying signal, option selection, option execution, or complete strategy returns. Do not label the first as the last.
3. Obtain a House-confirmed permitted validation route before funding another options variant. Specify the evidence it can produce and a spending limit. Do not assume an exemption from qualification or authority to modify the core engine.
4. If no route exists, defer further variant research. Model turns consume credits even without replay purchases; repeating an unsupported research plan is not free.

## Checkable outcome

The next options proposal must identify supported validation and actual data coverage before research spend. Otherwise it remains deferred. Any permitted forward evaluation must report its own completed exposures and losses; neither a runtime smoke pass nor a few forward blocks establish a trading edge.

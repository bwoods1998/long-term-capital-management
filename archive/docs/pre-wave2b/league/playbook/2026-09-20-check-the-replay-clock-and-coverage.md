# Check the replay clock and data coverage before interpreting its score

An observed September 20 research pass blamed a 30-bar daily feed for an idle strategy. The live data path actually returned 210 bars; the research preview had silently displayed only the last 30. `markets_now` now reports actual coverage, preview counts, and history dates. A display limit is not a trading-input limit.

The following replay limitations were reproduced against the current implementation:

- Main Alpaca replay honors the declared bar timeframe. It is not universally five-minute data. But its decision clock advances on those bars, with no separate intraday execution clock or pre-window warmup. Daily equity bars produce midnight wakes, while the shipped daily seeds require regular-session decisions. Extending the tape alone did not make the overnight seed trade. Do not remove a market-session guard merely to make an invalid clock produce fills.
- Earlier Kalshi tapes dropped candles between the last grid observation and trading close. The same source candles could hide a losing resting fill on a coarse grid. New tapes preserve that final range as execution history, without an extra strategy wake. Historical replay scores still describe their original simulator.
- Event replay still pays at trading close rather than independently recorded settlement time. It also omits the resolution-time hint from strategy context. Cash reuse and resolution-sensitive rules therefore need better evidence.
- Options replay is a current-snapshot smoke check, not a historical profitability test.

Before retrying, name the input and clock your hypothesis needs, check what the test actually supplies, and record any mismatch in the journal and tool request. A zero-trade or winning result from an unsupported experiment does not establish an economic conclusion. Keep session constraints, costs, and earlier trial history; report a changed simulator as a changed experiment, not independent confirmation of the old score.

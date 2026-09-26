# Matching replays are not independent confirmation

## What was tried

The weather-favorites family produced two passing agents with exactly matching headline replay results:

| Agent | Trades | Return | Sharpe | Counted trials | Deflated score |
|---|---:|---:|---:|---:|---:|
| mullins-2 | 44 | 15.5% | 0.36060968185484843 | 6 | 0.949582 |
| mullins-6 | 44 | 15.5% | 0.36060968185484843 | 10 | 0.899812 |

Both passed. These numbers do **not** establish that the implementations or trades are identical, but they require an artifact comparison before anyone calls the second result replication. Mullins-2 has two forward blocks and +0.014347 total log growth; mullins-6 has zero forward blocks. There is not yet a second forward record confirming the result.

The graveyard supplies two accounting warnings:

- **Scholes-5:** two local replay trials, but its final evaluation counted twelve. Its 331-trade replay returned +6.1395%, yet failed out-of-sample growth and scored only 0.252913 against a 0.75 deflated threshold. A new agent name did not reset the evidence burden.
- **Meriwether-8:** replay passed with 70 trades and a 0.955397 deflated score, then the agent was displaced with zero forward blocks. This was a capacity outcome, not an observed forward trading loss.

## Why this matters

Counting passing descendants as separate confirmations can exaggerate support without adding observations. Conversely, counting every graveyard entry as a failed trading thesis discards a replay-passing candidate that never received a forward test. Neither agent count nor survival status measures independent evidence.

The current runtime explicitly classifies reused history as development evidence. Different deflated scores alone do not identify a strategy improvement; trial accounting also differs here.

## Before spending another credit

1. Compare archived candidate code/configuration, declared inputs, replay window, execution settings, and fill/settlement records. Matching summary statistics are a flag to inspect—not proof of duplication.
2. Record separately: local runs, evaluator-counted trials, and which observations are genuinely new. Use the evaluator's count; do not substitute the child's local count.
3. If a descendant uses the same history, label its result development evidence even when parameters changed. Do not purchase a duplicate run solely to obtain another passing agent name.
4. Preserve the passing candidate's artifacts when displacement occurs. Treat it as proposed, not adopted, until the House records adoption or forking. Do not infer forward success or failure from zero blocks.

## How to judge the change

The next weather-family research report should explain whether the two 44-trade results share fills and history, without requiring another replay. Any claim of independent confirmation must identify new observations and the exact candidate evaluated. Until then, report two matching passes—not two independent validations.

# A live sports feed is not a backfilled props tape

## What failed

Sports-props-favorites agent **hufschmid** ran 14 replay trials and spent **$2.87**. Its last replay produced **7 closed trades, 17 blocks, Sharpe -0.1519**, and nonpositive out-of-sample growth. The recorded gates then required 20 trades and 20 blocks. Three forward blocks reported zero log growth; that does not establish whether there were fills.

**hufschmid-29** spent **$0.48** over four trials. Its last replay had **1 closed trade, 13 blocks, Sharpe 0.2774**, and nonpositive out-of-sample growth. It had no forward blocks. Both died by displacement, not a demonstrated forward-loss threshold.

These records show inadequate replay samples and failed growth tests. They do not establish that coverage was the sole cause or that more observations would reveal an edge.

## What has actually changed

As of **2026-09-23T03:51:29Z**, the House supports `NEEDS['feeds'] = {'sports': ['nfl', 'mlb']}`. Sports rows contain current-board status, scores, clock, start time, records, and sportsbook lines. They are recorded by receive time and supplied point in time.

Recording began **2026-09-23T01:30:43.380Z**; only **2.3 hours** were available. Declared feed keys each need 20 recorded horizon blocks before replay is supported. The reported earliest eligibility is **September 23 at 21:30:43.380Z for hour strategies**, or **October 13 at 01:30:43.380Z for day strategies**, subject to actual coverage.

This is not historical player-prop bid/ask data paired with settlements, an in-season August backfill, or a player-statistics feed. Those backlog requests remain unimplemented. League support also does not imply every Kalshi series is mapped.

## Before spending again

1. State the exact new decision the scoreboard enables—for example, rejecting entries unless a mapped game's observed status is pre-game. Do not describe that filter as a proven edge.
2. Check `runtime_status`, then `replay_coverage` with the complete proposed NEEDS. Identify missing keys and symbols individually.
3. Handle absent `ctx['feeds']`, missing rows, stale receive times, and unmatched events explicitly. Do not invent status or substitute today's board for historical observations.
4. Do not repeatedly request replay before coverage matures. Unsupported feed input is not a selection trial, but model turns still spend credits.
5. Once supported, inspect closed trades, blocks, and out-of-sample growth under the **current** policy. Its replay minimum is 10 trades and 20 blocks; the older 20-trade failures are historical evidence, not today's rule.

**Check:** The next feed-dependent research proposal must include its coverage result, availability timestamp, missing-input behavior, and one falsifiable decision change. Twenty hours of recording is permission to test—not twenty trades, evidence of edge, or permission to deploy capital.

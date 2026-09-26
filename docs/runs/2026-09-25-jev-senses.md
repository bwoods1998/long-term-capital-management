# Jev as the swarm's senses — September 25, 2026

Execution record for the owner's goal of Sept 25, 2026: execute
[the Jev plan](../goals/LTCM_JEV_SENSES.md) autonomously, with no deadline, beside the forward-first run
([its record](2026-09-25-forward-first.md) on `run/forward-first-2026-09-25`), the options run
([its record](2026-09-25-options-desk.md) on `run/options-desk-2026-09-25`) and the Kalshi-scale run
([its record](2026-09-25-kalshi-scale.md) on `run/kalshi-scale-2026-09-25`), until its Done list holds.

## The clock

- **T0:** 2026-09-25T06:16:40Z (the session's first `date -u` after reading the plan).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Windows:** no deploy 13:25-20:05Z on a trading day (Friday Sept 25, Monday Sept 28), none while a
  game a real Kalshi family holds is in play (Friday's MLB slate runs to about 03:00-05:00Z Saturday),
  one deploy at a time across the four runs, never inside another release's canary or watch, never within
  30 minutes of another run's announced deploy.
- **Progress notes:** a scoreboard reading and a short state note every four hours from T0 (10:17Z,
  14:17Z, 18:17Z, ... Sept 25) in "Progress notes" below, and a line at every deploy.

## The owner's message (Sept 25, 2026, at T0)

- The /goal text arrived as the plan's last section without its first bullet (the "Execute ..." and
  "Direction" lines); the three bullets received are "Coordinate", "Authority" and "Method" verbatim.
  **Read as** the plan's own copy of the message: execute the plan until its Done list holds.
- **Authority:** the forward-first plan's "Authorized" list applied to this run's workstreams (J0-J5):
  implement, test, merge with CI green, owner and gateway deploys outside the windows above, spend funded
  compute and align caps up to funded balances. Jev never gets order, promotion, spending or merge
  authority. Nothing in "Not authorized": no back-filled or fabricated evidence, no cap above funded
  money, no test orders. **No money rule changes**, so this run never moves the grant's digest and never
  ratifies. No owner steps.
- **Funded Jev money:** the owner stated about $25 in the TypeSafe account (Sept 25). The gateway's Jev
  line read $16.230245 spent at 06:22Z, so funded lifetime is about $41.23 against the gateway's
  `TYPESAFE_PILOT_USD` cap of $42: $0.77 above funded money. The next gateway deploy lowers it to $41.

## The owner's wrap-up (Sept 26, 2026, about 01:26Z)

Across all four runs: finish soon, start nothing new. Build nothing further; ship only what is already built,
reviewed and CI-green, in the order B (forward-first, once tonight's last two real MLB games settle), G
(options), C (forward-first), **D-J2 with its J5 gateway deploy (this run)**, K2 (Kalshi, the scale rule
switched off); each 30 minutes after the previous watch, never while a real family's game is in play, never
13:25-20:05Z on a trading day; a run not ready passes its slot. Then: verify on the box, a final scoreboard,
anything needing a later market window recorded as a named window after the run with its numbers,
README/operations/memory, merged worktrees and branches removed (unmerged work pushed, never deleted), the final
PR of this record, the report with the owner's decisions; then stop.

**Read as:** D-J2 ships #349 (J3, its hook, the move feed switched off, two idle jobs off: built, reviewed on
its PRs; CI on the fixed head) and J5's gateway ships #304 (built; reviewed before it ships, since it had no
independent review yet); J4's event features are not built (blocked, with the numbers); the move feed's serve
switch, J3's arm report and the Jev shadow's cut become windows after the run.

## The first hour's decisions

1. **The plan to main.** PR #303 (docs only: a release tree holds `league/`, `ltcm/`, `scripts/`,
   `playbooks/`, `deploy/`, so the updater ships nothing for it), merged 06:25Z (`19c3771`).
2. **How this run's changes reach the box.** The updater reads `main` every 30 minutes and ships any new
   release tree, and it refuses a tree whose `league/config.json` moved a key that is not an operating
   dial (`league/ci.py` `CONFIG_DIALS`: `tick_seconds`, `mark_every_seconds`, `replay_days`,
   `inference_daily_cap_usd`). The `jev` block is not a dial: **every change to it is an owner deploy**
   (`scripts/floor_box.py deploy`), and merging one to `main` ahead of that deploy would make the updater
   refuse main's head for every run. So this run merges a House change only in its own announced slot,
   immediately before its own owner deploy. Gateway changes never ride the updater.
3. **J0's cap change goes with J1**, in one owner deploy (D-J1), rather than costing the House a restart
   for a cap alone: the daily pool rises from $0.25 / 400 calls to $1.50 / 25,000 calls, split gate 3,000,
   triage 1,500, links 1,000, exposure 500, move 19,000 (a ceiling each, not an allowance).
4. **J1 is recorded before it is served.** D-J1 ships only the recorder (point-in-time rows in its own
   store, `jev-features.sqlite`, starting at the newest snapshot: no back-fill). No strategy sees the
   feature until its held-out AUC on post-ship events meets the plan's 0.70 line; then the serving hook
   goes through `league/feeds.py` with the Kalshi run's agreement, after its K1 merges.
5. **Builders (06:21Z):** the J1 analyst (read-only, the Sept 20-22 lab data: which of the eight features
   carry the move lift, whether a free market-type table explains it, the frozen model) and the J1 builder
   (worktree `~/Work/ltcm-j1-move`, branch `j1/move-recorder`: `Sensor.ask_state`, `league/jev_features.py`,
   the `JevFloor` hook, the `jev` block, tests).

## Coordination with the other three runs

This run follows the options plan's "Coordination" section across four runs, as the plan says: before each
merge and deploy it reads the other three records (current waves, file owners, announced deploys); it edits
no file another run's current wave owns; one deploy at a time across the four, none 13:25-20:05Z on a
trading day, none while a real Kalshi family's game is in play (except a rollback), never inside another
release's canary or watch, never within 30 minutes of another run's announced deploy. It changes no money
rule. Whichever run deploys the gateway later rebases on the earlier gateway deploys and re-runs every
gateway test. Messages to another run are lines here, a comment on its open PR, and a direct message to
its session.

**This run's files and deploys (kept current):**

| Wave | State | Files owned |
|---|---|---|
| J0 + J1 (D-J1, owner deploy) | deployed 11:50:48Z (#319) | `league/jev.py`, `league/sensors.py`, `league/semantic_lab.py`, new `league/jev_features.py` and `league/jev_move_model.json`, `league/config.json`'s `jev` block only, `league/tests/test_jev_*.py` |
| J5 (gateway) | after the options run's and the Kalshi run's gateway deploys | `gateway/lib/typesafe.mjs` (the `score` answer), `TYPESAFE_PILOT_USD` in `gateway/wrangler.jsonc` (to $41), `gateway/test/` Jev cases |
| J1 serving (with J3 in the next deploy, switched off) | #327 (draft, base `k1/integration`; read by the Kalshi run, two checks being fixed) | one small hunk in `league/feeds.py` (a live internal feed `move`, never polled), `league/jev_features.py`, `league/sensors.py`, one line each in `league/FEEDS.md` and `league/CONTRACT.md`; `"serve": false` in the model file until the ship rule passes |
| J3 (next deploy) | built and reviewed, #322 (draft); its `researcher.py` hook #328 (draft, base `k1/integration`) | new `league/jev_memory.py` and `league/tests/test_jev_memory.py`; `league/jev.py` (`choice` answers), `league/sensors.py` |
| Hooks (J1 serving, J3's research block) | after their owners' waves merge | one hook each in `league/feeds.py` (Kalshi run, after K1) and `league/researcher.py` (J3's prior-results block in `_state`; the Kalshi run's I1 owns the file), each a small PR read by the owner run first. J2 builds no hook in `research_gate.py` (no Jev pre-filter earned its keep); J3 needs none in `lab.py` |

- **The Kalshi run's answers (06:29Z):** J1's serving hook `ctx["feeds"]["move"]` is agreed as a small
  PR after K1 merges, posted on its K1 PR for a read first, registered as a `Source`-style entry beside the
  existing ones, keeping `league/feeds.py`'s point-in-time rules (a key never recorded is absent, never
  zero; `t` stamped when the feature was computed), rebased on its I2 hunk (`league/open_feeds.py` into
  `RECORDERS`) if that has landed. J4 after I2 (its Deploy K2). Its gateway `web_fetch` deploys before this
  run's gateway change. D-J1 never within 30 minutes of K1.
- **Not touched by this run:** the allocator, families, book, constitution, grants, live trading, the
  seat market, `house.py` (the `JevFloor` hooks it already calls are enough), the strategies and seeds of
  any desk (J1's first users are children written with each desk's owner run), the options desk.
- **Announced deploys:** **D-J1** (House owner deploy: J0 caps + the J1 recorder; no money-digest
  change). **Agreed slot (06:27Z, both runs' answers):** Friday Sept 25 **12:15-12:55Z** if the options
  run's Deploy V ends its post-promotion watch by 11:45Z (start at least 30 minutes after V's written end;
  not started if the canary and watch could run past 12:55Z); if V ends later or is rolled back, Saturday
  Sept 26's quiet window after forward-first's Deploy B and the options run's Deploy G, before the Kalshi
  run's K2. The options run writes "D-J1 slot: open" or "D-J1 slot: Saturday" in its record. Nothing of
  this run's merges to `main` before forward-first's Deploy A or the options run's V; the merge happens in
  the slot, immediately before the deploy. After promotion: `live_trading.active` and the money digest
  checked unchanged (forward-first's request). Its exact start is written here first.
  **D-J2 (House owner deploy; Saturday Sept 26 about 09:00Z, the order forward-first proposed at 14:45Z and
  this run accepts):** B 06:00Z, the options run's G about 07:00Z, forward-first's C about 08:00Z, **this run's
  D-J2 about 09:00Z**, then the Kalshi run's before about 15:30Z; each starts 30 minutes after the previous
  watch ends. D-J2 carries J3 (#322), its `researcher.py` hook (#328) and J1's serving hook switched off (#327),
  both retargeted to main after K1, and Jev's exposure groups and hypothesis links switched off. **J5's gateway
  deploy** (#304) follows D-J2's watch in the same slot, rebased on the options run's and the Kalshi run's
  gateway changes, with every gateway test re-run. (22:25Z: forward-first moves B up to the moment the real
  family's last two games settle, about 04:30-05:30Z; the order is unchanged, so D-J2 starts 30 minutes after
  forward-first's C's watch ends, whatever the clock.)
  **10:31Z: today's slot is closed** (the options run: the usage-limit outage delayed Deploy V past 11:45Z).
  D-J1 goes in Saturday Sept 26's quiet window after forward-first's Deploy B and the options run's Deploy G,
  before the Kalshi run's K2.
  **11:10Z: reopened.** The options run's Deploy V promoted at 11:08:45Z and its watch ended "promoted" at
  11:18:45Z, so by the agreed terms the slot is open from 11:48:45Z, finished before 12:55Z. **D-J1 planned
  start: 11:50Z** (PR #319 only: J0 + J1; J3 is not ready), on three conditions: CI green on the rebased head
  `18d4b3f`, a pre-deploy blocker check clean, and no game a real Kalshi family holds in play (none before the
  evening MLB slate). If any fails, or the canary and watch could run past 12:55Z, it moves to Saturday. **Gateway (J5 + the cap to $41):** after the other runs' gateway deploys.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main | done 06:25Z (#303, `19c3771`) |
| 0.3 | J0 baseline | done 06:25Z (below) |
| J0 | Caps into one $1.50 daily pool | built in #319 (config, per-purpose breaker), ships in D-J1 |
| J1 | Move sensor | analysis done (the free model is served, Jev a shadow); recorder built in #319; ships in D-J1; post-ship evaluation after 24 h of rows; serving after K1 + AUC >= 0.70 |
| J2 | Filters in front of research, Merton, replays | measured offline: no Jev filter earns its keep; free findings sent to forward-first (10:36Z); nothing built |
| J3 | Shared memory | building (`j3/memory`): index + taxonomy, three-arm retrieval (control / free / Jev), graveyard query, report |
| J4 | News, scores, filings; market discovery | market map done (#318); event features wait for the Kalshi run's I2 recorders (K2) |
| J5 | Gateway `score`; named answer problems and opt-in partial answers; cap to $41 | built, #304 (draft); after the other gateway deploys |

## The scoreboard at T0 (J0 baseline)

Read-only on the box at 06:17-06:25Z Sept 25: `jev.sqlite`, `health.json` `jev`, the ledger's
`research.gate` rows (24 h to 06:20Z), the gateway's `typesafe` block (`scripts/gateway_admin.py status`).

| # | Metric | Reading at T0 | Target |
|---|---|---|---|
| 1 | Jev calls a day; dollars a day; cache hit rate | Sensor calls Sept 22 / 23 / 24: 358 / 370 / 326 (every per-purpose cap reached daily except exposure; Sept 25 to 06:17Z: 210, links already at its 60), $0.020 / $0.018 / $0.018 a day; cache hit rate Sept 24 70.7% (2,434 cached answers served against 1,010 questions bought). Outside the Sensor: researchers' `classify` tool 44 / 137 / 193 calls a day Sept 22-24, charged to the agents at cost. Gateway lifetime: $16.230245 over 139,568 calls (136,308 of them the semantic lab's Sept 20-22 burst) | ≥ 10,000; ≤ $1.50; ≥ 50% |
| 2 | Gate decisions made without Jev because a cap bound | 127 sessions in 79 `research.gate` rows with `:jev_unavailable` (116 skipped, 11 sampled) of 4,765 gate decisions; only 20 runs were woken by a Jev-relevant note | 0 |
| 3 | The move sensor's held-out AUC ("moves at all", 15 min) | 0.757 (lab, Sept 22, executable rows, unseen events); no live recorder | ≥ 0.70 on post-ship events |
| 4 | Strategies using a Jev feature; their adverse-selection loss against their parents | 0; none | ≥ 3; lower |
| 5 | Research + Astra dollars a day | $98.19 (Luna $38.58 + Astra $59.61, the forward-first scoreboard's 24 h to 04:23Z); the plan's reading $77.34 (research lane $48.62 + consultant $28.72, the Sept 25 gap review) | ≥ 30% lower, yield not lower |
| 6 | Research sessions handed Jev-retrieved prior results; their abstention against control | 0; 2,561 finished research sessions in 24 h, 566 with a candidate (22%) | all; lower |

**Row 4's baseline: what adverse selection costs the Kalshi makers now** (06:32Z; buy fills of event
contracts Sept 22 00:00Z to 06:31Z Sept 25 from `book.fill`, marked with the held side's midpoint from the
recorded market snapshots the strategies were shown, `recordings.sqlite` `markets:*`, 14,522 snapshots; a
markout is value 15 minutes after the fill (first snapshot 15-25 minutes later) less the fill price, times
the contracts; fills with no snapshot in that window are not marked, e.g. most 15-minute crypto markets,
which settle first):

| Book | Liquidity | Category | Fills | Marked at 15 min | 15-min markout | Per marked fill |
|---|---|---|---:|---:|---:|---:|
| practice | maker | crypto | 134 | 36 | −$100.01 | −$2.78 |
| practice | maker | weather | 127 | 118 | −$41.39 | −$0.35 |
| practice | maker | sports | 34 | 22 | −$5.47 | −$0.25 |
| practice | maker | other | 104 | 64 | −$38.24 | −$0.60 |
| practice | taker | sports | 150 | 115 | −$9.99 | −$0.09 |
| real | maker | crypto | 60 | 35 | −$0.54 | −$0.02 |
| real | maker | weather | 35 | 31 | +$0.22 | +$0.01 |
| real | maker | other | 5 | 5 | −$1.08 | −$0.22 |
| real | taker | sports | 22 | 15 | −$0.83 | −$0.06 |

Practice makers gave back $185 in 15 minutes on 240 marked fills (the practice book fills a resting quote
when a venue trade prints through it, so its makers are picked off by construction); real makers, at
$5-10 stakes, $1.40 on 71. That is the pool the move sensor can shrink, and the comparison J1's acceptance
makes (users against their parents) uses this same markout.

Other J0 readings: the gate's lifetime totals run 6,182, sample 1,350, skip 11,994 (Jev cost $0.023); in
the 24 h window `abstain_lock` skipped 2,590 sessions without asking Jev at all (the lock admits only the
agent's own venue outcomes). Triage reads 1,768 ledger rows behind the head (cursor 672,259 of 674,027);
hypothesis links read 9,132 behind (cursor 664,895; 2,234 mechanisms indexed, the 60-call cap binds every
day). Exposure's cap (40) was not reached on Sept 24 (25 calls, 1,931 cached answers).

## Findings

### J1 on the development data (07:28Z): the move lift is market type, and a free model beats Jev

The J1 analyst re-ran the Sept 22 evaluation on the semantic lab's own store (read-only extract of
`semantic.sqlite`, 128,246 labelled states Sept 20-22, all development data) and reproduced it exactly (lab
numeric 0.609 / 0.616 / 0.661; + 8 Jev answers per state 0.765 / 0.757 / 0.750, AUC for "the mid moves at all"
at 5 / 15 / 60 minutes, executable rows, test events never seen in training, 95% intervals from a 300-rep
event-clustered bootstrap). Then the ablations, on identical rows:

| Arm (15 min) | AUC [95%] |
|---|---|
| lab numeric (mid, spread, log OI, hours, drift) | 0.616 [0.570, 0.663] |
| + 8 Jev answers per state (the lab) | 0.757 [0.716, 0.790] |
| + a free 5-way category table from the series prefix (no Jev) | 0.735 [0.684, 0.772] |
| + 6 static Jev answers asked once per market | 0.705 [0.651, 0.748] |
| rich free numeric (19: time since the mid last moved, 60-minute range, abs drift, tight and pinned flags, volume, ...) | 0.829 [0.796, 0.851] |
| rich free + series table | 0.837 [0.809, 0.859] |
| rich free + series + 8 Jev per state | 0.838 [0.809, 0.859] (difference [−0.002, +0.003]) |

- **Most of Jev's lift is the market's type:** a free category table recovers 98% / 84% / 89% of it at 5 / 15 /
  60 minutes, and the series explains 97-98% of the variance of three of the static answers.
- **Jev adds nothing over a better free model** at any horizon (intervals straddle zero), within weather and
  within sports, on fresh rows, on series never seen in training and with the history thinned to 5-minute
  spacing. Crypto alone shows +0.002 to +0.007 at 5 minutes. Direction stays unpredictable (0.52-0.57).
- **The served model** (`move-v1-20260924`, 23 free features: the lab's 5, 13 more from the state and the
  recorder's own minute quotes, 5 category flags; logistic, fitted on fresh development rows): held-out
  0.859 / 0.829 / 0.806, against the lab's numeric + 8 Jev at 0.769 / 0.760 / 0.683 on the same basis. It costs
  $0 of Jev. The lab states carried no rules text (all 129,025 had empty `rules_primary`), the same shape as the
  live snapshots.
- **Cost of the Jev designs at the live load** (4,509 markets a day, 95,734 market-states a day at a 5-minute
  cadence, $0.000106 a state): per-state labels about $10 a day (7x the pool); static answers once per market
  about $0.48 a day.

**What J1 ships instead of the plan's Jev feature:** the free model as the served feature (`move_p5/15/60`),
and Jev only as a recorded SHADOW (`jev_p*`: the free features + the 6 static answers once per market, and the
two new "will it move within 15 / 60 minutes" questions on a paced sample of states), capped at $0.75 a day, so
the post-ship evaluation can say whether Jev adds anything on data it has never seen. If it does not after
3 days of post-ship events, the shadow is cut to $0. Both are validated on post-ship events before any
strategy reads them (the plan's 0.70 line applies to the served feature).

### J2 on the research gate (10:31Z): Jev does not pick the sessions worth paying for; a free model does

The J2 analyst built 6,846 finished research sessions Sept 22 00:00Z to Sept 25 06:00Z from the ledger (read-only),
each with its "new since the agent's previous session" evidence (its own fills, settlements, refusals, verdicts,
niche notes and lessons, fulfilled requests, inactivity, its previous conclusion; nothing at or after the start),
asked Jev one frozen question per session ("does this item contain decision-relevant NEW evidence that could
change what a researcher would conclude or build?", phrasing chosen on Sept 22-23 only), and scored it against
what the session produced: a retained candidate (o1) and a replay pass within 2 h (o2). Thresholds were chosen on
Sept 22-23; the held-out window is Sept 24 00:00Z to Sept 25 06:00Z; intervals clustered by agent. Jev spend $0.088.

| Held-out AUC for a replay pass (o2) | All gate runs + refusal fast path (2,697, $98.63) | Sessions forward-first's F2 would still run (1,228, $39.05) |
|---|---|---|
| Jev's p | 0.650 [0.613, 0.682] | 0.715 [0.674, 0.748] |
| trigger kind alone (free) | 0.790 [0.749, 0.826] | 0.856 [0.823, 0.887] |
| record class alone (free) | 0.852 [0.816, 0.881] | 0.885 [0.851, 0.914] |
| free logistic (kind, streak, record, previous outcome, fills, hours since last) | 0.860 [0.828, 0.885] | 0.896 [0.864, 0.925] |
| free logistic + Jev | 0.859 [0.828, 0.884] | 0.893 [0.861, 0.924] |

- **Jev's pre-filter fails the plan's bar:** at the threshold that keeps replay-pass loss under 10% on Sept
  22-23, it skips 5% of held-out dollars on F2's survivors (3% on all runs), far from 30%.
- **The free model meets it on F2's survivors:** 63% of sessions and 32% of dollars skipped for 8% of replay
  passes and 11% of candidates lost. Jev adds nothing on top.
- Sessions woken by the agent's own fills or settlements rarely produce anything (AUC 0.22 on F2's survivors,
  i.e. they predict NO candidate): F2 keeps them as triggers. That is for the forward-first run's F2/F4, which
  owns the gate; this run passes the numbers on and builds no Jev research pre-filter.

**The Merton half (10:35Z)**: 497 Merton passes Sept 22 00:00Z to Sept 25 06:00Z, $174.78 (plus 20 auditor
verdicts, $4.29). What each role produced:

| Role | Passes | Dollars | Produced nothing (passes / dollars) |
|---|---:|---:|---|
| consultant | 112 | $59.25 | 23 / $9.01 (89 wrote code; 30 led to a candidate that passed replay) |
| architect | 54 | $44.18 | 43 / $31.77 |
| engineer | 207 | $28.10 | 155 / $16.98 |
| teacher | 38 | $16.85 | 11 / $4.35 (27 lessons) |
| foundry | 43 | $11.45 | 7 / $1.10 (36 cards) |
| toolsmith, operator, designer | 43 | $14.95 | 42 / $14.19 |

Five Jev questions over each pass's REQUEST text (before the answer), one chosen on Sept 22-23: the best ("the
problem is already known or answered") scores held-out AUC 0.736 [0.649, 0.810] for "produced nothing"; the role
alone scores 0.771 [0.689, 0.839]; both 0.787. At the train-chosen cut the role saves $12.11 of the held-out $76.11
(4% of useful passes lost), role + Jev $12.57, Jev alone $8.13 (12% lost). Jev spend for both halves: $0.113 (675
calls, all completed).

**J2's verdict:** no Jev pre-filter is built for research or Merton: on held-out data neither earns its keep over
free rules. Two free findings go to the forward-first run, which owns the gate, Merton and the lanes (F2, F4, Y):
on the sessions F2 still runs, a trigger-kind skip cuts 31% of dollars for 9% of replay passes; and the architect,
toolsmith, operator and designer roles produced nothing on 85 of 97 passes ($45.96 of $59.13). Sent 10:36Z.

### J4 market discovery (07:32Z): what Kalshi trades that the swarm cannot price

Kalshi's public API at 07:15Z: 131,970 open markets in 4,132 series; 1,654 series with ≥ 100 contracts in 24 h
(59.31M contracts). Jev classified each series' settlement mechanics and which recorded feed could price it
(`choice` questions, $0.141; it agreed with the deterministic prefix rules on 97.0% of mechanics and 89.4% of
feeds). Kalshi desks cover 208 series, 53% of the volume, and 20.4M contracts of that covered volume have no
recorded feed pricing them. The largest near-term volume with no feed: WTA matches 10.03M, DP World Tour 3.06M
(all within 48 h), ATP matches 2.85M (2.80M within 48 h), T20 cricket 1.07M, international friendlies 0.62M, UFC
0.26M, F1 0.19M: ESPN's public scoreboards cover these sports, but the House's sports map does not. Sent to the
Kalshi run at 10:31Z.

### J1's ship rule, written before the post-ship data is read (12:22Z)

The evaluation command ran once at 12:21Z as a smoke test of the pipeline on the first 30 minutes of rows (it
works; those rows are too few to decide anything and the reading is not the decision). The rule, fixed now:

- **Data:** rows recorded from the recorder's start (11:52:51Z), outcomes from its own minute quotes,
  `python -m league.jev_features evaluate --cutoff 2026-09-25T11:52:51Z` on the box, read-only.
- **When:** the first decision read at least 24 hours after the start (not before 11:53Z Sept 26), and only
  if the "unseen events" population at 15 minutes (events never in the fit and never seen before the cutoff)
  holds at least 200 events. Otherwise it waits and reads again every 12 hours.
- **Serve the feature** (the `ctx["feeds"]["move"]` hook) only if, on that population at 15 minutes, the
  served model's AUC has its 95% event-clustered lower bound at or above 0.70 (stricter than the plan's point
  estimate), and on the lag <= 120 s population the point estimate is also at or above 0.70.
- **Per desk:** a strategy of a category (crypto, weather, sports, finance, other) may read it only if that
  category's own point AUC at 15 minutes is at or above 0.70 on at least 30 unseen events.
- **Jev's shadow** earns a place in the served model only if the Jev increment (shadow minus served, paired)
  has its 95% lower bound above zero on the same population; otherwise the shadow's spend goes to $0 after
  3 days of post-ship rows (Monday Sept 28 11:53Z).

### Which uses of Jev earned their keep (14:44Z; read-only, Sept 22 00:00Z to Sept 25 14:40Z)

| Use | Jev volume and cost | What it produced | Verdict |
|---|---|---|---|
| Research gate note relevance | 683 calls, $0.039 | 170 extra sessions ($5.24 of research): candidate 8.3%, replay pass 4.7%, the same as the gate's random 10% sample of would-be skips (6.6% / 4.5%, n 1,481) and a fifth of the free triggers (about 23%); $0.66 of research per replay pass against $0.16-0.19 for free triggers | **No value; costs research dollars.** D-J1's higher cap let it wake 4 sessions in its first 3 h (0 in the same hours before). Sent to forward-first 14:44Z; **its answer (14:45Z): a `research.gate.jev_relevance` dial, default false, ships in its Deploy C (Saturday); the cap stays** |
| Triage bug classifier | part of 408 calls, $0.027 | 96 bug groups; 13 reached Merton's engineer ($2.06), 7 verified (against audit's 14 of 164 and refusals' 6 of 26); the fixes are child strategies with 8 fills, −$11.00 | **Earned its keep as a cheap engineering feed; no trading value yet** |
| Triage request merges | 176 pairs asked | 27 aliases, but every merged name stays its own worklist job; 0 engineer passes | No value |
| Hypothesis links | 291 calls, $0.009 | 541 links (28 rewording); 0 cards grouped, blocked or retired; `failure_history` has no caller | No value |
| Exposure groups | 101 calls, $0.003 | 0 pairs at the 0.7 line; no consumer reads it | No value (no consumer) |
| Researchers' `classify` tool | 515 calls, $0.084 charged to 111 agents | Raw lift (replay pass 20.8% vs 12.4%) vanishes when sessions are matched on cost (87 vs 92 expected) | Cannot tell (confounded; no lift once effort is controlled) |
| J1 move shadow | 1,963 calls, $0.175 (Sept 25) | recorded beside the free served model | Cannot tell yet (the ship rule's read) |
| Semantic lab (Sept 20-22, off) | $6.20 since Sept 22 ($13.93 in all) | the Sept 22 move result, which a free model matches | No value over free features |

Everything measured to earn its keep so far is free: the gate's deterministic triggers, the audit and refusal
reporters, the free move model. The only Jev use with a positive reading is triage's bug classifier, and its
dollars are cents. Cut-backs this run proposes for its next deploy: exposure and hypothesis links off (no
consumer, no effect); the gate's relevance question is dropped by the gate's owner in its Deploy C.

## Progress notes

- **10:32Z (T0 + 4 h 16 m; the 10:17Z note was late: a usage limit stopped this session and its agents
  07:30-10:30Z, the other three runs too).** J0 done; J1's development analysis done (the free model is the
  feature, Jev a capped shadow), the recorder built and reviewed (no blockers; eight should-fix items and the
  model integration in progress); J2 research half measured (no Jev pre-filter; the free model goes to the gate's
  owner), Merton half in progress; J4 discovery done; J5 built (#304, draft, waits for the other gateway
  deploys). D-J1 moved to Saturday's window. Jev spent by this run so far: $0.23 of the gateway line (analyses
  from the Mac); the House's own Jev line is unchanged (still capped at $0.25 a day until D-J1).

- **14:03Z (T0 + 7 h 46 m; the 14:17Z reading, early).** D-J1 has run 2 h 10 m with no alert: the move sensor
  holds 10,222 rows over 1,429 markets (cycles 2-16 s, none refused since the first), no research-gate decision
  made without Jev since the restart (the old cap bound 127 a day), no breaker opened. Scoreboard: (1) Sensor calls
  today 2,077 by 14:02Z (gate 230, links 101, triage 76, exposure 7, move 1,663), $0.169 spent, cache hit rate 22%
  (move's once-per-market labels are mostly new markets; triage 48%, exposure 99%); the gateway's Jev line
  $16.669 over 142,838 calls (+$0.157 since 11:09Z). The plan's 10,000-calls-a-day target assumed per-state Jev
  labels; J1's evidence moved that spend to $0 (a free model), so the run will not buy calls to meet it. (2) 0
  gate decisions without Jev since 11:52Z. (3) J1 post-ship AUC: not read until the ship rule's first read (not
  before 11:53Z Sept 26). (4) 0 strategies use a Jev feature (serving is off by rule). (5) Research + Astra
  dollars: no Jev filter (J2); forward-first's F2 carries the free cut. (6) J3 not deployed (#322, #328 wait for
  K1 and a slot). Open PRs: #304 (J5), #322 (J3), #327 (J1 serving), #328 (J3 hook). Next House deploy: Saturday's
  window after forward-first's B and the options run's G.

- **22:19Z (T0 + 16 h; the 18:17Z note was missed: nothing needed action between 16:45Z and 22:15Z, and the
  watch was quiet).** The move sensor ran through two other runs' restarts (the options run's 16:39Z, the Kalshi
  run's K1 at 20:54Z) without an alert: 56,021 rows over 3,424 markets by 22:15Z, cycles 2-24 s, no refusal, no
  breaker, 0 gate decisions without Jev. Jev spend today $0.474 (move $0.443 of its $0.75); the gateway's Jev line
  $16.980 over 146,524 calls, +$0.750 since T0 (House about $0.47 today, this run's offline analyses about $0.26).
  Runway at today's pace (about $0.60 a day once the move sensor's first-day labelling burst passes; $0.75 + $0.20
  + the gate's and triage's cents at the caps): the ~$24.25 left of funded money lasts about 30-40 days; at the
  $1.50 pool's ceiling, 16 days. K1 merged 20:22:34Z; forward-first merged its Deploy B (#334) to main at 22:18:39Z
  and asked that nobody owner-deploy main before its B at 06:00Z (it holds B's money rules unreleased); this run's
  D-J2 stays at about 09:00Z. Done by 22:23Z: #322 rebased on main, #327 and #328 moved onto main and
  retargeted, and the three integrated as **#349** (`dj2/integration`, one docstring conflict in
  `sensors.py` resolved; every touched test module passes locally; CI on the PR). One local test depended on
  the Mac's free /tmp (the recorder's own 2 GB disk guard tripped during the test's set-up); made independent.
  **CI on #349 failed (22:33-22:35Z; seen 01:23Z):** two tests outside the touched set (`test_fast_research`'s
  cache layout, `test_pacer`'s idle brief) call `Researcher._state` on a stand-in `self` with no `_prior_block`.
  Fixed on #328 (`7def9f49`: the block is called through the class), re-merged (`9f07dd80`), and every module
  that calls `_state` re-run locally (researcher, fast_research, pacer; hypotheses' `_state` is another
  class). Lesson: a signature change's test set is every caller's module, found by grep, not the touched ones.

## Deploy log

- **D-J1 (House owner deploy; J0 + J1; no money rule).** Pre-checks: CI green on `18d4b3f` (rebased on the
  options run's V, `0d46e90`); a pre-deploy blocker check found none (93 touched tests pass; the model
  coefficients byte-identical to the analysed fit); the live grant active, pinned and running money digest both
  `535a7f15` (read-only, 11:25Z). #319 merged 11:29:26Z (`2ee015b`, on top of Merton's #321, a Hilibrand child
  strategy merged 11:28:05Z that the updater had not shipped: it rides this deploy). Merged ahead of the start on
  purpose: the updater's next check would otherwise launch #321 alone inside the slot; with the `jev` block on
  main it refuses the head instead, and the owner deploy ships both. (At 11:41:05Z the updater, now the release
  train, held main's head `main-785ead7f257a` for its 4-hour spacing, so no updater release was in flight.)
  **Started 11:49:11Z** from `~/Work/ltcm-deploy` at `origin/main` `2ee015b`: release
  `20260925T114915Z-007e06151f53` (704 files) staged 11:49:19Z, **promoted 11:50:48Z**, `ops.started` 11:51:59Z,
  the watch's verdict **promoted at 12:00:50Z** (every reading ok, no reasons, 0 error alerts). After promotion
  (11:59:48Z, read-only): the live grant active, pinned and running money digest both `535a7f15` (unchanged);
  `health.json` `jev.sensor` daily cap $1.50 / 25,000 calls; the move sensor's first cycle at 11:57:59Z: 17
  snapshots, 415 markets shown, 415 rows (the served model `move-v1-20260924` ready, the shadow ready), 382 Jev
  calls for $0.034 (400 static labels asked, stopped by the 60 s budget), lag p50 163 s; the Jev step 0.16 s of the
  tick; no alert. Four `research.gate` rows written 11:50-11:56Z still carry `:jev_unavailable`: aggregated skip
  episodes opened before the restart under the old 150-call cap, flushed after it. **The recorder's post-ship
  clock starts at 11:52:51Z** (`started_at`): no row before it exists, and none will be back-filled.

- **The options run's mid-session owner deploy (the owner's choice; 16:09Z notice):** practice structure
  founders, about 16:40-17:00Z, carrying main as it is (nothing of this run's is unshipped on main). One House
  restart: the move sensor resumes from its cursor (snapshots older than two intervals give quotes, not rows).
  This run checks the sensor after it.

## Report

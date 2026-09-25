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
| J0 + J1 (D-J1, owner deploy) | building | `league/jev.py`, `league/sensors.py`, `league/semantic_lab.py`, new `league/jev_features.py` and `league/jev_move_model.json`, `league/config.json`'s `jev` block only, `league/tests/test_jev_*.py` |
| J5 (gateway) | after the options run's and the Kalshi run's gateway deploys | `gateway/lib/typesafe.mjs` (the `score` answer), `TYPESAFE_PILOT_USD` in `gateway/wrangler.jsonc` (to $41), `gateway/test/` Jev cases |
| Hooks (J1 serving, J2, J3) | after their owners' waves merge | one hook each in `league/feeds.py` (Kalshi run, after K1), `league/research_gate.py` (forward-first F2, after Deploy B), `league/lab.py` (forward-first F1, after Deploy B), each a small PR read by the owner run first |

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
  **10:31Z: today's slot is closed** (the options run: the usage-limit outage delayed Deploy V past 11:45Z).
  D-J1 goes in Saturday Sept 26's quiet window after forward-first's Deploy B and the options run's Deploy G,
  before the Kalshi run's K2. **Gateway (J5 + the cap to $41):** after the other runs' gateway deploys.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main | done 06:25Z (#303, `19c3771`) |
| 0.3 | J0 baseline | done 06:25Z (below) |
| J0 | Caps into one $1.50 daily pool | built with J1 (config), ships in D-J1 |
| J1 | Move recorder | building; model analysis running |
| J2 | Filters in front of research, Merton, replays | offline evaluation first; hooks after F2 |
| J3 | Shared memory | after F1 |
| J4 | News, scores, filings; market discovery | with the Kalshi run's recorders |
| J5 | Gateway `score`; cap aligned to funded money | after the other gateway deploys |

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

## Progress notes

- **10:32Z (T0 + 4 h 16 m; the 10:17Z note was late: a usage limit stopped this session and its agents
  07:30-10:30Z, the other three runs too).** J0 done; J1's development analysis done (the free model is the
  feature, Jev a capped shadow), the recorder built and reviewed (no blockers; eight should-fix items and the
  model integration in progress); J2 research half measured (no Jev pre-filter; the free model goes to the gate's
  owner), Merton half in progress; J4 discovery done; J5 built (#304, draft, waits for the other gateway
  deploys). D-J1 moved to Saturday's window. Jev spent by this run so far: $0.23 of the gateway line (analyses
  from the Mac); the House's own Jev line is unchanged (still capped at $0.25 a day until D-J1).

## Deploy log

## Report

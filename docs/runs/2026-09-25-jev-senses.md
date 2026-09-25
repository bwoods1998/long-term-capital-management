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
  checked unchanged (forward-first's request). Its exact start is written here first. **Gateway (J5 + the cap to $41):** after the other runs' gateway deploys.

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

Other J0 readings: the gate's lifetime totals run 6,182, sample 1,350, skip 11,994 (Jev cost $0.023); in
the 24 h window `abstain_lock` skipped 2,590 sessions without asking Jev at all (the lock admits only the
agent's own venue outcomes). Triage reads 1,768 ledger rows behind the head (cursor 672,259 of 674,027);
hypothesis links read 9,132 behind (cursor 664,895; 2,234 mechanisms indexed, the 60-call cap binds every
day). Exposure's cap (40) was not reached on Sept 24 (25 calls, 1,931 cached answers).

## Progress notes

## Deploy log

## Report

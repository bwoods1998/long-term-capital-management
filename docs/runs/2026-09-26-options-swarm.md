# Run record: the options swarm (from Sept 26, 2026)

Plan: `docs/goals/LTCM_OPTIONS_SWARM.md`. This record is read first after any context reset; the
clock never restarts.

**T0 = 2026-09-26T06:23:14Z** (`date -u` on the laptop).

## The owner's /goal message (as given)

- Direction: one goal only, a swarm of AI agents trading level-3 options on the Brokerage Account
  profitably, with options returns greater than every input cost. Prune everything else. Agent time,
  not human time. Bold: the account's money can all be lost. Evidence honest.
- Schedule: rework tonight; train Saturday and Sunday; trade Monday's open (13:30Z Sept 28). A
  slipped milestone never skips its Done line. Wave 2b merges after Monday's close.
- Funding plan once the rework is done: Brokerage Account deposit $5,000; Sail about $1,500 after
  the owner's top-up; OpenAI $1,000 added; ThetaData Options Standard (key at
  `~/.config/thetadata/env`).
- Authority: the plan's Authorized list (see the plan). Nothing in the Not-authorized list.
- Method: T0 and this record first; the scoreboard at T0, every four hours and at each milestone; at
  most four builders in worktrees; an adversarial review of all money code; one test process at a
  time on the laptop; verify every change on the box; fix every defect with a test; report at the
  end with the owner's decisions.

## Milestones

| Milestone | Target | Done at | Evidence |
|---|---|---|---|
| M0 Safe and archived | T0 + 1 h | | |
| M1 Data flowing | T0 + 2 h | | |
| M2 The House is options-only | Sat morning | | |
| M3 The swarm is training | Sat 16:00Z | | |
| M4 Gated | Sun 22:00Z | | |
| M4b The live path deployed | Sun 22:00Z | | |
| M5 Monday's open | Mon 13:30Z | | |
| M6 The first session judged | Mon after 20:00Z | | |
| M7 The prune finished | after Mon close | | |

## Log

- 06:23:14Z T0. Run branch `run/options-swarm-2026-09-26` cut from the plan branch (c61cd52d).
  Plan PR #356 opened (docs only). Laptop idle (load 0.18, 4 GiB available); no other Claude session.
- 06:23Z State read: old House release `20260926T032739Z-aaf5ac74637c`, 128 living / 627 dead,
  maintenance pause, Kalshi book FROZEN; updater's next release eligible 07:01:37Z. Gateway: kill
  switch off; frontier month $596.11 of $607 (50,510 calls). Sail balance $118.79.
  Brokerage Account: equity $481.81, cash $457.05, level 3, multiplier 1; SOL 0.1029, XRP 7.9403,
  LTC 0.000373 (dust); two resting crypto sells. Paper: equity $99,984.55, 21 positions, 8 orders.
- 06:24:56Z Old House stopped (`floor_box.py stop --reason "options overhaul"`): quiesced in 15 s;
  loop alive=False, stop_latch=True, league_stop=True.
- 06:25:00Z Old grant `earned-live-20260921` disabled (`live_trading.py --disable`): active=False,
  revoked=1790403900.1.
- 06:25:30Z Brokerage leftovers closed: both resting sells cancelled (204); SOL 0.102938725 sold at
  $120.30 and XRP 7.940324297 at $1.5453 (market, filled). Now: cash $481.62, equity $481.65, LTC
  0.000373062 ($0.03, below the venue's 0.0137 minimum) kept as a legacy holding outside P&L; no
  open order.
- 06:27Z Paper account: 7 of 8 orders cancelled (the 8th, an LTC sell, had filled); every crypto
  position sold; closing orders queued for Monday's open for DIA, IWM, META, NVDA, QQQ, SPY, TSLA
  (market, day) and SOFI261002P00016500 / P00017000 (limit $0.01 sell_to_close, day). Paper equity
  $99,981.54.
- 06:31Z Builders launched, each in its own worktree: W1 data (`~/Work/ltcm-w1-data`, `data/gym-store`),
  W2a House options-only (`~/Work/ltcm-w2a-house`, `overhaul/options`), W3 Gym (`~/Work/ltcm-w3-gym`,
  `gym/engine`), W6 site (`~/Work/site-options`, personal-site `capital/options-reset`, plus
  `~/Work/ltcm-w6-publish`, `site/publisher`). Briefs share one fixed store schema ("store-v1": per-day
  Parquet of one-minute NBBO, underlying price, OI, trade_quote, calendar, expiries, manifest).
- 06:35Z House checkpoint `pre-options-20260926` (365-day TTL) FAILED: Sail 503 "prepare checkpoint warm
  snapshot ... i/o timeout". The box stayed healthy. Retry after the tarball.
- 06:36Z Old state moved aside on the box: `/workspace/state` -> `/workspace/archive/state-pre-options-20260926`
  (16 GB; largest: research.sqlite, experiments, provider.sqlite 2.9 GB each); a fresh empty
  `/workspace/state`; `tar | gzip -1` to `/workspace/archive/state-pre-options-20260926.tar.gz` running.
- 06:33Z Git archive: tag `archive/pre-options-2026-09-26` at 89bc49a1; 78 GitHub branches tagged
  `archive/branch/<name>` (tags pushed: 79); laptop-only commits bundled in `~/Work/archive/branches/`
  (k5b/allocator-tranches, 7 commits ahead of its remote; detached heads of ltcm-j1-review 0bf56386 and
  ltcm-rv-j5 5d4d7cd2; all three `git bundle verify` ok). 14 open PRs closed with a comment naming
  their tag (#355, #349, #348, #345, #335, #332, #331, #330, #328, #327, #325, #322, #313, #304).
- 06:37-06:39Z Sail: 420 old boxes terminated (agent sandboxes, lab/foundry boxes, canaries; 0 errors).
  Kept: `ltcm-floor` (House), `ltcm-data` (W1, new), `ltcm-lab` (sleeping, until the state archive is
  safe), two boxes of the separate portfolio app.
- 06:38Z Laptop: 35 old worktrees removed (each head in an archive tag or bundle; ignored files inside
  them, if any, were not kept); 57 local branches deleted (all covered); 78 archived branches deleted
  on GitHub (each tag verified equal to its branch tip first). Moved to `~/Work/archive/`:
  `ltcm-watch-*`, `ltcm-observation-*`, `ltcm_observe.py`, `ltcm_snapshot.py`,
  `ltcm-review-2026-09-16.md` (laptop/), `LTCM_OVERNIGHT_GOAL.md` (docs/), and `.data/`'s
  `capital-paper-shakedown-20260915` and `runtime` (data/, 19 GB).
- 06:39Z **The OpenAI month cap is NOT raised.** The gateway's $607 equals metered plus funded ($596.11
  spent); the owner's $1,000 arrives "once this rework is done", so a raise now would exceed funded
  money. When the owner confirms the top-up: September to $746 (spent + $150 burst), October to $215
  (the plan's month) before Oct 1. Until then the swarm's model calls run on Sail.
- 06:40Z Plan PR #356 merged (CI green: 3.11 10m44s, 3.14 14m12s); main `46ec3433`; the main checkout
  fast-forwarded to it.
- 06:40Z W6: checkpoint schema v2 fixed (personal-site `capital/options-reset` 4e35ec9): top level
  {schema_version 2, published_at, run, account, performance, compute, gym, agents (<=160, bands
  gym|candidate|probe|sized|retired), structures (<=100)}; tape kinds agent.note, agent.trade,
  swarm.news, account.mark; every sentence quote-free. Publisher `build_checkpoint` + a
  `house.site_inputs()` hook for W4/W5.

## Scoreboard

### T0 (2026-09-26T06:23Z; repo figures at 06:40Z)

| # | Metric | T0 |
|---|---|---|
| 1 | Net since the reset | no reset yet; options P&L $0; tracked profit of the old House since Sept 19 +$4.84 against $680 of compute |
| 2 | Data: underlying-days in the store | 0; the data box being built (W1) |
| 3 | Gym throughput | 0 (no Gym yet) |
| 4 | The search | 0 families (the old House's 128 agents stopped) |
| 5 | Evidence | 0 validation passes, 0 holdout looks |
| 6 | Forward | none |
| 7 | Execution | no option order; 0 orders today |
| 8 | Compute | Sail balance $118.79 (was $34/day before the pause); OpenAI month $596.11 of $607; ThetaData Standard $80/mo |
| 9 | Harness | CI 14m12s (3.14) / 10m44s (3.11); 1,103 files, 360,821 lines (league 90,343 + tests 80,279; ltcm 50,460 + tests 42,762); 119 docs .md; README 104.6 KB; CONTRACT 75.6 KB |

## Report

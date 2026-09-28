# Handoff: the options-swarm run

**D8 (owner, Sept 27 about 23:45Z): the two-release limit before Monday is lifted; the Monday 13:25-20:05Z freeze stands.**

## THE SPRINT — Sunday Sept 27, 15:40Z update (read first; the 02:00Z section below still holds for releases and the grant)

**Evidence.**
- One family passed Validation 2025: `low-close-location-backmonth-call` v7 (t 2.47, deflated
  Sharpe 0.997). The gate's review and Claude audit passed. Its sealed holdout look FAILED (-$9,372
  over 184 days of 2026).
- No holdout passes. Families at 6/8 on 2025: `event-crush-xsp-fly-r` (t 1.03),
  `sweep-bm-trend-long-option` (t 1.04).
- Refuted at honest costs: short-dated premium buying and selling, XSP credit, names at the
  natural, calendars, diagonals, condors, flies, and back-month verticals of any kind.
- What survives Train and costs: signal plus back-month SINGLE long options on SPY/QQQ.
- Train strength has not yet transferred to 2025/2026.

**Images.**
- Adopted since 13:25Z: the complete back-month pair, Gym `sbcp_a38bb07a`, gate `sbcp_a5e975a5`
  (stages 1-6, 25 roots, model `fm-c4a0c70c`).
- The pool's split runs fit the 6 GB worker cap. The operator sweep's split-1 runs of 3-root
  programs do not (`poolcheck.py`).
- The completion supervisor's final pair: check with `poolcheck.py` before any adoption.

**Push settings** (the owner topped up and said do not throttle):
- pool `start_boxes` 6 / `max_boxes` 10;
- researchers $4.5/h, `top_profile` pro_asap for the top 10;
- population 72, architect hourly, agenda v3 (back-month single options);
- diagnostician 5/round, $45/day;
- `claude.usd_cap` 98 (the gateway's lifetime `CLAUDE_USD` is 100).

**Money.**
- The owner deposited $1,000. Equity $1,481.63; options buying power $481.60 until it settles.
- Re-ratify the grant at the new capital once buying power shows it.
- PR #393 (credit) is not merged, by owner agreement.
- Any back-month long-call family costs about $300-1,500 a contract, over the $100 Probe cap:
  real money for one needs the settled deposit plus the owner's money-table decision.

**Defects found and handled.**
- The swarm mirror stalled 14 h (two private kinds unknown to the ledger).
  - Interim: `operator_mirror.py` on the House. Restart it after any House restart, without
    `--from-now`.
- The daily backup looked for the retired box name.
  - Interim: manual checkpoint `house-manual-20260927` (30 d).
- Code fixes for both: PR #394, re-review approved. Merge and release after Monday 20:05Z, then
  stop the operator mirror.
- The laptop's /tmp quota (the scratchpad on a 3.8 GB tmpfs) filled and blocked the shell: keep
  bulky scratch in `~/Work/.ltcm-main/scratch/`.

**Site.**
- The live thought feed has worked again since 13:46Z.
- The balance chart starts after the deposit (personal-site #14).

**Monday:** the private runbook `~/Work/.ltcm-main/monday-runbook.md`, covering the pre-open
checks, observe 8 then 60, the 13:35Z paper proof, calibration at 14:00Z, the post-close
post-mortem, #394, prune #375, rebase #385 and Tuesday's forward job.

## THE SPRINT — current state, Sept 27 02:00Z, images updated 12:30Z (read this first)

The owner's `/goal` runs `docs/goals/LTCM_SWARM_SPRINT.md` (merged #386). The owner's decisions:
- D1 real money for Monday;
- D2 evidence reform;
- D3 calibration at $50/day;
- D4 the bold money table;
- D5 no deposit yet;
- D6 no Sail top-up (pace so Sail stays above the $32 guard through Tuesday);
- D7 Claude $100.

The run record `docs/runs/2026-09-26-options-swarm.md` has "The sprint" log and scoreboards. Private
operator tools and receipts are in `~/Work/.ltcm-main/`:
- `board.py`: the scoreboard;
- `R2-runbook.md`;
- `revive.py`;
- `claude_probe.py`;
- `middiag/`: the private diagnostic;
- `apply_r*_settings.sh`.

**Deployed.**
- **R1:** `20260926T225946Z-22b18ea9f452` (#388 Claude, #389 search/D2).
- **R2:** `20260927T002925Z-2bfef7a749bf` (main `440f6de4`: #387 honest fill model, #390 live path,
  #391 Claude streaming, #392 `real_money` true). Promoted 00:30:02Z; the watch passed.
- **R2 was the last release before Monday** (the owner's /goal method). Until Monday 20:05Z only
  `swarm.json` switches, data or image adoption, and a rollback are allowed. The rollback guard
  refuses while real positions or orders exist (`--force-real-risk` overrides).
- **Gateway:** version `953a9b46` (Claude route + streaming, `CLAUDE_USD` 100; real types = 4 debit
  types; `MAX_ORDER_EQUITY_SHARE` 0.25).
- **Grant `options-swarm-20260928`:** enabled 00:30:15Z, pinned to money digest `ad9bd54c`, capital
  $481.63, Probe floor $100.

**Images and model (updated Sept 27 12:30Z).**
- ADOPTED since 08:57Z: the interim 25-root pair, Gym `sbcp_b358ab73`, gate `sbcp_92c29288`
  (`names-interim-20260927`).
  - Stages 1-5: the core five plus twenty names; the deployed model `fm-c4a0c70c` (sha `3de9e2a6`).
  - Verified by exact reproduction: the founded rebound gave the same 168 trades, t and P&L as on
    `core-honest-v1`.
  - It was cut mid-download, so it holds back months (beyond 14 DTE) for SOME days only. The
    agenda says to keep NEEDS within 14 DTE.
- NOT adopted: the back-month interim pair (Gym `sbcp_a38bb07a`, gate `sbcp_a5e975a5`, stages 1-6).
  - The rebound fails on it with a memory-map error: complete back months make the SPY/QQQ NBBO
    trees about 3 GB each.
  - The Gym maps the store per root across the window, so three roots exceed the 6 GB
    per-worker address space (`GYM_WORKER_MEMORY_GB`).
- DO NOT ADOPT the completion supervisor's final pair (`images-ready.json`, still in its SIP relay) as
  it stands. It carries the same back months and will break multi-root families. First run the
  exact-reproduction check (`~/Work/.ltcm-main/sweep`:
  `sweep.py --templates verify_rebound_rank0 --image <gym ckpt> --top 0`; expect 168 trades,
  t 2.1864). Then decide the engine change (a larger worker cap for the pool, or back months stored
  apart). That needs a release, so it is post-Monday.
- Model `fm-c4a0c70c9afbf09f` on the Gym, the gate and the House shadow book. Names were never
  sampled, so they fill at the natural only.

**`swarm.json` now** (a backup before every edit, `swarm.json.before-*`):
- population start 60, floor 44, ceiling 96;
- `sail_usd_per_hour` 2.0;
- `gym.start_boxes` 6;
- `validation_split` 1;
- `top_profile` null;
- `architect.agenda` set, refill 1200 s, every 7200 s;
- `tournament.retire_revisions` 200;
- `claude.usd_cap` 70;
- `live.observe` true, `observe_max` 8, `calibration` true.

**Monday (Sept 28):**
- pre-open 10:00-13:25Z per `docs/operations.md` (updated by #390);
- no deploy 13:25-20:05Z;
- paper proofs at 13:35Z (multi-leg, then single-leg);
- only families past the holdout become Probe, and a Probe must be moved before 13:30Z to trade
  Monday;
- observe starts at 8 instances; raise toward 48 after 30 healthy minutes of `options_live` timings;
- after the close: post-mortem, calibration report (`python -m league.live --root /workspace/state
  --calibration`), recalibrate from real fills, prune #375 re-integrated after 20:05Z, rebase #385.

**Known gaps to do after Monday:**
- researchers cannot read an older version's code (they rebuild from memory);
- #381 held (review findings on the PR);
- #384 unmerged;
- about 26 stale Codex worktrees under ~/Work.

**Evidence so far:** 0 validation passes under D2. The nearest two meet 6 of 8 checks and fail t and
the deflated Sharpe. 0 holdout looks.


## Current continuation, September 26 20:34Z

Read this update before the historical Claude handoff below. The run record remains the source
of truth and now includes the **T0 + 12 h scoreboard**. T0 is still **2026-09-26T06:23:14Z**;
the next four-hour scoreboard is 22:23Z. The overall goal is active and is **not complete**.

This continuation completes engineering, data, paper/shadow operation and readiness. It has not
enabled autonomous real-money execution: `real_money=false`, no live grant, real openings off.
No strategy has passed validation, no holdout look has occurred, and profitability is unproven.

### Owner direction: breadth, rapid learning and visible progress

The owner wants the harness to give **all supported options strategies and securities** a path
through research, historical testing and Alpaca paper execution. Simple long calls and puts
compete alongside spreads; complexity earns no preference. Covered calls and cash-secured puts
need their own inventory/collateral, assignment and exit mechanics. The first five and next
20 roots are data batches, not a permanent universe limit. Keep explicit coverage by root and
expiry; discovering a symbol does not supply its history or correct settlement rules.

Prioritize short hypothesis/replay/diagnosis/revision loops, persistent lessons, useful exploration
and evidence-directed compute. Agent counts and trials measure activity, not an established edge.
The site should show genuine thoughts and each agent's actual promotion progress with minimal
surrounding text; that interface is deployed. The goal remains profitable production trading
beginning Monday, but current evidence does not establish that result.

The goal, README, design, operations and researcher/Gym contracts record this direction in
[#382](https://github.com/bwoods1998/long-term-capital-management/pull/382), merged as `3d464985`
at 20:32Z after independent review and green CI. Researcher instructions and Gym guide
changes take effect only at deployment and change the Gym bundle identity. Preserve historical
trials, lineages and holdout looks; new validation/gate evidence must bind the deployed bundle.

### Deployed and verified

- Deployed code is based on `60b34dd97639cf1c3ec94c41dc7665e90d068965`. House release
  `20260926T181814Z-b4bc25619f84` passed its complete watch at **18:28:53Z**. House, swarm
  (PID 9188) and nightly (PID 9184, start ticks 57687395) match the release. Verify identities
  afresh before acting; do not signal a process from these historical numbers alone.
- The former #362 live-path defects and #365 gate fixes are merged, reviewed and tested.
  Subsequent releases fixed full-book options P&L, independent paper-route readiness, researcher
  READ/REVISE protocol, funded Sail pacing, explicit retirement and fresh order-admission checks.
  Real positions/orders remain empty, with only legacy crypto dust outside the options book.
- [The site](https://blakewoods.us/capital/) is complete for the owner's latest requests:
  Profit and Running, genuine agent thoughts, bare account chart caption, stable LTCM partner
  names and three stages of clickable dots. Each agent's ring follows its own current promotion
  evidence; selected detail shows remaining checks and blockers. No invented progress or odds.
  Site main `5abc570`, Worker `e473bcbc-0200-480a-92e0-de2001d55b20`. All 63 site tests passed;
  independent reviews and actual production checks passed at desktop and narrow phone widths.
  New pages request `checkpoint?progress=1`; default reads preserve old tabs' strict schema.
  Local dynamic tests verified improvement, regression and confirmed stage changes. Earlier
  production observation proved incoming WebSocket thoughts reach the main card automatically.
- Full publisher CI, independent policy comparisons and actual-House archive tests passed.
  The 18:20 public checkpoint had 16 active dots, 13 with verified progress. Missing or stale
  evidence leaves an empty track. Nothing in this feature changes promotion or money rules.

### Funding and search

- Owner confirmed Sail $200 and OpenAI API $124 after top-ups. Observed Sail about **$188.34**
  at 20:00Z; reserve remains $32, researcher Sail-model allowance $2.25/hour. OpenAI September
  gateway spending **$599.88 / $707**, with no October allowance added. Do not raise caps based
  on the older unfunded plan. The conservative unresolved $2 architect hold remains accounted
  for separately from settled costs.
- Brokerage equity **$481.63**, cash $481.60, no open orders or option position. No new deposit
  has been verified. Profit on the site is **$0.00**, unrelated to compute or deposits.
- At 20:01Z: 17,631 trials and 25,212.33 durable program-years; 16 active families, 57 retired.
  Fifteen active families are multi-leg and one is long-put. Historical families included single
  calls, but the architect favored spreads; #383 removes that prompt bias. The active Gym still
  trains only SPY, QQQ, IWM, XSP and SPXW. No validation/holdout pass. Do not relax evidence
  requirements to manufacture one.
- At 20:04Z the actual Alpaca asset lookup returned 6,305 optionable equity/ETF assets, 6,177
  tradable. This is the discovery universe, not verified history or account-contract readiness.
  The simulator has 11 types, including long calls/puts; covered inventory is absent. The paper
  path is still a single SPY route proof, not a general agent paper book.
- Cost audit through 18:46:56Z: Sail box billing is $4.22136 finalized plus $0.01723 estimated
  active cost; House Sail model requests in that window total $22.83364 by token usage and
  configured prices, not invoice confirmation. Do not add billed boxes to the Gym estimate or
  the account debit meter. Early laptop trials, aligned billing windows and subscriptions still
  need reconciliation before exact all-input Net. Private evidence is in `.ltcm-main/`.

### What remains, in order

0. **Finish the broader research and paper harness.** Main `f789e7e0` includes reviewed,
   green-CI #378 (complete universe context), #379 (shadow restart state) and #380 (role/Flex
   routing with durable spending reservations), #382 (direction docs) and #383 (research breadth).
   None is deployed yet. #383 removes the architect's complex-strategy/short-horizon preference
   and shows actual research coverage; independent review, 95 local/actual-House tests and full
   CI passed on `948d1153`, merged at 20:34Z. #384 (`29453f2d`)
   builds the discovery/coverage catalog and data backlog, under independent review. It neither
   expands the collector automatically nor grants paper/live eligibility.
   W5's #381 execution recorder/report passed the focused local/House review, but full CI exposed
   an existing SIGALRM ownership defect through the new test order; W5 fixed it in `f2b670fb`
   with a regression, with full CI rerunning. This also changes the Gym bundle. W4's #385
   (`80cbf01b`) implements post-burst budgets, maintenance commitments, the smaller
   cohort and owned-backfill cutoff; independent review/full CI are pending. A general paper
   book is designed, not implemented. Its first delivery must support singles as well as
   verified spreads, preserve separate ownership from legacy paper holdings and the route proof,
   and record partial fills, cancels, expiry and restarts correctly. Broader exits and covered
   inventory remain explicit follow-up work. The automatic post-close scheduler is also absent.
   Require independent review, green CI and exact committed-archive House checks before deploy.
   Paper/shadow outcomes never substitute for real fills in calibration or promotion. Do not
   enable real money or raise funding caps as part of this engineering work.
1. **Final data completion/adoption.** Core, holdout, 2022 and trade-quote calibration stages are
   complete. Names were 11,255/23,740 at 20:28Z, with 150 vendor-empty tasks and no failures;
   back months were 0/2,374. The completion supervisor is healthy in the ThetaData phase.
   A read-only local completion watch follows the same live backfill (PID 22487, start ticks
   3310972); current observations go to `.ltcm-main/completion-watch.jsonl`. Check the existing
   process and watch before starting anything. Observation failures do not authorize a duplicate
   collector. The estimated remaining time was about thirteen hours, not a completion guarantee.
   Active Gym is still v1, `sbcp_4f1f0577-9b32-4e8d-b610-480bb88d617d`; the gate is disabled.
   Do not select the provisional calibrated pair. Await full ThetaData/SIP, final calibration,
   sealed final pair and actual primary/backup restores. Follow the expanded adoption procedure
   in the run record and private `.data/w2b/FINAL-DATA-ADOPTION.md` in the main checkout.
   Independent preparation caught three more gaps: calendar/expiry control metadata, inherited
   active forward checkpoints and model-path environment overrides. Helpers now check these;
   15 synthetic tests and an isolated real-bundle probe passed. Actual final-image checks and
   adoption are still pending. Preserve all evidence/lineage/looks and leave a failed adoption
   stopped rather than partially resuming it.
2. **Monday paper/shadow session.** Use the run record's pre-open checklist. Reconcile the nine
   inherited paper positions separately; observe the independent one-lot SPY paper route proof
   at minute five, expected 13:35Z. Candidate live shadow depends on actual evidence. No deploy
   **13:25–20:05Z** except rollback. Record that no strategy qualifies if that is the outcome.
3. **Prune after Monday close only.** Draft [#375](https://github.com/bwoods1998/long-term-capital-management/pull/375)
   is ready at `cadba222fcac73fc5f12887a0032ac6af594334c`, including current main. Independent
   review found and verified fixes for assignment/reconciliation rollback protection and
   malformed paper-proof state. Full CI passed (3.11 98s, 3.14 81s, gateway 7s); isolated
   actual-House archive verification ran 175 tests, 173 passed and two optional schema checks
   skipped. It remains **DRAFT, unmerged, undeployed until Monday September 28 after 20:05Z**.
   Recheck later-main changes, deployment/rollback state, money digest and Gym bundle then.
4. **Tuesday September 29 06:00Z.** Verify the first actual nightly forward collection, SIP
   ingestion and sealed gate copy/checkpoint. Current nightly heartbeat waits for that time.
   Saturday rehearsal is not completion of this milestone.
5. Write the final report and update memory from actual outcomes. The future session, final
   data adoption, prune deployment and first nightly job cannot be claimed complete today.

Root scratch remains `~/Work/.ltcm-main`; one laptop test process at a time under
`flock /tmp/ltcm-options-tests.lock`. Builder worktrees have their own private `.data` receipts.
The recorded House recovery checkpoint is `sbcp_939a5990-309b-4aa1-b643-add639dafb0a` from
18:37Z (generation 1595, expires October 26 18:37:41Z); it has not been restored in a test.
The earlier 17:19Z checkpoint remains recorded. These include credentials and must never
become independently trading clones. No rollback
before `20260926T084913Z-8158a11cfe3f`. No extra ThetaData login: the credentialed data box owns
the account's only session. Keep quotes, source programs, fitted model tables and secrets private.

## Historical Claude handoff, September 26 ~14:40Z

**The goal file this run executes:** `docs/goals/LTCM_OPTIONS_SWARM.md` (on `main`, merged in #356). Read it first:
its "Done" list is the finish line, its "Authority" section is the permission boundary, and its "Order of work"
(Waves 0-9, milestones M0-M7) is the schedule.

**The run record:** `docs/runs/2026-09-26-options-swarm.md` on branch `run/options-swarm-2026-09-26` (worktree
`~/Work/ltcm-goal-swarm`). It has the full timestamped log, milestones and scoreboards (T0, T0+4h, T0+8h). This
handoff summarises it; the record is the source of truth. Keep appending to it; never restart the clock.

- **T0 = 2026-09-26T06:23:14Z.** Monday's open is **2026-09-28 13:30Z**. No deploys 13:25-20:05Z on a trading day
  except a rollback.
- The main session's scratch files are in `~/Work/.ltcm-main/` (review JSONs, helper scripts `boxexec.py`,
  `boxgw.py`). Never keep anything in the shared session scratchpad (it was wiped once).
- The session was stopped by the account's usage limit from ~11:06Z to ~14:14Z; everything on Sail kept running.

## Milestones

| Milestone | Target | Status |
|---|---|---|
| M0 Safe and archived | T0+1h | **Done** except the OpenAI month raise (unfunded; waits for the owner's top-up) |
| M1 Data flowing | T0+2h | **Done 06:58Z** |
| M2 House options-only | Sat morning | **Done 07:49Z** (#359) |
| M3 Swarm training | Sat 16:00Z | **Done 10:33Z** (new House + swarm live on the box) |
| M4 Gated | Sun 22:00Z | **Open**: the gate is OFF (gate_checkpoint null) until PR #365 deploys; 0 families over the validation line yet |
| M4b Live path deployed | Sun 22:00Z | **Open**: PR #362 in its third verification; not merged; real_money false; grant not enabled |
| M5 Monday's open | Mon 13:30Z | Open |
| M6 First session judged | Mon after 20:00Z | Open |
| M7 Prune finished (Wave 2b) | after Mon close | Open (docs half done in #360; code prune not started) |

## What exists now

**Sail boxes** (Sail's `/sailboxes` API via `ltcm.sailbox.SailboxClient` or `league/sailbox.py`):
- **The House: `sb_1d99c4a7-bee2-4226-ba7b-c694ccd857d3` (ltcm-house)**, size s, Python 3.11 + numpy 2.4.4. The
  old House box `sb_d36bc830` failed a Sail runtime upgrade at 08:09Z and is stuck `interrupted_restorable`; the new
  one is a fork of its Sept 22 checkpoint with state cleared (`.data/ltcm/box.json` and the gateway's SAILBOX_ID
  point at the new one). It is on Sail's OLD runtime (guest 253): a forced Sail upgrade could fail the same way.
  Working checkpoint: `sbcp_a3a46ed8` (house-fresh-20260926, 30 d).
- **Running release `20260926T105515Z-b25acc7981e2`** (main after #363). **No rollback past
  `20260926T084913Z-8158a11cfe3f`** (older releases are old-era Kalshi/Jev code).
- **Data box `sb_d69a1ebe` (ltcm-data)**: the ThetaData key only in `/data/secrets/thetadata.env`; the store in
  `/data/store` (store-v1 Parquet); the backfill runs in the background (`/data/work/`, `progress.json`,
  pid in `backfill.pid`) at ~1,600 underlying-days/h. ThetaData allows ONE session per account: never log in from
  anywhere else while it runs.
- **Images**: Gym v1 `sbcp_4f1f0577-9b32-4e8d-b610-480bb88d617d` (Train 2023-2024, Validation 2025, core five;
  365 d); gate image `sbcp_61d027f4-ba8c-4e9e-8f0a-c9be4f9be28c` (adds holdout 2026-01-02..09-25 and the GATE mark;
  365 d). Records in `~/Work/long-term-capital-management/.data/gym/images.json`.
- Swarm Gym boxes are named `ltcm-swarm-*` and managed by the swarm itself.

**The swarm** (runs as its own process on the House box, supervised by the House's swarm step):
- Switch: `/workspace/state/swarm.json` on the House box, currently
  `{"enabled": true, "gym": {"enabled": true, "image_checkpoint": "sbcp_4f1f0577...", "gate_checkpoint": null}}`.
  `touch /workspace/state/swarm.stop` stops the swarm alone.
- Check it: on the box, `cd /workspace/current && /workspace/.venv/bin/python scripts/verify_swarm.py --root /workspace/state`.
- At 14:14Z: 9,549 trials, ~8,000 program-years/h on 6 Gym boxes, 3,000 inner-loop cycles/h (median 29 s), 44 families
  alive, 11 retired, first tournament 13:23Z (18 validated, **0 over the validation line**, 0 holdout looks), spend
  $4.63/h. Main weakness seen: programs trade too rarely for the line (it needs >= 100 trades on >= 60 days, daily
  t >= 2, DSR >= 0.95, 3 of 4 quarters, positive at 1.5x spread); the nearest was term-calendar-iwm (54 trades, 29
  days, t 1.81). Suggest to the swarm builder: tell researchers the line's trade-count requirement and favour
  daily-trading mechanisms.
- The verify script's `population` check fails only because 44 < 48 alive (a check to fix, and refill toward 96).

**Money and accounts:**
- Brokerage Account: equity ~$481.63, all cash plus LTC dust 0.000373062 (below the venue minimum; a legacy holding
  outside P&L). Level 3, limited margin under $2,000 (debit structures only until equity >= $2,000). No open orders.
  Paper account: queued closes for DIA/IWM/META/NVDA/QQQ/SPY/TSLA and the two SOFI puts fill at Monday's open.
- Old grant `earned-live-20260921` disabled 06:25Z. **New grant `options-swarm-20260928`** exists in code
  (`league/live_trading.py`, store `<state>/live-grant.sqlite`, ceiling `live_trading.ceiling_usd` 5500) but is **not
  enabled yet**. `real_money` is **false** in `league/config.json`.
- Gateway: kill switch off; OpenAI month $596.29 of $607 (not raised: unfunded). Sail balance ~$99 at 14:14Z,
  burning ~$4.6/h; the swarm's guard brakes at $32.
- Site (blakewoods.us/capital): reset 07:21Z; "AI agents trading options."; schema 2; reset pair
  PERFORMANCE_START_AT 2026-09-26T06:25:30.000Z, START_EQUITY 481.65; the new House publishes to it.

**Merged to main:** #356 plan, #357 publisher (schema 2), #358 the Gym (after an adversarial review, all findings
fixed), #359 House options-only + the new grant, #360 docs + `archive/`, #361 gateway SAILBOX_ID, #364 + #363 the
swarm (after an adversarial review and two fix rounds). The gateway is deployed at main 3f660144 (version 8054eecb).

## Open work, in order

1. **PR #365 (branch `swarm/stage3`, W4)**: the swarm's stage-3 fixes (a stale look_inflight marker, staleness by
   version number, finish() clearing a newer marker, fork look accounting, double booking of timed-out calls).
   **CI green at d8d22fb4 (14:30Z)** (the earlier 3.14 failure was a rare race in test_watchdog, not the swarm).
   It also adds: a validation is reused only on the Gym image in use (v0 -> v1 switch), and the architect refills
   the population below 48 hourly and grows it toward 96 every 4 h while under the spend pace. Verify the fixes
   (a short review workflow over d2b365a1..d8d22fb4, as done for stage 2),
   merge, deploy (`python3 scripts/floor_box.py deploy` from `~/Work/ltcm-deploy` on origin/main), then set
   `gate_checkpoint` to `sbcp_61d027f4-ba8c-4e9e-8f0a-c9be4f9be28c` in the House's `swarm.json`. That is M4's start.
2. **PR #362 (branch `live/options`, W5, head 769243f4): the live money path.** Three rounds: the first review found
   10 confirmed defects (2 critical); round 2 left C2 unfixed and 6 partly; round 3 (769243f4) verified C2, C5, C7,
   m6, m9, R1, R2 and more fixed; **still partly: m2** (the daily stop's base can be taken from a reading made while
   a transfer was pending) and **m16** (the decider child's isolation: netns via unshare where allowed; no
   per-minute clamp; one child for all programs). The **regression hunt and a fresh full pass on 769243f4 were
   re-launched** (workflow run `wf_3048d1aa-607`); read their results (`~/.claude/projects/-home-bwoods1998-Work/
   551089ee-bad4-4d48-a821-22438d30a90b/subagents/workflows/wf_3048d1aa-607/journal.jsonl`) or re-run them. Review
   material: `~/Work/ltcm-w5-live/.data/w5/review362.md` and `fixverify362.md`; JSONs in `~/Work/.ltcm-main/`.
   **Round-3 verification finished ~14:35Z** (`~/Work/ltcm-w5-live/.data/w5/fixverify362-round3.md`, JSON in
   `~/Work/.ltcm-main/fixverify362-round3.json`): **1 CRITICAL** (pre-existing): with the committed config,
   `service.build` crashes before the House starts (the options_history block reads `brokers["alpaca"]` / `paper`,
   which the live path no longer builds) -> **do not deploy #362 until fixed and a build test on the unmodified
   config passes**; **6 major** from a fresh full pass (an exit waiting forever behind another position's resting
   close; a lost exit-only program never reloaded; a real instance taken off real money; `_export_real`'s cursor
   dropping real trades; Probe/Sized demoted to Candidate too eagerly; a venue-liquidated expiring position left
   'awaiting'); m2, m16 (the decider docstring's false claim that the child cannot read the token), R7 partly.
   All sent to W5 at ~14:37Z. Re-verify after its fixes.
   W5's open question: cap how often a program may re-send a close (recommended: cap re-sends of the same close,
   never the first send). After fixes and a clean verification: merge (after merging main), deploy the gateway
   first (`npx wrangler deploy` in `gateway/`: new vars MAX_DAY_OPEN_ORDERS 250, MAX_DAY_USD 4000,
   MAX_DAY_USD_ALPACA 10000, caps by max loss, flex), then an owner deploy with `real_money` true (a config change
   in a commit), then on the box `python3 scripts/live_trading.py --enable options-swarm-20260928` and `--ratify`
   within a minute (the money digest moved to 8dba0b1f). A family moved to real money trades from the NEXT session,
   so all of this must be done before Monday 13:25Z for Monday. That is M4b.
3. **W1's data branch `data/gym-store`** (worktree `~/Work/ltcm-w1-data`): the data tools (`scripts/data/*`:
   backfill, images, check, nightly, box). Not yet PR'd: open the PR, CI green, merge. The backfill still needs the
   20 names (~23,740 root-days; ETA ~03:40Z Sunday) and back months; then Gym v2 with 2022 + names, and the fill
   model's calibration from the trade_quote samples (stage 5 done) with `league/gym/calibrate.py` on a Gym box
   (the plan's Done item 4). One 2022 day (XSP 2022-06-29) fails at ThetaData.
4. **The nightly forward job** (`scripts/data/nightly.py`): must run Tuesday 06:00Z for Monday Sept 28 (the first
   forward day): wake the data box, pull the day, copy it into the gate image, re-checkpoint, then the swarm's
   nightly forward replays of Candidates. Confirm how it is triggered (a scheduled wake + the laptop or the House).
5. **Monday**: the pre-open checklist is in `docs/operations.md` on #362 ("Monday's pre-open", 12:00-13:25Z):
   equity (with any deposit; a landed deposit is answered by `--ratify`), gateway caps, the grant active on the
   running digest, the House healthy, the Probe list; a 1-lot paper structure proves the multi-leg route before
   the first real one; watch every 30 min; after the close the post-mortem, fill recalibration from real fills,
   the scoreboard.
6. **Wave 2b, the code prune** (after Monday's close only): delete the cut modules and tests, fold the needed `ltcm/`
   modules into `league/`, prune the gateway's dead routes, CI under 5 minutes. Also fix `scripts/floor_box.py fork`
   (its latch missed a running loop: kill with pgrep, not only pid files).
7. **The report** in the run record's "Report" section, the memory update, the swarm left running 24/7.

## Owner steps outstanding

1. **Top up Sail now** (~$99 left at $4.6/h; the swarm brakes at $32, and running out pauses every box, the House
   included).
2. Add OpenAI credit ($1,000 planned) and say so: then raise the gateway's `FRONTIER_MONTH_USD` and
   `FRONTIER_MONTH_MAX_USD` in `gateway/wrangler.jsonc` (September to spent + $150 ~ $746; October to $215 before
   Oct 1) and deploy the gateway. Until then every OpenAI role runs on Sail models.
3. Deposit $5,000 to the Brokerage Account (then `--ratify`; equity >= $2,000 unlocks credit structures).

## Builders and worktrees (at handoff)

W1 data (`~/Work/ltcm-w1-data`, `data/gym-store`), W4 swarm (`~/Work/ltcm-w4-swarm`, `swarm/loop` and
`swarm/stage3`), W5 live path (`~/Work/ltcm-w5-live`, `live/options`). Read-only review worktrees:
`~/Work/ltcm-review-362`, `~/Work/ltcm-review-363`. Deploys run from `~/Work/ltcm-deploy` (detached at origin/main;
its `.data` is a symlink to the main checkout's; never `ln -sfn` over it). One unittest process at a time on the
laptop (8 cores, 7 GiB); CI is the source of truth.

## Operating commands (from `~/Work/ltcm-deploy`)

- `python3 scripts/floor_box.py status | deploy | start | stop | logs | checkpoint --name N --ttl-days D`
- `python3 scripts/gateway_admin.py status | kill | unkill`
- `python3 scripts/live_trading.py [--enable options-swarm-20260928 | --ratify options-swarm-20260928 | --disable]`
- Box shell: `python3 ~/Work/.ltcm-main/boxexec.py '<cmd>'` (House) or `--box <id> '<cmd>'`
- Gateway reads through the House box: `python3 ~/Work/.ltcm-main/boxgw.py alpaca GET v2/account`

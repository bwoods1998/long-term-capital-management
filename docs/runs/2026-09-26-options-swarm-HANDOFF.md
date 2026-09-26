# Handoff: the options-swarm run, as of Sat Sept 26, 2026 ~14:40Z

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

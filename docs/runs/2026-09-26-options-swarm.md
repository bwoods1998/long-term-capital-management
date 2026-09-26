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
| M1 Data flowing | T0 + 2 h | 06:58Z (T0 + 35 min) | data box downloading since 06:49:43Z; universe chosen (W1) |
| M2 The House is options-only | Sat morning | 07:49:25Z | #359 merged, CI green; updater off, tools off `ltcm`, grant `options-swarm-20260928`, options-only service and tick |
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
- 06:5xZ W2a step 3 committed (`overhaul/options` 7fa58114; steps 1-2 d7c5a7c9 updater off, fac879ae tools
  off the legacy package): grant `options-swarm-20260928` in `league/live_trading.py`, its own store
  `<state>/live-grant.sqlite`, empty-root safe, alpaca only, capital = min(equity, config
  `live_trading.ceiling_usd` 5500), pinned to `money_digest`; every House/allocator/capital/shards/merton
  call site asks `House.grant`; no grant -> no real entry; the campaign grant no longer read for money.
- 06:50Z House box facts: Python 3.11.2, no numpy (PyPI in its egress: install numpy at deploy);
  XSP contracts tradable (european); SPXW lists under underlying SPX root SPXW; XSP snapshots
  latestQuote only.
- 06:54Z Old-state tarball done: `/workspace/archive/state-pre-options-20260926.tar.gz`, 8,256,763,269 bytes,
  sha256 e9e5c04482a3321707902dd376a9902fe260954cd76cbe204eec89be6a16256f; `gzip -t` OK (06:57Z). Box disk
  ~5 GB free until the uncompressed copy goes.
- 06:58Z **M1 holds** (T0 + 35 min). Data box `ltcm-data` sb_d69a1ebe-94ea-4f37-9bfe-4d294e946973 (l, 8 vCPU,
  32 GiB, 256 GiB) downloading since 06:49:43Z; run restarted 06:57:56Z with all six stages queued (32,840
  tasks), SPY+XSP sample days first. Egress: the two ThetaData hosts only; gRPC over TLS passes the SNI
  allowlist. Key only in `/data/secrets/thetadata.env` (0600). Universe (2024 EOD): SPY QQQ IWM XSP SPXW +
  TSLA NVDA TLT AMD SLV AMZN META AAPL PLTR TQQQ SMCI MARA GLD TSM MSFT MU BABA SMH GOOGL SOXL (numbers in
  `.data/gym/universe.json`, gitignored). **ThetaData allows ONE session per account**: any second login
  kicks the box's session; nobody else authenticates while the backfill runs; the nightly job stops the
  backfill, pulls the day, restarts it.
- 06:59Z W1: the Gym sample on the laptop (`.data/gym-sample/store/`, SPY+XSP, 10 Train days incl. FOMC/CPI/
  monthly expiry/vol spike/half day; 60 files, 37 MB, sha256-verified); relayed to W3. Notes: the 09:30 row is
  often absent for ETF roots (first quote at 571); SPXW strike range 40 per side ($5 strikes).
- 07:00Z House checkpoint retry FAILED again (503 "prepare guest for clean base snapshot: context deadline
  exceeded"). The archive is the verified tarball; streaming it to `~/Work/archive/house-state/`.
- 07:02Z W3: the Gym's program API fixed (`gym/engine` e5fe74c3; `league/gym/PROGRAM.md`): NEEDS/PARAMS/decide(ctx)
  -> intents; live-path pieces importable on Python 3.11 + numpy only (`runtime.py`, `ctx.py` incl.
  `parity_spot`, `legs.py`, `venue.py`, `fills.py`, `events.py`); holdout/forward days only through a gate
  capability that needs the store's `GATE` marker. Real sample: 3 programs x 10 days SPY+XSP in 1.3 s.
- 07:19Z W1 rehearsed images and the nightly job on real boxes (07:08-07:19Z; forks terminated, checkpoints
  2-day TTL): Sail checkpoints WORK on these boxes (4 made, 0 errors, 38-39 s each; the House box's failure is
  that box's); a fork from an image checkpoint starts in 3 s and inherits `no_network`. Gym path: stop the
  backfill, checkpoint the data box, restart; fork, seal, prune to train+validation, scrub, verify inside (no
  egress, no key line, no file after 2025-12-31, no GATE), checkpoint. Gate path keeps all windows and writes
  `/data/store/GATE`. Nightly rehearsal: a holdout day (9 files) copied to the sealed gate, sha256-checked,
  gate re-checkpointed. Quality over 138 root-days (56M rows): 0 crossed/negative/no-offer, 0 outside the
  session, every listed 0-14 DTE expiry present. Recorded Alpaca OPRA vs ThetaData: 82.2% within a tick at
  minute resolution (95.9% for quotes in a minute's first 2 s; 149,124 compared); 99.6% within a tick of the
  same or next second at 1-s resolution (SPY/QQQ/IWM Sept 23; 5,527 compared). Throughput 650-700
  underlying-days/h (ThetaData server-bound). ETAs: core five 2023-2025 ~12:30-13:00Z -> Gym image v1;
  holdout ~14:00-14:30Z -> gate image.
- ~07:2xZ W3 benchmark (gym/engine e89afd66; laptop, one pinned core, real sample, ~1,050-1,100 contracts a
  day): chain load 52-65 ms a root-day; one program-year (252 days, loads included): light cadence-10
  16.7-18.1 s, condor-vrp 19.4-20.3 s, putspread-dip 15.8-16.1 s, worst case (cadence 1, all greeks every
  minute, trades often) 65.4-69.9 s (target 60 s: typical programs pass, the stress case misses by ~10%).
  Day-major batch of 16 mixed programs: ~420-430 program-years/hour/core (2,000/h needs ~5 cores).
  Extrapolated, NOT measured on Sail: 4-8 l boxes ~12k-25k program-years/hour. Inner loop (Train ~750 days):
  ~60 s single-core typical, ~210 s worst; ~30 s with --split 8 on an l box (extrapolated).
- 07:18Z W6 done: personal-site PR #9 and LTCM PR #357 (publisher) green; both merged 07:20Z (#357 ->
  main d1855afc; site main 287b495). Schema 2, allowlisted blocks on both sides, quote masking (25 smuggled
  fields and 19 quoted sentences refused; 3,000 random sentences through the site's `quoteFree`), no venue
  names. W4 (the swarm) launched in W6's slot (`~/Work/ltcm-w4-swarm`, `swarm/loop`).
- 07:21Z **Site deployed** (`npm run build && npx wrangler deploy`, version 650a8ac1) and **reset**
  (`/reset?confirm=erase-everything`, token on stdin): real record cleared 20,000 events, 1,604
  floor_history, 1 checkpoint, 136 desks; /t/test 283/14/1/4; /t/canary empty. All three checkpoints
  answer 404; the page reads "AI agents trading options."; 0 venue names on the page. Reset pair:
  PERFORMANCE_START_AT 2026-09-26T06:25:30.000Z, START_EQUITY 481.65.
- 07:28Z The archive stream broke at 3.94 GB (IncompleteRead); Sail's files API ignores Range, so the rest is
  fetched in 1 GiB pieces cut on the box with dd, each sha256-checked, then the whole file checked.
- 07:35Z **Sail box spend is small**: every box since 06:00Z cost $0.105 (Sail's /sailboxes/spend); the data box
  $0.035 for its first hour (billed on measured use: ~1.1 vCPU, ~0.7 GiB average). The Sail balance ($118.70)
  moves with model inference, not boxes: the swarm's researchers are what the Sail guard must watch.
- ~07:35Z W2a done: PR #359 (`overhaul/options` 6ca2d7dc, +3,795 -18,432, 218 files); CI green on the dispatch run
  36226798132; `python3 -m league.ci` passed; ltcm/tests 2,002 OK. Empty-root tick builds only `alpaca-paper`
  and `options-shadow` books; no campaigns/feeds/Jev/lab/foundry/semantic lab/shards/Kalshi. Hooks
  `house.swarm` (W4) and `house.options_live` (W5) in `House.PLUGGABLE_STEPS`. `real_money` false;
  `performance` = the reset pair. Left for W4/W5: old Pacer ($100/$100 expedition), Budget (Sail $100/month),
  the old founding (7 options agents on agent boxes with the old researcher), Merton's teacher.
- ~07:38Z W5 (the live path) launched in W2a's slot (`~/Work/ltcm-w5-live`, `live/options` from 6ca2d7dc).
- ~07:40Z W3 done: PR #358 (`gym/engine` eb53aa5f; new files only). 62 Gym tests OK on the laptop (skipped on CI
  until #359's `pip install -r requirements-gym.txt`). Hand-computed vertical/condor/calendar to the cent;
  no future/date/year to programs; cutoffs, 15:30 liquidation, exercise, cash settlement; fills keyed by
  (contract, minute); deterministic. Defects found and fixed by its tests: underlying history never grew;
  IV solver overwrote solved values; float32 noise in prices; numpy methods failing on first use in a
  fresh process. Unverified: nothing run on Sail yet; calibration on synthetic prints only; ASSUMED fees
  (SPXW exchange, XSP >= 10 lots, SEC rate); late-2025/2026 event dates.
- ~07:42Z An adversarial review of the Gym (lookahead/leakage, fill honesty, P&L arithmetic) launched before
  merging #358; W2b-docs (the five documents and `archive/`, docs only) launched in W3's slot
  (`~/Work/ltcm-w2b-docs`, `prune/docs`).
- 07:49:25Z **M2 holds**: #359 merged (CI green on its own run: 3.11 10m11s, 3.14 10m36s); main 6c715d83. The Gym branch merged main (c6e7c9bd) so CI runs its tests with numpy.
- ~08:00Z The Gym's adversarial review: 6 major, 6 minor, 0 critical (5 majors demonstrated with probes): (1) t and
  trade count per trade, not per day (one 80-day series split 5 ways moved t 0.93 -> 2.09 and flipped the
  line); (2) 1.5x stress inert on mid-limit fills, no adverse selection on passive fills; (3) a program's
  `except Exception` swallows its timeout (2.6 s against 1 s, counted 0); (4) zero-bid wings (bid_size 0:
  4.7% SPY, 6.4% XSP contract-minutes) block closes, stops silently ignored; (5) `arr.flags` writable,
  views shared between batch-mates (one program changed another's trades); (6) no settlement on days with
  no file (zombie positions). Minors: remainder fills at limit, repr addresses, run_id identity, validation
  boundary returns trades, index settlement at 16:00 minute, forced marks at mid. Clean: lookahead in the
  data path, sandbox escapes (no route to os/sys/builtins), venue arithmetic. W3 resumed to fix all with
  tests before #358 merges; W4 told to use daily t and flag price-level constants at the gate.
- 08:04Z The archive is on the laptop: `~/Work/archive/house-state/state-pre-options-20260926.tar.gz`, sha256
  e9e5c044... MATCHES the box's. 08:05:38Z the uncompressed old state deleted on the box (tarball + sha kept
  in `/workspace/archive/`); box disk 9.4 GB used, 21 GB free. numpy 2.4.4 installed in the House box venv.
  Checkpoint retried in the background.
- 08:05:56Z The Alpha Lab box `ltcm-lab` sb_742fe765 terminated. Boxes not terminated: ltcm-floor, ltcm-data, one
  W4 Gym test box, and the two portfolio-app boxes (not LTCM's).
- 08:09Z **First real inner-loop cycle** (W4, from the laptop): condor-vrp cycle 2 on DeepSeek-V4-Flash (2 model
  calls, 3 tool calls, $0.0012) revised its program and ran `gym_run` on a sealed Gym box (sb_2f98b91a, a fork
  of W1's rehearsal image sbcp_2a16a7aa): 5.4 s batch after a 17 s fork + setup; 144 s wall for the cycle
  (target < 3 min). Box terminated after the test.
- 08:08Z Docs PR #360 merged (merge commit dc3e0192): `docs/` 218 files -> 3 (design.md, operations.md,
  goals/LTCM_OPTIONS_SWARM.md); README 104,630 -> 10,068 bytes (148 lines); `archive/` 221 files with
  `archive/README.md` (a one-page history); CHANGELOG.md started; gateway and deploy READMEs short.
- 08:08:36Z House checkpoint failed a THIRD time even with 21 GB free. The House box runs guest schema 253 (the new
  data box 263): upgrading it to the current Sail runtime while the loop is stopped (disk persists).
- 08:11Z W4's laptop-side trial (real models, real Gym boxes) called GPT-6 Astra once through the gateway with the
  laptop's gateway token: $0.177 of the OpenAI month (inside the $607 cap). W4 raised the swarm's
  `openai_reserve_usd` to $25 so OpenAI roles fall back to Sail until the month is raised.
- 08:38Z The Gym (#358) merged after its review fixes (gym/engine bce0d315: every finding 1-10 and 12 fixed, each
  with a test that failed before; 78 Gym tests; CI 3.11 10m11s, 3.14 11m21s, 4,087 league tests, the Gym's now
  running on CI); main b68b3800. Validation runs return the validation view only, with a 1.5x-stress twin.
- **INCIDENT, the House box.** 08:09Z the main session asked Sail to upgrade the old House box (guest 253) to fix its
  failing checkpoints; the restore onto the new runtime failed (503 "wait for guest exec agent: context deadline
  exceeded") and the box went `interrupted_restorable`. Resume failed at 08:15, 08:20, 08:25, 08:31, 08:38Z.
  Nothing was at risk: the loop was stopped, the grant revoked, the account all cash, the archive on the laptop.
  Recovery: 08:38:41Z gateway kill switch ENGAGED (precaution); 08:39:04Z `floor_box.py fork --from
  sbcp_9dc7fd6b (pre-rebuild-20260922) --name ltcm-house --i-know` -> sb_1d99c4a7-bee2-4226-ba7b-c694ccd857d3.
  **The fork's latch missed the running loop**: the Sept 22 `league run` process (pid 4409) was alive in the
  restored memory (the latch kills only the pids in the pid files); found at ~08:39:30Z, killed by 08:39:48Z.
  It did nothing: no site checkpoint or event (404/empty), gateway orders today still the 2 Wave-0 sells,
  OpenAI calls unchanged, its log's last tick dated Sept 22. Then: Sept 22 state deleted, empty state root with
  STOP, numpy 2.4.4 installed, `.data/ltcm/box.json` repointed (old box recorded under `retired_boxes`), checkpoint
  `house-fresh-20260926` sbcp_a3a46ed8 (30 d) WORKS on the new box (guest 253 on the old runtime); PR #361 points
  the gateway watchdog's SAILBOX_ID at it (215 gateway tests pass); 08:42:32Z kill switch RELEASED.
  Defect for Wave 2b: `floor_box.py fork` must kill every league process (pgrep), not only the pid files'.
  Risk to record: the House box is on Sail's old runtime (guest 253); a forced upgrade by Sail could fail the
  same way. The swarm's Gym boxes are on the current runtime (263).
- ~08:45Z W5 opened PR #362 (`live/options` 52f41e61; 47 files, +8,346 -390): `league/live/` (shadow = the Gym's
  engine one minute behind, a decider child with no secrets, the real book and order path, the money table,
  stops, reconciliation, assignments, the paper proof), constitution `options_money` + a new digest, gateway caps
  by max loss / flex / watchdog / live_stop (247 node tests), `House.site_inputs` merge, the Monday pre-open
  checklist in docs/operations.md. 08:47Z the three-lens adversarial review launched as a workflow (money rules
  and sizing; order path and venue safety; gateway and process boundary; a skeptic verifies each major or
  critical finding) against a read-only worktree at 52f41e61 (`~/Work/ltcm-review-362`).

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

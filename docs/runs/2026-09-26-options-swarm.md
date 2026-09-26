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
| M0 Safe and archived | T0 + 1 h | 08:05:56Z | old House stopped and grant revoked; gzip-tested state archive copied to laptop with matching SHA; old lab terminated (original log below) |
| M1 Data flowing | T0 + 2 h | 06:58Z (T0 + 35 min) | data box downloading since 06:49:43Z; universe chosen (W1) |
| M2 The House is options-only | Sat morning | 07:49:25Z | #359 merged, CI green; updater off, tools off `ltcm`, grant `options-swarm-20260928`, options-only service and tick |
| M3 The swarm is training | Sat 16:00Z | 10:33Z | site reset (07:21Z); the fresh House live on new state (10:22Z); 6 sealed Gym boxes running programs; 48 families, 46 researchers cycling (299 cycles in 11 min, median 79.6 s) |
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
- 08:49:55Z First new-era release on the new House box: `20260926T084913Z-8158a11cfe3f` (main b68b3800, 723 files,
  `real_money` false) canaried and PROMOTED in 44 s with the loop NOT started (watch 0); no box created by the
  canary. previous = main-196fb783261d (Sept 22, old era): **no rollback past 20260926T084913Z-8158a11cfe3f**.
- 08:53:22Z #361 merged (CI green) and the gateway deployed from main 3f660144 (version 8054eecb; the only change
  against the deployed a1f9a8e is SAILBOX_ID -> sb_1d99c4a7). 08:59Z the gateway reads the new box as running.
- 08:58:20Z **Gym image v0** (W1): sbcp_2cde3f22-27b3-4f11-a8db-af3b825df051 (+ copy sbcp_8ef9a704), 30-day TTL, from
  image box sb_366c435f (asleep). Verified inside: no_network, egress fails, no key, no GATE, 0 files after
  2025-12-31, windows train+validation only. Store: 5,341 files; Train (2024) 252 days for each of IWM, QQQ,
  SPXW, SPY, XSP; Validation (2025-01-02..06-04) IWM 105, QQQ 104, SPXW 103, SPY 104, XSP 104. Backfill
  restarted, ~1,100 underlying-days/h. v1 ETA ~10:40Z; gate ~11:30Z. trade_quote calibration (stage 5) moved
  ahead of the 20 names (stage 4).
- ~08:55-09:10Z W4 finished PR #363 (`swarm/loop` a987eb86, CI green): training needs only the Gym image (the gate
  waits for its own); guard line $32 (house_burn_usd_day 1.0); Provider bodies older than an hour blanked; the
  swarm keeps its own event table (cycle rows not mirrored); researchers at reasoning "minimal" (28-64 s a
  turn); V4.1-Flash off (4x the cost at the cache share seen); stall rewrites in the background, 4/day/family
  (moving to pro_asap); pace cap $4/h of model spend; OpenAI only above a $25 month reserve. Laptop trial: 213
  cycles on 3 real Gym boxes, median 71 s, p90 114 s, 99.5% < 180 s; gate path end to end on a real gate box
  with a never-trading program (no strategy's holdout seen). Test spend ~$2 Sail models, <$0.10 boxes, $0.18
  OpenAI. `league/CONTRACT.md` 75.6 KB -> 12 KB. Under a two-lens adversarial review (evidence; spend/process).
- ~09:11Z The shared scratchpad directory was emptied (cause unknown; the main session's helper scripts, briefs and
  queued log, and the builders' scratch files). Running processes unaffected. The main session's files now live
  in `~/Work/.ltcm-main/`; builders told to keep theirs under their worktree's `.data/`.
- ~09:08Z **The money review of PR #362** (15 agents): 29 findings, 10 CONFIRMED by a skeptic, 2 refuted, 17 minor
  (unverified). Critical (two lenses, one bug): a program's resting close on an expiring near-money equity
  structure blocks the House's forced close (step.py:941), carrying it past the cutoff. Major: `one_record` drops
  real trades whenever the shadow traded that day (real results never reach Sized/Kelly); Sized never below the
  Probe cap (outside eighth- to half-Kelly; family 12% -> 30%); candidate -> sized skipping Probe; another
  family's resting open blocks exits on a shared contract; closes and cancels bypass the order governor and exits
  have no protected room below the gateway's 300; one malformed intent aborts every family's minute; the shadow
  stops reading legs that leave the program's window. Refuted: forward record per family vs per version; the
  parent-filled-legs-uncovered claim. All sent to W5 to fix with tests (`.data/w5/review362.md` in its worktree).
- 09:14Z **The swarm review of PR #363** (20 agents): 24 findings, 16 CONFIRMED (12 major after the skeptic), 2
  refuted, 6 minor unverified. Deploy blockers: the Sail guard fails OPEN on a failed balance read; researchers'
  notes would publish fitted PARAMS and code fragments to the site; box startup failures re-fork l boxes forever;
  stray boxes never adopted or terminated; a slow heartbeat starts duplicate swarm processes; the supervisor could
  signal a reused pid (even the House); full Gym results kept forever on the House disk; timed-out Gym jobs still
  run. Evidence: a failed nightly replay wipes the forward record; a market day counted twice (nightly + shadow);
  refused/failed programs offered to live as tuition; forward records not tied to a version; no Astra audit at
  the gate. Refuted: the three-looks limit bypass by forks; boxes left awake on stop. All sent to W4 to fix with
  tests before the deploy.
- ~09:25Z W5 pushed its review fixes (#362 head 0735ef77, CI green, gateway 252 tests): all 10 confirmed + 16 of 17
  minors, m13 kept with a reason. Money digest moved again (options_money.gateway.max_day_open_orders 250);
  gateway MAX_DAY_OPEN_ORDERS 250, MAX_DAY_USD back to 4000, MAX_DAY_USD_ALPACA 10000; a family moved onto
  real money trades from the NEXT session. W4 pushed its fixes (#363 head 9508c032, CI green): all 22.
- ~09:55Z **Fix verification** (10 agents, both PRs): #363 16 fixed, 6 partly (C1 lineage trial count, C7 audit
  without OpenAI room, C11 fitted values as words still public, C13 reconcile can kill a box mid-fork, C16
  daily cap on estimates, M4 stale gate snapshot) + 1 major regression (a holdout look cut off by a restart is
  never recorded or retried) + 6 minor. #362 19 fixed, m13 kept (accepted), C2 NOT fixed (probe -> sized five
  minutes later with no real Probe trade), 6 partly (C5, C7, m2, m6, m9, m16) + 8 regressions (3 major:
  broken-leg resend stamp without a day; forced window refusing closes of any expiring structure; the
  instance order budget refusing a program's own exits). Both back to their builders; the swarm deploys for
  training after the public-notes fix (C11), the gate-side fixes land before the gate image.
- 10:21:31Z The swarm's training stage merged as PR #364 (the reviewed swarm up to W4's d2b365a1: C11 public notes
  refuse number words, ':' and parentheses, and the role prompt says notes are public; C13a forks recorded before
  their POST); main 310225ae. #363 continues with the gate-side fixes.
- 10:22:17Z Release `20260926T102142Z-e71ed057c625` canaried and PROMOTED (loop stopped); previous =
  20260926T084913Z-8158a11cfe3f (the rollback floor holds). 10:22Z `/workspace/state/swarm.json` =
  {"enabled": true, "gym": {"enabled": true, "image_checkpoint": sbcp_2cde3f22 (Gym v0), "gate_checkpoint": null}}.
- 10:22:29Z **The new House started** (`floor_box.py start`: supervisor 5318, loop 5322). First tick 10:22:26Z:
  budget open, books alpaca-paper + options-shadow reconciled, living 0 (no old-style agents), real_money false.
  The swarm process (pid 5336, niced) started 10:22:27Z: 48 families founded, 0 boxes adopted; the gate
  "waiting" (no gate image). 10:23Z six sealed Gym boxes `ltcm-swarm-gym-*` running. The site's first new-era
  checkpoint at 10:22:27Z: schema 2, run.started_at 10:22:21.321Z, account equity $481.63.
- 10:47:10Z Stage 1 of the backfill (core five 2023-2025) complete: 0 empty, 0 failed tasks. 10:58:44Z **Gym image v1**:
  sbcp_4f1f0577-9b32-4e8d-b610-480bb88d617d (+ copy sbcp_204a6762), 365-day TTL, image box sb_a9eca175 asleep;
  verified inside (no_network, no key, no GATE, nothing after 2025-12-31). Store: 3,760 root-days of 1-minute
  NBBO (1.63 billion rows, 6.95 GiB); Train 2023-2024 502 days per root, Validation 2025 250 per root, for
  IWM, QQQ, SPXW, SPY, XSP; underlying for all, OI 3,759. Holdout (stage 2, 920 root-days) next; the gate
  image builds itself when it completes (~11:50Z); then 2022, trade_quote, the 20 names.
- ~10:52Z W5's round-2 fixes pushed (#362 769243f4, CI green): C2 (Sized only after 5 real Probe trades and a whole
  session at Probe; money digest -> 8dba0b1f), C5/R4 (waiting exits persisted), C7 (legs refuse bad types;
  pending and forced closes isolated), m2, m6 (credit latch gone), m9/R8, R1-R7, and two more it found (a
  waiting exit after the cutoff; the live path not following swarm.json). Under a third verification.
- 10:55Z #363 (the swarm's fixes through 4026a42c) merged; deploying with the gate off. W4's stage 3 is PR #365.
- 10:55:51Z #363 (through 4026a42c) PROMOTED as `20260926T105515Z-b25acc7981e2` (the House restarted at 11:05:52Z
  after the watch; the swarm took the new release; 0 failed jobs since).
- 11:57:47Z **Gate image v1** (W1's waiter, before it stopped): sbcp_61d027f4-ba8c-4e9e-8f0a-c9be4f9be28c (+ copy
  sbcp_74aaa06a), 365-day TTL, box sb_fdd0b97d, gate mark present, windows holdout+train+validation, 14,109 files,
  2022-01-03 .. 2026-09-25. gate_checkpoint stays null until the swarm's stage 3 (#365) lands.
- **~11:06-14:14Z the session was stopped by the account's weekly usage limit** (W1, W4 and two verification agents
  died with it; the owner bought credits and said "continue" at ~14:14Z). The House, the swarm and the backfill ran
  on their own throughout. W1's laptop-side waiters died (the gate image had been built at 11:57Z).
- 14:14Z Swarm after 3 h 52 min (verify_swarm on the box): 9,549 trials, 9,449 program-years; 3,000 cycles in the
  last hour, median 29.2 s, 2 errors; first tournament 13:23Z: 44 on the board, 18 validated, 0 gate-ready, 7
  retired ("no validation improvement in 31-52 revisions"), 1 born (a fork); 44 alive, 11 retired; pool 6 boxes,
  1,214 batches, 8,245 jobs, 0 failed, 30,973 program-years in 25,002 box-seconds (~8,000 program-years/h);
  spend $4.63/h (models $3.46, boxes $1.17); guard: balance $99.17, line $32, burst spent $19.40, not braked.
  The verify script's population check FAILs only because 44 < 48.
- 14:15Z swarm.json -> Gym v1 (sbcp_4f1f0577); gate still null. W4 and W1 resumed; the #362 round-2 verification's
  two lost agents re-run.
- 15:04:30Z **Codex continuation started; T0 is unchanged.** Read the handoff, this record and the full goal;
  reconciled local worktrees, GitHub and the running House. Persistent goal created for the engineering,
  testing, data, paper/shadow deployment and operational-readiness work. This continuation does not execute
  real-money orders or activate autonomous brokerage trading; real-money activation remains an owner action.
  No live grant is enabled or ratified, and `real_money` remains false. The original goal's market-session
  and post-close milestones remain open; no future result is claimed.
- 15:01Z takeover readings: House release `20260926T105515Z-b25acc7981e2`, supervisor 5318 / loop 5684,
  healthy ticks; swarm pid 5708, matching release, 46 active families and 14 retired, 11,408 trials,
  13,019.71 recorded program-years, 2,781 recent cycles, median 40.2 s and 99.6% under 180 s. Zero
  validation-ready families at the latest tournament (14:23:56Z), zero holdout looks/passes. Population
  reports FAIL on the old verifier's fixed 48 threshold; the running population is inside the configured
  floor/ceiling. Gateway OpenAI $596.29/$607; Sail $96.43, swarm booked pace about $3.96/h, $32 guard.
  Brokerage read: equity $481.63, cash $481.60, no open orders, only the previously recorded LTC dust.
- 15:02:16Z W1 resumed and verified later progress omitted from the handoff: PR **#366** already exists,
  CI green at `f8ce1b3d`. Core 2022 is **1,255/1,255** (the failed XSP day was recovered); stage 1
  3,760/3,760, holdout 920/920, calibration samples 755/755; names 2,868/23,740 (68 vendor-empty,
  zero failures), back months 0/2,374. Verified Gym v2b from 14:46:50Z adds core-five Train 2022:
  `sbcp_c9820e03-418a-46b4-b9a3-01dbe7ae3688`, backup `sbcp_69a14100-a70f-43aa-be7d-306734b783f5`.
  The House has not been switched to it yet.
- 15:04Z Three builders resumed in the existing W1/W4/W5 worktrees; the main session owns merges,
  deployment and independent verification. One laptop test process is enforced with
  `/tmp/ltcm-options-tests.lock`. W4 found a further image-binding gap in the current-best validation
  shortcut. W1 found missing nightly supervision/checkpoint handoff, a download-failure exit-status
  defect and a fixed-UTC winter scheduling defect. These are being fixed with behavioral regression
  tests before deployment. The nightly target is Tuesday Sept 29 06:00Z, then 02:00 New York time.
  Owner funding confirmation requested; existing funded caps remain in force.

- 15:36Z **Funding confirmed by the owner:** Sail now $200, OpenAI credit $124 (previously stated
  $24; a $100 addition). Brokerage stays around its current balance; no new deposit confirmed.
  Read-only gateway snapshot: Sail $194.50 after ongoing charges, OpenAI September $596.29/$607,
  brokerage equity $481.63/cash $481.60, no open orders/options. Swarm: 12,801 trials, 44 alive,
  16 retired, 15,784.66 recorded program-years, 2,438 cycles/hour, median 55.37 s, two recent errors;
  booked pace $3.4873/hour (Sail models $2.688 + Gym $0.7993), zero gate-ready/holdout passes.
- 15:38Z **#366 merged** at reviewed head `5781ce3d`, main `ee055804`; Python 3.11/3.14 and gateway CI
  green. W1 verified the deployed data scripts and a sealed-gate nightly rehearsal (15 historical
  files, SHA checked, separate rehearsal checkpoint, rehearsal box terminated). Production gate
  unchanged. Root confirmed the SIP read path from the House: September 25 SPY produced 390
  completed-minute rows, 09:31–16:00 ET. No real order was sent.
- 15:38Z **Production child isolation verified** on a source snapshot, not an active deployment:
  host uid/gid 65534, no supplementary groups, no-new-privileges, private network namespace with
  no IPv4 routes, no outbound connection, dummy secret read denied, dummy state write denied,
  root-owned read-only runtime, and a synthetic program matching the inline decision. This kernel
  exposes dormant `sit0` alongside loopback; the portable regression now checks routes/addresses.
  Private evidence is under `~/Work/.ltcm-main/house-isolation-review.json`.
- 15:41Z **#367** adds the House's nightly supervision, stopped-fork cleanup and the SIP relay.
  Independent review reproduced and fixed two supervisor races: a job starting just before a
  release-handover TERM, and a temporarily unreadable child start identity. 52 focused tests pass;
  independent reruns confirm both repairs. Full CI pending at `f4d8fcb9`.
- 15:41Z **#368** applies only the confirmed $100 OpenAI addition: September aggregate cap
  $607 -> $707, still below metered spending plus confirmed credit. A funded-month guard prevents
  an unfunded October renewal. Independent review and 217 gateway tests pass; CI/deploy pending.
- 15:42:13Z **Funded research pace set:** private `swarm.json` model ceiling $4 -> $2.25/hour, with
  other guards unchanged. At roughly $0.8/hour Gym plus data/House costs this leaves room to keep
  training toward Monday with the $32 Sail reserve. The previous config is backed up on the House.
  Reconcile actual burn again before changing throughput. No trading limit or grant changed.
- 15:42Z Verification continues before #365/#362 merge. Root reproduced a stale holdout-image
  promotion when only the gate checkpoint changed; W4 is fixing it while preserving the consumed
  look. Independent W5 review reproduced a concurrent band/evidence race that could undo a
  demotion; W5 owns its fix. Evidence thresholds stay unchanged.
- 15:52Z **#368 merged and deployed.** Main `647c8384`; gateway version
  `e602bdb4-59ca-4c29-9977-098a97faeb58`. The post-deploy status confirms September's cumulative
  OpenAI cap $707, metered spending $596.29, kill switch false and no change to today's order
  counters. October cannot reuse the September funding automatically. Real option opens stay off.
- 15:56Z **#365 merged** at reviewed head `5d03099a`, main `49df3d9b`. Its tests and CI passed.
  The running store's private backup migrated in 0.008 seconds and reopened in 0.001 seconds:
  60 families, 44 alive, 2,592 versions, no holdout looks, SQLite integrity `ok`. The production
  store was not mutated by this rehearsal. Gate selection remains null pending final SIP images.
- 16:02Z **#367 merged** at reviewed head `acee1211`, main `8d1a7354`, all CI green.
  The committed source passed 223 integrated tests on the House. Private data/image/calendar/
  calibration metadata is installed at `/workspace/state/data`, hashes verified, files 0600;
  supervision remains disabled until the integrated House release is verified.
- 16:03Z Funded-pace observation: Sail $193.68, booked swarm cost $2.9593/hour (models $2.1612,
  Gym $0.7981); 13,546 trials and 17,268.75 recorded program-years, 44 alive/16 retired,
  median cycle 60.15 seconds, 2,057 recent cycles and one error. No validation-ready family or
  holdout look. The verifier's default 48-population check is a founding target, not the adaptive
  floor (16); current population is within the planned range. Brokerage remains $481.63 equity,
  $481.60 cash, no open orders/options, only LTC dust.
- 16:04Z W5's five additional repairs independently reproduced: atomic band/evidence confirmation,
  expired broken-structure recovery, funding/equity snapshot consistency, cumulative-fill value
  accounting, and promotion time persisted with the band transition. A residual old-local/new-
  durable timestamp mismatch was also fixed. Head `11b6f1f2` passed 163 focused tests on the House;
  the production-kernel isolation probe passed again (uid/gid 65534, no extra groups, no network,
  dummy secret/state access denied, read-only runtime, synthetic decision parity).
- 16:05Z Root found and assigned a wiring mismatch: market-data authentication must use `alpaca`
  even with real execution disabled, as the goal requires. Read-only entitlement probes actually
  returned HTTP 200 for OPRA through both credentials, so this was a plan/credential-routing
  defect, not evidence of an observed subscription outage. Paper inventory is **nine legacy
  positions and zero open orders**: seven stock fractions and two SOFI Oct 2 puts. This supersedes
  the handoff's claim that closes are still queued; Monday must inspect/clear or explicitly retain
  them in its paper accounting, not assume they disappeared. No order was sent by this probe.
- 16:05Z #369's committed completion/nightly/locking tests passed on the House: 52 run, 15 skipped
  because that box deliberately has no Arrow/Polars (the data box does). Data-side scripts and the
  sealed forward rehearsal were separately verified by W1. #370's daily-statistics feedback
  correction passed independent review, 29 focused laptop tests and its on-box regression. Both
  await full CI. Wave 2b is being built only as a draft and will not merge before Monday's close.

- 16:21Z #369 and #370 passed full CI and merged. Main `570f023c` is running as House release
  `20260926T161049Z-6a9300a67fbb`; the canary and the complete ten-minute watch passed, with the
  final promoted verdict at 16:21:27Z. The House and swarm heartbeats are fresh and no health
  failure is reported. Real money remains off. The previous release is
  `20260926T105515Z-b25acc7981e2`, safely after the archived-House rollback boundary.
- 16:12Z The private forward/completion seed was installed with matching hashes and restrictive
  permissions. After verifying the exact deployed sources, root enabled the data worker and the
  full-completion daemon. The collector holds its process-identity lock, reports a fresh heartbeat
  and waits for **Tuesday Sept 29 06:00Z**. Completion is waiting on the healthy Theta backfill,
  with no error. Active Gym/gate pointers were not changed. The final SIP-complete images and
  Train-only calibrated fill model remain Sunday work.
- 16:27Z #362 head `285f7135` passed 135 focused tests on the actual House. Root independently
  reran the four adversarial paper-proof probes: an ambiguous open survives restart under the same
  client order ID; uneven partial fills never pass and owned inventory is cleaned up; an unfinished
  prior-day proof survives restart; unavailable position evidence blocks dispatch. All four now
  produce the expected outcomes. These are synthetic fault probes, not a venue route proof.
- 16:34Z The owner requested a quieter website: only Profit and Running at the top; a bare balance
  chart; durable LTCM-partner names; an Agents dot-stage view with strategy/results on click; and
  genuine agent notes as the prominent live hook. W4 is finishing desktop/mobile/browser checks
  in the separate personal-site worktree. Root reviewed the first captures. No invented activity
  or fixture P&L will be published. The production site still awaits that reviewed deployment.
- 16:34Z Root's #371 adds a public aggregate of the complete real-options book, including retired
  families, fees and partial closes. Independent review found and fixed persisted-freeze and
  concurrent-fill errors; 35 focused tests pass locally. A quote-update revision fence is being
  coordinated with #362 so bid/ask columns cannot be mixed across updates. The new site schema
  must deploy before this publisher. Existing account movement, deposits, compute and crypto dust
  do not become the website's Profit number; no real options trades means zero.

- 16:42Z Personal-site #10 merged at `0458a88` and deployed as Worker version
  `2506e646-25d9-4e7e-a2be-082c3b9ad3ca`. All 55 tests, production build and deployment dry run
  passed. Independent production Chromium checks saw the real 66-family roster (49 Practice,
  17 retired), durable partner aliases, two headline metrics, no standalone structures/table,
  and readable details on a 375px phone. Keyboard/focus, 320px/390px layouts, thought dwell and
  expansion, simulated live updates and stale-value behavior passed separately. The production
  WebSocket connected; no new thought was invented during the research pause.
- 16:45-16:49Z #371 and final #362 head `7cf0dff8` passed full CI and merged; main is `4472c334`.
  Final W5 parity/paper tests passed 23/23 on the House, including persisted recovered fill answers
  and concurrent quote revisions. Profit passed 35 tests on the House (one cross-site Node test
  skipped because the box has no site checkout; numpy tests **did** run). The integrated actual-W5
  synthetic book produced -$6.28 open and -$12.57 closed including fees; frozen/concurrent records
  withheld their public value. The earlier description of that skip as numpy-related was incorrect.
- 16:49Z Gateway main `4472c334` deployed as `20a6b706-3f78-4690-8da4-e2d711cb80cc`, keeping
  `OPTION_STRUCTURES_REAL=off`, September funded month and $707 OpenAI ceiling. House release
  `20260926T164943Z-04457584301d` passed canary and promoted at 16:50:15Z; its ten-minute watch is
  still running. At 16:53Z the actual House has `options_live=true`, session state `closed`, no
  health failure, and `real_money=false`. Swarm and forward worker restarted on the same release;
  the latter still waits for Tuesday 06:00Z. The site first published verified Profit **$0.00** at
  16:50:47Z. No grant activation or real order was performed.
- 16:54Z The quiet public notes were traced through both cursors: publication was caught up to the
  ledger and swarm source. Research was paused by its combined $2.25/hour pace: $2 of unresolved
  OpenAI architect reservation plus Sail spend exceeded it. #372 introduces an optional separately
  funded Sail pace, keeping the existing OpenAI holds and month/burst limits. Independent review
  passed 45 checks, and the exact head `e3e66525` passed 70 tests on the House. CI and deployment
  are pending; the private setting has not been switched yet.
- 16:54Z Root found the paper proof was coupled to real execution. #373 (`4b9f8757`) schedules the
  existing bounded paper proof with no real client/book/grant/family, preserving restart ownership
  and weekend silence. 114 focused tests passed both locally and on the House. Independent review
  and full CI are pending. This is synthetic evidence only; the actual paper route remains Monday's
  check. Separately, W5 is reproducing/fixing a researcher protocol defect where a refused Gym
  call could be described as a completed experiment; no evidence requirement is being loosened.

- 17:00:15Z House release `20260926T164943Z-04457584301d` finished its ten-minute watch with
  verdict **promoted**, every poll passing. At 17:05Z the House, swarm and nightly worker were
  healthy on that release; real money remained off, no grant existed and the real-options book
  was empty. Production Chromium also confirmed **$0.00 Profit** on the deployed site.
- 17:05Z #373's independent review passed three additional service-factory probes and 31
  focused regressions. Its gateway and Python 3.11 CI passed. Both #372 and #373 encountered
  the same pre-existing Python 3.14 watchdog stress failure: one `ENOENT` while reading through
  `current` during atomic symlink swaps. Twelve isolated repetitions passed locally and twelve
  on the House; the full-suite failure remains under investigation, with neither PR merged.
- 17:07Z The bounded protocol repair #374 (`57a6c016`) passed 55 researcher/loop tests on the
  House, plus independent three-probe review. It keeps refused inputs in REVISE, records a
  missing required tool call as a failed cycle, and preserves the sole dispatched-run allowance
  and late trial accounting. Full CI is pending. This edge defect does **not** explain the
  sampled terminal thoughts: all 150 recent terminal responses followed actual runs, and all
  87 required calls in the last 300 requests contained a tool call. The separate observed waste
  is researchers repeatedly testing no-op programs while declaring themselves finished. An
  explicit Gym-only retirement action is being implemented, preserving evidence, population
  floor, lineage, live exit ownership and existing thresholds; prose alone will never retire a
  family.

### Monday pre-open and forward-run checklist (prepared Saturday; results still pending)

This continuation prepares paper/shadow operation and leaves `real_money=false`, the grant
disabled and real-option openings off. The original plan's real-money milestone is not claimed.

1. Before 12:00Z Sept 28, reconcile the exact deployed release, latest backup, House and swarm
   heartbeats, data collector lock/start identity and heartbeat, free disk, Sail reserve and funded
   OpenAI allowance. Read the final image/calibration identities and the current engine bundle.
   Every eligible family's validation and holdout evidence must match those identities.
2. Read the actual session/expiry/event calendar; inspect Candidate and paper instance lists,
   missing quotes, unresolved positions/fills, stops and alerts. Read the brokerage and paper
   accounts separately. Do not call a pending deposit trading profit or assume funding landed.
3. Reconcile the nine inherited paper positions against current positions/orders. Record their
   disposition separately from the swarm. The one-lot SPY paper route proof must open and close
   successfully on the venue; synthetic tests and historical rehearsal do not satisfy this check.
4. At 13:30Z, run Candidates in live shadow and observe the paper proof. Record actual simulated
   and paper fills, rejections, quote staleness, buying power, attribution and execution latency.
   No strategy qualifying is a valid result to report. It is not permission to lower the evidence
   requirements. No deploy from 13:25Z through 20:05Z except a rollback.
5. Inspect every 30 minutes during the session and reconcile after 20:00Z. Report options P&L
   separately from funding and all compute/data costs. Only then consider the reviewed Wave 2b
   merge after 20:05Z, with its before/after repository and CI measurements.
6. Tuesday Sept 29 06:00Z: verify the actual first forward collection, SIP ingestion, sealed gate
   copy/checkpoint and consumed manifest for Sept 28. The Saturday rehearsal is not that run.

The production index level is inferred from option parity because Alpaca does not supply an
underlying index feed. Its September 2 launch notice confirms both live index-option support and
that data limitation ([Alpaca release](https://alpaca.markets/blog/alpaca-launches-index-options-via-trading-api/)).
Parity is an estimate, not an official cash-settlement value; unresolved settlement evidence must
be reported as such. Venue cutoffs and refusals must be observed, not inferred from a passing test.

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
- 10:33:10Z **M3 holds** (`scripts/verify_swarm.py --root /workspace/state` on the box, +11 min): process PASS
  (pid 5336, heartbeat 11.6 s, release = the House's); 48 families alive, 46 running; 299 cycles in the first
  11 minutes, median 79.55 s, 3 cycle errors; 331 trials (331 program-years); pool: 6 Gym boxes (4 ready, 2
  busy), 64 batches, 0 failed jobs, 1,158 box-seconds (~30% busy); spend $0.54/h (models $0.47, boxes $0.07);
  guard PASS (balance $115.56, line $32, not braked, 28.6 GB free); ledger PASS (48 swarm.born, 47 swarm.note,
  0 House agent.born); gate WAIT (no gate image); tournament not yet (due an hour after founding, ~11:22Z).
  The researchers, not the Gym, are the bottleneck.

### T0 + 4 h (10:23Z Sept 26)

| # | Metric | T0 + 4 h |
|---|---|---|
| 1 | Net since the reset | options P&L $0 (no option order yet); compute since T0: Sail $118.79 -> $116.08 (-$2.71, mostly the swarm's laptop trials), OpenAI $0.18 (one architect call in a trial); ThetaData $80/mo, market data $83/mo accrue |
| 2 | Data: underlying-days in the store | at 10:11Z: core five 2023-2025 3,136 of 3,760 (Gym v0 cut at 08:58Z: Train 2024 252 days per root, Validation Jan-Jun 2025 ~104); holdout 3 of 920; 2022 0 of 1,255; the 20 names 0 of 23,740; trade_quote 0 of 755; back months 0 of 2,374; ~1,000-1,300 underlying-days/h (ThetaData-bound); target core five 2023-2025 by 12:00Z: on track (~10:40Z) |
| 3 | Gym throughput | laptop: ~425 program-years/hour/core (typical programs 16-20 s a program-year; worst 66 s); on Sail: not yet measured on the box (6 Gym boxes starting at 10:23Z); laptop trial of the swarm: 213 inner-loop cycles, median 71 s, p90 114 s |
| 4 | The search | 48 families founded at 10:22:27Z on the House box; trials: 0 on the box (laptop trials excluded) |
| 5 | Evidence | 0 validation passes; 0 holdout looks (the gate waits for its image); leakage alarm silent |
| 6 | Forward | none (first forward day Monday) |
| 7 | Execution | no option order; the live path (PR #362) in its second fix round |
| 8 | Compute | Sail balance $116.08 (owner top-up pending); OpenAI month $596.29 of $607 (cap not raised: unfunded); ThetaData Standard |
| 9 | Harness | House restarts: 1 (the new House start); CI ~10-11 min; main 310225ae: 988 files (from 1,103), 353,272 lines (from 360,821); docs .md 3 (from 119); README 10 KB (from 105 KB); league/CONTRACT.md 12,048 bytes (from 75,558; rewritten for options by the swarm PR) |

### T0 + 8 h (14:23Z Sept 26)

| # | Metric | T0 + 8 h |
|---|---|---|
| 1 | Net since the reset | options P&L $0 (no option order); compute since T0: Sail $118.79 -> $99.17 (-$19.62: the swarm ~$17.4, trials and boxes the rest), OpenAI $0.18; ThetaData and market data accrue (~$0.9 so far) |
| 2 | Data | core five 2023-2025 3,760/3,760 (done 10:47Z); holdout 920/920 (in the gate image); 2022 1,254/1,255 (XSP 2022-06-29 fails: ThetaData INVALID_ARGUMENT "expecting 11 fields, got 8"); trade_quote 755/755; the 20 names 1,660/23,740; back months 0/2,374; 1,644 underlying-days/h; names ETA ~03:40Z Sunday. Gym v1 (Train 2023-24, Validation 2025) and the gate image built |
| 3 | Gym throughput | ~8,000 program-years/h on 6 l boxes (30,973 in 6.9 box-hours) (target 2,000 by Saturday evening: met); inner loop median 29 s (target < 3 min: met) |
| 4 | The search | 44 alive, 11 retired, 1 forked; 9,549 trials; 3,000 cycles/h; architect passes due every 4 h |
| 5 | Evidence | 18 validated, 0 over the validation line, 0 holdout looks (gate off pending #365), leakage alarm silent |
| 6 | Forward | none yet (first forward day Monday) |
| 7 | Execution | no option order; the live path (#362) in its third verification |
| 8 | Compute | Sail $99.17 (owner top-up pending; the guard brakes at $32: ~14 h at $4.6/h); OpenAI month $596.29 of $607 (unfunded: roles on Sail); ThetaData Standard |
| 9 | Harness | House restarts: 3 (start, #363 deploy, watch); CI ~10-11 min; the session lost ~3 h to the usage limit |

## Report

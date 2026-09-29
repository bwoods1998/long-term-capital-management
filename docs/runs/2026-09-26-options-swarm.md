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

- 17:12:42Z #372's unchanged head passed its failed-job rerun and merged as `079de48b`; #374
  passed full CI and merged at 17:16:07Z as `bc122348`. These changes are not deployed yet.
  Research resumed under the existing rolling pace by 17:10Z as older Sail spend aged out.
- 17:19:34Z A 30-day House recovery checkpoint was saved before the upcoming researcher-state
  changes: `sbcp_797f731a-e823-4f04-b68b-42cc4ce057be`. It is private and must not be forked into
  an independently running House.
- 17:20:58Z The production browser received nine genuine `agent.note` WebSocket events and
  displayed an incoming note in the main thought card automatically, with no refresh or script
  error. Profit remained **$0.00** and transport was live. The screenshot also confirms the
  underlying workflow issue: most recent notes declare failed mechanisms finished. Explicit
  retirement, not cosmetic replacement text, is the pending correction.
- 17:21Z The instrumented full Python 3.14 suite on main `4472c334` passed 4,649 tests in 531s
  (25 skips), with no captured symlink failure. The intermittent CI failure has no confirmed
  root cause; no production behavior or assertion was weakened. #373's failed job is being
  checked again. The unchanged watchdog code also passed main and draft-prune CI.
- 17:22Z Draft Wave 2b #375 had passed Python 3.11/3.14 CI in 101s/107s on `7c22d55a`; its
  subsequent canary cleanup `67d0946e` passed 160 House/operator/watchdog/grant/Profit tests on
  an isolated snapshot on the actual House. Root's bounded read found no confirmed regression,
  but full independent review and integration of newer main fixes remain. The draft has not
  been deployed and must not merge before Monday's close.
- 17:26Z Merged paper-route readiness #373 at `7645e202` after the unchanged failed CI job
  passed. Its 114 local and 114 House tests plus independent service-factory probes cover the
  paper proof without a real client, real book or grant. Monday's actual venue round trip is
  still pending. Deployed main `7645e202` as `20260926T172613Z-f62e2af878bb`; the canary and
  full ten-minute watch passed, with final promotion at **17:36:52Z** and no health failures.
  The new swarm and nightly collector run from that release; the latter still wakes Tuesday
  September 29 at 06:00Z. Read-only post-deploy checks confirm `real_money=false`, no live grant,
  and no real options positions or orders in the book.
- 17:28Z Selected the separately funded Sail researcher allowance of **$2.25/hour** using
  #372's optional `sail_usd_per_hour`; the prior combined allowance remains a fallback. The
  state update has a private backup and receipt. The $32 Sail reserve and OpenAI month cap of
  $707 are unchanged; an unresolved $2 architect reservation was not discarded. At 17:29Z the
  swarm reports 49 alive, 19 retired, 46 running, 14,764 trials and 19,515 program-years; its
  Sail pace is unpaused. Last-hour model and Gym spend total $1.11 and Sail balance is $191.93.
  No validation pass or holdout look has occurred; these are throughput figures, not evidence
  of profitability.
- 17:34Z Draft #375 integrated current main at `b13c968f`. Full CI is green (Python 3.11/3.14
  92s/109s, gateway 7s), and its updated paper/House/swarm modules passed 88 tests on an isolated
  snapshot on the actual House. It remains unmerged and undeployed until after Monday's close.
- 17:39Z Explicit researcher retirement is under review. Independent probes confirmed three
  defects in the first implementation: an already-running decision could open after retirement;
  a gate review completing after retirement could start another paid audit; and a retired
  family's stale in-flight gate marker could survive restart. Corrections and regression tests
  are in progress, with a second independent review of order admission and transaction boundaries.
  The data completion worker remains healthy: names 7,695/23,740, no failing stage; final images
  and calibration have not been adopted.
- 18:06Z Researcher retirement #376 is merged as `8c9216b6` and deployed in release
  `20260926T175520Z-f47c08cd0535`; the complete ten-minute watch passed. The three independent
  findings above were corrected and reproduced with regression probes. Exact-source verification
  on the actual House passed 275 tests. Researcher-requested retirement preserves strategy,
  trial and lineage evidence, look reservations and owned exits; admission rechecks identity and
  eligibility before creating an order. Retirement-floor refusals back off instead of spinning.
  Thirty researchers retired themselves shortly after rollout; the live population subsequently
  reached its floor of 16 before the existing architect refill. This is search turnover, not an
  evidence pass. House and both worker heartbeats are fresh; real money remains off.
- 18:14Z Agent promotion rings and click-through checklists are merged and deployed on the site
  (#11, main `0984954`, Worker `7959f35b-0f7d-4bad-b9a5-85dbe060c533`). Rings count only verified
  current prerequisites; stale or missing evidence clears them. Independent browser review
  caught and verified a stale-ring fix. The runtime publisher #377 passed both full CI suites,
  independent comparison against 450 promotion-policy cases, and 78 actual-House tests with
  two expected site-schema environment skips. Its read-only live-data rehearsal produced
  13 eligible progress projections among 16 active families in 0.074s, without publishing private
  scores or changing evidence. Deployment waits for site #12: old open tabs strictly reject a
  newly added field, so current pages explicitly request progress while legacy reads retain their
  original shape. All 63 site tests and the independent original-client probe passed.
- 18:14Z Draft prune #375 is at `ccf9cc27`, incorporating the retirement release; its 277 affected
  tests and full CI passed. It remains unmerged and undeployed until after Monday's close. An
  independent review of its money behavior, imports and deployment paths is underway; the next
  publisher merge will also need folding into the draft.
- 18:20Z Site compatibility #12 is merged as `5abc570` and deployed as Worker
  `e473bcbc-0200-480a-92e0-de2001d55b20`; both default and opt-in public reads return correctly.
  Publisher #377 is merged as `60b34dd9`; release `20260926T181814Z-b4bc25619f84` passed canary
  and restarted at 18:18:53Z, with its ten-minute watch still pending at this entry. The actual
  public record contains 16 active agents, 13 with verified progress. Chromium production checks
  at widths 1440, 390 and 320 found no overflow or page errors, correct 11-check detail, retained
  keyboard focus, working automatic checkpoint refresh and Profit $0.00. Live transport connects;
  this short observation had no new thought frame, so the earlier actual thought-rotation proof
  remains the recorded evidence of incoming thought display. Default reads omit progress and
  keep old tabs valid. Real-money config is false; the real options book has no positions or
  orders and no grant is installed.
- 18:25Z The owner clarified that each dot must give direct, dynamic sight of that agent's
  progress to the next level. An additional local browser rehearsal verified increasing and
  decreasing evidence move only the affected ring, an actual band change moves its dot to the
  next stage, and the selected detail stays open. These were synthetic local fixtures, never
  published to the real site; no claim that a production strategy has promoted.
- 18:27Z Independent review of draft #375 found a rollback guard gap: assigned shares can
  remain after option positions/orders disappear but before reconciliation freezes. The draft
  now refuses a target missing exit support while assignment, shares or reconciliation mismatch
  remain. Fix `669befe8` includes a synthetic actual assignment with a rate-limited share close;
  126 affected tests passed, exact-head re-review and CI are pending. The draft also incorporates
  #377 and its folded calendar import. It remains unmerged and undeployed.
- 18:29Z Publisher rollout `20260926T181814Z-b4bc25619f84` completed its ten-minute watch
  without a failure and received the promoted verdict at 18:28:53Z. House, swarm and nightly
  worker identities match the release; next forward wake remains Tuesday 06:00Z. The original
  pre-progress website validator also accepted the actual production default checkpoint after
  the new publisher started. The progress display is live and verified; this does not change the
  strategy-evidence or real-money readiness state.
- 18:31Z Draft #375 final head `cadba222` passed independent re-review and full CI (Python
  3.11 98s, 3.14 81s, gateway 7s). Review also caught malformed falsey paper-proof state being
  treated as empty; all five malformed cases now refuse the unsupported target. An exact archive
  on the actual House ran 175 tests: 173 passed and two optional site-schema environment checks
  skipped. The draft remains unmerged and undeployed for Monday after 20:05Z.
- 18:35Z Independent final-data preparation found and corrected three private audit gaps:
  Train/Validation identity omitted session/expiry control metadata; active forward-day receipts
  could bypass a new nightly copy; and an inherited model-path override could differ from the
  file being hashed. Fifteen synthetic tests passed after correction. Root separately ran the
  effective-model audit in the actual isolated 25-file Gym bundle and verified matching identity
  with no writes. The plan now compares canonical calendars to the final source, preserves and
  rejects unexpected active/staged forward receipts, and checks the effective loaded model in
  each restored Gym/gate environment. No production adoption or checkpoint restoration occurred.
- 18:37Z Recorded a new 30-day House recovery checkpoint,
  `sbcp_939a5990-309b-4aa1-b643-add639dafb0a`, generation 1595, expiring October 26 18:37:41Z.
  Creation succeeded; no restore was exercised and no clone was started. The current handoff
  now precedes the historical Claude handoff and includes deployed identities, funding, evidence,
  the staged prune and the remaining Sunday/Monday/Tuesday actions. The overall goal stays active.
- 18:55Z A read-only completion watch is following the existing data process, PID 22487 with
  start ticks 3310972, and the House completion supervisor. At 18:54Z the same process was live:
  names 9,369/23,740, 150 vendor-empty tasks, no failures; back months 0/2,374. The supervisor
  remains in the ThetaData phase with no error. Current throughput gives about twelve more
  hours, an estimate rather than a deadline. The watch records actual process identity and
  stops for inspection on completion-phase changes, errors or process loss. It does not restart
  or alter the collector; an observation timeout is not grounds to start a second job.
- 18:55Z Cost reconciliation now has direct Sail box billing for T0 through 18:46:56Z:
  $4.221360571 finalized plus $0.017232712 estimated active cost, covering all 46 returned boxes
  in the project's app. These are an alternative to the conservative Gym-box ledger estimate,
  not an additional charge on top of that estimate or the account balance-debit meter. A
  read-only request audit found $22.83363940 of House Sail model cost for requests created in
  that window, calculated from response token usage and configured rates; this is not an
  invoice. Two costs settled after the window, and the audit found no unresolved Sail request
  hold within that request set. The old laptop provider had no requests in the window, and no
  separate laptop swarm-trial provider database was found in the searched worktrees. OpenAI
  holds remain separate from gateway usage. Exact all-input Net stays unknown pending complete
  trial, billing-window and subscription reconciliation; real-options P&L remains $0. Private
  receipts are `.ltcm-main/sail-box-cost-window.json` and `cost-evidence-20260926.json`.

- 19:30Z A further completion audit found unfinished engineering requirements. W5 is adding
  bounded private execution receipts and a read-only post-close report: current paper/real order
  records lack selected-leg quote/timing/model provenance, and completed shadow detail is lost
  after export/restart. Paper and shadow observations remain separate from real calibration;
  no real fill exists to fit. W4 is implementing the post-burst Sail lifecycle, because current
  defaults do not enforce the Monday prorated period, shared maintenance reservations or a
  reduced research cohort. Root is wiring nonurgent OpenAI Flex and the existing postmortem
  output role. These changes are being built and reviewed, **not deployed or complete**.
- 19:30Z [#378](https://github.com/bwoods1998/long-term-capital-management/pull/378) merged
  as `9b4a0f8d`. The architect's fixed five-root system prompt and truncated gap list had hidden
  expanded-universe choices. The prompt now names every configured root and its uncovered
  structures. Root independently checked 100 synthetic population/universe cases; 115 affected
  tests passed locally and on the actual House's isolated committed archive. Python 3.11/3.14
  and gateway CI passed on `7026ed9a`. Production still runs the earlier `60b34dd9` release;
  merge is not deployment.
- 19:32Z W1 found and fixed a shadow restart defect: missing `seen/aggressive` state could change
  a synthetic resting fill from $1.90 to $1.80. [#379](https://github.com/bwoods1998/long-term-capital-management/pull/379)
  at `e30e01a6` preserves the classification. Old/malformed records retain their prior fallback
  and explicit unknown provenance; history is not reconstructed. Root reviewed the narrow fix;
  61 restart/live parity/live step tests pass locally and on the actual House. Full CI and
  deployment are pending. W5 incorporated the same fix into its separate recorder branch.
- 19:32Z The live completion watch still follows the same backfill process. At 19:23:51Z names
  reached 10,020/23,740, with 150 vendor-empty tasks and no failures; back months remain 0/2,374.
  The estimated remaining duration was about twelve hours. Actual Sail metadata confirms House
  capacity 1 vCPU/16 GiB/32 GiB and data capacity 8 vCPU/32 GiB/256 GiB. The billing API rates
  imply full-capacity active bounds $0.1653372/hour and $0.5547744/hour respectively; these are
  conservative capacity bounds, not measured ongoing burn or a measured nightly runtime.

- 20:30Z **Owner direction clarified and documented.** All Alpaca-supported options strategies
  and securities belong in the research target, with simple calls/puts given equal opportunity.
  The initial five and next 20 roots are collection batches, not a permanent universe boundary.
  Broader roots/expiries require suitable history, settlement rules and explicit readiness; covered
  strategies require inventory/collateral and assignment handling. Build a general agent paper
  environment, not just the existing SPY route proof. Rapid hypothesis/replay/diagnosis/revision
  loops, persistent lessons and useful evidence should drive compute. Trial count is activity,
  not profitability. The thoughts-first, minimally worded website and real per-agent progress
  remain the presentation requirements and are already deployed. Goal, README, design,
  operations and researcher/Gym contracts are updated in [#382](https://github.com/bwoods1998/long-term-capital-management/pull/382)
  (`f53003c3`), independently accepted, with full CI finishing. The contract/Gym guide affect
  prompts and bundle identity on deployment; preserve old evidence and require fresh binding.
- 20:30Z **Measured breadth and current limits.** At 20:01Z the House recorded 17,631 trials,
  25,212.33 durable program-years, 16 active families and 57 retired. Fifteen active families
  were multi-leg and one long-put; no validation passes or holdout looks. At 20:04Z the actual
  Alpaca asset lookup returned 6,305 optionable equity/ETF assets, 6,177 tradable. These are
  discovery counts, not verified historical coverage or account-contract eligibility. The Gym
  supports 11 types but actively trains only five roots; covered strategies are absent. Current
  data collection covers 0–14 DTE on 25 roots and extends 15–45 DTE on SPY/QQQ; syntax accepting
  60 DTE does not provide that data. Private discovery receipt remains in `.ltcm-main/`.
- 20:30Z Main is `e73e7740`: #379 shadow restart and [#380](https://github.com/bwoods1998/long-term-capital-management/pull/380)
  role/Flex routing are merged after independent review and green CI. #380 passed 221 affected
  tests locally and on the actual House. The deployed release remains `60b34dd9`; nothing in
  this checkpoint enables real money. At 20:00Z House health had no warnings, brokerage equity
  was $481.63/cash $481.60 with no open orders/options positions, Sail was $188.34, and September
  OpenAI gateway spending was $599.88/$707. No new brokerage deposit or October allowance.
- 20:30Z [#383](https://github.com/bwoods1998/long-term-capital-management/pull/383), exact
  `948d1153`, removes architect instructions favoring the five complex production-adapter types
  and 0–5 DTE. It exposes all configured strategy coverage, retained/retired effort and actual
  gaps, and requests the full bounded refill batch without changing admission or evidence rules.
  Independent probes verified lineage trial accounting and a population change during admission;
  95 affected tests pass locally and on the actual House. Full CI/deployment pending.
- 20:30Z [#384](https://github.com/bwoods1998/long-term-capital-management/pull/384), exact
  `29453f2d`, adds read-only catalog/backlog planning and explicit sealed-Gym coverage auditing.
  Discovery alone marks nothing ready; it does not automatically collect or grant paper/live
  eligibility. Independent review/full CI pending. [#385](https://github.com/bwoods1998/long-term-capital-management/pull/385),
  exact `80cbf01b`, adds the funded post-burst lifecycle, maintenance commitments, cohort allocation
  and receipt-bound backfill cutoff; 261 combined focused tests and the final 52 affected data
  tests passed, with independent review/full CI pending. Do not deploy either unfinished review.
- 20:30Z [#381](https://github.com/bwoods1998/long-term-capital-management/pull/381) has private
  bounded execution receipts and a read-only report. Root verified fixes for reader/writer WAL
  contention and future-session order contamination; exact `d3a5ca05` passed 228 actual-House
  tests (227 passes, one skip). Full CI exposed a process-global SIGALRM handler ownership defect
  when legacy and Gym runners execute in one process. W5 reproduced it and is fixing it with a
  regression; the PR remains unmerged. The general agent paper book and automatic post-close
  scheduler have saved designs, not implementations. Paper diagnostics remain separate from
  unseen forward evidence, real fills, live profit and calibration.
- 20:30Z The existing backfill remains PID 22487/start ticks 3310972; names were 11,255/23,740
  at 20:28Z, 150 vendor-empty tasks, no failures; back months 0/2,374. The completion supervisor
  remains in ThetaData with no error. Estimated remaining duration about thirteen hours. Active
  Gym v1 and gate-off state are unchanged. T0, Monday's session, post-close prune and Tuesday's
  first actual forward collection retain their original clocks; none is claimed complete.

- 20:34Z **Documentation update and breadth fix merged.** #382 merged at 20:32:41Z as
  `3d464985` after independent acceptance and green Python 3.11/3.14 and gateway CI. The eight
  Gym-driver tests passed locally; the actual House's isolated archive matched the contract/guide
  hashes and deterministic bundle. Its eight integration tests skipped because pyarrow is not
  installed on the House. #383 merged at 20:34:33Z as `f789e7e0` after independent review, 95
  local/House tests and all CI checks. Main now contains both; the production release remains
  unchanged. Updated this handoff and the private continuation memory to preserve the broader
  direction and current gaps. #381's handler correction is pushed as `f2b670fb`, with the new
  regression and 29 Gym tests passing; full discovery/CI verification is still running.

### Final data/image adoption (prepared Saturday; waits for completion)

The provisional calibrated pair is not the final pair. Do not select it or spend a holdout look
while the full ThetaData/SIP completion is pending.

1. Read the actual `data/completion.json` and `data/images-ready.json` from the House. Require
   completed ThetaData stages 1–6 with no failures, completed SIP relay, all universe roots,
   distinct sealed Gym/gate templates, two one-year checkpoints per template, and matching
   calibration SHA/model identity in `next-images/images.json` and `next-images/calibration.json`.
   Verify inside each sealed template and privately compare its model hash with the receipt.
   Check all 25 roots, actual covered windows, every manifest file hash/size and the stock
   underlying source paired with each options day. Verify matching Train/Validation manifests
   across the pair and the absence of holdout, credentials and network access in the Gym.
   Restore and verify each primary and backup checkpoint sequentially: a producer receipt alone
   does not prove recovery. Terminate verification forks only. The private adoption preflight and
   sealed-image checks are prepared and passed fifteen synthetic cases; they have not run on a
   final pair that does not yet exist.
2. Quiesce research with `swarm.stop` and collection with `data/nightly.stop`; verify process
   identity and released locks. A House maintenance pause alone does not stop existing research.
   Back up current metadata, `swarm.json`, any model file and forward manifest before changes.
3. Transfer the verified model privately from the sealed Gym to the House's
   `/data/calibration/fill_model.json` (0600), comparing SHA before and after. Adopt the staged
   image, calibration, universe and calendar records together; preserve the completion receipts.
   Select the final Gym checkpoint and its complete root list in `swarm.json`, keeping the gate
   pointer disabled. Verify all three gate pointers: swarm settings, optional `gym-forward.json`
   and `images.json`'s current gate checkpoint, which the nightly collector prefers. Sunday should
   have no genuine forward day; never discard an unexpected real forward receipt. Check for old
   image promotions or shadow inventory before switching; pointer changes do not revoke bands.
   Use fsynced temporary replacements and write the adoption receipt last. A partial failure
   leaves research and collection stopped until reconciled.
4. Restart the House so the shadow book loads the new model, then resume supervised research and
   collection. Verify the deployed release, effective `GYM_FILL_MODEL` path, model file hash,
   constructor wiring and process start after installation; current health does not report the
   in-memory model identity, so do not claim it does. Verify pool checkpoint identities and fresh
   heartbeats. Prior-image workers must not execute new jobs. Require fresh validation on the
   selected Gym and current engine bundle before enabling the matching final gate checkpoint.
   Preserve all previous trial counts, lineage links, look results and look reservations.
5. Confirm the active data records point to the final gate template for Tuesday's forward copy;
   verify next wake September 29 06:00Z. Record exact identities and evidence in this run before
   declaring final data readiness. No real execution or grant setting changes in this procedure.

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

## The sprint (docs/goals/LTCM_SWARM_SPRINT.md, from 21:24Z Sept 26)

The owner started the sprint with `/goal` on Saturday afternoon Pacific. It amends the plan, keeps T0
and this record, and lifts the Saturday continuation's no-real-money scope.

**Owner's decisions** (as given):
- D1 real money on for Monday: yes.
- D2 evidence reform as written: yes.
- D3 real-fill calibration round trips at $50 a day: yes.
- D4 money table at the bold end: yes.
- D5 deposit: none now; deposits across all accounts later this week, so size by what is there.
- D6 Sail: no top-up now; pace the burst so the Sail balance stays above the guard through Tuesday.
- D7 Claude API: $100 funded, key in the gateway as `CLAUDE_API_KEY` (listed in the Worker's secrets
  at 21:10Z).

### Sprint log

- **20:51Z Review.** Three read-only reviews: Gym realism, swarm dynamics, Monday's live path. Main
  findings, counts only:
  - 76 families, 18,226 trials, 0 over the validation line;
  - 16 alive at the floor of 16; 7 of 8 Gym boxes idle.
  - The seven causes are in the sprint file.
- **21:24Z** Sprint goal merged as #386 (`28395fd7`).
- **21:24Z Wave 0 settings** in `/workspace/state/swarm.json` on the House. Backup is
  `swarm.json.before-sprint-20260926T212416Z`; mode 600 kept. Changes:
  - `population.floor` 16 to 44 (start 48, ceiling 96);
  - `architect.refill_seconds` 1200, `every_seconds` 7200, `max_refill` 12;
  - `tournament.retire_revisions` 200, `retire_evaluations` 4000;
  - `gym.validation_split` 1: no forced segment closes on Validation;
  - `researcher.sail_usd_per_hour` 2.25 to 1.5 (D6 pacing);
  - **Gym image v1 to `core-calibrated-v1`**: `sbcp_fb07667a-…`, Train 2022-2024 plus the provisional
    fitted fill model, sealed, holdout-free;
  - **the gate on**: `gate_checkpoint` `sbcp_87f6a5ae-…`, the paired gate image with the 2026 holdout.

  The Saturday plan's "final pair only" adoption is superseded by the sprint: image adoption costs
  one re-validation and no holdout looks, and the 25-root pair follows when the names land.
  - At 21:25:51Z, verified: process PASS, heartbeat 15 s, pace 1.5 read. The pool ended the v1 boxes
    and forked on the new image. Gate WAIT, since nothing is over the line.
- **21:25Z Wave 0.3** mid-fill diagnostic started on its own sealed fork
  (`sb_2ff60e71`, `ltcm-diag-mid-*`) with the deployed engine: 72 validated families × stress 1.0 /
  0.5 / 0.0 on Validation. Results are private (`~/Work/.ltcm-main/middiag/`) and never shown to
  researchers; the runs count as diagnostic trials.
- **21:25Z Wave 0.5 data order.** `backfill.py run` supports `--order`, but no reorder. The back
  months only become usable with B2's horizon admission in R2, by which time both stages will have
  finished (names about 09:30Z Sunday). Restarting the supervised collector would risk a duplicate
  session for no gain.
- **21:22Z Wave 1** builders started, each in its own worktree:
  - B1 search: `sprint/b1-search`, ~/Work/ltcm-sprint-b1;
  - B2 Gym: `sprint/b2-gym`;
  - B3 Claude: `sprint/b3-claude`;
  - B4 live: `sprint/b4-live`.

  An independent review of #381 is also running.

- **21:52Z Wave 0.3 verdict: EXECUTION-BOUND.** 72 validated families' validated versions were
  re-run on Validation at three fill levels. The diagnostic box was terminated at 21:52Z. These runs
  count as diagnostic trials: 72 programs × 3 stress levels, plus the 1.5x twin at natural.

  | Fill level | Positive | t ≥ 2 | Meet D2's frequency, t and quarters |
  |---|---|---|---|
  | natural | 17 | 3 | - |
  | half the half-spread (stress 0.5) | 26 | 3 | 1 |
  | mid (stress 0) | 50 | 20 | 14 |

  - 34 families flip from negative to positive between natural and mid.
  - 18 of the 20 with t ≥ 2 at mid were already retired.
  - The edge the search found is real but thin, and it lives mostly in the last half of the
    half-spread. How close to mid the swarm really fills decides everything.

  Actions taken:
  - B2 re-prioritised: the fill model becomes an honest point estimate. It had a Wilson lower bound,
    exposure diluted by never-traded strikes, and a min(single, half complex) multi-leg rule. The
    adverse-selection rule and the 1.5x stress are kept; mid and touch limits become fillable.
  - B4 checks that live and Gym limit rules match.
  - D3's real-fill samples on Monday become the key measurement.
  - Per-family numbers stay private (`~/Work/.ltcm-main/middiag/`) and never reach researchers.
- **21:40Z PR #381 held until after Monday.** Its independent review returned merge-after-fixes:
  - unbounded full-day chain arrays (an out-of-memory risk on the size-s House);
  - a recorder whose one failure stops every source for the day, with no rotation;
  - about six fsyncs per real order on the minute thread.

  Findings are posted on the PR. D3 records its own bounded samples in B4's code instead.
- **21:45Z B3 PR #388 opened:** the Claude gateway route, Claude-first architect and audit, and the
  diagnostician.

- **22:00-22:25Z Reviews.**
  - **#388 (B3, Claude):** merge after fixes. Two billing-safety fixes:
    - a truncated upstream answer settled at $0;
    - holds never swept.
    
    Also: a diagnostician retry loop on billed failures, a retire race, phantom holds, empty answers
    counted as success, and masking. Sent to B3.
  - **#389 (B1, search and D2):** merge after fixes. The high finding: a version demoted by its 1.5x
    Train robustness run kept `gate_ready` and its tuition eligibility. Also:
    - submitted versions skipped robustness;
    - a migration restart-loop risk;
    - batch-dependent per-year eligibility;
    - top-10 profile cost against the $1.5/h pace, so `top_profile` will be set null in `swarm.json`;
    - a retire-reason D2a leak;
    - a retire race;
    - unbounded robustness queueing.
    
    Sent to B1. R1 waits for these fixes.
- **22:16Z Site.** personal-site #13 merged (`e4a96f6`) and deployed (version `5ce5265c`). Agent progress
  checklists accept the D2 line (50 trades on 25 days) beside 100 on 60, so the site stays valid across
  R1. Page 200; the checkpoint loads.
- **22:07Z Population.** 26 alive, up from 16 at the sprint's start. The deployed architect still asks
  for "3 to N"; main's #383 asks for the whole gap and ships in R1.

- **22:34Z #388 merged** (`13963028`): Claude through the gateway, Claude-first architect and audit, and
  the diagnostician.
  - The review's nine findings and the verification's three follow-ups are fixed.
  - Gateway: 267 tests. Python: 417 tests. CI green.
- **22:37Z Gateway deployed** from main `13963028`, version `42e443bb`. The only change since the 16:49Z
  deploy is the Claude route and its funded meter (`CLAUDE_USD` 100).
- **22:39Z Claude probe**, run from the House:
  - `GET /v1/claude/models` lists `claude-opus-5-5`, priced;
  - one `claude-opus-5-5` call returned 200 with `end_turn` and structured JSON `{"ok":true}`,
    cost $0.001, settled;
  - `/v1/claude/request/probe-1` reads settled;
  - health shows $99.999 remaining, geo `global` (no premium), 0 holds.

  The House uses Claude from R1 on.
- **22:33Z #389 fix verification:** 6 of 8 fixed, plus two new stuck-candidate paths:
  - a non-ok 1.5x run never retried;
  - robustness attempts charged at queue time.
  
  With robustness-job aging for liveness, these go back to B1.

- **22:59-23:11Z R1 deployed.** Main `5ba25909` (#388 Claude + #389 search and D2).
  - House checkpoint `sbcp_05f4d395` (pre-r1-sprint) taken first. The money digest is unchanged
    (`8dba0b1f`).
  - Release `20260926T225946Z-22b18ea9f452` was staged, canaried and PROMOTED at 23:00:24Z, and passed
    its 10-minute watch.
  - Swarm restarted (pid 11170) on the release. The migration re-picked 34 families' bests, 20 with an
    eligible best, 0 errors.
  - The Claude diagnostician is live: 15 eligible; the first rewrite and a retire note, $0.34 by 23:12Z.
- **23:08Z Settings** (backup `swarm.json.before-r1-*`):
  - `researcher.top_profile` null (cost);
  - `architect.agenda` (the operator's research agenda, 3.2 KB);
  - `claude.usd_cap` 70 (the pre-Monday budget).
- **23:15Z** `gym.start_boxes` 6: the queue was 41 on 4 boxes during the re-validation and robustness
  wave.
- **23:14Z Claude architect timeout.** The architect's first Claude call hit Anthropic's edge 524,
  because a non-streaming, high-effort answer ran past 100 s; it fell back to Astra/Sail. B3 is
  building streaming (gateway SSE pass-through plus the House client), to ship with R2.
- **Reviews in flight:**
  - #387 (B2's honest fill model) needs one more fix: an exposure floor for unsampled moneyness. The
    operator also added a guard: stress runs halve passive hazards. Then it merges main.
  - #390 (B4's live path): all three lenses verified. Money and venue lenses: safe to deploy. Evidence
    lens: fixed after a double count (calibration losses as compute) was removed. Final follow-ups
    (quote overwrite, calibration re-quote, time-bounded observe reads) are on `a06854d9` or later.

- **23:18Z-00:28Z Merges for R2.**
  - #390 (B4 live path, `ef867ef0`; three-lens adversarial review, fixes verified).
  - #387 (B2 honest fill model, `da474ede`; review and verification fixes, plus two operator guards:
    a moneyness exposure floor, and stress runs halve passive hazards).
  - #391 (B3 Claude streaming, `76151c6b`; review fixes).
  - #392 (`real_money` true, `440f6de4`; D1).
  
  #392's CI exposed a pre-existing wall-clock test that failed between 00:00Z and 07:00Z. It is fixed
  in the same PR, so the gate's forward test now uses its fake clock.
- **Gateway deploys.**
  - 23:18Z: version `9634002d`, with B4's `OPTION_STRUCTURES_REAL` = the four debit types and
    `MAX_ORDER_EQUITY_SHARE` 0.25.
  - 23:41Z: version `953a9b46`, Claude streaming. A re-probe settled at $0.001.
- **23:25Z** `researcher.sail_usd_per_hour` 1.5 to 2.0. The pace had paused researchers (1 of 46
  running). The D6 arithmetic allows about $3.4/h in total to Monday's open and keeps the balance above
  the $32 guard through Tuesday.
- **23:28Z** The population reached 48, the start target (16 at 21:24Z).
- **00:29-00:30Z R2 deployed.**
  - House checkpoint `sbcp_9659a2a2` (pre-r2-sprint) first.
  - Release `20260927T002925Z-2bfef7a749bf` (main `440f6de4`, `real_money` true, money digest
    `ad9bd54c`, full digest `4f4edaf5`) promoted at 00:30:02Z.
  - **00:30:15Z Grant enabled:** `options-swarm-20260928` is active and persistent, pinned to
    `ad9bd54c`, capital $481.63, stake (Probe floor) $100, max_agents 4.
  - Real entries still need a holdout-passed family (Probe), Monday's multi-leg and single-leg paper
    proofs, clear stops and the kill switch off.
  - **00:31Z Switches:** `live.observe` true, `live.observe_max` 8, `live.calibration` true (D3).
  - This is the last release before Monday. From here to Monday's close, only `swarm.json` switches
    and data or image adoption, except a rollback.

- **00:40Z R2 passed its watch** (20 readings; stage prune). The House runs `real_money` true. After it:
  - 48 families running, 972 cycles/h, 0 cycle errors;
  - Gym queue 44 on 6 boxes (the one-time re-validation after the Gym code changed, plus robustness
    runs), so `gym.start_boxes` went to 8 for the wave.
- **00:41-00:48Z Honest refit** on the House: `scripts/data/calibration.py --version core-honest-v1`,
  with B2's estimator.
  - Fitted on the sealed Gym template from Train `trade_quote` only (755 days): model
    `fm-c4a0c70c9afbf09f`, 2,114 cells, 180 size cells, sha `3de9e2a6…`.
  - Checkpoints: Gym `sbcp_4500cd6f` (backup `sbcp_bf69c55f`), gate `sbcp_0a6f54da` (backup
    `sbcp_7ebe850f`).
  - Both passed the seal check from inside: Gym Train and Validation only, 2022-01-03 to 2025-12-31;
    gate including the holdout.
  - Operational note: the data CLI finds the Sail key only through the process environment, so it
    was passed that way from `/workspace/.env` without printing it.
- **01:00Z Adopted `core-honest-v1`** in `swarm.json` (image and gate).
  - **01:01Z** Model copied privately from the sealed Gym template to the House's
    `/data/calibration/fill_model.json` (mode 600). SHA verified on both ends; nothing stored on the
    laptop.
  - **01:01-01:02Z House stop and start** (a restart, not a release). `health.json`
    `options_live.fill_model` now reads `fm-c4a0c70c9afbf09f`, 2,114 cells. The Gym, the gate and the
    live shadow share one fill model.
- **01:03Z Revived 13 retired families** as lineage continuations (`<id>-r`, parent = the retired
  family). Each has v1 = its validated program, authored operator-revive, and inherits its lineage's
  trials (41-818) and look ration (0 looks used).
  - The selection is the operator's, made on the Wave 0 execution diagnostic (validation-window runs
    at mid). Validation-based selection is exactly what the sealed holdout, Holm across every look
    and the forward record exist to check.
  - The revived: butterfly-pin, close-imbalance-iwm-credit, eod-drift-spxw, event-crush-xsp-fly,
    factor-residual-iwm-debit, gap-revert-iwm-on-spy, open-drive-iwm-fly, orb-break-qqq, orb-fade,
    orb-fade-iwm, pin-qqq-fly, skew-revert-qqq-on-spy, vrp-condor-xsp.
  - 8 are debit types, eligible for real money at this equity.
  - Population 61.

- **01:13-01:21Z Researcher retirements above the start** (population 61 to 56). Five retired, the
  guard allowing it above 48. Four were weak.
  - The fifth, `weekend-decay-fly`, had submitted a strong candidate (v48: all Train years positive,
    9-11 of 12 quarters, about 143 trades on 75 days, positive at 1.5x). It then retired because it
    could not rebuild v48's exact code to re-check it. Researchers have no tool to read an older
    version's code, so they rebuild from memory; 8 notebook entries since R2 show the confusion.
    The tournament's own robustness runs use the stored code and are unaffected.
  - Mitigation, with no deploy (R2 was the last release):
    - `weekend-decay-fly-r` revived from v48 (`revive.py --prefer best`), 01:23Z;
    - `population.start` 48 to 60, so researchers cannot retire below 60 and the architect refills
      toward 60.
  - The missing read-version tool is recorded for after Monday.
- **01:24Z** The first Claude architect pass after streaming: `claude-opus-5-5`, $0.15, 3 families
  following the operator's agenda (a multi-day VRP debit butterfly, a daily-trend debit vertical, a
  macro-release drift debit).
- **01:55Z** `gym.start_boxes` back to 6: the re-validation wave has cleared (queue 12) and Sail pacing
  needs it (see below).

- **04:05-05:36Z Operator sweep, generation 1**, in response to the owner's push for agent-time search.
  - A workflow of 27 agents wrote 10 parametric templates (debit-first):
    - VRP debit butterfly;
    - weekend theta butterfly;
    - event IV-crush butterfly;
    - intraday momentum vertical;
    - gap fade vertical;
    - multi-day trend vertical;
    - dip-rebound call;
    - range breakout option;
    - cheap-vol strangle;
    - a patient short-dated condor (credit).
    
    Each was audited adversarially and fixed; all pass the Gym safety check. Programs and parameters
    stay private.
  - Swept 790 variants on Train 2022-2024 (SPY/QQQ/IWM pooled) on 4 dedicated sealed forks of
    `core-honest-v1` with the deployed engine. Each variant was scored with the swarm's own
    `train_score`, and the top 5 per template were re-run at 1.5x stress, which halves passive fills.
  - **Result: no Train edge.**
    - Per template, 0-4 variants were net positive on Train.
    - The best robust scores were negative for every template.
    - 0 of the 35 stress-tested finalists were positive at 1.5x.
    - The short-dated short-premium condor was about break-even (best score -0.36).
    - Two templates (dip rebound, intraday momentum) failed on dropped exec streams, and one had
      memory errors on large batches. The runner now saves before stress, retries, and chunks grids
      of 24.
  - Reading: under honest fills, 0-7 DTE index-ETF options (bought or sold, directional or
    volatility) do not clear costs in 2022-2024; buying premium loses systematically (the variance
    risk premium). Nothing was founded from generation 1.
  - Next:
    - generation 2 (novel signals: 3 idea lenses and a judge, 8 templates) and generation 3
      (15-45 DTE SPY/QQQ back months, the classic VRP horizon), being written by workflows;
    - generation 3 sweeps on the final image once stage 6 lands (about 09:30-10:00Z).
- **04:55Z** Diagnostician widened (Claude was idle): family_hours 3, near_miss_checks 5,
  min_validations 1, per_round 3, `usd_day` 30.

- **06:25-07:45Z Credit-at-$2,000 prepared: PR #393** (not merged, not deployed; the owner decides).
  - Credit types (`credit_vertical`, `iron_condor`, `iron_butterfly`) become real types when SIZING
    equity (the lower of account equity and grant capital) is >= $2,000. The gateway independently
    refuses credit opens under $2,000.
  - Adversarial 3-lens review with independent verification: two MAJOR findings confirmed.
    - Assignment risk: an in-the-money short leg gave more contracts through max-loss sizing.
    - Expiry day: a short leg just outside 1% could be assigned after the cutoff.
  - Both fixed at `d3627c10`:
    - refuse real credit with an in-the-money short leg on equity roots;
    - cap the short-leg stock notional at <= 3x sizing equity, and 1 structure per order at Probe,
      mirrored in the gateway;
    - refuse real short calls beyond 5 DTE on equity roots;
    - close every expiring equity-root credit structure on expiry day whatever its moneyness.
  - Fix verification: SAFE TO DEPLOY if the owner approves. Money digest `ec0a1bc4` moves again with
    the fixes; the new digest is in the PR.
  - Implication: the notional cap means SPY/QQQ/IWM credit structures cannot trade real money below
    about $20k of equity. Real credit runs through cash-settled XSP/SPXW, which cannot be assigned
    early.
  - Deploying needs the owner's approval of a third release before Monday, then --ratify, and a
    deposit to >= $2,000 followed by --ratify again.
- **07:40Z Architect agenda v2** in `swarm.json`: the evidence (premium buying loses; short-dated
  selling about break-even) and the documented directions:
  - liquidity-provision reversal;
  - fear-premium ITM call verticals (a debit form of the short put spread);
  - session-only long gamma;
  - dealer-gamma regimes;
  - back-month VRP ladders.
- **07:39Z Operator sweep, generation 2:** 7 new-signal templates (from 3 idea lenses and a judge,
  audited and fixed) sweeping on 4 sealed boxes. The single-name earnings template waits for the
  final image.

- **08:05-08:30Z Sweep generation 2 results.**
  - `liquidity_rebound_itm_vertical` has Train edge. Founded as two families; their robustness runs
    at mid had per-year t of 2.94 / 1.11 / 1.44 (rank 0).
  - Local search around it: 70 of 72 neighbors positive on Train (a plateau, not a peak); best
    robust score 0.67; 5 of 6 finalists positive at 1.5x.
  - `fear_premium_itm_call_vertical`: edge only in 2023-2024. Finalist 0 stayed positive at 1.5x and
    was founded.
  - No edge: `close_pressure_ibs`, `day_session_long_gamma`, `intraday_skew`.
  - `spy_spx_retail_tilt` failed its own mechanism checks.
  - `dealer_gamma` overruns the Gym's per-program memory on full SPXW chains even at 2 workers:
    shelved.
- **08:29Z Validation 2025 on the founded families: 0 passes.**

  | Family | Mean per $ of max loss | Daily t | Failed checks |
  |---|---|---|---|
  | rebound rank 0 | +0.039 | 0.29 | t, deflated Sharpe, trades < 50 |
  | rebound rank 1 | +0.051 | 0.37 | t, deflated Sharpe, stress |
  | fear premium | +0.003 | 0.06 | t, deflated Sharpe |

  Positive, but far from the one-year t >= 2 line. Reading: the rebound fires a few times a year per
  root, and t grows only with the square root of independent bets. The honest route to the line is
  breadth, not a looser line.
- **08:25-08:42Z Sweep generation 4 (XSP, cash-settled credit): no edge.**
  - Put credit verticals at 1-7 DTE: 1 of 77 positive.
  - Condors: 0 of 74.
  - A weekly put ladder at 7-14 DTE: 0 of 78.
  - Finalists at 1.5x stress: 0 of 15 positive.
  - Selling short-dated XSP premium loses after honest costs in 2022-2024; XSP's spreads eat the
    premium. This is evidence against the XSP-credit route that PR #393 opens.
- **08:35Z Interim 25-root image pair building (no release).**
  - The data box already holds the twenty names' full NBBO and underlying history; only stage 6
    (back months) is still downloading.
  - An operator job on the House builds a Gym and gate pair from stages 1-5 in a separate staging
    directory. The completion supervisor's records are untouched.
  - It installs the deployed honest fill model. Names were never sampled, so they fill at the
    natural only.
  - Purpose: a names version of the rebound (breadth) and the names templates, about 7 hours before
    the final pair.
- **08:30-08:50Z Two template workflows.**
  - Generation 5, debit-form VRP (real-money eligible):
    - an always-on put-write held as an ITM call vertical;
    - a calendar-window version (turn of month, pre-holiday, pre-FOMC).
  - `liquidity_rebound_names`: the rebound on the twenty names.

- **08:57Z Interim 25-root pair adopted (a `swarm.json` switch, no release).**
  - Gym `sbcp_b358ab73`, gate `sbcp_92c29288`; the deployed fill model (sha `3de9e2a6`).
  - Verified before adoption: the founded rebound program on the new Gym image reproduced its
    core-image result exactly (168 trades, t 2.1864, the same P&L to the cent).
  - `gym.roots` now admits the core five plus the twenty names; the pool re-forked with every root
    present.
  - Every earlier validation is now stale; none had passed.
- **09:00Z 27 dormant families retired** (operator housekeeping, lessons written to the graveyard).
  - Each had declared its own mechanism falsified in its last three cycles and was re-running empty
    placeholder jobs on the Gym.
  - Kept the three with a positive Train score. Population 60 -> 33; the architect refilled 12 at
    09:03Z under agenda v3.
- **09:20Z The rebound on single names: refuted at honest costs.**
  - Four lineages of up to five names each: mega-cap tech, semis (SMCI dropped: option quotes on
    only 603 of 753 Train days), high beta, macro ETFs.
  - 13 of 228 variants positive; no robust Train score above zero; 3 of 20 finalists positive at
    1.5x (all with a losing year).
  - Names fill at the natural only in the Gym (their fills were never sampled). A full spread per
    leg costs more than the rebound earns.
  - An independent audit also flagged hindsight in the name lists: they are the period's biggest
    winners, chosen today. Any names finalist would have needed a same-names placebo control.
  - Agenda v3 was corrected at 09:25Z: names refuted. The architect's next refill targets the index
    reversal with more trading days, combined with a debit put-write in one family.
- **Arithmetic of the validation line.**
  - The index rebound's 2025 edge is about +0.04 per dollar of maximum loss a trading day, with a
    spread several times that.
  - One-year daily t >= 2 at that edge would take more trading days than a year has.
  - A family passes honestly only with a much higher per-trade Sharpe, or by combining uncorrelated
    positive harvests so more days carry return.

- **09:25-11:45Z Generation 5: debit-form premium harvests (all real-money eligible).**
  - Calendar windows (turn of month, pre-holiday, pre-FOMC): 1 of 72 positive; 0 of 5 finalists
    positive at 1.5x stress.
  - Always-on put-write held as a call vertical below spot, 3-10 DTE:
    - 12 ungated variants ran, all negative (2022 t -1.5 to -4.9);
    - the gated variants hit the Gym's 6 GB per-worker cap.
  - The Gym memory lesson: the store is memory-mapped by the NEEDS window, and a full-session
    window (from 10:00) with 0-14 DTE exceeds the cap. Reading from 13:30 (`start 810`, as the
    rebound does) fits. Founded families face the same cap in the pool.
  - Rebound plus gated put-write in one program (55 rows):
    - the rebound-only control reproduced exactly (164 trades, pooled t 1.97);
    - the best combined row raised pooled t to 2.21 on 336 trades;
    - every combined finalist lost at 1.5x stress (row 8: +$2,303 at 1x, -$1,550 at 1.5x).
  - The put-write layer's edge is thinner than one extra half-spread, so it was not founded. The
    index rebound alone remains the only stress-robust program.
- **11:28Z Tournament:** `event-crush-xsp-fly-r` (a long butterfly on XSP around events) scored t 1.03
  on 2025.
  - 58 trades on 51 days, +$1,177, +$978 at 1.5x, 3 of 4 quarters.
  - It fails t and the deflated Sharpe: 6/8, the closest real-money-type family so far.

- **11:47-12:05Z Back-month pair built; NOT adopted.**
  - Stage 6 (SPY/QQQ back months, out to about 45 DTE) completed at about 11:45Z. An interim pair
    was built from stages 1-6: Gym `sbcp_a38bb07a`, gate `sbcp_a5e975a5`.
  - To take the data-box lease, the completion supervisor was paused for 18 minutes; it resumed
    its SIP relay at 12:04Z.
  - The exact-reproduction check FAILED on it. The index rebound hit "Memory mapping file failed".
  - A fork has 15.7 GB free. But with complete back months, the SPY and QQQ NBBO trees are about
    3 GB each. The Gym maps the store per root across the window, so three roots pass the 6 GB
    per-worker address-space cap (`GYM_WORKER_MEMORY_GB`) before a program runs.
  - Adopting it would break every multi-root family.
  - The completion supervisor's final pair will have the same property. It must not be adopted
    without this reproduction check and an engine change (a larger worker cap in the pool, or back
    months stored apart). That is post-Monday work, because a release is needed.
  - Side effect: the adopted names pair (`sbcp_b358ab73` / `sbcp_92c29288`) was cut at 08:37Z,
    mid-download, so it holds back months for some days only.
    - Four alive families read past 14 DTE and were given an operator note: `event-term-crush-calendar`,
      `poor-mans-covered-call-diagonal`, `slow-tenor-rebound-debit`, `quiet-tenor-putwrite-debit`.
    - The agenda now says to keep NEEDS within 14 DTE.
    - The subset was not selected by outcome, so it thins that evidence rather than flattering it.
  - Early back-month rows (2-root templates fit): long put butterflies and trend long options at
    8-45 DTE lose in every Train year, since the Gym charges back-month legs the full spread both
    ways. The six gen-3 back-month templates are sweeping for the owner's credit question.

- **13:25-14:00Z The trend lead, the push, and two site defects.**
  - Complete back-month pair adopted (13:25Z). `poolcheck.py` ran the rebound the pool's way (Train
    split 8, Validation whole) on both images with identical numbers. The earlier memory failure
    came only from the operator sweep's split-1 runs.
  - Founded `sweep-bm-trend-long-option` (13:27Z).
    - Local search: 40 of 42 neighbours positive on Train, 24 positive in every year; 15 of 15
      finalists positive at 1.5x stress.
    - The best neighbour (target 42 DTE) was queued at 13:58Z as the family's next version, in the
      same lineage (42 trials counted). It scores 0.568 on the robust Train score, t 1.96,
      +$16,858; at 1.5x, +$15,054 with t 1.79.
  - An affordable short-dated version (3-14 DTE, $120 cap) had too few trades: 2022 had 7-21.
  - The owner topped up compute (Sail, OpenAI, Claude) and said not to throttle. Push:
    - Gym pool 12 boxes, `max_boxes` 12;
    - researchers $3/h, `top_profile` pro_asap for the top 10;
    - population 72, architect hourly;
    - diagnostician 5 a round, $45/day;
    - `claude.usd_cap` 98.
  - The owner deposited $1,000. Equity reads $1,481.63; options buying power is still $481.60. The
    grant is re-ratified at the new capital once buying power reflects it. PR #393 is not merged
    (the owner agreed; evidence posted on the PR).
  - Site defect 1: the live thought feed stopped at Sept 26 23:00:56Z.
    - Cause: R1 added two private swarm event kinds (`swarm.diagnostician`, `swarm.robustness`)
      that the House ledger does not know. Each 200-row mirror batch rolled back, the error was
      swallowed, and the cursor stuck at seq 22,468.
    - Interim: an operator mirror on the House (`operator_mirror.py`, the House's own mirror with
      those two kinds filtered), started at the present to avoid re-stamping a 14-hour backlog.
      Notes reach the site again from 13:46:51Z.
    - Code fix: a PR to merge after Monday's close.
  - Site defect 2: the House box's daily backup had failed eight times since Sept 26 10:22Z. It
    looks for a box named `ltcm-floor`; the new House box is `ltcm-house`. A manual 30-day
    checkpoint was taken at 13:53Z; the code fix is in the same PR.
  - Balance chart: at the owner's request, it starts after the deposit (13:36:06Z, $1,481.63).
    personal-site #14, deployed 13:50Z; profit already nets funding.

- **14:00-14:40Z The rebound as a back-month single call: the strongest result of the sprint.**
  - The index rebound signal, held as ONE 28-45 DTE call on SPY/QQQ (delta 0.5-0.6, 3 sessions,
    take profit and stop, out at 21 DTE).
    - 50 of 52 Train variants positive; 42 positive in every year.
    - The best: daily t 2.73 / 2.54 / 2.05 by year (4.14 pooled), 182 trades, +$24,072; at 1.5x,
      +$23,255 (t 4.20).
    - Placebos lose: every-session call -$9,648 (t -1.94); trend-inverted -$7,589 (t -0.68). The
      edge is the signal, not market drift.
    - The edge holds at delta 0.4 (t 2.27) and 0.45 (t 2.74).
  - Founded `sweep-rebound-bm-long-call-p2` (14:35Z; 62 sweep trials counted, both halves). Next:
    the pool's robustness run, Validation 2025, then the gate.
  - Real money is blocked by size, not evidence. One contract costs about $500-1,500. Options buying
    power is $481.60 until the deposit settles, and the D4 Probe cap is 5% (floor $100). A pass
    before Monday trades in shadow unless the owner approves a one-contract Probe after the deposit
    settles. Cheaper deltas (0.2-0.4) are being swept.
  - Refuted the same hour:
    - back-month put-write as call verticals: 0 of 59 positive, t about -7;
    - low-delta trend options under a $200 cap: too few trades, 2022 empty.
- **14:05-14:25Z The laptop shell was blocked** (every command failed). The session scratchpad sits
  on a 3.8 GB /tmp tmpfs, and template agents had left 3.1 GB of synthetic stores and venvs in it.
  Cleared. Remote work (the House, the pool, the running sweeps) was unaffected.

- **15:27-15:33Z The first validation pass, and the first holdout look: failed.**
  - `low-close-location-backmonth-call` v7 (architect-born 14:49Z) passed Validation 2025: 207
    trades on 51 days, t 2.47, deflated Sharpe 0.997, 3/4 quarters, +$17,998, +$14,867 at 1.5x.
  - The gate: review pass (GPT-6 Sol, 15:30:19Z), Claude audit pass (Opus 5.5, 15:30:31Z).
  - The sealed holdout look (15:32:40Z) FAILED: 184 days of 2026, -$9,372, daily Sharpe -0.07,
    bootstrap LB95 negative, p 0.836.
  - The family stays in the Gym; the look is spent (one of the lineage's three). No real money was
    at risk; this is the verifier working as designed.
  - Reading: calls bought on late-day weakness rode 2022-2025's recoveries; 2026's first nine months
    did not reward them.
  - The same hour the operator's rebound back-month call (the strongest Train result) scored 2025
    t 0.06 on 47 trades.
  - Train strength in this family of ideas has not transferred to unseen data. The swarm continues.

- **16:26-16:31Z Generation 7 (direction-neutral back-month single options): both refuted by their own mechanism checks.**
  - The two-sided rebound (a call after oversold selling in an up-trend, a put after an overbought
    rally in a down-trend): in 2024, calls made +$5,615 while puts lost -$3,134. In trend mode,
    67% of trades were calls.
  - Each side is the year's market drift, not the reversal mechanism.
  - Cheap-vol back-month straddle: its signal (implied vol under rising realized vol) was on for
    only about 26 root-sessions a year, under the 40-trade floor. Implied vol rarely sits under
    realized: that gap is the variance premium itself.
- **First-principles reading at 16:30Z** (about 45,000 trials; honest fills):
  - short-dated options: every mechanism loses to the spread;
  - premium selling: loses after costs at every horizon tested;
  - back-month single options: survive costs, but their profit is market drift. The sealed holdout
    rejected the one that passed 2025, and the direction-neutrality check confirms it
    independently.
  - What could change the picture is the cost model. The short-dated index rebound is strongly
    positive at the mid and marginal at honest costs. Monday's D3 calibration round trips measure
    real fills on exactly that structure (1-lot, $1-wide, near-money SPY/QQQ call verticals, at
    the mid then mid+1).

- **16:35-16:52Z Execution is the index rebound's lever.** Train, split 8 as in the pool.
  - Patient execution (never chase to the natural, 25-minute entries, exits at the mid) raises the
    robust score from 0.67 to about 1.0 (pooled t 2.6-2.9), but cuts trades to about 36 a year.
  - Adding the two-sided pullback rule (up-trend pullbacks in calls, down-trend rallies in puts,
    z 0.5, 20-day trend) keeps 61-68 trades a year: t 2.69, 183 trades, per-year t 2.37 / 1.58 /
    0.76. At 1.5x it falls to about zero (+$95, t 0.02).
  - The edge is execution-bound: it lives in patient fills.
  - Queued at 16:52Z as the next version of `sweep-liquidity-rebound-itm-vertical` (same lineage,
    about 90 trials counted). Validation 2025 judges it.
  - Monday's D3 calibration round trips measure exactly whether real patient fills behave like the
    Gym's.
- **16:29-16:33Z** A tournament fork of `low-close-location-backmonth-call` onto IWM (no back months,
  so the same SPY/QQQ program) passed Validation with the parent's identical t 2.47. Its holdout look
  failed too. That lineage has spent two of its three looks.

- **About 23:45Z Owner decision D8: the two-release limit is lifted.** The owner asked to build everything
  possible before Monday's open and to ignore "at most two releases before Monday". Releases before
  Monday's open are allowed. The deploy freeze Monday 13:25-20:05Z (except a rollback) stands. Plan:
  - the harness audit's `swarm.json` switches now;
  - research-side code (a researcher sweep tool, a park action for dead families, richer run
    diagnostics), each adversarially reviewed, in one release R3 before 13:25Z Monday. The money path
    (`league/live`, the gateway, the grant and the money table) is untouched.

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

### T0 + 12 h (18:23Z Sept 26)

Observed 18:22–18:24Z; counters advance during the read. Funding is not revenue.

| # | Metric | T0 + 12 h |
|---|---|---|
| 1 | Net since reset | real-options P&L $0.00; Net is negative. Swarm ledger: Sail models $22.6394 plus estimated Gym boxes $7.4445; OpenAI $0.3199 settled plus an unresolved $2 hold. Gateway actual OpenAI spending since T0 is $2.06 across roles. House/data/build costs and subscription accrual must still be reconciled before stating an exact all-input Net. |
| 2 | Data | core 3,760/3,760, holdout 920/920, 2022 1,255/1,255 and calibration 755/755 complete; names 8,626/23,740 with 150 vendor-empty tasks, back months 0/2,374, no failing stage. Completion worker is running ThetaData; final full-universe images and model are not yet ready/adopted. |
| 3 | Gym throughput | 22,684.43 durable program-years and 16,358 trials; about 3,188 durable program-years/hour since 14:15Z. Median model cycle 47s, p90 87.9s, 99.7% under 180s. Earlier +8h throughput used the pool's 30,973 execution-year counter; that is not the durable-run total (9,465.52 at 14:15Z), so do not subtract those different counters. |
| 4 | Search | database: 17 alive, 53 retired; heartbeat just before the next birth: 16 alive, 8 running; 1,758 cycles in the last hour. Population is refilling below its target of 48. The latest architect proposed/admitted one family for the gap that existed before the retirement wave. Retirement-floor refusals back off; they are not model/provider crashes. |
| 5 | Evidence | 0 validation passes, 0 holdout looks/passes; no leakage alarm. No profitability has been demonstrated. The new site renders current prerequisite counts without private scores or invented readiness. |
| 6 | Forward | no Candidate and no forward session yet. Nightly heartbeat fresh on the current release, next wake Tuesday September 29 06:00Z. Saturday preparation does not count as that run. |
| 7 | Execution | no new real-option orders or positions; account equity $481.63/cash $481.60, plus legacy crypto dust. Real money off, no grant. Gateway's two earlier legacy orders are unchanged. Independent SPY paper proof is prepared for Monday, not yet observed in-session. |
| 8 | Compute | Sail about $189.86–189.90; reserve $32, guard unbraked. Last-hour tracked cost $3.4006: Sail models $1.6391, estimated Gym $1.4416, OpenAI $0.3199. Funded Sail model cap remains $2.25/hour. OpenAI September $598.17/$707, $108.83 remaining; no October allowance added. |
| 9 | Harness | current main `60b34dd9`; 834 text files / 323,380 lines across active league, ltcm, scripts, gateway and docs, excluding archive. Eight recorded watchdog restarts since T0. Main CI 11m09s (3.11), 12m06s (3.14), gateway 8s. Draft prune stays for after Monday close; its previous integrated head passes in under two minutes, latest guard fix awaits CI/review. |

### Sprint scoreboard, T0 + 17 h (23:12Z Sept 26, after R1)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 34 alive, up from 16 at the sprint's start (21:24Z); 66 retired; 32 running; 8 born in the last hour. The researcher retire tool is now guarded (only above 48, never on REVISE) |
| 2 | Throughput | 690 cycles/h, median cycle 85 s (re-validation wave); Gym queue 41 on 4 boxes, pool raised to 6 |
| 3 | Robustness | 8 robustness runs in the first 10 minutes after R1. Mid-fill diagnostic verdict: execution-bound (natural 17/72 positive; mid 50/72) |
| 4 | Evidence | 19,732 trials, 30,467 program-years. 0 validation passes under the D2 line yet (the re-validation is under way). 0 holdout looks. Gate ON (core-calibrated-v1 pair) |
| 5 | Readiness | `real_money` false; grant not enabled; gateway types "off" (all by design until R2); Claude route live |
| 6 | Money | equity $481.63 cash; 0 orders; 0 option positions |
| 7 | Compute | Sail $184.75 (burn about $45/day; guard line $32, unbraked). OpenAI September about $602 of $707. Claude $0.34 of the $70 pre-Monday cap |

### Sprint scoreboard, T0 + 19.5 h (01:53Z Sept 27, after R2)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 60 alive (48 running), 72 retired; 18 born and 6 retired in the last 2 h, including the 13 revived and 1 rescued; `population.start` 60 |
| 2 | Throughput | 1,240 cycles/h, median cycle 116 s; 205 robustness runs in 2 h; Gym queue 12 on 8 boxes, pool back to 6 |
| 3 | Robustness | Honest fill model `fm-c4a0c70c9afbf09f` (2,114 cells) shared by the Gym, the gate and the live shadow; stress runs halve passive fill rates |
| 4 | Evidence | 23,402 trials, 45,221 program-years. 0 validation passes under D2. The nearest two meet 6 of 8 checks (trades, days, mean, quarters and stress pass); both fail t (about 0.45 against 2) and the deflated Sharpe. 0 holdout looks. Gate on (core-honest-v1) |
| 5 | Readiness | R2 live; `real_money` true; grant active on `ad9bd54c` (capital $481.63, Probe floor $100); gateway real types = 4 debit types, per-order share 0.25; observe 8 and calibration on for Monday; paper proofs (multi-leg and single-leg) at Monday 13:35Z |
| 6 | Money | equity $481.63 cash; 0 orders; 0 option positions (LTC dust only) |
| 7 | Compute | Sail $176.99 (last hour: models $1.78, Gym $1.51, plus the data box about $0.5; the D6 budget is about $3.5/h to Monday's open). OpenAI September $603.47 + $9.36 inflight of $707. Claude $2.20 of the $70 pre-Monday cap (22 calls) |

### Sprint scoreboard, T0 + 21.5 h (03:52Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 60 alive (48 running), 75 retired. Last 2 h: 3 born, 3 retired (2 by the tournament after review, 1 after its diagnostician rewrite) |
| 2 | Throughput | 1,363 cycles/h, median 102 s; 142 robustness runs in 2 h; Gym queue 5 |
| 3 | Robustness | honest fill model shared by the Gym, the gate and the shadow book |
| 4 | Evidence | 26,375 trials, 57,496 program-years. 0 validation passes. Three at 6 of 8 checks (including the revived `pin-qqq-fly-r`); all fail t and the deflated Sharpe. 0 holdout looks |
| 5 | Readiness | unchanged from the T0+19.5h board |
| 6 | Money | equity $481.63; 0 orders; 0 option positions |
| 7 | Compute | Sail $171.24 (about $2.9/h across 01:53-03:52Z, inside the D6 budget). OpenAI $603.74 + $9.36 inflight of $707. Claude $3.34 (29 calls). Data: names about 1,800 tasks/h, back months next |

### Sprint scoreboard, T0 + 24 h (06:20Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 60 alive (48 running), 80 retired; 5 born and 5 retired in 2 h, mostly researchers honestly abandoning long-premium ideas |
| 2 | Throughput | 1,435 cycles/h, median 102 s; Gym queue 2 |
| 3 | Search | 30,168 trials, 73,375 program-years. Operator sweep generation 1 (12 templates incl. re-runs, about 950 variants): no Train edge, 0 of about 45 finalists positive at 1.5x stress |
| 4 | Evidence | 0 validation passes, 0 holdout looks. Nearest: `range-consumed-spxw-credit` 6/8 (fails t, deflated Sharpe) |
| 5 | Readiness | unchanged; grant active, real money on, gateway 4 debit real types |
| 6 | Money | equity $481.63; 0 orders |
| 7 | Compute | Sail $162.85 (about $3.4/h over 2.5 h including sweep boxes; D6 limit about $3.5/h). Claude $7.43 (57 calls; the diagnostician is now active). OpenAI $603.74 + $9.36 inflight of $707 |

First-principles reading, recorded for the owner's morning review:
- The only durable options edge available to public-data, minute-scale research is a risk premium,
  mainly the variance risk premium, which sellers earn.
- Every premium-buying design lost on 2022-2024. Short-dated premium selling was about break-even
  after honest costs.
- The documented harvest horizon is 30-45 DTE, managed: generation 3 targets it once the SPY/QQQ back
  months land.
- Harvesting it needs credit structures, and real money needs equity >= $2,000. A credit-enable
  change is being prepared as a PR (not merged); deploying it needs the owner's deposit and an
  extra release.

### Sprint scoreboard, T0 + 26 h (08:16Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 60 alive (48 running), 85 retired; 5 born (2 founded by the operator sweep) and 5 retired in 2 h |
| 2 | Throughput | 1,625 cycles/h, median 102 s; Gym pool 6 busy, 2 ready; queue 1; 3 provider 502s |
| 3 | Search | 33,632 trials, 86,628 program-years. Sweep generation 2: `liquidity_rebound_itm_vertical` has Train edge (47 of 72 positive; best robust score 0.58, t 2.19; 2 of 5 finalists positive at 1.5x). It was founded as two families; the pool reproduced rank 0 (168 trades, t 2.06). `fear_premium_itm_call_vertical`: 41 of 93 positive, but 2022 is flat or negative in every strong variant (best robust score 0.002). `close_pressure_ibs`: 0 of 5 positive at stress. `day_session_long_gamma`: 0 of 82 positive. The SPXW-reading templates ran the sweep boxes out of memory; they will be re-run with one worker |
| 4 | Evidence | 0 validation passes, 0 holdout looks. Nearest: `range-consumed-spxw-credit` 6/8 |
| 5 | Readiness | unchanged; grant active, real money on, gateway 4 debit real types |
| 6 | Money | equity $481.63; 0 orders |
| 7 | Compute | Sail $157.10 (about $2.9/h since 06:20Z including 5 sweep boxes). To stay above the $32 line through Tuesday, the burn must drop to about $1/h after Monday's open. Claude $9.36 (67 calls; diagnostician $8.95). OpenAI $603.97 + $9.36 inflight of $707 |

Reading: the two Train edges are both in-the-money call verticals. By put-call parity each is a short put
spread held in debit form, so part of its return is equity beta. `liquidity_rebound`'s strongest year is
2022, a falling market, so its edge is more than beta. `fear_premium`'s edge is only in 2023-2024, which
looks like beta. Validation 2025 and the holdout judge both.

### Sprint scoreboard, T0 + 28 h (10:02Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 60 alive before, 39 after 10:05Z. Last 2 h: 30 born (24 names families from the architect under agenda v3; 3 operator-sweep founders), 30 retired (27 self-declared dormant). At 10:05Z, 21 architect names families were retired: none reached a positive eligible Train score in 6-15 versions each, matching the sweep |
| 2 | Throughput | 953 cycles/h, median 177 s, pool 6 busy, queue 30: the names families' five-chain runs made the Gym the bottleneck (1,625 cycles/h at 08:16Z) |
| 3 | Search | 35,631 trials, 96,728 program-years. Sweeps since 08:16Z: XSP credit 1 of 229 positive; names rebound 13 of 228, none robust; calendar windows 1 of 72; always-on debit put-write: 12 of 79 ran, all negative (2022 deeply); 67 hit the per-worker memory cap and are re-running in small batches with the combined rebound-plus-put-write template |
| 4 | Evidence | 0 validation passes, 0 holdout looks. Five families at 5/8, including both founded rebound families (validation t 0.37 and 0.29) |
| 5 | Readiness | Interim 25-root pair adopted (Gym `sbcp_b358ab73`, gate `sbcp_92c29288`); grant active; real money on; gateway 4 debit real types; observe 8 and calibration on for Monday |
| 6 | Money | equity $481.63; 0 orders |
| 7 | Compute | Sail $151.94 (about $2.8/h since 08:16Z including the image builds and up to 6 sweep boxes). Claude $14.07 of the $70 pre-Monday cap (91 calls; diagnostician $13.09; about $1.85/h). OpenAI $604.60 + $9.36 inflight of $707 |

### Sprint scoreboard, T0 + 31 h (13:28Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 61 alive (48 running), 138 retired. Last 2 h: 4 born, 4 retired. Target raised to 72 at 13:30Z |
| 2 | Throughput | 1,122 cycles/h, median 151 s; pool 12 busy (raised from 6 at 13:25Z); queue 20. 14 cycles timed out waiting on the Gym during the image switch and scale-up |
| 3 | Search | 39,366 trials, 116,499 program-years. Back-month sweep (complete image), positive of total: credit ladder 4/63, condor 0/63, long put fly 0/70, calendar 0/66, diagonal 48/64 (2022 flat; not a real type), trend long options 7/8 (best positive every Train year and +$11,929 at 1.5x). Founded `sweep-bm-trend-long-option` at 13:27Z |
| 4 | Evidence | 0 validation passes, 0 holdout looks. Nearest: `event-crush-xsp-fly-r` 6/8 (2025 t 1.03) |
| 5 | Readiness | Complete back-month pair adopted 13:25Z (Gym `sbcp_a38bb07a`, gate `sbcp_a5e975a5`). The pool-style check (Train split 8, Validation whole) gave numbers identical to the names image. PR #393 not merged (owner agreed; evidence on the PR) |
| 6 | Money | equity $481.63; 0 orders. The owner is depositing more; the grant is re-ratified at the new capital once it reaches buying power |
| 7 | Compute | The owner topped up (Sail to $190, OpenAI $113, Claude balance $100) and said do not throttle. The guard still read $139.67 at 13:28Z. Push settings: Gym pool 12 boxes, researchers $3/h, population 72, architect hourly, diagnostician 5 a round and $45/day, Claude cap 98 (the gateway's lifetime `CLAUDE_USD` 100 binds first: $18.93 spent). Claude $3.08 in the last hour |

### Sprint scoreboard, T0 + 33 h (15:29Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 74 alive, 146 retired. Last 2 h: 21 born (the architect under the back-month single-option agenda), 8 retired |
| 2 | Throughput | 821 cycles/h; pool 10 ready, queue 0. Only 1 family was cycling: the V4-Pro top profile had spent the $3/h research pace. Rebalanced at 15:31Z (researchers $4.5/h, pool 6-10 boxes) |
| 3 | Search | 41,349 trials, 126,322 program-years. Rebound as a back-month call: Train plateau across delta 0.25-0.6, but 2025 t 0.06 on 47 trades (the signal was rare in 2025) |
| 4 | Evidence | **FIRST VALIDATION PASS**: `low-close-location-backmonth-call` (architect-born 14:49Z, version 7). A 30-45 DTE call on SPY/QQQ after an index closes low in its daily range inside an up-trend. Validation 2025: 207 trades on 51 days, daily t 2.47, deflated Sharpe 0.997 (the lineage's 1 validated version, 169 lineage trials), 3 of 4 quarters, +$17,998; at 1.5x +$14,867. All 8 checks. Gate (review, Claude audit, holdout look) pending. Also 6/8: `event-crush-xsp-fly-r`, `sweep-bm-trend-long-option` (2025 t 1.04, +$8,544) |
| 5 | Readiness | The passing family's typical structure is $559 of maximum loss. Options buying power is $481.60 (the deposit is unsettled). The D4 Probe cap is $100. Real money for it needs the settled deposit AND the owner's decision on a one-contract Probe |
| 6 | Money | equity $1,481.63 (deposit shown, not yet in options buying power); 0 orders |
| 7 | Compute | Sail $180.37. Claude $24.04 of the $100 lifetime (143 calls). OpenAI $606.22 + $9.36 inflight of $707 |

### Sprint scoreboard, T0 + 35 h (17:29Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 72 alive (48 cycling), 156 retired; 8 born and 10 retired in 2 h |
| 2 | Throughput | 1,210 cycles/h, median 119 s; pool 4 busy, 6 ready; queue 6; 17 provider 502s |
| 3 | Search | 43,913 trials, 139,630 program-years. Generation 7 (direction-neutral back-month) failed its own mechanism checks: the two-sided rebound's sides are the year's drift, and cheap vol is too rare. The index rebound's patient two-sided version (v78) scored 2025 t 0.19 |
| 4 | Evidence | 1 validation pass alive (the IWM fork of `low-close-location-backmonth-call`). Holdout looks 2, passes 0 (both that lineage's; -$9,372 on 2026). 6/8: `sweep-bm-trend-long-option` (t 1.04), `range-consumed-spxw-credit-on-qqq` |
| 5 | Readiness | Grant active; real money on; calibration on; observe 8. No family is eligible for real money: no holdout pass, and any back-month call costs more than the $100 Probe cap and the $481.60 options buying power |
| 6 | Money | equity $1,481.63 (options buying power $481.60 until the deposit settles); 0 orders |
| 7 | Compute | Sail $168.63 (about $5.9/h; about $50 expected at Monday's open, above the $32 line). Claude $26.36 of $100 (162 calls). OpenAI $606.41 + $9.36 inflight of $707 |

### Sprint scoreboard, T0 + 37 h (19:32Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 72 alive (48 cycling); 6 born and 6 retired in 2 h |
| 2 | Throughput | 1,261 cycles/h, median 116 s; pool 6 busy, 4 ready; queue 4 |
| 3 | Search | 46,643 trials, 154,181 program-years. The architect's direction-neutral volatility births lead Validation 2025: `peer-uncertainty-transfer-straddle` t 1.77 (6/8), `serial-revision-tail-strangle` t 1.20 (6/8), `scaled-entry-liquidity-reversal` (6/8) |
| 4 | Evidence | 1 validation pass alive (the IWM fork); holdout looks 2, passes 0 |
| 5 | Readiness | Unchanged: no family eligible for real money; calibration and observe on for Monday |
| 6 | Money | equity $1,481.63; options buying power $481.60 (the deposit unsettled); 0 orders |
| 7 | Compute | Sail $157.14 (about $5.6/h; about $56 at the open). Claude $30.70 of $100. OpenAI $606.86 of $707 |

### Sprint scoreboard, T0 + 39 h (21:30Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 75 alive (48 cycling); 11 born and 8 retired in 2 h |
| 2 | Throughput | 1,290 cycles/h, median 116 s; pool 9 busy; queue 3; 18 provider 502s |
| 3 | Search | 49,299 trials, 167,908 program-years. Best 2025 validation t in 2 h: `scaled-entry-liquidity-reversal` 1.41, `pre-earnings-iv-runup-straddle` 1.18 |
| 4 | Evidence | 1 validation pass alive (the IWM fork); holdout looks 2, passes 0 |
| 5 | Readiness | 24/7 research on (the owner, about 19:45Z): `guard.burst_until` 2026-10-05, `burst_cap_usd` 900. Private tools `preopen.py` (9/9 PASS live) and `fillcheck.py` (replay exact on 921 orders) ready for Monday |
| 6 | Money | equity $1,481.63; options buying power $481.60; 0 orders |
| 7 | Compute | Sail $145.98 (about $5.6/h; the $32 line around Monday 17:30Z without a top-up). Claude $32.17 of $100. OpenAI $608.75 of $707 |

### Sprint scoreboard, T0 + 41 h (23:30Z Sept 27)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 72 alive (48 cycling); 10 born and 13 retired in 2 h |
| 2 | Throughput | 1,308 cycles/h, median 117 s; pool 8 busy; queue 0 |
| 3 | Search | 52,060 trials, 182,881 program-years. 2025 validation leaders in 2 h: `pre-earnings-iv-runup-straddle` 1.13-1.18 (names; negative at 1.5x; not a real type), `scaled-entry-liquidity-reversal` 1.17 (43 trades) |
| 4 | Evidence | 1 validation pass alive (the IWM fork); holdout looks 2, passes 0. A second fork of that lineage is at 7/8 (one look left in the lineage, Holm-stricter) |
| 5 | Readiness | Unchanged. The account's own history holds 4 option fills (AAL penny calls), so Monday's calibration is the first real-fill measurement for SPY/QQQ verticals |
| 6 | Money | equity $1,481.63; options buying power $481.60; 0 orders |
| 7 | Compute | Sail $135.59 (about $5.2/h; the $32 line around Monday 19:30Z without a top-up). Claude $34.23 of $100. OpenAI $610.63 of $707 |

- **02:56Z Sept 28 R3 deployed** (release `20260928T025520Z-8d5e8eec714a`, main `e4c9fe5a`; PRs #394 and #397).
  - Contents:
    - mirror and backup identity fixes (#394);
    - researcher `gym_sweep` (up to 6 variants in one call);
    - dead families can retire (idle rule by Gym evaluations);
    - identical re-runs return the stored result with no trial;
    - honest holds and a 40-cycle dormancy clause;
    - the operator's gate hold.
  - Reviewed adversarially twice: 8 findings, all fixed in `327d3d21` and verified.
  - Research side only: no `league/gym`, money or gateway file changed; the money digest is `ad9bd54c`, the grant's pin.
  - Sail could not take a warm checkpoint (503), so a consistent SQLite backup of the swarm, ledger, live and grant
    databases is kept on the box at `state/backups/pre-r3/`.
  - Staged first: `researcher.retire_idle_evaluations` 500.
- **03:00-03:10Z What R3 showed at once: the dead families were only waiting for an exit.**
  - In the first 9 minutes, 1,183 of 1,428 cycles were holds (about 4 s and $0.0005 each).
  - Nearly every holder's own note said its mechanism was refuted and that the retire tool was not offered to it.
  - The operator retired 29 such families (not gate-ready, no passing validation), taking the population from 73 to 44.
  - `population.floor` 30, so the dormancy clause can clear the rest; `architect.every_seconds` 1800, so v4-agenda
    births refill faster (fewer, deeper families).
  - Gate hold on `low-close-location-backmonth-call-on`: the lineage's last look waits for the drift screen (#398).
  - The interim operator mirror is stopped; the House's own mirror advances.

### Sprint scoreboard, T0 + 43 h (01:29Z Sept 28)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 74 alive (48 cycling); 19 born and 17 retired in 2 h (10 of the retirements by the operator's dead-family list) |
| 2 | Throughput | 1,333 cycles/h, median 122 s; pool 8 busy, 2 ready; queue 2; 5 provider 502s |
| 3 | Search | 54,803 trials, 197,130 program-years. No new leader: the low-close lineage (t 2.47, one look left, to be held for its placebo), `peer-uncertainty-transfer-straddle` 1.77 (not a real type), `stacked-streak-rebound-ladder` 1.27 (SPY debit vertical, 2/4 quarters) |
| 4 | Evidence | 1 validation pass alive (the IWM fork); holdout looks 2, passes 0 |
| 5 | Readiness | R3 (`gym_sweep`, idle retire, no duplicate runs, dormancy, gate hold) integrating on #397; deploy before the 10:00Z pre-open, research side only |
| 6 | Money | equity $1,481.63; options buying power $481.60; 0 orders |
| 7 | Compute | Sail $125.39 (about $5.1/h; the $32 line around Monday 19:45Z without a top-up). Claude $36.98 of $100. OpenAI $614.37 + $9.36 inflight of $707 |

- **01:50-04:00Z Sept 28 The fill-model audit (a workflow: measure, build, sensitivity, three skeptics).** Train only; private numbers in the operator's files.
  - **The defect is real.** The engine lets a resting order's calibrated fill draw happen only on minutes when the
    structure's next-minute mid moves against it or stays flat. The hazard was measured over all minutes, so the rule
    removes roughly half of the calibrated draws and all favourable-minute fills.
  - **Most single-leg Gym fills are crosses**, where the next minute's natural comes through the limit. All-in, the
    Gym's single-leg fill rate is somewhat below the measured one. The distortion is mostly in fill quality: the Gym's
    passive fills are almost all adverse.
  - **Draft PR #400 (a conditional rule behind the fitted table; bit-identical with the adopted table) is NOT adopted.**
    The skeptics found that its fit over-credits favourable minutes for a fixed-price limit (it uses calibrate's pegged
    hit definition, not a print anchored to the limit's minute). Its package conditioning is mismatched, and it still
    overlaps with the engine's certain fills. For complex orders the Gym may already fill more often than a strict
    complex-book truth.
  - **Sensitivity:** eight rebound finalists (patient and two-sided variants) under today's model and the conditional
    one, at 1.0x and 1.5x.
    - Under either model, no finalist is robustly positive at 1.5x: 2024 loses at 1.5x for 7 of 8 under the conditional
      model and 6 of 8 under today's.
    - Trades both models take got cheaper, but the extra fills the conditional rule allows lost money: adverse
      selection is real.
    - Harness checks: the branch engine with the adopted table was bit-identical in 16 of 16 runs.
  - **Conclusion:** the fill model is not what stands between the rebound and a pass. The rebound's patient version
    scored 2025 t 0.19, and its Train edge fades in 2024. Monday's calibration round trips are a test set only: no
    table is fitted or tuned on them, and `fillcheck.py --replay` against Tuesday's tape classifies each worked minute
    as the engine does.
- **Also built tonight (R4 candidates, each adversarially reviewed):**
  - #398 drift screen: the fit was rebuilt after the first review found a variance-weighted bias;
  - #401 Gym memory: a snapshot/view cycle kept every day's chains alive, and a 150-day worker falls from about 1.2 GB
    to about 0.23 GB, byte-identical;
  - #402 hold backoff, with dead families offered retire on the REVISE turn and an idle pass every 5 minutes;
  - #399 Train 2020-21: being fixed after review; merges after the close.

- **04:00-04:50Z Sept 28 Design review (a workflow: five independent lenses, a judge, a critic).** Honest result: the
  odds that any family passes Validation and the holdout within 2-5 days are about 2%.
  - **Power.** Under D2, a family needs a true per-year t near 2.5-3 net of costs for decent odds. At an expected
    per-year t of 1.0, Validation passes 16% of the time and both stages about 1%; at 2.5, 68% and 35%.
  - **Train does not transfer.** The 168 Train-eligible versions with a positive worst year averaged a 2025 t of -0.21;
    1.8% reached t 2, below a zero-edge program's 2.3%. Rank correlation of Train t with 2025 t is 0.39, so only Train
    t of about 3+ carries information after about 400 trials a family.
  - **The rebound has no headroom.** At zero cost, as the underlying, its per-year t never reaches 2 in 2019-2025.
  - **Ensembles do not rescue it.** Train winners are nearly uncorrelated, so books look like Sharpe-3 portfolios on
    Train. Pre-registered on Train, the top-12 book would have scored 2025 t -0.89; the components' 2025 mean t is -0.3.
  - **The volatility premium in the real types:** mid edge is well under the round-trip cost.
  - **Metric mismatch.** Validation's t is per dollar of max loss; the holdout judges daily dollars. For programs whose
    risk varies by day, the dollar t is a third to two thirds of the ratio t.
  - **The critic's corrections.**
    - A full-size (wider) rebound was already validated by the swarm at $109-278 max loss, t at most 1.41.
    - Debit twins of credit and iron winners belong to a refuted class.
    - Live sizing allows a Probe structure only up to $100 of max loss including fees, with at most 3 open structures
      a family.
    - One SPXW diagnostic run looks like a settlement or marking artifact and is being investigated.
  - **Actions.**
    - Agenda v5 is live (architect): the Sharpe arithmetic, ceiling-first at the mid, the rebound and real-type VRP
      added to the refuted list, idiosyncratic and quarterly-recurring drivers first, and sizes of $60-95 with fees.
    - Follow-up tracks running:
      - the SPXW artifact hunt;
      - the pre-registration of a frozen 2020-21 replication screen, frozen before the data exists and counted by
        mechanism (at least 6 replicators across at least 3 mechanisms);
      - the single-name earnings event-variance premium at Probe size with a placebo, the one large documented
        premium never tested;
      - the frozen-version runner for that screen.
    - Holdout looks are protected: the operator gate-holds any new validation pass until it clears the drift screen
      and, once it exists, the 2020-21 replication.
  - If the pre-registered tests all fail by about Wednesday, the honest reading will be that no one-contract debit
    strategy of $100 or less on this data has the Sharpe D2 demands. The owner then chooses between full push and a
    low-cost standing mode.

### Sprint scoreboard, T0 + 45 h (03:30Z Sept 28, after R3)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 12 alive at 03:30Z. 70 retired in 2 h: 60 by the operator (researchers that had declared their own mechanism refuted and held 20-135 cycles), 10 by the tournament. `population.floor` 12. The architect (GPT-6 Astra) refills every 20 min, 12 a pass, toward 72: 3 born 03:06Z, 12 born 03:30Z, all two-sided under agenda v4 |
| 2 | Throughput | 3,000 cycles/h, mostly holds before the retirements, median 2.8 s; 0 cycle errors; pool 1 busy, 9 ready |
| 3 | Search | 57,318 trials, 211,123 program-years. The swarm's own verdict after about 57,000 trials: no family survives at the Gym's costs. Closest now 3 of 8 checks |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0. The low-close lineage is held at the gate |
| 5 | Readiness | R3 live. Being built or reviewed for R4: the drift screen (#398, second review), hold backoff with dead families able to exit, the Gym daily-GC memory fix, and the fill-model audit (does the adverse-selection rule double-count against patient orders?). #399 (Train 2020) is being fixed after its review; it merges after the close |
| 6 | Money | equity $1,481.63; options buying power $481.60; 0 orders |
| 7 | Compute | Sail $116.11 (about $4.6/h; the $32 line around 21:50Z without a top-up). Claude $39.59 of $100. OpenAI $615.00 + $9.36 in flight of $707 |

- **05:00-05:15Z Sept 28 Pre-registration: the frozen 2020-21 replication screen.** It is written before any 2020-21
  option data exists: PR #399 merges after today's close and the fetch runs after it. Nothing from 2020-21 was read to
  write it. No box was used, and the House was read only.
  - **Why.** Train winners have not transferred to 2025. 2020 (the crash and rebound) and 2021 (a quiet bull) are new,
    unseen regimes. Fixing the inventory and the kill test now makes the screen a real out-of-sample test.
  - **Verifiable later.** The private file `prereg-2020-21.json` has sha256
    `316fca9c62bea407d84c1e32cf77dc7592294f5515a45948e9376fbdfd0391d2`. It holds:
    - each component's family id and version, code sha256, merged-params sha256 and the Gym's run sha;
    - for sweep rows, the template name, grid index and the frozen placebo's hashes;
    - the Train figures the selection used, the mechanism tags, the exclusions and every rule below.

    It holds no program code and no parameter values.
  - **The inventory: 38 frozen components.**
    - **30 Train winners of the real-money types.** For each family, take the version with the best robust Train score,
      keeping only those with a positive worst Train year. Then drop:
      - clones with an identical Train result (7);
      - families with roots outside the 2020-21 fetch (7);
      - premium sold in debit form, per the critique: put-writes as call verticals, variance-premium ITM verticals, and
        long butterflies as iron-fly twins (5);
      - multi-leg XSP/SPXW (2).

      The top 30 by Train t remain (6 fell below the cut).
    - **The 8 rebound sweep finalists.** These are the top 2 by Train score from each of the four exec and
      patient-broad runs, the same set as the fill audit.
    - No Validation or holdout number was used to select or tag any component.
  - **Mechanism classes. Replication is counted by mechanism, not by version.**

    | Class | Mechanism | Components |
    |---|---|---|
    | R | Index short-horizon reversal (liquidity provision). Every rebound variant and its mirror counts as ONE mechanism | 25 |
    | T | Multi-session trend continuation held in long convexity | 6 |
    | E | Directional drift around scheduled macro events | 2 |
    | O | Overnight premium after closing inventory pressure | 1 |
    | M | Intraday liquidation continuation read from quote compression | 1 |
    | C | Calendar flows (month and quarter turns, pre-holiday, opex week) | 1 |
    | L | Leveraged-ETF close rebalancing flow | 1 |
    | F | Intraday opening-range breakout failure | 1 |
  - **The kill test.**
    - **Window.** 2020-01-02..2021-12-31. A trade belongs to the window by its entry day.
    - **Statistic.** t is the Gym's daily t on max loss.
    - **A component replicates only if all of these hold:**
      1. at 1.0x, t ≥ 1.0 over the window;
      2. at 1.5x, P&L > 0 over the window;
      3. at 1.0x, t > -0.5 in 2020 and in 2021;
      4. it beats its placebo in 2020 and in 2021: its mean daily return on max loss is strictly above the placebo's;
      5. at 1.0x, P&L > 0 with every trade that was open at any time in March 2020 removed;
      6. a natural-only twin was run and reported. It gates nothing, but a component without one does not replicate.
    - **Placebos.** A directional component's placebo is its signal inverted. A fly's placebo would be every eligible
      session, but no fly remains in the inventory.
      - The sweep rows' placebos are frozen in the file.
      - Each House component's inverted program changes only the entry condition. Its hashes go in an addendum, and that
        addendum's sha256 is recorded here before any 2020-21 run. A component with no frozen placebo by then fails
        test 4.
    - **Undefined results.** A t that cannot be computed fails the test that needs it. A program error counts as a
      failure. Only an infrastructure failure may be rerun, with the identical hashes.
    - **Runs.**
      - Train on the verified 2020-2024 Gym image, never a gate image.
      - Split 16, with each program's own roots.
      - Every run's code and params hashes are checked against the file before it counts.
  - **The decision.** The route continues only if at least 6 components replicate across at least 3 mechanism classes.
    Otherwise it stops: no book is built and nothing from this screen goes to Validation.
  - **Inventory mean.** The screen also reports the mean window t over all 38 components and the mean of the class means.
    Noise predicts about -0.4. This mean is descriptive only.
  - **The book rule** (only if the route continues):
    - The members are all the replicators, equally weighted.
    - Each member risks $100 of max loss (fees included) on each of its entry days.
    - The book's daily new max loss is fixed at N × $100. An unused slice is not reallocated, so there is no look-ahead.
    - The book's daily return is the mean of the members' daily returns on max loss, with zero for a member that did not
      enter. Its t is taken over days with any entry.
  - **The predicted 2025 t.** It is computed with this formula and recorded here before any Validation run of a
    replicator or the book, and before anyone reads their 2025 numbers from stored runs.
    - **Each member.** The shrunk per-year t is θ̂ = μ0 + k (t_window - √2 μ0), with k = √2 σ0² / (2 σ0² + 1). The
      constants are fixed now: μ0 = -0.2 and σ0² = 0.4, from the Train-positive versions' 2025 spread.
    - **The book.** T̂ = Σ wᵢ θ̂ᵢ / √(Σᵢ Σⱼ ρᵢⱼ wᵢ wⱼ).
      - wᵢ is the sd of member i's daily returns × √(its entry days a year).
      - ρᵢⱼ is the correlation of the members' all-session daily returns.
      - Both are measured on the 2022-24 part of the screen runs.
    - **What it implies.** Take 6 equal members, each at window t 1.5, with correlation 0.1: the book is predicted near
      t 0.7. At window t 2.5 it is predicted near t 1.35. **Even a passing screen predicts a book below the verifier's
      2**, unless replication is both strong and broad.
  - **Caveat: 2025 is not clean for this book.** 14 of the 30 House components already have a 2025 Validation run of the
    same version in the store. The clean tests are 2020-21 and the holdout, which this screen never touches.
- **05:11-05:18Z Earnings event-variance premium (S1), phase 0: killed.** The kill tests were written before any run. It
  was a 1-lot centred long call fly at a max loss of $95 or less with fees, with a matched placebo, on 14 reporting
  names in 3 shards, at 1.0x and 1.5x. All four kill tests fired:
  - pooled t at or below 0 in every Train year at both stresses;
  - the event arm not above the placebo in 2023 and 2024;
  - under 40 trades on 20 days in every year;
  - losses driven by max-loss trades.
  Filled at the mid, as a diagnostic only, it still misses the agenda's bar: t 1.93 / 1.00 / -1.14 in 2022-24. Buying
  at the natural costs about 30% a round trip. Only 71 of about 168 reports fit the $95 budget. The premium exists but
  is small: realised report gaps averaged about 0.7 of the priced move. Any future attempt needs a mechanism-level
  change.
- **05:00-06:20Z The SPXW "artifact" was the operator's own labelling bug, and the hunt found a real Gym marking bug.**
  - `middiag.py` paired the batch's name-sorted results with families in export order, so 68 of 72 rows in its private
    results carried another family's numbers. It is fixed and the file relabelled; its aggregate verdict did not depend
    on labels.
  - The t 8.24 row belongs to an SPXW nickel-credit spread whose sample holds no tail event. The daily t cannot see its
    risk, and its max loss is far above the Probe cap. Settlement is sound: the store's 16:00 index level matches the
    official close on all 753 Train days.
  - **The real bug:** when one leg's quote blows out, the sum of the legs' touches (the natural) can fall outside what
    the package can ever be worth, for example a debit vertical closed below zero, and the engine filled there. It is
    rare on Train and bites in blow-out episodes. Draft PR #404 bounds fills and marks to each structure's payoff range.
    The full suite is green and the money digest unchanged; it goes to review for the after-close release.
  - No real or shadow position was ever in XSP or SPXW.
- **06:15Z R4 merged** (#403 = #401 Gym memory + #402 hold backoff and idle pass + #398 drift screen). CI is green on
  both Pythons for the combined tree, the local sensitive suite (live close and parity, memory, drift, holds) passes
  143 tests, the money digest is unchanged, and the SQLite backup is at `state/backups/pre-r4/`. Deploying.

- **06:16Z R4 deployed and verified** (release `20260928T061526Z-971da2b2e678`, main `7effc585`).
  - The watchdog canaried, promoted and completed its watch.
  - The swarm restarted on the release with 0 cycle errors.
  - The hold backoff is visible: 11 of 12 families are waiting instead of cycling every ~12 s.
  - `researcher.dormant_cycles` is 12 (about 1 h at the 300 s backoff).
  - `preopen.py` passes 9/9: release, grant, gateway real types, account, swarm, bands (2 observe rows), the House's
    own mirror (lag 0), the House backup (ok, found by the pinned box id: #394 works), and compute.

- **07:02Z Sept 28 Placebo addendum to the 2020-21 pre-registration.** It is frozen before any 2020-21 run, as
  the pre-registration requires. No 2020-21 option data was read, no box was used, and the House was read only.
  - **Verifiable later.** The private file `prereg-2020-21-placebo-addendum.json` has sha256
    `1a95ab2e2b673c69521b547e02ce2a2ec3d4b14ba98fb28f75f3848d4f9f633d`.
    - It names the pre-registration it extends by that file's sha256,
      `316fca9c62bea407d84c1e32cf77dc7592294f5515a45948e9376fbdfd0391d2`, which is unchanged.
    - For each of the 30 House components it holds the placebo's status. For each frozen placebo it also holds the code
      sha256, the merged-params sha256 and the Gym run sha a placebo run must report.
    - It holds no program code and no parameter values. The placebo programs stay private and never enter git.
  - **The rule.** A directional component's placebo is its signal inverted.
    - Only the entry condition changes. The placebo trades the same structure, side, size, strikes, horizon, exits and
      timing, but enters when the signal says the opposite.
    - A regime or trend filter is kept and the move inside it flips: a pullback in an uptrend becomes a rally in an
      uptrend, and a rebound after lower closes becomes the same trade after higher closes.
    - A two-sided program has each side's trigger inverted. The structure and the side of the trade are never flipped.
    - Where the entry condition cannot be isolated honestly, no placebo is invented, and the component fails test 4 by
      rule.
  - **How it was checked.**
    - A writer drafted each placebo from the frozen code, and an independent checker reviewed each one. The checker
      confirmed the original's hashes, read the diff, ran mirror tests of the trigger and ran the Gym's own safety check
      and loader.
    - All 30 verdicts were ok. The hashes were then recomputed from the files on disk.
    - Each placebo keeps its original's params unchanged, so its params hash equals the original's.
  - **Result: 28 frozen, 0 rejected, 2 not isolable.**
    - **Frozen (28):**

    | Slot | Family |
    |---|---|
    | 1 | sweep-rebound-bm-long-call-p2 |
    | 2 | bear-regime-rally-fade-putvert |
    | 3 | low-close-location-backmonth-call--2 |
    | 4 | scaled-entry-liquidity-reversal |
    | 5 | sweep-liquidity-rebound-itm-vertic-2 |
    | 6 | sweep-liquidity-rebound-itm-vertical |
    | 7 | stacked-streak-rebound-ladder |
    | 8 | daily-oversold-rebound-vertical |
    | 9 | low-close-location-backmonth-call--3 |
    | 10 | tight-spread-liquidation-puts |
    | 11 | low-close-location-backmonth-call-on |
    | 13 | index-laggard-catchup-call |
    | 14 | overnight-inventory-call |
    | 15 | slow-tenor-rebound-debit |
    | 16 | slow-breadth-tail-call |
    | 18 | sweep-bm-trend-long-option-on-spxw-3 |
    | 19 | sweep-bm-trend-long-option |
    | 20 | spy-flush-stabilization-call |
    | 21 | orb-fade-iwm-r |
    | 22 | balanced-regime-reversal-vertical |
    | 23 | pre-announcement-drift-debit |
    | 24 | sweep-bm-trend-long-option-on-iwm |
    | 25 | shock-day-rebound-debit |
    | 26 | leverage-reset-close-momentum |
    | 27 | calendar-flow-harvest-basket |
    | 28 | downtrend-rally-fade-put-vertical |
    | 29 | low-close-location-backmonth-call |
    | 30 | macro-release-drift-debit |

    - **Not isolable (2). Each has no frozen placebo and fails test 4 by rule.**
      - Slot 12 `persistent-breakdown-tail-put`: its entry gate also decides when its exits run. The entry cannot change without
        changing the exits.
      - Slot 17 `crossasset-liquidation-tail-put`: the frozen version has no directional trigger to invert.
    - At most 28 of the 30 House components can now replicate. The decision rule is unchanged: at least 6 replicators
      across at least 3 mechanism classes.

- **06:58Z R5 deployed and verified** (release `20260928T065759Z-aae7108eda03`, main `9fe54351`; PR #399 Train
  2020-21 code with the switch OFF).
  - It shipped this morning, not after the close, because its main cost, a bundle move that re-validates families and
    pauses tuition rows, was nearly zero: no family passing Validation and no tuition row alive.
  - Two reviews, a verification and a final-head verification: 837 tests; with the switch off no migration, no alerts
    and the adopted pair accepted; drift decisions identical to R4 on 3,000 random cases.
  - SQLite backup at `state/backups/pre-r5/`. `preopen.py` passes 9/9; there are no span alerts.
- **07:04Z The 2020-21 fetch started** on the data box from the House (`box.py start --stages 1,2,3,4,5,6,9,10`),
  with the completion supervisor paused.
  - The probes confirm the ThetaData plan reaches 2020: SPY on 2020-03-16 (the crash) returned 18 expiries, and the
    late-2019 warm-up history returned.
  - 3,833 tasks are pending, an estimated 3-4.5 h.
  - The swarm never sees 2020-21 until the frozen screen's verdict is written; the screen runs on a sweep-only image.

### Sprint scoreboard, T0 + 47 h (05:31Z Sept 28)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 12 alive, 294 retired. 12 born and 24 retired in 2 h: architect births refute themselves and retire within about an hour, so the population sits at the floor. Agenda v5 has been live since about 04:55Z |
| 2 | Throughput | 3,000 cycles/h, still mostly hold spin until #402 ships; median 2.6 s; 2 provider 502s; pool 1 busy, 9 ready |
| 3 | Search | 58,086 trials, 216,438 program-years. Closest: `earnings-idio-drift-call` 3/8 |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Readiness | R4: #401 (Gym memory) ready, CI green; #402 (hold backoff) verified SHIP, one small fix in progress; #398 (drift screen) CI 3.11 green, 3.14 pending; #399 (Train 2020-21, switch off) under verification. Follow-up tracks running: SPXW artifact, pre-registration, earnings premium, frozen runner |
| 6 | Money | equity $1,481.63; options buying power $481.60; 0 orders |
| 7 | Compute | Sail $108.10 (about $4/h; the $32 line around 00:30Z Tuesday). Claude $42.19 of $100. OpenAI $617.04 + $9.36 in flight of $707 |

### Sprint scoreboard, T0 + 49 h (07:30Z Sept 28)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 12 alive, 294 retired, all holding at the floor; 0 born in 2 h (see row 5) |
| 2 | Throughput | 54 cycles in the last hour (the R4 hold backoff; before it about 3,000/h, nearly all holds); 0 cycle errors; pool 1 ready, 9 asleep |
| 3 | Search | 58,122 trials, 216,646 program-years. Closest: `earnings-idio-drift-call` 3/8 |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Readiness | R5 live (preopen 9/9). The 2020-21 fetch has been running since 07:04Z. **The architect had birthed nothing since agenda v5 (04:55Z):** Claude Opus stopped at max_tokens 16,000 before its JSON, GPT-6 Astra did not complete within 12,000 output tokens, and the Sail fallback (Kimi K3) proposed 0. At 07:31Z `claude.max_tokens` and `architect.max_output_tokens` were raised to 32,000 (streamed) |
| 6 | Money | equity $1,481.63; options buying power $481.60; 0 orders |
| 7 | Compute | Sail $105.32 (about $2.5/h with the swarm idle). Claude $44.46 of $100. OpenAI $618.97 + $9.36 in flight of $707 |

- **10:00Z Monday pre-open: `preopen.py` passes 9/9 on R5.**
  - Checks passed: release `20260928T065759Z-aae7108eda03`; grant `options-swarm-20260928` (digest `ad9bd54c`);
    gateway real types `debit_vertical,long_butterfly,long_call,long_put`; account ACTIVE (equity $1,481.63, options
    buying power $481.60: the deposit has not settled, so the grant stays at its capital); 2 observe rows; the House's
    own mirror (lag 9); backup ok; Sail $100.34.
  - Fill model `fm-c4a0c70c`, calibration on.
  - No Candidate, Probe, Sized or tuition row, so today's only real orders can be the three calibration round trips
    (14:00, 16:30, 18:30Z; $50 day loss bound): 1-lot $1-wide near-money SPY/QQQ call verticals at the mid, then mid +
    1 tick. They are a test set for the fill model; nothing is fitted on them.
  - Deploy freeze 13:25-20:05Z (rollback only).

### Sprint scoreboard, T0 + 51 h (09:31Z Sept 28)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 32 alive, 323 retired; 49 born and 29 retired in 2 h. The architect is back after the output-token fix: GPT-6 Astra proposed and birthed 12 of 12 in three of four passes (one Sail fallback proposed 0) |
| 2 | Throughput | 623 cycles/h, median 22 s (backoff on holds, real runs otherwise); pool 3 busy, 6 ready; 4 Gym timeouts (1,020 s) |
| 3 | Search | 58,784 trials, 224,649 program-years. Closest: `supplier-demand-cascade-put` 6/8 in Validation 2025 (fails quarters and t), born under agenda v5 |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Readiness | R5 live. 2020-21 fetch: stage 9 (core, 0-14 DTE) 2,825/2,825, 0 failing; stage 10 (SPY/QQQ back months) running, done about 10:20Z. Underlying sources match 2022-24, so no relay is needed. The pre-registered screen tooling is ready (150 runs, hash-checked, judge self-tested). #404 is ready for the after-close release |
| 6 | Money | equity $1,481.63; options buying power $481.60; 0 orders |
| 7 | Compute | Sail $101.64 (about $4.3/h; the $32 line around 01:30Z Tuesday without a top-up). Claude $47.79 of $100. OpenAI $623.12 + $11.37 in flight of $707 |

- **11:31Z The 2020-21 fetch completed.**
  - Stage 9 (the core roots at 0-14 DTE, plus 60 sessions of late-2019 underlying as history) 2,825/2,825 and stage
    10 (SPY/QQQ 15-45 DTE) 1,010/1,010, 0 failing, in about 4.5 h.
  - The quality check on a 300-day sample of the new window passed: 109.5M rows, 282k contracts, 0 bad quotes, 0
    outside hours, 0 unlisted or missing expiries, 0 missing underlying.
  - Underlying sources match 2022-24 (ThetaData), so no relay is needed.
  - 11:37Z: the sweep-only 2020-24 Gym image build (`train2020-v1`) started on the House. The swarm does not adopt it;
    `gym.train_from` stays unset until the pre-registered screen's verdict is written.

- **11:44Z The sweep-only 2020-24 Gym image is built and the pre-registered screen is launched.**
  - Image `train2020-v1`, calibrated checkpoint `sbcp_13c5a61d-e7e1-453d-8fad-8d3f997ac970`, sealed. The inside check
    passed: 83,544 files; windows history (from 2019-10-07), train and validation; nothing after 2025-12-31; network
    closed. The swarm does not adopt it.
  - The screen's check step: 38 components, 74 programs, 150 runs. Every hash matches the pre-registration
    (`316fca9c…`), the placebo addendum (`1a95ab2e…`) and the run list, and every program passes the Gym's check and
    loader. The released tree is main `9fe54351`.
  - The bridge, the screen and the judge run now on sealed sweep boxes (at most 4). The completion supervisor is
    resumed.

- **11:44-11:52Z The screen's bridge check, and why it was accepted.**
  - On the new 2020-24 image, the three proof versions over 2022-24 differed from their stored rows. The straddle:
    same 187 trades, P&L -$169. The put vertical: +4 trades. The overnight call: +4 trades, score 0.81 to 0.64.
  - The pre-registration allows differences only from the new early-2022 history, so the screen stayed blocked while
    three controlled runs isolated the cause:
    - **(A)** the old image with the released code reproduced the stored rows to the cent, so the R4 and R5 engine
      changes changed no result;
    - **(B)** the old image and **(C)** the new image, both started 2022-04-01, were identical on all three versions,
      so the data from April 2022 on is identical.
  - Conclusion: the difference comes only from Q1 2022, the new 2021 history, carried forward through equity path
    dependence. That is the effect the pre-registration anticipated. The bridge was accepted with that evidence
    recorded, and the screen started at about 11:52Z.

- **11:52-12:02Z THE PRE-REGISTERED 2020-21 REPLICATION SCREEN: decision STOP.**
  - Inputs: the 2020-24 image `sbcp_13c5a61d`, the released bundle, split 16, the pre-registration `316fca9c…` and
    the addendum `1a95ab2e…`. 150 of 150 runs were counted: 0 failed, 0 infrastructure reruns, 0 undefined t.
  - **7 components replicated**, passing all six tests on 2020-21 entries: window t at least 1.0, positive at 1.5x,
    each year t above -0.5, beats its placebo in 2020 and 2021, positive with March 2020 removed, natural twin run:
    - R (index reversal, liquidity provision), 6 of 25:
      - `sweep-rebound-bm-long-call-p2` (t 1.98);
      - the rebound sweep finalists `rebound_patient_broad_p1#8` (1.85), `rebound_patient_broad_p2#8` (1.61),
        `rebound_exec_p1#14` (1.60) and `rebound_exec_p2#14` (1.59);
      - `index-laggard-catchup-call` (1.25).
    - T (trend), 1 of 6: `sweep-bm-trend-long-option-on-spxw-3` (1.62).
  - **No replicator in any other class:** E 0/2, O 0/1, M 0/1, C 0/1, L 0/1, F 0/1.
  - Inventory mean t is 0.19 (noise predicted about -0.4); the mean of the class means is -0.38.
  - **Decision: STOP.** The rule needs at least 6 replicators across at least 3 mechanism classes; these span two. No
    book is built, and nothing from this screen goes to Validation.
    - Before the run, the alignment step flagged slot 13's class tag as doubtful (relative momentum tagged R).
      Re-tagging it after seeing results would flip the decision, and the frozen tag stands.
  - **What it means.**
    - The index liquidity-provision rebound is real: several independent implementations replicate on unseen years,
      beat their placebos in both years, and survive removing the March 2020 crash.
    - Its strength, a window t of about 1.6-2.0 over two years (roughly 1.1-1.4 a year), is well below what D2 needs
      for good odds: a per-year t near 2.5-3 in 2025 alone.
    - That is consistent with its 2025 validation t of 0.19, one draw from a modest true edge.
    - Everything outside the rebound (and one trend variant) was selection noise.

- **13:30-14:07Z The first session: a funding-read bug blocked every real entry; fixed mid-session with the owner's
  exception to D8.**
  - At the open, the live path reported "a stop's line is crossed on a reading whose deposits are not read yet: the
    account's funding history has not been read", which blocks every real entry, the D3 calibration included.
  - The ledger showed every funding read failing: `alpaca activities: HTTP 422 invalid activity type: WIRE`.
    `league/live/step.py` queried `ltcm.performance.ALPACA_FUNDING`, which includes WIRE, a classifier entry that
    Alpaca's activities endpoint refuses as a filter.
  - A read-only probe on the real account found CSD, CSW, JNLC, JNLS, ACATC, ACATS and CSR fine and only WIRE refused.
    The owner's deposit is a CSD, executed, created Sunday 13:30Z. The option-event types OPASN, OPEXC and OPEXP are
    valid (OPXRC is refused but unused), with 0 option-event alerts today.
  - **PR #405:**
    - the query leaves out `UNQUERYABLE_FUNDING = {WIRE}`; the classifier is unchanged;
    - the test fake now refuses WIRE as Alpaca does, and a new test fails with the old query;
    - 457 live, options and shadow tests pass, CI is green, and the money digest is unchanged.
  - Adversarial review: SHIP. No real flow is hidden (wires post as CSD/CSW). A simulation of the House's actual stop
    state unblocks with nothing latched (profit -$0.02, day P&L $0).
  - The owner chose an exception to the deploy freeze. It was deployed at 14:03Z (release
    `20260928T140336Z-766c07a9691b`, main `2e51ea71`, backup `pre-r5b`).
  - At 14:06:41Z `blocked: None`: the deposit is read as a funding flow, and neither the daily nor the drawdown stop
    latched. The 10:00 ET calibration slot (window to 14:45Z) can still fire.
  - The paper proof passed at 13:35Z: a multi-leg SPY 768/769 call vertical filled at 0.49.
- **14:10Z Agenda v6** (live, no deploy): "what is left" now points at breadth for the one replicated mechanism, the
  liquidity-provision reversal on roots uncorrelated with SPY (TLT, GLD, SLV, SMH, liquid names), and at trend as a
  diversifier. An operator breadth sweep is running.

- **14:08-14:10Z THE FIRST REAL-MONEY OPTIONS ROUND TRIP (D3 calibration, `house:calibration`, never evidence for a
  family).** The 10:00 ET slot fired at 14:08Z, after the unblock: a 1-lot SPY $1-wide near-money call vertical, 1 DTE.
  - **Open:** limit at the package mid, filled at the mid (0 ticks from the mid) after 173 s.
  - **Close:** limit at the mid, filled at the mid (0 ticks) in 6.6 s.
  - **Result:** -$2.20 including $0.20 of fees. The package mid moved 2 cents against it in about 3 minutes, and no
    spread was paid. The day's possible loss was bounded at $49.20 (D3 $50).
  - It is a single sample per cell. `fillcheck.py --replay` compares it with the Gym's hazard for that cell after
    Tuesday's nightly tape. Nothing is fitted on it.

- **14:20Z Exploratory, not a route to Validation: how the replicators combine.** Source: the screen's own 2020-24 runs
  at 1.0x.
  - The five rebound implementations are one bet: pairwise daily P&L correlation 0.79-1.00.
  - Trend and laggard-catchup are independent of the rebound (-0.05 to -0.08) and correlate 0.45 with each other.
  - An equal-risk book of six of the seven replicators has a per-year t of 1.27 / 1.43 / 2.09 / 1.76 / 0.31
    (2020-2024); the worst year is 2024, when the rebound fades in a quiet bull. `sweep-rebound-bm-long-call-p2` was
    missing from the book because of a program-name match error in the script; its window t is 1.98.
  - At the Gym's costs, the known edges combined stay short of what D2 needs (a per-year t near 2.5-3 in 2025 alone).
  - The levers left:
    - more independent edges (breadth, running now);
    - cheaper real execution, if the calibration round trips keep filling at the mid (1 of 1 today, both legs);
    - 5-year Train selection (the flip after tonight's close).

- **14:20-14:40Z Breadth sweep (operator, Train only): the replicated reversal does not generalise across assets.**
  - Setup: the replicated rebound templates, signal and exits unchanged, on TLT, GLD, SLV, SMH, TSLA, NVDA and AAPL.
    12 rows a root at 1.0x and 1.5x, both placebos, and daily P&L correlation against the SPY finalists.
  - No root meets the bar (positive at 1.5x every Train year, beats its placebo, correlation under 0.5 with SPY):
    - TLT is flat and negative in 2024;
    - on GLD and SLV the signal picks worse days than its own placebo;
    - SMH tracks SPY (0.40, and 0.60 on days both hold) and fails 2024;
    - TSLA and NVDA are negative at 1.5x in 2022;
    - AAPL is a lone near-miss (1.5x t 0.25 / 1.18 / 0.29).
  - Pooling the best roots into one family gains nothing. A per-year t near 2.5-3 would need about five independent
    roots each as strong as SPY after costs, and none was found.
  - Agenda v7 marks this breadth as tested, so the architect does not re-propose it.
  - The sweep found a Gym defect: a single-name position held across a stock split cannot be closed and settles as
    worthless (TSLA 2022-08-25, SMH 2023-05-05, NVDA 2024-06-10). No top row was affected. The fix is being built for
    the after-close release.

### Sprint scoreboard, T0 + 53 h (11:30Z Sept 28)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 42 alive, 373 retired; 60 born and 50 retired in 2 h |
| 2 | Throughput | 793 cycles/h, median 8 s; pool 1 busy, 8 ready; `gym.run_timeout_seconds` 1,500 since 10:05Z (batches of heavier single-name programs were timing out at 900 s) |
| 3 | Search | 59,828 trials, 237,878 program-years. Closest in Validation 2025: `finite-sell-program-exhaustion` and `supplier-demand-cascade-put-on-spy`, 5/8 each (fail DSR, mean, t) |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Readiness | Pre-open 9/9 at 10:00Z. The 2020-21 fetch finishes stage 10 about now; then quality checks, the 2020-24 sweep-only image, and the pre-registered screen |
| 6 | Money | equity $1,481.63; options buying power $481.60; 0 orders |
| 7 | Compute | Sail $96.52 (about $4.2/h; the $32 line around 02:30Z Tuesday). Claude $52.90 of $100. OpenAI $625.73 + $11.37 in flight of $707 |

- **15:50Z Operator decisions under the owner's delegation (Sept 28: "decide yourself how best to proceed").**
  Guardrails kept: D2, the money table, money movement and secrets.
  - `researcher.top_families` 1 to 6: the six highest-weight families research on V4-Pro instead of Flash.
  - A strong-model hypothesis tournament runs on the idle Gym capacity:
    - six new mechanisms outside the refuted list and graveyard, each with kill tests written before any run;
    - swept on the sealed 2020-24 image over Train 2020-2024 at split 16, with placebos;
    - survivors are founded into the swarm, and their predicted 2025 t is written before Validation.
  - PR #407, the calibration expansion, is ready for tonight's release:
    - six hourly slots and IWM within D3's unchanged $50 bound;
    - a 25-minute patient `mid25` cell at 12:00 and 14:00 ET;
    - $200 of the day cap left for families, a legs cap, and yielding to any family order on the same contracts;
    - interrupted attempts never count as samples.
    Adding IWM and the extra slots is an operator decision inside D3's dollar bound. The review also found that
    `fillcheck.py`'s Gym replay had been silently broken, falling back to a table estimate; it is fixed.

- **16:06-16:13Z THE SWARM IS ON 5-YEAR TRAIN (2020-2024).** An operator image adoption, not a release: it runs on
  R5's code. The pre-registered screen's verdict was written first, as the plan requires.
  - Steps: `swarm.stop`, then a clean exit at 16:12Z. One `swarm.json` edit (backup `swarm.json.before-train2020`):
    - `gym.image_checkpoint` `sbcp_13c5a61d` (the sealed 2020-24 image);
    - `gym.train_from` "2020-01-02";
    - the explicit run timeout removed, so split 16 and 1,500 s derive from the span.
    The swarm restarted at 16:13Z.
  - The migration: objective `worst-train-year-v1@2020-01-02`, 38 families migrated, 0 failed. Bests are empty until
    each family's next 5-year run. The idle and dormancy counts restart, so the flip retires no one.
  - Why now:
    - it rejects bull-market drift and selection noise better;
    - 2020 (crash and rebound) and 2021 (quiet bull) join 2022-24;
    - worst-year scoring over five regimes demands robustness.
  - Single-name families are scored only on the years their roots have data (2022-24).
  - The live trading process is untouched, and the gate image (Validation and holdout) is unchanged.

- **15:50-17:05Z Strong-model hypothesis tournament on 5-year Train: 0 of 6 pass.**
  - Six new mechanisms, none in the refuted list or the graveyard, each with kill tests written before any run.
    Proposals `scratch/tourney/proposals.json` sha256 0b8762f1…
  - They were swept on the sealed 2020-24 image (split 16, 1,258 days).
  - All six failed K0, the ceiling with every fill at the mid:
    - expiry-exercise inventory gap: worst year -2.03;
    - charm flow overnight: -1.11;
    - charm flow on expiry sessions: -0.78;
    - expiry concession reversal: -1.24;
    - cross-root hedging pressure: -0.17, 40 trades in 5 years;
    - scheduled-event vanna: -0.73.
  - Several lost to their own placebos. The always-long drift placebo beat the charm signal, and the next-expiry
    placebo beat exercise inventory.
  - 44 trials were used; the deflated Sharpe's ledger is about 62,044. All 10 boxes were terminated.
  - Lessons, now agenda v8:
    - dealer-positioning and open-interest signals on the index ETFs carry no direction beyond drift;
    - a one-day $1-wide vertical costs 7-14% of its max loss per round trip at honest costs, so a mechanism needs a
      large per-trade edge;
    - screen at the mid first, and check the trade count before any box.

### Sprint scoreboard, T0 + 57 h (15:30Z Sept 28, in session)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 43 alive, 503 retired; 58 born and 67 retired in 2 h (agendas v6 and v7) |
| 2 | Throughput | 763 cycles/h, median 12 s; 3 cycle errors (2 Gym exec failures, 3 provider 502s) |
| 3 | Search | 61,976 trials, 261,661 program-years. **Closest ever in Validation 2025:** `second-session-assimilation-call`, 7/8, failing only the deflated Sharpe (0.0): t 2.22, 4/4 quarters, positive at 1.5x. It is a long-call program on five high-momentum names with 2,358 trades whose P&L comes from a few very large days; the deflated Sharpe exists to refuse that fat-tailed profile. Runner-up `confirmed-round-level-release-call` 6/8 (t 1.40, deflated Sharpe 0.945) |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Money | Equity $1,479.44 (calibration round trip -$2.20 incl. fees; its legs filled at the mid). Options buying power $479.41. The live path has been unblocked since 14:06Z (#405) |
| 6 | Readiness | For after the close, built and in review: #404 marking, #406 splits (public split table, a no-look-ahead fix in progress), calibration expansion (six slots, IWM, a 25-min patient cell, the same $50 bound), site positions ledger (House feed and site section, reconciling exactly to Profit). The 5-year Train flip follows |
| 7 | Compute | Sail $86.33 (about $4/h; the $32 line around 05:00Z Tuesday without a top-up). Claude $59.69 of $100. OpenAI $630.28 + $11.35 in flight of $707 |

- **17:30-18:40Z Tournament round 2 (with round 1's lessons as rules): 0 of 6 pass.**
  - Six mechanisms, kill tests written first, on the sealed 2020-24 image:
    - the pre-release uncertainty premium;
    - the buyback-window reopening;
    - a volatility-state autocorrelation switch;
    - a jump-composition reversal;
    - diffusive-move continuation;
    - intermediary-capacity premium.
  - The release premium stopped at its outcome-blind precondition: 2020-21 chains priced no release kink. The other
    five failed K0 at the mid; the best worst-year t was 0.07 (diffusive continuation, beaten by drift in 2020 and
    2024). 60 runs; the deflated Sharpe's ledger is about 62,104. All 10 boxes were terminated.
  - The judge's conclusions:
    - daily index-ETF direction is used up with the Gym's information set: 12 strong-model mechanisms over two rounds,
      none reached a worst-year t of 1.5 even at zero cost;
    - the cost gap is about 5x, and multi-day holds do not close it, because legs past 7 DTE fill at the natural;
    - better real fills cannot rescue these, since every one failed at the mid;
    - the only 2025 near-passes are single-name convex programs, which the deflated Sharpe refuses as fat-tailed.
  - Agenda v9 (live): daily index direction is refuted as a class, and idiosyncratic single-name drivers with large
    per-trade moves are the priority.

- **18:35-18:50Z Order-flow screen (new information the programs never had): NOT.**
  - Pre-registered at 18:40:10Z (PREREG sha256 `350fe16c…`) before any flow feature was computed.
  - Signed option volume (buyer versus seller initiated, from the Gym's trade-print samples: 151 days per root,
    2022-24, 0-7 DTE, 20 strikes an expiry) against next-day and next-5-day returns. Controls: same-day return,
    5-day drift, absolute return, plus a within-year shuffle placebo.
  - 24 tests. The largest incremental t was 1.11 (ETF family) and 1.10 (S&P family) against a bar of 2 with the same
    sign every year; the smallest placebo p was 0.28.
  - A signal of the size D2 needs would have shown here. Smaller, literature-sized index effects remain possible but
    could not carry a family through D2.
  - One sealed box, terminated.

### Sprint scoreboard, T0 + 59 h (17:31Z Sept 28, in session)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 31 alive, 551 retired; 36 born and 48 retired in 2 h (5-year Train since 16:13Z; agenda v8) |
| 2 | Throughput | 663 cycles/h, median 10 s; pool 3 busy, 3 ready; 1 cycle error |
| 3 | Search | 62,557 trials, 269,365 program-years. Closest in Validation 2025: `cross-sector-morning-beta-lag` and `hedge-substitution-metal-call`, 4/8 each. Tournament round 1: 0/6. Round 2 and the real-fill recalibration protocol are running |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Real fills (D3) | 2 round trips. Of 4 filled orders, 3 filled at the mid (opens in 173 s and 19 s, a close in 7 s) and 1 at one tick worse (the QQQ close, after the mid close ran 5 min unfilled) |
| 6 | Money | Equity $1,475.27: -$6.36 across the two calibration trips (market moves plus fees). Options buying power $475.24. 0 family orders (no family eligible) |
| 7 | Compute | Sail $83.09 (about $3.7/h). Claude $61.79 of $100. OpenAI $634.41 + $13.33 in flight of $707 |

### Sprint scoreboard, T0 + 61 h (19:31Z Sept 28, the session's last half hour)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 45 alive, 597 retired; 60 born and 46 retired in 2 h (5-year Train, agenda v9) |
| 2 | Throughput | 804 cycles/h, median 20 s; 22 provider 503s and 6 502s (the model provider) |
| 3 | Search | 63,858 trials, 288,652 program-years. Closest in Validation 2025: three families at 4/8 (`hedge-substitution-metal-call`, `monthly-reporting-stock-leader-call`, `turn-loser-rebound-call`) |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Real fills (D3) | 3 round trips (SPY, QQQ, SPY). Of 6 filled orders, 5 were at the mid and 1 one tick worse. Opens 3/3 at the mid; closes 2/3 at the mid |
| 6 | Money | Equity $1,473.11: -$8.52 across the three calibration trips (market moves plus broker fees). Options buying power $473.08. 0 family orders (no family eligible) |
| 7 | Compute | Sail $77.10 (about $3.5/h). Claude $67.17 of $100 (about $3.3/h since the architect's 32k answers). OpenAI $636.07 + $11.40 in flight of $707 |


- **20:07Z R6 deployed after the close (release `20260928T200729Z-5bdeb710c88b`, main `2981566d`, PR #409): PROMOTED
  20:08:12Z.**
  - Contents:
    - #404, payoff-range fills and marks;
    - #406, stock splits from a public table;
    - #407, D3 calibration expansion (six hourly slots, SPY/QQQ/IWM, a 25-minute patient mid cell, the same $50 bound);
    - #408, the positions ledger, with Profit now including calibration and the broker's actual fees.
  - The money digest is unchanged (`ad9bd54c`), and so is the grant.
  - preopen: 8/9. The one fail is compute: the Sail projection runs out at Tuesday's close without a top-up.
  - The site's positions table (personal-site #15) is live under the chart:
    - three closed calibration round trips: SPY -$2.12, QQQ -$4.12, SPY -$2.12;
    - other: crypto fees -$0.08;
    - unreconciled $0.00;
    - the rows plus other add to -$8.44, exactly the Profit at the top.

- **Monday's close, the post-mortem (D3 real fills, `fillcheck.py`; the Gym replay waits for Tuesday's 06:00Z tape).**
  - The three round trips were 1-lot $1-wide call verticals, 0-1 DTE.
  - Resting passive orders: 5 of 6 filled at the mid (83%, 95% CI 44-97%). The hazard table predicts 78% (exact
    p = 1: consistent).
    - Opens: 3/3 at the mid, median 30 s.
    - Closes: 2/3 at the mid. The third rested 300 s unfilled, then closed at mid-1, one tick worse, in 2 s.
  - Real fills averaged +0.00 ticks against the mid, and the Gym would have charged the same.
  - Six attempts in one session are far too few to recalibrate anything. The patient 25-minute cell starts Tuesday.
  - The money: -$8.44 of trading P&L (market moves on the verticals plus the broker's fees). No family order: none is
    eligible.
  - The day's Net: about -$8.44 real, minus about $117 of compute (Sail about $58, Claude about $33, OpenAI about
    $26), about -$125.

- **20:30Z Decision: a pre-registered live test of the one replicated edge, at tuition size (the owner said "proceed
  as you see best fit" to the recommendation).**
  - What: the rebound finalist that replicated in the pre-registered 2020-21 screen, run unchanged as a House program
    in the pattern of D3 calibration:
    - its own family and its own records;
    - never evidence, never a promotion, and D2 unchanged.
  - The bounds, in code and fail-closed:
    - 1 lot, and at most $100 max loss a structure;
    - at most 3 open, and at most $300 of realized loss plus open max loss;
    - a permanent stop at $150 realized loss (exits still run);
    - it ends at 20 trading days or 30 closed round trips.
  - Why: the verifier says no family is ready, and the evidence says the rebound is about half the strength D2 needs.
    What remains unmeasured is how its actual trades fill and pay in the real market: 1-3 day holds, in-the-money
    legs, and the 15:35 ET decision. Calibration round trips cannot measure that. Thirty trades cannot prove
    profitability, and the pre-registration says so. What they can show is whether real execution matches the Gym on
    the one mechanism that replicated.
  - Status: built and adversarially reviewed as money code. It deploys only outside the 13:25-20:05Z freeze.


- **20:34-20:52Z News-data ceiling study: NOT (pre-registered, sha256 `75523905…`, locked before any news was fetched).**
  - The question: would pre-open headline data give the Gym's 14 single names a daily signal worth building in?
  - Reachability: the gateway does not sign Alpaca's news route (403). The data box holds only the options-data key.
    So no news was fetched and the signal tests did not run. Opening the route would take one read-only allowlist
    line plus an owner gateway deploy.
  - The finding that does not need news is the cost hurdle. It covers 1-lot adjacent-strike verticals filled at the
    natural, on 14 names, 2022-24, 753 sessions each:
    - a round trip costs about 63% of what perfect foresight of the session's direction would earn, so a direction
      signal would need about an 81% hit rate on the median name to break even;
    - an at-the-money straddle's hurdle is 0.25;
    - the index roots' hurdle is 0.29-0.37.
  - Daily direction on names is closed by cost, whatever the information. A news volatility signal would also have to
    beat the opening implied move. The route stays unopened unless a volatility mechanism earns it.


### Sprint scoreboard, T0 + 63 h (21:22Z Sept 28, after the close)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 48 alive, 642 retired; 48 born and 51 retired in 2 h (5-year Train; agenda v10 since 21:05Z) |
| 2 | Throughput | 741 cycles/h, median 11 s; 6 provider 502s |
| 3 | Search | 64,794 trials, 301,752 program-years. Closest in Validation 2025: two single-name long-call families at 5/8 (`corroborated-demand-call`, failing the deflated Sharpe, t and trade count; `focal-level-release-call`, failing the deflated Sharpe, quarters and t). Tournament round 3 (single-name convexity) is running |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Real fills (D3) | 3 round trips today (see the post-mortem above); none after the close |
| 6 | Money | Equity $1,473.11; Profit -$8.44, all of it calibration and fees. Options buying power $473.08 (the deposit is not in it yet) |
| 7 | Compute | Sail $71.38; the guard's burn estimate is $77/day, and its $32 line (where it brakes research to keep the House running) comes Tuesday morning without a top-up. Claude $68.85 of $100. OpenAI $639.69 + $11.40 in flight of $707. The swarm spent $15.01 in 2 h |


- **21:35-22:00Z New-roots structural-premium screen: 0 of 25 rows pass (pre-registered, sha256 `e1b6e279…`).**
  - The question: do underlyings the Gym does not hold carry a structural premium strong enough to justify fetching
    their option history?
  - Seven hypotheses with a concrete payer, 25 rows, on 19 roots: SPY, VXX, VIXM, UVXY, SVXY, TLT, LQD, HYG, the
    nine sector ETFs, KRE and XBI.
    - H1-H3: volatility-ETP roll-down with contango, trend and variance-premium gates.
    - H4-H5: month-end rebalancing, SPY against TLT, and bond duration extension.
    - H6: sector residual reversal.
    - H7: credit-ETF dips.
  - Daily underlying returns at zero cost. Train 2020-24 only; no 2025-26 row was loaded.
  - The bar: a t of 2.5 in every year, the placebo beaten every year, and Holm across the 25 rows.
  - Results:
    - Best worst-year t: 0.38 (month-end TLT). Best pooled t: 1.92 (month-end LQD).
    - Short-volatility ETP carry peaks at t of about 1.8 in single years and is flat or negative in 2020, 2022 and
      2024. The spot VIX term-structure gate adds almost nothing over always-short.
    - Sector residuals and LQD dips continue rather than revert, and the flipped signs also fail the per-year bar.
  - An independent verifier rebuilt all 25 rows with its own code and matched every t to within 0.015. No
    look-ahead, split or window errors.
  - The verdict: no new root earns an option-data fetch.
  - The lesson: the binding constraint is year-to-year stability, not pooled significance. Across these rows, round
    3's predecessors and about 65,000 swarm trials, nothing reaches a per-year t of 2.5 even at zero cost.


- **22:20Z D5: the grant re-ratified at the deposited capital.**
  - The deposit reached options buying power, $1,473.08 (it read $473.08 at 21:22Z).
  - `live_trading.py --ratify` on the House: grant `options-swarm-20260928`, 1 ratification.
    - Capital: $481.63 → $1,473.11, the lower of equity and the owner's $5,500 ceiling.
    - Max agents: 4 → 14.
    - The money digest is unchanged (`ad9bd54c`), and the grant is active.
  - Nothing was open at the time: 0 real positions and 0 working orders.
  - preopen: 8/9.
    - Sizing equity is $1,473.11: a Probe cap of $73.65 (5%), the one-contract floor $100, a gateway order cap of
      $368.27.
    - The one fail is the Sail projection (the owner is topping up).

### Sprint scoreboard, T0 + 64 h (22:20Z Sept 28)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 52 alive, 674 retired; 60 born and 54 retired in 2 h (agenda v10) |
| 2 | Throughput | 721 cycles/h, median 52 s (tournament and research boxes share the pool); 1 provider 502, 1 missing tool call |
| 3 | Search | 65,266 trials, 308,662 program-years. Closest in Validation 2025: `corroborated-demand-call` (single-name long call) at 6/8, failing the deflated Sharpe and t. Round 3 (six single-name convexity and volatility mechanisms) and the replicator book are running on sealed Train-only boxes |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Real fills (D3) | none since the close |
| 6 | Money | Equity $1,473.11; options buying power $1,473.08; grant capital $1,473.11 (re-ratified 22:20Z); 0 positions, 0 orders |
| 7 | Compute | Sail $68.73 (the guard's burn is $75/day; the owner is topping up). Claude $71.05 of $100. OpenAI $641.99 + $11.40 in flight of $707. The swarm spent $14.66 in 2 h |


- **21:00-22:45Z Tournament round 3 (single-name convexity and volatility, trend in cheap convexity): 0 of 6 pass.**
  - Each mechanism was pre-registered with its kill tests and cost hurdle before any run (proposals sha256
    `72f4a673…`). All ran on sealed 2020-24 boxes, Train 2022-24, and every box was terminated.
  - The six:
    - bellwether earnings-print variance spilling to peers;
    - persistence of unresolved-print variance;
    - trend held in cheap-strike convexity;
    - an idiosyncratic-variance discount;
    - lottery-demand cheap puts;
    - displayed-depth informed demand.
  - All six failed K0, the ceiling at the mid. Worst-year mid t per mechanism: -0.18 (bellwether spillover), 0.65
    (unresolved-print persistence), -0.83, -0.28, -1.46, -0.79. (Corrected 03:40Z: the first two were swapped.) Only the bellwether spillover's mid edge beat the cost gap (1.59x), and all of that edge was 2024.
  - All six were lottery-shaped even at zero cost: each year went negative after dropping its five best trades,
    which D2's deflated Sharpe refuses.
  - Event mechanisms produce only 10-35 structures a year under the $95 cap. By 2024 the cap makes most names
    unaffordable (AMD, TSM, MU and GOOGL fit in only 4-22% of sessions).
  - The judge's binding conclusions:
    - single-name long premium inside the envelope is refuted as a class;
    - no round 4 in single names or daily index direction;
    - the best remaining move is the book of the replicated mechanisms, at about 3-5% to pass Validation and about
      2% to pass Validation and the holdout.


- **22:39-23:09Z The real-fill recalibration protocol is frozen, and the owner has committed to its rule.**
  - PROTOCOL-v2 is frozen: sha256 `10f78877…`, amending v1 `7882bfa8…`.
    - Real calibration fills may move the Gym's patient-fill table only through a pre-registered, held-out test:
      even sessions fit, odd sessions test, at most four looks.
    - Adoption needs significance with sessions as the unit, no root or patient cell getting worse, and the Gym
      staying no more optimistic than real fills on price.
    - The first test session is Tuesday's.
  - The tool `recal.py` (private) is pinned: pin 2 at 23:04Z, before any test session, self-test 32/32.
  - `fillcheck.py`'s Gym replay broke on R6's engine (a close's payoff bounds). It is patched, and its self-test now
    replays 76 of 76 synthetic attempts through the House engine, closes included.
  - Power study, on synthetic data: at 30 samples a cell only a 2x error in the fill rate is caught.
    - The owner raised `live.calibration_samples` to 100: the same D3 bound of $50 a day, about months of sampling,
      catching a 1.5x error about half the time.
    - False adoption stays at 0-1%.
  - The owner committed in advance to adopt on a passing look without first seeing any strategy's results under the
    new table (`recal/owner-commitment.txt`, sha256 `befe90dc…`).
  - What a higher fill rate would mean for the rebound: the audit's sensitivity already showed no finalist becomes
    robustly positive. The extra fills are adversely selected, and every real fill so far came exactly at its limit,
    the Gym's own price.


- **22:34-23:30Z The replicator book (rebound + trend + laggard as one family): NO, it failed Train. Nothing founded,
  no Validation look spent.**
  - Pre-registered first (PREREG sha256 `a2650390…`).
    - Rebound: `rebound_patient_broad_p1#8`, the highest-window-t implementation that fits $95 unchanged.
    - Laggard and trend, weighted equal-risk.
    - One slot each, 1 lot, and each structure within its budget.
  - The build: each frozen component runs byte-for-byte inside one program and reproduces its native run trade for
    trade (R 279/279, L 224/224, T 405/405). The limits held in every run.
  - Train 2020-24 at 1.0x: 477 trades, +$2,456, t 2.19. At 1.5x: +$1,213, t 1.08. With natural-only fills: t 1.63.
    The placebo book lost $2,304. The kill tests:

| Test | Result | Numbers |
|---|---|---|
| K1, every year positive at 1.0x and 1.5x | FAIL | 2022 lost $54 at 1.0x and $544 at 1.5x |
| K2, beats the placebo every year | PASS | |
| K3, trade count | PASS | 76-107 trades a year |
| K4, no quarter above 40% | FAIL | 2023Q2 made 43.7% |
| K5, deflated Sharpe | PASS at N=1 (0.990) | 0.854 at N=5 |
| K6, the House's drift screen | FAIL | drift-adjusted alpha t -0.24: alpha -$329 against $2,785 of market drift |
| K7, clean runs | PASS | |

  - Two adversarial reviews (honesty and contamination; correctness) re-derived every number and hold the NO.
  - The lesson (now in agenda v12):
    - all three replicated mechanisms are bullish, so their "independence" from each other hid one shared bet on the
      2020-24 bull market;
    - components must pass the drift screen alone, balanced by side or conditioned on something the market's own
      return does not explain, and fit $95 natively. Under the cap, L and T had traded further-out strikes than the
      contracts that replicated.


- **23:38Z-00:07Z R7: the House live test and the 2020-21 splits, deployed; the grant re-ratified on the new money
  table (the owner approved the money-table change at 22:55Z).**
  - Contents: PR #410 (five 2020-21 splits in `events.SPLITS`; stale "never Profit" comments) and PR #412 (the House
    live test, one squashed commit after two adversarial money-code reviews; #411 closed unmerged).
  - Merged to main `6c2de074`. 599 money-path tests passed locally on the merged tree, and main's CI is green (3.11,
    3.14, gateway).
  - The money digest moved `ad9bd54c` → `a3e2aa7c` (full `4f4edaf5` → `fcf8d735`). The only change is the test's own
    six bounds in `options_money.house_test`; no family limit changed.
  - Backup `state/backups/pre-r7` (swarm, ledger, live, live-grant, calibration, swarm.json); `pre-r6` removed.
  - Release `20260928T235447Z-6005f971ffc5`, promoted 23:55:35Z. The grant was re-ratified at 23:56:41Z: active on
    `a3e2aa7c`, capital $1,473.11, 14 agents.
  - The frozen program is uploaded privately to `<state>/house-test/rebound-live/` (directory 700, files 600).
    `health.options_live.house_test.files` = verified, and the code, params and run hashes match the
    pre-registration.
  - The switch `live.house_test` stays off until the pre-registered analysis script is pinned.
  - preopen: 8/9 (the fail is the Sail projection; the owner is topping up).
  - The site's "House live test" label (personal-site #16) is deployed, version `dcd61fbc`. The positions table still
    reconciles: rows plus other = -$8.67 = Profit, which now includes more of the broker's posted fees.


- **00:16-00:22Z The House live test armed.**
  - Its analysis script was written and pinned before the switch (sha256 `a5eaf7a3…`, self-test 88/88; the House had
    no test rows).
  - The start fill model was kept privately (`3de9e2a6…`, `fm-c4a0c70c`).
  - `live.house_test` on at 00:17:28Z. By 00:22Z the House reported wanted "yes" and files "verified", and instance
    `house:rebound-live@0:h` was registered with the pre-registered run hash `0771b441`.
  - Its first possible decision is Tuesday's 15:35 ET. Expected pace from the Gym: about 3 trades in 20 sessions, so
    the verdict will rest mainly on fill behaviour, as pre-registered.

### Sprint scoreboard, T0 + 66 h (00:18Z Sept 29, R7 live)

| # | Metric | Value |
|---|---|---|
| 1 | Population | 40 alive, 722 retired; 36 born and 48 retired in 2 h (agenda v12 since 00:05Z) |
| 2 | Throughput | 559 cycles/h, median 11 s; 1 provider 503 |
| 3 | Search | 66,112 trials, 321,463 program-years. Closest in Validation 2025: `market-distraction-release-call` v11 (long calls on BABA, TSM, MU, MSFT and QQQ) at 7/8. It fails only t: 1.95 at 1.0x (1.88 at 1.5x), 158 trades on 65 days, traded-day skew 1.94. Next closest: `down-day-relative-strength-call` and `idiosyncratic-gap-confirmation-call` at 6/8. The drift-free component hunt is running |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Real fills (D3) | none since the close; calibration's target is 100 a cell from Tuesday |
| 6 | Money | Equity $1,473.11; Profit -$8.67; options buying power $1,473.08; grant capital $1,473.11 on `a3e2aa7c`; 0 positions, 0 orders |
| 7 | Compute | Sail $63.56 (the owner is topping up). Claude $73.93 of $100. OpenAI $643.08 + $11.40 in flight of $707. The swarm spent $10.44 in 2 h |


- **00:05-01:15Z Drift-free component hunt: 0 of 10 (the bar was fixed before any run, including the House's own
  drift screen).**
  - Ten intraday index components on SPY, QQQ and IWM, each balanced by side (about 50/50 calls and puts): opening
    drive continuation, small-cap lag, gap continuation into the afternoon, afternoon 0DTE gamma, intraday fear-spike
    relief, daily fear-jump fade, skew innovation, drive carried overnight, small-cap afternoon catch-up, and the
    closing reversal of the open.
  - Each was a $1-wide 0-3 DTE vertical within $95. Train 2020-24 on sealed boxes; all 21 boxes were terminated.
  - All ten failed C1 (year-stable t at the mid) and C5 (the drift screen alone).
    - The best at the mid was the opening drive: t 1.58, 2.11, 1.03, 0.34, 0.35. Its sign was a post-hoc inversion,
      and it was disclosed as one.
    - At 1.0x every component was negative pooled, with drift-adjusted alpha t between -2.62 and -14.93. (Corrected
      03:40Z: -1.87 was the opening drive's pooled 1.0x t, not an alpha t.)
  - The combiner re-derived every number from the raw runs (0 mismatches over 1,258 days) with the House's code:
    - drift was removed (charges of tens of dollars), but no alpha remained after costs;
    - round trips cost $4-7 against mid edges of -$0.9 to +$2.4 a trade;
    - even free execution gave no book a worst-year t above 0.44;
    - the components were nearly uncorrelated (median pairwise ρ 0.014).
  - Diversification is not the bottleneck; edge per trade is.
  - Agenda v13 at 01:20Z: intraday index timing as $1 verticals is refuted. A family must show a mid edge of at least
    $7 a trade (rare, large moves) or cheaper execution (single long options, 2 fills), while passing the drift
    screen alone.


### Sprint scoreboard, T0 + 68 h (02:18Z Sept 29), and a birth stall

| # | Metric | Value |
|---|---|---|
| 1 | Population | 12 alive (the floor), 750 retired; 0 born and 28 retired in 2 h |
| 2 | Throughput | 162 cycles/h, median 6 s; Gym runs fell from 300-670/h to 38 (01Z) and 12 (02Z) |
| 3 | Search | 66,423 trials, 325,060 program-years. Closest alive: three families at 3/8 |
| 4 | Evidence | Validation passes alive 0; holdout looks 2, passes 0 |
| 5 | Real fills (D3) | none overnight |
| 6 | Money | Equity $1,473.11; 0 positions, 0 orders |
| 7 | Compute | Sail $60.72. Claude $75.87 of $100. OpenAI $644.33 + $11.40 in flight of $707. The swarm spent $6.64 in 2 h |

- **What happened:**
  - The families' own researchers judged their mechanisms refuted and held rather than grind parameters. In one's
    words: "any run now would be false-positive parameter grinding on a dead idea, wasting lineage trials".
  - The idle rule (12 cycles without a new Gym evaluation) then retired them. That included
    `market-distraction-release-call` (7/8 in Validation at 23:29Z, t 1.95), whose researcher declined to tune on
    Validation feedback. That is the honest choice, and the operator did not intervene.
  - At the same time the architect proposed 0 families in four calls. Agendas v12 and v13 demanded proof at birth (a
    mid edge of at least $7 a trade, passing the drift screen) that no proposer can have before the Gym tests it.
- **The fix at 02:30Z, agenda v14** (steering only; D2 and every kill test unchanged):
  - "always propose; the Gym measures, you do not need proof at birth";
  - three open directions, on SPY/QQQ/IWM:
    - single long options, 2 fills, held 2-10 sessions and taken on both sides by rule, triggered by rare
      large-move states;
    - drift-neutral cross-root pairs;
    - long call plus long put only where implied vol sits below forecast realized vol.


- **03:35Z The operator's experiments are now in the swarm's memory.**
  - 44 graveyard lessons were compiled from the private results (every number re-read from source), reviewed
    adversarially as public-safe and accurate, and inserted.
  - They cover tournament rounds 1-3, the drift-free hunt, the new-roots screen, the book, news, order flow and the
    2020-21 screen's non-replicating classes.
  - Each row has an `op-` id, is dated when its experiment concluded, and gives the numbers plus a "do not re-propose
    unless…" line.
  - The graveyard went from 762 to 806 rows; a backup exists; all 44 read back identical. Researcher searches find
    them first (for example "buyback", "VIX roll", "news direction").
  - Found in review: the graveyard search counts raw word occurrences, so long lessons crowd out short ones. Replaying
    the last 150 births, the new lessons won 0 of 450 top-3 slots. A length-fair ranking is being built as a small
    research-side release.
  - The architect now runs every 900 s (was 1,800).


- **03:45-04:00Z The owner: "remove any limits that would inhibit this goal … take every bold swing". What changed,
  and what did not.**
  - Research throttles lifted, up to funded money:
    - researcher Sail pace $4.50 → $12/h, model pace $2.25 → $5/h;
    - Gym boxes 10 → 16;
    - population start 72 → 96 (the ceiling);
    - the architect 12 families every 30 min → 24 every 10 min;
    - the strong research profile for the top 12 families (was 6).
    The Sail guard's $32 line stays: it keeps the House alive with real positions open.
  - The two nearest Validation misses were revived as lineage continuations (`revive.py`, origin "operator-revive"):
    `market-distraction-release-call-r` (its parent was 7/8, t 1.95) and `down-day-relative-strength-call-r` (6/8).
    - They inherit their lineage's trials and holdout looks, so the deflated Sharpe counts every version and the
      sealed holdout judges anything that clears.
    - The selection used Validation check counts, disclosed here.
  - The width-lever experiment is running (pre-registered): frozen mechanisms with edge at the mid are re-run at $1-5
    widths to test whether a larger envelope turns cost-bound edges net-positive. Any money-table change it supports
    goes to the owner.
  - Unchanged: D2, the sealed holdout, no forced trades, the money table.


- **03:40-04:00Z The owner: use Claude Sonnet 5.5 throughout; from now on only Sail and Claude are topped up.**
  - Model evidence behind it:
    - architect calls since Sept 26 20:00Z, per family born: GPT-6 Astra about 4.7¢, 17% reached Validation, 8% positive
      Train (359 births); Claude Opus 5.5 about 4.6¢, 16% and 10% (193 births). Equal quality per dollar; an earlier
      "Astra reaches higher Validation scores" was a sample-size artifact and was retracted.
    - Claude Sonnet 5.5 (`claude-sonnet-5-5`, released Sept 28) costs $2/$10 per million tokens, half of Opus 5.5.
  - Done:
    - the architect is Claude-only (`architect.openai_model` null; Sail models as the fallback);
    - `claude.model` is Sonnet 5 until the House knows Sonnet 5.5;
    - diagnostician: $60 a day, 6 a round, every 3 hours per family.
  - PR #415 (Sonnet 5.5 in the gateway's price table and the House's hold ceilings) was merged, main `707077ec`. The
    review said SHIP; the US-region 1.1x risk does not apply (all 338 calls were global).
  - The gateway was deployed at 03:59Z (version `7eaede72`) and lists `claude-sonnet-5-5`. The funded Claude cap is
    unchanged ($100).
  - Being built for R8/R9:
    - Claude on the rewrite and review roles, with per-role daily lines;
    - the top families' research cycles on Sonnet 5.5 (tool use through the gateway, fallback to Sail);
    - the architect reading the full graveyard (1M context, cached);
    - a strategist that rewrites the agenda's "where to look" section from all evidence, under a locked operator
      preamble;
    - the length-fair graveyard search.
  - The docs will be reconciled before the release is called done.


- **03:44-04:20Z The width lever (pre-registered, sha256 `c3813ae6…`): 0 of 32 mechanism x width rows pass. No
  money-table request follows.**
  - The question: would a larger envelope turn cost-bound edges net-positive?
  - Eight frozen mechanisms were re-run at $1, $2, $3 and $5 widths (guards $95-480), only the width changed, on Train
    2020-24: the two rebounds, the opening drive, small-cap lag, skew innovation, diffusive continuation, a
    volatility-state trade, and reversal plus calm carry.
  - Cost did behave as hypothesized. A round trip costs about $5-6 at every width, so from $1 to $5 the cost per $1 of
    mid edge fell about 4.5x, and 6 of 8 mechanisms turn net-positive at 1.0x at $5.
  - But width fixes cost, not the ceiling.
    - For the six cost-bound mechanisms, the mid edge stays about 4% of max loss at every width.
    - The $5 residual is market drift (drift-adjusted t <= 0.40), and it is concentrated in single quarters (58-137%
      of P&L).
  - The rebounds were never cost-bound. They make $8.57-9.15 a structure at $1 and 1.0x, and fail on weak years
    (2020, 2024).
    - Width scales every year alike: REB14's 2024 t is 0.46-0.67 at every width.
    - The best row, REB14 at $3, has a pooled t of 3.48 but fails the every-year bar, drop-5, and the 40 structures a
      year.
  - The judge recomputed all 96 runs from the raw batches (0 mismatches). All 8 boxes were terminated. Holm rejects
    nothing.
  - Next: the rebound's year-to-year stability as a new, separately pre-registered hypothesis.

## Report

# Forward first — September 25, 2026

Execution record for the owner's goal of Sept 25, 2026: execute
[the forward-first plan](../goals/LTCM_FORWARD_FIRST.md) autonomously, with no deadline, outside US
market hours, until its Done list holds. The Sept 25 gap review (memory note
`ltcm-gap-review-2026-09-25`) is the baseline.

## The clock

- **T0:** 2026-09-25T04:22:57Z (the session's first `date -u` after reading the plan).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Progress notes:** a scoreboard reading and a short state note every four hours from T0
  (08:23Z, 12:23Z, 16:23Z, ... Sept 25), in "Progress notes" below.
- **US sessions:** Friday Sept 25 13:30-20:00Z (no deploy 13:25-20:05Z), then Monday Sept 28.
  The weekend has no stock or options session; Kalshi and Alpaca crypto trade throughout.

## The owner's message (Sept 25, 2026, at T0)

- The /goal text is the plan's last section with the funding and owner-step lines left as the
  template's placeholders. At 04:25Z the owner added: "you can ignore the things that require things
  from me like api keys. we can do those later i cant provide those now."
- **Read as:** no owner-stated funding figure, so "funded" means the balances read from the
  providers at T0 (below) and no cap is raised; no Sail top-up and no October `FRONTIER_MONTH_USD`
  this run; no Sail checkpoint ticket, no Odds API key, no EIA key. No notification is sent for them
  (the owner said so in the session); the exact commands are in the report.
- Authority: the plan's "Authorized" list and money-rule table (M1-M5, C8, H4), with a re-ratify of
  `earned-live-20260921` within a minute of each promotion that moves the digest (two digest
  changes, a third only for a money-path defect found in the watch). Nothing in "Not authorized".

## The first hour's decisions

1. **The deploy path (04:08-04:22Z).** H1 had already run before this session started: release
   `20260925T040816Z-532b1cd9b20c` was sent from `~/Work/ltcm-deploy` at `origin/main` `3defc0d`
   (#294) with the loop stopped (`watch_seconds 0`, canary 3 ticks), promoted at 04:09:55.8Z,
   `ops.started` at 04:11:49Z. It ships #289 (backup backoff, `began_at`), #292 and Merton's #288,
   #290, #291, #293, #294. The previous release `main-849c905c7146` (the updater's, 01:14Z) was
   rolled back at 01:17:55Z on the backup 503 ("prewarm base snapshot ... DeadlineExceeded").
   Still to verify: the backup alert's cadence (30 min doubling), and the updater's next release
   (this plan's merge, #295) not rolled back.
2. **Real books (04:21Z).** None frozen. The real Alpaca book failed to reconcile every ~5 minutes
   from at least 03:35Z to 04:03:42Z on `cash_diff` 0.01075037 (expected 465.61688803, venue
   465.627638403755211532, `dust_booked` 0), one error alert per failure; since the restart at
   04:11:49Z it reconciles. H4 still ships in Deploy A: the difference is unexplained by the book
   and will recur on the next venue fee activity.
3. **Ratify (04:26Z).** `ratify.py earned-live-20260921` (the no-restart wrapper around
   `league.live_trading --ratify`) returned `active True`, digest `535a7f15`, and wrote nothing
   (the policy is unchanged). This session can ratify: Deploys A and B may move the digest.
4. **Compute truth (04:25Z, `scripts/gateway_admin.py status`).** OpenAI gateway month $523.74 of
   $607.00 (settled $517.98, in flight $5.76); the House's OpenAI line $83.24; Sail $152.35 at about
   $16.17 a day (9.4 days); Jev $16.22 of $42.00. The gateway's profit index: equity $1,025.47
   (Kalshi $542.78, Alpaca $482.69), profit $7.72 above the $1,017.75 baseline. Kill switch off.
5. **The money set.** Deploy A carries H4's constitution key `allocator.real_book_dust_usd`
   (digest change 1 of 2). Deploy B carries M1-M5 and C8 (digest change 2 of 2).
6. **File owners, Wave 0:** H2 `league/watchdog.py`, `league/backup.py` (and the backup call and
   graceful shutdown in `house.py`, minimal); H3 `league/updater.py`; H4 `league/book.py`,
   `league/constitution.py`; H5/H6 `league/house.py` (the tick). Z `scripts/gap_scoreboard.py`.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main (#295) | done 04:31:43Z (`2470d26`) |
| 0.3 | First-hour decisions | done 04:28Z (above) |
| 0.4 | The scoreboard at T0 | done (below; Z, PR #298) |
| H1 | Ship the stuck head | promoted 04:09:55Z (not by this session); Sail's checkpoints recovered at 01:55:04Z, so the backup alert is quiet until the next failure; the updater's next CODE release is the last check |
| B | `kalshi-open` offered markets with no intent | not a defect (05:00Z, below) |
| H3 | The release train | built, PR #296 (CI green 05:31Z); owner deploy (Deploy A) |
| H5/H6 | The tick; sessions across restarts; restarts in health | built, PR #297 (CI green); adversarial review running |

## Findings before Wave 0 reports

- **Sail's checkpoint service recovered at 01:55:04Z Sept 25** (a successful backup after 73 failures since
  21:31:55Z Sept 24). The owner step "a Sail checkpoint ticket" is moot; H2 still ships (the next vendor outage
  must not roll a release back).
- **A docs-only merge to main is not a release.** The updater's 04:44Z check of `2470d26` (#295, the plan) wrote
  no row: a release tree holds `league/`, `ltcm/`, `scripts/`, `playbooks/` and `deploy/` only, so its digest
  equals the running one ("the box already runs main"). The Sept 25 memory note said the opposite; run-record
  merges restart nothing.
- **`kalshi-open` (the plan's bug list):** 2 living members; greenwich-h4cb387 woke 22 times in the 6 h to 04:23Z
  and made 3 intents; its thought each time is its program's screen ("Screen low-priced YES football outcomes and
  place bounded post-only NO bids; at most one position per event"), which rarely fires. Not a defect. The desk's
  gap is seats: 2 of 8 held, 4 waiters over 2 h, refused because the league's 128 seats are held (F3's case).

## Coordination with the other two runs

Two more runs execute beside this one: `docs/goals/LTCM_OPTIONS_DESK.md` (the owner's message at 05:47Z; record
`docs/runs/2026-09-25-options-desk.md` on `run/options-desk-2026-09-25`) and `docs/goals/LTCM_KALSHI_SCALE.md` (about
06:12Z; branch `goal/kalshi-scale-2026-09-25`, record `docs/runs/<date>-kalshi-scale.md` on its run branch). This run
follows the options plan's "Coordination" section across three runs: before each merge and deploy it reads all three
records (current waves, file owners, announced deploys); it edits no file another run's current wave owns; one deploy
at a time across the three, none 13:25-20:05Z on a trading day, **none while a real Kalshi family's game is in play**
(except a rollback), never inside another release's canary or watch, never within 30 minutes of another run's
announced deploy; after any promotion that leaves the grant inactive it ratifies `earned-live-20260921` only if every
changed money rule is a row of one of the three plans' tables (forward-first M1-M5, C8, H4; options O1-O5; Kalshi K5 and
`allocator.max_event_share` 0.25-0.35 for a proven sports family), else rolls back and records why. Whichever run
deploys the gateway second rebases on the first and re-runs the gateway tests. Messages to another run are lines here
plus a comment on its open PR.

**The Kalshi run owns** Kalshi strategies and founders in `league/strategies/`, the Kalshi desks' rows of
`league/niches.json` (seat changes coordinated with this run's F3), `league/feeds.py`, `ltcm/data/sports.py`,
`ltcm/data/weather.py`, `league/shards.py`, new capacity scripts, the gateway's `web_fetch` route, `LEAGUE_HOSTS`
additions, and after this run's Deploy B the scale rule in `league/live_trading.py` and `league/grants.py`. This run's
F3 changes desk capacity at run time in `house.py` (the forward record moves a desk's cap), never by editing a Kalshi
desk's row; S2's `kalshi-open` seats (Wave 2) are the Kalshi run's to change.

**This run's current wave, file owners and deploys (kept current; read this before merging into these files):**

| Wave | State | Files owned |
|---|---|---|
| 0 (Deploy A) | H3 #296, H5/H6 #297, Z #298 built (H5 in review); H2, H4 building | `league/watchdog.py`, `league/backup.py`, `league/updater.py`, `league/ci.py` (one dial), `league/config.json` (`tick_seconds`, `release_train_hours`), `league/book.py` (H4; passes to the options run at H4's merge), `league/constitution.py` (H4's key `allocator.real_book_dust_usd`), `league/house.py` (the tick, the births pass, the background lanes, `_run_backup`, health's restart and research-restart fields), `league/publish.py` (the updater's news line), `scripts/gap_scoreboard.py`, `scripts/floor_watch.py` |
| 1 (Deploy B) | building (F-lab, F-research), then C-money, C-family, F-seats | `league/lab.py`; `league/research_gate.py`, `league/merton.py`, `league/yield_ledger.py`; `league/allocator.py`, `league/constitution.py` (M1-M5 beside their rows, C8 `allocator.family_key` at the end); `league/families.py`, `league/hypotheses.py`; `league/house.py` (the seat market, waiters, expiries, desk capacity, displacement, births and a birth's family, C7's event split); `game.json` keys `lab`, `lab_bounds`, `research`, `merton`, `merton_bounds`, `audit`, `economy.proven_family_members`; in `league/book.py` only two small hunks (M2's refusal text, M6's Alpaca maker/taker classification in `_liquidity`), rebased onto the options run's book changes |

- **Free for the other runs** in Wave 1: `house.py`'s `_chain` and options hooks outside the regions above; the
  `alpaca-options` row and the Kalshi desks' rows of `league/niches.json`; new modules.
- **Announced deploys:** **Deploy A** (Wave 0; money-digest change 1 of 2, H4) between 08:00Z and 09:30Z Sept 25; the
  exact start is written here first. This run will not deploy between 09:30Z and 13:25Z, leaving the options run's
  Deploy V its 10:00-12:25Z window. **Deploy B** (Wave 1; digest change 2 of 2, M1-M5 and C8) not before 20:05Z Sept 25
  and only when no real Kalshi family's game is in play: the MLB games of the proven family run to about 03:00-05:00Z,
  so Deploy B is planned for a quiet window after the Friday night slate (about 05:00-15:00Z Saturday Sept 26), its
  start written here first.

**Answers to the options run's requests (06:20Z; also on its PR #299):**

1. The call line `options_desk.seat_founders(self)` after `self.enroll()` in the births pass: yes, the options run adds
   it itself once Deploy A is on main (it lands in the H5 births-pass region; keep it one line, and it inherits every
   protection `_displaceable` gives). This run's F-seats builder will keep it when it reworks that region.
2. `league/book.py` passes to the options run the moment H4 merges to main; the merge time is written here. This run's
   Wave 1 then touches `book.py` only by the two small hunks above, rebased onto the options run's.
3. Deploy V (with the gateway's practice multi-leg route) in 10:00-12:25Z: agreed.
4. `PAPER_BOOK` mapping for `options-shadow` in `allocator.py` / `families.py` after this run's Wave 1 merges: agreed.

## The scoreboard at T0

`scripts/gap_scoreboard.py --snapshot` (Z, PR #298) on the snapshot taken at 04:23-04:26Z Sept 25 (ledger to
04:23:14Z, window the 24 h before), with the box's `deploys.jsonl` read at 05:20Z.

| # | Metric | Reading (each number names its function) | Target at the end |
|---|---|---|---|
| 1 | Real settled profit a day (24 h) against compute a day (24 h); proven families and each one's capacity at its real size | `real_settled` $21.35 a day realized (57 settlements $21.17, 4 closing sales $0.18); `compute_per_day` $118.88 a day (OpenAI $102.69: Luna $38.58, Astra $59.61, lab $4.50; Sail $16.16; Jev $0.03); lifetime $570.52 ($564.70 by scripts/economics.py + $5.82 lab); `gateway_meter` the gateway metered the OpenAI line at $96.41 a day over 21.4 h; `unit_economics` compute 5.6x the profit: short of the target; `proven_capacity` 2 proven: megacaps-chip-demand-relay $0.12/day at $12.50 (the board), `capacity_at_sizes` $0.29 / $0.59 / - a day at 1x/2x/4x of $25.00 (the median bid; no real bid yet); sports-central-run-under $25.86/day at $6.00 (the board), `capacity_at_sizes` $28.41 / $56.82 / - a day at 1x/2x/4x of $5.10 (the median real bid) | compute <= 2 x real settled profit, or <= $60/day while no family swings; >= 3 proven families, capacity measured at 1x, 2x and 4x the stake |
| 2 | Forward-positive share of the last day's graduates and newborns (lab forward windows, first practice day); living median W_paper; agents above the 1.01 line | `forward_positive` graduates 2 of 8 with an active forward block (25%; 110 graduated, 91 with a window); newborns 16 of 44 on their first practice day so far (36%; 127 born), first day ended 37 of 76 (49%); lab-born active blocks 109 of 217 (50%, the baseline's measure); `practice_standing` median W_paper 1.00025 over 125; 37 above the 1.01 line (E at bunt_at 1.01: 27) | >= 60%; >= 1.005; >= 50 |
| 3 | Real dollars on proven families / on unproven (stake); the first family swing; Alpaca real stock agents (ever) | `real_dollars` $16.62 proven / $269.62 unproven; `capital_on_proof` no family swing yet: megacaps-chip-demand-relay 0 real settlements, 15 to go (look at 15, - days); sports-central-run-under 11 real settlements, 4 to go (look at 15, 0.72 days); Alpaca real stock agents ever: 0 filled (0 in a session), 0 staked on a stock desk | proven >= unproven; the swing reached at the sports family's 10th settlement, or the exact count why not; >= 2 during a session |
| 4 | House restarts a day; releases rolled back by causes outside the House (vendor, backup, site); tick p50; deploys inside a US session | `restarts` 26 in the window (26.0 a day), 7 inside a US session; `deploy_record` 7 releases rolled back, 6 by causes outside the House (backup 6, house 1); 5 of 21 deploys inside a US session (from deploys.jsonl); `tick_p50` interval p50 73.6 s over 989 ticks (p90 122.0 s); the last tick 30.4 s | <= 6; 0; <= 40 s; 0 |
| 5 | Waiters over 2 h and the longest; merged strategies never born; median life against each desk's evidence clock; displacement share of deaths | `seat_queue` 45 of 65 waiters over 2 h (13 on desks with a free seat), the longest 60.6 h (cards on kalshi-weather); 18 merged strategies waiting (the seat market at 2026-09-25T03:41:54.653Z); `life_vs_clock` median life under the desk's clock on 4 of 8 desks (alpaca-crypto-alts 0.2 h < 3.7 h, kalshi-crypto-15m 0.7 h < 2.8 h, kalshi-prices 6.0 h < 36.5 h, kalshi-sports 3.3 h < 20.5 h); `displacement_share` 86% of 111 deaths in the window (90% of 519 lifetime) | 0 with free capacity, longest < 2 h; 0; >= the clock on every desk; < 50% |
| 6 | Real fill rate (fills / orders, 24 h); real entries refused a day; taker entries by probes | `real_fill_rate` 61 of 165 orders filled (37%; kalshi 51 of 74, alpaca 10 of 91); the baseline's rows measure 62 of 695 (9%); `real_refusals` 341 real entries refused (341 a day), 116 in the last session (2026-09-24); the most: allocator.max_event_share 149, insufficient desk cash 83, allocator.real_entry_liquidity 56; `probe_taker_entries` 0 Kalshi taker entries by probes ($0.00), 60 probe entries refused for taking; Alpaca books every fill a taker (5 probe entries, $70.81) | >= 25%; < 30; allowed and measured |
| 7 | Sail runway; the October OpenAI cap; the population ceiling binding on runway | `runway` Sail 9.13 days ($152.57 less $5.00 reserve at $16.17 a day; the House reads 9.13); the OpenAI month 2026-09 at $529.37 of $607.00, October's cap unset; the population ceiling does not bind on runway (128 of 128; 0 population alerts in the window) | >= 5 days throughout; set from funded money at the owner's word; never |

How it compares with the plan's baseline (Z's hand checks): rollbacks since 21:16Z Sept 24, deploys inside the
Sept 24 session, restarts, the session's 116 real refusals, lifetime displacement and Sail runway all agree. The
real fill rate reads 37% per order (Kalshi 51 of 74, Alpaca 10 of 91) against the plan's 10%, which divided fill
rows by order-status rows (62 of 695): by the per-order measure row 6's fill target is met at T0. Waiters 65 (18
merged strategies, not 12). Forward-positive graduates 2 of 8 and newborns 16 of 44 on their first practice day;
the plan's 53% was lab-born agents' active blocks (109 of 217, 50%, at T0). Compute $118.88 a day includes $4.50 of
lab model calls that `scripts/economics.py` does not see.

Found by Z, for Wave 1: every Alpaca fill is booked as a taker (`Book._liquidity`), post-only dip bids included, so
Alpaca families' maker/taker records mean nothing (crypto-alts-reversion: taker n 292, maker n 0); "insufficient desk
cash" is the second refusal (83 in the day) and names no constitution key; the evidence clocks were last measured at
08:32Z Sept 24.

## Wave 0 reports

- **H3 (#296).** Replaying the live `deploys.jsonl` (14 updater launches 02:15Z Sept 24 to 01:14Z Sept 25, one at
  14:58Z inside the session, five rolled back) under the new rules gives 5 launches, none in a session. The hold
  window starts 30 minutes before 13:25Z (12:55Z) because the canary took 2.2-4.0 minutes from launch to restart
  and the watch is ten; the calendar is `ltcm.data.us_equity_session`, the function `house.py` uses. A head
  rolled back once is retried once at the next train; a second rollback retires it. `release_train_hours` 4
  (bounds 2-6 in `league/ci.py`). Digest unchanged.
- **H5/H6 (#297).** The tick interval had a 60 s floor (`tick_seconds` 60) and a p50 of 60.0-68.4 s quiet, 97-121
  s in the Sept 24 session; tick p50 60.8 s over 26 reads 04:31-05:00Z, the population step p50 22.0 s (max 75.3).
  Run read-only on the T0 snapshot, the population step asked the displacement scan 399 times a tick (once per
  deferred research candidate) for 10 distinct questions: 17.1 of 18.4 s, under the lifecycle lock, seating
  nobody. The fix answers each question once per pass (3.25 s), runs the births pass every 300 s or after a birth
  or death, moves research scheduling and the foundry step to a `house` background lane, polls kalshi-shadow once
  a minute, and sets `tick_seconds` 30. H6: of 110 research sessions that spanned one of the day's 26 restarts, 84
  resumed and 25 were lost with no alert (23 `campaign_post_unconfirmed`, 2 `tool outcome unconfirmed: replay`),
  each closed as a finished pass; they are now named in a warning and the agent may research again in 15 minutes.
  `health.json` gains `restarts_24h`, `restarts_24h_in_session`, `last_start`, `restart_research`.

## Progress notes

## Watch log

## Report

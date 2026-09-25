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
| H3 | The release train | merged 10:33:52Z (#296); LIVE in the options run's Deploy V (promoted 11:08:45Z, watched to 11:18:45Z); the updater held main's head to 20:05Z (the session hold) |
| H5/H6 | The tick; sessions across restarts; restarts in health | built, PR #297 (CI green); adversarial review running |
| H4 | A real book never freezes on cents | built, PR #302; three-lens review fixes on `h4/review` (`b62b215`); money digest `535a7f15` -> `d7d910fe`; integrated |
| Z | The scoreboard | merged 10:33:56Z (#298) |
| H2 | A vendor's outage never rolls back a release | built, PR #307; reviewed, fixes on `h2/review` (`49acc6c`), integrated |
| S | The search looks for capacity (foundry brief `foundry-2026-09-25.1`; alpaca-open 12 seats) | built, PR #331 (CI green; on #324); Deploy C |
| Y | Compute follows yield (lane throttle, trigger skip, unit economics, the contract by section) | built, PR #330 (CI green; built on #311); Deploy C |
| F3/C7 | Seat market by forward record; members on disjoint events | built, PR #329 (CI green); Deploy B; money review with C-money |
| B | Deploy B integration (`b/integration`) | Deploy A + C8/C6 + F1 (+review) + F2/F4/X2 (+review) + F3/C7; money digest `555b7aac` before C-money; C-money and the Wave 1 money review to come |
| C8/C6 | Family = mechanism; capacity at the real size | built, PR #324 (CI green); money digest (on H4) `d7d910fe` -> `555b7aac`; Deploy B; three-lens review with C-money |
| W | The site's flywheel strip | site #8 merged and DEPLOYED 12:35:10Z (version `2b780c2c`; the next checkpoint, 12:35:58Z, accepted); publisher #325 (CI green) merges in Deploy C |
| F1 | The lab places, breeds and graduates on forward growth | built, PR #306 (CI green); Deploy B (`lab.py` protected) |
| F2/F4/X2 | Research on outcomes; lanes measured; refusal dedupe | built, PR #311 (CI green); Deploy B (touches `ledger.py`: the `consult.outcome` kind) |
| A | Deploy A integration (`a/integration`, draft PR #323) | main (incl. the options run's Deploy V, #317) + H2, H4, H5 reviewed; 630 targeted tests OK after re-pointing the structure-invariance test to H4's book.py; CI running; Deploy A 20:10Z |

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

**A fourth run (the owner's message, about 06:10Z)** executes `docs/goals/LTCM_JEV_SENSES.md`. It owns only the Jev
files (`league/jev.py`, `sensors.py`, `triage.py`, `hypothesis_memory.py`, `exposure.py`, `semantic_lab.py`,
`jev_features.py`, `scripts/jev_lab_eval/`, `gateway/lib/typesafe.mjs`, `config.json`'s `jev` block), changes no money
rule, and lands small hooks into `research_gate.py` and `lab.py` (this run's Wave 1) and `feeds.py` (the Kalshi run's)
only after the waves that own them merge. One deploy at a time across four runs; any gateway deploy rebases on the
others' gateway changes and re-runs every gateway test. This run's Wave 1 writes the merge times of `lab.py` and
`research_gate.py` here.

**Answer to the Kalshi run (06:37Z, its seat request):** yes to `kalshi_founders.seat(house)` in the births pass (one
line after the options line, once Deploy A is on main, under the lifecycle lock), retiring at most one crypto-15m
PRACTICE resident a pass to seat a flagged founder, never a real-money agent, a proven family's member, one holding a
position or working order, stopping at 4 members, each death recorded with its own cause (`desk_closed`, not
`displaced`); and to crypto-15m `max_members` 8 -> 4 in its niches.json row. It is F3's own first move (crypto-15m:
-$254 practice, all five 15-minute families negative on real money) done early for that run's founders. Its evidence
on the proven run-under family (a public-record study of 239 KXMLBTOTAL games, the family's record inside a five-day
positive stretch) is being verified before C-money's brief fixes M1 and M3 for that family (below).

**This run's current wave, file owners and deploys (kept current; read this before merging into these files):**

| Wave | State | Files owned |
|---|---|---|
| 0 (Deploy A) | H3 #296, H5/H6 #297, Z #298 built (H5 in review); H2, H4 building | `league/watchdog.py`, `league/backup.py`, `league/updater.py`, `league/ci.py` (one dial), `league/config.json` (`tick_seconds`, `release_train_hours`), `league/book.py` (H4; passes to the options run at H4's merge), `league/constitution.py` (H4's key `allocator.real_book_dust_usd`), `league/house.py` (the tick, the births pass, the background lanes, `_run_backup`, health's restart and research-restart fields), `league/publish.py` (the updater's news line), `scripts/gap_scoreboard.py`, `scripts/floor_watch.py` |
| 1 (Deploy B) | building (F-lab, F-research), then C-money, C-family, F-seats | `league/lab.py`; `league/research_gate.py`, `league/merton.py`, `league/yield_ledger.py`; `league/allocator.py`, `league/constitution.py` (M1-M5 beside their rows, C8 `allocator.family_key` at the end); `league/families.py`, `league/hypotheses.py`; `league/house.py` (the seat market, waiters, expiries, desk capacity, displacement, births and a birth's family, C7's event split); `game.json` keys `lab`, `lab_bounds`, `research`, `merton`, `merton_bounds`, `audit`, `economy.proven_family_members`; in `league/book.py` only two small hunks (M2's refusal text, M6's Alpaca maker/taker classification in `_liquidity`), rebased onto the options run's book changes |

- **Free for the other runs** in Wave 1: `house.py`'s `_chain` and options hooks outside the regions above; the
  `alpaca-options` row and the Kalshi desks' rows of `league/niches.json`; new modules.
- **Announced deploys (revised 10:33Z):** a usage limit stopped every session on this account from about 07:35Z to
  10:30Z, so Deploy A missed its 08:00-09:30Z window. **Deploy A** (H2, H4, H5 and their reviews' fixes; H3 and Z too
  unless the options run's Deploy V carries them) now starts at **20:10Z Friday Sept 25**, if no real Kalshi family's
  game is in play then, else at the first quiet slot after; the exact start is written here first. **Deploy B** (Wave
  1; digest change 2 of 2) follows after the Friday night slate, about 05:00-15:00Z Saturday Sept 26, its start written
  here first. This run does not deploy 09:30Z-20:05Z Friday.
- **Exceptions granted to the options run (10:33Z, for its Deploy V today):** (1) its one call line
  `options_desk.seat_founders(self)` in `_births` lands on main before this run's Wave 0 (H5 rebases over it); (2) its
  structure-only hunks in `league/book.py` land before H4 (H4 rebases over them), with a test that non-structure books
  and positions behave exactly as before. Offered: H3 (#296) and Z (#298) merged to main before its 11:45Z merge so
  Deploy V carries the release train into today's session, if it agrees by 11:15Z. It agreed; **H3 (#296) merged to
  main at 10:33:52Z (`2aa7690`) and Z (#298) at 10:33:56Z (`ce3b97c`)**, both with CI green (tests 3.11 and 3.14,
  gateway). H3 is protected: the updater now refuses main's heads until an owner deploy ships them (Deploy V).

**Answers to the options run's requests (06:07Z; also on its PR #299):**

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

## The proven sports family, verified (07:11Z)

The Kalshi run's study (a public-record test of the family's mechanism) was verified by four independent agents
(a workflow: reproduce and audit the study; match the family's program; recompute its proof clustered by date; a
skeptic). Scripts in the session scratchpad (`skeptic/`). What holds:

- **The program is the study's mechanism.** meriwether-h2d625d (born seq 193200, code `6d65362f`, never rewritten):
  KXMLBTOTAL only, buys NO at the ask (taker) 0.38-0.60, spread <= 2.5c, 2-27 h before first pitch, no feeds, 20 lots.
  45 fills (28 practice, 17 real), all by the founder. Rebuilt with the program's own rules from Kalshi's public prints
  over all 277 games Sept 4-24 at a 16 h lead: 241 entered, 46.1% won, -12.2% a dollar (t -1.91); 14 of 21 days
  negative at every lead tested.
- **The study reproduces exactly** (107/239, NO 0.499, -14.2%/$, t -2.19) but charges twice the real fee (KXMLBTOTAL's
  `fee_multiplier` is 0.5; real fills paid 0.035 C P(1-P)) and prices at the VWAP (0.6-0.8c under the ask); the two
  offset (-13.8%/$ at the ask with the right fee, t -2.17). Sept 4-19: 72/186 won, -24%/$, 14 of 16 days negative;
  Sept 20-24: 35/53, +29%/$; the split is unlikely to be chance (p 0.005, 0.05 with the 37 skipped Arizona and White
  Sox games added).
- **Same-night correlation is not the defect** (within-date correlation -0.003). The defect is that the family
  record counts events with no time dimension: all 25 events lie on 3 slate dates (Sept 22-24) inside one five-day
  regime, the real 11 on 2. One observation per date (the House's own collapse rule): n 3, mean +0.1507, 80% bound
  -0.0665, not proven. The dollar-at-risk weight also counts two-strike games heavily: with equal weights the bound is
  -0.1197 (14 of 25 events won; winners weigh 0.865, losers 0.545). The regime is closing (runs minus the central
  strike -1.71, -0.81, -0.60 on Sept 22, 23, 24; the real Sept 24 slate went 2 of 6, -$3.09), and MLB's regular
  season ends Sept 27 (4-game postseason slates from Sept 29).
- **What M1 would do:** the look at 10 real settlements at 90% reads -0.1187 (not ready; at 80% +0.0473). Under the
  LIVE rules the look at 15 is decided by the next 4 real events, already open (SD-LAD Sept 24; TB-PHI, PIT-DET,
  TEX-MIN, AZ-SD Sept 25): 4 of 4 gives +0.1031 (the swing's entry, then the auditor), 3 of 4 gives -0.0436.
- **Members:** -3, -5, -6 run the same code with 0 fills (more exposure on the same slate, no new evidence); -4
  rewrote itself at 02:37Z Sept 25 into a KXWNBAGAME favourite-maker (`26152cae`) and keeps the family's name (C8).

**Decision (07:11Z), inside the table:** M1's entry look moves to 10 real settlements AND every swing look (entry,
hold, doubling) also needs the family's real record to span at least 5 distinct settlement dates
(`family_swing.min_distinct_dates` 5, a stricter gate carried in M1's row: the evidence shows a count of events cannot
tell a regime from an edge). M3 seats a proven family's members only when the family's pooled proof spans at least 5
distinct settlement dates and only members running the proven code (the digest the family's settled evidence was
earned with; C8 ships with it); `economy.proven_family_members` stays 4. For the owner (outside this run's table): the
same distinct-dates requirement on the `family_proven` line itself, and an equal-weight bound beside the at-risk one;
today meriwether-h2d625d stays a proven-family bunt at $16.62 on a proof of 3 dates.

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

- **H4 (#302; money digest `535a7f15` -> `d7d910fe`, constitution `38a57fe9` -> `d0aa4c2a`).** The Sept 25
  02:38:59-04:11:50Z real Alpaca freeze had no fee or fill behind it: the book added each resting crypto bid back to
  the venue's cash unrounded while Alpaca holds each bid rounded half-up to the cent ($317.95 cash + $147.68 of
  rounded holds = $465.63 at 04:37Z); the fractions were booked as dust at each reading until four of the eight bids
  resting at 02:26Z were cancelled or replaced and -0.01075 stood. With the rounding the cash never moves across 339
  fill-free pairs of readings (unrounded it moved 66 times). The 04:11:50Z un-freeze was a second bug: the rebuild
  after a restart counted every fill the book ever had as "since the last check", so the first reading allowed $0.12
  of slack ($1.39 on the real Kalshi book) and booked the 0.0108 as dust 1.2 s after start; the same cleared the
  Sept 24 option freeze (-0.0324) at 18:45:22Z. Fixes: holds at the cent (the first clean reading after the deploy
  takes back the old rounding once), restarts count fills since the last clean reading, real option fills pay the
  OCC $0.03 a contract at the fill, and the key `allocator.real_book_dust_usd` 0.50 (a shortfall under it, positions
  agreeing, nothing in doubt, inside the room recent option and stock fills leave for regulators' fees, is dust on the
  House row with an error alert; anything else freezes). Open, from the builder: the Sept 24 ORF fee ($0.03) is still
  unbooked on the real book; a dividend or interest credit would freeze a real book as an unexplained surplus.

- **H2 (#307).** `watchdog.service_failed(exc)` marks an error alert as a service's (5xx, 408/425/429, timeouts,
  refused/reset/unreachable connections, DNS, cut-off replies, TLS drops; through wrappers) and never a 4xx or this
  code's own exception; marked alerts are counted in `detail.environment_alerts` and never a reason, in the watch and
  the canary. The backup outage is one error when it begins, warnings at later backoff steps, an info at recovery,
  all marked. The 73 s shutdown of 00:04Z was the run loop, not the backup: `time.sleep` slept through TERM, so
  TERM-to-exit took 24-82 s over the 13 restarts from 18:43Z Sept 24; the loop now sleeps a second at a time and
  stops on TERM (`league/__main__.py`, 7 lines). Found, not fixed: two `lab.py` errors a Sail outage can raise are
  unmarked; `feeds.py`'s poll warnings and `DataError` carry no status for the classifier.
- **H5 review (on `h5/review`).** Four defects fixed: the tick walked `_jobs` while the new `house` lane added keys
  ("dictionary changed size during iteration" would fail a tick and roll a release back); the stop warning came after
  one minute at 30 s ticks (now 120 s, `STOPPED_TELL_SECONDS`); a saved scan answer could hand over a replay-only
  resident whose research was queued mid-pass; the scan read desk stamps other threads write. Being fixed now: real
  books polled at most every 60 s (a flaky venue's warnings must not reach the 10-in-30-minutes error inside a watch),
  `_enforce_horizon` cancelling the House's own resting exit and re-sending it with the same nonce (rejected as a
  duplicate: the position had no exit), and `hypotheses.py` iterating the registry while other threads add agents.

- **F-research (#311, Wave 1).** Replayed on the T0 day (`scripts/gate_replay.py`): sessions 2,566 -> 1,038 plus about
  44 samples (-58%), adoptions or forks 108 -> 85 (-21%), candidates 547 -> 253 (-54%), dollars $87.65 -> $34.48
  (-61%). The candidates target ("unchanged or up") is missed on purpose: 350 of the clock's 387 runs were idle agents
  re-running every 12 minutes (mcentee-hfadaea 33 times in the day), and the clock's 201 candidates produced 9
  adoptions or forks; adoptions per dollar double. Keeping the idle clock (`idle_runs: clock`) keeps 397 candidates but
  only cuts dollars 32%. X2: 670 refusals from 86 distinct reasons had bought 544 sessions; now one per agent, reason
  and day. F4: the yield row gains `lift`; at T0 the consultant reads `no_lift` ($35.44 for 62 answers; 50 of 110 judged
  consults led to nothing; $0.45 a positive block against research's $0.29), the engineer 22 verified repairs for
  $27.54; the lesson count had been counting desk-mates' post-mortems (111 of 117). The consultant's pause is decided
  on 24 h of live lift after Deploy B.
- **The Kalshi run's K5 (07:23Z):** its one line in `Allocator.grant_capital` (a ratified version-2 tranche's
  `unlocked_usd`, 0 until the owner ratifies) goes in as its own small PR after Deploy B, reviewed here.

- **F-lab (#306, Wave 1).** Replayed on the T0 `lab.sqlite`: 44 of 83 archive cells change program; elites from
  forward-winning lineages 15 -> 46, from losing ones 24 -> 3, with no record 44 -> 34; Luna and agent elites 9 -> 24.
  Of the last day's 273 graduates only 2 (0.7%) would have passed (268 had no winning forward window of their own):
  graduations will fall to what the forward windows can score until they catch up (each forward run scored 5-31
  candidates in its 90 s at T0; `forward_box_seconds` 90 -> 180 and `forward_candidates_per_run` 48 -> 96, both
  bounded). 11 lineages blocked at T0 (latest window losing over 6+ active blocks). `reserved_share` 0.5 -> 0.33:
  mechanism children take 22 of 32 batch slots. Watch after Deploy B: graduations a day and the seat market's inflow.

- **From the Jev run (J2, offline, held out Sept 24 00Z-Sept 25 06Z; its record, section "J2"), for Wave 2's Y:**
  on the 1,228 held-out sessions F2 would still run ($39.05), the trigger kind alone predicts a replay pass at AUC
  0.856 [0.823, 0.887] and a free logistic (trigger kind, empty streak, record class, previous outcome, fills/settles,
  hours since last) 0.896; skipping by trigger kind drops 31% of dollars for 9% of replay passes and 12% of candidates.
  Sessions woken by the agent's own fills or settlements predict no candidate (AUC 0.215). Merton, 497 passes Sept
  22-25 ($174.78): architect 43 of 54 produced nothing ($31.77 of $44.18); toolsmith, operator and designer 42 of 43
  ($14.19); engineer 155 of 207 ($16.98); consultant 23 of 112 (30 led to a replay-passed candidate). The consultant
  looks productive by outcome while F4's forward-lift reading says no lift: the pause decision reads both. Jev builds
  no pre-filter (it does not beat these free rules).

- **H2 review (two lenses, then a skeptic-fixer).** Found the hole the plan did not foresee: marking the TRADING
  path's failures as environment (a wake's box run, `_wake_safely`, the venue polls) let a release that breaks every
  wake with a service-shaped error be promoted: e.g. `wake_workers` 6 -> 32 makes Sail answer 429 to every box run, or
  a 2 s order-path timeout makes every wake time out at the gateway; the repeat escalation was the only signal that
  caught either, and it carried the marker. Fixed: those four sites are unmarked again (the backup, publish, updater,
  background jobs, replay, fork, retire, Sail's runway and the gateway meters stay marked, where a rollback cannot
  help); `service_failed` now follows `__context__` only under `raise ... from None` (a BookError or RuntimeError raised
  inside a timeout handler was being marked). Tests: every box run refused with 429 rolls back; a wake timing out at
  the gateway rolls back and a canary refuses it. Open, low: HTTP 5xx from the venue and data clients carries no
  status (they err toward rollback, as before); a bare builtin `TimeoutError` still reads as a service's.

- **H4 review (three lenses, verified, fixed; `h4/review` `b62b215`).** Confirmed and fixed: a regulators' fee (ORF,
  CAT, TAF, REG) taken at the fill and booked as real dust stayed bookable when its listing came hours later, so it
  could silently explain a later unrelated shortfall (the live CAT $0.01 of Sept 24's fills was booked again at
  02:20:33Z Sept 25 against bid rounding): real dust now keeps a prepaid balance and a covered listing is written as a
  zero-cash `venue-fee` row with `covered_usd`; the dust alert carries `began_at` (the newest option or stock fill no
  clean reading has followed), so a fill before a promotion is inherited by the watch; room ages with its own fill,
  oldest first; the first reading after the deploy expects the old rounding with its sign and books no listing against
  it. The first reading after Deploy A raises no alert (replayed on all 1,461 snapshot reading pairs). Open: the
  pre-existing `UnboundLocalError` on `inherited` in `watchdog.read_health` when health.json is missing (a follow-up).
- **The options run's Deploy V (#317, merged 11:15Z; release `20260925T110706Z-c7adcaf627d5`)** carried H3 and Z and
  its structure work (house.py +577 lines incl. the births-pass line, book.py structure hunks). Merging it into
  `a/integration` conflicted in `_enforce_horizon`: rebuilt by hand as main's per-book `_horizon_exits` (with the
  structure close) plus the H5 review's standing exits; `league/fees.py`'s docstring keeps both runs' paragraphs.

- **C-family (#324, Wave 1; digest `d7d910fe` -> `555b7aac`, constitution `d0aa4c2a` -> `2fa6e95b`).** The family key is
  the program's code less its PARAMS literal (`parameters.same_logic`, digested by `lab.mechanism_digest`) plus its
  venue, series and symbols; a params-only child stays in its parent's family, any other program founds or joins the
  family of its mechanism (founders included); an in-place rewrite moves the agent from the rewrite's row on; a
  one-time re-key at the first start writes `agent.family` rows (no old row edited). On the T0 snapshot: 781 rows for
  424 agents; 60 of 110 labels keep their record exactly, 50 change, 588 new families; real dollars +$25.55 before and
  after. **sports-central-run-under reproduces to the cent** (n 25, bound +0.0344, real n 11, +$16.39 real; -2 leaves,
  -4 keeps only its pre-rewrite stretch with 0 fills). **megacaps-chip-demand-relay's proof moves whole** to
  `megacaps-megacap-short-horizon-re-8a220c` (its one member rewrote itself 11 times on Sept 23; all 26 fills came
  after the 11th). Consequences to settle in Wave 1: three more families prove on their own records (two single-program
  crypto-15m families on practice only, n 20 bound +0.093 and n 14 bound +0.018; crypto-alts-reversion's original
  program, no living member); haghani-58 lands in a losing family and drains; krasker-14's $80 options probe stops
  draining (its own program has 3 blocks, under R5's 6); R5's holds must be keyed by the family at the demotion
  (`tape.family_at`, C-money); the scoreboard must read `agent.family` rows (Z follow-up).

- **Other runs' deploys today (from their messages):** the options run's Deploy V, release
  `20260925T110706Z-c7adcaf627d5`, promoted 11:08:45Z, watched to 11:18:45Z (carried H3 and Z); the Jev run's D-J1,
  release `20260925T114915Z-007e06151f53` (main `2ee015b`: #319 and Merton's #321), promoted 11:50:48Z, verdict promoted
  12:00:50Z with 0 error alerts, grant active on `535a7f15`. Deploy A's integration contains both (merged 11:52Z; PR
  #323, CI re-running).

- **W (site #8, publisher #325).** The capital page gains a "Last 24 hours" strip (compute a day and its multiple of
  real profit, winning forward blocks, graduates and proofs a day, real profit, restarts a day; hidden when older than
  30 minutes) and, per proven family, its clock to compounding (with the distinct days still lacking) and its capacity
  curve at 1x/2x/4x. The schema's new fields are optional and exact; every older checkpoint still passes. The
  publisher sends each field only when its source has it and falls back to the checkpoint without them on a 400 from
  an older site. Site tests 84 pass (3 new, failing on main); deployed 12:35:10Z, before the session.

- **F-seats (#329, Wave 1).** The "18 merged strategies waiting" were 13 corrected children whose card had passed
  replay (also counted among the cards) and 5 whose card had failed (never to be born): each is now counted once, and
  a failed card leaves the queue. Quota: one merged strategy born a births pass (real-money parents' fixes first, e.g.
  `hilibrand-event-budget-child`), never into a trader's seat; expiry at 24 h back to the lab with the forward record
  kept; desk capacity moves one seat every 12 hours at run time (negative 7-day record on 100+ active blocks shrinks to
  a floor of 4; positive on 30+ grows up to the file's cap + 4), never editing niches.json; a trader keeps its seat
  until its desk's evidence clock has run from its first fill; `seats.deaths` counts `desk_closed` apart; C7 splits a
  proven family's real members' Kalshi events by a hash of `evaluator.event_key` (a real entry on another member's
  event is refused; exits never split). Replayed on T0 with the clock run forward: 13 ready strategies, 1 seated at
  T0 (every resident protected), 4 by +1 h, 9 by +4 h, 11 by +8 h; displaceable 0 / 3 / 11 / 28 at T0 / +1 / +4 / +24 h.
- **F-lab review (`f-lab/review`).** Seven of nine findings fixed with tests: residents keep a quarter of every
  forward run (the new order starved re-scoring), a young window is re-scored only once a block has closed, tried
  candidates are not asked for, parameter children keep their third of the asks, a daily desk's cell asks the next
  program after 24 h of data, a losing program no longer deadlocks its agent's submissions, a blocked lineage places
  as a losing one; re-placing T0 moves 46 of 83 cells. **Open (owner / Wave 2 X):** graduation selects on a forward
  window that lies inside the House's replay's out-of-sample third on Kalshi and the non-deep Alpaca desks (the same
  `tape_for` tape), so that replay is no longer independent; X cuts the House's replay tape at the candidate's
  freeze. The plan's ">= 60% forward-positive graduates" becomes 100% by construction: the run reads the newborns'
  first practice day instead (the scoreboard's `forward_positive` second number).
- **F-research review (`f-research/review`).** Seven of nine fixed with tests: the consult price multiple could take
  an agent's balance to zero (4 of 90 consults at 4x on T0): the surcharge is now capped; rung-0 agents keep their
  clock after three abstentions; the teacher's control arm no longer reads the lesson that names it (3 days,
  `teacher_days`; also for control agents on real money); a paused practice agent hears news of its own program at
  once and its own trading once a UTC day; the multiple decays after 7 days; the barren count restarts on a reset; a
  paused consultant's row is written once. Replay after the fixes: 794 sessions (+44 samples), 259 candidates, 90
  adoptions or forks, $34.58 (T0 day: 2,566, 547, 108, $87.65). The candidates target stays missed (recorded).

- **Y (#330, Wave 2).** Lane throttle (`economy.lane_throttle` 3, bounds 2-5): at each hourly yield row a lane whose
  24-hour dollars per positive forward block exceed 3x the best lane's (the cheapest with at least 10 positive blocks),
  or that spent $1 and bought none, is halved until a row finds it back under the line (practice research interval
  doubled up to one session a day, real agents untouched; the consultant's price doubled; scheduled roles' cadence
  doubled; the engineer waits two intervals except for a real-money job; audits never). On the T0 day's 24 yield rows:
  lab $0.038 a positive block (best), foundry $0.052 (1.4x), engineer $0.18 (4.7x, halved), research $0.29 (7.5x,
  halved), consultant $0.51 (13.2x, halved), architect $7.38 with no positive block (halved). Trigger skip: J2
  reproduced exactly; on practice agents only, `book.fill` (495 sessions, $0.62 a replay pass) and `book.settle` (62,
  $0.44) no longer wake research; held out it skips 408 of 1,171 sessions, 13% of dollars, for 2% of replay passes and
  3% of candidates. Y2: `health.json` `unit_economics` ($118.88 against $21.35 a day at T0, 5.57x). The contract by
  section for Merton and the engineer: 10.77 MB -> 6.26 MB a day of prompt (-42%), about $1.19-14.83 a day, and $0.73
  off the average engineer hold. Open: the researcher's prompt (the Kalshi run's file) still sends the whole contract
  (about 89 KB a turn); the foundry and the lab too.

- **S (#331, Wave 2).** Every foundry card states its capacity (markets a day x profit a settlement x the size before
  fills halve, from the desk's C6 curve or $6 Kalshi / $12.50 Alpaca) and is refused under `min_capacity_usd` $5 a day
  (bounds 2-20), before replay on its stated number or after on the replay's measured one (`under_capacity`). Calls:
  half capacity (desks with a positive pooled 7-day record over 6+ active blocks, weighted by their families' measured
  capacity, never a family by name), three tenths model-versus-market (weather ensemble, EDGAR earnings, DVOL and
  funding, the sportsbook line on leagues no founder prices), two tenths exploration. `alpaca-open` 8 -> 12 (the Kalshi
  run owns `kalshi-open`); a card spanning two desks is replayed on both. **On the T0 snapshot none of the last day's 55
  replayed cards measures $5 a day** (best $4.15 on the closed crypto-15m desk; weather's best $0.47): expect few
  foundry births until cards with more markets or larger edges come; the floor stays $5 and is watched. At T0 about 93%
  of capacity calls would go to kalshi-sports, weighted by the MLB-totals regime families; it fades with the 7-day
  window. At T0 the foundry refused every call ("no seat is open on any eligible desk"): F3 frees seats first.

## Progress notes

### T+6.2 h (10:36Z Sept 25; the 08:23Z note was lost to the usage-limit outage)

Snapshot taken 10:36:08-10:38:03Z (`gap_scoreboard.py --take`, ledger to 10:36:11Z, release `main-47c52e860764`:
the updater shipped Merton's #314-#316 during the outage). Nothing of this run is deployed yet: the rows move with the floor.

| # | Metric | Reading (each number names its function) | Target at the end |
|---|---|---|---|
| 1 | Real settled profit a day (24 h) against compute a day (24 h); proven families and each one's capacity at its real size | `real_settled` $19.38 a day realized (66 settlements $19.15, 6 closing sales $0.23); `compute_per_day` $122.31 a day (OpenAI $104.99: Luna $41.59, Astra $57.87, lab $5.53; Sail $17.27; Jev $0.04); lifetime $607.44 ($599.97 by scripts/economics.py + $7.47 lab); `gateway_meter` the gateway metered the OpenAI line at $105.98 a day over 22.4 h; `unit_economics` compute 6.3x the profit: short of the target; `proven_capacity` 2 proven: megacaps-chip-demand-relay $0.11/day at $12.50 (the board), `capacity_at_sizes` $0.25 / $0.51 / - a day at 1x/2x/4x of $25.00 (the median bid; no real bid yet); sports-central-run-under $29.36/day at $6.00 (the board), `capacity_at_sizes` $32.33 / $64.65 / - a day at 1x/2x/4x of $5.39 (the median real bid) | compute <= 2 x real settled profit, or <= $60/day while no family swings; >= 3 proven families, capacity measured at 1x, 2x and 4x the stake |
| 2 | Forward-positive share of the last day's graduates and newborns (lab forward windows, first practice day); living median W_paper; agents above the 1.01 line | `forward_positive` graduates 4 of 10 with an active forward block (40%; 100 graduated, 87 with a window); newborns 7 of 30 on their first practice day so far (23%; 99 born), first day ended 42 of 71 (59%); lab-born active blocks 112 of 223 (50%, the baseline's measure); `practice_standing` median W_paper 1.00083 over 125; 32 above the 1.01 line (E at bunt_at 1.01: 21) | >= 60%; >= 1.005; >= 50 |
| 3 | Real dollars on proven families / on unproven (stake); the first family swing; Alpaca real stock agents (ever) | `real_dollars` $16.62 proven / $258.21 unproven; `capital_on_proof` no family swing yet: megacaps-chip-demand-relay 0 real settlements, 15 to go (look at 15, - days); sports-central-run-under 12 real settlements, 3 to go (look at 15, 0.56 days); Alpaca real stock agents ever: 0 filled (0 in a session), 0 staked on a stock desk | proven >= unproven; the swing reached at the sports family's 10th settlement, or the exact count why not; >= 2 during a session |
| 4 | House restarts a day; releases rolled back by causes outside the House (vendor, backup, site); tick p50; deploys inside a US session | `restarts` 24 in the window (24.0 a day), 7 inside a US session; `deploy_record` 7 releases rolled back, 6 by causes outside the House (backup 6, house 1); 5 of 19 deploys inside a US session (from deploys.jsonl); `tick_p50` interval p50 72.4 s over 1007 ticks (p90 121.1 s); the last tick 134.7 s | <= 6; 0; <= 40 s; 0 |
| 5 | Waiters over 2 h and the longest; merged strategies never born; median life against each desk's evidence clock; displacement share of deaths | `seat_queue` 73 of 78 waiters over 2 h (11 on desks with a free seat), the longest 66.8 h (cards on kalshi-weather); 21 merged strategies waiting (the seat market at 2026-09-25T09:44:54.675Z); `life_vs_clock` median life under the desk's clock on 4 of 9 desks (alpaca-megacaps 4.5 h < 22.3 h, kalshi-open 1.1 h < 2.0 h, kalshi-prices 0.1 h < 46.1 h, kalshi-sports 12.1 h < 21.6 h); `displacement_share` 81% of 83 deaths in the window (90% of 550 lifetime) | 0 with free capacity, longest < 2 h; 0; >= the clock on every desk; < 50% |
| 6 | Real fill rate (fills / orders, 24 h); real entries refused a day; taker entries by probes | `real_fill_rate` 75 of 202 orders filled (37%; kalshi 62 of 89, alpaca 13 of 113); the baseline's rows measure 77 of 858 (9%); `real_refusals` 372 real entries refused (372 a day), 116 in the last session (2026-09-24); the most: allocator.max_event_share 168, insufficient desk cash 84, allocator.real_entry_liquidity 67; `probe_taker_entries` 0 Kalshi taker entries by probes ($0.00), 71 probe entries refused for taking; Alpaca books every fill a taker (7 probe entries, $95.49) | >= 25%; < 30; allowed and measured |
| 7 | Sail runway; the October OpenAI cap; the population ceiling binding on runway | `runway` Sail 8.32 days ($148.21 less $5.00 reserve at $17.20 a day; the House reads 8.32); the OpenAI month 2026-09 at $560.89 of $607.00, October's cap unset; the population ceiling does not bind on runway (128 of 128; 0 population alerts in the window) | >= 5 days throughout; set from funded money at the owner's word; never |

State: Wave 0 is built and reviewed except H4's fixes and H2's review (both running); H3 and Z merged at 10:33Z and ship
in the options run's Deploy V; Deploy A (H2, H4, H5) is set for 20:10Z. Wave 1: F1 (#306) and F2/F4/X2 (#311) built,
C-family building, C-money and F-seats next. **Runway:** the OpenAI month reads $560.89 of $607.00 and the House's line
$50.14 at about $105 a day: the House's own tiers (`game.json` `frontier_reserve`) move it to "earned" under $20 (cheap
research to Sail, unearned roles paused; about 16:30Z) and to "audits" under $8 (about 19:00Z), where it stays until
the month resets on Oct 1 unless the owner raises September's cap. Sail $148.21, 8.32 days. The sports family has 12
real settlements (the look at 15 is 3 away under the live rules).


## Watch log

## Report

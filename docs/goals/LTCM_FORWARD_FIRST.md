# LTCM run: forward first

An autonomous run with no deadline, started and deployed outside US market hours, that closes the
seven gaps measured on the night of Sept 24-25, 2026 and moves the floor toward the north star:
**a swarm of trading agents that trades real money 24/7, improves itself recursively at the pace
of agents rather than humans, and compounds exponentially.**

- **Purpose.** Make forward outcomes the fitness of every engine on the floor (the lab, research,
  the seat market, Merton's lanes and compute), move real capital onto proof within a day instead
  of a week, put the idle Alpaca envelope to work on the desks whose forward record is positive,
  stop the harness from fighting itself (rollbacks, thirty restarts a day, a deploy path
  deadlocked on a vendor outage), spend compute only where yield is measured, and point the
  search at mechanisms with capacity.
- **Method.** The Sept 25 review's numbers are the baseline. One scoreboard is read at T0, every
  four hours and at the end. Every change is built by a builder in its own worktree from one
  brief, reviewed adversarially when it touches money, deployed through the runbook in a wave,
  and verified in its named window on the box. There is no deadline: the run ends when the Done
  list holds, or a row is recorded as blocked with numbers.
- **Where it lives.** This plan; the run record `docs/runs/<T0 date>-forward-first.md`; the
  scoreboard `scripts/gap_scoreboard.py` extended by workstream Z; the memory note
  `ltcm-gap-review-2026-09-25` (the review that produced this plan).

## The owner's direction

Sept 23, 2026:

> "I deeply want to speed up the dynamism of agents moving up and down the levels of the game as
> quickly as possible and aggressively aligned on incentives so star traders can compound and run
> wild and profit exponentially and losing agents die off ... allow for trading to be done on the
> timescale of 24/7 agents not human clocks."

> "being bold and ambitious and not afraid to take risks both in our approach and the agents (im
> fine with volatility and lose on my portfolio to achieve the north star goal), and keeping all
> docs and repo up to date and clean free of any unneeded clutter"

> "The worst thing to me is making no progress and seeing no trading besides these tiny weather
> kalshi contracts."

Sept 25, 2026: a deep dive, a replay of the US session and a 30-minute watch, then "identify the
biggest gaps that remain today to meet our north star goal ... a swarm of 24:7 self recursively
learning at a rapid ai agent pace that reaches exponential profitability", and this plan.

## The seven gaps, with the numbers that prove them

Measured Sept 25, 2026, 01:42-02:12Z (and a 04:06Z reading), on release `main-8d48771e009d`
(Deploy F of the close-the-gaps run plus Merton's #287), money digest `535a7f15`, 128 living.
The queries are read-only sqlite on the House box and `scripts/economics.py`; the memory note
`ltcm-gap-review-2026-09-25` has the method.

| # | Gap | Evidence |
|---|---|---|
| 1 | **No edge with capacity; the unit economics are upside down.** | Lifetime (124.6 h): tracked real profit +$5.16 (+0.51%); real Kalshi +$23.30 net on 112 closed trades, real Alpaca −$0.33 on 5; compute $562 (Luna $177, Astra $231, Sail $140, Jev $14). Last 24 h: about $108 of compute against +$27.35 of real settlements, the best day so far. Two families are proven: sports-central-run-under (real n 9, capacity about $31 a day) and megacaps-chip-demand-relay (practice only, $0.13 a day at its $12.50 practice size). Practice books: −$392.50 on 1,520 closed trades; kalshi-shadow alone −$338.59, the 15-minute crypto desk −$254 and crypto strikes −$175. |
| 2 | **The search is a treadmill.** | 24 h: 2,489 research sessions, 74% abstaining; 558 candidates; 335 replay passes; 389 lab graduates; 118 of 224 lab forward blocks positive (53%). The living population's median W_paper is 1.0003; 33 of 128 are above the 1.01 line; median age 23.8 h; 464 of 513 deaths (91%) were displacement. Four crypto-15m agents born on Sept 24 lived 2, 4, 10 and 10 minutes. The archive places programs by replay fitness on the search tape; forward windows only rank. |
| 3 | **Capital does not follow proof.** | The proven bunt holds a $16.62 stake ($35 equity). Five Alpaca probes hold $125 on crypto-alts-reversion (pooled bound −0.018) and $80 sits in an options probe on a losing family, draining since 19:48Z. No real stock has ever traded: the proven megacaps family's only member has E 1.0018 on 13 practice trades, under the 1.01 line a $12.50 practice position cannot reach. The first family swing needs 15 real settlements (9 now, about 3.5 a day) and starts at $60. |
| 4 | **The self-improvement path is deadlocked and fragile.** | Sail's checkpoint API has answered 503 since 21:31:55Z Sept 24 (73 failed backups by 01:51Z). The watchdog reads each as an error alert and rolled back every release since: the updater at 22:21, 23:00, 23:39, 00:38 and 01:14Z, the owner at 00:02Z. Main is seven pull requests ahead of the floor (#288-#294), the backup fix (#289) among them. The House restarts 24-37 times a day (Sept 20-24), seven of them inside the Sept 24 US session, each killing in-flight research and wakes. The tick runs 37-95 s, the population step 16-50 s of it. At 04:06Z the real Alpaca book is frozen on a $0.0108 cash difference (ten error alerts in the hour), which blocks every Alpaca real entry. |
| 5 | **The seat market is at its ceiling.** | 128 of 128 seats held, 0 displaceable, 58 tested waiters (31 lab graduates, 14 cards, 12 merged Merton strategies, 1 retained candidate), the oldest 60 h. Residents are held as "a winner" at W 1.005. Desk caps: crypto-15m still holds 8 seats on a −$254 practice record while sports (+$164) has one waiter. |
| 6 | **Execution friction eats small edges.** | 694 real orders in 24 h produced 72 fills (10%). In the US session 116 real entries were refused, 22+ by maker-until-proven and about 15 by the 25% per-event cap. In the watch the over-under family's taker entry was refused although its taker record is +$30.75 on 3. Real Alpaca crypto: 148 orders, 6 fills, 27 cancels. Weather favourites measure $0.24 a day of capacity. |
| 7 | **Runway.** | The September OpenAI month reads $522.77 of $607 and resets Oct 1; the House line has $84 left. Sail holds $152 at about $16 a day (9 days). Compute-follows-profit is capped at funded money, so it buys nothing today. |

## The scoreboard (workstream Z)

`scripts/gap_scoreboard.py`, extended by Z with the rows below, prints these at T0, every four
hours and at the end, from a snapshot of the House (`--take`). The run is judged on the movement.

| # | Metric | Baseline (Sept 25 04:06Z) | Target at the end |
|---|---|---|---|
| 1 | Real settled profit a day (24 h) against compute a day (24 h); proven families and each one's capacity at its real size | +$27 vs $108; 2 families ($31/day, $0.13/day) | compute ≤ 2 × real settled profit, or ≤ $60/day while no family swings; ≥ 3 proven families, capacity measured at 1×, 2× and 4× the stake |
| 2 | Forward-positive share of the last day's graduates and newborns (lab forward windows, first practice day); living median W_paper; agents above the 1.01 line | 53%; 1.0003; 33 of 128 | ≥ 60%; ≥ 1.005; ≥ 50 |
| 3 | Real dollars on proven families / on unproven (stake); the first family swing; Alpaca real stock agents (ever) | $16.62 / $254; none; 0 | proven ≥ unproven; the swing reached at the sports family's 10th settlement, or the exact count why not; ≥ 2 during a session |
| 4 | House restarts a day; releases rolled back by causes outside the House (vendor, backup, site); tick p50; deploys inside a US session | 24-37; 6 since 21:16Z Sept 24; 37-95 s; 5 on Sept 24 | ≤ 6; 0; ≤ 40 s; 0 |
| 5 | Waiters over 2 h and the longest; merged strategies never born; median life against each desk's evidence clock; displacement share of deaths | 58 at 60 h; 12; 23.8 h; 91% | 0 with free capacity, longest < 2 h; 0; ≥ the clock on every desk; < 50% |
| 6 | Real fill rate (fills / orders, 24 h); real entries refused a day; taker entries by probes | 10%; 116 in one session; 0 allowed | ≥ 25%; < 30; allowed and measured |
| 7 | Sail runway; the October OpenAI cap; the population ceiling binding on runway | 9 days; unset; no | ≥ 5 days throughout; set from funded money at the owner's word; never |

Each row keeps the function that computes it, as the scoreboard does today, and the four-hourly
readings go into the run record.

## Where the floor stands at plan time (Sept 25, 2026, 04:06Z)

- **Release** `main-8d48771e009d`; grant `earned-live-20260921` active on money digest `535a7f15`
  (constitution `38a57fe9`); 128 living, 517 dead; tick 78 s; the real Alpaca book frozen
  ("cash differs by 0.0108"); `main` at `3defc0d` (#294), seven PRs ahead of the floor.
- **Bands:** 1 Kalshi bunt (meriwether-h2d625d, the proven sports family), 6 Kalshi probes, 6
  Alpaca probes (5 crypto-alts, 1 options draining), 112 on practice, 3 in replay. Envelope:
  Kalshi $540.45 with $120.85 committed, Alpaca $500 with $205.94 committed. Floor real P&L
  +$10.52 marked; throttle off.
- **Seats:** 58 waiters, displaceable 0; caps by desk: sports 19, index-etfs 18, weather 17,
  megacaps 16, crypto-alts 16, crypto-majors 12, crypto-15m 8, open desks 8 each, options 8,
  prices 8, strikes 6, sports-props 6, attention 4. Population 128 at the ceiling; Sail runway 9.1
  days.
- **Compute:** gateway month $522.77 of $607 (settled $517.19); House OpenAI line $84.17; Sail
  $152.12 at $16.17 a day; Jev $16.21 of $42. Research 2,489 sessions a day at $48.62; consultant
  $28.72 for 51 answers; engineer $12.59; architect $9.55; teacher $3.98 for 137 lessons; foundry
  $2.53.
- **The deploy path:** every release since 21:16Z Sept 24 rolled back by the backup error;
  `scripts/floor_box.py deploy` skips the post-promotion watch (`--watch-seconds 0`, the canary
  still runs) whenever the loop is not running, so `floor_box.py stop` then `deploy` promotes
  without the rollback. That is the first act of the run if the outage persists.
- **Re-baseline at T0.** The run may start hours or days after this was written. Measure again
  before building: if a defect below no longer reproduces, keep its regression test and its
  invariant and skip the fix.

## What "closer to the north star" means when the run ends

1. **Forward outcomes are the fitness.** The lab breeds, places and graduates by forward growth
   where a lineage has one; research runs on triggers and pays for outcomes; the seat market keeps
   residents by forward record and seats newcomers by forward score; every Merton lane and every
   compute line is throttled by its measured yield per dollar.
2. **A proven mechanism compounds within a day.** The sports family swings at its 10th real
   independent settlement and doubles every 10 winning ones, held by measured capacity; a proven
   family's member trades real money on the family's proof; probes may take the price.
3. **Idle capital works.** Stock and ETF desks hold real probes at $50 in a session; the options
   probe is drained; probes never sit on zero-edge families.
4. **The harness is quiet.** Releases are never rolled back by a vendor's outage; the House
   restarts at most six times a day and never inside a US session; the tick is under 40 s; a real
   book never freezes on cents.
5. **The seat market clears.** Every tested newcomer has a seat within two hours where its desk has
   capacity; merged strategies are born; desk capacity follows the desks' forward records.
6. **The search looks for capacity.** Every foundry card names its capacity; proven families get
   more members on disjoint events; the open desks grow.
7. **Compute follows yield.** Lanes with no measured lift are paused; the unit economics row moves
   toward parity.
8. **Every bug observed is fixed with a test, docs and repo are current, and the report is delivered.**

## Principles

1. **Forward first.** Replay admits; forward outcomes rank, breed, seat and stake. Nothing a
   development tape says outranks a forward record once there is one.
2. **Proof at the family level, money at the agent level** (unchanged). A mechanism is proven by
   its family's pooled forward record over independent events; stakes sit on agents.
3. **Evidence stays honest.** Practice fills stay conservative; the sealed holdout stays sealed; no
   agent grades its own work; no trade is forced; no evidence is fabricated or back-filled.
4. **Bold is allowed; blind is not.** Money rules move only inside the closed table below, each
   change recorded with its evidence and re-ratified within a minute of promotion.
5. **The harness serves the floor.** No deploy inside a US session; releases are trains, not
   drips; a vendor's outage is never the floor's failure.
6. **Compute buys evidence.** Every dollar of model spend is attributed to a lane and judged by
   forward blocks per dollar; a lane that buys none is paused until profit.
7. **The envelope, the gateway and the throttle are the whole risk budget:** $517.75 Kalshi
   (grown by realized profit), $500 Alpaca, the $75 order cap, the day caps, the kill switch, the
   throttle, no leverage, no shorts, no written options.
8. **A merged PR is not a deployed feature.** Verify on the box, in the change's window.

## Clock, budget, authority

**The clock.** No deadline: the run ends when the Done list holds. The first action writes T0
(`date -u`) into the run record `docs/runs/<T0 date>-forward-first.md` and commits it; T0 anchors
the scoreboard and the four-hourly progress notes. A context reset does not end the run.

**The first hour's decisions**, each recorded before Wave 0's builders launch:

1. **Is the deploy path alive?** Read `deploys.jsonl` and the last `ops.deploy` rows. If the
   newest release was rolled back on a backup error and Sail's checkpoint API still answers 503,
   run H1 first: `python3 scripts/floor_box.py stop --reason "ship the backup fix"`, then
   `python3 scripts/floor_box.py deploy` from `~/Work/ltcm-deploy` at `origin/main`. No money
   rule changes in the pending PRs, so no ratify. Verify: `ops.started` on the new release, the
   backup alert every 30 min doubling instead of every 3 min, the updater's next attempt not
   rolled back.
2. **Is a real book frozen?** Read `health.json` `books`. A real book frozen on a sub-dollar
   difference is H4's case: record the amount and the venue activity that explains it; H4 ships in
   Deploy A. Until then the real Alpaca probes cannot enter, which the record says.
3. **Can this session ratify?** `python3 scripts/live_trading.py --ratify earned-live-20260921`
   against the running digest writes nothing when the policy is unchanged. If the permission
   check blocks it, no deploy in this run may change the money digest; money-rule changes wait on
   a pushed branch with the owner's commands in the report.
4. **Compute truth.** The gateway's month, the House's OpenAI line, Sail's balance and burn. One
   push notification to the owner with the owner steps; then carry on.
5. **The money set of Deploy B** is fixed from the evidence in this plan (M1-M5 and C8 below),
   one digest change and one ratify. Deploy A carries at most H4's constitution key. A third digest
   change is allowed only for a defect in the money path found in the watch.
6. **One owner per protected file per wave**, at most four builders at once, adversarial
   three-lens reviews of money code in separate `*/review` worktrees, the parallel test runner on
   the tmpfs (recreate `ptest/run.sh` from the Sept 24 record: about 5 minutes for both suites),
   CI as the source of truth.

**The owner's steps** (sent once at T0, never waited on):

- **Sail:** the checkpoint outage (a support ticket if it lasts a day), and a top-up or
  auto-recharge before the balance reads 5 days at the measured burn. The run keeps a 1.5-day
  floor plus the House's `sail_reserve_usd`, cutting growth before anything that trades.
- **OpenAI:** October's `FRONTIER_MONTH_USD` and `FRONTIER_MONTH_MAX_USD` in
  `gateway/wrangler.jsonc` from the funded balance, and `scripts/campaign_topup.py` for the House
  line; the run aligns caps up to funded money only when the owner states the figure.
- **Keyed hosts:** `api.the-odds-api.com` (paid; the sports family is the one proven real family
  and its capacity is what this feed would grow) and `api.eia.gov` (free key; `kalshi-prices`).
  Place the keys in the box's `.env`, run `python3 scripts/floor_box.py hosts --add <host>` from
  `~/Work/ltcm-deploy`; the recorders read them within five minutes.
- **Level-3 options:** not this run (workstream O of the close-the-gaps plan).

**Budget.** Funded means a balance read from the provider at T0 or later, or one the owner states
in the session. Floors that hold throughout: OpenAI keeps at least $8 in the gateway month for
audits; Sail keeps 1.5 days at the measured burn plus the reserve. The run creates no new Sailbox.

**Authorized:**
- Implement, test, commit, push, open and merge PRs to `main` of this repo and of `personal-site`
  with CI green. Builders in their own worktrees; the main session merges.
- Change the money rules inside the closed table below, re-ratifying `earned-live-20260921`
  within a minute of each promotion that changes the digest. At most two digest changes, a third
  only for a money-path defect found in the watch.
- Change the risk-free rules on recorded evidence with no re-ratification: `ladder.replay`,
  `ladder.paper_death`, `league/turbo.json` (population 64-128 while Sail's runway stays over 1.5
  days), `league/game.json` within `bounds`, `merton_bounds` and `lab_bounds` (new keys need new
  bounds and a `league.ci` check), `league/niches.json` seats, the operating dials in
  `league/config.json`.
- Deploy: owner deploys (`scripts/floor_box.py deploy` from `~/Work/ltcm-deploy`), gateway
  deploys (`npx wrangler deploy --tag <sha>` in `gateway/`), site deploys (`npm run build && npx
  wrangler deploy` in `~/Work/personal-site`). Each with its tests green, none inside a US
  session (13:25-20:05Z on a trading day) except a rollback.
- Trade real money on Kalshi and Alpaca inside the envelope; volatility and losses accepted.
- Move collateral between Kalshi exchange shards (`league/shards.py`; `scripts/kalshi_shard.py`
  by hand if the funder is blocked).
- Spend funded compute and align caps up to funded balances.
- Stop in an emergency, then record why and tell the owner at once: `scripts/gateway_admin.py
  kill`; `league.watchdog rollback`; `npx wrangler rollback`; `allocator.enabled: False` with an
  owner deploy and a re-ratify.
- Tidy the repos under D.

**Money-rule bounds for this run.** The table is the whole list; every other money rule stays as
it is. New constitution keys are allowed only to carry a row of this table, and `book.py` reads
any book-side rule through a constitution key, so the digest moves and the grant is re-ratified.

| Rule | Now | Allowed range | Why |
|---|---|---|---|
| M1 `allocator.family_swing.min_real_settlements` | 15 | 10-15 (`entry_every` 5 and `entry_confidence` 0.9 unchanged; the lopsided loss-rate gate applies at every look) | Gap 3: the proven family reaches its entry look in a day, not three; the Sept 24 simulation put the edgeless entry near 20% at every 5th settlement at 90% |
| M2 `allocator.real_entry_liquidity` | `maker_unless_family_taker_positive` | `probe_may_take`: a PROBE (the smallest stake) may enter as a taker up to `position_share_event` of its stake; bunts and swings stay maker-unless-proven; the taker proof counts from `taker_proof_min` 5-10 pooled taker events with the bound above zero (10 now) | Gap 6: pocket change may take the price; a taker record cannot be earned by an agent that may not take |
| M3 `allocator.proven_family_member` (new) | none: every agent needs E ≥ 1.01 | a member of a PROVEN family with ≥ 1 closed practice trade and W_paper ≥ 1.0 is seated as a bunt on the family's proof, best W first, up to `proven_family_members` seats on real money | Gap 3: megacaps-chip-demand-relay is proven (n 13, bound +0.001) and its member sits at E 1.0018; no real stock has ever traded |
| M4 `allocator.probe_bunt_usd.alpaca_equity` (new class key beside `probe_bunt_usd.alpaca`, Kalshi $10 / Alpaca $25 now) | $25 | $25-60 for stock and ETF programs (crypto stays $25; options `option_bunt_usd` $80) | Gap 3: a $25 fractional stock probe at a 2 bps haircut cannot move W, and capacity measured at $12.50 understates liquid names |
| M5 `allocator.family_probe.reseat` | `gain_since_demotion`: positive over 6 blocks | `bound_since_demotion`: the family's record since the demotion has a one-sided 80% lower bound above zero over ≥ 6 active blocks | the Sept 24 report's decision 1: a zero-edge family flipped back in on +0.0113 over 375 blocks |
| C8 `allocator.family_key` (new) | the `family` label a birth carries | `mechanism`: a program whose code differs from its parent's beyond PARAMS, or whose venue, series or symbols differ, founds a new family (its lineage kept for the graveyard); labels already born are re-keyed once at deploy | the Sept 24 report's decision 2: 98 children carried a family name whose mechanism they did not run |
| H4 `allocator.real_book_dust_usd` (new; `book.py` reads it) | a real book freezes on any difference | $0.25-1.00: a real book's cash difference under it that a venue fee activity, an in-kind fee or rounding explains is booked as dust on the House row with an error alert naming it, never a freeze; over it the freeze stays until the owner clears it | Gap 4: the real Alpaca book froze on $0.0108 at 04:06Z Sept 25 and on the OCC fee on Sept 24 |

**Not authorized:**
- Deposits, withdrawals, transfers between venues; enlarging the grant; raising any cap above
  funded money; changing the order and day caps.
- Disabling the kill switch, the gateway caps or the throttle (the run may release a kill it
  engaged itself, once the cause is fixed and verified).
- Widening the gateway's `VENUE_PATHS`, or weakening #187's refusals.
- Secrets, venue account settings, `wrangler secret put`, `scripts/place_secrets.sh`, the box's
  `.env`. Record what is needed as an owner step.
- Leverage, shorting, writing options, multi-leg option orders on either account.
- A real-money or practice order that no agent's intent produced. No test orders.
- Forcing trades, planting intents, fabricating or back-filling evidence, hand-editing the ledger,
  the books, the lab store, holdout budgets or the history store.
- Loosening a sealed verifier: the holdout seal and its ration, deep replay, the auditor, the
  practice fill model.
- Skipping the watchdog's canary. H1 skips only the post-promotion watch, once, for the reason
  on record.
- Deleting unmerged or unpushed work.

## The order of work (no deadline)

A dependency order, not a schedule.

1. **Phase 0.** T0, the baseline scoreboard, the first hour's decisions (H1 if needed), the owner
   steps sent, the watch loop started. Launch together: the scoreboard analyst (Z), the Wave 0
   builders (H2-H5), the cleanup agent (D).
2. **Wave 0** builds, reviews and fixes: H2 no rollback on a vendor's outage, H3 the release
   train, H4 the real book's dust, H5 the tick.
3. **Deploy A** (owner deploy; ratify within a minute if H4's key moves the digest: change 1 of 2).
   Watch its first hour while Wave 1 builds.
4. **Wave 1** builds: F1 the lab's forward fitness, F2 research on outcomes, F3 the seat market's
   forward tenure and desk capacity, F4 lanes measured; C1-C8 the money set.
5. **Deploy B** (owner deploy; ratify, digest change 2 of 2). The swing clock, the proven-family
   members and the equity probes are verified in their windows.
6. **Wave 2** builds: S the search for capacity, Y compute follows yield, X execution, W the site.
   Unprotected fixes ship through the updater's train.
7. **Deploy C**, the last planned owner deploy.
8. **The watch:** at least three hours after the last deploy, then one full US session
   (13:30-20:00Z) watched every 30 minutes with no deploy, then the final scoreboard, docs, memory
   and the report. If the watch finds a row short of its target for a reason the run can still
   fix, build again: another wave and a fourth deploy are allowed, outside the session.

- **Deploys happen outside US market hours.** A wave that finishes inside a session waits for
  20:05Z. Verification during a session uses the markets that trade around the clock and the
  stock desks' own wakes; the equity probes (M3, M4) are verified in the first session after
  Deploy B.
- **A build cycle is about two hours** including the adversarial review; CI 7-20 minutes; the
  canary and watch about 15 more.
- **Progress notes.** Every four hours the run appends a scoreboard reading and a one-paragraph
  state to the run record.

## Workstreams, in priority order

### Z. The scoreboard (analyst; T0, every four hours, and the end)

- Extend `scripts/gap_scoreboard.py` with the seven rows above (unit economics from the ledger's
  `book.settle` real rows and the `ops.budget` yield rows plus `provider.request` and
  `merton.pass` costs; forward-positive share from the lab's `forward` table and the first
  practice day's `eval.block` rows; restarts from `ops.started`; rollbacks from `ops.deploy`; tick
  p50 from `health.json` `tick_steps`; fill rate from `book.order` and `book.fill` real rows;
  waiters and caps from `health.json` `seats`; runway from the campaign block). Keep the old rows;
  print `--markdown` for the record.
- Measure the evidence clock per desk as today (`evidence_clocks`) and print median life per desk
  beside it, so row 5's target is read per desk.
- Acceptance: the T0 and final readings in the run record, every number naming its function.

### H. The harness (Wave 0, Deploy A)

- **Evidence:** six releases rolled back on backup errors since 21:16Z Sept 24; 24-37 restarts a
  day; seven inside the Sept 24 session; the tick 37-95 s with the population step 16-50 s; the real
  Alpaca book frozen on $0.0108 at 04:06Z Sept 25 (ten error alerts in the hour) after freezing on
  the OCC fee on Sept 24.
- **H1. Ship the stuck head** (Phase 0, if the outage persists): the stop-then-deploy path above,
  once, recorded with the release id and the verdict. It ships #289 (the backup backoff and the
  alert's `began_at`), the docs of #292, and Merton's #288, #290, #291, #293, #294.
- **H2. A vendor's outage never rolls back a release** (`league/watchdog.py`, protected;
  `league/house.py`, `league/backup.py`). The watchdog classifies error alerts: an alert whose
  `what` is `backup`, `publish` or another call to a service outside the House's process (Sail's
  API, the site, a data host) is an environment alert, counted in the reading's `detail` and never
  a rollback reason; House failures (a tick stall, a frozen real book the release caused, an
  exception in the loop, a health failure) still roll back. The House raises the backup outage as
  one error alert when it begins and a warning at each backoff step; the graceful shutdown waits
  at most 5 s for a backup in flight (73 s on Sept 25). Regression tests: a release watched during
  a backup outage promotes; a release whose first tick raises an exception still rolls back.
- **H3. The release train** (`league/updater.py`, protected): the updater ships main's head at
  most once every 4 hours (`release_train_hours`, 2-6), never between 13:25Z and 20:05Z on a day
  the House's session calendar calls a trading day (the same source as `_shut_session`), and
  never within 30 minutes of the last `ops.started`; a head that changes a protected path is
  refused as today. Owner deploys in this run are waves, four at most. `health.json` counts
  restarts in the last day and the watch prints it. Acceptance: ≤ 6 restarts a day over the
  watch; 0 inside a session.
- **H4. A real book never freezes on cents** (`league/book.py`, protected; the constitution key
  `allocator.real_book_dust_usd` in the table): a real book's cash difference under the key that a
  venue FEE activity, an in-kind fee or rounding explains is booked on the House row as dust with
  an error alert naming the amount and the explanation; a larger or unexplained difference keeps
  the freeze for the owner. Real option fills pay the OCC clearing fee at the fill, as #278 does on
  practice (the Sept 24 report's decision 3: one real fill confirmed the timing). Three-lens
  review before merge; regression tests for both directions of the line.
- **H5. The tick under 40 s** (`league/house.py`): the population step (seat caps, waiters, the
  displacement scan) computed once every five minutes and read from a cache between, the
  `poll:kalshi-shadow` step skipped when the shadow book has no working order, the hypotheses
  step off the tick. Read `tick_steps` before and after; acceptance: p50 ≤ 40 s over an hour with
  128 living.
- **H6. Sessions survive restarts:** verify that research sessions in flight at a restart resume
  (`durable_research` in `health.json`) and count the ones that did not in the watch; a session
  lost to a restart is a warning that names it.

### F. Forward first (Wave 1, Deploy B)

- **Evidence:** median W_paper 1.0003 across 128 living after 14,801 research sessions and 15,066
  lab candidates; 53% of lab forward blocks positive; 74% of research sessions abstain; the
  archive places by replay fitness (`lab.py` `_place`) and forward windows only rank; 91% of
  deaths are displacement at a median 24 h life; 12 merged strategies never born; crypto-15m keeps
  8 seats on a −$254 practice record.
- **F1. The lab breeds and graduates on forward growth** (`league/lab.py`, protected). A lineage
  with at least `forward_min_active_blocks` (3) forward-window blocks is placed in the archive and
  ordered by its forward growth per block; search fitness places only lineages without a forward
  record. A lineage whose latest forward window is negative over 6 blocks is neither bred nor
  graduated until a later window is positive. `reserved_share` 0.5 → 0.33 for parameter children
  (mechanism children first; `lab_bounds` 0.33-0.75). Graduation needs a positive forward window
  where the lab can build one, or a mechanism change (E2's rule) where it cannot. Acceptance:
  forward-positive share of graduates ≥ 60% in the final scoreboard; LLM share ≥ 50%.
- **F2. Research runs on outcomes** (`league/research_gate.py`, `game.json` `research`). Clock
  and heartbeat runs (145 of 441 runs in the Sept 24 session; the `abstain_lock_profile` "state
  healthy" passes at $0.005-0.008 each) go only to an agent on real money that holds a position or
  met a refusal since its last session; everyone else waits for a trigger (a fill, a settlement, a
  refusal, an active block, a lesson naming it). The heartbeat `max_skip_hours` (24 now) becomes
  72 for practice agents; a real agent keeps 24. A session that abstains three times in a row on a
  practice agent pauses that agent's research until its next fill. Acceptance: sessions a day −40%, candidates a day unchanged or up,
  research dollars per positive forward block halved (the yield row).
- **F3. The seat market's forward tenure and desk capacity** (`league/house.py`).
  - *Quotas:* a merged Merton strategy (waiter class `strategies`) is born within an hour: each
    desk keeps one seat reserved for that class (`strategies_reserved_seats`), or displaces its
    weakest never-traded resident past its fair chance. The 12 waiting now are the test case.
  - *Expiry:* a waiter over 24 h expires into the lab archive with its forward record kept (a
    card or graduate is a lab candidate again, never lost); the watch prints expiries by rule.
  - *Desk capacity follows the forward record:* a desk whose pooled forward growth over the last 7
    days is negative on ≥ 100 active blocks loses 2 seats a day to a floor of 4 (crypto-15m first);
    a desk whose record is positive gains 2 a day to its cap (sports, weather, megacaps); the
    league's population stays under the ceiling. Seats freed this way go to the waiters of desks
    with positive records, first of every class.
  - *Tenure:* a resident that has traded is displaced only by a newcomer whose forward score beats
    its record (as today), and never before its desk's evidence clock has run from its first fill;
    the fair chance stays `max(1 h, min(clock, grace))` for the never-traded.
  - Acceptance: 0 waiters over 2 h on desks with free capacity; the 12 merged strategies born;
    median life ≥ the desk clock on every desk; displacement under 50% of deaths.
- **F4. Every lane is measured** (`league/merton.py`, `league/yield_ledger.py`, `game.json`).
  The hourly yield row already prices each lane; add the forward lift: for the teacher, agents
  that read a lesson against those that did not (by agent-id parity) on forward growth over 3
  days; for the consultant, the agent's next 6 blocks against its previous 6 (a `consult.outcome`
  row) and a consult that produced no candidate or edit within 2 sessions doubles that agent's next
  consult price; for the engineer, repairs verified per dollar (22 lifetime for $26.59). A lane with
  no measured lift by the end is added to `merton.paused_until_profit` (bounds allow the teacher).
  Acceptance: consultant dollars per positive forward block ≤ research's, or the lane paused.

### C. Capital follows proof (Wave 1, Deploy B; the money owner)

- **Evidence:** $16.62 on the proven bunt against $254 on probes; the sports family at 9 of 15;
  the megacaps family proven on practice with its member at E 1.0018; five Alpaca probes on a
  bound of −0.018; the over-under taker entry refused on a +$30.75 on 3 record; 98 mislabelled
  children.
- **C1. The swing at 10** (M1): `family_swing.min_real_settlements` 10; the entry look stays at
  90% every 5 settlements with the loss-rate gate. The auditor's packet for the entry is prepared
  at the 8th settlement (`audit.pre_pack`, a new `game.json` key with a bound), so the look at 10
  is not delayed by the audit.
- **C2. Probes may take** (M2): `real_entry_liquidity: probe_may_take`; `taker_proof_min` 5; the
  book's refusal text names the band. Verify on the first probe taker entry.
- **C3. A proven family's members trade on the family's proof** (M3): the allocator seats, best
  W_paper first, up to `proven_family_members` (4 → 6, a risk-free dial within its bounds) members
  of a proven family with ≥ 1 closed practice trade and W_paper ≥ 1.0 as bunts. mcentee-hddb4ae is
  the first case; the sports family's practice members the second.
- **C4. Equity probes at $50** (M4): `probe_bunt_usd.alpaca` by asset class; the position cap
  stays half the stake; the gateway's $68.18 Alpaca cap holds.
- **C5. Re-admission by bound** (M5): `family_probe.reseat: bound_since_demotion`.
- **C6. Capacity at the real size** (`league/families.py`): a family's capacity row reads the real
  book's fill rate at the current stake once it has bid 10 markets there, and reports the fill
  curve at 2× and 4× the stake; the swing's `capacity_fill_ratio` reads the same curve.
- **C7. Members on disjoint events** (`league/house.py`): a proven family's members on real money
  split their desk's events by a stable hash of the event ticker, so each settlement is one
  observation for the pooled record (the House's births into the sports family on Sept 24 traded
  the same games and added weight, not settlements). Verify: the family's `real.n` rises with
  members.
- **C8. Family = mechanism** (the table's C8; `league/hypotheses.py` `_mechanism`,
  `league/families.py`, `league/house.py` births): a child whose code differs beyond PARAMS, or
  whose venue, series or symbols differ, founds a new family keyed by that mechanism; existing
  labels are re-keyed once at deploy with a `family.record` row per family that changes; the
  graveyard keeps lineage. Three-lens review: the proven families' records must be reproduced to
  the cent after re-keying.
- **Acceptance:** at the end every real agent is a probe, a proven family's bunt or a swing; the
  sports family's swing clock reads its look at 10; ≥ 2 Alpaca real stock agents in the first
  session after Deploy B, or the exact numbers why not.

### S. The search for capacity (Wave 2, Deploy C)

- **Evidence:** the proven real family caps at $31 a day; weather favourites at $0.24; the lab's
  archive has 82 cells over 12 hand-picked desks; 21 of 57 families have positive pooled growth,
  most on pennies of capacity.
- **S1. The foundry brief `foundry-2026-09-25.1`** (`league/hypotheses.py`): every card names its
  capacity estimate (markets a day in its band × the size at which fills halve × profit per
  settlement) and is refused under $5 a day; half of the calls go to the proven families' desks
  (sports, megacaps) as mechanism variants on disjoint events, three tenths to model-versus-market
  on allowed feeds (the weather ensemble transfer card already in `first_transfer`, EDGAR
  earnings for megacaps, DVOL and funding for crypto majors), two tenths exploration. Cards for
  desks the search closed stay closed.
- **S2. The open desks grow:** `kalshi-open` and `alpaca-open` 8 → 12 seats (`niches.json`), and
  a card that spans two desks is replayed on both tapes.
- **S3. The Odds API** when the owner places the key: the sports recorder goes live and the
  foundry's sports cards may read consensus probabilities; until then the family's capacity is
  what it is, and the report says so.
- **Acceptance:** ≥ 3 proven families in the final scoreboard, each with capacity at 1×, 2× and
  4× the stake; every card of the run carries a capacity estimate.

### Y. Compute follows yield (Wave 2)

- **Evidence:** $108 a day against +$27; research $48.62 for 558 candidates and 182 positive
  blocks; consultant $28.72 for 51 answers with no measured lift; the population ceiling follows
  Sail runway.
- **Y1. Lane throttles** (`game.json` `economy.lane_throttle`, new, with bounds): a lane whose
  24-hour dollars per positive forward block exceed 3× the best lane's is halved (cadence or
  budget) at the next hourly yield row, floors: one research session an agent a day, the engineer's
  repairs of real-money defects never throttled, audits never throttled. The throttle writes an
  `ops.budget` row naming the lane and the ratio.
- **Y2. The unit-economics row on the site and in health:** compute a day against real settled
  profit a day, so the owner reads parity from the page.
- **Y3. Runway:** the population rule is unchanged; the run sets October's House line only at the
  owner's stated figure; Sail growth stops at 1.5 days of runway as today.
- **Acceptance:** row 1's compute line ≤ $60 a day while no family swings, or ≤ 2× the real
  settled profit when one does.

### X. Execution (Wave 2)

- **Evidence:** 72 fills on 694 real orders in 24 h; 116 real refusals in one session; refusals
  pull research passes forward.
- **X1.** Each agent's snapshot carries its own fill rate and median time to fill on the real book,
  and the research brief asks for a requote rule where the rate is under 25%; M2 lets probes take.
- **X2.** A refusal triggers research only once per agent, reason and day
  (`research_gate` trigger dedupe); the count of refusals a day is on the watch.
- **X3.** The 25% per-event cap and the longshot floor stay; the refusal text names the band, the
  cap and the free room, so the agent's next order fits.
- **Acceptance:** real fill rate ≥ 25% on probes over the watch; refusals a day under 30.

### W. The site (Wave 2; `~/Work/personal-site`)

- The capital page gains a flywheel strip: compute a day, evidence a day (positive forward blocks,
  graduates, proofs), real profit a day, restarts a day; each proven family's swing clock and
  capacity at the real size; the schema first, the site deployed before the publisher.
- Acceptance: the strip live within a minute of the first publish under Deploy C.

### D. Docs and a clean repo (throughout)

- README's Status entry for the run and its known limits; the runbook's grant and digest history;
  operations for H2-H4, F3's quotas and expiries, Y1's throttle; `league/README.md` rows for the
  touched modules; the run record; the memory note.
- Merged worktrees and branches removed; unmerged work pushed, never deleted; `~/Work` free of
  stale session directories the run created.

### B. Bugs

Every bug observed is fixed with a regression test and an invariant or a warning that would have
caught it. Known at plan time: the real Alpaca book's freeze on cents (H4); the backup outage's
rollbacks (H1/H2); the population step's cost (H5); 98 mislabelled children (C8); research
sessions lost to restarts (H6); `kalshi-open` offered markets on 9 wakes in an hour with no intent
(read the members' thoughts before judging).

### O. Level-3 options: not this run

The options family is losing (27 practice blocks, −0.598); krasker-14 drains. The design stays on
draft #210.

## Risk-free dials (defaults; tune from evidence within the bounds)

| Key | Default | Bounds | Why |
|---|---|---|---|
| `turbo.json` `max_population` | 128 | 64-128 | Sail's floor holds |
| `game.json` `economy.proven_family_members` | 4 → 6 | 1-8 | C3, C7 |
| `game.json` `lab.reserved_share` | 0.5 → 0.33 | 0.33-0.75 | F1 |
| `game.json` `lab.max_births_per_hour` | 6 | 1-12 | |
| `game.json` `research.gate` clock and heartbeat (F2) | real money with a position or a refusal only | as F2 | |
| `game.json` `merton.paused_until_profit` | architect, toolsmith, operator, designer | any subset incl. teacher | F4 |
| `game.json` `economy.lane_throttle` (new) | 3× | 2-5× | Y1 |
| `updater` `release_train_hours` (new) | 4 | 2-6 | H3 |
| `niches.json` seats | as now; open desks 12 | follow forward records (F3) | |
| `house.json` desk evidence clocks (measured) | per desk | ≥ 12 h | F3 |

## Deploys and ratification

The runbook is the north-star plan's ["Deploys and ratification"](LTCM_NORTH_STAR_BUILD.md#deploys-and-ratification-the-runbook),
with these specifics:

- Deploy from `~/Work/ltcm-deploy` at `origin/main` with the `deploy_ratify.sh <log> 1` wrapper
  (recreate it from the Sept 24 record if the scratchpad is gone): the ratify runs the moment
  the log says `promoted`.
- H1's stop-then-deploy is used once, for the deadlock on record; every later deploy runs the
  watch. If a deploy's watch meets a running House's in-flight environment error before H2 ships,
  retry right after a failure row and say so in the record.
- Protected work stays on its wave's integration branch and merges to main minutes before its
  deploy; a protected merge on main blocks the updater for everything after it.
- No deploy between 13:25Z and 20:05Z on a trading day, except a rollback.
- Read CI's job states before `gh pr merge`; a cancelled job is not a pass.
- After every promotion: health fresh, no real book frozen, the grant active on the expected
  digest, the first ticks complete, the lab's first batch, restarts counted.
- Gateway and site deploys are separate and never ride the House release; the site deploys
  before the floor publishes new fields.

## Watching

- `scripts/floor_watch.py --since <ISO>` every 15 minutes into the run record's watch log; the
  events monitor for band moves, family state changes, audits, real fills, deaths, births by class,
  lab batches, restarts, error alerts by class (House or environment).
- Through one full US session after Deploy B: stock and option wakes, intents, orders, fills and
  refusals every 30 minutes; the first equity probe's fills.
- Read-only box queries only; the House box has 1 vCPU.

**When each change can be verified:**

| Change | Deploy | Window | What counts |
|---|---|---|---|
| H1 | Phase 0 | 10 min | the new release's `ops.started`; the backup alert at 30 min then doubling; the updater's next release not rolled back |
| H2 | A | the next backup failure | a reading that counts an environment alert and promotes |
| H3 | A | 4 h | at most one updater release; none in the session; restarts a day on the watch |
| H4 | A | the next fee activity | a dust row on the real book with its alert; no freeze under the key |
| H5 | A | 1 h | `tick_steps` p50 ≤ 40 s |
| F1 | B | 2 h | archive rows ordered by forward growth; a graduate with a positive window; the forward-positive share rising |
| F2 | B | 2 h | `research.gate` clock/heartbeat runs only on real agents with a position or refusal; sessions a day down |
| F3 | B | 2 h | the 12 merged strategies born; expiries by rule; crypto-15m's cap falling; no waiter over 2 h with free capacity |
| F4 | B | 24 h | `consult.outcome` rows; the teacher's lift row; a lane paused or kept with its number |
| C1-C5 | B | the sports family's 10th settlement (about a day); the first session for M3/M4; the next probe taker entry | the swing clock's look at 10; a megacaps bunt on the family's proof; an equity probe at $50 in the session; a probe's taker fill |
| C6, C7 | B | 24 h | capacity at 2× and 4×; the family's `real.n` rising per member |
| C8 | B | at deploy | re-keyed families with records reproduced to the cent |
| S1-S2 | C | 2 h | cards with capacity estimates; a spanning card replayed on two tapes |
| Y1 | C | the next yield row | a throttle row when a lane exceeds 3× |
| X1-X3 | C | 6 h | fill rate on probes; refusals a day; deduped triggers |
| W | C | 1 min after publish | the flywheel strip on blakewoods.us/capital |

## Lessons to read before starting

From Sept 22-25. The full runbook is in the north-star plan.

- **Ratify at promotion, not later.** A late ratification once stopped the floor for 9 minutes.
- **Protected paths skip the updater**: `gateway/`, `campaigns.py`, `lab.py`, `book.py`,
  `allocator.py`, `evaluator.py`, `parameters.py`, `constitution.py`, `resolution.py`,
  `updater.py`, `watchdog.py`, `ci.py` need an owner deploy.
- **A deploy's watch reads the House being replaced.** The old House's in-flight errors are the
  new release's until H2; the previous run lost six releases to it.
- **The owner deploy skips the watch only when the loop is stopped** (`floor_box.py` starts the
  watchdog with `--watch-seconds 0` then); the canary still runs.
- **`date -u` before every time written**; times from the box for event windows.
- **Local tests on the /tmp tmpfs run ~25× faster** than on `~/Work`'s disk; one suite at a
  time; /tmp is 3.8 GB and parallel suites filled it once.
- **Never remove a builder's worktree before its report**; never `pkill -f "unittest discover"`;
  never chain a deploy on grep's exit code; commit each merge before the next; `rerere` off for
  overlapping merges; never `git add -A` after a failed merge.
- **`~/Work/ltcm-deploy/.data` is a symlink**; never `ln -sfn` over it.
- **The ledger's shapes:** `agent.born` carries the desk as `specialty`; `agent.research` has a row
  per turn and the finished row carries `profile`; `allocator-board.json` `families` is
  `{venue: {family: record}}`; `ops.deploy` rows with `what: backup` are backup attempts.
- **Kalshi:** an order on an unfunded shard fails with `insufficient_shard_balance`; a cross-shard
  move can take an hour to credit.
- **Read transcripts before judging research** (`/workspace/state/traces/*.json.gz`).
- **The copy rule:** practice, never paper; the levels are the owner's words.
- **Keep subagent counts modest** and effort proportionate.

## The report at the end

In the run record and in the session:

1. **The scoreboard** at T0 and at the end, row by row, with the four-hourly readings between.
2. **What is live:** release, commits, the money digests with their evidence, the grant state,
   restarts a day.
3. **Real money:** agents by family state per venue, stakes, fills, real P&L per venue, the
   throttle, the first family swing if any, the equity probes' session.
4. **The loop:** the lab's forward-positive share, research sessions and candidates a day, the seat
   market's expiries and births by class, the lanes' lifts and what was paused.
5. **Compute:** OpenAI, Sail and Jev at T0 and at the end; the unit-economics row's path.
6. **Bugs:** found and fixed, who noticed each first, invariants added, anything open.
7. **Repo and docs:** what was cleaned.
8. **Rollback steps**, and the owner's next decisions with a recommendation for each: the keyed
   hosts, Sail's checkpoints and top-up, the October OpenAI cap, level-3 options, the next desks to
   open or close on their forward records.

## Done

The run is done when all of these hold:

- the scoreboard's final reading is in the run record, and every row has reached its target or
  carries the numbers that say why it cannot yet (a settlement count not reached, a session that
  has not opened, an owner step not taken);
- every workstream is live and verified in its window, scheduled for a named window after the
  run, or blocked with the blocker recorded with numbers;
- all test suites and CI are green;
- every real-money agent is a probe, a proven family's bunt or a swing; the proven family's stake
  follows its bound; no probe sits on a losing family;
- no release has been rolled back by an environment alert since Deploy A; restarts a day ≤ 6; no
  deploy inside a session;
- the lab places by forward growth, research runs on triggers, the merged strategies are born, no
  waiter is over two hours old where its desk has capacity;
- README, operations, the run record and memory are current;
- the repo and `~/Work` are free of stale worktrees, branches and PRs, with unmerged work pushed;
- the report is delivered at the end.

## The /goal message

The owner starts the run by pasting this (edit the funding lines to what is true that day):

```
/goal Execute docs/goals/LTCM_FORWARD_FIRST.md (branch goal/forward-first-2026-09-25, merge it to main first) autonomously with no deadline, outside US market hours, until its Done list holds.

- Direction: forward outcomes are the fitness of every engine; a proven mechanism compounds within a day; idle capital works; the harness stops fighting itself; compute follows yield; the search looks for capacity. Be bold inside the envelope: I accept volatility and losses on Kalshi and Alpaca to reach the north star.
- Funding as of today: OpenAI gateway month $<spent> of $<cap> (House line $<left>); Sail $<balance>. I will <top up Sail by $X / set October's FRONTIER_MONTH_USD to $Y / neither>. Align caps up to funded money only, never above.
- Owner steps I am taking now / not taking: Sail checkpoint ticket <yes/no>; the Odds API key <yes/no>; the EIA key <yes/no>. Do not wait on any of them: one notification, then proceed, with the exact commands in the report.
- Authority: everything the plan's "Authorized" list grants, including the money-rule table (M1-M5, C8, H4) with a re-ratify of earned-live-20260921 within a minute of each promotion that moves the digest (two digest changes, a third only for a money-path defect found in the watch); owner, gateway and site deploys with CI green, none inside a US session; H1's stop-then-deploy once if the deploy path is still deadlocked; real trading on both venues inside the envelope; funded compute up to the funded balances; cleanup under D. Nothing in "Not authorized".
- Method: the scoreboard at T0, every four hours and at the end; builders in worktrees from one brief each; adversarial three-lens reviews of money code; one owner per protected file per wave; verify every change on the box in its window; fix every bug observed with a test; keep docs and repo clean; write the run record as you go; report at the end with the owner decisions and recommendations.
```

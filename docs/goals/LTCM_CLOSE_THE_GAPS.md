# LTCM run: close the gaps to the north star

An autonomous run with no deadline, outside US market hours. It takes the seven gaps measured
on the night of Sept 23-24, 2026 and closes each one on the running floor, in the order that
moves real money toward proven edges fastest, working as long as that takes. It fixes every
bug it meets, leaves the docs and the repo clean, and ends with at least three hours of watching
the agents play under the new rules.

- **Purpose:** make the floor a place where a proven mechanism compounds real capital within
  days, an unproven one risks pocket change, evidence is measured before a seat is lost, and the
  search looks for edges with capacity instead of nudging parameters on thin markets.
- **Method:** the gap review's numbers are the baseline; a scoreboard measures each gap at T0,
  every four hours, and at the end; every change is deployed through the runbook and verified in
  its window. There is no deadline: the run ends when every gap is closed or recorded as blocked
  with numbers.

## The owner's direction

The owner, Sept 23, 2026:

> "I deeply want to speed up the dynamism of agents moving up and down the levels of the game as
> quickly as possible and aggressively aligned on incentives so star traders can compound and run
> wild and profit exponentially and losing agents die off ... allow for trading to be done on the
> timescale of 24/7 agents not human clocks."

> "being bold and ambitious and not afraid to take risks both in our approach and the agents (im
> fine with volatility and lose on my portfolio to achieve the north star goal), and keeping all
> docs and repo up to date and clean free of any unneeded clutter"

> "The worst thing to me is making no progress and seeing no trading besides these tiny weather
> kalshi contracts."

**The north star:** a swarm of trading agents that is exponentially profitable, trades 24/7 on
real money (Kalshi and Alpaca), and improves itself recursively. Winners compound capital and
compute, losers die, the swarm writes, tests and breeds its own strategies, and the site shows it.

## The seven gaps, with the numbers that prove them

Measured Sept 24, 2026, 00:19-00:50Z, on release `20260923T233921Z-493b4a2ff9ab` (main
`76e446d`), money digest `c2b0e09c`. The full review is in the session memory
`ltcm-gap-review-2026-09-24`; the queries are the read-only pattern of the agent study
([`docs/research/2026-09-23-agent-study.md`](../research/2026-09-23-agent-study.md)).

| # | Gap | Evidence |
|---|---|---|
| 1 | **No engine finds edges with capacity.** The search nudges parameters on twelve hand-picked desks of thin Kalshi markets. | Of the lab's 3,641 candidates, 2,137 are parameter mutants; 16 of 18 born graduates are nudges (an impulse floor 0.0006 → 0.000686). The one proven edge, resting bids on 0.90-0.97 weather favourites, earns about $1 a day at its capacity. |
| 2 | **The promotion statistic is noise.** E ≥ 1.01 on 3 settlements promotes the luckiest of a hundred agents. | Every one of the allocator's 9 promotions to real money ran an unproven mechanism (15-minute crypto taker momentum at 182 bps, MLB-total takers at 7%, 20c ETH-strike longshots). Settled result −$18.62 on 16 settlements; 6 negative, 4 demoted after one loss, 0 positive at 00:30Z. |
| 3 | **Capital does not follow proof.** | The proven family holds $66 (mullins-2 $29.86 at W_real 1.19, "6 of 6 slots in use"; mullins-6 $36.70). Nine unproven bunts hold $256. Alpaca's $500 has never traded: 50 practice agents, median 0 closed trades, −$99.78 in 12 h. A swing stake of `bunt × E²` needs weeks of perfect wins to matter. |
| 4 | **The evidence clock is days; the seat clock is hours.** | 103 deaths in 24 h, median life 14.3 h, 70 of them before 3 fills. Weather and sports settle in 1-3 days. Displacement took traders with 38, 26 and 24 fills, and mullins-14 with a retained passing candidate. |
| 5 | **The self-improvement loop is broken at its joints.** | The lab's step has failed every minute since 23:21:59Z (`IndexError`, a warning with no traceback); last batch 23:37Z; 607 queued; 25 graduates and 5 cards waiting up to 11 h, with no forward score while the step fails. A research child fixed its real-money parent's taker entry (39 of 40 in replay) and the parent kept trading. 84% of research sessions produce nothing; Sail's `pro_asap` costs $0.055 a session against Luna's $0.017. Merton's pull-request roles: architect $57, teacher $21, toolsmith $19, operator $15, designer $8 for about one positive forward record. 49 OpenAI holds with no response ($98.36; 28 older than 24 h) are counted as spend, so the House line reads $7.94 and the tier is "audits". |
| 6 | **Execution rules block exits and manufacture evidence.** | The self-cross rule refused market exits for seven crypto-alts agents 7-18 times each in 6 h, positions 9 h past their stops. Stacked strikes on one game count as independent trades: meriwether-h7d7702 reached W_paper 1.38 on what it called "4 games, not 13 fills" and went back on real money at 00:39Z. |
| 7 | **The inputs agents ask for do not exist.** | Earnings calendars, settlement fixings, attention underlyings and weather ensembles are owner egress steps. The attention desk had no intent in 48 h and still receives lab graduates; alpaca-crypto-majors was offered markets on 42 wakes in an hour with no intent. |

## The scoreboard (workstream Z)

One read-only script, `scripts/gap_scoreboard.py`, prints these at T0, every four hours and at the end, from the
ledger, the lab store and the board. The run is judged on the movement.

| # | Metric | Baseline (Sept 24 00:50Z) | Target at the end |
|---|---|---|---|
| 1 | Families with a positive real lower bound, and their measured capacity ($/day) | 1 family, about $1/day | ≥ 2 families, capacity measured for each |
| 2 | Allocator promotions to real money: settled result and share positive | −$18.62 on 9, 0 positive | every promotion since Deploy A on a family with a positive pooled forward record, or a probe stake |
| 3 | Real dollars in proven families / in unproven; Alpaca real agents | $66 / $256; 0 | proven ≥ unproven; ≥ 1 Alpaca real agent, or the exact numbers why not |
| 4 | Median agent life (h); deaths before 3 fills (share) | 14.3 h; 68% | ≥ 24 h on day-horizon desks; < 30% |
| 5 | Lab batches an hour; LLM-children share of graduates; waiters and the longest wait; parents superseded by corrected children | 0; 2 of 18; 30 at 11 h; 0 | ≥ 30; ≥ 50%; 0 over 2 h; every corrected real-money parent |
| 6 | Self-cross exit refusals (6 h); promotions on stacked positions | about 85; 1 | 0; 0 |
| 7 | Recorders live on the allowed data hosts; desks with markets offered and no intent for 48 h | 0 of 12 allowed hosts recorded; 3 desks | a recorder live for every allowed host a desk needs; 0 desks |

## Where the floor stands at plan time (Sept 24, 00:50Z)

- **Release** `20260923T233921Z-493b4a2ff9ab`; grant `earned-live-20260921` active on money digest
  `c2b0e09c`; 110 living, 383 dead; tick 30-40 s; no book frozen.
- **Bands:** Kalshi bunts 10 ($322.83 of $517.75 committed), Kalshi practice 49, Alpaca practice
  50, swings 0, Alpaca real 0. Real equity $997.96 against $1,017.75 at the grant.
- **Compute:** the gateway month $394.46 of $408 ($13.54 left; resets Oct 1); the House line $7.94
  after $98.36 of phantom holds; tier "audits". Sail about $65-71 at about $44 a day (run-out
  about 10:00Z Sept 25); #216 already cut research to 120-minute intervals with 6 workers (Sail
  settled $1.54 in the last hour). Jev $16.15 of $42.
- **Live:** `docs/runs/2026-09-23-learn-and-unblock.md` (paused at 23:30Z) has every workstream's
  state. W2-house (agents' pause and size-down tools, the wake skip) and the open desks' members
  were never built. Level-3 debit verticals are a design only (draft PR #210).
- **Re-baseline at T0.** The run may start hours or days after this was written. Measure again
  before building: if a defect below no longer reproduces, keep its regression test and its
  invariant and skip the fix.

## What "closer to the north star" means when the run ends

1. **A proven mechanism compounds.** A family whose pooled real record clears a lower bound is
   staked by Kelly on that bound, and its stake grows with every further batch of settlements.
   The weather-favourites family is the first test.
2. **Unproven mechanisms risk pocket change.** A first real stake is a probe at the venue
   minimum, promoted only by the family's forward record, and one loss on a probe is not a demotion.
3. **Evidence is measured before a seat is lost.** A resident is not displaced before its desk's
   evidence clock has run, a retained candidate outlives its author, and a corrected child replaces
   its defective parent on real money at once.
4. **The loop runs and is watched.** The lab evaluates again, the holds are released, repeated
   warnings escalate with a traceback, and the search spends on mechanism changes in deep markets.
5. **Exits are never walled off**, and correlated positions never count twice.
6. **Alpaca real money trades**, or the exact reason it does not is on record with numbers.
7. **The site shows the mechanism ledger:** which families have proven edges, at what capacity and
   stake, and who was born and died and why.
8. **Every bug observed is fixed, docs and repo are current, and the report is delivered.**

## Principles

1. **Proof at the family level, money at the agent level.** A mechanism is proven by its
   family's pooled forward record over independent settlements, never by one agent's three lucky
   settlements. Stakes still sit on agents, so the board, the books and the site keep working.
2. **Evidence stays honest.** Practice fills stay conservative; the sealed holdout stays sealed; no
   agent grades its own work; no trade is forced; no evidence is fabricated or back-filled.
3. **Bold is allowed; blind is not.** Money rules move only inside the closed table below, each
   change recorded with its evidence and re-ratified. A rule changed to make the night look busy
   is not allowed.
4. **We design the environment and the agents find the alpha.** Feeds, verifiers, capacity
   measurements and incentives are the House's; strategies are the agents'.
5. **The envelope, the gateway and the throttle are the whole risk budget:** $517.75 Kalshi,
   $500 Alpaca, the $75 order cap, the day caps and the kill switch, the throttle, no leverage, no
   shorts.
6. **A merged PR is not a deployed feature.** Verify on the box, in the change's window.

## Clock, budget, authority

**The clock.** There is no deadline: the run ends when the Done list holds. The first action
writes T0 (`date -u`) into the run record `docs/runs/<T0 date>-close-the-gaps.md` and commits
it; T0 anchors the scoreboard and the four-hourly progress notes. A context reset does not end
the run.

**The first hour's decisions**, each recorded in the run record before Wave 0's builders launch:

1. **Can this session ratify?** From `~/Work/ltcm-deploy`, run `python3 scripts/live_trading.py
   --ratify earned-live-20260921` against the running digest; with the policy unchanged it writes
   nothing. If the permission check blocks it, no deploy in this run may change the money digest;
   money-rule changes then wait on a pushed branch with the owner's commands in the report.
2. **Compute truth.** Read the gateway's month (`/v1/health` `frontier`), the House's OpenAI
   commitments by age, and Sail's balance and burn. Send the owner one push notification with the
   owner steps (below), then carry on. Release nothing by hand: D2 is the fix.
3. **The lab.** Confirm whether the step still fails (`ops.alert` "the lab's step failed", the
   last `batches` row in `lab.sqlite`). D1 goes first in Wave 0 either way, for the traceback and
   the escalation.
4. **Deploy A's money set** is fixed from the evidence already on record (the nine promotions,
   the one-loss demotions, the stacked-strikes promotion): D4, P1 and P2 below, one digest change
   and one ratify. Wave 1's family swing (C1) is the second and last digest change.
5. **One owner per protected file per wave**, at most four builders at once, adversarial
   three-lens reviews of money code in separate `*/review` worktrees, the parallel test runner
   (`ptest/run.sh` from the Sept 23 scratchpad, or recreate it: about 5 minutes for both
   suites), CI as the source of truth.

**The owner's steps** (sent once at T0, never waited on; everything else proceeds):

- **Sail:** auto-recharge or a top-up. At the plan's burn the balance runs out about 10:00Z Sept
  25; the run keeps a 1.5-day floor plus the House's `sail_reserve_usd`, cutting growth before
  anything that trades.
- **OpenAI:** read the true month-to-date spend on the OpenAI dashboard and state it in the
  session, so D2 can be checked against it; top up if wanted (the month resets Oct 1). The run
  aligns `FRONTIER_MONTH_USD`, `FRONTIER_MONTH_MAX_USD` and the House line up to funded money,
  never above.
- **Egress hosts.** The key-free hosts of workstream I were allowed by the owner on Sept 24,
  2026 at about 01:55Z (`scripts/floor_box.py hosts --add`; 39 hosts on the live allowlist, and
  `LEAGUE_HOSTS` records them), so their recorders go live in Wave 1 without asking. Still the
  owner's: the keyed hosts, `api.eia.gov` (a free key) and `api.the-odds-api.com` (paid), with
  their keys placed in the box's `.env` by the owner, or by the run under an explicit line in the
  /goal message; and the contact address that SEC and NWS ask for in a User-Agent header.
- **Level-3 options:** a second Alpaca practice account with its keys in the gateway (workstream O).

**Budget.**
- **Funded** means a balance read at T0 or later from the provider, or one the owner states in
  the session. Never a figure from a House, agent or builder message.
- **Floors that hold throughout and at the end:** OpenAI keeps at least $8 in the gateway month
  for audits; Sail keeps 1.5 days at the burn then measured plus the reserve.
- The run may create no new Sailbox. Not the run's to do: auto-recharge, buying credit, payment
  methods.

**Authorized:**
- Implement, test, commit, push, open and merge PRs to `main` of this repo and of `personal-site`
  with CI green. Builders in their own worktrees; the main session merges.
- Change the money rules inside the closed table below, and re-ratify `earned-live-20260921`
  within a minute of each promotion that changes the digest. At most two digest changes.
- Change the risk-free rules on recorded evidence with no re-ratification: `ladder.replay`,
  `ladder.paper_death`, `league/turbo.json` (population 64-128, only while Sail's runway stays
  over 1.5 days), `league/game.json` (including `merton.schedule_hours`, `research`, `lab`,
  `economy` within `bounds`), `league/niches.json` seats, the operating dials in
  `league/config.json`.
- Deploy: owner deploys (`scripts/floor_box.py deploy` from `~/Work/ltcm-deploy`), gateway
  deploys (`npx wrangler deploy --tag <sha>` in `gateway/`), site deploys (`npm run build && npx
  wrangler deploy` in `~/Work/personal-site`). Each with its tests green.
- Trade real money on Kalshi and Alpaca inside the envelope; volatility and losses accepted.
- Move collateral between Kalshi exchange shards of the one account (`league/shards.py` does it;
  `scripts/kalshi_shard.py` by hand if the funder is blocked).
- Spend funded compute and align caps up to funded balances.
- Stop in an emergency, then record why and tell the owner at once: `scripts/gateway_admin.py
  kill`; `league.watchdog rollback`; `npx wrangler rollback`; `allocator.enabled: False` with an
  owner deploy and a re-ratify.
- Tidy the repos under H.

**Money-rule bounds for this run.** The table is the whole list; every other money rule stays as
it is (`order_caps`, the throttle, `profit_indexed_envelope`, `max_share_of_venue` 0.6, `e_cap`,
`swing_min_w_real`, `real_drawdown_demote` 0.35, `die_below`, `evidence.paper_weight` 0.5,
`performance_fee_share`, `tuition`, `rungs`, `ladder.death`, `ladder.micro_demotion`,
`ladder.drift`, `book.DEFAULT_RULES`). New constitution keys are allowed only to carry a row of
this table, and `book.py` reads any book-side rule through a constitution key, as U1 did, so the
digest moves and the grant is re-ratified.

| Rule | Now | Allowed range | Why |
|---|---|---|---|
| `allocator.independent_settlements` (new) | every settlement counts | `"event"`: settlements are counted per distinct event (the market ticker's event), for `bunt_min_settled`, `swing_min_real_trades` and the family record | Gap 6: stacked strikes on one game are one bet |
| `allocator.max_event_share` (new) | none | 0.2-0.5 of the stake in one event on a real book | one upset cannot demote a bunt by itself |
| `allocator.probe_bunt_usd` (new) | none (every bunt is `bunt_usd`) | Kalshi $5-15, Alpaca $20-25 | Gap 2: an unproven family's first real stake risks pocket change (Alpaca: the $10 crypto minimum under the 50% order rule) |
| `allocator.bunt_usd` (a proven family's bunt) | Kalshi $30, Alpaca $25 | Kalshi $30-60, Alpaca $25-60; options bunt $80 | Gap 3 |
| `allocator.family_proven` (new) | none | pooled forward record over ≥ 10-20 independent settlements (practice at weight 0.5, real at 1) with a one-sided 80% lower bound above zero | the proof that moves a family from probe to bunt |
| `allocator.family_swing` (new) | none | real pooled record over ≥ 15-40 independent settlements with the one-sided 80% lower bound above zero; stake = Kelly on the bound against the venue's capital, starting at 2-4 × `bunt_usd`, doubling every 10 further positive independent settlements while the bound holds, capped by `max_share_of_venue` and by measured capacity (fill rate at size) | Gap 3: the proven family compounds within days |
| `allocator.hysteresis_after_settled` (new) | 0 | 0-5 real settlements before the hysteresis exit applies (the 35% stay drawdown always applies) | Gap 2: the one-loss trial |
| `allocator.position_share_event` (new) | `position_share` 0.5 | 0.15-0.5 on event books | same |
| `allocator.bunt_at`, `bunt_min_trades`, `bunt_min_settled` | 1.01 / 5 / 3 | 1.01-1.05 / 5-10 / 3-5, never lower | lines may only rise |
| `allocator.swing_at`, `swing_min_real_trades` | 1.25 / 8 | 1.25-1.5 / 8-20 | the agent-level swing stays as a second route |
| `allocator.longshot_floor_real` (new; `book.py` reads it) | 0.15 | 0.15-0.35 for real books | Gap 6: 20c strikes lost twice; cheap contracts lose |
| `allocator.real_entry_liquidity` (new; `book.py` reads it) | any | `"maker_unless_family_taker_positive"`: a real entry on an event book is post-only unless the family's pooled taker record is positive | Gap 2: the taker mechanisms were the loss engine |
| `allocator.corrected_child_supersedes` (new) | repairs only | `true`: a research child that passes replay with a fix to its real-money parent's entry mechanism demotes the parent at once | Gap 5 |
| `evidence.alpaca_paper_haircut_bps` | crypto 4, equity 2, option 24 | per class from ≥ 30 measured fills, never below 2 | unchanged rule |

**Not authorized:**
- Deposits, withdrawals, transfers between venues; enlarging the grant (`--enable`, a new grant,
  `venue_capital_usd`); raising any cap above funded money; changing the order and day caps.
- Disabling the kill switch, the gateway caps or the throttle (the run may release a kill it
  engaged itself, once the cause is fixed and verified).
- Widening the gateway's `VENUE_PATHS`, or weakening #187's refusals (multi-leg, symbol-less,
  stop and adjusted-option orders).
- Secrets, venue account settings, `wrangler secret put`, `scripts/place_secrets.sh`, the box's
  `.env`. Record what is needed as an owner step.
- Leverage, shorting, writing options, multi-leg option orders on either account.
- A real-money or practice order that no agent's intent produced. No test orders.
- Running two Houses on one practice account. Committing secrets.
- Forcing trades, planting intents, fabricating or back-filling evidence, hand-editing the ledger,
  the books, the lab store, holdout budgets or the history store.
- Loosening a sealed verifier: the holdout seal and its ration, deep replay, the auditor, the
  practice fill model (the haircut row is the only exception).
- Deleting unmerged or unpushed work.

## The order of work (no deadline)

The run is not time-boxed. It ends when the Done list holds, however long that takes, and a
context reset does not end it. The order below is a dependency order, not a schedule.

1. **Phase 0.** T0, baseline, the first hour's decisions, the owner steps sent, the watch loop
   started. Launch together: the scoreboard analyst (Z), the Wave 0 builders (D, P, X0), the
   cleanup agent (H).
2. **Wave 0** builds, reviews and fixes: D1 lab traceback and fix, D2 holds, D3 exits, D4 + P1 +
   P2 money set, X0 book rules.
3. **Deploy A** (owner deploy; ratify within a minute, digest change 1 of 2). Watch it through
   its first hour while Wave 1 builds.
4. **Wave 1** builds: C1 the mechanism ledger and the family swing, S the evidence clock and the
   seat market, L the loop's joints, I the feed recorders.
5. **Deploy B** (owner deploy; ratify, digest change 2 of 2).
6. **Wave 2** builds: E the lab as a search and the foundry brief, C3 Alpaca, W the site.
   Unprotected fixes ship through the updater.
7. **Deploy C**, the last planned owner deploy.
8. **The watch:** at least three hours after the last deploy of watching, fixing and redeploying
   (rollback or a money-path defect only), then the final scoreboard, docs, memory and the
   report. If the watch finds a scoreboard row short of its target for a reason the run can
   still fix, build again: another wave and a fourth deploy are allowed.

- **The run happens outside US market hours.** Everything that needs a stock or options session
  is built, tested and deployed in its wave, then recorded as "to verify at the next open
  (13:30Z)" with the exact check, and never rushed. Live verification during the run uses the
  markets that trade around the clock: Kalshi's 15-minute crypto and its daily weather, sports
  and crypto-strike settlements, and Alpaca crypto. The first Alpaca real agent the run can
  verify is therefore a crypto family.
- **Three owner deploys is the plan, not a cap.** Each restart empties the lab's tape cache (D1
  makes the lab survive it). A builder that misses its wave's cut rides the next wave.
- **A build cycle is about two hours** including the adversarial review; CI about 7-10 minutes
  (the 3.14 job sometimes sits at its limit; re-run once before reproducing on the box); the
  canary and watch about 15 more. These are estimates for pacing builders, not limits.
- **Progress notes.** Every four hours the run appends a scoreboard reading and a one-paragraph
  state to the run record, so the owner can read where it stands without the session.

## Workstreams, in priority order

### Z. The scoreboard (analyst; T0, every four hours, and the end)

- **Method:** a read-only sqlite backup of `ledger.sqlite`, `lab.sqlite` and `campaigns.sqlite`
  taken at T0, every four hours and at the end, queried locally, never the live box. Every
  number carries the query.
- **Deliverable:** `scripts/gap_scoreboard.py` (read-only, run from the owner's machine like
  `floor_watch.py`) printing the seven metrics of the scoreboard, and the two readings in the run
  record. The final reading is the report's first section.
- **Also measured at T0:** each desk's evidence clock (median hours from a member's first fill to
  its third independent settlement, over the last 7 days) for S1; each family's pooled forward
  record for C1; the capacity of the weather-favourites family (markets in the band a day,
  fill rate at $10 and at larger sizes if any).

### D. Live defects (Wave 0, Deploy A)

1. **D1. The Alpha Lab's step** (`league/lab.py`, protected; `lab.py` owner).
   - **Evidence:** "the lab's step failed (IndexError: list index out of range)" every 1-3
     minutes since 23:21:59Z Sept 23, 43 times in 2 h, 27 in the 30-minute watch; the step
     finishes in about 0.09 s (its `ops.job` row), before any tape work; the last batch ran
     23:37:17Z; `health.json` `lab.refusal` and `closed_since` are null, so nothing escalated. The
     restart of 23:40Z emptied the in-memory tape cache, so `ready_queued()` is 0 and every step
     goes to `breed()` first. `parameters.mutate` guards its bounds pairs, so the site is
     elsewhere in the breeding path; find it from the traceback, not by reading.
   - **Change:**
     - the step's alert carries the traceback (`traceback.format_exc()`, last 2,000 characters) in
       its payload, and `lab.stats` carries `error` and `failures_in_a_row`;
     - the fix at the site, with a regression test built from the failing state;
     - five failures in a row raise one error alert and set `health.json` `lab.failing_since`;
       the watch prints it;
     - a queued candidate whose tape the House already holds on disk counts as ready
       (`ready_queued()`), so a restart does not turn every step into a breeding step, and the
       lab's tape keys and idents are persisted in `lab.sqlite` `meta` across restarts.
   - **Acceptance:** batches resume within 15 minutes of Deploy A; ≥ 30 batches an hour after
     the first hour; the waiting graduates get forward scores at the next hourly run.
2. **D2. Phantom OpenAI holds** (`league/campaigns.py` and `campaigns.json`, protected; one
   owner).
   - **Evidence:** 49 OpenAI commitments with no settled cost: 21 aged 6-24 h ($26.36), 28 older
     than 24 h ($72.01). They are counted as spend, so the House line reads $7.94 while the gateway
     month has $13.54 left. `campaigns.json` `meter_required` is `["sail"]`, so
     `CampaignBudget.absorb_stale` never touches them.
   - **Change:** OpenAI becomes a metered provider whose meter is the gateway month
     (`/v1/health` `frontier.spent_usd`, which the House already reads for the bonus mirror);
     `absorb_stale("openai", older_than_seconds=6 h)` runs with Sail's every ten minutes, with
     the same rule that the meter must dominate the settled sum; each release is an `ops.budget`
     "holds absorbed" row with its evidence in `cost_reconciliations`. Check the gateway too: a
     reservation whose upstream call fails or times out must be given back (`gateway/lib/
     frontier.mjs`); if the gateway's `spent_usd` carries unreturned reservations, fix it there
     with a node test and a gateway deploy, and reconcile both meters against the owner's
     dashboard reading.
   - **Acceptance:** the House line and the tier reflect the gateway month within ten minutes of
     Deploy A; no hold older than 6 h with no response remains; the tier rises to "earned" or
     "all" if the funded month allows.
3. **D3. Exits walled off by the self-cross rule** (`league/book.py`, protected; the `book.py`
   owner, with X0).
   - **Evidence:** `Book._would_cross_own` refuses any market order that could execute against
     the House's own resting order. Seven alpaca-crypto-alts agents were refused 7-18 times each
     in 6 h ("a market order here could trade against the House's own resting order"); their
     time-stops fired every wake against a peer's resting bid; positions were 9 h past their
     stops. The study counted 64 + 2 such refusals in 48 h.
   - **Change:** a reducing intent that would cross the House's own resting order is never
     refused: if the resting order is the same agent's, it is cancelled first; if a peer's, the two
     are crossed inside the House at the resting order's price as `cross` fills for both (the book
     already attributes `cross` fills), never sent to the venue; where a cross cannot be booked, the
     exit is re-priced as a post-only limit at the touch and told so. Entries keep the refusal.
   - **Tests:** same-agent, peer, partial quantity, practice and real, Kalshi and Alpaca, reconcile
     after the cross. Adversarial review before deploy.
   - **Acceptance:** zero self-cross refusals of reducing orders after Deploy A; the seven agents'
     positions closed within an hour.
4. **D4. Independent settlements** (`league/allocator.py` `closed_trades`, `league/evaluator.py`,
   `league/constitution.py`; the money owner, with P).
   - **Evidence:** meriwether-h7d7702 bought NO at strikes 7, 8 and 9 of the same MLB total in
     three games, counted 13 fills, reached W_paper 1.38 and was promoted at 00:39Z after it had
     been demoted at 23:33Z for one game going over; MILPHI-6, -7 and -8 lost together.
   - **Change:** `allocator.independent_settlements: "event"`: settlements count once per distinct
     event for `bunt_min_settled`, `swing_min_real_trades` and the family record; W is unchanged
     (money is money); `allocator.max_event_share` caps a real book's exposure to one event.
   - **Tests:** three strikes of one game are one settlement; two games are two; the cap refuses
     the fourth strike.

### P. Promotion on proof (Wave 0, Deploy A; the money owner)

- **Evidence:** the nine promotions above; the design memo's own warning that the best of 50
  edgeless agents shows a 75% win rate after 20 trades; huang-l23cdb7's −$8.51 in 90 minutes at
  positions of 24-26% of a $30 stake; the two earners promoted by the old ladder on the same
  E ≥ 1.01 line are a family, not two lucky agents.
- **P1. Two tiers of bunt.** A paper agent that meets `bunt_at` and the trade counts is seated as a
  **probe** at `probe_bunt_usd` when its family is not proven, and as a **bunt** at `bunt_usd`
  when its family is proven (`allocator.family_proven`, from C1's ledger; until C1 lands, the
  family's pooled practice-and-real record computed from the ledger the same way, as a pure
  function in `allocator.py`). A probe becomes a bunt the pass after its family is proven; a bunt
  becomes a probe the pass after its family's bound falls below zero (free cash returns, no forced
  sale).
- **P2. The one-loss trial.** `hysteresis_after_settled` 3: the hysteresis exit applies only after
  three real settlements; before that only the 35% stay drawdown and death apply.
  `position_share_event` 0.2: a position on an event book is at most a fifth of the stake ($6 of
  a $30 bunt, $2 of a $10 probe).
- **P3. Maker unless proven.** `real_entry_liquidity`: a real entry on an event book is post-only
  unless the family's pooled taker record is positive. `longshot_floor_real` 0.30.
- **Tests first:** probe and bunt seating by family state; the promotion of a stacked record fails
  the independent count; a probe survives one loss; the taker refusal names the family record.
  Then the adversarial review, the owner deploy and the ratify.
- **Acceptance (within 90 minutes of Deploy A):** every seated real agent is either a probe or a
  member of a proven family; the board's `band` and `stake_usd` say which; the site shows it.

### C. Capital follows proof (Wave 1, Deploy B; the money owner)

1. **C1. The mechanism ledger** (`league/families.py`, new, protected, a money judge added to
   `ci.FORBIDDEN`).
   - Per family: every member's active blocks and independent settlements on practice (weight
     0.5) and real (weight 1), living or dead; mean log growth per settlement; the one-sided 80%
     lower bound (`league/stats.py`); the maker and taker records apart; the capacity estimate
     (markets offered in the band a day, fill rate at the current size, settlements a day); the
     proven and swing states with their `since`.
   - Persisted rows (`family.record`) at most every five minutes; `Allocator`, `House._refill`,
     the foundry, the lab's lineage weights and the publisher read one source.
   - The rules text (`league/rules.py`) tells every agent: your family's record is your proof;
     mechanism changes start a new family; the numbers that make a family proven and swinging.
2. **C2. The family swing.** `allocator.family_swing`: when a family's real pooled record has
   ≥ 15 independent settlements and the lower bound is above zero, every member on real money is
   staked at Kelly on the bound against the venue's capital, starting at 2 × `bunt_usd`, doubling
   every 10 further positive independent settlements while the bound holds, capped at
   `max_share_of_venue` and by capacity: when the fill rate at the new size falls below half the
   fill rate at the old size, the stake holds and the board says "capacity". The first family swing
   is audited on the family's real record (the auditor gets the family packet with
   `allocation_context`). A swing family whose bound falls below zero returns to bunts (free cash
   only). The agent-level swing (`swing_at`) stays as the second route.
   - **Worked example to test against:** the weather-favourites family had 14 real independent
     settlements at plan time; one more clears the count; at about 5 settlements a day the stake
     goes $60 → $120 in about two days and $240 in four, inside the $310.65 cap, if the bound
     holds.
3. **C3. Alpaca real money** (Wave 2 for the parts that need a session).
   - **Evidence:** 0 of 52 Alpaca agents ever reached the bunt line; a stock trade moves W by
     0.02-0.04%; alpaca-paper lost $99.78 in 12 h, on crypto-alts reversion (8 agents) and options
     long premium; W2-house's size-down and pause tools were never built.
   - **Change:** family-level proof (C1) lets a stock or crypto family with many small positive
     trades across members qualify where no single agent's W can; the Alpaca probe is $25
     (fractional day limits, A7, are live); the options bunt stays $80; a family negative after 6
     active blocks is not re-bred (exists) and its members rank first for displacement (S1);
     `research` tells practice agents that sizing is theirs and practice money is free, so a
     conviction-sized practice record earns proof faster (the rules text, not a forced size).
   - **Acceptance:** ≥ 1 Alpaca real agent before the run ends, through a crypto family (Alpaca
     crypto trades around the clock; stocks and options cannot be verified outside the session
     and are recorded for the next open), or the numbers: every Alpaca family's pooled record
     and bound in the final scoreboard.
4. **C4. The board and the site** carry `family`, `family_state` (unproven, proven, swing),
   `family_bound`, `capacity` and `stake_usd` per agent (schema first, W).

### S. The evidence clock and the seat market (Wave 1, Deploy B; `house.py`, unprotected)

- **Evidence:** 103 deaths in 24 h, median life 14.3 h, 70 before 3 fills; day-horizon desks need
  1-3 days per settlement; displacement took haghani-46 (38 fills), haghani-39 (26), meriwether-
  hadd32b (24), hawkins-21 (8), mullins-13 (9), mullins-14 (6, with a retained passing candidate);
  25 graduates and 5 cards waited 11 h while `seats.displaceable` said 23.
- **S1. The evidence clock.** `_displaceable`: a resident's grace on a desk is the larger of 12 h
  and the desk's measured evidence clock (Z: median hours from a member's first fill to its third
  independent settlement, refreshed daily and stored in `house.json`); a resident with 3+ fills is
  displaced only by a newcomer whose forward score beats the resident's own forward record; a
  resident whose family is proven is never displaced by an unproven newcomer. Never-traded
  residents past their grace still go first.
- **S2. Residents have forward scores.** The lab's hourly forward windows score every living
  resident's program too (they are its seeds), so the comparison in S1 exists for everyone. Forward
  windows never promote anyone and never count as practice evidence.
- **S3. Retained candidates outlive their author.** When a resident dies holding a replay-passed
  candidate, the candidate enters the seat queue as a card with the author's lineage. mullins-14's
  candidate (113 trades, +38.4% in replay) is the test case: find it in `research_jobs` and the
  private candidate store and seat it first.
- **S4. Population.** Keep 112, but every seat must hold a program with a forward score, a fill or
  a grace still running; the hourly seat-market watch reports seats holding none.
- **Acceptance:** median life on day-horizon desks ≥ 24 h in the final scoreboard; deaths before 3 fills under
  30%; no waiter over 2 h; 0 traders displaced by a newcomer with a worse forward record.

### L. The loop's joints (Wave 1, Deploy B)

1. **L1. Corrected children supersede** (`house.py`; the money key in P). When a research child
   of a real-money parent passes replay and its `agent.strategy` row names the parent's entry
   mechanism as the defect (fee, side, liquidity), the parent is demoted to practice at once and
   the child takes its seat, entering real money as a probe or bunt by its family's state. The
   engineer's repair route already does this for merged repairs; the research route joins it.
   Evidence: meriwether-h2d625d (taker moneylines at 7%) and its child -2 (maker, 39 of 40).
2. **L2. Research economy** (`game.json`, `turbo.json`, `research_gate.py`, `merton.py`).
   - Merton's architect, toolsmith, operator and designer pause until the floor's 24-hour real P&L
     is positive (`merton.paused_until_profit`); the teacher runs every 12 h; the auditor, the
     consultant and the engineer (strategy defects of living, trading parents) keep their cadence.
   - Sail research is capped at $2 an hour (`turbo.json`); an agent under `abstain_lock` runs on
     `flash_asap`; a session that ends in a provider 502 or 504 is refunded and does not count as
     a pass; the hourly yield row reports candidates per dollar per profile.
   - Evidence: 3,048 of 3,972 sessions in a day ended with no candidate; `pro_asap` $0.055 a
     session; the roles' lifetime spend above.
3. **L3. Warnings escalate** (`house.py` `alert`, `watchdog.py` health). The same warning text 10
   times in 30 minutes becomes one error alert carrying the last payload and traceback, listed in
   `health.json` `repeating_warnings`; the watch prints it; "the lab evaluated nothing in the last
   hour while its queue is not empty" is a health failure the watchdog reads.
4. **L4. The history refresh** re-fetches KXETHD's seven pages every run (2,183 log lines):
   fetch only what the store lacks.

### X. Execution rules (X0 in Wave 0 with D3; the rest Wave 1)

- **X0** (`book.py`): D3's cross-inside-the-House; `longshot_floor_real`; `real_entry_liquidity`;
  `max_event_share`; all read through constitution keys.
- **X1. Agents can pause and size down** (W2-house, never built): `pause_entries` and
  `resume_entries` research tools that hold a deployed strategy's entries while exits continue
  (recorded as `agent.strategy` with `was`), and an in-place parameter edit inside
  `parameter_rules.bounds` that keeps the seat, replayed first at half notional. Evidence: agents
  say "research tools cannot pause it ... escalate containment"; 555 texts on sizing and caps.
- **X2. The horizon rule** refuses bin-skipping configurations on kalshi-prices (34 refusals):
  judge by the market's scheduled expiration, as sports already are.

### E. Edges with capacity (Wave 2, Deploy C)

1. **E1. The lab as a search** (`lab.py`, protected).
   - Half of each batch is reserved for mechanism-changing children (`luna`, `sol`, `agent`
     origins) whenever any wait on the chosen tape (a third today).
   - A candidate graduates only with a code change beyond `PARAMS` relative to every living member
     of its lineage on that desk, or a forward score above the desk's living median.
   - Ranking for seats, breeding and graduation uses the forward window when one exists; search
     fitness never promotes by itself.
   - No graduation onto a desk with no intent in 48 h unless a feed the desk asked for was
     fulfilled since.
   - The lab's LLM line follows the family ledger: lineages with a positive pooled record get
     more Luna calls; Sol's leaps go to the deep-market desks first.
   - Evidence: 2,137 param mutants of 3,641; 16 of 18 born graduates nudges; attention graduates.
2. **E2. The foundry brief** `foundry-2026-09-24.1` (`hypotheses.py`, unprotected): cards for
   megacaps, index ETFs, crypto majors, options and the open desks, each a model-versus-market
   mechanism with its data named; no card for kalshi-crypto-strikes or kalshi-crypto-15m until a
   family there shows three positive forward blocks; every card states the fee it pays and the
   edge it needs.
3. **E3. Capacity is measured**, not assumed: C1's capacity estimate per family, from markets
   offered, fill rate at size and settlements a day; the board shows it; the family swing respects
   it.

### I. Inputs (owner egress; House recorders in Wave 1, live when allowed)

| Host | State | Desk it unblocks | What the recorder stores (receive-time stamped, point in time) |
|---|---|---|---|
| `api.open-meteo.com`, `ensemble-api.open-meteo.com`, `historical-forecast-api.open-meteo.com` | allowed | kalshi-weather (the proven desk; a fair value makes it scalable to more series and to rain and low-temperature markets) | ensemble member forecasts per city and date with the forecast's issue time; the historical-forecast API for backfill |
| `api.weather.gov` | allowed; User-Agent with a contact address | kalshi-weather | the NWS forecast for each settlement station, as issued |
| `www.sec.gov`, `efts.sec.gov`, `api.nasdaq.com` | allowed; SEC asks for a User-Agent with a contact address | alpaca-megacaps, alpaca-options | earnings announcement times as first known (8-K acceptance times; the calendar for the days ahead) |
| `sports.core.api.espn.com` | allowed | kalshi-sports | pre-game odds and win probabilities as shown, per event |
| `markets.newyorkfed.org`, `home.treasury.gov` | allowed | kalshi-open (rates series) | SOFR, par yields |
| `www.tsa.gov`, `www.realclearpolling.com` | allowed; HTML pages, fragile | kalshi-attention | passenger volumes, polling averages, as published |
| `api.eia.gov` | owner's step: a free key | kalshi-prices | WTI and gasoline fixings as published |
| `api.the-odds-api.com` | owner's step: paid, with a key | kalshi-sports | consensus win probabilities across books |

- Also, with hosts already allowed: a Kalshi candlestick recorder (`feeds.py`, Kalshi's own API)
  for price-versus-outcome tapes; perps OI backfill where OKX offers history.
- Each recorder writes `data.coverage`, and a strategy's NEEDS may name the feed as
  `feeds.requested` does today. Missing hosts stay owner steps in the report, with the number of
  agents that asked for each.

### W. The site (Wave 2; `~/Work/personal-site`)

- `capital/schema.js` first (validators refuse unknown fields; deploy the site before the floor
  publishes the fields). Then the capital page shows the mechanism ledger: families by state
  (unproven, proven, swing) with their bound, settlements, capacity and stake; the births and
  deaths feed with causes; the lab's batches an hour and waiters. Keep the rules: no links,
  "practice" never "paper", the levels "Practice", "Live Trading" and "Increased Capital",
  phone-first, CSSOM only. Update `DESIGN.md`.

### O. Level-3 options: not this run

The design and pure pieces exist (draft PR #210, `docs/design/2026-09-24-level-3-debit-verticals.md`).
The build is 5-6 days on the protected order path and needs a second Alpaca practice account
that no House reconciles. It is scheduled for its own run after the owner's step. No multi-leg
order goes to either account in this run, practice included.

### B. Bugs

- Every defect seen gets a regression test that fails without the fix, the fix, and the right
  deploy path (the updater for unprotected files, a wave's owner deploy for `ci.FORBIDDEN`).
- Money code gets the multi-lens adversarial review before deploy.
- For each bug, record whether any alert, watchdog check or Merton role noticed it before this
  session did; where none did, add the cheapest invariant (L3 is the general one).
- Known at plan time, beyond D: the history refresh loop (L4); research sessions charged on
  provider 502s (L2); `scripts/floor_watch.py`'s `--since` must be an ISO stamp with `T`
  (sqlite's `datetime('now', ...)` yields a space and admits the whole day).

### H. Docs and a clean repo

- The cleanup agent runs from T0 and finishes before Deploy A, under the rules of the learn-and-unblock
  plan's H (scope, worktrees, branches, PRs, docs, scripts). Start with the paused run's list:
  `ltcm-w0-*`, `ltcm-w1-*`, `ltcm-w2-*`, `ltcm-*-rev`, `ltcm-w1-bugs-fu`, `ltcm-pacing`,
  `ltcm-rules`, `ltcm-secondlook`, `ltcm-sailfloor`, `ltcm-run` (its record is merged with #216);
  keep `w2-options/design` (draft #210). Never the main checkout, `~/Work/ltcm-deploy`, or
  anything with a commit or modified file in the last 6 hours.
- Docs kept current at each deploy: README (bands, families, probes), `docs/operations.md`
  (every new dial and health block), `docs/runbook-go-live.md`, `league/README.md`,
  `league/CONTRACT.md` (pause and size-down tools), `gateway/README.md` (the OpenAI meter),
  the site's `DESIGN.md`, the agents' rules text and playbook.
- Memory: a new project memory for this run and its MEMORY.md line.

## Risk-free dials (defaults; tune from evidence within the bounds)

| Key | Default | Bounds | Why |
|---|---|---|---|
| `turbo.json` `max_population` | 112 | 64-128 | seats follow evidence, Sail's floor holds |
| `turbo.json` `research_minutes` / `research_workers` | 120 / 6 | 60-240 / 4-8 | research on evidence, not the clock |
| `turbo.json` Sail research cap (new) | $2/h | $1-4/h | Gap 5 |
| `game.json` `merton.paused_until_profit` (new) | architect, toolsmith, operator, designer | any subset | roles that produced nothing |
| `game.json` `merton.schedule_hours.teacher` | 6 | 6-24 | |
| `game.json` `lab.batch_size` / `reserved_share` (new) | 32 / 0.5 | 16-64 / 0.33-0.75 | mechanism children first |
| `game.json` `lab.max_births_per_hour` | 6 | 1-12 | |
| `game.json` `economy.displace_trading_after_sessions` | 3 | 1-10 | with S1's evidence clock |
| `house.json` desk evidence clocks (new, measured) | per desk | ≥ 12 h | S1 |
| `niches.json` seats | as now | follow proven families and waiters | |

## Deploys and ratification

The runbook is the north-star plan's ["Deploys and ratification"](LTCM_NORTH_STAR_BUILD.md#deploys-and-ratification-the-runbook),
with these specifics:

- Deploy from `~/Work/ltcm-deploy` at `origin/main` with `scratchpad/deploy_ratify.sh <log> 1`
  or its equivalent: the ratify runs the moment the log says `promoted`.
- Protected work stays on its wave's integration branch and merges to main minutes before its
  deploy; a protected merge on main blocks the updater for everything after it.
- Read CI's job states before `gh pr merge`; a cancelled 3.14 job is not a pass.
- After every promotion: health fresh, no book frozen, the grant active on the expected digest,
  the first ticks complete, the lab's first batch.
- Gateway and site deploys are separate and never ride the House release; the site deploys
  before the floor publishes new fields.

## Watching

- `scripts/floor_watch.py --since <ISO>` every 15 minutes into the run record's watch log; the
  events monitor for band moves, family state changes, audits, real fills, deaths, lab batches
  and graduations, error alerts.
- If a US session opens while the run is still going, stock and option wakes, intents, orders,
  fills and refusals every 30 minutes; otherwise the next open is a named window in the report.
- Read-only box queries only; the House box has 1 vCPU.

**When each change can be verified:**

| Change | Deploy | Window | What counts |
|---|---|---|---|
| D1 lab | A | 15 min | a batch row in `lab.sqlite`; ≥ 30 batches in the following hour; graduates scored |
| D2 holds | A | 10 min | an "holds absorbed" row for OpenAI; the House line and tier agree with the gateway month |
| D3 exits | A | the next stop | a `cross` fill or a post-only exit where a refusal was; 0 self-cross refusals of reducing orders |
| D4, P1, P2, P3 | A | 90 min | every real agent labelled probe or proven-family bunt; a probe that loses once stays; a stacked record not promoted; a taker entry on an unproven family refused with the family record |
| C1, C2 family swing | B | the weather family's 15th independent settlement (about a day at its rate; possibly after the run ends) | the family's stake doubles on the board with the audit's approval; otherwise the family packet and the arithmetic on record |
| S1-S4 seats | B | 2 h | no trader displaced by a worse forward record; waiters at 0 within 2 h; mullins-14's candidate seated |
| L1 supersede | B | the next passing child of a real-money parent | the parent demoted, the child seated |
| L2, L3 | B | hourly | Sail research ≤ $2/h; roles paused; a repeated warning escalated with a traceback |
| E1, E2 | C | 2 h | half of a batch's rows from LLM origins; a graduate with a code change; a foundry card on a deep-market desk |
| C3 Alpaca | B/C | Alpaca crypto any hour; stocks and options at the next open (13:30Z) | an Alpaca family's pooled record and bound on the board; a crypto probe if one qualifies; the stock and option checks named for the next open |
| I recorders | B | when a host is allowed | `data.coverage` rows; a strategy naming the feed |
| W site | C | 1 min after publish | families and the deaths feed on blakewoods.us/capital |

## Lessons to read before starting

From Sept 22-24. The full runbook is in the north-star plan.

- **Ratify at promotion, not later.** A late ratification once stopped the floor for 9 minutes.
- **Protected paths skip the updater**; `gateway/`, `campaigns.py`, `lab.py`, `book.py`,
  `allocator.py`, `evaluator.py`, `parameters.py` and `constitution.py` all need an owner deploy.
- **A restart can race a fill** (fixed by #153 and #212), and **empties the lab's tape cache**
  (D1 makes it survive). Three owner deploys at most.
- **The auditor needs `allocation_context`** in every promotion path, the family packet included.
- **The site's validators refuse unknown fields**: schema first, deploy the site first.
- **Never `pkill -f "unittest discover"`**; never chain a deploy on grep's exit code; commit each
  merge before the next; `rerere` off for overlapping merges; never `git add -A` after a failed
  merge.
- **`~/Work/ltcm-deploy/.data` is a symlink**; never `ln -sfn` over it.
- **Kalshi:** an order on an unfunded shard fails with `insufficient_shard_balance`; a
  cross-shard move can take an hour to credit.
- **Warnings that repeat are defects.** 43 identical lab warnings in 2 h escalated nowhere (L3).
- **Read transcripts before judging research.** `/workspace/state/traces/*.json.gz` holds every
  session (`inputs.conversation`, `outputs`); the research is often right and the rules around
  it are what fail.
- **The copy rule:** practice, never paper; the levels are the owner's words.
- **Keep subagent counts modest** and effort proportionate: a session lost 3.7 hours to a usage
  limit on Sept 23.

## The report at the end

In the run record and in the session:

1. **The scoreboard** at T0 and at the end, gap by gap, with the four-hourly readings between.
2. **What is live:** release, commits, both money digests with their evidence, the grant state.
3. **Real money:** agents by family state per venue, stakes, fills, real P&L per venue, the
   throttle, the first family swing if any, Alpaca's state.
4. **The loop:** lab batches an hour, LLM-children share, graduates and their forward scores,
   supersessions, research yield per dollar per profile, the roles paused and why.
5. **Compute:** OpenAI, Sail and Jev at T0 and at the end; holds released; cost per unit of
   evidence.
6. **Bugs:** found and fixed, who noticed each first, invariants added, anything open.
7. **Repo and docs:** what was cleaned.
8. **Rollback steps**, and the owner's next decisions with a recommendation for each: the hosts,
   the paid odds feed, the level-3 account, Sail auto-recharge, the October OpenAI cap.

## Done

The run is done when all of these hold:

- the scoreboard's final reading is in the run record, and every row has reached its target or
  carries the numbers that say why it cannot yet (a market session that has not opened, a
  settlement count not yet reached);
- every workstream is live and verified in its window, scheduled for a named window after the
  run (the next US open for stocks and options), or blocked with the blocker recorded with
  numbers;
- all test suites and CI are green;
- every real-money agent is a probe or a member of a proven family, and the proven family's stake
  follows its bound;
- the lab evaluates, no waiter is over two hours old, no exit is walled off;
- README, operations, the run record and memory are current;
- the repo and `~/Work` are free of stale worktrees, branches and PRs, with unmerged work pushed;
- the report is delivered at the end.

# Learn what blocks the north star, then unblock it — September 23, 2026

Execution record for the owner's goal of Sept 23, 2026: execute
[the learn-and-unblock plan](../goals/LTCM_LEARN_AND_UNBLOCK.md) autonomously for ten hours.

## The clock

- **T0:** 2026-09-23T16:22:40Z (the first action of the session, `date -u`).
- **Deadline:** 2026-09-24T02:22:40Z (T0 + 10 h). A context reset does not restart the clock.
- **The final watch starts no later than:** 2026-09-24T00:52:40Z (the last 90 minutes).
- **Report:** at the deadline, in this file and in the session.
- The plan's schedule assumed T0 ≈ 16:00Z; every window below is shifted by +23 minutes, except
  the US close (20:00Z), which is fixed. Deploy A therefore must promote by about 19:00Z to be
  verified in today's stock session.

| Window (plan) | This run (UTC) | What |
|---|---|---|
| T0-T+0:20 | 16:22-16:45 | T0, baseline, first-hour decisions, watch loop, snapshot; launch L, Wave 0, H |
| T+0:20-2:15 | 16:45-18:37 | Wave 0 builds and review; study v1 at ~17:52, ranked blockers by ~18:07; Wave 1 launches |
| T+2:15-2:45 | 18:37-19:07 | Deploy A (owner deploy, ratify within a minute if the digest moved) |
| T+2:45-4:15 | 19:07-20:37 | Watch stocks and options every 30 min to the 20:00Z close; study appendix at ~20:37 |
| T+4:15-5:00 | 20:37-21:22 | Deploy B (Wave 1); Wave 2 launches from the refreshed study |
| T+5:00-7:30 | 21:22-23:52 | Wave 2 builds; U2 must be live before the evening sports (~23:00Z) |
| T+7:30-8:00 | 23:52-00:22 | Deploy C (Wave 2), the last planned owner deploy |
| T+8:00-10:00 | 00:22-02:22 | At least 90 minutes of watching, fixing, redeploying (rollback or money-path defect only); docs, memory, report |

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 and deadline recorded and committed | done |
| 0.2 | Baseline (`scripts/floor_watch.py`) | done (below) |
| 0.3 | First-hour decision 1: ratify and shard transfer permission checks | done (below) |
| 0.4 | First-hour decision 2: owner told about compute; OpenAI pacing set by T+0:30 | done 16:30Z / 16:41Z (PR #194) |
| 0.5 | First-hour decision 3: Deploy A's money set fixed by T+0:45 | done 16:42Z (U1 + U5 + A2a) |
| 0.6 | Study snapshot taken (read-only sqlite backups) | done 16:28Z |
| 0.7 | Study (L), Wave 0 and cleanup (H) launched together | done 16:38Z |
| L | The agent study, `docs/research/2026-09-23-agent-study.md` | version 1 committed 17:13Z (`a8af31e`); refresh at 20:37Z and 23:52Z |
| U1 | Daily-loss rules as constitution keys (real bunts: stay drawdown; real halt per venue) | live 17:34Z (Deploy A), mechanism verified; no live instance yet |
| U2 | Durable Kalshi shard funding | live 17:34Z; first pass 17:36:49Z read all shards, no move needed; a shard-3 fill is the sports-window check (~23:00Z) |
| U5 | Winners compound (`bunt_usd × clamp(W_real, 1, swing_at)`) | live 17:34Z; verified 17:36Z (mullins-2 re-staked toward $34.84) |
| C2 | The lab decoupled from the OpenAI tier | live 17:34Z; verified once the tier drops below "all" |
| C3 | OpenAI pacing | PR #194 (updater); burn re-read hourly |
| A7 | Fractional one-day stock limits; wind-down sells held to the open | live 17:34Z; verified by an agent's practice fractional limit order (to 20:00Z) and the next out-of-hours wind-down |
| V1 | `kalshi-open` maker fees | live 17:34Z (163 series listed; regression test) |
| Deploy A | Wave 0, ratified at promotion if the digest moved | done 17:34:17Z, ratified 17:34:36Z on `1d63a56e` |
| Wave 1 / Deploy B | from the study | builders launched 17:03Z (seats, loop, bugs; lab to follow) |
| Wave 2 / Deploy C | from the refreshed study | ⟨pending⟩ |
| O | Level-3 options design and pure pieces on a pushed branch | ⟨pending⟩ |
| B | Bugs: regression test, fix, invariant | ⟨pending⟩ |
| H | Cleanup: worktrees, branches, PRs, dead docs | done 16:49Z (below) |
| Docs | README, operations, runbook, league README, CONTRACT, gateway README, DESIGN.md | ⟨pending⟩ |
| Memory | project memory + MEMORY.md line | ⟨pending⟩ |
| Report | at the deadline | ⟨pending⟩ |

## Baseline (T0, 16:21Z watch)

- **Release** `20260923T152910Z-9a5970c56aca` (Deploy 7, main `da846db`; origin/main is `cd1b0dc`
  with the plan #193 and #192 on top, both unprotected). Tick 91.7 s. Living 96, dead 343. Nothing
  stopped, no book frozen. Long jobs: research on huang-l23cdb7 and krasker-10.
- **Grant** `earned-live-20260921` active on money digest `44e8d48d` (max_agents 101).
- **Bands:** Alpaca practice 50, Kalshi bunt 5, Kalshi practice 41. Moves in the hour: 2 Alpaca
  replay → practice (haghani-57, haghani-58). Births 5, deaths 5 (4 displaced, 1 evidence).
- **Envelope:** Kalshi $517.75 with $98.64 committed; Alpaca $500 with $0.51 committed. Floor real
  P&L −$3.10; throttle off.
- **Real money in the last hour:** none. Practice: alpaca-paper 58 fills ($1,520, −$34.59 realized,
  22 agents); kalshi-shadow 10 fills ($140, −$10.98, 8 agents).
- **Top evidence:** mullins-2 E 1.178 (W_real 1.158, 11 paper / 10 real trades, stake $5.11 after
  the sweep); mullins-6 E 1.055 (stake $36.70); meriwether-h2d625d E 1.010 (bunt, $10). The best
  practice agents are at E 1.006 (mullins-13, haghani-56).
- **Lab:** 2,179 candidates evaluated, 30 archive cells, 40 graduations recorded (22 `lab.graduate`
  events in the hour).
- **Compute:** OpenAI gateway month $367.47 of the funded $408 ($34.92 left in the House line,
  $98.36 of pending holds, $5.00 settled in the last hour); Sail $96.38 at $32.32 a day (2.67 days);
  Jev $16.15 of $42; 58 pending calls.
- **Kalshi shards** (after the $1 check move): shard 0 $372.81, shard 2 $36.60, shard 3 $22.77;
  cash $432.18 plus $83.42 of positions.
- **Refusals in the hour:** 14, all "would trade against the House's own resting order".
- **Site:** publishing (age 101 s, 104 desks, board present).

## First-hour decisions

1. **Ratify and shard moves without the owner: yes.**
   - 16:2xZ: the ratify ran on the box through the same exec `scripts/live_trading.py` uses
     (`league.live_trading main --ratify earned-live-20260921`). The grant stayed active on
     `44e8d48d`; nothing was written. The wrapper script restarts the House after every ratify
     that leaves the grant active, even a no-op, so the check ran without that restart step (a
     restart empties the lab's tape cache). Deploys that change the digest use the wrapper as the
     runbook says.
   - 16:2xZ: `scripts/kalshi_shard.py transfer --usd 1 --to 3` moved $1 from shard 0 to shard 3
     (transfer `93edc423-352e-4f85-8e3e-4047da737ec0`). The account total is unchanged.
   - So this run may change money rules with a ratify at each promotion, and U2 keeps its Wave 0
     place.
2. **Compute.**
   - The owner was told in the session at 16:30Z (the push notification was not sent because the
     terminal was active): the gateway month reaches the $20 reserve at about 20:50Z unpaced and
     resets Oct 1; Sail has about 2.6 days; an OpenAI top-up and Sail auto-recharge are asked for.
     The run carries on without waiting.
   - **Funded balances at T0** (read from the providers through the gateway and the watch): OpenAI
     gateway month $367.66 of $408 (cap = funded; the House line has $34.92); Sail $96.38 at
     $32.32 a day (2.67 days); Jev $16.15 of $42. No credit has arrived, so no cap moves.
   - **Pacing (C3), set at 16:41Z, PR #194** (risk-free dials, no ratify): the toolsmith waits
     48 h (8 PRs this month, all refused by CI, $17.72) and the architect 24 h (4 strategies from
     6 PRs, $47.30; the Sol foundry writes strategies at about a sixth of the cost); the lab's own
     LLM line is $0.75 an hour (was $1.50; parameter children and batches spend no OpenAI); an
     agent with no earned record researches every 6 intervals (90 min, was 45; 82-84% of those
     sessions abstained). The teacher (13 of 13 merged) and audits keep their cadence. Expected
     burn about $3.50 an hour against the $3.30 target; re-read hourly below. It ships through the
     in-box updater (unprotected files).
   - **Floors at the deadline:** OpenAI ≥ $8 in the gateway month; Sail ≥ 1.5 days plus the House's
     `sail_reserve_usd`.
3. **Deploy A's money set (fixed 16:42Z):** one digest change, one ratify, from the evidence on
   record (the 12:21Z daily-loss freeze of huang-h51fdd3-2; the shard refusals at 12:58Z and
   13:30Z; mullins-2 and mullins-6 shrunk while earning; the options bunt staked $40 but capped at
   $20):
   - U1: `allocator.bunt_daily_loss: "stay_drawdown"` (real bunts are governed by the 35% stay
     drawdown, not the book's 10% daily rule; swings keep the 10%) and
     `allocator.real_halt: {"basis": "venue_grant_capital", "pct": "0.08"}` (the real book's halt is
     8% of that venue's grant capital: $41.42 Kalshi, $40.00 Alpaca);
   - U5: a bunt's target stake is `bunt_usd × clamp(W_real, 1, swing_at)`, carried as a
     constitution key; losers are not refilled; the envelope's headroom bounds every increase;
   - A2a: the options bunt stake is $80 so one $40 contract fits under the 50% rules.
   - Not in Deploy A: `bunt_usd`, `kappa`, the swing lines and the haircut wait for the study's
     evidence (U4/A8; the run's one later digest change, if any).

## Log

- 16:22:40Z — T0. Plan read from `origin/main` (`cd1b0dc`, PR #193). Deploy checkout
  `~/Work/ltcm-deploy` moved to `cd1b0dc`. Run worktree `~/Work/ltcm-run`, branch
  `run/learn-and-unblock-2026-09-23`.
- 16:21-16:27Z — baseline watch; the ratify and shard checks (decision 1).
- 16:28Z — **the study's snapshot:** `ledger.sqlite` (300 MB, 333,668 rows to 16:28:30Z),
  `lab.sqlite` and `campaigns.sqlite` backed up on the box with sqlite's backup API into
  `/tmp/snap`, gzipped, downloaded to the session scratchpad and queried there (the House box has
  1 vCPU; its tick was 202 s at 16:24Z). Refresh due at T+4:15 (20:37Z) and T+7:30 (23:52Z).
- 16:33Z — the 15-minute watch loop started (`scripts/floor_watch.py --since`, to the session
  scratchpad, until the deadline).
- 16:35Z — four Wave 0 worktrees created from `cd1b0dc`: `ltcm-w0-money` (U1, U5, A2a, A7's
  book part: owns `constitution.py`, `allocator.py`, `book.py`), `ltcm-w0-shards` (U2: a new
  protected `league/shards.py`), `ltcm-w0-lab` (C2 and two lab invariants: owns `lab.py`),
  `ltcm-w0-house` (A7's wind-down hold, V1 maker fees, two floor invariants: owns `house.py`).
- 16:38Z — **launched together:** the study's three analysts (A: funnel, loop yield, compute
  economics; B: where money is made and lost, does the verifier predict; C: 24/7 coverage, what
  the agents say and ask for), the four builders, and the cleanup agent (H). Study findings are
  due at 17:35Z, builder PRs at 17:50Z, the cleanup by 18:20Z.
- 16:41Z — PR #194, OpenAI pacing (decision 2). Its first CI run failed on a pinned value
  (`test_house.ResearchPace` pins `unproven_multiple` 3); the test now pins 6 (pushed 16:50Z).
- 16:42Z — the in-box updater shipped main `cd1b0dc` (#192, #193) as release `main-63b36c385bfe`;
  the House restarted at about 16:40Z on its own schedule.
- 16:49Z — **the cleanup (H) finished** (report copied into this record at the deadline): 34
  worktrees removed (31 merged; `codex/architect-registry-repair`, `night/record` and
  `night/repairs` pushed to origin first and their local branches kept), 72 merged GitHub branches
  deleted (remote heads 110 → 38), 11 `merton/` PRs closed with a one-line comment each (#30,
  #36-#39, #41, #43, #44, #72, #73, #149). Nothing refused. One deletion proposed for the docs
  pass: `scripts/options_demo.py` (referenced by nothing). Also noted: the plan
  `docs/goals/LTCM_LEARN_AND_UNBLOCK.md` is not linked from `docs/README.md`.
- 16:52-17:00Z — **the four Wave 0 PRs are open:** #195 (W0-lab: C2 plus the closed-lab and
  waiting-graduate alerts; CI green 16:59Z), #196 (W0-house: wind-down sells held for the open,
  `kalshi-open` maker fees for 163 series, the quiet-desk and frozen-bunt invariants; the 3.11 CI
  job hit the known 10-minute runner hang, 3.14 green), #197 (W0-shards: `league/shards.py`,
  protected; CI green), #198 (W0-money, 17:00Z).
- 16:56Z — the adversarial review of #197 launched in its own worktree (branch `w0-shards/review`).
  Its one open question was settled read-only through the gateway at 16:58Z: Kalshi's `GET /markets`
  rows carry `exchange_index` (KXMLBTOTAL 3, KXBTC15M 2, KXHIGHNY 0).
- 16:57Z — PR #194 (pacing) merged as `c04d76d` after CI passed on both Pythons; the updater ships it.
- 16:58-17:05Z — **the study's three analysts finished** (files in the session scratchpad; the
  study document follows). The numbers that decided the next hours:
  - Practice lost $505 since Sept 22 13:30Z (−$19/h), 92% from the agents' own entries (signal),
    5-8% fees, 0-4% the House's exits; 72% of today's Kalshi loss came from the largest 10% of
    positions (two foundry BTC-strike agents −$113.68). Real P&L since the grant +$1.65; the only
    earning mechanism is maker bids on 0.90-0.97 event favourites held to settlement (mullins-2
    10/10, +$4.89).
  - **A Kalshi bunt is a one-loss trial:** a lost position over 15.4% of the stake drops E below
    the hysteresis line 0.8585; huang-h427345 was demoted after one −$2.55 settlement; the
    allocator swept $144.19 of bunt equity to cash today (mullins-2 $60 → $5.11).
  - **Replay anti-predicts practice:** 0 of 20 replay passes positive after 6 active blocks; rank
    correlation −0.68; every family with 2+ forward-tested passes is negative.
  - 0 of 52 Alpaca agents ever reached the bunt line against 7 of 51 on Kalshi (a Kalshi
    settlement moves the purse 3x more per trade and pays no haircut). Lowering `bunt_at` /
    `bunt_min_trades` is not supported: the 5-agent cohort just under the line has a median
    forward log of −0.0002.
  - **The funnel:** 441 born, 345 died, 312 (90%) by displacement and 9 by evidence; the House's
    own parameter mutations are 74% of births and 88% of displacements (median life 3.8 h,
    staked every 120 s); 20 lab graduates, 6 replay-passed cards and 6 merged strategy PRs wait
    for seats while about ten residents are displaceable and `enroll()` breaks silently; 21 of 96
    residents never had a fill (the plan's "61 of 96" was a different count).
  - **The loop's yield:** the lab evaluates a candidate for $0.0006 and a holdout pass for $0.05
    but has never evaluated any of its 394 LLM-written children (a priority/batch-order defect);
    the foundry is the only paid source that reached rung 2 ($0.26 a replay pass) but its Kalshi
    crypto cards are the practice loss engine; architect designs cost $45.53 for one positive
    forward record; the engineer's 16 children have 0 forward blocks; consults fail 35% and are
    still charged.
  - **Compute:** $6.7/h in all ($4.93/h OpenAI: Luna research $2.50, Merton $2.30, audits $0.05);
    +$0.013 of real P&L per real agent-hour against $6.7/h of compute (400:1); 90.3% of research
    sessions abstain and abstentions cost about $82 a day; 41% of sessions fire on the clock.
  - **Coverage:** 36.8% of living agent-hours were inactive in 48 h (missing data 423 h, a pause
    358 h, abstained 185 h, provider failures 102 h); 8.4 h of Sept 22 had zero wakes anywhere;
    the crypto desks had no trading member for 34-35 of 48 h because of rung-0 churn; a real fill
    landed in 11 of 25 hours. Today's stock session after #189/#190 is healthy: ETF 218 wakes →
    22 intents → 22 fills, megacaps 161 → 43 → 43, options 71 → 16 → 21, 0 refusals.
- 17:02Z — **Deploy A's money set widened on that evidence** (one digest change still): the
  W0-money builder added `bunt_usd.kalshi` $10 → $30 (a typical $2.70 Kalshi position is then a
  −9% loss, not a demotion), `swing_at` 1.5 → 1.25 (the two earners needed 2.8 and 5.6 days to
  reach 1.5 at their rates; the first swing is still audited on the real record) and `kappa` 1 → 2
  (winners compound; no swing exists yet). Alpaca's bunt stays $25 (2 real fills: no evidence).
  The hysteresis line and `position_share` are outside the table, so the one-loss trial's full fix
  (a settlements grace before the hysteresis exit, or a 15% position share on event books) is an
  owner decision, recorded in the study. The grant's `max_agents` becomes 40 at the ratify
  (floor($1,017.75 / $25)).
- 17:03Z — **Wave 1 launched early from the study** (Deploy B at about 21:00Z): W1-seats (the seat
  market: waiting graduates, cards and merged strategies take every freed seat first, no House
  mutation while they wait, forward-evidenced newcomers displace never-traded residents, desk
  caps follow evidence, population 112, no re-breeding of losing families), W1-loop (research
  runs on change not on the clock, abstention has a memory, the foundry follows yield and is
  exempt from the "earned" tier, consult refunds on error, the engineer only for living trading
  parents, an hourly yield ledger), W1-bugs (dead agents waking, "the venue has no such order",
  option market intents fitted to limits, sliced exits after the close). The study synthesis
  agent was launched at the same time; W1-lab (forward windows, the lab's LLM children, the
  ration check before the House replay) launches from W0-lab's branch.
- 17:04Z — the adversarial review of #198 launched (branch `w0-money/review`).
- 17:00Z watch — OpenAI settled $3.69 in the hour (the House line $32.76), before the pacing
  release; Sail $95.27; no real fill in the hour; meriwether-42 replay → practice; one merged
  strategy (#161, sports runline) born.
- 17:12Z — the Wave 0 integration branch (`w0/integration`: #196 + #195 + #197, no conflicts) passed
  the full suites locally: league 94 modules / 2,369 tests, ltcm 1,790, `league.ci` content checks.
  #198 joins it after its review.
- 17:13Z — **the study, version 1, is on the run branch** (`docs/research/2026-09-23-agent-study.md`,
  `a8af31e`, with its 46 queries and outputs under `docs/research/queries/2026-09-23/`). It is
  published to main with Deploy A. Its ranked blockers: (1) a Kalshi bunt is a one-loss trial;
  (2) winners swept to a flat bunt; (3) the seat market held by 2-minute House mutations; (4)
  replay anti-predicts the forward record and dead families are re-bred; (5) the loss engine
  (foundry Kalshi crypto cards, hour-horizon taker bets, long premium); (6) compute on the clock
  and the month ending tonight; (7) the lab never evaluates its LLM children; (8) the floor goes
  dark (pause mode, wind-down spam, 37% inactive agent-hours); (9) the $500 Alpaca envelope idle;
  (10) the inputs agents ask for do not exist (owner egress steps: EDGAR 8-K index or the Nasdaq
  calendar, TSA, RCP, EIA).
- 17:14Z — the in-box updater shipped main `c04d76d` (#194's pacing dials) as release
  `main-417d92cc3e00`; verified on the box: `merton_schedule_hours` toolsmith 48 / architect 24,
  the lab's LLM line $0.75 an hour, `unproven_multiple` 6. Another merged strategy (#154,
  index month-start flow) was born by the House.
- 17:15Z — PR #199: the rules the agents read now say a fresh bunt is a one-loss trial (one lost
  position over about 15% of the stake, computed from `hysteresis`) until its wins build a buffer.
  No rule moves; it rides Deploy A.
- 17:18Z — **the adversarial review of #198 (money)** finished: one major and one minor confirmed
  and fixed on `w0-money/review` (a `gtc` equity exit over the order cap was sliced into fractional
  `gtc` orders that Alpaca refuses, so the exit could never complete: now cut on whole shares; the
  envelope reserved the flat bunt for an unfunded seat while `seat` lends `bunt × W_real`: now it
  reserves what `seat` will lend). Judged and left as the table's letter: a re-seat lends
  `bunt × lifetime W_real` (W_real is never reset by the allocator's own definition); a bunt halved
  by the throttle while W_real < 1 is not refilled when the throttle lifts (losses shrink by free
  cash only); every real-book check now reads the agent's rung from the ledger (unmeasured cost on
  the box: watched through the tick time). Pre-existing, noted for a fix: `Book.day_open` is
  in-memory, so a restart mid-day forgets the day's loss for both daily-loss rules. Verdict: safe
  with the follow-ups.
- 17:22Z — **the adversarial review of #197 (shards)** finished: three majors and five minors
  confirmed and fixed on `w0-shards/review`, each with a regression test that fails on the build
  (a stake whose shard could not be told counted on shard 0 only, so a small shard could be drained
  below its own desks' stakes on the first pass after a deploy; a lagging balance re-read let a
  second move draw shard 0 below its keep; a move with an unknown outcome counted nothing toward
  the $200 day; guards read once a pass; half-even rounding a third of a cent past the floor; a
  refusal on a shard at the floor moved nothing; a blocked or failed pass dropped the refusals'
  requests for an hour; the funder shared the busy ops lane, now its own lane). Unverified from
  here: the venue's mid-transfer balance semantics (a move now runs under the real book's lock),
  and `Book.stake` checks the account's total cash, not the shard's (self-heals through the
  refusal path at the cost of one lost order). Verdict: safe with the follow-ups.
- 17:19-17:23Z — **the Wave 0 integration branch** `w0/integration` merged #196, #195,
  `w0-shards/review` (#197 plus fixes), `w0-money/review` (#198 plus fixes), #199 and the run
  branch (the study): two README table conflicts, no code conflicts. Money digest `1d63a56e`
  (full `52c6c7e5`), pinned. **PR #200** opened at 17:24Z for Deploy A; the full suites run
  locally on the final tree (recorded below).
- 17:32Z — PR #200's CI green on both Pythons (3.11 7m04s, 3.14 7m49s, gateway); merged as
  `b40e737` and deployed at once from `~/Work/ltcm-deploy` (`deploy_ratify.sh`), so no
  protected range waited on main.
- **17:34:17Z — Deploy A promoted:** release `20260923T173244Z-8c7467281a19` (was
  `main-417d92cc3e00`). **17:34:36Z — the grant `earned-live-20260921` re-ratified** (19 s after
  promotion) on money digest `1d63a56e` (constitution `52c6c7e5`): the same capital, `max_agents`
  101 → 40, `stake_usd` 10 → 25. The House restarted at 17:35:40Z on the new release.
- 17:37Z — **verified on the box** (read-only): health fresh (tick 84 s, 96 living, nothing
  stopped, no book frozen), the grant active on `1d63a56e`, `frontier_tier` "all". The shard
  funder's first pass ran at 17:36:49Z on its own lane: balances shard 0 $372.81, 2 $36.60,
  3 $22.77, every wanted shard above the $20 floor so nothing moved, 0 unattributed, the
  series→shard map learned from the listings (`KXBTC15M` 2, ...). The lab kept running with its
  LLM-skip counters started; 24 graduates wait for seats. The invariants' cursor was set from
  the head. `wind_down_held` is empty. **The first allocator pass under the new rules (17:36:21Z)
  lent mullins-2 $24.75 toward a $34.84 target** (`bunt_usd` $30 × W_real 1.1616; E 1.1815; it had
  been swept to $10.09): U5 and the $30 bunt verified live on the earner. The watchdog's
  10-minute watch runs to about 17:45Z.
- 17:39Z — the deployed tree's local suites: league 94 modules / 2,392 tests, ltcm 1,791, content
  checks, money digest `1d63a56e` pinned: all green (CI had passed the same tree on 3.11 and 3.14).
- 17:29-17:38Z — **W1-loop finished early (PR #202, CI green, unprotected):** research runs on
  evidence (a fill, settlement, refusal, active block, verdict, repair, lesson, market change)
  instead of the clock, with the trigger recorded on every `research.gate` row (expected saving
  about $1.40 an hour from the 41% clock-driven sessions); three empty sessions lock an agent to
  its own events; the foundry's fast lane drops `kalshi-crypto-strikes` and closes any desk whose
  foundry-born agents are negative over 6 blocks, asks for maker entries on `kalshi-crypto-15m` and
  warns of the one-loss trial; failed consults are refunded (the 21 production ones at the agents'
  next pass); the engineer buys a defect only for a living, trading parent, and a repair child is
  replayed as a foundry card before it takes any seat (the engineer's 16 children had 0 forward
  blocks); an hourly yield row (`ops.budget` `what: "yield"`). The foundry was already exempt from
  the "earned" tier (the brief's premise was wrong there). It conflicts with main after Deploy A
  (docs, `house.py`); the builder is resolving it, then the updater ships it.
- 17:33-17:42Z — **W1-bugs finished (PR #203, CI green, `book.py` protected → Deploy B).** The
  ledger corrected three of the study's defects: no agent ever woke after death (the 607 "no
  seat" refusals were the House's own wind-downs, fixed on Sept 22); the 125 option-market
  refusals were wind-downs too; the 153 "no such order" rows were 403 refusals an older adapter
  read as unknown (fixed Sept 22) plus four transport failures in a gateway outage. What it
  fixed anyway: an option market intent is fitted to a limit at the touch and a crossing
  post-only Kalshi order re-priced one tick inside once; unseated agents' intents are dropped
  with one warning; a resume after a pause drains the wake backlog one desk at a time,
  longest-waiting first (the Sept 22 "8.4 dark hours" were a pause file left through a restart,
  then a slow drain, 5 of 12 desks in the first 17 minutes); a never-arrived order needs two
  venue answers 60 s apart and is re-checked for 15 minutes (a found order is revived with its
  fills); empty Kalshi rejection reasons now carry the venue's text ("post-only order would
  cross"); sliced market exits are held while the market is shut; two invariants (a dead agent
  with a refusal; a 24/7 desk with no wake for 30 minutes while not paused). 13 new tests.
  Who noticed first: the repair worklist and the engineer saw the option refusals on Sept 22
  (then stopped for want of authority); nothing noticed the rest. Its `reconcile()` re-read change
  is money-adjacent: an adversarial review was launched at 17:43Z (`w1-bugs/review`).
- 17:43Z — **W2-options launched** (the level-3 debit-vertical design and pure pieces on a pushed,
  unmerged draft branch; no multi-leg order anywhere this run).
- 17:44:27Z — Deploy A's watchdog watch passed (all checks; exit 0). The release is final.
- 17:33-17:46Z — **W1-lab finished (PR #204, CI green, mergeable; `lab.py` protected → Deploy B).**
  The lab's LLM children get evaluated: `PRIORITY` luna/sol 1 (the stored queue is re-keyed when
  the lab opens, since 394 children sit at the old priority) and, the real cause, the tape key no
  longer includes `style`/`parameter_rules`/`wake_minutes`/`max_hours_to_close`, so a Luna child
  no longer looks like a new tape (372 Luna NEEDS collapse to 137 tapes) and a third of each
  batch is reserved for agent/Luna/Sol origins with their tapes built first. Forward windows:
  every hour archived elites and waiting graduates are re-scored on data that arrived after their
  code froze (`forward` table; `Lab.forward_score`); elites rank by forward record; lineage
  weights take forward ±1 and the born graduates' practice/real record ±1 (weights within
  [1/8, 8]); the teacher's lessons become lab priors (`league/playbook/…pause-prior-window-fade-forks.md`
  with a `lab-prior` block; param mutants of a paused lineage are not bred). The ration check
  already ran before the House replay (the study's item did not reproduce: all 14 rationed lines
  had zero trials); it is now pinned by a test. Re-issuing a lineage's holdout budget for a fresh
  window was deliberately NOT built: the only fresh data has been replayed thousands of times by
  agents' trials, so it would loosen the seal (documented). 14 new tests; verified against a
  merge with current main.
- 17:46Z — A7's live check so far: no equity limit order from any agent since the deploy (the
  stock agents send market orders), so "mechanism verified in tests, no live instance" may be
  the record at the close; no refusal and no alert since the deploy.
- 17:27-17:47Z — **W1-seats finished (PR #201, CI green, unprotected).** One seat queue: waiting
  lab graduates, replay-passed cards and merged strategies take every freed seat first, in that
  order, and `_refill` stakes no House mutation while any of them waits (mutations at most every
  10 minutes: `newcomer_seconds` 120 → 600); a newcomer with forward evidence may displace a
  rung-0 resident or a rung-1 resident that has never traded since its program's chance, inside
  the 12-hour grace (a keeps-hours desk only after its first session; never real money, a winner,
  a trader short of its record, or a position held through a shut market; one displacement a
  desk a tick); a desk keeps one seat for a trading member and never loses its only trader to a
  mutation; no mutation, fork or revival of a family whose pooled forward record is negative
  after 6 active blocks; refused births are alerted instead of silently dropped; desk caps
  follow the graduates (weather 14, sports 16, index-etfs 14, crypto-15m 10; strikes 4,
  sports-props 4, attention 4); population 96 → 112 (16 more boxes ≈ $0.43 a day of Sail: the
  runway stays 2.9 days, over the 1.5-day floor); a `seats` health block and hourly warnings.
  18 tests. The one line it needs in the protected `lab.py` (`evidenced=True` on the lab's four
  `_weakest` calls) is applied on the Wave 1 integration branch. Seen outside scope: `spawn` and
  `enroll` never check a desk's `max_members` (crypto-alts sat at 14/12); the lab overwrites a
  graduate's `graduations.at` on every retry.
- 17:47Z — **the Wave 1 integration branch** `w1/integration` started: #201 and #204 merged (two
  additive docs conflicts), the lab one-liner applied. #203 joins after its review (~18:35Z) and
  #202 after its conflict resolution. Deploy B goes as soon as the branch is green rather than
  at the plan's 21:00Z: the lab's tape-key fix and the seat market earn more hours of evidence,
  and Deploy A's stock-session verification is unaffected by a restart.
- **17:51-21:31Z — the session stopped on a usage limit** (the Claude session's limit, not the
  floor's). Two agents were cut off mid-task (the adversarial review of #203 and the W2-options
  builder); both were resumed at 21:35Z. The floor ran on Deploy A throughout, and the watch loop
  kept its 15-minute record. The plan's Deploy B window (20:37-21:22Z) and the study refresh at
  20:37Z slipped by about an hour; Deploy B goes as soon as its CI is green.
- **What Deploy A did while the session was stopped** (read on the box at 21:32Z and from a
  21:36Z snapshot, `docs/research/queries/2026-09-23/R-1.py`):
  - **U5 verified:** mullins-2, swept to $10.09 before the deploy, was lent $24.75 toward a
    $34.84 target at 17:36:21Z; it made three more weather maker fills and at 21:31Z holds $29.86
    of a $35.64 target (W_real 1.188, E 1.208, 10 real trades: 0.04 below the 1.25 swing line).
  - **U1 verified with a live instance:** the lab's first graduate huang-l23cdb7 was promoted to a
    $30 bunt at 18:49Z (the first lab-born agent on real money), won +$6.64 (19:15Z), lost
    −$7.32 (19:45Z, 20% of the day's opening equity) and **entered again at 20:21:56Z with no
    daily-loss refusal** (the only real refusal was a limit 6 cents through the ask). The
    allocator's hysteresis then demoted it at 20:25:51Z (E 0.7350 < 0.8585); its open position
    settled at −$7.84 and the account closed. Net −$8.52: the one-loss trial again, at $30
    positions of 24-26% of the stake, above the 15% the rules now advise.
  - **U2 verified:** the funder moved $30 in the rolling day (one move) and meriwether-h7d7702, a
    sports bunt promoted at 20:07Z, filled 25 KXMLBTOTAL at $0.34 on shard 3 at 20:39:57Z. At
    21:32Z shard 3 held $14.07, under the $20 floor, after that fill: the next hourly pass must
    top it up (checked at the next watch).
  - **C2 verified:** the OpenAI House line fell under $20 at about 20:50Z (alerts "$19.68 left" and
    "$16.44 left"); the tier is "earned"; the lab stays open (`closed_since` null), its Luna calls
    are skipped on the record (15 by 21:31Z) and it keeps evaluating (75 candidates in 21Z's first
    half hour).
  - **Band moves:** three promotions to real money (huang-l23cdb7 18:49Z, meriwether-h7d7702
    20:07Z, hilibrand-h6ca596-3 21:02Z, each a $30 Kalshi bunt), one demotion. Kalshi bunts 7,
    $191.91 of the $517.75 envelope committed. Alpaca: none.
  - **Real P&L since Deploy A:** Kalshi 9 fills ($59.59), 5 settlements, −$7.35 realized; the
    floor's real P&L since the grant −$8.43; the throttle off.
  - **Practice since 16:28Z turned positive:** kalshi-shadow +$99.76 (sports +$74.01 on 18
    settlements, strikes +$26.75, 15-minute crypto −$4.45), alpaca-paper +$12.05.
  - **The stock session after Deploy A** (17:34-20:00Z): ETF desk 336 wakes, 38 intents, 18 fills;
    megacaps 216 wakes, 19 intents; after the close 20 ETF market orders were refused ("outside
    regular hours", the agents' own late orders). **No agent sent an equity limit order, so A7's
    fractional limit path has no live instance:** it is verified by tests only, and the Sept 24
    open (13:30Z) is its next window.
  - **The lab:** 673 candidates evaluated since 16:28Z (156, 183, 128, 67, 123 an hour: the restart
    at Deploy A emptied the tape cache), 124 Luna children evaluated in all by 21:36Z; graduations
    6 born, 28 passed and waiting, 27 rationed, 13 failed the House replay. Throughput does not
    bind: seats do (28 waiting), so S4 (tapes on the lab box) is not built this run.
  - **Invariants firing as designed:** the quiet-desk warning named kalshi-attention, alpaca-options,
    kalshi-prices and alpaca-crypto-majors; the waiting-graduate warning named four graduates at
    6 hours. The frozen-bunt warning never fired.
  - **New defect seen:** the daily backup of the House box failed three times ("sailbox api 503:
    prepare checkpoint"). Sail's API refused the checkpoint; the next check is whether a later
    attempt succeeds.
- 21:36Z — **the refresh snapshot** (`ledger.sqlite` to 21:36:30Z, `lab.sqlite`), taken with
  sqlite's backup API and downloaded; the box's temporary copies were removed. The study's refresh
  section 3a is written from it (`queries/2026-09-23/R-1.py`). The Sail-side backup errors
  resolved themselves: the House retried, and the 21:28Z attempt finished at 21:32Z with no alert.
- 21:36Z — **Wave 2 launched, trimmed to what the Done list needs** (the usage-limit gap cost 3.7
  hours): W2-money (the run's second and last digest change: A8, the practice haircut per asset
  class from measured fills; a bunt lent less than today's base is lent up to it, never refilling
  losses, because meriwether-h2d625d sat at $10 against a $30 target at W_real 0.9978; the day's
  opening equity survives a restart). W2-house (the wake skip and the agents' pause and size-down
  tools) is not built in this run: its brief is kept for the next build.
- 21:45Z — **the adversarial review of #203 (order path)** finished on `w1-bugs/review`
  (`ca05a98`): one major confirmed and fixed (a buy closed as never-arrived freed its reserved cash
  while the book still asked the venue, so a second buy could pass and a revived fill leave the
  agent 96% invested against the 50% cap: the buy's cash now stays reserved for the recheck
  window, and a dead agent's sweep takes free cash only). Two of its follow-ups were applied at
  once on `w1-bugs/followups` (`5a02e8e`), because both bear on Deploy C itself: the wake stamps
  are written under the state lock (a new key added while `_save_state` serializes could raise
  "dictionary changed size during iteration"), and a real book whose only problem is an order
  whose outcome is still unknown raises a warning, not an error (an error inside a deploy's
  watch rolls a good release back). Left as recorded follow-ups: re-reading settlements after a
  revived fill on a settled market (rare; pre-PR it froze too), re-snapping a re-priced post-only
  order to a coarser price band (the venue rejects it as before), and a docstring.
- 21:44Z — PR #209 (Wave 1: #201 seats, #204 lab, #202 research and foundry, the lab one-liner,
  Merton's #205-#207, the run branch) green on 3.11 (9m13s) and 3.14 (7m35s) and locally (league
  98 modules / 2,442 tests, ltcm 1,791); merged as `563a030` and deployed at once.
- **21:46:00Z — Deploy B promoted:** release `20260923T214445Z-f5650ac1d870` (was
  `main-24bda8977420`). No money rule changed (digest `1d63a56e`), so no ratify.
- 21:47-21:49Z — **Deploy B verified on the box** (first ticks): health fresh, no book frozen,
  the grant active on `1d63a56e`; the seat market is live (`seats`: 32 graduates waiting, 10
  desks reserved for them); the research gate records its triggers (`abstain_lock`, `backoff`,
  `lesson`, `repair.status`, `book.settle`: #202 live); the lab marked itself closed while the
  House started (21:46:04Z) and its forward windows have not run yet (checked again below).
- **U2's first move, read in full** (the ledger's `shard_move` row): at 20:40:17Z the hourly pass
  found shard 3 at $14.07 (under the $20 floor after meriwether-h7d7702's sports fill at 20:39:57Z)
  and moved $30 from shard 0 (transfer `3e9591d4`). The source was debited at once
  ($347.54 → $317.54) but **the destination was credited about an hour later**: shard 3 still read
  $14.07 at 21:32Z and $44.07 by 21:40Z. The account total is unchanged ($361.61 across the two
  shards before and after). The review's conservative re-read (#197 review fix 2) is what kept the
  funder from moving a second $30 while the credit was in flight. A venue fact worth keeping: a
  Kalshi cross-shard move can take about an hour to land.
- 21:39-21:46Z — **workstream O done:** draft PR #210 (`w2-options/design`, CI green, not for
  deploy): `docs/design/2026-09-24-level-3-debit-verticals.md` (every claim cited to the code;
  owner steps first: a second Alpaca practice account with its keys in the gateway, and the three
  unknowns settled only with a practice order; about 2,200 lines and 5-6 build days) and
  `league/verticals.py`, a pure module imported by nothing in the House (the spread, its maximum
  loss, the caps, Alpaca's multi-leg order shape, and one spread counted as one trade from per-leg
  fills), with 33 tests including a guard that nothing imports it.
- **21:49:20Z — Deploy B was rolled back by the watchdog** (reading 6 of its watch): one error
  alert, `alpaca-paper does not reconcile: cash differs by 40.0116; positions differ:
  crypto:LINKUSD:alpaca-paper -3.262934654`. **Cause (read from the ledger):** at 21:48:50Z
  haghani-37 placed a marketable limit sell of 3.262934654 LINK at $12.28 on the practice account;
  it filled within seconds, after the mark pass's poll, and Alpaca's positions and cash showed the
  sale before its orders endpoint did. The fill was booked at 21:49:01Z (venue time 21:48:58Z), and
  after the rollback the practice book reconciled with nothing frozen. Nothing in Deploy B's code
  caused it: the race is pre-existing (a marketable order filling between a mark pass's poll and its
  reconcile), and it hit inside a watch. Who noticed: the watchdog did, as designed; no alert or
  role had noticed the race before.
- 21:53Z — **PR #212, the fix:** `reconcile_with_second_look` in `league/house.py` (unprotected). A
  failing reconcile with an order working on that book is read again after 3 s and a fresh poll;
  a mismatch that stays is real and stands; with no order working the first reading stands; and
  the second look does not count twice toward a practice book's adoption of the venue (the first
  version did, and `test_house`'s "more than cents is an error" test caught it). Deploy B is
  redeployed with it once CI is green: the same release content plus the fix, still the run's
  second owner deploy in substance.
- 22:01Z — PR #212 green on both Pythons; merged as `cb955cb`; **Deploy B redeployed** (the same
  Wave 1 content plus the second look). **22:03:12Z promoted:** release
  `20260923T220154Z-b460e9de858e`. No money rule changed, no ratify.
- 22:08Z — **Deploy B verified on the box:** 104 living (the population rises toward 112 as the
  seat market seats waiters: 3 lab graduates born in five minutes, among them leahy-l9acfcb, plus a
  card and two House births); the seat market shows 34 graduates and 5 cards waiting, 11 desks
  reserved; the lab evaluated 7 Luna children in its first minutes (#204: the LLM children reach
  batches at last) and its first forward windows ran (3 rows, 2 ranked, both positive); the
  research gate runs on triggers (library notes, lessons, a fill, a block, heartbeats; clock runs
  only for winners and idle agents); no book frozen, no error alert, tick 35 s.

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
| U1 | Daily-loss rules as constitution keys (real bunts: stay drawdown; real halt per venue) | PR #198, in review |
| U2 | Durable Kalshi shard funding | PR #197 (CI green), in review |
| U5 | Winners compound (`bunt_usd × clamp(W_real, 1, swing_at)`) | PR #198, in review |
| C2 | The lab decoupled from the OpenAI tier | PR #195 (CI green) |
| C3 | OpenAI pacing | PR #194 (updater); burn re-read hourly |
| A7 | Fractional one-day stock limits; wind-down sells held to the open | PRs #198 (book) + #196 (House) |
| V1 | `kalshi-open` maker fees | PR #196 |
| Deploy A | Wave 0, ratified at promotion if the digest moved | ⟨pending⟩ |
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

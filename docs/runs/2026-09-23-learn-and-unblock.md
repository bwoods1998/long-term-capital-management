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
| 0.4 | First-hour decision 2: owner told about compute; OpenAI pacing set by T+0:30 | done 16:29Z / 16:50Z (PR #194) |
| 0.5 | First-hour decision 3: Deploy A's money set fixed by T+0:45 | done 16:52Z (U1 + U5 + A2a) |
| 0.6 | Study snapshot taken (read-only sqlite backups) | done 16:28Z |
| 0.7 | Study (L), Wave 0 and cleanup (H) launched together | done 16:43Z |
| L | The agent study, `docs/research/2026-09-23-agent-study.md` | ⟨pending⟩ |
| U1 | Daily-loss rules as constitution keys (real bunts: stay drawdown; real halt per venue) | ⟨pending⟩ |
| U2 | Durable Kalshi shard funding | ⟨pending⟩ |
| U5 | Winners compound (`bunt_usd × clamp(W_real, 1, swing_at)`) | ⟨pending⟩ |
| C2 | The lab decoupled from the OpenAI tier | ⟨pending⟩ |
| C3 | OpenAI pacing | PR #194 (updater); burn re-read hourly |
| A7 | Fractional one-day stock limits; wind-down sells held to the open | ⟨pending⟩ |
| V1 | `kalshi-open` maker fees | ⟨pending⟩ |
| Deploy A | Wave 0, ratified at promotion if the digest moved | ⟨pending⟩ |
| Wave 1 / Deploy B | from the study | ⟨pending⟩ |
| Wave 2 / Deploy C | from the refreshed study | ⟨pending⟩ |
| O | Level-3 options design and pure pieces on a pushed branch | ⟨pending⟩ |
| B | Bugs: regression test, fix, invariant | ⟨pending⟩ |
| H | Cleanup: worktrees, branches, PRs, dead docs | ⟨pending⟩ |
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
   - The owner was told in the session at 16:29Z (the push notification was not sent because the
     terminal was active): the gateway month reaches the $20 reserve at about 20:50Z unpaced and
     resets Oct 1; Sail has about 2.6 days; an OpenAI top-up and Sail auto-recharge are asked for.
     The run carries on without waiting.
   - **Funded balances at T0** (read from the providers through the gateway and the watch): OpenAI
     gateway month $367.66 of $408 (cap = funded; the House line has $34.92); Sail $96.38 at
     $32.32 a day (2.67 days); Jev $16.15 of $42. No credit has arrived, so no cap moves.
   - **Pacing (C3), set at 16:50Z, PR #194** (risk-free dials, no ratify): the toolsmith waits
     48 h (8 PRs this month, all refused by CI, $17.72) and the architect 24 h (4 strategies from
     6 PRs, $47.30; the Sol foundry writes strategies at about a sixth of the cost); the lab's own
     LLM line is $0.75 an hour (was $1.50; parameter children and batches spend no OpenAI); an
     agent with no earned record researches every 6 intervals (90 min, was 45; 82-84% of those
     sessions abstained). The teacher (13 of 13 merged) and audits keep their cadence. Expected
     burn about $3.50 an hour against the $3.30 target; re-read hourly below. It ships through the
     in-box updater (unprotected files).
   - **Floors at the deadline:** OpenAI ≥ $8 in the gateway month; Sail ≥ 1.5 days plus the House's
     `sail_reserve_usd`.
3. **Deploy A's money set (fixed 16:52Z):** one digest change, one ratify, from the evidence on
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
- 16:34Z — the 15-minute watch loop started (`scripts/floor_watch.py --since`, to the session
  scratchpad, until the deadline).
- 16:36Z — four Wave 0 worktrees created from `cd1b0dc`: `ltcm-w0-money` (U1, U5, A2a, A7's
  book part: owns `constitution.py`, `allocator.py`, `book.py`), `ltcm-w0-shards` (U2: a new
  protected `league/shards.py`), `ltcm-w0-lab` (C2 and two lab invariants: owns `lab.py`),
  `ltcm-w0-house` (A7's wind-down hold, V1 maker fees, two floor invariants: owns `house.py`).
- 16:43Z — **launched together:** the study's three analysts (A: funnel, loop yield, compute
  economics; B: where money is made and lost, does the verifier predict; C: 24/7 coverage, what
  the agents say and ask for), the four builders, and the cleanup agent (H). Study findings are
  due at 17:35Z, builder PRs at 17:50Z, the cleanup by 18:20Z.
- 16:50Z — PR #194, OpenAI pacing (decision 2).

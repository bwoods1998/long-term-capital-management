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
| 0.4 | First-hour decision 2: owner told about compute; OpenAI pacing set by T+0:30 | ⟨pending⟩ |
| 0.5 | First-hour decision 3: Deploy A's money set fixed by T+0:45 | ⟨pending⟩ |
| 0.6 | Study snapshot taken (read-only sqlite backups) | ⟨pending⟩ |
| 0.7 | Study (L), Wave 0 and cleanup (H) launched together | ⟨pending⟩ |
| L | The agent study, `docs/research/2026-09-23-agent-study.md` | ⟨pending⟩ |
| U1 | Daily-loss rules as constitution keys (real bunts: stay drawdown; real halt per venue) | ⟨pending⟩ |
| U2 | Durable Kalshi shard funding | ⟨pending⟩ |
| U5 | Winners compound (`bunt_usd × clamp(W_real, 1, swing_at)`) | ⟨pending⟩ |
| C2 | The lab decoupled from the OpenAI tier | ⟨pending⟩ |
| C3 | OpenAI pacing | ⟨pending⟩ |
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
2. **Compute:** ⟨pending⟩
3. **Deploy A's money set:** ⟨pending⟩

## Log

- 16:22:40Z — T0. Plan read from `origin/main` (`cd1b0dc`, PR #193). Deploy checkout
  `~/Work/ltcm-deploy` moved to `cd1b0dc`. Run worktree `~/Work/ltcm-run`, branch
  `run/learn-and-unblock-2026-09-23`.

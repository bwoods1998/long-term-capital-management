# Close the gaps to the north star — September 24, 2026

Execution record for the owner's goal of Sept 24, 2026: execute
[the close-the-gaps plan](../goals/LTCM_CLOSE_THE_GAPS.md) autonomously, with no deadline, until
every gap in its Done list is closed or recorded as blocked with numbers. The run happens outside
US market hours: anything that needs a stock or options session is built and deployed, then
recorded for the next open; live verification uses the markets that trade around the clock.

## The clock

- **T0:** 2026-09-24T01:34:02Z (the first action of the session, `date -u`).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Progress notes:** a scoreboard reading and a short state note every four hours from T0
  (05:34Z, 09:34Z, 13:34Z, ... Sept 24), in the "Progress notes" section below.
- **Report:** when the Done list holds, in this file and in the session.

## The owner's message (Sept 24, 2026, at T0)

- Funding in place: Sail funded to $170 (the owner added $100) and OpenAI to $213 (added $200).
  At T0 the run records the top-up (`scripts/campaign_topup.py --sail 100 --openai 200`), raises
  the gateway's `FRONTIER_MONTH_USD` and `FRONTIER_MONTH_MAX_USD` to the month's spend plus the
  $213 funded, deploys the gateway and confirms the frontier tier is "all" before Wave 0 launches.
- The key-free data hosts of workstream I are on the live allowlist; their recorders are built in
  Wave 1. The EIA and Odds API keys are not available yet: those two recorders stay behind a host
  check and are the owner's step in the report.
- Authority: everything the plan grants (money rules inside its closed table with a re-ratify of
  `earned-live-20260921` at each promotion that moves the digest; owner, gateway and site deploys
  with tests green; real trading on Kalshi and Alpaca inside the envelope, volatility and losses
  accepted; funded compute up to the funded balances; repo cleanup under its rules). Nothing in
  the plan's "Not authorized" list.
- Never wait on the owner: one notification per owner step, everything else proceeds, the exact
  commands in the report. Fix every bug observed and add an invariant for it.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan read from origin/main (the no-deadline version, PR #219) | ⟨pending⟩ |
| 0.3 | Top-up recorded; gateway month raised and deployed; tier "all" | ⟨pending⟩ |
| 0.4 | Baseline and the scoreboard at T0 | ⟨pending⟩ |
| 0.5 | First-hour decision 1: can this session ratify | ⟨pending⟩ |
| 0.6 | First-hour decision 2: compute truth; owner notified | ⟨pending⟩ |
| 0.7 | First-hour decision 3: the lab | ⟨pending⟩ |
| 0.8 | First-hour decision 4: Deploy A's money set | ⟨pending⟩ |
| 0.9 | First-hour decision 5: file owners per wave | ⟨pending⟩ |
| Z | The scoreboard (`scripts/gap_scoreboard.py`) | ⟨pending⟩ |
| D1 | The lab's step | ⟨pending⟩ |
| D2 | Phantom OpenAI holds | ⟨pending⟩ |
| D3 | Exits walled off by the self-cross rule | ⟨pending⟩ |
| D4 | Independent settlements | ⟨pending⟩ |
| P | Promotion on proof (probes, the one-loss trial, maker unless proven) | ⟨pending⟩ |
| X0 | Book rules through constitution keys | ⟨pending⟩ |
| Deploy A | Wave 0, ratified at promotion (digest change 1 of 2) | ⟨pending⟩ |
| C1/C2 | The mechanism ledger and the family swing | ⟨pending⟩ |
| S | The evidence clock and the seat market | ⟨pending⟩ |
| L | The loop's joints | ⟨pending⟩ |
| I | Feed recorders on the allowed hosts | ⟨pending⟩ |
| X1/X2 | Pause and size-down tools; the horizon rule | ⟨pending⟩ |
| Deploy B | Wave 1, ratified at promotion (digest change 2 of 2) | ⟨pending⟩ |
| E | The lab as a search; the foundry brief; capacity | ⟨pending⟩ |
| C3 | Alpaca real money | ⟨pending⟩ |
| W | The site's mechanism ledger | ⟨pending⟩ |
| Deploy C | Wave 2 | ⟨pending⟩ |
| Watch | At least three hours after the last deploy | ⟨pending⟩ |
| B | Bugs: regression test, fix, invariant | ⟨pending⟩ |
| H | Cleanup: worktrees, branches, PRs, dead docs | ⟨pending⟩ |
| Docs | README, operations, runbook, league README, CONTRACT, gateway README, DESIGN.md | ⟨pending⟩ |
| Memory | project memory + MEMORY.md line | ⟨pending⟩ |
| Report | when the Done list holds | ⟨pending⟩ |

## Progress notes

⟨every four hours from T0⟩

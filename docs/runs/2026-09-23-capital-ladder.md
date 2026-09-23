# Capital is the ladder — September 23, 2026

Execution record for the owner's goal of Sept 23, 2026: execute
[the north-star build plan](../goals/LTCM_NORTH_STAR_BUILD.md) autonomously for eight hours.

## The clock

- **T0:** 2026-09-23T06:30:58Z (the first action of the session, `date -u`).
- **Deadline:** 2026-09-23T14:30:58Z (T0 + 8 h). A context reset does not restart the clock.
- **The watch starts no later than:** 2026-09-23T13:00:58Z (the final 90 minutes).
- **Morning report:** at the deadline, in this file and in the session.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 and deadline recorded and committed | done |
| 0.2 | Baseline snapshot (release, grant, digest, population, live agents, fills, budget lines, foundry) | ⟨⟩ |
| 0.3 | Alpaca live crypto check (`crypto_status`) | ⟨⟩ |
| 0.4 | Compute aligned to funded balances (OpenAI, Sail, Jev) | ⟨⟩ |
| 0.5 | `scripts/floor_watch.py` | ⟨⟩ |
| 0.6 | Builders B, C, D spawned in their own worktrees | ⟨⟩ |
| A | The allocator: evidence as wealth, bands, stakes, death, performance fee | ⟨⟩ |
| B | The capital board (publisher + site) | ⟨⟩ |
| C | Exit splitting and stake-scaled positions | ⟨⟩ |
| D | The Alpha Lab (box, batch evaluator, evolution, graduation, royalties, tools) | ⟨⟩ |
| E | Profit-indexed compute and envelope; a tick that never blocks | ⟨⟩ |
| F | Open desks (stretch) | ⟨⟩ |
| Deploy 1 | A+B+C, ratified at promotion, 20-minute watch | ⟨⟩ |
| Deploy 2 | D+E | ⟨⟩ |
| Watch | ≥ 90 minutes, every 15 minutes through `scripts/floor_watch.py` | ⟨⟩ |
| Docs | README, operations, runbook, league README, CONTRACT, gateway README, DESIGN.md, rules, playbook | ⟨⟩ |
| Cleanup | this build's worktrees and branches removed once merged | ⟨⟩ |
| Memory | project memory + MEMORY.md line | ⟨⟩ |
| Report | morning report at the deadline | ⟨⟩ |

## Log

- 06:30:58Z — T0. Plan read from `origin/main` (`daebfbe`, PR #155). Worktree `~/Work/ltcm-ladder`,
  branch `night/capital-ladder`.

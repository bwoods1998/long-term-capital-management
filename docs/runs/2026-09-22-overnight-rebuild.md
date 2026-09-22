# Overnight rebuild — September 22, 2026

Execution record for `docs/goals/LTCM_OVERNIGHT_GOAL.md`, run by Claude Code (Opus 5) under the owner's `/goal`.

- **Start:** 2026-09-22T06:40:51Z
- **Deadline:** 2026-09-22T14:40:51Z (eight hours; fixed, never restarted by a context reset)
- **Core rebuild operating by:** ~12:40Z, leaving the final two hours to observe and repair

## State at the start (06:39Z)

- Release `main-6d3c54c0dcf2` (main 3a68fb1), 64 living agents, 255 dead, tick 163 s.
- 14 research sessions running, 14 durable research jobs, the semantic lab running.
- Campaign: OpenAI $90.69 left of the burst (≈ $17/h committed), Sail $79.59 left; live grant
  `earned-live-20260921` active; mullins-2 (weather) the only live agent.

## Checklist

| Workstream | Implementation | Verification | Remaining |
|---|---|---|---|
| 0. Pause the expensive loop | `House.paused()` + `floor_box.py maintenance on/off` | `league/tests/test_pause.py` | deploy, verify on the box |

## Log

- 06:40Z Goal set. PAUSE written on the box at 06:5xZ (effective once the pause release deploys).

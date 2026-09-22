# Overnight rebuild — September 22, 2026

Execution record for `docs/goals/LTCM_OVERNIGHT_GOAL.md`, run by Claude Code (Opus 5) under the owner's `/goal`.

- **First start:** 2026-09-22T06:40:51Z. The session went down at about 07:05Z and came back at 13:17Z.
- **The window now in force (the owner, 13:26Z):** "since we got stopped in the middle of this goal, you should still spend a full 8 hours on it ... the full 8 hour rebuild remains".
  - **Start:** 2026-09-22T13:17:37Z.
  - **Deadline:** 2026-09-22T21:17:37Z. It is fixed; a context reset never restarts it.
- **Core rebuild operating by:** about 19:17Z, leaving the final two hours (19:17–21:17Z) to observe and repair.

## State at the start (06:39Z)

- Release `main-6d3c54c0dcf2` (main 3a68fb1), 64 living agents, 255 dead, tick 163 s.
- 14 research sessions running, 14 durable research jobs, the semantic lab running.
- Campaign: OpenAI $90.69 left of the burst (≈ $17/h committed), Sail $79.59 left; live grant
  `earned-live-20260921` active; mullins-2 (weather) the only live agent.

## Baseline: the twelve hours before the start (18:40Z Sept 21 → 06:40Z Sept 22)

Read from the production ledger (read-only). These are the "before" numbers every later claim is measured against.

| Measure | 12 h |
|---|---:|
| Research sessions | 4,973 (Luna 3,820, pro_asap 1,116, pro_flex 37) |
| Research credits charged | $102.75 |
| Sessions returning a candidate | 228 (4.6%) |
| Provider failures (503/502/unconfirmed) | 272 |
| Replay trials / passed | 406 / 30 (7.4%) |
| Births / deaths (displaced) | 186 / 170 (162) |
| Merton passes (cost) | 39 ($21.29): teacher 11, architect 11, consultant 7, operator 6, toolsmith 3, designer 1 |
| Audits (cost) | 3 ($0.64) |
| Luna requests (metered cost) | 10,488 ($67.17), 0% prompt-cache hits |
| Campaign committed: OpenAI / Sail | +$169 (≈ $14/h) / +$82 (≈ $6.8/h) |
| Promotions | 17 to paper, 6 founder seats, 1 to micro-real |
| Fills | alpaca-paper 103, kalshi-shadow 43, kalshi (real) 15 |

Cost per replay pass ≈ $8.4 of combined OpenAI + Sail commitment. Cost per paper promotion ≈ $14.8.

## Checklist

| Workstream | Implementation | Verification | Remaining |
|---|---|---|---|
| 0. Pause the expensive loop | `House.paused()` + `floor_box.py maintenance on/off` | `league/tests/test_pause.py` | deploy, verify on the box |

## Log

- 06:40Z Goal set.
- 06:44Z `PAUSE` written on the box (`floor_box.py maintenance on`).
- 06:4xZ Seven build workstreams started in parallel worktrees: hypotheses (Astra births), repairs
  (queue + engineer), jev (gate, triage, memory), routing (caching, routes, experiments, traces,
  economics), verifier (trusted release, audits off the tick, pre-audit, consult recovery), alpaca
  (deep history, walk-forward, holdout, quote-informed fills), options (options replay, IV features).
- 06:57Z PR #87 (maintenance pause) promoted as release `20260922T065328Z-57fa3c004c29`. First
  paused ticks at 06:59Z: budget "stopped", no background jobs, tick 8 s, eight durable research
  jobs parked for resume.
- **~07:05Z → 13:17Z: the coordinating Claude Code session was down.** Its process exited; the
  seven build agents stopped with uncommitted partial work, and nothing was merged or deployed.
  The House stayed paused for the whole gap. Checked at 13:17Z: zero research, Merton passes,
  births or deaths; campaign unchanged at OpenAI $85.35 / Sail $78.86; real-money exits still
  worked (2 Kalshi orders, 1 fill); no error alerts. Six hours of the eight were lost, including
  the planned two-hour observation window.
- 13:20Z Resumed. The coordinator built a small, tested v0 on `night/v0`:
  - research backoff with a measured sample;
  - evidence-led births with exhausted-line retirement;
  - the semantic lab off.
- 13:26Z The owner restarted the full eight-hour window (see above). The seven agents were told to
  return to their full scope, with ready-for-review PRs due by 16:15–16:30Z. The ingestion PR comes
  first, so history can load while the rest is built.

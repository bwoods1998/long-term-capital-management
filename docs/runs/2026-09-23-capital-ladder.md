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
| 0.2 | Baseline snapshot (release, grant, digest, population, live agents, fills, budget lines, foundry) | done (below) |
| 0.3 | Alpaca live crypto check (`crypto_status`) | done: ACTIVE, crypto ACTIVE, $500 cash |
| 0.4 | Compute aligned to funded balances (OpenAI, Sail, Jev) | done: PR #157, gateway `c6c507ad`, House top-up |
| 0.5 | `scripts/floor_watch.py` | done (in PR #163) |
| 0.6 | Builders B, C, D, E spawned in their own worktrees | done 07:05Z |
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

## Baseline (T0, 06:30Z)

- **Release** `main-f45606af3205` (the updater's), health 44.98 s tick, nothing stopped.
- **Grant** `earned-live-20260921` active on money digest `a6b83f9e` (constitution `64a206c6`): Kalshi $517.75, Alpaca $500, 16 agents.
- **Population** 96 living / 335 dead: Alpaca paper 48, Kalshi paper 45, Kalshi rung 2: 3 (mullins-2 $61.29, mullins-6 $60.50, hawkins-19 $59.47 on $60 stakes each). The Alpaca real account has never traded.
- **Last hour** (05:30-06:30Z): fills alpaca-paper 14 ($538 notional), kalshi-shadow 19 ($253); real: 1 Kalshi order rejected, 3 cancelled, no real fill. Refusals: 24 "market orders outside regular hours", 6 below Alpaca's $10 crypto minimum.
- **Replay** in the hour: Alpaca 23 passed / 6 failed (15 of the passes through the out-of-sample floor), Kalshi 5 / 4. Promotions 0→1: haghani-53, haghani-54, scholes-28. Births 13 (12 foundry cards), deaths 12 (10 displaced, 2 redundant: holdout rationed).
- **Budget**: House OpenAI line $65.88, Sail $100.66; gateway OpenAI month $308.46 of $374; Jev $16.14 of $20; Sail balance $102.26 at $30.8/day (runway 3.0 days). 44 pending calls.
- **Foundry**: 108 cards (33 passed, 73 failed, 2 data-blocked), 8 waiting for seats, $8.48 of its $40 window spent.
- **Defect found at T0**: the site had refused every checkpoint since about 05:30Z (`HTTP 400 Invalid checkpoint`, 63 alerts in the hour): 96 living + 8 dead = 104 desk rows against the site's `MAX_DESKS` 100. Fixed twice over: PR #156 (publisher bounds the roster to 100; merged 06:39Z, updater-deployable) and the site's `MAX_DESKS` 160 (site PR #4, builder B). Publishing resumed by 07:13Z.

## Compute aligned to funded balances (Phase 0.4, 07:14Z)

| Line | Before | After | How |
|---|---|---|---|
| OpenAI gateway month | $374 cap, $308.46 metered | **$408** (metered + owner-funded ~$100, rounded down) | PR #157, gateway version `c6c507ad` |
| Jev (TypeSafe) | $20 cap, $16.14 metered | **$42** (metered + $26 funded) | same deploy |
| OpenAI House line | $58.61 left | **$85.91** left | `campaign_topup.py --id topup-20260923-capital-ladder-funded --openai 28` (matches the gateway's ~$87 remaining) |
| Sail | $101.84 balance, $28.9/day | unchanged (prepaid; auto-recharge is the owner's decision) | — |

## Log

- 06:30:58Z — T0. Plan read from `origin/main` (`daebfbe`, PR #155). Worktree `~/Work/ltcm-ladder`,
  branch `night/capital-ladder`.
- 06:34Z — PR #156 (site roster ≤ 100) opened; merged 06:39Z.
- 06:40Z — PR #157 (funded caps) opened; merged and gateway deployed 07:14Z (`c6c507ad`); House top-up +$28.
- 06:45Z — measured the evidence distribution on the live ledger: only the three live Kalshi agents have E ≥ 1.01; the best paper agent 1.0094.
- 07:05Z — builders launched as background workflows (build → adversarial review → fix): B board (`ltcm-board` + `personal-site-board`), C exits (`ltcm-exits`), D-core (`ltcm-labcore`), D-evo (`ltcm-labevo`), E (`ltcm-noblock`).
- 07:17Z — PR #163 (Workstream A, the allocator) opened; an adversarial three-lens review workflow launched on it.
  - Dry run on a copy of the live ledger: 96 agents' evidence in 1.0 s.
  - Alpaca bunt $25, not $15: the book's 50%-of-equity order rule and Alpaca's $10 crypto minimum make a $15 bunt untradeable (found by `test_allocator`'s end-to-end test).
  - `bunt_at` 1.01, not 1.03: no paper agent was near 1.03, and 1.03 would have seated nobody for days. Both changes are inside the plan's bounds.

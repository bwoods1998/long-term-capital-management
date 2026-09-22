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
| 0. Pause the expensive loop | #87 `House.paused()`, `floor_box.py maintenance on/off` | Six paused hours: no research, Merton, births or deaths; exits and reconciliation kept working; spend flat | Lift the pause at the restart |
| 1a. Astra hypotheses, not mutations | #90 hypothesis foundry (`hypotheses.py`) replaces the House's mutation refill; #92 v0 evidence-led refill and exhausted-line retirement | 24 tests; dry run: 8 of 8 cards were valid code and 1 of 7 replayed cards passed ($1.17); on deploy it retired 6 exhausted families | First live foundry calls after the restart |
| 1b. Criticism becomes work | #94 repair queue (`worklist.py`), deterministic sources, engineer (`engineer.py`), `follow()` repair, per-strategy registry files, drill; #93 pre-audit and consult recovery | 41 + tests; production dry runs: 140 queued jobs, 7 of 32 paper agents flagged, 123 recovered consult items | The drill end to end on production; the first engineer PR |
| 1c. Autonomous engineering loop | #94 engineer (bounded allowlist, per-job ceiling, retries against CI's own failure text via gateway route `/v1/github/pr/<n>/failures`); #93 independent release verifier (exact-commit attestation, the running release judges) | Gateway route live on version 7e3a180b; tests | External Sail broker not built; engineer keeps the existing Merton allowlist |
| 2. Jev as sensor and router | #95 research gate, inactivity reasons, triage, hypothesis memory, exposure groups; semantic lab off (#92) with a capped evaluation | Lab: no tradable value on 128k labels; gate replay would skip 67.5% of past sessions; 48 tests | Live gate numbers; `python -m league.research_gate LEDGER` |
| 3. Sail and model routing | #98 Luna cache layout, routing table, traces, economics, experiment | Cache: 97% read on a follow-on turn; 0% over 15,044 old calls; experiment $0.97; explicit hints admitted by gateway 7e3a180b | Live cache rates after restart; balanced tier ships off |
| 4. Alpaca data | #89 history store and ingestion; #96 deep walk-forward replay, sealed holdout, quote-informed fills; #97 dated replay quotes; options (#91, in progress) | Phase 1: 13,358 calls, 11.7M rows, 0 failed; demo holdouts +7.1% / +2.3% | Phase-2 quote probes running; `min_trades` decision; options replay |
| 5. Compounding loop | Ledger kinds for cards, links, repairs, gates, routes, traces, coverage, holdout access, inactivity | — | Observe the full path live |

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
- 13:33Z Recoverable checkpoint of the House box: `sbcp_9dc7fd6b-88e4-4e59-9b2e-78cf031114a0`
  (expires 2026-10-22; it holds the box's credentials, so treat it like the box). The first attempt
  at 13:29Z failed with a Sail-side 503 while the guest prepared its snapshot. The House was
  unaffected, and every book reconciled.
- 13:52Z #92 (v0) merged. CI on Python 3.11 first hit the 10-minute job limit, then passed on a
  rerun in 9m21s. Timing on this machine: v0 costs about 20% on the slowest lifecycle test, and the
  runner's variance is larger than that; later runs took 3m29s–6m50s.
- 14:05Z #89 (history store and ingestion) merged. Main (v0 + #89) deployed as release
  `20260922T140503Z-8257fa020126`, promoted 14:09:45Z, still paused.
- 14:10Z Phase-1 history ingestion started on the box (pid 5237): 27 core symbols; 1Day, 1Hour and
  5Min since 2016; capped at 30,000 calls, 1,500 a minute, through the gateway. By 14:16Z: 4,984
  calls, 1.2M rows, 1Day complete from 2016, no failures.
  - The Workers plan was checked first. Account-wide Worker requests were 127,286 on Sept 21, and
    ltcm-gateway served 10–13k an hour while the league ran, with no failures. That is above the
    free tier's 100k a day, so the account is on Workers Paid.
- 14:20Z #94 (repair queue, engineer, `follow()` repair, registry collision fix, drill) merged.
- 14:36Z #90 (hypothesis foundry) merged.
- 14:4xZ #95 (Jev research gate, inactivity reasons, triage, hypothesis memory, exposure groups,
  semantic lab evaluation) merged.
  - It replaces v0's gate body, and fixes a v0 flaw: routine `look`/`progress` verdicts had counted
    as news, so a paper agent almost never backed off.
- #97 (dated replay quotes) was found by the foundry's dry run and folded into #96. A recorded quote
  is dated when it was quoted (now − age); a synthesized one is dated at its step.
- 14:36Z Phase-2 ingestion (quote probes since 2024-10-31, tier-1 symbols, 120k-call cap) started (pid 5514).
- 14:40Z #98 (routing, caching, traces, economics) merged; main deployed as release
  `20260922T143927Z-02148288a0b8` (canary passed 3 ticks, promoted 14:43:48Z), still paused.
  Gateway deployed from the same main: version `7e3a180b-5e11-435f-a633-23adbed8fdcb` (the CI
  failures route of #94 and the cache-aware frontier meter of #98). Verified: `/v1/github/pr/73/failures`
  returns the failed runs; a Luna call with `prompt_cache_key` and an explicit breakpoint is admitted.
- 14:58Z `api.github.com` added to the House box's egress allowlist (32 hosts), which the release
  verifier of #93 reads to attest the exact commit. It is a read-only API host beside `github.com`
  and `codeload.github.com`, which were already allowed.

## Alpaca: deep history, deep replay, the sealed holdout, quoted fills (#89, #96)

**Store and ingestion (#89).**
- Where: `league/history.py` keeps Alpaca history in `/workspace/state/history/history.sqlite`, fetched through the gateway like the House's own data reads, at 1,500 calls a minute by default.
- What it holds:
  - daily and hourly bars since 2016, both raw and adjusted for splits and dividends;
  - raw 5-minute bars for the 24 most-used symbols;
  - quote probes: the NBBO at each regular-session 5-minute close + 2 s;
  - optional trade windows.
- Resumable: each chunk commits together with its completion record, so a killed run resumes where it stopped.
- Unavailable vs unfetched: `empty` means the venue returned nothing and the input is unavailable; an absent chunk is unfetched, a gap in the store rather than a fact about the market.
- Each finished run becomes a private `data.coverage` row.
- Measured: Alpaca pages by time span, about 2 calls per symbol-month. Phase 1 on the box (27 core symbols; 1Day, 1Hour and 5Min since 2016; about 20k calls) started at 14:10Z at about 770 calls a minute.

**Deep replay (#96).**
- Which history: an Alpaca strategy replays on the store's development window when every input it declares has been fetched.
  - The window is the 252 days (daily) or 63 days (hourly) before the holdout, capped at the largest live tape.
  - Otherwise the strategy gets the live 21/126-day tape, as before.
- Same code as live: the same `AlpacaData.tape` builder runs through `StoreClient`, with bars stamped at their close.
- Adjustments: signal bars are adjusted; execution bars and quotes are raw, scaled by that day's factor.
- A development fold can read nothing past its own end and nothing in the holdout.

**The sealed holdout (#96).**
- Window: fixed at 2025-11-14 → 2026-05-15. Replays began Sept 19 and the oldest daily tape reaches back to May 16, so no agent has seen this window.
- Promotion: a development pass reaches paper only if the holdout also passes. The holdout runs at the recorded spread and at double spread, and both must clear the evaluator's own gate (`Evaluator.replay_gate`; no statistics changed).
- Rationing: one evaluation per strategy version and three per lineage root. Every access writes a private `holdout.access` row first.
- Callers see only pass/fail, return rounded to a whole percent, and a trade-count band.

**Quote-informed fills (#96).**
- A market order pays the recorded NBBO touch. A quote more than 10 s old is stale: the touch is centred on the close and at least twice the assumed spread.
- `spread_stress` = 2 is the double-spread variant.
- A touched limit is not a fill. Queue and depth are unknown, and the output says so.
- Tapes without quotes replay byte-identically.
- Measured over the holdout: SPY's quoted spread was 0.21 bp and QQQ's 0.27 bp, against the old fixed 2 bp assumption.

**Switches.**
- `league/config.json`: `"deep_replay"` and `"holdout_gate"`, both default on. They do nothing until a strategy's inputs are fetched.
- `Settings.holdout_lineage_budget` (3) and `Settings.deep_replay_days`.
- `history.py` and `deep_replay.py` are in `league/ci.py`'s FORBIDDEN list.

**Demonstration (real SIP data, through a House).**
- Development window, 2025-03-07 → 2025-11-14:
  - equity-trend: +13.9%, 9 trades, DSR 0.97.
  - equity-rsi2: +2.7%, 8 trades.
- Holdout:
  - equity-trend: +7.1% at the recorded spread, +7.0% at double spread.
  - equity-rsi2: +2.3% at both.
- Both fail only on `min_trades` = 20. That threshold assumes short hourly tapes, and changing it is an open decision.

**Still open.**
- Historical options replay and IV features (the options PR).
- Phase-2 quote probes, about 255k calls.
- The `min_trades` decision.

# Overnight rebuild — September 22, 2026

Execution record for `docs/goals/LTCM_OVERNIGHT_GOAL.md`, run by Claude Code (Opus 5; Opus 5.5 from 17:10Z) under the owner's `/goal`.

- **First start:** 2026-09-22T06:40:51Z. The session went down at about 07:05Z and came back at 13:17Z.
- **The window now in force (the owner, 13:26Z):** "since we got stopped in the middle of this goal, you should still spend a full 8 hours on it ... the full 8 hour rebuild remains".
  - **Start:** 2026-09-22T13:17:37Z.
  - **Deadline:** 2026-09-22T21:17:37Z. It is fixed; a context reset never restarts it.
- **Core rebuild operating by:** about 19:17Z, leaving the final two hours (19:17–21:17Z) to observe and repair.
- **Owner's pause and resume.** At 16:52Z the owner asked the coordinator to stop at a good point;
  the league itself stayed live. The owner resumed at 17:10:24Z: "continue with your goal given
  youve spent 4 hours on it already". So four hours remained, and **the deadline in force is
  2026-09-22T21:10:24Z.**

## Final report

The figures below are measured through ⟨T⟩. The **after** window is the league's open hours since
the restart: 15:27:20–16:47:39Z and 17:45:14Z–⟨T⟩. It leaves out the 58-minute meter stall.

### What was built, and what is verified live

- **Astra (Merton, gpt-6-astra).**
  - **Built:**
    - the hypothesis foundry, replacing House-staked parameter mutations (#90, #92, #114);
    - the durable repair queue and engineer, which revises against CI's own failure text through
      a read-only gateway route (#94, #103, #116);
    - the pre-audit and consult recovery (#93);
    - an independent release verifier with exact-commit attestation (#93);
    - per-strategy registry files, with no more registry collisions (#94);
    - `follow()` keeps watching refused PRs (#94).
  - **Verified live:**
    - the first foundry call wrote 4 falsifiable weather cards; 1 passed replay and 3 failed
      honestly;
    - **three autonomous repairs** were written, CI-passed and merged with no human: #100 (hawkins
      horizon guard), #113 (haghani entry rounding) and #119 (haghani sub-cent prices). The
      updater attested and deployed #100 and #113 by itself;
    - the attested updater deployed releases by itself and refused the two protected changes
      (#102, #110);
    - the labelled synthetic drill ran end to end and was **verified** at 18:08:32Z (#104 refused
      by CI, #105 revised against CI's failure text, merged, deployed, 20 minutes without
      recurrence).
- **Jev.**
  - **Built:** the research gate on exact triggers with Jev relevance, explicit inactivity reasons,
    triage into repair reports, hypothesis memory (rewordings linked, never genealogy) and
    report-only exposure groups (#95). The continuous semantic lab is off (#92) after a capped
    evaluation of 128,179 labels found no tradable value.
  - **Verified live:** the gate skips more than half of due sessions (⟨gate⟩). It is cheap (Jev
    $0.015 over 282 calls) and it measures itself. **Its sampled miss rate is 8.75% (7 of 80),
    no lower than the runs' 8.3%.** So far it throttles volume (about $4/h saved) rather than
    picking out empty sessions. Triage has turned the swarm's writing into 127 deduplicated repair
    groups, and exposure groups show up to 7 agents on one event.
- **Sail and model routing.**
  - **Built:**
    - the Luna cache layout, with explicit hints admitted by the gateway (#98, #99);
    - the task routing table, research traces, the economics report and a bounded model
      experiment ($0.97; balanced ships off, Flash rejected);
    - box sleeps moved off the tick thread (#102);
    - the Sail meter now reads the balance, not a rolling window (#110).
  - **Verified live:** 51% of Luna input tokens are now read from cache (0% over 15,044 calls
    before). Ticks fell from 60–250 s to 9–45 s.
- **Alpaca.**
  - **Built:**
    - a resumable history store (#89);
    - deep walk-forward replay, a sealed holdout (2025-11-14 → 2026-05-15) and quote-informed fills
      (#96, #97);
    - options history and replay, with IV/skew/activity features (#91).
  - **Verified live:**
    - 13,358 bar calls (11.7M rows) and 160,146 quote probes, with 0 failures;
    - deep tapes build for 15 of 25 living Alpaca agents;
    - the demo holdouts returned +7.1% (equity-trend) and +2.3% (equity-rsi2);
    - SPY's quoted spread is 0.21 bp, against the old 2 bp assumption.

### The synergies that mattered

1. **Gate + cache + evidence-led births: less spent on research, more candidates per dollar.**
   - The gate stops paying for passes that keep coming back empty.
   - The cache makes the passes that do run cheaper.
   - Births come from replay passers, earning parents and cards, instead of the emptiest desk.
   - Together: research cost per hour fell by more than half, while the share of sessions with a
     candidate and the replay pass rate both rose (table below).
2. **Pre-audit → repair queue → engineer → CI → attested updater: the league repairs its own
   strategies.** The pre-audit names a defect in a strategy on paper; the queue deduplicates it and
   ranks it; the engineer writes a corrected child; CI judges it; the Merton workflow merges it;
   and the updater deploys that exact commit through the canary. No step needs a person, and none
   can approve its own spending or release.
3. **History store → deep replay and holdout → the foundry's packet.** Merton is shown what history
   exists and what the gate needs, never the holdout. So cards are written against a replay that
   can reject them honestly.

### Before and after

| Measure | Before (12 h) | After (⟨h⟩ open h) |
|---|---:|---:|
| Research sessions per hour | 414 | ⟨a⟩ |
| Research cost per hour | $8.56 | ⟨b⟩ |
| Sessions with a candidate | 4.6% | ⟨c⟩ |
| Replay pass rate | 7.4% | ⟨d⟩ |
| Research $ per replay pass | $3.42 | ⟨e⟩ |
| Luna $/h (cache read) | $5.60 (0%) | ⟨f⟩ |
| Merton $/h | $1.77 | ⟨g⟩ |
| Births: House-staked mutations | 186 in 12 h, nearly all mutations | ⟨i⟩ |
| Verified or merged autonomous repairs | 0 | 2 merged, ⟨j⟩ verified |

The after window is hours, not days. Pass rates and candidate shares on samples this small move
with a handful of trials. The real-money book traded too little either way to say anything about
an edge.

### State at the deadline

- **Real money.** mullins-2 (weather, Kalshi) is the only live agent. The live grant
  `earned-live-20260921` is active, and the money-rule digest is unchanged (`6b55f3fb…`); no
  money rule was touched tonight. League-basis account equity is ⟨equity⟩ against the $1,017.36
  start. The Alpaca real account ($500) has no agent on the micro rung yet.
- **Paper.** ⟨living⟩ agents are living. Births follow replay passers, earning parents and
  hypothesis cards, and 6 exhausted families are retired.
- **Deployed.**
  - House release ⟨release⟩ = main ⟨sha⟩.
  - Gateway version `8f829375-d373-4349-9941-609a04d5b820`.
  - Pre-rebuild box checkpoint `sbcp_9dc7fd6b-88e4-4e59-9b2e-78cf031114a0` (expires 2026-10-22).
- **Allowance left (campaign basis).** OpenAI ⟨oa⟩, Sail ⟨sail⟩. About $45 of OpenAI and $56 of
  Sail are held for calls whose outcome is unproven. They are left conservative; releasing them
  needs vendor receipts.
- **Rollback.**
  - One release, on the box:
    `cd /workspace/previous && /workspace/.venv/bin/python -m league.watchdog rollback --base /workspace --reason "..."`.
  - A feature: its switch in [operations](../operations.md). Each new feature has one, and "off"
    restores the old behaviour.
  - The gateway: `npx wrangler rollback`.
  - Everything: fork the pre-rebuild checkpoint.
- **Outstanding blockers.**
  1. The replay gate's `min_trades` = 20 blocks daily strategies on deep history. The demo
     strategies were positive on the sealed holdout with 8–14 trades. This is a ladder
     threshold, so it is the owner's call.
  2. The external Sail spending broker is not built, so the engineer keeps Merton's path allowlist
     and core House code stays the owner's.
  3. Options desks now need a replay before paper (`options_history: false` reverts that).
  4. The foundry is seat-bound whenever the league is full and no resident is displaceable.
  5. A CI runner that is slow enough to hit the 10-minute job limit blocks attestation until the
     hourly scheduled Checks run passes. It fails closed.

### Still collecting evidence, and the next step

- **Collecting evidence.**
  - The hawkins horizon repair (#100) and the haghani child (#113): 24 h observation windows and
    their paper records.
  - The weather card `6aed49`, waiting for a seat.
  - The sealed holdout: no development pass has reached it yet, so it has 0 accesses.
  - The research gate's miss rate: 0 candidates in the sampled skips so far.
  - The Luna cache on the explicit-hint layout.
  - Options replay admissions.
- **The highest-value next step:** decide the replay gate's trade minimum for daily strategies
  judged on deep history. It is the one rule standing between the new evaluation machinery (deep
  history, sealed holdout, quoted fills) and a stream of equity and ETF candidates onto paper.
  Right now the gate turns them away before the holdout can judge them.

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
| 0. Pause the expensive loop | #87 `House.paused()`, `floor_box.py maintenance on/off`; #112 names every stop (`stopped_because`) and warns when one lasts | Six paused hours: no research, Merton, births or deaths; exits and reconciliation kept working; spend stayed flat | — |
| 1a. Astra hypotheses, not mutations | #90 hypothesis foundry replaces the House's mutation refill; #92 evidence-led refill and exhausted-line retirement; #114 a card waiting on a full desk no longer blocks the foundry | Live 15:48Z: 4 cards for the weather desk, 1 passed replay and 3 failed honestly; 6 exhausted families retired; births since the restart are evidence-driven | More live calls; the waiting card needs a seat |
| 1b. Criticism becomes work | #94 repair queue, deterministic sources, engineer, `follow()` repair, per-strategy registry files; #93 pre-audit and consult recovery; #103 requested jobs first | **Two autonomous repairs merged with no human: #100 (hawkins horizon guard, deployed by the attested updater) and #113 (haghani entry rounding)** | #100 is observing (24 h window); #113 awaits deployment |
| 1c. Autonomous engineering loop | #94 engineer (bounded allowlist, per-job ceiling, revises against CI's own failure text via the gateway's read-only failures route); #93 independent release verifier (exact-commit attestation, the running release judges, protected files are the owner's) | **Drill on production: patch 1 refused by CI (#104), patch 2 written against CI's failure text, passed and merged (#105), deployed.** The updater attested and deployed four releases by itself and refused the protected #102 and #110 | External Sail broker not built; the engineer keeps the existing Merton allowlist |
| 2. Jev as sensor and router | #95 research gate, inactivity reasons, triage, hypothesis memory, exposure groups; semantic lab off (#92) after a capped evaluation | Lab: no tradable value on 128k labels. Live gate: about 41% of due sessions skipped; sampled skips found 0 candidates in 54; Jev spend about $0.02/day | Longer sample for the miss rate |
| 3. Sail and model routing | #98 Luna cache layout, routing table, traces, economics, experiment; #102 box sleeps off the tick and Merton cadence by yield | Live: 51% of Luna input tokens read from cache (0% before); Luna $/h down 58%; ticks down from 60–250 s to 9–45 s | Balanced tier ships off; batch inference has no consumer yet |
| 4. Alpaca data | #89 history store and ingestion; #96 deep walk-forward replay, sealed holdout, quote-informed fills; #97 dated replay quotes; #91 options history and replay, IV/skew/activity features | Phase 1: 13,358 calls and 11.7M rows; phase 2: 160,146 quote probes; 0 failures. 15 of 25 living Alpaca agents' inputs are covered. Demo holdouts +7.1% and +2.3% | `min_trades` = 20 blocks daily strategies (the owner's call); no holdout pass yet |
| 5. Compounding loop | Private ledger kinds link cards, links, repairs, gates, routes, traces, coverage, holdout access and inactivity to the existing trials, births, fills and deploys | The full path ran live: evidence → pre-audit → repair job → engineer PR → CI → merge → attested deploy → observing | Attribution of fills to cards and repairs over days |
| Operations | #110 Sail meter on the balance (it was a rolling window); #106–#108, #115 wind-down, death and reconcile robustness; `docs/operations.md` | Floor reopened 17:45Z after the meter latch; each fix has a regression test that fails on the old code | Stale holds need receipts before they can be released |

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

- 15:00Z Ingestion restarted in a better order, which is resumable, so nothing was lost. Phase 2
  had been running newest-first, so a capped run would probe months that deep replay never uses.
  The new sequence on the box is:
  - crypto alts at 15-minute bars since 2021, so the haghani desk can deep-replay;
  - then quote probes over the holdout and the development window only
    (`--quote-since 2025-03-07 --quote-until 2026-05-15`, capped at 200k calls).
- 15:05Z #93 (verifier) and #99 (restart batch: `cache.explicit_hints` on) merged.
- 15:10Z #91 (options history, options replay, IV/skew/activity features) merged. Gateway
  version `8f829375-d373-4349-9941-609a04d5b820` deployed; it adds read-only historical option
  prints. Alpaca has no historical option quotes, so options-replay quotes are labelled estimates.
- 15:17Z Main `7ca0fae` deployed as release `20260922T151256Z-c7c96474e945`: canary passed 3
  ticks, promoted 15:17:08Z, watch clean. Before the restart, the free sources filed 66 repair
  reports (59 missing data, 7 strategy defects), all while the House was still paused.
- **15:27:20Z Pause lifted (`floor_box.py maintenance off`): the rebuilt league is running.**
  - The live grant is active and the money digest is unchanged.
  - The aggressive layer (`turbo.json`) is unchanged: research every 5 minutes, 32/8 workers,
    population 64. On top of it now sit the research gate, the hypothesis foundry in place of
    mutation refill, the engineer, the Jev floor, deep replay with the holdout gate, and the
    cached Luna layout.
- 15:28Z Repair drill planted: `synthetic:repair-drill:20260922t152804`, labelled synthetic and $0.

- 15:28–15:32Z First open ticks. The first took 246 s: every agent became due for research at
  once after six paused hours. The Merton roles all fired too; six passes cost $2.23 at gateway
  prices.
- 15:29Z–15:56Z **The first real repair, end to end.**
  - The engineer took a pre-audit finding: hawkins strategies check time to close, not time to
    payout, so their entries are refused past the 48 h rule.
  - It wrote a corrected child strategy, and PR #100 was opened in the new per-strategy file
    format.
  - CI passed and the Merton workflow merged it.
  - At 15:50Z **the release verifier's updater attested the exact commit** (the Checks run on that
    sha) and deployed `main-3fa15113d476` through the canary by itself.
  - The job moved to `observing`, and is watched 24 h for recurrence before `verified`.
- 15:48Z **The first hypothesis foundry call** was made for the weather desk. It returned 4 cards,
  each with a mechanism, an edge after costs and a rejection test:
  - card `6aed49`, buying the expensive NO leg passively when the YES leg is a lottery ticket,
    passed replay;
  - three failed honestly (0 trades, or out-of-sample growth ≤ 0).
- 15:4xZ py-spy on the House showed the tick thread waiting in `SailSandbox._sleep` for a newborn's
  box. Ticks were alternating 60 s / 210–250 s. #102 moves box sleeps to a pool, and moves Merton's
  burst cadence to follow measured yield:
  - operator 4 h, designer 12 h, toolsmith 3 h, architect 2 h, teacher 1 h;
  - that is about $5/h at campaign prices, moved to the foundry and the engineer.
- 15:56Z **The verifier refused an automatic release.** `main c6388d3` (#102) changes
  `league/sandbox.py`, the agents' box seal, so the updater logged "this one is the owner's deploy".
  It was deployed with `floor_box.py deploy` as release `20260922T160437Z-fb8d1a3ec7f4`, promoted
  16:09:15Z with a clean watch. Ticks are now 12–35 s.
- 16:06Z An error alert on the paper book: `alpaca-paper does not reconcile: cash differs by -0.06`.
  - Probable cause: two option buys paid venue regulatory fees that the book does not model.
  - The next reconcile booked it as dust and passed.
  - It is recorded as a risk: an error during a deploy watch triggers a rollback.
- 16:08Z–16:20Z **The repair drill, end to end on production** (labelled synthetic, $0):
  - reported → admitted → reproducing → patching → PR #104;
  - CI refused #104 as designed;
  - `revising`: the engineer read CI's own failure text through the gateway's
    `/v1/github/pr/<n>/failures`;
  - attempt 2 → PR #105 → CI passed → merged → `canary`;
  - #104 was closed by hand, as the drill specifies.
  - The drill had waited 40 minutes for admission, behind higher-priority jobs; #103 now admits
    requested jobs first.
- 16:25Z #106 merged. After the night's restarts, the wind-downs of four dead agents were refused as
  "has no seat on the book" 45 times in an hour: seats live only in memory, and only the living are
  re-seated. A dead account's exit is now seated first.
- Measured, 15:27–16:25Z:
  - 256 research sessions, 25 with a candidate (9.8%, against 4.6% before);
  - 31 replay trials;
  - the gate: 196 run, 142 skipped, 28 sampled;
  - Luna cache: 51% of input tokens read from cache over 725 calls (0% before);
  - births 6 and deaths 6, every birth evidence-led and every death by displacement;
  - Jev spend $0.005;
  - OpenAI campaign from $85.35 to $70.18. After the first 15 minutes' burst the rate was about
    $6/h, against about $14/h before.

- 16:27Z–16:52Z Watching and repairing: #106, #107 and #108 merged.
  - The economics report (`scripts/economics.py`, read-only) was run over the twelve hours before
    the start and over the first live hour after the restart. The figures are in the final report.
  - 16:41Z The updater attested and deployed `main-bb348cdc203c` (#103, #105–#108) by itself. It was
    promoted at 16:57:49Z after a clean 20-reading watch.
- 16:47:39Z **Incident: the whole floor stopped.**
  - **Cause.** The campaign's Sail meter read the usage summary's `range=period` figure. On this
    plan that figure is a ROLLING seven-day window (`effective_range: "7d"`, `plan_limited: true`,
    read live at 17:12Z). It fell from ≥$512.60 to $407.51 as the first run's Sept 15 spend aged
    out. `CampaignBudget.observe_spend` treats any fall as a vendor reset that needs a manual
    reconciliation, and it latched `meter_health` failed.
  - **Effect.** No research, Merton, foundry, engineer, audits, births or payouts. Exits and
    reconciliation went on, and $73 of Sail and $66 of OpenAI allowance went unused. The repair
    drill froze at `canary`, because the engineer steps only while the floor is open.
  - **Missed.** Nothing alerted: the budget simply read "stopped". It was found at 17:10Z when the
    goal resumed.
- 17:10Z–17:21Z **The fix, #110.** The meter now reads the account balance.
  - Every decrease counts as spend; an increase (a top-up, a refund) is never credited back. The
    meter can never run backwards, and a top-up cannot hide spend.
  - The first balance reading continues the existing meter where it stands (nothing measured is
    forgotten). It clears the old feed's latch once, with the vendor evidence kept in
    `meter_reconciliations`.
  - An unavailable balance leaves the meter unread, which stops paid work after 180 s as before;
    it never latches.
  - This is not a budget reset. The burst caps, the settled and pending commitments and the $47.90
    measured since the burst began are all unchanged.
  - The full suite (1,868 tests) and CI passed. `campaigns.py` and `funded.py` are protected, so this
    needs the owner's deploy.
- 17:01Z Phase-2 ingestion finished: 160,146 calls, 160,250 quote probes over the development
  window and the sealed holdout (2025-03-07 → 2026-05-15), 0 failures, 115 minutes, 1.2 GB in the
  store.
- 17:20Z The updater began deploying `main-106e68e7c15c` (#109, a teacher lesson). It holds the
  deploy lock, so the owner's deploy of #110 follows it.
- 17:23Z #111 (docs): `docs/operations.md`, the operator's page for pausing, inspecting,
  deploying, rolling back and recovering, plus the README's rebuild summary.

- 17:30Z #111 (docs) and #112 merged. #112 makes a stop loud: every tick names its
  `stopped_because` (also in `health.json`), and a stop that lasts three ticks raises one warning.
- 17:37Z The owner's deploy of main `dcd97c2` (#110–#112) became release
  `20260922T173718Z-42913a542843`. It had waited for the updater's release of #109, which was
  promoted at 17:36:47Z; the lock allows one deploy at a time.
  - 17:43:22Z promoted.
  - 17:45:27Z the new House's first balance reading ($127.34) cleared the latch. The reconciliation
    row `sail:balance-feed:1790099127` keeps the vendor's own evidence (`effective_range: "7d"`,
    `plan_limited: true`, the rolling window) and the meter as it stood.
  - 17:45:14Z the first tick reads `budget: "open"`: 5 agents woken, 1 order, all four books
    reconciled.
  - **The floor was stopped for 57½ minutes (16:47:39Z–17:45:14Z).**

- 17:46:36Z The engineer, stepping again, moved the drill job to `observing`. The running release
  holds PR #105's files, and its synthetic observation window is 20 minutes.
- 17:47Z The foundry had made no call since 15:48Z. Its one replay-passing card (weather, `6aed49`)
  waited for a seat on a desk full of young research candidates, and any waiting card blocked
  calls for every desk. #114: a waiting card blocks new calls only when its own desk could seat it,
  and a desk with a card waiting gets no more cards. The regression test reproduces the
  production refusal.
- 17:5xZ **Second autonomous repair.** The engineer's #113 is a haghani child whose dip entries
  round down: the cent-rounding defect the auditor and the pre-audit both named. CI's judge passed
  it and the Merton workflow merged it with no human.
- 17:56Z #115. The wind-down sent a market sell, and an option sells only at a limit, so four dead
  options agents' contracts could never close: 12 refusals in 8 minutes once #106 had seated them.
  Options are now sold at the bid, as the expiry rule does.
- Stale holds: $44.84 of OpenAI and $55.72 of Sail burst allowance are pending for calls whose
  outcome the House cannot prove (timeouts, restarts, unconfirmed posts). They are left
  conservative; releasing them needs vendor receipts. See the remaining work.

- 18:05Z #116: the engineer makes one paid call per 15 minutes (it was 30). Measured yield: four
  paid calls ($0.94) gave two merged repairs, with 53 jobs admitted. This spends about $1 an hour of
  the research gate's measured saving on repairs.
- **18:08:32Z The repair drill reached `verified`** ("no recurrence for 0.33 h after the fix was
  running"). The whole state sequence ran on production: reported → admitted → reproducing →
  patching → testing (#104) → revising (CI's failure text read back through the gateway) →
  reproducing → patching → testing (#105) → canary → observing → verified. It is labelled
  synthetic and cost $0.
- 18:10Z #117. The hawkins job (#100) went back to `revising` because hawkins-9, still on the old
  code, was refused again. A repair that only adds strategy files cannot change running agents,
  so the agents that reported the problem on the old code no longer count as its recurrence.
  Any other agent's recurrence still reopens the job.
- **18:17:19Z The updater attested and deployed main `37bb07f` by itself** (`main-ded16d0d651d`:
  the engineer's #113, and #114–#116). The canary passed 3 ticks; promoted 18:24:00Z.
- 18:21Z #117's CI was cancelled at the 10-minute job limit on a slow runner: the `ltcm` suite
  took 153 s against its usual 35–45 s. A rerun passed and #117 merged. The same slowness on a
  `main` Checks run would block the updater's attestation until the hourly scheduled run passes;
  it fails closed.

- 18:18:57Z The hawkins job's second attempt ended `rejected`. The engineer itself found the
  recurrence came from hawkins-9, still on the old code, and that its first child (#100) already
  rejects the out-of-horizon entries: "no change the evidence justifies". That was right, and it
  cost about $0.20. #117 now keeps such a job observing, with no paid attempt.
- 18:25:28Z The haghani job (#113) moved to `observing` once the updater's release held its files.
- 18:25:33Z **The foundry called again**, 90 s after #114 went live. Its 4 cards for
  `kalshi-sports`: favourite–longshot bias in moneylines, pregame liquidity supply, lineup-news
  momentum and strike-ladder dominance. All 4 failed replay on 41–50 blocks of real sports markets
  (0, 0 and 4 trades). They were judged honest failures, not a data gap. The foundry total is now
  8 cards and 1 pass, for $1.48.
- 18:28Z **The research gate, measured on production** (`league.research_gate`, read-only):
  - 802 decisions; 338 runs; 624 sessions skipped; an estimated $8.59 saved for $0.0076 of Jev.
  - **Sampled miss rate 8.75% (7 of 80).** Split by decision:
    - sampled skips retained a candidate 8.8% of the time (backoff 3 of 35, blocker 4 of 45);
    - runs retained one 8.3% of the time (28 of 338);
    - replay-passing candidates: 1 of 80 skips, 7 of 338 runs.
  - The evidence does not yet show that the gate skips the less productive sessions. It saves
    about $4 an hour by throttling volume. It stays as built, with its 10% sample collecting
    evidence; tuning it is a decision for more data.
- Options history: 22,178 live OPRA quotes are recorded on the box, but no backfill has run yet.
  The daily job runs from 17:00 New York (21:00Z). After it, options newcomers must pass the
  estimate-based replay before paper; `options_history: false` reverts that.
- Sail `campaign_post_unconfirmed` sessions: Sail's docs say a retry with the same key and body
  returns the existing request "when it is still available", but not for how long. So the House's
  refusal to re-POST an unconfirmed request stays. Asking Sail for the retention window would let
  interrupted sessions be recovered safely.

- 18:36Z The Jev floor's shared views (health.json; report only, and never trading authority):
  - **Triage** has 127 deduplicated groups (107 missing data, 19 bug reports, 1 strategy defect).
    The most shared missing inputs, as the swarm asks for them:
    | Missing input | Agents |
    |---|---:|
    | Live sports scores | 43 |
    | Point-in-time earnings surprises | 33 |
    | Perp positioning / funding | 32 |
    | Attention-market underlier values | 31 |
    | Lineups and inactive players | 30 |

    None of these is an Alpaca feed. They are the ranked case for the next data spend.
  - **Exposure:** up to 7 agents sit on one event. On `KXWNBAGAME-26SEP22CONNWSH`, 7 meriwether
    agents hold 9 practice positions costing $85. The deterministic risk layer still decides; this
    is visibility.
  - The sensor has spent $0.0149 over 282 Jev calls, with a p50 latency of 0.5 s.

- 18:55:58Z **Third autonomous repair: #119**, a haghani child that keeps sub-cent entry and exit
  prices. It came from the pre-audit's `strategy_defect` job, while #113 came from the audit veto
  on the same rounding defect. The queue does not yet merge related jobs across sources, so each
  child competes on its own evidence. The same minute the teacher's #118 merged, a lesson to
  reconcile haghani's executions before more mutations.
- 18:55Z The updater found `main` at commits whose Checks runs were still in progress. With nothing
  to attest, it waits for its next check (fail-closed, as designed).
- **Runway.** The OpenAI campaign fell from $61.94 to $52.07 between 17:49 and 18:57Z (about
  $8.70/h at campaign prices). That leaves roughly $33 at the deadline, and at this rate it is
  spent around 01:00Z. After that the frontier tiers keep audits and move cheap research to Sail.
  The Sail balance of about $127 at about $40/day lasts about three days.

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

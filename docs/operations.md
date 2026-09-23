# Operating the league

This is the operator's page for the league as rebuilt on September 22, 2026
([execution record](runs/2026-09-22-overnight-rebuild.md)) and revised on September 23
([Dynamism II](runs/2026-09-23-dynamism-ii.md)): how to pause and resume it, inspect it,
deploy and roll it back, and recover it. The box itself is described in
[deploy/README.md](../deploy/README.md), and real money in [runbook-go-live.md](runbook-go-live.md).
Commands run from the repository root on the owner's machine unless they say "on the box".

## The loop

The work flows through these stages:

1. **Triage.** New evidence (fills, settlements, verdicts, refusals, journals, audit vetoes, failed
   pull requests) is triaged by code first and by Jev second. The outputs are `research.gate`
   decisions, explicit `agent.inactive` reasons and deduplicated `repair.reported` jobs.
2. **Work.** Each piece of work goes to one of three workers:
   - an agent's **research pass**: Luna, or Sail DeepSeek, with cached prompts;
   - a **hypothesis card** written by Merton on GPT-6 Sol (the foundry, `league/hypotheses.py`);
   - a **repair**: the engineer (`league/engineer.py`) patches strategies, tools, dials and lessons
     by pull request, and revises against CI's own failure text.
3. **Birth and replay.** A merged strategy is born on rung 0, repairs first, even into a full
   league (Sept 23, 2026). Every new program is replayed:
   - Alpaca programs on deep history (`league/deep_replay.py`), and then on the sealed holdout
     before a paper seat;
   - options programs on option history (`league/options_replay.py`);
   - Kalshi programs on recorded markets.
4. **The ladder.** Paper, then the screen. A screen-passer takes the micro stake at once, under
   the live grant, and is audited there (off the tick); a veto sends it back to paper. An agent
   with a known defect is audited before promotion instead.
5. **Feedback.** Results and repairs feed the next round.

## Pause, resume, stop

```sh
python3 scripts/floor_box.py maintenance on --reason "why"   # pause: paid work and new entries stop
python3 scripts/floor_box.py maintenance status
python3 scripts/floor_box.py maintenance off                 # resume on the next tick
```

`maintenance on` writes `/workspace/state/PAUSE`, and the House keeps ticking.

- **What stops:**
  - research;
  - Merton's roles, the foundry and the engineer;
  - Jev's jobs;
  - births and payouts;
  - promotions;
  - every new entry.
- **What continues:**
  - holders are still woken, and their sells and cancels reach the books;
  - reconciliation, marks, horizon exits, real-money judging and publishing;
  - an audit owed to an agent already on the micro rung, because its real-money book is still
    judged (audit after promotion, Sept 23, 2026).
- **Research in flight** defers at its next paid turn and resumes from its durable job.
- **Clocks:** paper records are not judged while paused, and clock-based culls wait.
- **Measured on Sept 22:** six paused hours cost nothing beyond box hosting.
- **Resuming:** expect the first open tick to be long (about 4 minutes), because every agent is due
  at once.

The alternatives:

- `floor_box.py stop` ends the loop, and every exit with it. Prefer `maintenance on`.
- `python3 scripts/gateway_admin.py kill` stops real-money orders at the gateway.

## Deploy and roll back

There are two paths to the box, and both go through the in-box watchdog. The watchdog runs 3
canary ticks on a simulated venue, promotes, then watches the House for 10 minutes. A stale
`health.json` or any error-level alert during the watch rolls back.

- **The updater (automatic).** Every 30 minutes the House reads `main`'s head and deploys it by
  itself. It does so only if both of these hold:
  - GitHub's Checks passed on that exact commit. The attestation is kept in `ops.deploy` and in
    `deploys.jsonl`.
  - The change touches no protected file (`league/ci.py` FORBIDDEN): the judges, the money rules,
    the campaign meter, the agent-box seal and the workflows.

  A protected change is refused with the warning "this one is the owner's deploy". Merton's
  merged pull requests (strategies, tools, lessons, dials) arrive this way.
- **The owner's deploy.** `python3 scripts/floor_box.py deploy` sends the working tree.
  - Use it for protected changes.
  - Only one deploy runs at a time. If you see `REFUSED: another deploy or rollback is running
    (pid N)`, the updater is mid-deploy. Wait for that watchdog to exit (`league.watchdog
    status`, on the box), then deploy again.
- **A money rule.** The live grant `earned-live-20260921` pins `constitution.money_digest()`:
  every rule except the version, the budgets, the replay gate and death on paper (`RISK_FREE`).
  Changing a money rule (Sept 23, 2026: `ladder.paper.settled_day` and `ladder.paper.audit`) takes
  three steps:
  1. Change `league/constitution.py` and re-pin `PINNED_DIGEST` in the same commit, which
     `league/tests/test_constitution.py` checks. The owner makes that commit.
  2. Deploy it with the owner's deploy: the updater refuses the constitution.
  3. Re-ratify the grant at once, from the owner's machine:
     `python3 scripts/live_trading.py --ratify earned-live-20260921`.

  Until step 3 the grant reads inactive (`live_trading.active` false). Real-money entries are
  refused while exits continue, no agent is promoted to real money, and the House drops the
  funded burst's settings. Ratifying re-pins the same capital to the new money digest, keeps the
  old policy in `live_ratifications` and restarts the House, which reloads those settings. It never
  enlarges the capital, and a revoked grant cannot be ratified.
- **Roll back by hand (on the box):**
  `cd /workspace/previous && /workspace/.venv/bin/python -m league.watchdog rollback --base /workspace --reason "why"`
- **The gateway.** Deploy with
  `cd gateway && node --test test/*.test.mjs && npx --yes wrangler@4 deploy --config wrangler.jsonc`;
  roll it back with `npx wrangler rollback`.
- **Checkpoint the box before risky work:**
  `python3 scripts/floor_box.py checkpoint --name why --ttl-days 30`.
  - It contains the box's credentials.
  - Sept 22's pre-rebuild checkpoint is `sbcp_9dc7fd6b-88e4-4e59-9b2e-78cf031114a0`, which expires
    2026-10-22.

## Inspect

- **`python3 scripts/floor_box.py status`:** the box, the loop, releases, the last deploy, health and
  the log tail.
- **`/workspace/state/health.json`** is written every tick:
  - `campaign`: what each provider has left, the burst, the live grant and `pending_calls` (holds
    not yet settled).
  - `hypotheses`: cards, pending evaluations, the foundry's `refusal` reason and its window spend.
  - `jev`: gate totals, the sensor's spend against its caps, triage groups and exposure groups.
  - `background_jobs`, `durable_research` and `promotion_status`.
- **`promotion_status`** has a row for each living agent on paper or above that has been judged,
  with the `stage` its next move waits on. Each change of stage or reason is also an
  `eval.verdict` row with `decision: "progress"`. Since Sept 23, 2026:
  - `promoted`: the screen and allocation gates passed. Under audit after promotion the reason
    says the frontier audit follows on the micro rung.
  - `audit_confirmed`: the audit after promotion approved it.
  - `audit_retry`: the audit could not run. The agent trades the micro stake and is audited
    again after the half-hour error cooldown.
  - `audit_veto`: the audit refused it. After promotion this comes with a `demote` row whose
    reason begins "the frontier audit after promotion vetoed it".
  - `auditing`: an audit before promotion, for an agent with a known defect.
  - `audit_cooldown`, `tuition`, `campaign`, `live_book`, `accounting_integrity`, `paused` and
    `evidence` say what else holds it. `audit_credits` appears only when `audit.house_pays` is off.
- **Ledger rows from the Sept 23 revision:**
  - an `eval.verdict` progress row on rung 0 with `stage: "holdout"`: a development replay passed
    and the sealed holdout refused or failed it, with the reason and the holdout's coarse numbers;
  - a promotion to the micro rung under audit after promotion carries `audit_timing: "after"`;
  - `audit.verdict` carries `paid_by` (`house` or `agent`);
  - `agent.died` has two new causes, `superseded` (a born corrected child replaces its code) and
    `redundant` (the holdout would not evaluate its passing replay, and the same program already
    holds a paper seat);
  - `ops.budget` with `what: "holds absorbed"`: the Sail holds released into the meter, with
    `absorbed`, `usd`, `measured_usd` and `settled_usd`. Each hold's evidence is in
    `campaigns.sqlite` `cost_reconciliations`, under `absorbed:<commitment>`.
- **`/workspace/state/repairs.json`:** the repair queue by state, its top jobs and the engineer's
  last step.
- **Read-only reports, on the box.** Every database is opened `mode=ro`.
  - `scripts/economics.py --ledger /workspace/state/ledger.sqlite [--since ISO] [--until ISO]`
    reports:
    - real and practice P&L, never summed together;
    - spend by provider;
    - useful work per dollar;
    - sample-size warnings.
  - `python -m league.research_gate /workspace/state/ledger.sqlite`: the gate's decisions, estimated
    savings and sampled miss rate.
  - `python -m league.history coverage --root /workspace/state`: what history is stored, what is
    unavailable, and what has not been fetched.
  - `scripts/repair_drill.py --inspect`: the repair drill's states.
- **New ledger kinds**, all private:
  - `hypothesis.card`, `hypothesis.link` and `hypothesis.retired`;
  - `repair.reported` and `repair.status`;
  - `research.gate` and `agent.inactive`;
  - `route.decision` and `trace.record`;
  - `data.coverage` and `holdout.access`;
  - `triage.item`.

## Recover

- **The budget reads "stopped" but money is left.** Read `meter_health` in
  `/workspace/state/campaigns.sqlite`: a failed Sail meter stops every paid lane.
  - Until #110, the meter read the usage summary's `range=period` figure. On this plan that figure
    is a rolling seven-day window, and it fell at 16:47:39Z on Sept 22. The meter latched and the
    whole floor stopped.
  - The meter now reads the account balance: every decrease is spend, and a top-up is never
    credited back.
  - The first balance reading cleared the old latch, and its evidence is in
    `meter_reconciliations`.
  - A missing balance now leaves the meter unread for that minute; it never latches.
- **The campaign reads far less left than the accounts hold.** Look at the holds first:
  `pending_calls` in `health.json` `campaign`, or the `commitments` rows with no `cost` in
  `campaigns.sqlite`. Since Sept 23, 2026 the House releases what it can prove:
  - **Sail.** Every ten minutes, once the balance meter has been read, a hold older than an hour
    with no linked response is absorbed into the meter (`CampaignBudget.absorb_stale`). Such a
    request's POST was never confirmed, and whatever the vendor charged for it is already inside
    the meter. Nothing is absorbed while the meter is unhealthy or reads less than what has been
    settled since the burst began. Measured before the fix (Sept 22, 23:50Z): 329 holds ($60.59)
    made the campaign read $54.76 left while the account held $116.
  - **OpenAI.** A verified frontier call settles at the gateway's metered cost, and a refused one
    (HTTP 4xx) at $0. Before, every call was booked at the long-context ceiling when that was
    higher, and the House's line closed at about half the owner's real spend.
  - **What stays held.** A frontier call that never answered (5xx, a timeout, a dropped
    connection) keeps its worst case, because the gateway keeps its worst case on the month too,
    so there is no measured cost to settle it at. The Jev earmark's holds stay until that route
    is closed and billed. Releasing either needs vendor receipts.
- **Research ends with `provider: campaign_post_unconfirmed`.** A Sail request was in flight when
  the House restarted. The House cannot prove whether the vendor accepted it, so it will not buy it
  again inside the idempotency window, and the agent researches on its next due session. Many at
  once means many restarts.
- **Durable research older than six hours expires** after a long pause
  ("session expired after six hours").
- **A dead agent's exits are refused as "has no seat on the book."** This is fixed by #106:
  wind-downs are seated first. A death during a venue outage is recorded, and its exits are retried
  by the mark pass (#107).
- **"does not reconcile" on a paper book, by cents.** This is a warning, not an error (#108): it is
  the venue's end-of-day fee activity. An error means real money, or positions that disagree; read
  the `book.reconciled` rows.
- **File a repair.** Drop a JSON file into `/workspace/state/repairs-inbox/`:
  `{"key", "kind", "summary", "agents", "severity"}`. It is admitted whatever its priority.
  `{"drill": "<stamp>"}` plants the labelled synthetic drill; `scripts/repair_drill.py --plant`
  writes one for you.
- **Restore.** `floor_box.py fork --from <checkpoint> --i-know` gives you a second box. Never run
  two Houses on one paper account.

## Switches

Change them by pull request, and deploy through the canary. "Off" means the House behaves as it did
before that feature. The two constitution rows are money rules: changing one needs the owner's
deploy and a re-ratified grant (see "A money rule" above).

| File | Key | Default | What it does |
|---|---|---|---|
| `league/config.json` | `semantic_lab` | `false` | The continuous Jev midpoint labeller. It stays off: a capped evaluation found no tradable value |
| | `jev.enabled`, `jev.daily_usd`, `jev.daily_calls` | on, $0.25, 400 | The Jev floor: gate relevance, triage, hypothesis links, exposure |
| | `deep_replay`, `holdout_gate` | on | Deep Alpaca history for replay, and the sealed holdout before paper |
| | `options_history` | on | Options history, options replay, and IV/skew/activity features |
| | `research_traces` | on | Private research transcripts with their cost and outcome (for eventual fine-tuning) |
| `league/house.py` | `Settings.enroll_displaces` | on | A merged strategy takes a seat in a full league, repairs first: from an agent still running the code it corrects, else from the weakest eligible resident. A born corrected child retires the agents off real money still running that code (`superseded`). Off: merged strategies wait for an empty seat |
| `league/game.json` | `audit.house_pays` | on | The House pays for promotion audits. Off: the agent pays at cost, and one under `audit.min_credits_usd` ($0.60) waits at `audit_credits` |
| | `research.gate.enabled`, `after`, `max_factor`, `sample_percent` | on, 2, 8, 10 | Back off research whose passes come back empty while nothing about the agent has changed; a 10% sample still runs. The routine epoch payout is not a trigger (Sept 23, 2026) |
| | `research.pace.winner_share`, `loser_multiple`, `unproven_multiple` | 0.1, 8, 3 | Research interval multiples: an earned profitable record 0.1x; a losing one on paper or above with 5 observations 8x; no earned record 3x, unless the agent is idle, when its research is pulled forward instead. `unproven_multiple` 1 turns the last off; until Sept 23, 2026 winners waited 0.33x and losers 4x |
| | `hypotheses.enabled`, `replace_mutation_refill`, `call_minutes`, `budget_usd` | on, on, 10, $40 per 24 h | The hypothesis foundry, which replaces blind House mutations (15 minutes and $20 until Sept 23, 2026) |
| | `hypotheses.fast_desks`, `fast_share` | six desks, 0.5 | Up to half the foundry's calls go to the hourly, around-the-clock desks: both Alpaca crypto desks, both Kalshi crypto desks, index ETFs and megacaps, rotating to the one with the fewest recent cards (until Sept 23, 2026 always the best-scored one, the index-ETF desk). `fast_share` 0 is off |
| | `hypotheses.transfer_share` | 0.3 | Up to 30% of the foundry's calls port a family with an earned forward record (real money first) to the best-scored desk of its venue where it has never been tried; the packet carries its mechanism in words and asks for at least half the batch as adaptations. Offered before the fast route, then exploration, then evidence. 0 is off, as before Sept 23, 2026 |
| | `hypotheses.prefer_horizon` | `hour` | The horizon the foundry's packet tells Merton to prefer where a desk allows it. Empty: the desk's first listed horizon |
| | `hypotheses.max_pending_cards` | 8 | How many cards may await replay before the next call. 0: any pending card holds the next call, as before Sept 23, 2026 |
| | `economy.line_exhausted_trials`, `explore_every` | 15, 5 | Retire lines with 15 failed trials and no pass; one birth in five explores |
| `league/constitution.py` | `ladder.paper.settled_day` | 1 finished day once 3 trades have settled | A daily agent on a Kalshi book is screened after one finished active day once three of its trades have settled on paper. Since the swing-and-bunt revision every daily agent's screen is one finished day, so the lane only matters again if `min_active_blocks_day` rises |
| | `ladder.paper` `min_active_blocks`, `min_active_blocks_day`, `max_drawdown` | 3, 1, 0.25 | The screen to the micro rung (4, 2 and 0.15 until the owner's swing-and-bunt revision of Sept 23, 2026 ~03:10 UTC) |
| | `ladder.promotion_alpha`, `ladder.look_every_active_blocks`, `ladder.micro.min_active_blocks` | 0.20, 3, 3 | Promotion to scaled size spends 0.20 across looks every 3 active blocks, from the 3rd; death keeps `alpha` 0.05 (0.05, 5 and 5 before the swing-and-bunt revision) |
| | `ladder.family` `alpha`, `min_member_active_blocks` | 0.20, 5 | A family's pooled real-money record promotes a member at the promotion budget, members counted after 5 active blocks (0.05 and 10 before) |
| | `rungs.3` `kelly_fraction`, `max_share_of_venue` | 1.0, 0.6 | Full Kelly on the lower bound, up to 60% of the venue's cash (0.5 and 0.4 before) |
| | `ladder.death.max_drawdown` | 0.40 | Death's drawdown on any rung above replay (0.30 before) |
| | `ladder.replay.min_oos_growth` | -0.0005 | Out-of-sample growth need only clear -0.05% a block for a paper seat (above zero before), and one out-of-sample block must be active. Risk-free: the live grant's money digest does not include it. When it loosens, the House brings back once, on its line, the code of rung-0 deaths of the last two days whose replay failed only on out-of-sample growth now admitted (`House._revive_near_misses`: at most 12, never more than half the free seats) |
| | `ladder.paper.audit` | `after` | A screen-passer takes the micro stake at once and is audited there; a veto demotes it. An agent with a known defect is still audited first. `before`: the audit precedes promotion, as before Sept 23, 2026 |
| `league/engineer.json` | `enabled`, `max_attempts`, `max_job_usd` | on, 3, $5 | The repair engineer. No Merton role may write this file. Since Sept 23, 2026 its paid queue is ordered by priority times the forward record of the job's agents (x3 on real money or earning, x0.5 when all are dead or on replay; `league/service.py` `evidence_weight_of`); requested jobs stay first |
| `league/research_routes.json` | `cache.layout`, `cache.explicit_hints` | `messages`, on | The Luna cache layout; `packet` is the old layout |
| | `routing.sail_by_evidence` | off | Let measured evidence move new Sail sessions to a cheaper tier |
| `league/turbo.json` | `research_minutes`, `research_workers`, `replay_workers` | 15, 16, 12 | The funded burst's research interval and workers (5, 32 and 8 until Sept 23, 2026). In force while the burst is, which it is while the live grant is active |
| | `max_population`, `newcomer_seconds`, `endowment_usd` | 96, 120 s, $8 | The burst's population ceiling (64 until Sept 23, 2026, when foundry cards that passed replay waited for seats), newcomer cadence and House endowment |
| | `fork_threshold_usd` | $10 | The credits an agent needs before it may fork a parameter copy of itself. Above the endowment, so only an agent that has earned payouts forks. Until Sept 23, 2026 the burst forced $2, every newborn forked at once (22 copies in 40 minutes), and the foundry's replay-passing cards waited for seats on full desks |
| | `merton_schedule_hours` | operator 48, designer 96, toolsmith 12, architect 12, teacher 4 | Merton's burst cadence, set by each role's measured yield (operator 4, designer 12, toolsmith 3, architect 2, teacher 1 until Sept 23, 2026) |
| | `luna_fraction` | 0.95 | The share of agents whose research runs on GPT-6 Luna; the rest stay on Sail as the comparison (a Luna session cost about $0.011 against about $0.06 on Sail, Sept 23, 2026) |
| `league/niches.json` | `max_members` | Kalshi: crypto strikes 8, crypto 15-minute 8, weather 10, sports 12, props 6, prices 8. Alpaca: crypto majors and alts, index ETFs and megacaps 12 each, options 8 | How many agents a desk may hold. Raised Sept 23, 2026 so seats follow evidence (weather is the one mechanism earning real money) |

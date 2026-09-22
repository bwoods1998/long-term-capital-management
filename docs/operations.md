# Operating the league

This is the operator's page for the league as rebuilt on September 22, 2026
([execution record](runs/2026-09-22-overnight-rebuild.md)): how to pause and resume it, inspect it,
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
   - a **hypothesis card** written by Merton (the foundry, `league/hypotheses.py`);
   - a **repair**: the engineer (`league/engineer.py`) patches strategies, tools, dials and lessons
     by pull request, and revises against CI's own failure text.
3. **Replay.** Every new program is replayed:
   - Alpaca programs on deep history (`league/deep_replay.py`), and then on the sealed holdout
     before a paper seat;
   - options programs on option history (`league/options_replay.py`);
   - Kalshi programs on recorded markets.
4. **The ladder.** Paper, then an audit (off the tick), then real money under the existing ladder
   and the live grant.
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
  - reconciliation, marks, horizon exits, real-money judging and publishing.
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
  - `campaign`: what each provider has left, the burst, and the live grant.
  - `hypotheses`: cards, pending evaluations, the foundry's `refusal` reason and its window spend.
  - `jev`: gate totals, the sensor's spend against its caps, triage groups and exposure groups.
  - `background_jobs`, `durable_research` and `promotion_status`.
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
before that feature.

| File | Key | Default | What it does |
|---|---|---|---|
| `league/config.json` | `semantic_lab` | `false` | The continuous Jev midpoint labeller. It stays off: a capped evaluation found no tradable value |
| | `jev.enabled`, `jev.daily_usd`, `jev.daily_calls` | on, $0.25, 400 | The Jev floor: gate relevance, triage, hypothesis links, exposure |
| | `deep_replay`, `holdout_gate` | on | Deep Alpaca history for replay, and the sealed holdout before paper |
| | `options_history` | on | Options history, options replay, and IV/skew/activity features |
| | `research_traces` | on | Private research transcripts with their cost and outcome (for eventual fine-tuning) |
| `league/game.json` | `research.gate.enabled`, `after`, `max_factor`, `sample_percent` | on, 2, 8, 10 | Back off research whose passes come back empty while nothing about the agent has changed; a 10% sample still runs |
| | `hypotheses.enabled`, `replace_mutation_refill`, `call_minutes`, `budget_usd` | on, on, 30, $20 per 24 h | The hypothesis foundry, which replaces blind House mutations |
| | `economy.line_exhausted_trials`, `explore_every` | 15, 5 | Retire lines with 15 failed trials and no pass; one birth in five explores |
| `league/engineer.json` | `enabled`, `max_attempts`, `max_job_usd` | on, 3, $5 | The repair engineer. No Merton role may write this file |
| `league/research_routes.json` | `cache.layout`, `cache.explicit_hints` | `messages`, on | The Luna cache layout; `packet` is the old layout |
| | `routing.sail_by_evidence` | off | Let measured evidence move new Sail sessions to a cheaper tier |
| `league/turbo.json` | `merton_schedule_hours` | operator 4, designer 12, toolsmith 3, architect 2, teacher 1 | Merton's burst cadence, set by each role's measured yield |

# Operating the league

This is the operator's page for the league as rebuilt on September 22, 2026
([execution record](runs/2026-09-22-overnight-rebuild.md)), revised on September 23
([Dynamism II](runs/2026-09-23-dynamism-ii.md)) and rebuilt around capital the same day
([the north-star build](runs/2026-09-23-capital-ladder.md): the allocator, the capital board,
sliced exits, the Alpha Lab, a tick that never blocks, profit-indexed compute and the open desks).
It says how to pause and resume the league, inspect it, deploy and roll it back, and recover it.
The box itself is described in [deploy/README.md](../deploy/README.md), and real money in
[runbook-go-live.md](runbook-go-live.md).
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
4. **Bands of capital** (since Sept 23, 2026). At every mark pass the allocator
   (`league/allocator.py`) reads each agent's evidence (its wealth multiple) and moves it between
   Paper, Bunt and Swing, sizing its real stake inside the live grant's envelope. Since Sept 24, 2026
   (promotion on proof) a bunt is a PROBE ($10 Kalshi, $25 Alpaca) unless the agent's family's pooled
   record is proven, and counts on Kalshi are once per event. The first swing is
   audited, and an agent with a known defect is audited before its bunt. With `allocator.enabled`
   off, the old ladder decides again: the screen, then the micro stake with the audit after it.
5. **The Alpha Lab** (since Sept 23, 2026). Off the tick, the lab searches strategy programs in
   batches on its own box and sends the fittest of each cell through the House's replay and the
   sealed holdout; survivors are born on paper. Since Sept 24, 2026 (E1) half of each batch and
   half of its tape builds go to the programs someone wrote, and a graduate needs a code change
   beyond its parameters or a forward score above its desk's living median (see the lab below).
6. **Feedback.** Results and repairs feed the next round.

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
  - the Alpha Lab (it also stops while a release is staged and when the Sail meter stops the
    floor; an OpenAI tier below `all` stops only its Luna and Sol calls, since Sept 23, 2026);
  - every new entry.
- **What continues:**
  - holders are still woken, and their sells and cancels reach the books;
  - reconciliation, marks, horizon exits, real-money judging and publishing;
  - the allocator's pass, except moves up: moves down, deaths on paper wealth, stake sizing and
    the board (no agent moves up to a bunt or a swing while paused);
  - an audit owed to an agent already on the micro rung, because its real-money book is still
    judged (audit after promotion, Sept 23, 2026).
- **Research in flight** defers at its next paid turn and resumes from its durable job.
- **Clocks:** paper records are not judged while paused, and clock-based culls wait.
- **Measured on Sept 22:** six paused hours cost nothing beyond box hosting.
- **Resuming:** expect the first open tick to be long (about 4 minutes), because every agent is due
  at once. The backlog is drained one desk at a time, the desk longest without a wake first (Sept
  23, 2026: after the 15:28Z resume on Sept 22 the first seventeen minutes had reached five of the
  twelve desks in deadline order, and the 24/7 crypto desks waited), so every desk sees a wake
  within the first few ticks; the drain still runs at `cold_wakes_per_tick` (5) for the House's
  first five minutes and `max_wakes_per_tick` (16) after.
- **What the pause is, on the record:** the ledger shows the two Sept 22 wake holes as a pause
  lifting at 15:28:11Z (every kind of work resumed in that second) and a Sail allowance closing at
  11:01Z on Sept 21. Neither is a scheduler fault, and the House now says which markets a stop
  leaves unattended: a warning for each round-the-clock desk (coins, Kalshi) with living members
  and no wake for 30 minutes, or for twice its briskest member's `wake_minutes` when that is longer,
  while the House is NOT paused, told once per that long (`House._order_path_invariants`). The clock
  starts at the latest of the desk's last wake, the House's start, a pause and its oldest living
  member's birth. Sept 24, 2026: kalshi-attention's one member, waking every 30 minutes as scheduled,
  was called unwoken twelve times that day at 30 or 31 minutes, and kalshi-open was called unwoken
  "for 146 minutes" 29 seconds after its first member ever was born (the clock had started at the
  House's own start); since then neither is a warning. And a warning once a day when an intent is refused for an agent
  that is not alive (the House's own wind-down walking into a wall each mark pass, as 607 "no seat"
  and 576 "outside regular hours" refusals did on Sept 21-23 before anyone read the ledger).

The alternatives:

- `floor_box.py stop` ends the loop, and every exit with it. Prefer `maintenance on`.
- `python3 scripts/gateway_admin.py kill` stops real-money orders at the gateway.

## Deploy and roll back

There are two paths to the box, and both go through the in-box watchdog. The watchdog runs 3
canary ticks on a simulated venue, promotes, then watches the House for 10 minutes. A stale
`health.json` or any error-level alert during the watch rolls back, and so does a health failure
(`health.json` `failures`) -- except a condition that began before the promotion (L3, Sept 24,
2026): a failure whose `since`, or an error whose `began_at` (a warning that had been repeating, a
health failure the House announced), is earlier than the reading taken just before the promotion is
inherited, reported in the deploy's detail and never a rollback. The lab's idle hour therefore never
rolls a release back (it cannot begin inside a ten-minute watch); a canary inherits nothing and
refuses on any of them, though a canary runs no lab; `league.watchdog status` shows them all. A frozen
book counts only in a `health.json` the new House wrote (dated at or after its first `ops.started`
since the promotion): until its first tick finishes, the file is the old process's, and a freeze in
it is reported as `frozen_by_previous_process`, never a rollback (Sept 24, 2026: Deploy C was rolled
back at 15:39:27Z on a practice-book freeze the old House recorded 30 s before the promotion). The
old file still goes stale after `max_age_seconds`, and a House that never restarts still fails the
watch.

- **The updater (automatic).** Every 30 minutes the House reads `main`'s head and deploys it by
  itself. It does so only if both of these hold:
  - GitHub's Checks passed on that exact commit. The attestation is kept in `ops.deploy` and in
    `deploys.jsonl`.
  - The change touches no protected file (`league/ci.py` FORBIDDEN): the judges, the money rules,
    the campaign meter, the agent-box seal and the workflows.

  A protected change is refused with the warning "this one is the owner's deploy". Merton's
  merged pull requests (strategies, tools, lessons, dials) arrive this way. The Checks workflow's
  tests job has 20 minutes (Sept 24, 2026: the 3.14 job hit a 10-minute limit twice in a row, and
  took 9-14 minutes on the day's later heads); a change to `.github/workflows/` re-pins
  `TRUSTED_WORKFLOWS_SHA256` in `league/updater.py` in the same commit (a test fails otherwise) and
  reaches the box only by the owner's deploy, after which the updater trusts the new workflow.
- **The release train (Sept 25, 2026).** A head that may ship waits while any of three holds
  stands, and ships at the first look after they all lift (the updater looks again the moment the
  last one lifts, not up to half an hour later):
  - *The train:* one updater release every `release_train_hours` (`league/config.json`, default 4;
    `league/ci.py` `CONFIG_DIALS` bounds it 2-6, so the operator may move it inside that). It is
    measured from the last updater release that restarted the House (its `promote` row in
    `deploys.jsonl`). A rolled-back attempt counts; a canary refusal does not, because nothing
    restarted. A head rolled back once is tried once more at the next train; twice, never again.
  - *The US session:* no launch on a day the House's calendar (`ltcm.data.us_equity_session`, the
    one `league/house.py` uses) calls a trading day, from 12:55Z to 20:05Z. The window is 13:25Z to
    20:05Z, or the session's own open and close with five minutes each side when that is wider
    (14:25-21:05Z in winter). The launch stops 30 minutes before it opens, because the canary
    (2.2-4.0 minutes to the restart on Sept 24-25), the ten-minute watch and any rollback all
    restart the House. Weekends and NYSE holidays have no window.
  - *A recent start:* none within 30 minutes of the ledger's last `ops.started`, whatever caused it.

  Why: the House restarted 26 times in the 24 hours to 04:23Z Sept 25 (24-37 a day on Sept 20-24),
  and seven of those restarts fell inside the Sept 24 session. The updater alone launched 14
  releases in the day from 02:15Z Sept 24, one of them at 14:58Z, inside the session. Every restart
  kills the research and wakes in flight.

  A held head is `held` in the updater's answer, with `holds` (train, session, recent_start), the
  reasons and `next_eligible_at`. It is written once per head per reason: a `stage: train` row in
  `deploys.jsonl` and an `ops.deploy` row with `action: held` on the ledger. It raises no warning.
  A protected head is still refused at once, whatever holds. `scripts/floor_watch.py` prints all of
  it on its `## releases` line: restarts in the last day (health.json `restarts_24h` when present,
  else the ledger's `ops.started`), the last updater ship and launch, the holds now, the last hold
  on the ledger and the next eligible time.

  The owner's deploy (`floor_box.py deploy`) is not held by the train. Deploy outside the session
  anyway: the plan's rule is no deploy between 13:25Z and 20:05Z on a trading day, except a rollback.
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
- **The allocator's deploy (Sept 23, 2026).** The `allocator` section is a money rule. Run
  `floor_box.py deploy` in the background and watch its log. At `promoted`, run
  `python3 scripts/live_trading.py --ratify earned-live-20260921` at once. Until the ratify
  finishes, `_live_open` is false and the allocator seats nobody on real money. The first
  mark pass then does two things:
  - It shrinks the legacy $60 micro stakes toward their bunt stake. Only free cash moves.
  - It publishes `allocator-board.json`. Read it with `python3 scripts/floor_watch.py`.
- **Is it a money rule?** Compare
  `python3 -c "from league.constitution import digest, money_digest; print(digest(), money_digest())"`
  on the tree you deploy with the grant's digest (`floor_watch.py` prints it). Only a changed money
  digest needs the ratify. The close-the-gaps run's R5 (Sept 24, 2026, its third and last digest change:
  `allocator.family_probe`, no probe on a losing family) moves them to constitution `38a57fe9…`, money
  `535a7f15…`: its deploy needs the ratify (the grant's 101 seats unchanged). Its Deploy B (the mechanism
  ledger's unit, the family swing with its entry looks, `swing_requires_proven_family`,
  `corrected_child_supersedes`) had set constitution `915c978e…`, money `c02ed852…` (the grant's 101 seats
  unchanged: the smallest real stake is still the $10 probe). Its Deploy A had set `8116302e…` / `521c4586…`; at that run's T0 they were `34adf385…` / `c2b0e09c…` (40 agents, a $25 stake line). Deploy A of the
  learn-and-unblock run (17:34Z, Sept 23, 2026) had set `52c6c7e5…` / `1d63a56e…`, the grant
  re-ratified at 17:34:36Z. Before it: `9fa83727…` / `44e8d48d…`, ratified at 08:28:13Z (101 agents, a $10
  line); that day's Deploys 2-7 changed no money rule and needed no ratify.
- **Roll back by hand (on the box):**
  `cd /workspace/previous && /workspace/.venv/bin/python -m league.watchdog rollback --base /workspace --reason "why"`
- **The gateway.** Deploy with
  `cd gateway && node --test test/*.test.mjs && npx --yes wrangler@4 deploy --config wrangler.jsonc`;
  roll it back with `npx wrangler rollback`. After a deploy that touches the frontier month, read
  `/v1/health` `frontier`: `cap_usd` (the cap in force), `base_cap_usd` (`FRONTIER_MONTH_USD`) and
  `profit_index` (`equity_usd` against `baseline_usd`, `earned_usd`, `bonus_usd`, `read_ok`,
  `reason`). Since Sept 23, 2026 `/v1/health` reports the stored equity reading and never reads
  the venues itself, because the House reads its kill switch there on the order path. The first
  frontier call more than ten minutes after the last reading takes a new one. Since Sept 24, 2026
  it also reports `settled_usd` (the month's spend less the holds of calls still unanswered, to the
  microdollar), `inflight_usd` (those holds) and `previous` (the month that ended, with its
  `spent_usd` and `settled_usd`). The House's OpenAI meter reads all three, so deploy the gateway
  before a House release that reads them (below, **The OpenAI meter**).
- **Checkpoint the box before risky work:**
  `python3 scripts/floor_box.py checkpoint --name why --ttl-days 30`.
  - It contains the box's credentials.
  - Sept 22's pre-rebuild checkpoint is `sbcp_9dc7fd6b-88e4-4e59-9b2e-78cf031114a0`, which expires
    2026-10-22.

## Inspect

- **`python3 scripts/floor_box.py status`:** the box, the loop, releases, the last deploy, health and
  the log tail.
- **`python3 scripts/floor_watch.py [--since ISO] [--json]`** (Sept 23, 2026): the watch in one
  read-only command, from the owner's machine. It runs a snippet on the box that opens every
  database `mode=ro`, asks the gateway's `/v1/health` from the box, and reads the site's
  checkpoint from here. `--since` defaults to an hour ago. It prints:
  - health: release, tick seconds, living and dead, frozen books, the grant and its money digest,
    and background jobs running over ten minutes;
  - the tick's steps (`## tick steps`, Sept 24, 2026, from `health.json` `tick_steps`): the last
    tick's six slowest steps with their seconds, each step's slowest in the last hour with the time
    of that tick, and each background lane's last run;
  - bands per venue from `allocator-board.json`, band moves, births and deaths, the envelope and
    the throttle;
  - venue fills, notional, realized P&L and agents per book: the real accounts (`kalshi`,
    `alpaca`) on the "real money" line with the performance fees, and the practice books on their
    own line;
  - the top evidence (E, W_paper, W_real, trades, stake);
  - the lab's `lab.sqlite` table counts, its `lab.*` ledger rows, the batches it ran since `--since`,
    and from `health.json` whether its step is failing (`failing_since`, `failures_in_a_row`,
    `error`; D1, Sept 24, 2026);
  - the seat market (`## seats`, S1-S4 of the close-the-gaps run, Sept 24, 2026): waiters by class
    (the `retained` candidates of dead authors too), the displaceable count, the seats holding no
    evidence (`seats_holding_none`: count and the first ids), the desks' evidence clocks, and why each
    class of waiter was last refused a seat; and each House-sent sale stopped after three identical
    refusals (`wind down stopped`, from house.json `wind_down_refusals`). Since R2 (Sept 24, 2026) the
    `longest wait` line (class, id, desk, hours and the rule that holds its desk), an `over 2 h on`
    line a desk where newcomers have waited over two hours (count, longest, rule), and one line with
    the waiters that left the queue in the last day by rule and the population the league may grow to
    now (`population <now> of <ceiling>` and why, from Sail's runway);
  - costs (OpenAI settled in the hour and pending holds, Sail, Jev), the gateway's month with its
    `profit_index` (E1: equity, baseline, bonus and why) and, since Deploy A, `settled_usd`,
    `inflight_usd` and the `previous` month, refusals, alerts, and the site checkpoint's age and
    whether it carries the board;
  - the newest hourly yield row (spend, evidence and `usd_per` by line, and `by_profile`: research
    candidates per dollar by model profile). Until Sept 24, 2026 the watch looked for `"what":
    "yield"` with a space, which the ledger's canonical JSON never writes, and printed none;
  - `repeating_warnings`, the health `failures` and the `research_economy` block (L3 and L2, Sept 24,
    2026; below).

  `--since` takes any ISO time and is rewritten as `YYYY-MM-DDTHH:MM:SS` UTC before it is compared
  with the ledger's `at`; anything else is refused. Sept 24, 2026: sqlite's `datetime('now', ...)`
  writes a space where the ledger writes `T`, a space sorts before `T`, and that form admitted the
  whole day.
- **`python3 scripts/gap_scoreboard.py --snapshot DIR | --take DIR [--since ISO] [--baseline ISO]
  [--deploys FILE] [--json | --markdown]`** (Sept 24, 2026; the forward-first rows Sept 25): the
  scoreboard of [the forward-first plan](goals/LTCM_FORWARD_FIRST.md) and, kept in a second table,
  of [the close-the-gaps plan](goals/LTCM_CLOSE_THE_GAPS.md) (workstream Z of both), read-only, from
  a snapshot of the House's stores rather than the live box. `--take` backs up `ledger.sqlite`,
  `lab.sqlite`, `campaigns.sqlite` and `feeds.sqlite` on the box into `/tmp` (sqlite's backup API,
  each source opened `mode=ro`), downloads them gzipped with `health.json`, `house.json`,
  `allocator-board.json`, `allocator.json` and the watchdog's `/workspace/deploys.jsonl`, and deletes
  the box copies; `--snapshot` reads a directory taken before (`--deploys FILE` names a deploy log kept
  outside it; without one, deploys and rollbacks are read from the ledger, which cannot see a release
  killed before its first `ops.started`). The first table is the forward-first plan's seven rows with
  their targets: real settled profit a day against compute a day (`scripts/economics.py`'s method plus
  the lab's own calls in `lab.sqlite`, with the gateway's meter and the yield rows as checks) and the
  proven families' capacity at 1x, 2x and 4x their real size; the forward-positive share of the day's
  graduates and newborns; real dollars on proof, the swing clock and Alpaca real stock agents;
  restarts, rollbacks by cause, the tick interval's p50 and deploys inside a US session (the NYSE
  calendar); the seat queue, median life against each desk's evidence clock and the displacement
  share; the real fill rate per order, refused real entries by rule and probes' taker entries; Sail's
  runway, October's OpenAI cap and the population ceiling. Every part of a reading names the function
  that computed it. The second table is the close-the-gaps plan's seven metrics; then each row in
  detail, each desk's evidence clock (hours from a member's first fill to its third independent
  settlement), every family's pooled record (practice at weight 0.5, real at 1, one observation an
  event, a one-sided 80% Student's t bound) and the weather favourites' capacity. Its clock is the
  snapshot's newest ledger row; `--since` (default 24 hours before it) sets the window, and
  `--baseline` counts promotions only from a moment (Deploy A). Every definition is in the script's
  docstring.
- **`/workspace/state/health.json`** is written every tick:
  - `campaign`: what each provider has left, the burst, the live grant and `pending_calls` (holds
    not yet settled). `meters` (Sept 24, 2026) has one entry per metered provider (`sail`,
    `openai`): `ready` (read in the last 180 s), `checked_at`, and `line`, the burst line's
    arithmetic: `house_line_usd` = `cap_usd` - max(`settled_usd`, `measured_usd`) -
    `before_meter_usd` - `unmetered_settled_usd` - `pending_usd`; `provider_left_usd`, what the
    gateway's month has left at a fresh reading less what the House committed since (null without
    one); and `remaining_usd`, the smaller of the two, which is what every reader of the House's
    line sees. OpenAI's entry also has `month`: the gateway month last read, its highest reading
    (`high_usd`), the finals carried from earlier months (`carried_usd`), `settled_total_usd`, the
    month's own `cap_usd` and `spent_usd` at the last reading, `base_usd` (what the meter carried
    when `covers_from` last moved), `covers_from` and the check's `anchor`.
  - `hypotheses`: cards, pending evaluations, the foundry's `refusal` reason and its window spend.
  - `lab` (Sept 23, 2026): the Alpha Lab's `refusal`, `closed_since` and `closed_minutes`, `llm`
    (`paused`, `skipped`: the Luna and Sol phases skipped below the `all` tier), `waiting_seat`
    (`count`, `longest_hours`, up to eight graduates with their line, desk and hours), `queued`
    and `born_total`. Since D1 (Sept 24, 2026): `failing_since` (null until five steps in a row
    have failed; then the first failure's time, until a step works again), `failures_in_a_row`,
    `error` (the last failed step's, null once one works) and `tapes` (`search_copies` in memory,
    `indexed`: the tapes built in the last six hours that a restart remembers). Since E1 (Sept 24,
    2026): `held`, what the last graduation pass held back (`at`, `counts` by reason: `forward`, a
    losing forward window, its own or, with none, its mechanism's on average; `idle`, a desk offered markets for 48 h with no intent and no feed it
    asked for since; `nudge`, the same program beyond PARAMS as a living one on its desk without a
    forward score above the desk's median), or null.
  - `jev`: gate totals, the sensor's spend against its caps, triage groups and exposure groups.
  - `wakes_skipped` (Sept 24, 2026, the wake skip): the stock and option wakes not run while the
    regular session was shut (`count`, `by_desk`, `since`, `last_at`; kept in `house.json`). Such an
    agent is woken a few seconds after the bell instead; nothing it sent before then could trade.
    In the 48 hours before T0 of the close-the-gaps run there were 2,891 of them (29% of all wakes).
  - `feeds` (`league/feeds.py`): per feed its `keys`, how many are `recording`, `since`, `last_ok`,
    `failing` keys, `polls`, `snapshots` and `next_due`; for a history feed its `backfill`
    (`complete`, `in_progress`, `unlisted`); `store_mb`. Since Sept 24, 2026 the recorders of the
    allowed data hosts carry their `host`, and a keyed one (`eia`, `consensus`) its `waiting_for`
    until the owner's key is in the House's `.env` and its host in `LEAGUE_HOSTS`. Waiting is not
    failing. A key a source does not list (a stock Nasdaq shows no date for, a league whose board is
    not recorded yet) or a site that refuses the House (`polls`: RealClearPolling's bot wall) shows
    in `failing` with its reason and is not warned about hourly. Each recording feed also writes an
    hourly `data.coverage` ledger row (`asset: feed`, `host`, `status`: current, partial or
    unavailable). An `earnings` stock is named in the hourly "feeds: N of 24 earnings polls failed 3
    times in a row" warning only after three failed polls in a row (`Source.warn_after`), and EDGAR is
    given 45 s to answer (Sept 24, 2026: its browse feed took a median 6.4 s, 44% of polls over 10 s,
    and 31 of 995 polls hit the old 30 s read timeout, every stock read at its next poll; a failed
    pass is asked again five minutes later and reads back a day before the last good poll, so one
    timeout loses no filing). `failing` shows a stock at its first failure. A warning quotes each URL
    without its query, so the reason (a read timeout, an HTTP status) is on the line.
  - `background_jobs`, `durable_research` and `promotion_status`.
  - `tick_steps` (Sept 24, 2026): where the tick's time went, on the monotonic clock. `last`: the
    last tick's `at`, `total_seconds` (from its start to its health block written) and `steps`, the
    seconds of each: `replay_rules`, `feeds` (scheduling the recorders), `poll:<book>` (fills and
    settlements), `cancel_stale`, `order_path_invariants`, `meter` and `hold_absorb` (with a
    campaign), `due`, `wakes` (the agents' wakes, side by side), `submit:<book>`, `wind_downs`,
    `mark:<book>` and `judge:<book>` (on a mark pass: mark and reconcile; judge, wind-downs and
    sweeps), `allocator`, `floor_invariants`, `research`, `schedule` (the background jobs it starts),
    `jev`, `history_coverage`, `merton`, `hypotheses`, `lab`, `shards`, `payout`, `notices`,
    `horizon`, `tuition`, `population` (culls and births), `save_state`, `publish` and `health` (this
    file's own block). `slowest_hour`: each step's slowest over the ticks of the last hour, the eight
    slowest first, with that tick's `at`; `ticks_in_hour`; and `background`: each lane's
    (`research`, `replay`, `ops`, `audit`, `feeds`, `shards`) last job with its `key`, `state`,
    `seconds` and `at`, which ran beside the tick and are not in its time. `tick_duration_seconds`
    is unchanged: the tick up to its health block. Measured Sept 24, 2026 08:40-08:50Z: ticks of
    51-64 s landing 70-80 s apart, the House at about 74% of the box's one vCPU, and nothing that said
    which step cost what.
  - `deferred` (Sept 23, 2026): work the tick put off because a box was busy or Sail did not
    answer, by kind: `wakes` (an agent's box held by its research; woken on the next tick),
    `births` (the probe box held for more than `probe_wait_seconds`, or a Sail failure during
    births) and `revival` (the replay-rules revival). Each has `count`, `reason`, `at` and
    `first_at`, and drops out an hour after its last deferral. An info alert says so at most every
    fifteen minutes a kind. A count that keeps rising means one job holds a box for long: look in
    `background_jobs` for a `running_seconds` in the hundreds. The tick itself stays short.
  - `shards` (Sept 23, 2026, `league/shards.py`): the Kalshi shard funder's last check, the cash
    per exchange shard (`balances`), the shards the desks are offered or hold positions on
    (`wanted`), series or tickers whose shard no listing has named (`unmapped`), the rolling
    day's `moved_24h_usd` against `day_cap_usd` (a move whose outcome is unknown counts),
    `unattributed_usd` (real stakes whose shard no listing has named: kept on every donor),
    `pending` (shards a blocked pass still owes a refusal; it tries again in five minutes), shards
    backing off after a failed move or a top-up on a refusal's word, and
    `blocked` (why nothing may move: the kill switch, no active grant, a pause, a frozen real
    book). Every move is an `ops.alert` whose payload carries `shard_move` (transfer id, amount,
    source and destination shards, balances before and after); a refusal with
    `insufficient_shard_balance` is a warning alert naming the agent, market and shard, and the
    next pass runs at once. `scripts/kalshi_shard.py balance` reads the same breakdown by hand,
    and `transfer` still moves collateral by hand when the funder is blocked.
  - `repeating_warnings` (L3, Sept 24, 2026): each warning text (numbers and ids folded,
    `house.alert_key`) that came `REPEAT_WARNINGS` (10) times inside 30 minutes, with its last `text`,
    the folded `key`, the `count` of the run, `first_seen`, `last_seen` and `escalated_at`, until it
    has been quiet for 30 minutes. The runs live in `house.json`, so a restart keeps them. Over the
    T0 snapshot this rule escalates three texts: the lab's IndexError (at 23:44:48Z Sept 23),
    "publishing failed (... HTTP 400 Invalid checkpoint)" and "alpaca-paper: could not poll or settle
    (... timed out)".
  - `failures` (L3, Sept 24, 2026): the health failures the in-box watchdog reads, each `{check,
    text, since}`. Today one: `lab_evaluates`, the Alpha Lab evaluated nothing for an hour since the
    later of its last batch and its oldest queued candidate while candidates are queued (the text
    names the queue, the last batch, a refusal and the step's error). At T0 of the close-the-gaps run
    the last batch was 23:37:17Z with 618 queued.
  - `research_economy` (L2, Sept 24, 2026): `sail_cap` (`cap_usd`, `last_hour_usd` settled on Sail
    research in the last hour, `calls`, `inflight_calls` and their `inflight_reserved_usd`, and
    `capped`) and `merton` (the roles of `paused_until_profit`, those `paused` now, and the
    `real_pnl_24h_usd` and `settlements` they wait on).
  - `unit_economics` (Y2, Sept 25, 2026): compute a day against real settled profit a day over the
    last 24 hours, as the hourly yield row last read them (`league/yield_ledger.py` `UnitEconomics`,
    counted as `scripts/gap_scoreboard.py`'s `unit_economics` counts them): `compute_per_day_usd`,
    `profit_per_day_usd`, `compute_over_profit`, `providers_usd` (openai-luna, openai-astra,
    openai-lab, sail, jev, web-search) and `real_closes`. The site's flywheel strip reads the first two
    (the publisher's `site_unit_economics`). Up to an hour old; null until the first yield row after
    the deploy. On the T0 snapshot: $118.88 against $21.35 (5.57x), to the cent the scoreboard's.
  - `seats` (Sept 23, 2026, the seat market): `waiters` by class (`graduates`, `retained`,
    `cards`, `strategies`) and `waiters_by_desk`; `reserved_desks` (desks a waiting graduate,
    retained candidate or card has first claim on); from the hourly watch, `displaceable`
    (residents an evidenced newcomer with no proof and no forward score could take now),
    `never_traded_past_grace` (of those, the ones that never traded: replay-only seats and paper seats
    past their fair chance -- since Sept 24, 2026 a never-traded paper seat is not an evidenced
    newcomer's before its desk's evidence clock, capped at the plain grace and never under an hour,
    has run), `waiting_over_an_hour` and `at`; and `last_refused_birth` a class
    (`count`, `why`, `at`). A warning `ops.alert` says once an hour a class when graduates,
    retained candidates, cards or merged strategies cannot be born and why, and once an hour when
    more than `economy.seat_waiters_warning` (8) newcomers have waited over an hour. A
    `displaceable` of zero with waiters is the market stalled: every seat is real money, a winner,
    a trader short of its record, a proven family's trader, a trader with three fills and no worse
    forward record, or a desk not yet through its first session. Since Sept 24, 2026 (S1-S4, the
    close-the-gaps run) also `seats_holding_none` (`count` and the first 40 `ids`: residents off
    real money with no ranked forward score, no fill since their program's opportunity and no
    grace left -- seats that carry no evidence) and `evidence_clocks` (`at`, and `hours` by desk:
    the median hours from a member's first fill to its third independent settlement over the last
    7 days, the House's closing sales at a death not counted, null where the median was never
    reached and the plain 12-hour grace stands).
    `retained` waiters are the latest replay-passed research candidates of residents that died
    holding them (house.json `retained`; their admission rows say `orphaned`), seated first by the
    admission pass on their author's line (a proven family's first, then the longest wait), dropped
    after 72 hours.
    **R2 and R3 (Sept 24, 2026, the close-the-gaps run): the seat market's capacity.** Measured at
    15:06Z: 82 newcomers waited (41 graduates, the longest 24.5 h since passing; 15 cards, 47.3 h; 11
    retained candidates; 15 merged strategies) in a league of 112 of 112 whose every desk they waited
    for was full; 50 had waited over two hours and the only warning said how many, not where or why.
    - `waiters` has a first class, `proven` (R3): a proven family's program owed births on its desk.
      Every class is what REMAINS once the search has closed a waiter's way: a waiter whose desk the
      search closes (the foundry's closed desks, `Foundry._closed_desks`: game.json
      `hypotheses.closed_desks` until a family there is positive over `closed_reopen_blocks` active
      blocks on that desk; the lab's idle desks, `Lab._idle_desk`) or, for a lab graduate, whose own
      forward window loses (`Lab.forward_score` at or below zero) leaves the queue once, with a
      `route.decision` row `seat-expired:<class>:<id>` (route `expired`, the reason and the rule), a
      house.json `seat_expired` entry kept a week, and one info alert a desk an hour ("N waiters for
      <desk> left the seat queue"). It is not counted while its reason holds: not in `waiters`, the
      refusals, the reserved desks or the scoreboard's metric 5 (which reads house.json `seat_expired`).
      It is asked again each pass, and is a waiter again once the reason is gone -- its desk reopened,
      its window no longer loses (the review of #276: the foundry reopens a desk on one family's record
      there, read through a ten-minute cache). An expired retained candidate is held, never seated,
      until its desk reopens or its 72-hour TTL drops it, an expired merged strategy is not enrolled,
      no card is admitted onto a closed desk, and no seat is made there for a graduate (`_displaceable`
      gives an evidenced newcomer no seat on a desk the search closes, and the House holds that desk's
      cap at its members until it reopens: `_follow_the_search`). A merged corrected child whose defect a living
      resident still runs is not expired: it takes that resident's seat. At 15:06Z 21 would have left
      (the 20 of kalshi-crypto-15m: 3 graduates, 6 cards, 4 retained candidates, 7 corrected children
      of dead parents; and a megacaps graduate whose window lost -0.000142 a block), and Deploy C's
      lab holds 17 nudges itself: 44 remain. kalshi-crypto-strikes was NOT closed: the search had
      reopened it on two lab families positive there (17 and 7 active blocks, one on real money).
    - `expired`: the waiters that left the queue in the last day (`last_day`, `by_rule`, `by_desk`).
    - `over_two_hours` (desk -> `count`, `longest_hours`, `longest`, `rule`) and `longest_wait`
      (`class`, `id`, `desk`, `hours`, `since`, `reason`), the invariant: no newcomer waits over two
      hours, or one warning a desk an hour ("N newcomers have waited over 2 hours for a seat on
      <desk> (the longest ..): <rule>") names the desk, the count, the longest wait and the rule that
      holds them -- a free seat the birth passes have not reached (the lab births at most 6 an hour,
      the refill one a `newcomer_seconds`), or the rules that keep every resident of the desk from
      the best waiter that asks, counted: real money, a winner, inside its grace or its desk's
      evidence clock, a trader short of its record, its day screen pending, a proven family's
      member, a forward record the newcomer does not beat, one displacement a desk a tick, the
      search closes the desk, the desk held for the proven family's births. `longest_wait` is
      recomputed every tick; its `reason` is the hourly watch's.
    - `caps` (desk -> `cap`, `base` (niches.json), `members`, `waiting`) and `population`
      (`max_population` now, `ceiling` (turbo.json), `held_at`, `runway_days`, the `sail` reading and
      the `rule`): the league grows toward turbo.json `max_population` (128) only while Sail's runway
      -- the latest balance less `sail_reserve_usd` over the trailing day's falls, from the Sail
      meter's `ops.budget` "sail" rows -- is over `economy.population_runway_days` (1.5); otherwise,
      or unread (or unreadable), it is held at `economy.max_population_short_runway` (112), killing
      nobody (an info or warning alert when it moves). Once held it grows again only over the floor
      by `POPULATION_RUNWAY_BAND_DAYS` (0.25 d; house.json `population_held`, `grows_over_days`), so a
      runway hovering at the floor does not flip it. At 15:06Z: $162.30 against $34.88 a day, 4.51 days.
    - S3 in `displaceable`: a waiter with a winning forward window takes the seat of a practice
      resident whose desk evidence clock has run (its seat older than the clock -- the plain 12-hour
      grace where none is measured -- and its fair chance; on a desk that keeps hours, a session
      closed since) with no positive record of its own (no winning standing, no positive forward
      window), past the S1 forward rule and the trading and screen protections; never inside its
      clock or fair chance, a real-money seat, a winner, a proven family's member by an unproven
      newcomer, one holding a position while its market is shut, or one holding an event contract
      still to settle (the settlements its clock waits for; `_awaits_settlement`); one a desk a tick. At 15:06Z 29
      practice seats were stale by this test (10 index ETFs, 5 options, 4 crypto-15m, 3 megacaps, 2
      crypto majors, 2 sports, 2 sports props, 1 attention); one waiter had a winning window
      (a megacaps graduate, +0.000102 a block over 3 active blocks).
    - R3: a proven family's program (its anchor: the living member on the highest rung with fills of
      its own that runs the markets and style of the family's founding program, `_family_program`;
      its program is the anchor's code beyond PARAMS, `lab.mechanism_digest`) is born first
      on its desk, a House mutation of the anchor's PARAMS inside their bounds at the newcomer cadence
      (`House._proven_births`, route `proven_family`), until `economy.proven_family_members` (4)
      living members run it; while it is owed, no newcomer of another family may displace a resident of
      its desk, and the desk is reserved from cards (and, in a full league, from merged strategies); a
      free seat there is not held: the lab's graduates, retained candidates and merged strategies take one
      without asking. Not at the family's measured capacity (E3), not for a losing family, and not for an
      hour after its program had no distinct valid PARAMS mutation left (then nothing is owed and its desk
      is not held). A member that inherited the family's name with other code is not its program
      (meriwether-h2d625d-2). Since the same day a research fork or a retained candidate whose NEEDS name
      other markets or another style than its parent's program is born into its own family
      (`<desk>-<style>-<6 hex>`; its birth row's reason says so, and names its parent as before); a fix of
      the same program keeps the family -- a proven family's name only when that program is the family's
      founding one (its first member's NEEDS at birth, `_family_program`), so a member carrying the name
      with another program cannot pass the proof to its forks, and never anchors R3 (the review of #276).
      Agents born before keep their family on the ledger.
- **`/workspace/state/allocator-board.json`** (Sept 23, 2026), rewritten every mark pass: each
  agent's band, stake and evidence, the last 50 moves, bands per venue (count and capital), the
  throttle and the envelope per venue (`capital_usd`, `committed_usd`). The allocator's own state
  (throttle, fee cursor) is in `allocator.json`, and an `alloc.board` ledger row is written at
  most every five minutes. Since Deploy B (Sept 24, 2026) each row also has `family_state`
  ("unproven", "proven" or "swing"), `capacity` (`usd_per_day` at its family's stake, `binds`) and
  `stake_limit` (for a swinging family's member: `ramp`, `capacity`, `kelly`, `venue_share` or
  `bunt`), and the board has a `families` block: per venue, per family followed that pass, its
  `state` and `since`, the pooled record (`n`, `bound`, `loss_gate`, `proven`, `edge_per_dollar`),
  the REAL record (`real.n`, `real.bound`, `real.honest_bound`), maker and taker, active blocks,
  members (`members_living`, `members_real`), the stake a member on real money is lent, the
  capacity estimate (markets bid a day, the fill rate at the stake's position, real settlements a
  day, dollars a day) and, swinging, the ramp (`swing`: `level`, `positive_since_entry`,
  `next_doubling_in`, `kelly_usd`, `venue_share_usd`, `entered_seq`). The same row is written to the
  ledger as `family.record` (private) at most every five minutes when it changed, the capacity
  estimate's clock-driven rates aside (`families.change_view`): the durable record of every state
  change. The family states and the swing's audits live in `allocator.json`
  (`families`, `family_audits`). Since R3 and R5 of the close-the-gaps run (Sept 24, 2026), for the watch
  and the owner and never the site (the publisher copies the site's fields by name):
  - every row has `family_forward` (`blocks`, `growth`: the family's pooled forward record, the House's
    `family_forward`, every member ever born), and a practice or rung-2 row `probe_gate`: null, `"losing"`
    (no probe is seated from the family; a probe seated on it goes back to practice), `"held since
    <time>"` (the earliest probe demotion of the family whose record since has not turned positive over
    6 active blocks), or `"unreadable"` (the gate could not be read this pass: no probe is seated);
  - a real row has `equity_usd` beside `stake_usd`. `stake_usd` is the NET LOAN (what was lent, less the
    profit swept back), not what the account is worth: at the resume the notes read meriwether-h2d625d's
    $20.06 stake as short of its $37.50 target while its equity was $41.67;
  - each family has `swing_clock`: `real_n`, `real_since` (its first real dollar), `real_days`,
    `real_per_day` (independent real settlements a day over its real life, once that life is an hour
    long), `needs` (`real_settlements` to the next entry look, `look_at`, the look's `confidence`, whether
    the pooled `proof` is still missing, the `audit` that follows a passing look, and `grant`: the live
    grant does not yet release stakes above the bunt) and `days_to_swing` at its own rate (null with no
    rate, with no member on real money, or with only the pooled proof left). It moves with
    the clock alone, so it is never on a `family.record` row. sports-central-run-under at 15:06Z Sept 24:
    real n 5 since 04:52Z Sept 23, 3.5 a day, 10 to the look at 15, about 2.9 days;
  - `allocator.json` `probe_holds`: the ledger position the probe demotions were folded to (`cursor`),
    each family's probe demotions still in force (`families`: a list of `seq`, `at`, `agent`, `why`; a
    demotion whose family record since has turned is dropped for good) and the mechanism ledger's state per
    family as its `family.record` rows said it (`states`). A House that lost the file folds the ledger again
    to the same holds.
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
  - Under the allocator (Sept 23, 2026) only the allocator writes these for moves up: `promoted`
    ("the allocator seated it as a probe" or "as a bunt", or moved it to the swing band), `auditing` (a known
    defect before the bunt, or the first swing), `envelope` (the venue's envelope cannot seat
    another probe or bunt and no weaker flat agent can be displaced -- a probe displaces only a probe;
    with `capital_usd` and `headroom_usd`),
    `venue_cash` (the account's free cash cannot take the stake now), `campaign` (the grant has not
    released the swing band) and `accounting_integrity`.
  - The probe gate (R5, Sept 24, 2026; `allocator.family_probe`), before any audit or displacement:
    `family_losing` ("its family X's pooled forward record is -0.0600 over 6 active blocks: no probe is
    seated from a family at or below zero after 6") and `family_held` ("Y, a probe of its family X, went
    back to practice at <time>: no probe is seated from the family until its pooled forward record since
    then is positive over 6 active blocks (it is +0.0500 over 5)"), each with `family_forward` and, held,
    `held_since`. A new row is written only when a block closes and the numbers move. A probe on a losing
    family goes back to practice with a `demote` row carrying `rule: "allocator.family_probe"` and
    `family_forward`; on Alpaca its working bids are cancelled first (the demotion path's own first step),
    and while it still holds a position the demotion would sell, or a buy is still in question at the venue,
    it keeps its seat (its own exits go on, nothing is sold for it, it is lent nothing more), the pass summary
    lists it in `probes_waiting_flat`, and one info alert says why ("now: holding", "reserved"). While it
    waits, the House holds its entries the way an agent holds its own (`House._hold_draining_probes`: an
    `agent.strategy` `pause_entries` row under session `house:drain`, its resting buys cancelled, every sell
    goes on; house.json `drain_holds`), and releases the hold with a `resume_entries` row once a pass has
    ended the drain: the probe is back in practice (or dead, with no row), or its family's gate reads neither
    losing nor unreadable. A pass that cannot read the gate, the family's record or the probe's own evidence
    ends nothing, and while the allocator is off every hold is released. The row's session, not house.json,
    says which pauses are the House's. A research request to resume is refused while the hold stands, and
    while a probe that paused itself waits; one that paused itself is left as it is, and a pause research
    asks for during the House's hold is its own (it outlasts the drain). The House's hold is not a pause of
    its own to the seat market (`_paused_past`). Sept 24, 2026: krasker-14, an $80 options probe on
    options-pullback (19 blocks, -0.383), bought a second real contract at 18:52:30Z while it waited, before
    the hold existed. A gate that cannot be read this pass (a failed fold or forward read) holds every probe
    promotion at `family_unreadable` and demotes nobody.
- **Ledger rows from the Sept 23 revision:**
  - an `eval.verdict` progress row on rung 0 with `stage: "holdout"`: a development replay passed
    and the sealed holdout refused or failed it, with the reason and the holdout's coarse numbers;
  - a promotion to the micro rung under audit after promotion carries `audit_timing: "after"`;
  - `audit.verdict` carries `paid_by` (`house` or `agent`);
  - `agent.died` has two new causes, `superseded` (a born corrected child replaces its code) and
    `redundant` (the holdout would not evaluate its passing replay, and the same program already
    holds a paper seat);
  - `ops.budget` with `what: "holds absorbed"`: holds released into their provider's meter, with
    `kind` (`sail`, or `openai` since Sept 24, 2026), `absorbed`, `usd`, `measured_usd` and
    `settled_usd`; an OpenAI row also has `check` (`since_anchor_usd`, `gateway_growth_usd`,
    `anchor_at`). Each hold's evidence is in `campaigns.sqlite` `cost_reconciliations`, under
    `absorbed:<commitment>`.
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
    savings, sampled miss rate and, since Sept 23, 2026, the runs, candidates and dollars per
    candidate of each trigger (`by_trigger`: which kind of evidence buys research that produces);
    since Sept 25, 2026 the runs by the money their agent was on and reason (`by_money`: under F2 a
    `clock` or 24-hour `heartbeat` run is `real`) and `refusals_deduped`.
  - `python3 scripts/gate_replay.py LEDGER [--hours 24] [--idle barren|off|clock] [--no-parity]`
    (Sept 25, 2026): which of the sessions a ledger actually ran the F2/X2 rules would have run, by
    the reason each ran, with candidates, adoptions or forks and dollars; its docstring lists where it
    approximates. Read-only; it runs on a snapshot or on the box.
  - `python -m league.history coverage --root /workspace/state`: what history is stored, what is
    unavailable, and what has not been fetched.
  - `scripts/repair_drill.py --inspect`: the repair drill's states.
- **The Alpha Lab** (Sept 23, 2026, `league/lab.py`). It runs only where `config.json` `lab` names a
  box (`box_id`) and `game.json` `lab.enabled` is on; a canary House never runs it.
  - **`/workspace/state/lab.sqlite`**, opened `mode=ro`:
    - `candidates`: every program the lab has seen, with its `origin` (`seed`, `param`, `luna`,
      `sol`, `agent`), `author`, `lineage`, `status` (`queued`, `evaluated`, `failed`, `invalid`,
      `blocked`), `fitness`, `trades`, `trades_per_day`, `corr` and `cell`;
    - `archive`: one row per cell, the elite and its fitness;
    - `batches`: each batch's tape, candidates, how many ran, were eligible, cleared the gate and
      were archived, its seconds and its estimated Sail cost;
    - `calls`: each Luna and Sol call's cost, programs written and programs refused;
    - `graduations`: each graduate's latest state (`refused`, `holdout_rationed`, `replay_failed`,
      `replay_unavailable`, `holdout_failed`, `passed`, `waiting_probe`, `waiting_seat`,
      `refused_at_birth`, `born`), its line, family and agent. Since Sept 24, 2026 (E1) also `held`:
      a passer held before its birth, its `detail` starting `held:` with the reason; it is asked
      again every ten minutes, scored in the forward windows as a waiting graduate is, and, not
      being `passed`, reserves no seat in the House's seat market nor counts as a waiter on the
      scoreboard. A program held before the House's replay has no row at all (it was not tried);
    - `forward` (S2, Sept 23, 2026): one row per candidate and forward-window run: `window_start`
      and `window_end` (epochs; the window starts at the hour after the program's code was frozen,
      so no search, replay or holdout saw a step of it), `blocks`, `active_blocks`, `log_growth`,
      `mean_log_growth`, `trades`, `tape_id`, `ok`, `error`. The latest row per candidate is its
      forward record; the archive's `fitness` is never rewritten by it. `SELECT candidate,
      active_blocks, mean_log_growth FROM forward f WHERE at = (SELECT MAX(at) FROM forward WHERE
      candidate = f.candidate) ORDER BY mean_log_growth DESC` is the forward leaderboard;
    - `meta`: cursors and stamps (`forward_at`: the last completed forward run). Since D1 (Sept 24,
      2026) also the step's failure record (`failures_in_a_row`, `failures_first_at`,
      `last_failure` with its phase and error, `failing_since` once escalated) and `tape_index`:
      a JSON object, tape key -> `at` (built), `ident` (the lab's tape id, as `batches.tape_id`
      names it), `house` (the House's tape id) and `source` (`history-dev`, rebuilt from the
      history store on the House's disk; `live`, fetched), for the tapes of the last six hours.
      A `blocked` candidate's `error` says why: unsupported input (a sealed tape, missing
      observed bars, a tape with no steps: nothing was recorded in its window; since Sept 24, 2026
      also NEEDS the House's tape reader refuses for their size, "ask for a shorter window", and a
      tape that failed "the same way N times in a row"), or "the lab could not read its NEEDS or its
      tape" / "the lab could not score its result" with the exception. `meta` `tape_failures`
      (Sept 24, 2026): tape key -> the folded error of its failed builds in a row, `tries` and
      `since`; at `tape_failures_before_block` (12) hourly tries the rows are blocked with one warning.
  - **`lab.stats` ledger rows**, at most every ten minutes (`stats_every_minutes`), over the last
    hour: `batches`, `evaluated`, `per_hour`, `candidates_per_box_second`, `stages` (programs written
    by origin, ran, eligible, gate, archived, graduations by state), `pass_rates`, `calls`,
    `coverage` (cells by desk), `queued`, `spend` (OpenAI, the Sail estimate, the royalty balance),
    `born_total`, `refusal`, `llm` (`paused`: why Luna and Sol are being skipped, or null;
    `skipped`: the Luna and Sol phases skipped since the process started), `closed_since`,
    `failing_since`, `failures_in_a_row` and `error` (D1, Sept 24, 2026: as in `health.json`),
    `waiting_seat` (`count`, `longest_hours`) and, since S2 (Sept 23, 2026), `forward`
    (`last_run_at`; `last_run` with `candidates`, `scored`, `batches`, `seconds` and `skipped` by
    reason, for example `no forward data yet` or `the run's box seconds are spent`; `records`, the
    candidates with a forward row; `ranked`, those with `forward_min_active_blocks` active blocks;
    `positive`, those whose window wins; `priors`: the lessons whose ```lab-prior``` blocks are in
    force and how many parameter forks each has paused since the process started). Forward windows
    rank seats, cells and breeding and are never practice evidence: no `eval.*`, `holdout.*` or
    `agent.born` row ever comes from them. A row is written only at the end of a lab step, and
    a step runs only while the lab is open, so `refusal` is the last reason a Luna or Sol call was
    refused or skipped inside a step (no model client, an OpenAI tier below `all`, the House's
    OpenAI allowance closed, or the lab's hourly line too small for the call's hold), or null.
    Below the `all` tier the lab keeps seeding, breeding parameter children, evaluating on its box
    and graduating (C2, Sept 23, 2026); only the paid phases stop, and `llm.paused` says so. When
    the lab is stopped (disabled, the House closing, stopped or paused, a release being staged,
    the Sail allowance closed or the Sail meter stopped, or a lab box that failed a batch in the
    last five minutes), no step runs and no `lab.stats` row is written: the rows stop, and
    `health.json` `lab` (`refusal`, `closed_since`, `closed_minutes`, `llm`, `waiting_seat` with
    up to eight graduates, each with its `forward` score for the seat market, `queued`,
    `born_total`, `forward`) says why. Since E1 (Sept 24, 2026) the rows also carry `reserved`
    (`share`: the share of each batch and of the tape builds kept for the programs someone wrote,
    `game.json` `lab.reserved_share` held to `lab_bounds`; `evaluated`: how many of theirs the hour
    evaluated) and `held` (as in `health.json`). The batch turns (`batch_turn`): with the half,
    queue order, written programs, largest group, written programs, and again; a step builds at
    most `max_tapes_per_step` (4) tapes, one a turn. What the lab is searching for, and why it
    graduates less than before, is in `held`: a desk with no ranked resident needs a graduate's own
    winning forward window for a parameter nudge, and nudges wait for one.
  - **The foundry's brief** (`foundry-2026-09-24.1`, E2): cards name the recorded feeds of their desk
    and state their `fee` and `edge_needed` (a card without them is refused before its replay, and
    says so in the call's `merton.pass` `refused`); `game.json` `hypotheses.fast_desks` is the
    deep-market desks; `closed_desks` (kalshi-crypto-strikes, kalshi-crypto-15m) get no card until a
    family there is positive over three active forward blocks on that desk (one block a block key,
    however many of its members were active in it); the first transfer (`first_transfer`)
    scales the weather favourites on the ensemble's fair value, once: its call's `merton.pass`
    `allocation.transfer` carries `scale: true`. A family at its measured capacity gets no
    evidence-driven House mutation (E3).
  - **`lab.graduate` rows**, one per candidate and outcome, carry the program's lineage, origin,
    author, parents, idea, fitness and cell. **`lab.royalty` rows** record each royalty charged to
    a graduate that earned a performance fee.
  - **The box**, from the owner's machine: `python3 scripts/lab_box.py status` (the box, its seal
    read back from the API, python, the tapes it holds) and `python3 scripts/lab_box.py sleep`.
    `create [--size l]` makes, provisions, seals and records a new box in `config.json`; `bench`
    measures candidates a second through the House's own `LabBox`. The box sleeps by itself after
    ten idle minutes.
- **New ledger kinds**, all private:
  - `hypothesis.card`, `hypothesis.link` and `hypothesis.retired`;
  - `repair.reported` and `repair.status`;
  - `research.gate` and `agent.inactive`;
  - `route.decision` and `trace.record`;
  - `data.coverage` and `holdout.access`;
  - `triage.item`;
  - since Sept 23, 2026: `alloc.board`, `book.exit_plan` (a sell over the order cap, sent in
    slices: the plan, then its close), `lab.stats`, `lab.graduate` and `lab.royalty`.
- **Allocator rows** (Sept 23, 2026):
  - a band move is an `eval.verdict` promote or demote row with `via: "allocator"`, `band_from`,
    `band_to`, `stake_usd` and the evidence;
  - a stake change alone is an `eval.verdict` row with `decision: "size"`;
  - the performance fee is a `credit.grant` with id `perf:<ledger id>`;
  - the throttle turning on or off is an `ops.budget` row with `what: "allocator throttle"`.

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
    (HTTP 4xx) at $0. Before Sept 23, every call was booked at the long-context ceiling when that
    was higher, and the House's line closed at about half the owner's real spend. A call with no
    answer (a 5xx, a timeout, the House's own restart) keeps its hold, and since Sept 24, 2026
    that hold is absorbed into OpenAI's meter, the gateway's frontier month (**The OpenAI meter**,
    below), once it is six hours old. Measured before the fix (Sept 24, 01:34Z): 49 such holds
    ($98.36, 28 of them over a day old) made the House's line read $7.94 while the gateway's month
    had $13.54 left, and the frontier tier fell to "audits".
  - **What stays held.** Jev's backing (`external-pilot:typesafe:*`, $20) stays until that route
    is closed and billed: the gateway's frontier month never sees it, so releasing it would drop
    Jev's spend. An OpenAI hold younger than six hours, or made before the meter's `covers_from`,
    stays too.
- **The OpenAI meter** (Sept 24, 2026). OpenAI is metered like Sail (`campaigns.json`
  `meter_required`), and its meter is the gateway's frontier month, read on every tick
  (`league/frontier.py` `FrontierMonth` into `CampaignBudget.observe_month`).
  - **It never runs backwards.** The month falls whenever a call settles below its worst case and
    starts at zero on the 1st, so the meter keeps the month's highest reading plus the finals of
    earlier months (the gateway's `previous`). It counts from the start of the first month it read
    (`covers_from`); a month the gateway could not close moves `covers_from` forward, and what the
    meter carried until then leaves its measure (`base_usd`), because the House's own settled costs
    of those calls are counted apart (`before_meter_usd`).
  - **What is released.** Every ten minutes, a `frontier:` hold with no answer, older than six
    hours and made since `covers_from`, is absorbed: the gateway reserved that call's worst case
    on its month before it called OpenAI, and settled it at the metered cost or kept the worst
    case, so the month already counts it once.
  - **The check.** Nothing is released until a call has settled since the meter's anchor (its first
    reading with `settled_usd`, taken again each month), and nothing while the gateway's settled
    figure has grown less than what the House settled since then. The anchor is not the burst's
    start because the House booked calls at its ceiling prices until Sept 23: its settled sum
    since the burst ($495.35) was above the gateway's whole September ($402.96).
  - **What the owner reads.** `health.json` `campaign.meters.openai` (the line's arithmetic and
    the month), the `ops.budget` "holds absorbed" rows with `kind: "openai"`, and
    `meter_reconciliations` in `campaigns.sqlite` (the meter's start, its anchors and every month
    it closed). The tier still reads the nearer of the House line and the gateway's month.
  - **Never above the month.** While a reading is fresh, the House's OpenAI line reads at most the
    gateway month's `cap_usd` less its `spent_usd`, less what the House has committed since that
    reading: reservations, the pacer, the agents' credit pool, the tier and `health.json` all see
    the smaller line. The gateway's month is the one aligned to the owner's funded balance; the
    House's own line is raised by top-ups and settles at the House's prices, and on the T0 snapshot
    it read $273.85 after the release against the month's $203.74. Nothing is rewritten: no top-up
    is lowered and no settled row changes (`house_line_usd` keeps the House's own arithmetic).
  - **An unread gateway.** Three minutes without a reading and OpenAI reservations are refused:
    Merton, audits and the lab's Luna and Sol calls wait. Sail work, trading and exits go on. A
    reservation that finds the reading a minute old reads the gateway again first. While it lasts
    the tier reads "audits", so no role is scheduled into a refusal and new research runs on
    Sail, and one `ops.alert` warning ("OpenAI's meter is not ready ...") says so; another says
    when the meter is read again. The House's line then stands alone (`provider_left_usd` null).
  - **The first deploy** records the policy change in `phase_amendments` beside the phase's pinned
    policy, which is never rewritten, so a rollback to the release before still opens the phase.
    Only a new meter may be added this way; any other change to `campaigns.json` still refuses to
    open the phase.
- **Wakes or births keep being deferred.** Since Sept 23, 2026 the tick never waits on a box that
  background work holds, so a hung Sail call shows up as `deferred` in `health.json` (above), not as
  a stale health file. Background Sail calls give up on their own: a resume, a checkpoint or a
  batch's result after 120 s, a new box after 180 s, an upload after 60 s plus 4 s a megabyte.
  Deferred work is retried on every tick, and nothing needs restarting. Before E3, a hung first tick
  cleared only when the Sail call returned (05:07Z Sept 23: about twelve minutes).
- **"the Alpha Lab is stopped: its box is gone"** (an error alert). Sail reports the lab box
  terminated or failed. It is never replaced from the agents' image; the lab asks again every hour.
  Make a new box with `python3 scripts/lab_box.py create`, which writes the new `box_id` into
  `league/config.json`, and deploy it. A batch that fails for any other reason is a warning: its
  candidates stay queued, and the lab leaves the box alone for five minutes.
- **"the Alpha Lab has been closed for N minutes (since ...): <why>"** (a warning, once per
  closing, after `closed_alert_minutes`, 30; Sept 23, 2026). The refusal is the one `Lab.open`
  gives now (the House paused, stopped or staging a release, the Sail allowance or meter, the box
  after a failed batch, the lab disabled, the House not open for business). The since-when is kept
  in `lab.sqlite` `meta`, so a restart does not reset it. "the Alpha Lab is open again after N
  minutes closed" (an info) follows when it works again.
- **"the Alpha Lab graduate <line> (<candidate>, <desk>) has waited N hours for a seat"** (a
  warning, once per graduate, after `seat_wait_alert_hours`, 6). Its desk or the league is full of
  agents that have earned their seats (`league/niches.json` seats, `league/turbo.json`
  `max_population`); the lab asks again every ten minutes. `health.json` `lab.waiting_seat` lists
  them, longest wait first.
- **"the lab's step failed (<error>)"** (a warning, each failed phase of a step; D1, Sept 24,
  2026). The payload names the `phase` (`royalties`, `seed`, `breed`, `batches`, `graduate`,
  `forward`) and carries the last 2,000 characters of the traceback as `_traceback` (private:
  never published). Read it with `SELECT payload FROM ledger WHERE kind='ops.alert' AND payload
  LIKE '%step failed%' ORDER BY seq DESC LIMIT 1`. The other phases of the step still ran. From
  23:21:59Z Sept 23 this warning came every one to three minutes for over two hours with no
  traceback: one queued candidate whose tape had no steps failed every step.
- **"the Alpha Lab's step has failed N times in a row since <time> (<error>)"** (an error, once
  per run of failures, after `failures_alert_after`, 5). It carries the traceback like the
  warnings, and `health.json` `lab.failing_since` is set until a step works again, when "the
  Alpha Lab's step works again after N failures in a row since <time>" (an info) clears it. The
  count is in `lab.sqlite` `meta`, so a restart does not reset it. Like every error alert, the
  watchdog reads it: inside a release's ten-minute watch after promotion it rolls the release back.
- **"a warning repeated N times in 30 minutes: <text>"** (an error, once per run of repeats; L3,
  Sept 24, 2026). The same warning text, numbers and ids folded, came `REPEAT_WARNINGS` (10) times
  inside 30 minutes. It carries the last warning's payload, its `_traceback` when the caller sent
  one, `repeated` (the folded text, the count, first and last seen) and `began_at`; `health.json`
  `repeating_warnings` lists it until it stops for 30 minutes, and a new run after that escalates
  again. The watchdog counts it like any error, unless it began before a promotion it is watching.
- **"health failure: the lab evaluated nothing in the last hour while N candidates are queued
  (...)"** (an error, once when it begins, with `failure: lab_evaluates` and `began_at`; L3), and
  **"the lab evaluates again"** (an info) when a batch runs. Read the lab's `refusal`,
  `failing_since` and `error` in `health.json` `lab` for why.
- **"the lab could not evaluate N queued candidate(s) and blocked them (<error>)"** (a warning,
  at most one a step; D1). A row's NEEDS, tape or result raised something the lab has no refusal
  for; `candidates` names the rows, each now `blocked` with its error, and `_traceback` is the
  first one's. More than `row_errors_per_step` (8) in one step is the lab's own defect, not the
  rows': the step fails (the warning above) and the rest of the queue is left as it was.
- **Research ends with `provider: campaign_post_unconfirmed`.** A Sail request was in flight when
  the House restarted. The House cannot prove whether the vendor accepted it, so it will not buy it
  again inside the idempotency window, and the agent researches on its next due session. Many at
  once means many restarts.
- **Research ends with `provider: provider_http_502` (or 500, 503, 504, 529).** The vendor failed
  the session (L2, Sept 24, 2026: 13 sessions ended in a 502 and 13 in a 504 in the day before T0).
  What its model turns were charged comes back in one `credit.grant` (id
  `research-refund:<session>`; the summary row says `refunded_usd`), the session is no completed
  pass (`research_gate.completed_pass`: no streak moves, displacement does not count it), its job is
  closed as cancelled so the research clock does not restart, and the agent may research again in
  15 minutes. A session its own model ended (`provider: max_output_tokens`) or a cap stopped is not
  refunded.
- **A replay or a lab row says "unsupported input: the history store holds no <symbol> <timeframe>
  bars in <window> (its first is <day>)".** The history store fetched that window and the venue had
  nothing: the symbol did not trade yet (ADA/USD trades on Alpaca from 2026-02-01, so an hourly
  development window of 2025 holds none). Since Sept 24, 2026 the House refuses such a development
  tape where it builds it (`House._deep_tape`, `history.series_without_bars`), so it is not a trial,
  the lab blocks the row, and the sealed holdout is refused before its seal is opened, spending no
  evaluation of the lineage's ration. A window never fetched still falls back to the live tape.
- **Durable research older than six hours expires** after a long pause
  ("session expired after six hours").
- **A dead agent's exits are refused as "has no seat on the book."** This is fixed by #106:
  wind-downs are seated first. A death during a venue outage is recorded, and its exits are retried
  by the mark pass (#107).
- **A dead stock or options agent still holds its position overnight.** That is by design since
  Sept 23, 2026: a wind-down's sale of a stock or an option is held for the regular session (before,
  the book refused the market sell as "market orders outside regular hours" on every mark pass, 576
  times in a day). One info alert names what is held (`wind_down_held` in `house.json`), and the
  House sells it in the first tick after the bell, an option at the bid. Coins and Kalshi positions
  wind down at once.
- **A living stock or options agent is not woken at night** (Sept 24, 2026, the wake skip): no
  `agent.woke` row, no box run, no order between the close and the open, counted in `health.json`
  `wakes_skipped`. It is woken a few seconds after the bell, and its own exit of a position held
  overnight goes then, if its strategy sends one: the skip itself sells nothing (a dead agent's
  held wind-down still sells at the bell). "market orders outside regular hours are not permitted"
  from a living agent now means an open-desk agent that names a coin (still woken all night) sent a
  stock or option SELL at night; its stock or option buys are refused by the House first ("outside
  the regular session no stock or option entry is sent").
- **An agent paused its own entries, or edited its parameters in place** (X1, Sept 24, 2026). Its
  `agent.strategy` rows carry `control` (`pause_entries`, `resume_entries`, `edit_params`), `was`
  and its `note`; `agent.research` rows with tool `control` are its requests (status `requested`)
  and any the House did not make (status `not_applied`, with the reason: for an edit, an audit
  running or owed, a standing veto, an approval standing on real money or a strategy changed after
  its replay; already paused). A paused agent's wakes show `held` (buys the House held, never a
  refusal) and its resting buys are cancelled. Held buys are not activity: its wakes count barren,
  the stuck rule applies, and a practice resident paused past the grace is displaceable like an idle
  one, and the seat report (`seats_holding_none`, the watch's seat line) counts it as holding none.
  The allocator promotes no paused agent (a `progress` status with stage `paused`), and after
  24 hours paused holds a real agent's stake to its probe by free cash only (a `size` verdict whose
  reason says "held to the probe"; the board row's `entries_paused_since`).
  `Registry.entries_paused` is the live state; the ledger is the record. Its edit replays are
  `agent.research` rows with tool `edit_replay` (at half the practice stake and caps, no
  `eval.trial`, never the holdout, one an agent a day). Nothing here moves a limit, a stake or a
  band. A pause or resume row adopts nothing (`allocator.adopted_strategy`): it moves no generation
  and sets no audit verdict aside. An edit is a new strategy to `allocator.audit_standing`, so an
  agent whose code was approved is audited again before a first swing.
- **The horizon rule's refusals name what they judged by** (X2, Sept 24, 2026): "this market is
  expected to resolve in N hours, by its scheduled expiration (...)", "..., by its close plus its
  series' measured settle lag (...)", "..., by its expected expiration (...), a deadline days
  after its close: its series has fewer than 20 settled markets on record ..." or "..., by its
  close (...): the venue lists no scheduled expiration for it". An expected expiration two days
  or more after the close is a deadline (the diesel prints, the AI-share weeklies); such a market
  is judged by its close plus the p95 settle lag of its series' last 40 settled markets on record
  (at least 20), which `settle_lags.json` beside the House's state keeps (fed by every Kalshi
  tape's settled markets; recomputed once a day; delete it to measure afresh). The answer is
  `league/resolution.py`, a money judge in `ci.FORBIDDEN` (an owner deploy changes it, never the
  updater), and it reads that file as untrusted data: an entry that settled before its close, or is
  not three finite times with a real deadline, is ignored; each lag is clamped to [0, its
  deadline]; a series needs 20 good settlements. A series stuck on "fewer than 20 settled markets"
  is one no tape has replayed enough of yet. The House asks before
  the book; the book still judges every entry after it, from the same answer. The book's own shorter
  text ("expected to resolve in N hours; entries must resolve within 48", no basis) would now mean
  the two looks disagreed, at the boundary a moment apart.
- **"booked ... as dust instead of selling it"** (info, Sept 24, 2026): a wind-down found a holding
  the venue will not trade -- worth under a cent even at the ask (a holding under a cent at its mark,
  the last bid, is quoted again: a stub bid on a thin book is not a price), or under the venue's
  minimal order quantity where the asset record states one -- and moved it off the account onto the House row, as
  the reconciliation books position dust (two `book.fill` rows with `source: dust`, written as one
  ledger group: a crash between them cannot leave the book short of the venue); the account then
  closes. Before, haghani-h426990's 0.000000001 LINK/USD was sent every five minutes and refused 107
  times ("order qty must be >= minimal qty of order 0.000000002").
- **"the House's sale of ... was refused 3 times in a row"** (warning): the same refusal of a
  House-sent sale, by the venue or the book, three times in a row; the sale is not sent again until
  the holding changes, or a day after the last refusal (a refusal then stops it for another day, with
  no second warning: an outage is not left to strand a holding for good). `wind_down_refusals` in
  `house.json` keeps the count and the order id. Read the refusal it names.
- **"... was superseded by its research child ..."** (info): L1, when the constitution's
  `allocator.corrected_child_supersedes` is on. The parent's research child passed replay and its
  own account names the parent's entry as the defect (taker liquidity, the fee, the side) -- an
  account of the program the parent runs NOW (the child's rewrite of a copy of it, or the parent's
  own research candidate made while it ran it; never the child's fix of its own earlier file) --
  and the programs bear it out (the parent's entry fills were takers and the child's file rests its
  entries post-only, for a liquidity or fee defect); the parent was demoted from real money (a `demote` verdict,
  `band_to: paper`, `superseded_by`) and retired `superseded`. The child enters real money when the
  allocator's rules seat it on its own evidence.
- **"... is not superseded by its research child ..."** (info, once a parent and child pair; house.json
  `supersede_skipped`): L1 found a maker fix of the parent's taker entry, but the family's pooled TAKER
  record is proven positive (`Allocator.family_taker`, the record the real book's X0 rule reads to let
  the family take): a maker fix of a proven taker mechanism is not a defect fix. The alert carries the
  record (`taker`); the pair is judged again hourly, and supersedes once the record is no longer proven.
- **"the desks' evidence clocks ..."** (info, at most daily): the House measured each desk's
  evidence clock and the seat grace follows it (`house.json` `evidence_clocks`); a measurement that
  fails is a warning and the last reading stands.
- **"N waiters for <desk> left the seat queue (...): its desk <desk> is closed by the search: ..."**
  (info, at most once an hour a desk; R2, Sept 24, 2026): waiters whose desk the search closes (the
  foundry's closed desk, or the lab's idle desk) or, a graduate, whose own forward window loses, left
  the queue with their reason (`route.decision` `seat-expired:<class>:<id>`). Nothing to do: they are
  not seated and not counted. A desk that should be open again reopens when a family there is
  positive over `hypotheses.closed_reopen_blocks` active blocks on it, and its waiters are waiters again.
- **"N newcomers have waited over 2 hours for a seat on <desk> (the longest ..): <rule>"** (warning,
  once an hour a desk; R2, Sept 24, 2026): the two-hour invariant. The rule says what holds them: a
  free seat the birth passes have not reached yet (the lab's six births an hour, the refill's one a
  `newcomer_seconds`), or the residents' protections, counted (real money, winners, inside the grace
  or the desk's evidence clock, traders short of their record, a proven family's members ...). Read it
  with `health.json` `seats.over_two_hours`: a desk whose seats are all real money or winners needs a
  cap (`league/niches.json`), a forward-scored waiter (S3) or patience, not a rule change.
- **"the league's population is now N (was M): ..."** (info when it grows, warning when it is held;
  R2, Sept 24, 2026): Sail's runway crossed `economy.population_runway_days` (1.5 days) or its meter
  went unread; the league grows toward turbo.json `max_population` only while the runway holds, and is
  held at `economy.max_population_short_runway` (112) otherwise; once held, it grows again only over
  1.75 days (the quarter-day band), and a restart that finds it held says so once. Nobody is killed: a
  held league stops growing.
- **"K proven family's births wait for a seat: <family> on <desk>: ..."** (warning, once an hour; R3):
  the proven family's program is owed births and its desk (or the full league) has no resident a
  proven family's newcomer may displace.
- **`ops.alert` warnings from the floor's invariants** (Sept 23, 2026; `House._floor_invariants`,
  every five minutes over the ledger rows since its saved cursor, `invariants` in `house.json`):
  `<desk>: offered markets on N wakes in the last hour ... and no agent of the desk wrote an intent`
  (once a desk an hour: its rules are not firing on what it is shown, a research pass is the answer).
  Since Sept 24, 2026 an offer is a market of a series the program's NEEDS names that resolves inside
  its horizon (`House._offered`): the busiest live series a desk shows a program whose own series
  have nothing in its window (`ctx["note"]`) is not one, and such a wake is `shut` (nothing in its
  window), not `barren` -- greenwich-h4cb387, NFL props within six hours ten hours before the game,
  was shown UEFA and DJI markets and called quiet at 14:58Z. A desk whose offered agents are all day
  programs is told only after a day without an intent (`QUIET_DESK_DAY_SECONDS`, counted from its first
  unanswered offer since its last intent, once a day), and the warning says for how many hours:
  kalshi-sports, whose favourites programs trade around game time, was told six times on Sept 24
  while two of its agents made the floor's profit
  and `<agent>: a real-money bunt on <book> was frozen by a daily-loss rule` (once an agent a day:
  the book's daily rule is meant not to apply to a rung-2 bunt; if this fires, it is applying).
- **An exit that met the House's own resting order** (D3, Sept 24, 2026). It is no longer refused
  ("a market order here could trade against the House's own resting order" now refuses entries
  only; 74 sells were refused so in the 48 hours to 01:42Z Sept 24, and time-stopped crypto
  positions sat 9 h past their stops). What the ledger shows instead: the seller's own crossing
  bid cancelled (its `book.order` `cancelled` row's `reason` says why); a peer's bid at or above the
  market's bid cancelled at the venue, then one `book.cross_plan` with `cross` fills for both (the
  seller's at the market's bid, never under its own limit, with `resting_orders`; the bidder's at its
  own limit, with `resting_order` and `note`) and `cross-house` rows that mirror them, the House row
  keeping the gap, no venue order (with no fresh market bid, no cross); a peer's bid under the market's bid left alone, the exit sent as a
  limit one step above it; and on doubt (a cancel the venue has not confirmed after two re-reads a
  quarter-second apart, an order it has not acknowledged) the exit resting post-only at the ask.
  Each re-priced order's `book.order` rows carry the reason, and `house_repriced` (the agent's own
  order terms): such an order lives one pass (each poll re-prices it, or cancels it and sends the
  agent's order again, a new client order id for the same intent, once nothing is in the way), and
  the agent's own next sell of the instrument cancels it first (its cancelled row says so). A self-cross refusal on a SELL is a
  defect: `book.refused` rows whose `reasons` mention "House's own resting order" should all be buys.
  Two sells may still be refused where no price exists at all, and neither is a self-cross refusal:
  "no price is left above the House's own best bid to rest this exit at" (a House bid at the top of an
  event's range, or a stale quote, while a cross is not allowed) and "no ask to rest this exit at".
  A crossed book reconciles to the cent: the venue saw only the cancel.
- **A practice book's cents are dust, not a freeze** (Sept 24, 2026, `book.PRACTICE_DUST_USD`). A
  practice book's cash difference under $1.00, with every position agreeing and no order in doubt, is
  booked to the House row at once: a `book.fill` row with `source: dust` and a `detail` beginning
  "practice book:". The cents are Alpaca's option fees (the OCC clearing fee, $0.03 on a one-contract
  buy and $0.02 on a sale, is taken from cash at the fill but listed as a FEE activity only the next
  morning), a maker's refund on a crypto fill, and cent rounding on fractional fills. Until then they
  froze `alpaca-paper` (every Alpaca practice entry refused, 11 on Sept 24) until more fills raised the
  per-fill tolerance or three readings adopted the venue, and a freeze at 15:37:27Z rolled Deploy C
  back inside its watch. A "does not reconcile" warning on a practice book now means a dollar or
  more, or cents beside an order whose outcome is unknown; an error means real money, or positions
  that disagree. Read the `book.reconciled` rows. A real book is unchanged: its cents still freeze it.
- **File a repair.** Drop a JSON file into `/workspace/state/repairs-inbox/`:
  `{"key", "kind", "summary", "agents", "severity"}`. It is admitted whatever its priority.
  `{"drill": "<stamp>"}` plants the labelled synthetic drill; `scripts/repair_drill.py --plant`
  writes one for you.
- **Restore.** `floor_box.py fork --from <checkpoint> --i-know` gives you a second box. Never run
  two Houses on one paper account.

## Owner steps the floor is waiting on

What the Sept 23 study (`docs/research/2026-09-23-agent-study.md`) found the agents need and the
House cannot do for itself. Each is the owner's to take; nothing in the League widens its own
egress, funds itself or changes a venue account.

- **Data hosts the agents asked for.** Sept 24, 2026: the owner allowed twelve key-free hosts
  (`scripts/floor_box.py` LEAGUE_HOSTS) and the House records them (`league/feeds.py` RECORDERS:
  weather, nws, forecast, earnings, earnings_date, rates, treasury, odds, tsa, polls, oi). Who had
  asked, in the T0 snapshot (Sept 19 21:14Z - Sept 24 01:40Z; tool requests, research summaries,
  `request_tool` arguments and consults; each agent once an input): earnings dates and
  announcement times 26 agents, an earnings surprise panel 31 (not recorded: no allowed host
  publishes estimates against actuals point in time), attention underlyings 35 (20 naming TSA
  volumes or an approval average), perp open interest or positioning 34, settlement fixings 12,
  Kalshi price against outcome 7, weather forecasts 4, sportsbook odds 2, rates 0. What is still
  the owner's:
  - `api.eia.gov` (a free key; WTI, Brent, gasoline and diesel for `kalshi-prices`) and
    `api.the-odds-api.com` (paid; consensus win probabilities for `kalshi-sports`, about 8 calls a
    league a day at its three-hour cadence). Place `EIA_API_KEY` / `ODDS_API_KEY` in the box's
    `/workspace/.env` by hand -- `floor_box.py secrets` sends only `BOX_ENV_NAMES` -- and run
    `python3 scripts/floor_box.py hosts --add api.eia.gov api.the-odds-api.com`, adding the hosts
    to LEAGUE_HOSTS as well: the recorder reads the key within five minutes and needs no restart.
    Until then `health.json` `feeds.eia.waiting_for` says which part is missing.
  - The approval average (`kalshi-attention`'s KXTRUMPAPPROVE): www.realclearpolling.com answers
    every automated client, a browser User-Agent included, with a DataDome captcha (HTTP 403, Sept
    24, 2026). The House does not get around a bot wall; the `polls` recorder records the refusal
    and nothing else. Another source for the average is the owner's decision.
  - The contact address SEC and NWS ask for: `CONTACT_USER_AGENT` in `ltcm/data/__init__.py` (one
    constant) is `ltcm (agent@blakewoods.us)`.
- **The one-loss trial** (the study's blocker 1) was decided in the close-the-gaps run (Sept 24,
  2026, inside its money table): the hysteresis exit applies only after
  `allocator.hysteresis_after_settled` (3) independent real results in the stay, and a Kalshi position
  is `allocator.position_share_event` (0.2) of the stake. See Switches.
- **Compute:** an OpenAI top-up (the September gateway month is funded at $408 and the House line
  fell under the $20 "earned" reserve at about 20:50Z Sept 23; the month resets Oct 1) and Sail
  auto-recharge (about 2.6 days of runway at $32 a day on Sept 23). After a top-up, align
  `FRONTIER_MONTH_USD`, `FRONTIER_MONTH_MAX_USD` (`gateway/wrangler.jsonc`) and the House line
  (`scripts/campaign_topup.py`) up to the funded balance, never above. Since Sept 24, 2026 the
  House line no longer counts holds with no answer (**The OpenAI meter**), and while the gateway's
  month is read the line never reads above what that month has left, so aligning the gateway's
  month to the funded balance bounds the House's line too; read `house_line_usd` and
  `provider_left_usd` in `health.json` `campaign.meters.openai.line` before aligning the House's own.
- **Level-3 options:** a second Alpaca practice account that no House reconciles, with its keys in
  the gateway, to settle the multi-leg unknowns before any spread trades (the design is
  `docs/design/2026-09-24-level-3-debit-verticals.md` on its draft branch).

## Switches

Change them by pull request, and deploy through the canary. "Off" means the House behaves as it did
before that feature. The two constitution rows are money rules: changing one needs the owner's
deploy and a re-ratified grant (see "A money rule" above).

| File | Key | Default | What it does |
|---|---|---|---|
| `league/config.json` | `semantic_lab` | `false` | The continuous Jev midpoint labeller. It stays off: a capped evaluation found no tradable value |
| | `jev.enabled`, `jev.daily_usd`, `jev.daily_calls`, `jev.purpose_calls` | on, $1.50, 25,000; gate 3,000, triage 1,500, links 1,000, exposure 500, move 7,500 | The Jev floor: gate relevance, triage, hypothesis links, exposure, and the move sensor's shadow labels. One daily pool aligned to the funded Jev balance (Sept 25, 2026; $0.25 and 400 before). A breaker per purpose |
| | `jev.move` (`enabled`, `interval_seconds`, `max_markets_per_cycle`, `daily_usd`, `retention_days`) | on, 300 s, 800, $0.75, 14 days | The move sensor (`league/jev_features.py`, J1): every market the Kalshi strategies are shown gets point-in-time `move_p5/15/60` from the free model every 5 minutes, and Jev's static answers once per market as a recorded shadow. Not served to strategies until its held-out AUC on post-ship events is at least 0.70 |
| | `deep_replay`, `holdout_gate` | on | Deep Alpaca history for replay, and the sealed holdout before paper |
| | `options_history` | on | Options history, options replay, and IV/skew/activity features |
| | `options_structures.book`, `options_structures.shadow.starting_cash` | `options-shadow`, $100,000 | Level-3 structures (Sept 25, 2026, the options-desk run; `league/structures.py`): the book a STRUCTURE AGENT (the `alpaca-options` desk, NEEDS `"structures": true`) trades on at rung 1. `options-shadow` is the House's own practice account (`league/options_shadow.py`: fills only on a strictly newer OPRA quote, at the structure's touch from every leg, at most 10% of any leg's shown size, session only, $0.05 a contract a leg, marks at the bid, a structure still held after its expiry's close settled at intrinsic, never written off at zero; nothing leaves the House). `alpaca-paper` sends each structure to the shared practice account as ONE multi-leg order (Track P, not before Sept 28; only the five types it can close as one covered order). A structure is held as ONE long instrument priced at net value plus collateral: its cost is its maximum loss, a flat sale is one closed trade, no book holds a negative leg. The House refuses structure intents on real money until O1 (`allocator.option_spreads_real`), closes structures from 15:30 New York on their earliest expiry day (30 minutes before an early close), cancels resting opens at the 14:30 entry cut (90 minutes before an early close), and seats structure founders one a tick (`league/options_desk.py`, cause `options_seat`, at most 12 retirements, never real money, a winner, a proven family's member, a working order or a position while its market is shut, never a Kalshi desk). An unknown book name: every structure intent is refused with the reason |
| | `research_traces` | on | Private research transcripts with their cost and outcome (for eventual fine-tuning) |
| | `lab.box_id`, `lab.box_key` | `sb_742fe765-…`, `lab` | The Alpha Lab's own Sailbox (`scripts/lab_box.py create`, size l, sealed). The service binds it under `box_key` and hands the lab that evaluator; without a `box_id` there is no lab (a name alone binds nothing). A terminated lab box is never replaced from the agents' image: the lab stops with the error alert "the Alpha Lab is stopped: its box is gone" and asks again hourly. Make a new box and set its id |
| `league/house.py` | `Settings.box_wait_seconds`, `probe_wait_seconds` | 2 s, 15 s | The tick never waits on background work (Sept 23, 2026): a wake whose box another caller holds waits this long, then is skipped and due again on the next tick; births wait this long for the probe box, then defer to the next tick (`health.json` `deferred`). Measured Sept 22: a probe takes about 20 s and a box's sleep up to about 17 s. The research thread's admission may wait up to 600 s for the probe box, since it never holds the tick's lock while it waits |
| | `EVIDENCE_CLOCK_DAYS`, `EVIDENCE_CLOCK_REFRESH_SECONDS`, `FORWARD_RULE_FILLS`, `House.RETAINED_TTL_SECONDS`, `WIND_DOWN_REFUSALS`, `WIND_DOWN_RETRY_SECONDS` | 7 d, 1 d, 3, 72 h, 3, 1 d | The seat market by evidence (S1-S4, Sept 24, 2026): the evidence clock's window and refresh (a paper seat's grace is the larger of 12 h and its desk's clock); the fills after which a trader goes only to a newcomer with a better forward record; how long a dead author's retained candidate waits for a seat (and how far back the first pickup reaches); the identical refusals of a House-sent sale before its retries stop, and how long until it is tried again. Constants in `league/house.py`: an update or owner deploy changes them |
| | `SEAT_WAIT_WARN_SECONDS`, `SEARCH_CLOSED_TTL_SECONDS`, `SEAT_EXPIRED_KEEP_SECONDS`, `SAIL_BURN_WINDOW_SECONDS`, `SAIL_BURN_MIN_SPAN_SECONDS` | 2 h, 10 min, 7 d, 1 d, 6 h | The seat market's capacity (R2, Sept 24, 2026): how long a newcomer waits before one warning a desk an hour names its desk, count and rule; how often the search's closed desks are read (the foundry's rule reads every block of every agent that lived on them); how long an expired waiter is remembered; and Sail's burn for the population rule (the falls of the Sail meter's readings over the trailing day, scaled to a day, none measured under six hours of readings). Constants in `league/house.py` |
| | `POPULATION_RUNWAY_BAND_DAYS`, `PROVEN_UNBRED_RETRY_SECONDS` | 0.25 d, 1 h | The review of #276 (Sept 24, 2026): once the population rule holds the league it grows again only over the runway floor by this band (the runway moves 2.6% a reading at the 90th percentile and rose with no top-up in half the 15:06Z snapshot's readings, so at the floor it flipped and the league crept up); and a proven family's program with no distinct valid PARAMS mutation left is held, its desk not kept from other families, this long before it is asked again. Constants in `league/house.py` |
| | `Settings.enroll_displaces` | on | A merged strategy takes a seat in a full league, repairs first: from an agent still running the code it corrects, else from the weakest eligible resident. A born corrected child retires the agents off real money still running that code (`superseded`). Off: merged strategies wait for an empty seat |
| `league/tapes.py` | `SETTLED_MEMO_ROWS` (`KalshiData.settled_memo_rows`) | 400,000 rows | A Kalshi series' day whose every market has settled is read from `ltcm.history` once a process and kept in memory: only the fields the tape reads (`SETTLED_FIELDS`, times as epoch seconds), the least recently used day out first (Sept 24, 2026). Measured on the real listings: 240-245 bytes a row held for KXBTC, KXBTCD, KXETH and KXETHD (3,350-3,470 as History parses it), 347 for the other series, so at most about 140 MB; a 14-day tape of those four is 293,888 rows. A second such tape costs about a quarter of what it did (on the developer machine: about 58 s every time before, 10-12 s once held; interleaved on a varying clock, a median 80 against 19.5 CPU-seconds). 0: every read is History's, as before. A day still settling keeps `settled_listing_ttl` (600 s) |
| `league/game.json` | `audit.house_pays` | on | The House pays for promotion audits. Off: the agent pays at cost, and one under `audit.min_credits_usd` ($0.60) waits at `audit_credits` |
| | `research.gate.enabled`, `after`, `max_factor`, `sample_percent` | on, 2, 8, 10 | Back off research whose passes come back empty while nothing about the agent has changed; a 10% sample still runs. The routine epoch payout is not a trigger (Sept 23, 2026) |
| | `research.gate.clock_runs`, `abstain_lock_after` | `real_positions`, 3 | Research runs on outcomes (F2, Sept 25, 2026; `league/research_gate.py` rules 9-12). The clock (and its backoff) runs only an agent on REAL money that holds a position or a working order there or met a refusal since its last session, and a rung-0 agent (replay only); everyone else researches on a trigger: a fill, settlement, refusal (once a day, below), active block, audit or repair verdict, code or rung change, a teacher's lesson naming it, a desk note, a fulfilled request, a market that opened or closed, a lifted blocker, and an idle program's outcome (`idle_runs`). Replayed on the T0 snapshot (`scripts/gate_replay.py`, the 24 hours to 04:23Z Sept 25): 2,566 sessions ($87.65, 547 candidates, 108 adoptions or forks) would have been 1,038 plus about 44 samples ($34.48, 253 candidates, 85 adoptions or forks); the lost candidates are mostly the idle treadmill's (201 from 387 `clock` runs, 9 adopted). A real agent keeps the Sept 23 lock: after 3 abstaining sessions only its own fill, settlement or refusal wakes it. `winners_and_idle` restores the Sept 23 rule (a winner and an idle agent on the clock), `all` / 0 the Sept 22 rule. Every row carries `trigger`, `record` and, under this rule, `money` (`real`/`practice`); `python -m league.research_gate LEDGER` prices each trigger (`by_trigger`) and counts runs by money (`by_money`). Bounds: `research_bounds.gate` |
| | `research.gate.max_skip_hours`, `practice_max_skip_hours` | 24, 72 | F2: the heartbeat, no agent frozen: 24 h on real money, 72 h on practice, counted from the gate's first sight of an agent that never researched (121 of the 122 heartbeats of the day to T0 were a newborn's first session at age 0, when `last` was 0) |
| | `research.gate.practice_pause_after` | 3 | F2: a practice agent whose last 3 sessions abstained researches only on a fill of its own (no settlement, refusal, note, heartbeat or Jev question) until a session retains a candidate or runs a replay; its skip rows say `practice_pause:<streak>`. 0 is off. Its sessions run on `abstain_lock_profile` |
| | `research.gate.idle_runs` | `barren` | F2: an idle program researches once it has met live markets `research.idle.barren_wakes` (10) more times with nothing done since its last session (trigger `barren:<n>`; adopting new code restarts the count); a market that is only closed waits for the open. `off`: idleness wakes nobody. `clock`: idle agents keep their idle cadence (the replay: 1,289 sessions, $59.21, 397 candidates, 88 adoptions or forks) |
| | `research.gate.sample_hours` | 6 | F2: a skip is drawn for the 10% sample at most once per 6 hours per agent, not once per research interval (a winner's interval is 12 minutes; 275 samples of locked winners in the day to T0 retained 4 candidates) |
| | `research.gate.refusal_dedupe` | on | X2 (Sept 25, 2026): a refusal triggers research once per agent, reason and UTC day, on the House's refusal fast path (`research_gate.refusal_news`, which writes a `research.gate` row `reason: refusal`) and among the gate's triggers. The reason is its first reason without numbers or tickers (`refusal_class`). At T0: 670 refusals from 86 distinct (agent, day, reason) triples had bought 437 prompt sessions and 107 gate runs. Counted in `health.json` `jev.gate` (`refusal_keys`, `refusals_deduped`) and on run rows (`refusals_deduped`) |
| | `research.gate.lesson_sources`, `lesson_arm` | teacher, `parity` | F2/F4: a lesson is a `playbook.entry` from the teacher, never a post-mortem (134 of 204 lesson-triggered rows at T0 had only one), and names an agent by id, family, desk or the desk without its venue (`research_gate.lesson_words`). Under `parity` it wakes only the agents whose id hashes even (`research_gate.lesson_arm`); the odd half is the control the yield row's `lift.teacher` compares; the split's start is `lesson_arm_since` in `research-gate.json`. `all` wakes every agent it names |
| | `research.gate.practice_skip_triggers` | `book.fill`, `book.settle` | Y, from the Jev run's J2 (Sept 25, 2026; `league/research_gate.py` rule 13): a practice agent's own fills and settlements do not wake its research; anything else found (a forward block, a lesson, a note, a verdict, a refusal) still does, and an agent on real money keeps every trigger. Chosen on Sept 22-23 (kinds with 20+ practice sessions at over 3x the day's $0.138 a replay pass: fills $0.62, settlements $0.44); held out Sept 24 00Z-Sept 25 06Z it skips 13% of the dollars of the sessions F2 still runs for 2% of their replay passes. A skip reads `trigger_skip:<kind>`; the passed fills are consumed. A practice agent under the pause (rule 10) is then woken only by the sample. `[]` restores F2. Bounds: `research_bounds.gate` lists the kinds allowed |
| | `economy.lane_throttle` | 3 | Y1 (Sept 25, 2026; `league/yield_ledger.py` `plan_throttle`): at each hourly yield row a lane whose dollars per positive forward block over the last day exceed 3x the best lane's (the cheapest with 10+ positive blocks; the lab's own calls price its blocks), or that bought none after spending $1, is halved until a row finds it under the line: research's cadence for practice agents (twice the interval, never past a day since its last session; real money keeps its pace; Luna and Sail alike), the consultant's price, each scheduled Merton role's schedule, the engineer's pace (except a job about real money). Audits never; the lab and the foundry are priced, not halved. Each change is an `ops.budget` row `what: "lane throttle"` with `lane`, `throttled`, `usd_per_positive_block`, `best`, `ratio`, `why` and `how`; the yield row carries `throttle` every hour. Replayed on the T0 day: the lab best at $0.038, research 7.5x, the engineer 4.7x, the consultant 13.2x (F4's reading), the architect none bought: all four halved. Remove the key to switch it off. Bounds 2-5 |
| | `research.pace.winner_share`, `loser_multiple`, `unproven_multiple` | 0.1, 8, 3 | Research interval multiples: an earned profitable record 0.1x; a losing one on paper or above with 5 observations 8x; no earned record 3x, unless the agent is idle, when its research is pulled forward instead. `unproven_multiple` 1 turns the last off; until Sept 23, 2026 winners waited 0.33x and losers 4x |
| | `hypotheses.enabled`, `replace_mutation_refill`, `call_minutes`, `budget_usd` | on, on, 10, $40 per 24 h | The hypothesis foundry, which replaces blind House mutations (15 minutes and $20 until Sept 23, 2026) |
| | `hypotheses.fast_desks`, `fast_share` | five desks, 0.5 | Up to half the foundry's calls go to the hourly, around-the-clock desks: both Alpaca crypto desks, Kalshi 15-minute crypto, index ETFs and megacaps (Kalshi crypto strikes left the list on Sept 23, 2026: 40 born, 2 replay passes ever, -10.3% an active block), ranked by the forward yield of each desk's own foundry children, then rotating to the one with the fewest recent cards (until Sept 23, 2026 always the best-scored one, the index-ETF desk). `fast_share` 0 is off |
| | `hypotheses.fast_lane_min_blocks`, `fast_lane_reopen_blocks` | 6, 3 | The foundry follows yield (Sept 23, 2026: foundry-born agents were -$272.96 of the -$361 shadow loss since Sept 22 13:30Z). A desk whose foundry-born agents have a negative pooled forward record over 6 active `eval.block`s (`Foundry.desk_forward`) gets no fast-lane call until one family there is positive over 3; the evidence, exploration and transfer routes are unchanged. The foundry runs at the `earned` frontier tier and stops only at `audits` |
| | `hypotheses.transfer_share` | 0.3 | Up to 30% of the foundry's calls port a family with an earned forward record (real money first) to the best-scored desk of its venue where it has never been tried; the packet carries its mechanism in words and asks for at least half the batch as adaptations. Offered before the fast route, then exploration, then evidence. 0 is off, as before Sept 23, 2026 |
| | `hypotheses.prefer_horizon` | `hour` | The horizon the foundry's packet tells Merton to prefer where a desk allows it. Empty: the desk's first listed horizon |
| | `hypotheses.max_pending_cards` | 8 | How many cards may await replay before the next call. 0: any pending card holds the next call, as before Sept 23, 2026 |
| | `lab.enabled`, `lab.budget_usd_per_hour` | on (with a `config.json` `lab.box_id`), $1.50 | The Alpha Lab (`league/lab.py`): its OpenAI line per trailing hour, plus royalties, inside the campaign allowance. Its Luna and Sol calls run only at frontier tier `all`; the rest of the lab (seeds, parameter children, batches, graduation) runs whatever the tier (C2, Sept 23, 2026) |
| | `lab.batch_size`, `param_children`, `llm_children`, `leap_every` | 32, 48, 6, 10 | Candidates a batch on the lab box; parameter mutants bred each time fewer than a batch of queued candidates have their tape built (16 until later on Sept 23, 2026, when 191 seeds waiting on their tapes starved breeding); programs one Luna call writes; a Sol leap after every ten Luna calls |
| | `lab.search_fraction`, `step_seconds` | 0.66, 240 s | The share of the House's replay tape the search sees (the rest is the graduation replay's out-of-sample test); how long one lab step runs off the tick |
| | `lab.max_births_per_hour`, `royalty_share`, `submit_max` | 6, 0.10, 8 | Graduates born on paper an hour; the share of a graduate's performance fee paid to the lab's line; programs an agent may have waiting in the lab |
| | `lab.leap_candidates`, `max_graduations_per_step`, `luna_model`, `sol_model` | 4, 1, `gpt-6-luna`, `gpt-6-sol` | Programs a Sol leap writes; graduations tried per lab step; the models behind mutations and leaps |
| | `lab.box_usd_per_hour` | $0.20 | The price the lab records for its box's time (`lab.stats` `spend.sail_usd_estimate`, `batches.sail_usd`) |
| | `lab.holdout_reserve`, `stats_every_minutes`, `max_queue`, `max_tapes_per_step` | 1, 10, 600, 4 | Not in `game.json`: defaults in `league/lab.py` `DEFAULTS`, which a `game.json` `lab` key of the same name overrides. The sealed-holdout evaluations of a living line the lab never spends (they stay with the line's own forks); how often a `lab.stats` row is written; the most candidates queued at once; search tapes built a step |
| | `lab.closed_alert_minutes`, `seat_wait_alert_hours` | 30, 6 | Also `DEFAULTS` only (Sept 23, 2026): after how long closed the lab raises its one warning, and after how long waiting for a seat a graduate is named once |
| | `lab.forward_resident_cut_hours`, `tape_failures_before_block` | 6, 12 | `DEFAULTS` only (Sept 24, 2026): every living resident's program is scored in the forward runs too (S2), its window cut after its program was frozen on this grid of hours so the residents of one tape share a batch; a tape that fails the same way this many hourly tries in a row is unsupported input and its queued rows are blocked (one warning) |
| | `lab.failures_alert_after`, `row_errors_per_step` | 5, 8 | `DEFAULTS` only (D1, Sept 24, 2026): failed steps in a row before the one error alert and `health.json` `lab.failing_since`; queued rows a step may block for an error of the lab's own before the step fails instead |
| | `lab.forward_every_minutes`, `forward_candidates_per_run`, `forward_box_seconds`, `forward_days`, `forward_min_active_blocks`, `forward_min_trades` | 60, 48, 90, 7, 3, 3 | `DEFAULTS` only (S2, Sept 23, 2026): how often the lab replays its elites, waiting graduates and (since Sept 24, 2026) every living resident's program on their forward windows, how many a run and for at most how many box seconds, how many days of live tape the lab builds for the deep-replay Alpaca desks, how many active forward blocks a record needs to rank anything, and from how many closed practice trades a born graduate's board row moves its lineage's search share. At the box's measured rates (11 candidates a second on Kalshi tapes, 1.7 on crypto) a run is some 5-30 box seconds: under a cent of Sail an hour. But `forward_box_seconds` is the run's own time and the tapes it builds fill it: on Sept 23 (22:11Z, 23:14Z) a run scored 4 and 5 of its 48 due and skipped the rest, so 25 graduates waiting for seats need several hourly runs. Since D1 a waiting graduate's first window comes before an elite's |
| | `research.evidence_max_turns` | 20 | Research turns for an agent with evidence (rung >= 1 and a closed trade); others keep `max_turns` |
| | `research.gate.abstain_lock_profile` | `flash_asap` | L2, Sept 24, 2026: an agent under the abstention lock runs its next session on this profile (`TaskRouter.research_settings`, from `ResearchGate.lock_profile`), whatever its cohort; a cheaper Sail profile it already runs on is kept. flash_asap cost $0.0027 a call against Luna's $0.0080 and pro_asap's $0.0299 on the Sept 22 routing packets, and spends Sail, not the gateway month. Bounds: a Sail profile `ltcm/provider.py` prices. `""` turns it off |
| | `merton.paused_until_profit` | architect, toolsmith, operator, designer | L2, Sept 24, 2026: these roles do not sit down while the floor's 24-hour REAL P&L -- the realized result of the real books' settlements and closing fills over the last 24 hours (`merton.RealPnl`; not the allocator's `floor_pnl`, a level since the books began with no 24-hour window) -- is not positive; one `ops.budget` "merton pause" row when a role pauses or resumes. Lifetime to Sept 24 those roles and the teacher had spent about $120 for about one positive forward record. Bounds: any subset of `merton_bounds.paused_until_profit` (Merton's five roles and, since Sept 25, 2026, the consultant: then no agent may hire him meanwhile, `Researcher._consult` refuses before anything is spent). F4: a lane whose `lift` verdict is `no_lift` at the end of the forward-first run goes here. The auditor and the engineer are not paused here |
| | `merton.lift` | days 7, teacher_days 3, consult_sessions 2, consult_blocks 6, consult_max_multiple 8 | F4, Sept 25, 2026 (`league/yield_ledger.py` `lifts`, `league/merton.py` `consult_price_multiple`): the window of the yield row's `lift`; the teacher's forward window after a lesson; a consult is productive if the agent retained a candidate or changed its strategy within 2 sessions, and each unproductive one in a row doubles that agent's next consult (the minimum credits and the charge, never the House's `merton.pass` cost) up to 8x; the consultant's lift is the agent's next 6 active blocks against its previous 6. Bounds: `merton_bounds.lift` |
| | `merton.schedule_hours.teacher` | 12 | The teacher's cadence (6 until Sept 24, 2026), bounded 6-24 h by `merton_bounds` (`economy.check_bounds`, so `league.ci`). The burst no longer accelerates it |
| | `economy.line_exhausted_trials`, `explore_every` | 15, 5 | Retire lines with 15 failed trials and no pass; one birth in five explores |
| | `economy.losing_family_min_blocks`, `seat_waiters_warning` | 6, 8 | The seat market (Sept 23, 2026): no House mutation, parameter fork or revival of a family whose pooled forward record is negative after this many active blocks (an info alert an hour a family); a warning when more than this many newcomers have waited for seats over an hour |
| | `economy.proven_family_members`, `population_runway_days`, `max_population_short_runway` | 4 (1-8), 1.5 d (1.5-7), 112 (64-128) | R2 and R3 (Sept 24, 2026): how many living members a proven family's program runs on before the House stops breeding it first on its desk (`House._proven_births`: House mutations of the anchor's PARAMS; at 15:06Z sports-central-run-under ran its program on one member); the Sail runway above which the league grows toward turbo.json `max_population`, and the population it is held at otherwise (`House._population_rule`) |
| `league/constitution.py` | `allocator.corrected_child_supersedes` | on (Deploy B) | L1 (Sept 24, 2026): a research child that passed replay with a fix to its real-money parent's entry mechanism (liquidity, fee, side, borne out by the parent's own entry fills) supersedes the parent at once, demoted from real money through the evaluator and retired `superseded` (`House._supersede_by_research`). The account must be of the parent's CURRENT program and a liquidity or fee fix must rest its entries post-only (review of #245: the child meriwether-h2d625d-2 fixed its own moneyline file, not its parent's KXMLBTOTAL entries); a parent whose family's pooled taker record is proven positive (`Allocator.family_taker`, as X0 reads it) is not superseded for a liquidity or fee fix. Absent or false: only merged repairs supersede (`_retire_superseded`). A money rule: re-ratify after a change |
| `league/constitution.py` | `allocator.enabled` | on | Capital is the ladder (Sept 23, 2026, `league/allocator.py`): bands and stakes follow evidence at every mark pass. Off: the screen, the micro bound, `micro_demotion` and Kelly sizing below decide again (the rollback). A money rule: re-ratify after either change |
| `league/shards.py` | `FLOOR_USD`, `TOP_UP_USD`, `KEEP_USD`, `MAX_MOVE_USD`, `MAX_DAY_USD` | $20, $30, $60, $100, $200 | The Kalshi shard funder (Sept 23, 2026): a wanted shard under the floor is topped up from the richest other shard that keeps its floor (shard 0 keeps $60) and the stakes of the desks on it; at most $100 a move and $200 a rolling day, counted from the ledger. Constants in a protected file: an owner deploy changes them |
| | `allocator.evidence` `paper_weight`, `alpaca_paper_haircut_bps` | 0.5; crypto 4, equity 2, option 24 | E = W_paper^paper_weight × W_real; Alpaca paper fills haircut per side of filled notional at the rate of the fill's asset class (A8, Sept 23, 2026 ~22:00 UTC: each class's practice optimism against the order's reference at intent time, the larger of the notional-weighted mean and the round-trip reading, rounded up, never below 2; `docs/research/queries/2026-09-23/A8-haircut.py`). Options tightened from 10, crypto and stocks loosened to what was measured. A plain number charges every class (the rollback); a class not named pays the table's largest rate |
| | `allocator` `bunt_at`, `bunt_min_trades`, `bunt_min_settled` | 1.01, 5, 3 | Paper → bunt: E at the line and 5 closed paper trades, or 3 settlements on Kalshi (plan default 1.03; set from the Sept 23 06:45 UTC distribution, bounds 1.0-1.25) |
| | `allocator.bunt_usd` | Kalshi $30, Alpaca $25 | A PROVEN family's bunt (since Sept 24, 2026; plan default Alpaca $15: untradeable under the book's 50%-of-equity order rule and Alpaca's $10 crypto minimum). Kalshi $10 → $30 on Sept 23, 2026 ~17:00 UTC: a $10 bunt was a one-loss trial (any lost $5 position over $1.54 crossed the hysteresis line) |
| | `allocator.probe_bunt_usd` | Kalshi $10, Alpaca $25 | An UNPROVEN family's first real stake (P1, Sept 24, 2026; table Kalshi $5-15, Alpaca $20-25): the nine promotions of Sept 23-24 all ran unproven mechanisms and settled -$18.62. A probe becomes a bunt the pass after its family is proven and back when the bound falls (free cash only). An options probe is still $80. The grant's seats follow the smallest real stake: floor($1,017.75 / $10) = 101 (40 at $25) |
| | `allocator.family_probe` | `losing_min_blocks` 6, `reseat` `gain_since_demotion` | No probe on a losing family (R5, Sept 24, 2026; the close-the-gaps run's third money-digest change, granted by the owner). A family is LOSING when its pooled forward record -- the House's `family_forward`: active `eval.block` count and summed log growth over every member ever born, living or dead (the allocator reads the same rows from its tape) -- is at or below zero after 6 active blocks (`families.losing`, the House's breeding line, `economy.losing_family_min_blocks`; a record that nets to zero is not a loss). Then no probe is seated from it (`family_losing`), and a probe seated on it goes back to practice at the next pass by the demotion path: a Kalshi contract is held to settlement, and on Alpaca, where that path sells (an option at the bid, a stock or an option at the next open outside the session), the probe keeps its seat until it holds nothing that path would sell (dust is booked, not sold): its working bids are cancelled first, as the path itself does (a fill that races the cancel is a position, and it waits), a buy the book still asks the venue about waits, and it is lent nothing more meanwhile (no sale is forced). Under `reseat` `gain_since_demotion` each probe demoted from real money, for any reason (hysteresis, the stay drawdown, displacement, drift, an audit's veto, this rule), holds its family until the family's record SINCE that demotion turns: positive over 6 active blocks (`family_held`). A turn is for good, and each demotion is its own hold, so a later probe's turn never releases an earlier one's. The demotions are the ledger's own `eval.verdict` rows: a probe's by its `band_from`, or, for a row that names no band (drift, audit veto, tuition), by the family's state in its last `family.record` row before it; a seat whose stake never landed (`unfunded`) holds nothing. A probe newcomer never displaces a probe of its own family, an audit that approves a known defect's seat asks the gate again (`House._commit_promotion` -> `Allocator.refuses_probe`), and a gate that cannot be read seats no probe and demotes nobody that pass (`family_unreadable`). A proven or swinging family's agents are bunts and are never gated. Evidence (docs/research/queries/2026-09-24/R5-family-probe.py, 15:06Z snapshot): 11 of the allocator's 21 promotions since Sept 23 went onto such families, -$8.12 on 22 closes, no stay positive; the other 10 made +$28.96 on 34 closes. At 15:06Z 9 of 14 seated probes ($139.75 of $168.94) sat on losing families: on that snapshot the first pass would return the 6 on Kalshi (hawkins-19, hilibrand-h6ca596-3, huang-h427345-4, huang-h51fdd3-6, huang-l0c6f38, huang-l5aa23e) and the 3 crypto-alts-reversion probes on Alpaca once each is flat (haghani-62 and -63 held crypto then). Since the snapshot: huang-h51fdd3-6 (crypto-15m-doge-flat-spot-no, losing) lost $1.20 on an XRP 15-minute contract at 16:00:36Z and was demoted at 16:03:31Z; krasker-14 (alpaca-options, options-pullback) was seated as an $80 options probe at 16:47:37Z while its family read 19 practice blocks, -0.3829 (16:53:40Z; bound -0.1088 on n 28), which this rule refuses. Absent: probes on any record, as before |
| | `allocator.family_proven` | 10 independent settlements, practice 0.5, real 1, 80%, `lopsided_gate` true, `unit` `at_risk`, `reference_share` 0.01 | The proof (P1): a family's pooled forward record (`families.family_record`: every member ever born, living or dead; one observation per event, members of one event pooled at the largest weight; an Alpaca practice trade pays `alpaca_paper_haircut_bps`, as E does) with a one-sided 80% lower bound (Student's t on n_eff - 1) above zero, and a lopsided record (80% or more of its observations winning: favourites) also above the House's exact loss-rate gate at 80% (`stats.lopsided_growth_lcb`, as `Evaluator._judge_family` applies it; `lopsided_gate` false restores the t bound alone). Since Deploy B an event is what it made per dollar its positions put at risk (`unit` `at_risk`: ln(1 + 1% x r) / 1%, a worthless contract -1.005), weighing what it put at risk against its member's mean on that book (the review of #242: weighed alike, small wins and large losses read as an edge while the dollars lost); `account` restores Deploy A's account growth, under which a real row on a $30 stake weighed several times a practice row on the $200 purse. On the T0 snapshot this proves what Deploy A proves: sports-central-run-under (+0.1423 at risk; its winners carried twice its losers' dollars) and nothing else (weather-favorites' loss-rate bound -0.2112). The board shows `family`, `family_state`, `family_bound`, `family_n`, and "probe" as its own band in rows, the summary and the moves (the site shows it as Probe) |
| | `allocator.family_swing` | 15 real settlements, 2x the bunt, doubling every 10, capacity 0.5 on 5 markets over 7 days, `entry_every` 5, `entry_confidence` 0.9 | The family swing (C2, Deploy B, Sept 24, 2026): a PROVEN family (the pooled record, `family_proven`: the real record alone never proves nor swings a family) ENTERS when its entry look passes and the frontier auditor approves that entry (`audit:family:<family>@<venue>` on the audit lane, the family packet with `allocation_context` and the look; `audit.verdict` rows carry `family_swing`). The look is judged only at 15 real independent settlements and every 5 more (15, 20, 25, ...: `families.entry_checkpoint`, from the count alone, so a restart never looks early), on the first that many real events, with the honest lower bound at 90% -- the t bound and, for favourites, the loss-rate bound (`families.entry_look`); a failed look waits for the next checkpoint. Why: an edgeless family re-read at every settlement at 80% entered 37% of the time by 30 real settlements and 44% by 50 in the main session's simulation (`scratchpad/rev-bfam/sim_rules2.py`); at every 5th at 90%, 19% and 22%. It STAYS, and the ramp doubles, while the whole real record's honest bound at 80% holds at every pass (`families.swing_ready`) and it is still proven. Every member on real money is staked at the ramp: 2 x `bunt_usd` ($60 Kalshi), doubled after each 10 further WINNING independent real settlements while the bound stays above zero, capped by the FAMILY's full Kelly on that bound against the venue's capital (capital at risk on one event, so the stake is that over the most one event may hold: `max_event_share`, 25% on Kalshi) and 60% of it, shared by its members on real money (a newcomer seated in the same pass shares from its first dollar), and held where the fill rate at the next size is under half the fill rate at the size before (the board's `stake_limit` "capacity"); never under the bunt; the envelope's headroom bounds every raise. The bound at zero or below, or a live grant that stops releasing rung 3 (`allows_live(3)`, read every pass): back to bunts (probes if the pooled proof went too), free cash only. An approval licenses entries until it lapses (`allocator.json` `family_audits` status `lapsed`, an info alert): when the family leaves the swing, or when a member takes a new program (`agent.strategy`) or a member is born into the family (`agent.born`: a research child, how a real-money line changes its code) after the audit looked; the next entry is audited again, and a swing already running is untouched. The family's `audit.verdict` (`family_swing`) is never read as the verdict on the member it was written against (`audit_standing`, `House._audit_wait`). A swinging member's band is "swing" on the board and to the book (its daily-loss rule). Without the key: no family swing. At T0 no family's real record qualifies (weather-favorites: 5 real events, all won; at 93c its loss-rate bound needs 23 clean real events at 80% and 32 at 90%: its first passing look would be at 35) |
| | `allocator.swing_requires_proven_family` | on | The agent-level swing (`swing_at`) is a proven or swinging family's agent's only (Sept 24, 2026; carried as a key in Deploy B so the ratified digest records it): an unproven family's agent at the swing line stays a probe, a swing whose family loses its proof drops to rung 2, and a swing audit that finishes after that does not commit (`House._commit_promotion` reads `Allocator.swing_allowed`). Off: the agent-level swing of Sept 23 for every family |
| | `allocator.corrected_child_supersedes` | on | L1 (Deploy B): a research child of a real-money parent that passes replay with a fix to the parent's entry mechanism demotes the parent at once and takes its seat (`league/house.py`). Off: only the engineer's merged repairs supersede |
| | `allocator.independent_settlements` | `event` | Closed trades and settlements on the Kalshi books count once per event (D4, Sept 24, 2026; `evaluator.event_key`) for the bunt line, the swing's real trades, the one-loss trial and the family record: meriwether-h7d7702 was promoted "on 6 closed trades" that were two games. W is unchanged. `trade`: every settlement counts |
| | `allocator` `hysteresis_after_settled`, `position_share_event` | 3, 0.2 | The one-loss trial (P2, Sept 24, 2026): the hysteresis exit waits for 3 independent real results in the stay (the 35% stay drawdown always applies); a Kalshi position is a fifth of the stake ($6 of $30, $2 of a $10 probe). 4 of the nine promotions were demoted after one loss |
| | `allocator.bunt_growth` | `w_real` | A bunt keeps what it makes (Sept 23, 2026 ~16:00 UTC, the learn-and-unblock run): its target is `bunt_usd` × clamp(W_real, 1, `swing_at`), profit inside the headroom is not swept, and a bunt with W_real under 1 is never topped back up. `flat`: the flat `bunt_usd`, swept above 10%, as before |
| | `allocator.option_bunt_usd` | $80 | An options bunt's stake (was max(`bunt_usd`, `rungs.2.option_max_position_usd`) = $40, which the book's 50%-of-equity rules cut to a $20 contract): one $40 contract fits under half of $80 |
| | `allocator.bunt_daily_loss` | `stay_drawdown` | A real-money bunt is not frozen by the book's per-desk daily-loss rule (`book.DEFAULT_RULES` `max_daily_loss_pct` 0.10, unchanged); its stay drawdown (`real_drawdown_demote`) and hysteresis govern. Swings and practice books keep the book's rule. `book`: the book's rule for bunts too |
| | `allocator.real_halt` | `venue_grant_capital`, 0.08 | The real book's daily-loss halt is 8% of that venue's grant capital ($41.42 Kalshi, $40.00 Alpaca), per venue, never the combined envelope on one venue and never the staked accounts' sum (one $25 bunt made that a $2.00 halt). Practice books keep the staked-sum basis; `staked` restores it on real books. Since Sept 23, 2026 ~22:00 UTC the day's opening equity survives a House restart (`day_open.<book>.json` in the House root, see below), so a restart mid-day no longer gives either daily-loss line back |
| | `allocator.longshot_floor_real` (read by `book.py`) | `"0.30"` | X0, Sept 24, 2026: a REAL Kalshi entry priced under it is refused by the risk engine's longshot rule; the floor is the larger of it and the book's `min_event_price` (0.15, which practice books keep). 20-cent ETH strikes lost twice on real money on Sept 23. Without the key: 0.15 everywhere |
| | `allocator.real_entry_liquidity` (read by `book.py`) | `maker_unless_family_taker_positive` | X0: a REAL Kalshi entry must be a post-only limit unless the agent's family's pooled taker record is positive (`Allocator.family_taker`, wired to each real book as `family_taker`); an unmeasured record refuses it, and the refusal names the family, its taker settlements and bound. The taker mechanisms were the loss engine of the nine promotions of Sept 23. Without the key: any order type |
| | `allocator.max_event_share` (read by `book.py`) | `"0.25"` | X0: on a REAL Kalshi book an agent's holdings at cost, working buys and the new order on one event (a ticker's first two `-` segments, Kalshi's own event: every strike of one game or one city's day, every player prop of one game; a two-segment ticker is its own event) are at most this share of its equity on the book; the refusal says "one event may hold at most 25% of the stake". Without the key: no cap. `Book.risk_lines(agent)["entry_rules"]` lists the three a real book enforces |
| | `allocator` `swing_at`, `swing_min_real_trades`, `swing_min_w_real`, `swing_exit_w_real` | 1.25, 8, 1.0, 0.9 | Bunt → swing (audited the first time), for a PROVEN family's agent only since Sept 24, 2026 (`swing_requires_proven_family`; an unproven family's agent stays a probe, and a swing whose family stops being proven drops to a probe; a swing audit that finishes after that does not commit); a swing leaves under 1.25 × hysteresis or W_real 0.9. 1.5 → 1.25 on Sept 23, 2026 ~17:00 UTC: the only two earners needed 2.8 and 5.6 days at their rates to reach 1.5 |
| | `allocator` `kappa`, `e_cap`, `max_share_of_venue`, `position_share` | 2, 20, 0.6, 0.5 | A swing's stake is the bunt × min(E, e_cap)^kappa, up to 60% of the venue's capital (kappa 1 → 2 on Sept 23, 2026 ~17:00 UTC: winners compound in the square of their evidence); a position is up to half the stake at Alpaca (`position_share_event` on Kalshi), never under the venue minimum × 1.2 |
| | `allocator` `stars`, `star_min_w_real` | 3, 1.25 | The site's top lane: the best swings by real P&L |
| | `allocator` `hysteresis`, `real_drawdown_demote`, `die_below`, `die_min_trades` | 0.85, 0.35, 0.80, 10 | Down as fast as up: band exits, a 35% real drawdown (of the current real stay) back to paper, paper-wealth death |
| | `allocator.reentry_cooldown_hours` | 1.0 | An agent sent back to paper from real money waits an hour before it may bunt again, so a record near a line cannot flap between books at every mark pass |
| | `allocator.venue_minimum_usd` | Kalshi $1, Alpaca $10 | The smallest order each venue takes; a position cap is never under 1.2 times it, and the throttle never halves a stake below what can trade |
| | `allocator.throttle` `halve_below`, `restore_above` | −0.30, −0.15 | The floor throttle: every real stake halved below −30% of the envelope, restored above −15% |
| | `allocator` `min_stake_change`, `performance_fee_share`, `profit_indexed_envelope` | 0.10, 0.2, on | Ignore stake moves under 10%; 20% of realized real profit becomes compute credits; a venue's envelope is the grant's capital plus its realized profit |
| | `ladder.paper.settled_day` | 1 finished day once 3 trades have settled | A daily agent on a Kalshi book is screened after one finished active day once three of its trades have settled on paper. Since the swing-and-bunt revision every daily agent's screen is one finished day, so the lane only matters again if `min_active_blocks_day` rises |
| | `ladder.paper` `min_active_blocks`, `min_active_blocks_day`, `max_drawdown` | 3, 1, 0.25 | The screen to the micro rung (4, 2 and 0.15 until the owner's swing-and-bunt revision of Sept 23, 2026 ~03:10 UTC) |
| | `ladder.promotion_alpha`, `ladder.look_every_active_blocks`, `ladder.micro.min_active_blocks` | 0.20, 3, 3 | Promotion to scaled size spends 0.20 across looks every 3 active blocks, from the 3rd; death keeps `alpha` 0.05 (0.05, 5 and 5 before the swing-and-bunt revision) |
| | `ladder.family` `alpha`, `min_member_active_blocks` | 0.20, 5 | A family's pooled real-money record promotes a member at the promotion budget, members counted after 5 active blocks (0.05 and 10 before) |
| | `rungs.3` `kelly_fraction`, `max_share_of_venue` | 1.0, 0.6 | Full Kelly on the lower bound, up to 60% of the venue's cash (0.5 and 0.4 before) |
| | `ladder.death.max_drawdown` | 0.40 | Death's drawdown on any rung above replay (0.30 before) |
| | `ladder.replay.min_oos_growth` | -0.0005 | Out-of-sample growth need only clear -0.05% a block for a paper seat (above zero before), and one out-of-sample block must be active. Risk-free: the live grant's money digest does not include it. When it loosens, the House brings back once, on its line, the code of rung-0 deaths of the last two days whose replay failed only on out-of-sample growth now admitted (`House._revive_near_misses`: at most 12, never more than half the free seats) |
| | `ladder.paper.audit` | `after` | A screen-passer takes the micro stake at once and is audited there; a veto demotes it. An agent with a known defect is still audited first. `before`: the audit precedes promotion, as before Sept 23, 2026 |
| `league/engineer.json` | `enabled`, `max_attempts`, `max_job_usd` | on, 3, $5 | The repair engineer. No Merton role may write this file. Since Sept 23, 2026 its paid queue is ordered by priority times the forward record of the job's agents (x3 on real money or earning, x0.5 when all are dead or on replay; `league/service.py` `evidence_weight_of`); requested jobs stay first. A `strategy_defect` is bought only for a parent that is alive and has a fill of its own (16 repair children had 0 forward blocks, $0.70 each): a dead parent's defect is `rejected`, a living untraded parent's waits at no cost. A merged corrected child is replayed before any seat (`Foundry.takes_strategy`, from `House.enroll`; the card carries `strategy` and `author: engineer`) and born only on a pass; one that fails never displaces anyone and its job goes `dormant` with the replay's reasons |
| (none) | the hourly yield row | every hour | `league/yield_ledger.py` writes one `ops.budget` row (`what: "yield"`) an hour, on the foundry's bookkeeping tick: spend by line (research tokens, each of Merton's roles, audits) and the evidence each line produced (sessions, abstentions, candidates, replay passes, active and positive forward blocks, cards, proposals, lessons, consult answers and failures), with `usd_per` unit, and since Sept 24, 2026 `by_profile`: research sessions, candidates, provider failures, token dollars and `candidates_per_usd` for each model profile. Lessons are the teacher's only since Sept 25, 2026 (every post-mortem counted before: 111 of the 117 "lessons" of the day to T0). Since Sept 25, 2026 (F4) the row carries `lift` over `merton.lift.days`: `teacher` (forward growth per active block over 3 days after a lesson, `lesson_arm` against `control_arm`, from `lesson_arm_since`), `consultant` (judged consults, productive ones, mean lift of the next 6 blocks against the previous 6, dollars per positive block after, beside `research_usd_per_positive_block_24h`) and `engineer` (repairs verified per dollar, window and lifetime), each with a `verdict` (`lift`, `no_lift`, `insufficient`); and before the row it writes the due `consult.outcome` rows (private; `stage: sessions` with `productive` and `doubles_next_price`, then `stage: blocks` with `before`, `after` and `lift`). Since Sept 25, 2026 (Y1, Y2) the row also carries the lab's own calls as its `lab` spend (from `lab.sqlite`), `throttle` (each lane's price per positive block over the day, the best lane, and which lanes `economy.lane_throttle` halves; each change is its own `ops.budget` "lane throttle" row) and `unit_economics` (compute and real settled profit a day, which health.json repeats). Read it with `sqlite3 ... "select payload from ledger where kind='ops.budget' and payload like '%\"what\":\"yield\"%' order by seq desc limit 3"` or from `scripts/floor_watch.py` |
| `league/research_routes.json` | `cache.layout`, `cache.explicit_hints` | `messages`, on | The Luna cache layout; `packet` is the old layout |
| | `routing.sail_by_evidence` | off | Let measured evidence move new Sail sessions to a cheaper tier |
| `league/turbo.json` | `research_minutes`, `research_workers`, `replay_workers` | 15, 16, 12 | The funded burst's research interval and workers (5, 32 and 8 until Sept 23, 2026). In force while the burst is, which it is while the live grant is active |
| | `max_population`, `newcomer_seconds`, `endowment_usd` | 128, 600 s, $8 | The burst's population ceiling (64 until Sept 23, 2026, when foundry cards that passed replay waited for seats; 96 until the seat market of Sept 23, when 20 lab graduates, 6 replay-passed cards and 6 merged strategies waited: 16 more boxes cost about $0.43 a day of Sail, 2.9 days of runway; 112 until R2, Sept 24, when 82 newcomers waited, 44 once the search's closed desks were taken out: the league grows to 128 only while Sail's runway is over `economy.population_runway_days`, and is held at `economy.max_population_short_runway` otherwise; 4.51 days at 15:06Z), the House mutation cadence (120 s until then; no mutation is staked while any waiter waits) and House endowment |
| | `fork_threshold_usd` | $10 | The credits an agent needs before it may fork a parameter copy of itself. Above the endowment, so only an agent that has earned payouts forks. Until Sept 23, 2026 the burst forced $2, every newborn forked at once (22 copies in 40 minutes), and the foundry's replay-passing cards waited for seats on full desks |
| | `merton_schedule_hours` | operator 48, designer 96, toolsmith 48, architect 24, teacher 12 | Merton's burst cadence, set by each role's measured yield. Until Sept 24, 2026 `load_turbo` dropped this key, so it never reached the House and the burst's own defaults ran (operator 0.25 h, toolsmith and architect 0.5 h, teacher and designer 1 h, stretched by backoff): the ledger shows the teacher about hourly and the architect every 30-60 minutes on Sept 23. The teacher is bounded 6-24 h (`TURBO_MERTON_HOURS`) |
| | `sail_research_usd_per_hour` | $2 | L2, Sept 24, 2026: no NEW research session starts on Sail while the settled cost of the Sail commitments created in the last hour (`campaigns.sqlite`; every Sail call is research) has reached it; a session under way resumes, a job still queued for a research worker waits like a new session, and Luna is not capped. A call in flight counts once it settles, so the hour can overshoot by what is in flight. One `ops.budget` "sail research cap" row when it closes or opens; `health.json` `research_economy.sail_cap` shows it. Bounds $1-4 (`TURBO_RANGES`). Sail settled $5-6.5 an hour on Sept 23 at 19-23Z and $1.27 in the hour before T0 |
| | `luna_fraction` | 0.95 | The share of agents whose research runs on GPT-6 Luna; the rest stay on Sail as the comparison (a Luna session cost about $0.011 against about $0.06 on Sail, Sept 23, 2026) |
| `league/niches.json` | `max_members` | Kalshi: crypto strikes 6, crypto 15-minute 8, weather 17, sports 19, props 6, prices 8, attention 4. Alpaca: crypto majors 12, alts 16, index ETFs 18, megacaps 16, options 8 | How many agents a desk may hold. Set Sept 23, 2026 so seats follow evidence: up where lab graduates wait (weather, the one desk with a positive forward record, sports, index ETFs, 15-minute crypto), down on the graveyards (strikes: 40 born, 2 passed replay; props 34 and 5; attention 34 and 2). Every desk keeps one seat for a member that trades (`House._mutation_room`). R2 (Sept 24, 2026): the seats follow the 44 waiters that remained at 15:06Z once the search's closed desks and the lab's holds were taken out (megacaps +4 for 4 graduates, index ETFs +4 for 9 waiters, weather +3 for the longest card and two retained candidates, crypto alts +4 for 4 cards and 4 corrected children behind 9 winners and 3 probes, props +2 for two retained candidates, crypto strikes +2 for the two lab families the search reopened it on, sports +3 for the proven family's births), and fewer where the search is closed (15-minute crypto 10 -> 8; while the search closes a desk the House holds its cap at its members, `House._follow_the_search`). The caps add up to 154, above the population's ceiling (128) |
| | `open`, `asset_classes`, `exclude_patterns` | `kalshi-open` and `alpaca-open` (8 seats each); Alpaca `equity`, `crypto`; Kalshi `^KXMVE` | The open desks (Sept 23, 2026): a desk whose universe is every tradable market of its venue. `status: dormant` closes one. `niches.OPEN_DISCOVERY` (24) is the length of an open desk's discovery list, of which a strategy naming nothing it may trade is shown the first twelve (`MAX_UNIVERSE`); a Kalshi desk missing from the last survey is surveyed within the half hour, not at the next day's turn |
| `gateway/wrangler.jsonc` | `FRONTIER_MONTH_USD` (and `FRONTIER_MONTH_MAX_USD`), `TYPESAFE_PILOT_USD` | $607, $42 | The OpenAI month and Jev's lifetime allowance, aligned to metered plus the owner's funded balances: the month on Sept 24, 2026 ($394.46 metered + $213 funded; $408 before), Jev on Sept 23. Never above funded money. Deployed with `wrangler deploy`, not through the canary |
| | `COMPUTE_PROFIT_SHARE`, `EQUITY_BASELINE_USD`, `FRONTIER_MONTH_MAX_USD` | 0.3, $1,017.75, $408 | Compute follows profit (Sept 23, 2026, `gateway/lib/equity.mjs`): the month's cap is `FRONTIER_MONTH_USD` plus 0.3 of the real accounts' equity above the grant's capital, held to `FRONTIER_MONTH_MAX_USD`. That ceiling equals the funded month, so today profit is reported (`profit_index.earned_usd`) and buys nothing; raise it with each OpenAI top-up bought from profit. An unset share or baseline, or an unreadable or stale reading, gives exactly `FRONTIER_MONTH_USD`. The House's line mirrors the raise (`CampaignBudget.mirror_gateway_bonus`) |

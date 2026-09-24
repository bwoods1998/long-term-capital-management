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
   sealed holdout; survivors are born on paper.
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
  leaves unattended: a warning once per half hour for each round-the-clock desk (coins, Kalshi)
  with living members and no wake for 30 minutes while the House is NOT paused
  (`House._order_path_invariants`); and a warning once a day when an intent is refused for an agent
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
refuses on any of them, though a canary runs no lab; `league.watchdog status` shows them all.

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
  digest needs the ratify. The close-the-gaps run's Deploy B (Sept 24, 2026: the mechanism ledger's
  unit, the family swing with its entry looks, `swing_requires_proven_family`, `corrected_child_supersedes`) moves them to
  constitution `915c978e…`, money `c02ed852…` (the grant's 101 seats unchanged: the smallest real stake
  is still the $10 probe). Its Deploy A had set `8116302e…` / `521c4586…`; at that run's T0 they were `34adf385…` / `c2b0e09c…` (40 agents, a $25 stake line). Deploy A of the
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
    refusals (`wind down stopped`, from house.json `wind_down_refusals`);
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
  [--json | --markdown]`** (Sept 24, 2026): the scoreboard of
  [the close-the-gaps plan](goals/LTCM_CLOSE_THE_GAPS.md) (workstream Z), read-only and standard
  library only, from a snapshot of the House's stores rather than the live box. `--take` backs up
  `ledger.sqlite`, `lab.sqlite`, `campaigns.sqlite` and `feeds.sqlite` on the box into `/tmp`
  (sqlite's backup API, each source opened `mode=ro`), downloads them gzipped with `health.json`,
  `house.json` and `allocator-board.json`, and deletes the box copies; `--snapshot` reads a directory
  taken before. It prints the plan's seven metrics, each number with the function that computed it,
  then each desk's evidence clock (hours from a member's first fill to its third independent
  settlement), every family's pooled record (practice at weight 0.5, real at 1, one observation an
  event, a one-sided 80% Student's t bound) and the weather favourites' capacity. Its clock is the
  snapshot's newest ledger row; `--since` (default 24 hours before it) sets the window for deaths,
  the lab and supersessions, and `--baseline` counts promotions only from a moment (Deploy A). Every
  definition is in the script's docstring.
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
    `indexed`: the tapes built in the last six hours that a restart remembers).
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
    unavailable).
  - `background_jobs`, `durable_research` and `promotion_status`.
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
  - `seats` (Sept 23, 2026, the seat market): `waiters` by class (`graduates`, `retained`,
    `cards`, `strategies`) and `waiters_by_desk`; `reserved_desks` (desks a waiting graduate,
    retained candidate or card has first claim on); from the hourly watch, `displaceable`
    (residents an evidenced newcomer with no proof and no forward score could take now),
    `never_traded_past_grace`, `waiting_over_an_hour` and `at`; and `last_refused_birth` a class
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
  (`families`, `family_audits`).
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
    candidate of each trigger (`by_trigger`: which kind of evidence buys research that produces).
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
      `refused_at_birth`, `born`), its line, family and agent;
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
    `born_total`, `forward`) says why.
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
- **`ops.alert` warnings from the floor's invariants** (Sept 23, 2026; `House._floor_invariants`,
  every five minutes over the ledger rows since its saved cursor, `invariants` in `house.json`):
  `<desk>: offered markets on N wakes in the last hour ... and no agent of the desk wrote an intent`
  (once a desk an hour: its rules are not firing on what it is shown, a research pass is the answer)
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
- **"does not reconcile" on a paper book, by cents.** This is a warning, not an error (#108): it is
  the venue's end-of-day fee activity. An error means real money, or positions that disagree; read
  the `book.reconciled` rows.
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
| | `jev.enabled`, `jev.daily_usd`, `jev.daily_calls` | on, $0.25, 400 | The Jev floor: gate relevance, triage, hypothesis links, exposure |
| | `deep_replay`, `holdout_gate` | on | Deep Alpaca history for replay, and the sealed holdout before paper |
| | `options_history` | on | Options history, options replay, and IV/skew/activity features |
| | `research_traces` | on | Private research transcripts with their cost and outcome (for eventual fine-tuning) |
| | `lab.box_id`, `lab.box_key` | `sb_742fe765-…`, `lab` | The Alpha Lab's own Sailbox (`scripts/lab_box.py create`, size l, sealed). The service binds it under `box_key` and hands the lab that evaluator; without a `box_id` there is no lab (a name alone binds nothing). A terminated lab box is never replaced from the agents' image: the lab stops with the error alert "the Alpha Lab is stopped: its box is gone" and asks again hourly. Make a new box and set its id |
| `league/house.py` | `Settings.box_wait_seconds`, `probe_wait_seconds` | 2 s, 15 s | The tick never waits on background work (Sept 23, 2026): a wake whose box another caller holds waits this long, then is skipped and due again on the next tick; births wait this long for the probe box, then defer to the next tick (`health.json` `deferred`). Measured Sept 22: a probe takes about 20 s and a box's sleep up to about 17 s. The research thread's admission may wait up to 600 s for the probe box, since it never holds the tick's lock while it waits |
| | `EVIDENCE_CLOCK_DAYS`, `EVIDENCE_CLOCK_REFRESH_SECONDS`, `FORWARD_RULE_FILLS`, `House.RETAINED_TTL_SECONDS`, `WIND_DOWN_REFUSALS`, `WIND_DOWN_RETRY_SECONDS` | 7 d, 1 d, 3, 72 h, 3, 1 d | The seat market by evidence (S1-S4, Sept 24, 2026): the evidence clock's window and refresh (a paper seat's grace is the larger of 12 h and its desk's clock); the fills after which a trader goes only to a newcomer with a better forward record; how long a dead author's retained candidate waits for a seat (and how far back the first pickup reaches); the identical refusals of a House-sent sale before its retries stop, and how long until it is tried again. Constants in `league/house.py`: an update or owner deploy changes them |
| | `Settings.enroll_displaces` | on | A merged strategy takes a seat in a full league, repairs first: from an agent still running the code it corrects, else from the weakest eligible resident. A born corrected child retires the agents off real money still running that code (`superseded`). Off: merged strategies wait for an empty seat |
| `league/game.json` | `audit.house_pays` | on | The House pays for promotion audits. Off: the agent pays at cost, and one under `audit.min_credits_usd` ($0.60) waits at `audit_credits` |
| | `research.gate.enabled`, `after`, `max_factor`, `sample_percent` | on, 2, 8, 10 | Back off research whose passes come back empty while nothing about the agent has changed; a 10% sample still runs. The routine epoch payout is not a trigger (Sept 23, 2026) |
| | `research.gate.clock_runs`, `abstain_lock_after` | `winners_and_idle`, 3 | Research runs on evidence, not the clock (Sept 23, 2026: 90.3% of 7,532 sessions abstained, $112.80 of $147.44, 41% of runs were `clock`/`backoff_elapsed`). A session is due only on a trigger (fill, settlement, refusal, active block, audit or repair verdict, code or rung change, a lesson or note for its desk, a fulfilled request, a lifted blocker); a winner (positive earned record) and an idle agent still run on the clock; the 24 h heartbeat and the sample stay. After 3 abstaining sessions in a row only a settlement, a fill or a refusal wakes the agent until a session produces a candidate. `all` / 0 restore the Sept 22 rule. Every `research.gate` row carries `trigger` and `record`; `python -m league.research_gate LEDGER` prices each trigger (`by_trigger`) |
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
| | `merton.paused_until_profit` | architect, toolsmith, operator, designer | L2, Sept 24, 2026: these roles do not sit down while the floor's 24-hour REAL P&L -- the realized result of the real books' settlements and closing fills over the last 24 hours (`merton.RealPnl`; not the allocator's `floor_pnl`, a level since the books began with no 24-hour window) -- is not positive; one `ops.budget` "merton pause" row when a role pauses or resumes. Lifetime to Sept 24 those roles and the teacher had spent about $120 for about one positive forward record. Bounds: any subset of `merton_bounds.paused_until_profit` (Merton's five roles). The auditor, the consultant and the engineer are not scheduled here |
| | `merton.schedule_hours.teacher` | 12 | The teacher's cadence (6 until Sept 24, 2026), bounded 6-24 h by `merton_bounds` (`economy.check_bounds`, so `league.ci`). The burst no longer accelerates it |
| | `economy.line_exhausted_trials`, `explore_every` | 15, 5 | Retire lines with 15 failed trials and no pass; one birth in five explores |
| | `economy.losing_family_min_blocks`, `seat_waiters_warning` | 6, 8 | The seat market (Sept 23, 2026): no House mutation, parameter fork or revival of a family whose pooled forward record is negative after this many active blocks (an info alert an hour a family); a warning when more than this many newcomers have waited for seats over an hour |
| `league/constitution.py` | `allocator.corrected_child_supersedes` | on (Deploy B) | L1 (Sept 24, 2026): a research child that passed replay with a fix to its real-money parent's entry mechanism (liquidity, fee, side, borne out by the parent's own entry fills) supersedes the parent at once, demoted from real money through the evaluator and retired `superseded` (`House._supersede_by_research`). The account must be of the parent's CURRENT program and a liquidity or fee fix must rest its entries post-only (review of #245: the child meriwether-h2d625d-2 fixed its own moneyline file, not its parent's KXMLBTOTAL entries); a parent whose family's pooled taker record is proven positive (`Allocator.family_taker`, as X0 reads it) is not superseded for a liquidity or fee fix. Absent or false: only merged repairs supersede (`_retire_superseded`). A money rule: re-ratify after a change |
| `league/constitution.py` | `allocator.enabled` | on | Capital is the ladder (Sept 23, 2026, `league/allocator.py`): bands and stakes follow evidence at every mark pass. Off: the screen, the micro bound, `micro_demotion` and Kelly sizing below decide again (the rollback). A money rule: re-ratify after either change |
| `league/shards.py` | `FLOOR_USD`, `TOP_UP_USD`, `KEEP_USD`, `MAX_MOVE_USD`, `MAX_DAY_USD` | $20, $30, $60, $100, $200 | The Kalshi shard funder (Sept 23, 2026): a wanted shard under the floor is topped up from the richest other shard that keeps its floor (shard 0 keeps $60) and the stakes of the desks on it; at most $100 a move and $200 a rolling day, counted from the ledger. Constants in a protected file: an owner deploy changes them |
| | `allocator.evidence` `paper_weight`, `alpaca_paper_haircut_bps` | 0.5; crypto 4, equity 2, option 24 | E = W_paper^paper_weight × W_real; Alpaca paper fills haircut per side of filled notional at the rate of the fill's asset class (A8, Sept 23, 2026 ~22:00 UTC: each class's practice optimism against the order's reference at intent time, the larger of the notional-weighted mean and the round-trip reading, rounded up, never below 2; `docs/research/queries/2026-09-23/A8-haircut.py`). Options tightened from 10, crypto and stocks loosened to what was measured. A plain number charges every class (the rollback); a class not named pays the table's largest rate |
| | `allocator` `bunt_at`, `bunt_min_trades`, `bunt_min_settled` | 1.01, 5, 3 | Paper → bunt: E at the line and 5 closed paper trades, or 3 settlements on Kalshi (plan default 1.03; set from the Sept 23 06:45 UTC distribution, bounds 1.0-1.25) |
| | `allocator.bunt_usd` | Kalshi $30, Alpaca $25 | A PROVEN family's bunt (since Sept 24, 2026; plan default Alpaca $15: untradeable under the book's 50%-of-equity order rule and Alpaca's $10 crypto minimum). Kalshi $10 → $30 on Sept 23, 2026 ~17:00 UTC: a $10 bunt was a one-loss trial (any lost $5 position over $1.54 crossed the hysteresis line) |
| | `allocator.probe_bunt_usd` | Kalshi $10, Alpaca $25 | An UNPROVEN family's first real stake (P1, Sept 24, 2026; table Kalshi $5-15, Alpaca $20-25): the nine promotions of Sept 23-24 all ran unproven mechanisms and settled -$18.62. A probe becomes a bunt the pass after its family is proven and back when the bound falls (free cash only). An options probe is still $80. The grant's seats follow the smallest real stake: floor($1,017.75 / $10) = 101 (40 at $25) |
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
| (none) | the hourly yield row | every hour | `league/yield_ledger.py` writes one `ops.budget` row (`what: "yield"`) an hour, on the foundry's bookkeeping tick: spend by line (research tokens, each of Merton's roles, audits) and the evidence each line produced (sessions, abstentions, candidates, replay passes, active and positive forward blocks, cards, proposals, lessons, consult answers and failures), with `usd_per` unit, and since Sept 24, 2026 `by_profile`: research sessions, candidates, provider failures, token dollars and `candidates_per_usd` for each model profile. Read it with `sqlite3 ... "select payload from ledger where kind='ops.budget' and payload like '%\"what\":\"yield\"%' order by seq desc limit 3"` or from `scripts/floor_watch.py` |
| `league/research_routes.json` | `cache.layout`, `cache.explicit_hints` | `messages`, on | The Luna cache layout; `packet` is the old layout |
| | `routing.sail_by_evidence` | off | Let measured evidence move new Sail sessions to a cheaper tier |
| `league/turbo.json` | `research_minutes`, `research_workers`, `replay_workers` | 15, 16, 12 | The funded burst's research interval and workers (5, 32 and 8 until Sept 23, 2026). In force while the burst is, which it is while the live grant is active |
| | `max_population`, `newcomer_seconds`, `endowment_usd` | 112, 600 s, $8 | The burst's population ceiling (64 until Sept 23, 2026, when foundry cards that passed replay waited for seats; 96 until the seat market of Sept 23, when 20 lab graduates, 6 replay-passed cards and 6 merged strategies waited: 16 more boxes cost about $0.43 a day of Sail, 2.9 days of runway), the House mutation cadence (120 s until then; no mutation is staked while any waiter waits) and House endowment |
| | `fork_threshold_usd` | $10 | The credits an agent needs before it may fork a parameter copy of itself. Above the endowment, so only an agent that has earned payouts forks. Until Sept 23, 2026 the burst forced $2, every newborn forked at once (22 copies in 40 minutes), and the foundry's replay-passing cards waited for seats on full desks |
| | `merton_schedule_hours` | operator 48, designer 96, toolsmith 48, architect 24, teacher 12 | Merton's burst cadence, set by each role's measured yield. Until Sept 24, 2026 `load_turbo` dropped this key, so it never reached the House and the burst's own defaults ran (operator 0.25 h, toolsmith and architect 0.5 h, teacher and designer 1 h, stretched by backoff): the ledger shows the teacher about hourly and the architect every 30-60 minutes on Sept 23. The teacher is bounded 6-24 h (`TURBO_MERTON_HOURS`) |
| | `sail_research_usd_per_hour` | $2 | L2, Sept 24, 2026: no NEW research session starts on Sail while the settled cost of the Sail commitments created in the last hour (`campaigns.sqlite`; every Sail call is research) has reached it; a session under way resumes, a job still queued for a research worker waits like a new session, and Luna is not capped. A call in flight counts once it settles, so the hour can overshoot by what is in flight. One `ops.budget` "sail research cap" row when it closes or opens; `health.json` `research_economy.sail_cap` shows it. Bounds $1-4 (`TURBO_RANGES`). Sail settled $5-6.5 an hour on Sept 23 at 19-23Z and $1.27 in the hour before T0 |
| | `luna_fraction` | 0.95 | The share of agents whose research runs on GPT-6 Luna; the rest stay on Sail as the comparison (a Luna session cost about $0.011 against about $0.06 on Sail, Sept 23, 2026) |
| `league/niches.json` | `max_members` | Kalshi: crypto strikes 4, crypto 15-minute 10, weather 14, sports 16, props 4, prices 8, attention 4. Alpaca: crypto majors and alts 12, index ETFs 14, megacaps 12, options 8 | How many agents a desk may hold. Set Sept 23, 2026 so seats follow evidence: up where lab graduates wait (weather, the one desk with a positive forward record, sports, index ETFs, 15-minute crypto), down on the graveyards (strikes: 40 born, 2 passed replay; props 34 and 5; attention 34 and 2). Every desk keeps one seat for a member that trades (`House._mutation_room`) |
| | `open`, `asset_classes`, `exclude_patterns` | `kalshi-open` and `alpaca-open` (8 seats each); Alpaca `equity`, `crypto`; Kalshi `^KXMVE` | The open desks (Sept 23, 2026): a desk whose universe is every tradable market of its venue. `status: dormant` closes one. `niches.OPEN_DISCOVERY` (24) is the length of an open desk's discovery list, of which a strategy naming nothing it may trade is shown the first twelve (`MAX_UNIVERSE`); a Kalshi desk missing from the last survey is surveyed within the half hour, not at the next day's turn |
| `gateway/wrangler.jsonc` | `FRONTIER_MONTH_USD` (and `FRONTIER_MONTH_MAX_USD`), `TYPESAFE_PILOT_USD` | $607, $42 | The OpenAI month and Jev's lifetime allowance, aligned to metered plus the owner's funded balances: the month on Sept 24, 2026 ($394.46 metered + $213 funded; $408 before), Jev on Sept 23. Never above funded money. Deployed with `wrangler deploy`, not through the canary |
| | `COMPUTE_PROFIT_SHARE`, `EQUITY_BASELINE_USD`, `FRONTIER_MONTH_MAX_USD` | 0.3, $1,017.75, $408 | Compute follows profit (Sept 23, 2026, `gateway/lib/equity.mjs`): the month's cap is `FRONTIER_MONTH_USD` plus 0.3 of the real accounts' equity above the grant's capital, held to `FRONTIER_MONTH_MAX_USD`. That ceiling equals the funded month, so today profit is reported (`profit_index.earned_usd`) and buys nothing; raise it with each OpenAI top-up bought from profit. An unset share or baseline, or an unreadable or stale reading, gives exactly `FRONTIER_MONTH_USD`. The House's line mirrors the raise (`CampaignBudget.mirror_gateway_bonus`) |

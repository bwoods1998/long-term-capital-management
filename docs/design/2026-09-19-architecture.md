# The rebuild: architecture, as built (Sept 19 to 20, 2026)

Companion to `docs/proposals/2026-09-19-the-game.md`. This file was the plan for the overnight
build of Sept 19 to 20; it has been revised into a description of what was built, and every
place the build departed from the plan is listed with its reason in
[Built differently from the first plan, and why](#built-differently-from-the-first-plan-and-why).
The builder's log, with each decision as it was made, is
`docs/runs/2026-09-20-overnight-build.md`. How to run it: `league/README.md` and
`docs/runbook-go-live.md`.

Owner's decisions: venues are Kalshi and Alpaca; Sail budget $100 a month and OpenAI budget $100 a
month, each raised only on measured return; the frontier model is auditor, architect and the
other pull-request roles, never the trade picker; the loop runs with no human in it, inside
bounds no model can move.

## Trust boundaries

| Zone | Runs | May do | May never do |
|---|---|---|---|
| **Gateway** (Cloudflare Worker, `gateway/`) | venue keys (Kalshi, Alpaca real and paper), OpenAI key, GitHub token, order caps, frontier budget, pull-request cap, kill switch, the external watchdog | sign orders, meter spend, open a pull request, resume and restart the House box | be changed by anything on Sail; merge, approve or push |
| **House** (one Sailbox, trusted, `python3 -m league run`) | ledger, books, evaluator, economy, researcher loop, publisher, in-box release watchdog | decide promotion, death and budgets; send netted orders to the gateway; drive each agent's box over Sail's exec API; make every model call and web search on an agent's behalf | run agent-written code in its own process; hold a venue key, the OpenAI key or the GitHub token |
| **Agents** (one Sailbox each, untrusted) | a strategy program, run by `runner.py` or `replay.py` | return plain data (intents, cancels, a thought, a memory) on stdout when the House runs them | hold **any** credential; reach the House, a venue, the gateway or any host at all; write the ledger |
| **Merton** (frontier model, via gateway) | reads the evidence the House gathers for its role | audit a candidate (a veto); propose a pull request inside one role's paths | pick a trade; touch the constitution, ledger, book, evaluator, statistics, auditor, watchdog, CI, gateway or workflows; merge |
| **GitHub CI** (`.github/workflows/merton.yml`) | the path guard, content checks, the replay regression and the whole league suite | squash-merge a green `merton/…` pull request | be rewritten by the branch it judges (`pull_request_target` runs `main`'s copy) |

The House box holds exactly three secrets, in a mode-600 `.env`: `GATEWAY_TOKEN`, `SAIL_API_KEY`
and `CAPITAL_PUBLISH_TOKEN`. An agent's box is a fork of a clean image, sealed before it is ever
used with an egress allowlist of one host that never resolves (`sealed.invalid`; Sail refuses an
empty allowlist), so DNS fails inside it. Death is the House ceasing to wake the agent, winding
down its positions, writing its post-mortem to the ledger and the playbook, and terminating its
box.

`league/constitution.py` holds what no model and no code path on Sail may change: the two
budgets, the order caps ($75 an order, $4,000 and 2,000 orders a day), and every statistical
threshold of the ladder. CI and the gateway both refuse any pull request that touches it, its
digest is pinned by a test, and the House writes the digest to the ledger every time it starts.
The caps, the OpenAI budget and the kill switch are *enforced* in the gateway; the Sail budget is
enforced by the House's own meter, because Sail has no spend caps.

## House modules (package `league/`, reusing the first run's tested parts)

The ledger and the money:

- `league/ledger.py`: one append-only, hash-chained SQLite record of every intent, order, fill,
  mark, credit move, trial and verdict. UPDATE and DELETE are refused by triggers; ids are
  idempotent; `verify()` recomputes the chain. Agents are given `agent_view()` rows, never a handle.
- `league/book.py`: one netting book per venue account. Runs every intent through the first run's
  risk engine (`ltcm/risk.py`, all 21 rules, unchanged) plus the league's rules, nets a batch's
  market orders, attributes venue fills back pro rata, and reconciles to the venue against a
  baseline.
- `league/fees.py`: what a fill costs as each venue was *measured* to charge it.
- `league/venues.py`: the real adapters (`ltcm/adapters`) in gateway mode, for `kalshi`, `alpaca`
  and `alpaca-paper`.
- `league/paper.py`: the Kalshi shadow account, a `Broker` over live Kalshi quotes with
  conservative maker rules. (Alpaca's paper account needs no module: it is the real adapter
  through the gateway's `alpaca-paper` venue.)
- `league/sim.py`: a simulated Alpaca account that behaves as the paper venue was measured to,
  for canary Houses, which must never trade on the shared paper account.
- `league/capital.py`: rung 3 sizing (a quarter of Kelly on the lower bound, clamped) and the
  standing capital recommendation for the owner.

The ladder:

- `league/constitution.py`: the pre-registered numbers.
- `league/stats.py`: log growth, one-sided t bounds, alpha spending across looks, the exact
  (Clopper-Pearson) loss-rate bound for lopsided records, the deflated Sharpe ratio, quarter
  Kelly, the CUSUM drift alarm. Pure, standard library only.
- `league/evaluator.py`: the four rungs. Replay with every run counted as a trial against the
  family (rung 0), paper forward test (rung 1), micro-real at $1 to $10 a position (rung 2),
  scaled (rung 3). Promotion and death are sequential tests on a confidence bound of after-cost
  log growth, in hour or day blocks; drift demotes. It reads the ledger and writes `eval.*` rows;
  the House acts on its verdicts.
- `league/replay.py`: the mechanical replay simulator, self-contained so it ships into the
  agent's box as it is.
- `league/tapes.py`: recorded history for replay and live snapshots of the same shape, for both
  venues. Alpaca tapes are 21 days of hour blocks or 126 of day blocks; Kalshi tapes a week
  (hourly strategies) or seven weeks (daily).

The agents:

- `league/agents.py`: identity, strategy, lineage and fate, folded from the ledger.
- `league/sandbox.py`: one sealed Sailbox per agent, driven over Sail's exec API (resume, upload,
  run, read one token-marked line, sleep). `LocalSandbox` is for tests and is refused for real money.
- `league/runner.py`: runs one `decide` inside the agent's box. Self-contained.
- `league/safety.py`: what a strategy file may contain (an import allowlist, no underscore
  attributes, no attribute assignment, no `eval`/`exec`/`open`), ported unchanged from the first
  run's Foundry. The contract a strategy follows is `league/CONTRACT.md`.
- `league/seeds/`: the twelve founding programs (four Kalshi, four Alpaca crypto, four Alpaca
  equities).
- `league/niches.py`, `league/niches.json`: the specialties. Every agent belongs to one for life;
  the 26 founders are the seeds' programs pointed at them; a Kalshi universe follows the season
  through a daily survey of the venue.
- `league/strategies/`, `league/tools/`, `league/playbook/`: what Merton adds by pull request as
  architect, toolsmith and teacher. `strategies/registry.json` lists what the House should spawn.

The economy:

- `league/economy.py`: compute credits. Income is a share of the daily pool (`game.json`: $2.00 a
  day, 40% of it niche floors, the rest by evidence-weighted performance); costs are metered
  model tokens, sandbox seconds, web searches and frontier audits at cost. Zero is death; a rich
  agent may fork and must endow the child.
- `league/researcher.py`: a cheap Sail model thinking on one agent's behalf, at that agent's
  expense. The House runs the loop and executes every tool call.
- `league/commons.py`: web search, the shared research library, the tool-request queue and the
  playbook (the graveyard's lessons).
- `league/rules.py`: what every agent is told, generated from the constitution and `game.json`
  so it cannot drift from what is enforced.
- `league/budget.py`: the Sail month, metered from falls in Sail's credit balance.
- `league/game.json` and `league/config.json`: the tunable dials (Merton may propose changes
  inside `bounds`) and where the House finds things. `"real_money": true` is a line only the
  owner changes.

The frontier model and change control:

- `league/frontier.py`: the client for the gateway's `/v1/frontier/responses`.
- `league/auditor.py`: the veto before real money, charged to the agent; every veto is scored
  afterwards as if it had been taken.
- `league/merton.py`: the five pull-request roles (architect, toolsmith, operator, game designer,
  teacher) and the forge that opens the pull request through the gateway.
- `league/ci.py`: the judge. Path guard, content checks, the replay regression and the whole
  suite. It asks no model anything.
- `league/watchdog.py`: the in-box release watchdog: stage, canary, promote, watch, roll back.
- `league/updater.py`: every half hour the House box downloads `main` (the repository is public,
  so no credential), runs the current release's content checks on it, refuses any change to
  `real_money`, and hands a changed tree to the watchdog.

The process:

- `league/house.py`: the one trusted process and its `tick()`: settle and poll, wake due agents,
  net and send, mark, reconcile, judge, research, pay, publish. Replays, research, Merton and
  updates run beside the tick, never inside it.
- `league/publish.py`: the public tape the site's five sections are drawn from, cleaned to the
  site's own schema.
- `league/service.py` and `league/__main__.py`: build the real House from the config and the
  environment; `run`, `tick`, `found`, `status`, `verify`, `stop`, `start`.

## The frontier model

The owner's choice is the best model available: `gpt-6-astra` for every frontier job (confirmed
reachable with the project's key on Sept 19, 2026). Metered prices are $12.50 per million input
tokens (the cache-write rate, so the meter errs high), $1.00 cached, $50 output. The gateway
reserves each call at its worst case and settles it at the provider's reported usage.

Measured on the night of the build, against what the plan assumed:

| Call | Plan assumed | Measured |
|---|---|---|
| Audit of one candidate | about $0.30 (8k in, 4k out) | **$0.23** (a veto with four blockers; a first attempt cost $0.07 more) |
| Architect pass | about $1.25 (50k in, 12k out) | **$0.10** (it declined to write a strategy, with reasons; a pass that writes code costs more, and cannot exceed about $1.25 at its 12,000-token output limit) |
| Toolsmith pass | not planned | **$0.06** (it answered that all three requests needed data, not tools) |

The roles run on fixed clocks: operator and toolsmith daily, teacher every three days, designer
and architect weekly; an agent is audited at most once every 72 hours and pays for it from its
own credits. The operator, designer and teacher passes were not measured; they are limited to
5,000 output tokens against the architect's 12,000. If each cost what an architect pass did, all
five roles together would come to about $7 a month, which leaves the $100 month room for some
four hundred audits, far more than the ladder will send to real money. Spend is attributed per
agent and per role in `/v1/health`, and each job's budget follows its measured return.

## What was built

The plan's six steps, in the order they were finished. Each shipped with its tests, and the live
checks are in the build log.

1. **Ledger, book, gateway-mode adapters for both venues, the old risk rules.** Verified against
   the real Alpaca paper account through the gateway: two agents, netted buys, an internal cross,
   everything closed, the book reconciled to the venue after every stage with differences under
   a cent.
2. **Evaluator rungs 0 and 1**: statistics, the replay simulator, tapes for both venues, the
   Kalshi shadow venue, the constitution.
3. **Economy and agent lifecycle on Sail**: credits, the registry, sealed sandboxes, the
   researcher, the commons, the rules text, the twelve seeds, the House loop, the Sail budget.
4. **Rung 2 behind the auditor, and the publisher.** The auditor vetoed a deliberately bad
   candidate live; the publisher's output passes the site's own validators and was shown on a
   test tape. No real-money order was placed during the build.
5. **Merton's five pull-request roles, CI, the canary and the in-box watchdog.** Proven live on
   GitHub: a strategy importing `os` refused by the `judge` job, a designer branch editing the
   constitution refused by the `guard` job, a lesson merged by the `merge` job with no human step.
6. **Rung 3 sizing, drift monitors, the standing capital recommendation**, and a whole-ladder
   test, which found two real defects (a one-step crumb of BTC the venue still showed froze the
   book; sweeping a promoted agent's paper account read as a 100% daily loss and tripped the
   floor breaker). Both fixed: stake flows no longer count as profit or loss in the breakers.

An adversarial test pass against the evaluator, sandbox, runner, auditor and frontier client found
18 defects, all fixed. The ones that mattered most: a box was recorded before it was sealed (now
sealed first, destroyed if it cannot be); failed replays did not raise the family's trial count
(now every replay does); the audit read the string "false" as approval.

Not yet done: the first run's unused code (`ltcm/` desks, committee, evolution, Foundry, lab,
mind, service) is kept, not removed, because removing it safely is a job of its own; and the
owner has still to place `GITHUB_TOKEN` in the gateway before Merton's five roles can open pull
requests unattended (until then each pass is recorded with `forge_error: GitHub is not
configured`).

## Built differently from the first plan, and why

1. **Agents hold zero credentials, not a House token, and the House has no ingress.** The plan
   gave each agent a House token and a network allowlist of the House and public data hosts.
   Instead the House drives each agent's box over Sail's exec API (resume, run `decide`, read
   stdout, sleep), builds the market snapshot itself and passes it in as data, and runs the
   researcher model and every tool on the agent's behalf. Nothing in an agent's box can reach
   anything. *Why:* it is inside the constitution's bound ("no credential except a House token"),
   stricter than it, and it removes the need for any ingress to the House.
2. **Death is the House's act, not `max_lifetime_seconds` and a refused token.** There is no
   token to refuse. The House stops waking the agent, winds down its positions and terminates
   its box. *Why:* follows from 1.
3. **The ledger is one chain in `league/ledger.py`, not a reuse of `ltcm/events.py`.** It copies
   that module's mechanics (canonical JSON, a digest over the previous digest, UPDATE/DELETE
   triggers, idempotent ids) with the league's own kinds and an `agent` column. *Why:* one chain
   gives a total order that a reconciliation can pin (`ledger_seq`, `ledger_digest`); the first
   run's store kept one chain per stream.
4. **The whole risk engine of the first run is reused unchanged, plus league rules.** The plan
   said "reuses `ltcm/gateway.py` risk rules". The book builds a `RiskContext` from its own state
   and runs all 21 rules of `ltcm/risk.py`, then adds the $75 order cap, per-rung position and
   order caps, no leverage to the cent (fees and a market order's slippage included), no shorts,
   a quote-age limit, and no order that could trade against the House's own resting order.
   *Why:* `ltcm/risk.py` is pure and duck-typed on the manifest, and it carries the first run's
   hard-won event rules.
5. **The netting rule.** The plan said only "intents are netted". Built: market orders of one
   batch on one instrument are netted, and the minority side is crossed inside the House, priced
   as the venue would have priced it (the buyer pays the ask, the seller receives the bid, both
   pay the taker fee), so each agent is scored exactly as if it had traded alone; what the
   account did not actually pay accrues to the House row, which keeps the books summing to the
   venue. Limit orders are never pooled: one venue order per intent, so no apportioning. An
   intent that could execute against a House resting order is **refused rather than
   cancel-and-crossed**. *Why:* simpler, and never a wash trade; the cost is that a refused agent
   loses that fill.
6. **One account never holds both legs of a Kalshi market.** The book refuses an opening buy on
   a leg whose opposite leg the House holds or bids. *Why:* Kalshi nets YES against NO and pays
   the pair out early, which would stop per-agent legs summing to the venue.
7. **Reconciliation is against a baseline, with dust rules.** The paper account holds $100,000
   that is not the book's and the real accounts hold unallocated cash, so each book records once
   what the venue held at opening (the House takes every baseline at start, before anything can
   trade); afterwards venue cash must equal the baseline plus the book's own cash, to the cent,
   and each position the baseline's plus the agents'. Under a cent for each venue fill since the
   last check is booked to the House row as dust; more freezes new entries but never exits.
   Two measured Alpaca facts are built in: fills are booked at the taker's 0.25% and a maker's
   difference comes back through reconciliation (Alpaca reports no fee and accepts every order
   asynchronously), and the cash behind a resting crypto bid is added back before comparing
   (Alpaca takes it out of `cash`).
8. **Founders start on paper.** The plan had every agent pass replay first. The twelve founding
   seeds are seated on rung 1 at birth; their replay still runs and still counts as their
   family's first trial. Everything born later (forks, mutations, Merton's strategies) must pass
   replay first. *Why:* the first dry run showed honest replays failing most seeds (crypto
   reversion Sharpe below zero after fees; Kalshi favourites at a deflated Sharpe of 0.85 against
   the 0.90 line). Paper costs nothing, and forward evidence is what counts.
9. **Niche floors are paid only to qualified agents, and there is a qualification deadline.** A
   niche is occupied only by agents on rung 1 and up, and a rung-0 agent that has not passed
   replay within three epochs of its birth is retired. *Why:* a floor for an agent that does
   nothing would pay for squatting on a population slot.
10. **The loss-rate gate is exact (Clopper-Pearson), not Wilson.** *Why:* the one-sided Wilson
    bound was measured at 92 to 94% coverage for clean records where it claims 95%. A record of
    clean +0.5% wins risking 7% now needs 46 of them, not 40. (`wilson_upper` is kept in
    `stats.py` for reference only.)
11. **Drift is measured on the edge per closed trade, not on block growth.** Each recent block is
    one observation: the mean edge of the trades it closed (what each made over what its units
    had cost, fees in), in units of its own standard error against the per-trade record of the
    rung below; a one-sided CUSUM with k = 0.5 and h = 6 raises the alarm. *Why:* the same
    strategy has about a fifth of its stake at work on paper and a third on the micro-real rung,
    so growth per block differs by rung and would read as drift; a first attempt normalised block
    growth by sampled exposure and still demoted a healthy agent in the whole-ladder test, and
    h = 4 would false-alarm about weekly on hourly blocks. An edge per trade is scale-free, and
    real fills that are worse than the paper fills that earned rung 2 are exactly the fall it is
    there to catch. Block growth per unit of exposure remains the fallback when a stay has no
    trade-by-trade record.
12. **Merton has five pull-request roles, not one architect.** The plan had `league/architect.py`
    opening changes to `strategies/` only. Built: architect (`league/strategies/`), toolsmith
    (`league/tools/`, tool tests), operator (`league/config.json`), game designer
    (`league/game.json`, inside its bounds) and teacher (`league/playbook/`), in `league/merton.py`.
    Pull requests go **through a gateway GitHub route** (`POST /v1/github/pr`), which holds the
    token like every other credential and enforces each role's paths outside Sail. They are
    **judged by a `pull_request_target` workflow**, run from `main`'s copy so a branch cannot
    rewrite its judge, and **merged only when green**, by a job that never runs the branch's
    code. *Why:* the owner approved the extra roles, and a GitHub token on Sail would have been
    the one credential that could change the rules.
13. **A canary with a simulated paper venue, and an in-box release watchdog.** A release is
    staged, run as a whole House for a few ticks on throwaway state, promoted, watched, and
    rolled back on the first bad health reading after a grace of two. The canary trades on
    `league/sim.py`, not on the shared Alpaca paper account. *Why:* the real House reconciles that
    account to the cent, and a second trader on it would break the reconciliation within one
    fill. The gateway's external watchdog is unchanged and does a different job: it keeps the box
    alive; the in-box one only chooses which release runs.
14. **Merged code reaches the House by itself** (`league/updater.py`), which the plan did not
    describe: `main` is pulled every half hour, checked, and handed to the watchdog. It may never
    change `real_money`.
15. **The evaluator does not reuse `ltcm/backtest.py` or `ltcm/evidence.py`.** `league/replay.py`
    and `league/stats.py` are new. *Why:* the simulator runs inside the agent's sealed box, so it
    must be one self-contained file on the standard library; and the statistics move real money,
    so they are small, pure and tested on their own.
16. **Web search is Sail's search API**, with Google News RSS as the fallback. The House runs
    the search and charges the agent a conservative $0.01 a query. *Why:* it was found working
    with the project's key, and Sail publishes no price for it.
17. **The Sail budget is metered from balance falls.** The House reads Sail's credit balance and
    counts a month's spend as the sum of the falls between readings (a top-up is a rise, not a
    fall). At $100 in the month, or at the $10 reserve that keeps the House's own box alive,
    research and practice stop; only agents holding real-money positions are still woken, so they
    can exit. *Why:* Sail has no spend caps at any level, so there is no enforcement point there.
18. **Per-agent cost attribution is the House's own meter, not one Sail API key per agent.** The
    plan was a key per agent, attributed by Sail's `/v2/usage/api-keys`, with sandbox seconds from
    `/sailboxes/spend`. Built: every model call is charged to the agent that caused it from the
    settled cost of that one request (`ltcm/provider.py` computes it from the usage Sail returns),
    and sandbox seconds are charged from the House's own timing of each run at `game.json`'s box
    rate; each is a `credit.charge` row on the ledger. *Why:* the House makes every model call
    itself on the agent's behalf, so its own ledger rows *are* the attribution, already per
    agent and per request, and no agent box ever needs a Sail key. The overnight goal allowed
    "one Sail API key or equivalent attribution per agent"; this is the equivalent.
19. **Replays and research run beside the tick, never inside it.** *Why:* the first real tick took
    six minutes because a Kalshi tape build and a flex-window model call ran inline.
20. **Kalshi replay tapes are a week (hourly) and seven weeks (daily), not a day.** *Why:* the dry
    run's own agents diagnosed the one-day tape and filed tool requests; Merton's toolsmith
    correctly answered that this needed data, not a tool, so the House was changed.
21. **The site got a test tape** (`/api/capital/t/test/…`, viewed at `/capital/?tape=test`): the
    same Durable Object class under another name, allow-listed to `test` and `canary`. *Why:* the
    production tape stays empty until go-live, which also keeps the gateway's external watchdog
    from resuming or restarting the box, since it acts only on a published production checkpoint
    (it still mails: see `gateway/README.md`).
22. **The paper gate is a screen with a dollar cap, not a confidence bound** (the owner's decision,
    Sept 19). The plan used the same bound at both real-money gates. Built: paper to micro-real
    needs 15 active blocks, 10 closed trades, growth above zero, a drawdown under 15% and the
    audit; the micro rung's loss is capped by the constitution's `tuition` (4 agents at once, $50
    net, the seated agents' possible losses budgeted before they happen, and at the line everyone
    on the rung returns to paper). *Why:* run with the ladder's own code, the one edge the first
    run measured had a 0% chance of reaching real money in a month and an excellent crypto edge
    11% in a week; a small edge needs about a thousand trades to prove by any honest test, and the
    strict test was guarding a $25 stake. The strict bound stays between micro-real and scaled.
23. **Promotion and death spend separate alpha.** They shared one series, and the looks at 20 and
    25 active blocks, where promotion is impossible, spent 76% of it. *Why:* they are errors in
    opposite directions; each is still bounded at 5% over all looks.
24. **A family's pooled real-money record can carry a member to the scaled rung**, and sizes it
    while its own bound is not above zero (on its own variance). One series, the mean growth of
    the family's rung-2 agents block by block, with its own alpha and looks; the member's own
    growth must be above zero. *Why:* the first run's favourites edge was only ever measurable pooled.
25. **The horizon rule**: Kalshi entries must be expected to pay within 12 hours (hourly agents)
    or 48 (daily); crypto positions are closed after 48 hours; equities and options are not
    bounded (the owner's decision). Markets are shown and judged by their scheduled expiration,
    because a game lists a close two days after kickoff (before this, no NFL, college, MLB or
    soccer game was visible to any agent).
26. **Specialists** (the owner's design): every agent belongs to one niche of `league/niches.json`
    for life. The plan's niches were venue x horizon x style labels an agent gave itself. Built:
    eleven open specialties and one dormant (options), with universes from a live survey of the
    venue, briefs of what is measured there, 26 founders, a daily survey so a universe follows
    the season, and one broad sports niche rather than one per sport. *Why:* a small research
    budget spent in one place compounds; spread over everything it learns nothing.
27. **The replay charges Kalshi makers where the series does.** *Why:* found by replaying a sports
    founder over a real week: the big leagues' game series charge a maker fee and the replay
    charged none. The same replay showed a bid left resting during a match being picked off when
    a goal is scored (38 wins, 7 losses at 93 cents), so sports founders enter before the start only.
28. **Listed options, long premium only** (the owner asked for level 3; the House uses less than
    the account allows). The gateway refuses multi-leg orders, market orders and anything but
    `buy_to_open` / `sell_to_close`, and prices a contract at 100 shares (it was pricing one at a
    hundredth of its cost). *Why not spreads:* a short leg can be assigned early into a hundred
    shares the account cannot carry, the book's accounts have never held a negative position, and
    none of it could be tried against an open market before the run began. The micro rung's
    constitution gains `option_max_position_usd` ($20): one contract cannot be cut smaller. Paper
    is the specialty's replay (`replay: false`): there are no recorded chains to walk.
29. **Venue fees are read from the venue, not estimated.** A cash shortfall at reconciliation is
    first explained by Alpaca's FEE activities (end-of-day regulatory fees, which no fill shows);
    only what they do not explain freezes the book. *Why:* a one-cent fee after any equity sale
    would otherwise have frozen the real Alpaca book on its first evening.
30. **The expedition** (the owner's decision): `budgets.expedition` in the constitution and
    `league/pacer.py`. The plan was a $2-a-day pool and monthly caps; built is a daily allowance
    from what is left over the days that are left, which the pool, research and Merton follow, with
    the unearned performance share paid to the floors. The Sail reserve is $5, not $10.
31. **An agent's persistent memory is a journal on the ledger**, inherited by its children, and a
    research pass can see the live view and gets a digest of where a replay won and lost. *Why:*
    a pass used to start from nothing but the agent's code and standing, and a replay said only
    pass or fail; the diagnosis that mattered most on the first day (resting bids picked off
    during matches) took a human reading the fill log.
32. **The House stakes a research candidate that passes replay** when its parent cannot afford the
    endowment (one a parent a day). *Why:* the first real research pass on a founder said it in so
    many words: above rung 0 it cannot edit itself and a fork costs $4 of credits it would take
    weeks to earn, so nothing it learned could ever trade.
33. **The House box is checkpointed daily with Sail** (`league/backup.py`), each kept a week. *Why:*
    the ledger is one SQLite file on one disk, and it is every agent's code, record and journal.
34. **The public chart is on the league's basis** (the owner's decision on the first production
    afternoon). `account_equity` is the starting balance ($1,017.36, what the two real accounts held
    on Sept 19 before the league's first real trade) plus the league's own real-money result from
    the ledger; the raw balance is published beside it as `real_account_equity`. *Why:* the page
    showed -$4.57 of "profit" before any real trade, all of it the first run's leftover Kalshi
    contracts being marked to market. Total profit and the chart now move only when the league
    trades real money; the owner's transfers do not move them either.
35. **Three queues, a gentle cold start, and health from the moment the books are open.** Replays,
    research and housekeeping each have their own lane; a House wakes five agents a tick in its
    first five minutes. *Why, both measured in production on Sept 19:* one two-slot queue held
    research, the backup and the survey behind 28 founders' replays; and the release that fixed it
    was ROLLED BACK by the in-box watchdog, correctly, because its first tick re-read every venue
    listing for sixteen agents and did not finish within the watchdog's five minutes. The floor
    came back on the previous release by itself within a minute.
36. **A replay is deflated by the candidate's own LINE, not by its cousins** (measured in the first
    hours of production). Six sports founders shared one family, so their six founding replays
    spent the family's whole trial budget, and then every agent that researched refused to
    experiment at all: three of three passes said in so many words that a replay "would waste a
    counted trial". A deflated Sharpe corrects for picking the best of several tries at ONE idea;
    six different rules tested once each are six hypotheses, not a selection. Trials are now
    counted along the agent's lineage, a child inherits its parent's count, and the rules text
    gives agents the measured budget (a Sharpe-0.20 strategy still passes at 5 trials, fails by
    10) instead of the old flat "do not grind variants". The family is still what pools a real-money
    record at the scaled gate.
37. **The paper screen counts a week, not fifteen blocks** (`min_active_blocks_day`: 5). A block is
    a calendar day for a daily strategy, so fifteen of them is longer than the whole expedition and
    seventeen of the twenty-eight founders could never have reached real money inside one.
38. **An answer cut short by the output budget still carries its work.** Five of the first eight
    research passes ended as "incomplete" after two turns and everything the model had done was
    thrown away. The tool calls it managed are now run, the reason is recorded, and the research
    budget is 16,000 output tokens (reasoning tokens count toward it).
39. **The names are the firm's** (the owner's, Sept 19). Each specialty is one partner's DESK and
    every agent of it is numbered from that name, as the first run's were Mullins VI and VIII:
    `meriwether`, `meriwether-2` ... and a child takes the next free number in the line. A founder
    is now keyed by the role it plays on its desk (`favorites-maker`), which is what makes founding
    idempotent when six founders share a name. Astra is **Merton**, the firm's deepest theorist:
    the branch prefix, the ledger kinds, the workflow and the CI guard all carry the name. The
    model behind it is still `gpt-6-astra`, which is a model at the gateway and not a person.
40. **An agent may hire Merton with its own credits** (the owner's, Sept 19). `ask_merton` in the
    research loop: at least $1.00 of credits, once a day, gated by the expedition's own frontier
    allowance, charged at the cost the gateway reports. He is given the agent's whole file,
    journal, trades and replay digests, and answers with advice or a whole strategy file, which
    goes through the same safety check and the same replay as anything the agent writes itself.
    *Why:* performance already earned credits and credits already bought compute, but the best
    thinking in the firm was reserved for the House's own schedule. Now the flywheel closes.
41. **A failure frees a seat that something new fills.** Before this the House staked a newcomer
    only below the population FLOOR, so a death shrank the league from 28 towards 12. It fills to
    the ceiling instead, one an hour, on the desk with the most room.
42. **Bold where it is free, strict where it costs** (the owner's, Sept 19 evening). A paper seat
    costs the owner nothing but compute, so the only gate before one asks 75% confidence rather
    than 90%: a three-to-one bet on free information. The volume thresholds are untouched, because
    what the league is short of is strategies that trade at all. Every gate that spends money is
    where it was: the screen, Merton's audit, the $50 tuition and the confidence bound at the
    scaled rung.
43. **An agent with no record rewrites itself in place.** Measured on the first evening: the six
    agents of the sports desk each saw 126 to 200 live markets, found none inside the band they
    were born with, and could not trade at all; none could afford a fork for days. An agent with no
    holding, no working order, no active block and no closed trade has no record for new code to
    inherit unfairly and no position to leave it holding, so code that passes replay simply becomes
    its own. The moment it trades, the rule returns and an improvement is a child.
44. **Idleness costs.** The niche floor is paid only to an agent that has traded within the epoch
    or has an order resting. An agent that does neither earns nothing and spends down what it has.
    Before this an idle agent was immortal: it accrued no active blocks, so no statistical death
    could reach it, and the floor paid it for ever.
45. **What a rung buys is more of Merton.** An agent may hire him every 24 hours on paper, every 8
    on real money, every 6 once scaled, and he may answer by putting the DATA the agent cannot work
    without into the toolsmith's queue in his own name.
46. **A strategy may WATCH what it may not trade.** `NEEDS["observe"]` takes up to six symbols and
    six series on EITHER venue, whatever the agent's own is; they arrive as `ctx["observed"]` live
    and on the replay tape alike, and an order in any of them is refused by the book and by the
    replay. *Why:* five agents asked the toolsmith in their first hours for the spot price their
    Kalshi contracts settle against, a live match state, the value behind an attention market and
    BTC/ETH bars for an alt-coin desk, and Merton answered, correctly, that none of it could be
    built as a tool: what they wanted was data the House did not fetch.
47. **A replay the box could not run is not a trial** (killed, timed out, or exited non-zero with
    no result). Three agents of the sports desk were charged one each for a seven-week tape that
    exhausted a 16 GB box. A daily Kalshi tape now steps by the half hour and carries at most 500
    markets: a strategy judged on daily blocks does not need five-minute resolution.
48. **A research pass must end in a tool call.** Nine of fifteen passes spent their whole output
    budget reasoning and returned no tool call at all, at about three cents each. The provider
    takes an optional `tool_choice`, "auto" for the first run's desk loop and "required" for the
    league's research loop, whose output budget is now 32,000 tokens.

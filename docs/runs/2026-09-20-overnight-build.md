# Overnight build of the rebuilt floor (night of Sept 19 to 20, 2026)

This file is the builder's place-keeper and, at the end, the report. The goal is
`docs/design/overnight-goal.txt` (every line binds); the designs are
`docs/proposals/2026-09-19-the-game.md` and `docs/design/2026-09-19-architecture.md`.

Started 2026-09-19 06:00 UTC. Eight hours ends 14:00 UTC.

## The report

Written at the end of the build, about 09:30 UTC on Sept 19, 2026 (02:30 in California), three and
a half hours after it started. All six steps are built. Everything below was run, not assumed;
where something was not verified it says so.

### After the report: the owner's changes of Sept 19 (afternoon)

The owner's worry on reading the report was a league too strict to ever trade. It was right, and
measured: run with the ladder's own code, the one edge the first run measured had a 0% chance of
reaching real money within a month. Four changes followed, all built with tests (the league's
suite is now 923) and recorded as deviations 22 to 27 in `docs/design/2026-09-19-architecture.md`:

- **The paper gate is a screen with a dollar cap** (`tuition`: 4 agents on the micro rung at once,
  $50 net, then the rung closes). The confidence bound stays between micro-real and scaled, with
  its own alpha, and a family's pooled real-money record can carry a member.
- **The horizon rule:** Kalshi entries pay within 12 or 48 hours, crypto positions close after 48,
  equities unbounded. Games are now shown by their scheduled end (before this no NFL, college,
  MLB or soccer game was visible to any agent).
- **Specialists:** eleven open niches and one dormant (options), 26 founders, universes from a live
  survey of the venue that the House repeats daily so they follow the season.
- **Found on the way:** a rung-3 agent's limits were reset to the micro rung's at every wake; the
  replay charged Kalshi makers nothing on the series that charge them; a bid left resting during a
  match is picked off when a goal is scored (sports founders now enter before the start only).

**Not built:** options. The gateway refuses Alpaca's option chain and quote paths, and nothing
about pricing a contract can be checked against a live market before Monday's open.

### State everything was left in

- Gateway kill switch **engaged**. No real-money order was placed tonight (gateway counter: 0
  orders, $0.00). `league/config.json` has `"real_money": false`.
- The House loop is **stopped** and has never been started on the box. The House box holds the
  release the watchdog promoted from `main`, three secrets, no venue key, and is **paused**.
- The production tape is **empty** (`/api/capital/checkpoint` is 404); the page shows the red
  "stopped" dot by itself. Test data is on the `test` tape only.
- The Alpaca paper account is **flat**: no positions, no open orders, $99,999.18.
- Every Sail box this build created (agent boxes, probes, canaries) is terminated. The first run's
  ~100 boxes are as they were: paused or sleeping, billing nothing.
- Both repositories are clean and pushed; the deployed gateway, site and box code are `main`.

Switching on is `docs/runbook-go-live.md`: `floor_box.py resume`, `deploy`, `start`.

### What was built

| Step | What | Where |
|---|---|---|
| 1 | Append-only hash-chained ledger; one netting book per venue (per-agent accounts folded from the ledger, the first run's 21 risk rules unchanged plus the league's own, market orders netted with internal crosses priced as the venue would have, pro-rata attribution, reconciliation against a baseline); gateway venues including `alpaca-paper` | `league/ledger.py`, `book.py`, `fees.py`, `venues.py` |
| 2 | Statistics (alpha-spent t-bounds, the exact loss-rate gate, deflated Sharpe, CUSUM, quarter Kelly); a self-contained replay simulator that runs in the agent's box; tapes from Alpaca and Kalshi; the Kalshi shadow venue; the evaluator; the pinned constitution | `stats.py`, `replay.py`, `tapes.py`, `paper.py`, `evaluator.py`, `constitution.py` |
| 3 | Compute credits with niche floors, payout, fork threshold; the agent registry; one sealed Sailbox per agent with fork-by-checkpoint; the in-box runner and its safety check; web search, library, tool-request queue, graveyard playbook; the researcher loop; twelve founding seeds; the House tick; the Sail budget meter | `economy.py`, `game.json`, `agents.py`, `sandbox.py`, `runner.py`, `safety.py`, `commons.py`, `researcher.py`, `rules.py`, `seeds/`, `house.py`, `budget.py` |
| 4 | The frontier client and the fail-closed auditor with counterfactual scoring; the publisher for the five-section site; service wiring and the command line; on the site: a test tape, practice positions with a tag, the new research tools, a data-driven live dot | `frontier.py`, `auditor.py`, `publish.py`, `service.py`, `__main__.py`; personal-site |
| 5 | Astra's five pull-request roles; the gateway's GitHub route; the CI judge and the two workflows; releases, canary, promotion, watch and rollback; a simulated paper venue for the canary; the updater that pulls `main`; the box script rebuilt around releases | `astra.py`, `ci.py`, `strategies/`, `tools/`, `playbook/`, `watchdog.py`, `sim.py`, `updater.py`, `gateway/lib/github.mjs`, `.github/workflows/astra.yml`, `scripts/floor_box.py` |
| 6 | Quarter-Kelly stakes on the lower bound, capped by a share of the venue's cash and by what one order can close; drift on the edge per trade; the standing capital recommendation | `capital.py`, `evaluator.py` |

### Definition of done, item by item

**(a) All three suites pass.** League: 847 tests. Gateway: 104. Site: 65. (The first run's suite,
which the league's imports depend on: 1,753.) GitHub Actions ran the league and first-run suites
green on Python 3.11 and 3.14. The league's suite includes a whole-ladder test (paper, the audit,
micro-real, scaled, sizing, decay and demotion in one run) and a replay regression over canned
tapes for every seed.

**(b) End-to-end dry runs on Alpaca paper and the Kalshi shadow book, with real Sail boxes.**
- *Book against the real paper venue* (scratch `book_live.py`): two agents, three netted buys, a
  cross inside the House with only the difference sent, everything closed; reconciled after every
  stage with cash differences of -$0.0015, -$0.0024, +$0.0021, no position differences.
- *The league for an hour* (scratch root `dry2`, test tape): twelve founders woke on their clocks in
  sealed Sailboxes, thought, researched with real Sail inference (53 research steps, 5 library
  notes, 3 tool requests, about $0.001 a pass), proposed 7 orders, rested bids on both venues, took
  a Kalshi shadow maker fill that later settled, ran 12 replays as counted trials; both books
  reconciled at every one of 24 checks; the ledger's 576 rows verified, including after a
  `kill -9` of the House mid-run and a restart on the same state.
- *Accelerated* (scratch `accel3`, sandbox seconds priced a thousand times over so a week's burn
  takes minutes): `crypto-dip-limit`, born with $3.30 of credits, **forked** `crypto-dip-limit-2` by
  rule and endowed it with $1.00 (a real Sail checkpoint fork: `box_forked: true`);
  `favorites-no` **died** of credits at its second wake, with a post-mortem in the playbook; both
  books reconciled with a cash difference of zero; 102 ledger rows verified.
- Paper fills seen tonight: Alpaca crypto market buys and sells (real paper fills), a Kalshi shadow
  maker fill and its settlement. **Not yet seen as a fill:** any equity, any option, any Alpaca
  limit order (they rested), anything on a real venue. Equity and option order paths were verified
  as accepted-then-cancelled paper orders (F, one share; SPY 2026-10-16 740 call, one contract).
  The House's own rules correctly refused an equity market order while New York was closed.
  **Options are switched off** in the book until the House can quote them (no chain or option
  quotes; the gateway does not serve Alpaca's contract listing).

**(c) Astra, metered through the gateway.** The auditor vetoed a deliberately bad candidate (a
martingale with a good-looking 40-block paper record) with four blockers, naming the unbounded
doubling, the breach of the micro limits and the $75 cap, and wins that were losses after fees:
$0.23 (a first attempt with an empty record cost $0.07). The architect completed one metered pass
($0.10) and declined to write a strategy, with reasons; the toolsmith one ($0.06), correctly
answering that the agents' three requests needed data, not tools (the House was changed instead).
Pull requests: **#1** (a strategy importing `os`) refused by the `judge` job; **#2** (a designer
branch editing the constitution) refused by the `guard` job run from main's copy; **#3** (a lesson
for the playbook) passed guard, judge and both suites and was squash-merged by the `merge` job with
no human step. The three were opened from this machine with a `gh` forge of the same interface,
because the gateway has no GitHub token yet (see "what is still yours").

**(d) The watchdog on the box.** First deploy of the league: canary passed, `PROMOTED`. Then a
release whose `House.tick` raises was handed to it on the box: verdict `refused` ("tick 1: it
exited 1: RuntimeError: a deliberately broken release"), `current` untouched. The other half, a
release that passes the canary and degrades after promotion being rolled back, is verified by the
watchdog's tests with real subprocesses and symlinks and by a command-line run against a stand-in
House; it was **not** run on the box, because that needs the House loop running and tonight's rule
was that it stays stopped.

**(e) The site on a test tape.** The real publisher filled `https://blakewoods.us/capital/?tape=test`
during the dry runs. The page's own functions over that live tape: a live stream of agents'
thoughts and league news; Total profit $0.00 and a running clock (the real accounts are flat
against the $1,021.93 baseline, funding verified); a 16-point balance chart of the real accounts;
a closed Kalshi shadow trade with its reason (open-position rows with reasons are covered by the
publisher's tests and the site's contract test; none were open at that moment); one improvement
bar for generation 1. The publisher's output passes the site's `validCheckpoint` and
`validEventBatch`. Production was never written to.

**(f)** `docs/runbook-go-live.md`.

**(g)** This file.

**(h) GitHub.** Both repositories clean and pushed; gateway (version d553812d), site (8ed04f2d) and
the box's release deployed from `main`; README rewritten for the system as it exists with the first
run's record moved to `docs/history/`; `league/README.md` added; `ltcm/README.md`,
`gateway/README.md`, `docs/README.md`, `deploy/README.md`, the architecture (with a section on
everything built differently from the plan, and why) and the game memo brought into agreement with
the code; the repository description and website link are unchanged and right; tonight's commits
in both repositories were scanned for the values in `.env`, key and token shapes and the two
account identifiers: nothing (one match is a labelled test fixture string).

### What was deferred, and why

- **Removing the first run's code.** The league imports its adapters, broker types, risk engine,
  fee model, Sail clients, provider, data readers and funding-flow reader. The rest (desks,
  committee, evolution, Foundry, lab, mind, service) is no longer run. Cutting it out safely means
  untangling 1,753 tests; tonight the documents were corrected instead.
- **Replay for daily-bar equity strategies.** A day's bar is stamped at its close, when the market
  is shut, so the simulator never sees a moment an equity order is allowed. Those three founders are
  judged forward only, and their children cannot qualify until the tape steps inside the session.
- **Options.** Order path proven; no quotes, chains or marks. Switched off.
- **An off-box copy of the ledger.** The ledger lives on the House box's disk. A lost box is a lost
  ledger (the public tape would survive). A daily Sail checkpoint taken by the House itself is the
  obvious next step.
- **Rollback on the box with the loop running** (see (d)).

### What is still yours

1. **`GITHUB_TOKEN` in the gateway** (runbook, section 4). Without it Astra's five pull-request
   roles run, are recorded and change nothing. The auditor does not need it.
2. The two obsolete `COINBASE_*` Worker secrets are already gone from the Worker; revoke the key at
   Coinbase if you have not.
3. About a hundred first-run Sail boxes are paused or sleeping. They cost nothing; terminating them
   is tidying.

### Every known risk

1. **Most founders honestly fail replay** (crypto reversion lost after fees; Kalshi favourites scored
   a deflated Sharpe of 0.85 against 0.90). They trade on paper anyway, earn floors, pay for their
   compute, and some will die within days. That is the game working, but the first week may look
   like attrition, and the population is refilled by forks and House-staked mutations, not by
   brilliance, until Astra's architect can open pull requests.
2. **Practice fills are kinder than real ones.** Alpaca paper fills at the touch with no queue; the
   shadow book models no depth. Rung 2 exists to measure the gap at $10 a position, and the drift
   monitor demotes an agent whose real edge per trade falls below its paper edge.
3. **No real-money path has carried a real order** (tonight's rule). The real Kalshi and Alpaca
   books are the same code as the practice books behind the same adapters, and are tested against
   fakes, including Kalshi's habit of reporting a NO holding as a negative count. What has not been
   seen live: a real Kalshi fill's fee attribution, a real Kalshi settlement arriving through
   `settlements()`, Alpaca's real crypto fee tier. Every one of those failing shows up as a book
   that does not reconcile, which freezes new entries on that book, never exits, and raises an
   alert. The first real order is more than a day away after real money is turned on, and gated by
   the audit: look at `status` when the first agent reaches rung 2.
4. **The updater deploys whatever reaches `main`**, through the content checks, the canary and a
   ten-minute watch. A change that passes all three and degrades an hour later is not rolled back
   (the gateway's watchdog restarts a quiet House but never changes its release).
5. **Two watchdogs read two signals.** A House that ticks but cannot publish is healthy to the
   in-box one and stale to the gateway's, which will restart it every thirty minutes. A gateway
   restart landing inside the in-box watch can age `health.json` and cause a needless rollback (to
   the known-good release).
6. **Sail's search price is unpublished.** Agents are charged an assumed $0.01 a query. The real
   cost shows up only in the Sail balance, which the budget meter reads, so the monthly line holds
   either way.
7. **The Sail budget is metered from falls in the account balance**, so anything else spending on
   that account counts against the league's $100.
8. **The agent image is the first run's lab image checkpoint** (Sept 15). If Sail expires it,
   existing agent boxes keep working but no new box can be made (no births, forks or canaries).
   A small dedicated image should replace it.
9. **Reads that grow with the ledger.** The publisher and parts of the evaluator re-read whole
   tables each tick. Fine for a week (tens of thousands of rows), not for a year.
10. **The canary uses real Sail boxes** (two agents and a probe), destroyed at its end; a canary that
    dies midway can leave a few asleep (free, untidy).
11. **Mail.** While the kill switch is engaged and the box paused, the gateway's watchdog mails
    about both every six hours, plus the evening digest. That stops when the floor runs.
12. **A long `pause` is undone by the gateway's watchdog** once the production tape has a
    checkpoint (runbook, section 6).

### Spend tonight

| | Start | End | Spent | Limit for tonight |
|---|---|---|---|---|
| Sail credit | $97.80 | $97.50 | **$0.30** | $10 |
| OpenAI, through the gateway's meter | $0.01 | $0.44 | **$0.43** (five calls: two audits, one architect pass, one toolsmith pass, and the first audit attempt) | $10 |
| Real-money orders | 0 | 0 | none | none allowed |

The Sail figure is the fall in the account balance (`/v2/usage/summary`), so it includes every
agent box, probe, fork, canary, replay and research pass of the night and the House box's hours
awake. The five Astra calls are filed under "unattributed" in the gateway's month because the
House sent names with a colon, which the gateway does not accept; fixed during the build
(`league/frontier.py`), so from now on audits are filed under `audit-<agent>` and passes under
`astra-<role>`.

## Where I am (the builder's place-keeper, kept for the record)

- **Step:** finished. The report above is the summary; what follows is the log it was written from.

## Decisions and their reasons

(Appended as they are made. Newest last.)

1. **New package `league/` beside `ltcm/`.** The old runtime stays importable while the new one
   is built; old code is removed only when the new code replaces it and the tests prove it.

2. **Kill switch found released at 06:03 UTC and engaged.** `/v1/health` said `kill_switch: false`
   (left off after the Alpaca route checks). The goal says it stays engaged, so `POST /v1/kill`.
   The paper venue ignores it by design, so tonight's paper tests still run.
3. **The ledger is one chain, not one per stream.** `league/ledger.py` copies the mechanics of
   `ltcm/events.py` (canonical JSON, digest over the previous digest, UPDATE/DELETE triggers,
   idempotent ids) with the league's own kinds and an `agent` column. One chain gives a total order
   that a reconciliation can pin (`ledger_seq`, `ledger_digest`).
4. **The old risk engine is reused unchanged.** `ltcm/risk.py` is pure and duck-typed on the
   manifest, so the book builds a `RiskContext` from its own state and runs all 21 rules, then adds
   the league's rules: $75 order cap, rung position caps, cash including fees and slippage, quote
   age, and no order that could trade against the House's own resting order.
5. **Netting rule, v1.** Same-batch market orders on one instrument are netted; the minority side
   is crossed inside the House at the venue's touch with the venue's taker fee (each agent is
   scored exactly as if it had traded alone; the saving accrues to the House row, which keeps the
   books summing to the venue). Limit orders are never pooled (one venue order per intent, so no
   apportioning). An intent that could execute against a House resting order is refused rather
   than cancel-and-crossed: simpler, never a wash trade. Cost: a refused agent loses that fill.
6. **Agents get zero credentials, not a House token.** The House drives each agent's box over the
   Sail exec API (resume, run `decide`, read stdout, sleep) and runs the researcher model and
   tools on the agent's behalf, metered to it. Nothing in an agent's box can reach the House, a
   venue or the gateway. This is inside the constitution's bound ("no credential except a House
   token") and removes the need for House ingress.
7. **Reconciliation uses a baseline.** The paper account holds $100,000 that is not the book's and
   the real accounts hold unallocated cash, so the book records once what the venue held at
   opening; afterwards venue cash must equal baseline plus the book's own cash, to the cent, and
   each position the baseline's plus the agents'. Under a cent (per venue fill since the last
   check) is booked to the House row as dust; more freezes new entries but never exits.

8. **Alpaca fills are booked at the taker's fee; reconciliation returns a maker's difference.**
   Alpaca reports no fee and accepts every order asynchronously, so only the venue knows whether a
   limit order made or took. The book assumes the taker's 0.25% and keeps a per-reconciliation
   allowance; a venue that charged less shows up as surplus coins or cash, booked to the House row.
9. **One account never holds both legs of a Kalshi market.** Kalshi nets YES against NO and pays the
   pair out early, which would stop per-agent legs summing to the venue. The book refuses an
   opening buy on a leg whose opposite leg the House holds or bids. (The real adapter reports a NO
   holding as a negative count; reconciliation reads it that way.)
10. **The loss-rate gate is exact, not Wilson.** The statistics builder measured the one-sided
    Wilson bound at 92 to 94% coverage for clean records; the gate now uses Clopper-Pearson. A
    record of clean +0.5% wins risking 7% needs 46 of them, not 40.
11. **Founders start on paper.** The first dry run showed honest replays failing most seeds (crypto
    reversion Sharpe below zero after fees; Kalshi favourites deflated Sharpe 0.85 against the 0.90
    line). Paper costs nothing and forward evidence is what counts, so the twelve founding seeds
    are seated on rung 1 at birth; their replay still runs and still counts as their family's first
    trial. Everything born later (forks, mutations, Astra's strategies) must pass replay first.
12. **Niche floors are paid only to qualified agents (rung 1 and up), and a rung-0 agent that has
    not passed replay within three epochs is retired.** A floor for an agent that does nothing
    would pay for squatting on a population slot.
13. **Replays and research run beside the tick, never inside it.** The first real tick took six
    minutes because a Kalshi tape build and a flex-window model call ran inline.
14. **The site got a test tape** (`/api/capital/t/test/...`, viewed at `/capital/?tape=test`): the
    same Durable Object class under another name, allow-listed to `test` and `canary`. The
    production tape stays empty until go-live, which also keeps the gateway's old watchdog quiet
    (it acts only on a published production checkpoint).
15. **Web search is Sail's search API** (found working with the project key; price unpublished, so
    the House charges agents a conservative $0.01 a query), with Google News RSS as the fallback.
16. **Agent boxes are forks of the first run's lab image checkpoint** (python3 present), sealed with
    an egress allowlist of one never-resolving host because Sail refuses an empty allowlist.
    Verified live: DNS fails inside the box; decide takes about 9 s a wake; a fork takes about 25 s.

17. **Every defect an adversarial test pass found was fixed** (a subagent wrote tests against the
    evaluator, sandbox, runner, auditor and frontier client and found 18). The ones that mattered
    most: a box was recorded before it was sealed (now sealed first, destroyed if it cannot be);
    failed replays did not raise the family's trial count (now every replay does); `observe`
    crashed after a rung change on a shared book; the audit read the string "false" as approval.
18. **Astra's pull requests go through the gateway** (`POST /v1/github/pr`), which holds the GitHub
    token like every other credential and enforces each role's paths outside Sail. CI on GitHub
    judges (`.github/workflows/astra.yml`, run from main's copy with `pull_request_target`, so a
    branch cannot rewrite its judge) and merges a green PR from a job that never runs the branch's
    code. **The owner must place `GITHUB_TOKEN` in the gateway** (a fine-grained token for this one
    repository: Contents and Pull requests read/write) before Astra's five PR roles can act
    unattended; until then each pass is recorded with `forge_error: GitHub is not configured` and
    nothing else changes. The auditor does not need it. Tonight the flow was proven from the
    owner's machine with a `gh`-based forge of the same interface.
19. **Drift is compared per unit of exposure.** The same strategy has a fifth of its stake at work
    on paper and a third on the micro-real rung, so raw growth per block differs by rung; blocks
    now record their average exposure and the CUSUM compares growth per unit of it.
20. **The whole-ladder test earned its keep**: it found that a one-step crumb (0.000000001 BTC) the
    venue still showed after its holder sold out froze the book, and that sweeping a promoted
    agent's paper account read as a 100% daily loss and tripped the floor breaker for every other
    agent. Both fixed; stake flows no longer count as profit or loss in the breakers.
21. **Alpaca takes the cash behind a resting crypto bid out of `cash`** ($80.00 for two $40 bids,
    measured). Reconciliation adds it back; the House takes every book's baseline at start, before
    anything can trade.
22. **Kalshi replay tapes are a week (hourly) and seven weeks (daily).** The dry run's own agents
    diagnosed the one-day tape and filed tool requests; Astra's toolsmith correctly answered that
    this needs data, not a tool, so the House was changed.
23. **Old-run code is kept, not removed.** The league imports the first run's venue adapters,
    broker types, risk engine, fee model, Sail clients, inference provider, data readers and
    funding-flow reader. The rest of `ltcm/` (desks, committee, evolution, foundry, lab, mind,
    service) is no longer run. Removing it safely is a job of its own (1,753 tests live there);
    tonight the documents were corrected instead.

## Step log

### Step 1: ledger and order book (done about 06:20 UTC)

Built `league/ledger.py`, `league/fees.py`, `league/book.py`, `league/venues.py`.

Verified:
- 40 league tests pass (12 ledger, 28 book); the old runtime suite still passes (1,696).
- **Live check against the real Alpaca paper account through the gateway**
  (scratch `book_live.py`): two agents staked $200 each; three netted buys (BTC twice, ETH), then
  one agent sold out while the other bought (crossed inside the House, only the difference sent),
  then everything closed. The book reconciled to the venue after every stage: cash differences
  -$0.0015, -$0.0024, +$0.0021 (all under a cent, booked as dust), no position differences, 47
  ledger rows verified.
- What the live check taught, all now in the code and the tests: Alpaca takes the 0.25% crypto
  taker fee out of the coins on a buy and out of the proceeds (rounded up to the cent) on a sell,
  and reports a fee of zero; every order comes back `accepted` and fills a moment later (so
  "still open" does not mean maker); positions come back as `BTCUSD` for orders in `BTC/USD`.

### Step 2: evaluator rungs 0 and 1 (done about 06:45 UTC)

`league/stats.py` (97 tests), `league/replay.py` (61), `league/tapes.py` (39, plus a live smoke
check: 72 BTC bars through the gateway, 27 live KXBTCD markets, a 12-hour Kalshi tape in 13 s),
`league/paper.py` (42: the Kalshi shadow venue), `league/evaluator.py`, `league/constitution.py`.

### Step 3: economy and lifecycle (done about 07:10 UTC)

`league/economy.py`, `league/agents.py`, `league/sandbox.py`, `league/runner.py`,
`league/commons.py`, `league/researcher.py`, `league/rules.py`, `league/seeds/` (12 seeds, 131
tests), `league/house.py`, `league/budget.py`. Sail sandbox verified live (decision 16). First real
dry run (three seeds): replays ran in Sail boxes in 10 s each and were recorded as trials.

### Step 5: Astra's roles, CI, canary, watchdog (done about 08:10 UTC)

`league/ci.py`, `league/astra.py`, `league/strategies/`, `league/tools/`, `league/playbook/`,
`.github/workflows/astra.yml`, `league/watchdog.py`, `league/sim.py`, `gateway/lib/github.mjs`
(gateway suite 104), `scripts/floor_box.py` rewritten around releases (first-run suite 1,753).
Verified live: one metered architect pass ($0.10: it declined to write a strategy, with reasons) and
one toolsmith pass ($0.06: all three requests need data, not tools); PR #1 (a strategy importing
`os`) refused by the `judge` job; PR #2 (a designer branch editing the constitution) refused by the
`guard` job; PR #3 (a lesson) passed guard, judge and both suites and was squash-merged by the
`merge` job with no human step.

### Step 6: sizing, drift, recommendation (done about 08:05 UTC)

`league/capital.py`, drift in `league/evaluator.py`, `league/tests/test_ladder.py`.

### Step 4: auditor and publisher (done; verified live)

Live: the auditor vetoed a deliberately bad candidate (a martingale with a good-looking paper
record) with four blockers, $0.23 (plus a $0.07 first attempt); the dry run published 12 agents to
the test tape and the site stored the checkpoint after the stamp-order fix.

`league/frontier.py`, `league/auditor.py`, `league/publish.py`, `league/service.py`,
`league/__main__.py`. The publisher's real output passes the site's own `validCheckpoint` and
`validEventBatch`. Site changes deployed (version 64cdf966): test tape, practice positions with a
tag, research tool phrases; production checkpoint still 404 (clean).

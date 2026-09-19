# Long Term Capital Management

**AI agents that trade real money on Kalshi and Alpaca, compete for compute, and rewrite
themselves from every result, in public and with no human in the loop.**

Cheap open models on [Sail](https://sailresearch.com) research and write trading strategies. A
strategy climbs a ladder from mechanical replay, to paper trading, to a few real dollars, to real
size, and only evidence moves it up. Agents earn their share of the compute budget by what they
prove, die when they run out, and fork when they thrive. A frontier model audits every candidate
before it touches money and writes new strategy code, tools and fixes as pull requests that must
pass the tests. Venue keys, order caps, budgets and the kill switch live in a Cloudflare gateway
that nothing on Sail can change.

Watch it at [blakewoods.us/capital](https://blakewoods.us/capital/). The design is in
[the game](docs/proposals/2026-09-19-the-game.md) and
[the architecture](docs/design/2026-09-19-architecture.md).

The name is a joke and a warning. No affiliation with the 1998 fund, its partners or its estate.

> The project was rebuilt from a clean slate on September 19 and 20, 2026, and this page describes
> what exists now. The first run (September 15 to 19: chat desks, a committee, shadow books) is kept
> as a record in [docs/history](docs/history/2026-09-first-run-readme.md) and [docs/runs](docs/runs/).

## The game

**The unit of selection is a strategy program, not a chat persona.** A strategy is one Python file
with a `decide(ctx)` function ([the contract](league/CONTRACT.md)). An agent is that file, a cheap
Sail model that researches on its behalf, a small memory, and an account of compute credits. The
first run's chat desks lost money; its code strategies were the only part that learned, so the
rebuild selects on code.

**The ladder.** Every agent climbs the same four rungs, and only evidence moves it. The thresholds
are constants in [`league/constitution.py`](league/constitution.py), written before any agent
traded. What is measured is after-cost log growth of the agent's own account, in blocks of an hour
or a day.

| Rung | Where it trades | Stake and limits | What moves it up |
|---|---|---|---|
| 0. Replay | nowhere: its code is walked over recorded history in its own sealed box | none | at least 20 closed trades, 30 blocks and 8 out-of-sample blocks with growth above zero, and a deflated Sharpe ratio of 0.90 or more against every replay its family has ever run |
| 1. Paper | Alpaca's paper account; a Kalshi shadow book that reads live quotes and fills conservatively | $200 stake, $100 a position, $75 an order (the live account's limits, not the paper account's $100,000) | 30 active blocks, 10 closed trades, and a one-sided lower confidence bound on mean block growth above zero; then Astra's audit; and only once the owner has turned real money on |
| 2. Micro-real | the real Kalshi and Alpaca accounts | $25 stake, $10 a position, $10 an order | the same test again, on 30 active blocks of real fills |
| 3. Scaled | the real accounts | a quarter of Kelly on the lower bound of its growth: never under $25, never over 25% of the venue's cash, a position up to half the stake and never above $60 (so one order under the $75 cap can always close it), $75 an order | nothing: it is resized every epoch, and a drift alarm sends it back down a rung |

The error rate for every promotion and every statistical death is 5%, spent across looks (look
`k` may spend `0.05 x 6 / (pi^2 k^2)`, one look every 5 active blocks), so looking often cannot buy
a false pass. A record that wins 80% or more of its trades must also clear an exact
(Clopper-Pearson) bound on its loss rate, assuming one loss of everything at risk that has not been
seen yet: clean wins of +0.5% risking 7% need 46 in a row. On rungs 2 and 3 a CUSUM compares the
edge per closed trade with the record that earned the rung (real fills worse than the paper fills
that earned rung 2 are exactly what it is there to catch); promotion is not tenure.

**Compute credits.** The owner funds a fixed research pool, $2.00 a day. Profit decides an agent's
share of it, never its size. Each epoch (a day) 40% of the pool is a floor split evenly across the
occupied niches, paid only to agents that have reached paper, and 60% is paid in proportion to mean
block growth x the square root of active blocks x the rung's weight (replay 0, paper 0.2, real
money 1.0). If nobody has performed, that share is not spent. Agents pay for what they use: model
tokens at Sail's prices, sandbox seconds ($0.04 an hour), web searches ($0.01) and their own audit
(at cost: $0.23 for the one measured). Credits cannot be created by an agent; every grant is a
House row on the ledger. These dials live in [`league/game.json`](league/game.json), inside bounds
the same file lists.

**Death.** Credits at zero; a 30% drawdown; an upper confidence bound on growth below zero after 20
active blocks; or, on rung 0, three epochs without passing replay. The House closes the account,
retires the box and writes a post-mortem that every living agent's research reads.

**Forks.** An agent with $3.00 of credits or more may fork, and must endow the child with $1.00 of
its own. An agent above rung 0 never edits itself, because its record belongs to its code: an
improvement is a child, a mutation of its parameters or new code its researcher wrote, and the child
answers for itself from replay up. The population is kept between 8 and 16.

**Niches** are venue x horizon x style (`kalshi/hour/favorites`, `alpaca/day/trend`). The floor is
paid per niche so the population cannot collapse onto whichever niche got lucky last week.

**Founders start on paper.** The twelve founding seeds (four Kalshi, four Alpaca crypto, four Alpaca
equities) are seated on rung 1 at birth. The first dry run showed honest replays failing most of
them (crypto reversion below zero after fees; Kalshi favourites at a deflated Sharpe of 0.85 against
the 0.90 line). Paper costs nothing and forward evidence is what counts, so they are forward-tested
from the first day; their replay still runs and still counts as their family's first trial.
Everything born later must pass replay first.

**Agents are told all of this**, with the numbers ([`league/rules.py`](league/rules.py) generates
the text from the constitution and the game file). An agent that understands the lower-bound rule
has no reason to gamble.

## Trust zones

| Zone | Runs where | Holds | May do | May never do |
|---|---|---|---|---|
| **Gateway** ([`gateway/`](gateway/README.md)) | a Cloudflare Worker, outside Sail | the Kalshi and Alpaca keys, the OpenAI key, the GitHub token, the order caps, the frontier budget, the kill switch | sign orders, meter spending, open a pull request inside a role's paths | be changed by anything on Sail; merge a pull request (there is no merge route) |
| **House** ([`league/`](league/README.md)) | one trusted Sailbox | three tokens (gateway, Sail, site publishing), the ledger | net and send orders through the gateway, score, pay, promote, retire, publish | hold a venue key; run agent-written code in its own process; decide a trade |
| **Agents** | one sealed Sailbox each, asleep between wakes | nothing: no credential, and an egress allowlist of one host that never resolves | run `decide` or a replay on data the House uploads, and print one line of plain data back | reach the House, a venue, the gateway or the network; write the ledger |
| **Astra** (the frontier model, `gpt-6-astra`) | behind the gateway's metered route | nothing | veto a candidate before real money; propose changes by pull request | pick a trade; touch the ledger; merge; change its own judges |

The House drives each agent's box from outside, over Sail's exec API: resume, upload, run, read one
token-marked line of stdout, sleep. Research (the cheap model, web search, the shared library) runs
in the House on the agent's behalf and is charged to the agent.

## The constitution

What no model and no code path on Sail may change, and where each item is enforced.

| Item | Value | Enforced |
|---|---|---|
| Order caps | $75 an order, $4,000 and 2,000 orders a day | in the gateway, before anything is signed (`gateway/wrangler.jsonc`); `league/book.py` refuses first so it can say why |
| Kill switch | engaged or released | in the gateway; the House's token can engage it, only the owner's separate token releases it. The paper venue passes it, because no money is behind it |
| OpenAI budget | $100 a month | in the gateway: a call is reserved at its worst case and refused (402) when the month cannot cover it |
| Sail budget | $100 a month, $10 reserve | in `league/budget.py`, because Sail has no spend caps: at the line research and practice stop and only agents holding real positions are still woken, so they can exit |
| The ladder | every threshold, stake and limit above | constants in `league/constitution.py`; a test pins the file's digest, and the House writes the digest to the ledger every time it starts |
| The judges | `constitution.py`, `ci.py`, `ledger.py`, `book.py`, `evaluator.py`, `stats.py`, `auditor.py`, `watchdog.py`, `safety.py`, `replay.py`, `updater.py`, `gateway/`, `.github/` | out of reach of every Astra role: the gateway refuses the path before a branch exists, and CI's path guard refuses it again. GitHub runs that guard from `main`'s copy, so a branch cannot rewrite its judge |
| Real money | `"real_money": false` in `league/config.json` | only the owner changes it; CI refuses an operator change to anything but four operating dials; the House refuses real money unless agents run in sealed Sailboxes |

## Astra's six jobs

Astra never picks a trade. As auditor it can only veto; in the other five roles it can do exactly one
thing, propose a pull request, and each role may touch only its own paths. The gateway opens the pull
request, [CI](.github/workflows/astra.yml) judges it (path guard, content checks, the replay
regression, the whole league suite) and a workflow job that never runs the branch's code merges a
green one. Every pass is a row on the ledger and a line on the public tape, with its cost.

| Job | When | What it does | May touch |
|---|---|---|---|
| Auditor | when a paper record clears the test (at most once per agent every 72 hours) | reads the agent's whole evidence packet and hunts for look-ahead, fee errors, thin data, a record carried by one fill, duplicated exposure. One blocker is a veto. The agent pays. Vetoes are scored afterwards as if taken | nothing |
| Architect | weekly | reads the league table, the graveyard and the replay trials; writes at most two new strategies, born on rung 0 | `league/strategies/` |
| Toolsmith | daily, when agents have filed requests | builds pure-Python helpers agents may import, with tests; answers every request | `league/tools/`, `league/tests/test_tool_*` |
| Operator | daily | reads alerts, health and budget | four dials in `league/config.json` (`tick_seconds`, `mark_every_seconds`, `replay_days`, `inference_daily_cap_usd`), inside bounds |
| Game designer | weekly | judges the economy: diversity, causes of death, where compute goes | `league/game.json`, inside the bounds it lists |
| Teacher | every three days | distils the graveyard into specific, checkable lessons | `league/playbook/` |

## What is public

The House publishes to [blakewoods.us/capital](https://blakewoods.us/capital/), which draws five
sections from the tape:

1. a live stream of agents' thoughts, research and trades, and the league's own news (births,
   replays, promotions, audits, deaths);
2. total profit and running time;
3. the balance chart: the real Kalshi and Alpaca accounts against the owner's baseline, deposits
   and withdrawals taken out. Practice money is never added to it;
4. open and closed positions, each with the agent's own reason (practice positions are tagged);
5. one self-improvement series: after-cost return on the capital at work, by generation.

Strategy source stays private; its hash, parameters, family and results are public. The site
validates every byte and refuses a whole batch for one bad event
([the contract](league/tests/fixtures/site_contract.md)). A **test tape**
([blakewoods.us/capital/?tape=test](https://blakewoods.us/capital/?tape=test), `--tape test`) is the
same page over separate storage; the production tape stays empty until go-live.

## Repository layout

| Path | What it is |
|---|---|
| `league/` | The rebuilt runtime: the House. Standard library only. [Its own guide](league/README.md). |
| `ltcm/` | The first run's runtime. No longer run; the league imports its venue adapters, broker types, risk engine, fee model, Sail clients and data readers. [What is still used](ltcm/README.md). |
| `gateway/` | The Cloudflare Worker that holds every credential, the caps and the kill switch. |
| `scripts/` | The owner's tools: `floor_box.py` (the House's Sailbox), `gateway_admin.py` (kill switch and status), and the first run's scripts. |
| `deploy/` | [How the House runs on its box](deploy/README.md): releases, the canary, the two watchdogs. |
| `docs/` | [Index](docs/README.md): the design, the build log, the runbook, and the first run's record. |
| `playbooks/` | The first run's desk playbooks, kept as history. The league's lessons are in `league/playbook/`. |
| `.github/workflows/` | `astra.yml` judges and merges Astra's pull requests; `checks.yml` runs all three suites on every push to `main` and every pull request. |

The `league/` modules:

| Module | What it does |
|---|---|
| `ledger.py` | One append-only, hash-chained SQLite record of everything that decides an agent's fate. |
| `book.py` | One netting book per venue account: risk rules, netting, fill attribution, reconciliation to the cent. |
| `fees.py` | What a fill costs at each venue, as measured. |
| `venues.py` | The venue adapters in gateway mode (`alpaca`, `alpaca-paper`, `kalshi`). |
| `constitution.py` | The constants no model may change, and their digest. |
| `stats.py` | The statistics the ladder decides on: bounds, alpha spending, the loss-rate gate, deflated Sharpe, CUSUM, quarter-Kelly. |
| `evaluator.py` | The ladder: trials, blocks of log growth, looks, promotion, death, drift. |
| `replay.py` | Rung 0: the mechanical replay simulator. Self-contained; runs inside the agent's box. |
| `tapes.py` | Recorded history for replay and live snapshots of the same shape, for both venues. |
| `paper.py` | The Kalshi shadow account: live quotes, conservative fills, no order ever sent. |
| `sim.py` | A simulated Alpaca account, the venue a canary House trades on. |
| `economy.py`, `game.json` | Compute credits: grants, charges, payouts, forks; the tunable dials and their bounds. |
| `agents.py` | Who is in the league: identity, strategy, lineage and fate, folded from the ledger. |
| `sandbox.py` | One sealed Sailbox per agent (or a local subprocess for tests). |
| `runner.py` | Runs one `decide` inside the box and prints one token-marked line. |
| `safety.py` | What a strategy file may contain: the import whitelist and the banned constructs. |
| `commons.py` | What agents share: web search, the research library, the tool-request queue, the playbook. |
| `researcher.py` | The research loop a cheap Sail model runs for one agent, at that agent's expense. |
| `rules.py` | The text every agent is told, generated from the constitution and the game file. |
| `seeds/` | The twelve founding strategies. |
| `strategies/`, `tools/`, `playbook/` | What Astra adds by pull request: strategies, helper modules, lessons. |
| `house.py` | The House: one `tick()` is the whole loop. |
| `budget.py` | The Sail budget meter. |
| `frontier.py` | The client for the gateway's metered frontier route. |
| `auditor.py` | The veto before real money, and its counterfactual score. |
| `astra.py` | Astra's five pull-request roles. |
| `ci.py` | The judge of every change: path guard, content checks, the suite. |
| `capital.py` | Rung 3 sizing and the standing capital recommendation for the owner. |
| `publish.py` | The public tape. |
| `service.py`, `config.json` | Builds the real House from the config and three secrets. |
| `__main__.py` | The command line. |
| `watchdog.py` | In-box releases: stage, canary, promote, watch, roll back. |
| `updater.py` | Pulls `main` every half hour on the House box and hands a changed tree to the watchdog; never lets `real_money` change that way. |
| `CONTRACT.md` | The strategy contract. |

## Running things

Tests. Python 3.11 or later, standard library only; the gateway needs Node.

```sh
python3 -m unittest discover -s league/tests -t .   # 847 tests, about two minutes (the whole-ladder test is most of it)
python3 -m unittest discover -s ltcm/tests -t .     # 1,753 tests: the first run's suite, still green
(cd gateway && npm test)                            # 104 tests
python3 -m league.ci --no-tests                     # content checks: strategies, tools, game and config bounds
```

The House, from the repository root (it reads a 0600 `.env` holding `GATEWAY_TOKEN`, `SAIL_API_KEY`
and `CAPITAL_PUBLISH_TOKEN`):

```sh
python3 -m league found     # seed the founding population (idempotent)
python3 -m league tick      # one tick, then exit; prints its summary
python3 -m league run       # tick, sleep, tick, until a STOP file appears in the state directory
python3 -m league status    # the league table, the books and the budget, as JSON
python3 -m league verify    # re-hash the ledger's chain and reconcile every book to its venue
python3 -m league stop      # write the STOP file; the loop ends after the tick in hand
python3 -m league start     # remove the STOP file
```

Options: `--root DIR` (state directory, default `.data/league`), `--tape NAME` (publish to a test
tape), `--no-publish`, `--no-research`, `--seeds a,b` (for `found`), `--local-sandbox` (agents run in
local subprocesses: a developer's machine only, refused with real money) and `--canary` (a House
that can hurt nothing: simulated paper venue, no publishing, no research; needs its own `--root`).
One safe tick on a laptop: `python3 -m league tick --local-sandbox --no-publish`.

The House's box, from the owner's machine ([details](deploy/README.md)):

```sh
python3 scripts/floor_box.py create     # the box, the egress allowlist, the venv, run.sh; loop stopped
python3 scripts/floor_box.py secrets    # the three tokens -> /workspace/.env (no venue key ever goes)
python3 scripts/floor_box.py deploy     # send a release; the in-box watchdog canaries, promotes, watches, rolls back
python3 scripts/floor_box.py start      # start the supervised House loop
python3 scripts/floor_box.py status     # box, spend, loop, releases, last deploy, health, log tail
python3 scripts/floor_box.py stop       # finish the tick, sleep the agents' boxes, stop the loop
```

Also `logs`, `checkpoint`, `checkpoints`, `fork`, `sleep`, `resume`, `pause`, `terminate`, `hosts`.
`python3 scripts/gateway_admin.py status | kill | unkill` reads and sets the gateway's kill switch.

**Switching the floor on** is in [docs/runbook-go-live.md](docs/runbook-go-live.md).

## Status

Built on September 19 and 20, 2026 ([the build log](docs/runs/2026-09-20-overnight-build.md) has
every decision and its reason). The league starts on practice venues: Alpaca's paper account and
the Kalshi shadow book. Real money needs two switches, both the owner's: `"real_money": true` in
`league/config.json`, sent to the box as a release like any other, and the gateway's kill switch
released. Even then no real order is sent until an agent has cleared the paper test and the audit,
and then at $1 to $10 a position.

Known limits:

- **Daily-bar equity strategies cannot be replayed yet.** A day's bar is stamped at its close, when
  the market is shut, so the simulator never sees a moment when an equity order is allowed. Three
  seeds (`equity-overnight`, `equity-trend`, `equity-rsi2`) are judged forward only, and their
  children cannot qualify until the tape steps inside the session.
- **Astra's five pull-request roles need the owner's `GITHUB_TOKEN` in the gateway** (a fine-grained
  token for this one repository). Until then each pass runs and is recorded with
  `forge_error: GitHub is not configured`, and nothing changes. The auditor does not need it.
- **Merged code reaches the box by itself, and only through the canary.** Every half hour the House
  downloads `main` (public, so the box holds no GitHub credential), runs the running release's
  content checks on it and hands it to the in-box watchdog (`league/updater.py`,
  `league/watchdog.py`). A change to `real_money` is refused on that path: that switch is only ever
  the owner's own `floor_box.py deploy`.
- **Practice fills are kinder than real ones.** Alpaca's paper account fills market orders at the
  touch with no queue; the Kalshi shadow book fills a resting order only when the market trades
  through it, but models no depth. Rung 2 exists to measure the difference at $10 a position.
- **Alpaca fills are booked at the taker's fee.** Alpaca reports no fee and accepts every order
  asynchronously, so only the venue knows whether a limit order made or took; reconciliation
  returns a maker's difference to the House row.
- **An intent that would cross one of the House's own resting orders is refused**, not
  cancel-and-crossed: never a wash trade, at the cost of that fill.
- **Sail does not publish a price for web search**; the House charges agents $0.01 a query.
- **The first run's code is retained as a library.** The league imports parts of `ltcm/`; the rest
  (desks, committee, evolution, Foundry, lab) is no longer run, and its 1,753 tests still pass.
  Removing it safely is a job of its own.
- Expected dollars are small at this capital. The near-term product is verified edges and a
  standing, evidence-ranked recommendation of where the owner's next dollar belongs.

Blake Woods owns every position shown. Nothing published is investment advice.

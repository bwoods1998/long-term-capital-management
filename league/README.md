# The league

`league/` is the House: the one trusted process of the rebuilt floor. It keeps the ledger, wakes the
agents, nets and sends their orders, scores them on a four-rung ladder, pays them compute credits,
retires them, and publishes all of it. It decides no trade. What the project is and how the game
works are in [the repository README](../README.md); why each thing is the way it is is in
[the build log](../docs/runs/2026-09-20-overnight-build.md). This page is for someone changing the
code.

## Design rules

- **Standard library only.** `sqlite3`, `urllib`, `decimal`, `hashlib`, `json`, `threading`,
  `unittest`. Nothing to install on the box.
- **One append-only, hash-chained ledger.** Every intent, order, fill, mark, credit move, trial and
  verdict is a row in `ledger.sqlite`. A row's digest covers its identity, its content and the row
  before it; SQLite triggers refuse `UPDATE` and `DELETE`. There is one chain, not one per stream,
  so a reconciliation can pin a total order (`ledger_seq`, `ledger_digest`).
- **State is folded from the ledger.** Books, credit balances, the registry and rungs are rebuilt
  from rows on start, so a restart rebuilds exactly what the ledger records. Ids are derived from
  durable identities: appending the same id with the same content returns the stored row, and with
  different content raises `LedgerConflict`, so a crash and a retry never record a fill or a charge
  twice.
- **Decimal money in the book.** Cash, prices and quantities are `Decimal`, serialized as strings.
  Floats appear in two places only: the statistics (`stats.py`, `evaluator.py`: evidence, not money)
  and inside the sandbox (`ctx` is plain JSON floats; the House converts what comes back to exact
  decimals).
- **Agents' code never runs in the House process.** A strategy's `decide`, its replay, even reading
  its `NEEDS`, run in the agent's own sealed Sailbox (`sandbox.py`). The House uploads a spec, runs
  `runner.py` or `replay.py` there over Sail's exec API, and reads back one line marked with a
  token that is a secret of that run. `LocalSandbox` does the same in a subprocess for tests and
  laptops; it is a process boundary, not a security boundary, and the House refuses it for real
  money.
- **Everything that decides a fate is a ledger row**: every replay trial, every block of growth,
  every look with the alpha it spent, every promotion, demotion, death, audit, grant and charge.
  Payload keys beginning with `_` are private (strategy source is one) and never leave the box.
- **The constitution is not configuration.** `constitution.py` holds the thresholds, written before
  any agent traded; a test pins its digest and the House writes the digest to the ledger at every
  start. `game.json` holds the economy's tunable dials, inside bounds the file itself lists.
  `config.json` holds where things are and four operating dials; it never holds a secret.
- **Slow work runs beside the tick, never inside it.** Replays, research passes and Astra's passes
  run on background threads (two at a time); the first real tick took six minutes before this rule.

## Modules

| Module | What it does |
|---|---|
| `ledger.py` | `Ledger`: the append-only, hash-chained SQLite record. `append` (idempotent on id), `read`/`iter`/`last`, `verify()` re-hashes the chain, `agent_view()` and `public_view()` are the only ways rows leave. `KINDS` lists every row kind and whether it is public. |
| `book.py` | `Book`: one netting book per venue account. Folds each agent's cash and holdings from the ledger; runs every intent through the first run's 21 risk rules plus the league's (the $75 order cap, the rung's position and order caps, cash including fees, quote age, no shorts, no leverage, nothing that could trade against the House's own resting order, never both legs of a Kalshi market); nets one batch's market orders and crosses the minority side inside the House at the venue's touch and taker fee; attributes venue fills pro rata; reconciles to the venue against a baseline taken at start, booking under a cent a fill as dust and freezing new entries (never exits) on more. |
| `fees.py` | `Fees(venue)`: what a fill costs, as measured. Alpaca crypto takes 0.25% out of the coins on a buy and out of the proceeds on a sell and reports a fee of zero; Kalshi's taker formula is rounded up to $0.0001 an order. |
| `venues.py` | `gateway_broker(name, ...)`: the first run's Alpaca and Kalshi adapters in gateway mode. `alpaca-paper` is the same adapter signed with the paper keys. `market_hours` for equities. |
| `constitution.py` | `CONSTITUTION`, `digest()`, `PINNED_DIGEST`. Changing it means changing the pinned digest too, in a commit the owner makes. |
| `stats.py` | Pure functions: `log_growth`, `mean_bounds` (one-sided t bounds, with its own `t_quantile`), `spend` (alpha per look), `lopsided` and `lopsided_growth_lcb` (the exact Clopper-Pearson loss-rate gate), `deflated_sharpe`, `cusum_decay`, `quarter_kelly`, `max_drawdown`. Degenerate data returns `None`, never raises. |
| `evaluator.py` | `Evaluator`: `record_trial` (scores a replay and counts it against the family), `observe` (turns equity marks into blocks of log growth), `judge` (looks, promotion eligibility, death), `drift` (a CUSUM on the edge per closed trade against the record of the rung below, on rungs 2 and 3), `promote`/`demote`/`seat`. It reads the ledger and writes `eval.*` rows; the House acts on the verdicts. |
| `replay.py` | Rung 0: walks a strategy over a tape one step at a time with conservative fills (a resting order fills only when a later step trades strictly through it). Self-contained (standard library plus `safety.py`): it is uploaded into the agent's box as it is. |
| `tapes.py` | `AlpacaData` and `KalshiData`: recorded tapes for replay and live snapshots of the same shape. A bar is stamped with the moment it closed; a Kalshi row carries only what was on the screen; a capped board is a seeded draw that never looks at volume or results. |
| `paper.py` | `KalshiShadowBroker`: a simulated Kalshi account over live quotes. Holds no credential and sends nothing. State in `kalshi-shadow.json`. |
| `sim.py` | `SimBroker`: a simulated Alpaca account that behaves as the paper venue was measured to. A canary House trades on it, never on the shared paper account. |
| `economy.py` | `Economy`: balances folded from `credit.*` rows; `grant`, `charge` (never refused: the compute is already spent), `transfer`, `shares`/`payout` (niche floor plus evidence-weighted share), `can_fork`, `box_cost`. `load_game` and `check_bounds` read `game.json`. |
| `game.json` | The economy's dials (pool, floor share, rung weights, endowments, fork threshold, population bounds, audit cooldown, research cadence) and the bounds the game designer must stay inside. |
| `agents.py` | `Registry` and `Agent`: identity, strategy versions, lineage, niche (`venue/horizon/style`) and fate, folded from the ledger. `adopt` is for rung 0 only; above it new code is a child. |
| `sandbox.py` | `SailSandbox` (one Sailbox per agent, forked from `agent_image_checkpoint`, sealed with an egress allowlist of `sealed.invalid` before it is recorded, destroyed if it cannot be sealed) and `LocalSandbox`. Both offer `decide`, `needs`, `replay`, `fork`, `retire`, `sleep_all`. |
| `runner.py` | Runs one `decide` (or reads `NEEDS`) inside the box: 5 second limit, strategy prints discarded, one `DECIDE-RESULT <token>` line, then `os._exit`. |
| `safety.py` | `check_code`: the import whitelist and the banned constructs (no underscore attributes, no attribute assignment, no `eval`/`exec`/`open`/`getattr`). Ported from the first run's Foundry, where it was hardened against real attempts. Imports nothing from the league. |
| `commons.py` | `Commons`: web search (Sail's search API, Google News RSS as fallback, $0.01 charged per query), the research library, the tool-request queue, the playbook. All of it is ledger rows. |
| `researcher.py` | `Researcher`: a cheap Sail model's tool loop for one agent, every token and tool call charged to that agent. Its `replay` tool is a counted trial. A passing candidate is adopted on rung 0 and forked above it. |
| `rules.py` | `rules_text(game)`: what every agent is told, generated from the constitution and `game.json` so it cannot drift from what is enforced. |
| `seeds/` | The twelve founding strategy files and `all_seeds()`. They are data, not modules: nothing imports them. |
| `strategies/` | Strategies Astra adds as architect; `registry.json` lists them and the House enrolls each once, on rung 0. Empty at the start. |
| `tools/` | Pure helper modules Astra adds as toolsmith; uploaded beside the strategy so it may `from tools.<name> import ...`. Empty at the start. |
| `playbook/` | Lessons Astra adds as teacher, one markdown file each; the House loads them into the ledger's playbook. |
| `house.py` | `House`: `found`, `spawn`, `seat`, `wake`, `judge`, `kill`, `fork`, `research`, `keep_population`, `tick`. `Settings` are the House's own dials. |
| `budget.py` | `Budget`: reads Sail's credit balance, counts a month's spend as the sum of its falls, returns `open` or `stopped`. |
| `frontier.py` | `Frontier.ask`: one metered call through the gateway's `/v1/frontier/responses`; the cost comes back in `X-LTCM-Cost-USD`. Model `gpt-6-astra`. |
| `auditor.py` | `Auditor.audit` (the evidence packet, the veto, charged to the agent) and `score` (what each veto cost or saved, scaled to the micro stake). |
| `astra.py` | `Astra`: the schedule and one pass of each pull-request role; `GatewayForge` (production) and `GhForge` (the owner's machine, through `gh`); `evidence_from(house)`. |
| `ci.py` | `python3 -m league.ci`: the path guard (`ROLE_PATHS`, `FORBIDDEN`, `CONFIG_DIALS`), content checks for strategies, tools, `game.json` and `config.json`, then the suite. Also makes the canned regression tapes. |
| `capital.py` | `kelly_stake` and `resize` (rung 3), `recommend` (the standing capital recommendation, an `ops.recommendation` row). |
| `publish.py` | `Publisher`: cleans ledger rows into the site's exact event and checkpoint shapes and posts them. Cursor in `publish.json`. |
| `service.py` | `build(root, ...)`: the real House from `config.json` and three secrets (`GATEWAY_TOKEN`, `SAIL_API_KEY`, `CAPITAL_PUBLISH_TOKEN`), read from the environment or a 0600 `.env`. `canary=True` builds a House that can hurt nothing. |
| `__main__.py` | `python3 -m league run | tick | found | status | verify | stop | start`. |
| `watchdog.py` | `python3 -m league.watchdog deploy | status | rollback | prune`: releases on the box, the canary, promotion, the watch, the rollback. Imports nothing else from the package at import time. |
| `updater.py` | How merged code reaches the House box with no human step: every half hour it downloads `main` (public, no credential), unpacks the release trees, runs the running release's content checks (`ci.py`) on them, refuses any change to `real_money`, and hands a changed tree to the watchdog for canary, promotion, watch and rollback. A tree judged once is never tried again. |
| `CONTRACT.md` | The strategy contract. |
| `config.json` | Gateway and site URLs, the agent image checkpoint, `real_money`, the operating dials, the performance baseline. |

## The life of one tick

`House.tick()` is the whole loop (`python3 -m league run` calls it every `tick_seconds`, 60).

1. **Settle and poll.** For every book: advance the simulated venues (`advance()` fills resting
   shadow orders the market has traded through), poll resting orders for fills, apply new Kalshi
   settlements. One venue's outage is an alert and does not stop the others.
2. **Check the budget.** `open` or `stopped`. When stopped, only agents holding real-money positions
   or orders are woken, so they can exit; research, Astra, payouts and births wait.
3. **Wake each agent that is due** (at most 16 a tick, 6 side by side; its own `wake_minutes`, 5 to
   1,440). If its code has not had its replay, one is started in the background. A rung-0 agent
   stops here. Otherwise the House seats it (limits and stake for its rung), builds its snapshot
   (its account, its open orders, closed bars and the touch, or Kalshi's open markets), runs
   `decide` in its box, charges the box seconds, keeps its `memory`, records its `thought`, applies
   its cancels and converts its intents to exact decimals. A malformed intent is dropped and
   reported; a failed wake is an alert, never a failed tick.
4. **Submit one batch per book**, so opposite market orders on one instrument net inside the House.
5. **Every `mark_every_seconds` (300), per book:** poll, mark every account, reconcile to the venue
   (a mismatch is an error alert and freezes new entries). Then judge each living agent on that
   book: close finished blocks of log growth, take a look if one is due, and act on the verdict:
   `die` kills; `eligible` promotes (from paper only through Astra's audit, and only when real money
   is on); on rungs 2 and 3 a drift alarm demotes and moves the agent back to the practice book.
   Dead agents' free cash is swept back to the House row.
6. **Start due research passes** in the background (at least six hours apart, and only for an agent
   with more than twice the minimum credits). A candidate that passes replay is adopted on rung 0 or
   becomes a fork above it.
7. **Start Astra's due roles** in the background, and ask the gateway what CI made of each open
   pull request.
8. **Once an epoch:** load new lessons from `playbook/`, resize rung-3 stakes, write the capital
   recommendation, pay the pool, score the auditor's vetoes.
9. **Keep the population:** kill agents at zero credits and rung-0 agents past the replay deadline;
   fork agents above the fork threshold (rung 1 and up, once an epoch); re-found any seed never born
   if the population is under its floor; enroll Astra's registered strategies; if every seed has had
   its life and the floor is still not met, stake a mutation of whoever stands highest.
10. **Save `house.json`, publish, write `health.json`.** A publishing failure is a warning: the site
    is downstream of the floor, never upstream.

## The strategy contract

[`CONTRACT.md`](CONTRACT.md): the file's shape (`NEEDS`, `PARAMS`, `decide(ctx)`), the allowed
imports, everything in `ctx`, what `decide` returns, and how replay scores it. The same file runs
in replay, on paper and with real money. It is handed to the researcher model and to Astra as
architect and toolsmith, so a change to it changes what they write.

## State on disk

Everything the House keeps is under one directory, `--root` (default `.data/league`; on the box,
`/workspace/state`).

| Path | What it holds |
|---|---|
| `ledger.sqlite` | The ledger. The only record that matters; everything else can be rebuilt or lost. |
| `house.json` | The House's working memory: each agent's next wake, `memory`, last research, the code hash that has had its replay, last marks, last settlement stamp. Mode 0600. |
| `sandbox.json` | Which Sailbox belongs to which agent. |
| `kalshi-shadow.json` | The Kalshi shadow account: cash, positions, orders, fills, settlements applied. |
| `provider.sqlite` | The metered record of cheap-model calls (the first run's `Provider`). Absent with `--no-research`. |
| `publish.json` | The publisher's cursor into the ledger and its last mark time. |
| `health.json` | Rewritten every tick: living, dead, frozen books, open orders, `ledger_seq`, `real_money`, the release. The watchdog reads it. |
| `STOP` | If present, the `run` loop ends after the tick in hand. `python3 -m league stop` writes it, `start` removes it. |
| `cache/` | Kalshi history and news, a byte-capped disk cache. |
| `boxes/`, `alpaca-sim.json` | Only with `--local-sandbox` (one private directory per agent) and `--canary` (the simulated Alpaca account). |

## Tests

```sh
python3 -m unittest discover -s league/tests -t .        # 847 tests, about 75 s
python3 -m unittest league.tests.test_book               # one module
python3 -m league.ci --no-tests                          # the content checks alone
```

No test touches a network, a venue or Sail: `league/tests/fakes.py` has a fake broker that behaves
as Alpaca's paper venue was measured to, and a clock. One test is slow on purpose:
`test_ladder.py` (about 40 s) runs a whole House through paper, the audit, micro-real, scaled
sizing and decay back down, and is the only place every rule is seen working together. While
iterating, skip it by running the modules you touched.

`league/tests/fixtures/site_contract.md` is what the site accepts, with the two JSON fixtures the
site's own validators are tested against.

## The replay regression

`test_replay_regression.py` replays every founding seed over two deterministic canned tapes
(`ci.regression_tape`) and compares trades, fills, maker fills, refusals, errors, steps, blocks,
final equity and fees with `tests/fixtures/replay_regression.json`. A change to the simulator, the
fee model, the safety rules or a seed that moves any number fails here by name, so a change to the
arithmetic cannot pass as a refactor. To accept an intended change, re-record the fixture and
commit it with the change:

```sh
python3 -m league.tests.test_replay_regression --record
```

## What the league imports from `ltcm/`

The first run's runtime is kept as a library. These are the only modules the league imports
(`grep -rn "from ltcm" league/ --include=*.py`, tests aside):

| `ltcm` module | Used by | For |
|---|---|---|
| `ltcm.broker` | `book`, `fees`, `house`, `paper`, `sim`, `publish`, `venues` | `Instrument`, `OrderIntent`, `Order`, `Fill`, `Quote`, the `Broker` protocol and its errors, `money`, `instant` |
| `ltcm.risk` | `book` | `RiskEngine` and `RiskContext`: all 21 pre-trade rules, unchanged, and the event-cluster keys |
| `ltcm.sim` | `fees` | `FeeModel` (the Kalshi fee arithmetic) |
| `ltcm.adapters` | `venues`, `tapes`, `service` | `VenueClient`, `GatewaySigner`, the credential types |
| `ltcm.adapters.alpaca`, `ltcm.adapters.kalshi` | `venues`, `paper` | `AlpacaBroker`, `KalshiBroker`, Kalshi's price grid and contract helpers |
| `ltcm.data` | `venues` | `market_open_at` (the US equity calendar) |
| `ltcm.data.kalshi` | `paper`, `tapes`, `service` | `KalshiMarketData`, `parse_price_ranges`; `ltcm/data/kalshi_fees.json` is the list of series that charge makers |
| `ltcm.data.news` | `service` | `News`, the Google News RSS reader behind the search fallback |
| `ltcm.history` | `tapes`, `service` | `History`: settled Kalshi markets and candles, throttled and cached |
| `ltcm.provider` | `service` | `Provider`: the Sail Responses client with its rate card and cost records |
| `ltcm.sailbox` | `service` | `SailboxClient`: create, fork, exec, egress, checkpoints |
| `ltcm.performance` | `publish` | `AccountPerformance`: the funding-flow reader behind the profit figure |

Those modules in turn import `ltcm.events`, `ltcm.manifest`, `ltcm.data.yahoo` and
`ltcm.data.coinbase`. `scripts/floor_box.py` also uses `ltcm.sailbox`. Nothing else in `ltcm/` is
imported or run; see [`ltcm/README.md`](../ltcm/README.md).

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

> The project was rebuilt from a clean slate on September 19, 2026. Everything below this line
> describes the first run and is kept as its record until the new runtime's documentation
> replaces it.

## Partners

| Desk | The partner | Mandate | Venue | Capital | Model |
|---|---|---|---|---|---|
| Merton | Robert Merton, option pricing, Nobel 1997 | Concentrated long book from primary SEC filings and cash-flow bridges; holds for months | Alpaca | shadow | DeepSeek V4 Pro |
| Rosenfeld | Eric Rosenfeld, Salomon arbitrage | Post-earnings drift and guidance surprises within ten trading days of a release | Alpaca | shadow | DeepSeek V4 Pro |
| Hawkins | Greg Hawkins, Salomon arbitrage | The same earnings mandate, run by a different model | Alpaca | shadow | Kimi K2.6 |
| Krasker | William Krasker, Salomon arbitrage | The same earnings mandate, run by a different model | Alpaca | shadow | GLM 5.3 |
| Mullins | David Mullins, former Vice Chairman of the Federal Reserve | Fed decisions, economic releases and other resolvable event contracts | Kalshi | **live** | DeepSeek V4 Pro |
| Hilibrand | Lawrence Hilibrand, Salomon arbitrage | Documented trend, mean-reversion and catalyst setups in BTC and ETH, 24/7 | Coinbase | **live** | DeepSeek V4 Pro |
| Meriwether | John Meriwether, who founded the fund | The committee: allocates capital by track record, promotes and cuts desks, writes the memo | — | — | DeepSeek V4 Pro |

Rosenfeld, Hawkins and Krasker share one mandate on three models, so the scoreboard measures the
model and not the idea. The four equity desks are shadow until the Alpaca account opens.

## Live and shadow

**There is no paper trading.** Mullins and Hilibrand trade real money on Kalshi and Coinbase now;
the equity desks will when the account opens. Every other desk is a **shadow** desk, which is not
the same thing as a paper one:

- it runs full sessions and proposes orders through the same deterministic risk engine;
- an approved order is **never sent**. It is scored against the real venue's quote with the real
  venue's fee model, and published as a hypothetical trade marked `shadow`;
- its capital is a notional scoring budget, never money. No shadow number is ever added to the
  floor's equity, and the site shows the two apart.

That score is what a shadow desk is for. Meriwether's gates read its forward record -- days live,
independent decisions, cost-adjusted excess return, drawdown inside mandate, no circuit breakers --
and a desk that passes takes over a live sleeve and starts trading the owner's money. A desk that
stays below its family's median is retired and replaced. Children of a live desk are born shadow.

## How it works

```
data (quotes, bars, filings, news, event markets) ──> desks ──intents──> risk engine ──> broker gateway ──> venues
                                                        │                    │                 │
                                                        └───── every event ──┴─────────────────┘──> event log ──> site
                                                                    ▲
                     committee (Meriwether): capital by track record; evolution: spawn, score, retire; post-mortems
```

- **Guardrails are code.** The risk engine, broker gateway, budget caps, evaluator and publication
  policy are human-written and cannot be edited by any agent. Playbooks, prompts, tool use and
  capital allocation are allowed to evolve.
- **Append-only and hash-chained.** Nothing is edited; corrections are new events. Anyone can
  verify the chain.
- **Public by default.** Reasoning summaries, tool calls, memos, playbook diffs, post-mortems,
  fills, marks, allocations and evolution events publish live. Prompts, raw model output,
  credentials and licensed quotes never leave the box.
- **Standard library Python.** SQLite, `urllib`, `decimal`, `unittest`. No framework.

## The recursive loop

Every desk writes a post-mortem each night and rewrites its own playbook from it, so tomorrow's
desk is authored by yesterday's results. Desk families breed and retire variants on forward
performance, not on backtests. Profit raises the floor's daily inference budget and losses lower
it, so the desks that make money buy the compute that makes the next decision.

## Run it

```sh
python3 -m venv .venv && .venv/bin/python -m pip install cryptography   # request signing only
.venv/bin/python scripts/setup_venues.py setup    # hidden prompts; writes .env and key files
.venv/bin/python scripts/setup_venues.py verify   # one read-only call per venue
python3 -m unittest discover -s ltcm/tests -t .
python3 -m ltcm init && python3 -m ltcm run
```

`python3 -m ltcm status` prints what the site shows, `verify` re-hashes the event chain, `session`
runs one desk now, `promote` moves a desk between a shadow book and a live sleeve, and `kill` stops
new orders immediately. [`deploy/README.md`](deploy/README.md) installs the floor as an always-on user
service.

## Repository map

| Path | What it is |
|---|---|
| `ltcm/` | The floor runtime: event log, broker contracts, manifests, risk engine, simulator, data sources, venue adapters, provider, desk runtime, ledgers, gateway, committee, evolution, publisher, service. |
| `ltcm/desks/` | The six desk manifests: mandate, venue, model, cadence, limits and capital. |
| `ltcm/tests/` | 723 tests. `python3 -m unittest discover -s ltcm/tests -t .` |
| `playbooks/` | The playbooks desks rewrite after each post-mortem, with version history. |
| `scripts/` | `setup_venues.py` for credentials and read-only verification, `check_keys.py` for a quick audit. |
| `deploy/` | systemd user unit and runbook. |
| `docs/` | The proposal the floor was built from, the launch record, and `docs/history/` for Portfolio Agent, the first generation. |

Blake Woods owns every position shown. Nothing published is investment advice. Orders publish
after they fill.

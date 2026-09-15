# Long Term Capital Management

**An AI hedge fund that teaches itself to be as profitable as possible, with no human in the loop,
in public.** Six desks, each named after a partner in the 1998 fund, run their own mandate, venue,
model, playbook and sub-ledger on real money. A deterministic risk engine sits between every desk
and every broker; a rules-based committee moves capital between desks by track record; every night
each desk reviews its own trades and rewrites its playbook, and desk families breed and retire
variants on forward results. Every thought, tool call, memo, playbook diff, fill and allocation is
streamed to [blakewoods.us/capital](https://blakewoods.us/capital/) and kept in a hash-chained
public record. The goal is not to beat an index. It is to find out how far a fully autonomous,
self-improving fund can get, and to show all of it.

The name is a joke and a warning. No affiliation with the 1998 fund, its partners or its estate.

[Live floor](https://blakewoods.us/capital/) · [Runtime design](ltcm/README.md) ·
[The plan](docs/proposals/2026-09-14-the-floor.md) · [Docs](docs/README.md)

## Partners

| Desk | The partner | Mandate | Venue | Model |
|---|---|---|---|---|
| Merton | Robert Merton, option pricing, Nobel 1997 | Concentrated long book from primary SEC filings and cash-flow bridges; holds for months | Alpaca | DeepSeek V4 Pro |
| Rosenfeld | Eric Rosenfeld, Salomon arbitrage | Post-earnings drift and guidance surprises within ten trading days of a release | Alpaca | DeepSeek V4 Pro |
| Hawkins | Greg Hawkins, Salomon arbitrage | The same earnings mandate, run by a different model | Alpaca | Kimi K2.6 |
| Krasker | William Krasker, Salomon arbitrage | The same earnings mandate, run by a different model | Alpaca | GLM 5.3 |
| Mullins | David Mullins, former Vice Chairman of the Federal Reserve | Fed decisions, economic releases and other resolvable event contracts | Kalshi | DeepSeek V4 Pro |
| Hilibrand | Lawrence Hilibrand, Salomon arbitrage | Documented trend, mean-reversion and catalyst setups in BTC and ETH, 24/7 | Coinbase | DeepSeek V4 Pro |
| Meriwether | John Meriwether, who founded the fund | The committee: allocates capital by track record, promotes and cuts desks, writes the memo | — | DeepSeek V4 Pro |

Rosenfeld, Hawkins and Krasker share one mandate on three models, so the scoreboard measures the
model and not the idea. Every desk starts on paper; the committee's gates decide when one earns a
live sleeve and when it is cut.

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
runs one desk now, `promote` moves a desk to a live sleeve, and `kill` stops new orders
immediately. [`deploy/README.md`](deploy/README.md) installs the floor as an always-on user
service.

## Repository map

| Path | What it is |
|---|---|
| `ltcm/` | The floor runtime: event log, broker contracts, manifests, risk engine, simulator, data sources, venue adapters, provider, desk runtime, ledgers, gateway, committee, evolution, publisher, service. |
| `ltcm/desks/` | The six desk manifests: mandate, venue, model, cadence, limits and capital. |
| `ltcm/tests/` | 474 tests. `python3 -m unittest discover -s ltcm/tests -t .` |
| `playbooks/` | The playbooks desks rewrite after each post-mortem, with version history. |
| `scripts/` | `setup_venues.py` for credentials and read-only verification, `check_keys.py` for a quick audit. |
| `deploy/` | systemd user unit and runbook. |
| `docs/` | The proposal the floor was built from, the launch record, and `docs/history/` for Portfolio Agent, the first generation. |

Blake Woods owns every position shown. Nothing published is investment advice. Orders publish
after they fill.

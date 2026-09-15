# Woods Capital Management

**A public floor of autonomous AI portfolio managers, trading real money with every thought on display.**

Woods Capital is a roster of *desks*: independent agents with their own mandate, venue, model,
playbook and sub-ledger. A deterministic risk engine sits between every desk and every broker.
A rules-based committee (its agent is called **Helm**) moves capital between desks by track
record. An evolution loop breeds and retires desk variants on forward results, and each desk
rewrites its own playbook after a daily post-mortem. Everything a desk thinks, reads, proposes and
fills is streamed to [blakewoods.us/capital](https://blakewoods.us/capital/) as it happens and kept
in a hash-chained public record. Profit buys compute: the floor's daily inference budget rises
with realized gains and falls with losses.

Blake Woods owns every position shown. Nothing published is investment advice. Orders publish
after they fill, never before.

[Live floor](https://blakewoods.us/capital/) · [Runtime design](woodscapital/README.md) ·
[The plan](docs/proposals/2026-09-14-the-floor.md) · [First generation](docs/README.md)

## The floor

| Desk | Mandate | Venue | Skill test |
|---|---|---|---|
| Filings | Concentrated long book from primary SEC filings and cash-flow bridges; holds for months | Alpaca | excess return vs S&P 500 |
| Earnings (three variants on DeepSeek, Kimi and GLM) | Post-earnings drift and guidance surprises within ten days of a release | Alpaca | per-event alpha |
| Kalshi | Base-rate forecasts on economic, weather and political event contracts | Kalshi | Brier score vs market price |
| Crypto | Documented trend, mean-reversion and catalyst setups in BTC and ETH, 24/7 | Coinbase | return over drawdown |

Every desk starts on paper. The committee's gates decide when a desk earns a live sleeve, when it
is cut, and when it is retired to make room for a mutated successor.

## How it works

```
data (quotes, bars, filings, news, event markets) ──> desks ──intents──> risk engine ──> broker gateway ──> venues
                                                        │                    │                 │
                                                        └───── every event ──┴─────────────────┘──> event log ──> site
                                                                    ▲
                     committee (Helm): capital by track record; evolution: spawn, score, retire; post-mortems
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

## Run it

```sh
python3 -m venv .venv && .venv/bin/python -m pip install cryptography   # request signing only
.venv/bin/python scripts/setup_venues.py setup    # hidden prompts; writes .env and key files
.venv/bin/python scripts/setup_venues.py verify   # one read-only call per venue
python3 -m unittest discover -s woodscapital/tests -t .
python3 -m woodscapital init && python3 -m woodscapital run
```

`deploy/README.md` installs the floor as an always-on user service. `python3 -m woodscapital kill`
stops new orders immediately; `verify` re-checks every hash chain.

## Repository map

| Path | What it is |
|---|---|
| `woodscapital/` | The floor runtime: event log, broker contracts, manifests, risk engine, simulator, data sources, venue adapters, Sail provider, desk runtime, ledgers, gateway, committee, evolution, publisher, service. |
| `woodscapital/desks/` | Desk manifests (JSON). `playbooks/` holds the playbooks desks edit, with version history. |
| `scripts/` | Credential setup and verification, first-generation host tools. |
| `deploy/` | systemd unit and runbook. |
| `docs/` | Design proposal, first-generation architecture, evaluation notes, run records and lessons. |
| `portfolio_runtime/`, `control-plane/`, `experiments/` | The first generation (Portfolio Agent): one S&P 500 paper portfolio on Sail with a Cloudflare supervisor. Retires into `docs/history/` after its final scheduled week. |

## First generation

Woods Capital grew out of **Portfolio Agent**, an autonomous S&P 500 paper portfolio built on
Sail inference, Sailboxes, Supercache and Voyages. Its source-checked research bank across 502
companies seeds the Filings desk. Its records stay at [docs/](docs/README.md) and
[blakewoods.us/portfolio](https://blakewoods.us/portfolio/).

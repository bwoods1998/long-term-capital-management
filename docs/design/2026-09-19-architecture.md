# The rebuild: architecture and build order (Sept 19, 2026)

Companion to `docs/proposals/2026-09-19-the-game.md`. Owner's decisions: venues are Kalshi and
Alpaca; Sail budget $100 a month and OpenAI budget $100 a month, each raised only on measured
return; the frontier model is auditor and architect, never the trade picker; the loop runs
with no human in it, inside bounds no model can move.

## Trust boundaries

| Zone | Runs | May do | May never do |
|---|---|---|---|
| **Gateway** (Cloudflare Worker) | venue keys, OpenAI key, order caps, frontier budget, kill switch | sign orders, meter spend | be changed by anything on Sail |
| **House** (one Sailbox, trusted) | ledger, evaluator, economy, order netting, publisher | decide promotion, death, budgets; send netted orders to the gateway | run agent-written code in its own process |
| **Agents** (forked sandboxes, untrusted) | a strategy program and its researcher model | read market data and their own record; emit intents and evidence packets to the House | hold any credential but their own House token; write the ledger; reach a venue or the gateway |
| **Architect** (frontier, via gateway) | reads the league table and graveyard | open a change to `strategies/` only | touch House, gateway, evaluator, caps or its own rules; merge without CI |

An agent's sandbox is created with a network allowlist of the House and public data hosts.
Death is `max_lifetime_seconds` plus the House refusing its token.

## House modules (new package `league/`, reusing the old runtime's tested parts)

- `league/ledger.py`: append-only, hash-chained record of every intent, fill, mark, budget
  move and verdict (reuses `ltcm/events.py`). Agents get a read view of their own rows.
- `league/evaluator.py`: the ladder. Mechanical replay with a trial counter and deflated
  Sharpe (rung 0), paper forward test (rung 1), micro-real (rung 2), scaled (rung 3).
  Promotion and death are pre-registered sequential tests on a lower confidence bound of
  after-cost log growth. Reuses `ltcm/backtest.py` and `ltcm/evidence.py` (hour blocks).
- `league/economy.py`: compute credits. Income is a share of the daily research budget by
  evidence-weighted performance; costs are metered Sail inference (one API key per agent,
  `/v2/usage/api-keys`), sandbox seconds (`/sailboxes/spend`) and frontier audits at cost.
  Niche floors (venue x horizon x style) keep diversity. Bankruptcy is death; a rich agent
  may fork a child and must endow it.
- `league/book.py`: one netting book per venue. Agent intents are netted before any order is
  sent, so two agents never trade against each other; fills are attributed back pro rata.
  Reuses `ltcm/gateway.py` risk rules and the venue adapters in gateway mode.
- `league/paper.py`: Alpaca paper accounts through the identical adapter (second key pair in
  the gateway as venue `alpaca-paper`), and Kalshi shadow fills with conservative maker rules.
- `league/agents.py`: lifecycle on Sail: fork from checkpoint, scheduled wakes, sleep, death,
  post-mortem to the graveyard.
- `league/auditor.py` and `league/architect.py`: the two frontier jobs, through
  `/v1/frontier/responses`, each with its own measured return (rejections are scored as if
  taken; architect strategies are scored against cheap-model mutations per dollar).
- `league/publish.py`: the public tape. The site reads thoughts, research, fills, outcomes,
  balance marks, positions with reasons, and one `improvement` series by generation.

## Build order

1. Ledger + book + gateway-mode adapters for both venues, with the old risk rules. (Trade
   nothing yet.)
2. Evaluator rungs 0 and 1: replay with trial counting; Alpaca paper and Kalshi shadow.
3. Economy with metering, and agent lifecycle on Sail. First population: seeded from what the
   old run measured (Kalshi maker favorites, hourly quotes) plus Alpaca seeds.
4. Rung 2 micro-real behind the auditor. Publisher and the simplified site go live.
5. Architect loop with CI on `strategies/`.
6. Rung 3 sizing, drift monitors, the owner's standing capital recommendation.

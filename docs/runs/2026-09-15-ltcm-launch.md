# Long-Term Capital Management launch record · September 15, 2026

Overnight build from the Portfolio Agent repository into **Long-Term Capital Management**: one
project, one repository, one site section. This is the state at hand-off, written before the
owner woke up.

## What is running

- **Floor service**: `ltcm.service` (systemd user unit on the MacBook) runs
  `python -m ltcm run` every 30 seconds: due desk sessions, paper broker ticks, ledger
  marks every five minutes, circuit breakers, committee and evolution on their slots, publication
  to the site every loop. `deploy/README.md` has the commands. `python3 -m ltcm status`
  prints the same view the site shows.
- **Mode: paper for every desk.** Six desks are funded from the floor's $5,000 of virtual
  capital: Filings, Earnings on DeepSeek, Earnings on Kimi, Earnings on GLM, Kalshi and Crypto.
  Sessions run on each desk's cadence (Crypto every six hours around the clock; Kalshi three
  times a day including weekends; the equity desks on weekday market hours), and every desk runs
  a **post-mortem session at 21:30 local** that rewrites its playbook.
- **Public site**: https://blakewoods.us/capital/ (floor, live tape, leaderboard), per-desk pages
  at `/capital/desk/?id=<desk>`, the committee at `/capital/committee/`. The tape updates over a
  WebSocket with polling fallback. The checkpoint and events APIs are public and cached for a
  few seconds.
- **Budget**: floor cap $15 a day of Sail inference plus 25% of trailing seven-day realized
  profit, ceiling $60; each desk $2.50 to $4 a day. Manual shakedown sessions cost about 2 to
  6 cents each. The reserve floor stops new requests when the Sail balance is under $10.

## What was verified live

| Check | Result |
|---|---|
| Alpaca paper account read | ACTIVE, $100,000 simulated cash, options level 3, crypto enabled |
| Kalshi account read | balance $492.29; positions, orders and fills endpoints answer |
| Coinbase account read | $487.50 USD; positions, orders and fills endpoints answer |
| Coinbase order path | 0.0001 BTC bought and sold through the adapter; fees $0.09 each way; balance reconciled |
| Kalshi order path | **not exercised live**; request shape verified against the v2 documentation only |
| Sail desk sessions | Kalshi and Crypto desks ran full sessions with tool calls, visible reasoning and memos |
| Paper fills | BTC round trip through risk engine, simulator, ledger and site publication |
| Site publication | events and checkpoints accepted; 474 runtime tests and 84 site tests pass |

## What is deliberately not on

**Real money.** Promoting the Kalshi and Crypto desks to their live sleeves was prepared but not
executed: the automated session's permission classifier refused the real-money step, and that is
the owner's decision to make anyway. Everything else is ready. To go live:

```sh
cd ~/Work/long-term-capital-management
# 1. enable the venues (edit "live_venues": ["kalshi", "coinbase"] in ltcm/config.json)
# 2. promote the desks; each promotion is a public event on the committee page
.venv/bin/python -m ltcm promote kalshi-01 --to live --reason "first live sleeve"
.venv/bin/python -m ltcm promote crypto-01 --to live --reason "first live sleeve"
# 3. restart the floor
systemctl --user restart ltcm.service
```

The two manifests already carry $200 live sleeves (`capital.usd`), so the first live orders are
capped at $30 per Kalshi order and $100 per crypto position by the risk engine. Suggested first
step: watch the first Kalshi order on the committee page, since that path is unproven.

## Known gaps

- The Kalshi desk trades the YES leg only until the NO-leg price scaling on the v2 order
  endpoint is confirmed with a live order.
- The Kalshi market index is a background sweep of open markets closing within 60 days; the
  first search after a restart can be thin for up to a minute.
- Alpaca is paper-only; live equity trading needs the live key pair in `.env` and `"paper": false`.
- The first-generation Portfolio Agent week is still running on its Sailbox through Friday and
  spends roughly $70 a day of the same Sail balance. Pausing it early is a one-command decision:
  `scripts/week_host.py pause --directory .data/runtime/week-20260914-v6`.
- Option chains, futures and Schwab are not wired yet.

## Where things are

- Runtime: `ltcm/` (README documents modules, event kinds, budget and publication policy).
- Desk manifests: `ltcm/desks/`; playbooks: `playbooks/` with version history.
- Data and state: `.data/ltcm/` (events, provider, memory, paper books, health). Backups of
  this directory are not yet automated; the event log verifies with `python3 -m ltcm verify`.
- Credentials: `.env` and `.data/ltcm/keys/` (owner-only). `scripts/setup_venues.py verify`
  re-checks every venue read-only.

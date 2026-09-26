# Long-Term Capital Management

**A swarm of AI agents trading level-3 options on one brokerage account, trained around the clock in
a Gym of real recorded quotes, judged by the live market.** Public page:
[blakewoods.us/capital](https://blakewoods.us/capital/).

The project narrowed to this one goal on September 26, 2026. How it got here (a paper portfolio, chat
desks on Kalshi and Coinbase, a league of strategy programs) is in [archive/](archive/README.md).

## The goal

A swarm of AI agents trading anything available with level-3 options on the owner's Alpaca account
(the "Brokerage Account" on the public page), profitably: **options returns greater than every
input cost** (Sail, OpenAI, ThetaData and the market-data subscription). The money in the account
may all be lost; the evidence must stay honest.

## The one number

**Net = the options book's realized P&L after every fee, minus every input cost.** Deposits and
withdrawals are never profit. The scoreboard reports Net daily, weekly and since the reset
(Sept 26, 2026, 06:25:30Z, equity $481.65). At the steady-state budgets the inputs cost about
$565-740 a month, so the bar falls as the account grows, and compute drops to its floor whenever
the forward record does not pay for it. A change that cannot say how it raises Net does not ship.

## The game

The full design is [docs/design.md](docs/design.md); the run that is building it is
[docs/goals/LTCM_OPTIONS_SWARM.md](docs/goals/LTCM_OPTIONS_SWARM.md).

- **The Gym.** One-minute NBBO for the option contracts near the money, 0-14 days to expiry, across
  the universe (SPY, QQQ, IWM, XSP and SPXW, then about 20 liquid single names and ETFs), from
  ThetaData, stored as Parquet on sealed Sailboxes. A vectorized engine replays agent programs over
  it at roughly 100,000 times real time per core, fills each leg against the recorded quote on the
  minute after the decision (the natural price by default), and applies the venue's rules: expiry
  cutoffs, liquidation, exercise, assignment, fees, buying power.
- **Agent time.** The swarm learns in the Gym at thousands of times the market's speed, nights and
  weekends included, and uses the live market as the judge of what it learned, not as its teacher.
  Every clock is set by what an agent can learn from it: seconds for a revision, hours for
  selection, a night for a new forward day.
- **The agents.** An agent is one family: a mechanism (why the trade should make money), a
  defined-risk structure type (verticals, condors, butterflies, straddles, calendars, single long
  options) and a slice of the universe. A researcher model owns it, keeps a notebook, and revises
  one Python program (`NEEDS`, `PARAMS`, `decide(ctx)`). A program never sees the calendar date, so
  the sealed holdout cannot be recognized. Programs live in the House's state, never in git.
- **The loops.** Inner (a researcher revises and reruns on Train, in minutes); tournament (hourly:
  validation runs, a bandit that moves Gym time and model calls to evidence, forks and retirements);
  architect (every four hours, new families from the leaderboard and the graveyard); gate (review,
  audit and one holdout look when a family meets the validation line); nightly forward (each new
  trading day, for Candidates only); live (market hours: every Candidate in shadow, Probes and Sized
  families on real money); post-mortem (after each close).
- **Evidence.** Train 2022-2024, Validation 2025, a sealed holdout from Jan 2 to Sept 25, 2026, and
  every day after that forward. Every Gym evaluation counts as a trial. A family passes validation
  with at least 100 trades on 60 days, a t of 2 on P&L per dollar of maximum loss, a deflated Sharpe
  probability of 0.95 for its trial count, 3 of 4 quarters positive and a profit at 1.5x the
  half-spread; then one holdout look per version, corrected for every look the swarm has made, and
  researchers hear only pass or fail. The forward record sizes money.
- **Bands.** Gym, Candidate (live shadow only), Probe (real, small), Sized (real, by evidence),
  Retired.
- **Money rules, in a paragraph.** Everything is sized by maximum loss, never by premium: a Probe
  risks 3% of equity a structure (one contract when its maximum loss is at most $60), three open
  structures and 12% per family; a Sized family risks by quarter-Kelly on its forward record's lower
  bound, up to 10% a structure and 30% a family; the whole book at most 70% of equity. No new entries
  after a 25% day; real money pauses at a 50% drawdown from the peak. Real money trades only the
  five structure types the venue closes in one order, and credit types only from $2,000 of equity.
  The House nets every agent's intents into one order stream, never crosses itself, stays under 250
  orders a day and closes expiring structures before the venue's cutoffs. Real money flows only
  under the owner's grant `options-swarm-20260928`, pinned to the money rules, behind the gateway's
  caps and kill switch.

## Where it runs

| Piece | What | Where |
|---|---|---|
| The House | the loop, the ledger, the books, the tournament, the gate, the live tick, the publisher | one Sailbox (size s) |
| The gateway | the account's and OpenAI's keys, caps by order, the OpenAI month, the kill switch, an outside watchdog | a Cloudflare Worker |
| The data box | ThetaData downloads into the Gym store; the nightly forward day | one Sailbox (size l), asleep when idle |
| The Gym | sealed forks of the Gym image (Train and Validation only), 4-8 at a time | Sailboxes (size l) |
| The gate | a sealed fork with the holdout and forward days | one Sailbox, used by the gate only |
| The site | the public page | `personal-site`, a Cloudflare Worker |

Vendors: **Alpaca** (the account, level 3; live OPRA quotes and SIP bars through Algo Trader Plus;
a paper account for the multi-leg route), **ThetaData** Options Standard (historical option quotes),
**Sail** (the boxes, and open models for the researchers: DeepSeek, Kimi), **OpenAI** through the
gateway (GPT-6 Sol reviews programs; GPT-6 Astra is the architect, the gate's auditor and the
post-mortem).

## The repository

As it will stand after the prune (Wave 2b, after Monday Sept 28's close); until then the legacy
`ltcm/` package, `playbooks/` and the old league's modules are still here.

| Path | What it is |
|---|---|
| `league/` | the House: `house.py` (the tick), `ledger.py`, `book.py`, `allocator.py`, `constitution.py` (the money rules and their digest), `live_trading.py` (the grant), `publish.py`, `service.py`, `watchdog.py`, `stats.py`, `config.json` |
| `league/gym/` | the Gym: the store reader, the engine, fills, the venue's rules, greeks, the batch runner, the sealed-box driver; the program contract in `PROGRAM.md` |
| `league/swarm/` | the swarm: researchers, the tournament and bandit, the architect, the gate, the Sail guard, the Gym pool |
| `league/CONTRACT.md` | the options strategy contract every researcher reads (under 20 KB) |
| `league/tests/` | the tests |
| `gateway/` | the Worker ([its README](gateway/README.md)) |
| `scripts/` | `floor_box.py` (the House's box), `gateway_admin.py` (the kill switch), `live_trading.py` (the grant), `scripts/data/` (the data box, the backfill, the images, the nightly job, the store checks) |
| `deploy/` | [how the House runs on its box](deploy/README.md) |
| `docs/` | [design.md](docs/design.md), [operations.md](docs/operations.md), `goals/` (the run's plan), `runs/` (run records) |
| `archive/` | the history and the documents of earlier generations |
| `CHANGELOG.md` | one entry per deploy |

## Running the tests

Python 3.11 or later. The House is standard library only apart from the Gym, which needs numpy,
pyarrow and polars (`pip install -r requirements-gym.txt`); the gateway needs Node.

```sh
python3 -m unittest discover -s league/tests -t .   # the House, the Gym, the swarm, the data tools
python3 -m unittest discover -s ltcm/tests -t .     # the legacy package, until the prune removes it
python3 -m league.ci --no-tests                     # content checks: strategies, tools, game and config bounds, structures
(cd gateway && npm run check && npm test)           # the gateway
```

CI (`.github/workflows/checks.yml`) runs all of it on every pull request and is the source of truth.
On the owner's laptop (8 cores, 7 GiB shared with other work) run one test process at a time, only
the modules a change touches, with `TMPDIR` on the tmpfs (`TMPDIR=$(mktemp -d /tmp/t.XXXX)`) and
delete it afterwards.

## Operating it

[docs/operations.md](docs/operations.md) has the details. In short, from the repository root on the
owner's machine:

```sh
python3 scripts/floor_box.py status                        # the box, the loop, releases, health
python3 scripts/floor_box.py maintenance on --reason why   # pause paid work and new entries; exits go on
python3 scripts/floor_box.py deploy                        # a release through the in-box watchdog (from ~/Work/ltcm-deploy)
python3 scripts/floor_box.py start | stop                  # the supervised loop
python3 scripts/floor_box.py rollback --reason why         # current := previous
python3 scripts/gateway_admin.py status | kill             # the gateway; `unkill` needs the owner's token
python3 scripts/live_trading.py [--enable | --ratify | --disable]   # the grant, on the box
python3 scripts/data/box.py status                         # the data box and the backfill
```

No deploy from 13:25Z to 20:05Z on a trading day except a rollback. A merged pull request is not a
deployed feature: verify it on the box.

## The public repository

This repository is public. **Never commit licensed data or anything derived from it**: no ThetaData
or Alpaca quotes, spreads, implied-volatility surfaces, fitted parameters, fill-model calibrations or
agent programs, and no keys. They live in gitignored paths (`.data/`) on the owner's machine, on the
Sail boxes and in the House's state. The public site names no venue and shows no quote; the
publisher strips quote fields and a test proves it.

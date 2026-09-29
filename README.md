# Long-Term Capital Management

**Building a swarm of AI agents that researches and trades options, trained around the clock in
a Gym of real recorded quotes, judged by the live market.** Public page:
[blakewoods.us/capital](https://blakewoods.us/capital/).

The project narrowed to this one goal on September 26, 2026. How it got here (a paper portfolio, chat
desks on Kalshi and Coinbase, a league of strategy programs) is in [archive/](archive/README.md).

## The goal

A swarm of AI agents trading anything available with level-3 options on the owner's Alpaca account
(the "Brokerage Account" on the public page), profitably: **options returns greater than every input
cost** (Sail, Claude, OpenAI, ThetaData and the market-data subscription). The money in the account
may all be lost; the evidence must stay honest.

The owner's September 26 update makes breadth explicit: simple calls and puts, covered calls,
cash-secured puts and supported multi-leg strategies should all have a path through research and
testing. Discover the optionable securities Alpaca supports; the initial five roots and next 20
names are data batches, not a permanent universe limit. Complexity earns no preference. Each new
strategy, security and expiry range needs suitable historical data, accurate account/settlement
handling and paper execution support before it is called ready.

The engineering job is the game and its feedback loop: parallel hypotheses, short replay/review/
revision cycles, persistent lessons, and compute following credible evidence. Monday September 28
at 13:30Z is the target first market session. Profitable production trading is the goal, not an
outcome established by more agents, more trials, or a successful backtest.

## Current state — September 26, 20:04Z

- The House and research swarm are running. Real money is off, no live grant is enabled, and no
  new options trades have been placed on the production account.
- At 20:01Z: 16 active families, 57 retired, 17,631 recorded trials, **zero validation passes and
  zero holdout looks**. Fifteen active families use multi-leg strategies; one uses a single put.
- The active Gym covers SPY, QQQ, IWM, XSP and SPXW. The 25-root data expansion is still downloading;
  its final images are not adopted and the gate is disabled. Alpaca's asset lookup returned 6,177
  tradable optionable equity/ETF assets: discovery is much broader than training readiness.
- The simulator supports 11 types, including single long calls and puts. Covered calls and
  cash-secured puts still need inventory/collateral support. The current Alpaca paper path proves
  one SPY vertical round trip; a general agent paper book remains to be built.
- The live site has genuine agent thoughts and clickable dots whose progress follows each
  agent's promotion evidence. Trading Profit is $0; project Net is negative because inputs cost
  money. Exact all-input costs are still being reconciled.

The [goal](docs/goals/LTCM_OPTIONS_SWARM.md) records the updated direction and remaining work;
[operations](docs/operations.md) distinguishes merged code from deployed behavior.

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
  the first data batches (five core roots, then 20 liquid single names and ETFs), from
  ThetaData, stored as Parquet on sealed Sailboxes. A vectorized engine replays agent programs over
  it at roughly 100,000 times real time per core, fills each leg against the recorded quote on the
  minute after the decision (the natural price by default), and applies the venue's rules: expiry
  cutoffs, liquidation, exercise, assignment, fees, buying power.
- **Agent time.** The swarm learns in the Gym at thousands of times the market's speed, nights and
  weekends included, and uses the live market as the judge of what it learned, not as its teacher.
  Every clock is set by what an agent can learn from it: seconds for a revision, hours for
  selection, a night for a new forward day.
- **The agents.** An agent is one family: a mechanism (why the trade should make money), a
  supported options strategy type and a slice of the data-ready universe. Simple long options
  compete alongside spreads; covered strategies are an explicit implementation gap. A researcher
  model owns each family, keeps a notebook, and revises
  one Python program (`NEEDS`, `PARAMS`, `decide(ctx)`). A program never sees the calendar date, so
  the sealed holdout cannot be recognized. Programs live in the House's state, never in git.
- **The loops.** Inner (a researcher revises and reruns on Train, in minutes); tournament (hourly:
  validation runs, a bandit that moves Gym time and model calls to evidence, forks and retirements);
  architect (every four hours, new families from the leaderboard and the graveyard); gate (review,
  audit and one holdout look when a family meets the validation line); nightly forward (each new
  trading day, for Candidates only); live (market hours: every Candidate in shadow, Probes and Sized
  families on real money when execution is separately enabled); post-mortem (after each close).
  General agent paper trading and automatic post-close reporting are unfinished; the current
  SPY paper proof checks the route only.
- **Evidence.** Train 2022-2024, Validation 2025, a sealed holdout from Jan 2 to Sept 25, 2026, and
  every day after that forward. Every Gym evaluation counts as a trial. A family passes validation
  with at least 50 trades on 25 days, a t of 2 on P&L per dollar of maximum loss, a deflated Sharpe
  probability of 0.95 on traded days for its lineage's validated versions, 3 of 4 quarters positive and
  a profit at 1.5x the half-spread (the owner's decision D2, Sept 26, 2026); then one holdout look per version, corrected for every look the swarm has made, and
  researchers hear only pass or fail. The forward record sizes money.
- **Bands.** Gym, Candidate (live shadow only), Probe (real, small), Sized (real, by evidence),
  Retired.
- **Money rules, in a paragraph.** Everything is sized by maximum loss, never by premium: a Probe
  risks 3% of equity a structure (one contract when its maximum loss is at most $60), three open
  structures and 12% per family; a Sized family risks by quarter-Kelly on its forward record's lower
  bound, up to 10% a structure and 30% a family; the whole book at most 70% of equity. No new entries
  after a 25% day; real money pauses at a 50% drawdown from the peak. The current real adapter is
  restricted to five spread types, and credit types require $2,000 of equity. Those implementation
  limits are not a description of everything Alpaca level 3 supports; broadening the research and
  paper harness does not silently change the money rules.
  The House nets every agent's intents into one order stream, never crosses itself, stays under 250
  orders a day and closes expiring structures before the venue's cutoffs. Real money flows only
  under the owner's grant `options-swarm-20260928`, pinned to the money rules, behind the gateway's
  caps and kill switch.

## Where it runs

| Piece | What | Where |
|---|---|---|
| The House | the loop, the ledger, the books, the tournament, the gate, the live tick, the publisher | one Sailbox (size s) |
| The gateway | the account's, OpenAI's and Anthropic's keys, caps by order, the OpenAI month, the Claude funded total, the kill switch, an outside watchdog | a Cloudflare Worker |
| The data box | ThetaData downloads into the Gym store; the nightly forward day | one Sailbox (size l), asleep when idle |
| The Gym | sealed forks of the Gym image (Train and Validation only), 4-8 at a time | Sailboxes (size l) |
| The gate | a sealed fork with the holdout and forward days | one Sailbox, used by the gate only |
| The site | the public page | `personal-site`, a Cloudflare Worker |

Vendors: **Alpaca** (the account, level 3; live OPRA quotes and SIP bars through Algo Trader Plus; a
paper account for the multi-leg route), **ThetaData** Options Standard (historical option quotes),
**Sail** (the boxes, and open models for the researchers: DeepSeek, Kimi), **Anthropic** through the
gateway (Claude Sonnet 5.5 runs the top families' research cycles, Sept 29, 2026; Claude answers the
architect, the gate's audit and the diagnostician first), **OpenAI** through the gateway (GPT-6 Sol
reviews programs; GPT-6 Astra is the architect's other pass, the audit's fallback and the post-mortem)
while its funded month lasts. From Sept 29 only Sail and Claude are topped up.

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

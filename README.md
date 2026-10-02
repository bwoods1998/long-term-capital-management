# Long-Term Capital Management

**Building a swarm of AI agents that researches and trades options, trained around the clock in
a Gym of real recorded quotes, judged by the live market.** Public page:
[blakewoods.us/capital](https://blakewoods.us/capital/).

The project narrowed to this one goal on September 26, 2026. How it got here (a paper portfolio, chat
desks on Kalshi and Coinbase, a league of strategy programs) is in [archive/](archive/README.md).

## The goal

A swarm of AI agents trading anything available with level-3 options on the owner's Alpaca account
(the "Brokerage Account" on the public page), profitably: **options returns greater than every
input cost** (Sail, Claude, OpenAI while its funded September lasts, ThetaData and the market-data
subscription). The money in the account may all be lost; the evidence must stay honest.

The owner's September 26 update makes breadth explicit: simple calls and puts, covered calls,
cash-secured puts and supported multi-leg strategies should all have a path through research and
testing. Discover the optionable securities Alpaca supports; the initial five roots and next 20
names are data batches, not a permanent universe limit. Complexity earns no preference. Each new
strategy, security and expiry range needs suitable historical data, accurate account/settlement
handling and paper execution support before it is called ready.

The engineering job is the game and its feedback loop: parallel hypotheses, short replay/review/
revision cycles, persistent lessons, and compute following credible evidence. The first market
session was Monday September 28 (13:30Z); no family had passed the holdout, so its only real options
orders were the House's own calibration round trips. Profitable production trading is the goal, not an
outcome established by more agents, more trials, or a successful backtest.

## Current state: October 2, 14:15Z (paused)

- **LTCM v3, release V3-A: built, not yet deployed.** On Oct 2 the owner chose a desk with no human in the loop
  ([the run record](docs/runs/2026-10-02-unattended-desk.md)): the in-box updater on with its walls, the operator's
  scripts as House jobs (`league/ops/`), a research budget that follows realized profit inside prefunded meters, a
  standing grant, settings as code (`league/swarm/policy.json`), a daily public scoreboard in
  [docs/runs/desk/](docs/runs/desk/README.md), and the gateway's walls for an engineer agent. The forward ladder (WP6)
  and credit types at $2,000 of equity (WP7) are landing in V3-A, being integrated. Until the owner deploys it, the
  bullets below describe production. [Operations](docs/operations.md) ("LTCM v3: release V3-A") has the detail.
- **Active development is paused** (the owner, Oct 2). Production keeps running unchanged: no deploy and no settings
  change until work resumes. How to resume is in [operations](docs/operations.md) ("Paused").
- **What runs.** The House runs `20261002T112610Z-e11710692569` (main `e3d0111f`, promoted 11:26Z Oct 2), the gateway
  `4471596a`, the money digest `42c4a3af`, and the grant `options-swarm-20260928` is active (re-ratified at Release B,
  Oct 1). There have been two planned evidence resets (Release A, Sept 30; Release B, Oct 1) and none since. Main is
  ahead of the running release by docs and comments only.
- **Real money** (on since Sept 27). No family has passed the holdout (3 looks, 0 passes), so no family trades real
  money on D2. The real orders are the House's own:
  - D3 calibration round trips (19 closed by the Oct 2 open);
  - the House live test, one frozen, pre-registered program at tuition size and never evidence (no order yet);
  - one tuition lot opened Sept 30 (a 1-lot GOOGL debit vertical, never evidence), exit-only since its program failed
    its holdout look.

  The incubator (one real lot for a family whose live practice was positive, never evidence) has been on since Oct 1;
  no first look is possible before about Oct 6-7.
- **Net since the reset** (08:56Z Oct 2 cutoff): realized options P&L -$37.80, input costs $596.28 (the owner declared
  no external costs), so Net is -$634.08 ([the run record](docs/runs/2026-09-30-continuous-learning.md), "Oct 2:
  pause").
- **Research.** About 20 families alive (start 96, floor 12) and the practice league's cohorts trading shadow on live
  quotes. The architect runs on Sail as DeepSeek-V4-Pro on the asap queue (`architect.sail_profile` `pro_asap`, high
  effort, at most 6 births a pass, a pass every 20 minutes while the population is below its start): Sail's balanced
  queue did not answer from 07:00Z to 12:53Z Oct 2, and the Claude architect bore no family in its 4 passes that day. It
  reads agenda v16c (private) and may bear only debit verticals and two-sided singles. A rebirth in a refuted cell must
  name a listed row (`architect.claimable_rows` 4); open cells stay off by the owner's decision, and automatic forks of
  validated lineages are off. The gate refuses a duplicate look and holds a look the holdout cannot judge (Oct 2). The
  swarm trains on 25 roots, with Train 2020-2024 (2022-2024 for the 20 added names). Alpaca's asset lookup returned
  6,177 tradable optionable equity/ETF assets: discovery is much broader than training readiness.
- **Models.** The Sail researchers (DeepSeek) do the inner loop at a $1.30 an hour pace. Claude reads programs at the
  gate (Sonnet 5.5 for the review, Opus 5.5 for the audit) and writes the strategist's section. Stall rewrites, the
  diagnostician and the Claude research band are off. OpenAI is unused.
- **While paused.** The research burst ends Oct 5 00:00Z (`guard.burst_until`), and the swarm's Sail spend then falls to
  `guard.after_burst_usd_day` ($12 a day by default). Sail has about $130 and runs out around Oct 7-9 at the current
  pace; the guard brakes the swarm at $32, before the House is at risk. Claude has about $93 of its $265. The tuition
  lot closes before its Oct 7 expiry cutoff. No harness improvement is retained.
- **What real money may open:** four debit types under $2,000 of equity. The simulator supports 11 types. Covered calls
  and cash-secured puts still need inventory and collateral support, and there is no general agent paper book (the paper
  proofs check the route).
- **The public page** is the owner's (revamped by the owner on Oct 2). The House's publisher feeds it; the page's own
  code lives in the owner's `personal-site` repository and is not changed from here.

The [goal](docs/goals/LTCM_OPTIONS_SWARM.md) and [the sprint that amends it](docs/goals/LTCM_SWARM_SPRINT.md)
record the direction and remaining work; [operations](docs/operations.md) distinguishes merged code from
deployed behavior.

## The one number

**Net = the options book's realized P&L after every fee, minus every input cost.** Deposits and
withdrawals are never profit. The scoreboard reports Net daily, weekly and since the reset
(Sept 26, 2026, 06:25:30Z, equity $481.65). The plan put the inputs at about $565-740 a month at
its steady-state budgets, an estimate made before Claude replaced OpenAI on Sept 29 and not yet
re-derived ([design.md](docs/design.md)). The bar falls as the account grows, and compute drops to
its floor whenever the forward record does not pay for it. A change that cannot say how it raises Net does not ship.

## The game

The full design is [docs/design.md](docs/design.md); the run that is building it is
[docs/goals/LTCM_OPTIONS_SWARM.md](docs/goals/LTCM_OPTIONS_SWARM.md).

- **The Gym.** One-minute NBBO for the option contracts near the money, 0-14 days to expiry (15-45
  for SPY and QQQ back months), across the first data batches (five core roots from 2020, then 20
  liquid single names and ETFs from 2022), from ThetaData, stored as Parquet on sealed Sailboxes. A vectorized engine replays agent programs over
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
- **The loops.** Inner (a researcher revises and reruns on Train, in minutes); tournament (hourly: validation runs, an
  allocation that moves Gym time and model calls to each family's expected information value, forks and retirements;
  forks of validated lineages are off on the live settings since Oct 2); architect (Claude by default; on the live
  settings Sail, DeepSeek-V4-Pro on the asap queue since Oct 2; every 30 minutes on the live settings and every 20
  minutes while the population is below its start, every four hours by default: new families from the leaderboard and
  the graveyard); diagnostician (Claude on the stuck and nearly-there families; off on the live settings since Sept 30);
  gate (review, audit and one holdout look when a family meets the validation line); nightly forward (each new trading
  day, for Candidates only); live (market hours: the practice league, every alive family's validated or eligible Train
  version in observe shadow from Release A; every Candidate in shadow; Probes and Sized families on real money, and the
  House's own calibration round trips and live test); post-mortem (after each close; the operator's for now, no
  scheduled one is built). General agent paper trading is unfinished; the paper proofs check the route only.
- **Evidence.** Train 2020-2024 (2022-2024 for the added names; 2022-2024 is the code's default),
  Validation 2025, a sealed holdout from Jan 2 to Sept 25, 2026, and every day after that forward.
  Every Gym evaluation counts as a trial. A version reaches Validation only after its 1.5x Train
  robustness run made a profit and it passed the drift screen. A family passes validation with at
  least 50 trades on 25 days, a t of 2 on P&L per dollar of maximum loss, a deflated Sharpe
  probability of 0.95 on traded days for its lineage's validated versions, 3 of 4 quarters positive and
  a profit at 1.5x the half-spread (the owner's decision D2, Sept 26, 2026); then one holdout look per version, corrected for every look the swarm has made, and
  researchers hear only pass or fail. The forward record sizes money. From Release A, a change to the Gym or live
  code, the fill model or the image archives the derived selection evidence (a planned evidence reset). Trials and
  consumed holdout looks are kept, and evidence is never compared across such a change.
- **Bands.** Gym, Candidate (live shadow only), Probe (real, small), Sized (real, by evidence),
  Retired. (The practice league: every alive Gym family's validated version, and from Release A its eligible Train
  version, trades an observe shadow on live quotes, never real, never evidence. At most `live.observe_max` (48)
  instances and, from Release A, `live.observe_roots_max` (24) roots. Code guards keep practice instances off the real
  order path.)
- **Money rules, in a paragraph** (the owner's decision D4, Sept 26). Everything is sized by maximum
  loss, never by premium: a Probe risks 5% of equity a structure (one contract when its maximum loss is
  at most $100), three open structures and 15% per family; a Sized family risks by quarter-Kelly on its
  forward record's lower bound, up to 10% a structure and 30% a family; the whole book at most 90% of
  equity. No new entries after a 35% day; real money pauses at a 60% drawdown from the peak. Under
  $2,000 of equity real money opens exactly four debit types (debit verticals, long butterflies, long
  calls, long puts); credit types come back only in one deploy with the gateway's list and a re-ratified
  grant (#393, the owner's decision). Execution tuition is at most $200 a day; the House's D3
  calibration round trips at most $50 of possible loss a day; the House live test one structure of at
  most $100, three open and no new open once it has lost $150. Those implementation limits are not a
  description of everything Alpaca level 3 supports; broadening the research and paper harness does
  not silently change the money rules.
  The House nets every agent's intents into one order stream, never crosses itself, stays under 250
  orders a day and closes expiring structures before the venue's cutoffs. Real money flows only
  under the owner's grant `options-swarm-20260928`, pinned to the money rules, behind the gateway's
  caps (an order at most the lower of $1,000 and 25% of equity) and kill switch.

## Where it runs

| Piece | What | Where |
|---|---|---|
| The House | the loop, the ledger, the books, the tournament, the gate, the live tick, the publisher | one Sailbox (size s) |
| The gateway | the account's, OpenAI's and Anthropic's keys, caps by order, the OpenAI month, Claude's funded total, the kill switch, an outside watchdog | a Cloudflare Worker |
| The data box | ThetaData downloads into the Gym store; the nightly forward day | one Sailbox (size l), asleep when idle |
| The Gym | sealed forks of the Gym image (Train and Validation only), 4-8 at a time by default (2-6 on the live settings since Release A) | Sailboxes (size l) |
| The gate | a sealed fork with the holdout and forward days | one Sailbox, used by the gate only |
| The site | the public page | `personal-site`, a Cloudflare Worker |

Vendors: **Alpaca** (the account, level 3; live OPRA quotes and SIP bars through Algo Trader Plus; a paper account for
the multi-leg route), **ThetaData** Options Standard (historical option quotes), **Sail** (the boxes, and open models
for the researchers and the roles' fallbacks: DeepSeek, Kimi), **Anthropic** through the gateway (Claude answers first
for the roles the live settings give it. Since Sept 30's spend cut those are the gate's program review (Sonnet 5.5,
`claude-sonnet-5-5`), its audit (Opus 5.5) and the strategist. The architect's Claude line is $0, so its births run on
Sail (DeepSeek-V4-Pro on the asap queue since Oct 2). The top-band research, the stall rewrite and the diagnostician are
off on Claude; the code still supports each), **OpenAI** through the gateway (GPT-6 Sol and Astra, the code's defaults
for the review and the audit's fallback, are switched off in the live settings since Sept 29). From Sept 29 only Sail
and Claude are topped up; the gateway's OpenAI cap is $0 from Oct 1.

## The repository

As it will stand after the prune (#375, still a draft); until it merges the legacy `ltcm/` package,
`playbooks/` and the old league's modules are still here.

| Path | What it is |
|---|---|
| `league/` | the House: `house.py` (the tick), `ledger.py`, `book.py`, `allocator.py`, `constitution.py` (the money rules and their digest), `live_trading.py` (the grant), `publish.py`, `trading_profit.py` and `account_activity.py` (Profit and the positions table), `claude.py` and `frontier.py` (the Claude and OpenAI clients, through the gateway), `service.py`, `watchdog.py`, `stats.py`, `config.json` |
| `league/live/` | the live path: the shadow and observe books, the real book, the paper route proofs, the D3 calibration round trips, the House live test |
| `league/gym/` | the Gym: the store reader, the engine, fills, the venue's rules, greeks, the batch runner, the sealed-box driver; the program contract in `PROGRAM.md` |
| `league/swarm/` | the swarm: researchers, the tournament and the allocation, the architect, the family cards, the diagnostician, the gate, the model router, the Sail guard, the funding-cliff alerts, the Gym pool, the evaluator record; `policy.json`, the research settings as code (V3-A) |
| `league/ops/` | the House's jobs (V3-A): the scheduler on the NYSE calendar, the runner and receipts, the pre-open checks, the close economics, hygiene, the venue clock, the scoreboard, and the protected budget rule, standing grant and drills |
| `league/CONTRACT.md` | the options strategy contract every researcher reads (about 32 KB) |
| `league/tests/` | the tests |
| `gateway/` | the Worker ([its README](gateway/README.md)) |
| `scripts/` | `floor_box.py` (the House's box), `gateway_admin.py` (the kill switch), `live_trading.py` (the grant), `desk_receipts.py` (the House's receipts, read without exec; V3-A), `settings_migrate.py` (swarm.json to policy.json; V3-A), `scripts/data/` (the data box, the backfill, the images, the nightly job, the store checks) |
| `deploy/` | [how the House runs on its box](deploy/README.md) |
| `docs/` | [design.md](docs/design.md), [operations.md](docs/operations.md), `goals/` (the run's plan and the sprint that amends it); `runs/` (the Oct 2 unattended-desk record and its daily scoreboard in `runs/desk/`, the Sept 30 continuous-learning run record; the Sept 26 run's record is on branch `run/options-swarm-2026-09-26`) |
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

CI (`.github/workflows/checks.yml`) runs all of it on every pull request and is the source of truth. It runs the suites
with `TMPDIR` on `/dev/shm` when it can, because the live state's SQLite commits (`synchronous=FULL`) dominate the live
tests on a disk, and its tests job has a 35-minute limit. A cancelled run is not green.
On the owner's laptop (8 cores, 7 GiB shared with other work) run one test process at a time, only
the modules a change touches, with `TMPDIR` on a scratch directory on disk rather than the small
`/tmp` tmpfs (agents filled it on Sept 26-27 and every shell failed), and delete it afterwards.

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
python3 scripts/desk_receipts.py                           # V3-A: the House's job receipts, read without exec
```

From V3-A, merged code outside the protected paths reaches the House through the in-box updater; the protected paths
(the money rules, the live path, the grant, the updater, the watchdog, `league/ci.py`, the gateway, the budget rule,
the standing grant's job and the drills) stay the owner's deploy.

No money-path deploy from 13:25Z to 20:05Z on a trading day except a rollback; a research-class release may deploy in
session under the rules in [operations](docs/operations.md) ("Rules that hold every day"). A merged pull request is not
a deployed feature: verify it on the box.

## The public repository

This repository is public. **Never commit licensed data or anything derived from it**: no ThetaData
or Alpaca quotes, spreads, implied-volatility surfaces, fitted parameters, fill-model calibrations or
agent programs, and no keys. They live in gitignored paths (`.data/`) on the owner's machine, on the
Sail boxes and in the House's state. The public site names no venue and shows no quote; the
publisher strips quote fields and a test proves it.

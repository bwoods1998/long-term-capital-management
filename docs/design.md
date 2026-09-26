# The design: a swarm of agents trading options

The game as designed on Sept 26, 2026, kept current as the swarm changes. The run's goal file is
[goals/LTCM_OPTIONS_SWARM.md](goals/LTCM_OPTIONS_SWARM.md): it holds the owner's direction, the
order of work and the authority; this page holds the design alone. Where this page and the code
disagree, the code is right and this page is fixed. How to operate it is in
[operations.md](operations.md).

## Where each part stands (Sept 26, 2026, 08:00Z)

| Part | Code | State |
|---|---|---|
| The House, options only | `league/` | PR #359 merged 07:49Z (main `6c715d83`): updater off, the new grant, options-only service and tick; not yet deployed (the old House is stopped) |
| The data store and images | `scripts/data/` | the data box downloading since 06:49:43Z; images and the nightly job rehearsed 07:08-07:19Z; code on branch `data/gym-store` |
| The Gym | `league/gym/` | PR #358 open, under adversarial review before it merges |
| The swarm | `league/swarm/`, `league/CONTRACT.md` | being built (Wave 4) |
| The live path | the House's live tick, `gateway/` | being built (Wave 5); real money stays off until it is deployed |
| The public page | blakewoods.us/capital | reset and deployed at 07:21Z (schema 2); no checkpoint until the new House publishes |

## The goal and the one number

One goal: a swarm of AI agents trading level-3 options on one brokerage account (the "Brokerage
Account"), profitably, where profitably means options returns greater than everything the project
spends.

**Net = the options book's realized P&L on the Brokerage Account, after every fee, minus every input
cost** (Sail, OpenAI, ThetaData, the market-data subscription, and anything added). Deposits and
withdrawals are never profit. The scoreboard reports Net daily, weekly and since the reset. A change
that cannot say how it raises Net does not ship.

The bar at steady-state budgets:

| Input | Monthly |
|---|---|
| Market data (Alpaca Algo Trader Plus, about $1,000 a year) | $83 |
| ThetaData Options Standard | $80 ($64 billed annually) |
| Sail after the training burst | $250-360 ($8-12 a day) |
| OpenAI after the training burst | $150-215 |
| **Total** | **about $565-740** |

On a $6,500 account that is 9-11% a month before Net turns positive. The bar falls in proportion as
the account grows, and compute drops to its floor whenever the forward record does not pay for it.

## The venue

One account at Alpaca, approved for level 3. The facts the design is built on (verified Sept 26):

- **No pattern-day-trader rule** since June 4, 2026: the swarm may open and close the same day as
  often as it likes; a real-time margin check rejects any order that would create a deficit.
- **Under $2,000 of equity the account is 1x with no shorting.** A spread needs options buying power
  equal to its maximum loss (a debit spread its debit; a credit spread width x 100 minus the credit).
  Options settle T+1.
- **Structures:** at most 4 legs, every short leg covered inside the same order, whole-order replace
  only. **Only five types close in one order:** debit and credit verticals, iron condors, iron
  butterflies, long butterflies. Legging out risks a naked short (refused) or a buying-power refusal.
- **Positions net per contract across the whole account**, so one agent's sale can close another
  agent's leg, and opposing orders that could cross on one contract are rejected as wash trades.
- **Index options** (SPX, SPXW, XSP, VIX, VIXW, DJX) are cash-settled and European; every leg of an
  index multi-leg order has one expiry. SPY, QQQ, IWM and single names are American and physically
  settled: an assigned short leg becomes shares.
- **Expiry day:** orders on expiring contracts by 15:15 ET (15:30 for SPY and QQQ); from 15:30 ET
  (15:45 for broad ETFs) the venue liquidates what it cannot carry. Auto-exercise at $0.01 in the
  money.
- **Order rate:** over 390 orders a day on average in a month (cancels included) makes the account
  "professional". The Trading API allows 200 requests a minute.
- **Fees:** $0 commission on equity options while retail; regulatory fees of a few cents a
  contract; index options $0.50 a contract plus exchange fees. Hours 09:30-16:00 ET only.

## The data

- **ThetaData Options Standard**: every OPRA NBBO since 2016 at any interval (one minute for
  multi-day requests), trades with the NBBO at each trade, historical implied vol and first-order
  greeks, open interest, EOD, for equity and index options. Its greeks history carries the
  underlying's price every minute; the index and stock price endpoints are separate subscriptions
  the project does not hold. Four concurrent requests and **one session per account**. The license
  is personal and non-professional and forbids publishing the data or anything derived from it.
- **Alpaca Algo Trader Plus**: live OPRA NBBO (up to 1,000 symbols on one WebSocket), chain
  snapshots with greeks, SIP stock bars and quotes since 2016. No historical option quotes.
- **The SPX level** for XSP and SPXW comes from put-call parity on the at-the-money options, the same
  way in the Gym and live (ThetaData's underlying price is the check).

## Agent time

The market trades options about 1,640 hours a year. The swarm does not learn at that pace: it
learns in the Gym on real recorded quotes at thousands of times real speed, and the live market
judges what it learned.

- One Gym core replays a program over a year of one-minute NBBO in about a minute (roughly 100,000
  times real time). Four to eight 8-vCPU Gym boxes give several million market-hours of experience
  a weekend.
- Every clock is set by what an agent learns from it: the inner loop in seconds to minutes,
  selection in hours, the gate the moment evidence is enough, forward evidence every night and
  every market minute.
- 24/7: nights and weekends in the Gym and the nightly forward replay; market hours in live shadow
  trading of every candidate at once, plus real money.

The danger at this speed is a search that finds luck. Every program evaluation is counted as a
trial, and the evidence rules below are as much a part of the game as its speed.

## The world

- **Universe.** The core five: SPY, QQQ and IWM (ETF options, daily expiries) and XSP and SPXW
  (cash-settled, so 0DTE can be held to expiry with no assignment). Then about 20 single names and
  ETFs ranked by 2024 option volume and quoted spread (never from holdout days). Any optionable
  underlying is admissible once its data is in the Gym.
- **Structures:** everything level 3 allows, all defined-risk: debit and credit verticals, iron
  condors, iron butterflies, long butterflies, long straddles and strangles, calendars and diagonals
  (equity options only), single long calls and puts. No naked short anywhere.
- **Horizons:** 0-5 days to expiry at the center, so each agent closes one or more independent
  trades a day; calendars and diagonals may hold a back leg to 45 days.
- **Time splits**, for every family and program:

  | Window | Dates | Use |
  |---|---|---|
  | Train | 2022-01-03 to 2024-12-31 | the inner loop; agents see everything |
  | Validation | 2025-01-02 to 2025-12-31 | selection; agents see only summaries |
  | Holdout (sealed) | 2026-01-02 to 2026-09-25 | one look per program version at the gate; never on a Gym box |
  | Forward | each trading day from Sept 28, 2026 | the judge: nightly replays, live shadow, real money |

  The Gym serves only the expiries that existed on each day (SPY and QQQ daily expiries from
  mid-Nov 2022; IWM's Tuesday and Thursday expiries from 2024).

## The Gym

- **The store** (`store-v1`): per-day Parquet, partitioned by underlying and day, of one-minute NBBO
  (bid, ask and sizes) for strikes around the money and 0-14 days to expiry (0-45 for calendar back
  months), the underlying's price by minute, daily open interest, `trade_quote` samples for fill
  calibration, and the listing calendar and expiries.
- **Three places, three contents.**
  - **The data box** (Sail size l) downloads and writes the store. It holds the ThetaData key in its
    own 0600 file and nothing else: no venue key, no gateway token, no agent code. Its egress is the
    two ThetaData hosts. It sleeps when idle (never pauses: a paused box cannot wake on a schedule).
  - **The Gym image** is a fork of the data box with the key, the holdout and the forward days
    deleted, sealed with `no_network`, checkpointed twice with a one-year TTL. Gym boxes are forks
    of it.
  - **The gate image** is a second sealed fork, without the key but with the holdout and forward
    days, used only by the gate and the nightly forward replays of Candidates. Its store carries a
    `GATE` mark; the Gym opens sealed windows only on a store with that mark.
- **Gym boxes**: size-l forks of the Gym image, no network. Programs go in and results come out
  through Sail's file and exec APIs. Four to start, up to eight while the queue is long, asleep when
  it is short.
- **The engine** is a vectorized, day-major replay: it loads a day's chain once and runs a batch of
  programs over it. Each program sees the chain only through its `ctx`, one decision step at a time,
  with nothing from the future; the engine owns the clock.
- **Honest fills.** A structure fills against each leg's recorded NBBO on the minute after the
  decision: at the natural price (every leg's half-spread paid) by default; better only with the
  probability the fill model gives, keyed by (contract, minute), never by the program, so an edit
  cannot re-roll luck. The model is calibrated on Train days from `trade_quote`, then from real
  fills; paper fills prove the order route, never the calibration. Size is capped by the quoted
  size. A family must stay positive at 1.5x the half-spread to pass the gate.
- **The venue's rules in the engine**, the same as the House's: no new opening order on an expiring
  contract after 15:00 ET; closing orders until 15:10 ET (15:25 for SPY and QQQ); the venue's
  liquidation from 15:30 ET; auto-exercise and physical settlement for equity options; cash
  settlement for XSP and SPXW; the buying-power check (maximum loss plus fees plus 10%); the ticks.
- **A run returns** every trade (legs, fills, fees, maximum loss, P&L), the daily P&L series, P&L
  per dollar of maximum loss, win rate, profit factor, Sharpe, drawdown, turnover, fill statistics,
  P&L by weekday, time of day, DTE and volatility regime, and the worst trades. Runs are
  deterministic and hashed from (program, data version, engine version, window).
- **Speed targets:** one program over one underlying-year in 60 s on one core; at least 2,000
  program-years an hour across the Gym; a researcher's inner-loop answer in under 3 minutes.

## The agent

- **An agent is one family**: a mechanism (why the trade should make money), a structure type and a
  universe slice, owned by a researcher model with a notebook, a lineage of program versions and a
  record. Two agents never share a family; forks start new families.
- **The program** is one Python file with `NEEDS`, `PARAMS` and `decide(ctx)`, run at a cadence it
  declares (1 to 30 minutes). `ctx` gives the time of day, weekday, days to each expiry, event flags
  (FOMC, CPI, jobs, earnings, monthly expiry, index rebalances), recent underlying bars, the chain
  slice `NEEDS` asked for as numpy arrays, and the program's positions, cash, risk budget and the
  venue's rules. It never gives the calendar date or year: the models know what happened in 2026,
  so the holdout must not be recognizable, and the safety check rejects date literals. `decide`
  returns structure intents (type, legs by expiry and strike or delta rules, a quantity or
  maximum-loss budget, a limit rule, a time in force) and exits. numpy and math only; no I/O.
- **The contract** is [league/CONTRACT.md](../league/CONTRACT.md), for options only and under
  20 KB, because every researcher call pays for it; the rest lives in reference pages read on demand.
- **Programs live in the House's state, never in git.** The repository is public and a program's
  parameters are fitted to licensed data.
- **Seeds:** the 12 structure founders of Sept 25 re-expressed in the new contract, plus the
  architect's first library of mechanisms (variance risk premium in short-dated index options,
  intraday momentum, opening-range breaks and fades, gap reversion, end-of-day drift, 0DTE pinning,
  term-structure and skew mean reversion, post-event volatility crush, weekly-expiry dynamics).
- **Population:** 48 researchers at the start of the training burst, a ceiling of 96 and a floor of
  16; about 16 after Sept 28 while Net is not positive. Families compete for Gym time and model
  calls through a bandit over their validation evidence (Thompson sampling, 25% exploration for new
  families). A family retires when its best program has not improved on validation in 30 revisions
  or 2,000 evaluations, or its trial-adjusted evidence falls below the line. Its lessons go to the
  graveyard, which every new family's researcher reads first.

## The loops

| Loop | Cadence | Who | What happens | Output |
|---|---|---|---|---|
| Inner | seconds to minutes | each researcher | revise the program, run it on Train, read the diagnostics, revise again | a better program or a lesson |
| Tournament | hourly | the House | validation runs of each family's best versions, the bandit's reallocation, forks and retirements, the leaderboard | Gym time and model calls follow evidence |
| Architect | every 4 hours | GPT-6 Astra | reads the leaderboard, the graveyard and the gaps; writes families with a mechanism, a structure and a rejection test | 3-6 new families |
| Gate | when a family meets the validation line | GPT-6 Sol, Astra, the gate box | review for lookahead, leakage and fill abuse; the audit; one holdout look | a Candidate, or a recorded refusal |
| Nightly forward | after 01:45 ET each trading night | the data box, the gate box | the new day goes to the gate image only; every Candidate is re-run on it | one unseen day a night for every Candidate |
| Live | 09:30-16:00 ET | the House | Candidates trade the shadow book on live quotes; Probe and Sized families trade real money; the paper account measures multi-leg execution | forward records, real P&L, real fills |
| Post-mortem | after each close; weekly | the House, Astra | live P&L against what the Gym expected; the fill model recalibrated | calibration, lessons, repairs |

**Models.** The inner loop runs on Sail's DeepSeek-V4-Flash (V4.1-Flash where long cached histories
make it cheaper), with a cache key per agent and the shared contract cached once a day. A researcher
that stalls for 5 revisions escalates one rewrite to DeepSeek-V4-Pro (Kimi-K3 for the top ten
families). Bulk overnight variants go through Sail's Batch API. Through the gateway, GPT-6 Sol
reviews every program before live shadow, and GPT-6 Astra is the architect, the gate's auditor and
the weekly post-mortem, on OpenAI's half-price flex tier wherever latency does not matter.

## Evidence

- **Every Gym evaluation is a trial**, counted per lineage (forks inherit their parent's count and
  holdout looks) and in total on the ledger.
- **The validation line** (a family's best program): at least 100 trades on at least 60 distinct
  days in Validation; mean P&L per dollar of maximum loss above zero after fees with a one-sided t of
  at least 2; a deflated Sharpe probability of at least 0.95 given the lineage's trial count;
  positive in at least 3 of Validation's 4 quarters; positive at 1.5x the half-spread.
- **The holdout line**, one look per program version and at most three per lineage: P&L after fees
  positive; a day-block bootstrap one-sided 95% lower bound on mean daily P&L above zero, with a
  Holm-Bonferroni correction across every holdout look the swarm has made; holdout Sharpe at least
  half the validation Sharpe. **Researchers learn only pass or fail**, never the holdout's numbers.
- **Forward days never reach a Gym box.** Nightly forward replays run on Candidates only; they move
  bands and never select among Gym programs.
- **The forward record** (nightly replays, live shadow and real trades) is what sizes money. A
  Candidate whose forward record turns negative over 20 trades loses its band. Families whose code
  was written with knowledge of 2024-2026 need a forward record before they are Sized.
- **The leakage alarm:** once there are at least 10 holdout looks, if more than 30% pass, the gate
  stops until leakage is ruled out.
- The lines may be tightened on evidence; loosening one is the owner's decision.

## Money

**Bands:** Gym, Candidate (shadow only), Probe (real, small), Sized (real, by evidence), Retired.

| Rule | Default | Allowed range |
|---|---|---|
| Probe: a Candidate that passed the holdout, trades one of the five one-order-closeable types, and whose typical maximum loss fits the cap at current equity | real from its next session | - |
| Credit structures on real money | only from $2,000 of equity (or once a real credit order is accepted); debit types until then | - |
| Probe max loss per structure | 3% of equity | 2-5% |
| Probe open structures per family | 3 | 1-5 |
| Probe family total max loss | 12% of equity | 8-15% |
| Probe floor for a small account | one contract when its max loss is at most $60 | $0-100 |
| Sized: forward record of at least 20 trades, mean > 0 and 80% lower bound > 0 | quarter-Kelly on the lower bound | eighth- to half-Kelly |
| Sized max loss per structure | 10% of equity | 5-15% |
| Sized family total max loss | 30% of equity | 20-40% |
| Book: open max loss, all families | 70% of equity | 50-90% |
| Daily stop: the day's realized plus marked loss | 25% of start-of-day equity: no new entries that day | 15-35% |
| Drawdown stop from the peak since the reset | 50%: real money paused, exits go on, the owner told, the Gym keeps running | 40-60% |
| Execution tuition: 1-lot real orders before the holdout, to measure multi-leg fills (never evidence) | $100 max loss a day, $300 a week | $0-200 a day |

- **Sizing is by maximum loss**, never by premium.
- **The order path:** the House nets every agent's intents into one order stream per contract;
  never sends opposing orders on one contract; queues or refuses an intent against a contract
  another agent holds; reserves maximum loss plus fees plus 10% of buying power before sending;
  stays under 250 orders a day (counting cancels and each leg until the venue's counting is
  verified) and 150 requests a minute; sends no new opening order on an expiring contract after
  15:00 ET; closes expiring equity-option structures with a short leg near the money by 15:10 ET
  (15:25 for SPY and QQQ) with one multi-leg order; and polls account activities for assignments.
  Real money trades only the five one-order-closeable types until a paper round trip proves another.
- **The gateway's caps follow the account:** per order, maximum loss at most the lower of $1,000 and
  15% of equity; opening maximum loss a day at most 100% of equity; 300 orders a day; the kill
  switch. `OPTION_STRUCTURES_REAL` names the types real money may open.
- **The grant** `options-swarm-20260928` (`league/live_trading.py`) covers the Brokerage Account
  only. Its capital is the lower of the account's equity and the owner's ceiling at each
  ratification; it is pinned to the money digest, re-ratified within a minute of any promotion that
  moves the digest and whenever a deposit lands. With no active grant the House sends no real
  opening order; exits always go on.
- **Capital flows are the owner's.** The publisher and the scoreboard read the account's funding
  activities and net out deposits and withdrawals; the daily stop and the drawdown peak do the same.

## Compute

| Job | Service | Model or size | Budget |
|---|---|---|---|
| Researchers' inner loop | Sail | DeepSeek-V4-Flash asap (V4.1-Flash for long cached histories); cached contract | about $1-2 an hour at 48-96 agents |
| Rewrites on a stall; top families | Sail | DeepSeek-V4-Pro balanced; Kimi-K3 balanced | capped per family per day |
| Bulk overnight variants | Sail Batch | V4-Pro flex | capped per night |
| Program review before live shadow | OpenAI via the gateway | GPT-6 Sol, flex | about $0.03 a program |
| Architect, every 4 hours | OpenAI | GPT-6 Astra, flex | about $0.55 a pass |
| Gate audit | OpenAI | GPT-6 Astra, standard | about $0.90 an audit |
| Weekly post-mortem | OpenAI | GPT-6 Astra, flex | about $2 |
| Gym | Sail boxes | 4-8 sealed size-l boxes | $0.10-0.40 an hour each while busy; asleep when idle |
| Data | Sail box + ThetaData | one size-l box, asleep when idle | $5-15 a day while running |
| The House | Sail box | one size-s box | about $0.03 an hour |
| History, the nightly forward day, fill calibration | ThetaData | four concurrent requests | $80 a month |
| Live quotes, SIP bars, paper and real orders | Alpaca | through the gateway | already paid |

- **Budgets.** The training burst (Sept 26 to Monday Sept 28's open): Sail at most $350, OpenAI at
  most $150. After that: Sail at most $12 a day and OpenAI at most $215 a month until Net is
  positive over 30 days; then compute may grow to half the trailing 30-day gross options profit.
  When the forward record is flat, compute drops to the floor: the nightly forward replay, live
  shadow and one architect pass a day.
- **The Sail guard.** Running out of Sail credits pauses every box, the House included. Gym boxes and
  researchers scale down whenever the balance falls below two days of the House's burn plus $30,
  and stop before the House does.
- **Dropped** with the league: Jev, GPT-6 Luna research, Sail web search, the Alpha Lab, the
  hypothesis foundry, the semantic lab, Merton's roles other than the architect and the engineer,
  and every Kalshi, crypto and stock feed.

## What is public

The House publishes to [blakewoods.us/capital](https://blakewoods.us/capital/), which says "AI
agents trading options." and calls the account the "Brokerage Account": no venue is named anywhere a
visitor reads. It shows the account's balance from its equity at the reset (Sept 26, 06:25:30Z,
$481.65), total profit since the reset net of deposits and withdrawals, the running timer, Net
beside it, each agent's family, mechanism, band and record, the Gym's pace, open structures with
their maximum loss and P&L, and the agents' decisions in their own words.

**Never quotes, spreads, implied-volatility surfaces or fitted parameters**, on the site, in the
public JSON or in this repository: the data licenses forbid it. The publisher strips every quote
field and a test proves it. Programs and fitted parameters stay in the House's state and on Sail.

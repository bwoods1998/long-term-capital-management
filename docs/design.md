# The design: a swarm of agents trading options

The game as designed on Sept 26, 2026, kept current as the swarm changes. The run's goal file is
[goals/LTCM_OPTIONS_SWARM.md](goals/LTCM_OPTIONS_SWARM.md): it holds the owner's direction, the
order of work and the authority; this page holds the design alone. Where this page and the code
disagree, the code is right and this page is fixed. How to operate it is in
[operations.md](operations.md).

## Where each part stands (Sept 29, 2026, 04:55Z)

| Part | Code | State |
|---|---|---|
| The House, options only | `league/` | running R8, release `20260929T044127Z-2c265b03bc04` (main `8074e262`, promoted 04:42Z Sept 29); real money on since Sept 27; the grant active on money digest `a3e2aa7c`, capital $1,473.11 |
| The data store and images | `scripts/data/` | the core five from 2020 (the 2020-21 fetch completed Sept 28) and the 20 added names from 2022, 0-14 days to expiry, SPY/QQQ back months to 45; ThetaData Options Standard's history reaches 2016; a longer-history fetch as private blocks is in progress (#413) |
| The Gym | `league/gym/` | 25 roots, Train 2020-2024 on a sealed image adopted Sept 28 (2022-2024 for the added names); 11 types including long calls and puts; the honest fill model from Train samples |
| The swarm | `league/swarm/`, `league/CONTRACT.md` | at 04:33Z Sept 29: 92 alive, 774 retired, 67,882 trials; 2 holdout looks, 0 passes; the gate on; Claude on every paid role since 04:53Z (Sonnet 5.5; Opus 5.5 for the audit), OpenAI unused |
| Paper and production paths | `league/live/`, `gateway/` | real money opens four debit types; both paper route proofs passed Sept 28; the D3 calibration ran three real round trips Sept 28; the House live test armed Sept 29, no trade yet; no general agent paper book; covered strategies absent |
| The public page | blakewoods.us/capital | deployed: genuine thoughts first, Profit/Running, clickable agent dots with evidence-based progress, a positions table that adds up to Profit (an opt-in read); Profit -$8.68, all of it the House's calibration round trips and the broker's fees |

This is observed state, not completion of the design below. Broad universe discovery, covered
strategies and the general paper environment are still to build; longer history (#413), the top
families' research on Claude Sonnet 5.5 (#417) and an architect that reads the whole graveyard are in
progress.

## The goal and the one number

One goal: a swarm of AI agents trading level-3 options on one brokerage account (the "Brokerage
Account"), profitably, where profitably means options returns greater than everything the project
spends.

The September 26 owner feedback sets the scope: **all Alpaca-supported options opportunities with
the data and mechanics needed to test them**, with no preference for complicated structures. The
first five and next 20 roots are collection batches. Neither is the eventual universe boundary.
Simple calls/puts, covered calls/cash-secured puts and supported spreads must compete on evidence.
The first market session was Sept 28. No family has passed Validation yet (2 holdout looks, 0 passes),
so the record does not yet demonstrate an edge or establish that the goal will be met.

**Net = the options book's realized P&L on the Brokerage Account, after every fee, minus every input
cost** (Sail, Claude, OpenAI, ThetaData, the market-data subscription, and anything added). Deposits and
withdrawals are never profit. The scoreboard reports Net daily, weekly and since the reset. A change
that cannot say how it raises Net does not ship.

The bar at steady-state budgets, as the plan estimated it (Sept 26):

| Input | Monthly |
|---|---|
| Market data (Alpaca Algo Trader Plus, about $1,000 a year) | $83 |
| ThetaData Options Standard | $80 ($64 billed annually) |
| Sail after the training burst | $250-360 ($8-12 a day) |
| OpenAI after the training burst | $150-215 in the plan; not topped up after September 2026 (the owner, Sept 29) |
| Claude (Anthropic, through the gateway) | a funded total, not a month: `CLAUDE_USD` $100, raised only by what the owner adds; the swarm's own line is `claude.usd_cap` |
| **Total** | **about $565-740 in the plan; to be re-estimated with Claude in place of OpenAI** |

On a $6,500 account the plan's figure is 9-11% a month before Net turns positive. The bar falls in
proportion as the account grows, and compute drops to its floor whenever the forward record does not
pay for it.

## The venue

One account at Alpaca, approved for level 3. The facts the design is built on (verified Sept 26):

- **No pattern-day-trader rule** since June 4, 2026: the swarm may open and close the same day as
  often as it likes; a real-time margin check rejects any order that would create a deficit.
- **Under $2,000 of equity the account is 1x with no shorting.** A spread needs options buying power
  equal to its maximum loss (a debit spread its debit; a credit spread width x 100 minus the credit).
  Options settle T+1.
- **Capabilities:** level 3 includes lower-level permissions: long calls and puts, covered calls
  backed by owned shares, and cash-secured puts backed by cash, as well as supported multi-leg
  orders. Multi-leg orders have at most four option legs, with short legs covered within the order;
  stock-plus-option combination orders are not supported. The current House's four-type real
  allowlist is an implementation restriction, not the venue's entire options capability. Exit
  behavior and inventory reservations need verification for each added type. See Alpaca's
  [options levels](https://docs.alpaca.markets/us/docs/options-trading) and
  [multi-leg restrictions](https://docs.alpaca.markets/us/docs/options-level-3-trading).
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
  The project's store holds the core five from 2020 and the added names from 2022; a longer-history
  fetch (#413) is in progress, and which roots the vendor serves from which day stays private.
- **Alpaca Algo Trader Plus**: live OPRA NBBO (up to 1,000 symbols on one WebSocket), chain
  snapshots with greeks, SIP stock bars and quotes since 2016. No historical option quotes.
- **The SPX level** for XSP and SPXW comes from put-call parity on the at-the-money options, the same
  way in the Gym and live (ThetaData's underlying price is the check).

## Agent time

The market trades options about 1,640 hours a year. The swarm does not learn at that pace: it
learns in the Gym on real recorded quotes at thousands of times real speed, and the live market
judges what it learned.

- One Gym core replays a program over a year of one-minute NBBO in about a minute (roughly 100,000
  times real time). Four to eight 8-vCPU Gym boxes (up to 16 on the live settings) give several
  million market-hours of experience a weekend.
- Every clock is set by what an agent learns from it: the inner loop in seconds to minutes,
  selection in hours, the gate the moment evidence is enough, forward evidence every night and
  every market minute.
- 24/7: nights and weekends in the Gym and the nightly forward replay; market hours in live shadow
  trading of every candidate at once, plus real money.

The danger at this speed is a search that finds luck. Every program evaluation is counted as a
trial, and the evidence rules below are as much a part of the game as its speed.

Improve the loop recursively: a hypothesis, runnable program, recorded replay, actionable failure
diagnostic, revision, then independent evaluation. Compare mechanisms and simple baselines before
spending on repeated parameter sweeps. Preserve notebooks and failed ideas, allocate exploration
across strategy types and securities, and use stronger models where diagnoses or rewrites need
them. Measure useful revisions, completed evaluations, refusals, coverage and cost per result.
Agent count and simulated years measure activity; passing unseen evidence measures progress.

## The world

- **Universe.** Discover Alpaca's optionable assets and supported index products. Keep distinct
  states for discovered, data pending, historically testable, paper-supported and production-ready.
  Rank collection work by liquidity, coverage gaps and research demand using Train-era data; keep
  all other eligible securities in the backlog. Initial batches are SPY/QQQ/IWM/XSP/SPXW and 20
  liquid names/ETFs. The 20:04Z asset receipt contains 6,177 tradable optionable equity/ETF assets;
  this is a discovery count, not a claim that their contracts/data are all supported today.
- **Strategies.** Give single long calls and puts the same research opportunity as debit/credit
  verticals, condors, butterflies, straddles, strangles, calendars and diagonals. Add covered calls
  and cash-secured puts with explicit stock/cash reservations, assignment, dividends/corporate
  actions and exit accounting; they are not implemented by pretending a short option is naked.
  Stock inventory held to support an options strategy belongs in the options harness. Independent
  stock/crypto trading remains outside the project. Complexity is not a promotion criterion.
- **Horizons and rules.** Admit only the expiry ranges, listing history, multipliers and settlement
  rules supported by each root's data and implementation. Current collection is 0–14 DTE across 25
  roots and a 15–45 DTE extension on SPY/QQQ only, with the core five's history from 2020 and the
  added names' from 2022; runtime syntax permitting 60 DTE does not supply that data. Short-dated
  options are the initial batch, not a permanent research objective. New AM-settled index products
  require their own settlement/spot treatment, not XSP/SPXW defaults.
- **Paper environment.** Every supported candidate needs a general Alpaca-paper order, inventory,
  cancel, fill, restart and reconciliation path. The current one-lot SPY proof establishes only
  route connectivity. Paper is for execution diagnostics and rehearsal; synthetic fills never
  establish a real fill model or live profitability.
- **Time splits**, for every family and program:

  | Window | Dates | Use |
  |---|---|---|
  | Train | 2020-01-02 to 2024-12-31 on the live swarm (2022-2024 for the added names); 2022-01-03 by default | the inner loop; agents see everything |
  | Validation | 2025-01-02 to 2025-12-31 | selection; agents see only summaries |
  | Holdout (sealed) | 2026-01-02 to 2026-09-25 | one look per program version at the gate; never on a Gym box |
  | Forward | each trading day from Sept 28, 2026 | the judge: nightly replays, live shadow, real money |

  The Gym serves only the expiries that existed on each day (SPY and QQQ daily expiries from
  mid-Nov 2022; IWM's Tuesday and Thursday expiries from 2024). Train's first day is the switch
  `gym.train_from` ("2017-01-03", "2020-01-02" or "2022-01-03"), adopted together with a Gym image that holds
  those years; the swarm's live settings have used 2020 since Sept 28. A 2017 image (Train from 2017) is built
  with each root fetched only from 2020 at its own first day (`images.py --root-first`).

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
  it is short (the defaults; the live settings start six and allow sixteen).
- **The engine** is a vectorized, day-major replay: it loads a day's chain once and runs a batch of
  programs over it. Each program sees the chain only through its `ctx`, one decision step at a time,
  with nothing from the future; the engine owns the clock.
- **Honest fills.** A structure fills against each leg's recorded NBBO on the minute after the
  decision: at the natural price (every leg's half-spread paid) by default; better only with the
  probability the fill model gives, keyed by (contract, minute), never by the program, so an edit
  cannot re-roll luck. The model is calibrated on Train days from `trade_quote`; real fills move it
  only through the frozen recalibration protocol's held-out test (even sessions fit, odd sessions
  test, at most four looks) and the owner's advance commitment to its rule. Paper fills prove the
  order route, never the calibration. Size is capped by the quoted size. A family must stay positive
  at 1.5x the half-spread to pass the gate.
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
- **Population:** by default 48 researchers at the start, a ceiling of 96 and a floor of 16; the
  live settings (Sept 29) start at 96, the ceiling, with a floor of 12. Families compete for Gym time
  and model calls through a bandit over their validation evidence (Thompson sampling). Since R11b only
  an old family whose latest validation mean is positive is exploited, each earning at most 15% of the
  share; new families and old ones at zero or below share the rest, never less than 25%. A family
  retires when its best program has not improved on validation in 30
  revisions or 2,000 evaluations by default (200 and 4,000 live), or its trial-adjusted evidence falls
  below the line, or by the idle rule: evaluations without an eligible Train version (150 by default,
  500 live) or cycles with no new evaluation (40 by default, 12 live), checked every five minutes. An
  idle-rule death is filed under the verdict of its Train record (R11b): DRIFT, STRESS, THIN or
  EXHAUSTED are tested findings, and only a family that never traded on Train is IDLE, a time limit.
  A family that holds three cycles in a row with a Train record behind it is offered `retire`, and its
  researcher's own retirement is SELF-REFUTED. A family whose latest validation met six of the eight
  checks is exempt from the dormancy clause until its 2017-19 extension result lands. Its
  lessons go to the graveyard, which every new family's researcher reads first. The graveyard is ranked
  by BM25, a new family is born with three distinct lessons, and it also holds the operator's own
  experiments as `op-` lessons.

## The loops

| Loop | Cadence | Who | What happens | Output |
|---|---|---|---|---|
| Inner | seconds to minutes | each researcher | revise the program, run it on Train, read the diagnostics, revise again | a better program or a lesson |
| Tournament | hourly | the House | validation runs of each family's best versions, the bandit's reallocation, forks and retirements, the leaderboard | Gym time and model calls follow evidence |
| Architect | every 4 hours by default, refilling hourly below the start; every 10 minutes live, refilling every 20 | Claude (Claude-only live: `architect.openai_model` null); Kimi-K3 on Sail as the fallback when Claude has no room or line (never after a cut answer: R11b salvages its complete families and retries once on Claude at medium effort) | reads the leaderboard, the graveyard and the gaps; writes families with a mechanism, a structure and a rejection test; at most 12 living families a mechanism class (R11b) | 3-6 new families by default; the gap to the start, up to 24 a pass live |
| Diagnostician | every 5 minutes | Claude | reads a stuck or nearly-there family's Train diagnostics (never Validation's numbers); rewrites its mechanism or writes its lesson; live: 6 a round, a family every 3 hours, $60 a day | a new mechanism, or a lesson and a retirement |
| Gate | when a family meets the validation line | review: Claude when "review" is in `claude.roles` (live: Sonnet 5.5), else GPT-6 Sol while the OpenAI month has room and `gate.review_openai_model` names it (null live), else DeepSeek-V4-Pro on Sail; audit: Claude (live: Opus 5.5, `claude.role_model`), then GPT-6 Astra on the same terms (null live), then a second Sail model; the gate box | review for lookahead, leakage and fill abuse; the audit; one holdout look | a Candidate, or a recorded refusal |
| Nightly forward | after 01:45 ET each trading night | the data box, the gate box | the new day goes to the gate image only; every Candidate is re-run on it | one unseen day a night for every Candidate |
| Live | 09:30-16:00 ET | the House | the practice league: every alive family's validated or eligible Train version in observe shadow (two caps: 48 instances, 24 roots); Candidates in live shadow; Probes and Sized on real money; the House's D3 calibration round trips and its live test; no general agent paper book yet | separate paper, shadow, practice and real records |
| Post-mortem | after each close; weekly | the operator for now (no scheduled post-mortem is built; it would run on Claude, whose `reserve_usd` is kept for it) | compare captured executions with the Gym; diagnose gaps and propose repairs | private reports; calibration only through the recalibration protocol |

**Models** (Sept 29, 2026; only Sail and Claude are topped up from now on). The inner loop runs on
Sail's DeepSeek-V4-Flash (V4.1-Flash where long cached histories make it cheaper), with a cache key per
agent and the shared contract cached once a day; the bandit's top `researcher.top_families` (10 by
default, 12 live) run on DeepSeek-V4-Pro at low effort. **The top band on Claude** (PR #417): the
bandit's top `researcher.claude_top` families by weight (12) run their research cycles on Claude Sonnet
5.5 at medium effort through the gateway, with the same loop, tools and limits, so the families closest
to passing get the strongest reasoning. A cycle is Claude's when it has fresh evidence (a queued run or
a rewrite landed), after a cycle that did not hold, and on every third cycle of a hold streak; the rest
of a streak is the family's Sail profile's. Every Claude failure (a refusal, a cut answer, the funded
total or a daily line reached, a timeout, an input that does not validate, an answer that cannot be
read) finishes that turn on the family's own Sail profile, never a cycle error, and a breaker pauses
the band after repeated unknown bills (league/swarm/claude_research.py). A researcher that stalls for 5
revisions escalates one rewrite to DeepSeek-V4-Pro asap (Kimi-K3 for the top ten families), or to Claude
when "rewrite" is in `claude.roles`. Bulk overnight variants go through Sail's Batch API. Through the
gateway, Claude answers first for the roles in `claude.roles` (by default the architect, the gate's
audit, the diagnostician and the researcher's top band), each role within its own optional daily line
(`claude.role_usd_day`; the researcher's is $100) and model (`claude.role_model`; the researcher's is
Sonnet 5.5), on `claude.model` (Opus 5.5 by default). Since 04:53Z Sept 29 the live settings put all
five one-shot roles on Claude: Sonnet 5.5 for the architect, the diagnostician, the rewrite ($15 a day)
and the review ($5 a day), and Opus 5.5 for the audit, so a program's two reads stay two different
models. By default GPT-6 Sol reviews programs and GPT-6 Astra stands behind the audit while OpenAI's
funded month lasts (to Sept 30), on its half-price flex tier wherever latency does not matter; the live
settings switch both off, so OpenAI is unused. Sail is the last fallback of every role but the
diagnostician.

## Evidence

- **Every Gym evaluation is a trial**, counted per lineage (forks inherit their parent's count and
  holdout looks) and in total on the ledger.
- **The validation line** (a family's best program): at least 50 trades on at least 25 distinct
  days in Validation; mean P&L per dollar of maximum loss above zero after fees with a one-sided t of
  at least 2; a deflated Sharpe probability of at least 0.95 on the traded-day Sharpe, against the
  lineage's validated versions (inherited ones included); positive in at least 3 of Validation's 4
  quarters; positive at 1.5x the half-spread. The owner's decision D2 (Sept 26, 2026) set these; it
  also limits what a researcher sees of Validation to pass or fail and a count of checks passed.
  A version reaches Validation only after its 1.5x-stress Train robustness run made a profit and it
  passed the drift screen (its Train alpha net of the root's own move, pooled t at least 1, positive
  in every Train year but one); the gate refuses a look at a version that fails the screen.
- **The holdout line**, one look per program version and at most three per lineage: P&L after fees
  positive; a day-block bootstrap one-sided 95% lower bound on mean daily P&L above zero, with a
  Holm-Bonferroni correction across every holdout look the swarm has made; holdout Sharpe at least
  half the validation Sharpe. **Researchers learn only pass or fail**, never the holdout's numbers.
- **Forward days never reach a Gym box.** Nightly forward replays run on Candidates only; they move
  bands and never select among Gym programs.
- **The forward record** (nightly replays, live shadow and real trades) is what sizes money. A
  Candidate whose forward record turns negative over 20 trades loses its band. Families whose code
  was written with knowledge of 2024-2026 need a forward record before they are Sized.
- **Practice is a research signal, never evidence** (the practice league, Sept 29, 2026). Every alive
  Gym-band family with a validated or eligible Train version trades live quotes in the House's shadow book
  under the Gym's own fill rules: live days from Sept 29 on are the one period no model behind the
  researchers has seen. Its record (`observe.sqlite`, private) is never a forward row and never reaches the
  verifier, the gate, the holdout, the bands or the money table. Research reads it: the strategist a
  PRACTICE table (by mechanism class and family: sessions, trades, the sign of realized P&L, a t; never
  dollars, dates, versions or code), the architect PRACTICE BY CLASS lines, and the bandit a capped bonus
  (a family gains at most 25% of its share, all bonuses move at most 10% of share; the weight only orders
  research, Train jobs, retirements and the Claude band). Promotion to real money is D2 exactly:
  Validation, the holdout, then the money table.
- **Immutable practice cohorts.** A program survives research retirement and newer revisions long enough to collect
  observations: three observed sessions and ten program closes while flat, or a bounded horizon that accommodates its
  declared DTE. Snapshots, coverage, decisions, quotes, rejected orders and fill receipts survive restarts in the private
  practice ledger. Completed snapshots never re-enter. Researcher feedback becomes actionable at ten program closes
  over three close-session days; a new feedback revision wakes an idle researcher without paying for idle polling.
- **The forward embargo.** Because practice now lets forward-window days select among Gym programs, a Sized
  move also needs the forward record of the sessions after both the banded version's creation and selection to meet Sized on
  its own; demotion and every other rule still read the whole record. This only makes Sized harder; the
  Validation and holdout periods end before any practice day and are untouched, and the money digest does
  not move.
- **The leakage alarm:** once there are at least 10 holdout looks, if more than 30% pass, the gate
  stops until leakage is ruled out.
- The lines may be tightened on evidence; loosening one is the owner's decision.

## Money

**Bands:** Gym, Candidate (shadow only), Probe (real, small), Sized (real, by evidence), Retired.

| Rule | Now (D4, Sept 26) | Allowed range |
|---|---|---|
| Probe: a Candidate that passed the holdout, has a verified/enabled execution type, and whose typical maximum loss fits the cap at current equity | real from its next session; real money opens four debit types | - |
| Credit structures on real money | only from $2,000 of equity, in one deploy with the gateway's list and a re-ratified grant (#393, the owner's decision); debit types until then | - |
| Probe max loss per structure | 5% of equity | 2-5% |
| Probe open structures per family | 3 | 1-5 |
| Probe family total max loss | 15% of equity | 8-15% |
| Probe floor for a small account | one contract when its max loss is at most $100 | $0-100 |
| Sized: current-version forward record of at least 20 trades, mean > 0 and 80% lower bound > 0, plus at least 5 real Probe trades and 1 whole Probe session | quarter-Kelly on the lower bound; paper/shadow alone cannot satisfy the real minimum | eighth- to half-Kelly |
| Sized max loss per structure | 10% of equity | 5-15% |
| Sized family total max loss | 30% of equity | 20-40% |
| Book: open max loss, all families | 90% of equity | 50-90% |
| Daily stop: the day's realized plus marked loss | 35% of start-of-day equity: no new entries that day | 15-35% |
| Drawdown stop from the peak since the reset | 60%: real money paused, exits go on, the owner told, the Gym keeps running | 40-60% |
| Execution tuition: 1-lot real orders before the holdout, to measure multi-leg fills (never evidence) | $200 max loss a day, $300 a week | $0-200 a day |
| D3 calibration: the House's own 1-lot round trips on SPY, QQQ and IWM (never evidence) | $50 of possible loss a day | - |
| The House live test: one frozen, pre-registered program as the House's own instance (never evidence) | a structure at most $100, 3 open, $300 at risk, no new open after a $150 loss, 20 sessions, 30 round trips | - |

- **Sizing is by maximum loss**, never by premium.
- **The order path:** the House nets every agent's intents into one order stream per contract;
  never sends opposing orders on one contract; queues or refuses an intent against a contract
  another agent holds; reserves maximum loss plus fees plus 10% of buying power before sending;
  stays under 250 orders a day (counting cancels and each leg until the venue's counting is
  verified) and 150 requests a minute; sends no new opening order on an expiring contract after
  15:00 ET; closes expiring equity-option structures with a short leg near the money by 15:10 ET
  (15:25 for SPY and QQQ) with one multi-leg order; and polls account activities for assignments.
  The current real adapter permits four debit types. Broader research or a paper round trip alone
  does not implement another production type: its accounting, exits, gateway rules and tests must
  also agree before that type is enabled.
- **The gateway's caps follow the account:** per order, maximum loss at most the lower of $1,000 and
  25% of equity; opening maximum loss a day at most 100% of equity; 300 orders a day; the kill
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
| Researchers' inner loop | Sail | DeepSeek-V4-Flash asap (V4.1-Flash for long cached histories); cached contract | the researcher Sail pace, $12 an hour live |
| The bandit's top families | Sail | DeepSeek-V4-Pro asap at low effort (10 families by default, 12 live) | inside the same pace |
| Rewrites on a stall | Claude, or Sail | Claude when "rewrite" is in `claude.roles` (live: Sonnet 5.5); else DeepSeek-V4-Pro asap, Kimi-K3 balanced for the top ten | capped per family per day; Claude's $15 a day live (`claude.role_usd_day`) |
| Bulk overnight variants | Sail Batch | V4-Pro flex | capped per night |
| Program review before live shadow | Claude or OpenAI via the gateway | Claude when "review" is in `claude.roles` (live: Sonnet 5.5); by default GPT-6 Sol, flex, while the September month has room (off live); else DeepSeek-V4-Pro on Sail | Claude's $5 a day live; about $0.03 a program on Sol |
| Architect | Claude via the gateway | `claude.model` (Sonnet 5.5 at $2 input, $10 output per million tokens; Opus 5.5 at $4 / $20), Claude-only live; Kimi-K3 on Sail as the fallback | inside Claude's funded total |
| Gate audit | Claude via the gateway | `claude.role_model["audit"]` or `claude.model` (live: Opus 5.5); GPT-6 Astra while the September month has room (off live), then a second Sail model, as fallbacks | inside Claude's funded total |
| Diagnostician | Claude via the gateway | `claude.model` | `diagnostician.usd_day`, $60 a day live |
| Weekly post-mortem | - | not built; the operator writes the post-mortem | - |
| Gym | Sail boxes | 4-8 sealed size-l boxes by default, up to 16 live | $0.10-0.40 an hour each while busy; asleep when idle |
| Data | Sail box + ThetaData | one size-l box, asleep when idle | $5-15 a day while running |
| The House | Sail box | one size-s box | about $0.03 an hour |
| History, the nightly forward day, fill calibration | ThetaData | four concurrent requests | $80 a month |
| Live quotes, SIP bars, paper and real orders | Alpaca | through the gateway | already paid |

- **Budgets.** The training burst was planned for Sept 26 to Monday Sept 28's open (Sail at most
  $350, OpenAI at most $150). The owner extended it for 24/7 research: the swarm's Sail burst runs to
  Oct 5 at most $900 (`guard.burst_cap_usd`). OpenAI is not topped up after September; Claude spends
  within the owner's funded total (`CLAUDE_USD`, the swarm's `claude.usd_cap`). After the burst the
  plan's rule stands: Sail at most $12 a day until Net is positive over 30 days; then compute may grow
  to half the trailing 30-day gross options profit. When the forward record is flat, compute drops to
  the floor: the nightly forward replay, live shadow and one architect pass a day.
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
their maximum loss and P&L, and the agents' decisions in their own words. A positions table (Sept 28)
lists every closed and open position and adds up exactly to Profit, with the House's own rows
labelled "House calibration" and "House live test"; it is an opt-in read
(`/api/capital/checkpoint?progress=1&positions=1`), and the default read omits it.

**Never quotes, spreads, implied-volatility surfaces or fitted parameters**, on the site, in the
public JSON or in this repository: the data licenses forbid it. The publisher strips every quote
field and a test proves it. Programs and fitted parameters stay in the House's state and on Sail.

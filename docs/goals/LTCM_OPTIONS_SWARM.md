# The options swarm: prune to one goal, train in agent time, trade Monday

**One goal.** A game in which a swarm of AI agents trades anything available with level-3 options on
the owner's brokerage account, profitably: options returns greater than everything the project
spends (Sail, OpenAI, ThetaData, the market-data subscription, and anything this plan adds).

Everything in this repository after this run serves that goal or leaves. This plan replaces every
earlier goal file; those move to the archive.

## The owner's direction (Friday Sept 25, 2026, late evening Pacific)

- **One focus.** "A game design that allows for a swarm of trading agents who can trade anything
  available with level 3 options on my Alpaca account profitably. This means returns from options
  trading is greater than Sail, openai, theta data, alpaca market data subscription." Kalshi is
  out: its markets are not liquid enough to scale. Options are the focus because of their upside,
  bets in both directions, and capacity if the owner adds a lot of capital.
- **(1) Agent time, not human time.** "If 10k agents were able to solve the Navier Stokes theorem
  in 80 days, I think our trading agent swarm can reach profitability soon if we push them 24/7 in
  a rapid learning loop game design that is running in agent time scale not human."
- **(2) Bold.** "The money I have in alpaca can be all lost ... be very bold and ambitious here in
  our approach. Don't hold back."
- **(3) Budget.** Up to $10,000 across the brokerage balance, Sail, OpenAI and whatever else helps;
  the allocation is below.
- **(4) The website starts fresh.** Clear it. The copy says "AI agents trading options." and never
  names Alpaca; the account is the "Brokerage Account". The balance starts from the current account
  balance; total profit and the running timer reset; every historical agent is cleared.
- **(5) One ultra-clean repository.** Pruned of historical iterations; anything of value goes to an
  archive folder so the project's evolution stays understandable.
- **(6) Best use of every input.** Understand Sail, OpenAI and the market data fully before
  designing; the facts section below is that understanding, verified on Sept 26.
- **(7) The schedule.** Rework everything tonight (Friday night into Saturday), train the swarm on
  Saturday and Sunday in a game built for rapid learning, and trade options on Monday's open.
- **ThetaData stays.** The Options Standard subscription ($80 a month) is a permanent, integral
  part of the project.

## The one number

**Net = the options book's realized P&L on the Brokerage Account, after every fee, minus every
input cost** (Sail, OpenAI, ThetaData, the market-data subscription at about $1,000 a year, and
anything added). The scoreboard reports Net daily, weekly and since the reset. A change that cannot
say how it raises Net does not ship.

The bar, at the steady-state budgets below:

| Input | Monthly |
|---|---|
| Market data (Algo Trader Plus, about $1,000 a year) | $83 |
| ThetaData Options Standard | $80 (or $64 billed annually) |
| Sail after the training burst | $250-360 ($8-12 a day) |
| OpenAI after the training burst | $150-300 |
| **Total** | **about $565-825** |

On a $6,500 account that is 9-13% a month before Net turns positive, so capital is part of the
answer: the bar falls in proportion as the account grows, and compute is cut to the floor whenever
the forward record does not pay for it (the compute rule under "Compute").

## Where things stand at plan time (Sept 26, 2026, about 06:00Z)

- **The House is paused** (maintenance, since 03:55:56Z; exits and reconciliation only). Release
  `20260926T032739Z-aaf5ac74637c` (options Deploy G, main `a1f9a8e7`); `origin/main` is `89bc49a1`.
  The live grant `earned-live-20260921` is active on money digest `be1e3ce9`. 128 agents in 121
  families (76 Alpaca, 45 Kalshi) and 627 dead. Since Sept 19: tracked profit +$4.84 against $680 of
  compute.
- **The Brokerage Account** (read through the gateway at 05:45Z): equity $481.78, cash $457.05,
  options approved and trading at level 3, multiplier 1 (Alpaca's limited margin tier under $2,000:
  no margin, no shorting). Leftovers of the old desks: XRP 7.90 and SOL 0.10 held by two crypto
  probes, crypto dust on the House row, one resting SOL sell. No option position.
- **Kalshi** holds about 30 two-contract weather NO positions and 15 CIN-TOR NO, all settling at the
  venue within days, and a real book frozen by the owner's hand sales. Nothing in the new system
  reads Kalshi again; the owner withdraws that cash when it settles.
- **ThetaData Options Standard is live** and its key is at `~/.config/thetadata/env` on the laptop
  (mode 600). Verified at 05:3xZ with the official Python library (`~/Work/.options-history/.venv`,
  `thetadata` 1.0.11 with python-dotenv, polars, pyarrow; probe script
  `~/Work/.options-history/probe_theta.py`):
  - authentication in 0.6 s;
  - SPY and QQQ list an expiry every weekday from Feb 2024 (666 in Feb 2024 to Sept 2026), IWM 645;
  - one-minute NBBO with sizes for 42 SPY 0DTE contracts over a full day came back in 3.5 s: 406 rows
    per contract, 09:30 to 16:15 ET, the 09:30 row empty;
  - `option_history_trade_quote` (the NBBO at each trade) works: 243 trades for one contract-day;
  - a first reading: an at-the-money SPY 0DTE call on Feb 12, 2024 quoted a median $0.12 spread on
    a $5.78 bid, about 2% of premium; the old replay assumed 4%.
- **Compute:** OpenAI's September month $595.79 of $607; Sail $118.93 (04:06Z Sept 26; the burn
  was $34 a day before the pause); Jev $17.17 of $42 (dropped by this plan).
- **Clutter:** 38 worktrees under `~/Work`, 45 unmerged local branches, 14 open PRs, a 20 GB
  `.data` in the main checkout, 118 files under `docs/`, a 104 KB README, a 75 KB strategy contract
  (paid on every model call), `league/` 90k lines + 77k of tests, the legacy `ltcm/` 50k + 35k,
  CI 10-20 minutes.
- **Research behind this plan:** `.data/research/nbbo-sources-2026-09-26.json` (the NBBO vendor
  study, 11 agents with fact-checks) and the four Sept 26 maps summarized in the next section.

## The facts the design rests on (verified Sept 26, 2026)

### The venue: Alpaca options, one account

- **The pattern-day-trader rule is gone.** SEC Release 34-105226 (Apr 14, 2026) approved FINRA's
  replacement; effective June 4, 2026. Alpaca removed the PDT designation, the day-trade count and
  the $25,000 minimum on June 4 (the API fields were deleted by July 6), replacing them with a
  real-time intraday margin check that rejects any order creating a margin deficit. **The swarm
  may open and close the same day as often as it likes.**
- **Every account is a margin account.** Under $2,000 of equity it is "limited margin", 1x, no
  shorting; spreads need `options_buying_power` equal to their maximum loss (a debit spread costs
  its debit; a credit spread costs width × 100 minus the credit). Options settle T+1.
- **Structures:** multi-leg orders of at most 4 legs, every short leg covered inside the same order,
  ratios in lowest terms, market or limit (a positive limit is a debit, a negative one a credit),
  `day` time in force (GTC on multi-leg is unverified). Replace only the whole order. Close a
  structure with one multi-leg order; never leg out the short leg first. Each leg shows as its own
  position.
- **Index options since Sept 2, 2026:** SPX, SPXW, XSP, VIX, VIXW and DJX are cash-settled and
  European. Every leg of an index multi-leg order has the same expiry (no index calendars or
  diagonals); morning-settled contracts cannot trade on their expiry day; SPXW and XSP stop at
  16:00 ET. NDX and RUT are not supported, nor is the index spot feed.
- **Expiry day:** orders on expiring contracts must be in by 15:15 ET (15:30 for SPY and QQQ).
  From 15:30 ET (15:45 for broad ETFs) Alpaca liquidates expiring positions it cannot carry, and
  may close slightly out-of-the-money ones. Auto-exercise at $0.01 in the money. SPY, QQQ, IWM and
  single-name options are American and physically settled: an assigned short leg becomes shares and
  can bring an assignment lock. Cash-settled XSP and SPXW carry no assignment.
- **Order rate:** averaging over 390 orders a day in a month (cancels included) makes the account
  "professional" under Cboe's 390 rule, which brings commissions. Accounts with fill rates under 1%
  or rapid create-and-cancel get flagged non-retail. The Trading API allows 200 requests a minute.
- **Wash-trade protection:** opposing orders that could cross on one contract are rejected (403),
  paper included. Many agents on one account collide unless the House nets them.
- **Fees:** $0 commission on equity options (while retail); OCC $0.025, ORF $0.015 and CAT $0.0003
  a contract on both sides, TAF $0.00329 a contract and the SEC fee on sells; index options $0.50 a
  contract plus exchange fees (XSP: $0 exchange fee under 10 contracts). Paper leaves regulatory
  fees out. Price ticks $0.05 under $3 and $0.10 above, except penny-class contracts and SPY, QQQ,
  IWM.
- **Hours:** options trade 09:30-16:00 ET only; orders sent after the close queue for the next day.
  Assignments are not pushed; poll the account activities.

### The data

- **ThetaData Options Standard ($80/mo):** every OPRA NBBO (tick level) since 2016 at any interval
  (1 minute for multi-day requests), trade prints with the NBBO at each trade (`trade_quote`),
  historical implied vol and first-order greeks, open interest, EOD; index options as well as
  equity options (verified Sept 26: XSP and SPXW list 435 expiries each since 2025, and a 0DTE day of
  one-minute NBBO comes back in 5-10 s, sessions ending 16:00); real-time snapshots and a stream of
  10,000 quote contracts. **The index and stock endpoints need separate subscriptions** (the SPX
  index price and SPY stock bars answer PERMISSION_DENIED), but **the options greeks history
  carries the underlying's price every minute** (XSP's is SPX/10) with bid, ask, implied vol and
  first-order greeks, verified on an XSP 0DTE day. Four
  concurrent requests account-wide. The Python library talks gRPC over TLS to
  `mdds-01.thetadata.us:443` after authenticating at `nexus-api.thetadata.us:443`; no Java is needed.
  Pass `interval='1m'` explicitly (the default is 1 s). Keep each response under a million rows;
  multi-day requests name an expiry and span at most a month. The previous day is unavailable
  00:00-01:45 ET. Terms: personal, non-professional use; no publication or redistribution of the
  data or of works derived from it (quotes, spreads, fitted parameters).
- **Alpaca Algo Trader Plus (already paid, about $1,000 a year):** live OPRA NBBO (a WebSocket of up
  to 1,000 option symbols, msgpack; chain snapshots with sizes and greeks through the gateway's
  existing route); SIP stock bars and quotes since 2016; option bars and trades since Feb 2024. **No
  historical option quotes** (Alpaca staff, June 17, 2026: not on the roadmap). 10,000 data calls a
  minute. No 0DTE greeks in snapshots. Its terms also forbid republishing quotes.

### Sail

- **Inference** (USD per million tokens, input / cached / output):

  | Model | asap | balanced | flex |
  |---|---|---|---|
  | DeepSeek-V4-Flash-0731 | 0.09 / 0.02 / 0.18 | 0.07 / 0.02 / 0.14 | 0.05 / 0.01 / 0.09 |
  | DeepSeek-V4.1-Flash | 0.15 / 0.006 / 0.60 | 0.12 / 0.005 / 0.48 | 0.08 / 0.004 / 0.30 |
  | GLM-5.3-Flash | 0.11 / 0.02 / 0.35 | 0.08 / 0.02 / 0.28 | 0.05 / 0.01 / 0.18 |
  | DeepSeek-V4-Pro-0813 | 0.92 / 0.04 / 2.77 | 0.74 / 0.03 / 2.22 | 0.46 / 0.02 / 1.39 |
  | GLM-5.3 | 0.98 / 0.18 / 3.08 | 0.50 / 0.12 / 2.50 | 0.40 / 0.08 / 1.80 |
  | Kimi-K3 | 2.50 / 0.25 / 12.50 | 2.00 / 0.20 / 10.00 | 1.25 / 0.15 / 6.25 |

  Responses API recommended; `background: true` works for balanced and flex only; no
  `previous_response_id` (each turn resends history, so caching matters); `prompt_cache_key` routes
  the cache; **supercache** keeps a prefix of at least 1,025 tokens for 24 hours (writing costs 100x
  the input price, reading 10% of the cached price). Batch: up to 100,000 requests and 256 MB, at
  the chosen window's price, no latency promise. Results expire 10 minutes after the first read:
  store them at once.
- **Sailboxes:** $0.015 per vCPU-hour, $0.008 per GiB-hour of RAM in use, $0.0007 per GiB-hour of
  disk; **sleeping, paused and checkpointed boxes cost nothing**. Sizes: s 1 vCPU (2-64 GiB, 8-128
  GiB disk), m 4 vCPU (8-128 GiB, 32-512 GiB), l 8 vCPU (16-256 GiB, 64-1,024 GiB). Size is fixed at
  creation; a fork keeps its source's size and egress. `{"no_network": true}` seals a box while exec
  and file transfer keep working. Checkpoint lifetimes up to years (`ttl_seconds`; the project's 30
  days was its own default). Egress allowlists take 128 hostnames, wildcards or IPv4 ranges; a
  hostname entry passes TLS with SNI. Secrets inject only into HTTPS headers or query strings. The
  free plan allows 100 concurrent boxes. **Running out of credits pauses every box, the House
  included.**

### OpenAI (through the gateway)

- **Prices** (per million, input / cached / output): GPT-6 Astra $10 / $1 / $50; GPT-6 Sol $2 /
  $0.20 / $10; GPT-6 Luna $0.10 / $0.01 / $0.50. Flex (`service_tier: "flex"`) and Batch are half
  price; prompt caching reads at 0.1x for 30 minutes. The gateway's price table matches.
- **Fine-tuning and RFT are closed** (no new jobs; no GPT-6 fine-tuning; RFT's only base model shuts
  down Oct 23): the swarm learns in its own Gym, not by training a model.
- **The gateway today** forwards `/v1/responses` only, standard tier, text input, at most 16,000
  output tokens, no structured outputs. Flex needs about 20 lines and tests (a `flex` rate per model;
  charge flex only when the response reports it).

## The game

### Agent time

The market trades options 6.5 hours a day, about 1,640 hours a year. A human learns from those
hours as they happen; the swarm must not. **The swarm learns in the Gym, on real recorded quotes,
at thousands of times real speed, and uses the live market as the judge of what it learned, not as
its teacher.**

- One Gym core replays a program over a year of one-minute NBBO in about a minute: roughly 100,000
  times real time. Six 8-vCPU Gym boxes are about 48 cores; running a weekend, that is several
  million market-hours of experience, tens of thousands of program evaluations, and every agent
  revising its program many times an hour.
- Every clock in the game is set by what an agent can learn from it, never by the calendar: the
  inner loop runs in seconds to minutes, selection in hours, the gate the moment evidence is
  enough, forward evidence every night and every market minute.
- 24/7 means: nights and weekends in the Gym and the nightly forward replay; market hours in live
  shadow trading of every candidate at once, plus real money. Nothing waits for a human.

The danger at this speed is fooling ourselves: a search over tens of thousands of programs finds
something that looks great on any window by chance. So the game's rules on evidence are as
important as its speed (below), and every program evaluation is counted as a trial.

### The world

- **Universe.** The core: SPY, QQQ and IWM (ETF options, physically settled, daily expiries), and
  XSP and SPXW (cash-settled index options: 0DTE can be held to expiry with no assignment). Then
  the top 20 or so single names and ETFs by average daily option volume with tight quoted spreads,
  chosen from ThetaData's EOD data in Wave 1. "Anything available" holds: any optionable
  underlying is admissible once its data is in the Gym, and the backfill is flat-priced.
- **Structures:** everything level 3 allows, all defined-risk: debit and credit verticals, iron
  condors, iron butterflies, long butterflies, long straddles and strangles, calendars and
  diagonals (equity options only), plus single long calls and puts. No naked short anywhere (the
  venue refuses it anyway).
- **Horizons:** 0-5 days to expiry is the center, because each agent then closes one or more
  independent trades a day and its evidence clock runs in days; calendars and diagonals may hold a
  back leg to 45 days.
- **Time splits** (every family, every program, no exceptions):

  | Window | Dates | Use |
  |---|---|---|
  | Train | 2022-01-03 to 2024-12-31 | the inner loop; agents see everything |
  | Validation | 2025-01-02 to 2025-12-31 | selection; agents see only summaries |
  | Holdout (sealed) | 2026-01-02 to the last full day before T0 | one look per program version at the gate; never on a Gym box |
  | Forward | each new trading day after T0, and live from Monday Sept 28 | the judge |

  SPY and QQQ have daily expiries only from mid-Nov 2022 (Mon/Wed/Fri before), and IWM's Tuesday
  and Thursday expiries start in 2024; the Gym serves what existed on each day and nothing else.

### The Gym

The Gym is the new heart of the project: the place where agent-written programs meet real
recorded quotes, fast and honestly.

- **The store.** One-minute NBBO (bid, ask, bid size, ask size) per contract from ThetaData, for the
  universe's strikes around the money and 0-14 days to expiry (0-45 for the calendar back months),
  written as Parquet partitioned by underlying and day; underlying one-minute bars from Alpaca's SIP
  history (SPY/QQQ/IWM/stocks) and, for XSP/SPXW, the `underlying_price` of ThetaData's greeks
  history (verified; the index endpoint itself is not in the subscription); ThetaData's implied vol
  and first-order greeks where the engine does not compute its own; daily open interest;
  `trade_quote` samples for fill calibration. Exchange and condition columns are
  dropped from the store except where calibration needs them.
- **Where it lives.** A Sail **data box** (size l, 32 GiB RAM, 256-512 GiB disk; egress only to
  `nexus-api.thetadata.us` and `mdds-01.thetadata.us`, plus PyPI while it is set up) downloads and
  writes the store, holding the ThetaData key in its own 0600 env file and nothing else: no venue
  key, no gateway token, no agent code. It pauses when idle. A **golden Gym image** is built from
  the store without the key and without the holdout, then checkpointed with a long TTL (two
  checkpoints and a rebuild script, because Sail's checkpoint API has failed before).
- **Gym boxes.** Size-l boxes forked from the golden image and sealed with `no_network`. Programs go
  in and results come out through Sail's exec and files APIs. Start with four; scale to eight while
  the queue is long and the budget allows, and let them sleep when it is short.
- **The engine.** A new, vectorized replay (numpy/polars/pyarrow over memory-mapped Arrow): load a
  day's chain once, then run a batch of programs over it ("day-major batching"), so the data cost is
  paid once per day, not once per program. Each program sees the chain only through its `ctx`, one
  decision step at a time, with nothing from the future; the engine owns the clock.
- **Honest fills.** A structure fills against each leg's recorded NBBO on the minute AFTER the
  decision: at the natural price (paying every leg's half-spread) by default; at a better price only
  with the probability the calibrated fill model gives for that distance from the mid, the
  structure type, DTE, moneyness and time of day. The fill model starts conservative and is
  calibrated from `trade_quote` (multi-leg prints are identified by their condition codes), then
  from paper and real fills. Size is capped by the quoted size. Fees per the venue table. A stress
  run at 1.5x the half-spread must stay positive for a family to pass the gate.
- **Venue rules in the engine:** the expiry-day cutoffs and liquidation times, auto-exercise and
  physical settlement for equity options (an assigned short leg becomes shares at the close;
  programs that hold a short in-the-money leg into expiry take that risk in the Gym as they would
  live), cash settlement at the SPX close for XSP/SPXW, the buying-power check (max loss plus fees
  plus 10%), 09:30-16:00 only, and the price ticks.
- **What a run returns:** every trade (entry, exit, legs, fills, fees, max loss, P&L), the daily
  P&L series, P&L per dollar of maximum loss, win rate, profit factor, Sharpe on daily P&L,
  drawdown, turnover, fill statistics, P&L by year, quarter, weekday, time of day, DTE and regime
  (realized and implied vol terciles), and the worst trades with their context. Results are hashed
  and written to the ledger; runs are deterministic and reproducible from (program sha, data
  version, engine version, window).
- **Speed targets.** A program over one year of one underlying in 60 s or less on one core; at
  least 2,000 program-years an hour across the Gym by Saturday evening; a researcher's inner-loop
  answer (one program, train window) in under 3 minutes.
- **The holdout never touches a Gym box.** The gate runs on its own sealed box forked from a
  separate image that holds the holdout days, invoked only by the House's gate, with a ration of
  looks written to the ledger.

### The agent

- **An agent is one family:** a mechanism (why the trade should make money), a structure type and a
  universe slice, owned by a researcher model with a notebook (its memory), a lineage of program
  versions, and a record. Two agents never share a family; forks start new families.
- **The program** is one Python file with `NEEDS`, `PARAMS` and `decide(ctx)`, run at a decision
  cadence the program declares (1 to 30 minutes). `ctx` gives the time, the underlying's recent
  bars, the chain slice the program's `NEEDS` asked for as numpy arrays (strikes, expiries, bid,
  ask, sizes, mid, implied vol and greeks computed by the engine, open interest), the program's
  positions and cash, its risk budget, the venue rules and the calendar. `decide` returns structure
  intents (type, legs chosen by expiry, strike, delta or distance rules, quantity or a max-loss
  budget, a limit rule of natural, mid or mid plus k ticks, and a time in force) and exits. numpy
  and math are importable; nothing else outside the whitelist; no I/O.
- **The strategy contract** (`league/CONTRACT.md`) is rewritten for options only and kept under
  20 KB, because every researcher call pays for it; the rest moves to reference pages the
  researcher reads on demand.
- **Seeds.** The 12 structure founders from Deploy G (condor-vrp, putspread-dip, ironfly-quiet,
  strangle-cheap, calendar-term, butterfly-pin, orb, trend-vertical, reversal, skew, diagonal,
  gap-drift) re-expressed in the new contract, plus the architect's first library of mechanisms
  that the literature and the data suggest: the variance risk premium in short-dated index options,
  intraday momentum and trend days, opening-range breaks and fades, gap reversion, end-of-day drift,
  0DTE pinning near large open interest, term-structure and skew mean reversion, post-event
  volatility crush on single names, weekly-expiry dynamics.
- **Population.** 48 researcher agents at the start, a ceiling of 96 and a floor of 16. Families
  compete for Gym time and model calls through a bandit over their validation evidence (Thompson
  sampling with a 25% exploration share for new families). A family retires when its best program
  has not improved on validation in 30 revisions or 2,000 Gym evaluations, or its trial-adjusted
  evidence falls below the line; its lessons go to the graveyard, which every new family's
  researcher reads first.

### The loops

| Loop | Cadence | Who | What happens | Output |
|---|---|---|---|---|
| Inner | seconds to minutes | each researcher | revise the program, run it on Train in the Gym, read the diagnostics, revise again | a better program or a lesson |
| Tournament | hourly | the House | validation runs of each family's best versions, the bandit's reallocation, forks and retirements, the leaderboard | Gym time and model calls follow evidence |
| Architect | every 4 hours | GPT-6 Astra | reads the leaderboard, the graveyard and the gaps; writes new families with a mechanism, a structure and a rejection test | 3-6 new families |
| Gate | when a family meets the validation line | Sol, Astra, the holdout box | code review for lookahead, leakage and fill abuse; the audit; one holdout look | a Candidate, or a recorded refusal |
| Nightly forward | after 01:45 ET each trading night | the data box, the Gym | ThetaData's new day is appended to the forward store; every Candidate and the 100 best programs are re-run on it | one truly unseen day per night for all of them |
| Live | 09:30-16:00 ET | the House | every Candidate trades the shadow book on live OPRA quotes; Probe and Sized families trade real money; the paper account measures multi-leg execution | forward records, real P&L, real fills |
| Post-mortem | after each close; Astra weekly | the House, Astra | live P&L against what the Gym expected: fills, slippage, regime; the fill model recalibrated | calibration, lessons, repairs |

**Model use in the loops.** The inner loop runs on Sail DeepSeek-V4-Flash at asap (V4.1-Flash
where long cached histories make it cheaper), with a `prompt_cache_key` per agent and the shared
contract and rules supercached once a day. A researcher that stalls for 5 revisions escalates one
rewrite to DeepSeek-V4-Pro at balanced (Kimi-K3 at balanced for the top ten families). Bulk
overnight program generation (variants for the bandit's winners) goes through Sail's Batch API in
the flex window. GPT-6 Sol (flex) reviews every program before it reaches live shadow; GPT-6 Astra
is the architect (flex), the gate's auditor (standard: its latency matters) and the weekly
post-mortem (flex).

### Evidence: fast without fooling ourselves

- **Every Gym evaluation is a trial**, counted per family and in total on the ledger.
- **The validation line** (a family's best program): at least 100 trades on at least 60 distinct
  trading days in Validation; mean P&L per dollar of maximum loss above zero after fees with a
  one-sided t of at least 2; a deflated Sharpe probability of at least 0.95 given the family's trial
  count (`league/stats.py` has it); positive in at least 3 of Validation's 4 quarters; positive at
  1.5x the half-spread.
- **The holdout line**, one look per program version and at most three per family: P&L after fees
  positive; a day-block bootstrap 80% lower bound on mean daily P&L above zero; holdout Sharpe at
  least half of validation Sharpe.
- **The forward record** (nightly replays plus live shadow plus real) is what sizes money. A
  Candidate whose forward record turns negative over 20 trades loses its band.
- **Leakage alarm:** if more than 30% of the families that reach the holdout pass it, stop the gate
  and look for leakage before anything else.
- The lines may be tightened on evidence; loosening one is the owner's decision.

### Money

**Bands:** Gym, Candidate (shadow only), Probe (real, small), Sized (real, by evidence), Retired.

| Rule | Default | Allowed range this run |
|---|---|---|
| Probe: a Candidate that passed the holdout | real from its next session | - |
| Probe max loss per structure | 3% of Brokerage equity | 2-5% |
| Probe open structures per family | 3 | 1-5 |
| Probe family total max loss | 12% of equity | 8-15% |
| Probe floor, so a small account can still trade | one contract when its max loss is at most $60, whatever the percentage | $0-100 |
| Sized: forward record of at least 20 trades (nightly + shadow + real) with mean > 0 and an 80% lower bound > 0 | quarter-Kelly on the lower bound | eighth- to half-Kelly |
| Sized max loss per structure | 10% of equity | 5-15% |
| Sized family total max loss | 30% of equity | 20-40% |
| Book: open max loss, all families | 70% of equity | 50-90% |
| Daily stop: day's realized plus marked loss | 25% of start-of-day equity: no new entries that day | 15-35% |
| Drawdown stop: from the peak since the reset | 50%: real money paused, exits go on, the owner notified, the Gym keeps running | 40-60% |
| Execution tuition: 1-lot real orders from validation-passing families before their holdout, only to measure real multi-leg fills (never counted as evidence) | $100 max loss a day, $300 a week | $0-200 a day |

- Sizing is always by **maximum loss**, never by premium: the $75 premium cap that forced agents
  onto penny contracts goes.
- **The order path:** the House nets every agent's intents into one order stream per contract,
  never sends opposing orders on one contract, reserves maximum loss plus fees plus 10% of
  buying power before sending, keeps under 250 orders a day including cancels and under 150 API
  requests a minute, sends no new order on an expiring contract after 15:00 ET (index 0DTE
  included until the venue's index cutoff is verified on a live session), closes expiring
  equity-option structures with a short leg in or near the money by 15:10 ET (15:25 for SPY and
  QQQ) with one multi-leg order, and polls account activities for assignments.
- **The gateway's caps follow the account:** per order, maximum loss at most the lower of $1,000
  and 15% of equity; opening maximum loss a day at most 100% of equity; 300 orders a day; the kill
  switch unchanged. Real structures turn on (`OPTION_STRUCTURES_REAL` and constitution O1) for the
  types the venue accepts.
- **The grant.** A new grant, `options-swarm-20260928`, covers the Brokerage Account only, its
  capital the account's equity at ratification, pinned to the new money digest; the old grant
  `earned-live-20260921` is revoked. Changes inside this table re-ratify within a minute of the
  promotion that carries them.
- **Capital flows are the owner's.** Deposits and withdrawals are never profit: the publisher and
  the scoreboard read funding activities and net them out.

### Compute: every input at its best

| Job | Service | Model or size | Budget |
|---|---|---|---|
| Researchers' inner loop | Sail | DeepSeek-V4-Flash asap (V4.1-Flash for long cached histories); supercached contract | about $1-2 an hour at 48-96 agents |
| Rewrites on a stall; top families | Sail | DeepSeek-V4-Pro balanced; Kimi-K3 balanced | capped per family per day |
| Bulk overnight variants | Sail Batch | V4-Pro flex | capped per night |
| Program review before live shadow | OpenAI via gateway | GPT-6 Sol, medium, flex | about $0.03 a program |
| Architect, every 4 hours | OpenAI | GPT-6 Astra, high, flex | about $0.55 a pass |
| Gate audit | OpenAI | GPT-6 Astra, high, standard | about $0.90 an audit |
| Weekly post-mortem | OpenAI | GPT-6 Astra, xhigh, flex | about $2 |
| Gym | Sail boxes | 4-8 sealed l boxes | $0.10-0.40 an hour each while busy; asleep when idle |
| Data | Sail box + ThetaData | 1 l box, paused when idle | a few dollars a day |
| The House | Sail box | the existing s box | about $0.03 an hour |
| History, nightly forward day, fill calibration | ThetaData Standard | 4 concurrent requests | $80 a month |
| Live quotes, SIP bars, paper and real orders | Alpaca | via the gateway | already paid |

- **Dropped:** Jev (the House's sensors, the move sensor, the gateway lane), GPT-6 Luna research,
  Sail web search, the Alpha Lab, the hypothesis foundry, the semantic lab, Merton's six roles
  other than the architect and the engineer, every Kalshi, crypto and stock feed and recorder.
- **Budgets.** The training burst (T0 to Monday's open): Sail at most $350, OpenAI at most $150.
  After Monday: Sail at most $12 a day and OpenAI at most $300 a month until Net is positive over
  30 days; after that, compute may grow to half of the trailing 30-day gross options profit. When
  the forward record is flat, compute drops to the floor (the nightly forward replay, live shadow,
  one architect pass a day).
- **The gateway gains OpenAI flex** (a `flex` rate per model; the House asks for flex on every
  non-urgent call; a 429 settles at $0) and a per-role output ceiling above 16,000 for the
  post-mortem.

## The prune

The repository ends as one thing: the House, the Gym and the swarm for options, with the gateway,
the deploy tools and five documents. Everything else leaves `main`. Git keeps it (the archive tags
of Wave 0), and `archive/` keeps the documents that explain how the project got here. The map below
comes from a read-only survey of release `a1f9a8e7` on Sept 26; `file:line` references are to that
release.

### Three traps first

1. **The real-money grant lives in the campaign store.** `league/campaigns.py` and
   `campaigns.sqlite` hold it, and the House, the allocator and `capital.py` ask
   `campaigns.allows_live` / `live_authorization` before any real order (house.py 2630, 3337, 3655,
   4944-4953, 5212-5222, 5593, 5647, 5665, 8731-8735; allocator 1354, 1470, 2758, 2927; capital
   117). The new grant (`options-swarm-20260928`) moves into `league/live_trading.py` and the
   constitution BEFORE campaigns is cut, or real money silently turns off.
2. **Removing the Kalshi and crypto keys from the constitution moves the money digest**, which
   revokes the grant until it is re-ratified, and `PINNED_DIGEST` (constitution.py:718) moves with
   it.
3. **The in-box updater cannot carry this prune**: CI's forbidden paths (ci.py:47-52), the workflow
   pin (updater.py:116) and the release trees (updater.py:98, which also names `playbooks/`) all
   change. It ships as an owner deploy onto the fresh state root; `auto_update` stays off until the
   overhaul has run a day.

### `league/` (95 modules, 68,171 lines)

| Verdict | Modules | Notes |
|---|---|---|
| Keep | ledger, stats, episodes, parameters, runner, safety, structure_core, structures, experiments, recordings, preaudit, agents, capital, watchdog, backup, updater, worklist, engineer, sim, sandbox | `sandbox.py:143` imports `deep_replay.HOLDOUT`: move the constant. |
| Keep, rewritten for options only | house, book, allocator, evaluator, families, constitution, service, publish, ci, merton (architect and engineer only), niches (one options desk), rules, venues, fees, accounting, options_shadow, options_desk, live_trading, auditor, frontier, budget, `__main__`, `seeds/` | They wrap kept logic in Kalshi, crypto, equity and credit-economy branches. |
| Keep as the swarm's researcher, credits removed | researcher, commons, research_jobs, admissions, capabilities | The inner loop. Agent credits (researcher.py:438-960) become per-family budgets the tournament sets; `commons` keeps only what the loop uses. |
| Superseded by the Gym | options_replay, options_history, replay (its options path), tapes (keep only `AlpacaData`, 222-512, if the live path still needs it) | Deleted once the Gym passes its tests. |
| Cut: the credit economy | economy, campaigns, pacer, grants, funded, overnight, live_pilot, phase1, yield_ledger | Move first: `economy.load_game`, `check_bounds`, `Standing` (44, 50, 120). |
| Cut: the Alpha Lab and foundry | lab, labbox, hypotheses, hypothesis_memory | Move first: `lab.static_literal`, `with_params`, `mechanism_digest`, `family_at_capacity` (389, 405, 588, 621). |
| Cut: Jev and the semantic stack | jev, jev_features, semantic_lab, sensors, triage, exposure, research_gate, routing, fast_research, traces | Move first: `research_gate.provider_fault`, `completed_pass` (292, 299). |
| Cut: Kalshi | kalshi_founders, shards, paper, resolution | Move first: `paper._cursor`, `_at_or_after` and the order and fill (de)serializers (611-660), used by options_shadow:122. |
| Cut: feeds, stocks, crypto, other | feeds, open_feeds, history, deep_replay, consult_recovery, verticals | |

**Edges the prune must sever** (kept module: cut imports): house 44, 47, 52, 59, 629-641, 656, 663,
671, 692, 863, 1716, 4029, 4342-4423, 4356, 4395, 4507, 5243, 6244, 6985, 7187, 7199, 7665, 8825,
8850, 9908, 10784, and the tick's branches for the burst, meter, semantic lab, Jev, foundry, lab,
shards and payouts (10284-10373, 10485-10562), the Kalshi book hooks (711-712, 748) and the wakes
gated by `economy.alive` (10384); service 162-414 (and its defaults that switch cut features on when
a key is absent: feeds 266, kalshi_founders 245, traces 317, jev 327); merton 416, 871, 884, 894; ci
297 and 51; families 1342, 1483, 1503; frontier 133; niches 179, 275, 276, 354; options_shadow 122;
tapes 60, 534 and 513-1188; live_trading 13 (the policy demands both alpaca and kalshi) and 79;
researcher 28, 577, 945; allocator 658; capital 117; auditor 287; publish 972, 1022, 1219; book 79,
4184; fees 40; venues 14, 16; evaluator 64.

**Seeds, strategies, tools, playbook:** keep the 14 `options_*` seeds and the 9 option-family
strategies (krasker_* and options_breakout_occ_exits); cut the other 13 seeds and 74 strategies;
keep the realized_volatility and repair_drill tools; prune the 54 playbook lessons to the options
ones.

### The legacy `ltcm/` package (50,460 lines; about 7,600 are needed)

Move into `league/` and trim, then delete `ltcm/` entirely: `broker` (drop the crypto, future and
event asset classes), `risk` (drop the event rules, 301-550; its `DeskManifest` is only a type
annotation, so `manifest` goes), `adapters/__init__` (the gateway signer and the Alpaca parts;
drop Kalshi and Coinbase, 61-156, 240-268, 314-334, 403), `adapters/alpaca` (drop the crypto paths,
154-173 and 553-557), `data/__init__` (the market calendar; drop `CompositeMarketData`, 684-795),
`provider` (the Sail Responses client), `events` (two helpers; inline them), `sailbox` (drop the
Kalshi, Coinbase, weather and perp hosts, 56-80), `performance` (Alpaca-only: the funding-flow
reader behind the deposit-netted profit). `data/news` goes unless the researcher keeps a news
tool. Everything else goes, including `sim` once `fees`, `niches` and `tapes` stop importing its
Kalshi fee model.

### Tests (CI under 5 minutes)

- Keep and fix: about 88 `league/tests` files (46,184 lines) and 14 `ltcm/tests` files moved with
  their modules (fakes, broker, risk, events, provider, sailbox, adapters_alpaca,
  adapters_alpaca_structures, adapters_gateway, data_calendar, performance, floor_box). Many kept
  tests are Kalshi-heavy and are rewritten, not deleted (promotion_on_proof has 96 Kalshi
  references, families 76, evaluator 43); tests that import `economy` (allocator, alpaca_truth,
  auditor, capital_follows_proof, families, family_key, house, house_evidence, ladder, merton,
  options, promotion_on_proof, real_structures, structure_practice, tick_cadence,
  tick_never_blocks, tuition, researcher, research_jobs) move to the new budgets.
- Cut: 68 `league/tests` files (economy, pacer, grants, phase1, sail_meter, overnight, live_pilot,
  openai_meter, profit_compute, loop_joints, lab_*, hypotheses, foundry_brief, jev_*,
  research_evidence_gate, research_outcomes, lane_lift, yield_ledger, semantic_lab, routing,
  fast_research, frontier_reserve, model_prices, kalshi_*, shards, paper, exit_slices, horizon,
  listing_window, maker_fees, settlement_grace, event_capacity, receipt_accounting, phantom_repair,
  feeds, feed_recorders, open_feeds*, sports_*, weather_ensemble, tool_sports_game_status,
  consult_recovery, open_desks, mcentee_session_hours, stock_desk_seats, traces, tape_terminal,
  economics, seat_*, verticals) and the other 70 `ltcm/tests` files.
- Fixtures: regenerate `site_checkpoint.json` and `site_events.json`; prune
  `replay_regression.json` to options; cut the Kalshi, sports and weather fixtures.
- New: the Gym's tests (Wave 3) and the swarm's (Wave 4).

### Scripts, gateway, config

- **Scripts:** keep `floor_box.py` (prune `LEAGUE_HOSTS`, line 236), `floor_watch.py` (rewritten for
  the new scoreboard), `gateway_admin.py`, `forward_structures.py`, `replay_structures.py`,
  `data_readiness.py`, `repair_drill.py`, `options_demo.py`, `verify_learning_gates.py`; rewrite
  `place_secrets.sh`, `live_trading.py` and `economics.py`; add the data tools (backfill, universe,
  checks, images, nightly); cut the other 24.
- **Gateway:** cut Kalshi (routes, `kalshi.mjs`, `pem.mjs`, caps, equity parts; secrets
  `KALSHI_KEY_ID`, `KALSHI_PRIVATE_KEY`; `MAX_ORDER_USD_KALSHI`), Jev/TypeSafe (`typesafe.mjs`, the
  route, its gate and worker methods and variables), web_fetch (`fetch.mjs` and its route), crypto
  paths and pairs, the obsolete Coinbase secrets, and stock orders except the sale of assigned
  shares (stock market data stays for underlying bars). Keep Alpaca options, OpenAI (make
  `equity.mjs` Alpaca-only with the new baseline, or drop the profit index), GitHub, notify, health,
  kill and the watchdog. Add flex and the caps by maximum loss. Cut the typesafe and fetch tests;
  rewrite router, caps, equity, signing and github tests. Delete the dead secrets with the owner's
  `wrangler secret delete` (an owner step if the session cannot).
- **Config:** `config.json` loses `jev`, `lab`, `semantic_lab` and gets a fresh `performance`
  (start time and the Brokerage Account's equity at the reset) and the Gym and swarm blocks;
  `game.json` loses `lab`, `lab_bounds`, `hypotheses`, `horizon`, `horizon_bounds`,
  `research.gate`, `research_bounds`, the credit keys under `economy` and their bounds, the
  `min_credits_usd` keys and `merton.lift`; `niches.json` keeps one options desk; the constitution
  loses `budgets.expedition`, every Kalshi, crypto and equity allocator key, the event keys and
  `LEGACY_GRANT_DIGESTS`, and gains the options money table. Delete `campaigns.json`, `turbo.json`,
  `overnight.json`, `repairs.json` (read at accounting.py:188), `research_routes.json`,
  `routing_evidence.json` and the `jev_move_model*.json` files. The market-data client reads
  through the real account's credentials (`alpaca`) instead of `alpaca-paper` (service.py:199,
  265): the kill switch stops orders only.

### Documents and the archive

The documents that stay, and nothing else outside `archive/`:

| File | What it is |
|---|---|
| `README.md` | Under 300 lines: the goal, the game, how to run it, the one number. |
| `docs/design.md` | The game: this plan's design, kept current as the swarm changes. |
| `docs/operations.md` | Pause, deploy, roll back, inspect, recover, the switches; rewritten from the kept parts of today's (48-323). |
| `league/CONTRACT.md` | The options strategy contract, under 20 KB (from 75.6 KB). |
| `CHANGELOG.md` | One entry per deploy from this run on. |

`gateway/README.md` and `deploy/README.md` are rewritten short; `league/README.md`, `league/FEEDS.md`,
`ltcm/README.md`, `deploy/ltcm.service` and `playbooks/` go. `archive/` holds `archive/README.md` (a
one-page history: Portfolio Agent, the first LTCM run of chat desks, the league of Sept 19-25, and
why the project narrowed to options) and `archive/docs/` with today's `docs/` (runs, research,
history, proposals, goals, design, contracts, the old README and operations pages). Code is not
copied into the archive: the tags are the archive of code.

**Local data:** of the main checkout's 20 GB `.data`, `capital-paper-shakedown-20260915` (14 GB) and
`runtime` (4.9 GB) are old runtime copies and move to `~/Work/archive/` or are deleted after the
tags exist; `.data/ltcm/box.json` and what `floor_box.py` needs stay; `sail-docs` and `research`
stay.

## The website

The capital pages at blakewoods.us/capital start over.

- **Words.** The page says "AI agents trading options." The account is the "Brokerage Account". No
  venue is named anywhere a visitor can read: `capital/index.html` 7 (meta description) and 28 (the
  lede), `capital.js` 48-96 (the twelve-desk partner list with "via Kalshi/Alpaca"), 369 (the venue
  label) and 576 ("searching Kalshi for ..."), and the `kalshi.com` link allowlist in `schema.js` 75
  and `publish.py` 57.
- **What it shows.** The Brokerage Account balance, starting from the account's equity at the
  reset; total profit since the reset, net of deposits and withdrawals; the running timer from the
  reset; the one number (profit after compute) beside it; the swarm (each agent's family,
  mechanism in a sentence, band and record); the Gym's pace (programs tested, market-years
  simulated); open structures with their maximum loss and P&L; and the tape of the agents'
  decisions in their own words. **Never quotes, spreads, implied vol surfaces or fitted
  parameters** (the data licenses forbid it).
- **How it resets:**
  1. Stop the old publisher (Wave 0 stops the old House).
  2. `POST /api/capital/reset?confirm=erase-everything` with the publish token (capital.mjs
     344-349 runs `resetAll`, which empties `events`, `floor_history`, `checkpoint` and `desks`),
     and the same under `/t/test` and `/t/canary`.
  3. A new `PERFORMANCE_START_AT` in `capital.js` (line 29) equal to `config.json`
     `performance.start_at`, with `start_equity` the Brokerage Account's equity at that moment;
     the tests that pin them (`test/capital.test.mjs:1627`, `test/league-contract.test.mjs` 48, 96)
     move with them.
  4. The new House starts on a new ledger with no `publish.json`, so its cursor starts at zero and
     `run.started_at` (the first `ops.started`) starts the timer.
  5. `schema.js` is simplified to the options House (agents in place of desks, at most 160; the
     committee, lab, watch and flywheel blocks go), `capital.js` and `index.html` are rebuilt to
     the list above, the site tests are updated, then `npm run build && npx wrangler deploy`.
- **Storage:** Durable Objects only (EXCHANGE, the inert PORTFOLIO_STATE, CAPITAL `capital-v1`);
  no KV, D1 or R2. Reads are edge-cached for 3-5 seconds; the gateway watchdog sees a 404 until the
  first checkpoint and restarts nothing.

## The owner's $10,000

| Where | Amount | Why |
|---|---|---|
| Brokerage Account deposit | $6,000 | Capital is what compounds and what lowers the bar (costs divided by equity). It lifts equity over $2,000 (full margin buying power, credit structures) and, at 3% of equity per probe, funds about 20 concurrent probes of about $195 maximum loss each. |
| Sail credits | $1,200 | The training burst (at most $350), then 2-3 months at $8-12 a day. |
| OpenAI credits | $800 | At most $150 for the burst in what is left of September, then about $215 a month for October to December. |
| ThetaData: switch the subscription to annual billing | $768 | $64 a month instead of $80, saving $192 a year. |
| Reserve | $1,232 | Released only by evidence: more capital when a Sized family's capacity binds, more Sail when the Gym queue is the bottleneck. |
| **Total** | **$10,000** | The market-data subscription is already paid. |

If the figure is $3,000 rather than $10,000: Brokerage Account $1,700 (equity to about $2,180, over
the $2,000 margin line), Sail $600, OpenAI $400, ThetaData $240 (three months), reserve $60.

**The owner's steps, before the run starts** (the run never waits on them; it sizes by what is
funded and says what is missing):

1. Deposit to the Brokerage Account (an ACH deposit takes 1-3 business days; an instant deposit, if
   offered, makes Monday's open).
2. Top up Sail credits.
3. Add OpenAI credits, check the organization's usage tier covers the month (Tier 3 caps at
   $1,000), and set a project hard limit equal to the gateway's month cap as a second fence.
4. Switch ThetaData to annual billing when convenient.
5. When the Kalshi positions settle, withdraw that cash; moving it to the Brokerage Account is
   optional and counts as a deposit.
6. Leave the laptop on its charger (the agent-host service keeps it awake on AC power): the run's
   session lives there all weekend, even though the heavy work runs on Sail.
7. State the funded figures in the /goal message.

## The order of work

The owner's schedule is the plan's clock: rework tonight, train Saturday and Sunday, trade Monday's
open (13:30Z Sept 28). Each milestone has a Done line. **A milestone that slips does not skip its
Done line**: real money goes live only on a verified path, and whatever is not ready by Monday's
open goes live at the first verified moment after it.

| Milestone | Target | Done when |
|---|---|---|
| M0 Safe and archived | T0 + 1 hour | the old House stopped and archived; tags pushed; leftovers closed |
| M1 Data flowing | T0 + 2 hours | the data box downloading; the universe chosen |
| M2 Pruned | Saturday morning | the overhaul merged to main, CI green in under 5 minutes |
| M3 The swarm is training | Saturday by 16:00Z | fresh House live on new state; Gym boxes running programs; 48 researchers in the inner loop; the site reset |
| M4 Gated | Sunday by 22:00Z | holdout looks made; the Candidate list and the Probe list written |
| M5 Monday's open | Monday 13:30Z | Candidates in live shadow; Probes on real money; the paper account measuring execution |
| M6 The first session judged | Monday after 20:00Z | the post-mortem, the scoreboard and the report |

### Wave 0: safe and archived (the main session, first hour)

1. `date -u` is T0. Write it into the run record `docs/runs/<T0 date>-options-swarm.md` on the
   branch `run/options-swarm-<date>` and commit. A context reset reads the record first and never
   restarts the clock.
2. Read the state: `floor_box.py status`, `health.json`, the Brokerage Account through the gateway,
   Sail's balance, the gateway's OpenAI month, ThetaData's key (`~/.config/thetadata/env` exists).
   Send one push notification with anything the owner must do.
3. **Archive git:** tag `archive/pre-options-2026-09-26` at `origin/main`; for every unmerged local
   or remote branch, push it, tag its head `archive/branch/<name>` and push the tags. Close the 14
   open PRs with a comment naming the tag. Nothing unpushed is ever deleted.
4. **Stop the old House:** `python3 scripts/floor_box.py stop --reason "options overhaul"` (this
   also stops the in-box updater, which would otherwise ship half-pruned main heads). Confirm the
   loop, the supervisor and the watchdog are down and the stop latch is set.
5. **Archive the old state:** a Sail checkpoint of the House box with a one-year TTL; a compressed
   tarball of `/workspace/state` (ledger, books, research traces, lab store, options history) kept
   on the box under `/workspace/archive/` and downloaded to `~/Work/archive/`. Then the box's
   `/workspace/state` is moved aside so the new House starts on an empty root.
6. **Close the leftovers** on the Brokerage Account through the gateway: cancel the resting SOL
   sell, sell the XRP, SOL and crypto dust at the touch. Verify the account holds only cash and no
   open order. Kalshi is left to settle at the venue.
7. **Retire old boxes:** terminate the agent sandboxes and the Alpha Lab box (after step 5's
   checkpoint); keep the House box. List boxes afterwards and record the count.
8. **Tidy the laptop:** remove every worktree except `~/Work/ltcm-deploy` and this run's (each
   branch pushed and tagged first); move `~/Work/ltcm-watch-*`, `~/Work/ltcm-observation-*`,
   `~/Work/ltcm_observe.py`, `~/Work/ltcm_snapshot.py`, `~/Work/ltcm-review-2026-09-16.md` and the
   main checkout's `.data` (except what `scripts/floor_box.py` needs, e.g. `.data/ltcm/box.json`)
   into `~/Work/archive/`. The untracked `docs/goals/LTCM_OVERNIGHT_GOAL.md` in the main checkout
   goes to the archive. The main checkout ends on the new main.

### Wave 1: data (starts at T0 + 20 minutes; runs all weekend)

1. **The data box:** a size-l Sailbox (32 GiB RAM, 512 GiB disk) with egress to
   `nexus-api.thetadata.us`, `mdds-01.thetadata.us` and PyPI (PyPI removed after setup); Python
   3.12+, the `thetadata` library, polars, pyarrow. Copy the ThetaData key from the laptop into the
   box's own 0600 env file (authorized) and nowhere else. Probe authentication and one request
   before the backfill.
2. **The universe:** from ThetaData EOD over the last 60 trading days, rank optionable underlyings
   by option volume and by the quoted spread of near-the-money 0-7 DTE contracts; take the core five
   plus the best 20. Record the list and the numbers.
3. **The backfill, in this order** (one-minute NBBO, strikes within about 25 of the money, 0-14
   DTE; four concurrent requests; per-day Parquet; resumable from a manifest; checksummed):
   1. SPY, QQQ, SPXW, XSP, IWM over Train's 2023-2024;
   2. the same over Validation (2025);
   3. the same over 2022;
   4. the 20 single names over Train and Validation;
   5. the holdout (2026) into the separate gate store only;
   6. `trade_quote` calibration samples: one day in five, 0-7 DTE, 10 strikes around the money,
      core five;
   7. back months to 45 DTE for calendars and diagonals on SPY and QQQ.
4. **Underlyings:** Alpaca SIP one-minute bars for the ETFs and stocks (through the gateway); for
   XSP and SPXW, the `underlying_price` column of `option_history_greeks_first_order` at one
   minute (a narrow strike range is enough), since the subscription has no index endpoint.
5. **Checks before the Gym trusts it:** row counts per day and contract; no crossed or negative
   quotes kept; the recorded Alpaca OPRA quotes of Sept 22-24 (316,141 rows in
   `~/Work/.options-history/options_history.sqlite`) agree with ThetaData's minute NBBO within a
   tick on the same contracts and minutes; the data's first days match the expiry calendar.
6. **Images:** the golden Gym image (Train and Validation, no key, no holdout) and the gate image
   (plus the holdout), each checkpointed twice with a one-year TTL, and a script that rebuilds them.
7. **The nightly forward job:** each trading night after 01:45 ET the data box wakes (Sail's
   scheduled wake), pulls the previous day, appends it to the forward store, refreshes the Gym
   boxes, and the House runs the nightly forward replays.

### Wave 2: the prune (a builder in its own worktree, from T0 + 30 minutes)

On branch `overhaul/options`, first move the live grant out of the campaign store into
`league/live_trading.py` with its semantics unchanged (trap 1 under "The prune"), then cut in this
order, running the kept tests after each cut and committing each cut on its own (the precise map is
under "The prune" below): Kalshi; stocks and crypto; Jev; the Alpha Lab, foundry, semantic lab, founding, Firm Mind; the
credit economy and six of Merton's roles; the legacy `ltcm/` package (the modules the kept code
needs move into `league/`); the gateway's dead routes and variables; the docs (to `archive/`).
Done: CI green in under 5 minutes, `python3 -m league.ci` passes, the repo's line count and file
count recorded before and after.

### Wave 3: the Gym (a builder, from T0 + 30 minutes, in new modules so the prune cannot collide)

`league/gym/` (the engine, the fill model, the store reader, the batch runner and the sealed-box
driver), with tests: a hand-computed vertical, condor and calendar P&L reproduced to the cent; a
program that tries to read the future gets nothing; expiry cutoffs, liquidation and settlement;
fees; determinism (same inputs, same hash); a benchmark meeting the speed targets on the data box's
first days. Then the fill model's calibration from the `trade_quote` samples, with its fit written
to a gitignored store, never into committed code.

### Wave 4: the swarm (a builder, on top of Wave 2's branch once the Gym's run API is fixed)

The researcher loop (tools: `gym_run`, diagnostics, the notebook, the graveyard, the contract), the
tournament and bandit, forks and retirements, the architect, the program reviewer and the gate's
auditor on the gateway, the holdout ration, the seeds re-expressed, the ledger rows for each step,
and the population rules. Done: 48 researchers each completing an inner-loop cycle in under 3
minutes, and the first tournament written.

### Wave 5: the live path (a builder on top of Wave 2's branch; money code, so an adversarial three-lens review follows)

The House's live tick for options only: chain reads and the shadow book on live OPRA quotes, the
paper account's multi-leg route, the real route; netting, the order-rate governor, the expiry-day
rules, buying-power reservation, assignment polling; the bands and sizing of "Money" (the allocator
rewritten for options); the new constitution money table and digest; the new grant; the gateway
(caps by maximum loss, `OPTION_STRUCTURES_REAL` on, flex for OpenAI, the dead routes gone). Tests
against recorded venue responses. Done: the review's confirmed findings fixed, CI green, the
gateway deployed.

### Wave 6: the site (a builder in `~/Work/personal-site`)

The reset under "The website" below. Done: deployed, and the page shows the new House's first
checkpoint.

### Wave 7: deploy and start training (the main session, Saturday)

The fresh House on an empty state root: owner deploy with the canary; the gateway first when it
changes; the grant ratified if real money is on; the site; then open for business in the Gym.
Verify on the box: the Gym boxes running batches, researchers cycling, the tournament, the ledger
and the site's checkpoint.

### Wave 8: the weekend

Watch every two hours (the scoreboard below); fix every defect with a test; raise throughput;
widen the universe and the backfill as the data lands; run the gates as families reach the line.
Sunday evening: the Candidate list, the Probe list with sizes from the account's equity at that
moment, and the Monday pre-open checklist written into the record.

### Wave 9: Monday

- **Pre-open (12:00-13:25Z):** the Brokerage Account's equity (with any deposit that has landed),
  the gateway caps set from it, the grant active on the running digest, the House healthy, the
  expiry calendar for the day, the Probe list final. No deploy from 13:25Z to 20:05Z except a
  rollback.
- **The session:** Candidates in live shadow; Probes real from their first signal; a 1-lot paper
  structure early in the session proves the multi-leg route before the first real one; the first
  real order comes from an agent's intent, never from a test. Watch every 30 minutes: fills against
  the Gym's expectation, slippage, refusals, the order count against 250, buying power, the daily
  and drawdown stops.
- **After the close:** the post-mortem, the fill model recalibrated, the scoreboard, the report.

## The scoreboard

Read at T0, every four hours, at each milestone and at the end, and written into the run record.

| # | Metric | Target |
|---|---|---|
| 1 | Net since the reset: options P&L after fees minus all input costs, and each part | positive, then growing |
| 2 | Data: underlying-days in the store by window; the backfill queue | core five Train by Saturday 12:00Z; all windows by Sunday |
| 3 | Gym throughput: program-years an hour; inner-loop latency | 2,000 an hour by Saturday evening; under 3 minutes |
| 4 | The search: families alive and retired, programs evaluated (trials), revisions an agent-hour | 48-96 alive; tens of thousands of trials by Monday |
| 5 | Evidence: families over the validation line, holdout looks and passes, the leakage alarm | passes honest; alarm silent |
| 6 | Forward: Candidates' nightly and shadow records; real P&L by family | positive where money is |
| 7 | Execution: real and paper fills against the fill model; slippage; orders a day | within the model's band; under 250 |
| 8 | Compute: Sail, OpenAI and ThetaData spend a day, against the budgets | inside the budgets |
| 9 | Harness: House restarts, CI time, repo lines and files, docs count | CI under 5 min; 5 core docs |

## Authority

**Authorized:**
- Implement, test, commit, push, open and merge PRs to `main` in this repository and in
  `personal-site`, with CI green. Builders in their own worktrees (at most four at a time; one test
  process at a time on the laptop); the main session merges.
- Everything in Wave 0: tags, pushes, closing the 14 open PRs, removing worktrees and local
  branches once pushed and tagged, archiving local data, stopping and archiving the old House,
  terminating the old agent sandboxes and the Alpha Lab box, and starting the new House on an empty
  state root.
- Closing the Brokerage Account's leftover crypto positions and resting orders through the gateway.
- Creating and operating Sail boxes for the data box, the Gym and the gate (inside the budgets),
  and copying the ThetaData key from `~/.config/thetadata/env` into the data box's env file only.
- Rewriting the constitution's money rules for options inside the table under "Money", creating and
  ratifying `options-swarm-20260928`, revoking `earned-live-20260921`, and re-ratifying within a
  minute of each promotion that moves the digest.
- Deploys: owner deploys (`scripts/floor_box.py deploy` from `~/Work/ltcm-deploy`), gateway deploys
  (`npx wrangler deploy` in `gateway/`), including the caps, `OPTION_STRUCTURES_REAL` and the
  OpenAI month cap up to funded money, and site deploys (`npm run build && npx wrangler deploy` in
  `~/Work/personal-site`), including wiping the site's stored history. None from 13:25Z to 20:05Z
  on a trading day, except a rollback.
- Trading real options on the Brokerage Account inside the money table; losses accepted.
- Spending funded compute inside the budgets.
- Stopping in an emergency (`scripts/gateway_admin.py kill`, `league.watchdog rollback`, `npx
  wrangler rollback`), then telling the owner at once.

**Not authorized:**
- Deposits, withdrawals and transfers; any venue account setting; credentials other than placing
  the ThetaData key on the data box; `wrangler secret put`.
- Raising any cap above funded money; disabling the kill switch, the gateway's caps or the daily
  and drawdown stops (the run may release a kill it engaged once the cause is fixed and verified).
- Naked short options, stock positions other than an assignment's, crypto, Kalshi.
- An order no agent's intent produced, except closing the leftovers in Wave 0 and the one 1-lot
  paper structure that proves the multi-leg route on Monday.
- Forcing trades; fabricating, back-filling or hand-editing evidence, the ledger or the books;
  giving any Gym box the holdout; loosening an evidence line.
- Publishing ThetaData or Alpaca quotes, spreads or anything fitted from them on the site, in the
  public JSON or in committed code (the GitHub repository is public).
- Deleting unmerged or unpushed work.

## Lessons from the last ten days (read before starting)

- **A merged PR is not a deployed feature.** Verify on the box, in the change's window.
- **The in-box updater ships main's heads** that pass CI and touch no protected file; that is why
  the old House stops at T0 and the new House's `auto_update` stays off until the overhaul settles.
- **Ratify at promotion, not later**; a late ratification once stopped the floor.
- **`date -u` before every time written**; take event times from the box.
- **The laptop has 8 cores and 7 GiB**: one test process at a time, only the modules a change
  touches, CI as the source of truth; tests on the /tmp tmpfs run about 25x faster but it is 3.8 GB.
- **Never chain a deploy on grep's exit code**; commit each merge before the next; `rerere` off for
  overlapping merges; never remove a builder's worktree before its report.
- **`~/Work/ltcm-deploy/.data` is a symlink** into the main checkout; never `ln -sfn` over it.
- **The account usage limit can stop every agent for hours** (Sept 25, 07:30-10:30Z): keep the
  run record current so a resumed session loses nothing.
- **Practice fills flatter:** the old shadow book filled resting quotes only when a trade printed
  through them, and practice makers lost $185 on 240 fills where real ones lost $1.40. Calibrate on
  real fills as soon as there are any.
- **Sail's checkpoint API has gone down for a day**; keep two images and the rebuild script, and
  never let a vendor outage roll back a release.
- **Running out of Sail credits pauses every box**, the House included.

## Done

The run is done when all of these hold, or the record says with numbers why one cannot:

1. The repository is pruned to the options swarm: the layout under "The prune", five core docs,
   `archive/` with its README, CI under 5 minutes, no dead config.
2. The old House is archived and stopped; the new House runs on fresh state; the site is reset and
   shows the new run.
3. The data store holds the universe's Train and Validation windows, the gate holds the holdout,
   and the nightly forward job has run at least once.
4. The Gym meets its speed targets and passes its correctness tests; the fill model is calibrated
   from `trade_quote` and, from Monday, from real and paper fills.
5. The swarm trained through the weekend: the trial count, families, validation passes, holdout
   looks and passes are on the scoreboard.
6. Monday's session ran with Candidates in live shadow and every Probe that passed the gate on real
   money (or the record says why none did), inside the money table.
7. The report is written, the memory updated, and the swarm left running 24/7 on its own.

## The report at the end

In the run record's last section: the scoreboard at T0, at each milestone and at the end; Net and
its parts; what the swarm learned (the families that passed and failed, and why); Monday's session
trade by trade on real money; the fill model against reality; compute spent against the budgets;
the repo before and after; defects found and fixed; what is next; and the owner's decisions, each
with a recommendation.

## The /goal message

The owner starts the run by pasting this, with the funding lines made true:

```
/goal Execute docs/goals/LTCM_OPTIONS_SWARM.md (branch goal/options-swarm-2026-09-26; merge it to main first) autonomously, with no deadline, until its Done list holds.

- Direction: one goal only, a swarm of AI agents trading level-3 options on my Brokerage Account profitably, with options returns greater than every input cost. Prune everything else. Design for agent time, not human time: train 24/7 in the Gym on real recorded quotes and let the live market judge. Be bold: the money in the account can all be lost. Keep the evidence honest.
- Schedule: rework tonight; train Saturday and Sunday; trade Monday's open (13:30Z Sept 28). A slipped milestone never skips its Done line.
- Funding as of now: Brokerage Account deposit $<amount> (<landed / pending until DATE>); Sail $<balance> after my top-up; OpenAI $<credits>, gateway month cap may go to $<cap> for September and $<cap> for October; ThetaData Options Standard (key at ~/.config/thetadata/env). Stay inside the plan's budgets and never above funded money.
- Authority: everything in the plan's Authorized list, including stopping and archiving the old House, closing the account's crypto leftovers, retiring old Sail boxes, placing the ThetaData key on the data box, the new grant options-swarm-20260928 and re-ratifying it inside the Money table, owner, gateway and site deploys (none 13:25-20:05Z on a trading day except a rollback), wiping the site's history, and real options trading inside the Money table. Nothing in the Not-authorized list.
- Method: T0 and the run record first; the scoreboard at T0, every four hours and at each milestone; at most four builders in worktrees; an adversarial review of all money code; one test process at a time on the laptop; verify every change on the box; fix every defect with a test; report at the end with my decisions.
```

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
| OpenAI after the training burst | $150-215 |
| **Total** | **about $565-740** |

On a $6,500 account that is 9-11% a month before Net turns positive, so capital is part of the
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
  - history depth: whole days from 2019, 2022 and 2023 came back for SPY and XSP, including the bulk
    form (`expiration='*'` with `max_dte`), so the Train window below is served;
  - the first spread readings were well under the old replay's assumed 4% of premium (the figures
    stay out of this public file: the data license forbids publishing them).
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
  structure with one multi-leg order: legging out is a last resort, because selling a long leg
  first would leave a naked short (refused) and buying a short leg back alone can be refused for
  buying power. **Only five types close in one order** (debit and credit verticals, iron condors,
  iron butterflies, long butterflies; the Sept 25 run found Alpaca refuses one-order closes of
  calendars and straddles). Each leg shows as its own position, and positions net per contract
  across the whole account: one agent's sale can close another agent's leg.
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
  paper included. Many agents on one account collide unless the House nets them, and whether the
  390 count takes a multi-leg order as one order or one per leg is unverified.
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
  first-order greeks, verified on an XSP 0DTE day. Live, Alpaca has no index spot feed either, so
  the SPX level for XSP/SPXW is derived from put-call parity on the at-the-money options, the same
  way in the Gym and live (ThetaData's `underlying_price` is the check). Four
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
  times real time. Four to eight 8-vCPU Gym boxes are 32-64 cores; running a weekend, that is several
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
  chosen from ThetaData's EOD data for 2024 (never from holdout days) in Wave 1. "Anything available" holds: any optionable
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
  written as Parquet partitioned by underlying and day. Underlying one-minute bars for the ETFs and
  stocks come from Alpaca's SIP history, fetched by the House through the gateway and handed to the
  data box; the SPX level for XSP/SPXW comes from put-call parity (ThetaData's `underlying_price` is
  the check). Also daily open interest and `trade_quote` samples for fill calibration. Exchange and
  condition columns are dropped except where calibration needs them.
- **Three places, three contents.**
  - **The data box** (size l, 32 GiB RAM, 256 GiB disk; egress only to `nexus-api.thetadata.us`,
    `mdds-01.thetadata.us`, and PyPI while it is set up) downloads and writes the store. It holds the
    ThetaData key in its own 0600 env file and nothing else: no venue key, no gateway token, no agent
    code. It sleeps when idle (never paused: a paused box cannot wake on a schedule) and wakes by
    Sail's scheduled wake for the nightly job.
  - **The Gym image** is a fork of the data box with the key, the holdout days and the forward days
    deleted, sealed with `no_network` and checkpointed twice with a one-year TTL, plus a script that
    rebuilds it (Sail's checkpoint API has failed for a day before). Gym boxes are forks of it.
  - **The gate image** is a second fork without the key but with the holdout and forward days,
    sealed, used only by the House's gate and the nightly forward replays of Candidates.
- **Gym boxes.** Size-l boxes forked from the Gym image, `no_network`. Programs go in and results
  come out through Sail's exec and files APIs. Four to start; up to eight while the queue is long
  and the budget allows; asleep when it is short.
- **The engine.** A new, vectorized replay (numpy/polars/pyarrow over memory-mapped Arrow): load a
  day's chain once, then run a batch of programs over it ("day-major batching"), so the data cost is
  paid once per day, not once per program. Each program sees the chain only through its `ctx`, one
  decision step at a time, with nothing from the future; the engine owns the clock.
- **Honest fills.** A structure fills against each leg's recorded NBBO on the minute AFTER the
  decision: at the natural price (paying every leg's half-spread) by default; at a better price only
  with the probability the fill model gives for that distance from the mid, the structure type,
  DTE, moneyness and time of day. The model's random draws are keyed by (contract, minute), never by
  the program, so a trivial edit cannot re-roll luck. It starts conservative and is calibrated on
  Train days only from `trade_quote` (multi-leg prints identified by their condition codes), then
  from real fills. Paper fills prove the order route, never the calibration (paper fills are
  synthetic). Size is capped by the quoted size. Fees per the venue table. A stress run at 1.5x the
  half-spread must stay positive for a family to pass the gate.
- **Venue rules in the engine, the same as the House's:** no new opening order on an expiring
  contract after 15:00 ET; closing orders until 15:10 ET (15:25 for SPY and QQQ); Alpaca's
  liquidation of what remains from 15:30 ET; auto-exercise and physical settlement for equity
  options (an assigned short leg becomes shares at the close, with the risk that brings); cash
  settlement for XSP/SPXW; the buying-power check (maximum loss plus fees plus 10%); 09:30-16:00
  only; the price ticks.
- **What a run returns:** every trade (entry, exit, legs, fills, fees, maximum loss, P&L), the daily
  P&L series, P&L per dollar of maximum loss, win rate, profit factor, Sharpe on daily P&L,
  drawdown, turnover, fill statistics, P&L by weekday, time of day, DTE and regime (realized and
  implied vol terciles) and by period within the window, and the worst trades with their context.
  Results are hashed and written to the ledger; runs are deterministic and reproducible from
  (program sha, data version, engine version, window).
- **Speed targets.** A program over one year of one underlying in 60 s or less on one core; at
  least 2,000 program-years an hour across the Gym by Saturday evening; a researcher's inner-loop
  answer (one program, train window) in under 3 minutes.

### The agent

- **An agent is one family:** a mechanism (why the trade should make money), a structure type and a
  universe slice, owned by a researcher model with a notebook (its memory), a lineage of program
  versions, and a record. Two agents never share a family; forks start new families.
- **The program** is one Python file with `NEEDS`, `PARAMS` and `decide(ctx)`, run at a decision
  cadence the program declares (1 to 30 minutes). `ctx` gives the time of day, the weekday, days
  to each expiry and event flags (FOMC, CPI and jobs days, the underlying's earnings, monthly
  expiry, index rebalances) but **never the calendar date or year** (the models know what happened
  in 2026; the holdout must not be recognizable, and the safety check rejects date literals); the
  underlying's recent bars; the chain slice the program's `NEEDS` asked for as numpy arrays
  (strikes, expiries, bid, ask, sizes, mid, implied vol and greeks computed by the engine, open
  interest); the program's positions and cash, its risk budget and the venue rules. `decide` returns structure
  intents (type, legs chosen by expiry, strike, delta or distance rules, quantity or a max-loss
  budget, a limit rule of natural, mid or mid plus k ticks, and a time in force) and exits. numpy
  and math are importable; nothing else outside the whitelist; no I/O.
- **The strategy contract** (`league/CONTRACT.md`) is rewritten for options only and kept under
  20 KB, because every researcher call pays for it; the rest moves to reference pages the
  researcher reads on demand.
- **Programs live in the House's state, not in git** (the repository is public, and a program's
  parameters are fitted to licensed data). The engineer's pull requests change House code only.
- **Seeds.** The 12 structure founders from Deploy G (condor-vrp, putspread-dip, ironfly-quiet,
  strangle-cheap, calendar-term, butterfly-pin, orb, trend-vertical, reversal, skew, diagonal,
  gap-drift) re-expressed in the new contract, plus the architect's first library of mechanisms
  that the literature and the data suggest: the variance risk premium in short-dated index options,
  intraday momentum and trend days, opening-range breaks and fades, gap reversion, end-of-day drift,
  0DTE pinning near large open interest, term-structure and skew mean reversion, post-event
  volatility crush on single names, weekly-expiry dynamics.
- **Population.** 48 researcher agents at the start of the training burst, a ceiling of 96 and a
  floor of 16; after Monday, about 16 while Net is not positive (the Sail budget allows about that
  many at $12 a day). Families
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
| Nightly forward | after 01:45 ET each trading night | the data box, the gate box | ThetaData's new day goes to the gate image only; every Candidate is re-run on it | one truly unseen day per night for every Candidate |
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

- **Every Gym evaluation is a trial**, counted per lineage (forks inherit their parent's count and
  holdout looks) and in total on the ledger.
- **The validation line** (a family's best program): at least 100 trades on at least 60 distinct
  trading days in Validation; mean P&L per dollar of maximum loss above zero after fees with a
  one-sided t of at least 2; a deflated Sharpe probability of at least 0.95 given the lineage's
  trial count (`league/stats.py` has it); positive in at least 3 of Validation's 4 quarters;
  positive at 1.5x the half-spread.
- **The holdout line**, one look per program version and at most three per lineage: P&L after fees
  positive; a day-block bootstrap one-sided 95% lower bound on mean daily P&L above zero, with a
  Holm-Bonferroni correction across every holdout look the swarm has made; holdout Sharpe at least
  half of validation Sharpe. **The gate tells researchers only pass or fail**, never the holdout's
  numbers.
- **Forward days never reach a Gym box**, and nightly forward replays run on Candidates only; they
  move bands, never select among Gym programs.
- **The forward record** (nightly replays plus live shadow plus real) is what sizes money. A
  Candidate whose forward record turns negative over 20 trades loses its band. Families whose code
  was written with knowledge of 2024-2026 (the Deploy G seeds among them) need a forward record
  before they are Sized.
- **Leakage alarm:** once there are at least 10 holdout looks, if more than 30% pass, stop the gate
  and look for leakage before anything else.
- The lines may be tightened on evidence; loosening one is the owner's decision.

### Money

**Bands:** Gym, Candidate (shadow only), Probe (real, small), Sized (real, by evidence), Retired.

| Rule | Default | Allowed range this run |
|---|---|---|
| Probe: a Candidate that passed the holdout, trades one of the five one-order-closeable types, and whose typical maximum loss fits the cap at the current equity (else it stays shadow-only) | real from its next session | - |
| Credit structures on real money | only once the account reads $2,000 of equity or more (or a real credit order is accepted); debit types until then | - |
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
- **The order path:** the House nets every agent's intents into one order stream per contract;
  never sends opposing orders on one contract; rejects or queues any intent that would take the
  opposite side of a contract another agent holds (positions net across the account); reserves
  maximum loss plus fees plus 10% of buying power before sending; keeps under 250 orders a day,
  counting cancels and each leg of a multi-leg order until the venue's counting is verified, and
  under 150 API requests a minute; sends no new opening order on an expiring contract after 15:00
  ET (index 0DTE included until the venue's index cutoff is verified on a live session); closes
  expiring equity-option structures with a short leg in or near the money by 15:10 ET (15:25 for
  SPY and QQQ) with one multi-leg order; and polls account activities for assignments. Real money
  trades only the five one-order-closeable types until a paper round trip proves another type.
- **The gateway's caps follow the account:** per order, maximum loss at most the lower of $1,000
  and 15% of equity; opening maximum loss a day at most 100% of equity; 300 orders a day; the kill
  switch unchanged. Real structures turn on (`OPTION_STRUCTURES_REAL` and constitution O1) for the
  types the venue accepts.
- **The grant.** A new grant, `options-swarm-20260928`, covers the Brokerage Account only, built
  fresh (not migrated) in `league/live_trading.py` so it works on an empty state root. Its capital
  is the lower of the account's equity and the owner's stated ceiling at each ratification, and it
  is re-ratified when a deposit lands (the old grant's "deposits do not enlarge it" rule is
  dropped); it is pinned to the new money digest. The old grant `earned-live-20260921` is disabled
  in Wave 0. Changes inside this table re-ratify within a minute of the promotion that carries
  them. The daily stop and the drawdown peak net out deposits and withdrawals.
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
| Data | Sail box + ThetaData | 1 l box, asleep when idle | $5-15 a day while running (the disk is most of it) |
| The House | Sail box | the existing s box | about $0.03 an hour |
| History, nightly forward day, fill calibration | ThetaData Standard | 4 concurrent requests | $80 a month |
| Live quotes, SIP bars, paper and real orders | Alpaca | via the gateway | already paid |

- **Dropped:** Jev (the House's sensors, the move sensor, the gateway lane), GPT-6 Luna research,
  Sail web search, the Alpha Lab, the hypothesis foundry, the semantic lab, Merton's six roles
  other than the architect and the engineer, every Kalshi, crypto and stock feed and recorder.
- **Budgets.** The training burst (T0 to Monday's open): Sail at most $350, OpenAI at most $150.
  After Monday: Sail at most $12 a day and OpenAI at most $215 a month until Net is positive over
  30 days; after that, compute may grow to half of the trailing 30-day gross options profit. When
  the forward record is flat, compute drops to the floor (the nightly forward replay, live shadow,
  one architect pass a day).
- **The Sail guard.** Running out of Sail credits pauses every box, the House included. Gym boxes
  and researchers scale down whenever the balance falls below two days of the House's burn plus
  $30, and stop before the House does.
- **The gateway gains OpenAI flex** (a `flex` rate per model; the House asks for flex on every
  non-urgent call; a 429 settles at $0) and a per-role output ceiling above 16,000 for the
  post-mortem.

## The prune

The repository ends as one thing: the House, the Gym and the swarm for options, with the gateway,
the deploy tools and five documents. Everything else leaves `main`. Git keeps it (the archive tags
of Wave 0), and `archive/` keeps the documents that explain how the project got here. The map below
comes from a read-only survey of release `a1f9a8e7` on Sept 26; `file:line` references are to that
release.

### Five traps first

1. **The real-money grant lives in the campaign store.** `league/campaigns.py` and
   `campaigns.sqlite` hold it, and the House, the allocator and `capital.py` ask
   `campaigns.allows_live` / `live_authorization` before any real order (house.py 2630, 3337, 3655,
   4944-4953, 5212-5222, 5593, 5647, 5665, 8731-8735; allocator 1354, 1470, 2758, 2927; capital
   117). The new grant is **re-created, not migrated**, in `league/live_trading.py` for the
   Brokerage Account alone (today's `policy()` demands both Alpaca and Kalshi, keeps "same
   capital" on ratify, and `main()` refuses to run without a campaign database), and every one of
   those call sites moves to it BEFORE campaigns is cut, or real money silently turns off.
2. **Removing the Kalshi and crypto keys from the constitution moves the money digest**, which
   revokes any grant until it is ratified, and `PINNED_DIGEST` (constitution.py:718) moves with it.
3. **The in-box updater must stay off and cannot carry this prune.** `league/config.json:22` sets
   `"auto_update": true` and `service.py:403` treats a missing key as true: the first commit of the
   prune sets it false and makes the default false. CI's forbidden paths (ci.py:47-52), the
   workflow pin (updater.py:116, `REQUIRED_CHECKS` and `TRUSTED_WORKFLOWS_SHA256`) and the release
   trees (updater.py:98, which also names `playbooks/`) all change, so the prune ships as owner
   deploys, and the updater stays off until the overhaul has run a day. Merton's workflow
   (`.github/workflows/merton.yml`) stops auto-merging.
4. **The operator's tools import the legacy package.** `scripts/floor_box.py:75-76` imports
   `ltcm.broker` and `ltcm.sailbox`; `scripts/gateway_admin.py` reads `ltcm/config.json` (62) and
   `.data/ltcm/keys/gateway-admin.token` (19). Repoint them in the first cut and run `floor_box.py
   status` and `gateway_admin.py status` from the pruned tree before it merges: without them there
   is no deploy, no rollback and no way to release a kill.
5. **CI runs both suites by path.** `.github/workflows/checks.yml` runs `discover -s ltcm/tests`
   (53) and `league/tests` (55); it changes with the prune, and the updater's pins with it.

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

**Seeds, strategies, tools, playbook:** keep the 14 `options_*` seeds (re-expressed in the new
contract) and move the 9 option-family strategies (krasker_* and options_breakout_occ_exits) into
the House's state as programs (programs no longer live in git); cut the other 13 seeds and 74
strategies;
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

**Local data:** `~/Work/ltcm-deploy/.data` is a symlink to the main checkout's `.data`, so only its
children move. `capital-paper-shakedown-20260915` (14 GB) and `runtime` (4.9 GB) are old runtime
copies and move to `~/Work/archive/`; `.data/ltcm/` stays whole (`box.json`, `keys/` with the
gateway admin token), as do `.env`, `sail-docs` and `research`.

**Branches:** branches already on GitHub are tagged `archive/branch/<name>` and deleted; branches
that exist only on the laptop are saved as `git bundle` files in `~/Work/archive/branches/` and
never pushed (the repository is public and nobody has read what they hold).

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
  parameters** (the data licenses forbid it): the publisher strips every quote field, and a test
  proves it.
- **How it resets** (before the new House starts, so its first checkpoint lands on a clean site):
  1. Stop the old publisher (Wave 0 stops the old House).
  2. `POST /api/capital/reset?confirm=erase-everything` with the publish token (capital.mjs
     344-349 runs `resetAll`, which empties `events`, `floor_history`, `checkpoint` and `desks`),
     and the same under `/t/test` and `/t/canary`.
  3. A new `PERFORMANCE_START_AT` in `capital.js` (line 29) equal to `config.json`
     `performance.start_at`, with `start_equity` the Brokerage Account's equity at that moment,
     read after Wave 0 has closed the leftovers;
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
| M0 Safe and archived | T0 + 1 hour | the old House stopped, its grant disabled and its state archived; tags and bundles made; the account holds only cash (and sub-minimum dust); the OpenAI month raised |
| M1 Data flowing | T0 + 2 hours | the data box downloading; the universe chosen |
| M2 The House is options-only | Saturday morning | Wave 2a merged: updater off, tools repointed, the grant re-created, the House wired for options only, CI green |
| M3 The swarm is training | Saturday by 16:00Z | the site reset; the fresh House live on new state; Gym boxes running programs; 48 researchers in the inner loop |
| M4 Gated | Sunday by 22:00Z | holdout looks made; the Candidate list and, from it, the Probe list (with the shadow-only Candidates named and why) |
| M4b The live path deployed | Sunday by 22:00Z | Wave 5 reviewed and deployed; the gateway's caps and `OPTION_STRUCTURES_REAL` set; the grant ratified on the running digest |
| M5 Monday's open | Monday 13:30Z | Candidates in live shadow; Probes on real money; the paper account proving the multi-leg route |
| M6 The first session judged | Monday after 20:00Z | the post-mortem, the scoreboard and the report |
| M7 The prune finished | after Monday's close | Wave 2b merged: the legacy package folded in, dead modules and tests gone, CI under 5 minutes, the five documents |

**Builders:** at most four at once, each in its own worktree from one brief. Tonight: data (Wave
1), the House's options wiring (2a), the Gym (3) and the site (6). Once 2a merges: the swarm (4)
and the live path (5) take 2a's and the site's places. The full prune (2b) takes the first free
place after that and merges after Monday's close (its documents may merge sooner: `docs/` and
`archive/` are not in a release). One owner per file per wave; `house.py` belongs to 2a, then 5.

### Wave 0: safe and archived (the main session, first hour)

1. `date -u` is T0. Write it into the run record `docs/runs/<T0 date>-options-swarm.md` on the
   branch `run/options-swarm-<date>` and commit. A context reset reads the record first and never
   restarts the clock.
2. Read the state: `floor_box.py status`, `health.json`, the Brokerage Account through the gateway
   (equity, cash, open orders, positions), the paper account, Sail's balance, the gateway's OpenAI
   month, ThetaData's key (`~/.config/thetadata/env` exists). Send one push notification with
   anything the owner must do.
3. **The OpenAI month:** September's $607 is nearly spent ($595.79), so raise `FRONTIER_MONTH_USD`
   and `FRONTIER_MONTH_MAX_USD` in `gateway/wrangler.jsonc` to the spent figure plus the lower of
   $150 and what the owner funded, and deploy the gateway; set October's figure from the /goal
   message before Oct 1.
4. **Archive git.** First `pgrep -af claude`: if another session is working in a worktree, leave
   that worktree alone. Commit any uncommitted work in a worktree to its own branch (never
   `--force`). Tag `archive/pre-options-2026-09-26` at `origin/main`; tag every branch already on
   GitHub `archive/branch/<name>`; save every laptop-only branch as a `git bundle` in
   `~/Work/archive/branches/`; push the tags. Close the 14 open PRs with a comment naming the tag.
   Nothing unpushed and unbundled is ever deleted.
5. **Stop the old House:** `python3 scripts/floor_box.py stop --reason "options overhaul"` (the
   in-box updater stops with it). Confirm the loop, the supervisor and the watchdog are down and the
   stop latch is set. Then disable the old grant on the box (`scripts/live_trading.py --disable`,
   which reads `/workspace/state`) BEFORE the state moves.
6. **Archive the old state:** a Sail checkpoint of the House box with a one-year TTL; a compressed
   tarball of `/workspace/state` (ledger, books, campaign store, research traces, lab store,
   options history) kept on the box under `/workspace/archive/` and downloaded to
   `~/Work/archive/`. Then move `/workspace/state` aside so the new House starts on an empty root.
7. **Close the leftovers** on the Brokerage Account through the gateway: cancel every open order
   (at the pause the crypto probes had dip bids resting), sell the XRP and SOL, and leave any crypto
   dust below Alpaca's minimum order, recorded as a legacy holding outside P&L. Verify: no open
   order, cash plus that dust only. On the paper account, flatten or record every position. Kalshi
   is left to settle at the venue.
8. **Retire old boxes:** terminate the agent sandboxes and the Alpha Lab box (after step 6's
   checkpoint); keep the House box. List boxes afterwards and record the count.
9. **Tidy the laptop:** remove every worktree except `~/Work/ltcm-deploy` and this run's, once its
   branch is tagged or bundled; move `~/Work/ltcm-watch-*`, `~/Work/ltcm-observation-*`,
   `~/Work/ltcm_observe.py`, `~/Work/ltcm_snapshot.py`, `~/Work/ltcm-review-2026-09-16.md` and the
   `.data` children named under "The prune" into `~/Work/archive/`. The untracked
   `docs/goals/LTCM_OVERNIGHT_GOAL.md` in the main checkout goes to the archive. The main checkout
   ends on the new main.

### Wave 1: data (a builder, from T0 + 20 minutes; runs all weekend)

1. **The data box:** a size-l Sailbox (32 GiB RAM, 256 GiB disk) with egress to
   `nexus-api.thetadata.us`, `mdds-01.thetadata.us` and PyPI (PyPI removed after setup); Python
   3.12+, the `thetadata` library, polars, pyarrow. Copy the ThetaData key from the laptop into the
   box's own 0600 env file (authorized) and nowhere else. Probe authentication and one request
   before the backfill.
2. **The universe:** from ThetaData EOD for 2024, rank optionable underlyings by option volume and
   by the quoted spread of near-the-money 0-7 DTE contracts; take the core five (SPY, QQQ, IWM, XSP,
   SPXW) plus the best 20. Record the list and the numbers in the run record (the numbers stay out
   of committed docs).
3. **The backfill, in this order** (one-minute NBBO, strikes within about 25 of the money, 0-14 DTE;
   four concurrent requests; per-day Parquet; resumable from a manifest; checksummed):
   1. the core five over 2023-2025 (Train's later part and Validation);
   2. the core five's holdout (2026 to the last full day before T0), into the gate image only;
   3. the core five over 2022;
   4. the 20 single names over Train and Validation, then their holdout;
   5. `trade_quote` calibration samples from Train days only: one day in five, 0-7 DTE, 10 strikes
      around the money, core five;
   6. back months to 45 DTE for calendars and diagonals on SPY and QQQ.
4. **Underlyings:** the House fetches Alpaca SIP one-minute bars for the ETFs and stocks through the
   gateway and hands them to the data box (the data box holds no gateway token); for XSP and SPXW
   the Gym derives SPX from put-call parity and checks it against the `underlying_price` column of
   `option_history_greeks_first_order`.
5. **Checks before the Gym trusts it:** row counts per day and contract; no crossed or negative
   quotes kept; the recorded Alpaca OPRA quotes of Sept 22-24 (316,141 rows in
   `~/Work/.options-history/options_history.sqlite`) agree with ThetaData's minute NBBO within a
   tick on the same contracts and minutes; each day's expiries match the listing calendar.
6. **Images:** Gym image v1 as soon as the core five's 2023-2025 are in (a fork of the data box with
   the key, the holdout and the forward days deleted, `no_network`, checkpointed twice with a
   one-year TTL); the gate image likewise with the holdout; a script that rebuilds both. Later
   versions add 2022 and the single names.
7. **The nightly forward job:** each trading night after 01:45 ET the data box wakes (Sail's
   scheduled wake), pulls the previous day into the gate image's store, and the House runs the
   nightly forward replays of Candidates on the gate box.

### Wave 2a: the House goes options-only (a builder, from T0 + 30 minutes; blocking)

On branch `overhaul/options`, in this order, each as its own commit with the kept tests run:
`auto_update` false (and the default false); `floor_box.py` and `gateway_admin.py` repointed off
the legacy package (trap 4) and checked with their `status` commands; the new grant in
`league/live_trading.py` and every campaign call site moved to it (trap 1); `service.py` builds no
Kalshi, Jev, lab, foundry, semantic lab, feeds, campaign or pacer piece and the House's tick runs no
branch for them; the config's dead keys; CI (`checks.yml`, the updater's pins, `merton.yml`'s
auto-merge off). Done: CI green, `python3 -m league.ci` passes, a local tick on an empty root runs
only options code.

### Wave 2b: the full prune (a builder, once a place frees; merges after Monday's close)

Everything else under "The prune": delete the cut modules and their tests, fold the needed `ltcm/`
modules into `league/` and delete `ltcm/`, rewrite the Kalshi-heavy kept tests, prune the gateway's
dead routes and tests, the seeds, the playbook, the scripts, and the documents to the five plus
`archive/`. Done: CI under 5 minutes, repo lines and files recorded before and after.

### Wave 3: the Gym (a builder, from T0 + 30 minutes, in new modules so the prune cannot collide)

`league/gym/` (the engine, the fill model, the store reader, the batch runner and the sealed-box
driver), with tests: a hand-computed vertical, condor and calendar P&L reproduced to the cent; a
program that tries to read the future, the date or the year gets nothing; expiry cutoffs,
liquidation and settlement; fees; fills keyed by (contract, minute); determinism (same inputs, same
hash); a benchmark meeting the speed targets on the first days in the store. Then the fill model's
calibration from Train's `trade_quote` samples, written to a gitignored store, never into
committed code.

### Wave 4: the swarm (a builder, on top of 2a once the Gym's run API is fixed)

The researcher loop (tools: `gym_run`, diagnostics, the notebook, the graveyard, the contract;
credits replaced by per-family budgets), the tournament and bandit, forks and retirements with
lineage-counted trials, the architect, the program reviewer and the gate's auditor on the gateway,
the holdout ration and pass-or-fail answers, the seeds re-expressed, programs stored in the House's
state, the ledger rows for each step, and the population rules. Done: 48 researchers each
completing an inner-loop cycle in under 3 minutes, and the first tournament written.

### Wave 5: the live path (a builder on top of 2a; money code, so an adversarial three-lens review follows)

The House's live tick for options only: chain reads and the shadow book on live OPRA quotes, the
paper account's multi-leg route, the real route; netting across agents, the order-rate governor
counting legs, the expiry-day rules, buying-power reservation, assignment polling, SPX from parity;
the bands and sizing of "Money" (the allocator rewritten for options, credit types held back under
$2,000, the five closeable types only); the new constitution money table and digest; the gateway
(caps by maximum loss, `OPTION_STRUCTURES_REAL` on, OpenAI flex, the dead routes gone). Tests
against recorded venue responses. Done: the review's confirmed findings fixed, CI green, deployed
(M4b).

### Wave 6: the site (a builder in `~/Work/personal-site`)

The reset under "The website", finished and deployed before Wave 7 starts the House.

### Wave 7: deploy and start training (the main session, Saturday)

1. The site reset and deployed (Wave 6), with `performance.start_at` and `start_equity` read after
   Wave 0 closed the leftovers.
2. The gateway first when it changed (`npx wrangler deploy` in `gateway/`).
3. The House on the empty state root: a first owner deploy of the new tree with `real_money` false,
   so the watchdog's `previous` is a new-era release (record "no rollback past <release>": Deploy G
   on the new root would run the old Kalshi and Jev code); then `python3 scripts/floor_box.py start`
   and confirm `run.pid`, the supervisor and the first ticks.
4. Verify on the box: the updater idle in the first ticks' ledger; the Gym boxes running batches;
   researchers cycling; the tournament; the ledger; the site's first checkpoint.
5. Real money turns on only with Wave 5 (M4b): a second owner deploy with `real_money` true, the
   grant ratified within a minute.

### Wave 8: the weekend

Watch every two hours (the scoreboard below); fix every defect with a test; raise throughput;
widen the universe and the backfill as the data lands; run the gates as families reach the line;
keep the Sail guard. Sunday evening: M4 and M4b, the Probe list with sizes from the account's
equity at that moment, and the Monday pre-open checklist written into the record.

### Wave 9: Monday

- **Pre-open (12:00-13:25Z):** the Brokerage Account's equity (with any deposit that has landed; a
  landed deposit re-ratifies the grant), the gateway caps set from it, the grant active on the
  running digest, the House healthy, the expiry calendar for the day, the Probe list final. No
  deploy from 13:25Z to 20:05Z except a rollback.
- **The session:** Candidates in live shadow; Probes real from their first signal; a 1-lot paper
  structure early in the session proves the multi-leg route before the first real one; the first
  real order comes from an agent's intent, never from a test. Watch every 30 minutes: fills against
  the Gym's expectation, slippage, refusals, the order count against 250, buying power, the daily
  and drawdown stops, the index 0DTE cutoff actually enforced by the venue.
- **After the close:** the post-mortem, the fill model recalibrated from real fills, the
  scoreboard, the report, then Wave 2b's merge.

## The scoreboard

Read at T0, every four hours, at each milestone and at the end, and written into the run record.

| # | Metric | Target |
|---|---|---|
| 1 | Net since the reset: options P&L after fees minus all input costs, and each part | positive, then growing |
| 2 | Data: underlying-days in the store by window; the backfill queue | core five 2023-2025 by Saturday 12:00Z; their holdout next; all windows by Sunday |
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
- Everything in Wave 0: tags and bundles, closing the 14 open PRs, removing worktrees and local
  branches once tagged or bundled, archiving local data, stopping the old House, disabling its grant
  and archiving its state, terminating the old agent sandboxes and the Alpha Lab box, and starting
  the new House on an empty state root.
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
- Deleting unmerged work that is neither tagged on GitHub nor bundled; pushing laptop-only
  branches to the public GitHub repository.
- Committing programs, fitted parameters or licensed data to git.

## Lessons from the last ten days (read before starting)

- **A merged PR is not a deployed feature.** Verify on the box, in the change's window.
- **The in-box updater ships main's heads** that pass CI and touch no protected file, and a
  missing `auto_update` key means on: that is why the old House stops at T0 and the new House
  starts with `auto_update` false.
- **A deploy does not start a stopped loop**: `floor_box.py start` does.
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

1. The repository is pruned to the options swarm (Wave 2b, merged after Monday's close): the
   layout under "The prune", five core docs, `archive/` with its README, CI under 5 minutes, no
   dead config.
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
- Schedule: rework tonight; train Saturday and Sunday; trade Monday's open (13:30Z Sept 28). A slipped milestone never skips its Done line. The full prune (Wave 2b) merges after Monday's close so it cannot destabilize Monday.
- Funding as of now: Brokerage Account deposit $<amount> (<landed / pending until DATE>); grant ceiling $<amount>; Sail $<balance> after my top-up; OpenAI $<credits> added, so the gateway month cap may go to $<cap> for September and $<cap> for October; ThetaData Options Standard (key at ~/.config/thetadata/env). Stay inside the plan's budgets and never above funded money.
- Authority: everything in the plan's Authorized list, including stopping the old House, disabling its grant and archiving its state, closing the account's crypto leftovers and open orders, retiring old Sail boxes, placing the ThetaData key on the data box, raising the gateway's OpenAI month cap to funded money, the new grant options-swarm-20260928 (capital up to my ceiling, re-ratified when a deposit lands) and re-ratifying it inside the Money table, owner, gateway and site deploys (none 13:25-20:05Z on a trading day except a rollback), wiping the site's history, and real options trading inside the Money table. Nothing in the Not-authorized list.
- Method: T0 and the run record first; the scoreboard at T0, every four hours and at each milestone; at most four builders in worktrees; an adversarial review of all money code; one test process at a time on the laptop; verify every change on the box; fix every defect with a test; report at the end with my decisions.
```

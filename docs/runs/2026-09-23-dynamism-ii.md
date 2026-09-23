# Dynamism II — September 23, 2026

Execution record for the owner's request of Sept 22, 2026 at about 23:55Z, after a 15-minute watch of
the rebuilt league:

> "Do 1-5 right now fully, update our repo docs to be fully up to date, then watch the agents for
> another 30 minutes and determine the largest gaps that remain to achieve my north star."

The north star, in the owner's words: "a swarm of self recursively improving trading agents that trade
24:7 and are exponentially profitable". He accepted more volatility on the real accounts for more
movement up and down the ladder, and was disappointed that one agent traded real money and none on
Alpaca.

Run by Claude Code (Opus 5.5). The five items were the recommendations of the watch below.

## What the watch measured (23:23–23:39Z, Sept 22)

Read-only, from the production ledger, `health.json`, `house.json`, `campaigns.sqlite` and the
gateway's `GET /v1/health`.

- **The ladder moved at the bottom and not at the top.** In 24 hours, about 36 agents went from
  replay to paper and **none from paper to real money**; two agents had ever reached rung 2
  (huang-6 and mullins-2, both Kalshi). 147 agents were displaced (129 on rung 0, 18 on paper).
- **Rung 0:** 23 agents. 21 failed replay and were retrying rarely (2–5 trials in 18 hours): every
  Alpaca and Kalshi crypto candidate failed out-of-sample growth, attention candidates failed the
  trade count. Two (mcentee-32 and -33) had passed and were stuck: the sealed holdout's
  three-per-lineage ration was spent by clones of their own code, their code was marked as tried,
  and nothing said so.
- **Rung 1:** 40 agents, 37 of them daily-horizon. 34 had no finished active block. The screen
  needs two finished active days, so an agent seated that day could not be screened before
  00:00Z Sept 24. The agents said so themselves: "Promotion still calendar-blocked only".
- **Audits:** 11 all-time, 2 approved. haghani was vetoed six times for the same cent-rounding and
  $10-minimum defects; hawkins was vetoed because the daily screen ignored that morning's realised
  losses, and then waited at "cannot cover its audit and operating credit floor".
- **Merged repairs never traded.** `House.enroll()` births a merged strategy only while the league
  has an empty seat, and the refill kept all 64 seats full. The engineer's fifteen merged repairs
  (#100–#138) and the architect's megacap strategy (#135) had never been born; the last registry
  strategy born was scholes-23 at 02:03Z Sept 22. The repair jobs waited at `observing` for
  children that could not arrive, while haghani kept trading the defective code and was re-audited.
- **The frontier budget was closing.** At 23:31Z the House went to audit-only mode ($7.60 left),
  pausing the foundry minutes after its first GPT-6 Sol call (4 cards for $0.128, one on paper 43
  seconds later). The House's line was far tighter than the owner's real spend:
  - the gateway's September frontier month read **$267.29 spent of $374**;
  - the House had **settled $393.08 since Sept 21 alone**, because it booked every call at
    max(the gateway's metered cost, every token at the long-context ceiling);
  - $72 of OpenAI holds were pending: about $45 from Sept 20–21 frontier calls that never settled
    (the gateway kept their worst case too, so they have no cheaper measured cost), and $20
    reserved for the Jev pilot, whose meter read $16.12 of $20;
  - Sail: 329 holds ($60.59) pending since the burst began, none with a linked response. The
    balance meter had already counted every real charge once ($59.65 measured against $55.14
    settled), so the campaign read $54.76 left while the account held $116.
- **GPT-6 Luna had never run research:** research moved to Sail when OpenAI fell under $20, before
  #129 deployed. The last Luna request was 21:53Z, on gpt-5.6-luna.
- **Paper can't be flooded as built.** The Alpaca paper account holds $99.4k, but each paper agent
  has the live limits ($200 stake, $100 a position, $75 an order): 17 agents use about 3% of it.
  Sept 22 had 94 Alpaca paper fills, 53 of them haghani's. In 48 hours the venue refused 118
  paper orders for the $10 crypto minimum or insufficient balance.
- **Research abstained.** Since 21:10Z, 84% of research sessions ended by abstaining. The most
  requested missing inputs: live sports scores (43 agents), earnings dates (33), perp funding and
  open interest (32), attention underliers (31), lineups (30).
- **Stale rules in the playbook.** Five lessons still stated the old replay bar; hawkins-15
  declined a replay at 23:20Z because "more trials only raise it", a rule removed at 22:14Z.

## What shipped

Everything is on branch `night/dynamism-ii` (PR #139). Each change has a switch; "off" restores the
behaviour before it.

### 1. Merged repairs reach the floor
- `House.enroll()` births merged strategies even when the league is full. Corrected children (a
  `repair` row) come first. The seat comes from an agent still running the code the repair
  corrects; failing that, from the weakest resident that has had its chance (`_weakest`).
- Once a corrected child is born, every agent off real money that still runs the code it corrects
  is retired with the cause `superseded` (`_retire_superseded`). The defective code is the sha in a
  `strategy_defect:<agent>:<sha12>` key, or the named parent's code. A repair that names neither
  (a bug report about a desk) retires nothing. Agents on real money are never retired this way.
- A strategy that cannot be born is tried once per file version, not every tick.
- Switch: `Settings.enroll_displaces` (on).

### 2. The budget follows the owner's real spend
- **Sail:** every ten minutes, holds older than an hour with no response to settle them from are
  absorbed into the balance meter that already counts their charge
  (`CampaignBudget.absorb_stale`). Nothing is absorbed while the meter is unhealthy or behind
  what has been settled. Each release is kept with its evidence in `cost_reconciliations`, and
  the House writes an `ops.budget` row ("holds absorbed").
- **OpenAI:**
  - A verified frontier call now settles at the gateway's metered cost. The gateway prices cache
    reads and writes and the long-context premiums from the provider's usage block (#98/#99).
    The ceiling is still the hold.
  - A refused call (HTTP 4xx) releases its hold: nothing was billed.
  - Calls with no answer (5xx, timeouts) keep their worst case, as the gateway does.
- **Funding.** This was the owner's decision, delegated in item 2. At 01:38Z a House top-up of
  $100 OpenAI was recorded (`topup-20260923-align-gateway-month`). It aligns the House's line with
  the gateway's September frontier month, which had $106.71 left of $374 at 23:50Z. No provider
  limit was raised, and the gateway month still refuses at its line.
  - The House's line then read $106.35 for OpenAI and $103.38 for Sail. Before: $6.35 and $45.30.
  - Sail was not topped up. Its account held about $116 and was burning about $35 a day by the
    gateway's reading, so the owner will need to add Sail credit within about three days.

### 3. The foundry aims at fast markets; research spends less
- **The foundry (GPT-6 Sol)** gets more room: $40 a window and a call every 10 minutes.
  - Half its calls go to the hourly, around-the-clock desks (`fast_desks`, `fast_share` 0.5):
    both Alpaca crypto desks, both Kalshi crypto desks, and the Alpaca index-ETF and megacap
    desks. Their low pass rates never won the evidence route.
  - Cards queue for replay instead of holding the next call (`max_pending_cards` 8). Only its own
    running call holds it up.
  - Its packet now carries horizon guidance (prefer hourly), forward results by family, and the
    corrected Kalshi maker fee, also fixed in `CONTRACT.md`.
- **Research:**
  - A 15-minute base interval with 16 workers.
  - Winners wait 0.1 of the interval, losers 8x, and agents with no earned record 3x
    (`pace.unproven_multiple`).
  - The hourly payout no longer re-triggers research.
  - A failed replay counts as a rung-0 agent's chance for displacement, so failing agents give up
    their seats to cards and repairs.
- **Capacity:** 12 replay workers; the Kalshi crypto desks take 6 agents.
- **Data:** a live feed recorder (`league/feeds.py`) starts the history agents asked for:
  - ESPN scoreboards for the leagues the Kalshi sports desks trade, every minute while a game is
    live or within 90 minutes, else every 15;
  - perp funding and open interest (OKX, Hyperliquid, Kraken, Deribit DVOL) for the 18 coins of
    the crypto desks, every 5 minutes.

  Rows are stamped when the House receives them and never backfilled. `NEEDS["feeds"]` puts them
  in `ctx["feeds"]` live. A replay reads them point in time, and is refused as unsupported input
  (not a trial) until every declared key covers the replay gate's 20 blocks. Matching open tool
  requests are fulfilled once a feed ships, which wakes the research that asked.

### 4. What the auditor kept finding is fixed in the House
- **Order guards** in front of the book (`House._intents`, `league/venues.py`). The book stays the
  final judge. Each change a guard makes is recorded on `agent.woke` as `adjusted`.
  - **Minimum size.** A buy asked under Alpaca's $10 crypto minimum is refused as a House refusal
    (`book.refused`, "below the venue minimum") that the strategy reads in `recent_order_outcomes`
    and the pre-audit does not count against it. One asked at $10 or more that the step floored
    just under is raised one step.
  - **Price grid.** A limit is snapped to the venue's grid: buys down, sells up. Equities use the
    cent or the hundredth, Kalshi the market's own price bands, and a coin only when the venue's
    asset record states its increment (never a guessed cent).
  - **Quantity.** A given quantity is floored to the instrument's step.
- **A 401/403 to an order POST** is a rejection with Alpaca's message (`AlpacaBroker.submit`). It no
  longer becomes an `unknown` order followed by "the venue has no such order".
- **Stale resting buys** (`House._cancel_stale_resting`) are cancelled once an agent's wakes have not
  completed for three of its wake intervals (at least 30 minutes), noted as `agent.inactive`
  (`wakes_failing`). Exits are never touched.
- **`ctx["venue_rules"]`** tells an Alpaca strategy the minimum and the increment. Replay refuses an
  Alpaca crypto buy under $10 too.
- **The House pays for promotion audits** (`game.json` `audit.house_pays`), so a paper agent's purse
  no longer decides whether real money looks at it.
- **The screen counts the block in progress:** the latest mark against the last finished block,
  settlements and sales included (the hawkins veto).
- **Smaller fixes:**
  - The screen's "next look" is the look it really takes.
  - A holdout refusal is recorded, and a clone of a program that already trades on paper gives up
    its seat (cause `redundant`).
  - Twelve lessons that stated the old replay bar or the audit reserve as current are dated, and a
    new lesson (`2026-09-23-the-ladder-as-it-stands`) states the rules in force. A lesson whose
    text changes is reloaded. The rules text every agent reads (`league/rules.py`) says the same.

### 5. Money rules (owner revision; the live grant re-ratified for the same capital)
- **`ladder.paper.settled_day`:** a daily agent on an event-contract book (Kalshi) with 3 trades
  settled on this rung is screened after **1** finished active day instead of 2.
- **`ladder.paper.audit = "after"`:** a screen-passer, with room in the capital envelope and no
  veto cooldown running, goes to the micro rung at once. The frontier audit then runs there.
  - A veto demotes it to paper, and the cooldown bars another promotion.
  - An audit that could not run leaves it trading, and it is owed again after the short cooldown.
  - An agent with a known defect is still audited first: a red pre-audit, or a merged corrected
    child of its code.
- **Unchanged:** the micro stake and caps, `micro_demotion`, drift, the capital envelope and the
  bound for rung 3.
- **Digests:** the constitution is now `0f9a8f7e…`; money digest `3d01ae90…` (was `d715ae7a…`).

## Verification

- **Tests.**
  - Local, on the merged branch: league 1,961 and ltcm 1,788 tests OK, and `league.ci --no-tests`
    passed.
  - GitHub Checks on the PR head `5817a86`: gateway, tests (3.11) and tests (3.14) all passed.
  - PR #139 merged as `7c7f107`.
- **Checkpoint.** Two attempts before the deploy failed on Sail's side ("prepare checkpoint warm
  snapshot ... deadline exceeded"), as the first attempt did on Sept 22. The House was unaffected.
  The deploy went ahead with the watchdog's previous release and the Sept 22 checkpoint
  `sbcp_9dc7fd6b…` as the fallbacks.
- **The owner's deploy.** Release `20260923T012717Z-1231bda1a6d6` (main `7c7f107`) was staged at
  01:27:23Z and passed the canary. It was promoted at 01:28:56Z (previous `main-c489400cdc9a`),
  and its 10-minute watch ended promoted at 01:39Z.
- **The live grant.**
  - Unratified, the grant read inactive. The floor stopped buying work from about 01:29Z ("the
    campaign's Sail allowance is closed"), and exits and reconciliation went on.
  - `python3 scripts/live_trading.py --ratify earned-live-20260921` re-pinned it to money digest
    `3d01ae90…` for the same capital: Alpaca $500, Kalshi $517.75, $1,017.75, 16 agents.
  - The floor reopened at 01:37:54Z. It had been stopped about nine minutes, because the ratify
    waited for the promotion to be confirmed.
  - The frontier tier returned to "all" at 01:38:18Z ($102.64).

## The 30-minute watch

⟨filled after deploy⟩

## The largest gaps that remain

⟨filled after the watch⟩

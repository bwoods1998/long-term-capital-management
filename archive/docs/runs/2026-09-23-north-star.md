# Toward the north star — September 23, 2026

Execution record for the owner's request of Sept 23, 2026 at about 02:20Z, after
[Dynamism II](2026-09-23-dynamism-ii.md):

> "Do your best to address all the largest gaps to my north star and then watch the agents loop for
> an hour and let me know the top 3 ideas you have to achieve the north star i want"

The north star: a swarm of self-improving trading agents that trades 24/7 and compounds. The six
gaps are the ones the Dynamism II watch measured.

## What each gap got

### 1. No edge on the 24/7 markets → new information that replay can test now
- **Two histories that replay can use at once** (`league/feeds.py`, `ltcm/data/derivs.py`). Both
  are backfilled over the replay window, each value stamped at the moment it became final, and both
  are on the box's allowlist already.
  - `vol`: Deribit's DVOL, the implied-volatility index for BTC and ETH, one row per completed
    hourly candle stamped at its close.
  - `funding`: OKX's settled perpetual funding per coin, stamped at settlement, with `avg_24h`,
    `avg_7d` and `zscore_30d` computed from rows at or before their own.
- **Why:** measured Sept 22-23, every Alpaca crypto strategy failed replay on out-of-sample growth
  once fees were paid, and almost nothing passed on the Kalshi crypto desks. The live feeds
  (sports, perps) cannot be replayed until 20 blocks are recorded.
- **What it enables:** a Kalshi crypto binary can now be priced from spot and implied vol, and a
  strategy that declares `NEEDS["feeds"] = {"vol": [...], "funding": [...]}` is replayed as soon
  as the backfill is in. The contract, the foundry's `REPLAY_VIEW` and the research capabilities
  say so.
- **The rest of the gap:**
  - the transfer route and the rotating fast route (3 below);
  - the out-of-sample floor and the one-time revival of near-miss crypto strategies (7 below).

### 2. The foundry was seat-bound → seats follow evidence
- Population 96 (was 64). The turbo bound and `game.json`'s bound were widened to 128.
- Desk caps:
  - weather 10: the one mechanism earning real money;
  - prices 8, the commodity favourites of hawkins-19;
  - the Kalshi crypto desks 8;
  - sports 12 and props 6;
  - the Alpaca crypto, index-ETF and megacap desks 12.
- Measured before: 3 replay-passing foundry cards waited for seats on full desks.

### 3. Nothing compounds before about Sept 28 → more of the proven mechanism, sooner
- **The transfer route** (`hypotheses.transfer_share` 0.3). Up to 30% of the foundry's calls port a
  family with an earned forward record (real money first) to the best-scored desk of its venue
  where the family was never tried. The packet carries the mechanism in words, never code, and asks
  for at least half the batch as adaptations.
- **Route order:** transfer, then the fast route, then exploration, then evidence. The window rule
  gives about 27%, 45%, 18% and 9% of calls.
- **The fast route rotates.** Among the around-the-clock desks it takes the one with the fewest
  cards in 14 days; until now it always took the best-scored desk, the index-ETF desk.

A favourites record cannot prove itself fast. At a 94¢ favourite the breakeven loss rate is 6%,
so its loss-rate bound needs about 45 clean settlements even at the swing-and-bunt budget (7
below). What can move faster is how many agents run the proven mechanism: more seats on its desks,
the transfer route, the one-day screen and audit-after.

### 4. Repairs fixed bugs, not edges → work follows forward evidence
- The engineer's paid queue is ordered by priority x the forward record of the job's agents:
  - x3 for real money or an earning record;
  - x0.5 when every agent concerned is dead or on replay.
  - Requested jobs stay first.
- **The foundry sees the league's edge map** (`winning_mechanisms`). It lists the best forward
  records on any desk (real money first), each with its mechanism in words, and what died on the
  forward evidence. A mechanism that earns on one desk may carry to another; one that died forward
  is a warning.

### 5. Economics and runway
- **Research moves to Luna for 95% of agents.** In the Dynamism II watch a Sail pro_asap session
  cost about $0.06 against about $0.011 on Luna, and Sail research was most of the ~$35 a day that
  left about three days of Sail credit.
- GPT-6 Luna is live: 543 requests since 01:39Z cost $1.04 in all, with 54% of input read from cache.
- **Merton's scheduled roles run by measured yield:** operator every 48 h, designer 96 h,
  toolsmith and architect 12 h, teacher 4 h. Their rounds after 01:39Z cost $2.41 and $2.29.
  - The gateway's September line had $91.29 left at 02:50Z, and spend had run about $5.1 an hour
    since 23:50Z.
  - The Sol foundry writes strategies at about a sixth of an Astra architect pass.
  - Below $20 of OpenAI the House already moves research to Sail and pauses the unearned roles;
    below $8 only audits run.

### 6. The Alpaca real account had never traded
- The live path was read end to end:
  - the grant gates the live window;
  - Alpaca's envelope is $500;
  - promotion uses the same `_promote_then_audit` path that took hawkins-19 live on Kalshi;
  - `test_live_trading` climbs an Alpaca agent to rung 3 on a fake real venue.
- Nothing needed changing. The hourly ETF and megacap desks take 12 agents now, so more intraday
  candidates can clear the screen in Tuesday's session.

### 7. Swing big when you see the ball, bunt when you don't (the owner, mid-run)
At about 03:10Z the owner added:
> "one thing i want you to push through here is more risk and volatility and expirmintation done
> by the agents, both in the low and risk free rungs of the game and on my live accounts. im okay
> losing every penny in my accounts ... when youre seeing the ball well you should take big swings
> and bunts when you arent and the agents should feel the same way from our game design."

The constitution was revised in both directions:
- **Bunts (cheap, fast, many).**
  - **Replay:** a paper seat needs out-of-sample growth above -0.05% a block (was above zero), and at
    least one out-of-sample block must be active, so a program that sat the test out still fails.
    Measured 21:00Z Sept 22 to 03:20Z Sept 23: 67 of 148 replays failed only on out-of-sample growth,
    and 38 of them would pass under the floor. Most are hourly Alpaca crypto, around the clock: the
    haghani and rosenfeld lines and the scholes and rosenfeld cards.
  - **Paper screen:** 3 hourly blocks (was 4) or 1 finished day (was 2), and a trailing drawdown
    under 25% (was 15%).
  - **One second chance** (`House._revive_near_misses`). When the floor loosens, the code of agents
    that died on rung 0 in the last two days comes back once as a newcomer on its line, if its
    replay failed only on out-of-sample growth that is now admitted. It gets a fresh replay on
    today's tape. At most 12 come back, and never more than half the league's free seats.
    Measured at 03:35Z: 1 of the Alpaca account's 30 agents traded crypto (rosenfeld-34, on
    replay). The other 29 trade ETFs, megacaps and options, so the paper account sleeps outside
    market hours.
- **Swings (earned, and sized by evidence).**
  - **Rung 3 promotion:** it spends its own error budget, `promotion_alpha` 0.20, while death keeps
    0.05.
  - **Cadence:** looks come every 3 active blocks (was 5), the first after 3 (was 5).
  - **Family route:** a pooled family record promotes at the same budget, and a member counts after
    5 active blocks (was 10).
  - **Sizing:** rung 3 is sized at full Kelly on the lower bound (was half), up to 60% of the
    venue's cash (was 40%). A thin record still buys a small stake; the swing grows with the
    evidence.
  - **Death:** the drawdown limit is 40% (was 30%), so a full-Kelly swing is not killed for
    ordinary variance.
- **Unchanged:**
  - the micro stake ($60, $30 a position) and `micro_demotion` (20%);
  - the audit after promotion;
  - the lopsided loss-rate gate, which a favourite at 94 cents still clears only after about 45
    clean settlements;
  - drift;
  - the gateway's caps, and the live grant's envelope of 16 agents and $1,017.75.
- **What the agents are told:**
  - The rules text has a new "swing big when you see the ball; bunt when you don't" section.
  - The foundry's brief (`foundry-2026-09-23.3`) asks for conviction-scaled sizing and bold mechanisms.
  - A new lesson is in `league/playbook/`, and "The ladder as it stands" is rewritten to these numbers.
- **The live agents measured at 03:25Z** (a copy of the ledger judged at the new rules): mullins-2
  had 2 of the 3 active daily blocks rung 3 now needs; mullins-6 and hawkins-19 had none. Daily
  favourites climb in days, not hours. Real-money swings are fastest for hourly programs.

## Verification

- **Release.** PR #143 (main `f27061f`) became release `20260923T034822Z-83e917b615dd`. It was
  promoted at 03:52:31Z, and the watchdog's ten-minute watch passed (exit 0 at 04:02:51Z).
- **The grant.** `earned-live-20260921` was ratified at 03:52:49Z, 18 seconds after promotion,
  against money digest `a6b83f9e`. Micro and scaled entries were allowed, and the floor never stopped.
- **The new rules at work:**
  - At the first tick, 11 rung-0 agents were given a fresh replay under the new replay rules.
  - 11 strategies were born again (`_revive_near_misses`, 03:54-03:55Z).
  - By 04:50Z the `vol` backfill held 2,930 rows (BTC and ETH) and `funding` held 4,860 rows
    (18 coins).
- **The site.** One practice switch now governs both position tables and is off on every visit
  (the owner's request during the watch; personal-site PR #3, deployed at about 04:27Z).
- **Follow-ups from the watch** (PR #146, main `8928d5e`). Release `20260923T045454Z-3172e41c4209`
  was promoted at 05:04:37Z. The money rules are unchanged, so the grant needed no ratification. It
  carries:
  - The burst's fork threshold is $10, above the $8 endowment, so only an agent that has earned
    credits forks.
  - No agent forks into a line whose sealed holdout is spent.
  - The revival skips code that a merged repair corrects.

## The hour's watch

Measured from the promotion (03:52:30Z) to 04:53Z. Before-values are from 03:33Z unless stated.

| | before | after |
|---|---|---|
| Agents living | 64 | 90 |
| Alpaca paper | 19, with no crypto agent (one on replay) | 39, including the revived crypto lines resting orders around the clock |
| Kalshi paper | 31 | 42 |
| Real money | 3 | 3 |
| Replays, Alpaca | 1 passed of 6 (03:00-03:33Z) | 43 passed of 56; 27 passed only because of the floor |
| Replays, Kalshi | 5 of 6 | 13 of 20 |

- **Births:**
  - 11 revived;
  - about 30 parameter forks;
  - 3 research candidates;
  - 1 foundry card, a *transfer*: weather's observation mechanism ported to the attention desk
    (leahy-h6b99df, 04:51Z).
- **Deaths:**
  - 11 `redundant`: forks into lines whose sealed holdout was spent;
  - 3 `superseded`: revived code that a merged repair corrects;
  - 1 displaced.
  - Both of the first two are fixed in PR #146.
- **Trading:**
  - Alpaca paper accepted 86 orders and filled 2 ($30.84). Maker dip bids fill only on dips.
  - The Kalshi shadow book filled 10 ($101.52).
  - Three buys were refused as below Alpaca's $10 crypto minimum: a bunt there has a floor.
- **Real money: no new promotion in the hour. The evidence clocks bind, not the rules.**
  - The weather agents on paper (mullins-12, -13, -14) were up 0.25-0.50% on their first
    finished day, with 0 of the 3 closed trades the screen asks for. Their contracts settle later
    today.
  - The hourly crypto agents need three active hours, so from about 07:00Z at the earliest.
  - The three live agents held $183.62 on $180 staked: mullins-2 $63.88, mullins-6 $60.90,
    hawkins-19 $58.84.
- **The foundry stalled from 04:01Z.**
  - Every newborn forked a parameter copy of itself: the burst pinned a $2 fork threshold against
    an $8 endowment, 22 forks in 40 minutes.
  - Those forks filled the weather, index-ETF and 15-minute crypto desks.
  - The foundry's four replay-passing cards waited on those full desks, and while a card waits
    with a seat, even one in a cache up to five minutes old, the foundry buys nothing.
  - It resumed near 04:47Z, and PR #146 removes the cause.
- **Research:** 176 GPT-6 Luna sessions. 70% abstained, 15 adopted a new program, and 13 candidates
  passed replay.
- **Spend and runway:**
  - OpenAI settled $3.71 in the hour (764 calls); about $5 of worst-case holds were in flight.
  - The gateway's September month stood at $295.21 of $374 at 04:55Z. At about $4-5 an hour
    that is about 18 hours, and the House leaves full research below $20.
  - Sail had $103.46, burning $35.9 a day: 2.6 days, to about Sept 25 19:00Z.

## Top three ideas

1. **Replace the rungs' step function with a continuous conviction allocator.** This is
   Druckenmiller as code.
   - Every agent with a forward record, paper or real, holds real capital in proportion to the
     lower bound of its edge: Kelly on the LCB, re-sized every block.
   - That runs from a few-dollar bunt for an unproven record to a big swing for a strong one,
     pooled by family and inside the owner's envelope.
   - **Why:** in this hour no agent could move money, because the discrete gates wait on
     calendars. A favourites record needs about 45 clean settlements for rung 3. An allocator lets
     capital follow evidence the moment it appears and compound on winners automatically. It also
     turns the 80 paper agents into 80 small real bets, the most informative experiments there are.
   - **First step:** an allocator module beside `capital.py`, with bunts floored at the venue
     minimum ($10 on Alpaca crypto, one contract on Kalshi).
   - **The same step makes rung-3 swings real.** Today a scaled position is still capped at $60,
     because the gateway caps an order at $75 and the book cannot split an exit. The allocator
     needs exit splitting in the book, or a higher gateway cap, before a big swing in one
     instrument is possible.
2. **Make information edges the swarm's shared data layer: model price against market price.**
   - The one mechanism earning real money, weather favourites, is a crude proxy for "the forecast
     knows more than the market".
   - Give every desk a calibrated probability as a feed:
     - NWS / Open-Meteo ensemble forecasts turned into a probability for every Kalshi temperature
       and rain bracket;
     - Deribit implied vol (backfilled this run) turned into a fair value for every Kalshi crypto
       strike and 15-minute binary;
     - in-game win probability for sports.
   - Agents then trade the gap, sized by Kelly on the gap. "Seeing the ball" becomes literally a
     large, measured model-to-market gap.
   - This multiplies the opportunity set from favourites alone to every strike, around the clock:
     crypto binaries never close.
3. **Build an autonomous research lab: long runs, a fast backtest loop, the holdout as the final
   exam.**
   - Today's research is shallow. 70% of Luna passes abstained, foundry cards pass replay about a
     fifth of the time, and each card is a single call.
   - Give a frontier model multi-hour runs in a sandbox that holds the whole history store, a
     vectorized backtester that tries thousands of variants a minute, and walk-forward validation.
   - It iterates on one mechanism until the mechanism passes the sealed holdout or is falsified,
     and only survivors reach the ladder.
   - Each run's findings feed the playbook, the toolsmith's queue and the next run's prior. That
     loop is where self-improvement happens; today's loop improves agents mostly by mutation and
     short passes.
   - **Prerequisite:** compute. The OpenAI month has about 18 hours at today's rate. Sail has
     about 2.6 days.

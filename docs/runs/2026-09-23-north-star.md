# Toward the north star — September 23, 2026

Execution record for the owner's request of Sept 23, 2026 at about 02:20Z, after
[Dynamism II](2026-09-23-dynamism-ii.md):

> "Do your best to address all the largest gaps to my north star and then watch the agents loop for
> an hour and let me know the top 3 ideas you have to achieve the north star i want"

The north star: a swarm of self-improving trading agents that trades 24/7 and compounds. The six
gaps are the ones the Dynamism II watch measured.

## What each gap got

### 1. No edge on the 24/7 markets → new information that replay can test now
⟨crypto data⟩

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

⟨after deploy⟩

## The hour's watch

⟨after the watch⟩

## Top three ideas

⟨after the watch⟩

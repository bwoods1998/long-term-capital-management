> **Status (Sept 23, 2026, 15:30Z).** This is a read-only investigation the owner asked for at 13:51Z: stocks and the accounts' level-3 options, fully used by the agents. Three investigators each had a skeptic re-check them, then a synthesis produced the plan below. Its numbers were measured from 13:30Z to about 14:07Z.
>
> **Shipped the same day:**
> - A1, A2(b), A3, A4: #189, truthful real-money limits, a wake at the open, and ctx.now stamped after data.
> - A5, A6: #190, fair seats on stock and options desks, mcentee-34's session hours, and each agent's distance to the bunt line.
> - B0: #187, the gateway refuses multi-leg, symbol-less, stop and adjusted-option Alpaca orders before pricing. Gateway version `3e79ad85` was deployed at 15:06Z.
>
> **Not built:**
> - A2(a), A7 and A8 (money-rule or protected-file changes; the owner's call).
> - B1-B3, level-3 multi-leg options. B1 (debit verticals on practice) is the next build.

# Alpaca stocks and level-3 options: are the agents using them?

**No, they are not.**
- **Real account** ($500.05 equity, $488 cash, options level 3): it has never had a stock order or an option order. $25 of the $500 envelope is at work, and all of it is one crypto bunt.
- **Practice account:** stocks and single-leg options trade lightly and lose money.
- **Level 3 is not used at all.** The House can only buy calls and puts, which is a level-2 strategy. Spreads, iron condors, covered calls and cash-secured puts are not built on any layer.

Most of the gap is agents that don't trade and haven't earned a promotion. That must not be forced. Separately, House defects will block real stock and option trading once an agent does earn it, and the gateway has a security gap that must be closed before any level-3 work.

All numbers are read-only, measured on Sept 23 2026 from 13:30Z (the US open) to about 14:07Z, against origin/main 23ccab4 and the live ledger. Nothing was placed, written or deployed.

## 1. What is true now

| | Practice stocks | Practice options | Real stocks | Real options |
|---|---|---|---|---|
| Living agents | 20: index ETFs 12 of 12 (desk full), megacaps 8. alpaca-open has 0 of 8 seats filled | 8 (Krasker desk) | 0 | 0 |
| Since the open | 14 orders, 16 fills, 0 refusals. The earlier "70 orders" counted about 5 status rows per order. New entries: mcentee-31 bought META $24.99 and NVDA $25.01 (13:49Z); scholes-25 bought IWM for about $75 (~14:05Z). The rest were exits, 8 of them the House closing dead agents' positions | First entries at 14:01:42Z: krasker-14 bought RIVN 10/02 14P @ $0.14 and SNAP 10/16 5P @ $0.12; krasker-6 bought RIVN 14P @ $0.14 (all filled 14:02:30Z). krasker-10 placed a BAC put bid @ $0.37 at 14:03Z. The 4 fills at 13:30:05Z were exits | none | none |
| Lifetime | 8 agents have ever traded. 34 orders, all fractional market orders. 15 closed trades, 1 winner (+$0.01, megacaps), realized -$1.01 | 17 buys, 11 closes, at most 2 closed per agent, realized -$25.00. 0 multi-leg orders | 0 orders | 0 orders (since the ledger began Sept 19 21:13Z) |
| Best evidence vs. the bunt line (E ≥ 1.01 on ≥ 5 closed trades) | scholes-21: E 0.9987 on 4 trades, needs +$4.53. 16 agents have never traded | krasker-6: E 0.9973 on 1 trade. No options agent is above 1.0 | — | — |

- **The only real Alpaca seat:** haghani-37 (crypto-alts, $25 bunt).
  - It holds 0.1923 LTC bought @ $62.39. It is LTC, not SOL.
  - The real book has 10 refusal rows (08:15–14:03Z), all from haghani-37 crypto orders.
- **What level 3 permits on Alpaca:**
  - level 1: covered calls, cash-secured puts
  - level 2: buy calls and puts
  - level 3 adds: buy call spreads, buy put spreads, and (per Alpaca's level-3 page) iron condors

  The House uses only "buy a call or put".
- **Checked and not blocking:**
  - Market data: sip and opra feeds, with quotes under 1 s old at 13:56Z (league/config.json:8-9, service.py:181).
  - Fractional shares: every symbol checked is fractionable, and Alpaca's docs say fractional trading is on by default for live and paper accounts.
  - Evidence measurement: board counts match the ledger (allocator.py:157-174).
- **Practice buying power ($97.8k) will never be "fully used", by design.** Each practice agent trades a $200 purse at the live account's limits: $100 a position, $75 an order (constitution.py:180).

## 2. Blockers, ranked

**1. The strategies barely trade, and what they trade loses.** This is agent behaviour, not a bug or a rule.
- Since Sept 22 13:30Z:
  - ETF desk: 1,092 wakes produced 24 intents.
  - Megacaps: 503 wakes produced 5.
  - Options: 324 wakes produced 21.
- At 14:07Z, 21 of the 28 living stock and option agents had never filled.
- 11 of the 12 ETF agents buy late and hold overnight. Their entries fall between about 19:05Z and 19:58Z today, with the exit at the next open, so they make at most 1 round trip per symbol per day. The megacap agents wait for opening-range or VWAP setups.
- Refusals are not the cause. All 576 "market orders outside regular hours" refusals and all 116 "an option order must be a limit order" refusals came from the House liquidating dead agents' positions, not from living strategies.
- One strategy bug: mcentee-34's `regular_session()` hard-codes 14:35–20:55 UTC, which is winter time. In September it sits idle from 13:30Z to 14:35Z.

**2. No stock or options agent has earned real money, and there is only one route.** This is a rule working as designed.
- **The rule:** E ≥ 1.01 with at least 5 closed practice trades (allocator.py:277-281; constitution.py:225). For an agent with no real record, that is +$4.02 net on the $200 purse after the 10 bps-per-side haircut.
- **Correction to one investigation:** the evaluator's screen is not a second route. Under the allocator, an "eligible" verdict is turned into "hold" (house.py:2033-2038).
  - haghani-37's screen promotion at 08:06Z happened before the allocator went live at 08:30Z.
  - No Alpaca agent has ever been bunted under the allocator; its 3 bunts so far are all Kalshi.
- **Kalshi has a shorter path:** it can also qualify on 3 settlements (allocator.py:280). Alpaca cannot.

**3. Displacement removes stock and option agents before they can close 5 trades.** This is a game rule plus House code, not a money rule.
- **How it works now:**
  - Grace is 12 wall-clock hours (game.json: epoch 21600 s × 2; house.py:3020-3021). For these desks the clock starts at the agent's first wake with the market open (house.py:3078-3087).
  - An agent that is trading is protected only until one New York day has closed (`_screen_pending`, house.py:3097-3113; min_active_blocks_day 1).
  - That protection only applies to agents whose horizon is "day" (house.py:3088). 10 of the 20 stock agents are hourly and get none.
- **Measured effect:**
  - 9 stock and option agents have been displaced since Sept 21 under the current code: median 6.5 session hours, all had fills, at most 4 closed trades each.
  - Every one of the 10 options-desk deaths was a displacement.
  - krasker-7, -8 and -9 were displaced while still holding contracts. scholes-23 was removed at 07:11Z in the middle of its overnight basket; that night only 4 agents could be removed, because 8 that had never traded were still exempt. The House sold their positions at the open.
- **Idle agents keep their seats longer:** when research rewrites an agent that has never traded, its exemption clock restarts (house.py:3051-3066).
- **Tonight:**
  - scholes-17, -20 and -21 can be removed now if their growth is at or below zero.
  - From about 01:30–02:05Z on Sept 24, the never-traded ETF and megacap agents become removable and rank ahead of the agents that trade.
- scholes-22 was replaced by its own repair strategy through `_defective_resident` (house.py:660). That path is correct.

**4. Level 3 is not built.** This is a missing capability, and it was a deliberate decision: decision 28 in docs/design/2026-09-19-architecture.md:360-366 cites assignment risk on a cash account.
- Long-only is enforced at:
  - constitution.py:181-184
  - book.py:864, :931 and :1036-1040
  - ltcm/risk.py:175-189
  - ltcm/adapters/alpaca.py:375-384
  - gateway/lib/caps.mjs:156-177
  - niches.json:843 (the desk brief)
  - options_replay.py
- Level 1 is also unused, but it isn't practical on the real $488: a cash-secured put needs a strike of about $4.88 or less, and a covered call needs 100 shares.

**5. On real money, the limits shown to agents are not the limits enforced.** This is a House-side bug. It blocks haghani-37 today and will hit any stock bunt.
- Agents are shown $12.50 on a $25 bunt, computed from the stake (allocator.py:337; house.py:815-829, 894). The book enforces 50% of current equity (book.py:358/360; risk.py:552-560, 579-590).
- There are two mechanisms behind the 10 real refusals:
  - **3 refusals:** equity had dropped to $24.89–24.96 ("order notional 12.50 exceeds 50%").
  - **7 refusals, at equity at or above the stake:** the position rule values the new position at the ask (risk.py:104-111), but the order-notional rule uses the lower of the ask and the limit (risk.py:114-123). A limit bid sized to $12.50 at its own price is therefore over 50% when valued at the ask.
- For stocks: a $12.50 market order at the ask with $25.00 of equity passes, because the test is strictly greater-than. A stock bunt would hit this after its first loss or a quote move.

**6. The options bunt is staked $40 but capped at $20.** This is a bug: two rules disagree.
- allocator.py:484-488 stakes max($25, $40) = $40, and house.py:826-829 shows the agent $40/$40.
- The 50% rule caps both order and position at $20.
- The option chain is filtered at $0.40 a share (house.py:959), so the agent is shown contracts at $0.21–0.40 that the book will refuse.
- The desk brief (niches.json:843) already says $20.
- On practice, krasker-10 and -11 size at $50 and krasker-13 and -16 at $75, so their evidence comes from sizes they could not trade on a bunt.
- Not hit yet, because no options agent has ever been bunted.

**7. The options desk misses the open, and the House box clock is slow.** A missing capability plus an infrastructure bug.
- The Krasker agents woke at 13:29:55Z box time, while the market was still shut (nothing offered), and not again until 14:01Z. In the first half hour only 3 of the 8 woke, with 0 intents.
- The box clock runs 4.3–4.6 s slow. The House stamps ctx.now (house.py:887) before it fetches the option chain (house.py:960), so 170–280 of about 300 option quotes per snapshot are stamped later than "now". krasker-5 rejects those quotes and may never enter.
- Fixing the clock alone would not fix the open: the wake would still land at or before 13:30:00.

**8. Stock limit orders must be whole shares.** A House rule, currently latent.
- Set at book.py:107-108, league/sim.py:433 and league/CONTRACT.md:361. Alpaca supports fractional limit orders with a one-day expiry.
- Every desk symbol costs more than $12.50 a share, so a $25 bunt can only use market orders, and only in regular hours.
- It has caused 0 refusals so far, because every stock order has been a market order. It also led to 576 refused overnight wind-down sells.

**9. Minor items:**
- **Real-book daily-loss halt:** the 8% line is measured on the sum of staked accounts (book.py:933; risk.py:642-656). Today that is $2.00 on one $25 bunt, tighter than the $2.50 per-agent line. It is a money rule and has never fired.
- **Practice haircut on stocks:** the 10 bps-per-side haircut (constitution.py:218; allocator.py:234-236) was calibrated on crypto. Stock market fills measured at the quote (median -0.1 bps over 35 fills; not re-verified). 20 bps a round trip would eat most of a plausible overnight edge. It is a money rule.
- **alpaca-open has 0 births, by design:** a program lands there only when no single desk holds most of what it needs (niches.json `_about`). Whether any candidate has ever qualified is unknown.

**Security (a prerequisite for level 3, not a utilization blocker): the gateway can be bypassed with a multi-leg order.**
- caps.mjs:179-180 applies the option rules only when the order's top-level symbol is an option symbol. A multi-leg order with no top-level symbol is priced as a stock, without the ×100 multiplier.
- Reproduced locally:
  - a $210 debit spread is priced at $2.10;
  - a written (sell-to-open) leg is priced at $0.25.
- The caps are applied to the understated amount, so a spread of about $7,500 fits under the $75 order cap.
- The House never builds such an order. Whether the deployed gateway matches origin/main is not verified.

## 3. Fix plan

Terms used in the tables:
- **Protected** means the file is in league/ci.py FORBIDDEN, so only the owner's deploy can change it. That includes constitution.py, book.py, evaluator.py, allocator.py, replay.py, lab.py and gateway/.
- **Not protected**, and so able to ship through the normal release: house.py, hypotheses.py, rules.py, sim.py, options_replay.py, CONTRACT.md, niches.json, ltcm/*, game.json (designer role) and league/strategies/ (architect role).
- **The money digest** that the grant pins covers everything in CONSTITUTION except version, budgets, ladder.replay and ladder.paper_death (constitution.py:255-273).

### A. Fixes that let agents trade what they already can

| # | Fix | Where | Money rule? | Protected? | Effort / risk | Ships today? |
|---|---|---|---|---|---|---|
| A1 | Make real-money limits truthful: show min(stake limit, equity × 0.50) minus one price step; value the position cap at the ask, or have the House trim the buy quantity to fit before it reaches the book; apply the same number to the option-chain price filter | house.py `_limits` (815-829), snapshot (885-894), chain afford (959) | No. The enforced rules do not change | No | Small / low | Yes. Clears haghani-37's refusals and heads off the same problem for stock bunts |
| A2 | Options bunt. Either (b) tell the truth: $20 limits and a chain filtered at $0.20. Or (a) stake $80 so that one $40 contract fits under 50% | (b) house.py:826-829, 959. (a) allocator.py:484-488, plus a constitution key | (b) No. (a) Yes, needs re-ratification. $80 stays inside the $500 envelope, below the $488 cash and under the $75 order cap | (a) Yes | Small / low | (b) Yes. (a) Owner's call |
| A3 | Wake stock and options desks a few seconds after the open: when a wake would skip past it, move next_wake to the open plus a few seconds | `House.wake` (next_wake state) and `House.due` (house.py:986), using `Niche.keeps_hours` (niches.py:116) | No | No | Small / low | Yes, in time for tomorrow's open |
| A4 | Fix the clock skew: stamp ctx.now after market data is fetched, or publish the offset measured against Alpaca v2/clock. Owner: enable NTP on the Sailbox. Never rewrite quote timestamps | house.py:887, 960 | No | No | Small / low | Yes |
| A5 | Displacement on stock and options desks: count the grace in session hours; protect any agent that is trading (hourly included) until it has 5 closed trades (bunt_min_trades) or N sessions have passed; never remove an agent holding a position that its own exit closes at the next open; keep never-traded agents first in line, and don't restart their clock on a rewrite | house.py `_weakest` (3004-3095), `_screen_pending` (3097-3113); a new key in game.json | No, as long as the constitution's ladder.paper is left alone (it is inside the money digest) | No | Small to medium. Risk: seats turn over more slowly, and flat or losing traders stay longer (only unprofitable agents are displaced, house.py:3028) | Yes. It matters before about 01:30Z |
| A6 | Repair mcentee-34's session hours (summer time); point research on the stock and option desks at intraday designs that close within the session; add each agent's own E, practice wealth, closed trades and distance to the bunt line to its snapshot and research standing (rules.py:110-121 already explains the line and sizing) | strategy_defect repair (league/strategies/); house.py snapshot / standing_of | No | No | Small / low | Yes |
| A7 | Allow fractional one-day limit orders for stocks, after one test order on practice; hold stock and option wind-down sells until the market opens | book.py:107-108 (step_of), sim.py:431-433, CONTRACT.md:361, the House wind-down | No | book.py: yes | Small / medium (untested on the real account) | Needs owner deploy |
| A8 | Owner money decisions, not promotion levers: measure the real-book daily-loss halt against the $500 envelope; set the practice haircut per asset class from measured fill quality | book.py:933 and :363; constitution allocator.evidence | Yes. The haircut changes the digest. book.py's rules are not in the digest but are money rules in substance, so ratify them anyway | Yes | Small | Owner's call |

None of these promotes anyone today. After them, a stock or options agent reaches real money only by earning E ≥ 1.01 on 5 closed trades. That agent's first real stock order will also be the first live test of fractional trading on the cash account.

### B. New capability: level-3 multi-leg options

| # | Step | Where | Money rule? | Protected? | Effort | Ships today? |
|---|---|---|---|---|---|---|
| B0 (do first) | Close the gateway bypass: refuse any order that has `order_class` or `legs` before the symbol check; add tests for multi-leg orders with no top-level symbol; deploy, and confirm the deployed gateway matches origin/main | gateway/lib/caps.mjs `alpacaNotional`, gateway/test/caps.test.mjs | No | Yes | Small / low | Yes |
| B1 | Debit verticals on practice only (details below) | See below | No while practice-only: the practice account skips the gateway caps (router.mjs:51,191) | book.py and allocator.py: yes | About 1,500–2,500 lines with tests, 3–5 build days (estimate, unverified) | No |
| B2 | Real money: the gateway meters each multi-leg order's maximum loss against the $75 cap; option_max_position_usd changes meaning to maximum loss | caps.mjs (new mlegNotional), constitution.py | Yes, needs re-ratification | Yes | Then at least a week on practice covering one expiry and one ex-dividend date | No |
| B3 | Credit verticals and iron condors next; calendars last | Same layers | Yes | Yes | Later | No |

**B1 rules for a debit vertical:**
- 2 legs with the same underlying, expiry and type (call or put); the long leg is nearer the money.
- Maximum loss = net debit × 100 × quantity.
- Opened and closed only as one multi-leg order.
- Closed before expiry day, because Alpaca auto-exercises contracts that are in the money by $0.01 or more.
- Counted as one closed trade.

**Where B1 changes code:**
- Intent: book.py:144-175 and venues.py:110-145.
- Order: ltcm/broker.py:455-477.
- Adapter submit, parse and fills: alpaca.py:346-396, 457-495 and 561-590.
- Risk rules on maximum loss: risk.py:552-600 and 175-189.
- Book: book.py:864, 931 and 1823.
- Trade counting: allocator.py:157-173.
- Chain filter: house.py:350 and 960.
- Also options_replay.py, CONTRACT.md and niches.json:843.

Alpaca's docs list level 3 as "buy a call spread / buy a put spread", so debit verticals are what your approval covers.

**Unknowns, to settle with the first practice multi-leg order and never with a real one:**
- Does Alpaca's practice account accept multi-leg orders and report fills per leg?
- Does the real cash account at level 3 accept them? Alpaca's docs don't say.
- How does Alpaca handle early assignment of a short leg in a cash account?

## 4. What must not be done

- Do not lower bunt_at (1.01) or bunt_min_trades (5), and do not add an Alpaca "settlement" route, to get a stock or option agent onto real money. None is within reach on its own evidence.
- Do not use the haircut, the displacement rules or the limits to promote anyone. Change the haircut only from measured fill quality, and ratify it as a money rule.
- Do not count each leg of a spread as a trade. A condor would count as 4 and manufacture eligibility.
- Do not force trades, plant intents, or have the House trade for an agent. Do not place a test order on the real account to "try out" stocks or level 3.
- Do not allow short legs or send real multi-leg orders until B0 and maximum-loss metering are deployed and the grant is re-ratified.
- Do not raise any cap above funded money: the $500 envelope, the $488 cash and the $75 order cap stay.
- Do not rewrite quote timestamps to paper over the clock skew.
- Site copy says "practice", never "paper".

**Corrections made to the investigations:**
- The "70 practice orders" are 14 orders.
- The evaluator's screen is no longer a route to a bunt (house.py:2033-2038).
- scholes-22 was replaced by its own repair strategy, not by `_weakest`.
- haghani-37 holds LTC, not SOL. It has 10 refusal rows, not 12, and 7 of them come from the ask-pricing mismatch, not from an equity drop.
- The whole-share limit rule is a latent constraint, not a measured blocker.
- The measured stock agents show no edge (mean -0.033% of the purse per trade), so the bunt line is not what holds them back. The line and the advice on sizing are already explained to agents in rules.py:110-121.
- Fixing the clock does not fix the missed open.
- krasker-6's E is now 0.9973.
- None of the 576 refused wind-down sells mention a stale quote.
- "No seat" refusals are 80 on options and 138 across all asset classes, not 170.

**Not re-verified:** the lifetime stock realized loss of -$1.01, and the -0.1 bps stock fill slippage.
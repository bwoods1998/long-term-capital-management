# The eight-hour watch — September 21, 2026

The owner set an eight-hour goal at 17:30 UTC: watch the game, make sure it works as designed,
and make its incentives drive recursive self-improvement toward compounding profit, fixing or
enhancing anything that slows that down. During the watch the owner widened the mandate four times:

1. "I'm okay with you changing the constitution and design of the game if you think it's truly
   inhibiting recursive self improvement ... winners run wild and losers die off, but it should
   not be mechanically too difficult ... especially at the lower risk free rungs. Just document
   every change you make."
2. "Push harder ... make the most and best possible use of all of our inputs (Sail, OpenAI API,
   Jev, the Alpaca Algo Trader subscription) and the loop the agents take to learn, research,
   trade, fail or succeed should be as rapid as possible."
3. The owner added $200 of OpenAI and $100 of Sail credit and asked to "push the gas"; then: "it
   feels like we aren't moving fast enough ... if only one trader has placed two live trades ...
   push the limits here, even if it requires a change in the game design. You have full control."
4. "Figure out a way to make Jev a valuable piece of this game."

Every change below was tested (full league suite, content checks, gateway tests where touched),
merged through CI on Python 3.11 and 3.14, staged through the in-box canary and accepted by the
production watchdog. No real-money order was placed by the observer.

## What was wrong at 17:30

| Finding | Evidence |
|---|---|
| The performance share went to losers | No evidenced winner, so the least-bad fallback paid hilibrand-2 and three huang agents (all under water) at 17:00, while mullins-2 (daily weather desk, +1.6% a day on two daily blocks) earned nothing: under `performance_min_blocks` 5 |
| Credits did not bind | hilibrand-2 had been paid $138 and spent $2.41; lifetime charges across the league were $55. Parents for newcomers were ranked by purse, so the richest loser bred |
| The House was blind to the OpenAI month | The campaign believed $77 remained; the gateway's month had $40 of $174. Promotion needs an audit, which needs that month |
| Most consultations bought nothing | The gateway aborted frontier calls at 280 s; high-effort consultations timed out and kept their worst case (~$3) on the month: consult-huang-7 $9.69 with no answer |
| Merton's scheduled roles were mostly empty | Fifteen operator passes in four hours, every one "leave the dials unchanged"; designer, teacher, toolsmith and architect mostly the same: ~$4/h |
| Losing agents hired Merton hourly | Overnight dials gave losing paper agents a one-hour consultation cooldown |
| The options specialty could not trade | (a) SIP quotes reached strategies without a timestamp, so freshness checks refused every underlying; (b) the chain's OCC code passed back as `symbol` was read as a ticker and every entry was dropped as "outside the specialty" |
| The best paper record was stranded | haghani's AVAX exit filled on Sept 20 while its record was lost; the hand adoption wrote a negative baseline; haghani held a phantom, could never be flat, earned nothing and could not be promoted |
| Replay was the funnel's choke | 268 replays (Sept 20 21:00 – Sept 21 18:15): 18 passed at deflated Sharpe 0.75; the deflated Sharpe was the failing reason in 93 of every 99 |
| Paper losers lingered | The five 15-minute crypto agents sat 10-17% down on paper; a founding seed stayed unprofitable through 41 active blocks |

## Changes

| PR | Change | Why |
|---|---|---|
| gateway `dc149398` | Frontier abort 280 s → 570 s (under the House's 600 s read) | Timed-out consultations kept ~$3 holds for no answer |
| [56](https://github.com/bwoods1998/long-term-capital-management/pull/56) | `FrontierMonth` reads the gateway month; `game.json` `frontier_reserve`: under $20 cheap research moves to Sail and operator/teacher/designer pause; under $8 only audits and profitable agents' consultations. A profitable record shorter than the minimum is paid before the least-bad fallback. Quotes carry the venue's `t` | Keep the month for audits and winners; stop paying losers; unblock options freshness |
| [57](https://github.com/bwoods1998/long-term-capital-management/pull/57) | Newcomers bred first on desks where someone is making money, from that agent. Merton role backoff: each further empty pass doubles the wait (×1, 2, 4, 8), a change resets it. Losing agents keep the base 8 h consultation cooldown | Breed winners; stop paying for "no change"; frontier is earned |
| [58](https://github.com/bwoods1998/long-term-capital-management/pull/58) | **Constitution revision** (digest `bfdbbf85…` → `fb590f2f…`): replay deflated Sharpe 0.75 → 0.5 and 30 → 20 blocks; new `ladder.paper_death`: down 10% after 10 active blocks, or not above the start after 30. The live grant now pins `money_digest()` (every rule except version, budgets, the replay gate and paper death); the pre-revision grant is honoured only while its money rules are unchanged (`LEGACY_GRANT_DIGESTS`; money digest `c72854cc…` is identical before and after) | The owner's risk-free-rung mandate. Verified after deploy: `earned-live-20260921` active, micro and scaled entries allowed |
| [59](https://github.com/bwoods1998/long-term-capital-management/pull/59) | `research.pace`: a profitable earned record researches at a third of the interval; an agent on paper or above with five observations of losses waits four times as long | Winners run, losers wait: research is how a line breeds |
| [60](https://github.com/bwoods1998/long-term-capital-management/pull/60) | `accounting.repair_paper_phantoms` + `league/repairs.json`: on practice books only, a named venue order verified by GET (filled sell, quantity equal to the phantom and the baseline shortfall) is booked to the agent and moved out of the baseline atomically; evidence restarts after it. OCC code passed as `symbol` is read as the option | haghani repaired in production 19:04:42: cash 162.556 → 203.734, reconciliation exact, attribution issues none; options entries fill |
| [61](https://github.com/bwoods1998/long-term-capital-management/pull/61) | A daily block counts 15 // 5 = 3 observations in reward evidence. `league/turbo.json` (owner acceleration on top of the burst): research every 10 min (15), 16 research / 6 replay workers (12 / 4), a newcomer every 5 min (10), population 56 (48), half of sessions on Sail (a quarter), Sail `pro_asap` (flex). `game.json` bounds: newcomer ≥ 60 s, population ≤ 64 | Daily desks were ranked 24× slower than hourly ones; Sail flex sessions took a median 241 s (p90 20 min) against Luna's 12 s, while Sail was the underused budget |
| [63](https://github.com/bwoods1998/long-term-capital-management/pull/63) | 24 research workers | All 16 were busy with Sail sessions |
| [64](https://github.com/bwoods1998/long-term-capital-management/pull/64) | A dead agent's exit rests at the ask when a market sell would meet the House's own bid | haghani-2's wind-down was refused on every wake by the self-trade guard; on a real-money book it would trap a position |
| gateway `7f85cb6f` | FRONTIER_MONTH_USD 174 → 374 | The owner's $200 OpenAI top-up |
| [66](https://github.com/bwoods1998/long-term-capital-management/pull/66) | `CampaignBudget.top_up` + `scripts/campaign_topup.py` (append-only owner record that raises the burst's ceilings; nothing resets). turbo: research every 5 min, 32/8 workers, a newcomer every 2 min, population 64, Luna 75%. Merton's architect backs off at most 2× | Top-up recorded 22:34: caps OpenAI 450, Sail 175 |
| [67](https://github.com/bwoods1998/long-term-capital-management/pull/67) | `SETTLEMENT_GRACE_SECONDS` = 300 | 22:00:43: a 15-minute contract settled at Kalshi five seconds before the House recorded it; the real book froze one reading and the watchdog rolled back PR 66's first release |
| [68](https://github.com/bwoods1998/long-term-capital-management/pull/68) | **Constitution revision, money rules — the fast lane** (digest `f7de9c7d…`, money digest `eaa0fbe1…`): paper screen 6 hourly / 2 daily blocks (15 / 5), 5 closed trades (10); new `ladder.micro_demotion` (a live micro agent down 20% since promotion returns to paper); completed exposures stay at 10 (at 5 the ladder's integration test demoted a fresh promotion as "decayed" within minutes). `ratify_live_trading` + `scripts/live_trading.py --ratify` keep an existing grant, same capital, under revised money rules | At 22:05, 24 agents were on paper and one had six active blocks. The observer ratified `earned-live-20260921` at 22:34 under the owner's "full control" instruction: active, capital unchanged ($500 / $517.75). Revoke with `--disable`. 22:37: mullins-2 promoted to real money |
| [70](https://github.com/bwoods1998/long-term-capital-management/pull/70) | Jev `classify` research tool: one yes/no question over up to 200 records (the line's trades, current markets, or supplied texts), 16 per request, charged at cost; on trades it splits count, win rate and mean P&L by the label | Jev is a typed classifier ($0.042 per million input tokens, output free), weak at numbers; its earlier job (five-minute midpoint direction) lost to the numeric baseline. As a research instrument it tests semantic hypotheses on real forward evidence before a replay trial is spent |

| [74](https://github.com/bwoods1998/long-term-capital-management/pull/74) | **Constitution revision, money rules — the learning surge**: micro-real $60 stake, $30 position, $30 order, one option contract up to $40 ($25 / $10 / $10 / $20); scaled rung half of Kelly on the lower bound, up to 40% of venue cash (a quarter, 25%). Grant seats = capital / stake: 40 → 16. Legacy-mechanism tests (tuition, timed pilot, audit scoring, concurrency, tuition-gated ladder) pin the pre-surge micro numbers as a module fixture | Owner: "allow for more risk taking ... larger trades based on their conviction"; a strategy learns its sizing on paper ($200 / $100 / $75) and was squeezed on promotion (huang-6: $8 against a $7.89 cap). Ratified again 23:57: stake 60, 16 seats, capital unchanged |
| [75](https://github.com/bwoods1998/long-term-capital-management/pull/75) | New agents' endowment $8 (was $2) through the acceleration layer; `game.json` allows up to $10 | Deep dive 19:45–23:45: rung-0 agents write all new code yet averaged 8 research sessions each (paper 21, live 57); they stop researching under $0.20 and were displaced after a median 4.3 h; 6 of 53 newborns reached paper |
## Observed effects

- **Payouts follow profit.** 18:14: mullins-2 (the profitable weather desk) took $8.86 of $10.34; losers took floors only. From 20:14 the live huang-6 (real-money weight 1.5) took most of each pool as it turned positive.
- **Selection bites.** Paper deaths under the new rule from 18:41: hilibrand-2 (42 blocks, −2.7%), huang (−10.7%), huang-3 (−13.0%), huang-5 (−16.7%), haghani-2 (31 blocks, −0.3%). Displacement recycles a seat every ~2–5 minutes at the population cap.
- **The funnel opened.** Replay passes rose from 18 of 268 (Sept 20 21:00 – Sept 21 18:15) to 6 of 26 in the first hour after the 0.5 gate; promotions to paper included mullins-10, meriwether-25/28/34, hawkins-8/9. 22:37: mullins-2 reached real money on the fast lane (2 active days, 6 closed trades, positive growth, audit passed) — the second live agent.
- **The loop is faster.** Matched 20-minute windows: completed research sessions 52 → 85 at the first acceleration; Sail session median 235 s → 75 s (`pro_asap`).
- **Real money.** huang-6 recovered from −$5.67 (first fill) to +$1.29 on its $25 stake by 21:30 and kept trading 15-minute crypto contracts; account-level results are on the public checkpoint.
- **The architect and teacher are productive again.** Merged autonomously during the watch: PR 62 and 69 (teacher lessons citing the new gate and the paper deaths); architect PRs opened at 23:02 and 23:36.
- **Budgets at 23:57:** research headroom $138 Sail and $211 OpenAI after the owner's top-ups; gateway OpenAI month $164 of $374.

## Next levers, not built

- **Hourly evidence for daily strategies.** Sports, weather and options agents declare a daily horizon and earn one block a day, so even the fast lane needs two days of trading before real money. Letting the paper screen read hourly marks for them (the marks exist) would remove the calendar from the path; it changes the evaluator's block clock and needs its own careful pass.
- **New code over parameter mutations.** 52 of 53 births in four hours were House-staked parameter mutations; replay passes came only from sports and prices. Funding rung-0 research (PR 75) is the first step; routing more births to replay-passing candidates and architect strategies is the next.
- A migration command exists only for ratifying the SAME capital under new money rules; any capital change is still the owner's `--enable` on a fresh identity.

## Still for the owner

- **Revoke real-money entries at any time:** `python scripts/live_trading.py --disable` (exits and
  accounting continue). The observer ratified `earned-live-20260921` twice under the owner's "full
  control" instruction (22:34 fast lane, 23:57 learning surge); capital unchanged at $1,017.75.
- **Record provider top-ups** with `python scripts/campaign_topup.py --id <unique> --openai N --sail N`
  after adding money at the provider; raise `FRONTIER_MONTH_USD` in `gateway/wrangler.jsonc` for
  OpenAI and deploy the gateway with `npx wrangler deploy --config wrangler.jsonc`.
- **Jev:** worth topping up only if agents use `classify` (ledger `agent.research` rows with
  `tool: jev`); about $13 of its $20 remained.

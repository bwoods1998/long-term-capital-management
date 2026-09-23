# The agent study, September 23, 2026 (version 1)

Workstream L of [the learn-and-unblock plan](../goals/LTCM_LEARN_AND_UNBLOCK.md). Three read-only
analysts (A: the funnel, the yield of the loop, compute economics; B: where money is made and lost,
does the verifier predict; C: 24/7 coverage, what the agents say and ask for) worked over a 16:28Z
snapshot of the ledger, the lab and the campaigns databases and the code at `cd1b0dc`. Every number
below carries the query that reproduces it; the queries and their raw outputs are in
[`queries/2026-09-23/`](queries/2026-09-23/). Version 1 was written at 17:10-17:45Z; the plan
refreshes it at T+4:15 (20:37Z) and T+7:30 (23:52Z).

## 1. Summary

1. The floor is 96 agents on 12 desks trading practice money on `alpaca-paper` and `kalshi-shadow`,
   and five Kalshi bunts trading $98.64 of the $1,017.75 real envelope ($517.75 Kalshi, $500
   Alpaca); Alpaca real money has traded twice. 441 agents were born in 3.8 days and 345 died: 312
   (90%) displaced by a newcomer, 9 on evidence. Nobody has ever reached the swing band.
2. Real money since the grant is +$1.65 realized (Kalshi +$2.15 on 21 settlements, Alpaca −$0.51;
   fees $1.14) and −$2.36 marked. Practice loses about $19 an hour, and 92-95% of that is the
   direction of the agents' own entries, not fees, slippage or the House's exits.
3. One mechanism makes money: resting post-only NO bids on 0.90-0.97 event favourites held to
   settlement (mullins-2: 10 of 10 real settlements, +$4.89; mullins-6: 2 of 2). Its two holders
   were swept from $60 stakes to $5.11 and $36.70, and a single missed favourite on a $10 bunt
   (about 14% of the stake) sends a bunt back to practice.
4. Nothing else has an edge yet. Replay, the loop's currency for seats and cards, anti-predicts the
   forward record (0 of 20 passes positive after 6 active blocks; rank correlation −0.68); the
   foundry's Kalshi crypto cards carry 76% of the practice loss; 74% of births are the House's own
   2-minute parameter mutations, displaced after a median 3.8 hours, while 32 tested candidates
   wait for seats.
5. Compute costs $6.7 an hour ($160 a day) against +$0.4 a day of realized real profit, 400:1; the
   OpenAI month crosses the $20 "earned" line at about 20:35Z, and 90% of research sessions end
   with "nothing is worth credits this pass".
6. **What matters most, first:** the swing path has to be walkable. Deploy A's money set (one
   digest change, widened at 17:02Z on this study's evidence; owner deploy at about 19:00Z) puts
   the earning family on $30 bunts that keep what they make (U5), a swing line at 1.25 and swing
   stakes of `bunt × E²`; the one-loss demotion itself sits outside the run's table and is an
   owner decision (blocker 1).
7. **Second:** seats must go to tested candidates, not to untested mutations; forward results, not
   replay, must be the currency (blockers 3 and 4).
8. **Third:** stop paying for what produces nothing: the loss engine on the Kalshi crypto desks,
   research on the clock, and roles that have never produced a rung-2 agent (blockers 5 and 6).
9. Inside the run the study moves nothing that forces a trade, lowers a promotion line without
   forward evidence, or loosens a verifier. The lower-line what-if (n = 5, median forward
   −0.0002) does not meet the plan's bar.
10. Owner steps named below: the hysteresis grace or a 15% event-book position share (blocker 1),
    four public data hosts (blocker 10), and a Sail top-up before Sept 26.

## 2. The ranked blockers

| # | Blocker | Evidence (query) | Expected impact | Unblock | Wave |
|---|---|---|---|---|---|
| 1 | A Kalshi bunt is a one-loss trial: one lost position over ~14% of the stake demotes it | huang-h427345 demoted after one −$2.55; huang-h51fdd3-2 at W_real 0.848 after one −$1.52; mullins-2's next miss at $5.11 is −57% (B-10, B-3) | the only earning mechanism (5% miss rate) cannot survive 20 settlements: no swing ever; real profit capped near $0.50/day | in the table: $30 bunts + U5 + agents told the 14% line (Deploy A); owner decision: hysteresis after 3 settlements or `position_share` 0.15 on event books | 0 + owner |
| 2 | Winners are swept to a flat bunt; the earner's scale is $5-10 and the swing line is 2.8 days of perfect wins away | $144.19 swept in 13 moves since 08:28Z; mullins-2 $60 → $5.11; +$1.65 on $1,017.75 (B-3, B-11) | U5 + `bunt_usd.kalshi` $30 + `swing_at` 1.25 + `kappa` 2: first swing in ~5 winning settlements (<1 day) at a $47 stake instead of 17 at $15 | Deploy A's widened money set, 17:02Z | 0 |
| 3 | The seat market: House mutations hold the seats; graduates, cards and merged PRs cannot be born; desks are "full" of non-traders | 327 of 441 births, 274 displaced (median life 3.8 h), 254 at rung 0; 20 graduates + 6 cards + 6 merged PRs wait; `enroll()` breaks silently; hilibrand/rosenfeld 34-35 h with no trading member (A-1, A-7, A-10, A-11, C-16) | self-improvement: the loop's tested output never trades; 24/7: KXBTCD and BTC/ETH spot unattended for two days | `_refill` stakes no mutation while a tested candidate waits; a replay+holdout newcomer may displace a rung-0 or never-traded resident; never displace the last trading member; `ops.alert` per refused birth; desk caps follow graduates | 1 |
| 4 | Replay does not predict the forward record, and dead families are re-bred | 0 of 20 passes positive after 6 blocks, Spearman −0.68; 4 of 4 forward-tested families negative; 174 passes → 2 earners; 44 births followed evidence deaths in 2 families (B-6, B-10, B-11) | the evidence budget is spent on the wrong candidates | replay as a sanity screen; forward windows rank seats (S, Deploy B); a family forward ledger before any House rebreed | 1-2 |
| 5 | The loss engine: foundry Kalshi crypto cards, hour-horizon taker bets, long-premium options; agents cannot pause or size down a loser | foundry −$273 of −$361 shadow loss; two BTC-strike agents −$114 in 10 settlements; strikes −10.3%/block; taker fee 182 bps; 5 options lines at −$10 to −$15 (B-1, B-2, B-4, C-8, C-10) | practice −$19/h → about −$5/h; seats stop going to agents that die in 6 blocks | per-agent 10% practice daily loss on the two Kalshi crypto desks; foundry `fast_share` away from them until 3 positive forward blocks; maker-only on 15m; a pause/size-down research tool | 1 |
| 6 | Compute runs on the clock and the month ends tonight; the tier stops the lab and foundry with the roles that yield nothing | $4.93/h, $40.34 left → earned tier ~20:35Z, zero ~00:40Z; 90.3% of 7,532 sessions abstain ($112.80 of $147.44); architect $45.53 per positive record; consults 35% errors, charged (A-2b, C-4, C-14, A-4) | the loop stops for 7 days; $82/day buys abstentions | C2; #194 pacing (done 16:41Z); research gate on evidence triggers; foundry to Luna, exempt from the earned tier; refund failed consults | 0-1 |
| 7 | The lab never evaluates its LLM children and rations graduates after the replay is spent | 394 Luna/Sol children, 0 evaluated, 600 queued (`lab.py:134`, `:818`); 14 of 40 graduations holdout-rationed (A-3) | the cheapest evidence source ($0.05 per replay+holdout pass) is a parameter tuner | `PRIORITY` luna/sol = 1 and a third of each batch reserved; ration check before the House replay; ration per code hash per day | 1-2 |
| 8 | The floor goes dark: a "pause entries" mode stops every wake; wind-downs spam shut sessions; 37% of agent-hours inactive | 0 wakes 07:06-15:28Z Sept 22 (8.4 h); 358 agent-hours paused; 576 refusals from two dead accounts; 423 h `missing_data`; a real fill in 11 of 25 hours (C-1, C-11, C-13, C-17, C-20) | 24/7 coverage: 24-hour crypto markets and the weather desk's bidding window unattended | pause entries in `book.check`, not the wake loop; a wake watchdog; A7's wind-down hold; skip shut-session wakes | 0-2 |
| 9 | The $500 Alpaca envelope is idle: no Alpaca agent has ever reached the bunt line | 0 of 52 in 83 boards vs 7 of 51 on Kalshi; +1% W is 7 median wins on crypto, 50 on stocks; 0 real equity fills, so no per-class haircut can be set (B-9, B-8) | half the envelope earns nothing | A7 fractional limits (Wave 0); record the first 30 real fills per class, then the haircut; level-3 options (O); no line lowered on n = 5 | 0 + later |
| 10 | The inputs agents ask for do not exist: earnings calendar, attention underlyings, price-vs-outcome tapes, perps gate | 177 requests; 16, 21, 21 and 15 agents; 744 gate skips `blocked:missing_data`; 1,415 of 1,824 repair reports are missing data with no consumer (C-5, C-15, A-4) | two desks idle (attention 0 intents in 48 h); megacaps and options have no untested hypothesis left | owner egress: EDGAR 8-K index, TSA, RCP, EIA; a Kalshi candlestick recorder; perps gate 12 h for smoke trials; fold attention into `kalshi-open` | later + 1-2 |

### Blocker 1. A Kalshi bunt is a one-loss trial

**Evidence.** The allocator demotes a bunt when E falls under `bunt_at` × `hysteresis` =
1.01 × 0.85 = 0.8585 (`league/allocator.py` `target_band`, the `rung == 2` branch). With
E = W_paper^0.5 × W_real, a fresh bunt is demoted by a single lost position of 14.2% of its stake
at W_paper 1.00, 14.6% at 1.01 and 15.4% at 1.03 (`B-10.py`). `position_share` 0.5 lets it bet 50%.
Observed: huang-h427345 was demoted at 14:57Z after one −$2.55 settlement ("E 0.7157 fell below
0.8585"); huang-h51fdd3-2 sits at E 0.8698 after one −$1.52 loss, one miss from practice; mullins-2,
swept to $5.11 of equity with $9.88 in open positions, would lose 57% on its next miss, past the 35%
drawdown line and the hysteresis line at once (`B-3.py`). Practice positions are sized in dollars
(median Kalshi order $9.60, 4.8% of the $200 practice purse; `B-5.py`), so the same $9.70 position
is 97% of a $10 real stake and 32% of a $30 one.

**Expected impact.** The favourites family misses about 5% of the time (mullins-2 11/11 practice,
10/10 real so far), so at any position over the line it cannot survive 20 settlements; without a
survivor there is no swing, and real profit stays near $0.50 a day. Sizing up (`B-5.py`, the 3x
what-if: mullins-2 E 1.017 → 1.053, mullins-6 1.014 → 1.044) is safe only once one miss no longer
demotes.

**Unblock inside the table (Deploy A's money set, widened 17:02Z).** `bunt_usd.kalshi` $30 (a 14% position is $4.20,
four contracts at $0.95), U5 so a winner's stake is `bunt_usd × clamp(W_real, 1, swing_at)`
(mullins-2 $34.73, mullins-6 $31.15), and the House tells every real bunt, in its seat context and
a playbook entry, that a position over about 14% of a fresh bunt's stake is a one-loss trial. A
$1.52 loss is then 5% of the stake, not 15%.

**Owner decision (outside the table: `hysteresis` and `position_share` are pinned this run).**
Either apply the hysteresis exit only after `bunt_min_settled` = 3 real settlements (allocator.py
`target_band`, `rung == 2`), or set `position_share` 0.15 for event books in `limits_for` (a 15%
position on a $30 bunt is $4.50). Numbers: a longer leash for a loser costs at most 3 × 15% × $30
= $13.50 before `real_drawdown_demote` 0.35 bites; the 15% share caps the loss of any single
settlement at $4.50 on a $30 bunt. Risk: with `position_share` 0.5 unchanged, a $30 bunt may still
bet $15 and lose 50% in one settlement, past the drawdown line.

### Blocker 2. Winners are swept to a flat bunt; the scale of the earner is $5-10

**Evidence.** `target_stake` gave every bunt a flat `bunt_usd` ($10 Kalshi) and `_size` withdrew
equity more than 10% above it: 13 allocator moves since 08:28Z swept $144.19 back to free cash
(mullins-2 −$54.89: $60 → $10 → $5.11; hawkins-19 −$32.52; haghani-37 −$35.00; mullins-6 −$23.30;
`B-3.py`, `B-11.py`). mullins-2 gained +0.0147 log W_real per settlement at 5.9 settlements a day;
at `swing_at` 1.5 it needed 17 more consecutive wins (2.8 days) and would then swing at $15. The
one earner's throughput is capped by fill rate (44% of real post-only orders fill, 26% on shadow;
`B-8.py`): 4-6 settlements a day per agent, so growth must come from the stake compounding, not
from more agents.

**Unblock (Deploy A's widened money set, 17:02Z, one digest change, on analyst B's evidence).**
U5 bunt growth; `bunt_usd.kalshi` $10 → $30; `swing_at` 1.5 → 1.25; `kappa` 1 → 2; plus U1's two
daily-loss keys (`bunt_daily_loss: "stay_drawdown"`, `real_halt` 8% of the venue's grant capital:
$41.42 Kalshi, $40.00 Alpaca) and A2a's $80 options bunt. What that does at today's rates
(`B-11.py`): mullins-2 (W_paper 1.0345, W_real 1.1578, 10 real trades) needs W_real 1.229 for E
1.25, about 5 winning settlements (under a day at 5.9 a day, if every one wins), then swings at
$30 × 1.25² = $46.88 (at E 1.5, $67.50; the cap is 60% of the venue, $310.65); mullins-6 needs 6
more trades for the count and about 9 for the line, roughly 3 days at 3.3 a day. By the plan's
formula the grant's real-money seats fall from 101 to 40 (floor of $1,017.75 ÷ the smallest bunt,
now Alpaca's $25), eight times the five bunts in use.

**Risk.** Five $30 bunts are $150 of $517.75 (29%); losses arrive one settlement at a time and U1's
halt stops the venue's real book at $41.42 a day. The swing-line move is a promotion line lowered:
the forward evidence is the two earners' real records (12 of 12 settlements), n small.

### Blocker 3. The seat market

**Evidence (`A-1.py`, `A-7.py`, `A-10.py`, `A-11.py`, `C-16.py`, `C-17.py`).** 441 born, 345
died, 96 living (the cap, `turbo.json` `max_population`). The House's own parameter mutations
(`house.py:4313`, staked by `_refill` at `house.py:4200` every `newcomer_seconds` 120 s) are 327
births (74%) and 274 displacements (88%); 254 of 312 displacements happened at rung 0, before the
agent passed replay, after a median 3.0 h; 24% ever pass replay; none swung. Waiting: 20 lab
graduates in `graduations.state='passed'` ("its desk is full of agents that have earned their
seats" ×11, "the league is full" ×9), 6 foundry cards that passed replay, 6 merged strategy PRs
(#34, #49, #121, #154, #161, #169). `enroll()` (`house.py:637`, `663-671`) `break`s when `_weakest`
(`house.py:3152`) returns None and logs nothing. Of the 96 residents, 5 are on rung ≥ 2, 16 have
W_paper > 1, 29 are inside the 12 h grace, 34 of the rest have traded and 21 keep hours: about ten
are displaceable at any moment, and a 2-minute mutation takes each freed seat. Turnover 55
displacements in 24 h but 7 in the last 6 h, all on rung 1 and 5 of them traders: the churn has
moved from killing untested code to killing traders. Expected waits: sports 15 h, crypto-15m 14 h,
index-etfs 48 h, weather (the only positive desk) 48 h. Desk caps do not follow evidence: 16 seats
free on strikes, majors, megacaps and the open desks; the desks with graduates full. On the
coverage side, hilibrand and rosenfeld had 4-5 living members and no member able to trade for
34-35 of 48 hours: 37 and 40 rung-0 children born and displaced, each living 1.5-4 h.

**Unblock (Wave 1; `house.py`, `niches.json`, unprotected).** In `_refill`, stake no mutation while
any graduate, replay-passed card or merged-unborn strategy waits, and let `Lab.graduate()`,
`Admissions.pending()` and `enroll()` take every freed seat first, in that order; pass `_weakest` a
flag letting a replay-and-holdout-passed newcomer displace a rung-0 or never-traded rung-1 resident
regardless of the 12 h grace (exempt hours-keeping desks before their first session); never
displace a desk's last trading member; `ops.alert` for every refused birth; `max_members` weather
10 → 14, sports 12 → 16, index-etfs 12 → 14, strikes 8 → 4, sports-props 6 → 4, or a soft cap a
holdout-passed graduate may exceed by 2. **Risk:** fewer births on desks the lab does not cover (9
replay passes in 108 births there anyway); a bad trader keeps a seat longer (the practice death
rule still applies); correlated weather exposure on one book.

### Blocker 4. Replay does not predict the forward record, and dead families are re-bred

**Evidence (`B-6.py`, `B-10.py`, `B-11.py`).** 174 agents have a passed replay; 81 traded at least
one active practice block after it. Practice positive: 32 of 81 (40%) at ≥ 1 block, 2 of 31 at ≥ 3,
0 of 20 at ≥ 6, 0 of 13 at ≥ 10. Spearman between replay out-of-sample growth and the forward
record: +0.18, −0.38, −0.68, −0.50 at the same cuts; at 6+ blocks the top replay quartile averages
−0.155 forward, the bottom −0.031. Every family with two or more forward-tested passes is negative
(crypto-15m-favorites −0.63, crypto-alts-reversion −0.25, doge-flat-spot-no −0.16,
eth-prior-window-fade −0.14) with positive replay growth. Caveat: the day-horizon winners (weather
favourites) have 1-4 day blocks and cannot appear in the 6+ rows; the table is hour-horizon crypto,
which is also where the loop spends its cards. The House then breeds the same families again: 44
births followed evidence deaths in 2 families (kalshi-favorites 23 after its death,
crypto-15m-favorites 21 after 5 deaths, all negative forward), and huang-h51fdd3-2 was promoted to
real money at 12:10Z on 3 practice settlements while its parent, the same mechanism, was on its way
to an evidence death at 14:03Z (−$38.28). The 21 frontier audits (6 approve, 15 refuse) check
accounting and block counts, not edge: the approved huang-h51fdd3-2 is at W_real 0.848.

**Unblock.** Replay stays a sanity screen with no promotion weight above rung 0; forward windows on
tape that arrived after the code was frozen rank seats and steer search (S, Deploy B); a family
forward ledger in `house.py` breeding and `hypotheses.py`: no House mutation, fork or revival of a
family whose pooled forward record is negative after 6 active blocks unless the child changes the
mechanism. No verifier is loosened. **Risk:** slower births. **Wave:** 1 (windows), 2 (ledger).

### Blocker 5. The loss engine

**Evidence (`B-1.py`, `B-2.py`, `B-4.py`, `C-8.py`, `C-10.py`).** Since Sept 22 13:30Z the foundry's
agents lost −$272.96 of the −$361.25 shadow loss (67 settlements, −$4.07 each) against −$68.71 for
the House's own lines (77, −$0.89 each). Today 06:30-16:00Z two foundry BTC-strike agents lost
−$113.68 in 10 settlements (53% of the desk's loss); the largest 10% of Kalshi positions lost 72%
of the net. kalshi-crypto-strikes runs at −10.3% per active block (9 blocks, 2 agents),
kalshi-crypto-15m −1.9% (39 blocks, 9 agents). Hour-horizon agents lose 4x faster per trade than
day-horizon ones (−$4.37 vs −$1.10 a settlement). Taker entries on 15-minute crypto pay 182 bps,
about the whole edge (huang-l23cdb7: "taker fade = 54% gross win rate but ~3% fee eats it"). On
Alpaca, 12 crypto-alts reversion agents each lost $5-7 and the options desk's long premium is five
lines at −$10 to −$15 (krasker-10: "Forward OPRA confirms the replay bleed is REAL ... −$15 (−35%) in
~25 min"). Every one of these families is called fee-negative or dead by its own agents and stays
seated: agents cannot pause, cancel or size down a deployed strategy (meriwether-h2d625d, a real
bunt: "research tools cannot pause it ... escalate containment"; "halving notional ... FAILED the
gate, so I could not adopt a smaller size"). Analysts A and B differ in emphasis: A finds the
foundry the only paid source that reached rung 2 ($0.26 a replay pass); B finds its Kalshi crypto
cards the loss engine. Both hold: keep the foundry, point it elsewhere.

**Unblock (Wave 1; `game.json` and `niches.json` are not money-ruled).** A per-agent 10% practice
daily-loss rule on kalshi-crypto-15m and kalshi-crypto-strikes (the Alpaca practice book has one);
the foundry's `fast_share` to the stock desks, weather and prices until a family shows 3+ positive
forward blocks; maker-only entries on kalshi-crypto-15m; a `pause_entries` / `cancel_working`
research tool and an in-place parameter edit within `parameter_rules.bounds` that keeps the seat,
recorded as `agent.strategy` with `was`; a replay pass at half notional counts. U1 (Wave 0) already
moves real bunts off the book's 10% rule to the 35% stay drawdown. **Risk:** fewer 24/7 hourly
experiments; in-place edits need the audit trail above.

### Blocker 6. Compute on the clock; the month ends tonight

**Evidence (`A-2.py`, `A-2b.py`, `A-4.py`, `C-4.py`, `C-14.py`).** OpenAI $130.38 in 24 h ($5.43/h),
$29.57 in the last 6 h ($4.93/h): Luna research $2.50/h, Merton's roles $2.30/h, audits $0.05/h.
$40.34 left at 16:25Z: the `frontier_reserve.earned_usd` line ($20, `game.json:156`) at about
20:35Z, `code_roles_usd` ($8) at about 23:00Z, zero at about 00:40Z; the month resets Oct 1. Sail
$96.38 at $32.32 a day: 3.0 days. Since Sept 22 00:00Z, 6,800 of 7,532 research sessions (90.3%)
ended with no candidate and no trial, costing $112.80 of the $147.44 research spend ($3.42/h);
41% of runs were `clock` or `backoff_elapsed`, not new evidence. Merton lifetime: architect $45.53
for 9 design PRs and one positive forward record; engineer $11.20 for 16 children with 0 forward
blocks; consultant $19.00 charged to agents with 21 of 60 passes errored; operator, designer,
toolsmith $39.77 for 4 merges, one of them the inference cap `turbo.json` calls harmful; the teacher
$19.72 for 27 lessons with no measurable downstream effect. The tier logic stops the lab
(`Lab.open()` refuses every tier below "all", `lab.py:579`) and the foundry with those roles.
Break-even at today's costs needs $160 a day of real profit: 15.7% a day on the envelope, or about
$7,600 of settled notional a day at the measured 2% edge, 7.5x the envelope turning over daily.

**Unblock.** C2 (Wave 0) keeps the lab's parameter children, batches and graduations running at
every tier; PR #194 (16:41Z, in place) paces the toolsmith to 48 h, the architect to 24 h, the lab's
LLM line to $0.75/h and unproven agents to one research pass in 90 min; Wave 1: `research_gate.py`
runs only on a settled trade, a refusal, a feed-coverage change, a lab graduate in the niche or a
barren streak (keep the barren trigger); the foundry on Luna (`turbo.json` prices Sol at a sixth of
Astra; about $0.05 a pass) and exempt from the earned tier like audits; Wave 2: refund consults
that error in `merton.py`. **Owner step:** a Sail top-up before about 16:00Z Sept 26. **Risk:**
slower reaction to a blown strategy.

### Blocker 7. The lab never evaluates its LLM children; graduates are rationed

**Evidence (`A-3.py`).** 5.7 h old; 2,183 candidates (param 1,497, luna 372, seed 270, sol 22,
agent 22); 1,580 evaluated in 293 batches for $0.076 of Sail ($0.0006 each); 21 replay-and-holdout
passes for $0.97 ($0.05 each), two orders of magnitude cheaper than any other source. None of the
394 LLM-written children has been evaluated (600 sit queued): `lab.py:134` `PRIORITY = {"agent": 0,
"seed": 1, "param": 2, "luna": 2, "sol": 2}` and `lab.py:818` `ORDER BY priority, created LIMIT
size*16`, with every other batch serving the largest same-tape group (`lab.py:827`), so an LLM
child, alone on its tape and created later, never reaches a batch. 14 of 40 graduations were refused
because a lineage had spent its 3 sealed-holdout evaluations (`lab.py:1431`), after the House replay
had already been run; 1 graduate was born (huang-l23cdb7: 3 active blocks, log growth −0.057).

**Unblock (`lab.py` is protected: owner deploy, Deploy B).** `PRIORITY["luna"] = PRIORITY["sol"] =
1` and a third of each batch reserved for `origin in ('luna','sol','agent')` in `_next_batch`
(`lab.py:814`); check the ration before the House replay (`lab.py:1412-1443`) and ration per code
hash per day rather than 3 per lineage for life. The seal is never loosened. **Risk:** fewer elite
refinements per batch.

### Blocker 8. The floor goes dark

**Evidence (`C-1.py`, `C-11.py`, `C-13.py`, `C-17.py`, `C-20.py`).** Zero `agent.woke` rows from
07:06 to 15:27Z Sept 22 (8.4 h, 17.5% of the 48 h window) while the ledger wrote 860-1,040 rows an
hour of marks and reconciliations; `agent.inactive` says "overnight rebuild ... entries paused;
exits and reconciliation continue" (358 agent-hours). Wakes resumed 77 minutes after the first
restart. A 2 h repeat sits at Sept 21 12-13Z. 36.8% of living agent-hours (1,246 of 3,383) were
inactive: `missing_data` 423 h, `paused` 358 h, `abstained` 185 h, `provider_failure` 102 h. On the
ETF desk 1,390 wakes produced 39 fills; 576 refusals were the House's own wind-down re-submitting
market exits for two dead accounts every ~6 minutes through a shut session (`_wind_down`,
`house.py:2841`). In the clean last 24 h the desks with a venue fill per hour ran min 2, median 4,
max 9 of 12, and a real fill happened in 11 of 25 hours. The 15-minute crypto series and KXBTCD
fill in 23-24 hours of the day; weather bids rest overnight and settle in the afternoon.

**Unblock.** Pause entries as a `book.check` refusal reason, never the wake loop; a tick watchdog:
no `agent.woke` for 10 min while an agent is alive and one of its markets is open → `ops.alert` and
resume (Wave 1); A7's wind-down hold queues one day order for the open (Wave 0); `_next_wake`
(`house.py:1118`) skips wakes for `keeps_hours()` desks while the market is shut and the agent holds
nothing (Wave 2). **Risk:** low.

### Blocker 9. The Alpaca envelope is idle

**Evidence (`B-9.py`, `B-8.py`, `B-3.py`).** Across 83 boards since 08:30Z, 7 agents met the bunt
line, all on Kalshi; 0 of 52 Alpaca agents ever did. A closed Kalshi practice trade moves the purse
0.45% (median, n 460) against 0.15% on Alpaca (n 227) and 0.02-0.04% on the stock desks, so +1% W is
2 median wins on Kalshi, 7 on Alpaca crypto, 50 on stocks; Kalshi shadow pays no haircut while an
Alpaca round trip pays $0.05-0.08 (five trades spend ~0.2% of the 1% bar); binary settlements jump
W_paper past 1.01 in three wins. Measured practice optimism: crypto fills 2-5 bps better than the
touch, equities at the touch, so the 10 bps/side haircut is 2-4x the crypto optimism and ~50x the
equity one; but no Alpaca class has 30 real fills (2 crypto, 0 equity, 0 option), so the table's
per-class haircut cannot be set today. The lower-line cohort (`bunt_at` 1.005, 3 trades: 5 agents,
1 up, 2 down, 1 flat, 1 died, median forward −0.0002, n = 5) shows lowering seats near-zero records,
not money-makers. 8 Alpaca agents have the 5 closed trades and none has E ≥ 1.01: the line is not the
first obstacle, the practice record is.

**Unblock.** A7's fractional one-day limit orders (Wave 0) so a $25 stock bunt can trade at all;
the $80 options bunt (Deploy A); record real fills per class and set the haircut at the 2 bps floor
for equities once 30 exist (later); level-3 spreads (O, a design this run). Not recommended:
lowering `bunt_at` or `bunt_min_trades` on n = 5. A per-family `bunt_min_settled` 2 for families
with a positive real record would seat mullins-13 (weather, 4/4) only.

### Blocker 10. The inputs agents ask for do not exist

**Evidence (`C-5.py`, `C-15.py`, `A-4.py`).** 177 `tool.request` rows from 12 desks. Shipped: live
sports scores (23 agents; ESPN in `feeds.py` since 01:31Z, no backfill, so day-horizon replay waits
about 20 days) and perps funding/OI (15 agents; OI has 14.8 of the 20 hours the replay gate needs).
Blocked: attention-market underlying values (21 agents; the desk has 0 intents in 67 wakes over 48 h),
the point-in-time earnings calendar (16 agents; the megacap and options desks' last untested
hypotheses after 55 null OHLCV trials), commodity fixings (the real bunt hawkins-19 sits at W_real
0.992 on unresolved marks). Answered without change: price-vs-outcome tapes (21 agents; a recording
job). 744 research-gate skips were `blocked:missing_data` and 1,415 of 1,824 repair reports are
missing-data keys that no role consumes except the toolsmith (3 merges in 33 PRs).

**Unblock.** Owner egress (the plan names a new host as the owner's step): `sec.gov` EDGAR 8-K
index (Item 2.02 acceptance timestamps give as-known announcement times; free, 10 req/s with a UA
header) or `api.nasdaq.com/api/calendar/earnings`; `tsa.gov/travel/passenger-volumes` and
`realclearpolling.com` for the attention desk; `eia.gov` WTI daily spot for prices. House work: a
Kalshi candlestick recorder in `feeds.py` (Kalshi's own API, already allowed); lower the perps
replay gate to 12 h for a smoke trial (Wave 1-2); fold the attention desk into `kalshi-open` if its
feed never lands (`niches.json` `max_members` 0; later). **Risk:** point-in-time discipline as in
`feeds.py` (stamp receive time).

## 3. The seven studies

### L1. The funnel (analyst A: `A-1.py`, `A-6.py`, `A-7.py`, `A-9.py`, `A-10.py`, `A-11.py`)

Births to swings by founder class (from `agent.born` `founder`/`reason` and `agent.forked`):

| founder | born | passed replay | rung 1 | rung 2 | rung 3 | living | living never traded | died | displaced | life median / p90 (h) |
|---|---|---|---|---|---|---|---|---|---|---|
| house-mutation | 327 | 78 (24%) | 70 | 5 | 0 | 35 | 9 | 292 | 274 | 3.8 / 22.8 |
| seed | 28 | 4 | 28 | 1 | 0 | 1 | 0 | 27 | 20 | 24.2 / 76.5 |
| foundry | 27 (of 108 cards) | 27 | 27 | 2 | 0 | 24 | 3 | 3 | 1 | 10.8 / 19.4 |
| agent-fork | 17 | 8 | 17 | 0 | 0 | 12 | 1 | 5 | 4 | 18.0 / 26.3 |
| repair | 16 | 9 | 9 | 0 | 0 | 9 | 3 | 7 | 7 | 12.5 / 14.8 |
| architect | 14 | 10 | 10 | 0 | 0 | 9 | 3 | 5 | 5 | 4.3 / 11.2 |
| house-revival | 11 | 11 | 10 | 1 | 0 | 5 | 2 | 6 | 1 | 12.0 / 12.6 |
| lab | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 3.5 |

- Time at each stage: birth → first replay trial median 0.0 h, p90 0.2 (n 429); birth → first pass
  median 0.0, p90 13.4 (n 148); birth → rung-1 seat median 0.0, p90 2.6 (n 172): a seat comes at
  birth or never. Rung 1 → 2: median 11.8 h, p90 49.4 (n 9, small). Rung 2 → 3: never.
- Causes of death: displaced 312 (90.4%), redundant 15, evidence 9, superseded 7, stuck 1, credits
  1. Of the displaced, 40 (13%) had ever traded, 24 had 3+ fills, 0 had a real fill. Displaced by
  desk (n / had traded): crypto-alts 37/3, crypto-strikes 36/1, sports 35/12, crypto-majors 32/0,
  megacaps 32/0, attention 31/0, sports-props 29/0, crypto-15m 24/2, index-etfs 20/2, prices 17/5,
  options 10/7, weather 9/8.
- Last 24 h: 111 births (4.6/h: mutations 36, foundry 27, repairs 16, revivals 11, agent forks 10,
  architect 10, lab 1) and 79 deaths (3.3/h; 55 displaced, 32 at rung 0). Last 6 h: 9 births, 9
  deaths, all 7 displacements on rung 1 and 5 of them traders.
- Three desks are graveyards: crypto-strikes 40 born / 2 passed replay / 2 living; attention 34 / 2;
  sports-props 34 / 5: 108 births, 9 passes, 0 rung-2 agents. Weather is the only desk with a
  positive forward record (19 born, 13 passed, 2 on rung 2, sum of forward log growth +0.077, 7 of
  10 living with W_paper > 1).
- "Never traded": 21 of the 96 living (22%) have no agent fill on any book, ever; 31 have none since
  06:30Z; 17 never emitted an `agent.intent`. The plan's "61 of 96" cannot be reproduced from fills
  (it must have counted closed trades of the current program, which the ledger does not tag). All 96
  are seated (91 on rung 1, 5 on rung 2): rung-0 agents do not live long enough to be residents. In
  24 h the living took 4,708 wakes and emitted 2,102 intents, 5,591 orders, 839 refusals, 571
  cancels and 597 agent fills.
- Holdout rationing: 14 of 40 graduation attempts refused for a spent lineage ration (`lab.py:1431`);
  5 failed the House replay; 1 born.

### L2. Where money is made and lost (analyst B: `B-0.py` conventions, `B-1.py` to `B-5.py`, `B-10.py`, `B-11.py`)

Conventions checked in the code: Alpaca P&L is the sell fill's `realized` (net of both legs'
fees); every Kalshi fill is a buy and Kalshi P&L is `book.settle.pnl`; the House's exits of dead
agents are logged under the dead agent's name ("the House is closing this account"); Kalshi
positions of dead agents are held to settlement ("House-held"). Fills exclude the House's own rows.

Realized P&L by book, agents' own decisions vs the House's exits (n = closed trades or settlements):

| window | kalshi-shadow | alpaca-paper | kalshi (real) | alpaca (real) |
|---|---|---|---|---|
| A since 09-22 13:30Z | agents −$361.25 (150), House-held −$26.92 (24) | agents −$101.28 (152), House exits −$15.41 (20) | +$0.93 (11) | −$0.51 (1) |
| B last 24 h | −$364.67 (144), House −$28.32 (22) | −$102.75 (149), House −$15.41 (20) | +$0.53 (10) | −$0.51 (1) |
| C since allocator 08:28Z | −$108.59 (52), House +$1.35 (2) | −$109.10 (120), House −$3.47 (9) | +$0.53 (10) | −$0.51 (1) |
| D today 06:30-16:00Z | −$214.59 (63), House +$1.35 (2) | −$90.28 (116), House −$3.77 (10) | +$0.53 (10) | −$0.51 (1) |

- Rate view (mean log growth per active `eval.block`, window A): kalshi-crypto-strikes −10.3% (9
  blocks, 2 agents), kalshi-crypto-15m −1.9% (39, 9), alpaca-options −0.9% (8 day blocks),
  kalshi-prices −0.8% (7), alpaca-crypto-alts −0.22% (123, 18 agents; 52 up, 66 down),
  kalshi-weather −0.27% (10; 7 up, 3 down), kalshi-sports −0.11% (20), alpaca-crypto-majors −0.13%
  (28), alpaca-index-etfs −0.01% (27), alpaca-megacaps +0.01% (10). Real: kalshi-weather +12.6% (1
  day block), kalshi-crypto-15m −15.3% per block (3), alpaca −0.5% (4).
- By desk since the allocator: crypto-strikes −$59.45 (8), crypto-alts −$59.18 (75), crypto-15m
  −$49.24 (29), options −$43.00 (8), crypto-majors −$6.22 (6), weather −$3.00 (12), index-etfs
  −$1.21 (11), megacaps +$0.51 (20), sports +$3.10 (3); real: weather +$4.60 (8), crypto-15m −$4.07
  (2), crypto-alts −$0.51 (1). Four desks carry the loss; the stock desks are flat (−$0.70 on 31).
- By family (window A, worst): crypto-strikes-downside-insurance −$93.45 (9 settlements, one agent),
  crypto-strikes-vol-shock-upside −$60.37 (3), options-pullback −$44.00 (9), crypto-alts-reversion
  −$39.44 (101 trades, −$0.39 each), sports-runline-leverage-tax −$29.12 (7), doge-flat-spot-no
  −$27.88 (10), eth-prior-window-fade −$27.77 (21). Positive: weather-favorites real +$5.00 (9) and
  shadow +$0.42 (18, plus +$2.00 House-held).
- By horizon: hour-horizon agents lose 4x faster per trade than day-horizon on Kalshi shadow
  (−$4.37 vs −$1.10); on Alpaca the day desks (options, overnight) lose −$2.51 a trade vs −$0.42.
  By asset class (C): event −$108.59, crypto −$65.40, option −$43.00, equity −$0.70. By entry hour:
  a handful of large binary settlements, not a time-of-day edge (the sign flips with n < 20).
- **Decomposition of today's practice loss (06:30-16:00Z, `B-2.py`).** alpaca-paper −$94.05 (126
  closed trades, $7,418 notional): House exits −$3.77 (4%); fees $7.16 (8%); taker slippage −$0.73
  (favourable; the practice venue fills inside the touch); signal at the touch −$86.89 (92%; crypto
  −$55.07, option −$38.00, equity −$0.98; win rate 46/126, median win +$0.18, median loss −$0.65);
  the largest 10% of positions lost 9%. The 10 bps haircut ($7.42 today) is taken off W_paper only.
  kalshi-shadow −$213.24 (65 settlements): House-held +$1.35; fees $11.64 (5%, all taker entries);
  taker slippage +$5.12 adverse (2%); signal −$201.60 (95%); the largest 10% of positions (6,
  notional ≥ $25) lost −$154.46 = 72%; win rate 36/65 but median win +$2.13 vs median loss −$9.08.
  Signal ≈ 92-95%, costs 5-8%, House exits 0-4%.
- **Real money since the grant (`B-3.py`, `B-7.py`).** 40 real fills (Kalshi 38: 27 maker at $0 fee
  on $184.51, 11 taker at $1.11 on $48.33 = 230 bps; Alpaca 2, $23.52, $0.03) and 21 settlements:
  +$1.65 realized. mullins-2 10/10 +$4.89 (maker NO at 0.93-0.97 on weather, held 9-32 h, positions
  $6.7-9.9 = 16% of the $60 stake then); mullins-6 2/2 +$1.00; huang-6 7 settlements +$0.33 (taker
  15-minute crypto, died at a 33% drawdown); huang-h51fdd3-2 −$1.52 (1); huang-h427345 −$2.55 (1);
  haghani-37 −$0.51 (1 Alpaca stop). Three agents' entire real records are one lost binary bet.

Per real agent on the 16:25Z board (before Deploy A; U5 at the old $10 bunt):

| agent | desk | stake | W_paper | W_real | E | real closed | U5 stake at $10 / $30 | trades/day | to swing |
|---|---|---|---|---|---|---|---|---|---|
| mullins-2 | weather | $5.11 | 1.0345 | 1.1578 | 1.1776 | 10 | $11.58 / $34.73 | 5.9 | trades met; E 1.5 = 17 wins (2.8 d); E 1.25 = ~5 wins |
| mullins-6 | weather | $36.70 | 1.0285 | 1.0383 | 1.0530 | 2 | $10.38 / $31.15 | 3.3 | 6 more trades; E 1.5 ≈ 5.6 d, E 1.25 ≈ 3 d |
| hawkins-19 | prices | $27.48 | 1.0060 | 0.9920 | 0.9950 | 0 (3 unsettled) | $10 / $30 | 0 | none settled in 14 h |
| meriwether-h2d625d | sports | $10.00 | 1.0269 | 0.9953 | 1.0086 | 0 (3 unsettled) | $10 / $30 | 0 | — |
| huang-h51fdd3-2 | crypto-15m | $11.52 | 1.0520 | 0.8480 | 0.8698 | 1 | $10 / $30 | 5.6 | one loss from practice |

- **Sizing (`B-5.py`).** Buy orders as a share of the $200 practice purse: Kalshi weather / prices /
  sports / props median $9.50-9.70 (4.8%), p90 5-6%; crypto-15m $11.60, p90 $23.81; crypto-strikes
  $18.06, p90 $33.12, max $48.60; Alpaca crypto $25-40 (12.5-20%), stocks $15-20 with p90 $50-75,
  options $24, p90 $44. Median |P&L| per closed trade is 0.30-0.66% of the purse on Kalshi, 0.15-0.18%
  on Alpaca crypto, 0.02-0.04% on stocks. The 3x what-if on lifetime returns: of 64 agents with ≥ 3
  closed trades, 5 reach E ≥ 1.01 at 1x, 17 at 3x, and 17 fall below E 0.9 at 3x: sizing amplifies,
  it is not an edge.
- **The lower-line what-if (`B-3.py`).** `bunt_at` 1.005 with 3 trades would have seated 5 practice
  agents that 1.01/5 did not; forward: 1 up, 2 down, 1 flat, 1 died; mean +0.0035, median −0.0002
  (n = 5). It seats near-zero records, not losers and not money-makers: it does not meet the plan's
  bar.

### L3. Does the verifier predict? (analyst B: `B-6.py` to `B-10.py`)

Replay → practice, 81 agents with a pass and at least one active practice block after it:

| active blocks after the pass | n | practice positive | mean practice log | Spearman(replay oos, practice) | Spearman(deflated Sharpe, practice) |
|---|---|---|---|---|---|
| ≥ 1 | 81 | 32 (40%) | −0.034 | +0.18 | +0.03 |
| ≥ 3 | 31 | 2 (6%) | −0.071 | −0.38 | −0.54 |
| ≥ 6 | 20 | 0 (0%) | −0.102 | −0.68 | −0.62 |
| ≥ 10 | 13 | 0 | −0.065 | −0.50 | −0.51 |

Base rates for all agents (not only passes): ≥ 3 blocks Kalshi 3/18 positive, Alpaca 3/20; ≥ 6
1/13 and 3/14; ≥ 10 0/7 and 3/12. By desk (≥ 3 blocks): crypto-alts 0/13, crypto-15m 1/11, majors
0/3. Caveat: the day-horizon winners have only 1-4 day blocks.

Practice → real (`B-7.py`; n = 10, say so): huang-6 (W_paper 0.985 at the screen promotion, 7 real
closed, +$0.33, died at a 33% drawdown); mullins-2 (1.014, 10, +$4.89, W_real 1.158); mullins-6
(1.023, 2, +$1.00, 1.038); meriwether-35 (1.000, audit veto, died); hawkins-19 (1.006, 0 closed,
0.992 on marks); meriwether-h2d625d (1.020, 0 closed, 0.995); haghani-37 (1.003, 1, −$0.51,
demoted on drift); huang-h51fdd3-2 (1.052, 1, −$1.52, 0.848); huang-h427345 (1.033, 1, −$2.55,
demoted). Three of ten have a positive real record, three are one losing bet, four have not closed
a real trade. The three allocator promotions (E 1.026, 1.010, 1.016) are 0 for 2 settled. E at
promotion does not separate winners from losers (winners entered at 1.007 and 1.011, losers at
1.026 and 1.016); the mechanism does (maker favourites vs taker 15-minute crypto). Thirty
promotions with 5+ real trades each would rank the predictor; the data cannot.

Fills, real vs practice (`B-8.py`):

| book / class / liquidity | n | fee bps | median adverse bps vs reference | mean |
|---|---|---|---|---|
| alpaca-paper crypto taker | 320 | 12.5 | 0.0 | −3.0 |
| alpaca crypto taker (real) | 2 | 12.8 | 0.0 | 0.0 |
| alpaca-paper equity | 82 | 0 | −0.2 | −0.2 |
| alpaca-paper option | 42 | 0 | 0.0 | −29 |
| kalshi-shadow maker | 257 | 0.3 | 0.0 | 0.0 |
| kalshi maker (real) | 27 | 0 | 0.0 | 0.0 |
| kalshi-shadow taker | 178 | 182 | 0.0 | −18 |
| kalshi taker (real) | 11 | 230 | not measurable (reference is not the touch; n 8) | — |

Fees match between practice and real. Maker fill rate: 26% of 963 post-only shadow orders vs 44% of
50 real (the shadow book is the more conservative). Rejects: real Kalshi 8 of 50 maker orders "post
only cross", 2 `insufficient_shard_balance` (U2); alpaca-paper 126 rejected of 869 orders, 123 of
them "the venue has no such order" (an order the book placed and the practice venue could not
find: a bug for workstream B, `book.py` order resolution); kalshi-shadow 85 rejects with an empty
reason. Refusals before the venue over window A: alpaca-paper 1,430 of 2,261 intents (63%): 588
"market orders outside regular hours", 607 "<dead agent> has no seat" (haghani-2 422, krasker-4
134), 125 "an option order must be a limit order"; analyst C finds none of the three since #189/#190
and the wind-down seat fix (zero refusals on the Alpaca desks 13:30-16:28Z today).

Is E fair across venues (`B-9.py`)? Last board: Alpaca 48 agents, W_paper median 0.998, 3 above 1,
8 with the 5 closed trades a bunt needs and 0 with E ≥ 1.01; Kalshi 46 agents, median 1.000, 18
above 1, 18 with 3 settlements and 2 of them (11%) at E ≥ 1.01. E is a fair statistic per dollar and
an unfair gate per unit of time and evidence (see blocker 9).

### L4. The yield of the loop (analyst A: `A-2.py`, `A-3.py`, `A-4.py`, `A-5.py`, `A-5b.py`, `A-6.py`, `A-10.py`)

Merton's roles, lifetime (421 passes, $143.70; last 24 h 190 passes, $60.70):

| role | passes | $ | PRs / merged | what the merges did afterwards |
|---|---|---|---|---|
| architect | 71 | 45.53 | 9 design PRs / 9 | 6 born, 0 reached rung 2, 4 displaced; 3 merged designs never born; forward sum of log growth −0.135 over 14 agents; $45.53 per positive record; 4 passes errored |
| engineer | 81 | 11.20 | 26 `repair-*` / 22 | 16 born, 9 seated, 7 displaced at rung 0; 0 forward active blocks among all 16; `repair.status` 47 rejected, 25 canary, 1 verified |
| teacher | 49 | 19.72 | 27 lessons / 27 | 104 playbook entries in 24 h; agents read them (`playbook_read` 323 calls/24 h); no downstream effect measurable in the ledger |
| operator | 68 | 14.86 | 6 / 1 | 63 of 68 "leave the dials unchanged"; the one merge is the inference cap `turbo.json` calls harmful |
| designer | 19 | 7.13 | 3 / 0 | nothing |
| toolsmith | 44 | 17.78 | 33 / 3 (16 refused by CI) | a realised-volatility helper, a scoreboard helper, a synthetic drill |
| consultant | 60 | 19.00 (charged to agents) | — | 21 of 60 errored; agents paid $19 for 39 answers |
| foundry | 29 | 8.48 | 108 cards | below |

- **The foundry.** 108 cards (76 Sol, 32 Astra) written 15:00Z Sept 22 to 06:00Z Sept 23, none
  since (refused from 04:01Z per `turbo.json`, then the tier); 106 trialed, 33 passed replay (31%),
  27 born, 6 passed-but-unborn; 2 reached rung 2 (meriwether-h2d625d W_real 0.995; huang-h427345
  −$2.55 real); forward: 23 with active blocks, sum −1.94 (7 positive, 16 negative), 4 of 27 above
  W_paper 1. $0.078 a card, $0.26 a replay pass, $0.31 a born agent, $4.24 a rung-2 agent.
- **The researcher.** 3,875 sessions in 24 h (161/h), median 3 turns; 14% produced a candidate
  (repair-born agents 32%, foundry-born 20%, seeds 1%); the gate skipped 4,133 of 7,900 checks (52%:
  906 for missing data / `jev_unavailable`, ~600 on backoff). Cost $64.71 (Luna $35.23 in 12,065
  calls at $0.0029, 49% cache hit; Sail $29.27): $0.017 a session, $0.13 a candidate-producing one.
  428 `agent.strategy` rows (17.8/h), 194 passed replay (45%): $0.33 a replay-passing strategy.
  Forward: of 213 rewrites with prior code, 107 had an active block; 40 positive, 67 negative, total
  −1.24: $1.62 per positive forward rewrite. Replay: 856 trials (35.7/h), 459 passed (54%); top
  failures: out-of-sample growth not above zero (94), not above −0.05%/block (94), too few closed
  trades (70).
- **The lab.** See blocker 7. Cost per evaluated candidate $0.0006; per replay+holdout pass ~$0.05;
  one seat in 5.7 h.
- **Repairs.** 1,824 `repair.reported`: missing_data 1,415 (78%), order_refusal 207 ("market orders
  outside regular hours" 80, "below the venue minimum" 41), strategy_defect 112, bug_report 64,
  ci_failure 13, audit_veto 13. The engineer answers strategy defects only.

Per-source scorecard:

| source (window) | $ | candidates | replay passes | seats | rung 2 | positive forward | $/pass | $/seat | $/positive |
|---|---|---|---|---|---|---|---|---|---|
| lab (5.7 h) | 0.97 | 1,580 evaluated | 21 (+14 rationed) | 1 | 0 | 0 | 0.05 | 0.97 | — |
| foundry (lifetime) | 8.48 | 108 cards | 33 | 27 | 2 | 7 | 0.26 | 0.31 | 1.21 |
| research (24 h) | 64.71 | 428 strategies | 194 | rewrites keep their seat | — | 40 of 107 | 0.33 | — | 1.62 |
| engineer repairs | 11.20 | 16 born | 9 | 9 | 0 | 0 | 1.24 | 1.24 | — |
| architect designs | 45.53 | 9 PRs | 6 | 6 | 0 | 1 | 7.6 | 7.6 | 45.5 |
| House mutations | replay time | 327 | 78 | 70 | 5 | 21 | ~0 | ~0 | ~0, at 274 displacements |
| teacher, operator, designer, toolsmith, consultant | 78.5 | 0 strategies | — | — | — | — | — | — | — |

Buy more of the lab and the foundry (on Luna, pointed away from Kalshi crypto: blocker 5); buy
less of architect designs, consults, operator/designer/toolsmith and the teacher's 4 h cadence.
Research's binding constraint is inputs, not sessions (52% gate skips, 14% candidate rate).

### L5. 24/7 coverage (analyst C: `C-1.py`, `C-2.py`, `C-3.py`, `C-7.py`, `C-11.py`, `C-13.py`, `C-16.py`, `C-17.py`, `C-18.py`, `C-19.py`, `C-20.py`)

The hour × desk table for the 48 h to the snapshot is in `queries/2026-09-23/out/C-1.txt`
(classes: T fills, R refused, I intents without a fill, O offered and no intent, N woke into a shut
session, Z alive but no wake). Hours by class, of 48:

| desk | T | R | I | O | N | Z | wakes | intents | fills | refused |
|---|---|---|---|---|---|---|---|---|---|---|
| kalshi-crypto-strikes | 7 | 0 | 5 | 2 | 0 | 34 | 209 | 32 | 15 | 0 |
| kalshi-crypto-15m | 22 | 1 | 0 | 6 | 0 | 19 | 1,277 | 174 | 67 (8 real) | 19 |
| kalshi-weather | 36 | 0 | 4 | 2 | 0 | 6 | 254 | 196 | 74 (23 real) | 5 |
| kalshi-sports | 31 | 0 | 4 | 6 | 0 | 7 | 735 | 239 | 140 (3 real) | 0 |
| kalshi-sports-props | 2 | 0 | 22 | 14 | 2 | 8 | 218 | 139 | 6 | 0 |
| kalshi-prices | 15 | 11 | 13 | 3 | 0 | 6 | 195 | 179 | 52 (3 real) | 34 |
| kalshi-attention | 0 | 0 | 0 | 36 | 1 | 11 | 67 | 0 | 0 | 0 |
| alpaca-crypto-majors | 6 | 0 | 2 | 5 | 0 | 35 | 589 | 23 | 18 | 2 |
| alpaca-crypto-alts | 35 | 7 | 4 | 0 | 0 | 1 | 622 | 1,130 | 292 (2 real) | 545 |
| alpaca-index-etfs | 4 | 7 | 0 | 5 | 17 | 15 | 1,390 | 615 | 39 | 576 |
| alpaca-megacaps | 5 | 2 | 0 | 2 | 20 | 19 | 650 | 48 | 45 | 3 |
| alpaca-options | 9 | 13 | 3 | 2 | 21 | 0 | 514 | 356 | 42 | 314 |
| kalshi-open, alpaca-open | 0 members, 0 wakes, 0 births | | | | | | | | | |

- Uncovered by the strict definition (an open market got no attention): the whole-floor wake hole
  (blocker 8); hilibrand and rosenfeld with no trading member for 34-35 h (blocker 3); 36.8% of
  agent-hours inactive; kalshi-attention 0 intents in 48 h; kalshi-sports-props 22 hours intent-only
  (resting bids at the venue minimum that never fill: 6 fills from 555 orders).
- Refusals in 48 h, 1,498, by whose action: House 576 wind-down market exits + 607 dead-agent "no
  seat" (none after the `_wind_down` seat fix); agents 125 option market orders (gone since #189),
  64 + 2 self-cross ("could trade against the House's own resting order"), 43 below the $1 minimum,
  39 horizon rule (prices 34), 14 caps, 3 daily-loss (U1).
- Kalshi series that trade around the clock (hours of the UTC day with an order): KXRAIN 24,
  KXBTC15M 24, KXMLBTOTAL 24, KXBTCD 23, KXWTI 23, KXETH15M 23, KXXRP15M 23, KXSOL15M 23, KXDOGE15M
  23, KXWNBAGAME 23; evening-only: KXNFLGAME 11, KXSERIEAGAME 8, KXLIGAMXGAME 12. Shards: crypto and
  commodities on shard 2, MLB/WNBA/tennis on shard 3, everything else on shard 0; the League has no
  shard-funding code (`grep shard league/*.py` is empty) and the 2 real `insufficient_shard_balance`
  rejects at 12:58Z were on shard 3: U2 (Wave 0).
- Alpaca today after #189/#190 (13:30-16:28Z, practice): index-etfs 218 wakes → 22 intents → 22
  fills; megacaps 161 → 43 → 43; options 71 → 16 → 21; zero refusals (the previous day: 1,082 → 607
  → 576 refused on the ETF desk). Caveat: 8 of the 22 ETF intents were the House closing dead
  accounts and 6 were scheduled exits at the open; the new entries came from mcentee-h4054c4 (14
  round trips of a 45-minute momentum rule), three scholes lines and six krasker single-contract
  puts and calls at $0.09-$0.74.
- The open desks: the daily survey found 161 series beyond the desks' lists and every one matched
  a desk pattern, so `kalshi-open` owns no series by construction; its discovery list (24 series) is
  rates and slow numbers (KXSOFRD, KXUST2AD, KXUST10AD, KX30YMORTW, KXTXERCOTPEAKD), hourly
  temperature, NFL props the props desk misses, MLB innings, MLS, YouTube, KXTRUEV. A
  published-number margin-of-safety program there needs authoritative point-in-time hosts
  (`newyorkfed.org` SOFR, `home.treasury.gov` par yields, Freddie Mac PMMS, `ercot.com`): an owner
  egress step.

### L6. Compute economics (analyst A: `A-2.py`, `A-2b.py`, `A-8.py`, `A-8b.py`)

- Spend per hour: OpenAI $5.43/h over 24 h, $4.93/h over 6 h (Luna research $1.47 → $2.50/h;
  Merton $2.53/h: architect $0.81, engineer $0.45, consultant $0.33, teacher $0.33, foundry $0.32,
  toolsmith $0.15, operator $0.11, designer $0.04; audits $0.05/h; lab LLM $0.16/h while it ran).
  Sail research $1.22/h ($0.54/h in the last 6 h); the Sail balance fell $31.90 in 24 h (box and lab
  time ~$2.6/day). Total about $6.7/h ($160/day) at the 24 h rate. Commitments reconcile against
  the ledger within cents from 01:00Z Sept 23 (`A-2b.out`).
- Per unit: $0.070 per agent-hour ($1.68 per agent-day) across 96 agents, 21 of which never traded
  and 54 of which have W_paper < 1; $0.017 per research session; $0.0013 of box time per replay
  (the research behind it is the cost: $0.14 per pass); $0.0006 per lab candidate; ~$0.05 per lab
  graduate; $0.31 per foundry-born agent; $0.70 per engineer-born; $7.6 per architect-born.
  Internal credits, for contrast: epoch payouts hand the agents $11.5-12.7 an hour ($280/day);
  performance fees on real profit total $0.92 lifetime.
- Runway: gateway month $367.66 of $408 at 16:25Z ($40.34 left): the $20 earned line at about
  20:35Z, $8 at about 23:00Z, zero at about 00:40Z Sept 24; the House line $34.92 at zero about
  23:30Z; the month resets Oct 1. Sail $96.38 at $32.32/day: 3.0 days (about 16:00Z Sept 26). Jev
  $16.15 of $42.
- Break-even: real equity $1,017.36 → $1,015.00 in 3.8 days (−$2.36 marked, $1.14 fees; +$2.15
  realized on Kalshi, −$0.51 Alpaca). 9 agents ever on rung 2, 123.4 real agent-hours: +$0.013
  realized per real agent-hour (−$0.019 marked). Practice loses about $500/day on $19,200 of
  practice stakes. Compute $160/day against +$0.4/day: 400:1. At the one measured edge (favourites
  maker: +2.15c a contract at ~$0.95, 2.3% per settle; mullins-2's +$4.89 on $232 of notional is
  2.1%), break-even needs about $7,600 of settled notional a day, or compute under $4/day for the
  $60-100 of notional the floor runs. Every $1 of daily compute needs $50 of daily settled notional
  behind a proven line.
- Pacing by evidence per dollar: keep the lab and the foundry (on Luna); Luna research at a reduced
  rate with `missing_data` blocking the spend; cut architect designs, consults, the teacher's
  cadence (4 h → 12 h), toolsmith, operator/designer ($1.6/h together, a third of the burn, 0 rung-2
  agents); the engineer only for `strategy_defect` keys with a living, trading parent.

### L7. What the agents say and ask for (analyst C: `C-4.py`, `C-5.py`, `C-8.py`, `C-9.py`, `C-10.py`, `C-12.py`, `C-14.py`, `C-15.py`)

- The sample: 84 journals across 12 desks, rungs 0-2 and every founder class, 30 abstention
  summaries, 18 lab submissions, all 21 audit verdicts, the winners' and losers' latest texts:
  150+ items. Journals are `agent.research` rows with `tool='journal'` (`researcher.py:727-731`).
- Why sessions abstain: 6,800 of 7,532 (90.3%) since Sept 22 00:00Z ended with no candidate and no
  trial: rung 0 95.5%, rung 1 87.8%, rung 2 93.7%; by desk attention 98.2%, weather 98.1%, majors
  95.7%, alts 94.7%, strikes 94.0%, prices 93.4%, sports 90.7%, 15m 90.4%, props 84.5%, megacaps
  83.7%, options 80.7%, index-ETFs 77.2%. Keyword classes over-count "rules" and "budget" (every
  summary recites the bunt line and its balance); a hand classification of the 30 most recent:
  nothing changed since the last pass / waiting for settlements 14 of 29 (48%); no data 5 (17%); no
  idea or family measured dead 4 (14%); rules, sizing, capacity 4 (14%); closed market 2; missing
  control (cannot pause or verify a deployment) 2. The winners abstain because they are
  capacity-bound, not idea-bound (mullins-2: "$1.30 cash, $9.88 equity ... little capacity to
  deploy"; mullins-6: "$0 cash, four open positions").
- The gate (`research_gate.py:417-439`): 3,155 runs since Sept 22 (`trigger` 1,740,
  `backoff_elapsed` 754, `clock` 532, `jev_relevant_note` 129) against 5,300 skips (`backoff`
  3,407, `blocked:missing_data` 744, `blocked:market_closed` 143).
- Stated edge vs the record: the one stated edge that shows up in the real record is the weather
  NO favourite (mullins-2 10 settles +$4.89, mullins-6 2 +$1.00), and its two holders are the two
  agents that cannot deploy. huang-h427345's own line falsified its thesis (J13) before its real
  loss; haghani-37: "the maker-reversion replay is negative"; hawkins-19: "no point-in-time fixing
  feed"; meriwether-h2d625d's sibling: "structurally −EV, 6/6 underwater". The practice bottom is
  all options long premium (five krasker lines, −$10 to −$15) and alt reversion; the shadow bottom
  the crypto-strike favourite makers (hilibrand −$18.20 on 20, hilibrand-2 −$14.10 on 59).
- What agents say about the game (25,465 texts since Sept 21): seats / league full 734 texts (301
  agents); sizing, minimum, caps 555 (95); fees 407 (118); the horizon rule 1,254 (140); missing
  tool or data 1,845 (237); "the House should / the rule is wrong" 20 (13). The design requests in
  their words: cannot stop a losing strategy from research; cannot size down below the gate; cannot
  rewrite in place (a child must clear a bar the family cannot reach); the horizon rule is wrong for
  bin-skipping configs (34 refusals on kalshi-prices, `book.py:1050`); the daily-loss lock blocks a
  real bunt's entries (U1); replay cannot tell "no orders" from "never filled"; self-cross refusals
  wall off exits (64 + 2); capacity for the winners.
- Requests: see blocker 10.

## 4. What the study could not answer

- **Does E at promotion predict real results?** n = 10 promotions, 6 with a settled real trade. Thirty
  promotions with 5+ real trades each would answer it; the widened money set will produce them
  faster if the seats follow.
- **Whether the favourites edge survives at size.** 12 of 12 real settlements and 26 of 26 practice
  settlements for the family, all at $5-10 positions; fill rate 44% real. Twenty settlements at $30
  stakes and 14% positions would show the miss rate and the fill rate at size.
- **A per-class Alpaca haircut.** 2 real crypto fills, 0 equity, 0 option; the table needs 30 of a
  class. Only real fills answer it; A7 makes them possible.
- **Whether the House's exits or the horizon rule change agents' results.** The House's exits are
  0-4% of the loss; the horizon rule's 39 refusals are on the record but their counterfactual is not.
- **The "61 of 96 never traded" figure** in the plan: the ledger reproduces 21 of 96 by fills and 17
  by intents; the plan's count needs the program-level tag the ledger does not carry.
- **The time-of-day edge:** n < 20 per hour and a handful of binary settlements flip the sign.
- **What a lesson does.** The teacher's 27 lessons are read (323 `playbook_read` calls a day) and no
  downstream effect is measurable; a lesson id carried on `agent.strategy` would make it so.
- **The lab's LLM children's quality:** none has been evaluated, so their yield is unknown.
- **The box's research transcripts** (`research.sqlite`, 1.6 GB) were not read beyond the journals
  and summaries in the ledger; the classification of abstentions rests on 30 hand-read items.

## 5. Method

- **The snapshot.** `ledger.sqlite` (333,668 rows, 2026-09-19T21:13Z to 2026-09-23T16:28Z),
  `lab.sqlite` and `campaigns.sqlite`, backed up on the House box with sqlite's backup API at 16:28Z
  and queried in the session scratchpad. Two queries (C-18, C-19) read `house.json` on the box,
  read-only. The code is `origin/main` at `cd1b0dc`. Nothing touched the gateway, the venues or the
  site.
- **Windows.** "24 h" is Sept 22 16:28Z to Sept 23 16:28Z; "6 h" is 10:28Z to 16:28Z; A is since
  Sept 22 13:30Z (27 h); C since the allocator, Sept 23 08:28Z; D today 06:30-16:00Z (the plan's
  numbers); L5 uses the 48 h to the snapshot; L7 uses texts since Sept 21 or Sept 22 00:00Z as
  stated.
- **Books.** `alpaca-paper` and `kalshi-shadow` are practice; `alpaca` and `kalshi` are real. Fills
  exclude the House's own (`source='dust'` sweeps and "the House is closing this account" exits:
  420 rows on alpaca-paper, 9 on real books). Alpaca P&L is the sell fill's `realized`; Kalshi P&L
  is `book.settle.pnl`.
- **Definitions** (`league/allocator.py`, `league/constitution.py` `allocator`). `W_paper`: the
  agent's wealth multiple on its practice book, stakes lent or returned taken out, less
  `alpaca_paper_haircut_bps` 10 a side on Alpaca practice. `W_real`: the same on its real book since
  its first real dollar. `E = W_paper^0.5 × W_real` (`paper_weight` 0.5). Bands: practice (rungs 0
  and 1) → bunt (rung 2: E ≥ `bunt_at` 1.01 on `bunt_min_trades` 5 closed trades, or
  `bunt_min_settled` 3 settlements on an event book; stake `bunt_usd`, after Deploy A `bunt_usd ×
  clamp(W_real, 1, swing_at)`) → swing (rung 3: E ≥ `swing_at`, W_real ≥ 1, `swing_min_real_trades`
  8; stake `bunt_usd × min(E, e_cap)^kappa` up to `max_share_of_venue` 0.6) → star. Down: hysteresis
  (a bunt leaves below `bunt_at` × 0.85 = 0.8585; a swing below `swing_at` × 0.85 or W_real < 0.9),
  `real_drawdown_demote` 0.35 from the real high-water mark, `die_below` 0.80 on 10 trades. A
  "block" is the evaluator's `eval.block` (hour blocks on hour-horizon desks, day blocks on weather,
  sports and options); "LG" is log growth over active blocks.
- **Founder classes** from `agent.born` `founder`/`reason` and `agent.forked`: seed, house-mutation
  (`house.py:4313`), agent-fork, foundry (`card:*`), architect and repair (`enroll()` births of
  merged PRs), house-revival, lab.
- **Queries.** `queries/2026-09-23/A-*.py`, `B-*.py` (B-1 to B-11 import `B-0.py`), `C-*.py`, with
  their raw outputs beside them and under `out/`. They point at the scratchpad snapshot path
  (`SNAP` in `B-0.py`; the same literal in the others); re-point that path at a snapshot to re-run.
- **Rules kept.** Numbers over adjectives; "practice" for the site; no forced trade, no promotion
  line lowered without forward evidence, no verifier loosened; owner steps named as such (the
  hysteresis or position-share decision, four data hosts, the Sail top-up).

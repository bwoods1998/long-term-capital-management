# LTCM ten-hour run: learn what blocks the north star, then unblock it

A ten-hour autonomous run, planned for the owner's working day on Sept 23, 2026. It starts at about
16:00 UTC (9 AM Pacific), so the first four hours are the US stock and options session.

- **Purpose:** study the agents while every venue and every security is trading, and find what
  stands between today's floor and the north star.
- **Then:** unblock those things boldly, fix every bug that turns up, and leave the docs and the
  repo current and clean.

## The owner's direction

The owner, Sept 23, 2026, at about 16:00 UTC:

> "make this 10 hour run about learning as much as possible about our agents and whats blocking
> exponentially profitable 24:7 recursively self improving trading agent swarm and unblocking those
> things, fixing any bugs observed, being bold and ambitious and not afraid to take risks both in
> our approach and the agents (im fine with volatility and lose on my portfolio to achieve the north
> star goal), and keeping all docs and repo up to date and clean free of any unneeded clutter"

**The north star:** a swarm of trading agents that is exponentially profitable, trades 24/7 on
real money (Kalshi and Alpaca), and improves itself recursively. Winners compound capital and
compute, losers die, and the swarm writes, tests and breeds its own strategies.

## Where the floor stands at plan time (15:57 UTC)

Measured with `python3 scripts/floor_watch.py`. The record of the build that got here is
[`docs/runs/2026-09-23-capital-ladder.md`](../runs/2026-09-23-capital-ladder.md).

- **Release:** `20260923T152910Z-9a5970c56aca` (Deploy 7, main `da846db`).
  - The grant `earned-live-20260921` is active on money digest `44e8d48d`.
  - The allocator, the capital board, sliced exits, the Alpha Lab, a tick that never blocks and
    the open desks are all live.
- **Real money is barely used.**
  - The envelope is $1,017.75: Kalshi $517.75 and Alpaca $500.
  - At work: Kalshi $98.64 in 5 bunts ($10-$56 stakes). Alpaca has nothing.
  - Since 06:30 UTC there have been 10 real Kalshi fills (+$0.53 realized) and 2 Alpaca fills
    (−$0.51).
  - Nobody has swung: a swing needs 8 real trades, and the best agent has 4.
- **Winners cannot compound.**
  - `target_stake` (`league/allocator.py`) gives every bunt a flat `bunt_usd`.
  - `_size` withdraws equity more than 10% above that as free cash. The floor's only real
    earners, mullins-2 and mullins-6, were shrunk from $60 toward $10 this way.
  - A Kalshi swing at E 1.5 is only $15.
- **The agents have no demonstrated edge.**
  - Practice P&L between 06:30 and 16:00 UTC was −$94.05 on Alpaca (40 agents) and −$203.69 on
    Kalshi (28 agents). These are realized figures from `floor_watch`, and they include the
    House closing dead agents' positions. The study separates the two.
  - Stock desks barely trade: 1,092 wakes produced 24 intents on the ETF desk, measured from
    Sept 22 13:30Z to about 14:00Z today.
  - 61 of 96 residents have never traded.
  - Lab programs pass replay and the sealed holdout, and the teacher has already recorded one
    family (the ETH prior-window fade) whose forward record is negative.
  - The loop produces strategies faster than it produces evidence that any of them work.
- **Stocks and options:** fixes #189 and #190 went live at 15:30 UTC and have not seen a market
  session yet.
  - Level-3 multi-leg options are not built. The read-only investigation is
    [the Alpaca stocks and level-3 options proposal](../proposals/2026-09-23-alpaca-stocks-and-level-3-options.md).
- **The self-improvement loop stops at about T+4.5 h unless something changes.**
  - OpenAI's gateway month is at $365.85 of the funded $408 cap ($42.15 left); the House line
    has $36.59. At about $5 an hour the month falls under `frontier_reserve.earned_usd` ($20,
    `league/game.json`) at about 20:30Z, just after the US close.
  - From then the frontier tier is "earned". The teacher, operator and designer pause, and
    cheap-model research moves to Sail.
  - **The whole Alpha Lab stops as well.** `Lab.open()` (`league/lab.py`) refuses every tier
    below "all", although its parameter children, batch replay and graduation spend no
    OpenAI.
  - Under $8 (`code_roles_usd`, about T+6.8 h) only audits and earned consultations remain.
  - The month resets on Oct 1.
  - Sail is at $96.81, about 2.6 days at $32.93 a day. Jev is at $16.16 of its $42 cap.
- **Known open items,** from the capital-ladder report:
  - **The daily-loss freeze.** The book's 10% per-desk daily-loss rule freezes a $10 bunt after
    one small loss.
  - **Kalshi shards.** The League never funds exchange shards. Shard 3 (MLB, WNBA, tennis) was
    funded by hand with $30, and shard 2 (crypto, commodities) holds about $39.
  - **Graduates wait for seats.** 16 lab candidates have passed the House replay and are waiting
    (1 born). The league is at its population cap of 96 (`league/turbo.json` `max_population`),
    and the graduates' desks are full (`league/niches.json` seats).
  - **Holdout rationing** has refused 11 graduations. 1,521 candidates have been evaluated.
  - **The open desks have no members,** and `kalshi-open` lists no `maker_fee_series`. Its
    replay treats maker fills as free, though 163 of its 195 series charge makers.

## What "closer to the north star" means by the deadline

1. **We know why the swarm is not profitable, with numbers.**
   - The agent study (L) is published.
   - It gives a ranked list of the blockers, each with its evidence and expected impact.
2. **The biggest blockers are unblocked.** Each is live on the running release and verified in
   its window (see "When each change can be verified"), or scheduled for a named later window,
   or has a written reason with numbers.
3. **More real money is at work, honestly.**
   - Winners keep what they make, and stakes grow with evidence.
   - At least one agent is on real money at each venue, or the exact reason there is not.
4. **The loop learns from forward results**, not only from replay, and the lab and every other
   part of the loop that spends no OpenAI keep running whatever the OpenAI tier.
5. **Compute lasts the run and follows yield.**
6. **Every bug observed is fixed,** and where the floor did not notice it itself, an invariant now
   does.
7. **Docs and repo are current and clean.** Stale worktrees, branches, PRs and dead docs are
   removed, with unmerged work preserved on GitHub.

## Principles

1. **Learn while you build.**
   - The blockers the last run already measured start building at T0: the daily-loss freeze,
     Kalshi shard funding, compounding bunts, the lab's OpenAI gate, fractional stock limits and
     the `kalshi-open` maker fees.
   - The study decides everything after them, and may reorder Waves 1 and 2.
2. **Evidence stays honest.**
   - Practice fills stay conservative, and the sealed holdout stays sealed.
   - No agent grades its own work.
   - No trade is forced, and no evidence is fabricated.
3. **Bold is allowed; blind is not.**
   - The owner accepts volatility and losses inside the envelope.
   - Money rules may move within the closed table below. Each change is recorded with the
     evidence behind it, and re-ratified.
   - A bolder rule is fine. A rule changed only to make tonight look busy is not.
4. **We design the environment and the agents find the alpha.** Do not hand agents strategies.
   Give them resources, verifiers, feedback and incentives.
5. **The envelope, the gateway and the throttle are the whole risk budget.**
   - The envelope: $517.75 Kalshi and $500 Alpaca.
   - The gateway: the $75 order cap, day caps and kill switch.
   - The throttle.
   - No leverage and no shorts.

## Clock, budget, authority

**The clock.** The first action writes T0 (`date -u`) and the deadline T0 + 10 h into the run
record `docs/runs/2026-09-23-learn-and-unblock.md`, and commits it. A context reset does not
restart the clock.

**The first hour's decisions.** Each is recorded in the run record by T+0:45.

1. **Can this session ratify and move shard collateral without the owner?**
   - At T0, from `~/Work/ltcm-deploy`, run `python3 scripts/live_trading.py --ratify
     earned-live-20260921` against the running digest. With the policy unchanged it writes
     nothing.
   - Also move $1 from shard 0 to shard 3 with `python3 scripts/kalshi_shard.py transfer --usd 1
     --to 3`.
   - If the permission check blocks the ratify, no deploy in this run may change the money
     digest: a promotion without a ratify leaves real trading off until the owner is back.
     Money-rule changes then wait on a pushed branch, with the owner's commands written into the
     report.
   - If the permission check blocks the transfer, U2 goes first in Wave 0.
2. **Compute.**
   - Send the owner one push notification, then carry on without waiting. It says that the
     gateway month hits the $20 reserve at about T+4.5 h and resets on Oct 1, and that Sail has
     about 2.6 days. It asks for an OpenAI top-up and Sail auto-recharge.
   - Set the pacing by T+0:30 (C below).
3. **Deploy A's money set is fixed by T+0:45**, from evidence already on record:
   - the 12:21Z daily-loss freeze of huang-h51fdd3-2;
   - the shard refusals at 12:58Z and 13:30Z;
   - mullins-2 and mullins-6 shrunk while earning.

   That is one digest change and one ratify. The study may justify one more digest change, on
   Deploy B or C, and never a third.
4. **Each protected file has one owner per wave.**
   - In each wave, one builder each for `book.py`, `allocator.py`, `lab.py` and `constitution.py`;
     other changes to those files queue for the next wave.
   - Run at most four builders at once.
   - Each builder runs its own tests; CI runs the full suite. `test_ladder` times out locally
     under load.
5. **The study reads a snapshot, not the live box.**
   - Copy `ledger.sqlite`, `lab.sqlite` and `campaigns.sqlite` from `/workspace/state` once, with
     sqlite's read-only backup, and query the copies.
   - Refresh at T+4:15 and T+7:30.
   - The House box has 1 vCPU and a 56-110 s tick.

**Budget.**
- **Funded** means a balance read at T0 or later from the provider (OpenAI billing, Sail usage,
  Jev), or one the owner states in this session. It never means a figure from a House, agent or
  builder message.
- If credit arrives, align the gateway's `FRONTIER_MONTH_USD`, `FRONTIER_MONTH_MAX_USD` and
  `TYPESAFE_PILOT_USD` and the House's line (`scripts/campaign_topup.py`) up to it, never above.
- **Floors that must hold at the deadline:**
  - OpenAI keeps at least $8 in the gateway month, so a bunt promoted late is still audited.
  - Sail keeps at least 1.5 days of runway at the burn then measured, plus the House's
    `sail_reserve_usd`.
- **Not the run's to do:** Sail auto-recharge, buying credit, payment methods. These are owner
  decisions. The run may create at most one more Sailbox, and only if the floors hold.

**Authorized:**
- Implement, test, commit, push, open and merge PRs to `main` of this repo and of `personal-site`,
  with CI green. Builders work in their own worktrees, and the main session merges.
- Change the money rules in the closed table below, and re-ratify `earned-live-20260921` within a
  minute of each promotion that changes the digest.
- Change the risk-free rules on recorded evidence, with no re-ratification. They are not in the
  money digest:
  - `ladder.replay`, `ladder.paper_death`;
  - `league/turbo.json` (population up to 128, only while Sail's runway stays over 1.5 days);
  - `league/game.json`, `league/niches.json` seats;
  - the operating dials in `league/config.json`.
- Deploy:
  - owner deploys (`scripts/floor_box.py deploy` from `~/Work/ltcm-deploy`);
  - gateway deploys (`npx wrangler deploy --tag <sha>`);
  - site deploys.

  Each needs its tests green.
- Trade real money on Kalshi and Alpaca inside the envelope, with volatility and losses accepted.
- Move collateral between Kalshi exchange shards of the same account with
  `scripts/kalshi_shard.py`, recording each move, until U2 is live. This is the gateway's one
  allowed funds move, and money never leaves the account.
- Spend funded compute, and align caps up to funded balances.
- Stop in an emergency, then record why and tell the owner in the session at once. Any of these:
  - `python3 scripts/gateway_admin.py kill`;
  - the House rollback (`league.watchdog rollback`);
  - `npx wrangler rollback` in `gateway/`;
  - `allocator.enabled: False` with an owner deploy and a re-ratify.
- Tidy the repos under the rules in H.

**Money-rule bounds for this run.** Each change needs its evidence written down first.

- **The table is the whole list.** Every other money rule stays exactly as it is:
  - `order_caps`;
  - `allocator.throttle` (−0.30 / −0.15) and `profit_indexed_envelope`;
  - `max_share_of_venue` 0.6, `position_share` 0.5, `e_cap`, `swing_min_w_real`;
  - `hysteresis`, `real_drawdown_demote` 0.35, `die_below`;
  - `evidence.paper_weight` 0.5, `performance_fee_share`;
  - `tuition`, `rungs`, `ladder.death`, `ladder.micro_demotion`, `ladder.drift`;
  - `book.DEFAULT_RULES` `max_position_pct`, `max_order_notional_pct` (0.50) and
    `max_limit_deviation_pct`.
- **New constitution keys** are allowed only to carry a row of this table.
- **This table overrides the proposal's §4 line** against lowering `bunt_at` and
  `bunt_min_trades`, on the owner's direction. A lowering still needs the study's evidence that
  agents just under the line make money forward, not just that more agents would qualify.

| Rule | Now | Allowed range | Notes |
|---|---|---|---|
| `allocator.bunt_usd` | Kalshi $10, Alpaca $25 | Kalshi $10-$30, Alpaca $25-$60; an options bunt up to $80 (proposal A2a) | Raising bunts lowers the grant's real-money seats (`max_agents` = floor($1,017.75 ÷ smallest bunt)). |
| Bunt stake growth (new, U5) | flat `bunt_usd`; equity more than 10% above it is swept each pass | `bunt_usd × clamp(W_real, 1, swing_at)` | Losses still shrink by free cash only; the envelope's headroom bounds every increase. |
| `allocator.kappa` | 1 | 1-2 | Swing stake = `bunt_usd × E^kappa`. |
| `allocator.bunt_at` | 1.01 | 1.005-1.05 | |
| `allocator.bunt_min_trades` / `allocator.bunt_min_settled` | 5 / 3 | 3-5 / 2-3 | |
| `allocator.swing_at` | 1.5 | 1.25-1.5 | |
| `allocator.swing_min_real_trades` | 8 | 5-8 | |
| A real-money bunt's daily-loss rule (`book.DEFAULT_RULES` `max_daily_loss_pct` 0.10, per desk) | 10% of the stake a day | For real-money bunts only, replaced by the allocator's stay drawdown (`real_drawdown_demote` 0.35, unchanged). Swings keep the book's 10%. | Authority: the owner's words at 16:00Z ("im fine with volatility and lose on my portfolio"). Record them as the basis. |
| Real-book daily-loss halt (`book.DEFAULT_RULES` `floor_max_daily_loss_pct` 0.08) | 8% of the staked accounts' sum | 8% of that venue's grant capital, per venue: at most $41.42 on Kalshi and $40.00 on Alpaca | Never 8% of the combined $1,017.75 applied to one venue. |
| `allocator.evidence.alpaca_paper_haircut_bps` | 10 bps a side on Alpaca practice (every class); Kalshi practice has none | per asset class, each from at least 30 measured fills of that class, never below 2 bps a side | |

**How the two daily-loss rules must change.**
- Both rules live in `league/book.py`. That file is in `ci.FORBIDDEN`, so only an owner deploy can
  change it, but it is outside the money digest.
- A `book.py`-only change would move no digest and record no ratification. So make each rule a
  constitution key that `book.py` reads, for example:
  - `allocator.bunt_daily_loss: "stay_drawdown"`;
  - `allocator.real_halt: {"basis": "venue_grant_capital", "pct": "0.08"}`.
- The digest then moves, and the grant is re-ratified on it. Do not edit the numbers in
  `book.DEFAULT_RULES`.

**Not authorized:**
- Deposits, withdrawals, or transfers between venues. The only funds move is between Kalshi
  exchange shards of the same account.
- Enlarging the grant:
  - no `live_trading.py --enable`;
  - no new grant;
  - no change to `venue_capital_usd`.

  The only grant command is `python3 scripts/live_trading.py --ratify earned-live-20260921`.
- Raising any cap above funded money, or changing the order and day caps (the gateway's
  `MAX_ORDER_USD*` $75 and `MAX_DAY_USD`; the constitution's `order_caps`).
- Disabling the kill switch, the gateway caps or the throttle.
  - `scripts/gateway_admin.py unkill` and `provision` belong to the owner.
  - The one exception: the run may release a kill it engaged itself, once the cause is fixed and
    verified.
- Widening the gateway's `VENUE_PATHS` allow-list (`gateway/lib/caps.mjs`), or weakening #187's
  refusal of multi-leg, symbol-less, stop and adjusted-option orders.
- Touching secrets or venue accounts:
  - no `wrangler secret put`, `scripts/place_secrets.sh`, edits to the box's `.env`, or venue API
    keys;
  - no Alpaca or Kalshi account setting (margin multiplier, shorting, options level, PDT).

  Record anything needed as an owner step.
- Leverage, shorting, or writing options on any account.
- Multi-leg option orders on either account, practice included (see O).
- A real-money order that no agent's own intent produced, including a "test" order. A manual order
  on the practice account also freezes every Alpaca practice agent until the book adopts it, so
  make none.
- Running two Houses on one practice account.
- Committing secrets.
- Forcing trades, planting intents, or having the House trade for an agent.
- Fabricating or back-filling evidence, or hand-editing the ledger, the books, the lab database,
  holdout budgets or the history store on the box. State changes go through House code.
- Loosening a sealed verifier: the holdout seal and its per-lineage budget, deep replay, the
  auditor, or the practice fill model. The haircut row above is the only exception.
- Deleting unmerged or uncommitted work that has not been pushed.

## The day's schedule (UTC; T0 ≈ 16:00)

| Window | UTC | What the run does |
|---|---|---|
| T0-T+0:20 | 16:00-16:20 | T0, baseline and the first hour's decisions. Start the watch loop and take the study's snapshot. Launch the study (L), **Wave 0**, and the cleanup agent (H) together. |
| T+0:20-2:15 | 16:20-18:15 | **Wave 0** builds, then is reviewed and fixed: U1, U2, U5, C2, A7 (with the wind-down held until the open), V1. Study v1 lands at T+1:30 and ranks the blockers by T+1:45. **Wave 1** launches from it. |
| T+2:15-2:45 | 18:15-18:45 | **Deploy A:** an owner deploy of Wave 0's integration branch, re-ratified within a minute if the digest changed. It is the last deploy that can be verified in today's stock session. |
| T+2:45-4:15 | 18:45-20:15 | Watch stocks and options on Deploy A every 30 minutes until the 20:00Z close. The study's stock-session appendix follows at T+4:15. |
| T+4:15-5:00 | 20:15-21:00 | **Deploy B** (Wave 1). **Wave 2** launches from the refreshed study. |
| T+5:00-7:30 | 21:00-23:30 | Wave 2 builds. The watch's fixes in unprotected files ship through the updater. U2 must be live before the evening sports, about 23:00Z. |
| T+7:30-8:00 | 23:30-00:00 | **Deploy C** (Wave 2), the last planned owner deploy. |
| T+8:00-10:00 | 00:00-02:00 | At least 90 minutes of watching, fixing and redeploying (only for a rollback or a money-path defect), then docs, memory and the report. |

- **At most three owner deploys.** Each restart empties the lab's tape cache, which costs 30-60
  minutes of lab throughput. A builder that misses its wave's cut rides the next wave.
- **A build cycle is about two hours.** Builder launch to merge took 1 h 40 min to 2 h on Sept 23,
  including an adversarial review and a fix pass. Then CI takes about 7 minutes, and the canary
  and watch about 15 more.
- **The stock-session cut-off.** Anything that needs a stock or options session and misses Deploy
  A is recorded as "to verify at the Sept 24 open (13:30Z)". It is not rushed.

## Workstreams, in priority order

### L. The agent study (T0-T+1:30, refreshed at T+4:15 and T+7:30)

- **Method:** parallel read-only analysts over the snapshot, the books and the code. Each finding
  carries numbers and a query that reproduces it.
- **Output:** `docs/research/2026-09-23-agent-study.md`, linked from the run record.

1. **The funnel.**
   - Stages: birth → replay → practice → bunt → swing, by desk, family and founder (House,
     foundry card, lab, repair, architect).
   - Measure: time spent at each stage, the causes of death, and where agents stall.
2. **Where money is made and lost.**
   - Split: practice and real P&L by desk, family, horizon, asset class, time of day, entry type
     and liquidity (maker or taker).
   - Decompose today's practice losses into signal, costs, sizing and the House's exits of dead
     agents.
   - For each real agent: the stake it carries now, the stake it would carry under U5, and how
     many days the swing path takes at today's real trade rates.
3. **Does the verifier predict?**
   - Does replay predict practice? Does practice predict real?
   - Do real fills match practice fills: slippage, fees, rejects?
   - Is E a fair yardstick across venues?
4. **The yield of the loop.**
   - Sources: Merton's roles (architect, teacher, auditor, toolsmith, designer), the researcher,
     the foundry and the lab.
   - For each: what it produced (PRs, strategies, lessons, graduates), what those did going
     forward, and at what compute cost.
5. **24/7 coverage.** Hour by hour, which markets each desk is offered, trades, or cannot trade
   (data gaps, refusals, closed shards, desks that keep hours), across Kalshi series, Alpaca
   stocks, options and crypto.
6. **Compute economics.**
   - Cost per agent-hour, per research session, per replay and per graduate, against the evidence
     each produced.
   - The runway, and what a profit-indexed swarm needs to break even.
7. **What the agents say and ask for.**
   - Read a stratified sample of at least 60 items, across desks, rungs and founders: research
     transcripts, abstentions, journals, lab submissions and audit verdicts.
   - Classify why sessions abstain (82% did on Sept 22): no idea, no data, a missing tool, a
     closed market, or the budget.
   - List the data and tools agents ask for, against what exists and what became of each request.
   - Compare what each winner and loser believes its edge is with its forward record.
   - The most-requested missing inputs go into the blocker list. A new public data host is the
     owner's egress step: name the host and why.

**Output:** the ten biggest blockers to an exponentially profitable, 24/7, self-improving swarm,
ranked by expected impact. Each has its evidence, a proposed unblock, its risk, and the wave it
fits in.

### U. Real money at work

1. **The daily-loss freeze (Wave 0, Deploy A).** Real-money bunts are governed by the allocator's
   stay drawdown instead of the book's 10% rule. The real-book halt is set per venue, through
   constitution keys as described above.
2. **Durable Kalshi shard funding (Wave 0, Deploy A).**
   - The House keeps collateral on every shard its desks trade (today 0, 2 and 3), checked
     hourly, with a floor, a top-up and a keep amount, as in the first run's `ltcm/service.py`
     `_fund_kalshi_shards`.
   - The shards come from the venue's event data (`exchange_index`), not a fixed list.
   - Each move is recorded as an ops alert.
   - **Bounds:**
     - It uses only the gateway's existing `POST portfolio/intra_exchange_instance_transfer`,
       between shards of the one account.
     - At most $100 a move and $200 a day, unless the run record gives a measured reason.
     - Shard 0 is never drawn below the stakes of the desks that trade there.
     - Nothing moves while the kill switch is engaged or the grant is inactive.
   - The mover lives in its own module, added to `ci.FORBIDDEN` as `allocator.py` was.
   - Adversarial review before deploy.
3. **Winners compound (U5; Wave 0, Deploy A).**
   - A bunt's target becomes `bunt_usd × clamp(W_real, 1, swing_at)`, so a bunt keeps what it
     makes.
   - Losses still shrink the stake by free cash only; the 35% stay drawdown and hysteresis still
     demote; the envelope's headroom bounds every increase.
   - **Tests first:**
     - a winning bunt keeps its profit inside the headroom;
     - a losing one is not refilled;
     - the throttle still halves.
   - Then an adversarial review, the owner deploy and the ratify.
4. **Use the envelope (Wave 1 or 2).** From the study's evidence, move `bunt_usd`, `kappa` and
   the swing lines within the table, so agents with evidence carry meaningful stakes.
5. **Alpaca real money.**
   - **Stock bunts (A7, Wave 0, Deploy A):** the proposal's fractional one-day limit orders, and
     wind-down sells held until the open.
     - Verify with the agents' own practice orders after Deploy A, never with a manual order.
     - If it misses Deploy A, it rides Deploy B and is verified at the Sept 24 open.
   - **The options bunt stake (A2a):** a digest change. It either joins Deploy A's money set or
     is the run's one later digest change.
   - **The haircut per asset class (A8):** from measured fills, within the table.

### C. Compute: the loop must not stop at T+4.5 h

1. **Tell the owner at T0** (see the first hour's decisions).
2. **Decouple the lab from the OpenAI tier (Wave 0, Deploy A).**
   - `league/lab.py` is protected; add a test that fails without the fix.
   - At the "earned" and "audits" tiers, the lab keeps seeding, breeding parameter children,
     batch-evaluating on the lab box and graduating.
   - Only its Luna and Sol calls stop, as `_llm_refusal` already enforces. Its Sail line and the
     Sail meter still stop it.
3. **Pace OpenAI by T+0:30.**
   - Aim for the House line ÷ the hours left (about $3.30 an hour), keeping the $8 floor.
   - The auditor and teacher keep their tiers. The architect, toolsmith and designer drop a tier
     or pause. Research runs only for agents with a closed trade, and not for those that keep
     abstaining.
   - Spend what remains where L6 shows the most evidence per dollar.
   - Check the burn every hour, and record every pause and the yield number behind it.
4. **Keep the Sail floor.** If the runway would fall under 1.5 days, stop growth (population,
   research workers) before anything that trades.

### S. The loop learns from forward results

1. **Graduates' seats (Wave 0 or 1, mostly unprotected `house.py`).**
   - A graduate with a positive forward window outranks a resident that has never traded.
   - Population may rise toward 128 (`turbo.json`), with desk seats following where graduates
     wait, within Sail's floor.
   - Lineage holdout rationing gets a documented policy for fresh holdout windows as new data
     arrives. The seal is never loosened.
2. **Forward windows and forward feedback (Wave 1, Deploy B; `lab.py` is protected).**
   - Every hour, re-score every archived elite and every waiting graduate on tape data that
     arrived after its code was frozen. No search and no holdout has seen that window.
   - Forward windows use replay fills. They rank seats and steer search. They never count as
     practice evidence, and never promote anyone to money.
   - Graduates' practice and real results feed their lineage's budget and the archive's fitness.
     A lineage whose forward results lose gets less search.
   - The teacher's lessons become lab priors (for example the prior-window-fade pause).
3. **Compute follows yield.** From L4, give the roles and agents that produce forward evidence
   more turns, and cut the ones that do not.
4. **Lab throughput, only if the study says it binds.**
   - Measure candidates an hour over the last 6 hours first. The last run reached about 1,200 an
     hour.
   - If throughput still binds, build tapes on the 8-vCPU lab box in Wave 2 (Deploy C).

### V. Every venue, every security, every hour

1. **Fix `kalshi-open`'s maker fees before any open-desk birth (Wave 0).** Add a regression test,
   then the fix.
2. **The open desks get members.**
   - Give the lab open-desk archive cells, seeded from programs whose NEEDS reach past one desk.
   - Send a share of foundry calls to the open desks.
3. **List every uncovered hour** from L5, with its reason and a fix or an owner step. An hour is
   uncovered when no desk is offered a tradable market, or when a desk is offered markets and
   its agents never intend.

### O. Level-3 options: a design and a branch, not a deploy

- **Why not a deploy:** the proposal estimates B1 at 1,500-2,500 lines and 3-5 build days, on
  the same protected files as U.
- **No multi-leg order goes to either account in this run, practice included.**
  - The practice book reconciles to the shared practice account.
  - A vertical's sold leg is a negative position, which `_adopt_the_venue` (`league/book.py`)
    refuses to adopt. That would freeze every Alpaca practice agent while the spread is open.
- **The build (Wave 2):** one builder writes B1's design against the code, and builds the pure
  pieces with tests on a pushed, unmerged branch:
  - the maximum-loss arithmetic;
  - one spread counted as one trade;
  - the intent schema.
- **Settling the three unknowns** needs a second Alpaca practice account that no House
  reconciles. Creating it and placing its keys in the gateway is an owner step; list it in the
  report.

### B. Bugs

- **Every defect seen in the study or the watch gets:**
  - a regression test that fails without the fix;
  - the fix;
  - a deploy through the right path: the updater for unprotected files, a wave's owner deploy for
    `ci.FORBIDDEN` paths.
- Money code gets a multi-lens adversarial review before deploy.
- **Make the floor find the next one itself.**
  - For each bug, record whether any floor alert, watchdog check or Merton role noticed it before
    this session did.
  - Where none did, add the cheapest invariant the House or watchdog checks every tick or mark
    pass, raised as an ops alert. Examples:
    - a real order refused with `insufficient_shard_balance`;
    - a bunt frozen by a daily-loss rule;
    - a lab graduate waiting more than 6 hours;
    - a desk offered markets for an hour with zero intents;
    - the lab closed for more than 30 minutes.

### H. Docs and a clean repo

- **Timing:** the cleanup runs as a background agent from T0 and is done by T+2:00. The run's own
  worktrees wait for the deadline.
- **Docs:**
  - README, operations, runbook, the League README, CONTRACT, the gateway README and the site's
    DESIGN.md describe what is running.
  - The README's deploy list is updated at each deploy.
- **Scope.**
  - Only the worktrees listed by `git -C ~/Work/long-term-capital-management worktree list`.
  - Never the main checkout `~/Work/long-term-capital-management`: `~/Work/ltcm-deploy/.data`
    links to its `.data`.
  - Never `~/Work/ltcm-deploy`.
  - Never the run's own worktrees.
  - Never a worktree with a commit or modified file in the last 6 hours: another session may be
    using it.
  - Nothing under `~/Work` that is not in that worktree list (for example `github-backups/`,
    `agent-host/`, `tries/`, `personal-site/`).
- **Before removing a worktree.**
  - `git status --porcelain` must be empty. If it is not, commit to a `wip/<dir>` branch and push
    it.
  - Push every unmerged branch to origin. Today that means `codex/architect-registry-repair`,
    `night/record` and `night/repairs`.
  - Never `git worktree remove --force`, `git clean`, `git reset --hard` or a bare `git stash`.
- **Branches.** Delete on GitHub only branches merged into `origin/main`. Never delete `main`, or
  the head branch of an open PR.
- **PRs.**
  - Close only PRs on `merton/` or `astra/` branches that nothing will merge (today, for example,
    the toolsmith volatility helpers #36-#44, #30, #72, #73 and #149). Give each a one-line
    comment and list it in the run record.
  - Every open PR shows the owner's account as author, so go by the branch prefix.
  - Never close a PR this run or its builders opened.
- **Docs and scripts.**
  - History is not clutter: keep `docs/runs/`, `docs/proposals/` and `docs/design/`.
  - Delete a doc or script only when nothing references it. Check this repo, `~/Work/ltcm-deploy`,
    `~/Work/personal-site`, the memory directory and the box's crontab and units.
  - Never delete a `ci.FORBIDDEN` path.
  - List each deletion in the run record.
- **Memory:** a new project memory and its MEMORY.md line.

## Watching

- **The watch loop:** `scripts/floor_watch.py` every 15 minutes into the session log.
- **The events monitor:** band moves, audits, real fills, deaths, lab graduations and error alerts.
- **During the US session:** also record stock and option wakes, intents, orders, fills and
  refusals every 30 minutes.
- **Verify on the box.** A merged PR is not a deployed feature: check the running release's files.

**When each change can be verified:**

| Change | Deploy | Window | What counts |
|---|---|---|---|
| U1 daily-loss | A | any hour (Kalshi 15-minute crypto trades 24/7) | a real bunt down more than 10% on the day keeps entering with no daily-loss refusal on a real book; at about one real fill an hour, "mechanism verified, no live instance" may be all there is |
| U2 shards | A | first hourly pass; shard-3 sports from about 23:00Z | an ops alert per move, a shard-3 fill, the account total unchanged |
| U5 compounding | A | the first real settlement with a gain | the winner's stake holds its gain inside the headroom |
| C2 lab gate | A | once the tier drops below "all" (about 20:30Z unpaced) | the lab keeps evaluating with no Luna or Sol calls |
| A7 fractional limits | A | practice, until 20:00Z; otherwise the Sept 24 open | an agent's practice fractional limit order fills with no whole-share refusal |
| #189 limits | live | to 20:00Z (real Alpaca crypto 24/7) | no real refusal for an order sized to the limits the agent was shown |
| #190 seats | live | overnight to the deadline | no stock or options agent holding a position is displaced; never-traded agents go first |
| A3 wake at the open | live | Sept 24 13:30Z | recorded as unverified at the deadline |
| S seats and forward windows | A or B | 1-2 h after deploy | a graduate born in place of a never-traded resident; a lineage's search cut by forward loss |
| OpenAI pacing | T+0:30 | hourly | burn about $3.30 an hour or less, and no audit waiting for budget |

## Lessons to read before starting

These are from Sept 22-23. The full runbook is
[the north-star plan's "Deploys and ratification"](LTCM_NORTH_STAR_BUILD.md#deploys-and-ratification-the-runbook).

- **Ratify at promotion, not later.**
- **Protected paths skip the updater.**
  - A range that touches `ci.FORBIDDEN` (including `gateway/`) needs an owner deploy, which still
    runs the canary and the 10-minute watch.
  - **A protected merge on main blocks the updater for everything after it,** including Merton's
    PRs and unprotected fixes, until it is owner-deployed.
  - Keep protected work on its wave's integration branch, and merge it to main only minutes
    before its deploy.
  - The updater polls about every 30 minutes. A manual deploy during its run is refused
    ("another deploy or rollback is running"): wait and retry, never chain.
- **Gateway deploys are separate** (`npx wrangler deploy --tag <sha>`), and never ride the House
  release.
- **Never chain a deploy on grep's exit code.** Commit each merge before the next.
- **Never `pkill -f "unittest discover"`.**
- **`~/Work/ltcm-deploy/.data` is a symlink** to `~/Work/long-term-capital-management/.data`.
  Never `ln -sfn` over it.
- **The auditor judges bunts with the allocator's `allocation_context`.** Keep it in any new
  promotion path.
- **Kalshi exchange shards:** an order on an unfunded shard fails with HTTP 404
  `insufficient_shard_balance`.
- **The site's copy rule:** practice, never paper. The ladder's levels are "Practice", "Live
  trading" and "Increased capital", the owner's words.

## The report at the deadline

In the run record and in the session:

1. **What is live:** release, commits, money digest, grant state, and every rule changed with its
   evidence.
2. **What we learned:** the study's top findings and the ranked blockers; what was unblocked, what
   was not, and why.
3. **Real money:** agents and dollars at work per venue, band moves, fills, real P&L per venue,
   the throttle, and whether any winner compounded.
4. **Practice:** P&L by desk and family, and which families show forward edge.
5. **The loop:**
   - lab throughput and forward windows;
   - graduates and their results;
   - the yield of Merton's roles;
   - what the agents asked for.
6. **Compute:** OpenAI, Sail and Jev spent, what was paced, and cost per unit of evidence.
7. **Bugs:** found and fixed, who found each one (the floor or this session), the invariants
   added, and anything still open.
8. **Repo and docs:** what was cleaned (worktrees, branches, PRs, docs).
9. **Rollback steps,** and the owner's next decisions with a recommendation for each.

## Done

The run is done when all of these hold:

- the study is published;
- every workstream is in one of three states:
  - live on the running release and verified in its window;
  - scheduled for a named window after the deadline (A3, and anything that missed Deploy A:
    the Sept 24 open);
  - blocked, with the blocker recorded with numbers;
- all test suites and CI are green;
- real money is at work at both venues, or the exact reason it is not is recorded;
- README, operations, the run record and memory are current;
- the repo and `~/Work` are free of stale worktrees, branches and PRs, with unmerged work pushed
  first;
- the report is delivered at the deadline.

"""The constitution: what no model and no code path on Sail may change.

These are versioned evaluation rules. The initial thresholds preceded the league; owner-requested
revisions and their rationale are recorded in the run reports. Merton's pull requests cannot
touch this file (`league/ci.py` guards the path). The House records its digest whenever it starts,
so changed rules are visible and cannot be described as an unchanged preregistered experiment.

The order caps, the OpenAI budget and the kill switch are ENFORCED in the Cloudflare gateway,
outside Sail, where nothing here can reach them; they are repeated here so the House refuses
first and can say why. The Sail budget has no enforcement point at Sail (Sail has no spend caps),
so the House meters it against Sail's own usage record and stops spending at the line.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CONSTITUTION: dict[str, Any] = {
    "version": 1,
    "budgets": {
        "sail_month_usd": "100",
        "openai_month_usd": "100",
        # Never spend the last of the credit: the House box itself must stay up.
        "sail_reserve_usd": "5",
        # The expedition (the owner's decision of Sept 19, 2026): both budgets are to be USED, in
        # full, over fourteen days, so the game's design can be judged on a fortnight of real
        # work rather than a thrifty month. `league/pacer.py` spends them evenly; these are
        # ceilings as well as targets, and the monthly caps above still stand behind them.
        "expedition": {"start": "2026-09-19", "days": 14, "sail_usd": "100", "openai_usd": "100", "front_load": "2"},
    },
    "order_caps": {"max_order_usd": "75", "max_day_usd": "4000", "max_day_orders": 2000},
    "ladder": {
        # One-sided error rate for every promotion and every statistical death, spent across
        # looks as alpha * 6 / (pi^2 k^2) so that looking often can never buy a false pass.
        "alpha": 0.05,
        # Owner revision, Sept 23, 2026 ~03:10 UTC, "swing big when you see the ball, bunt when you
        # don't" ("im okay losing every penny in my accounts ... when youre seeing the ball well you
        # should take big swings and bunts when you arent and the agents should feel the same way
        # from our game design"). Promotion to SCALED size (rung 2 -> 3, the agent's own bound, its
        # completed exposures and its family's pooled record) spends this error budget; death keeps
        # `alpha`. A false pass costs a Kelly stake sized on the same lower bound -- a weak bound buys
        # a small stake, a strong one a big swing -- and drift, `micro_demotion` and death still send
        # it down. Measured Sept 23 03:15 UTC: no agent had ever reached rung 3; three held rung 2.
        "promotion_alpha": 0.20,
        # Same revision: 5 -> 3, so a live record is read, and can swing, sooner.
        "look_every_active_blocks": 3,
        # The screen's drawdown is read over this many most recent blocks, not the whole stay: a
        # lifetime high-water mark never falls, and one bad afternoon would otherwise bar an agent
        # from real money for the rest of its life. Death still reads the whole stay.
        "screen_drawdown_blocks": 30,
        # No promotion on fewer closed trades than this, however good the blocks look.
        # Owner revision, Sept 21, 2026 ~22:30 UTC (the fast lane): 10 -> 5.
        # Owner revision, Sept 22, 2026 ~19:50 UTC ("push harder ... more dynamism ... I'm willing to
        # accept more vol on my accounts"): 5 -> 3. See `paper` below for the measurement.
        "min_closed_trades": 3,
        # Rung 0 -> 1: mechanical replay, and the only gate before a PAPER seat, which costs the
        # owner nothing but compute. The deflated Sharpe is the confidence that the idea beats the
        # best of the trials in its line; 0.75 is a three-to-one bet on free information, and the
        # bar for money is the screen, the audit and the tuition cap that come after. The volume
        # thresholds are NOT relaxed: what the league is short of is strategies that trade at all.
        # Owner revision, Sept 21, 2026 ("push hard ... not mechanically too difficult at the risk-free
        # rungs"): 0.75 -> 0.5 and 30 -> 20 blocks. Of the 268 replays from Sept 20 21:00 to Sept 21
        # 18:15, 18 passed at 0.75 and 40 would have at 0.5; the deflated Sharpe was the reason in 93
        # of every 99 failures. 0.5 still asks that the idea more likely than not beats the best of
        # the trials in its own line, and paper -- forward evidence -- is where it is really tested.
        # Owner revision, Sept 22, 2026 ~21:25 UTC ("desperate need of more dynamism ... I would've
        # expected my alpaca paper trading account to have a ridiculous amount of trading on it"):
        # deflated Sharpe 0.5 -> 0 (off) and 20 -> 10 closed trades. A paper seat now needs a program
        # that trades enough to judge and made money out of sample. The multiple-testing penalty
        # stays where money is at stake: the screen, the audit and the scaled rung's bound. It had
        # deadlocked whole desks here -- Alpaca megacaps' line reached 59-63 trials, each failure
        # raised the bar for the next, and its agents stopped trying. Of the 786 replays from Sept 20
        # 21:20 to Sept 22 21:20, 38 agents passed at the old values (5 on Alpaca desks); 157 would
        # have at these (54 on Alpaca desks).
        # Owner revision, Sept 23, 2026 ~03:10 UTC ("more risk and speed and exploration and
        # experimentation ... in the low and risk free rungs"): out-of-sample growth need only be
        # above `min_oos_growth` a block, not above zero. Replay has been the pessimist: haghani's
        # hourly crypto reversion made +7.4% over 70 blocks of paper while its children's replays
        # read -0.02% to -0.05% a block. A near-breakeven idea gets a free paper seat, where
        # forward fills judge it, and `paper_death` takes the seat back from a loser.
        "replay": {"min_trades": 10, "min_blocks": 20, "min_deflated_sharpe": 0.0, "min_oos_blocks": 8,
                   "min_oos_growth": -0.0005},
        # Rung 1 -> 2: a SCREEN, then the frontier audit. Not a confidence bound: a bound strict
        # enough to mean something needs hundreds of trades (the first run's one measured edge
        # could not pass it in a month), and what it would protect is a $25 stake. The loss of the
        # micro rung is capped in dollars instead: see `tuition`.
        # `min_active_blocks` is in BLOCKS, and a block is an hour or a calendar day by the
        # strategy's own declared horizon. This remains an alternative for long or overlapping
        # exposures; completed_exposures below removes a mandatory elapsed-time requirement.
        # Owner revision, Sept 21, 2026 ~22:30 UTC, "the fast lane": 15 -> 6 hourly blocks and 5 -> 2
        # daily. At 22:05 twenty-four agents sat on paper and one had six active blocks; after eight
        # hours of accelerated research one agent had traded real money. The $25 stake, the frontier
        # audit, the order caps and the owner's capital envelope are unchanged, and `micro_demotion`
        # below sends a live loser back down: cheap to try on real money, expensive to scale.
        # Owner revision, Sept 22, 2026 ~19:50 UTC, for dynamism with more volatility accepted on the
        # real accounts: 6 -> 4 hourly blocks (daily stays at 2: a look needs two blocks for its
        # bounds). Measured at 19:45: 29 of 31 paper agents were still at the evidence stage and
        # 24 had no finished active block, most of them trading, and one agent traded real money.
        # The same revision stopped the evaluator dropping the block an account is funded in, which
        # cost a daily agent a whole day. Growth above zero, the drawdown screen, the frontier audit,
        # accounting integrity, the owner's capital envelope, `micro_demotion` and the statistical
        # bound for scale are all unchanged.
        # Owner revision, Sept 23, 2026 ~00:00 UTC ("do 1-5 right now fully"; more volatility on the
        # accounts accepted for more movement up and down the ladder). Measured Sept 22 23:35 UTC: 0
        # promotions from paper to money in 24 hours and 2 ever; 37 of 40 paper agents trade a daily
        # horizon; 11 audits had approved 2.
        #   - `settled_day`: a daily agent on an event-contract book whose trades have SETTLED --
        #     three market outcomes on this rung -- is screened after one finished active day, not
        #     two. A settlement is evidence, not a mark; the two-day wait bought only calendar.
        #   - `audit: "after"`: the frontier audit no longer stands BEFORE the micro rung. An agent
        #     that clears the screen, with room in the owner's capital envelope, goes to the micro
        #     rung at once and is audited there; a veto sends it straight back to paper, and a veto's
        #     cooldown still bars another promotion. The micro stake, its order and position caps,
        #     `micro_demotion`, drift, the capital envelope and the bound for rung 3 are unchanged.
        # The screen also counts the block in progress (the evaluator, same date): a daily screen
        # that read only finished days passed hawkins while that morning's settlements had lost $15.50.
        # Owner revision, Sept 23, 2026 ~03:10 UTC (swing and bunt): the micro rung is where an
        # unproven idea BUNTS -- $60 of real money, $30 a position -- so the screen in front of it
        # asks less: 3 hourly blocks (was 4), 1 finished day (was 2; the screen needs no bound, and
        # a day with nothing settled is still a day of marks), and a recent drawdown under 25% (was
        # 15%: a volatile record that is up is what the owner asked to see tried). The frontier audit
        # after promotion, `micro_demotion` and the capital envelope are unchanged.
        "paper": {"gate": "screen", "min_active_blocks": 3, "min_active_blocks_day": 1, "max_drawdown": 0.25,
                  "settled_day": {"min_active_blocks": 1, "min_settled_trades": 3}, "audit": "after"},
        # Rung 2 -> 3: real fills at $1 to $10 a position, and the confidence bound, because
        # this is the gate that protects real size. Promotion spends its own alpha: the looks
        # that can only kill (before `min_active_blocks`) spend none of it.
        # Owner-requested accelerated experiment, Sept 20: remove the 30-hour minimum.
        # Five active blocks retain the conventional route. The completed-exposure route below
        # has no elapsed-time minimum; both routes share the original promotion error budget.
        # Swing and bunt (Sept 23, 2026 ~03:10 UTC): 5 -> 3 active blocks before the first bound,
        # which is read at `promotion_alpha`.
        "micro": {"gate": "bound", "min_active_blocks": 3},
        # Kept at 10: at 5 the qualifying record was too short a reference for drift, and a fresh
        # promotion was demoted as "decayed" within minutes in the ladder's own integration test.
        "completed_exposures": {"min_episodes": 10, "look_every_episodes": 5, "promotion_alpha_share": 0.5},
        # A small edge proves itself across a family sooner than in one agent (the first run's
        # favourites edge was only ever measurable pooled). An agent on rung 2 whose own record is
        # positive but not yet decisive may be scaled on its family's pooled real-money record:
        # one series, the mean growth of the family's rung-2 agents block by block, tested at its
        # own alpha with its own looks.
        # Swing and bunt (Sept 23, 2026 ~03:10 UTC): a mechanism several live agents are winning with
        # is the clearest sight of the ball the league gets. Its pooled record is read at the
        # promotion budget (0.05 -> 0.20), and a member counts after 5 active blocks (was 10).
        "family": {"alpha": 0.20, "min_members": 2, "min_member_active_blocks": 5},
        # Death at any rung above 0: evidence that growth is negative, or the stake is going.
        # Swing and bunt (Sept 23, 2026 ~03:10 UTC): 0.30 -> 0.40. Full Kelly on a lower bound
        # (rung 3 below) draws down a third or more in ordinary luck; a big swing must not be killed
        # for its variance alone. The statistical death test and drift are unchanged.
        "death": {"min_active_blocks": 20, "max_drawdown": 0.40},
        # Owner revision, Sept 21, 2026: losers on PAPER die fast, because a paper seat is the
        # scarcest free thing the league has. After `min_active_blocks`, a paper record down
        # `max_loss` or more from where it started dies; after `unprofitable_blocks`, any record
        # that is not above where it started dies. Measured that day: the five 15-minute crypto
        # agents were down 10-17% on paper and held their seats for a day, and a founding seed
        # sat unprofitable through 41 active blocks. Real money keeps `death` above.
        # Owner revision, Sept 22, 2026 ~19:50 UTC: 10 -> 6 and 30 -> 20, so failing paper records
        # leave as fast as passing ones rise (movement down as well as up); paper costs no money.
        "paper_death": {"min_active_blocks": 6, "max_loss": 0.10, "unprofitable_blocks": 20},
        # The fast lane's other half: a micro-real agent down this share of its record since
        # promotion goes back to paper at once (it may earn its way back), rather than waiting
        # twenty blocks to die or for drift. Rise fast, fall fast.
        "micro_demotion": {"max_loss": 0.20},
        # Drift at rungs 2 and 3: a CUSUM on block growth against the record that earned the rung.
        # h = 6 is about one false alarm in 1,300 blocks (h = 4 would be one a week on hourly blocks).
        "drift": {"k": 0.5, "h": 6.0, "window_blocks": 60, "min_reference_blocks": 10},
        # A record with this share of winning trades is judged on an exact (Clopper-Pearson) bound
        # of its loss rate as well, because a t-interval flatters it until the first loss arrives.
        "lopsided_win_rate": 0.80,
    },
    # What the micro rung may cost, in dollars, whatever the statistics say. `max_loss_usd` is the
    # net loss of every real-money account that has not yet earned rung 3; at the line, promotions
    # to real money stop and the agents on rung 2 are sent back to paper. `max_agents` bounds how
    # much can be at risk at once. Only the owner refills it (by raising this number).
    "tuition": {"max_loss_usd": "50", "max_agents": 4},
    "rungs": {
        # Paper agents are held to the live account's real limits, not the paper account's.
        "1": {"stake_usd": "200", "max_position_usd": "100", "max_order_usd": "75"},
        # One option contract is 100 shares and cannot be cut smaller, so on this rung an option
        # position is ONE contract of at most `option_max_position_usd` in premium. Options are
        # long premium only (the gateway refuses anything else): what is paid is all that can be lost,
        # and the tuition cap above counts it like any other loss.
        # Owner revision, Sept 21, 2026 ~23:50 UTC (the learning surge): "allow for more risk taking ...
        # larger trades based on their conviction". A strategy learns its sizing on paper ($200 stake,
        # $100 a position, $75 an order) and was squeezed to $25 / $10 / $10 on promotion, so its
        # proven intents were refused or clipped (huang-6: $8 against a $7.89 cap). Now $60 / $30 /
        # $30, one option contract up to $40. `micro_demotion` still returns a live loser to paper.
        "2": {"stake_usd": "60", "max_position_usd": "30", "max_order_usd": "30", "option_max_position_usd": "40"},
        # Learning surge (owner, Sept 21, 2026 ~00:00 UTC: "it's obviously going to require some additional
        # risk taking and volatility which I'm willing to accept"): a PROVEN edge (positive lower bound)
        # compounds at half of Kelly on that bound, up to 40% of the venue's cash (a quarter and 25%).
        # Swing and bunt (owner, Sept 23, 2026 ~03:10 UTC: "when youre seeing the ball well you should
        # take big swings"): FULL Kelly on the lower bound (was half), up to 60% of the venue's cash
        # (was 40%). Sizing stays on the LOWER bound, never the point estimate, so a thin record still
        # buys a small stake: the swing grows with the evidence. Every order still meets the gateway's cap.
        "3": {"max_order_usd": "75", "kelly_fraction": 1.0, "max_share_of_venue": 0.6},
    },
    # Owner revision, Sept 23, 2026 ~06:00 UTC, "capital is the ladder" (docs/goals/
    # LTCM_NORTH_STAR_BUILD.md, Workstream A): "I deeply want to speed up the dynamism of agents moving
    # up and down the levels of the game as quickly as possible and aggressively aligned on incentives
    # so star traders can compound and run wild and profit exponentially and losing agents die off
    # ... allow for trading to be done on the timescale of 24/7 agents not human clocks and defined
    # times ... trading live on both my kalshi and alpaca account, I'm willing to accept volatility
    # and risk of these funds". While `enabled`, an agent's rank is its capital and `league/
    # allocator.py` moves it at every mark pass: evidence is the agent's wealth multiple (paper at
    # its square root, real in full), bunts are small real stakes at once, swings are sized by the
    # evidence, and hysteresis, a real drawdown line, paper-wealth death and a floor throttle move
    # capital down as fast. The paper screen and the micro bound no longer promote and `rungs.2`/
    # `rungs.3` sizing is superseded (kept for rollback: `enabled: False` restores the old ladder).
    # The grant's per-venue capital, the gateway's order cap, day caps and kill switch, no leverage
    # and no shorts are the whole risk budget; inside them the allocator decides. Measured Sept 23
    # 06:30 UTC: 3 agents on real money (all Kalshi favourites, $60 each), the Alpaca real account
    # had never traded, 93 agents on paper.
    "allocator": {
        "enabled": True,
        # A8, the learn-and-unblock run (Sept 23, 2026 ~22:00 UTC; the table's row: "per asset class,
        # each from at least 30 measured fills of that class, never below 2 bps a side"): the Alpaca
        # practice haircut is charged by each fill's asset class, at the optimism measured on that
        # class's own practice fills against the order's reference at intent time (the touch for a
        # market order, the limit for a limit order), because real Alpaca fills are too few to be the
        # benchmark (2 crypto at 0.0 bps, 0 equity, 0 option). Measured on the 21:36Z snapshot, fills
        # since Sept 21 (docs/research/queries/2026-09-23/A8-haircut.py and .out), + adverse, - better:
        #   crypto 368 fills, $12,148: notional-weighted mean -3.13 bps (buys -0.01, sells -6.63);
        #   equity 136 fills, $4,005: -0.21 (buys -0.17, sells -0.26), at the touch;
        #   option  46 fills, $982: -21.15 (buys -15.10, sells -32.84; a few limits filled far through).
        # Each class is charged the larger of the aggregate and the round-trip reading (half of the
        # buys' plus the sells' optimism: both fills of a position overstate it), rounded up to a
        # whole bp, never below 2: crypto 3.32 -> 4, equity 0.22 -> 2, option 23.97 -> 24. Options are
        # TIGHTENED from 10 (evidence honesty cuts both ways); crypto and stocks are loosened to what
        # was measured, since 10 a side was 3x crypto's optimism and 50x the stocks'. A plain number
        # still charges every class (the rollback form), and a class not named pays the largest rate.
        "evidence": {"paper_weight": 0.5, "alpaca_paper_haircut_bps": {"crypto": 4, "equity": 2, "option": 24}},
        # 1.01, not the plan's 1.03 (its bounds are 1.0-1.25): measured on the floor at 06:45 UTC,
        # paper agents size a few percent of their $200 purse, so no paper agent without real money
        # had E >= 1.03 (paper +6.1%) and the bunt -- a cheap real test by design -- would have seated
        # nobody for days, while the owner's first priority is movement onto real money on both
        # venues. 1.01 still asks for +2% on the whole purse after fees, and hysteresis sends a bunt
        # back below 0.8585.
        "bunt_at": 1.01, "bunt_min_trades": 5, "bunt_min_settled": 3,
        # Alpaca 25, not the plan's 15: the book refuses any order over half of an account's equity
        # (`book.DEFAULT_RULES` max_order_notional_pct / max_position_pct 0.50, the same share as
        # `position_share`), and Alpaca takes no crypto order under $10 -- so a $15 bunt could never
        # trade crypto (measured in `test_allocator`, Sept 23: "order notional 10.80 exceeds 50% of
        # desk equity"). $25 leaves a $10 order room for its fee and a price step.
        # Kalshi 30, not 10 (the learn-and-unblock run, Sept 23, 2026 ~17:00 UTC, from the agent
        # study's evidence, inside the table's $10-$30): a $10 bunt was a one-loss trial. With
        # `position_share` 0.5 it may hold a $5 position, and any lost position over 15.4% of the
        # stake ($1.54) drops E below the hysteresis line 0.8585 (bunt_at 1.01 x 0.85) and sends the
        # agent back to paper: huang-h427345 was demoted after one -$2.55 settlement (14:57Z), and
        # mullins-2, 10 of 10 winning real settlements (+$4.89 as a maker on weather favourites), had
        # been swept from $60 to $5.11 of equity, where its next miss is -57%. The allocator swept
        # $144.19 of bunt equity to cash in 13 moves that day. At $30 a typical Kalshi position
        # ($2.70, meriwether's sports bet) is a -9% loss and a bunt survives several. The grant's
        # seats follow the smallest real stake (`live_trading.policy`): the probe since Sept 24, 2026
        # (`probe_bunt_usd` below), floor($1,017.75 / $10) = 101; floor($1,017.75 / $25) = 40 before.
        # Since the close-the-gaps run (Sept 24, 2026) this is a PROVEN family's bunt (`family_proven`
        # below); an unproven family's first real stake is a probe.
        "bunt_usd": {"kalshi": "30", "alpaca": "25"},
        "venue_minimum_usd": {"kalshi": "1", "alpaca": "10"},
        # 1.25, not 1.5 (same revision, inside the table's 1.25-1.5): at their historic rates the only
        # two earners needed 2.8 days (mullins-2, +0.0147 log W_real a settlement, 17 more wins) and
        # 5.6 days (mullins-6) to reach E 1.5, and nobody else had a rate. The first swing is still
        # audited on the real record and the swing stake is sized by E, so a thin E buys a small
        # swing. `swing_min_real_trades` stays 8.
        "swing_at": 1.25, "swing_min_real_trades": 8, "swing_min_w_real": 1.0, "swing_exit_w_real": 0.9,
        # kappa 2, not 1 (same revision, inside the table's 1-2): the swing stake is `bunt_usd x
        # E^kappa`, capped at `max_share_of_venue` of the venue, so winners compound exponentially in
        # the evidence, the owner's direction. No swing existed on Sept 23, so it has no effect until
        # one is earned.
        "kappa": 2.0, "e_cap": 20, "max_share_of_venue": 0.6, "position_share": 0.5,
        "stars": 3, "star_min_w_real": 1.25,
        # An agent back on paper from real money waits this long before it may bunt again, so a
        # record near a line cannot flap between books (and pay a sweep and a fresh stake) at every
        # mark pass.
        "hysteresis": 0.85, "real_drawdown_demote": 0.35, "reentry_cooldown_hours": 1.0,
        "die_below": 0.80, "die_min_trades": 10,
        "throttle": {"halve_below": -0.30, "restore_above": -0.15},
        "min_stake_change": 0.10,
        "performance_fee_share": 0.2,
        "profit_indexed_envelope": True,
        # Owner revision, Sept 23, 2026 ~16:00 UTC, the learn-and-unblock run (docs/goals/
        # LTCM_LEARN_AND_UNBLOCK.md, "Money-rule bounds for this run"): "make this 10 hour run about
        # learning as much as possible about our agents and whats blocking exponentially profitable
        # 24:7 recursively self improving trading agent swarm and unblocking those things ... being
        # bold and ambitious and not afraid to take risks both in our approach and the agents (im fine
        # with volatility and lose on my portfolio to achieve the north star goal)". The four keys
        # below carry that table's rows; `league/book.py` and `target_stake` read them.
        #
        # `bunt_daily_loss`: a REAL-money bunt is governed by the allocator's stay drawdown
        # (`real_drawdown_demote`, unchanged) and hysteresis, not by the book's per-desk daily-loss
        # rule (`book.DEFAULT_RULES` max_daily_loss_pct 0.10, unchanged for swings and for every
        # practice book). Measured 12:21 UTC Sept 23: huang-h51fdd3-2, a $10 Kalshi bunt, lost $1.52
        # on its first real trade (15% of its stake) and the book froze it for the day ("desk daily
        # loss 13.2% reached limit 10%; only risk-reducing orders allowed") before the allocator's own
        # demotion lines could act. `"book"` restores the book's rule for bunts.
        "bunt_daily_loss": "stay_drawdown",
        # `real_halt`: the real book's daily-loss halt (`book.DEFAULT_RULES` floor_max_daily_loss_pct
        # 0.08) was measured on the sum of the staked accounts: with one $25 bunt staked, a $2.00 halt,
        # tighter than the per-agent line. Now `pct` of THAT venue's grant capital, per venue ($517.75
        # Kalshi -> $41.42, $500 Alpaca -> $40.00), never the combined envelope applied to one venue,
        # never the staked sum on a real book. Practice books keep the staked-sum basis; `basis:
        # "staked"` restores it on real books.
        "real_halt": {"basis": "venue_grant_capital", "pct": "0.08"},
        # `bunt_growth`: a bunt keeps what it makes. Its target stake is `bunt_usd x clamp(W_real, 1,
        # swing_at)` instead of the flat `bunt_usd` (`"flat"` restores that): profit stays in the
        # stake up to the swing line, above it the rest is swept as before, and a bunt whose W_real
        # is below 1 is never topped back up (its stake shrinks by what it lost; the stay drawdown,
        # hysteresis and death decide the rest). Measured 16:21 UTC Sept 23: mullins-2 and mullins-6,
        # the floor's only real earners, had been swept from $60 toward $10 by the flat rule --
        # mullins-2 held a $5.11 stake at E 1.178 (W_real 1.158), mullins-6 $36.70 at E 1.055.
        "bunt_growth": "w_real",
        # `option_bunt_usd`: an options bunt is staked this much (proposal A2a; the table allows up
        # to $80). At the old max(bunt_usd, rungs.2.option_max_position_usd) = $40 the book's
        # 50%-of-equity position and order rules held a contract to $20, so the chain was filtered at
        # contracts the book refused (docs/proposals/2026-09-23-alpaca-stocks-and-level-3-options.md,
        # blocker 6). At $80 one $40 contract fits under half the stake, inside the $500 Alpaca
        # envelope and under the $75 order cap.
        "option_bunt_usd": "80",
        # ---- Promotion on proof: the close-the-gaps run, Deploy A (docs/goals/LTCM_CLOSE_THE_GAPS.md,
        # D4 and P1-P3; each key below carries one row of that plan's closed "Money-rule bounds" table).
        # The owner, Sept 23-24, 2026: "I deeply want to speed up the dynamism of agents moving up and
        # down the levels of the game as quickly as possible and aggressively aligned on incentives so
        # star traders can compound and run wild and profit exponentially and losing agents die off",
        # and "being bold and ambitious and not afraid to take risks both in our approach and the
        # agents (im fine with volatility and lose on my portfolio to achieve the north star goal)".
        # The evidence (the gap review, Sept 24, 2026 00:19-00:50Z): the allocator's nine promotions to
        # real money (08:28Z Sept 23 to 00:17Z Sept 24) all ran unproven mechanisms -- 15-minute crypto
        # taker momentum at 182 bps, MLB-total takers at a 7% fee, 20c ETH-strike longshots, a lab
        # graduate -- and settled -$18.62 on 16 settlements: 6 negative, 4 demoted after one loss, 0
        # positive at 00:30Z. The design memo's own warning: the best of 50 edgeless agents shows a 75%
        # win rate after 20 trades. The one proven mechanism, resting bids on weather favourites
        # (mullins-2, W_real 1.19 on 10 of 10 winning real settlements), held $66 while nine unproven
        # bunts held $256 (the T0 board).
        #
        # `independent_settlements` (row "allocator.independent_settlements"): "event" counts closed
        # trades and settlements once per distinct EVENT on the event books (kalshi-shadow, kalshi):
        # the market ticker's event (`evaluator.event_key`), so three strikes of one game that all
        # settle are one settlement. `bunt_min_trades`, `bunt_min_settled`, `swing_min_real_trades`,
        # `hysteresis_after_settled` and the family record read these counts; W is unchanged (money is
        # money). "trade" restores one count per settlement. Evidence: meriwether-h7d7702 bought
        # strikes 7, 8 and 9 of one MLB total (KXMLBTOTAL-26SEP231310WSHDET-7/-8/-9, settled seq
        # 363205-363209) and was promoted at 20:07:05Z Sept 23 "on 3 closed trades" -- one game -- and
        # again at 00:39:48Z Sept 24 "on 6 closed trades": two games (WSHDET and MINSF).
        "independent_settlements": "event",
        # `max_event_share` (row "allocator.max_event_share", 0.2-0.5): a real book's exposure to one
        # event -- holdings there at cost, working buys on every market of the event, and the new order
        # -- is at most this share of the agent's EQUITY on that book (`league/book.py` refuses the entry
        # that would pass it). A quarter is under the 35% stay drawdown, so one upset cannot demote a bunt
        # by itself; meriwether-h7d7702's MILPHI-6/-7/-8 were $17.36 of one game on a $200 purse.
        "max_event_share": "0.25",
        # `probe_bunt_usd` (row "allocator.probe_bunt_usd", Kalshi $5-15, Alpaca $20-25): an agent whose
        # family is not proven is seated on real money as a PROBE at this stake; a member of a proven
        # family as a bunt at `bunt_usd`. Pocket change for an unproven mechanism, the owner's full bunt
        # for a proven one. Alpaca's probe is $25, the bunt's own floor: Alpaca takes no crypto order
        # under $10 and the book refuses an order over half an account. An options probe is still
        # staked `option_bunt_usd` ($80): one contract cannot be cut smaller.
        "probe_bunt_usd": {"kalshi": "10", "alpaca": "25"},
        # `family_proven` (row "allocator.family_proven": >= 10-20 independent settlements, practice at
        # 0.5, real at 1, a one-sided 80% lower bound above zero): a family is PROVEN when its pooled
        # forward record (`allocator.family_record`: every member ever born, living or dead; one
        # observation per independent event, correlated members pooled into one) has at least
        # `min_independent_settlements` observations and its lower bound on mean log growth per
        # observation, at `confidence` (Student's t on the effective count), is above zero. Proof at
        # the family level, money at the agent level: a mechanism is proven by its family's record,
        # never by one agent's three lucky settlements.
        #
        # `lopsided_gate` (the same row: its lower bound computed honestly; adopted by the main session
        # on the review of #224, Sept 24, 2026): a LOPSIDED record -- `ladder.lopsided_win_rate` (80%) or
        # more of its observations winning, as favourites win -- must also clear the House's exact
        # loss-rate lower bound at the same confidence (`stats.lopsided_growth_lcb`: a Clopper-Pearson
        # upper bound on the loss rate times the worst loss, the family's mean cash at risk an entry
        # until a whole loss is seen), the lower bound `Evaluator._judge_family` and `judge` already hold
        # such records to beside their t bounds. Until a loss is on the record a t bound is badly
        # anti-conservative (`league/stats.py`). Evidence: simulated, an edgeless family buying 93c
        # favourites passes the t bound alone at its 10th observation about 49% of the time (97c: about
        # 74%), not 20%; crypto-15m-favorites was proven at 11:17Z Sept 20 on ten small wins and unproven
        # by its eleventh, a loss (106 observations and a mean of -0.0021 at T0); at T0 weather-favorites
        # (buys at 93c on average) has a t bound of +0.0033 and a loss-rate bound of -0.0125: 2 losses in
        # 16 give an 80% upper bound of 25% on the loss rate, against a breakeven near 7% at 93c. False
        # restores the t bound alone. `min_independent_settlements` stays 10: raising it does not change
        # a symmetric record's false-positive rate at a look, and the gate is what fixes the lopsided one.
        #
        # `unit` and `reference_share` (the same row, Deploy B, Sept 24, 2026: C1 decided the unit of an
        # observation on the T0 snapshot, docs/goals/LTCM_CLOSE_THE_GAPS.md): "at_risk" measures an event
        # by what it made per dollar its positions put at risk, as the log growth of a small reference bet,
        # ln(1 + `reference_share` x r) / `reference_share` with r never below -1, so a contract that expires
        # worthless is a finite -1.005 at 1%, not an account's ruin. Measured on the T0 snapshot: a practice
        # row was growth on a $200 purse and a real row on a $30-60 stake, so a real row weighed three to
        # seven times its declared 1 against 0.5 (weather-favorites: a median 9.25% of the purse at risk an
        # event on practice, 31.7% of the stake on real money), and the account unit moves with the stake
        # itself, so a family swing that doubled a member's stake would halve its growth an event and pull
        # the family's own bound down. The at-risk unit is scale-free across purses, stakes and books, the
        # weights mean what they say, and bound / variance in it is Kelly's fraction of capital at risk.
        # Each event weighs what it put at risk against its member's mean on that book (the review of #242:
        # weighed alike, small wins and large losses -- a resting bid filled in full as the price falls
        # through it -- read as an edge while the dollars lost; weather-favorites' practice losers carried
        # 2.4 times its winners' dollars at T0, and a family that lost $44 of real money over 100 events was
        # proven and ready to swing). Effect at T0 (docs/runs/2026-09-24-close-the-gaps.md), the same states
        # as Deploy A's: weather-favorites unproven (2 losses in 16; loss-rate bound -0.2112 a dollar at risk);
        # sports-central-run-under proven (bound +0.1423: 6 of 11 practice events won at about even money after
        # a 7% taker fee, its winners carrying twice its losers' dollars; weighed alike it was -0.1234); every
        # other family unproven. "account" restores Deploy A's unit exactly.
        "family_proven": {"min_independent_settlements": 10, "practice_weight": "0.5", "real_weight": "1",
                          "confidence": "0.8", "lopsided_gate": True, "unit": "at_risk", "reference_share": "0.01"},
        # `family_swing` (row "allocator.family_swing", Deploy B, Sept 24, 2026; digest change 2 of 2): a
        # PROVEN family (`family_proven`, the pooled record: the table's one proof) whose REAL record has
        # `min_real_settlements` or more independent settlements and whose honest lower bound on it is above
        # zero (the one-sided t bound, and the loss-rate bound for a lopsided record: favourites must earn it
        # with losses on the record) SWINGS once the frontier auditor approves its entry on that real record.
        # The ENTRY is judged only at `min_real_settlements` real settlements and every `entry_every` more (15,
        # 20, 25, ...), on the first that many real events, with both bounds at `entry_confidence`; the family
        # STAYS, and its ramp doubles, while the whole real record's honest bound at `family_proven.confidence`
        # (80%) holds at every pass. Why (the review of #242 and the main session's decision, Sept 24, 2026): a
        # one-sided 80% bound re-read at every settlement is crossed by an EDGELESS family far more often than one
        # time in five. The main session's simulation (scratchpad/rev-bfam/sim_rules2.py, 500 runs a case, the
        # review's arithmetic) of the entry alone: at every settlement at 80% an edgeless even-money family enters
        # by 30 / 50 / 200 real settlements 37% / 44% / 61% of the time (a +14%/$ edge's median entry at 20); at
        # every 5th settlement at 90% it is 19% / 22% / 37% -- near the table's 20% over the 30-50 settlements that
        # matter -- while a +14%/$ edge still enters at a median 30, +8%/$ at 40, and a +1.8%/$ favourites edge at
        # 80 (an edgeless favourites family 9% by 50, 24% by 200). Leaving the swing, a member's new program or a
        # member born into the family after the audit lapses the approval: the next entry is audited again (a
        # swing already running is untouched). Every member on
        # real money is staked at the ramp -- `start_multiple` x `bunt_usd` ($60 at Kalshi) when the family
        # enters, doubling after every `doubling_every` further POSITIVE independent real settlements while
        # the bound stays above zero -- up to the FAMILY's caps shared by its members on real money: full
        # Kelly on that bound against the venue's capital (`rungs.3.kelly_fraction`, the owner's
        # swing-and-bunt sizing) and `max_share_of_venue` of it ($310.65 of $517.75), and held where the
        # measured fill rate at the next size (over `capacity_days`, on `capacity_min_markets` markets at
        # each size) is under `capacity_fill_ratio` of the rate at the size before. The envelope's headroom
        # bounds every increase; a bound at or below zero returns the members to bunts, by free cash only.
        # Values inside the table (15-40 settlements, 2-4x the bunt, doubling every 10; the entry's 90% is the
        # table's 80% bound computed honestly under repeated looks, as the loss-rate gate computed it honestly for
        # favourites at 04:15Z). Measured at T0: no family's real record qualifies (weather-favorites 5 real
        # events, all won: at 93c its loss-rate bound needs 23 clean real events at 80% and 32 at 90%, a look at 35).
        "family_swing": {"min_real_settlements": 15, "start_multiple": 2, "doubling_every": 10,
                         "capacity_fill_ratio": "0.5", "capacity_min_markets": 5, "capacity_days": 7,
                         "entry_every": 5, "entry_confidence": "0.9"},
        # `swing_requires_proven_family` (the main session's decision on the review of #224, Sept 24, 2026,
        # carried here so the ratified digest records it): only a proven (or swinging) family's agent takes
        # the agent-level swing (`swing_at`), an unproven family's agent at the swing line stays a probe, and
        # a swing whose family loses its proof drops back to rung 2 (free cash only). Every real-money agent
        # is then a probe or a proven family's member, the plan's Done list. False restores the agent-level
        # swing of Sept 23 for every family.
        "swing_requires_proven_family": True,
        # `corrected_child_supersedes` (row "allocator.corrected_child_supersedes", Deploy B): a research
        # child of a REAL-money parent that passes replay with a fix to the parent's entry mechanism (fee,
        # side, liquidity) demotes the parent to practice at once and takes its seat (`league/house.py`, L1).
        # Evidence: meriwether-h2d625d kept trading taker moneylines at a 7% fee while its child
        # meriwether-h2d625d-2 (maker) passed replay 39 of 40. Absent or false, only the engineer's merged
        # repairs supersede.
        "corrected_child_supersedes": True,
        # `hysteresis_after_settled` (row "allocator.hysteresis_after_settled", 0-5): the hysteresis
        # exit (E under `bunt_at` x `hysteresis`) sends an agent from real money back to practice only
        # once it has this many independent real closed results in its current stay (settled events on
        # Kalshi, closed trades on Alpaca); before that only the stay drawdown (`real_drawdown_demote`,
        # unchanged) and death apply. Evidence: a $30 bunt at `position_share` 0.5 could hold $15, and
        # one lost position over ~15% of the stake took E under 0.8585 -- 4 of the nine promotions were
        # demoted after one loss; huang-l23cdb7 lost $8.51 in 90 minutes on positions of 24-26% of its
        # stake; meriwether-h7d7702 was demoted at 23:33:37Z Sept 23 on a MARK (E 0.8038) with no real
        # settlement in its stay, and its position then settled +$16.31 (seq 398760).
        "hysteresis_after_settled": 3,
        # `position_share_event` (row "allocator.position_share_event", 0.15-0.5 on event books): on
        # Kalshi a real position is at most this share of the stake ($6 of a $30 bunt, $2 of a $10
        # probe), never under the venue minimum x 1.2. A binary contract loses its whole position, so
        # a fifth keeps one miss inside the stay drawdown. Alpaca keeps `position_share` 0.5.
        "position_share_event": "0.2",
        # `longshot_floor_real` (row "allocator.longshot_floor_real", 0.15-0.35 on real books;
        # `league/book.py` reads it): no opening buy on a real event book under this price. Evidence:
        # 20c ETH strikes lost twice on real money; the rules text's measured "cheap contracts lose".
        "longshot_floor_real": "0.30",
        # `real_entry_liquidity` (row "allocator.real_entry_liquidity"; `league/book.py` reads it): a
        # real entry on an event book is post-only unless the agent's family's pooled TAKER record is
        # positive (`Allocator.family_taker`). Evidence: the taker mechanisms were the loss engine of
        # the nine promotions (15-minute crypto momentum at 182 bps, MLB-total takers at 7%).
        "real_entry_liquidity": "maker_unless_family_taker_positive",
        # `family_probe` (row "allocator.family_probe"; R5 of the close-the-gaps run, Sept 24, 2026: the run's third and
        # last money-digest change, which the owner granted at the resume): NO PROBE ON A LOSING FAMILY. The line is the
        # House's own for breeding (`House._losing_family`, `families.losing`): a family's pooled forward record -- its
        # active `eval.block` count and summed log growth over every agent ever born into it, living or dead
        # (`House.family_forward`; the allocator reads the same rows from its tape, `Allocator.family_forward`) -- is
        # at or below zero after `losing_min_blocks` active blocks (a record that nets to zero is not a loss). Then:
        #   1. the allocator seats no PROBE from the family: the promotion waits, its status naming the blocks and growth;
        #   2. a probe already seated on it goes back to practice at the next pass by the demotion path (`_move_down` to
        #      practice), which holds a Kalshi contract to settlement and so sells nothing there; on Alpaca, where that
        #      path sells what the account holds (an option at the bid, a stock at the next open), only once the probe
        #      holds nothing that path would sell -- its working bids cancelled first, as the path itself does -- and no
        #      buy is still in question at the venue: no sale is ever forced, and it is lent nothing more meanwhile;
        #   3. under `reseat: "gain_since_demotion"`, each probe that goes back to practice from real money, for any
        #      reason, holds its family until the family's pooled forward record SINCE that demotion turns: positive over
        #      `losing_min_blocks` or more active blocks ("until the family's record turns"; a turn is for good, and each
        #      demotion is its own hold). The demotions are read from the ledger's `eval.verdict` rows (a restart forgets
        #      nothing): their `band_from`, and for a row that does not name its band, the family's state in the
        #      mechanism ledger just before it.
        # A gate that cannot be read seats no probe and demotes nobody.
        # A proven or swinging family's agents are bunts, not probes: none of this applies to them. Evidence
        # (docs/research/queries/2026-09-24/R5-family-probe.py, on the 15:06Z snapshot): of the allocator's 21
        # promotions to real money since Sept 23 00:00Z, 11 were onto families whose pooled forward record was negative
        # over 6 or more active blocks; they realized -$8.12 on 22 closes (8 positive) and no stay ended positive. The
        # other 10 made +$28.96 on 34 closes (26 positive). At 15:06Z 9 of the 14 seated probes, $139.75 of their $168.94
        # of stake, sat on such families: crypto-alts-reversion (351 blocks, -0.0569; haghani-62, -63 and -r42c38c on
        # Alpaca), crypto-15m-lab-335592 (22, -0.2777), crypto-15m-doge-flat-spot-no (35, -0.6226),
        # crypto-15m-prior-window-reset (25, -0.7019), crypto-strikes-vol-shock-upside (26, -0.2168) and
        # prices-favorites (23, -0.2225). 6 is the House's breeding line (`game.json` `economy.losing_family_min_blocks`).
        # Absent, a probe is seated on any family's record, as before.
        "family_probe": {"losing_min_blocks": 6, "reseat": "gain_since_demotion"},
    },
}


def digest(constitution: dict[str, Any] | None = None) -> str:
    """The SHA-256 of the constitution's canonical JSON."""
    text = json.dumps(constitution or CONSTITUTION, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: What does NOT govern real money: the version, the research budgets, and the two risk-free
#: rules (the replay gate to a paper seat, and death on paper). Everything else -- order caps,
#: tuition, the real-money rungs, the screen that promotes to money, drift, death on money -- is.
RISK_FREE = (("version",), ("budgets",), ("ladder", "replay"), ("ladder", "paper_death"))


def money_digest(constitution: dict[str, Any] | None = None) -> str:
    """The SHA-256 of the rules that govern real money. The owner's live-trading grant pins this,
    not `digest()`: tuning the risk-free rungs must not silently revoke real-money authorization,
    and changing any money rule still must."""
    import copy

    rules = copy.deepcopy(constitution or CONSTITUTION)
    for path in RISK_FREE:
        node = rules
        for key in path[:-1]:
            node = node.get(key, {})
        node.pop(path[-1], None)
    return digest(rules)


#: Grants recorded before the money digest existed pinned the whole constitution. Such a grant
#: stays valid only while the money rules are EXACTLY those in force when it was granted:
#: {full digest at grant: money digest of that same constitution}.
LEGACY_GRANT_DIGESTS = {
    'bfdbbf8567205153a18eed023819e9bf52e5d989dae5d113d60fd5c1a1e5fad1':
        'c72854cc5ede3b7f5cab0cdcfb6345714c105e111619e6b68d1fb0ccad6cc985',
}


#: Pinned by `league/tests/test_constitution.py`. Changing the constitution means changing this
#: line too, in a commit the owner makes: CI refuses any other author's change to this file.
PINNED_DIGEST = '38a57fe98b837c60007a86459090de14bee177c74cd83e58d718002de8986158'

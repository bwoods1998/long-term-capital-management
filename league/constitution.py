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
import re
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
        # since Sept 21 (archive/docs/research/queries/2026-09-23/A8-haircut.py and .out), + adverse, - better:
        #   crypto 368 fills, $12,148: notional-weighted mean -3.13 bps (buys -0.01, sells -6.63);
        #   equity 136 fills, $4,005: -0.21 (buys -0.17, sells -0.26), at the touch;
        #   option  46 fills, $982: -21.15 (buys -15.10, sells -32.84; a few limits filled far through).
        # Each class is charged the larger of the aggregate and the round-trip reading (half of the
        # buys' plus the sells' optimism: both fills of a position overstate it), rounded up to a
        # whole bp, never below 2: crypto 3.32 -> 4, equity 0.22 -> 2, option 23.97 -> 24. Options are
        # TIGHTENED from 10 (evidence honesty cuts both ways); crypto and stocks are loosened to what
        # was measured, since 10 a side was 3x crypto's optimism and 50x the stocks'. A plain number
        # still charges every class (the rollback form), and a class not named pays the largest rate.
        #
        # `option_spread` (row O5 of the options-desk run's money table, archive/docs/goals/LTCM_OPTIONS_DESK.md, Sept 25, 2026;
        # 24-60 bps a side): a level-3 STRUCTURE's fill (`league/structures.py`: one held instrument whose `market_id` names
        # its type and legs) pays this rate a side on its held notional, on every Alpaca practice book a structure trades
        # on (`allocator.HAIRCUT_BOOKS`: `alpaca-paper`, and the House's `options-shadow`, whose fills the plan's row says
        # "must stay conservative"), not the single contract's 24. 60, the top of the row, until it is measured from the
        # first 30 or more practice structure fills against the structure's touch at intent time: by 17:31Z Sept 25 the
        # shadow book had filled 4 structure opens and closed none (the run record's watch), so no rate can be measured
        # yet. A class the table does not name still pays its largest rate (`allocator._haircut_rate`), now 60.
        "evidence": {"paper_weight": 0.5, "alpaca_paper_haircut_bps": {"crypto": 4, "equity": 2, "option": 24, "option_spread": 60}},
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
        # contracts the book refused (archive/docs/proposals/2026-09-23-alpaca-stocks-and-level-3-options.md,
        # blocker 6). At $80 one $40 contract fits under half the stake, inside the $500 Alpaca
        # envelope and under the $75 order cap.
        "option_bunt_usd": "80",
        # ---- Promotion on proof: the close-the-gaps run, Deploy A (archive/docs/goals/LTCM_CLOSE_THE_GAPS.md,
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
        # `alpaca_equity` (row M4 of the forward-first run, Sept 25, 2026: $25-60 for stock and ETF programs; crypto
        # stays at `alpaca`, options at `option_bunt_usd`): a STOCK or ETF program's real stake at Alpaca -- one whose
        # desk trades equities (`niches.json` asset_class "equity"), or an open desk's program whose NEEDS name only
        # stocks -- is this much, probe or bunt: a proven family's bunt is never staked less than an unproven family's
        # probe of its class, as `option_bunt_usd` holds for an options bunt. The position cap stays half the stake
        # ($25), under the gateway's $68.18 Alpaca order cap. As with options (`Allocator.target_stake` rebinds the class's
        # bunt), the $50 is also the base a stock program's bunt grows from (`bunt_growth`: up to $62.50) and its agent-level
        # swing is sized on (`swing_stake`, $50 x E^2: $112.50 at E 1.5 against $56.25 on $25), under `max_share_of_venue`
        # and the gateway's order cap; a stock FAMILY's swing still starts at `start_multiple` x the $25 `bunt_usd`
        # (`_family_base_stake`), so its first step is no raise over the $50 bunt (disclosed by the Deploy B money review,
        # Sept 25, 2026: the swing needs 8 real stock trades, E 1.25 and 5 real dates, and no real stock has ever traded). Evidence (the plan's gap 3, Sept 25, 2026): no real stock
        # has ever traded on this floor; equity practice fills are measured 0.21 bps adverse (A8, 136 fills), so the
        # 2 bps haircut on a $25 fractional position cannot move W, and the proven megacaps-chip-demand-relay's
        # capacity was measured at a $12.50 position that understates liquid names.
        "probe_bunt_usd": {"kalshi": "10", "alpaca": "25", "alpaca_equity": "50"},
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
        # observation on the T0 snapshot, archive/docs/goals/LTCM_CLOSE_THE_GAPS.md): "at_risk" measures an event
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
        # proven and ready to swing). Effect at T0 (archive/docs/runs/2026-09-24-close-the-gaps.md), the same states
        # as Deploy A's: weather-favorites unproven (2 losses in 16; loss-rate bound -0.2112 a dollar at risk);
        # sports-central-run-under proven (bound +0.1423: 6 of 11 practice events won at about even money after
        # a 7% taker fee, its winners carrying twice its losers' dollars; weighed alike it was -0.1234); every
        # other family unproven. "account" restores Deploy A's unit exactly.
        "family_proven": {"min_independent_settlements": 10, "practice_weight": "0.5", "real_weight": "1",
                          "confidence": "0.8", "lopsided_gate": True, "unit": "at_risk", "reference_share": "0.01"},
        # `proven_family_member` (row M3 of the forward-first run, Sept 25, 2026; C3): a living member of a PROVEN (or
        # swinging) family on practice, with at least `min_practice_closed` closed practice trades of its own and W_paper
        # at or above `min_w_paper`, is seated as a BUNT on its family's proof -- no E >= `bunt_at` needed -- best W_paper
        # first, while the family holds fewer than `game.json` `economy.proven_family_members` (4) seats on real money,
        # and ONLY when (the main session's decisions of 07:11Z, the run record's "The proven sports family, verified"):
        #   - the family's POOLED proof spans at least `min_distinct_dates` distinct settlement dates (each event's own
        #     date, `families.event_day`): the one proven sports family's 25 events lie on 3 slate dates inside one
        #     five-day MLB under-regime, and the same mechanism lost 12-14% a dollar over Sept 4-24 on Kalshi's public
        #     record; one observation per date gives an 80% bound of -0.0665. A count of events cannot tell a regime
        #     from an edge, and more members on the same slate are exposure, not evidence;
        #   - the member runs the PROVEN CODE (`same_code`): the program (`code_sha256`, PARAMS apart) that entered a
        #     majority of the family's settled observations (`Allocator.proven_code`). meriwether-h2d625d-4 rewrote
        #     itself at 02:37Z Sept 25 into a KXWNBAGAME favourite maker and kept the family's name;
        #   - its E is at or above the bunt band's exit line (`bunt_at` x `hysteresis`): a member the exit sent back is
        #     not re-seated on the family's proof until its own E is back over it.
        # Measured on the T0 snapshot (04:23Z Sept 25): megacaps-chip-demand-relay is proven on practice (13 events, bound
        # +0.0010), all 13 entered by mcentee-hddb4ae's current code, at W_paper 1.0036 -- on 2 trading dates (Sept 23
        # and 24), so it waits for 3 more; sports-central-run-under's pooled proof spans 3 slate dates, and its members
        # -3, -5 and -6 (the proven code) have no closed practice trade. Nobody is seated by it at T0.
        # The same `min_distinct_dates` holds the STAKE of a thin proof (the Deploy B money review, Sept 25, 2026; no new
        # key, `Allocator.thin_proof`): a family proven on fewer dates while its REAL record alone is short of
        # `family_proven.min_independent_settlements` stakes, gates and lets take its members as probes, not bunts. C8's
        # re-key of the T0 snapshot made two single-program 15-minute BTC taker families proven on 2 practice dates (n 20,
        # bound +0.0927; n 14, +0.0182), and Deploy B's first pass seated both agents as $30 Kalshi bunts; with it they are
        # probes. sports-central-run-under (3 dates, real n 11) keeps its bunt, as decided at 07:11Z.
        "proven_family_member": {"min_practice_closed": 1, "min_w_paper": "1.0", "min_distinct_dates": 5, "same_code": True},
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
        #
        # Row M1 of the forward-first run (Sept 25, 2026; C1): `min_real_settlements` 15 -> 10 (the table's 10-15;
        # `entry_every` 5, `entry_confidence` 0.9 and the loss-rate gate at every look unchanged: the looks are 10, 15,
        # 20, ...), so the one proven family meets its entry look in a day, not three; AND a stricter gate carried in the
        # same row, `min_distinct_dates` 5: every swing look -- the entry (on the first that many real events), the hold
        # and so every doubling of the ramp (the whole real record), and the agent-level swing (`swing_at`: its entry and its
        # hold, `Allocator.swing_dates`) -- needs the family's real events to span at least 5 distinct
        # settlement dates, each event's OWN date (`families.event_day`: the date code of its Kalshi event ticker, the
        # slate the game was played on; the UTC date of its close where the ticker carries none, an Alpaca trade's).
        # Not the UTC date of the settlement: a night slate settles across two UTC dates (the real Sept 24 MLB slate
        # settled one event on Sept 24 UTC and five on Sept 25), and one regime must not count twice. Evidence (the main
        # session's verification of 07:11Z, the run record's "The proven sports family, verified"): the one proven
        # family's 25 events lie on 3 slate dates inside one five-day MLB under-regime, its real 11 on 2; rebuilt from
        # Kalshi's public prints the same program lost 12-14% a dollar over Sept 4-24 (14 of 21 days negative); one
        # observation per date is n 3, mean +0.1507, 80% bound -0.0665. A count of events cannot tell a regime from an
        # edge. On the T0 snapshot the look at 10 reads the first 10 real events (Sept 23 and 24 slates: 2 dates) and
        # does not pass (its 90% bound -0.1187 too); the looks at 15 and 20 need 5 slates among their first events. The
        # auditor's packet for an entry look is prepared `game.json` `audit.pre_pack` (8) real settlements into the
        # count before it (8 for the look at 10, 13 for 15), when the dates can still be met, so a passing look is not
        # delayed by its audit; an approval prepared so licenses that look and later ones, and lapses at a look that
        # does not pass (`Allocator._swing_approval`).
        "family_swing": {"min_real_settlements": 10, "min_distinct_dates": 5, "start_multiple": 2, "doubling_every": 10,
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
        # Row M2 of the forward-first run (Sept 25, 2026; C2): "probe_may_take" -- a PROBE, the smallest stake, may enter
        # as a taker, one position of at most `position_share_event` of its stake ($2 of a $10 probe: the book's position
        # cap, `allocator.limits_for`) -- in all, what it holds that it took and its crossing buys counted
        # (`Book._probe_taker_room`), and only as a probe: not while its family's record cannot be read, nor while its
        # account is sized above a probe's (the Deploy B money review, Sept 25, 2026: the per-market cap alone let a $10
        # probe take $2 on each of five events) -- a bunt and a swing stay post-only until the family's pooled taker record is
        # positive. `taker_proof_min` (the same row, 5-10): that record is positive from this many independent taker
        # events with its honest lower bound above zero (`families.family_record`'s taker side; the proof's 10 before).
        # Evidence: in the Sept 25 01:42-02:12Z watch the over-under family's taker entry was refused on a taker record
        # of +$30.75 on 3; 22+ real entries were refused by maker-until-proven in the Sept 24 session; the real fill rate
        # was 10% (72 of 694 orders in 24 h). Pocket change may take the price; a taker record cannot be earned by an agent
        # that may not take. "maker_unless_family_taker_positive" restores the rule for probes too.
        "real_entry_liquidity": "probe_may_take",
        "taker_proof_min": 5,
        # `real_book_dust_usd` (row "H4 allocator.real_book_dust_usd" of the forward-first run, Sept 25, 2026:
        # $0.25-1.00; `league/book.py` reads it, and treats a value outside `book.REAL_BOOK_DUST_BOUNDS` as no
        # key): a REAL book's cash shortfall under this, with every position agreeing, no order in doubt and no
        # settlement awaited, that the regulators' fees Alpaca takes at option and stock fills and lists only
        # later can explain (`Book._explain_real_cents`), is booked to the House row as dust with an error alert
        # naming it -- never a freeze and never an agent's record. Over it, or unexplained, the freeze stays for
        # the owner. Evidence: the real Alpaca book froze on -0.0308 at 18:23Z Sept 24 (an option buy's OCC,
        # ORF and CAT cents, all taken at the fill and listed hours later) and on +0.0108 from 02:49Z to 04:11Z
        # Sept 25 (the book's own rounding of resting bids, fixed in the book), each freeze refusing every
        # Alpaca real entry. Absent: a real book freezes on any difference over its per-fill tolerance.
        "real_book_dust_usd": "0.50",
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
        # (archive/docs/research/queries/2026-09-24/R5-family-probe.py, on the 15:06Z snapshot): of the allocator's 21
        # promotions to real money since Sept 23 00:00Z, 11 were onto families whose pooled forward record was negative
        # over 6 or more active blocks; they realized -$8.12 on 22 closes (8 positive) and no stay ended positive. The
        # other 10 made +$28.96 on 34 closes (26 positive). At 15:06Z 9 of the 14 seated probes, $139.75 of their $168.94
        # of stake, sat on such families: crypto-alts-reversion (351 blocks, -0.0569; haghani-62, -63 and -r42c38c on
        # Alpaca), crypto-15m-lab-335592 (22, -0.2777), crypto-15m-doge-flat-spot-no (35, -0.6226),
        # crypto-15m-prior-window-reset (25, -0.7019), crypto-strikes-vol-shock-upside (26, -0.2168) and
        # prices-favorites (23, -0.2225). 6 is the House's breeding line (`game.json` `economy.losing_family_min_blocks`).
        # Absent, a probe is seated on any family's record, as before.
        # Row M5 of the forward-first run (Sept 25, 2026; C5): `reseat` "gain_since_demotion" -> "bound_since_demotion": a
        # hold turns only when the family's record since the demotion has a one-sided `reseat_confidence` (80%) lower bound
        # above zero over `losing_min_blocks` (6) or more active block periods -- one observation an hour (or a day for a
        # daily program), the mean of the family's active blocks in it (`families.bound_gaining`), as the family's proof
        # takes one observation an event: members of one program in one hour are one observation, not six. Evidence (the
        # Sept 24 report's decision 1; the T0 snapshot): the zero-edge crypto-alts-reversion (its whole forward record
        # +0.0570 over 423 active blocks at T0, an 80% bound of -0.00006 a block; pooled proof bound -0.018) flipped back
        # in at 21:00:53Z Sept 24 as its forward record crossed zero (+0.0003 over 371 blocks; +0.0113 over 375 by 21:30Z)
        # and the 18:47Z demotions' hold turned on six blocks since, +0.0101 -- two hours, five of the blocks written in
        # the same second. Read a period at a time that hold waited until 01:02Z Sept 25 (6 periods, bound +0.0012); at T0
        # six Alpaca probes ($150) sat on the family. The deploy folds every demotion on the ledger again under the new
        # rule (`Allocator._fold_demotions`): at T0 crypto-15m-doge-flat-spot-no (14 blocks since, +0.0145),
        # crypto-15m-lab-335592 (16, +0.0626) and crypto-15m-prior-window-reset (9, +0.0371) had turned on sums whose
        # bounds are below zero and hold again. It changes no seated probe: a hold keeps new probes out.
        "family_probe": {"losing_min_blocks": 6, "reseat": "bound_since_demotion", "reseat_confidence": "0.8"},
        # `family_key` (row C8 of the forward-first run's money table, Sept 25, 2026; `league/families.py` reads it):
        # "mechanism": a family is keyed by its program's MECHANISM -- its code beyond its PARAMS literal
        # (`parameters.same_logic`'s line, `lab.mechanism_digest`) with the venue, series and symbols it trades. A child
        # whose program is its parent's beyond PARAMS stays in its parent's family; a program whose code differs beyond
        # PARAMS, or whose venue, series or symbols differ, founds a family of its own, and so does a founder whose label
        # is another mechanism's; an agent that rewrites itself in place moves to its new program's family from that
        # ledger position on. Every proof, probe gate, bunt and swing above reads the family, so a mechanism is proven
        # only by its own settlements. The labels born before it are re-keyed once at the deploy by `agent.family` rows
        # (the lineage stays on each birth row). Evidence (the Sept 24 report's decision 2; the T0 snapshot, 04:23Z
        # Sept 25): 343 of 647 births carried a label whose founding program was another mechanism and 148 agents
        # rewrote themselves into another one; meriwether-h2d625d-4 kept sports-central-run-under's name -- the one
        # proven family with real money on it -- after it rewrote itself into a KXWNBAGAME favourite maker at 02:37Z,
        # and -2, a CFB and soccer moneyline file, was born under it. Re-keyed on that snapshot (781 rows, 424 agents),
        # sports-central-run-under keeps its record to the cent (n 25, bound +0.0344, real n 11, +$16.39 real: all 45
        # of its fills are the founder's), and megacaps-chip-demand-relay's (n 13, bound +0.0010, practice only) moves
        # whole to the program that earned it, mcentee-hddb4ae's eleventh rewrite. Absent: the label a birth carries.
        "family_key": "mechanism",
        # ---- Real structures (rows O1-O4 of the options-desk run's money table, archive/docs/goals/LTCM_OPTIONS_DESK.md, and the
        # owner's amendment of 06:01Z Sept 25, 2026, item 4 "real money follows proof, fast"; this run's money-digest
        # change 1 of 2, Deploy G; O5 is `evidence.alpaca_paper_haircut_bps.option_spread` above). The owner, 18:15Z Sept
        # 25: "i want rapid recursively learning loop that has paper trading and production trading as soon as possible
        # based on actual progress made by the agents in the game". Real money follows a structure FAMILY's own record,
        # through the allocator, inside every cap; the bounds are `allocator.SPREAD_BOUNDS` and `league.ci` refuses a
        # value outside them (`Allocator.spread_line`, `allocator.spread_rule`).
        #
        # `option_spreads_real` (O1, false until O4's line is met by at least one family, then true): the switch. While
        # false no structure agent (the options desk's agents whose NEEDS say "structures": true) is promoted to real
        # money by any route, the House sends no structure OPEN to a real book, and a structure agent still on real money
        # is lent nothing more and goes back to practice once flat. True, by a digest change the grant re-ratifies, in the
        # same deploy that sets the gateway's `OPTION_STRUCTURES_REAL` to exactly `option_spread_real_types`
        # (`league.ci` refuses a tree where the two disagree). A close is never refused by it: it only takes risk off.
        "option_spreads_real": False,
        # The types a real structure may be, when O1 is on: the debit vertical, the one type the plan authorizes on the
        # cash account. A credit type (or any other) joins only with the owner's explicit confirmation, recorded in
        # `allocator.SPREAD_REAL_TYPES_AUTHORIZED` (the amendment's credit grant arrived with its lines cut, and is held).
        "option_spread_real_types": ["debit_vertical"],
        # `spread_probe_usd` (O2, $80-150): a structure agent's real stake as a probe (and the floor of its bunt, as
        # `option_bunt_usd` is a single contract's). $150, the top of the row (the owner: "be bold inside the
        # envelope"): two $30-75 verticals at once, every order inside the gateway's $75 cap, the grant's Alpaca capital
        # and the envelope's headroom unchanged (a probe is seated only where the headroom takes it).
        "spread_probe_usd": "150",
        # `spread_position_share` (O3, 0.5-1.0): a structure position's cap as a share of the stake, in MAXIMUM LOSS (the
        # held price S x 100 x structures, `league/structures.py`), not the premium of a leg: a vertical cannot lose more
        # than it cost. 1.0: a probe may hold its whole stake at risk, one order at most $75 (the gateway's cap, which
        # meters a multi-leg order at its maximum loss). The book's own rules still apply: `book.DEFAULT_RULES`
        # max_position_pct 0.50 holds ONE position to half the account's equity ($75 of a $150 probe) until the book
        # reads this row, so the whole stake is at risk only across two structures.
        "spread_position_share": "1.0",
        # `spread_probe_line` (O4): a structure family is probe-eligible when its POOLED record (`families.family_record`
        # `structures`: every member ever born, each for its stretch in the family, closed structures on its practice
        # books since each member's evidence cutoff, the O5 haircut paid) has at least `min_practice_closed` closed
        # practice structures with W_paper (the account-unit growth of those closes, pooled) at or above `min_w_paper`;
        # OR at least `replay_min_practice_closed` closed practice structure and a PASSED House replay on the options
        # history (`eval.trial`, of a program the family ran) with at least `replay_min_structures` structures and
        # out-of-sample growth above `replay_min_oos_growth`. R5 (`family_probe`: no probe on a losing family) applies
        # unchanged. Measured at 17:31Z Sept 25 (the run record's watch): 12 structure founders on practice, 4 structure
        # opens filled, none closed, and one founder's replay passed (options-gap-drift, out of sample -0.00024 a block:
        # not positive), so no family meets it yet. A structure is one closed trade: one flat sale of the held instrument.
        "spread_probe_line": {"min_practice_closed": 3, "min_w_paper": "1.01", "replay_min_practice_closed": 1,
                              "replay_min_structures": 20, "replay_min_oos_growth": "0"},
    },
    # ---- The options swarm's money table (the options-swarm run, Wave 5, Sept 26, 2026; the plan
    # docs/goals/LTCM_OPTIONS_SWARM.md, "Money"). The owner (Sept 25, 2026): "The money I have in alpaca can be all
    # lost ... be very bold and ambitious here in our approach." Every row below is the plan's DEFAULT, inside the
    # "allowed range this run" that `OPTIONS_MONEY_BOUNDS` pins (`options_money_problems`; `league.ci` refuses a tree
    # outside them). `league/live/money.py` is the one reader. Sizing is by MAXIMUM LOSS, never premium (the old $75
    # premium cap goes). Shares are of the SIZING EQUITY: the lower of the Brokerage Account's equity and the grant's
    # capital (`league/live_trading.py`). Deposits and withdrawals are never profit: the daily stop's base and the
    # drawdown's peak net them out (`league/live/money.py` `Stops`).
    #
    # - `real_types`: what real money opens, the five types the venue closes in ONE order; the others trade shadow only
    #   until a paper round trip proves them. `credit_types` open for real only once the account reads
    #   `credit_min_equity_usd` of equity (Alpaca's limited margin under $2,000: debit structures only) or a real credit
    #   order has been accepted.
    # - `probe`: a Candidate that passed the holdout, trades a real type, and whose typical maximum loss fits the cap at
    #   the current equity (else shadow-only, the reason recorded). `max_loss_share` a structure, `open_per_family`
    #   structures, `family_share` in all; `floor_usd`: one contract whose maximum loss is at most this, whatever the
    #   percentages, so a small account can still trade (and the family's own total may reach it).
    # - `sized`: a forward record (nightly + shadow + real) of at least `min_trades` trades with a mean return on maximum
    #   loss above zero and its `confidence` one-sided lower bound above zero: `kelly_fraction` of Kelly on the LOWER
    #   bound, a structure at most `max_loss_share`, the family at most `family_share`. Only a Probe with at least
    #   `min_probe_real_trades` real trades and `min_probe_sessions` whole sessions at Probe (the review of #362).
    # - `book_share`: every real structure's open maximum loss together. `daily_stop_share`: the day's realized plus
    #   marked loss against start-of-day equity: no new real entry that day. `drawdown_stop_share`: from the peak since
    #   the reset: real money paused (exits go on, the owner told, the Gym keeps running) until the owner releases it.
    # - `tuition`: 1-lot real orders from validation-passing families before their holdout, only to measure real
    #   multi-leg fills, never evidence: at most this much maximum loss a day and a week.
    # - `order_path`: the House's own order governor (under the venue's professional-customer line and rate limits);
    #   `gateway`: the caps the Cloudflare gateway enforces from its own reading of the account (repeated here so the
    #   House refuses first and says why).
    # - `calibration`: the D3 real-fill calibration round trips (`league/live/calibration.py`): 1-lot SPY and QQQ debit
    #   verticals the House itself sends at mid (then one tick worse) and closes, only to measure real fills, never
    #   evidence for any family: a strict bound on the day's possible loss, `day_usd` (a new open goes only while today's
    #   realized calibration loss, net and floored at zero, plus what is still held or working, plus its own maximum loss
    #   stays within it; a closed round trip frees its maximum loss).
    # - `house_test`: the House live test (`league/live/house_test.py`, family `house:rebound-live`, not a swarm family):
    #   one frozen, pre-registered program traded 1-lot with real money only to measure its real fills and real P&L,
    #   never evidence, never a promotion. The owner, Sept 28, 2026, asked whether to add it as a new shadow-to-real
    #   route: "proceed as you see best fit, you are in the best position possible to make these decisions"; the
    #   operator decided yes on these terms, fixed in a private pre-registration whose sha256 is
    #   c73e2d262b8d2e9493b53c427400ba7adc37490db8c981ddd96644fdb6977954.
    #   One structure's maximum loss with its fees at most `structure_usd`; at most `open` held or working; its realized
    #   loss plus what is held or working plus the new open at most `envelope_usd` at every open; no new open ever again
    #   once its realized loss reaches `stop_usd`; new opens only through its `sessions`th session and while its round
    #   trips are under `round_trips`. D2 and every promotion rule are unchanged.
    # - `incubator`: THE INCUBATOR (`league/live/incubator.py`), a new shadow-to-real route. The owner approved it on
    #   Sept 29, 2026, 14:51:12Z ("Yes, open the incubator"), and the reading was settled on Sept 30, about 14:35-14:45Z:
    #   families that pass Train, pass the drift screen alone and show positive live practice (the gate's review and
    #   audit still required) trade ONE lot of any approved real structure, at most `max_loss_usd` of maximum loss each
    #   (with its open and close fees), at most `max_open` held or working at once, and the route stops for the ISO week
    #   once its net realized loss reaches `week_loss_usd`: held as an envelope (this week's net realized loss, plus what
    #   is held, plus what is working, plus the new open, at most `week_loss_usd` at every open), so the weekly figure is
    #   a true bound apart from residuals (broker fees above the book's estimate, a broken structure closed leg by leg).
    #   `contracts` is the one lot. Positive live practice is pre-registered: one first look per practice cohort, at the
    #   first session pin with at least `min_sessions` completed sessions and `min_trades` program-closed practice
    #   trades under the current evaluator, passing only with decision coverage at least `min_coverage` and realized
    #   practice P&L above $0 over program closes, over all closes, and over all closes plus the open mark; a failed
    #   first look is final. Incubator orders are real P&L (Profit) and NEVER strategy evidence: never a forward row,
    #   never a band move, never a promotion. D2 is the only route to Probe and Sized. Expected value is negative until
    #   a family has a real edge: at most about $650 a month on average ($750 in a five-week month) plus residuals.
    #   THE INCUBATOR CAP (Oct 8, 2026; Claude's decision under the owner's goal of Oct 7, item 4, which allows up to 10%
    #   of equity at risk per Probe position, about $129 at E = $1,288): `max_loss_usd` $50 -> $75, a loosening, so
    #   lot-priced single-name programs can open at all (one-lot units at or under $50 -> $75 in the active cohorts' Gym
    #   Train trades: semis-lead 4% -> 71%, smci-mara 40% -> 71%, opening-range 40% -> 62%, china-tech 55% -> 77%,
    #   peer-skew 50% -> 71%). `week_loss_usd` ($150), `max_open` (4) and `contracts` (1) are unchanged, so the week's
    #   bound and the month's ($650 on average, $750 in a five-week month) are the same and at most two $75 units are
    #   ever open at once (three $50 ones before it). The same row is the family's cap on what it holds and works, so one
    #   family may now have $75 open (from $50). Its cost is use of that same envelope: replayed on those cohorts with no
    #   edge after costs (-8% of maximum loss a trade), the expected real loss per first-look pass rises from about $0.40
    #   to $2.45 at today's practice windows, from $2.22 to $25.53 at 30-session windows and from $5.52 to $26.59 at
    #   40-session windows; the worst simulated pass from -$272 to -$419 at 30 sessions (several weeks, each within the
    #   $150). Alone it opens nothing: on this tree no cohort holds a Train-and-drift mark (the tournament's drift screen
    #   is off), and in the incubator audit's replay (Oct 8) 11 of 12 cohorts never reach the first look's 10 program
    #   closes inside today's windows.
    #   Setting `max_open`, `week_loss_usd` or `max_loss_usd` to 0 stops the route (a tightening: a new digest and a
    #   ratification).
    #
    # THE SPRINT (docs/goals/LTCM_SWARM_SPRINT.md, Sept 26, 2026; the owner's decisions D1, D3 and D4, all "yes"): the
    # table at the bold end of the plan's ranges -- Probe 5% a structure with a $100 one-contract floor, the family 15%,
    # the book 90%, the daily stop 35%, the drawdown stop 60%, tuition $200 a day -- and the calibration's $50 a day (D3).
    # Real types under $2,000 of equity are exactly the four debit types the venue closes in one order: debit verticals,
    # long butterflies, and long calls and puts (one contract bought to open, sold to close; B4). The credit types are
    # NOT real types now: they return (with the gateway's list, in one deploy) only once a deposit takes equity to $2,000
    # and the grant is ratified again. The gateway's per-order equity share is 25% so a $100 Probe fits at $481.63 of
    # equity (its $1,000 absolute cap unchanged; never above funded money).
    #
    # THE FAST LANE (Oct 7, 2026; the owner's goal of Oct 7, item 4: "You may set Probe sizing up to 10% of equity at
    # risk per position and a Probe loss budget up to $400 in total"): a Probe position is ONE structure (`contracts` 1)
    # whose maximum loss with its open and close fees fits `max_loss_share` (10%) of the sizing equity E, replacing 5%
    # and the $100 one-contract floor (`floor_usd` 0). At most `max_open` Probe positions held or working at once (3 at
    # the fast lane, 8 since release L-D, below), and a Probe loss budget of `loss_budget_usd` ($400) in total at the
    # fast lane (in any rolling `loss_window_sessions` (20) sessions beside `loss_total_usd` in total since release L-D,
    # below: $400 at L-D, $800 since THE PROBE TOTAL AT $800 of Oct 10, 2026, the last paragraph before the table):
    # realized Probe losses since the fast lane, read by `loss_basis` (GROSS at the fast lane, each closed position a
    # Probe family opened counting its own loss with no gain offsetting it; NET since release L-D, below), plus the
    # maximum loss of every real position held or working (a Sized one too: a tightening), plus the new open; an open
    # that would breach it is refused, and exits go on (`league/live/money.py` `plan_open`, `league/live/real.py`
    # `probe_tally`, `probe_realized`). A tuition structure is held within the Probe's cap too (code, `plan_open`);
    # tuition stays outside the count and the budget, at its own caps. Each 10% position fits the gateway's per-order
    # cap, min($1,000, 25% of E), and its day cap (100% of E). At E = $1,288.40: the Probe cap $128.84, the per-order
    # cap $322.10, the day cap $1,288.40, the book cap $1,159.56, the daily stop $450.94. Setting `max_open` or
    # `loss_budget_usd` to 0 stops Probe opens. The kill switch, the daily stop and the drawdown stop are never loosened
    # by it; Sized rules are unchanged.
    #
    # RELEASE L-D (Oct 9, 2026; Claude's decision under the owner's goal of Oct 7, item 4: "You may set Probe sizing up
    # to 10% of equity at risk per position and a Probe loss budget up to $400 in total", and its item 5: every loosened
    # rule reported with its cost; the plan of Oct 9, "L: Release L-D", and its critic; and the owner's goal as he
    # re-set it on Oct 9, about 06:20Z, item 4, for the budget's two figures, the last row below). Five rows, none of
    # the 10% cap: three loosen how the Probe stage is run (NET, 8 slots, DM1), and the rolling budget's two, as set on
    # Oct 9, add a 20-session envelope beside a $400 total (a tightening of NET alone). Each has a value that restores
    # the rule before it: the CON-only rollback is `loss_basis` "gross", `max_open` 3, `demotion` "dm0",
    # `loss_total_usd` "400" (the value set on Oct 9; "800" since Oct 10, below) and `loss_window_sessions` 2000, one
    # owner deploy that moves the money digest (the standing grant re-ratifies at the House's start) and never the
    # execution fingerprint (no evidence reset). The figures are MONEY's simulation of Oct 9 (the Probe stage alone,
    # U10% of E, holds of 2, 3, 5 and 8 sessions, no edge unless said; "Done" is 30 real closes, consistent and net
    # positive, within the weeks named) and its critic's re-runs of MONEY's pinned paths; they are a model's, not a
    # measurement of this account.
    #
    # - `loss_basis` "net" (allowed exactly "gross" and "net": `OPTIONS_MONEY_CHOICES`; anything else, "Net" or "" too,
    #   is refused and nothing trades on it). The realized part of the budget is max(0, -(the sum of the cash of every
    #   CLOSED position a Probe family opened)), from inception (the Probe mark of the fast lane), in place of GROSS,
    #   the sum of each such position's own loss. It REVERSES the fast lane review's deliberate GROSS choice of Oct 7
    #   ("a net figure let a Sized gain or a Probe gain refill the budget"): a Probe gain now offsets Probe losses; a
    #   Sized gain never does (a Sized position carries no Probe mark). The net Probe loss still never exceeds the
    #   budget's figures ($400 in any rolling 20 sessions and `loss_total_usd` in total since the last row below, $400
    #   at L-D and $800 since Oct 10; $400 in total before it), over every window and not only at each open, because the
    #   window's realized figure is its WORST NET STRETCH (the last row below: a Probe gain offsets only the Probe
    #   losses closed before it there), plus residuals: broker fees above the book's estimate, a broken structure closed
    #   leg by leg. Cost (MONEY, U10%-M3, no edge, 8 weeks): P(net <= -$360) 0.19 -> 0.27, mean net -$8 -> -$14 (as the
    #   swarm traded, -$45 -> -$64); gain: P(Done) averaged over the holds 0.3% -> 2.6% (+5% edge). ITS MAIN EFFECT (the
    #   critic, B2, MONEY's pinned paths over 12 weeks at U10%-M8-net-DM1): because NET counts from inception, Probe
    #   gains refill the budget. At 2 / 3 / 5-session holds, P(gross realized Probe losses > $400) 0.65-0.72 / 0.56-0.62
    #   / 0.46-0.50 (p95 gross $2,005-2,088 / $1,709-1,744 / $1,318-1,338); P(the Probe's peak-to-trough realized
    #   drawdown > $400) 0.45-0.48 / 0.40-0.42 / 0.32-0.34 (worst $2,218-2,322 / $2,134-2,385 / $1,923-2,192); P(net
    #   Probe < -$400) at most 0.5% / 0.8% / 2.5%. Under GROSS every one of these stays at or under about $440. Of the
    #   three readings (GROSS, a high-water mark, NET) NET is the loosest: 12-week Done with 3 programs at Probe,
    #   3-session holds, zero edge: GROSS 0.5%, high-water mark 3.3%, NET 12.9% (+5% edge: 0.7%, 4.7%, 15.6%), so most
    #   of NET's gain is the re-risking of earlier Probe winnings. Chosen: NET (Claude, Oct 9: the only reading under
    #   which 30 real closes are reachable; the account's daily and drawdown stops still bound the whole account). The
    #   owner's goal as re-set the same morning names the budget net too ("realized Probe losses net of Probe gains",
    #   the last row below).
    # - `max_open` 8 (from 3; its bound 0-3 -> 0-8): the count of slots, not the dollars. "Why N = 3" was 3 x 10% = 30%
    #   of E inside the 35% daily stop; now the envelope (net realized + every real position's open maximum loss + the new
    #   open <= $400) keeps open Probe risk at or under $400, below the daily stop's $451.27 at E = $1,289.34. The dollars
    #   bind before the count: three $129 units fit, eight $50 units. Below E = $1,142.86 ($400 / 0.35) the $400 is more
    #   than the daily stop's line, which 3 x 10% never was at any E: the daily stop then stops new entries only after
    #   the day's loss, and the 60% drawdown stop is unchanged. The routes that keep room for Probe opens (the incubator,
    #   the House live test, the calibration) keep min(`max_open` x the Probe's cap, `loss_budget_usd`)
    #   (`money.probe_room`): $386.80 at 3 and $400.00 at 8 at E = $1,289.34, never the $1,031.47 that 8 x the cap would
    #   claim (the critic, B1: that refused every incubator open). Cost (MONEY, no edge, 8 weeks): P(net <= -$360) 0.30 ->
    #   0.35, P(net < -$400) 2.1% (through Sized, outside the budget); gain: Done 3.3% -> 6.3% (averaged over the holds,
    #   +5% edge).
    # - `demotion` "dm1" (allowed exactly "dm0" and "dm1": `OPTIONS_MONEY_CHOICES`; "dm0" is fast lane v2's D5 and the
    #   forward-negative demotion, code for code). Under "dm1" a family at Probe or Sized (a Candidate keeps every check of
    #   "dm0", the forward-negative one included, before its first Probe) no longer loses its band by D5's loss leg (-3 x
    #   its mean maximum loss) nor by a negative forward record: it is demoted (sticky, exits only, D5's mechanics) when
    #   its real trades are 10 or more and their summed return on maximum loss is below -1.645 x sigma x sqrt(n), sigma
    #   the sd of that return in the banded version's Validation run, else its forward record's at 10 or more trades,
    #   else 2.0 (`league/live/money.py` `demotion` and its constants); the live path keeps the version it demoted, so a
    #   sigma that grows later never lifts it. D5's replay-gap leg and the real_bad hold are kept.
    #   It applies to every Probe or Sized family, alpha too (the live row carries no lane; no alpha family is near
    #   Probe). Cost (the critic, 4,000 bootstrap paths of 30 closes over the 29 cells the direction bar admits): DM1 fires
    #   within 30 closes 6.5-13% of the time at zero edge, 14-22% at -0.10 a dollar of maximum loss, 29-36% at -0.25
    #   (sigma the cell's own sd, then 2.0), against D5's 77%, 83% and 90%: a losing program trades longer, and the
    #   shared $400 envelope, not demotion, is what mostly stops it, so one bad program can spend every program's room.
    #   Before release D-1 writes the Validation sd, sigma is the forward record's own (its nightly, shadow and real
    #   days). MONEY (no edge, 8 weeks): P(net <= -$360) 0.27 -> 0.30; gain: Done 2.6% -> 3.3% (averaged over the holds,
    #   +5% edge).
    # - THE ROLLING PROBE BUDGET: `loss_budget_usd` ($400) is now a ROLLING figure, over the last `loss_window_sessions`
    #   (20) New York trading sessions, today included, beside the new `loss_total_usd` from inception, set to $400. The
    #   owner's goal as he re-set it on Oct 9, 2026 (about 06:20Z), item 4, verbatim: "Probe loss budget: $400 net in
    #   any rolling 20 sessions and $800 net in total (realized Probe losses net of Probe gains, plus the maximum loss
    #   of everything open)". Its $400 a window is read as a wall (the window's worst net stretch, below), and its $800
    #   as a ceiling: the total was set at $400 on Oct 9, a tighter setting inside it (the operator's decision of Oct 9,
    #   after the budget simulation's worst-stretch run, below), and is the ceiling itself, $800, since Oct 10 (THE
    #   PROBE TOTAL AT $800, below). The realized figure of each is `loss_basis`'s over the closed Probe positions it
    #   covers: the window's those whose New York close day is in the last 20 sessions (the repo's NYSE calendar,
    #   `ltcm.data.us_equity_session`: weekends, the computed holidays and the special closures; `league/live/real.py`
    #   `probe_window_start`), the total's every one. Under "gross" each figure is their losses summed. Under "net" the
    #   total's is max(0, -their summed cash) from inception, and the window's is its WORST NET STRETCH: the largest
    #   max(0, -(the summed cash of the closes on or after s)) over every session s of the window (`probe_realized`; the
    #   review of release L-D, Oct 9: with the window's plain net, a +$300 Probe close let $700 of later losses be
    #   admitted against it, and once the gain aged out the next 20 sessions held $700 net, every open having passed).
    #   So a Probe gain offsets only the losses closed before it inside the window, and "$400 net in any rolling 20
    #   sessions" holds over every 20-session window as an outcome (the last open whose position closes in a window was
    #   checked against that window's stretch up to it plus every position then open at its maximum loss), as the total
    #   does from inception, residuals aside (the row above). A Probe open goes only if BOTH the window's realized
    #   + every real position's open maximum loss + the open <= $400 AND the total's realized + the same open maximum
    #   loss + the open <= `loss_total_usd` ($800 since Oct 10; $400 at L-D); the refusal names the one that binds, and
    #   exits always go on (`league/live/money.py` `plan_open`). Bounds: the window 20-2000 sessions (a longer window is
    #   never looser, under either basis: it sums more losses under "gross" and has more stretches under "net"; 2000 is
    #   the rollback's, a window holding every close), the total $0-800 (the owner's ceiling: raising the total to $800,
    #   as Oct 10 did, is a constitution-only change, a money-digest move and no fingerprint move). Open Probe risk
    #   stays at or under $400 (the window's envelope alone caps every real position's open maximum loss plus the open
    #   there), so `max_open`'s reasoning above stands and `money.probe_room` stays min(`max_open` x the Probe's cap,
    #   `loss_budget_usd`). Cost, as set on Oct 9 (the $400 total; the $800's is below): the worst net Probe loss from
    #   inception stays $400, as under NET alone, and the window adds a second wall: no 20 sessions lose more than $400
    #   net, even after earlier Probe gains have refilled the total. A bad stretch that ages out of the window frees no
    #   room in the total; only Probe gains do. Measured (the budget simulation of Oct 9, its worst-stretch variants,
    #   seed 202610097, post-hoc, as traded, holds of 2 / 3 / 5 sessions): P(Done) 6.0 / 3.3 / 1.0% at 12 weeks and 11.1
    #   / 8.7 / 5.9% at 24 (with an $800 total: 7.0 / 3.7 / 1.1% and 14.0 / 10.9 / 7.2%); P(net Probe P&L below -$400
    #   within 12 weeks) 0.9-2.1% (with $800: 37.6-39.2%); P(the 60% drawdown stop trips by 24 weeks) 3.0-8.3% (with
    #   $800: 41-46%). The table, with the $400 total and no window beside it, is in the L-D section of
    #   docs/operations.md. Its rollback, `loss_window_sessions` 2000 (a window that holds every close since the fast
    #   lane) and `loss_total_usd` "400" (the $800 total's own rollback, below) with `loss_basis` "gross", is fast lane
    #   v2's single $400 budget, decision for decision (`league/tests/test_ld_release.py`); with "net" kept, the
    #   2000-session window's worst stretch is the Probe's drawdown from its high-water mark, so the $400 then binds as
    #   the high-water-mark reading, tighter than NET from inception.
    #
    # THE PROBE TOTAL AT $800 (Oct 10, 2026; Claude's decision, pre-registered privately as PREREG-T under the Probe
    # roster R5 already live, inside the owner's goal as he re-set it on Oct 9, item 4: "Probe loss budget: $400 net in
    # any rolling 20 sessions and $800 net in total"): `loss_total_usd` "400" -> "800", the owner's ceiling, a
    # loosening; and beside it, swarm-side, the program loss line (DONE-RULE-A1 A1.3, `dlane.program_loss_usd` in
    # league/swarm/policy.json and league/swarm/dlane.py's `DEFAULTS`, its bound) -$200 -> -$300, a second. Nothing else
    # moves: the rolling $400 in any 20 sessions (`loss_budget_usd`, `loss_window_sessions`), the 10% cap,
    # `open_per_family` 3, `max_open` 8, DM1, the kill switch, the daily stop and the drawdown stop. Open Probe risk
    # stays at or under $400 (the window's envelope alone caps it), so `max_open`'s reasoning and `money.probe_room`
    # stand. Measured (the operator's simulation, three paired arms: cross-fit, fixed 2-, 3- and 5-session holds
    # standing in for the House's pool, roster 5, arrivals; what it trades is index beta minus option costs, not alpha):
    # P(Done) at 12 weeks 4.6% -> 5.5% (paired +0.92 points, SE 0.15), at 24 weeks 11.6% -> 14.4%; P(Done | zero edge)
    # 2.2% -> 2.7% at 12 weeks and 6.9% -> 9.0% at 24 (`dlane.ZERO_EDGE`). Its cost: P(the agents' running real net, the
    # Probe/Sized route and the incubator together, below -$400 within 12 weeks) 17.8% -> 36.8%, below -$600 0.6% ->
    # 4.4%; the 12-week net's 5th percentile -$396 -> -$679; P(the 60% drawdown stop trips by 24 weeks) 21% -> 48%; the
    # 12-week net's mean +$22 -> +$25 and its median -$327 -> -$231. Most of it is the total's: with the -$200 line kept
    # the figures are 35.8%, 4.1%, -$674 and 46% for P(Done) 5.3% and 14.2%, and the -$300 line beat that by 2.06
    # paired SE, just past PREREG-T's 2. A bad 20-session stretch (at most $400) that ages out of the window now leaves
    # room in the total for a second before any Probe gain refills it; at $400 it left none. MEASURED AT ROSTER 5 ALONE
    # (at no roster the operator's grid found the $800 total almost all cost): the roster is a swarm.json setting with
    # no deploy, so rolling it back or setting another count needs this rollback too, or a new measurement first; the
    # `dlane` report warns (PT1) while they run apart. Rollback, one owner deploy: `loss_total_usd` "400" here (re-pin
    # `PINNED_DIGEST`), `dlane.program_loss_usd` -200 and `dlane.done_zero_edge_p` 0.024 in league/swarm/policy.json and
    # in league/swarm/dlane.py's `DEFAULTS` (the line's bound is its default), and `dlane.ZERO_EDGE` back to
    # `ZERO_EDGES[0.024]`. The money digest moves back and the standing grant re-ratifies at the House's start; no
    # fingerprint move, no evidence reset.
    #
    # ONE OPEN STRUCTURE A PROBE FAMILY (Oct 15, 2026; the captain's decision from the pre-registered study THRU-1015,
    # parts B and C, private): `probe.open_per_family` 3 -> 1, inside its bound (1 to 5), a TIGHTENING. Why: the one
    # options program at Probe buys one short-dated call on every session its gate is on and holds each to expiry, so
    # at 3 it can hold three at once, and every one of them takes room in the $400 window the six share programs size
    # their lots against. Measured on the House's own engine and sizing over 3,048 historical paths from the live
    # state (A32's six at 0.50 x E, no new share program arriving), the program as coded against the same program one
    # structure at a time: P(Done) by Dec 7 +3.2 points (SE 1.1) with its calls priced from the paths, +2.3 (SE 1.1)
    # with their mean set to a 10% loss (zero edge); by Nov 6 +1.5 / +1.2, by Jan 6 +3.7 / +3.0. The share programs'
    # refused entries a path 19.6 -> 15.8 (18.4 -> 14.5), sessions with a window pause at an open 94% -> 90%, the
    # consistency clause's failures (A14) 7.1% -> 4.6% of paths (5.0% -> 3.4%). Its cost, stated: about 0.6 fewer
    # options closes a path in 12 weeks (5.4 -> 4.8), a Probe options program trades a smaller book than its own
    # replay holds (a refused open is no close, so no twin moves), the practice book (league/live/shadow.py) scales
    # to one structure a family too, and a two-sided `long_single` family at Probe (none is at Probe today) holds one
    # of its two legs at a time: its put waits until its call has closed (league/tests/test_live_long_single.py). Two
    # a family was measured too and is no better than three (the family share and the window already stop the third
    # call): the gain is one at a time. No program is stopped, no position is sold. Rollback, one owner deploy:
    # `open_per_family` 3 here (re-pin `PINNED_DIGEST`); the money digest moves back and the standing grant re-ratifies
    # at the House's start; no fingerprint move, no evidence reset.
    "options_money": {
        "real_types": ["debit_vertical", "long_butterfly", "long_call", "long_put"],
        "credit_types": ["credit_vertical", "iron_condor", "iron_butterfly"],
        "credit_min_equity_usd": "2000",
        "probe": {"max_loss_share": "0.10", "contracts": 1, "open_per_family": 1, "family_share": "0.15", "floor_usd": "0",
                  "max_open": 8, "loss_budget_usd": "400", "loss_window_sessions": 20, "loss_total_usd": "800",
                  "loss_basis": "net", "demotion": "dm1"},
        "sized": {"min_trades": 20, "confidence": "0.80", "kelly_fraction": "0.25", "max_loss_share": "0.10",
                  "family_share": "0.30", "min_probe_real_trades": 5, "min_probe_sessions": 1},
        "book_share": "0.90",
        "daily_stop_share": "0.35",
        "drawdown_stop_share": "0.60",
        "tuition": {"day_usd": "200", "week_usd": "300"},
        "calibration": {"day_usd": "50"},
        "house_test": {"structure_usd": "100", "open": 3, "envelope_usd": "300", "stop_usd": "150", "sessions": 20,
                       "round_trips": 30},
        "incubator": {"max_loss_usd": "75", "contracts": 1, "max_open": 4, "week_loss_usd": "150",
                      "min_sessions": 3, "min_trades": 10, "min_coverage": "0.80"},
        "order_path": {"max_orders_day": 250, "max_requests_minute": 150, "bp_buffer": "0.10",
                       "near_money_share": "0.01", "expiry_close_lead_minutes": 10},
        "gateway": {"order_max_loss_usd": "1000", "order_equity_share": "0.25", "day_equity_share": "1.0",
                    "max_day_orders": 300, "max_day_open_orders": 250},
    },
    # ---- THE EQUITY LANE's money table (release E1, Oct 2026; the owner's goal of Oct 10, 2026: agent programs may trade
    # ETFs, stocks and options with real money; league/equity/INTERFACES.md, section 7). `league/live/money.py`
    # `EquityTable` is its one reader. Every row sits inside `EQUITY_MONEY_BOUNDS`, whose loose end is the owner's line
    # (`equity_money_problems`; `league.ci` refuses a tree outside them, and holds `universe` and `enabled` to the gateway's
    # STOCK_UNIVERSE and STOCK_BUYS_REAL). Shares are of the SIZING EQUITY E, as in `options_money`: the lower of the
    # Brokerage Account's equity and the grant's capital. One sizing function applies them, the book's and the Gym's alike
    # (`league/equity/sizing.py` `size_entry`).
    #
    # THE LOSS BUDGET IS SHARED BY BOTH LANES. `options_money.probe.loss_budget_usd` ($400 net in any rolling 20 sessions)
    # and `loss_total_usd` ($800 net in total) bound every agent program's Probe opens, options AND equity, read by one
    # `probe_tally` (`league/live/real.py`): an equity lot counts at `open_risk_weight` x its marked value (open risk, with
    # every working buy), its close's net cash (fees and dividends in) joins the realized figures, and an equity program
    # takes ONE Probe slot however many lots it holds (A8.6). There is no second budget here. What the lane holds at
    # the seats and the sleeve in force is written in figures under `probe` below (THE DESIGN IN FORCE): a one-ETF
    # program's lot is `position_share.etf` of its sleeve; every entry is cut to the budget's room over its weight; the
    # options Probe lane keeps $400 less the window's realized loss less 0.20 x the equity lots, so with the equity
    # lane invested options Probe opens are effectively off. A program that holds several ETFs may fill its whole
    # sleeve, and THE INVESTED CAP (1.00 x E, 0.20 x E of open risk at most) bounds the lane then. The kill switch,
    # the daily stop and the drawdown stop bound both lanes.
    #
    # - `enabled`: the House's switch for real equity OPENS. THE SWITCH SHIPS ON (the captain's A10.2): E1 deploys True,
    #   one money-digest move with the block itself (the standing grant re-ratifies at the House's start); nothing trades
    #   until a program passes its sealed look (the swarm's `elane.mode` deploys "off" and the captain sets "gate" after
    #   the deploy is verified) AND the stock paper proof's BUY stage passes. False is the instant stop of every equity
    #   open, a constitution-only change that moves the money digest again. Exits never wait on it. True requires the
    #   gateway's STOCK_BUYS_REAL "on" (`league.ci`); the gateway may read "on" while this is False: this row is the
    #   switch.
    #   THE OLD LANES ARE EXITS ONLY: False (the owner's goal of Oct 19, 2026 and the frozen pre-registration
    #   PREREG-EVL-1, section 8: "the index ETF and options programs take no new entries from the first House release
    #   after the registration time (it switches equity opens off; options reads are already off); their open lots exit
    #   by their own rules"). This row alone moved. No real equity buy goes, the ETF and the panel programs' alike
    #   (league/equity/live.py `_open_block`: "equity_money.enabled is false: exits only"); every exit goes as before (a
    #   program's own sells, the maximum hold, the failed-decides rule, a retired program's lots, a carried exit, the
    #   owner's flatten, the close window), and the decide still runs while the book holds a lot, so a program's sells
    #   are planned. No band moves and nobody is seated while it is False. Money digest 5ea6f99f -> f4fc39ff,
    #   constitution 82a9a5a4 -> 34bbe7a5; the standing grant re-ratifies at the House's start on the owner's deploy.
    #   Rollback: True (one owner deploy; both digests back to 5ea6f99f / 82a9a5a4 exactly).
    # - `universe`: the symbols a program may trade, by class: the gateway's STOCK_UNIVERSE exactly. No leveraged or
    #   inverse ETF: they hold borrowing or short exposure inside them.
    # - `position_share`: one instrument's cap, the account's holding of it plus every open buy of it across all programs,
    #   as a share of E: 0.50 an ETF, 0.20 a stock (the owner's lines). A program's own position is held to the same
    #   share of its SLEEVE, as the Gym holds it. A STOCK AT 0.10 SINCE RELEASE R2 (the owner's goal of Oct 19, 2026,
    #   item 4: "<= 10% of equity per name"; the gateway's STOCK_SINGLE_EQUITY_SHARE "0.1" with it): a tightening, the
    #   old lanes being exits only; `config.POSITION_SHARE`'s 0.20 stays the code ceiling (an evidence constant).
    # - `invested_share`: CASH ONLY, BY CHOICE (the captain's A1): equity long value + open equity buys + the options' open
    #   maximum loss at most this share of E, 1.00. The goal allows margin where the account offers it (the overnight
    #   2x); E1 does not use it, because margin interest is not metered yet (the goal forbids hidden costs) and the loss
    #   budget binds first at this size. A later release may raise this row toward the venue's overnight multiplier once a
    #   margin-interest row is metered: a loosening, with its bound.
    # - `cash_reserve_usd`: THE HOUSE-WIDE CASH RULE (A8.1): no real open in EITHER lane may take available cash (cash -
    #   |short market value| - every working buy's worst cost in both books - working reservations) below this, $50
    #   (above the gateway's own $25 floor); while cash is below zero, or any us_equity position is short, every equity
    #   open is refused (`league/live/money.py` `available_cash`, `league/equity/sizing.py`), so margin interest never
    #   accrues.
    # - `open_risk_weight`: what an equity position counts in the shared budget, as a share of its marked value (the
    #   goal's convention: 0.20 an ETF, 0.40 a stock; only stricter).
    # - `probe` (A5): a program that passed its lane's look takes an equity roster seat (`max_programs`, equal to the
    #   swarm's `elane.roster`; who takes a free one is THE SEAT RULE, `probe.seat`, written under the table) with a
    #   sleeve of `sleeve_share` x E; an entry is cut to fit the budget's room over its weight, and nothing under
    #   `min_order_usd` is sent.
    #   THE SEATS AND THE SLEEVE ARE TWO NUMBERS (release E5-S, Oct 11, 2026; Claude's build under goal item 4):
    #   `max_programs` and `sleeve_share` are set TOGETHER, inside their bounds (`EQUITY_MONEY_BOUNDS`: 0 to 6 seats,
    #   a sleeve of 0 to 0.50 x E), by one mechanical step, `set_design SEATS SLEEVE`, which rewrites these two rows,
    #   the swarm's `elane.roster` (league/swarm/policy.json and league/swarm/elane.py's default), `PINNED_DIGEST`
    #   and the design blocks of the documents (the one below, docs/operations.md, league/equity/INTERFACES.md and
    #   CHANGELOG.md), and nothing else. The two numbers are the captain's to set from the verdict of the
    #   pre-registered study EQDONE-3, whose candidates are seats 3, 4, 5, 6 x sleeve 0.50, 0.33, 0.25;
    #   league/tests/test_equity_design.py holds the tree to every one of them through `size_entry` and pins each
    #   one's money digest, so the row the study names lands on a digest the tree already states. WHY THE TWO MOVE
    #   TOGETHER: Done reads 30 real closes whose P&L sums above zero; more programs trading at once make closes
    #   sooner, and a smaller lot a program keeps the same shared loss budget over them. ITS COST, PLAINLY: a
    #   seat is one passed sealed look, so more seats put more programs, the screen's false positives among them, on
    #   real money at once; a smaller lot pays the same spread and fees per dollar and earns back a loss more slowly;
    #   and closes made sooner by long-only index ETFs are weak evidence of skill. It buys closes, not edge.
    #   Every owner line stands and binds through `size_entry` at any seats and any sleeve: an ETF at most 0.50 x E
    #   across all programs (`position_share`), at most 1.00 x E invested (`invested_share`), the cash reserve, and
    #   the shared loss budget ($400 net in any rolling 20 sessions, $800 net in total). A SEAT ONLY DECIDES WHO MAY
    #   OPEN: no lot is ever sold because a number changed. A lot larger than a smaller sleeve keeps its own exits,
    #   and its program's next entries are held to the sleeve in force (no more of that ETF while the lot is over
    #   half the sleeve, nothing at all while it is over the whole of it); a buy planned under the old sleeve is
    #   sized at its send under the one in force; seats moved down unseat nobody. Rollback, one owner deploy:
    #   `set_design 3 0.50` (A20's seats and sleeve; the bounds may stay; its money digest is the pair's pin in
    #   league/tests/equity_design.py `DIGESTS`, which since release E5-A carries the seat rule's block: E1's own
    #   7e41909a was the table before that block); the standing grant re-ratifies at the House's start; no
    #   fingerprint move, no evidence reset.
    # <equity-design>
    #   THE DESIGN IN FORCE: 6 seats (`probe.max_programs`, `elane.roster`), a Probe sleeve of 0.25 x E
    #   (`probe.sleeve_share`). A one-ETF program's lot is `position_share.etf` (0.50) of its sleeve: 0.125 x E.
    #   A lot in every seat asks for 0.75 x E of ETFs; the lane holds at most 0.75 x E of them, 0.15 x E of
    #   open risk at weight 0.20. One ETF across programs (the instrument cap, 0.50 x E): 4 whole lots fit; the
    #   next program's lot of it is 0.00 x E. At E = $2,000, the account all cash and nothing realized: 6 of
    #   6 whole lots fit under the invested cap (1.00 x E) and the $50 cash reserve alone, and
    #   6 of 6 in the $400 window alone; the window alone holds all 6 up to E = $2,666.
    #   Whole sleeves (programs that hold several ETFs) ask for 1.50 x E; the lane holds at most 1.00 x E,
    #   0.20 x E of open risk. The options Probe lane keeps $400 less the window's realized loss less 0.20 x
    #   the equity lots: $400 - 0.15 x E against the one-ETF lots above. The gateway's day line (4x
    #   equity of buys a day, a cancelled one too) admits 32 sends of such a lot: 6 entries can each climb the
    #   collar's ladder of 5 sends. A Sized sleeve (the step is parked) would be between 0.25 x E and
    #   0.50 x E.
    # </equity-design>
    #   THE PROBE SLEEVE AT 0.50 (A20, Oct 11, 2026; Claude's decision under goal item 4, from the pre-registered study
    #   EQDONE-2 and its review, fixed before the first live equity trade and before the result of the options lane's
    #   next close was known; THE DESIGN E1 DEPLOYED, and the rollback above): `sleeve_share` "0.25" -> "0.50", a
    #   loosening of this one row and of its bound, with three seats and first-come seating. A program's position in
    #   one ETF is at most `position_share.etf` (0.50) of its sleeve (`size_entry`'s "sleeve_cap"), so a one-ETF
    #   program's lot went from 0.125 x E to 0.25 x E.
    #   Why a larger lot: Done reads the sum of the realized P&L of every agent program's closes since Oct 10, 2026,
    #   both lanes together, so a losing close early in that sum has to be earned back by the lots that follow, and a
    #   lot of an eighth of E earns too little to do it. WHY 0.50 AND NOT THE STUDY RULE'S 0.66: the pre-registered rule
    #   over first-come designs picked 0.66, and its review adopted that with a fallback to 0.50 if entries the House
    #   refuses or cuts make live trading differ from the replay that Done's consistency clause reads (A14). They do:
    #   at 0.66 three one-ETF lots meet the invested cap and the cash reserve, so some entries are cut or refused live
    #   that the Gym, which judges each program alone in its own sleeve, fills. At 0.50 no cross-program cap binds for
    #   three one-ETF programs. ITS COST, PLAINLY: against 0.66, a smaller rise in the chance of Done; against 0.25,
    #   about twice the dollar swings, losses as much as gains, and twice the spread and fees paid at zero edge. The
    #   larger lot buys variance and exposure to the market's direction, not edge and not a higher expected profit.
    # - `sized`, PRE-REGISTERED here before the first live trade (goal item 4; `league/equity/bands.py` `sized_up`,
    #   `sized_sleeve_share`): a Probe program is Sized when its version's real closes number at least `min_trades`, their
    #   mean net return on notional is above zero with its one-sided `confidence` lower bound above zero, its P&L beats the
    #   same-risk buy-and-hold over the same sessions (`beat_bh`, the goal's scaling rule), and it has spent at least
    #   `min_probe_sessions` sessions at Probe. Its sleeve is then, as coded, max(the Probe's `sleeve_share`,
    #   min(`kelly_fraction` Kelly on that lower bound, `sized.sleeve_share`)) x E: never below the Probe's.
    #   `sized.sleeve_share` STAYS 0.50 AT EVERY DESIGN (release E5-S: `set_design` does not move it). The rule's
    #   floor is the Probe sleeve in the code itself, whatever this row says, and no sleeve inside the Probe's bound
    #   is above 0.50, so the row is never under the Probe's and the rule stays as pre-registered. Where the Probe
    #   sleeve is 0.50 the cap equals the floor and a Sized program would keep the Probe sleeve and size nothing up;
    #   under a smaller Probe sleeve the rule could size a program up to 0.50 x E, which is one more reason the step
    #   below stays parked (raising or lowering the row is a later decision, with its bound). What Sized would still
    #   change: a lot bought while Sized carries no Probe mark, so its close joins neither the budget's realized
    #   figures nor the program's own loss line (`demotion.program_loss_usd`); its open value still counts as open
    #   risk, at the same weight.
    #   THE SIZING-UP STEP IS PARKED (Oct 11, 2026; the captain's decision on the review of A20's study): `min_trades`
    #   is 1000, inside its bound and a tightening. Why: the owner's loss budget ($400 net in any rolling 20 sessions,
    #   $800 net in total) covers all real money, and E1 as built leaves a Sized program's closes outside the Probe
    #   window, the total and the -$300 line. With 1000 no equity program is Sized, so every equity close stays inside
    #   the loss budget's tallies. The sizing-up RULE stays pre-registered as written (its own count is 20 real
    #   closes); the row is switched back only together with a change that counts Sized closes in the budget.
    # - `demotion`, EDM1, PRE-REGISTERED the same way (`league/equity/bands.py` `edm1`): exits only, sticky for the
    #   version, when its real closes are `min_trades` or more and their net returns sum below -`z` x sigma x sqrt(n)
    #   (sigma: the per-trade sd of its Validation run); when its realized net reaches `program_loss_usd`; or when its
    #   fills ran more than `twin_gap_bp` a side below their replay twins on average over `twin_min_closes` or more
    #   priced closes.
    # - `holds` (A8.5): a lot never sells in the session it was bought, the kill switch included; a program declares its
    #   maximum hold in NEEDS (`default_max_hold_sessions` when it does not, at most `max_hold_sessions`); after
    #   `failed_decides_exit` sessions of failed decides its lots exit at the next open. Pre-registered program rules,
    #   identical in the Gym.
    # - `order_path`: marketable limit day orders whose collar starts at `entry_collar_bp` and widens to `max_collar_bp`
    #   (basis points, by class); `max_orders_day` THE OLD LANES' orders a day, sends and cancels, before an ENTRY of
    #   theirs is refused (an exit is never stopped by it, only by the House-wide count; A8.3: the gateway's day order
    #   count is shared with the options book; since release 1019c the event kind's orders count against its own line,
    #   `event.max_orders_day`, below); and the schedule's offsets in seconds (`league/equity/schedule.py`): the open
    #   window (09:25 pre-open, 09:30:30 sends, entries until 09:45, exits until 15:55), THE CLOSE WINDOW (A2: 15:55:00
    #   sends, re-priced every 30 s until 15:59:30, then missed), the 16:20 bars, the 16:30 decisions and the 08:30 audit.
    "equity_money": {
        "enabled": False,
        "universe": {"etf": ["SPY", "QQQ", "IWM", "DIA", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU",
                             "XLV", "XLY", "TLT", "GLD"],
                     "stock": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "JPM", "V", "UNH", "XOM", "JNJ",
                               "PG", "MA", "HD", "AVGO", "LLY", "COST"]},
        "position_share": {"etf": "0.50", "stock": "0.10"},
        "invested_share": "1.00",
        "cash_reserve_usd": "50",
        "open_risk_weight": {"etf": "0.20", "stock": "0.40"},
        "probe": {"sleeve_share": "0.25", "max_programs": 6, "min_order_usd": "10"},
        "sized": {"min_trades": 1000, "confidence": "0.80", "kelly_fraction": "0.25", "sleeve_share": "0.50",
                  "beat_bh": True, "min_probe_sessions": 5},
        "demotion": {"rule": "edm1", "min_trades": 10, "z": "1.645", "program_loss_usd": "-300", "twin_gap_bp": "15",
                     "twin_min_closes": 5},
        "holds": {"min_hold_sessions": 1, "default_max_hold_sessions": 20, "max_hold_sessions": 60,
                  "failed_decides_exit": 2},
        "order_path": {"entry_collar_bp": {"etf": 10, "stock": 25}, "max_collar_bp": {"etf": 50, "stock": 100},
                       "max_orders_day": 60,
                       "preopen_before_open_s": 300, "open_send_after_open_s": 30, "exit_wait_s": 120,
                       "entry_until_after_open_s": 900, "exit_until_before_close_s": 300,
                       "close_send_before_close_s": 300, "close_until_before_close_s": 30,
                       "open_reprice_s": 60, "close_reprice_s": 30, "bars_after_close_s": 1200,
                       "decide_after_close_s": 1800, "audit_before_open_s": 3600},
    },
}

# ---- THE SEAT RULE (`equity_money.probe.seat`; the captain's A24, registered 13:42Z Oct 11, 2026, before the first live
# share close and before any program waited for a seat, AS AMENDED BY A30 at 20:47Z the same day, before the rule was
# live; release E5-A). A24 WITH A30 IS THE RULE IN FORCE. IT DECIDES WHO MAY OPEN NEXT, AND NOTHING ELSE.
# - `rule`: "activity-1-free" (in force) or "first-come" (the rollback: release E5-S's behaviour exactly, seats by the
#   time of the look pass).
# - A FREE SEAT goes to the best-ranked WAITING passed program. Its rank is K: the smaller of its Validation close days
#   and its Train-era close days per 250 sessions, a day counted only when the lots it closed that day sum to at
#   least `k_floor` of its sleeve (read as `k_floor` minus 0.0005: the engine rounds a lot's weight). Ties: the
#   earlier look pass, then the family id. K reads no P&L and no sealed window. It is fixed when the look is recorded
#   and is never printed in public text (a report shows a rank position only).
# - THE IDLE SEAT: a seated program that is flat and has had no buy reach the venue, and none cut or refused by the
#   loss budget, for `idle_sessions` seated sessions is flagged idle. It keeps its seat while nobody waits and yields
#   it at once when an unflagged program waits. A buy refused by the instrument cap, the invested cap or cash does not
#   count as asked. A yielded program returns only into a free seat, by the same rank, with no new look.
# - A30 (1), FREE SEATS FIRST, is A24's reading: a free seat is filled before the idle test, and an idle seat yields
#   only for an unflagged program that would still wait once every free seat is filled. (The study that measured the
#   rule ran the idle test first: its gain of the rule was measured under that slower order.)
# - A30 (2), THE IDLE CLOCK DOES NOT RUN WHILE THE HOUSE REFUSES EVERY OPEN: a session in which the House refused opens
#   for a House-wide reason (paused, the kill switch, a stop, a freeze, the grant not ratified, the paper proof's BUY
#   stage not passed: what the book's `_open_block` answers before it looks at the instance) is left out of every
#   program's idle count and of its seated-session count for the idle test. (A24 counts a loss-budget refusal as asked
#   because giving that seat away helps nobody; the same holds when the House itself would not open.)
# - A30 (3), A LOST BUY IS NOT FLAT: a buy whose answer was lost keeps its program from being read flat, and so from
#   yielding, for as long as the book may still take the lost order back. No seat change ends in a House sale of a lot
#   that shows up afterwards.
# - NOBODY TRADING IS EVER STOPPED BY THE SEAT RULE. OUTRANKING (a better-ranked arrival making a seated program
#   exit-only) is NOT ADOPTED: it may be switched on only by A24's own pre-registered line, as a new value of `rule`.
#   Never a forced or hand-placed trade; no lot is ever sold by the seat rule.
# - Seeded and bred programs follow the same rule. EDM1 (`demotion`) covers waiting programs too.
# - ITS COSTS, PLAINLY (A24): closes concentrate in frequent traders, so Done reached this way is weaker evidence of
#   skill; a daily slice of a quarter sleeve can buy rank; a slow, non-idle incumbent keeps its seat. A30 states and
#   accepts, unchanged: that daily quarter-sleeve slice buys immunity from the idle rule too.
# - Rollback, one owner deploy: `rule` "first-come" (one money-digest move; the standing grant re-ratifies at the
#   House's start; no fingerprint move, no evidence reset; nobody is unseated by it). `k_floor` is ONE value (K is
#   fixed per program, so a moved floor would rank old and new programs on two measures: a new floor is a new rule
#   name). `idle_sessions` sits at its loose end (10): inside its bound a change can only make a yield rarer.
# The `probe` row in the table stays one line of two numbers, because release E5-S's mechanical step (`set_design`)
# rewrites that exact line; the block is added to the same dict here, so it is a row of the table and of the money
# digest like every other (`EQUITY_MONEY_BOUNDS`, `EQUITY_MONEY_CHOICES`). Its reader is league/equity/bands.py
# `seat_settings` (league/live/money.py's `EquityTable` reads its rows by name and does not read this one).
CONSTITUTION["equity_money"]["probe"]["seat"] = {"rule": "activity-1-free", "k_floor": "0.25", "idle_sessions": 10}

# ---- THE PANEL SLEEVE AND THE PANEL SEATS (`equity_money.panel`; release E4 step two, Oct 14, 2026; Claude's build
# under goal item 4, from the step-two plan's money design; until the pre-registered study EQDONE-5 rules, the row
# ships at 1 seat and 0.10). A PANEL program (structure "panel": a basket of index members, league/xs) never takes,
# holds or yields one of the `probe` seats above, and never sizes from the `probe` sleeve:
# - `seats`: the panel programs that may hold a seat at once, a POOL OF THEIR OWN beside `probe.max_programs` (0 to 2;
#   0 stops new panel seats). The seat rule (`probe.seat`) ranks the waiting panel programs inside this pool only, by
#   the same K; the ETF seats, their plan, the idle test and K are untouched. Every leg of the panel lane is
#   lane-wide, so while one fails no panel row exists and nobody is seated into the pool: a program held on a failed
#   leg keeps its seat and resumes. The swarm's `elane.panel.seats` may only lower it.
# - `sleeve_share`: a panel program's sleeve as a share of E (0 to 0.25, and never above `probe.sleeve_share`: a table
#   with the Probe sleeve under the panel sleeve is refused, so a Probe sleeve set to 0 needs `sleeve_share` 0 with
#   it, or `seats` 0). At 0.10 x E its whole basket fits beside three HELD one-ETF lots at 0.50 x E with no loss in
#   the window while 3 x 0.25 x E x 0.20 + 0.10 x E x 0.40 = 0.19 x E is at most $400 (E up to $2,105; $380 of it at
#   E = $2,000). A name of an eight-name basket is 0.0125 x E, so a basket scaled under 800 / E of its sleeve (40% at
#   E = $2,000) has names under the $10 order minimum, which are refused, not cut. Outside that room a basket bought
#   from flat or rotated whole is scaled to the room the HELD lots leave (league/equity/live.py `_panel_budget`; the
#   other programs' buys planned for the same open are not seen, and they are worked first), and a partial
#   rotation's new name is refused at the send.
# THE WINDOW STAYS ONE, FIRST COME (A8.6 as registered): no slice of the $400 is reserved for the panel, and every
# owner line binds a panel lot through `size_entry` as it binds an ETF lot (a stock at most 0.20 x E, 1.00 x E
# invested, the cash reserve, the shared loss budget at 0.40 of a stock's mark). ITS COST, PLAINLY: one more program
# on real money at once (XS1's zero-edge pass rate at the House's bar is at most 10.02% a cell); a basket's lots
# closed at one open are one market move, so Done counts a panel program's lots closed on one date as one close
# (the direction report's `done_counts`; it states the lots and the distinct close dates beside every checkpoint).
# Rollback: `seats` 0 (one money-digest
# move; nobody holding a panel seat is unseated by it, and no lot is sold). The `probe` row stays one line (release
# E5-S's `set_design` rewrites that exact line), so this block is added here, as the seat rule's is. Its reader is
# league/equity/bands.py `panel_settings` (league/live/money.py's `EquityTable`, inside the options execution
# fingerprint, reads its rows by name and does not read this one).
CONSTITUTION["equity_money"]["panel"] = {"seats": 1, "sleeve_share": "0.10"}

# ---- THE EVENT LANE'S REAL MONEY (`equity_money.event`; release R2, Oct 2026; the owner's goal as he re-set it at
# 05:15Z Oct 19, 2026 and the frozen PREREG-EVL-3 section 2, with PREREG-EVL-1 section 8 and PREREG-EVL-2). VERSION 2 of
# each of the nine seatable programs of league/events/programs.py (a pre-registered rule over EDGAR filings and Alpaca
# news, never a swarm family; version 1 never trades) trades REAL money from its first event, at the band the event
# lane's store gives it (learning from birth; Probe after a passed look; Sized; retired: no real money), through the
# EquityBook's event kind (league/events/book.py), in whole shares, entered and exited in the listing exchange's
# auctions: limit-on-open / limit-on-close buys at `limit_ratio` x the previous SIP close, market-on-close (or, for
# PREREG-EVL-2's overnight rows, market-on-open) sales. Its rows, every one a money rule:
# - `enabled`: THE EVENT KIND'S OWN SWITCH, ON. `equity_money.enabled` STAYS FALSE (the old lanes are exits only,
#   PREREG-EVL-1 section 8): set back to True it would reopen the seated ETF programs' buys (a seat is never taken away
#   by a smaller count), which the frozen rule closed. This row opens only the event kind's buys, and nothing else of
#   the book. With it on, no event order goes until the gateway's STOCK_EVENT_BUYS is on (a gateway deploy) and the
#   auction paper proof's BUY stage has passed. False is the instant stop of every event buy (a constitution-only
#   change; exits never wait on it).
# - `position_share`: a position's target share of E, the account equity at the previous close (learning 0.02, Probe
#   0.035, Sized 0.10: PREREG-EVL-3 section 2 with the captain's A86 for Probe), sized in whole shares at the limit;
#   when that rounds to none, one share when it fits every wall and, at learning and at Probe, when one share at the
#   limit is at most `one_share_max` of the band (0.05 each) of E; otherwise the event is skipped (the shadow keeps it).
# - `max_open`: open positions a program may hold (learning 8, Probe 6, Sized 8).
# - `max_open_v8` (release 1019j; PREREG-EVL-8 section 4.1, F4): THE PX SEATS' LEARNING ROOM. PREREG-EVL-8's three PX
#   seats (PX-DROP-ON, PX-SURGE-ON, PX-GAP-O1) hold AT MOST 4 OPEN LEARNING POSITIONS a program, read for them ALONE
#   (league/events/book.py `max_open_8`; every other program, PREREG-EVL-8's meta-learners included, keeps
#   `max_open.learning` 8). Its bound is 0-4: 4 is the registered loose end (the text's own number, so a change may only
#   trade less) and 0 stops every PX learning buy. The red team's reason (goal-2026-10-19/evl8/redteam/rt_budget.py):
#   five more programs' full learning books would hold loss-budget and cash room the Probe tier needs; the PX screen's
#   money weights and top guard read the same 4 (F4). ITS COST, PLAINLY: at most 3 x 4 = 12 more learning lots at about
#   2% of E each (0.24 x E at target), every lot under the name's 10%, the 100% book, the cash, the loss budget at the
#   lot's weight and A85's reservation; no wall moves; this file's buys are planned and sent after every earlier row's
#   (league/events/book.py `EIGHT_ROOM`), so no earlier row's room moves.
# - A86 REVISED, PROBE SMALLER, INSIDE THE TRADE-LESS ENVELOPE (the captain's amendment of 20:30Z Oct 21, 2026,
#   replacing A86's proposal; decided before any Probe event; a sizing rule inside the frozen envelope: no program's
#   rule and no judge, look, alpha or Done rule moves): the Probe band was PREREG-EVL-1 section 8's 5% of E with at
#   most 6 open and one share up to the 10% name wall. Probe is now `position_share.probe` 0.035 (its bound stays
#   0-0.05: the pre-registered value is the loose end and a change may only trade less) with `one_share_max.probe`
#   0.05 (its own bounds row 0-0.05, held under the name's wall), and `max_open.probe` STAYS 6 (8 lies outside its
#   bound 0-6: `equity_money_problems` would fail the whole event kind closed; a slot rise above 6 would need a reviewed
#   bounds change and a new version, not taken). A program's Probe dollars at target are 6 x 0.035 = 0.21 x E (before
#   6 x 0.05 = 0.30), its worst case 6 one-share lots x 0.05 = 0.30 x E (before 6 x 0.10 = 0.60). ITS COST, stated:
#   Probe events carry 30% fewer dollars each; total Probe dollars are unchanged while cash binds; Done's "Probe size"
#   is 3.5% from here; a name whose one share at the limit is above 5% of E (and inside the wall) is skipped at Probe
#   as at learning, where PREREG-EVL-1 bought one share (the shadow keeps it). The screen's cost allowance keeps its
#   frozen 5% notional (league/events/score.py), so it understates the fixed CAT/TAF fees of a 3.5% Probe lot.
#   Learning and Sized do not move.
# - `reach_bar` (release 1019h; the captain's A97, S2 of the done-speed brief, and A100, which names the rows): PROBE
#   AND SIZED BUYS AT DONE'S SIZE. A Probe or Sized buy that flooring to whole shares at the limit took under
#   `reach_bar` x its band target buys the fewest whole shares that reach it (league/events/book.py `round_up`,
#   league/equity/live.py `_size_event`), only when ROUNDING caused the shortfall (`size_entry`'s fractional dollars
#   reach the bar: a cap that cut them under it is never rounded past), only when those shares at the limit are at most
#   the band's FROZEN PREREG-EVL-1 section 8 target of the walls' equity (the loose end of its `position_share` bounds
#   row: Probe 0.05, Sized 0.10; never a literal), and only when `size_entry` asked again for them gives every share
#   (the name wall, the 100% book, cash and the loss budget at the lot's weight). 0.8 is the Done reader's own size line
#   (league/events/done.py `PROBE_SIZE_SHARE`, read and never edited; a test pins the two equal): Done counts a Probe+
#   buy only at 0.8 of its target, and whole-share flooring left about a third of Probe buys under it. The target stays
#   position_share x E (`target_usd`, what the judge reads); the shares are never above floor(5% E / limit),
#   PREREG-EVL-1 section 8's own count, so the buys stay inside the frozen envelope (A86 REVISED's doctrine: no program
#   rule, selection, look, judge or Done rule moves). Learning has no row and never rounds up. Each row's bound is
#   0-0.8: 0 is release 1019f's floor rounding (no round-up: THE TIGHTEN-ONLY SWITCH, one money-digest move), a lower
#   bar rounds up less (at or under 0.5 never: a floored buy of one share or more is always above half its target). ITS
#   COST, PLAINLY: a Probe lot is at most 5% of E at the limit ($94.90 at E $1,898) where A86 REVISED's floor kept it at
#   most 3.5%; at E $1,898 a limit of about $33-47 grows from one share to two and one of about $22-27 from two to three
#   (about 15% more cash a Probe buy across prices); a lot's open risk stays at most about $10 (weight 0.105); no wall
#   moves and the book's open-risk ceiling is unchanged (cash binds). About 5% of Probe buys stay under size (the limits
#   $47.45-53.14 at E $1,898: one share is under the bar, two above 5% of E). At Sized the envelope is the target
#   itself, so no Sized buy rounds up while `position_share.sized` is 0.10.
# - `per_name_share`: THE GOAL'S 10% A NAME, BOOK-WIDE: every lot of the name on the book, every working buy of it and
#   the account's own position, all programs and lanes together, plus this entry, at most 0.10 x E (`size_entry`'s
#   instrument cap; the gateway holds the same 10% of its own equity reading as a code ceiling).
# - `limit_ratio`: the entry's limit over the previous SIP close (1.25: the pre-registered limit, never chased).
# - `open_risk`: what an event lot counts in the shared loss budget (the goal's own rule, PREREG-EVL-1 section 8):
#   value x max(`floor`, `z` x sigma x sqrt(h)), sigma the stock's daily return sd over the `sigma_sessions` before
#   entry, h the sessions in its hold. THE 0.40 FLOOR OF `open_risk_weight.stock` IS LOWERED FOR THIS CLASS ONLY: an
#   ETF lot, an old-lane stock lot and an options position weigh as before. A lot whose sigma cannot be read, or one
#   held past its scheduled exit (no auction print), weighs the stricter 0.40.
# - `order_path`: THE AUCTIONS' MOMENTS (league/equity/schedule.py `event_moments`), seconds from the session's own open
#   or close: the open decision at 09:15 ET (`open_decide_before_open_s` 900, pre-registered), its `opg` sends from
#   09:16 to 09:27 (840, 180); the close decision at close - 14 min (840, pre-registered), its `cls` sends from close -
#   13 to close - 11 min (780, 660). Early closes move with the session.
# - `max_orders_day` (release 1019c): THE EVENT KIND'S OWN DAY ORDER COUNT. Its auction orders of a New York day (sends,
#   and the cancels of its fallback ladder's day sales, as `order_path.max_orders_day` counts the old lanes') count
#   against this line and no other lane's: an event ENTRY goes only while one more order leaves room for the exit of
#   every event lot not yet sold that day; AN EXIT IS NEVER STOPPED BY IT (A28). The old lanes keep the equity book's
#   own 60 (`order_path.max_orders_day`), and both stay under the House-wide line (`options_money.order_path.
#   max_orders_day`, 250, both books' orders together) and the gateway's (`options_money.gateway.max_day_orders`,
#   300): `equity_money_problems` holds the two equity lines' sum under the first and this line under the second. 150 =
#   2 x the sum of `max_open` over the live bands (2 x (8 + 6 + 8) = 44), at least 150: nine
#   programs at learning hold at most 9 x 8 = 72 lots, a buy and a sale each in one day, 144 orders. Under the equity
#   book's shared 60 (release 1019b), the event kind's entries stopped at about 30 open-entry lots sold the same day (a
#   day of 40 open-entry lots left that day's close entries no room).
# PROMOTION, SIZED, DEMOTION AND RETIREMENT are the lane's (PREREG-EVL-3 sections 2 and 3, counted in settled events):
# it writes each program's band in its store, from its looks and the real fills the book writes back (`real_fills`);
# the book reads the band at each session's first decision. ROOM: Sized programs first, then Probe, then learning;
# within a band the tables' order. THE LOSS BUDGET STAYS ONE: no slice of `options_money.probe`'s $400 net in any 20
# sessions and $800 net in total is reserved; every event entry is cut to the room the window and the total leave, open
# risk counted (`size_entry`'s budget cap at the lot's own weight), and every event lot's close counts in it whatever
# its band. The kill switch, the daily and drawdown stops, long only, no shorts, no margin (`invested_share` 1.00 and the
# gateway's 1x book) bind as they bind every lot. ITS COST, PLAINLY: nine programs on real money from their first event
# at about 2% a position, at zero edge about the round-trip cost (11-21 bp a position, PREREG-EVL-3 section 4), each lot
# entered at an auction whose print it cannot see first. Rollback: `enabled` False (one money-digest move; no lot is
# sold by it: every open event lot exits at its own scheduled auction). Its reader is league/events/book.py `settings`
# (league/live/money.py's `EquityTable`, inside the options execution fingerprint, reads its rows by name and does not
# read this one).
CONSTITUTION["equity_money"]["event"] = {
    "enabled": True,
    "position_share": {"learning": "0.02", "probe": "0.035", "sized": "0.10"},
    "one_share_max": {"learning": "0.05", "probe": "0.05"},
    "reach_bar": {"probe": "0.8", "sized": "0.8"},
    "max_open": {"learning": 8, "probe": 6, "sized": 8},
    "max_open_v8": {"learning": 4},
    "per_name_share": "0.10",
    "limit_ratio": "1.25",
    "open_risk": {"floor": "0.10", "z": "1.65", "sigma_sessions": 60},
    "order_path": {"open_decide_before_open_s": 900, "open_send_before_open_s": 840, "open_until_before_open_s": 180,
                   "close_decide_before_close_s": 840, "close_send_before_close_s": 780,
                   "close_until_before_close_s": 660},
    "max_orders_day": 150,
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



#: The allowed range of every tunable row of `options_money` this run (the plan's "Money" table, Sept 26, 2026), and the
#: rows that are not tunable at all: `(low, high)` inclusive. Loosening a row past its range is the owner's decision,
#: in this file. `league.ci` refuses a constitution outside them (`options_money_problems`).
OPTIONS_MONEY_BOUNDS: dict[str, tuple[str, str]] = {
    # THE FAST LANE (Oct 7, 2026): the owner's goal item 4 allows up to 10% of equity at risk per Probe position (a
    # loosening from 5%, reported with its cost) and a Probe loss budget up to $400; one structure a Probe position.
    "probe.max_loss_share": ("0.02", "0.10"),
    "probe.contracts": ("1", "1"),
    # Release L-D (Oct 9, 2026; Claude's decision under the same goal item, its cost in the table's comment): 8 Probe
    # slots (3 before it). The $400 envelope, not the count, bounds what Probe opens may lose.
    "probe.max_open": ("0", "8"),
    # THE ROLLING PROBE BUDGET (release L-D; the owner's goal as he re-set it on Oct 9, 2026, item 4: "Probe loss
    # budget: $400 net in any rolling 20 sessions and $800 net in total"): $400 at most over a window of at least the
    # owner's 20 sessions, and $800 at most in total (the owner's ceiling; the table set $400 on Oct 9 and sets $800
    # since Oct 10). 2000 sessions is the CON-only rollback's window (every close since the fast lane); a longer window
    # is never looser, under either basis (the table's comment: under "net" the window's figure is its worst net
    # stretch).
    "probe.loss_budget_usd": ("0", "400"),
    "probe.loss_window_sessions": ("20", "2000"),
    "probe.loss_total_usd": ("0", "800"),
    "probe.open_per_family": ("1", "5"),
    "probe.family_share": ("0.08", "0.15"),
    "probe.floor_usd": ("0", "100"),
    "sized.min_trades": ("20", "1000"),
    "sized.confidence": ("0.80", "0.99"),
    "sized.kelly_fraction": ("0.125", "0.5"),
    "sized.max_loss_share": ("0.05", "0.15"),
    "sized.family_share": ("0.20", "0.40"),
    # The Probe is a real stage (the review of #362, C2): Sized only after this many real Probe trades on the current
    # program version and this many whole sessions at Probe. A tightening of the plan's row; loosening is the owner's.
    "sized.min_probe_real_trades": ("5", "50"),
    "sized.min_probe_sessions": ("1", "20"),
    "book_share": ("0.50", "0.90"),
    "daily_stop_share": ("0.15", "0.35"),
    "drawdown_stop_share": ("0.40", "0.60"),
    "tuition.day_usd": ("0", "200"),
    "tuition.week_usd": ("0", "600"),
    # D3 (the sprint, Sept 26, 2026): the calibration round trips' maximum loss opened a day, $50 at most.
    "calibration.day_usd": ("0", "50"),
    # The House live test (the owner, Sept 28, 2026; `league/live/house_test.py`): its pre-registered bounds are the top of
    # each range. A bound may only tighten; loosening one is the owner's.
    "house_test.structure_usd": ("0", "100"),
    "house_test.open": ("0", "3"),
    "house_test.envelope_usd": ("0", "300"),
    "house_test.stop_usd": ("0", "150"),
    "house_test.sessions": ("0", "20"),
    "house_test.round_trips": ("0", "30"),
    # The incubator (the owner, Sept 29, 2026; the reading of Sept 30; `league/live/incubator.py`): the owner's terms are
    # the loose end of each range, so a row may only tighten (0 stops the route); loosening one is the owner's. The
    # practice rule's floors are the pre-registered 3 sessions, 10 program closes and 0.80 coverage.
    # THE INCUBATOR CAP (Oct 8, 2026; Claude's decision under the owner's goal of Oct 7, whose item 4 allows up to 10% of
    # equity at risk per Probe position and whose item 5 asks every loosened rule reported with its cost): the unit cap's
    # loose end is $75 (the owner's $50 before it); the weekly envelope ($150), the 4 open and the one lot are unchanged.
    "incubator.max_loss_usd": ("0", "75"),
    "incubator.contracts": ("1", "1"),
    "incubator.max_open": ("0", "4"),
    "incubator.week_loss_usd": ("0", "150"),
    "incubator.min_sessions": ("3", "60"),
    "incubator.min_trades": ("10", "1000"),
    "incubator.min_coverage": ("0.80", "1.0"),
    "credit_min_equity_usd": ("2000", "2000"),
    "order_path.max_orders_day": ("1", "250"),
    "order_path.max_requests_minute": ("1", "150"),
    "order_path.bp_buffer": ("0.10", "0.50"),
    "order_path.near_money_share": ("0", "0.05"),
    "order_path.expiry_close_lead_minutes": ("1", "30"),
    "gateway.order_max_loss_usd": ("0", "1000"),
    # The sprint (Sept 26, 2026, "Money on Monday"): "the per-order maximum-loss cap is set so the Probe floor fits (never
    # above funded money)": 25% of $481.63 is $120.40, over the $100 floor; the $1,000 absolute cap stands.
    "gateway.order_equity_share": ("0", "0.25"),
    "gateway.day_equity_share": ("0", "1.0"),
    "gateway.max_day_orders": ("1", "300"),
    "gateway.max_day_open_orders": ("1", "300"),
}
#: The types the venue closes in one order: the only ones real money may open this run. The five multi-leg types, and
#: since the sprint (B4, Sept 26, 2026) a long call and a long put (one contract bought to open and sold to close).
OPTIONS_REAL_TYPES = ("debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly", "long_butterfly", "long_call",
                      "long_put")
#: The single-contract real types: `league/ci.py` reads the gateway's `OPTION_STRUCTURES_REAL` with these beside the
#: structure spec's types (`league/structure_core.py` TYPES), as the gateway's `SINGLE_LEG_TYPES` does.
OPTIONS_SINGLE_TYPES = ("long_call", "long_put")
OPTIONS_CREDIT_TYPES = ("credit_vertical", "iron_condor", "iron_butterfly")
#: The rows of `options_money` that name a rule rather than a number (release L-D, Oct 9, 2026): each is EXACTLY one of
#: its strings (case and all; "Net", "" or a missing row is refused, and nothing trades on a refused table). The first
#: of each pair is the rule before L-D, so setting L-D's rows back (`loss_basis` "gross", `probe.max_open` 3, `demotion`
#: "dm0", `probe.loss_total_usd` "400", `probe.loss_window_sessions` 2000) is a constitution-only rollback that never
#: moves the execution fingerprint.
#: - `probe.loss_basis`: how THE PROBE LOSS BUDGET reads realized Probe losses (`league/live/real.py` `probe_tally`):
#:   "gross", each closed Probe position's own loss summed (fast lane v2); "net", max(0, -the closed Probe positions'
#:   summed cash) from inception.
#: - `probe.demotion`: how live results end a Probe or Sized band (`league/live/money.py` `demotion`): "dm0", D5 and the
#:   forward-negative demotion (fast lane v2); "dm1", the calibrated band on the family's own real trades.
OPTIONS_MONEY_CHOICES: dict[str, tuple[str, ...]] = {
    "probe.loss_basis": ("gross", "net"),
    "probe.demotion": ("dm0", "dm1"),
}
#: Rows read as whole counts.
_OPTIONS_COUNTS = ("probe.open_per_family", "probe.contracts", "probe.max_open", "probe.loss_window_sessions", "sized.min_trades", "sized.min_probe_real_trades", "sized.min_probe_sessions", "order_path.max_orders_day", "order_path.max_requests_minute",
                   "order_path.expiry_close_lead_minutes", "gateway.max_day_orders", "gateway.max_day_open_orders",
                   "house_test.open", "house_test.sessions", "house_test.round_trips", "incubator.contracts",
                   "incubator.max_open", "incubator.min_sessions", "incubator.min_trades")


def options_money_problems(constitution: dict[str, Any] | None = None) -> list[str]:
    """Why the constitution's options money table is outside its bounds (`OPTIONS_MONEY_BOUNDS`), or [] when every row
    is inside them. A missing table is a problem: the live path trades nothing without it."""
    from decimal import Decimal, InvalidOperation

    table = (constitution or CONSTITUTION).get("options_money")
    if not isinstance(table, dict):
        return ["options_money: the table is missing"]
    problems = []
    for path, (low, high) in OPTIONS_MONEY_BOUNDS.items():
        node: Any = table
        for key in path.split("."):
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, bool) or node is None:
            problems.append(f"options_money.{path} is missing")
            continue
        try:
            value = Decimal(str(node))
        except (InvalidOperation, ValueError):
            problems.append(f"options_money.{path} = {node!r} is not a number")
            continue
        if not value.is_finite() or not Decimal(low) <= value <= Decimal(high):
            problems.append(f"options_money.{path} = {node!r} is outside [{low}, {high}]")
        elif path in _OPTIONS_COUNTS and (value != value.to_integral_value() or isinstance(node, float)):
            problems.append(f"options_money.{path} = {node!r} is not a whole count")
    for path, allowed in OPTIONS_MONEY_CHOICES.items():
        node = table
        for key in path.split("."):
            node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, str) or node not in allowed:
            problems.append(f"options_money.{path} = {node!r} is not exactly one of {list(allowed)}")
    real = table.get("real_types")
    if not isinstance(real, list) or not real or len(set(real)) != len(real) or any(t not in OPTIONS_REAL_TYPES for t in real):
        problems.append(f"options_money.real_types lists distinct types among {list(OPTIONS_REAL_TYPES)} (another type needs a "
                        f"paper round trip and the owner): {real!r}")
    if table.get("credit_types") != list(OPTIONS_CREDIT_TYPES):
        problems.append(f"options_money.credit_types is exactly {list(OPTIONS_CREDIT_TYPES)}")
    gate = table.get("gateway") if isinstance(table.get("gateway"), dict) else {}
    try:
        if int(gate.get("max_day_open_orders", 0)) >= int(gate.get("max_day_orders", 0)):
            problems.append("options_money.gateway.max_day_open_orders must leave exits room under max_day_orders")
    except (TypeError, ValueError):
        pass
    return problems

#: THE EQUITY LANE's bounds (release E1; league/equity/INTERFACES.md 7.1): every tunable row of `equity_money`, `(low,
#: high)` inclusive, with the owner's line at its LOOSE end, so a row may only tighten; loosening one past it is the
#: owner's decision, in this file. `league.ci` refuses a constitution outside them (`equity_money_problems`).
EQUITY_MONEY_BOUNDS: dict[str, tuple[str, str]] = {
    # The owner's goal of Oct 10, 2026: an ETF position at most 50% of equity, a single stock at most 20%. Above zero
    # (`EQUITY_MONEY_ABOVE_LOW`): `enabled` False is the way to stop the lane, never a zero share.
    "position_share.etf": ("0", "0.50"),
    "position_share.stock": ("0", "0.20"),
    # Cash only by choice (A1): at most 1.00 x E invested, options' open maximum loss included.
    "invested_share": ("0", "1.00"),
    # A8.1: at least $50 kept in cash, above the gateway's $25 floor.
    "cash_reserve_usd": ("50", "200"),
    # The goal's open-risk convention: an ETF counts at least 20% of its value, a stock at least 40%.
    "open_risk_weight.etf": ("0.20", "1.00"),
    "open_risk_weight.stock": ("0.40", "1.00"),
    # A5: no order under $10.
    # THE PROBE SLEEVE'S BOUND (A20, Oct 11, 2026; Claude's decision under goal item 4, from the pre-registered study
    # EQDONE-2 and its review, fixed before the first live equity trade): the sleeve's loose end is 0.50 of E (a quarter
    # of E before it), a loosening of this one row; a one-ETF program's lot is half its sleeve, 0.25 x E at most. Its
    # cost against a quarter of E: about twice the dollar swings, losses as much as gains, and twice the spread and
    # fees paid at zero edge; it buys variance and exposure to the market's direction, not edge. No owner line moves,
    # and each binds at any sleeve through `size_entry`: `position_share` (an ETF at most 0.50 x E across all
    # programs), `invested_share` (1.00 x E) and the shared loss budget (`options_money.probe`: $400 net in any
    # rolling 20 sessions, $800 net in total).
    "probe.sleeve_share": ("0", "0.50"),
    # THE SEATS' BOUND (release E5-S, Oct 11, 2026; Claude's decision under goal item 4): at most SIX Probe programs
    # (A5's three before it; 0 stops new seats), a loosening of this one bound, so that the seats and the sleeve are
    # set together as two numbers inside the bounds (the table's `probe` comment says why, with its cost: more
    # programs, the screen's false positives among them, on real money at once). No owner line moves: a seat only
    # decides who may OPEN, and `size_entry` holds every entry of every seated program to `position_share`,
    # `invested_share`, the cash reserve and the shared loss budget whatever the count. The swarm's `elane.roster`
    # equals the row in force (league/tests/test_elane.py) and a setting may only lower it.
    "probe.max_programs": ("0", "6"),
    "probe.min_order_usd": ("10", "100"),
    # THE SEAT RULE's constants (A24, Oct 11, 2026; release E5-A; the comment under the table). The floor of a close
    # day is ONE value, a quarter of the sleeve: K is fixed per program when its look is recorded, so a moved floor
    # would rank old and new programs on two measures (a new floor is a new rule name). The idle clock's loose end is
    # 10 seated sessions (A24 set 10 where the design said 20): a longer clock only makes a yield rarer.
    "probe.seat.k_floor": ("0.25", "0.25"),
    "probe.seat.idle_sessions": ("10", "60"),
    # THE PANEL ROW (release E4 step two; the comment under the table): at most two panel programs seated at once in a
    # pool of their own (0 stops new panel seats), each at a sleeve of at most 0.25 x E, and never above the Probe's
    # (`equity_money_problems`' order rule). Two baskets at 0.10 x E are 0.08 x E of open risk beside the ETF lane's.
    "panel.seats": ("0", "2"),
    "panel.sleeve_share": ("0", "0.25"),
    # THE EVENT LANE'S REAL MONEY (release R2; the comment under the table; PREREG-EVL-3 section 2). The pre-registered
    # values are the loose end of each row (a lower share, a lower one-share cap, fewer open positions, a lower limit, a
    # stricter floor or z may only trade less); the moments the rules fix are exact. The captain's A86 REVISED moves the
    # Probe share's VALUE inside its row (0.035) and adds the Probe one-share row; no bound is loosened.
    "event.position_share.learning": ("0", "0.02"),
    "event.position_share.probe": ("0", "0.05"),
    "event.position_share.sized": ("0", "0.10"),
    "event.one_share_max.learning": ("0", "0.05"),
    # A86 REVISED: Probe's own one-share cap (before it, one share at Probe went up to the name's wall), held under the
    # wall by `equity_money_problems`.
    "event.one_share_max.probe": ("0", "0.05"),
    # RELEASE 1019h (the captain's A97 S2, A100): the share of its band target a Probe or Sized buy rounds up to when
    # whole-share flooring left it under (Done's size bar). The loose end is the Done reader's own 0.8 (league/events/
    # done.py `PROBE_SIZE_SHARE`); 0 is no round-up (release 1019f's floor rounding); a bar under 0.8 rounds up less.
    "event.reach_bar.probe": ("0", "0.8"),
    "event.reach_bar.sized": ("0", "0.8"),
    "event.max_open.learning": ("0", "8"),
    "event.max_open.probe": ("0", "6"),
    "event.max_open.sized": ("0", "8"),
    # RELEASE 1019j (PREREG-EVL-8 section 4.1): the PX seats' learning room alone; every other program keeps
    # `event.max_open.learning` 8 and its bound.
    "event.max_open_v8.learning": ("0", "4"),
    "event.per_name_share": ("0", "0.10"),
    "event.limit_ratio": ("1.00", "1.25"),
    "event.open_risk.floor": ("0.10", "1.00"),
    "event.open_risk.z": ("1.65", "5"),
    "event.open_risk.sigma_sessions": ("60", "60"),
    "event.order_path.open_decide_before_open_s": ("900", "900"),
    "event.order_path.open_send_before_open_s": ("600", "899"),
    "event.order_path.open_until_before_open_s": ("180", "599"),
    "event.order_path.close_decide_before_close_s": ("840", "840"),
    "event.order_path.close_send_before_close_s": ("661", "839"),
    "event.order_path.close_until_before_close_s": ("660", "780"),
    # THE EVENT KIND'S OWN DAY ORDER COUNT (release 1019c; the comment under the table): 0 stops the kind's entries
    # (never an exit); its loose end is the gateway's day line's own (`options_money.gateway.max_day_orders`, at most
    # 300), and `equity_money_problems` holds it under the gateway's line in force and, with the old lanes' 60, under
    # the House-wide line in force.
    "event.max_orders_day": ("0", "300"),
    # The pre-registered sizing-up rule (the design's section 5): at least 20 closes, an 80% bound, quarter Kelly, half
    # of E at most (the loose end of the Probe sleeve's own bound, and a Sized sleeve is never below the Probe's: the
    # constitution's `sized` comment), five Probe sessions. THE STEP IS PARKED at the count's tight end (the row in
    # force is 1000: no equity program is Sized until Sized closes count in the loss budget; the `sized` comment).
    "sized.min_trades": ("20", "1000"),
    "sized.confidence": ("0.80", "0.99"),
    "sized.kelly_fraction": ("0.125", "0.25"),
    "sized.sleeve_share": ("0", "0.50"),
    "sized.min_probe_sessions": ("5", "60"),
    # EDM1: demoted at 10 closes or fewer, at z 1.645 or less, at -$300 realized or sooner (the A1.3 analogue), at 15 bp
    # a side of twin gap or less over 5 closes or fewer.
    "demotion.min_trades": ("1", "10"),
    "demotion.z": ("0", "1.645"),
    "demotion.program_loss_usd": ("-300", "-25"),
    "demotion.twin_gap_bp": ("1", "15"),
    "demotion.twin_min_closes": ("1", "5"),
    # A8.5: never sold in the session bought (exactly one session); a program's hold at most 60 sessions; two sessions of
    # failed decides at most before its lots exit.
    "holds.min_hold_sessions": ("1", "1"),
    "holds.default_max_hold_sessions": ("1", "60"),
    "holds.max_hold_sessions": ("1", "60"),
    "holds.failed_decides_exit": ("1", "2"),
    # The order path: collars in basis points (an ETF's at most 50, a stock's at most 100), and at most 60 equity
    # orders a day (A8.3: the gateway's day count is shared with the options book's).
    "order_path.entry_collar_bp.etf": ("1", "50"),
    "order_path.entry_collar_bp.stock": ("1", "100"),
    "order_path.max_collar_bp.etf": ("1", "50"),
    "order_path.max_collar_bp.stock": ("1", "100"),
    "order_path.max_orders_day": ("0", "60"),
    # The schedule's offsets, seconds (league/equity/schedule.py): each inside the session or the night around it, and
    # their order held by `equity_money_problems` (a send before its window's cut-off). At their loose ends the open
    # window's entries (3600 s after the open) close before the close window opens (1800 s before the close) even on a
    # 13:00 half day (12600 s).
    "order_path.preopen_before_open_s": ("60", "1800"),
    "order_path.open_send_after_open_s": ("0", "600"),
    "order_path.exit_wait_s": ("0", "600"),
    "order_path.entry_until_after_open_s": ("60", "3600"),
    "order_path.exit_until_before_close_s": ("60", "3600"),
    "order_path.close_send_before_close_s": ("60", "1800"),
    "order_path.close_until_before_close_s": ("5", "600"),
    "order_path.open_reprice_s": ("10", "600"),
    "order_path.close_reprice_s": ("5", "300"),
    "order_path.bars_after_close_s": ("60", "7200"),
    "order_path.decide_after_close_s": ("60", "14400"),
    "order_path.audit_before_open_s": ("60", "14400"),
}
#: The rows whose low end is EXCLUSIVE: a share of zero is no setting (the lane stops by `enabled` False).
EQUITY_MONEY_ABOVE_LOW = ("position_share.etf", "position_share.stock", "invested_share", "event.per_name_share",
                          "event.limit_ratio")
#: The rows that are EXACTLY one of their values, compared by type and value (1 is not True, "EDM1" is not "edm1").
EQUITY_MONEY_CHOICES: dict[str, tuple[Any, ...]] = {
    "enabled": (False, True),
    "sized.beat_bh": (True,),
    "demotion.rule": ("edm1",),
    # THE SEAT RULE (A24): the value in force, and the rollback ("first-come": release E5-S's behaviour exactly).
    # Outranking ("activity-1") is NOT a value here: it is not adopted, and adding it is the owner's line to write.
    "probe.seat.rule": ("activity-1-free", "first-come"),
    # The event kind's own switch (release R2): `equity_money.enabled` stays the old lanes' (False).
    "event.enabled": (False, True),
}
#: The event lane's moments (`league/equity/schedule.py` `EVENT_DEFAULTS`' keys), read by league/events/book.py.
EVENT_ORDER_OFFSETS = ("open_decide_before_open_s", "open_send_before_open_s", "open_until_before_open_s",
                       "close_decide_before_close_s", "close_send_before_close_s", "close_until_before_close_s")
#: The schedule's offsets (`league/equity/schedule.py` DEFAULTS' keys), read by `league/live/money.py` `EquityTable`.
EQUITY_ORDER_OFFSETS = ("preopen_before_open_s", "open_send_after_open_s", "exit_wait_s", "entry_until_after_open_s",
                        "exit_until_before_close_s", "close_send_before_close_s", "close_until_before_close_s",
                        "open_reprice_s", "close_reprice_s", "bars_after_close_s", "decide_after_close_s",
                        "audit_before_open_s")
#: Rows read as whole counts: the counts, the collars and the offsets.
_EQUITY_COUNTS = ("probe.max_programs", "probe.seat.idle_sessions", "panel.seats", "sized.min_trades",
                  "sized.min_probe_sessions",
                  "demotion.min_trades",
                  "demotion.twin_min_closes", "holds.min_hold_sessions", "holds.default_max_hold_sessions",
                  "holds.max_hold_sessions", "holds.failed_decides_exit", "order_path.entry_collar_bp.etf",
                  "order_path.entry_collar_bp.stock", "order_path.max_collar_bp.etf", "order_path.max_collar_bp.stock",
                  "order_path.max_orders_day", *(f"order_path.{name}" for name in EQUITY_ORDER_OFFSETS),
                  "event.max_open.learning", "event.max_open.probe", "event.max_open.sized", "event.max_open_v8.learning",
                  "event.open_risk.sigma_sessions", *(f"event.order_path.{name}" for name in EVENT_ORDER_OFFSETS),
                  "event.max_orders_day")
EQUITY_CLASSES = ("etf", "stock")
#: A ticker as the venue and the gateway's STOCK_UNIVERSE write it (a share class after a dot: BRK.B).
_TICKER = re.compile(r"[A-Z]{1,5}(\.[A-Z])?")


def _at(table: Any, path: str) -> Any:
    node: Any = table
    for key in path.split("."):
        node = node.get(key) if isinstance(node, dict) else None
    return node


def equity_money_problems(constitution: dict[str, Any] | None = None) -> list[str]:
    """Why the constitution's equity money table (`equity_money`) is outside its bounds (`EQUITY_MONEY_BOUNDS`,
    `EQUITY_MONEY_ABOVE_LOW`, `EQUITY_MONEY_CHOICES`) or malformed, or [] when every row is inside them. A missing table is
    a problem: the equity lane opens nothing without it (`league/live/money.py` `EquityTable`).

    THE LOSS BUDGET IS SHARED: this table holds no budget of its own. Every equity Probe open is bound by
    `options_money.probe.loss_budget_usd` ($400 net in any rolling 20 sessions) and `loss_total_usd` ($800 net in
    total), which `options_money_problems` bounds, read for both lanes by one `probe_tally`."""
    from decimal import Decimal, InvalidOperation

    table = (constitution or CONSTITUTION).get("equity_money")
    if not isinstance(table, dict):
        return ["equity_money: the table is missing"]
    problems: list[str] = []
    values: dict[str, Decimal] = {}
    # THE EVENT BLOCK IS OPTIONAL (release R2): a table without `event` is the table before R2 (its rollback), which
    # opens no event buy (league/events/book.py `settings` reads it as FALLBACK); with it, every row of it is checked.
    evented = isinstance(table.get("event"), dict)
    if "event" in table and not evented:
        problems.append("equity_money.event is not a table")
    for path, (low, high) in EQUITY_MONEY_BOUNDS.items():
        if path.startswith("event.") and not evented:
            continue
        node = _at(table, path)
        if isinstance(node, bool) or node is None:
            problems.append(f"equity_money.{path} is missing")
            continue
        try:
            value = Decimal(str(node))
        except (InvalidOperation, ValueError):
            problems.append(f"equity_money.{path} = {node!r} is not a number")
            continue
        above = path in EQUITY_MONEY_ABOVE_LOW
        inside = value.is_finite() and (value > Decimal(low) if above else value >= Decimal(low)) and value <= Decimal(high)
        if not inside:
            problems.append(f"equity_money.{path} = {node!r} is outside {'(' if above else '['}{low}, {high}]")
        elif path in _EQUITY_COUNTS and (value != value.to_integral_value() or isinstance(node, float)):
            problems.append(f"equity_money.{path} = {node!r} is not a whole count")
        else:
            values[path] = value
    for path, allowed in EQUITY_MONEY_CHOICES.items():
        if path.startswith("event.") and not evented:
            continue
        node = _at(table, path)
        if not any(type(node) is type(choice) and node == choice for choice in allowed):
            problems.append(f"equity_money.{path} = {node!r} is not exactly one of {list(allowed)}")
    universe = table.get("universe")
    if not isinstance(universe, dict) or sorted(universe) != sorted(EQUITY_CLASSES):
        problems.append(f"equity_money.universe lists symbols under exactly {list(EQUITY_CLASSES)}")
    else:
        listed: list[str] = []
        for klass in EQUITY_CLASSES:
            symbols = universe[klass]
            if not isinstance(symbols, list) or any(not isinstance(s, str) or not _TICKER.fullmatch(s) for s in symbols):
                problems.append(f"equity_money.universe.{klass} is a list of tickers: {symbols!r}")
            else:
                listed += symbols
        twice = sorted({s for s in listed if listed.count(s) > 1})
        if twice:
            problems.append(f"equity_money.universe lists {', '.join(twice)} more than once")

    def order(first: str, second: str, why: str) -> None:
        if first in values and second in values and not values[first] < values[second]:
            problems.append(f"equity_money.{first} ({values[first]}) must be under {second} ({values[second]}): {why}")

    panel, probe = "panel.sleeve_share", "probe.sleeve_share"
    if panel in values and probe in values and values[panel] > values[probe]:
        problems.append(f"equity_money.{panel} ({values[panel]}) is above {probe} ({values[probe]}): a panel program's "
                        "sleeve is never larger than a Probe's")
    hold, cap = "holds.default_max_hold_sessions", "holds.max_hold_sessions"
    if hold in values and cap in values and values[hold] > values[cap]:
        problems.append(f"equity_money.{hold} ({values[hold]}) is above {cap} ({values[cap]}): the default hold is inside "
                        "the lane's cap")
    for klass in EQUITY_CLASSES:
        first, last = f"order_path.entry_collar_bp.{klass}", f"order_path.max_collar_bp.{klass}"
        if first in values and last in values and values[first] > values[last]:
            problems.append(f"equity_money.{first} ({values[first]}) is above {last} ({values[last]}): a collar only widens")
    order("order_path.open_send_after_open_s", "order_path.entry_until_after_open_s", "entries are sent before their cut-off")
    order("order_path.close_until_before_close_s", "order_path.close_send_before_close_s",
          "the close window is sent before its cut-off")
    order("order_path.bars_after_close_s", "order_path.decide_after_close_s", "programs decide on the day's bars")
    order("order_path.preopen_before_open_s", "order_path.audit_before_open_s", "the bars' audit comes before the pre-open")
    # The event lane's rows (release R2): a learning position never larger than a Probe one, a Probe one never larger
    # than a Sized one, nor any than the name's own wall (the one-share cap neither); each auction's sends start after
    # its decision and end before the venue's cut-off.
    order_eq = (("event.position_share.learning", "event.position_share.probe",
                 "a learning position is never larger than a Probe one"),
                ("event.position_share.probe", "event.position_share.sized", "a Probe position is never larger than a Sized one"),
                ("event.position_share.sized", "event.per_name_share", "a position is never larger than the name's wall"),
                ("event.one_share_max.learning", "event.per_name_share", "one share is never above the name's wall"),
                ("event.one_share_max.probe", "event.per_name_share", "one share is never above the name's wall"))
    for first, second, why in order_eq:
        if first in values and second in values and values[first] > values[second]:
            problems.append(f"equity_money.{first} ({values[first]}) is above {second} ({values[second]}): {why}")
    order("event.order_path.open_send_before_open_s", "event.order_path.open_decide_before_open_s",
          "the open's sends start after its decision")
    order("event.order_path.open_until_before_open_s", "event.order_path.open_send_before_open_s",
          "the open's sends end after they start")
    order("event.order_path.close_send_before_close_s", "event.order_path.close_decide_before_close_s",
          "the close's sends start after its decision")
    order("event.order_path.close_until_before_close_s", "event.order_path.close_send_before_close_s",
          "the close's sends end after they start")
    # THE TWO EQUITY DAY ORDER LINES (release 1019c): the event kind's own (`event.max_orders_day`) never above the
    # gateway's day line in force, and with the old lanes' (`order_path.max_orders_day`) never above the House-wide line
    # in force (`options_money.order_path.max_orders_day`: both books' orders together). An options table that cannot
    # be read here is `options_money_problems`' to refuse.
    lines = (constitution or CONSTITUTION).get("options_money")
    lines = lines if isinstance(lines, dict) else {}
    try:
        house = Decimal(str((lines.get("order_path") or {})["max_orders_day"]))
        gateway = Decimal(str((lines.get("gateway") or {})["max_day_orders"]))
    except (KeyError, TypeError, InvalidOperation, ValueError, AttributeError):
        house = gateway = None
    event_line, old_line = values.get("event.max_orders_day"), values.get("order_path.max_orders_day")
    if event_line is not None and gateway is not None and gateway.is_finite() and event_line > gateway:
        problems.append(f"equity_money.event.max_orders_day ({event_line}) is above the gateway's day line "
                        f"(options_money.gateway.max_day_orders, {gateway})")
    if event_line is not None and old_line is not None and house is not None and house.is_finite() and \
            event_line + old_line > house:
        problems.append(f"equity_money.event.max_orders_day ({event_line}) and order_path.max_orders_day ({old_line}) "
                        f"are above the House-wide line together (options_money.order_path.max_orders_day, {house})")
    return problems


#: The gateway's `wrangler.jsonc` vars that repeat the money table: `league.ci` requires them equal.
GATEWAY_VARS = {
    "MAX_ORDER_MAX_LOSS_USD": "gateway.order_max_loss_usd",
    "MAX_ORDER_EQUITY_SHARE": "gateway.order_equity_share",
    "MAX_DAY_EQUITY_SHARE": "gateway.day_equity_share",
    "MAX_DAY_ORDERS": "gateway.max_day_orders",
    "MAX_DAY_OPEN_ORDERS": "gateway.max_day_open_orders",
    "CREDIT_MIN_EQUITY_USD": "credit_min_equity_usd",
}

#: Grants recorded before the money digest existed pinned the whole constitution. Such a grant
#: stays valid only while the money rules are EXACTLY those in force when it was granted:
#: {full digest at grant: money digest of that same constitution}.
LEGACY_GRANT_DIGESTS = {
    'bfdbbf8567205153a18eed023819e9bf52e5d989dae5d113d60fd5c1a1e5fad1':
        'c72854cc5ede3b7f5cab0cdcfb6345714c105e111619e6b68d1fb0ccad6cc985',
}


#: Pinned by `league/tests/test_constitution.py`. Changing the constitution means changing this
#: line too, in a commit the owner makes: CI refuses any other author's change to this file.
PINNED_DIGEST = '84dc7041f2de5d7811698284cb7287a334cd341198c0e2b09f4f27f70c0c8fe2'

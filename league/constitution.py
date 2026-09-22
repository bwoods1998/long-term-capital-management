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
        "look_every_active_blocks": 5,
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
        "replay": {"min_trades": 10, "min_blocks": 20, "min_deflated_sharpe": 0.0, "min_oos_blocks": 8},
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
        "paper": {"gate": "screen", "min_active_blocks": 4, "min_active_blocks_day": 2, "max_drawdown": 0.15},
        # Rung 2 -> 3: real fills at $1 to $10 a position, and the confidence bound, because
        # this is the gate that protects real size. Promotion spends its own alpha: the looks
        # that can only kill (before `min_active_blocks`) spend none of it.
        # Owner-requested accelerated experiment, Sept 20: remove the 30-hour minimum.
        # Five active blocks retain the conventional route. The completed-exposure route below
        # has no elapsed-time minimum; both routes share the original promotion error budget.
        "micro": {"gate": "bound", "min_active_blocks": 5},
        # Kept at 10: at 5 the qualifying record was too short a reference for drift, and a fresh
        # promotion was demoted as "decayed" within minutes in the ladder's own integration test.
        "completed_exposures": {"min_episodes": 10, "look_every_episodes": 5, "promotion_alpha_share": 0.5},
        # A small edge proves itself across a family sooner than in one agent (the first run's
        # favourites edge was only ever measurable pooled). An agent on rung 2 whose own record is
        # positive but not yet decisive may be scaled on its family's pooled real-money record:
        # one series, the mean growth of the family's rung-2 agents block by block, tested at its
        # own alpha with its own looks.
        "family": {"alpha": 0.05, "min_members": 2, "min_member_active_blocks": 10},
        # Death at any rung above 0: evidence that growth is negative, or the stake is going.
        "death": {"min_active_blocks": 20, "max_drawdown": 0.30},
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
        "3": {"max_order_usd": "75", "kelly_fraction": 0.5, "max_share_of_venue": 0.4},
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
PINNED_DIGEST = '6ebd41acaaca4195da74bb8a387d43efa98f8b52ce9ddd211b10f2a89c784c26'

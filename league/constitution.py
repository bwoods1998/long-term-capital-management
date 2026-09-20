"""The constitution: what no model and no code path on Sail may change.

These numbers were written down before any agent traded, which is what makes the tests
pre-registered. They are constants in a file that Merton's pull requests are refused for touching
(`league/ci.py` guards the path), and the House records this file's digest on the ledger every
time it starts, so a change is visible in the public record.

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
        # No promotion on fewer closed trades than this, however good the blocks look.
        "min_closed_trades": 10,
        # Rung 0 -> 1: mechanical replay, and the only gate before a PAPER seat, which costs the
        # owner nothing but compute. The deflated Sharpe is the confidence that the idea beats the
        # best of the trials in its line; 0.75 is a three-to-one bet on free information, and the
        # bar for money is the screen, the audit and the tuition cap that come after. The volume
        # thresholds are NOT relaxed: what the league is short of is strategies that trade at all.
        "replay": {"min_trades": 20, "min_blocks": 30, "min_deflated_sharpe": 0.75, "min_oos_blocks": 8},
        # Rung 1 -> 2: a SCREEN, then the frontier audit. Not a confidence bound: a bound strict
        # enough to mean something needs hundreds of trades (the first run's one measured edge
        # could not pass it in a month), and what it would protect is a $25 stake. The loss of the
        # micro rung is capped in dollars instead: see `tuition`.
        # `min_active_blocks` is in BLOCKS, and a block is an hour or a calendar day by the
        # strategy's own declared horizon: 15 days is the whole expedition, so a daily strategy
        # could never reach real money inside one. What the screen really asks for is a week of
        # honest forward trading, which is 15 hourly blocks or 5 daily ones.
        "paper": {"gate": "screen", "min_active_blocks": 15, "min_active_blocks_day": 5, "max_drawdown": 0.15},
        # Rung 2 -> 3: real fills at $1 to $10 a position, and the confidence bound, because
        # this is the gate that protects real size. Promotion spends its own alpha: the looks
        # that can only kill (before `min_active_blocks`) spend none of it.
        "micro": {"gate": "bound", "min_active_blocks": 30},
        # A small edge proves itself across a family sooner than in one agent (the first run's
        # favourites edge was only ever measurable pooled). An agent on rung 2 whose own record is
        # positive but not yet decisive may be scaled on its family's pooled real-money record:
        # one series, the mean growth of the family's rung-2 agents block by block, tested at its
        # own alpha with its own looks.
        "family": {"alpha": 0.05, "min_members": 2, "min_member_active_blocks": 10},
        # Death at any rung above 0: evidence that growth is negative, or the stake is going.
        "death": {"min_active_blocks": 20, "max_drawdown": 0.30},
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
        "2": {"stake_usd": "25", "max_position_usd": "10", "max_order_usd": "10", "option_max_position_usd": "20"},
        "3": {"max_order_usd": "75", "kelly_fraction": 0.25, "max_share_of_venue": 0.25},
    },
}


def digest(constitution: dict[str, Any] | None = None) -> str:
    """The SHA-256 of the constitution's canonical JSON."""
    text = json.dumps(constitution or CONSTITUTION, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: Pinned by `league/tests/test_constitution.py`. Changing the constitution means changing this
#: line too, in a commit the owner makes: CI refuses any other author's change to this file.
PINNED_DIGEST = "65f7691792da41b71bac8378af29274fb06d4d56f31369fd72220dd560a1327f"

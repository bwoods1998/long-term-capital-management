"""The constitution: what no model and no code path on Sail may change.

These numbers were written down before any agent traded, which is what makes the tests
pre-registered. They are constants in a file that Astra's pull requests are refused for touching
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
        "sail_reserve_usd": "10",
    },
    "order_caps": {"max_order_usd": "75", "max_day_usd": "4000", "max_day_orders": 2000},
    "ladder": {
        # One-sided error rate for every promotion and every statistical death, spent across
        # looks as alpha * 6 / (pi^2 k^2) so that looking often can never buy a false pass.
        "alpha": 0.05,
        "look_every_active_blocks": 5,
        # No promotion on fewer closed trades than this, however good the blocks look.
        "min_closed_trades": 10,
        # Rung 0 -> 1: mechanical replay. Every replay ever run for the family is a trial.
        "replay": {"min_trades": 20, "min_blocks": 30, "min_deflated_sharpe": 0.90, "min_oos_blocks": 8},
        # Rung 1 -> 2: forward paper test, then the frontier audit.
        "paper": {"min_active_blocks": 30},
        # Rung 2 -> 3: real fills at $1 to $10 a position.
        "micro": {"min_active_blocks": 30},
        # Death at any rung above 0: evidence that growth is negative, or the stake is going.
        "death": {"min_active_blocks": 20, "max_drawdown": 0.30},
        # Drift at rungs 2 and 3: a CUSUM on block growth against the record that earned the rung.
        # h = 6 is about one false alarm in 1,300 blocks (h = 4 would be one a week on hourly blocks).
        "drift": {"k": 0.5, "h": 6.0, "window_blocks": 60, "min_reference_blocks": 10},
        # A record with this share of winning trades is judged on an exact (Clopper-Pearson) bound
        # of its loss rate as well, because a t-interval flatters it until the first loss arrives.
        "lopsided_win_rate": 0.80,
    },
    "rungs": {
        # Paper agents are held to the live account's real limits, not the paper account's.
        "1": {"stake_usd": "200", "max_position_usd": "100", "max_order_usd": "75"},
        "2": {"stake_usd": "25", "max_position_usd": "10", "max_order_usd": "10"},
        "3": {"max_order_usd": "75", "kelly_fraction": 0.25, "max_share_of_venue": 0.25},
    },
}


def digest(constitution: dict[str, Any] | None = None) -> str:
    """The SHA-256 of the constitution's canonical JSON."""
    text = json.dumps(constitution or CONSTITUTION, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: Pinned by `league/tests/test_constitution.py`. Changing the constitution means changing this
#: line too, in a commit the owner makes: CI refuses any other author's change to this file.
PINNED_DIGEST = "e07748b44146f659515d97307ee5a97f712d06b195eec8e1e0eefd58bd742063"

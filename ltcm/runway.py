"""The floor's spend policy: no daily cap, a runway.

The owner's instruction is that infrastructure spend has no ceiling as long as he is told when
to top up and the floor stops gracefully when he does not. So the only limit on model spend is
the Sail credit itself, read live, and the policy is about *how* the floor approaches zero:

* **open** -- the balance covers more than `throttle_days` of the trailing burn. No cap: the
  floor may commit everything above the reserve today if the work calls for it.
* **throttled** -- the runway is shorter than `throttle_days`. The remaining credit is stretched
  over `stretch_days`, only live desks keep their sessions, and the owner has already been told.
* **stopped** -- the balance is at or under the reserve. No new model call starts; marks, order
  polling, settlements and publication continue, because they cost nothing. Credit added at
  Sail lifts the floor back to `open` on the next tick with no other step.
* **unknown** -- the balance could not be read. The floor keeps working under the last known
  numbers, or under `fallback_cap_usd` when it never read one; an outage at Sail's usage API is
  not a reason to stop trading.

One fuse survives: a single desk may not commit more than `desk_fuse_pct` of the spendable
credit in a day. It is not a budget -- a desk working normally never reaches it -- it is the
difference between a desk stuck in a tool loop costing an afternoon and costing the balance.

Everything here is pure arithmetic on numbers the service reads elsewhere, so it is tested
without a network and published verbatim in `ops.budget`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Mapping

ZERO = Decimal(0)
CENTS = Decimal("0.01")
DAYS = Decimal("0.1")
MODES = ("open", "throttled", "stopped", "unknown")

DEFAULT_POLICY: dict[str, Any] = {
    "reserve_usd": "10",
    "throttle_days": "3",
    "stretch_days": "5",
    "desk_fuse_pct": "0.25",
    "desk_fuse_min_usd": "10",
    "fallback_cap_usd": "40",
    "infra_usd_per_day": "0.30",
    "min_burn_usd_per_day": "0.50",
}


def _money(value: Any) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True)
class Runway:
    mode: str
    balance_usd: Decimal | None
    reserve_usd: Decimal
    spendable_usd: Decimal
    burn_usd_per_day: Decimal
    runway_days: Decimal | None
    cap_usd: Decimal
    desk_fuse_usd: Decimal
    live_only: bool

    def to_payload(self) -> dict[str, str | None]:
        """Strings only, the way the event log and the site want money."""
        return {
            "mode": self.mode,
            "balance_usd": None if self.balance_usd is None else str(self.balance_usd),
            "reserve_usd": str(self.reserve_usd),
            "spendable_usd": str(self.spendable_usd),
            "burn_usd_per_day": str(self.burn_usd_per_day),
            "runway_days": None if self.runway_days is None else str(self.runway_days),
            "cap_usd": str(self.cap_usd),
            "desk_fuse_usd": str(self.desk_fuse_usd),
        }


def assess(
    balance_usd: Any,
    model_burn_usd_per_day: Any,
    policy: Mapping[str, Any] | None = None,
) -> Runway:
    """Where the floor stands against its credit. `balance_usd` may be None (unreadable)."""
    p = {**DEFAULT_POLICY, **dict(policy or {})}
    reserve = _money(p["reserve_usd"])
    throttle_days = _money(p["throttle_days"])
    stretch_days = max(_money(p["stretch_days"]), Decimal(1))
    fuse_pct = _money(p["desk_fuse_pct"])
    fuse_min = _money(p["desk_fuse_min_usd"])
    fallback = _money(p["fallback_cap_usd"])
    infra = _money(p["infra_usd_per_day"])
    min_burn = _money(p["min_burn_usd_per_day"])

    burn = max(_money(model_burn_usd_per_day or 0), ZERO) + infra
    burn = max(burn, min_burn).quantize(CENTS, rounding=ROUND_DOWN)

    if balance_usd is None:
        return Runway(
            mode="unknown",
            balance_usd=None,
            reserve_usd=reserve,
            spendable_usd=ZERO,
            burn_usd_per_day=burn,
            runway_days=None,
            cap_usd=fallback,
            desk_fuse_usd=max(fuse_min, (fallback * fuse_pct)).quantize(CENTS, rounding=ROUND_DOWN),
            live_only=False,
        )

    balance = _money(balance_usd).quantize(CENTS, rounding=ROUND_DOWN)
    spendable = max(balance - reserve, ZERO)
    runway = (spendable / burn).quantize(DAYS, rounding=ROUND_DOWN)

    if spendable <= ZERO:
        mode, cap, live_only = "stopped", ZERO, True
    elif runway < throttle_days:
        mode, live_only = "throttled", True
        cap = (spendable / stretch_days).quantize(CENTS, rounding=ROUND_DOWN)
    else:
        mode, cap, live_only = "open", spendable, False
    fuse = max(fuse_min, (spendable * fuse_pct)).quantize(CENTS, rounding=ROUND_DOWN)
    fuse = min(fuse, cap) if cap > ZERO else ZERO
    return Runway(
        mode=mode,
        balance_usd=balance,
        reserve_usd=reserve,
        spendable_usd=spendable,
        burn_usd_per_day=burn,
        runway_days=runway,
        cap_usd=cap,
        desk_fuse_usd=fuse,
        live_only=live_only,
    )

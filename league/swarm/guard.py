"""The Sail guard: the swarm stops spending before the House is at risk.

Running out of Sail credits pauses EVERY box, the House included. So every few minutes the guard reads
Sail's balance (the usage summary through `Provider.check_balance`) and brakes the swarm, Gym boxes and
researchers to zero, when:

- the balance is below 2 x the non-swarm burn a day + `margin_usd` (plan: "two days of the House's burn
  plus $30"). The non-swarm burn is Sail's own 24-hour spend less what the swarm itself booked in those
  24 hours, and never less than `house_burn_usd_day`: it covers the House box, its model calls, and any
  other box (the data box) that eats the same credits;
- the swarm's Sail spend since the burst began reached `burst_cap_usd` ($350 until Monday's open);
- after the burst: the swarm's Sail spend today reached `after_burst_usd_day` less the House's burn;
- the balance could not be read for `unknown_brake_seconds` (a guard that cannot see does not spend).

It releases when the balance is back above the line plus `release_margin_usd` (hysteresis), the caps
allow, and a reading is fresh. Every change of state is a `swarm.guard` event. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, Callable, Mapping

from .store import SwarmStore

SWARM_SAIL_KINDS = ("sail_model", "gym_box")


def _epoch(text: str) -> float:
    return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()


class SailGuard:
    """The guard (the module docstring). `reader()` returns (balance_usd or None, sail_burn_usd_per_day or None)."""

    def __init__(self, store: SwarmStore, settings: Mapping[str, Any], reader: Callable[[], tuple[Any, Any]], *,
                 clock: Callable[[], float] = time.time):
        self.store = store
        self.settings = settings
        self.reader = reader
        self.clock = clock
        state = store.get("guard", {}) or {}
        self.braked: bool = bool(state.get("braked", False))
        self.reason: str = str(state.get("reason") or "")
        self.last_ok: float = float(state.get("last_ok") or 0.0)
        self.last: dict[str, Any] = dict(state.get("last") or {})
        self.checked_at: float = 0.0
        if not store.get("burst_started_at"):
            store.put("burst_started_at", self.clock())

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("guard", {})

    def allows(self, kind: str = "any") -> bool:
        return not self.braked

    def due(self) -> bool:
        return self.clock() - self.checked_at >= float(self.cfg.get("every_seconds", 180))

    def check(self) -> dict[str, Any]:
        """Read the balance and decide. Returns the reading and the decision."""
        now = self.clock()
        self.checked_at = now
        cfg = self.cfg
        try:
            balance, burn = self.reader()
        except Exception:  # noqa: BLE001 - unreadable is unknown
            balance, burn = None, None
        balance = float(balance) if balance is not None else None
        burn = float(burn) if burn is not None else None
        swarm_day = self.store.spent(SWARM_SAIL_KINDS, since=now - 86400)
        house = max(float(cfg.get("house_burn_usd_day", 2.0)), (burn - swarm_day) if burn is not None else 0.0)
        line = 2.0 * house + float(cfg.get("margin_usd", 30.0))
        burst_start = float(self.store.get("burst_started_at", now))
        burst_until = _epoch(cfg.get("burst_until", "2026-09-28T13:30:00Z"))
        in_burst = now < burst_until
        burst_spent = self.store.spent(SWARM_SAIL_KINDS, since=burst_start)
        midnight = now - (now % 86400)
        today_spent = self.store.spent(SWARM_SAIL_KINDS, since=midnight)
        reasons = []
        if balance is None:
            if now - self.last_ok >= float(cfg.get("unknown_brake_seconds", 900)):
                reasons.append("the Sail balance could not be read for 15 minutes")
        else:
            self.last_ok = now
            release = line + (float(cfg.get("release_margin_usd", 5.0)) if self.braked else 0.0)
            if balance < release:
                reasons.append(f"the Sail balance {balance:.2f} is under the House's line {release:.2f} "
                               f"(2 x {house:.2f} a day + {float(cfg.get('margin_usd', 30.0)):.0f})")
        if in_burst and burst_spent >= float(cfg.get("burst_cap_usd", 350.0)):
            reasons.append(f"the burst's Sail cap is spent ({burst_spent:.2f} of {float(cfg.get('burst_cap_usd', 350.0)):.0f})")
        if not in_burst:
            day_cap = max(0.0, float(cfg.get("after_burst_usd_day", 12.0)) - house)
            if today_spent >= day_cap:
                reasons.append(f"today's Sail allowance after the burst is spent ({today_spent:.2f} of {day_cap:.2f})")
        was = self.braked
        self.braked = bool(reasons)
        self.reason = "; ".join(reasons)
        self.last = {"balance": balance, "burn_day": burn, "house_day": round(house, 2), "line": round(line, 2),
                     "swarm_day": round(swarm_day, 4), "burst_spent": round(burst_spent, 4), "today_spent": round(today_spent, 4),
                     "in_burst": in_burst, "braked": self.braked, "reason": self.reason, "at": now}
        self.store.put("guard", {"braked": self.braked, "reason": self.reason, "last_ok": self.last_ok, "last": self.last})
        if was != self.braked:
            self.store.event("swarm.guard", None, {"action": "brake" if self.braked else "release", **self.last})
        return dict(self.last)


def provider_reader(provider: Any) -> Callable[[], tuple[Any, Any]]:
    """(balance, burn a day) from `ltcm.provider.Provider` (its 60-second cache)."""
    def read() -> tuple[Any, Any]:
        balance = provider.check_balance()
        return balance, provider.sail_burn_usd_per_day()
    return read


__all__ = ["SailGuard", "provider_reader", "SWARM_SAIL_KINDS"]

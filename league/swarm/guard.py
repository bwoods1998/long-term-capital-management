"""The Sail guard: the swarm stops spending before the House is at risk.

Running out of Sail credits pauses EVERY box, the House included. So every few minutes the guard reads
Sail's balance (the usage summary through `Provider.check_balance`) and brakes the swarm, Gym boxes and
researchers to zero, when:

- the balance is below 2 x the non-swarm burn a day + `margin_usd` (plan: "two days of the House's burn
  plus $30"). The non-swarm burn is Sail's own 24-hour spend less what the swarm itself booked in those
  24 hours, and never less than `house_burn_usd_day`: it covers the House box, its model calls, and any
  other box (the data box) that eats the same credits;
- the swarm's Sail spend since the burst began reached `burst_cap_usd` ($350 until Monday's open);
- after the burst: the swarm's Sail spend today (UTC) reached `after_burst_usd_day` less the House's burn,
  or Sail's own meter today (every fall of the balance since midnight, the whole account) reached
  `after_burst_usd_day`;
- the balance could not be read (FAIL CLOSED: at once, and a failed read never releases a brake), or no
  good reading is `stale_seconds` old;
- the burst's spend reaches the cap, counted as the larger of what the swarm booked and Sail's own meter
  (every fall of the balance since the burst began: every box and model call on the account);
- the state disk has under `min_free_disk_gb` free (the House's ledger lives there).

It releases only on a fresh good reading above the line plus `release_margin_usd` (hysteresis) with the
caps allowing. Every change of state is a `swarm.guard` event. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import shutil
import time
from typing import Any, Callable, Mapping

from .store import SwarmStore

SWARM_SAIL_KINDS = ("sail_model", "gym_box")


def _epoch(text: str) -> float:
    return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()


class SailGuard:
    """The guard (the module docstring). `reader()` returns (balance_usd or None, sail_burn_usd_per_day or None);
    `disk_free()` the state root's free bytes."""

    def __init__(self, store: SwarmStore, settings: Mapping[str, Any], reader: Callable[[], tuple[Any, Any]], *,
                 clock: Callable[[], float] = time.time, disk_free: Callable[[], float] | None = None):
        self.store = store
        self.settings = settings
        self.reader = reader
        self.clock = clock
        self.disk_free = disk_free or (lambda: float(shutil.disk_usage(store.root).free))
        state = store.get("guard", {}) or {}
        self.braked: bool = bool(state.get("braked", True))  # nothing is allowed before a first good reading
        self.reason: str = str(state.get("reason") or "no reading yet")
        self.last_ok: float = float(state.get("last_ok") or 0.0)
        self.last: dict[str, Any] = dict(state.get("last") or {})
        self.checked_at: float = 0.0
        if not store.get("burst_started_at"):
            store.put("burst_started_at", self.clock())

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("guard", {})

    def allows(self, kind: str = "any") -> bool:
        """FAIL CLOSED: braked, or no good reading for `stale_seconds`, allows no new cycle, round or box."""
        return not self.braked and self.clock() - self.last_ok < float(self.cfg.get("stale_seconds", 600))

    def due(self) -> bool:
        return self.clock() - self.checked_at >= float(self.cfg.get("every_seconds", 180))

    def _metered(self, balance: float | None, now: float) -> tuple[float, float]:
        """Sail's own meter: every fall of the balance between two good readings (a rise is a top-up, never negative
        spend), since the burst began and since this UTC midnight. It counts every box and model call on the account,
        booked or not."""
        spent = float(self.store.get("metered_spent", 0.0) or 0.0)
        day = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
        today = self.store.get("metered_today") or {}
        today_spent = float(today.get("spent") or 0.0) if today.get("day") == day else 0.0
        previous = self.store.get("metered_last_balance")
        if balance is not None:
            if previous is not None and balance < float(previous):
                spent += float(previous) - balance
                today_spent += float(previous) - balance
            self.store.put("metered_last_balance", balance)
            self.store.put("metered_spent", round(spent, 4))
            self.store.put("metered_today", {"day": day, "spent": round(today_spent, 4)})
        return spent, today_spent

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
        # `measured_burn`: Sail's own 24-hour spend less the swarm's, never below the floor. It counts every other box on
        # the account (the data box) and, for a day after a restart, whatever ran before it; false (the default) trusts
        # the configured `house_burn_usd_day` alone.
        measured = (burn - swarm_day) if burn is not None and cfg.get("measured_burn", False) else 0.0
        house = max(float(cfg.get("house_burn_usd_day", 1.0)), measured)
        line = 2.0 * house + float(cfg.get("margin_usd", 30.0))
        burst_start = float(self.store.get("burst_started_at", now))
        burst_until = _epoch(cfg.get("burst_until", "2026-09-28T13:30:00Z"))
        in_burst = now < burst_until
        metered, metered_today = self._metered(balance, now)
        burst_spent = max(self.store.spent(SWARM_SAIL_KINDS, since=burst_start), metered if in_burst else 0.0)
        midnight = now - (now % 86400)
        today_spent = self.store.spent(SWARM_SAIL_KINDS, since=midnight)
        reasons = []
        if balance is None:
            # FAIL CLOSED: a failed read never releases a brake, and brakes an unbraked guard at once.
            reasons.append("the Sail balance could not be read" + (" (braked before it)" if self.braked else ""))
        else:
            self.last_ok = now
            release = line + (float(cfg.get("release_margin_usd", 5.0)) if self.braked else 0.0)
            if balance < release:
                reasons.append(f"the Sail balance {balance:.2f} is under the House's line {release:.2f} "
                               f"(2 x {house:.2f} a day + {float(cfg.get('margin_usd', 30.0)):.0f})")
        if in_burst and burst_spent >= float(cfg.get("burst_cap_usd", 350.0)):
            reasons.append(f"the burst's Sail cap is spent ({burst_spent:.2f} of {float(cfg.get('burst_cap_usd', 350.0)):.0f})")
        if not in_burst:
            account_cap = float(cfg.get("after_burst_usd_day", 12.0))
            day_cap = max(0.0, account_cap - house)
            if today_spent >= day_cap:
                reasons.append(f"today's Sail allowance after the burst is spent ({today_spent:.2f} of {day_cap:.2f})")
            elif metered_today >= account_cap:
                reasons.append(f"today's Sail allowance after the burst is spent by Sail's meter ({metered_today:.2f} of "
                               f"{account_cap:.2f} for the account)")
        try:
            free_gb = self.disk_free() / 2 ** 30
        except OSError:
            free_gb = None
        if free_gb is not None and free_gb < float(cfg.get("min_free_disk_gb", 3.0)):
            reasons.append(f"the state disk has {free_gb:.1f} GB free (the House's ledger needs room)")
        was = self.braked if self.store.get("guard") is not None else None  # the first check says where it starts
        self.braked = bool(reasons)
        self.reason = "; ".join(reasons)
        self.last = {"balance": balance, "burn_day": burn, "house_day": round(house, 2), "line": round(line, 2),
                     "swarm_day": round(swarm_day, 4), "burst_spent": round(burst_spent, 4), "metered_spent": round(metered, 4),
                     "metered_today": round(metered_today, 4),
                     "today_spent": round(today_spent, 4), "free_disk_gb": None if free_gb is None else round(free_gb, 1),
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

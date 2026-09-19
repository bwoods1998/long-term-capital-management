"""The Sail budget: $100 a month, metered by the House because Sail has no spend caps.

Sail reports a credit balance. The House reads it, records it, and counts a month's spend as the
sum of the falls in that balance between readings (a top-up is a rise, and is simply not a fall).
At the monthly line, or at the reserve that keeps the House's own box alive, research and
practice stop; only agents holding real-money positions are still woken, so they can exit.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable

from .constitution import CONSTITUTION
from .ledger import Ledger, now_iso

ZERO = Decimal(0)


class Budget:
    def __init__(self, ledger: Ledger, read_balance: Callable[[], Decimal | None], *, clock=time.time, every_seconds: int = 900):
        self.ledger = ledger
        self.read_balance = read_balance
        self.clock = clock
        self.every = every_seconds
        self.cap = Decimal(CONSTITUTION["budgets"]["sail_month_usd"])
        self.reserve = Decimal(CONSTITUTION["budgets"]["sail_reserve_usd"])
        self._last_check = 0.0
        self._mode = "open"

    def month_spend(self, month: str | None = None) -> Decimal:
        month = month or now_iso(self.clock)[:7]
        total = ZERO
        for entry in self.ledger.iter(kinds="ops.budget"):
            if entry.payload.get("what") == "sail" and entry.at[:7] == month:
                total += Decimal(str(entry.payload.get("spent_usd") or 0))
        return total

    def _last_balance(self) -> Decimal | None:
        rows = [e for e in self.ledger.read(kinds="ops.budget", limit=500, newest=True) if e.payload.get("what") == "sail" and e.payload.get("balance_usd") is not None]
        return Decimal(str(rows[-1].payload["balance_usd"])) if rows else None

    def check(self, *, force: bool = False) -> str:
        """Read the balance if it is time to, record it, and return the mode: open or stopped."""
        now = self.clock()
        if not force and now - self._last_check < self.every:
            return self._mode
        self._last_check = now
        try:
            balance = self.read_balance()
        except Exception:  # noqa: BLE001 - an unreadable balance changes nothing
            balance = None
        if balance is None:
            return self._mode
        previous = self._last_balance()
        spent = max(previous - balance, ZERO) if previous is not None else ZERO
        month = self.month_spend() + spent
        mode = "stopped" if month >= self.cap or balance <= self.reserve else "open"
        self.ledger.append(
            "ops.budget",
            {"what": "sail", "balance_usd": format(balance, "f"), "spent_usd": format(spent, "f"), "month_usd": format(month, "f"),
             "cap_usd": format(self.cap, "f"), "mode": mode},
        )
        self._mode = mode
        return mode

    @property
    def mode(self) -> str:
        return self._mode

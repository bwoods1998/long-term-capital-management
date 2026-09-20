"""The Sail budget: $100 a month, metered by the House because Sail has no spend caps.

Sail reports a credit balance. The House reads it, records it, and counts a month's spend as the
sum of the falls in that balance between readings (a top-up is a rise, and is simply not a fall).
At the monthly line, or at the reserve that keeps the House's own box alive, research and
practice stop; only agents holding real-money positions are still woken, so they can exit. That is
the ACCOUNT's guard and the only one here: the expedition's own budget is the pacer's to enforce,
at every kind of spending, and a meter that also latched on it could never be unlatched.
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
        self.pacer: Any = None  # set by the House: the expedition's own ceiling on Sail
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
        # The meter guards the ACCOUNT -- the month's line and the reserve that keeps the House's
        # own box alive. It used to stop on the expedition's budget too, and that was a latch with
        # no key: `Pacer.spent` only ever grows, nothing rebases the expedition's start, and the
        # test never asked whether the expedition was still running. Once the fortnight's $100 was
        # spent the floor was stopped FOR EVER -- through every restart, every rollback, into new
        # calendar months, with the credit balance topped back up -- and silently, because the
        # notice that would have said so sits inside the payout the same flag closes. Verified by
        # running the real meter forward 140 days. The expedition is the pacer's to enforce, and
        # it already does, at every kind of spending, through `may_spend`.
        mode = "stopped" if month >= self.cap or balance <= self.reserve else "open"
        self.ledger.append(
            "ops.budget",
            {"what": "sail", "balance_usd": format(balance, "f"), "spent_usd": format(spent, "f"), "month_usd": format(month, "f"),
             "cap_usd": format(self.cap, "f"), "mode": mode},
        )
        if mode != self._mode:
            why = "the month's line" if month >= self.cap else "the reserve that keeps the House's box alive"
            self.ledger.append("ops.alert", {"level": "error" if mode == "stopped" else "info",
                                             "text": f"the Sail meter is {mode}"
                                                     + (f": {why} (balance ${balance:.2f}, month ${month:.2f} of ${self.cap})" if mode == "stopped" else "")})
        self._mode = mode
        return mode

    @property
    def mode(self) -> str:
        return self._mode

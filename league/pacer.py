"""The expedition's pace: the owner's budgets, spent evenly and spent in full.

The owner funds a run of fixed length (the constitution's `budgets.expedition`: $100 of Sail and
$100 of the frontier model over fourteen days from Sept 19, 2026) and wants it USED: a budget left
unspent is research that was not done. A hard cap alone cannot do that, and a schedule written in
advance cannot either, because nobody knows what a research pass or an architect's pass will cost
next week. So the House paces from what was really spent:

    today's allowance = (the budget - everything spent so far) / (the days that are left)

recomputed every day, so a quiet day's unspent share rolls forward and a dear day is paid back.
Three things follow the allowance: the day's pool of compute credits (what agents can spend on
research), whether another research pass may start now, and whether Merton may sit down again.
When a budget is gone, or the last day is over, that kind of spending stops for good and the
owner is told once. The monthly caps (the gateway's for the frontier model, the House's meter for
Sail) stand behind this as before.

Sail is metered from the falls in its credit balance (`league/budget.py`), which is where an
agent's research lands: a research pass runs on Sail's own inference (`ltcm/provider.py`), not on
the frontier model. The frontier budget is the gateway's: the cost it reports on each call, which
the ledger records on `merton.pass` and `audit.verdict` rows.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from .constitution import CONSTITUTION
from .ledger import Ledger

ZERO = Decimal(0)
KINDS = ("sail", "openai")


class Pacer:
    def __init__(self, ledger: Ledger, *, clock=time.time, expedition: Mapping[str, Any] | None = None):
        self.ledger = ledger
        self.clock = clock
        rules = dict(expedition or CONSTITUTION["budgets"]["expedition"])
        self.start = date.fromisoformat(str(rules["start"]))
        self.days = int(rules["days"])
        self.budget = {"sail": Decimal(str(rules["sail_usd"])), "openai": Decimal(str(rules["openai_usd"]))}
        self.front_load = Decimal(str(rules.get("front_load", 1)))
        self._cache: dict[str, tuple[float, dict[str, Decimal]]] = {}

    # ------------------------------------------------------------------ calendar
    def today(self) -> date:
        return datetime.fromtimestamp(self.clock(), tz=timezone.utc).date()

    def day(self) -> int:
        """0 on the first day; `days` and beyond once the expedition is over; negative before it."""
        return (self.today() - self.start).days

    def days_left(self) -> int:
        """Today counts as a day that is left."""
        return max(self.days - max(self.day(), 0), 0)

    def running(self) -> bool:
        return 0 <= self.day() < self.days

    # --------------------------------------------------------------------- spend
    def _spend(self, kind: str) -> dict[str, Decimal]:
        """{"total": since the expedition began, "today": since midnight UTC}, read from the ledger
        (at most once a minute: the rows that feed it are written far less often than it is asked)."""
        hit = self._cache.get(kind)
        if hit is not None and self.clock() - hit[0] < 60:
            return hit[1]
        first, today = self.start.isoformat(), self.today().isoformat()
        total = spent_today = ZERO
        if kind == "sail":
            rows = ((e.at, e.payload.get("spent_usd")) for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "sail")
        else:
            # Merton's own passes and the consultations agents buy from him (`merton.pass`), and the
            # auditor's verdicts. NOT `agent.research`: a research pass runs on Sail's own inference
            # (`ltcm/provider.py`), and the gateway's meter agrees -- on the first evening it had
            # billed $1.72 of frontier calls, every one a consult, a Merton pass or an audit.
            rows = ((e.at, e.payload.get("cost_usd")) for e in self.ledger.iter(kinds=("merton.pass", "audit.verdict")))
        for at, usd in rows:
            try:
                amount = Decimal(str(usd or 0))
            except ArithmeticError:
                continue
            if at[:10] >= first and amount > 0:
                total += amount
                if at[:10] == today:
                    spent_today += amount
        out = {"total": total, "today": spent_today}
        self._cache[kind] = (self.clock(), out)
        return out

    def spent(self, kind: str) -> Decimal:
        return self._spend(kind)["total"]

    def remaining(self, kind: str) -> Decimal:
        return max(self.budget[kind] - self.spent(kind), ZERO)

    def allowance(self, kind: str) -> Decimal:
        """What may be spent today: what is left over the days that are left, counting today, and
        then the front-loading ceiling on top. (What was already spent today is part of today's
        allowance, not taken from it twice.)

        The even share alone spreads an unused day thinly across every day that is left, so a
        budget that is behind takes the rest of the fortnight to catch up -- and early learning is
        worth more than late, because everything after is built on what it found. The owner asked
        for the budgets to be pushed harder after nine hours produced no promotion, so one day may
        spend up to `front_load` times its even share. That is a CEILING, not a target: nothing
        spends what nothing asks for, and because tomorrow's share is recomputed from what is
        really left, a hot day is paid for by cooler ones and neither budget can be overrun."""
        if not self.running():
            return ZERO
        spend = self._spend(kind)
        left_this_morning = max(self.budget[kind] - (spend["total"] - spend["today"]), ZERO)
        even = left_this_morning / Decimal(self.days_left())
        return min(even * self.front_load, left_this_morning)

    def room(self, kind: str) -> Decimal:
        """How much of today's allowance is still unspent. Zero when the budget or the run is over."""
        return max(self.allowance(kind) - self._spend(kind)["today"], ZERO)

    def may_spend(self, kind: str) -> bool:
        return self.room(kind) > 0 and self.remaining(kind) > 0

    def over(self, kind: str) -> bool:
        """True once this kind of spending has stopped for good."""
        return self.day() >= self.days or self.remaining(kind) <= 0

    # ---------------------------------------------------------------------- uses
    def credit_pool(self, *, share: Decimal = Decimal("0.85"), frontier_share: Decimal = Decimal("0.70"),
                    floor: Decimal = Decimal("0.50")) -> Decimal:
        """The day's pool of compute credits, out of both purses the owner funded.

        Most of the day's Sail allowance -- what an agent buys is mostly its sandbox seconds and
        its research tokens, and both are Sail costs -- and most of the day's frontier allowance,
        because the other thing it buys is Merton's time, billed at the gateway. Sized from Sail
        alone, a purse of about twenty cents a day could not buy a consultation priced at a dollar,
        so the agents that had EARNED the right to ask the frontier model for help could not afford
        to ask. Each kind of spending is still gated by its own budget (`may_spend`), so a wider
        purse cannot overrun either; it only stops the purse from being the thing that decides.

        The share the House keeps is what no agent is charged for: its own box and the agents'
        boxes between wakes. Measured Sept 20, 2026 over four hours, that is about $2.80 a day
        (thirty agent boxes $0.89, the House's own $0.41, the rest creation fees) against a $7.14
        allowance -- more than the 15% kept here. Deliberately so: over-granting early spends the
        budget front-loaded, which is where the learning is, and the allowance recomputed from what
        is really left pulls each later day down until the fortnight ends within a day of its
        budget. Sleeping boxes cost nothing, so the count of retired ones does not enter this."""
        if not self.running():
            return ZERO
        return max(self.allowance("sail") * share + self.allowance("openai") * frontier_share, floor).quantize(Decimal("0.01"))

    def report(self) -> dict[str, Any]:
        return {"day": self.day() + 1, "of": self.days, "running": self.running(),
                **{kind: {"budget_usd": format(self.budget[kind], "f"), "spent_usd": format(self.spent(kind).quantize(Decimal("0.0001")), "f"),
                          "today_usd": format(self._spend(kind)["today"].quantize(Decimal("0.0001")), "f"),
                          "allowance_today_usd": format(self.allowance(kind).quantize(Decimal("0.0001")), "f")} for kind in KINDS}}

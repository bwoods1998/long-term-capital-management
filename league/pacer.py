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

Sail is metered from the falls in its credit balance (`league/budget.py`); the frontier model from
the cost the gateway reports on each call, which the ledger records on `merton.pass`,
`audit.verdict` and `agent.research` rows -- every kind of frontier call the floor makes.
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
            # Every frontier dollar: Merton's own passes and the consultations agents buy from him
            # (`merton.pass`), the auditor's verdicts, and — by far the largest of the three — the
            # agents' own research passes. Measured on the first evening, research had spent $2.16
            # against Merton's $1.05, and none of it was counted here: the budget the owner funded
            # would have been overrun in silence while this meter read a third of the truth.
            rows = ((e.at, e.payload.get("cost_usd")) for e in self.ledger.iter(kinds=("merton.pass", "audit.verdict", "agent.research")))
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
        """What may be spent today: what is left, over the days that are left, counting today.
        (What was already spent today is part of today's allowance, not taken from it twice.)"""
        if not self.running():
            return ZERO
        spend = self._spend(kind)
        left_this_morning = max(self.budget[kind] - (spend["total"] - spend["today"]), ZERO)
        return left_this_morning / Decimal(self.days_left())

    def room(self, kind: str) -> Decimal:
        """How much of today's allowance is still unspent. Zero when the budget or the run is over."""
        return max(self.allowance(kind) - self._spend(kind)["today"], ZERO)

    def may_spend(self, kind: str) -> bool:
        return self.room(kind) > 0 and self.remaining(kind) > 0

    def over(self, kind: str) -> bool:
        """True once this kind of spending has stopped for good."""
        return self.day() >= self.days or self.remaining(kind) <= 0

    # ---------------------------------------------------------------------- uses
    def credit_pool(self, *, share: Decimal = Decimal("0.85"), floor: Decimal = Decimal("0.50")) -> Decimal:
        """The day's pool of compute credits: most of the day's Sail allowance (the rest is the
        House's own box and the boxes' idle minutes, which no agent is charged for)."""
        if not self.running():
            return ZERO
        return max(self.allowance("sail") * share, floor).quantize(Decimal("0.01"))

    def report(self) -> dict[str, Any]:
        return {"day": self.day() + 1, "of": self.days, "running": self.running(),
                **{kind: {"budget_usd": format(self.budget[kind], "f"), "spent_usd": format(self.spent(kind).quantize(Decimal("0.0001")), "f"),
                          "today_usd": format(self._spend(kind)["today"].quantize(Decimal("0.0001")), "f"),
                          "allowance_today_usd": format(self.allowance(kind).quantize(Decimal("0.0001")), "f")} for kind in KINDS}}

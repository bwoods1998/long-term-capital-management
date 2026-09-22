import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from league.budget import Budget
from league.ledger import Ledger, now_iso
from league.tests.fakes import Clock

D = Decimal


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.balance = D("97.80")
        self.budget = Budget(self.ledger, lambda: self.balance, clock=self.clock, every_seconds=900)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def step(self, balance):
        self.balance = D(balance)
        self.clock.advance(901)
        return self.budget.check()

    def test_spend_is_the_sum_of_falls_and_a_top_up_is_not_a_refund(self):
        self.assertEqual(self.budget.check(), "open")
        self.step("95.80")
        self.step("195.80")  # the owner topped up
        self.step("190.00")
        self.assertEqual(self.budget.month_spend(), D("7.80"))

    def test_it_stops_at_the_monthly_line_and_at_the_reserve(self):
        self.budget.check()
        self.assertEqual(self.step("50"), "open")
        self.balance = D("500")
        self.clock.advance(901)
        self.budget.check()
        self.assertEqual(self.step("447"), "stopped")  # 47.80 + 53 is over $100 this month
        other = Budget(self.ledger, lambda: D("9.99"), clock=self.clock)
        self.assertEqual(other.check(force=True), "stopped")

    def test_an_owner_top_up_raises_that_months_line(self):
        """Sept 21, 2026: the owner added $100 at Sail and recorded it with `campaign_topup.py`. That
        raised the campaign's ceiling and left this meter's $100 line where it was, so the floor
        would have stopped at $100 of September spend with his new credit unspent."""
        month = now_iso(self.clock)[:7]
        budget = Budget(self.ledger, lambda: self.balance, clock=self.clock, every_seconds=900,
                        topped_up=lambda m: D("100") if m == month else D("0"))
        self.assertEqual(budget.line(), D("200"))
        self.assertEqual(budget.line("1999-01"), D("100"))
        budget.check()  # 97.80
        for balance, mode in (("40", "open"), ("240", "open"), ("150", "open"), ("90", "stopped")):
            self.balance = D(balance)
            self.clock.advance(901)
            self.assertEqual(budget.check(), mode, balance)
        # 57.80 + 90 = 147.80 was over the constitution's $100 and under the $200 line; + 60 is over it.
        last = [e.payload for e in self.ledger.iter(kinds="ops.budget")][-1]
        self.assertEqual((last["month_usd"], last["cap_usd"]), ("207.80", "200"))

    def test_an_unreadable_top_up_record_raises_nothing(self):
        def broken(month):
            raise OSError("locked")

        self.assertEqual(Budget(self.ledger, lambda: self.balance, clock=self.clock, topped_up=broken).line(), D("100"))

    def test_it_reads_at_most_once_an_interval_and_survives_an_unreadable_balance(self):
        reads = []

        def read():
            reads.append(1)
            return D("90")

        budget = Budget(self.ledger, read, clock=self.clock, every_seconds=900)
        budget.check()
        budget.check()
        self.assertEqual(len(reads), 1)

        def broken():
            raise OSError("down")

        self.assertEqual(Budget(self.ledger, broken, clock=self.clock).check(force=True), "open")

    def test_a_new_month_starts_from_zero(self):
        self.budget.check()
        self.step("40")
        self.assertEqual(self.budget.month_spend(), D("57.80"))
        self.clock.advance(40 * 86400)
        self.assertEqual(self.budget.month_spend(), D("0"))


if __name__ == "__main__":
    unittest.main()

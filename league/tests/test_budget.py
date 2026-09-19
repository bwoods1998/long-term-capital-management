import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from league.budget import Budget
from league.ledger import Ledger
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

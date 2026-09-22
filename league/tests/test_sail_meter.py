"""The Sail meter reads the account balance, not a rolling usage window (Sept 22, 2026).

At 16:47:39Z the usage summary's `range=period` figure -- a rolling seven-day window on this plan
(`effective_range: "7d"`, `plan_limited: true`) -- fell as the first run's Sept 15 spend aged out.
The meter took the fall for a vendor reset, latched failed, and the whole floor stopped."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from league.campaigns import CampaignBudget, CampaignClosed
from league.funded import FundedTransport
from league.tests.test_phase1 import policy


class FakeVendor:
    def __init__(self, rows):
        self.rows = list(rows)

    def __call__(self, method, route, body=None, idempotency_key=None):
        assert (method, route) == ("GET", "/v2/usage/summary?range=period")
        return self.rows.pop(0)


class Meter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = [1800000000.0]
        rules = policy()
        rules["meter_required"] = ["sail"]
        self.guard = CampaignBudget(Path(self.tmp.name) / "campaigns.sqlite", rules, clock=lambda: self.now[0])
        self.addCleanup(self.guard.close)

    def test_balance_decreases_are_spend_and_a_top_up_is_never_credited_back(self):
        g = self.guard
        self.assertFalse(g.ready("sail"))
        self.assertEqual(g.observe_balance("sail", "100.00"), 0)  # the first reading starts the meter
        self.assertTrue(g.ready("sail"))
        self.assertEqual(g.remaining("sail"), 5)
        self.assertEqual(g.observe_balance("sail", "98.50"), Decimal("1.5"))
        self.assertEqual(g.remaining("sail"), Decimal("3.5"))
        self.assertEqual(g.observe_balance("sail", "198.50"), 0)  # the owner topped up: not negative spend
        self.assertEqual(g.remaining("sail"), Decimal("3.5"))
        g.observe_balance("sail", "198.00")
        self.assertEqual(g.remaining("sail"), Decimal("3"))
        self.now[0] += 181
        self.assertFalse(g.ready("sail"), "a stale reading still stops paid work")

    def test_the_switch_from_the_rolling_window_clears_its_latch_once_and_keeps_what_was_measured(self):
        g = self.guard
        g.observe_spend("sail", "461.08")
        g.observe_spend("sail", "462.58")  # $1.50 measured by the old feed
        with self.assertRaises(CampaignClosed):
            g.observe_spend("sail", "407.51")  # the window rolled: latched, as on production
        self.assertFalse(g.ready("sail"))
        g.observe_balance("sail", "127.39", evidence={"effective_range": "7d", "plan_limited": True})
        self.assertTrue(g.ready("sail"))
        self.assertEqual(g.remaining("sail"), Decimal("3.5"), "nothing already measured is forgotten")
        g.observe_balance("sail", "127.00")
        self.assertEqual(g.remaining("sail"), Decimal("3.11"))
        rows = g.db.execute("SELECT kind, evidence FROM meter_reconciliations").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIn("rolling window", rows[0]["evidence"])
        self.assertIn('"plan_limited":true', rows[0]["evidence"])
        # Only the latch the balance feed replaced is cleared, and only once.
        with self.assertRaises(CampaignClosed):
            g.observe_spend("sail", "1")
        g.observe_balance("sail", "126.90")
        self.assertFalse(g.ready("sail"))
        self.assertEqual(len(g.db.execute("SELECT 1 FROM meter_reconciliations").fetchall()), 1)

    def test_refresh_follows_the_balance_while_the_rolling_window_falls(self):
        vendor = FakeVendor([
            {"available": True, "balance": 12800.0, "period_spend": 51260.0, "effective_range": "7d", "plan_limited": True},
            {"available": True, "balance": 12739.4, "period_spend": 40750.6, "effective_range": "7d", "plan_limited": True},
            {"available": True, "balance_unavailable": True, "period_spend": 40000.0},
            {"available": True, "balance": 12700.0, "period_spend": 39000.0},
        ])
        funded = FundedTransport(vendor, self.guard, clock=lambda: self.now[0])
        self.assertTrue(funded.refresh())
        self.now[0] += 61
        self.assertTrue(funded.refresh(), "the window fell $105 while the balance fell $0.61: spend, not a latch")
        self.assertEqual(self.guard.remaining("sail"), Decimal("4.394"))
        self.now[0] += 61
        self.assertFalse(funded.refresh(), "no balance: the meter is unread this time")
        self.now[0] += 61
        self.assertTrue(funded.refresh(), "and reads again when the vendor answers; nothing latched")
        self.assertEqual(self.guard.remaining("sail"), Decimal("4"))


if __name__ == "__main__":
    unittest.main()

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


class StaleHolds(unittest.TestCase):
    """Sept 23, 2026: 329 Sail holds ($60.59) pending since the burst began, none with a response,
    while the balance meter had already counted every real charge once: the campaign read $54.76
    left with $116 in the account. A hold older than the meter's lag is absorbed into the meter."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = [1800000000.0]
        rules = policy()
        rules["meter_required"] = ["sail"]
        rules["caps_usd"] = {**rules["caps_usd"]}
        self.guard = CampaignBudget(Path(self.tmp.name) / "campaigns.sqlite", rules, clock=lambda: self.now[0])
        self.addCleanup(self.guard.close)
        self.campaign = next(k for k, v in rules["campaigns"].items() if v["kind"] == "sail")

    def test_an_old_unconfirmed_hold_is_absorbed_into_a_meter_that_already_counts_its_charge(self):
        g = self.guard
        g.observe_balance("sail", "100.00")
        self.assertTrue(g.reserve("old", self.campaign, "2.00"))
        self.assertTrue(g.reserve("answered", self.campaign, "2.00"))
        g.link_response("resp-1", "answered", "pro_asap")          # a response exists: settled from it, not here
        g.observe_balance("sail", "99.00")                          # the vendor charged $1 in all
        before = g.remaining("sail")
        self.assertEqual(g.absorb_stale("sail", older_than_seconds=3600)["absorbed"], 0)  # too young
        self.now[0] += 3601
        g.observe_balance("sail", "99.00")
        out = g.absorb_stale("sail", older_than_seconds=3600, evidence={"why": "test"})
        self.assertEqual((out["absorbed"], out["usd"]), (1, "2"))
        self.assertEqual(g.remaining("sail") - before, Decimal("2"))      # the double count is gone...
        used = g.db.execute("SELECT COALESCE(SUM(cost),0) FROM commitments").fetchone()[0]
        self.assertEqual(used, 0)
        self.assertEqual(g.db.execute("SELECT COUNT(*) FROM cost_reconciliations").fetchone()[0], 1)
        self.assertEqual(g.db.execute("SELECT cost FROM commitments WHERE id='answered'").fetchone()[0], None)
        # ...and the $1 the vendor charged is still counted, by the meter.
        self.assertEqual(g.absorb_stale("sail", older_than_seconds=3600)["absorbed"], 0)  # idempotent

    def test_nothing_is_absorbed_while_the_meter_is_stale_or_behind_what_was_settled(self):
        g = self.guard
        g.observe_balance("sail", "100.00")
        self.assertTrue(g.reserve("old", self.campaign, "2.00"))
        self.assertTrue(g.reserve("settled", self.campaign, "3.00"))
        g.settle("settled", "2.50")                                  # settled more than the meter has seen
        self.now[0] += 3601
        g.observe_balance("sail", "99.00")
        self.assertEqual(g.absorb_stale("sail", older_than_seconds=3600)["absorbed"], 0)
        self.now[0] += 400                                            # no reading for over three minutes
        g.observe_balance("sail", "97.00")
        self.now[0] += 181
        self.assertEqual(g.absorb_stale("sail", older_than_seconds=3600)["why"], "the meter is not healthy")

    def test_a_provider_without_a_meter_cannot_absorb(self):
        with self.assertRaises(ValueError):
            self.guard.absorb_stale("openai", older_than_seconds=3600)


if __name__ == "__main__":
    unittest.main()

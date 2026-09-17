"""The spend policy is arithmetic: every mode boundary is a number the owner can read."""

from __future__ import annotations

import unittest
from decimal import Decimal

from ltcm.runway import DEFAULT_POLICY, MODES, assess


class RunwayTests(unittest.TestCase):
    def test_a_healthy_balance_is_open_and_the_cap_is_everything_above_the_reserve(self):
        r = assess("279.82", "0.40")
        self.assertEqual(r.mode, "open")
        self.assertEqual(r.spendable_usd, Decimal("269.82"))
        self.assertEqual(r.cap_usd, Decimal("269.82"))  # no daily cap: the credit is the cap
        self.assertEqual(r.burn_usd_per_day, Decimal("0.70"))  # models plus the box
        self.assertEqual(r.runway_days, Decimal("385.4"))
        self.assertFalse(r.live_only)

    def test_the_desk_fuse_is_a_share_of_the_credit_never_under_the_minimum(self):
        self.assertEqual(assess("279.82", "0").desk_fuse_usd, Decimal("67.45"))
        self.assertEqual(assess("30", "0").desk_fuse_usd, Decimal("10.00"))

    def test_a_short_runway_throttles_and_stretches_the_credit(self):
        r = assess("20", "5", {"throttle_days": "3"})  # legacy opt-in, never the owner default
        self.assertEqual(r.mode, "throttled")
        self.assertTrue(r.live_only)
        self.assertEqual(r.cap_usd, Decimal("2.00"))  # $10 over five days
        self.assertEqual(r.desk_fuse_usd, Decimal("2.00"))  # the fuse never exceeds the cap

    def test_runway_never_throttles_the_default_owner_policy(self):
        for balance in ("202.90", "20", "10.01"):
            for burn in ("64.85", "10000"):
                with self.subTest(balance=balance, burn=burn):
                    r = assess(balance, burn)
                    self.assertEqual(r.mode, "open")
                    self.assertFalse(r.live_only)
                    self.assertEqual(r.cap_usd, Decimal(balance) - Decimal("10"))

    def test_at_the_reserve_the_floor_stops(self):
        for balance in ("10", "9.99", "0", "-3"):
            with self.subTest(balance=balance):
                r = assess(balance, "1")
                self.assertEqual(r.mode, "stopped")
                self.assertEqual(r.cap_usd, Decimal("0"))
                self.assertEqual(r.desk_fuse_usd, Decimal("0"))
                self.assertTrue(r.live_only)

    def test_an_unreadable_balance_keeps_the_floor_working_under_the_fallback(self):
        r = assess(None, "1")
        self.assertEqual(r.mode, "unknown")
        self.assertIsNone(r.balance_usd)
        self.assertIsNone(r.runway_days)
        self.assertEqual(r.cap_usd, Decimal(DEFAULT_POLICY["fallback_cap_usd"]))
        self.assertFalse(r.live_only)

    def test_burn_never_reads_as_zero_so_the_runway_is_always_finite(self):
        r = assess("100", "0", {"infra_usd_per_day": "0"})
        self.assertEqual(r.burn_usd_per_day, Decimal("0.50"))
        self.assertEqual(r.runway_days, Decimal("180.0"))

    def test_the_policy_can_be_tuned_from_config(self):
        r = assess("100", "10", {"reserve_usd": "50", "throttle_days": "10", "stretch_days": "2"})
        self.assertEqual(r.spendable_usd, Decimal("50"))
        self.assertEqual(r.mode, "throttled")
        self.assertEqual(r.cap_usd, Decimal("25.00"))

    def test_the_payload_is_strings_and_names_every_number_the_site_shows(self):
        payload = assess("279.82", "0.40").to_payload()
        self.assertEqual(payload["mode"], "open")
        self.assertEqual(payload["balance_usd"], "279.82")
        self.assertEqual(payload["runway_days"], "385.4")
        for value in payload.values():
            self.assertTrue(value is None or isinstance(value, str))
        self.assertIn(payload["mode"], MODES)


if __name__ == "__main__":
    unittest.main()

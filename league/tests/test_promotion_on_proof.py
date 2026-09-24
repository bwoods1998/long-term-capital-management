"""Promotion on proof (the close-the-gaps run, Sept 24, 2026; docs/goals/LTCM_CLOSE_THE_GAPS.md D4, P1-P3).

The evidence on record: the allocator's nine promotions to real money (08:28Z Sept 23 to 00:17Z Sept
24) all ran unproven mechanisms and settled -$18.62 on 16 settlements, 0 positive; four were demoted
after one loss; and meriwether-h7d7702 was promoted twice on strikes stacked on the same games. So:
settlements count once per EVENT (D4), a first real stake is a PROBE unless the agent's family has a
proven pooled record (P1), one early loss on a probe is not a demotion (P2), and the book's entry
rules read the constitution's keys (P3's keys; `league/book.py` implements them).
"""

import math
import unittest
from decimal import Decimal

from league.constitution import CONSTITUTION

D = Decimal


class MoneySet(unittest.TestCase):
    """Every key of Deploy A's money set carries a row of the plan's closed table, inside its bounds."""

    def setUp(self):
        self.r = CONSTITUTION["allocator"]

    def test_independent_settlements_are_counted_per_event(self):
        self.assertEqual(self.r["independent_settlements"], "event")

    def test_one_event_holds_at_most_a_quarter_of_a_real_stake(self):
        self.assertEqual(self.r["max_event_share"], "0.25")
        self.assertTrue(D("0.2") <= D(self.r["max_event_share"]) <= D("0.5"))

    def test_an_unproven_familys_first_real_stake_is_a_probe(self):
        probe, bunt = self.r["probe_bunt_usd"], self.r["bunt_usd"]
        self.assertEqual(probe, {"kalshi": "10", "alpaca": "25"})
        self.assertTrue(D("5") <= D(probe["kalshi"]) <= D("15"))
        self.assertTrue(D("20") <= D(probe["alpaca"]) <= D("25"))
        # A proven family's bunt is unchanged and never smaller than a probe.
        self.assertEqual(bunt, {"kalshi": "30", "alpaca": "25"})
        self.assertTrue(D("30") <= D(bunt["kalshi"]) <= D("60") and D("25") <= D(bunt["alpaca"]) <= D("60"))
        self.assertTrue(all(D(probe[v]) <= D(bunt[v]) for v in probe))
        # Alpaca takes no crypto order under $10, and the book refuses an order over half an account.
        self.assertGreaterEqual(D(probe["alpaca"]) / 2, D(self.r["venue_minimum_usd"]["alpaca"]))
        self.assertEqual(self.r["option_bunt_usd"], "80")  # one contract cannot be cut smaller

    def test_a_family_is_proven_by_its_pooled_record(self):
        rule = self.r["family_proven"]
        self.assertEqual(rule, {"min_independent_settlements": 10, "practice_weight": "0.5", "real_weight": "1",
                                "confidence": "0.8"})
        self.assertTrue(10 <= rule["min_independent_settlements"] <= 20)

    def test_the_one_loss_trial_and_the_event_position_share(self):
        self.assertEqual(self.r["hysteresis_after_settled"], 3)
        self.assertTrue(0 <= self.r["hysteresis_after_settled"] <= 5)
        self.assertEqual(self.r["position_share_event"], "0.2")
        self.assertTrue(D("0.15") <= D(self.r["position_share_event"]) <= D("0.5"))
        self.assertEqual(self.r["position_share"], 0.5)  # Alpaca keeps its half
        self.assertEqual(self.r["real_drawdown_demote"], 0.35)  # the stay drawdown always applies, unchanged

    def test_the_book_side_keys(self):
        self.assertEqual(self.r["longshot_floor_real"], "0.30")
        self.assertTrue(D("0.15") <= D(self.r["longshot_floor_real"]) <= D("0.35"))
        self.assertEqual(self.r["real_entry_liquidity"], "maker_unless_family_taker_positive")

    def test_the_lines_that_may_only_rise_did_not_fall(self):
        self.assertGreaterEqual(self.r["bunt_at"], 1.01)
        self.assertGreaterEqual(self.r["bunt_min_trades"], 5)
        self.assertGreaterEqual(self.r["bunt_min_settled"], 3)
        self.assertGreaterEqual(self.r["swing_min_real_trades"], 8)


if __name__ == "__main__":
    unittest.main()

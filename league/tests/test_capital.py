import unittest
from decimal import Decimal

from league.capital import kelly_stake, recommend, resize
from league.tests.test_house import BUYER, HouseCase

D = Decimal


class KellyStakeTest(unittest.TestCase):
    def test_no_record_or_no_edge_is_the_micro_stake(self):
        self.assertEqual(kelly_stake([], D(25), D(800))[0], D(25))
        self.assertEqual(kelly_stake([0.001] * 40, D(25), D(800))[0], D(25))  # no variance: nothing to bound
        losing = [(-0.004 if i % 2 else 0.002) for i in range(60)]
        stake, numbers = kelly_stake(losing, D(25), D(800))
        self.assertEqual(stake, D(25))
        self.assertIn("not above zero", numbers["reason"])

    def test_a_bounded_edge_is_sized_on_the_lower_bound_not_the_mean(self):
        growth = [(0.006 if i % 3 else -0.002) for i in range(90)]
        stake, numbers = kelly_stake(growth, D(25), D(100000))
        self.assertGreater(numbers["lcb"], 0)
        self.assertLess(numbers["lcb"], numbers["mean"])
        on_the_mean = D(25) * D(str(0.25 * numbers["mean"] / numbers["variance"]))
        self.assertLess(stake, on_the_mean)
        self.assertGreater(stake, D(25))

    def test_the_venue_share_is_a_ceiling(self):
        growth = [(0.006 if i % 3 else -0.002) for i in range(90)]
        stake, numbers = kelly_stake(growth, D(25), D(400))
        self.assertEqual(stake, D("100.00"))  # a quarter of the venue's cash, whatever Kelly says
        self.assertEqual(numbers["ceiling_usd"], "100.00")


class RecommendationTest(HouseCase):
    def test_with_nobody_above_paper_the_recommendation_is_to_add_nothing(self):
        self.seated()
        row = recommend(self.house, {"kalshi": D("522"), "alpaca": D("500")})
        self.assertTrue(row["summary"].startswith("Add nothing yet"))
        self.assertEqual(row["ranked"], [])
        self.assertEqual(self.house.ledger.last("ops.recommendation").payload["summary"], row["summary"])

    def test_resize_only_touches_rung_three_on_a_real_book(self):
        agent = self.seated()
        self.assertIsNone(resize(self.house, agent))


if __name__ == "__main__":
    unittest.main()

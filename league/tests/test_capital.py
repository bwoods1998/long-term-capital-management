import unittest
from decimal import Decimal

from league.book import GATEWAY_MARKET_MARKUP, Book
from league.capital import kelly_stake, recommend, resize, scaled_limits
from league.constitution import CONSTITUTION
from league.fees import Fees
from league.tests.fakes import FakeBroker
from league.tests.test_house import BUYER, HouseCase

D = Decimal


class KellyStakeTest(unittest.TestCase):
    def test_no_record_or_no_edge_is_the_micro_stake(self):
        # The floor is the constitution's micro stake: $60 since the learning surge of Sept 21, 2026.
        self.assertEqual(kelly_stake([], D(25), D(800))[0], D(60))
        self.assertEqual(kelly_stake([0.001] * 40, D(25), D(800))[0], D(60))  # no variance: nothing to bound
        losing = [(-0.004 if i % 2 else 0.002) for i in range(60)]
        stake, numbers = kelly_stake(losing, D(25), D(800))
        self.assertEqual(stake, D(60))
        self.assertIn("not above zero", numbers["reason"])

    def test_a_bounded_edge_is_sized_on_the_lower_bound_not_the_mean(self):
        growth = [(0.006 if i % 3 else -0.002) for i in range(90)]
        stake, numbers = kelly_stake(growth, D(25), D(100000))
        self.assertGreater(numbers["lcb"], 0)
        self.assertLess(numbers["lcb"], numbers["mean"])
        # The same fraction of Kelly (full since the owner's swing and bunt, Sept 23, 2026) on the MEAN
        # would be larger: the stake is sized on the lower bound.
        fraction = CONSTITUTION["rungs"]["3"]["kelly_fraction"]
        on_the_mean = D(25) * D(str(fraction * numbers["mean"] / numbers["variance"]))
        self.assertLess(stake, on_the_mean)
        self.assertGreater(stake, D(25))

    def test_the_venue_share_is_a_ceiling(self):
        growth = [(0.006 if i % 3 else -0.002) for i in range(90)]
        stake, numbers = kelly_stake(growth, D(25), D(400))
        share = D(str(CONSTITUTION["rungs"]["3"]["max_share_of_venue"]))  # 60% since swing and bunt (40% before)
        self.assertEqual(stake, (D(400) * share).quantize(D("0.01")))  # whatever Kelly says
        self.assertEqual(numbers["ceiling_usd"], str((D(400) * share).quantize(D("0.01"))))


class ScaledLimitsTest(unittest.TestCase):
    """Since the book slices exits (Sept 23, 2026) a position follows the stake; only an ORDER is capped."""

    def test_a_position_follows_the_stake_past_what_one_order_can_close(self):
        cap = Decimal(CONSTITUTION["order_caps"]["max_order_usd"])
        position, order = scaled_limits(Decimal("400"))
        self.assertEqual(position, Decimal("200"))  # half the stake: once $60 at most
        self.assertEqual(order, Decimal("60.00"))
        self.assertGreater(position, cap)

    def test_every_order_passes_the_gateway_on_its_own_pricing(self):
        """The gateway counts an Alpaca market order at the touch plus ten per cent: an order limit
        of $75 was $82.50 there, and every rung-3 market entry from $68.19 to $75 would have had a 403."""
        cap = Decimal(CONSTITUTION["order_caps"]["max_order_usd"])
        for staked in ("0", "20", "60", "100", "120", "136", "137", "150", "151", "400", "1000", "100000"):
            with self.subTest(staked=staked):
                position, order = scaled_limits(Decimal(staked))
                self.assertLessEqual(order, cap)
                self.assertLessEqual(order * GATEWAY_MARKET_MARKUP, cap)
                self.assertLess(order * GATEWAY_MARKET_MARKUP, cap * Decimal("0.9"))  # room for the touch to move
                self.assertLessEqual(order, position)

    def test_never_below_the_micro_rung(self):
        micro = CONSTITUTION["rungs"]["2"]
        position, order = scaled_limits(Decimal("10"))
        self.assertEqual(position, Decimal(micro["max_position_usd"]))
        self.assertEqual(order, min(Decimal(micro["max_order_usd"]), Decimal(CONSTITUTION["order_caps"]["max_order_usd"])))
        self.assertEqual(scaled_limits(Decimal("100")), (Decimal("50.00"), Decimal("50.00")))


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

    def test_shrinking_a_flat_real_account_does_not_immediately_fund_it_again(self):
        agent = self.seated()
        broker = FakeBroker("alpaca", cash="500")
        book = Book("alpaca", broker, self.house.ledger, fees=Fees("alpaca"), real_money=True, clock=self.clock)
        self.house.books["alpaca"] = book
        book.reconcile()
        self.house.evaluator.promote(agent.id, 2, "test micro admission")
        self.house.evaluator.promote(agent.id, 3, "test sizing an established real account")
        book.stake(agent.id, "100")
        self.house.seat(agent)
        row = resize(self.house, agent)  # no bounded return record: target the $60 micro stake
        self.assertEqual(D(row["moved_usd"]), D(-40))
        self.assertEqual(D(row["stake_usd"]), D(60))
        for _ in range(3):
            self.house.seat(agent)
        self.assertEqual(book.account(agent.id).cash, D(60))
        self.assertEqual(book.account(agent.id).staked, D(60))
        self.assertFalse(book.account(agent.id).swept)
        self.assertIsNone(resize(self.house, agent))
        self.assertEqual(len(list(self.house.ledger.iter(kinds="book.stake", agent=agent.id))), 2)
        self.assertEqual(broker.submitted, [])
        self.assertTrue(book.reconcile().ok)


if __name__ == "__main__":
    unittest.main()


class MicroTopUp(HouseCase):
    def test_a_live_micro_agent_seated_before_the_surge_is_raised_once_inside_the_headroom(self):
        from unittest.mock import patch
        from league.capital import top_up_micro
        agent = self.seated()
        book = Book("alpaca", FakeBroker("alpaca", cash="500"), self.house.ledger, fees=Fees("alpaca"), real_money=True, clock=self.clock)
        self.house.books["alpaca"] = book
        book.reconcile()
        self.house.evaluator.promote(agent.id, 2, "test: real money")
        book.stake(agent.id, D(25), note="a pre-surge stake")
        with patch.object(self.house, "tuition", return_value={"headroom_usd": D(500)}):
            row = top_up_micro(self.house, agent)
            self.assertEqual(D(row["moved_usd"]), D(35))
            self.assertEqual(book.account(agent.id).staked, D(60))
            self.assertIsNone(top_up_micro(self.house, agent))  # once
        other = self.seated("other")
        self.house.evaluator.promote(other.id, 2, "test: real money")
        book.stake(other.id, D(25), note="a pre-surge stake")
        with patch.object(self.house, "tuition", return_value={"headroom_usd": D(10)}):
            self.assertIsNone(top_up_micro(self.house, other))  # not inside the owner's headroom

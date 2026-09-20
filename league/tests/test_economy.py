import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from league.economy import Economy, Standing, check_bounds, load_game
from league.ledger import Ledger
from league.tests.fakes import Clock

D = Decimal


class EconomyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.economy = Economy(self.ledger, clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def test_grants_charges_and_death(self):
        self.economy.grant("a1", "1.00", "endowment")
        self.economy.charge("a1", "0.30", "inference")
        self.assertEqual(self.economy.balance("a1"), D("0.70"))
        self.assertTrue(self.economy.alive("a1"))
        self.economy.charge("a1", "0.70000001", "sandbox")
        self.assertFalse(self.economy.alive("a1"))

    def test_a_charge_rounds_up_and_a_grant_rounds_down(self):
        self.economy.grant("a1", "1.000000019", "x")
        self.economy.charge("a1", "0.000000011", "y")
        self.assertEqual(self.economy.balance("a1"), D("1.00000001") - D("0.00000002"))

    def test_idempotent_ids_do_not_pay_twice(self):
        self.economy.grant("a1", "1", "endowment", id="endow:a1")
        self.economy.grant("a1", "1", "endowment", id="endow:a1")
        self.economy.charge("a1", "0.25", "inference", id="req-1")
        self.economy.charge("a1", "0.25", "inference", id="req-1")
        self.assertEqual(self.economy.balance("a1"), D("0.75"))

    def test_a_restart_folds_the_same_balances(self):
        self.economy.grant("a1", "2", "endowment")
        self.economy.grant("a2", "1", "endowment")
        self.economy.transfer("a1", "a2", "0.5", "fork endowment")
        self.economy.charge("a2", "0.1", "inference")
        again = Economy(self.ledger, clock=self.clock)
        self.assertEqual(again.balance("a1"), D("1.5"))
        self.assertEqual(again.balance("a2"), D("1.4"))

    def test_a_transfer_cannot_kill_the_giver(self):
        self.economy.grant("a1", "1", "endowment")
        with self.assertRaises(ValueError):
            self.economy.transfer("a1", "a2", "1", "fork")

    def test_fork_threshold(self):
        threshold = D(self.economy.rules["fork_threshold_usd"])
        self.economy.grant("a1", threshold - D("0.01"), "x")
        self.assertFalse(self.economy.can_fork("a1"))
        self.economy.grant("a1", "0.01", "x")
        self.assertTrue(self.economy.can_fork("a1"))

    def test_niche_floors_keep_a_losing_niche_alive_and_winners_earn_more(self):
        standings = [
            Standing("k1", "kalshi/hour/favorites", 2, 0.002, 36),
            Standing("k2", "kalshi/hour/favorites", 1, 0.002, 36),
            Standing("a1", "alpaca/hour/reversion", 1, -0.001, 40),
            Standing("r0", "alpaca/day/trend", 0, 0.01, 100),
        ]
        shares = self.economy.shares(standings, "2.00")
        self.assertLessEqual(sum(shares.values()), D("2.00"))
        self.assertGreater(sum(shares.values()), D("1.9999"))
        # Two qualified niches share the 25% floor; an agent still in replay earns nothing at all.
        floor = D("0.50") / 2
        self.assertAlmostEqual(float(shares["a1"]), float(floor), places=6)   # its whole niche's floor
        self.assertEqual(shares["r0"], D("0"))
        # The same record, but real money weighs seven and a half times paper (1.5 against 0.2),
        # and three quarters of the pool is won rather than shared.
        self.assertAlmostEqual(float(shares["k1"] - floor / 2), float(D("1.50") * D("1.5") / D("1.7")), places=6)
        self.assertAlmostEqual(float(shares["k2"] - floor / 2), float(D("1.50") * D("0.2") / D("1.7")), places=6)

    def test_twice_as_profitable_earns_four_times_the_share(self):
        """Ultra-aggressive on purpose: credits buy research and Merton's time, so the curve that
        shares them is the curve that decides who gets the firm's intelligence."""
        standings = [Standing("fast", "n1", 1, 0.004, 25), Standing("slow", "n2", 1, 0.002, 25)]
        shares = self.economy.shares(standings, "2.00")
        floor = D("0.50") / 2
        self.assertAlmostEqual(float((shares["fast"] - floor) / (shares["slow"] - floor)), 4.0, places=6)

    def test_nobody_performed_means_the_performance_share_is_not_spent(self):
        game = load_game()
        game["economy"]["unearned_share_to_floors"] = False  # the design before the expedition
        economy = Economy(self.ledger, game, clock=self.clock)
        standings = [Standing("a1", "n1", 1, -0.01, 30), Standing("a2", "n2", 1, 0.0, 0)]
        self.assertEqual(sum(economy.shares(standings, "2.00").values()), D("0.50"))  # the floors, and nothing else

    def test_before_anybody_is_profitable_the_performance_share_goes_to_the_least_bad_trader(self):
        """It used to be split evenly, which paid an agent that had never placed an order exactly
        what it paid the best trader on the floor -- and credits are how frontier intelligence is
        bought. Ranked by how far above the WORST an agent is, among those that have traded."""
        self.assertTrue(self.economy.rules["unearned_share_to_floors"])  # the owner wants the budget used
        standings = [Standing("a1", "n1", 1, -0.01, 30), Standing("a2", "n1", 1, 0.0, 0), Standing("b1", "n2", 1, 0.0, 5), Standing("r0", "n3", 0, 0.0, 0)]
        shares = self.economy.shares(standings, "2.00")
        self.assertEqual(sum(shares.values()), D("2.00"))
        self.assertEqual(shares["b1"], D("0.25") + D("1.50"))  # its floor, and the whole performance share
        self.assertEqual((shares["a1"], shares["a2"]), (D("0.125"), D("0.125")))  # the worst, and one that never traded: floors only
        self.assertEqual(shares["r0"], D("0"))  # still in replay: nothing

    def test_with_nothing_at_all_to_rank_the_share_still_follows_the_floors(self):
        """The first hours of a league: not one agent has an active block. The owner wants the
        budget used, so it goes to the floors until somebody trades and there is a ranking."""
        standings = [Standing("a1", "n1", 1, 0.0, 0), Standing("b1", "n2", 1, 0.0, 0)]
        shares = self.economy.shares(standings, "2.00")
        self.assertEqual((shares["a1"], shares["b1"]), (D("1.00"), D("1.00")))

    def test_the_day_somebody_performs_the_performance_share_is_theirs_again(self):
        standings = [Standing("a1", "n1", 1, 0.002, 30), Standing("b1", "n2", 1, 0.0, 5)]
        shares = self.economy.shares(standings, "2.00")
        self.assertEqual((shares["a1"], shares["b1"]), (D("0.25") + D("1.50"), D("0.25")))

    def test_payout_is_due_once_an_epoch_and_is_recorded(self):
        standings = [Standing("a1", "n1", 1, 0.001, 30)]
        self.assertTrue(self.economy.payout_due())
        self.economy.payout(standings)
        self.assertEqual(self.economy.balance("a1"), D("2.00"))
        self.assertFalse(self.economy.payout_due())
        self.clock.advance(86400 / 2)
        self.assertFalse(self.economy.payout_due())
        self.clock.advance(86400 / 2)
        self.assertTrue(self.economy.payout_due())
        self.clock.advance(86400 * 9)  # ten epochs of downtime pay two, not ten
        self.economy.payout(standings)
        self.assertEqual(self.economy.balance("a1"), D("6.00"))

    def test_box_cost(self):
        self.assertEqual(self.economy.box_cost(90), D("0.001"))
        self.assertEqual(self.economy.box_cost(0, created=True), D("0.005"))

    def test_the_game_designer_cannot_leave_the_bounds(self):
        game = load_game()
        game["economy"]["daily_pool_usd"] = "50"
        with self.assertRaises(ValueError):
            check_bounds(game)


if __name__ == "__main__":
    unittest.main()

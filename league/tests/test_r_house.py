"""Adversarial review of the House's structure hooks and seats (r/house, Sept 25, 2026).

Each test states what the code SHOULD do; a failure is the demonstration of a finding."""

import unittest
from decimal import Decimal as D
from unittest import mock

from league import options_desk
from league.tests.test_options import STRUCTURE_AGENT, StructureHouseCase, THURSDAY_11_NY, condor_row, fake_chain
from league.tests.test_options_desk import SeatCase


class ContextAtAZeroMark(StructureHouseCase):
    def held_condor(self, agent, *, bid="0.55", ask="0.62"):
        from league import structures

        book = self.house.book_of(agent)
        self.house.seat(agent)
        inst = structures.instrument(structures.parse("options-shadow", condor_row()).spec, "options-shadow")
        self.shadow.set_quote(inst, bid, ask)
        intent = self.house._intents(agent, book, [condor_row()])[0][0]
        self.assertEqual(book.submit([intent])[0].status, "filled")
        return book, inst

    def test_a_structure_marked_at_zero_shows_its_loss_not_its_cost(self):
        agent = self.house.spawn("krasker", "options-structures-test", STRUCTURE_AGENT, reason="test", specialty="alpaca-options")
        book, inst = self.held_condor(agent)
        self.shadow.set_quote(inst, "0.00", "0.95")  # the legs are quoted and the bid comes to nothing: the book marks 0
        book.mark()
        self.assertEqual(book.marks[inst.key], D("0"))
        self.assertLess(book.equity(agent.id), book.account(agent.id).staked)  # the book says it lost
        row = self.house.snapshot(agent, book)["positions"][0]
        # The strategy must see the same: mark 0, P&L -(average cost x 100), natural mark = K (the whole wing to buy back).
        self.assertEqual(row["mark"], 0.0, row)
        self.assertLess(row["pnl_usd"], -60.0, row)


class ChainCost(StructureHouseCase):
    def test_requests_a_wake_makes_for_a_ten_day_six_underlying_structure_agent(self):
        asked = []
        chain = fake_chain(asked)
        for book in self.house.books.values():
            book.broker.option_chain = chain
        needs = STRUCTURE_AGENT.replace('"symbols": ["SPY"]', '"symbols": ["IWM", "F", "SOFI", "INTC", "PFE", "T"]') \
                               .replace('"max_days_to_expiry": 7', '"max_days_to_expiry": 10')
        agent = self.house.spawn("krasker", "options-structures-test", needs, reason="test", specialty="alpaca-options")
        self.house.seat(agent)
        self.house.snapshot(agent, self.house.book_of(agent))
        # One wake, cold cache: one request an underlying an expiry DATE (weekdays), empty dates included.
        print(f"\n[r/house] option_chain requests for one cold wake: {len(asked)} ({sorted(set(a[0] for a in asked))})")
        self.assertLessEqual(len(asked), 12, asked)


class RetireAfterBirth(SeatCase):
    def test_a_retirement_that_fails_leaves_no_founder_over_the_ceiling(self):
        self.options_resident(-0.10)
        self.grown_up()
        self.full()
        ceiling = self.house.game["economy"]["max_population"]
        with mock.patch.object(self.house, "kill", side_effect=RuntimeError("a venue error in the wind-down")):
            options_desk.seat_founders(self.house)
        self.assertLessEqual(len(self.house.registry.living()), ceiling)


if __name__ == "__main__":
    unittest.main()


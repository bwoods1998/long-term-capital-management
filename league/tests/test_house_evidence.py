"""Settlements remain evidence after an agent dies or leaves a book."""

import math
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from ltcm.broker import RejectedOrder
from league.book import Intent
from league.economy import load_game
from league.house import House, Settings
from league.ledger import now_iso
from league.tests.fakes import Clock, FakeBroker
from league.tests.test_book import event
from league.tests.test_house import HouseCase
from league.tests.test_ladder import InProcessSandbox


CODE = '''
NEEDS = {"venue": "kalshi", "horizon": "hour", "style": "favorites", "series": ["KXBTCD"]}
PARAMS = {}
def decide(ctx):
    return {}
'''


class WindingDownEvidence(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.real = FakeBroker("kalshi", cash="1000", family="kalshi")
        self.paper = FakeBroker("kalshi-shadow", family="kalshi")
        self.instrument = event()
        self.real.set_quote(self.instrument, ".79", ".8")
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.house = House(
            Path(self.directory.name), brokers={"kalshi": self.real, "kalshi-shadow": self.paper},
            sandbox=InProcessSandbox(), settings=Settings(real_money=True, research=False, mark_every_seconds=0),
            game=game, clock=self.clock,
        )
        self.agent = self.house.spawn("terminal", "test", CODE)
        self.house.evaluator.seat(self.agent.id, 2, "test")
        self.house.seat(self.agent)
        self.house._state["tried"][self.agent.id] = self.agent.code_sha256
        self.house._state["next_wake"][self.agent.id] = self.clock() + 86400
        self.book = self.house.books["kalshi"]
        self.book.resolves_at = lambda instrument: self.clock() + 3600
        intent = Intent.new(agent=self.agent.id, instrument=self.instrument, side="buy", quantity=Decimal(2),
                            reason="test", created_at=now_iso(self.clock))
        self.assertEqual(self.book.submit([intent])[0].status, "filled")
        self.book.mark()
        self.advance()
        self.book.mark()
        self.house.evaluator.observe(self.agent.id, "kalshi", "hour")

    def tearDown(self):
        self.house.close(wait=None)
        self.directory.cleanup()

    def advance(self):
        self.clock.advance(3600)
        self.real.clock_iso = self.paper.clock_iso = now_iso(self.clock)

    def settle_loss(self):
        self.advance()
        self.book.settle(self.instrument.market_id, "no")
        self.real.held.clear()  # the fake venue also resolved the losing contracts for no payout
        self.house.tick()

    def test_dead_agents_later_settlement_is_observed_and_sweep_is_not_a_loss(self):
        self.house.kill(self.agent, "credits", "test")
        self.assertEqual(len(self.book.account(self.agent.id).holdings), 1)
        self.settle_loss()
        for _ in range(2):
            self.advance()
            self.house.tick()
        rows = self.house.evaluator.blocks(self.agent.id, book="kalshi")
        pnl = float(self.house.ledger.last("book.settle", agent=self.agent.id).payload["pnl"])
        self.assertEqual(len(rows), 4)
        self.assertAlmostEqual(sum(r["log_growth"] for r in rows), math.log((25 + pnl) / 25), places=12)
        self.assertTrue(rows[2]["active"])
        self.assertLess(rows[2]["log_growth"], -0.06)
        self.assertEqual(rows[-1]["end_equity"], 0)
        self.assertAlmostEqual(rows[-1]["log_growth"], 0)
        pooled = self.house.evaluator.family_record([self.agent.id], "kalshi")
        self.assertEqual(pooled[0], [r["log_growth"] for r in rows])
        self.assertAlmostEqual(pooled[1][0], pnl / 25)

        # Once the terminal zero-equity block is finished, stop scanning the growing flat marks.
        with patch.object(self.house.evaluator, "observe", wraps=self.house.evaluator.observe) as observe:
            for _ in range(3):
                self.advance()
                self.house.tick()
            observe.assert_not_called()
        self.assertEqual(self.house.evaluator.blocks(self.agent.id, book="kalshi"), rows)

    def test_demoted_agents_old_book_is_observed_without_judging_it_as_paper(self):
        self.house.evaluator.demote(self.agent.id, "test")
        self.house._move_books(self.agent, self.book)
        self.assertEqual(self.house.book_of(self.agent).name, "kalshi-shadow")
        self.settle_loss()
        for _ in range(2):
            self.advance()
            self.house.tick()
        real_rows = self.house.evaluator.blocks(self.agent.id, book="kalshi")
        paper_rows = self.house.evaluator.blocks(self.agent.id, book="kalshi-shadow")
        self.assertLess(sum(r["log_growth"] for r in real_rows), -0.06)
        self.assertTrue(paper_rows)
        self.assertTrue(all(r["log_growth"] == 0 for r in paper_rows))
        self.assertTrue(self.agent.alive)
        self.assertEqual(self.house.evaluator.rung(self.agent.id), 1)
        self.assertEqual(self.house.standing_of(self.agent.id)["mean_growth"], 0)
        standing = next(row for row in self.house.standings() if row.agent == self.agent.id)
        self.assertEqual((standing.mean_growth, standing.active_blocks), (0, 0))


class RetiredExits(HouseCase):
    def test_dead_holding_is_retried_after_venue_recovers(self):
        agent = self.seated()
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        self.broker.raise_on_submit = RejectedOrder("temporary venue outage")
        self.house.kill(agent, "test")
        self.assertTrue(book.account(agent.id).holdings)
        self.broker.raise_on_submit = None
        self.clock.advance(301)
        self.broker.clock_iso = now_iso(self.clock)
        self.house.tick()
        self.assertFalse(book.account(agent.id).holdings)
        self.assertTrue(book.account(agent.id).swept)
        self.assertTrue(book.reconcile().ok)

    def test_pending_exit_is_neither_cancelled_nor_duplicated_on_retry(self):
        agent = self.seated()
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        self.broker.asynchronous = True
        # Hold the fake venue at accepted across several polls, then let it publish its fill.
        def pending_order(order_id):
            return next(order for order in self.broker.orders.values() if order_id in (order.id, order.broker_order_id))

        with patch.object(self.broker, "get_order", side_effect=pending_order):
            self.house.kill(agent, "test")
            self.assertTrue(book.open_orders(agent.id))
            for _ in range(2):
                self.clock.advance(301)
                self.broker.clock_iso = now_iso(self.clock)
                self.house.tick()
            self.assertEqual(len([order for order in self.broker.submitted if order.side == "sell"]), 1)
            self.assertFalse(self.broker.cancelled)
        self.clock.advance(301)
        self.broker.clock_iso = now_iso(self.clock)
        self.house.tick()
        self.assertFalse(book.account(agent.id).holdings)
        self.assertFalse(book.open_orders(agent.id))
        self.assertTrue(book.account(agent.id).swept)

"""The maintenance pause: nothing that spends or enters, everything that exits or reconciles."""
from decimal import Decimal

from league.tests.test_house import BUYER, HouseCase

D = Decimal


class Pause(HouseCase):
    def pause(self, reason="rebuilding"):
        (self.house.root / "PAUSE").write_text(reason, encoding="utf-8")

    def test_a_pause_lets_a_holder_sell_but_not_buy(self):
        agent = self.seated()
        self.house.tick()  # flat, so it buys
        book = self.house.books["alpaca-paper"]
        self.assertTrue(book.account(agent.id).holdings)
        self.pause()
        self.clock.advance(301)
        summary = self.house.tick()  # it holds, so it is woken and its sell goes through
        self.assertEqual(summary["paused"], "rebuilding")
        self.assertEqual(summary["woke"], [agent.id])
        self.assertEqual(book.account(agent.id).holdings, {})
        self.clock.advance(301)
        summary = self.house.tick()  # flat now: not woken at all, so no new entry
        self.assertEqual(summary["woke"], [])
        self.assertEqual(book.account(agent.id).holdings, {})

    def test_a_paused_buy_from_a_holder_is_refused_with_the_reason(self):
        code = BUYER.replace('if held:', 'if held and ctx["memory"].get("never"):')  # buys again while holding
        agent = self.seated(code=code)
        self.house.tick()
        self.pause()
        self.clock.advance(301)
        before = len(self.broker.submitted)
        self.house.tick()
        self.assertEqual(len(self.broker.submitted), before)
        refused = self.house.ledger.last("book.refused", agent=agent.id).payload
        self.assertIn("paused for maintenance", refused["reasons"][0])

    def test_no_research_births_or_clock_culls_while_paused(self):
        agent = self.house.spawn("idle", "test-family", BUYER, reason="test")  # rung 0, never replayed
        self.house.economy.grant(agent.id, "5", "rich enough to research")
        self.pause()
        self.assertFalse(self.house.research_due(agent))
        self.assertEqual(self.house._research_permission(agent), "maintenance pause")
        self.clock.advance(3 * 86400 + 60)
        summary = self.house.tick()
        self.house.wait()
        self.assertTrue(self.house.registry.get(agent.id).alive)  # the replay deadline waits too
        self.assertEqual(summary["budget"], "stopped")
        self.assertNotIn(agent.id, self.house._state["tried"])  # no replay started
        (self.house.root / "PAUSE").unlink()
        self.assertIsNone(self.house.paused())

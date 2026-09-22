"""A market that has not opened cannot supply an agent's fair trading opportunity."""
from league.tests.test_house import BUYER, HouseCase


class SelectionOpportunity(HouseCase):
    def test_paper_equity_grace_starts_with_its_first_tradable_wake(self):
        agent = self.seated("stocks", BUYER.replace('"BTC/USD"', '"SPY"'))
        rules = self.house.game["economy"]
        grace = float(rules["epoch_seconds"]) * float(rules["displace_after_epochs"])
        self.clock.advance(3 * 86400)
        self.house.ledger.append("agent.woke", {"ok": True, "offered": 0, "shut": 30}, agent=agent.id)
        self.assertIsNone(self.house._weakest(rules))
        self.house.ledger.append("agent.woke", {"ok": True, "offered": 1}, agent=agent.id)
        self.assertIsNone(self.house._weakest(rules))
        self.clock.advance(grace + 1)
        self.assertEqual(self.house._weakest(rules).id, agent.id)

    def test_crypto_tournament_keeps_its_existing_grace(self):
        agent = self.seated()
        rules = self.house.game["economy"]
        self.clock.advance(float(rules["epoch_seconds"]) * float(rules["displace_after_epochs"]) + 1)
        self.assertEqual(self.house._weakest(rules).id, agent.id)

    def test_late_replay_pass_gets_a_forward_opportunity(self):
        agent = self.house.spawn("late", "test-family", BUYER)
        rules = self.house.game["economy"]
        grace = float(rules["epoch_seconds"]) * float(rules["displace_after_epochs"])
        self.clock.advance(grace + 1)
        self.assertEqual(self.house._weakest(rules).id, agent.id)
        self.house.evaluator.promote(agent.id, 1, "passed replay", {})
        self.assertIsNone(self.house._weakest(rules))
        self.clock.advance(grace + 1)
        self.assertEqual(self.house._weakest(rules).id, agent.id)

    def test_replacement_strategy_gets_grace_but_duplicate_rows_do_not_extend_it(self):
        agent = self.seated()
        rules = self.house.game["economy"]
        grace = float(rules["epoch_seconds"]) * float(rules["displace_after_epochs"])
        self.clock.advance(grace + 1)
        self.house.registry.adopt(agent.id, code=BUYER + "\n# new program\n", needs=agent.needs,
                                  params=agent.params, reason="empty-record replacement")
        self.assertIsNone(self.house._weakest(rules))
        self.clock.advance(grace + 1)
        self.house.registry.adopt(agent.id, code=agent.code, needs=agent.needs,
                                  params=agent.params, reason="duplicate receipt")
        self.assertEqual(self.house._weakest(rules).id, agent.id)

    def test_old_equity_opportunity_does_not_age_a_replacement_strategy(self):
        agent = self.seated("stocks", BUYER.replace('"BTC/USD"', '"SPY"'))
        rules = self.house.game["economy"]
        grace = float(rules["epoch_seconds"]) * float(rules["displace_after_epochs"])
        self.house.ledger.append("agent.woke", {"ok": True, "offered": 1}, agent=agent.id)
        self.clock.advance(grace + 1)
        self.house.registry.adopt(agent.id, code=agent.code + "\n# new program\n", needs=agent.needs,
                                  params=agent.params, reason="empty-record replacement")
        self.clock.advance(grace + 1)
        self.assertIsNone(self.house._weakest(rules))
        self.house.ledger.append("agent.woke", {"ok": True, "offered": 1}, agent=agent.id)
        self.assertIsNone(self.house._weakest(rules))
        self.clock.advance(grace + 1)
        self.assertEqual(self.house._weakest(rules).id, agent.id)



class DailyScreenGrace(HouseCase):
    """A trading daily agent is not displaced before its paper screen could look (Sept 22, 2026)."""

    def setUp(self):
        super().setUp()
        self.rules = self.house.game["economy"]
        self.grace = float(self.rules["epoch_seconds"]) * float(self.rules["displace_after_epochs"])

    def daily(self, name):
        """A seated agent the House sees as a daily one (no test desk takes a daily BTC buyer)."""
        from dataclasses import replace
        agent = self.seated(name)
        real = self.house.registry.get
        self.house.registry.get = lambda agent_id: (lambda found: replace(found, horizon="day") if found.id == agent.id else found)(real(agent_id))
        return agent

    def fill(self, agent):
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "symbol": "BTC/USD", "side": "buy",
                                               "quantity": "0.001", "price": "60000"}, agent=agent.id)

    def closed_day(self, agent, key):
        self.house.ledger.append("eval.block", {"book": "alpaca-paper", "key": key, "horizon": "day", "start_equity": 100.0,
                                                "end_equity": 99.0, "flow": 0.0, "log_growth": -0.01, "active": True},
                                 agent=agent.id)

    def test_a_trading_daily_agent_keeps_its_seat_until_two_days_have_closed(self):
        agent = self.daily("weather")
        self.fill(agent)
        self.clock.advance(self.grace + 1)
        self.assertIsNone(self.house._weakest(self.rules))
        self.closed_day(agent, "2026-09-21")
        self.assertIsNone(self.house._weakest(self.rules))
        self.closed_day(agent, "2026-09-22")
        self.assertEqual(self.house._weakest(self.rules).id, agent.id)

    def test_a_daily_agent_that_never_traded_keeps_the_plain_grace(self):
        agent = self.daily("idle")
        self.clock.advance(self.grace + 1)
        self.assertEqual(self.house._weakest(self.rules).id, agent.id)

    def test_the_protection_ends_a_day_after_the_screen_could_have_looked(self):
        agent = self.daily("stuck")
        self.fill(agent)
        self.clock.advance(3 * 86400 - 60)
        self.assertIsNone(self.house._weakest(self.rules))
        self.clock.advance(61)
        self.assertEqual(self.house._weakest(self.rules).id, agent.id)

    def test_an_hourly_agent_keeps_the_plain_grace(self):
        agent = self.seated()
        self.fill(agent)
        self.clock.advance(self.grace + 1)
        self.assertEqual(self.house._weakest(self.rules).id, agent.id)

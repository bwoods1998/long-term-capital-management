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

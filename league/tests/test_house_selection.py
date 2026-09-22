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



class ReplayRulesChange(HouseCase):
    """When the owner changes the replay rules, rung-0 agents get one fresh replay (Sept 22, 2026)."""

    def test_rung_zero_agents_get_one_fresh_replay_when_the_rules_change(self):
        young = self.house.spawn("young", "test-family", BUYER, reason="a test agent")
        seated = self.seated("seated")
        self.house._state["tried"][young.id] = young.code_sha256
        self.house._state["replay_rules"] = "an-older-gate"
        self.house._replay_rules_changed()
        self.assertNotIn(young.id, self.house._state["tried"])
        self.assertEqual(self.house._state["tried"][seated.id], seated.code_sha256)
        self.house._state["tried"][young.id] = young.code_sha256
        self.house._replay_rules_changed()
        self.assertEqual(self.house._state["tried"][young.id], young.code_sha256)

    def test_a_new_house_has_no_old_verdict_to_revisit(self):
        from league.house import _replay_rules_key
        self.assertEqual(self.house._state["replay_rules"], _replay_rules_key())

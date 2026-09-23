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

    def test_a_trading_daily_agent_keeps_its_seat_until_the_screens_days_have_closed(self):
        from league.constitution import CONSTITUTION
        days = int(CONSTITUTION["ladder"]["paper"]["min_active_blocks_day"])  # 1 since swing and bunt (2 before)
        agent = self.daily("weather")
        self.fill(agent)
        self.clock.advance(self.grace + 1)
        for n in range(days):
            self.assertIsNone(self.house._weakest(self.rules))
            self.closed_day(agent, f"2026-09-{21 + n}")
        self.assertEqual(self.house._weakest(self.rules).id, agent.id)

    def test_a_daily_agent_that_never_traded_keeps_the_plain_grace(self):
        agent = self.daily("idle")
        self.clock.advance(self.grace + 1)
        self.assertEqual(self.house._weakest(self.rules).id, agent.id)

    def test_the_protection_ends_a_day_after_the_screen_could_have_looked(self):
        from league.constitution import CONSTITUTION
        days = int(CONSTITUTION["ladder"]["paper"]["min_active_blocks_day"])
        agent = self.daily("stuck")
        self.fill(agent)
        self.clock.advance((days + 1) * 86400 - 60)
        self.assertIsNone(self.house._weakest(self.rules))
        self.clock.advance(61)
        self.assertEqual(self.house._weakest(self.rules).id, agent.id)

    def test_an_hourly_agent_keeps_the_plain_grace(self):
        agent = self.seated()
        self.fill(agent)
        self.clock.advance(self.grace + 1)
        self.assertEqual(self.house._weakest(self.rules).id, agent.id)


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

    def near_miss(self, name, *, oos=-0.0003, reasons=("out-of-sample growth is not above zero",), cause="never qualified"):
        agent = self.house.spawn(name, "test-family", BUYER, reason="a test agent")
        self.house.ledger.append("eval.trial", {"family": "test-family", "passed": False, "reasons": list(reasons),
                                                "oos_mean_log_growth": oos, "code_sha256": agent.code_sha256}, agent=agent.id)
        self.house.kill(agent, cause, "a test death")
        return agent

    def revive(self):
        self.house._state["replay_rules"] = "an-older-gate"
        self.house._replay_rules_changed()
        return [a for a in self.house.registry.living() if a.parent]

    def test_a_near_miss_that_died_on_rung_zero_is_born_again_once_under_a_looser_floor(self):
        """Swing and bunt, Sept 23, 2026: code that failed replay only by out-of-sample growth the new
        floor admits gets one new life on its line, and today's tape decides."""
        from league.constitution import CONSTITUTION
        self.assertLess(CONSTITUTION["ladder"]["replay"]["min_oos_growth"], -0.0003)
        dead = self.near_miss("haghani")
        born = self.revive()
        self.assertEqual([(a.parent, a.code, a.params) for a in born], [(dead.id, dead.code, dead.params)])
        self.assertEqual(self.house.evaluator.rung(born[0].id), 0)
        self.assertIn("revived under the loosened replay gate", self.house.ledger.last("agent.born").payload.get("reason", ""))
        self.house._replay_rules_changed()  # the same rules again: nobody new
        self.assertEqual(len([a for a in self.house.registry.living() if a.parent]), 1)

    def test_a_lines_mutations_are_distinct_strategies_and_a_twin_comes_back_once(self):
        first, second = self.near_miss("haghani"), self.near_miss("haghani")
        self.house.registry.agents[second.id].params = {"notional": 25.0}
        twin = self.near_miss("haghani")
        self.assertEqual(twin.params, first.params)
        self.assertEqual(sorted(a.parent for a in self.revive()), sorted([twin.id, second.id]))

    def test_only_a_pure_out_of_sample_near_miss_of_a_fair_death_comes_back(self):
        self.near_miss("flat", oos=0.0)                       # sat the out-of-sample stretch out
        self.near_miss("deep", oos=-0.0009)                   # below the floor
        self.near_miss("thin", reasons=("out-of-sample growth is not above zero", "8 closed trades, 10 needed"))
        self.near_miss("replaced", cause="superseded")        # its code was corrected
        self.assertEqual(self.revive(), [])

    def test_code_a_merged_repair_corrects_is_not_brought_back(self):
        from unittest.mock import patch
        self.near_miss("haghani")
        with patch.object(type(self.house), "_known_defect", return_value="the merged repair haghani_fix corrects its code"):
            self.assertEqual(self.revive(), [])

    def test_a_line_whose_holdout_is_spent_forks_no_child_that_could_only_die(self):
        """A plain mutation shares its parent's lineage; once the lineage's sealed holdout is spent,
        its child passes no replay (it dies `redundant`), so the parent does not fork one."""
        agent = self.seated("crypto")
        self.house.settings.deep_replay = True
        self.assertFalse(self.house._holdout_spent(agent))
        root = self.house.registry.lineage(agent.id)[-1]
        for n in range(self.house.settings.holdout_lineage_budget):
            self.house.ledger.append("holdout.access", {"agent": agent.id, "lineage": root, "version": f"v{n}", "state": "opened"}, agent=agent.id)
        self.assertTrue(self.house._holdout_spent(agent))
        forks = []
        self.house.fork = lambda parent: forks.append(parent.id)
        self.house.economy.can_fork = lambda _agent_id: True
        self.house.keep_population(refill=True, clock=False)
        self.assertEqual(forks, [])

    def test_a_new_house_has_no_old_verdict_to_revisit(self):
        from league.house import _replay_rules_key
        self.assertEqual(self.house._state["replay_rules"], _replay_rules_key())

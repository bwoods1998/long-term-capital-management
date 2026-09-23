"""The overnight v0 of Sept 22, 2026: research backs off empty passes; births skip exhausted lines."""
from types import SimpleNamespace

from league.tests.test_house import HouseCase


class ResearchBackoff(HouseCase):
    def setUp(self):
        super().setUp()
        self.house.settings.research = True
        self.house.researcher = SimpleNamespace()  # research_due only asks that one exists
        self.house.game["research"]["min_hours_between"] = 1
        self.house.game["research"]["gate"] = {"after": 2, "max_factor": 8, "sample_percent": 0}
        self.house.game["research"]["pace"] = {}  # the gate under test, not the record-based pace
        self.agent = self.seated()
        self.house.economy.grant(self.agent.id, "5", "rich enough to research")
        self.house.pacer.may_spend = lambda kind: True
        self.house._state["last_research"][self.agent.id] = self.clock()

    def empty(self, times):
        for _ in range(times):
            self.house._note_research_result(self.agent.id, SimpleNamespace(candidate=None, trials=0, consulted=""))

    def test_two_empty_passes_double_the_interval_and_a_useful_one_resets_it(self):
        self.empty(2)
        self.clock.advance(3600 + 1)
        self.assertFalse(self.house.research_due(self.agent))
        gate = self.house.ledger.last("research.gate", agent=self.agent.id).payload
        self.assertEqual((gate["decision"], gate["empty_streak"]), ("skip", 2))
        self.clock.advance(3600)
        self.assertTrue(self.house.research_due(self.agent))  # x2 elapsed
        self.house._note_research_result(self.agent.id, SimpleNamespace(candidate={"code": "x"}, trials=0, consulted=""))
        self.assertEqual(self.house._state["empty_research"][self.agent.id], 0)

    def test_new_evidence_since_the_last_pass_runs_research_at_the_usual_interval(self):
        self.empty(4)
        self.clock.advance(3600 + 1)
        self.assertFalse(self.house.research_due(self.agent))
        self.house.ledger.append("eval.verdict", {"decision": "progress"}, agent=self.agent.id)
        self.assertTrue(self.house.research_due(self.agent))

    def test_the_backoff_is_capped_and_a_sample_still_runs(self):
        self.empty(12)
        self.clock.advance(8 * 3600 + 1)
        self.assertTrue(self.house.research_due(self.agent))  # capped at x8
        self.house.game["research"]["gate"]["sample_percent"] = 100
        self.house._state["last_research"][self.agent.id] = self.clock()
        self.clock.advance(3600 + 1)
        self.assertTrue(self.house.research_due(self.agent))
        self.assertTrue(self.house.ledger.last("research.gate", agent=self.agent.id).payload["sampled"])

    def test_one_gate_row_per_window_not_per_tick(self):
        self.empty(3)
        self.clock.advance(3600 + 1)
        for _ in range(5):
            self.house.research_due(self.agent)
        self.assertEqual(self.house.ledger.count(kinds="research.gate", agent=self.agent.id), 1)


class ExhaustedLines(HouseCase):
    def test_a_line_with_fifteen_failed_trials_is_not_bred_and_is_retired_once(self):
        tired, fresh = self.seated("tired"), self.seated("fresh")
        for n in range(15):
            self.house.ledger.append("eval.trial", {"family": "test-family", "passed": False, "sharpe": None, "n": n}, agent=tired.id)
        rules = self.house.game["economy"]
        rules.update(newcomer_seconds=600, max_population=10, min_population=0, explore_every=0)
        self.clock.advance(601)
        child = self.house._refill(rules)
        self.assertIsNotNone(child)
        self.assertEqual(child.parent, fresh.id)
        self.assertIn("passes in 0 trials", str(self.house.ledger.last("agent.born", agent=child.id).payload))
        retired = list(self.house.ledger.iter(kinds="hypothesis.retired"))
        self.assertEqual([r.payload["id"] for r in retired], [f"line:{tired.line or tired.name}"])
        self.clock.advance(601)
        self.house._refill(rules)
        self.assertEqual(self.house.ledger.count(kinds="hypothesis.retired"), 1)

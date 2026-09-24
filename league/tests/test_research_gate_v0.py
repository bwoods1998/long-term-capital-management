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

    def test_its_own_pause_is_not_new_evidence(self):
        """Review of #249: a pause row (X1) restates the strategy in force, not a new one."""
        self.empty(4)
        self.clock.advance(3600 + 1)
        self.assertFalse(self.house.research_due(self.agent))
        self.house.ledger.append("agent.research", {"tool": "control", "status": "requested", "control": "pause_entries",
                                                    "session": "s1", "note": "the live rule keeps adding losing positions"},
                                 agent=self.agent.id, id="control-request:s1:0")
        self.assertEqual(self.house._apply_controls(self.agent.id, "s1"), ["pause_entries"])
        self.assertFalse(self.house.research_due(self.agent))

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


class TheBudgetIsAskedLast(HouseCase):
    """Sept 24, 2026 (R6-perf): `research_due` asked the campaign's budget first, of every living agent on
    every tick: 17.7 ms a call on a copy of the 17:27Z snapshot, about 2 s of a tick. It is asked after the
    checks that read and write nothing, so only of agents otherwise due; the answer is the old order's."""

    def setUp(self):
        super().setUp()
        self.house.settings.research = True
        self.house.researcher = SimpleNamespace()
        self.house.game["research"]["min_hours_between"] = 1
        self.house.game["research"]["gate"] = {"after": 2, "max_factor": 8, "sample_percent": 0}
        self.house.game["research"]["pace"] = {}

    def old_research_due(self, agent):
        """`research_due` as it was before R6-perf, check for check: the answer to match."""
        from decimal import Decimal

        from league.house import _epoch

        house = self.house
        if house._closing.is_set() or not agent.alive or house.researcher is None or not house.settings.research:
            return False
        if house.paused():
            return False
        kind = house._research_budget_kind(agent)
        if not house.pacer.may_spend(kind):
            return False
        if house.deploying():
            return False
        pending = house.research_jobs.active(agent.id)
        if pending:
            if pending.get("status") == "queued" and kind == "sail" and house._sail_research_capped():
                return False
            return house.clock() >= pending["available"]
        if kind == "sail" and house._sail_research_capped():
            return False
        rules = house.game.get("research") or {}
        if house.economy.balance(agent.id) <= Decimal(str(rules.get("min_credits_usd", "0.10"))) * 2:
            return False
        last = max(float(house._state["last_research"].get(agent.id) or 0), house.research_jobs.last_finished(agent.id))
        refusal = house.ledger.last('book.refused', agent=agent.id)
        book = house.book_of(agent)
        if (refusal is not None and book is not None and refusal.payload.get('book') == book.name
                and _epoch(refusal.at) > last and house.clock() - last >= 60):
            return True
        interval = house.research_interval_hours(agent) * 3600
        if house.clock() - last < interval:
            return False
        return house._gate(agent, last, interval)

    def test_the_old_order_s_answer_and_the_budget_asked_only_of_agents_otherwise_due(self):
        from unittest.mock import patch

        agents = {name: self.seated(name) for name in ("just", "due", "broke", "refused", "waiting", "resumes")}
        for agent in agents.values():
            self.house.economy.grant(agent.id, "5", "rich enough to research")
        self.house.economy.charge(agents["broke"].id, "5.95", "spent")
        now = self.clock()
        state = self.house._state["last_research"]
        state.update({agents["just"].id: now, agents["due"].id: now - 7200, agents["broke"].id: now - 7200,
                      agents["refused"].id: now - 120, agents["waiting"].id: now - 7200, agents["resumes"].id: now - 7200})
        self.house.ledger.append("book.refused", {"book": "alpaca-paper", "reasons": ["too big"]}, agent=agents["refused"].id)
        pending = {agents["waiting"].id: {"session": "s-w", "status": "queued", "available": now + 600},
                   agents["resumes"].id: {"session": "s-r", "status": "queued", "available": now - 1}}
        for budget in (True, False):
            for capped in (False, True):
                asked = []
                with patch.object(self.house.research_jobs, "active", side_effect=lambda agent_id: pending.get(agent_id)), \
                        patch.object(self.house, "_sail_research_capped", side_effect=lambda: asked.append("cap") or capped), \
                        patch.object(self.house.pacer, "may_spend", side_effect=lambda kind: asked.append(kind) or budget):
                    new = {name: self.house.research_due(agent) for name, agent in agents.items()}
                    budget_asks, cap_asks = sum(1 for a in asked if a != "cap"), asked.count("cap")
                    asked.clear()
                    old = {name: self.old_research_due(agent) for name, agent in agents.items()}
                self.assertEqual(new, old, (budget, capped))
                self.assertEqual(budget_asks, 3, "asked of `due`, `refused` and `resumes` only, the agents otherwise due")
                self.assertLessEqual(cap_asks, 3 if budget else 0, "the cap, which writes, only after the budget said yes")
                if budget and not capped:
                    self.assertEqual({name for name, due in new.items() if due}, {"due", "refused", "resumes"})

"""Research waiting for a worker must not spend a retired agent's remaining purse."""
import threading
import json
from types import SimpleNamespace

from league.ledger import now_iso
from league.pacer import Pacer
from league.tests.test_house import BUYER, HouseCase


class ResearchLifecycle(HouseCase):
    def test_health_distinguishes_queued_work_from_running_work(self):
        lane = threading.Semaphore(0)
        self.house._lanes["research"] = lane
        entered, finish = threading.Event(), threading.Event()

        def work():
            entered.set()
            finish.wait(5)

        self.house._background("research:example", work)
        try:
            self.clock.advance(7)
            self.house._health({"at": now_iso(self.clock)})
            health = json.loads((self.house.root / "health.json").read_text())
            self.assertEqual(health["background_jobs"], [{"key": "research:example", "state": "queued", "queued_seconds": 7, "running_seconds": 0}])
            lane.release()
            self.assertTrue(entered.wait(5))
            self.clock.advance(3)
            self.house._health({"at": now_iso(self.clock)})
            health = json.loads((self.house.root / "health.json").read_text())
            self.assertEqual(health["background_jobs"][0]["state"], "running")
            self.assertEqual(health["background_jobs"][0]["running_seconds"], 3)
        finally:
            finish.set()
            lane.release()
            self.house.wait(5)
        self.assertEqual(self.house._job_status, {})

    def ready(self):
        self.house.settings.research = True
        self.house.pacer = Pacer(self.house.ledger, clock=self.clock, expedition={
            "start": now_iso(self.clock)[:10], "days": 10, "sail_usd": "50", "openai_usd": "50"})
        calls = []
        self.house.researcher = SimpleNamespace(research=lambda *a, **k: calls.append(a) or SimpleNamespace(candidate=None))
        return self.seated(), calls

    def test_retirement_while_queued_prevents_a_provider_call(self):
        agent, calls = self.ready()
        self.house._lanes["research"] = threading.Semaphore(0)
        self.house._background("research:" + agent.id, self.house._research_if_due, agent)
        self.house.registry.died(agent.id, "displaced")
        self.house._lanes["research"].release()
        self.house._jobs["research:" + agent.id].join(5)
        self.assertEqual(calls, [])
        self.assertNotIn(agent.id, self.house._state["last_research"])

    def test_exhausted_budget_is_rechecked_after_queueing(self):
        agent, calls = self.ready()
        self.assertTrue(self.house.research_due(agent))
        self.house.pacer.may_spend = lambda kind: False
        self.house._research_if_due(agent)
        self.assertEqual(calls, [])

    def test_new_owned_execution_refusal_accelerates_research_without_bypassing_budget(self):
        agent, _ = self.ready()
        self.house._state['last_research'][agent.id] = self.clock()
        self.assertFalse(self.house.research_due(agent))
        self.clock.advance(1)
        self.house.ledger.append('book.refused', {'book': 'alpaca', 'reasons': ['another book']}, agent=agent.id)
        self.clock.advance(59)
        self.assertFalse(self.house.research_due(agent))
        self.house.ledger.append('book.refused', {'book': 'alpaca-paper', 'reasons': ['oversized']}, agent=agent.id)
        self.assertTrue(self.house.research_due(agent))
        self.house.pacer.may_spend = lambda kind: False
        self.assertFalse(self.house.research_due(agent))
        self.house.pacer.may_spend = lambda kind: True
        self.house._state['last_research'][agent.id] = self.clock()
        self.assertFalse(self.house.research_due(agent), 'a refusal already covered by a pass must not retrigger it')

    def test_burst_reaudit_follows_new_completed_evidence_instead_of_waiting_a_day(self):
        agent = self.seated()
        self.house.seat(agent)
        self.house._burst = {'id': 'test-accelerated-game'}
        self.house.game['audit']['min_credits_usd'] = '0.20'
        self.house.ledger.append('audit.verdict', {'approve': False, 'summary': 'needs fresh evidence'}, agent=agent.id)
        self.assertFalse(self.house._audit_due(agent))
        # Five full non-overlapping exposures on the current book, all after the audit.
        for number in range(5):
            for side, cash, quantity in [('buy', '-5', '1'), ('sell', '5.1', '-1')]:
                self.clock.advance(1)
                self.house.ledger.append('book.fill', {'book': 'alpaca-paper', 'instrument': {'symbol': 'BTC/USD'},
                    'side': side, 'source': 'venue', 'cash_delta': cash, 'position_delta': quantity}, agent=agent.id)
            self.assertEqual(self.house._audit_due(agent), number == 4)
        self.assertEqual(self.house.evaluator.rung(agent.id), 1, 'reaudit permission is not a promotion')
        self.house.ledger.append('audit.verdict', {'approve': False, 'summary': 'still no edge'}, agent=agent.id)
        self.assertFalse(self.house._audit_due(agent), 'the same observations cannot purchase repeated reaudits')

    def test_retirement_during_a_pass_does_not_adopt_its_result(self):
        agent, _ = self.ready()
        original = agent.code_sha256
        better = BUYER + "\n# improvement\n"

        def finish(agent, standing, session):
            self.house.registry.died(agent.id, "displaced")
            return SimpleNamespace(candidate={"code": better, "needs": agent.needs, "params": agent.params,
                                              "purpose": "an improvement", "numbers": {}, "passed": True}, consulted="")

        self.house.researcher = SimpleNamespace(research=finish)
        self.house.research(agent)
        self.assertEqual(agent.code_sha256, original)
        self.assertFalse(agent.alive)
        self.assertNotIn(agent.id, self.house._state["last_research"])
        saved = self.house.ledger.last("agent.research").payload
        self.assertEqual(saved["status"], "not_adopted")
        self.assertEqual(saved["_candidate"]["code"], better)

    def test_a_promotion_during_research_uses_the_current_rung(self):
        agent = self.house.spawn("buyer", "test-family", BUYER)
        better = BUYER + "\n# improvement\n"
        original = agent.code_sha256
        forks = []

        def finish(agent, standing, session):
            self.assertEqual(standing["rung"], 0)
            self.house.evaluator.seat(agent.id, 1, "qualified during the pass")
            self.house.record_is_empty = lambda agent: False
            return SimpleNamespace(candidate={"code": better, "needs": agent.needs, "params": agent.params,
                                              "purpose": "an improvement", "numbers": {}, "passed": True}, consulted="")

        self.house.researcher = SimpleNamespace(research=finish)
        self.house.fork = lambda *args, **kwargs: forks.append(kwargs)
        self.house.research(agent)
        self.assertEqual(agent.code_sha256, original)
        self.assertEqual(len(forks), 1)

    def test_a_promotion_to_real_money_during_research_never_replaces_the_audited_code(self):
        agent, _ = self.ready()
        original = agent.code_sha256
        better = BUYER + "\n# unapproved improvement\n"
        forks = []
        self.house.record_is_empty = lambda agent: True

        def finish(agent, standing, session):
            self.assertEqual(standing["rung"], 1)
            self.house.evaluator.seat(agent.id, 2, "the original code passed its audit")
            return SimpleNamespace(candidate={"code": better, "needs": agent.needs, "params": agent.params,
                                              "purpose": "an improvement", "numbers": {}, "passed": True}, consulted="")

        self.house.researcher = SimpleNamespace(research=finish)
        self.house.fork = lambda *args, **kwargs: forks.append(kwargs)
        self.house.research(agent)
        self.assertEqual(agent.code_sha256, original)
        self.assertEqual(len(forks), 1)
        self.assertEqual(forks[0]["code"], better)

    def test_a_real_money_agent_is_never_promised_an_in_place_rewrite(self):
        agent, _ = self.ready()
        self.house.evaluator.seat(agent.id, 2, "audited original code")
        self.house.record_is_empty = lambda agent: True
        prompts = []
        self.house.researcher = SimpleNamespace(research=lambda agent, standing, session:
                                               prompts.append(standing) or SimpleNamespace(candidate=None))
        self.house.research(agent)
        self.assertFalse(prompts[0]["rewrites_in_place"])

    def test_a_barren_real_money_agent_cannot_adopt_a_failed_replay(self):
        agent, _ = self.ready()
        self.house.evaluator.seat(agent.id, 2, "audited original code")
        self.house.record_is_empty = lambda agent: True
        self.house._state["idle"][agent.id] = {"barren": 20, "offered": 10}
        original = agent.code_sha256
        forks = []
        self.house.researcher = SimpleNamespace(research=lambda agent, standing, session: SimpleNamespace(
            candidate={"code": BUYER + "\n# failed experiment\n", "needs": agent.needs, "params": agent.params,
                       "purpose": "it trades", "numbers": {"trades": 3}, "passed": False}, consulted=""))
        self.house.fork = lambda *args, **kwargs: forks.append(kwargs)
        self.house.research(agent)
        self.assertEqual(agent.code_sha256, original)
        self.assertEqual(forks, [])

    def test_an_adopted_candidate_is_joined_to_its_research_trace(self):
        from league.traces import TraceStore
        agent = self.house.spawn("buyer", "test-family", BUYER)
        better = BUYER + "\n# improvement\n"
        store = TraceStore(self.house.root, self.house.ledger, clock=self.house.clock)

        def finish(agent, standing, session):
            store.capture("research", key=session, model="openai_luna", inputs={}, outputs=[], cost_usd="0.01",
                          outcome="candidate_passed", useful=True, agent=agent.id)
            return SimpleNamespace(candidate={"code": better, "needs": agent.needs, "params": agent.params,
                                              "purpose": "an improvement", "numbers": {}, "passed": True}, consulted="")

        self.house.researcher = SimpleNamespace(research=finish, traces=store)
        self.house.research(agent)
        rows = [e.payload for e in self.house.ledger.iter(kinds="trace.record", agent=agent.id)]
        self.assertEqual([(r["version"], r["outcome"], r["useful"]) for r in rows],
                         [(1, "candidate_passed", True), (2, "adopted", True)])

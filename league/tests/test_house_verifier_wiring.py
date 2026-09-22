"""The verifier night's pieces, wired into a real House: what `_update` writes about a release,
and the pre-audit and the consult recovery running beside the tick."""

import unittest
from types import SimpleNamespace

from league.evaluator import Verdict
from league.preaudit import PREAUDIT_STATE_KEY
from league.tests import test_tuition


def setUpModule():
    test_tuition.setUpModule()


def tearDownModule():
    test_tuition.tearDownModule()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.fixture = test_tuition.TuitionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.house = self.fixture.house

    def rows(self, kind, **match):
        return [e for e in self.house.ledger.iter(kinds=kind) if all(e.payload.get(k) == v for k, v in match.items())]


class TheLedgerRecordsWhatTheUpdaterDid(Fixture):
    ATTESTATION = {"sha": "a" * 40, "state": "passed", "ok": True, "checks": [{"name": "gateway", "conclusion": "success"}]}

    def update(self, outcome):
        self.house.updater = SimpleNamespace(check=lambda: dict(outcome), due=lambda: True)
        self.house._update()

    def test_a_deploy_carries_its_attestation_onto_the_ledger(self):
        self.update({"action": "deploying", "release": "main-abc", "files": 3, "sha": "a" * 40, "attestation": self.ATTESTATION})
        row = self.rows("ops.deploy", action="deploying")[-1].payload
        self.assertEqual((row["sha"], row["attestation"]["state"]), ("a" * 40, "passed"))
        self.assertTrue(self.house.deploying())

    def test_a_blocked_head_warns_once_and_does_not_pause_research(self):
        self.update({"action": "blocked", "sha": "b" * 40, "reasons": ["api.github.com could not be reached"], "new": True,
                     "attestation": {"sha": "b" * 40, "state": "unavailable"}})
        self.assertEqual(len(self.rows("ops.deploy", action="blocked")), 1)
        warnings = [e for e in self.rows("ops.alert", level="warning") if "was not deployed (blocked)" in e.payload["text"]]
        self.assertEqual(len(warnings), 1)
        self.assertFalse([e for e in self.rows("ops.alert", level="error")])  # an error would roll the running release back
        self.assertFalse(self.house.deploying())
        self.update({"action": "blocked", "sha": "b" * 40, "reasons": ["still unreachable"], "new": False})
        self.update({"action": "waiting", "sha": "c" * 40, "reasons": ["pending"], "new": False})
        self.assertEqual(len(self.rows("ops.deploy")), 1)  # nothing new, nothing written


class ThePreAuditRunsBesideTheTick(Fixture):
    def test_a_paper_agent_whose_wakes_fail_gets_a_repair_report_and_keeps_its_seat(self):
        agent = self.fixture.on_micro("broken", rung=1)
        for _ in range(6):
            self.house.ledger.append("agent.woke", {"ok": False, "error": "ZeroDivisionError: division by zero", "book": "alpaca-paper"},
                                     agent=agent.id)
        self.house.tick()
        self.house.wait(10)
        reports = [e for e in self.house.ledger.iter(kinds="repair.reported", agent=agent.id)]
        self.assertEqual(len(reports), 1)
        self.assertEqual((reports[0].payload["kind"], reports[0].payload["source"]), ("strategy_defect", "audit"))
        self.assertTrue(self.house.registry.get(agent.id).alive)
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertEqual(self.house._state[PREAUDIT_STATE_KEY][agent.id]["verdict"], "red")
        # Every later promotion status carries the finding, so the agent's research packet sees it.
        self.house._promotion_status(agent, Verdict(agent.id, 1, "continue", "more evidence", {}), "evidence", "more evidence")
        self.assertEqual(self.house._state["promotion_status"][agent.id]["pre_audit"]["verdict"], "red")
        self.house.pre_audit._last = 0
        self.house.tick()
        self.house.wait(10)
        self.assertEqual(len([e for e in self.house.ledger.iter(kinds="repair.reported", agent=agent.id)]), 1)

    def test_the_consult_recovery_keeps_its_cursor_in_the_house_state(self):
        self.house.ledger.append("merton.pass", {"role": "consultant", "agent": "someone", "answer": "Fine.", "confidence": "low",
                                                 "cost_usd": "0.5"})
        self.house.tick()
        self.house.wait(10)
        self.assertIn("seq", self.house._state.get("consult_recovery") or {})


if __name__ == "__main__":
    unittest.main()

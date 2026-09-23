"""The production audit runs beside the tick, not inside it.

Until Sept 22, 2026 `House._promote` called the auditor inline, and `_promote` is reached from
`judge`, which the tick calls in its mark pass: a frontier audit of up to ~570 s stalled every wake
of the floor, real-money exits included. These tests pin the move to a background job: the tick
returns while the audit runs, one audit per agent at a time, the generation is checked before and
after, the gates after the audit are the same ones, and the "auditing" record survives a restart
without losing an approval or paying for a second audit.
"""

import json
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.evaluator import Verdict
from league.house import House, Settings
from league.tests import test_tuition
from league.tests.test_house import FakeAlpacaData
from league.tests.test_ladder import FakeAuditor, InProcessSandbox


def setUpModule():
    test_tuition.setUpModule()


def tearDownModule():
    test_tuition.tearDownModule()


def audit_before(test):
    """These tests pin the audit BEFORE promotion, the path an agent with a known defect still
    takes (and the constitution's rule until Sept 23, 2026); `AuditAfter` below pins the new one."""
    patch = mock.patch.object(House, "_audit_after", return_value=False)
    patch.start()
    test.addCleanup(patch.stop)


class BackgroundAudit(unittest.TestCase):
    def setUp(self):
        audit_before(self)
        self.fixture = test_tuition.TuitionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.house = self.fixture.house

    def blocking_auditor(self, approve=True):
        entered, release, calls = threading.Event(), threading.Event(), []
        self.addCleanup(release.set)

        def audit(agent, verdict):
            calls.append(agent.id)
            entered.set()
            self.assertTrue(release.wait(5), "the test never released the audit")
            self.house.ledger.append("audit.verdict", {"approve": approve, "summary": "test"}, agent=agent.id)
            return {"approve": approve, "summary": "test"}

        self.house.auditor = SimpleNamespace(audit=audit, policy_digest=None)
        return entered, release, calls

    def test_the_tick_does_not_wait_for_the_audit_and_one_audit_runs_at_a_time(self):
        agent = self.fixture.on_micro("audited", rung=1)
        entered, release, calls = self.blocking_auditor()
        verdict = Verdict(agent.id, 1, "eligible", "screen", {})
        started = time.monotonic()
        self.house._promote(agent, verdict)
        self.assertTrue(entered.wait(5))
        self.assertLess(time.monotonic() - started, 4.0)            # the caller did not sit through the (5 s) audit
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "auditing")
        self.house._promote(agent, verdict)                         # the next tick's screen pass
        self.house._promote(agent, verdict)
        release.set()
        self.house.wait(5)
        self.assertEqual(calls, [agent.id])                         # no double audit
        self.assertEqual(self.house.evaluator.rung(agent.id), 2)
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "promoted")
        self.assertNotIn(agent.id, self.house._state.get(House.AUDITS, {}))

    def test_a_generation_change_during_the_audit_promotes_nothing(self):
        agent = self.fixture.on_micro("audited", rung=1)
        entered, release, calls = self.blocking_auditor()
        self.house._promote(agent, Verdict(agent.id, 1, "eligible", "screen", {}))
        self.assertTrue(entered.wait(5))
        with self.house._lifecycle_lock:
            self.house.registry.adopt(agent.id, code=agent.code + "\n# unapproved change\n", needs=agent.needs,
                                      params=agent.params, reason="candidate")
        release.set()
        self.house.wait(5)
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertNotIn(agent.id, self.house.books["alpaca"].accounts)
        self.assertNotIn(agent.id, self.house._state.get(House.AUDITS, {}))

    def test_a_generation_change_before_the_audit_starts_buys_no_audit(self):
        agent = self.fixture.on_micro("audited", rung=1)
        calls = []
        self.house.auditor = SimpleNamespace(audit=lambda a, v: calls.append(a.id) or {"approve": True}, policy_digest=None)
        verdict = Verdict(agent.id, 1, "eligible", "screen", {})
        generation = self.house._generation(agent.id)
        with self.house._lifecycle_lock:
            self.house.registry.adopt(agent.id, code=agent.code + "\n# changed\n", needs=agent.needs, params=agent.params, reason="candidate")
        self.house._run_audit(agent.id, verdict, generation)
        self.assertEqual(calls, [])
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)

    def test_an_auditor_that_raises_is_recorded_as_an_error_and_waits_the_short_cooldown(self):
        agent = self.fixture.on_micro("unlucky", rung=1)
        calls = []

        def broken(a, v):
            calls.append(a.id)
            raise ValueError("the packet could not be built")

        self.house.auditor = SimpleNamespace(audit=broken, policy_digest="policy")
        verdict = Verdict(agent.id, 1, "eligible", "screen", {})
        self.house._promote(agent, verdict)
        self.house.wait(5)
        row = self.house.ledger.last("audit.verdict", agent=agent.id).payload
        self.assertFalse(row["approve"])
        self.assertIn("ValueError", row["error"])
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_veto")
        self.house._promote(agent, verdict)  # the next mark pass, five minutes later
        self.house.wait(5)
        self.assertEqual(calls, [agent.id])
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_cooldown")

    def test_a_veto_in_the_background_keeps_the_agent_on_paper(self):
        agent = self.fixture.on_micro("vetoed", rung=1)
        entered, release, calls = self.blocking_auditor(approve=False)
        self.house._promote(agent, Verdict(agent.id, 1, "eligible", "screen", {}))
        release.set()
        self.house.wait(5)
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_veto")


class Killed(BaseException):
    """The process dying mid-call: nothing after it runs, not even the House's own error handling."""


class RestartDuringAnAudit(unittest.TestCase):
    """The status and the generation the audit is bound to are on disk before the call is made."""

    def setUp(self):
        audit_before(self)
        self.fixture = test_tuition.TuitionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        hook = threading.excepthook
        threading.excepthook = lambda args: None if issubclass(args.exc_type, Killed) else hook(args)
        self.addCleanup(setattr, threading, "excepthook", hook)

    def restart(self, auditor):
        f = self.fixture
        f.house.close(wait=0)
        f.house = House(
            Path(f.dir.name) / "house", brokers={"alpaca-paper": f.paper, "alpaca": f.real}, sandbox=InProcessSandbox(),
            alpaca_data=FakeAlpacaData(), clock=f.clock, settings=Settings(mark_every_seconds=0, research=False, real_money=True),
            game=f.house.game, auditor=auditor)
        auditor.ledger = f.house.ledger
        return f.house

    def interrupted_audit(self, *, finished: bool):
        """An audit dispatched, the process gone mid-call (or just after the verdict was written)."""
        house = self.fixture.house
        agent = self.fixture.on_micro("restarted", rung=1)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def audit(a, v):
            entered.set()
            release.wait(5)
            raise Killed()

        house.auditor = SimpleNamespace(audit=audit, policy_digest=None)
        house._promote(agent, Verdict(agent.id, 1, "eligible", "screen", {}))
        self.assertTrue(entered.wait(5))
        saved = json.loads((Path(self.fixture.dir.name) / "house" / "house.json").read_text())
        self.assertEqual(saved["promotion_status"][agent.id]["stage"], "auditing")
        self.assertIn(agent.id, saved[House.AUDITS])
        if finished:
            house.ledger.append("audit.verdict", {"approve": True, "summary": "approved just before the restart"}, agent=agent.id)
        release.set()
        house._jobs[f"audit:{agent.id}"].join(5)
        return agent

    def test_an_approval_that_landed_before_the_restart_is_committed_not_bought_again(self):
        agent = self.interrupted_audit(finished=True)
        auditor = FakeAuditor()
        house = self.restart(auditor)
        self.assertIn(agent.id, house._state[House.AUDITS])  # read back from disk
        house._promote(house.registry.get(agent.id), Verdict(agent.id, 1, "eligible", "screen", {}))
        house.wait(5)
        self.assertEqual(auditor.seen, [])
        self.assertEqual(house.evaluator.rung(agent.id), 2)
        self.assertNotIn(agent.id, house._state.get(House.AUDITS, {}))

    def test_an_audit_that_left_no_verdict_is_run_again_once(self):
        agent = self.interrupted_audit(finished=False)
        auditor = FakeAuditor()
        house = self.restart(auditor)
        self.assertIn(agent.id, house._state[House.AUDITS])  # read back from disk
        house._promote(house.registry.get(agent.id), Verdict(agent.id, 1, "eligible", "screen", {}))
        house.wait(5)
        self.assertEqual(auditor.seen, [agent.id])
        self.assertEqual(house.evaluator.rung(agent.id), 2)


class AuditAfter(unittest.TestCase):
    """The owner's revision of Sept 23, 2026: a screen-passer takes the micro stake at once and the
    frontier audit runs on the micro rung; a veto sends it straight back to paper."""

    def setUp(self):
        self.fixture = test_tuition.TuitionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.house = self.fixture.house
        self.assertTrue(self.house._audit_after())  # the real constitution

    def auditor(self, approve=True, error=None):
        calls = []

        def audit(agent, verdict, charge=True):
            calls.append((agent.id, charge, verdict.numbers.get("audit_timing")))
            row = {"approve": approve, "summary": "test", **({"error": error} if error else {})}
            self.house.ledger.append("audit.verdict", row, agent=agent.id)
            return row

        self.house.auditor = SimpleNamespace(audit=audit, policy_digest=None)
        return calls

    def test_a_screen_passer_trades_the_micro_stake_before_its_audit_and_an_approval_keeps_it_there(self):
        agent = self.fixture.on_micro("fast", rung=1)
        calls = self.auditor(approve=True)
        self.house._promote(agent, Verdict(agent.id, 1, "eligible", "screen", {"book": "alpaca-paper"}))
        self.assertEqual(self.house.evaluator.rung(agent.id), 2)  # promoted before the audit returned
        self.assertIn(agent.id, self.house.books["alpaca"].accounts)
        self.house.wait(5)
        self.assertEqual(calls, [(agent.id, False, "after")])  # the House pays, and the auditor is told
        self.assertEqual(self.house.evaluator.rung(agent.id), 2)
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_confirmed")
        self.assertNotIn(agent.id, self.house._state.get(House.AUDITS, {}))

    def test_a_veto_sends_it_straight_back_to_paper(self):
        agent = self.fixture.on_micro("vetoed", rung=1)
        self.auditor(approve=False)
        self.house._promote(agent, Verdict(agent.id, 1, "eligible", "screen", {"book": "alpaca-paper"}))
        self.house.wait(5)
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_veto")
        demotion = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "demote"]
        self.assertEqual(len(demotion), 1)
        self.assertIn("audit after promotion vetoed", demotion[0]["reason"])
        # ...and the veto's cooldown bars an immediate second promotion.
        self.house._promote(agent, Verdict(agent.id, 1, "eligible", "screen", {"book": "alpaca-paper"}))
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_cooldown")

    def test_an_audit_that_could_not_run_leaves_it_trading_and_is_owed_after_the_short_cooldown(self):
        agent = self.fixture.on_micro("unlucky", rung=1)
        calls = self.auditor(approve=False, error="HTTP 502")
        self.house._promote(agent, Verdict(agent.id, 1, "eligible", "screen", {"book": "alpaca-paper"}))
        self.house.wait(5)
        self.assertEqual(self.house.evaluator.rung(agent.id), 2)
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_retry")
        self.assertIsNotNone(self.house._audit_owed(agent))
        generation = self.house._generation(agent.id)
        self.house._settle_after_audit(agent, generation)  # inside the short cooldown: nothing
        self.house.wait(5)
        self.assertEqual(len(calls), 1)
        self.fixture.clock.advance(3600)
        calls[:] = []
        self.auditor(approve=True)
        self.house._settle_after_audit(agent, self.house._generation(agent.id))
        self.house.wait(5)
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_confirmed")
        self.assertIsNone(self.house._audit_owed(agent))

    def test_an_agent_with_a_known_defect_is_audited_before_any_money(self):
        agent = self.fixture.on_micro("defective", rung=1)
        calls = self.auditor(approve=False)
        with mock.patch.object(House, "_known_defect", return_value="the pre-audit found cent_rounding"):
            self.house._promote(agent, Verdict(agent.id, 1, "eligible", "screen", {"book": "alpaca-paper"}))
            self.house.wait(5)
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertEqual([c[2] for c in calls], [None])
        self.assertEqual(self.house._state["promotion_status"][agent.id]["stage"], "audit_veto")

    def test_the_house_pays_so_a_broke_agent_is_still_audited(self):
        agent = self.fixture.on_micro("broke", rung=1)
        self.house.economy.charge(agent.id, self.house.economy.balance(agent.id), "test: spent")
        self.assertIsNone(self.house._audit_wait(agent))
        with mock.patch.dict(self.house.game["audit"], {"house_pays": False}):
            self.assertEqual(self.house._audit_wait(agent)["stage"], "audit_credits")


if __name__ == "__main__":
    unittest.main()

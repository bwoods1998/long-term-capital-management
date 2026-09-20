"""Slow work cannot commit into a different strategy, rung stay, or retired identity."""

import threading
import unittest
from types import SimpleNamespace

from league.evaluator import Verdict
from league.tests.test_house import BUYER, HouseCase
from league.tests import test_tuition


class Threads:
    def start(self, work):
        finished, errors = threading.Event(), []

        def run():
            try:
                work()
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        thread = threading.Thread(target=run)
        thread.start()

        def join():
            thread.join(5)
            self.assertFalse(thread.is_alive(), "a lifecycle worker did not finish")
            if errors:
                raise errors[0]

        return finished, join

    def gates(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        return entered, release

    def wait_for(self, event):
        self.assertTrue(event.wait(5), "the worker did not reach its expected boundary")


class CommitConcurrency(Threads, HouseCase):
    def candidate(self, agent):
        return SimpleNamespace(candidate={"code": BUYER + "\n# tested improvement\n", "needs": agent.needs,
                                          "params": agent.params, "purpose": "candidate", "numbers": {}, "passed": True},
                               consulted="")

    def research_ready(self, agent):
        self.house.researcher = SimpleNamespace(research=lambda *args, **kwargs: self.candidate(agent))

    def pause_research_commit(self):
        entered, release = self.gates()
        original, calls = self.house.record_is_empty, []

        def checked(agent):
            answer = original(agent)
            calls.append(answer)
            if len(calls) == 2:  # the final adoption check, after the provider and identity guard
                entered.set()
                self.wait_for(release)
            return answer

        self.house.record_is_empty = checked
        return entered, release

    def test_retirement_serializes_with_the_final_adoption_check(self):
        agent = self.seated()
        self.research_ready(agent)
        entered, release = self.pause_research_commit()
        _, research = self.start(lambda: self.house.research(agent))
        self.wait_for(entered)
        attempted = threading.Event()

        def retire():
            attempted.set()
            self.house.kill(agent, "displaced")

        done, death = self.start(retire)
        try:
            self.wait_for(attempted)
            self.assertFalse(done.wait(.05), "death raced through the candidate's atomic commit")
        finally:
            release.set()
        research()
        death()
        died = self.house.ledger.last("agent.died", agent=agent.id)
        self.assertFalse(agent.alive)
        self.assertTrue(all(row.seq < died.seq for row in self.house.ledger.iter(kinds="agent.strategy", agent=agent.id)))

    def test_old_first_order_cannot_fill_after_the_adoption_check(self):
        agent = self.seated()
        wake = self.house.wake(agent)
        self.research_ready(agent)
        entered, release = self.pause_research_commit()
        _, research = self.start(lambda: self.house.research(agent))
        self.wait_for(entered)
        submitted, attempted = [], threading.Event()

        def submit():
            attempted.set()
            submitted.extend(self.house._submit_wakes(wake["book"], [wake]))

        done, submitter = self.start(submit)
        try:
            self.wait_for(attempted)
            self.assertFalse(done.wait(.05), "order submission raced through the candidate's atomic commit")
        finally:
            release.set()
        research()
        submitter()
        self.assertEqual(submitted, [])
        self.assertEqual(self.house.books[wake["book"]].account(agent.id).holdings, {})
        self.assertEqual(self.broker.submitted, [])

    def test_a_first_fill_committed_before_research_protects_the_parent_record(self):
        agent = self.seated()
        original_hash = agent.code_sha256
        wake = self.house.wake(agent)
        self.research_ready(agent)
        forks = []
        self.house.fork = lambda *args, **kwargs: forks.append(kwargs)
        entered, release = self.gates()
        original_submit = self.broker.submit

        def slow_submit(intent):
            entered.set()
            self.wait_for(release)
            return original_submit(intent)

        self.broker.submit = slow_submit
        _, submitter = self.start(lambda: self.house._submit_wakes(wake["book"], [wake]))
        self.wait_for(entered)
        _, research = self.start(lambda: self.house.research(agent))
        release.set()
        submitter()
        research()
        self.assertEqual(agent.code_sha256, original_hash)
        self.assertEqual(len(forks), 1)
        self.assertTrue(self.house.books[wake["book"]].account(agent.id).holdings)

    def test_a_provider_wait_does_not_block_retirement_and_cannot_revive_its_result(self):
        agent = self.seated()
        original_hash = agent.code_sha256
        entered, release = self.gates()

        def provider(*args, **kwargs):
            entered.set()
            self.wait_for(release)
            return self.candidate(agent)

        self.house.researcher = SimpleNamespace(research=provider)
        _, research = self.start(lambda: self.house.research(agent))
        self.wait_for(entered)
        done, death = self.start(lambda: self.house.kill(agent, "displaced"))
        try:
            self.wait_for(done)
        finally:
            release.set()
        death()
        research()
        self.assertFalse(agent.alive)
        self.assertEqual(agent.code_sha256, original_hash)
        self.assertNotIn(agent.id, self.house._state["last_research"])

    def test_a_decision_wait_does_not_block_research_and_its_stale_effects_are_discarded(self):
        agent = self.seated()
        self.research_ready(agent)
        entered, release = self.gates()
        original_decide, wakes = self.house.sandbox.decide, []

        def decide(*args, **kwargs):
            entered.set()
            self.wait_for(release)
            return original_decide(*args, **kwargs)

        self.house.sandbox.decide = decide
        _, waking = self.start(lambda: wakes.append(self.house.wake(agent)))
        self.wait_for(entered)
        done, research = self.start(lambda: self.house.research(agent))
        try:
            self.wait_for(done)
        finally:
            release.set()
        research()
        waking()
        self.assertIn("changed", wakes[0]["skipped"])
        self.assertNotIn("intents", wakes[0])
        self.assertNotIn(agent.id, self.house._state["memory"])
        self.assertEqual(self.broker.submitted, [])

    def test_parameter_changes_and_rung_round_trips_invalidate_queued_orders(self):
        agent = self.seated()
        for change in ("parameters", "rung"):
            with self.subTest(change=change):
                wake = self.house.wake(agent)
                with self.house._lifecycle_lock:
                    if change == "parameters":
                        self.house.registry.adopt(agent.id, code=agent.code, needs=agent.needs,
                                                  params={"notional": 5.0}, reason="parameter improvement")
                    else:
                        self.house.evaluator.seat(agent.id, 0, "leave this stay")
                        self.house.evaluator.seat(agent.id, 1, "start a new stay")
                self.assertEqual(self.house._submit_wakes(wake["book"], [wake]), [])
        self.assertEqual(self.broker.submitted, [])

    def test_an_old_replay_cannot_mark_or_promote_replacement_code(self):
        agent = self.house.spawn("buyer", "test", BUYER)
        entered, release = self.gates()
        original_hash = agent.code_sha256

        def replay(*args):
            entered.set()
            self.wait_for(release)
            return {"ok": True, "code_sha256": original_hash, "params": {"notional": 20.0}, "trades": 30,
                    "blocks": [{"log_growth": .01 + .01 * (i % 2)} for i in range(40)],
                    "out_of_sample": {"blocks": 15, "mean_log_growth": .01}}, "test-tape"

        self.house._run_replay = replay
        _, replaying = self.start(lambda: self.house._replay_own(agent))
        self.wait_for(entered)
        with self.house._lifecycle_lock:
            self.house.registry.adopt(agent.id, code=BUYER + "\n# new untested strategy\n", needs=agent.needs,
                                      params=agent.params, reason="new candidate")
        release.set()
        replaying()
        trial = self.house.ledger.last("eval.trial", agent=agent.id).payload
        self.assertTrue(trial["passed"])
        self.assertEqual(trial["code_sha256"], original_hash)
        self.assertEqual(self.house.evaluator.rung(agent.id), 0)
        self.assertNotIn(agent.id, self.house._state["tried"])

    def test_refused_or_failed_forks_retain_the_full_candidate(self):
        agent = self.seated()
        self.research_ready(agent)
        self.house.record_is_empty = lambda agent: False
        original_hash = agent.code_sha256
        self.house.fork = lambda *args, **kwargs: None
        self.house.research(agent)
        deferred = self.house.ledger.last("agent.research", agent=agent.id).payload
        self.assertEqual(deferred["status"], "deferred")
        self.assertEqual(deferred["_candidate"]["code"], self.candidate(agent).candidate["code"])

        def broken(*args, **kwargs):
            raise RuntimeError("a probe box is unavailable")

        self.house.fork = broken
        with self.assertRaisesRegex(RuntimeError, "probe box"):
            self.house.research(agent)
        failed = self.house.ledger.last("agent.research", agent=agent.id).payload
        self.assertEqual(failed["status"], "fork_error")
        self.assertEqual(failed["_candidate"], deferred["_candidate"])
        self.assertEqual(agent.code_sha256, original_hash)


class AuditConcurrency(Threads, unittest.TestCase):
    def setUp(self):
        self.fixture = test_tuition.TuitionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.house = self.fixture.house

    def test_audit_wait_does_not_block_retirement_and_approval_cannot_promote_the_dead(self):
        agent = self.fixture.on_micro("audited", rung=1)
        entered, release = self.gates()

        def audit(*args):
            entered.set()
            self.wait_for(release)
            return {"approve": True}

        self.house.auditor = SimpleNamespace(audit=audit)
        verdict = Verdict(agent.id, 1, "eligible", "screen", {})
        _, auditing = self.start(lambda: self.house._promote(agent, verdict))
        self.wait_for(entered)
        done, death = self.start(lambda: self.house.kill(agent, "displaced"))
        try:
            self.wait_for(done)
        finally:
            release.set()
        death()
        auditing()
        self.assertFalse(agent.alive)
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertNotIn(agent.id, self.house.books["alpaca"].accounts)

    def test_approval_of_old_code_cannot_promote_a_replacement(self):
        agent = self.fixture.on_micro("audited", rung=1)
        entered, release = self.gates()

        def audit(*args):
            entered.set()
            self.wait_for(release)
            return {"approve": True}

        self.house.auditor = SimpleNamespace(audit=audit)
        verdict = Verdict(agent.id, 1, "eligible", "screen", {})
        _, auditing = self.start(lambda: self.house._promote(agent, verdict))
        self.wait_for(entered)
        with self.house._lifecycle_lock:
            self.house.registry.adopt(agent.id, code=agent.code + "\n# unapproved change\n", needs=agent.needs,
                                      params=agent.params, reason="candidate")
        release.set()
        auditing()
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertNotIn(agent.id, self.house.books["alpaca"].accounts)

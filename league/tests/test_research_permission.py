"""Ordinary paid research fencing, using synthetic resources and offline transports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from league.swarm import research_permission as P
from league.swarm.models import ModelError
from league.tests.test_swarm_pool import PoolCase, job
from league.tests.test_swarm_loop import LoopCase
from league.tests.test_swarm_sail_fallback import Case as ModelCase
from league.tests import test_swarm_sail_budget as sail_budget_tests
from ltcm.provider import ProviderError
from ltcm.tests.test_provider import FakeTransport
from league.gym.driver import GymDriver, GymError
from league.sailbox import SailboxError


def flag(root: Path, allowed: bool = False) -> str:
    raw = json.dumps({"schema": 1, "ordinary_allowed": allowed}, sort_keys=True).encode() + b"\n"
    path = root / P.FLAG
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


class Permission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_missing_flag_retains_legacy_but_never_proves_exclusivity(self):
        with P.dispatch(self.root):
            self.assertTrue(P.ordinary_allowed(self.root))
        with self.assertRaises(P.ResearchDispatchDenied):
            with P.fenced_host_scope(self.root, permission_sha="0" * 64, code_sha=P.wiring_sha()):
                self.fail("absent flag cannot claim a fence")

    def test_only_explicit_boolean_permission_is_accepted(self):
        self.assertTrue(P.ordinary_allowed(self.root))
        flag(self.root, True)
        self.assertTrue(P.ordinary_allowed(self.root))
        for document in [{"schema": 1, "ordinary_allowed": x} for x in (None, 0, 1, "false", [], {})] + [
                {"schema": True, "ordinary_allowed": True}, {"schema": 2, "ordinary_allowed": True},
                {"schema": 1, "ordinary_allowed": True, "extra": 0}, []]:
            with self.subTest(document=document):
                (self.root / P.FLAG).write_text(json.dumps(document))
                self.assertFalse(P.ordinary_allowed(self.root))
                with self.assertRaises(P.ResearchDispatchDenied):
                    with P.dispatch(self.root):
                        self.fail("malformed permission dispatched")

    def test_duplicates_large_documents_public_files_and_symlinks_fail_closed(self):
        path = self.root / P.FLAG
        for raw in (b'{"schema":1,"ordinary_allowed":false,"ordinary_allowed":true}', b'x' * 4097, b'\xff'):
            path.write_bytes(raw)
            path.chmod(0o600)
            self.assertFalse(P.ordinary_allowed(self.root))
        flag(self.root, True)
        path.chmod(0o644)
        self.assertFalse(P.ordinary_allowed(self.root))
        path.unlink()
        other = self.root / "other"
        other.write_text('{"schema":1,"ordinary_allowed":true}')
        other.chmod(0o600)
        path.symlink_to(other)
        self.assertFalse(P.ordinary_allowed(self.root))

    def test_gate_work_survives_even_a_malformed_ordinary_flag(self):
        (self.root / P.FLAG).write_text("bad")
        for kwargs in ({"kind": "gate"}, {"role": "review"}, {"role": "audit"}):
            with P.dispatch(self.root, **kwargs):
                pass
        for kwargs in ({"kind": "gym"}, {"role": "architect"}, {"role": "researcher"}, {"role": "unknown"}):
            with self.assertRaises(P.ResearchDispatchDenied):
                with P.dispatch(self.root, **kwargs):
                    self.fail("ordinary route dispatched")

    def test_attestation_binds_explicit_bytes_code_and_immutable_receipt(self):
        identity = flag(self.root)
        code = P.wiring_sha()
        with P.fenced_host_scope(self.root, permission_sha=identity, code_sha=code) as receipt:
            first = receipt["receipt_sha256"]
            with P.dispatch(self.root, role="audit"):
                pass
        with P.fenced_host_scope(self.root, permission_sha=identity, code_sha=code) as receipt:
            self.assertEqual(first, receipt["receipt_sha256"])
        other = self.root / "copied"
        other.mkdir()
        flag(other)
        with P.fenced_host_scope(other, permission_sha=identity, code_sha=code) as receipt:
            self.assertNotEqual(first, receipt["receipt_sha256"], "a copied flag has a different lock resource")
        with patch.object(P, "wiring_sha", return_value="e" * 64):
            with self.assertRaises(P.ResearchDispatchDenied):
                with P.fenced_host_scope(self.root, permission_sha=identity, code_sha=code):
                    self.fail("loaded identity alone cannot excuse changed source files")
        for expected_permission, expected_code in (("f" * 64, code), (identity, "f" * 64), (identity, "NaN")):
            with self.assertRaises(P.ResearchDispatchDenied):
                with P.fenced_host_scope(self.root, permission_sha=expected_permission, code_sha=expected_code):
                    self.fail("mismatched identity accepted")
        flag(self.root, True)
        with self.assertRaises(P.ResearchDispatchDenied):
            with P.fenced_host_scope(self.root, permission_sha=identity, code_sha=code):
                self.fail("stale deny receipt accepted")

    def test_inflight_dispatch_blocks_exclusive_claim_and_operator_installation(self):
        flag(self.root, True)
        entered, release, installed = threading.Event(), threading.Event(), threading.Event()
        def paid():
            with P.dispatch(self.root):
                entered.set()
                self.assertTrue(release.wait(3))
        def install():
            with P.operator_lock(self.root):
                flag(self.root)
            installed.set()
        worker = threading.Thread(target=paid)
        operator = threading.Thread(target=install)
        worker.start()
        self.assertTrue(entered.wait(3))
        operator.start()
        try:
            self.assertFalse(installed.wait(.05))
            with self.assertRaises(P.ResearchDispatchDenied):
                with P.fenced_host_scope(self.root, permission_sha="0" * 64, code_sha=P.wiring_sha()):
                    self.fail("in-flight call treated as drained")
        finally:
            release.set()
            worker.join(3)
            operator.join(3)
        self.assertTrue(installed.is_set())
        with P.fenced_host_scope(self.root, permission_sha=P.status(self.root)["permission_sha256"], code_sha=P.wiring_sha()):
            pass

    def test_each_driver_mutation_is_checked_but_readback_cleanup_are_free(self):
        calls = []
        host = Mock()
        for name in ("exec", "upload", "resume", "from_checkpoint", "download", "terminate", "sleep"):
            getattr(host, name).side_effect = lambda *a, n=name, **k: calls.append(n)
        client = P.GymClient(host, self.root, "gym")
        flag(self.root, True)
        client.exec("synthetic", "first")
        flag(self.root)
        for name in ("exec", "upload", "resume", "from_checkpoint"):
            with self.assertRaises(P.ResearchDispatchDenied):
                getattr(client, name)("synthetic")
        for name in ("download", "terminate", "sleep"):
            getattr(client, name)("synthetic")
        P.GymClient(host, self.root, "gate").exec("synthetic", "gate")
        self.assertEqual(calls, ["exec", "download", "terminate", "sleep", "exec"])

    def test_publish_deny_stops_new_work_before_waiting_for_existing_call_drain(self):
        flag(self.root, True)
        entered, release, drained = threading.Event(), threading.Event(), threading.Event()
        def paid():
            with P.dispatch(self.root):
                entered.set()
                self.assertTrue(release.wait(3))
        worker = threading.Thread(target=paid)
        worker.start()
        self.assertTrue(entered.wait(3))
        identity = flag(self.root)
        def wait_for_drain():
            with P.operator_lock(self.root):
                drained.set()
        waiter = threading.Thread(target=wait_for_drain)
        waiter.start()
        try:
            self.assertFalse(drained.wait(.05))
            with self.assertRaises(P.ResearchDispatchDenied):
                with P.dispatch(self.root):
                    self.fail("new work entered while old call was draining")
            with self.assertRaises(P.ResearchDispatchDenied):
                with P.fenced_host_scope(self.root, permission_sha=identity, code_sha=P.wiring_sha()):
                    self.fail("an in-flight old call cannot produce a drain receipt")
        finally:
            release.set()
            worker.join(3)
            waiter.join(3)
        self.assertTrue(drained.is_set())

    def test_actual_driver_exec_retry_rereads_fence_before_second_provider_call(self):
        calls = []
        host = Mock()
        def exec_call(*args, **kwargs):
            calls.append(args)
            flag(self.root)
            raise SailboxError("synthetic retryable refusal", status=503)
        host.exec.side_effect = exec_call
        driver = GymDriver(P.GymClient(host, self.root, "gym"), "synthetic", sleep=lambda seconds: None)
        flag(self.root, True)
        with self.assertRaises(GymError) as caught:
            driver._exec("synthetic command")
        self.assertEqual(len(calls), 1)
        self.assertTrue(P.is_denial(caught.exception))


class Models(ModelCase):
    def test_direct_sail_and_all_ordinary_roles_are_blocked_before_holds_or_factories(self):
        flag(self.store.root)
        self.router.frontier_factory = Mock(side_effect=AssertionError("no frontier"))
        self.router.claude_factory = Mock(side_effect=AssertionError("no Claude"))
        for role in ("architect", "strategist", "diagnostician", "researcher", "rewrite", None):
            with self.subTest(role=role), self.assertRaises(ModelError) as caught:
                self.router.sail("pro_asap", [], family="synthetic", key="direct", role=role)
            self.assertEqual(caught.exception.kind, "research_fenced")
        for role in ("architect", "strategist", "diagnostician", "researcher", "rewrite"):
            with self.assertRaises(ModelError):
                self.router.ask(role=role, system="synthetic", user="synthetic", family="synthetic", key="ask",
                                openai_model="gpt-6-sol", sail_profile="pro_asap")
        with self.assertRaises(ModelError):
            self.router.claude_turn(role="researcher", family="synthetic", key="turn", system="synthetic", tools=[], messages=[])
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.store.spent(), 0)
        self.assertFalse(self.store.get("unsettled"))

    def test_gate_review_audit_keep_their_existing_fallback_routes(self):
        flag(self.store.root)
        review = self.ask("pro_balanced", key="review", role="review")
        audit = self.ask("k3_balanced", key="audit", role="audit")
        self.assertEqual((review["model"], audit["model"]), ("pro_asap", "k3"))
        self.assertEqual(len(self.provider.calls), 3)

    def test_denial_is_rechecked_before_http_retry_and_keeps_existing_unknown_hold(self):
        flag(self.store.root, True)
        def response(*args, **kwargs):
            self.provider.calls.append((args[0], kwargs["request_key"]))
            flag(self.store.root)
            raise ProviderError("provider_http_500")
        self.provider.respond = response
        with self.assertRaises(ModelError):
            self.router.sail("pro_asap", [{"role": "user", "content": "synthetic"}], family="synthetic", key="retry")
        self.assertEqual(len(self.provider.calls), 1)
        self.assertGreater(self.store.spent(), 0, "a conservative prior admission is never refunded by the fence")

    def test_denial_between_balanced_and_fallback_never_pays_alternate_key(self):
        flag(self.store.root, True)
        def response(*args, **kwargs):
            self.provider.calls.append((args[0], kwargs["request_key"]))
            flag(self.store.root)
            raise ProviderError("provider_poll_timeout")
        self.provider.respond = response
        with self.assertRaises(ModelError):
            self.ask()
        self.assertEqual(self.provider.calls, [("k3_balanced", "arch-1")])


class CachedModel(unittest.TestCase):
    setUp = sail_budget_tests.SailBudget.setUp
    write_budget = sail_budget_tests.SailBudget.write_budget
    router = sail_budget_tests.SailBudget.router
    answer = staticmethod(sail_budget_tests.SailBudget.answer)
    ask = sail_budget_tests.SailBudget.ask

    def test_real_terminal_receipt_is_read_back_without_redispatch_after_fence(self):
        transport = FakeTransport(self.answer())
        router = self.router(transport)
        first = self.ask(router, key="prior", role="researcher")
        spent = self.store.spent()
        calls = len(transport.calls)
        flag(self.root)
        with patch.object(router.provider, "respond", side_effect=AssertionError("cache must be local")):
            recovered = self.ask(router, key="prior", role="researcher")
        self.assertEqual(recovered.response_id, first.response_id)
        self.assertEqual(self.store.spent(), spent)
        self.assertEqual(len(transport.calls), calls)
        with self.assertRaises(ModelError):
            self.ask(router, key="different", role="researcher")
        self.assertEqual(len(transport.calls), calls)


class Pool(PoolCase):
    def test_fenced_direct_creation_books_no_compute_and_gate_still_creates(self):
        pool = self.pool()
        flag(self.store.root)
        before = self.store.get("compute_holds")
        pool._start_box("gym")
        self.assertEqual(self.sail.forks, [])
        self.assertEqual(self.store.get("compute_holds"), before)
        with patch.object(pool, "_holdout_listing", return_value=("SPY",)):
            pool._start_box("gate")
        self.assertEqual(len(self.sail.forks), 1)
        self.assertEqual(next(iter(pool.boxes.values())).kind, "gate")

    def test_adopted_asleep_and_ready_boxes_cannot_resume_or_execute(self):
        pool = self.pool()
        for state in ("asleep", "ready"):
            with self.subTest(state=state):
                box = self.ready_box(pool)
                box.state = state
                j = pool.submit(job("synthetic"))
                self.clock.advance(9)
                batch = pool._take(box)
                held = self.store.get("compute_holds")
                spent = self.store.spent()
                flag(self.store.root)
                self.assertIs(pool.run_batch(box, batch), False)
                self.assertEqual(self.calls, [])
                self.assertEqual(self.sail.resumed, [])
                self.assertEqual(j.attempts, 0)
                self.assertFalse(j.done.is_set())
                self.assertIn(j, pool.queue)
                self.assertEqual(self.store.get("compute_holds"), held)
                self.assertEqual(self.store.spent(), spent)
                (self.store.root / P.FLAG).unlink()

    def test_fence_appearing_after_resume_prevents_exec_without_consuming_trial_or_retry(self):
        pool = self.pool()
        box = self.ready_box(pool)
        box.state = "asleep"
        j = pool.submit(job("synthetic"))
        self.clock.advance(9)
        batch = pool._take(box)
        old = self.sail.resume
        def resume(*args, **kwargs):
            answer = old(*args, **kwargs)
            flag(self.store.root)
            return answer
        self.sail.resume = resume
        self.assertIs(pool.run_batch(box, batch), False)
        self.assertEqual(self.sail.resumed, [box.id])
        self.assertEqual(self.calls, [])
        self.assertEqual(j.attempts, 0)
        self.assertFalse(j.done.is_set())
        self.assertIn(j, pool.queue)

    def test_gate_batch_delivers_and_cleanup_remains_available(self):
        pool = self.pool()
        box = self.ready_box(pool, "gate")
        j = pool.submit(job("synthetic", window="holdout", gate="synthetic sealed-test fixture"))
        flag(self.store.root)
        pool.run_batch(box, pool._take(box))
        self.assertTrue(j.done.is_set())
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(pool._retire_box(box, "synthetic cleanup"))
        self.assertEqual(self.sail.terminated, [box.id])

    def test_wrapped_driver_denial_preserves_queued_job_attempts_and_completion(self):
        pool = self.pool()
        box = self.ready_box(pool)
        j = pool.submit(job("synthetic"))
        self.clock.advance(9)
        batch = pool._take(box)
        def refused(*args, **kwargs):
            flag(self.store.root)
            try:
                P.require(self.store.root, kind="gym")
            except P.ResearchDispatchDenied as exc:
                raise GymError("synthetic wrapped driver denial") from exc
        box.driver.run = refused
        self.assertIs(pool.run_batch(box, batch), False)
        self.assertEqual(j.attempts, 0)
        self.assertFalse(j.done.is_set())
        self.assertIn(j, pool.queue)
        self.assertEqual(box.failures, 0)


class Scheduler(LoopCase):
    def test_loaded_runtime_receipt_rejects_old_or_replaced_actor_methods(self):
        swarm = self.swarm()
        self.assertTrue(swarm.status()["research_dispatch"]["runtime_wired"])
        with patch.object(swarm.router, "_sail_dispatch", new=lambda *a, **k: None):
            self.assertFalse(swarm.status()["research_dispatch"]["runtime_wired"])
        with patch.object(swarm.pool, "run_batch", new=lambda *a, **k: None):
            self.assertFalse(swarm.status()["research_dispatch"]["runtime_wired"])

    def test_worker_permission_is_independent_of_zero_or_negative_model_spend(self):
        swarm = self.swarm()
        flag(self.root)
        self.store.add_spend("sail_model", -1, detail={"synthetic": "cost correction"})
        swarm.settings["researcher"]["sail_usd_per_hour"] = 0
        with patch.object(swarm.scheduler, "take") as take:
            swarm.sleep = lambda seconds: swarm.stop.set()
            swarm._worker(0)
        take.assert_not_called()

    def test_fenced_rounds_leave_gate_forward_and_free_maintenance_running(self):
        swarm = self.swarm()
        flag(self.root)
        self.store.put("tournament_at", 1)
        self.store.add_spend("sail_model", -1, detail={"synthetic": "cost correction"})
        rounds = []
        with patch.object(swarm, "_round", side_effect=lambda name, fn: rounds.append(name)), \
                patch.object(swarm.gate, "due", return_value=True), \
                patch.object(swarm.gate, "forward_due", return_value=True), \
                patch.object(swarm.tournament, "due", return_value=True), \
                patch.object(swarm.architect, "due", return_value=True), \
                patch.object(swarm.architect, "refilling", return_value=True), \
                patch.object(swarm.diagnostician, "due", return_value=True), \
                patch.object(swarm.pool, "manage") as manage, \
                patch.object(swarm.funding, "tick") as funding, \
                patch.object(swarm.scheduler, "count_parked") as parked:
            swarm.step()
        self.assertEqual(rounds, ["gate", "forward"])
        manage.assert_called_once()
        funding.assert_called_once()
        parked.assert_not_called()
        self.assertEqual(swarm.architect_pass(), {"skipped": "research_fenced"})


if __name__ == "__main__":
    unittest.main()

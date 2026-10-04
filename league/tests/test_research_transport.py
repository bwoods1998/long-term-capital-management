"""Synthetic host capabilities only: no provider keys, external sockets or real data."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest import mock

from league.swarm.daily_compute import DailyAdmissionError, DailyBudget, DayCostEvidence, InventoryEvidence, ResourceBound, TariffEvidence
from league.swarm.research_transport import (
    ResearchBroker, ResearchCapabilityError, ResearchJob, ResearchPolicy, ResourceObservation,
    ModelCapability, ModelPolicy, ModelReply, IsolationProof, ISOLATION_FACTS, NAMESPACE_FACTS, STATE_KEY,
)
from league.swarm.store import SwarmStore
from league.gym.driver import build_bundle
from league.swarm.evaluator import execution_fingerprint
from league.tests.swarm_fakes import Clock

CODE = 'NEEDS = {"roots": ["SPY"]}\nPARAMS = {}\ndef decide(ctx):\n    return []\n'
BOX = "sb_aaaaaaaa-0000-0000-0000-000000000001"
PRODUCTION = "sb_bbbbbbbb-0000-0000-0000-000000000001"
TOOL = {"type": "function", "name": "gym_run", "description": "Reviewed local research tool", "parameters": {"type": "object"}}


class FakeProvider:
    def __init__(self, clock, policy):
        self.clock, self.policy = clock, policy
        self.creates, self.controls, self.observes, self.lookups = [], [], [], []
        self.rows = {}
        self.sealed = True
        self.lose_create = False

    def from_checkpoint(self, checkpoint, *, name):
        self.creates.append((checkpoint, name))
        self.rows[BOX] = ResourceObservation(BOX, name, checkpoint, self.clock(), self.policy.resource_bound, "running", "synthetic provider GET")
        if self.lose_create:
            raise TimeoutError("synthetic lost creation response")
        return {"sailbox_id": BOX, "status": "running"}

    def observe(self, resource_id):
        self.observes.append(resource_id)
        return self.rows[resource_id]

    def egress(self, resource_id):
        return {"document": {"no_network": True}} if self.sealed else {"document": {"allowlist": ["example.invalid"]}}

    def find_created(self, name, *, checkpoint):
        self.lookups.append((name, checkpoint))
        matches = [r for r in self.rows.values() if r.name == name and r.checkpoint == checkpoint]
        if len(matches) > 1:
            raise ValueError("synthetic ambiguous creation alias")
        return matches[0] if matches else None

    def _control(self, operation, resource_id, status):
        self.controls.append((operation, resource_id))
        self.rows[resource_id] = replace(self.rows[resource_id], status=status)
        return {"sailbox_id": resource_id, "status": status}

    def resume(self, resource_id):
        return self._control("resume", resource_id, "running")

    def sleep(self, resource_id):
        return self._control("sleep", resource_id, "sleeping")

    def terminate(self, resource_id):
        return self._control("terminate", resource_id, "terminated")


class FakeDriver:
    def __init__(self, provider, resource_id, version, calls):
        self.provider, self.resource_id, self.version, self.calls = provider, resource_id, version, calls
        self._bundle = build_bundle()[0]
        self.retries = 1

    def run(self, programs, **options):
        self.calls.append((self.resource_id, programs, options))
        return {"results": [{"run_id": "synthetic-run", "status": "ok", "trials": 1, "window": options["window"],
                             "roots": list(options["roots"]), "stress": options["stress"], "summary": {"trades": 0}}],
                "batch": {"bundle": self.version, "trials": 1}}


class ResearchTransport(unittest.TestCase):
    def test_documented_model_namespace_ids_keep_profiles_resources_and_urls_strict(self):
        for model in ("zai-org/GLM-5.3", "deepseek-ai/DeepSeek-V4-Pro-0813", "moonshotai/Kimi-K3", "openai/gpt-oss-120b"):
            with self.subTest(model=model):
                value = ModelPolicy(model, "1", "2", "0", 100, 100, 1, 200,
                                    "synthetic reviewed model profile")
                self.assertEqual(value.model, model)
        for model in ("https://example.com/model", "a/b/c", "a/../b", "a\\nb", "a\nb", "a/b?x", "a/b#x", "a/%2e", " a/b", "a/b ", None):
            with self.subTest(model=model), self.assertRaises(ResearchCapabilityError):
                ModelPolicy(model, "1", "2", "0", 100, 100, 1, 200, "synthetic reviewed model profile")
        from league.swarm.research_transport import _identity
        self.assertFalse(_identity("zai-org/GLM-5.3"), "profile/request/resource IDs are not broadened")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.start = dt.datetime(2026, 10, 4, tzinfo=dt.timezone.utc).timestamp()
        self.clock = Clock(self.start + 36000)
        self.store = SwarmStore(Path(self.tmp.name) / "host-private", clock=self.clock)
        self.addCleanup(self.store.close)
        self.bound = ResourceBound("synthetic-hard-gym", "gym", 2, "4", "32", "0", "0.01", "synthetic hard CPU/RAM/disk and all creation fees")
        self.artifact_root = Path(__file__).resolve().parents[2]
        self.policy = ResearchPolicy("synthetic-exclusive", "sbcp_aaaaaaaa-bbbb", build_bundle(self.artifact_root)[1], self.bound, ("SPY",),
                                     execution_fingerprint(self.artifact_root),
                                     forbidden_resource_ids=(PRODUCTION,))
        self.tariff = TariffEvidence(self.policy.scope, "0.01", "0.008", "0.001", "0", self.start, self.start + 30 * 86400,
                                     "synthetic complete daily maximum tariff, not production price proof")
        self.inventory = InventoryEvidence(self.policy.scope, (), (), True, True, False, self.start, self.tariff.valid_until,
                                           "synthetic exhaustive exclusive inventory")
        self.budget = self.make_budget()
        self.budget.initialize(DayCostEvidence(self.policy.scope, "2026-10-04", "0", "synthetic complete zero prior cost evidence"))
        self.provider = FakeProvider(self.clock, self.policy)
        self.driver_calls, self.model_calls, self.token_bodies, self.proof_calls = [], [], [], []
        self.model_policy = ModelPolicy("reviewed-model", "10", "20", "0", 2000, 1000, self.start, self.tariff.valid_until,
                                        "synthetic all-billed-token maximum rates and reviewed tokenizer", allowed_tools=(TOOL,))
        self.reply = ModelReply({"status": "completed", "id": "synthetic-response", "output": [], "usage": {}},
                                "0.0005", "2026-10-04", "synthetic authoritative terminal provider bill")
        self.broker = self.make_broker()

    def make_budget(self, store=None, **options):
        return DailyBudget(store or self.store, self.tariff, self.inventory, **options)

    def proof(self, peer, **facts):
        self.proof_calls.append((peer, facts))
        # This is explicitly synthetic namespace evidence; these unit tests assert no physical sandbox readiness.
        return IsolationProof(facts["scope"], peer, os.geteuid(), facts["broker_root"], facts["policy_digest"], "namespaces",
                              self.clock(), self.clock()+60, "a"*64, "b"*64, "c"*64, "d"*64,
                              tuple(sorted(ISOLATION_FACTS | NAMESPACE_FACTS)), "synthetic host process verifier")

    def tokens(self, body):
        self.token_bodies.append(body)
        return 200

    def send(self, body):
        self.model_calls.append(body)
        return self.reply

    def make_broker(self, *, store=None, budget=None, policy=None, verifier=None, factory=None, capability=None, artifact_root=None):
        policy = policy or self.policy
        return ResearchBroker(store or self.store, budget or self.budget, policy, provider=self.provider,
                              artifact_root=artifact_root or self.artifact_root,
                              driver_factory=factory or (lambda provider, box: FakeDriver(provider, box, policy.gym_bundle, self.driver_calls)),
                              model_adapters={"reviewed": capability or ModelCapability(self.model_policy, self.tokens, self.send)},
                              verify_isolation=verifier or self.proof)

    def call(self, operation, payload=None, *, broker=None):
        broker = broker or self.broker
        broker.authorize_peer(os.getpid(), os.geteuid(), os.getegid())
        return broker.handle(operation, payload or {})

    def job(self, **changes):
        return asdict(ResearchJob("synthetic-family", 1, CODE, {}, "train", ("SPY",), **changes))

    def model(self, **changes):
        return self.call("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "synthetic request"}], "key": "model-1", **changes})

    def test_open_runtime_has_no_paid_activity_or_resources(self):
        result = self.call("open_runtime")
        self.assertEqual(result["daily_budget"]["total_upper_usd"], "0")
        self.assertFalse(result["daily_budget"]["vendor_actual"])
        self.assertEqual((self.provider.creates, self.model_calls, self.driver_calls), ([], [], []))
        self.assertEqual(result["evaluation"], {"image": self.policy.checkpoint, "bundle": self.policy.gym_bundle,
                         "execution": self.policy.execution, "roots": ["SPY"], "train_first": "2020-01-02", "train_last": "2024-12-31",
                         "validation_first": "2025-01-02", "validation_last": "2025-12-31", "capital": "10000", "workers": 1, "max_split": 16})

    def test_actual_artifact_identity_is_required_and_reread_before_paid_work(self):
        for policy in (replace(self.policy, execution="f"*64), replace(self.policy, gym_bundle="wrong-bundle")):
            with self.subTest(policy=policy), self.assertRaises(ResearchCapabilityError):
                self.make_broker(policy=policy)
        clone = Path(self.tmp.name) / "reviewed-artifact"
        from league.gym.driver import LEAGUE_FILES
        for name in LEAGUE_FILES:
            target = clone / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.artifact_root/name, target)
        for name in ("gym", "live"):
            shutil.copytree(self.artifact_root/"league"/name, clone/"league"/name, ignore=shutil.ignore_patterns("__pycache__"))
        broker = self.make_broker(artifact_root=clone)
        path = clone/"league"/"live"/"step.py"
        path.write_text(path.read_text()+"\n# synthetic artifact mutation\n")
        with self.assertRaises(ResearchCapabilityError):
            self.call("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "x"}], "key": "after-mutation"}, broker=broker)
        self.assertEqual((self.provider.creates, self.model_calls), ([], []))

    def test_driver_actual_bundle_bytes_are_checked_before_first_run(self):
        def factory(provider, box):
            driver = FakeDriver(provider, box, self.policy.gym_bundle, self.driver_calls)
            driver._bundle = b"synthetic forged bytes"
            return driver
        with self.assertRaises(ResearchCapabilityError):
            self.call("run_gym", {"job": self.job(), "key": "forged-driver"}, broker=self.make_broker(factory=factory))
        self.assertEqual(self.driver_calls, [])

    def test_unauthenticated_or_unverified_runtime_cannot_dispatch(self):
        with self.assertRaises(ResearchCapabilityError):
            self.broker.handle("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "x"}], "key": "model-1"})
        for verifier in (lambda *a, **k: True, lambda *a, **k: None):
            with self.subTest(verifier=verifier), self.assertRaises(ResearchCapabilityError):
                self.call("run_gym", {"job": self.job(), "key": "gym-1"}, broker=self.make_broker(verifier=verifier))
        self.assertEqual((self.provider.creates, self.model_calls), ([], []))

    def test_static_stale_wrong_peer_or_incomplete_proof_is_not_authorization(self):
        for change in ({"observed_at": self.clock()-1000, "valid_until": self.clock()-1},
                       {"facts": tuple(ISOLATION_FACTS)}, {"mode": "distinct_uid"}, {"broker_root": "/synthetic/production"},
                       {"policy_digest": "f"*64}, {"mounts_sha256": "not-a-digest"}):
            with self.subTest(change=change):
                verifier = lambda peer, **kw: replace(self.proof(peer, **kw), **change)
                with self.assertRaises(ResearchCapabilityError):
                    self.call("run_gym", {"job": self.job(), "key": "gym-1"}, broker=self.make_broker(verifier=verifier))
        self.assertEqual(self.provider.creates, [])

    def test_fresh_physical_observation_uses_clock_after_synchronous_verification(self):
        before = self.clock()
        def observed(peer, **facts):
            self.clock.advance(1)
            return self.proof(peer, **facts)
        result = self.call("open_runtime", broker=self.make_broker(verifier=observed))
        self.assertEqual(result["isolation_receipt"]["observed_at"], before+1)
        self.assertEqual((self.provider.creates, self.model_calls), ([], []))

    def test_verification_clock_rollback_and_future_observation_never_authorize_work(self):
        def backward(peer, **facts):
            self.clock.advance(-1)
            return self.proof(peer, **facts)
        with self.assertRaises(ResearchCapabilityError):
            self.call("open_runtime", broker=self.make_broker(verifier=backward))
        def future(peer, **facts):
            return replace(self.proof(peer, **facts), observed_at=self.clock()+1)
        with self.assertRaises(ResearchCapabilityError):
            self.call("open_runtime", broker=self.make_broker(verifier=future))
        self.assertEqual((self.provider.creates, self.model_calls), ([], []))

    def test_peer_identity_is_per_thread_and_consumed_after_handle(self):
        self.call("open_runtime")
        with self.assertRaises(ResearchCapabilityError):
            self.broker.handle("open_runtime", {})
        self.broker.authorize_peer(os.getpid(), os.geteuid(), os.getegid())
        errors = []
        t = threading.Thread(target=lambda: self.capture(errors, lambda: self.broker.handle("open_runtime", {})))
        t.start(); t.join(2)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ResearchCapabilityError)

    @staticmethod
    def capture(errors, fn):
        try:
            fn()
        except Exception as exc:
            errors.append(exc)

    def test_exact_operation_schema_denies_routes_exec_ids_scope_and_cost_arguments(self):
        bad = [("exec", {"command": "echo bad"}), ("stop_gym", {"resource_id": PRODUCTION}),
               ("open_runtime", {"approved": True}), ("evaluate", {"profile": "reviewed", "items": [], "key": "k", "max_usd": "1"}),
               ("run_gym", {"job": self.job(), "key": "g", "checkpoint": self.policy.checkpoint})]
        for operation, payload in bad:
            with self.subTest(operation=operation), self.assertRaises(ResearchCapabilityError):
                self.call(operation, payload)
        self.assertEqual((self.provider.creates, self.provider.controls, self.model_calls), ([], [], []))

    def test_train_run_uses_only_pinned_resource_driver_and_host_execution_options(self):
        result = self.call("run_gym", {"job": self.job(purpose="probe", stress=0.0), "key": "gym-1"})
        self.assertEqual(result["gym_image"], self.policy.checkpoint)
        self.assertEqual(result["gym_bundle"], self.policy.gym_bundle)
        self.assertEqual(self.provider.creates[0][0], self.policy.checkpoint)
        self.assertEqual(self.driver_calls[0][0], BOX)
        options = self.driver_calls[0][2]
        self.assertEqual((options["window"], options["start"], options["end"], options["gate_reason"]),
                         ("train", "2020-01-02", "2024-12-31", None))
        self.assertEqual((options["workers"], options["timeout"], options["capital"]), (1, 900, 10000.0))
        self.assertEqual(result["gym_execution"], self.policy.execution)
        self.assertEqual(result["execution"], {"capital": "10000", "workers": 1, "split": 1, "window": "train",
                         "start": "2020-01-02", "end": "2024-12-31", "roots": ["SPY"], "stress": 0.0})
        self.assertGreater(self.budget.summary()["resource_upper_nanos"], 0)

    def test_validation_is_whole_window_and_never_a_gate_route(self):
        job = self.job()
        job.update(window="validation", purpose="validation")
        result = self.call("run_gym", {"job": job, "key": "validation-1"})
        options = self.driver_calls[0][2]
        self.assertEqual((options["window"], options["start"], options["end"], options["gate_reason"]), ("validation", None, None, None))
        self.assertEqual((result["execution"]["start"], result["execution"]["end"]), (None, None))

    def test_concurrent_broker_instances_commit_only_one_creation_intent(self):
        second_store = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(second_store.close)
        second = self.make_broker(store=second_store, budget=self.make_budget(second_store))
        barrier = threading.Barrier(2)
        for broker in (self.broker, second):
            original = broker._resource
            first = [True]
            def paused(original=original, first=first):
                result = original()
                if first[0]:
                    first[0] = False
                    self.assertIsNone(result)
                    barrier.wait(3)
                return result
            broker._resource = paused
        results, errors = [], []
        def run(broker, key):
            self.capture(errors, lambda: results.append(self.call("run_gym", {"job": self.job(), "key": key}, broker=broker)))
        threads = [threading.Thread(target=run, args=(broker, "concurrent-"+str(i))) for i, broker in enumerate((self.broker, second))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ResearchCapabilityError)
        self.assertEqual(len(self.budget._load()["resources"]), 1)

    def test_forbidden_windows_purposes_ranges_or_remote_options_refuse_before_create(self):
        bad = [{"window": "holdout"}, {"window": "forward"}, {"purpose": "prefilter"}, {"purpose": "holdout"},
               {"purpose": "forward"}, {"start": "2019-12-31"}, {"end": "2025-01-02"}, {"roots": ["QQQ"]},
               {"gate": None}, {"resource_id": PRODUCTION}, {"image": "other"}, {"volumes": []},
               {"split": True}, {"stress": float("nan")}, {"start": False}, {"start": ""}, {"end": 0},
               {"window": "validation", "purpose": "validation", "start": "2025-01-02"}]
        for change in bad:
            with self.subTest(change=change), self.assertRaises((ResearchCapabilityError, ValueError)):
                self.call("run_gym", {"job": {**self.job(), **change}, "key": "gym-1"})
        self.assertEqual(self.provider.creates, [])

    def test_arbitrary_python_exec_program_is_rejected_before_create(self):
        from league.gym.safety import CodeRefused
        with self.assertRaises(CodeRefused):
            self.call("run_gym", {"job": {**self.job(), "code": "import os\nos.system('echo forbidden')"}, "key": "gym-1"})
        self.assertEqual(self.provider.creates, [])

    def test_one_ceiling_rejects_compute_before_any_paid_create(self):
        self.budget.reserve_inference("other-authority-obligation", "24", provenance="synthetic shared all-meter commitment")
        with self.assertRaises(DailyAdmissionError):
            self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        self.assertEqual(self.provider.creates, [])

    def test_lost_creation_survives_restart_without_new_create_or_budget_release(self):
        self.provider.lose_create = True
        with self.assertRaises(TimeoutError):
            self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        before = self.budget.summary()["total_upper_nanos"]
        again_store = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(again_store.close)
        again_budget = self.make_budget(again_store)
        again = self.make_broker(store=again_store, budget=again_budget)
        with self.assertRaises(ResearchCapabilityError):
            self.call("run_gym", {"job": self.job(), "key": "gym-1"}, broker=again)
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(again_budget.summary()["total_upper_nanos"], before)
        self.assertTrue(self.call("recover_gym", broker=again)["outcome_known"])
        self.call("run_gym", {"job": self.job(), "key": "gym-1"}, broker=again)
        self.assertEqual((len(self.provider.creates), len(self.driver_calls)), (1, 1))

    def test_unresolved_gym_dispatch_blocks_new_keys_after_restart_without_rerun(self):
        original = FakeDriver.run
        def lost(driver, programs, **options):
            original(driver, programs, **options)
            raise TimeoutError("synthetic lost evaluation result")
        with mock.patch.object(FakeDriver, "run", lost), self.assertRaises(TimeoutError):
            self.call("run_gym", {"job": self.job(), "key": "original-gym"})
        before = self.budget.summary()["total_upper_nanos"]
        again_store = SwarmStore(self.store.root, clock=self.clock); self.addCleanup(again_store.close)
        again = self.make_broker(store=again_store, budget=self.make_budget(again_store))
        self.assertTrue(self.call("recover_gym", broker=again)["outcome_known"])
        self.call("sleep_gym", broker=again)
        for key in ("original-gym", "different-gym"):
            with self.subTest(key=key), self.assertRaises(ResearchCapabilityError):
                self.call("run_gym", {"job": self.job(), "key": key}, broker=again)
        self.assertEqual((len(self.provider.creates), len(self.driver_calls)), (1, 1))
        self.assertEqual(self.provider.controls, [("sleep", BOX)])
        self.assertEqual(self.budget.summary()["total_upper_nanos"], before)

    def test_malformed_or_production_creation_id_never_gets_control_or_driver(self):
        for resource_id in (None, "None", PRODUCTION):
            with self.subTest(resource_id=resource_id):
                other = tempfile.TemporaryDirectory(); self.addCleanup(other.cleanup)
                store = SwarmStore(Path(other.name), clock=self.clock); self.addCleanup(store.close)
                budget = self.make_budget(store)
                budget.initialize(DayCostEvidence(self.policy.scope, "2026-10-04", "0", "synthetic empty isolated scope"))
                provider_create = self.provider.from_checkpoint
                self.provider.from_checkpoint = lambda *a, **k: {"sailbox_id": resource_id}
                with self.assertRaises(ResearchCapabilityError):
                    self.call("run_gym", {"job": self.job(), "key": "gym-1"}, broker=self.make_broker(store=store, budget=budget))
                self.provider.from_checkpoint = provider_create
                self.assertGreater(budget.summary()["resource_upper_nanos"], 0)
        self.assertEqual((self.provider.observes, self.provider.controls, self.driver_calls), ([], [], []))

    def test_no_network_readback_is_required_and_a_breach_closes_paid_scope(self):
        self.provider.sealed = False
        with self.assertRaises(ResearchCapabilityError):
            self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        with self.assertRaises(DailyAdmissionError):
            self.model()
        self.assertEqual((self.driver_calls, self.model_calls), ([], []))

    def test_resource_resize_breach_blocks_work_but_can_stop_owned_resource(self):
        self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        self.provider.rows[BOX] = replace(self.provider.rows[BOX], bound=replace(self.bound, memory_gib="8"))
        with self.assertRaises(ResearchCapabilityError):
            self.call("run_gym", {"job": self.job(), "key": "gym-2"})
        with self.assertRaises(DailyAdmissionError):
            self.model()
        self.assertTrue(self.call("stop_gym")["runtime_stopped"])
        self.assertEqual(len(self.driver_calls), 1)

    def test_cached_gym_result_is_terminal_and_identical_work_does_not_rerun(self):
        result = self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        self.assertEqual(self.call("cached_result", {"key": "gym-1", "kind": "gym"}), result)
        self.assertEqual(self.call("run_gym", {"job": self.job(), "key": "gym-1"}), result)
        with self.assertRaises(ResearchCapabilityError):
            self.call("run_gym", {"job": self.job(stress=1.5), "key": "gym-1"})
        self.assertEqual(len(self.driver_calls), 1)

    def test_lost_gym_result_is_never_redispatched(self):
        driver = FakeDriver(self.provider, BOX, self.policy.gym_bundle, self.driver_calls)
        driver.run = mock.Mock(side_effect=TimeoutError("synthetic lost driver result"))
        self.broker = self.make_broker(factory=lambda *a: driver)
        with self.assertRaises(TimeoutError):
            self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        self.assertIsNone(self.call("cached_result", {"key": "gym-1", "kind": "gym"}))
        with self.assertRaises(ResearchCapabilityError):
            self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        driver.run.assert_called_once()

    def test_driver_that_can_retry_uncertain_exec_is_refused_before_evaluation(self):
        driver = FakeDriver(self.provider, BOX, self.policy.gym_bundle, self.driver_calls)
        driver.retries = 3
        self.broker = self.make_broker(factory=lambda *a: driver)
        with self.assertRaises(ResearchCapabilityError):
            self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        self.assertEqual(self.driver_calls, [])

    def test_sleep_resume_checks_today_shared_budget_and_never_duplicates_lost_resume(self):
        self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        before = self.budget.summary()["total_upper_nanos"]
        self.assertEqual(self.call("sleep_gym")["status"], "sleeping")
        self.assertEqual(self.budget.summary()["total_upper_nanos"], before)
        self.provider.resume = mock.Mock(side_effect=TimeoutError("synthetic lost resume"))
        with self.assertRaises(TimeoutError):
            self.call("run_gym", {"job": self.job(), "key": "gym-2"})
        with self.assertRaises(ResearchCapabilityError):
            self.call("run_gym", {"job": self.job(), "key": "gym-2"})
        self.provider.resume.assert_called_once()
        self.assertEqual(len(self.driver_calls), 1)

    def test_midnight_expired_daily_evidence_refuses_resume_before_control(self):
        self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        self.call("sleep_gym")
        self.clock.advance(31*86400)
        with self.assertRaises(DailyAdmissionError):
            self.call("run_gym", {"job": self.job(), "key": "gym-2"})
        self.assertEqual(self.provider.controls, [("sleep", BOX)])

    def test_matching_terminated_only_closes_runtime_but_retains_observation_day_hold(self):
        self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        before = self.budget.summary()["total_upper_nanos"]
        for status, response_id in (("failed", BOX), ("create_failed", BOX), ("terminated", PRODUCTION), ("terminating", BOX)):
            with self.subTest(status=status, response_id=response_id):
                self.provider.terminate = lambda _: {"sailbox_id": response_id, "status": status}
                self.assertFalse(self.call("stop_gym")["runtime_stopped"])
                self.assertEqual(self.budget.summary()["total_upper_nanos"], before)
        del self.provider.terminate
        self.assertTrue(self.call("stop_gym")["runtime_stopped"])
        self.assertEqual(self.budget.summary()["total_upper_nanos"], before)
        self.assertFalse(self.call("stop_gym")["vendor_actual"])

    def test_stock_minimal_effort_requires_explicit_review_and_keeps_token_bounds(self):
        from league.swarm.settings import DEFAULTS
        effort = DEFAULTS["researcher"]["reasoning_effort"]
        self.assertEqual(effort, "minimal")
        with self.assertRaises(ResearchCapabilityError):
            self.model(effort=effort)
        self.assertEqual(self.model_calls, [])
        self.assertEqual(self.budget._load()["inference"], {})
        reviewed = replace(self.model_policy, allowed_efforts=("low", effort))
        broker = self.make_broker(capability=ModelCapability(reviewed, self.tokens, self.send))
        result = self.call("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "stock effort"}],
                                      "key": "minimal-reviewed", "effort": effort}, broker=broker)
        self.assertEqual(result["cost_usd"], "0.0005")
        self.assertEqual(self.model_calls[0]["reasoning_effort"], effort)
        self.assertEqual(self.model_calls[0]["max_output_tokens"], self.model_policy.max_output_tokens)
        self.assertEqual(len(self.budget._load()["inference"]), 1)
        with self.assertRaises(ResearchCapabilityError):
            self.call("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "too much"}],
                                   "key": "over-output", "effort": effort, "max_output": reviewed.max_output_tokens + 1}, broker=broker)
        self.assertEqual(len(self.model_calls), 1)

    def test_minimal_syntax_does_not_accept_unknown_reviewed_efforts(self):
        for value in ("MINIMAL", "minimal ", "invented", None, True):
            with self.subTest(value=value), self.assertRaises(ResearchCapabilityError):
                replace(self.model_policy, allowed_efforts=(value,))

    def test_model_quote_includes_reviewed_tools_and_host_bounded_output(self):
        result = self.model(tools=[TOOL], max_output=100, cache_key="reviewed-cache")
        self.assertEqual(result["cost_usd"], "0.0005")
        body = self.token_bodies[0]
        self.assertEqual((body["tools"], body["model"], body["max_output_tokens"]), ([TOOL], "reviewed-model", 100))
        state = self.budget._load()
        obligation = next(iter(state["inference"].values()))
        self.assertEqual(obligation["max_nanos"], 4_000_000)
        self.assertIsNotNone(obligation["dispatch_at"])

    def test_unapproved_profile_tools_media_limits_or_price_refuse_before_inference(self):
        bad = [{"profile": "gateway"}, {"tools": [{"type": "web_search"}]}, {"max_output": 1001}, {"max_output": True},
               {"effort": "high"}, {"tool_choice": {"type": "function", "name": "exec"}},
               {"items": [{"role": "user", "content": [{"type": "input_image", "image_url": "https://example.invalid"}]}]}]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ResearchCapabilityError):
                self.model(**change)
        self.assertEqual(self.model_calls, [])

    def test_host_tokenizer_and_current_price_evidence_are_required(self):
        for token_count in (True, 0, 2001, float("nan")):
            with self.subTest(token_count=token_count), self.assertRaises(ResearchCapabilityError):
                self.model_with_capability(ModelCapability(self.model_policy, lambda _: token_count, self.send))
        stale = replace(self.model_policy, valid_until=self.clock()-1)
        with self.assertRaises(ResearchCapabilityError):
            self.model_with_capability(ModelCapability(stale, self.tokens, self.send))
        self.assertEqual(self.model_calls, [])

    def test_exact_model_price_expiry_and_builtin_tools_are_refused(self):
        expired = replace(self.model_policy, valid_until=self.clock())
        with self.assertRaises(ResearchCapabilityError):
            self.model_with_capability(ModelCapability(expired, self.tokens, self.send))
        for tool in ({"type": "web_search"}, {"type": "code_interpreter"}, {"type": "computer_use_preview"}):
            with self.subTest(tool=tool), self.assertRaises(ResearchCapabilityError):
                replace(self.model_policy, allowed_tools=(tool,))
        self.assertEqual(self.model_calls, [])

    def test_model_host_private_metadata_is_not_returned_or_cached(self):
        self.reply = replace(self.reply, result={**self.reply.result, "api_key": "synthetic-secret", "headers": {"authorization": "synthetic"},
                                               "metadata": {"account_id": "synthetic-account"}, "cost_usd": "0"})
        result = self.model()
        self.assertEqual(result["cost_usd"], "0.0005")
        for field in ("api_key", "headers", "metadata"):
            self.assertNotIn(field, result)
        self.assertNotIn("synthetic-secret", json.dumps(self.call("cached_result", {"key": "model-1"})))

    def model_with_capability(self, capability):
        return self.call("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "x"}], "key": "model-1"},
                         broker=self.make_broker(capability=capability))

    def test_model_budget_failure_precedes_adapter_dispatch(self):
        self.budget.reserve_inference("other-model", "25", provenance="synthetic shared authority hold")
        with self.assertRaises(DailyAdmissionError):
            self.model()
        self.assertEqual(self.model_calls, [])

    def test_lost_model_reply_keeps_slot_and_upper_cost_through_restart(self):
        send = mock.Mock(side_effect=TimeoutError("synthetic lost provider response"))
        broker = self.make_broker(capability=ModelCapability(self.model_policy, self.tokens, send))
        payload = {"profile": "reviewed", "items": [{"role": "user", "content": "x"}], "key": "model-1"}
        with self.assertRaises(TimeoutError):
            self.call("evaluate", payload, broker=broker)
        before = self.budget.summary()["inference_upper_nanos"]
        again = self.make_broker(capability=ModelCapability(self.model_policy, self.tokens, send))
        with self.assertRaises(ResearchCapabilityError):
            self.call("evaluate", payload, broker=again)
        self.assertIsNone(self.call("cached_result", {"key": "model-1"}, broker=again))
        self.assertEqual(self.budget.summary()["inference_upper_nanos"], before)
        send.assert_called_once()

    def test_unknown_model_bill_preserves_upper_hold_and_never_fabricates_zero(self):
        self.reply = replace(self.reply, actual_usd=None, accrued_day=None, provenance=None)
        result = self.model()
        self.assertIsNone(result["cost_usd"])
        self.assertIsNone(result["accrued_day"])
        held = self.budget.summary()["inference_upper_nanos"]
        self.assertGreater(held, 0)
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["inference_upper_nanos"], held)

    def test_terminal_cached_model_recovers_without_provider_calls_and_conflicting_key_refuses(self):
        result = self.model()
        again = self.make_broker()
        self.assertEqual(self.call("cached_result", {"key": "model-1"}, broker=again), result)
        self.assertEqual(self.model(), result)
        with self.assertRaises(ResearchCapabilityError):
            self.model(items=[{"role": "user", "content": "different"}])
        self.assertEqual(len(self.model_calls), 1)

    def test_large_terminal_gym_replies_keep_compact_journal_and_recover_after_restart(self):
        original = FakeDriver.run
        def large(driver, programs, **options):
            result = original(driver, programs, **options)
            result["results"][0]["run_id"] = "large-run-"+str(len(self.driver_calls))
            result["results"][0]["summary"]["synthetic_blob"] = "x"*(7*1024*1024)
            return result
        with mock.patch.object(FakeDriver, "run", large):
            results = [self.call("run_gym", {"job": self.job(), "key": "large-"+str(i)}) for i in range(4)]
        self.assertGreater(sum(len(json.dumps(result)) for result in results), 24*1024*1024)
        state = self.broker._load()
        self.assertLess(len(json.dumps(state)), 8192)
        for request in state["requests"].values():
            self.assertEqual(set(request["result"]), {"sha256", "bytes"})
        self.assertLess(len(json.dumps(self.store._all("SELECT payload FROM events WHERE kind='swarm.research_broker'"))), 16384)
        again_store = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(again_store.close)
        again = self.make_broker(store=again_store, budget=self.make_budget(again_store))
        self.call("open_runtime", broker=again)
        self.assertEqual(self.call("cached_result", {"key": "large-0", "kind": "gym"}, broker=again), results[0])
        self.assertEqual(self.call("run_gym", {"job": self.job(), "key": "large-0"}, broker=again), results[0])
        self.assertEqual((len(self.provider.creates), len(self.driver_calls)), (1, 4))

    def test_terminal_reply_bytes_and_directory_are_fsynced_before_immutable_receipt(self):
        original_record, original_sync = self.broker._record, os.fsync
        synced = []
        def sync(descriptor):
            synced.append(os.fstat(descriptor).st_mode)
            return original_sync(descriptor)
        def record(action, **details):
            if action == "request_finished":
                self.assertGreaterEqual(len(synced), 2)
                reference = details["result"]
                path = self.store.root/"research-broker-results"/(reference["sha256"]+".json")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), reference["sha256"])
                self.assertEqual(path.stat().st_size, reference["bytes"])
            return original_record(action, **details)
        with mock.patch("league.swarm.research_transport.os.fsync", side_effect=sync), mock.patch.object(self.broker, "_record", side_effect=record):
            self.model()

    def test_reply_blob_corruption_or_missing_file_durably_closes_paid_work_without_redispatch(self):
        result = self.model()
        row = self.broker._load()["requests"]["model-1"]
        path = self.store.root/"research-broker-results"/(row["result"]["sha256"]+".json")
        original = path.read_bytes()
        before = self.budget.summary()["total_upper_nanos"]
        path.write_bytes(b"!"+original[1:])  # same-size content corruption
        with self.assertRaises(ResearchCapabilityError):
            self.call("cached_result", {"key": "model-1"})
        self.assertTrue(self.broker._load()["closed"])
        path.write_bytes(original)
        with self.assertRaises(ResearchCapabilityError):
            self.model(key="model-2")
        self.assertEqual(len(self.model_calls), 1)
        self.assertEqual(self.budget.summary()["total_upper_nanos"], before)
        self.assertEqual(self.call("cached_result", {"key": "model-1"}), result)

    def test_missing_or_wrong_size_reply_blocks_new_paid_work_after_restart(self):
        for corruption in ("missing", "size", "wrong-hash"):
            with self.subTest(corruption=corruption):
                temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
                store = SwarmStore(Path(temporary.name), clock=self.clock); self.addCleanup(store.close)
                budget = self.make_budget(store)
                budget.initialize(DayCostEvidence(self.policy.scope, "2026-10-04", "0", "synthetic exclusive prior-cost receipt"))
                broker = self.make_broker(store=store, budget=budget)
                payload = {"profile": "reviewed", "items": [{"role": "user", "content": "x"}], "key": "original"}
                self.call("evaluate", payload, broker=broker)
                reference = broker._load()["requests"]["original"]["result"]
                path = store.root/"research-broker-results"/(reference["sha256"]+".json")
                if corruption == "missing":
                    path.unlink()
                elif corruption == "size":
                    path.write_bytes(path.read_bytes()+b" ")
                else:
                    path.write_bytes(b"!"+path.read_bytes()[1:])
                fresh_store = SwarmStore(store.root, clock=self.clock); self.addCleanup(fresh_store.close)
                fresh = self.make_broker(store=fresh_store, budget=self.make_budget(fresh_store))
                before = budget.summary()["total_upper_nanos"]
                calls = len(self.model_calls)
                with self.assertRaises(ResearchCapabilityError):
                    self.call("evaluate", {**payload, "key": "new"}, broker=fresh)
                self.assertTrue(fresh._load()["closed"])
                with self.assertRaises(ResearchCapabilityError):
                    self.call("evaluate", payload, broker=fresh)
                self.assertEqual(len(self.model_calls), calls)
                self.assertEqual(budget.summary()["total_upper_nanos"], before)

    def test_authoritative_over_bound_model_bill_closes_shared_scope(self):
        self.reply = replace(self.reply, actual_usd="1")
        with self.assertRaises(DailyAdmissionError):
            self.model()
        with self.assertRaises(DailyAdmissionError):
            self.call("run_gym", {"job": self.job(), "key": "gym-1"})
        self.assertEqual(len(self.model_calls), 1)
        self.assertEqual(self.provider.creates, [])

    def test_malformed_or_lost_broker_cache_does_not_reopen_paid_dispatch(self):
        self.model()
        for raw in ('null', '[]', '{"scope":"a","scope":"b"}'):
            with self.subTest(raw=raw):
                self.store._exec("UPDATE kv SET value=? WHERE key=?", (raw, STATE_KEY))
                with self.assertRaises(ResearchCapabilityError):
                    self.model()
        self.assertEqual(len(self.model_calls), 1)

    def test_host_policy_mutation_does_not_expand_a_reviewed_tool_capability(self):
        TOOL["parameters"]["properties"] = {"unreviewed": {"type": "string"}}
        self.addCleanup(lambda: TOOL["parameters"].pop("properties", None))
        with self.assertRaises(ResearchCapabilityError):
            self.model(tools=[TOOL])
        self.assertEqual(self.model_calls, [])

    def test_actual_gym_driver_round_trip_uses_only_synthetic_store_and_reviewed_commands(self):
        try:
            import numpy  # noqa: F401
            import pyarrow  # noqa: F401
        except ImportError:
            self.skipTest("synthetic GymDriver integration needs numpy/pyarrow")
        import sys
        from league.gym import synth
        from league.gym.driver import GymDriver, build_bundle
        from league.tests.test_gym_driver import FakeSail
        guest = Path(self.tmp.name) / "synthetic-guest"
        data = guest / "data"
        synth.generate(data, roots=("SPY",), days=synth.weekdays(dt.date(2023, 5, 1), 2), strikes_each_side=4, max_dte=3)
        local = FakeSail()
        for name in ("exec", "upload", "download"):
            setattr(self.provider, name, getattr(local, name))
        policy = replace(self.policy, gym_bundle=build_bundle()[1])
        self.broker = self.make_broker(policy=policy, factory=lambda provider, box: GymDriver(provider, box, remote_root=str(guest/"runtime"),
                                       store_root=str(data), python=sys.executable, retries=1, cleanup=False))
        result = self.call("run_gym", {"job": self.job(start="2023-05-01", end="2023-05-02"), "key": "real-driver-synthetic"})
        self.assertEqual(result["results"][0]["trials"], 1)
        self.assertEqual(result["results"][0]["window"], "train")
        self.assertEqual(result["gym_bundle"], policy.gym_bundle)
        self.assertTrue(any(kind == "exec" and "--window train" in command and "--start 2023-05-01" in command for kind, command in local.log))
        self.assertFalse(any("--gate" in command or "--window holdout" in command or "--window forward" in command for _, command in local.log))


if __name__ == "__main__":
    unittest.main()

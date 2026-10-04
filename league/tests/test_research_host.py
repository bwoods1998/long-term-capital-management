"""Synthetic host receipts/adapters, plus an actual fixed-controller namespace launch.

Local fake CI/billing/context receipts are deliberately not production evidence.
Only the Bubblewrap process/mount/network observations exercise real OS isolation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import time
import unittest
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest import mock

from league.swarm import research_host as host
from league.swarm import research_sandbox as sandbox
from league.swarm.daily_compute import (DailyBudget, DayCostEvidence, InventoryEvidence,
                                       ResourceBound, TariffEvidence)
from league.swarm.research_state import (ExportApproval, artifact_identity, capture_snapshot, import_snapshot)
from league.swarm.research_transport import (ModelCapability, ModelPolicy, ModelReply, ResearchPolicy)
from league.swarm.store import SwarmStore
from league.tests.test_research_transport import FakeProvider, FakeDriver, BOX, CODE


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class ResearchHost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = Path(__file__).resolve().parents[2]
        self.artifact, self.state, self.broker_root = (self.base/name for name in ("artifact", "isolated-state", "host-only"))
        self.artifact.mkdir(mode=0o700)
        self.broker_root.mkdir(mode=0o700)
        for package in ("league", "ltcm"):
            for original in sorted((self.repo/package).rglob("*")):
                if original.is_file() and "__pycache__" not in original.parts and (original.suffix == ".py" or
                        package == "league" and "gym" in original.relative_to(self.repo).parts and original.suffix == ".md"):
                    target = self.artifact/original.relative_to(self.repo)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(original, target)
        config = {"swarm": {"gym": {"workers": 1, "capital": 10000, "train_from": "2020-01-02", "train_split": 1},
                            "population": {"start": 0, "ceiling": 0}, "architect": {"max_new": 0, "max_refill": 0}}}
        (self.artifact/"config.json").write_text(json.dumps(config))
        (self.artifact/"policy.json").write_text("{}")
        shutil.copyfile(self.repo/"league"/"CONTRACT.md", self.artifact/"league"/"CONTRACT.md")
        self.manifest = tuple((path.relative_to(self.artifact).as_posix(), digest(path.read_bytes()))
                              for path in sorted(self.artifact.rglob("*")) if path.is_file())
        self.image = "sbcp_"+"a"*32
        identity = artifact_identity(self.image, self.artifact)
        source = self.base/"source-fixture"
        store = SwarmStore(source)
        store.put("research_evaluator", asdict(identity)); store.close()
        archive = self.base/"host-only-snapshot"
        snapshot = capture_snapshot(source, archive, snapshot_id="synthetic-host-source", original_evaluator=identity)
        approval = ExportApproval(snapshot["snapshot_id"], snapshot["manifest_sha256"], snapshot["metadata_sha256"], (), (),
                                  "synthetic empty source fixture, no real programs or market evidence")
        import_snapshot(archive, self.state, runtime_scope="synthetic-host", expected_evaluator=identity,
                        artifact_root=self.artifact, approval=approval)
        self.now = time.time()
        day = dt.datetime.fromtimestamp(self.now, dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        self.bound = ResourceBound("synthetic-reviewed", "gym", 1, "1", "1", "0", "0.01", "synthetic hard resource ceilings")
        self.policy = ResearchPolicy("synthetic-host", self.image, identity.bundle, self.bound, ("SPY",), identity.execution)
        self.tariff = TariffEvidence(self.policy.scope, "0.001", "0.001", "0.001", "0", day.timestamp(), day.timestamp()+30*86400,
                                     "synthetic guaranteed maximum tariff, not production pricing")
        self.inventory = InventoryEvidence(self.policy.scope, (), (), True, True, False, self.now-10, self.now+60,
                                           "synthetic exhaustive empty scope")
        self.ledger = SwarmStore(self.broker_root)
        self.budget = DailyBudget(self.ledger, self.tariff, self.inventory)
        self.budget.initialize(DayCostEvidence(self.policy.scope, day.date().isoformat(), "0", "synthetic complete prior cost receipt"))
        self.ledger.close()
        self.runbook = self.file("runbook.txt", b"Synthetic scoped rollback preserves obligations; not a production rehearsal.\n")
        self.adapter_file = self.file("host-adapters.py", b"# synthetic reviewed adapter receipt; unit tests inject synthetic capabilities\n")
        self.head = "a"*40
        self.gate_path = self.broker_root/"deployment.json"
        artifact_sha = digest(json.dumps(dict(self.manifest), sort_keys=True, separators=(",", ":")).encode())
        self.gate = {"schema": 1, "head": self.head, "artifact_sha256": artifact_sha, "observed_at": self.now-5,
                     "valid_until": self.now+600, "checks": {name: {"head": self.head, "conclusion": "success", "receipt_sha256": "b"*64}
                        for name in ("python311", "python314", "gateway", "content")},
                     "rollback": {"head": self.head, "artifact_sha256": artifact_sha, "stopped_scoped_controller": True,
                                  "obligations_preserved": True, "receipt_sha256": "c"*64},
                     "runbook": {"path": str(self.runbook.path), "sha256": self.runbook.sha256, "checks_passed": True},
                     "provenance": "synthetic explicit CI/rollback receipt; no hosted or production proof"}
        self.write_gate()
        self.config = host.HostConfig(self.head, self.artifact, self.manifest, self.state, self.broker_root, "capability.sock",
                                      "config.json", "policy.json", self.policy, self.tariff, self.inventory,
                                      host.ReviewedFile(self.gate_path, digest(self.gate_path.read_bytes())), self.adapter_file)
        self.provider = FakeProvider(time.time, self.policy)
        self.driver_calls, self.model_calls, self.context_calls, self.billing_calls = [], [], [], []
        model = ModelPolicy("synthetic-model", "0.001", "0.001", "0", 100000, 8192, self.now-10, self.now+600,
                            "synthetic complete bounded model bill")
        self.model = ModelCapability(model, lambda body: 100, self.send)
        self.adapters = host.HostAdapters(self.provider,
            lambda provider, box: FakeDriver(provider, box, self.policy.gym_bundle, self.driver_calls),
            {"reviewed": self.model}, self.context, self.billing)

    def file(self, name, raw):
        path = self.broker_root/name
        path.write_bytes(raw); path.chmod(0o600)
        return host.ReviewedFile(path, digest(raw))

    def write_gate(self):
        self.gate_path.write_text(json.dumps(self.gate)); self.gate_path.chmod(0o600)

    def updated_config(self):
        return replace(self.config, deployment_receipt=host.ReviewedFile(self.gate_path, digest(self.gate_path.read_bytes())))

    def context(self, policy_digest):
        self.context_calls.append(policy_digest)
        now = time.time()
        value = {"schema": 1, "scope": self.policy.scope, "broker_uid": os.getuid(), "broker_root": str(self.broker_root),
                 "policy_digest": policy_digest, "observed_at": now, "valid_until": now+60,
                 "facts": sorted(sandbox._EXTERNAL), "runbook": {"path": str(self.runbook.path), "sha256": self.runbook.sha256},
                 "adapters": [{"path": str(self.adapter_file.path), "sha256": self.adapter_file.sha256}],
                 "provenance": "synthetic billing/Gym/CI adapter facts; only namespace observation is real"}
        receipt = self.file("context.json", json.dumps(value).encode())
        return sandbox.HostContextEvidence(receipt.path, receipt.sha256)

    def billing(self):
        self.billing_calls.append(time.time())
        return self.tariff, replace(self.inventory, resource_ids=tuple(sorted(self.provider.rows)),
                                   observed_at=time.time()-1, valid_until=time.time()+60)

    def send(self, body):
        self.model_calls.append(body)
        return ModelReply({"status": "completed", "output": [], "usage": {}}, "0.000001",
                          dt.datetime.now(dt.timezone.utc).date().isoformat(), "synthetic terminal bill")

    def runtime(self, **changes):
        runtime = host.HostRuntime(changes.pop("config", self.config), changes.pop("adapters", self.adapters),
                                   calendar=changes.pop("calendar", lambda day: None), **changes)
        self.addCleanup(runtime.shutdown)
        return runtime

    def test_status_is_coherent_read_only_and_never_loads_adapters_or_provider(self):
        before = (self.broker_root/"swarm.sqlite").read_bytes()
        report = host.host_status(self.config)
        self.assertTrue(report["billing_admission"])
        self.assertFalse(report["physical_peer_verified"])
        self.assertFalse(report["adapters_loaded"])
        self.assertFalse(report["vendor_actual"])
        self.assertEqual(report["daily_budget"]["total_upper_usd"], "0")
        self.assertEqual((self.context_calls, self.billing_calls, self.provider.creates, self.model_calls), ([], [], [], []))
        self.assertEqual((self.broker_root/"swarm.sqlite").read_bytes(), before)

    def test_exact_head_ci_rollback_and_runbook_refuse_before_factory_or_launch(self):
        for change in ("head", "ci", "rollback", "runbook", "expiry"):
            original = json.loads(json.dumps(self.gate))
            if change == "head": self.gate["head"] = "f"*40
            if change == "ci": self.gate["checks"]["python314"]["conclusion"] = "failure"
            if change == "rollback": self.gate["rollback"]["obligations_preserved"] = False
            if change == "runbook": self.gate["runbook"]["checks_passed"] = False
            if change == "expiry": self.gate["valid_until"] = self.now-1
            self.write_gate()
            with self.subTest(change=change), mock.patch.object(host, "launch_sandbox") as launch, self.assertRaises(host.ResearchHostError):
                self.runtime(config=self.updated_config()).start()
            launch.assert_not_called()
            self.gate = original; self.write_gate()
        self.assertEqual((self.context_calls, self.billing_calls, self.provider.creates), ([], [], []))

    def test_reviewed_artifact_change_refuses_before_launch(self):
        (self.artifact/"config.json").write_text('{"changed":true}')
        with mock.patch.object(host, "launch_sandbox") as launch, self.assertRaises(sandbox.SandboxError):
            self.runtime().start()
        launch.assert_not_called()
        self.assertFalse(self.config.spec().broker_socket.exists())

    def test_real_calendar_90_minute_dst_early_close_and_holiday_boundaries(self):
        cases = [("2026-10-05T12:00:00+00:00", True), ("2026-10-05T11:59:59+00:00", False),
                 ("2026-11-02T13:00:00+00:00", True), ("2026-11-02T12:59:59+00:00", False),
                 ("2026-11-27T18:04:59+00:00", True), ("2026-11-27T18:05:00+00:00", False),
                 ("2026-12-25T16:00:00+00:00", False)]
        for stamp, blocked in cases:
            with self.subTest(stamp=stamp):
                self.assertEqual(host.deployment_window(dt.datetime.fromisoformat(stamp).timestamp()) is not None, blocked)
        with self.assertRaises(host.ResearchHostError):
            host.deployment_window(self.now, calendar=lambda _: (_ for _ in ()).throw(ValueError("synthetic missing calendar")))

    def test_crossing_blackout_is_rechecked_immediately_before_launch_and_unlinks_only_new_socket(self):
        times = iter([self.now, *([self.now+2]*100)])
        clock = lambda: next(times)
        session = SimpleNamespace(open_at=dt.datetime.fromtimestamp(self.now+5401, dt.timezone.utc),
                                  close_at=dt.datetime.fromtimestamp(self.now+7*3600, dt.timezone.utc))
        with mock.patch.object(host, "launch_sandbox") as launch, self.assertRaises(host.ResearchHostError):
            self.runtime(clock=clock, calendar=lambda _: session).start()
        launch.assert_not_called()
        self.assertFalse(self.config.spec().broker_socket.exists())
        self.assertEqual(self.provider.creates, [])

    def test_missing_stale_billing_and_changed_context_stop_before_namespace_launch(self):
        stale = replace(self.inventory, valid_until=self.now-1)
        for adapters in (replace(self.adapters, billing=lambda: None), replace(self.adapters, billing=lambda: (self.tariff, stale)),
                         replace(self.adapters, context=lambda _: True)):
            with self.subTest(adapters=adapters), mock.patch.object(host, "launch_sandbox") as launch, self.assertRaises(Exception):
                self.runtime(adapters=adapters).start()
            launch.assert_not_called()
            self.assertFalse(self.config.spec().broker_socket.exists())

    def test_fresh_context_cannot_replace_the_reviewed_launch_runbook_or_adapters(self):
        from league.swarm.research_transport import IsolationProof, ISOLATION_FACTS, NAMESPACE_FACTS
        runtime = self.runtime()
        process = self.stub()
        with mock.patch.object(host, "launch_sandbox", return_value=process):
            runtime.start()
        def observe(peer, evidence):
            # Explicit synthetic process verifier for this host hash-pinning unit test.
            now = time.time()
            return IsolationProof(self.policy.scope, peer, os.getuid(), str(self.broker_root), runtime.broker.policy_digest,
                                  "namespaces", now, now+60, runtime._reviewed_context[0], "b"*64, "c"*64,
                                  runtime._reviewed_context[1], tuple(sorted(ISOLATION_FACTS | NAMESPACE_FACTS)),
                                  "synthetic verifier, no physical readiness claimed")
        process.verify_peer = observe
        def call():
            runtime.broker.authorize_peer(os.getpid(), os.getuid(), os.getgid())
            return runtime.broker.handle("open_runtime", {})
        self.assertEqual(call()["scope"], self.policy.scope)
        original = process.verify_peer
        for field in ("runbook_sha256", "adapters_sha256"):
            process.verify_peer = lambda peer, evidence, field=field: replace(original(peer, evidence), **{field: "f"*64})
            with self.subTest(field=field), self.assertRaises(host.ResearchHostError):
                call()
        self.assertEqual((self.provider.creates, self.model_calls, self.driver_calls), ([], [], []))

    def stub(self):
        # Lifecycle-only stub; it never observes a kernel peer or authorizes paid work.
        return SimpleNamespace(process=SimpleNamespace(stdout=io.BytesIO(b"x"*200000), stderr=io.BytesIO(), poll=lambda: None),
                               close=mock.Mock())

    def test_concurrent_host_or_cleanup_refuses_and_shutdown_preserves_replaced_socket(self):
        runtime = self.runtime()
        with mock.patch.object(host, "launch_sandbox", return_value=self.stub()): runtime.start()
        with self.assertRaises((BlockingIOError, host.ResearchHostError)): self.runtime().cleanup_owned()
        original = self.config.spec().broker_socket
        original.rename(self.broker_root/"old.sock")
        replacement = host.create_listener(original); self.addCleanup(replacement.close)
        runtime.shutdown()
        self.assertTrue(original.exists())
        self.assertLessEqual(len(runtime._output["stdout"]), 65536)

    def socket_receipt(self, *, alive=False):
        path = self.config.spec().broker_socket
        listener = host.create_listener(path)
        info = path.stat()
        store = SwarmStore(self.broker_root)
        store.event("swarm.research_host", None, {"action": "socket_bound", "scope": self.policy.scope,
            "pid": os.getpid() if alive else 999999999, "birth": host.HostRuntime._birth(os.getpid()) if alive else 123,
            "dev": info.st_dev, "ino": info.st_ino, "ctime_ns": info.st_ctime_ns, "at": time.time()})
        store.close()
        return listener

    def test_restart_recovers_exact_dead_refused_socket_and_keeps_existing_budget(self):
        previous = self.socket_receipt(); previous.close()
        runtime = self.runtime()
        with mock.patch.object(host, "launch_sandbox", return_value=self.stub()): runtime.start()
        self.assertIsNotNone(runtime.listener)
        self.assertTrue(any(json.loads(row["payload"]).get("action") == "stale_socket_recovered"
                            for row in runtime.store._all("SELECT payload FROM events WHERE kind='swarm.research_host'")))
        self.assertEqual(runtime.budget.summary()["total_upper_usd"], "0")

    def test_live_or_unknown_socket_is_never_removed(self):
        previous = self.socket_receipt(alive=True); self.addCleanup(previous.close)
        path = self.config.spec().broker_socket
        with mock.patch.object(host, "launch_sandbox") as launch, self.assertRaises(host.ResearchHostError): self.runtime().start()
        launch.assert_not_called(); self.assertTrue(path.exists())
        previous.close(); path.unlink()
        unknown = host.create_listener(path); self.addCleanup(unknown.close)
        with mock.patch.object(host, "launch_sandbox") as launch, self.assertRaises(host.ResearchHostError): self.runtime().start()
        launch.assert_not_called(); self.assertTrue(path.exists())

    def test_actual_fixed_controller_namespace_launch_authenticates_unix_calls_and_cleanly_stops(self):
        if not Path("/usr/bin/bwrap").is_file():
            self.skipTest("Linux Bubblewrap prerequisite unavailable; no physical readiness claimed")
        runtime = self.runtime()
        runtime.start()
        captured = runtime.process
        runtime.serve(max_seconds=2)
        self.assertTrue(captured.peer_births, "actual kernel peer was never observed")
        self.assertTrue(captured.captured_peer_user_namespace)
        working = SwarmStore(self.state, readonly=True)
        try:
            heartbeat = working.get("isolated_controller_heartbeat")
        finally:
            working.close()
        self.assertIsNotNone(heartbeat)
        self.assertEqual(heartbeat["status"], "running")
        self.assertEqual(heartbeat["funnel"]["financial_execution_by_controller"], 0)
        self.assertEqual(heartbeat["funnel"]["unseen_evaluations_by_controller"], 0)
        self.assertEqual((self.provider.creates, self.driver_calls, self.model_calls), ([], [], []))
        self.assertGreaterEqual(len(self.context_calls), 2)
        runtime.shutdown()
        self.assertIsNotNone(captured.process.poll())
        self.assertFalse(self.config.spec().broker_socket.exists())
        self.assertEqual(host.host_status(self.config)["daily_budget"]["total_upper_usd"], "0")
        self.assertTrue(host.host_status(self.config)["last_peer_receipt"]["historical_only"])

    def test_actual_nonempty_stock_research_cycle_crosses_namespace_broker_and_counts_cost_trials_once(self):
        from league.swarm.researcher import TOOLS
        from league.tests.swarm_fakes import result as synthetic_result
        identity = artifact_identity(self.image, self.artifact)
        source = self.base/"nonempty-source"
        store = SwarmStore(source)
        store.put("research_evaluator", asdict(identity))
        family = store.add_family({"id": "synthetic-survivor", "mechanism": "synthetic fixture only", "structure": "long_call",
                                   "roots": ["SPY"]}, origin="synthetic-test")
        version = store.add_version(family["id"], CODE, {}, author="synthetic")
        historical = synthetic_result("synthetic-historical-train", t=4)
        historical.update(trials=7, gym_image=identity.image, gym_bundle=identity.bundle,
                          gym_execution=identity.execution)
        store.add_run(family["id"], version["n"], historical, window="train", stress=1, purpose="train", prune=False)
        for marker in ("b"*64, "c"*64):
            store.add_look(family["id"], version["n"], marker, passed=False, p_value=None,
                           detail={"synthetic": "consumed look fixture, no market evidence"})
        store.update_family(family["id"], inherited_trials=7, inherited_looks=2)
        store.close()
        archive = self.base/"nonempty-archive"
        snapshot = capture_snapshot(source, archive, snapshot_id="synthetic-survivor-source", original_evaluator=identity)
        approval = ExportApproval(snapshot["snapshot_id"], snapshot["manifest_sha256"], snapshot["metadata_sha256"],
                                  (version["sha"],), (), "synthetic source/program and inherited counters, no market data")
        state = self.base/"nonempty-isolated"
        import_snapshot(archive, state, runtime_scope=self.policy.scope, expected_evaluator=identity,
                        artifact_root=self.artifact, approval=approval)
        imported = SwarmStore(state, readonly=True)
        try:
            self.assertEqual(imported.lineage_trials(family["id"]), 7)
            self.assertEqual(imported.lineage_looks(family["id"]), 2)
            historical_ids = {row["run_id"] for row in imported.runs(family["id"])}
        finally:
            imported.close()
        config_document = json.loads((self.artifact/"config.json").read_text())
        config_document["swarm"]["researcher"] = {"profile": "reviewed", "top_profile": None, "reasoning_effort": "low",
            "top_families": 0, "claude_top": 0, "rewrites_per_day": 0, "sweep_enabled": False, "max_output_tokens": 8192}
        (self.artifact/"config.json").write_text(json.dumps(config_document))
        manifest = tuple((path.relative_to(self.artifact).as_posix(), digest(path.read_bytes()))
                         for path in sorted(self.artifact.rglob("*")) if path.is_file())
        artifact_sha = digest(json.dumps(dict(manifest), sort_keys=True, separators=(",", ":")).encode())
        self.gate["artifact_sha256"] = self.gate["rollback"]["artifact_sha256"] = artifact_sha
        self.write_gate()
        config = replace(self.updated_config(), state_root=state, artifact_files=manifest)
        from league.swarm.research_adapters import reviewed_tools
        tools = tuple(reviewed_tools([tool for tool in TOOLS if tool["name"] != "gym_sweep"]))
        model_policy = replace(self.model.policy, allowed_tools=tools)
        calls = []
        def model(body):
            calls.append(body)
            output = ([{"type": "function_call", "name": "gym_run", "call_id": "synthetic-call",
                        "arguments": json.dumps({"code": CODE+"# fresh synthetic revision\n", "params": {}, "full": True})}]
                      if len(calls) == 1 else [{"type": "message", "role": "assistant",
                                               "content": [{"type": "output_text", "text": "Synthetic turn complete."}]}])
            return ModelReply({"status": "completed", "output": output, "usage": {}}, "0.000001",
                              dt.datetime.now(dt.timezone.utc).date().isoformat(), "synthetic authoritative bill")
        original_driver = FakeDriver.run
        def gym(driver, programs, **options):
            document = original_driver(driver, programs, **options)
            row = synthetic_result("fixture-"+str(len(self.driver_calls)), window=options["window"], roots=tuple(options["roots"]), t=4)
            row["stress"] = options["stress"]
            document["results"] = [row]
            return document
        runtime = self.runtime(config=config, adapters=replace(self.adapters,
            models={"reviewed": ModelCapability(model_policy, lambda body: 100, model)}))
        with mock.patch.object(FakeDriver, "run", gym):
            runtime.start()
            runtime.serve(max_seconds=3)
        captured = runtime.process
        self.assertTrue(captured.peer_births)
        runtime.shutdown()
        working = SwarmStore(state, readonly=True)
        try:
            heartbeat = working.get("isolated_controller_heartbeat")
            self.assertEqual(heartbeat["status"], "running", {"heartbeat": heartbeat, "host_output": {
                key: bytes(value).decode(errors="replace")[-2000:] for key, value in runtime._output.items()},
                "model_calls": len(calls), "gym_calls": len(self.driver_calls)})
            research = next(action["result"] for action in heartbeat["actions"] if action["kind"] == "research")
            self.assertNotIn("error", research, research)
            self.assertGreaterEqual(research["trials"], 1)
            self.assertEqual(research["tool_calls"], 1)
            runs = working.runs(family["id"])
            count = sum(row["trials"] for row in runs if row["run_id"] not in historical_ids)
            self.assertGreater(count, 0)
            self.assertEqual(sum(row["trials"] for row in runs if row["run_id"] in historical_ids), 7)
            self.assertEqual(working.lineage_trials(family["id"]), 7+count)
            self.assertEqual(working.lineage_looks(family["id"]), 2)
            self.assertEqual(working.family(family["id"])["band"], "gym")
            self.assertAlmostEqual(working.spent(["sail_model"]), len(calls)*0.000001)
            self.assertTrue(all(row["window"] == "train" for row in runs))
        finally:
            working.close()
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(count, len(self.driver_calls))
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(all(call["tools"] for call in calls))
        ledger = SwarmStore(self.broker_root, readonly=True)
        try:
            ledger._db.execute("BEGIN")
            obligations = DailyBudget(ledger, self.tariff, self.inventory)._load()
            self.assertEqual(len(obligations["resources"]), 1)
            self.assertEqual(len(obligations["inference"]), len(calls))
            self.assertTrue(all(row["receipt"]["actual_nanos"] == 1000 for row in obligations["inference"].values()))
        finally:
            ledger.close()

    def test_unrelated_host_peer_cannot_use_running_controller_capability(self):
        runtime = self.runtime()
        runtime.start()
        from league.swarm.research_ipc import BrokerClient, ResearchIPCError
        import threading
        outcomes = []
        client = BrokerClient(self.config.spec().broker_socket, broker_uid=os.getuid(), timeout=3)
        thread = threading.Thread(target=lambda: self.capture(outcomes, client.open_runtime))
        thread.start()
        runtime.serve(max_seconds=1)
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], ResearchIPCError)
        self.assertEqual(self.provider.creates, [])

    @staticmethod
    def capture(outcomes, call):
        try: outcomes.append(call())
        except Exception as exc: outcomes.append(exc)

    def recorded_resource(self, *, bound=True):
        runtime = self.runtime()
        runtime._build_broker(admission=False)
        with runtime.store.atomic():
            runtime.broker._record("opened", scope=self.policy.scope, policy_digest=runtime.broker.policy_digest)
            runtime.budget.reserve_resource("synthetic-resource", self.bound)
            runtime.budget.dispatch("synthetic-resource")
            runtime.broker._record("resource_started", key="synthetic-resource", name="synthetic-owned")
        if bound:
            self.provider.from_checkpoint(self.image, name="synthetic-owned")
            runtime.broker._attach("synthetic-resource", runtime.broker._resource()[1], self.provider.observe(BOX))
        runtime.shutdown()

    def test_explicit_cleanup_uses_only_recorded_resource_and_retains_unknown_bill(self):
        self.recorded_resource()
        report = self.runtime(adapters=replace(self.adapters, billing=mock.Mock(side_effect=AssertionError("no new admission needed")))).cleanup_owned()
        self.assertEqual(report, {"status": "terminated", "runtime_stopped": True, "vendor_actual": False})
        self.assertEqual(self.provider.controls, [("terminate", BOX)])
        result = host.host_status(self.config)
        self.assertGreater(result["daily_budget"]["total_upper_nanos"], 0)
        self.assertEqual(result["resource_obligations"], 1)
        self.assertFalse(result["vendor_actual"])

    def test_unbound_lost_create_cleanup_never_discards_hold_or_searches_account(self):
        self.recorded_resource(bound=False)
        result = self.runtime().cleanup_owned()
        self.assertEqual(result["status"], "unresolved_creation")
        self.assertFalse(result["runtime_stopped"])
        self.assertEqual((self.provider.controls, self.provider.lookups, self.provider.observes), ([], [], []))
        self.assertGreater(host.host_status(self.config)["daily_budget"]["total_upper_nanos"], 0)

    def test_lost_or_wrong_terminal_cleanup_keeps_durable_stop_intent(self):
        self.recorded_resource()
        self.provider.terminate = mock.Mock(side_effect=TimeoutError("synthetic lost stop"))
        with self.assertRaises(TimeoutError): self.runtime().cleanup_owned()
        store = SwarmStore(self.broker_root, readonly=True)
        try:
            self.assertEqual(next(iter(store.get("research_broker_v1")["resources"].values()))["status"], "stop_requested")
        finally: store.close()
        for response in ({"sailbox_id": BOX, "status": "failed"}, {"sailbox_id": "sb_"+"b"*32, "status": "terminated"}):
            self.provider.terminate = mock.Mock(return_value=response)
            self.assertFalse(self.runtime().cleanup_owned()["runtime_stopped"])
        self.assertGreater(host.host_status(self.config)["daily_budget"]["total_upper_nanos"], 0)

    def test_cli_check_and_status_never_import_adapter_factory(self):
        document = asdict(self.config)
        raw = json.dumps(document, default=str).encode()
        reviewed = self.file("host.json", raw)
        loaded = host.load_config(reviewed)
        self.assertEqual(loaded, self.config)
        for operation in ("check", "status"):
            with mock.patch.object(host, "load_adapters", side_effect=AssertionError("must remain pure")), \
                    mock.patch.object(host, "deployment_window", return_value=None), mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(host.main([operation, "--config", str(reviewed.path), "--config-sha256", reviewed.sha256]), 0)
        reviewed.path.write_bytes(raw+b" ")
        with self.assertRaises(host.ResearchHostError): host.load_config(reviewed)

    def test_cli_check_refuses_stale_billing_changed_adapter_and_cleanup_uncertainty(self):
        config = replace(self.config, inventory=replace(self.inventory, valid_until=self.now-1))
        reviewed = self.file("stale-host.json", json.dumps(asdict(config), default=str).encode())
        with mock.patch.object(host, "load_adapters", side_effect=AssertionError("check must remain pure")), \
                mock.patch.object(host, "deployment_window", return_value=None), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(host.main(["check", "--config", str(reviewed.path), "--config-sha256", reviewed.sha256]), 2)
        reviewed = self.file("host.json", json.dumps(asdict(self.config), default=str).encode())
        self.adapter_file.path.write_bytes(b"# changed reviewed bytes\n")
        with mock.patch.object(host, "load_adapters", side_effect=AssertionError("check must remain pure")), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(host.main(["check", "--config", str(reviewed.path), "--config-sha256", reviewed.sha256]), 2)
        for status, expected in (("absent", 0), ("terminated", 0), ("unresolved_creation", 2), ("failed", 2), ("unknown", 2)):
            runtime = self.runtime()
            with self.subTest(status=status), mock.patch.object(host, "load_adapters", return_value=self.adapters), \
                    mock.patch.object(host, "HostRuntime", return_value=runtime), \
                    mock.patch.object(runtime, "cleanup_owned", return_value={"status": status}), \
                    mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(host.main(["cleanup", "--config", str(reviewed.path), "--config-sha256", reviewed.sha256]), expected)

    def test_hash_reviewed_factory_executes_verified_bytes_only_outside_controller_mount(self):
        code = b"from league.swarm.research_host import HostAdapters\ndef build_host_adapters(config):\n    return HostAdapters(object(), lambda *a: None, {}, lambda *a: None, lambda: None)\n"
        adapter = self.file("explicit-adapter.py", code)
        config = replace(self.config, adapter_file=adapter)
        self.assertIsInstance(host.load_adapters(config), host.HostAdapters)
        adapter.path.write_bytes(code+b"# changed\n")
        with self.assertRaises(host.ResearchHostError): host.load_adapters(config)
        mounted = self.artifact/"credential_adapter.py"
        mounted.write_bytes(code); mounted.chmod(0o600)
        with self.assertRaises(host.ResearchHostError):
            host.load_adapters(replace(self.config, adapter_file=host.ReviewedFile(mounted, digest(code))))


if __name__ == "__main__":
    unittest.main()

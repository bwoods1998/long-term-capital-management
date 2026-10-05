from contextlib import closing
import datetime as dt
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from league.swarm.research_controller import (ControllerConfig, ResearchController,
                                             ResearchControllerError, build_controller, explicit_settings, main)
from league.swarm.store import SwarmStore


class Broker:
    def __init__(self):
        self.calls = 0
        self.scope = "private-research"
        self.room = 10000000
        self.evaluation = {"capital": "5000", "workers": 8, "image": "sbcp_test", "max_split": 5}

    def open_runtime(self):
        self.calls += 1
        return {"scope": self.scope, "daily_budget": {"within_cap": True, "room_nanos": self.room},
                "evaluation": self.evaluation}


class Actor:
    def __init__(self):
        self.calls = []
        self.enabled = True

    def due(self):
        return self.enabled

    def run(self):
        self.calls.append("run")
        return {"done": True}

    def cycle(self, family):
        self.calls.append(family)
        return {"family": family}


class ResearchControllerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1791158400.0
        self.store = SwarmStore(Path(self.temp.name), clock=lambda: self.now)
        self.addCleanup(self.store.close)
        # Explicit empty synthetic import history; production build_controller
        # requires the complete guarded import receipt via assert_isolated_state.
        from league.swarm.research_state import _BASELINE_SQL
        self.store._db.executescript(_BASELINE_SQL)
        self.broker, self.researcher, self.tournament, self.architect = Broker(), Actor(), Actor(), Actor()
        self.state_checks = []
        self.controller = ResearchController(self.store, self.broker, ControllerConfig("private-research"),
                                             researcher=self.researcher, tournament=self.tournament,
                                             architect=self.architect, verify_state=lambda: self.state_checks.append(True),
                                             clock=lambda: self.now)
        self.clean_env = mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True)
        self.clean_env.start()
        self.addCleanup(self.clean_env.stop)

    def family(self, name, **state):
        family = self.store.add_family({"id": name, "mechanism": "synthetic hypothesis", "structure": "long_call",
                                       "roots": ["SPY"]}, origin="synthetic-test")
        if state:
            self.store.set_state(family["id"], **state)
        return family["id"]

    def test_actual_tick_calls_only_research_actors_and_emits_private_funnel(self):
        fid = self.family("survivor")
        before = self.store.totals()
        row = self.controller.step()
        self.assertEqual(row["status"], "running")
        self.assertEqual(self.researcher.calls, [fid])
        self.assertEqual(self.architect.calls, ["run"])
        self.assertEqual(self.tournament.calls, ["run"])
        self.assertEqual(self.state_checks, [True])
        self.assertEqual(row["funnel"]["unseen_evaluations_by_controller"], 0)
        self.assertEqual(self.store.totals(), before)

    def test_daily_funnel_excludes_same_day_imported_history_but_preserves_lineage_trials(self):
        from dataclasses import asdict
        from league.swarm.research_state import ArtifactIdentity, ExportApproval, artifact_identity, capture_snapshot, import_snapshot
        from league.tests.test_research_state import reviewed_fixture_projection
        from league.tests.swarm_fakes import result
        old = ArtifactIdentity("synthetic-old-image", "synthetic-old-bundle", "a"*64)
        self.store.put("research_evaluator", asdict(old))
        family = self.family("same-day-survivor")
        version = self.store.add_version(family, "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {}, author="synthetic")
        for window in ("train", "validation", "holdout"):
            row = result("historic-same-day-" + window)
            row["trials"] = 7
            self.store.add_run(family, version["n"], row, window=window, stress=1, purpose=window, prune=False)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        repo = Path(__file__).resolve().parents[2]
        actual = artifact_identity("synthetic-reviewed-checkpoint", repo)
        snapshot = capture_snapshot(Path(self.temp.name), base/"audit", snapshot_id="same-day-source", original_evaluator=old)
        projection = reviewed_fixture_projection(base/"audit")
        approval = ExportApproval(snapshot["snapshot_id"], snapshot["manifest_sha256"], snapshot["metadata_sha256"], (), (),
                                  "Explicit synthetic same-day history and safe development metadata review", projection.sha256)
        import_snapshot(base/"audit", base/"working", runtime_scope="private-research", expected_evaluator=actual,
                        artifact_root=repo, approval=approval, metadata_projection=projection)
        working = SwarmStore(base/"working", clock=lambda: self.now)
        self.addCleanup(working.close)
        self.controller.store = working
        self.assertEqual(self.controller._funnel(self.now)["runs"], [])
        self.assertEqual(working.lineage_trials(family), self.store.lineage_trials(family))
        new = result("new-isolated-train")
        new["trials"] = 3
        working.add_run(family, version["n"], new, window="train", stress=1, purpose="train", prune=False)
        self.assertEqual(self.controller._funnel(self.now)["runs"], [{"window": "train", "status": "ok", "runs": 1, "trials": 3}])
        self.assertEqual(working._one("SELECT count(*) n FROM runs")["n"], 4)
        self.assertEqual(working.lineage_trials(family), self.store.lineage_trials(family) + 3)

    def test_daily_funnel_refuses_missing_baseline_instead_of_claiming_copied_runs_are_fresh(self):
        self.store._exec("DROP TABLE research_baseline")
        with self.assertRaisesRegex(ResearchControllerError, "immutable imported-run baseline"):
            self.controller._funnel(self.now)

    def test_no_budget_room_or_wrong_scope_consumes_no_cycles_trials_or_actor_calls(self):
        self.family("survivor")
        before = self.store.totals()
        for changes in ({"room": 0}, {"room": True}, {"scope": "production"}):
            self.broker.room, self.broker.scope = 100, "private-research"
            for key, value in changes.items():
                setattr(self.broker, key, value)
            self.assertEqual(self.controller.step()["status"], "held")
        self.assertEqual(self.store.totals(), before)
        self.assertEqual(self.researcher.calls + self.architect.calls + self.tournament.calls, [])

    def test_credentials_and_invalid_state_stop_before_broker_or_research(self):
        with mock.patch.dict(os.environ, {"GATEWAY_TOKEN": "fixture-only"}):
            self.assertEqual(self.controller.step()["status"], "held")
        self.assertEqual(self.broker.calls, 0)
        def invalid():
            raise ResearchControllerError("copied production resource")
        self.controller.verify_state = invalid
        self.assertEqual(self.controller.step()["status"], "held")
        self.assertEqual(self.broker.calls, 0)

    def test_unseen_reservations_and_retirements_never_reenter_development(self):
        self.family("held", gate_ready=True)
        self.family("inflight", look_inflight="reserved-sha")
        fid = self.family("retired")
        self.store.update_family(fid, retired_at="2026-10-03T00:00:00Z")
        row = self.controller.step()
        self.assertEqual(self.researcher.calls, [])
        self.assertEqual(row["funnel"]["awaiting_unseen"], 1)

    def test_failed_validation_can_continue_research_with_evidence_retained(self):
        fid = self.family("survivor", validation_failed={"version": 1, "reason": "line_not_met"})
        before = self.store.family(fid)["state"]
        self.controller.step()
        self.assertEqual(self.researcher.calls, [fid])
        self.assertEqual(self.store.family(fid)["state"], before)

    def test_round_robin_and_cadence_dont_starve_a_surviving_family(self):
        fids = sorted([self.family("a"), self.family("b")])
        self.controller.step()
        self.controller.step()
        self.assertEqual(self.researcher.calls, [fids[0]])
        self.now += 60
        self.controller.step()
        self.now += 60
        self.controller.step()
        self.assertEqual(self.researcher.calls, [fids[0], fids[1], fids[0]])

    def test_explicit_settings_never_reads_state_env_or_sealed_image(self):
        with mock.patch("league.swarm.settings.read_policy", side_effect=AssertionError("implicit policy reader")):
            config = explicit_settings({"swarm": {"gate": {"enabled": True}, "forward": {"enabled": True}}}, {},
                                       checkpoint="sbcp_fixture", roots=("SPY",))
        self.assertIsNone(config["gym"]["gate_checkpoint"])
        self.assertFalse(config["gate"]["enabled"])
        self.assertFalse(config["forward"]["enabled"])
        self.assertFalse(config["claude"]["enabled"])

    def test_single_tick_lock_does_not_repeat_a_paid_actor(self):
        self.controller._stepping.acquire()
        try:
            with self.assertRaises(ResearchControllerError):
                self.controller.step()
        finally:
            self.controller._stepping.release()
        self.assertEqual(self.broker.calls, 0)

    def test_config_refuses_bad_scope_and_unbounded_cadence(self):
        for scope, cadence in (("production/../", 20), ("private", True), ("private", float("nan")), ("private", 0)):
            with self.assertRaises(ResearchControllerError):
                ControllerConfig(scope, tick_seconds=cadence)

    def test_shutdown_keeps_store_open_until_late_dispatcher_joins(self):
        pool = mock.Mock()
        pool.stop.return_value = False
        self.researcher.pool = pool
        close = mock.Mock()
        with mock.patch.object(self.store, "close", close):
            self.assertFalse(self.controller.close())
            close.assert_not_called()
            pool.stop.return_value = True
            self.assertTrue(self.controller.close())
            close.assert_called_once()

    def test_cli_does_not_report_success_when_dispatcher_shutdown_is_unresolved(self):
        config, policy = self.store.root / "config.json", self.store.root / "policy.json"
        config.write_text("{}")
        policy.write_text("{}")
        controller = mock.Mock()
        controller.run.return_value = 0
        argv = ["--state", str(self.store.root), "--artifact", str(self.store.root), "--scope", "private-research",
                "--image", "synthetic", "--broker-socket", str(self.store.root / "broker.sock"),
                "--broker-uid", str(os.getuid()), "--config", str(config), "--policy", str(policy), "--roots", "SPY", "--once"]
        with mock.patch("league.swarm.research_controller.build_controller", return_value=controller), \
                mock.patch("league.swarm.research_controller.signal.signal"):
            controller.close.return_value = False
            self.assertEqual(main(argv), 2)
            controller.close.return_value = True
            self.assertEqual(main(argv), 0)

    def test_free_original_receipt_recovery_precedes_a_paid_budget_hold(self):
        pool = mock.Mock()
        self.researcher.pool = pool
        self.broker.room = 0
        row = self.controller.step()
        self.assertEqual(row["status"], "held")
        pool.recover.assert_called_once_with(researcher=self.researcher, tournament=self.tournament)
        self.assertEqual(self.store.get("isolated_controller_heartbeat")["status"], "held")
        self.assertEqual(self.researcher.calls + self.architect.calls + self.tournament.calls, [])

    def test_host_capital_image_or_split_mismatch_holds_before_any_actor(self):
        self.controller.expected_evaluation = {"capital": "5000", "image": "sbcp_test", "required_split": 5}
        for changes in ({"capital": "1000"}, {"image": "sbcp_other"}, {"max_split": 4}, {"max_split": True}):
            self.broker.evaluation = {"capital": "5000", "image": "sbcp_test", "max_split": 5, **changes}
            self.assertEqual(self.controller.step()["status"], "held", changes)
        self.assertEqual(self.researcher.calls + self.architect.calls + self.tournament.calls, [])


class GuardedObjectiveBootstrap(unittest.TestCase):
    """Actual guarded imports and research actors; every broker answer is synthetic."""

    def setUp(self):
        from league.swarm.research_state import artifact_identity
        from league.tests.test_research_state import ResearchState

        self.environment = mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.fixture = ResearchState("runTest")
        self.fixture.repo = Path(__file__).resolve().parents[2]
        self.fixture.actual = artifact_identity("synthetic-bootstrap-checkpoint", self.fixture.repo)
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.import_state()
        self.root, self.identity = self.fixture.fresh, self.fixture.actual
        self.config_document = {"swarm": {"gym": {"train_from": "2020-01-02"}}}
        self.policy_document = {}
        self.broker = Broker()
        self.broker.scope = "synthetic-research-1"
        self.broker.evaluation = {"image": self.identity.image, "bundle": self.identity.bundle,
            "execution": self.identity.execution, "roots": ["SPY", "QQQ"], "capital": "10000",
            "workers": 8, "train_first": "2020-01-02", "max_split": 16}
        self.model_requests = []
        self.broker.evaluate = self.synthetic_model

    def synthetic_model(self, profile, items, *, key, **options):
        import json
        self.model_requests.append({"profile": profile, "items": items, "key": key, **options})
        return {"request_key": key, "profile": profile, "id": "resp_synthetic_bootstrap",
                "model": "synthetic/" + profile, "status": "completed", "cost_usd": "0",
                "accrued_day": dt.datetime.now(dt.timezone.utc).date().isoformat(),
                "output": [{"type": "function_call", "name": "gym_run", "call_id": "synthetic_hold",
                            "arguments": json.dumps({"hold": True, "why": "Synthetic startup; no Gym dispatch"})}]}

    def build(self):
        controller = build_controller(self.root, self.broker, ControllerConfig(self.broker.scope),
            image=self.identity.image, artifact_root=self.fixture.repo,
            config_document=self.config_document, policy_document=self.policy_document, roots=("SPY", "QQQ"))
        self.addCleanup(controller.close)
        return controller

    def history(self):
        with closing(SwarmStore(self.root, readonly=True)) as store:
            parent = store.family("parent")["state"]
            return {"baseline": store._all("SELECT * FROM research_baseline ORDER BY kind,identity"),
                "versions": store._all("SELECT * FROM versions ORDER BY family,n"),
                "runs": store._all("SELECT * FROM runs ORDER BY run_id"),
                "looks": store._all("SELECT * FROM looks ORDER BY seq"),
                "retired": store.family("other"), "N": store.lineage_trials("child"),
                "look_count": store.lineage_looks("child", include_inflight=True),
                "failed": {key: parent.get(key) for key in ("validation_verdicts", "mechanism", "incubator_barred",
                                                           "look_inflight", "gate_hold", "extension_hold")}}

    def test_constructor_initializes_real_import_objective_before_actors_and_keeps_history(self):
        from league.swarm import settings
        from league.swarm.architect import Architect
        from league.swarm.researcher import Researcher, running_span
        from league.swarm.tournament import Tournament

        before = self.history()
        controller = self.build()
        self.assertEqual(controller.store.get("train_objective"), "worst-train-year-v1@2020-01-02")
        self.assertIsInstance(controller.researcher, Researcher)
        self.assertIsInstance(controller.tournament, Tournament)
        self.assertIsInstance(controller.architect, Architect)
        self.assertEqual(running_span(controller.store), "2020-01-02")
        self.assertEqual(controller.researcher.pool.train_first, "2020-01-02")
        self.assertEqual(controller.expected_evaluation["required_split"], 16)
        self.assertEqual(controller.researcher.run_timeout(), 1500)
        self.assertEqual(settings.train_split(controller.researcher.settings, dt.date(2020, 1, 2)), 16)
        self.assertEqual(self.broker.calls, 0)
        self.assertEqual(self.model_requests, [])
        self.assertEqual(self.history(), before)
        controller.verify_state()  # Real SQL guards and scoped failure floors after migration.

    def test_actual_start_holds_when_host_split_cannot_cover_selected_span(self):
        controller = self.build()
        self.broker.evaluation["max_split"] = 8
        before = self.history()
        row = controller.step()
        self.assertEqual(row["status"], "held")
        self.assertEqual(self.model_requests, [])
        self.assertEqual(self.history(), before)

    def test_real_start_and_restart_preserve_migration_and_original_failure_history(self):
        import time
        controller = self.build()
        before = self.history()
        # Recent fixture timestamps leave the unchanged ordinary cadence intact.
        controller.store.put("architect_at", time.time())
        controller.store.put("tournament_at", time.time())
        row = controller.step()
        self.assertEqual(row["status"], "running")
        self.assertEqual(len(self.model_requests), 1)
        self.assertEqual(row["actions"][0]["family"], "child")
        self.assertTrue(row["actions"][0]["result"].get("hold"))
        self.assertEqual(self.history(), before)
        objective_events = controller.store._all("SELECT * FROM events WHERE kind='swarm.status'")
        self.assertTrue(controller.close())
        # A missing train_from setting keeps the completed stock objective.
        self.config_document = {"swarm": {"gym": {}}}
        replacement = self.build()
        self.assertEqual(replacement.store.get("train_objective"), "worst-train-year-v1@2020-01-02")
        self.assertEqual(replacement.expected_evaluation["train_first"], "2020-01-02")
        self.assertEqual(replacement.expected_evaluation["required_split"], 16)
        self.assertEqual(replacement.researcher.pool.train_first, "2020-01-02")
        self.assertEqual(replacement.researcher.settings["gym"]["train_from"], "2020-01-02")
        self.assertEqual(replacement.store._all("SELECT * FROM events WHERE kind='swarm.status'"), objective_events)
        self.assertEqual(self.history(), before)
        replacement.verify_state()
        self.assertTrue(replacement.close())
        self.config_document = {"swarm": {"gym": {"train_from": "unreadable-synthetic-setting"}}}
        unchanged_span = self.build()
        self.assertEqual(unchanged_span.expected_evaluation["train_first"], "2020-01-02")
        self.assertEqual(unchanged_span.researcher.pool.train_first, "2020-01-02")
        self.assertEqual(unchanged_span.researcher.settings["gym"]["train_from"], "2020-01-02")
        self.assertEqual(unchanged_span.store._all("SELECT * FROM events WHERE kind='swarm.status'"), objective_events)

    def test_missing_changed_or_unfinished_objective_holds_before_broker_or_actors(self):
        controller = self.build()
        objective = controller.store.get("train_objective")
        with mock.patch.object(controller.researcher.pool, "recover") as recover:
            for value in (None, "worst-train-year-v1", "unreadable@2020-01-02"):
                controller.store.put("train_objective", value)
                self.assertEqual(controller.step()["status"], "held")
            controller.store.put("train_objective", objective)
            controller.store.set_state("child", objective_migrated="worst-train-year-v1")
            self.assertEqual(controller.step()["status"], "held")
            recover.assert_not_called()
        self.assertEqual(self.broker.calls, 0)
        self.assertEqual(self.model_requests, [])

    def test_actual_architect_newborn_can_research_and_restart_without_a_migration_marker(self):
        import time
        from league.tests.test_swarm_cards import proposal

        controller = self.build()
        before = self.history()
        born = controller.architect.admit([proposal("a-newborn")])
        self.assertEqual(born, ["a-newborn"])
        self.assertIsNone(controller.store.family(born[0])["state"].get("objective_migrated"))
        controller.store.put("architect_at", time.time())
        controller.store.put("tournament_at", time.time())
        row = controller.step()
        self.assertEqual(row["status"], "running")
        self.assertEqual(row["actions"][0]["family"], born[0])
        self.assertTrue(row["actions"][0]["result"].get("hold"))
        self.assertEqual(len(self.model_requests), 1)
        self.assertEqual(self.history(), before)
        events = controller.store._all("SELECT * FROM events WHERE kind='swarm.status'")
        self.assertTrue(controller.close())
        replacement = self.build()
        self.assertEqual(replacement.store._all("SELECT * FROM events WHERE kind='swarm.status'"), events)
        self.assertIsNone(replacement.store.family(born[0])["state"].get("objective_migrated"))
        replacement.verify_state()

    def test_failed_or_unresolved_bootstrap_rolls_back_before_collaborators_exist(self):
        from league.swarm import researcher
        before = self.history()
        def contents():
            with closing(SwarmStore(self.root, readonly=True)) as store:
                return {table: store._all(f"SELECT * FROM {table} ORDER BY rowid")
                        for table in ("families", "events", "notebook", "kv")}
        unchanged = contents()
        original = researcher.migrate_objective
        def failed(store, **kwargs):
            runs = store.runs
            def broken_family(family, **options):
                if family == "child":
                    raise ValueError("Synthetic per-family migration failure")
                return runs(family, **options)
            with mock.patch.object(store, "runs", side_effect=broken_family):
                return original(store, **kwargs)
        for callback in (failed, lambda *a, **k: {"migrated": 0, "with_best": 0, "failed": 0}):
            with mock.patch.object(researcher, "migrate_objective", side_effect=callback), \
                    mock.patch("league.swarm.research_adapters.ResearchGymPool") as pool:
                with self.assertRaises(ResearchControllerError):
                    self.build()
                pool.assert_not_called()
            with closing(SwarmStore(self.root, readonly=True)) as store:
                self.assertIsNone(store.get("train_objective"))
            self.assertEqual(self.history(), before)
            self.assertEqual(contents(), unchanged)
        self.assertEqual(self.broker.calls, 0)
        self.assertEqual(self.model_requests, [])

    def test_allowed_import_span_floor_cannot_be_lowered_by_a_later_stock_migration(self):
        self.fixture.store.set_state("parent", span_trials=99)
        self.fixture.recapture_reviewed_fixture("synthetic-large-span-floor")
        self.root = self.fixture.base / "span-floor-working"
        self.fixture.import_state(fresh=self.root)
        controller = self.build()
        self.assertEqual(controller.store.family("parent")["state"]["span_trials"], 99)
        controller.verify_state()
        before = self.history()
        families = controller.store.families()
        events = controller.store._all("SELECT * FROM events ORDER BY seq")
        self.assertTrue(controller.close())
        self.config_document = {"swarm": {"gym": {"train_from": "2022-01-03"}}}
        with mock.patch("league.swarm.research_adapters.ResearchGymPool") as pool:
            with self.assertRaisesRegex(ResearchControllerError, "historical span trial baseline"):
                self.build()
            pool.assert_not_called()
        with closing(SwarmStore(self.root, readonly=True)) as store:
            self.assertEqual(store.get("train_objective"), "worst-train-year-v1@2020-01-02")
            self.assertEqual(store.families(), families)
            self.assertEqual(store._all("SELECT * FROM events ORDER BY seq"), events)
        self.assertEqual(self.history(), before)
        self.assertEqual(self.broker.calls, 0)
        self.assertEqual(self.model_requests, [])

    def test_unreadable_existing_objective_is_not_silently_reinterpreted(self):
        with closing(SwarmStore(self.root)) as store:
            store.put("train_objective", "different-objective@2020-01-02")
        with self.assertRaisesRegex(ResearchControllerError, "objective"):
            self.build()
        with closing(SwarmStore(self.root, readonly=True)) as store:
            self.assertEqual(store.get("train_objective"), "different-objective@2020-01-02")
        self.assertEqual(self.broker.calls, 0)

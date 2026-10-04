import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from league.swarm.research_controller import (ControllerConfig, ResearchController,
                                             ResearchControllerError, explicit_settings, main)
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

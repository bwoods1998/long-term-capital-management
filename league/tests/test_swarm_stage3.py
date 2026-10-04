"""Adversarial stage-3 checks: synthetic evidence, replay identity, accounting and concurrent writers."""

from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
import threading
import time
import unittest
from unittest.mock import patch

from league.swarm import settings as S
from league.swarm.architect import Architect
from league.swarm.gate import Gate, run_sha
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests import test_swarm_pool as P
from league.tests import test_swarm_researcher as M
from league.tests import test_swarm_rounds as R


class ValidationImageTests(R.RoundCase):
    def setup_image(self):
        self.image = "sbcp_gym_v0"
        self.pool.image = lambda kind: self.image
        self.answer = lambda job: {**R.strong(job), "gym_image": self.image, "gym_bundle": getattr(self, "bundle", None)}
        self.family("a")
        self.tournament = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        self.tournament.validate(self.store.families(alive=True))

    def test_current_best_is_revalidated_when_its_image_changes(self):
        self.setup_image()
        self.image = "sbcp_gym_v1"
        out = self.tournament.validate(self.store.families(alive=True))
        self.assertEqual(out["queued"], 1)
        self.assertEqual(self.store.family("a")["state"]["validation_image"], self.image)
        self.assertEqual(self.store.family("a")["trials"], 4)

    def test_an_engine_bundle_change_requires_validation_again_on_the_same_checkpoint(self):
        self.bundle = "engine-v1"
        self.pool.bundle = lambda: self.bundle
        self.setup_image()
        self.assertEqual(self.store.family("a")["state"]["validation_bundle"], "engine-v1")
        previous = self.answer(self.pool.jobs[-1])
        self.bundle = "engine-v2"
        self.replies = [{"text": '{"verdict":"pass"}'}] * 2
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertFalse([j for j in self.pool.jobs if j.window == "holdout"])
        self.assertEqual(self.tournament.validate(self.store.families(alive=True))["queued"], 1)
        self.assertEqual(self.store.family("a")["state"]["validation_bundle"], "engine-v2")
        self.assertIsNone(self.tournament.judge("a", 1, previous))

    def test_a_late_old_image_verdict_cannot_restore_gate_eligibility(self):
        self.setup_image()
        job = self.pool.jobs[0]
        old = {**R.strong(job), "gym_image": self.image}
        self.image = "sbcp_gym_v1"
        self.answer = lambda j: {**R.weak(j), "gym_image": self.image}
        self.tournament.validate(self.store.families(alive=True))
        self.assertIsNone(self.tournament.judge("a", 1, old))
        self.assertFalse(self.store.family("a")["state"]["gate_ready"])
        self.assertEqual(self.store.family("a")["trials"], 6, "the stale evaluation still counts")

    def test_the_gate_waits_for_validation_on_the_current_image(self):
        self.setup_image()
        self.image = "sbcp_gym_v1"
        self.replies = [{"text": '{"verdict":"pass"}'}] * 2
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertFalse([j for j in self.pool.jobs if j.window == "holdout"])
        self.assertEqual(self.sail.bodies, [], "no review spend on stale validation")

    def test_a_holdout_result_from_an_old_validation_image_cannot_promote(self):
        self.setup_image()
        self.pool.slow.add("a")
        self.replies = [{"text": '{"verdict":"pass"}'}] * 2
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        gate.run()
        self.image = "sbcp_gym_v1"
        job, late = self.pool.landing[0]
        late(R.strong(job))
        self.assertEqual(len(self.store.looks()), 1, "the opened holdout remains counted")
        self.assertEqual(self.store.family("a")["band"], "gym")

    def test_a_holdout_result_from_an_old_engine_bundle_cannot_promote(self):
        self.bundle = "engine-v1"
        self.pool.bundle = lambda: self.bundle
        self.setup_image()
        self.pool.slow.add("a")
        self.replies = [{"text": '{"verdict":"pass"}'}] * 2
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        gate.run()
        self.bundle = "engine-v2"
        job, late = self.pool.landing[0]
        late(R.strong(job))
        self.assertEqual(len(self.store.looks()), 1, "the opened holdout remains counted")
        self.assertEqual(self.store.family("a")["band"], "gym")

    def test_validation_keeps_typical_loss_by_version_for_the_live_banded_program(self):
        self.setup_image()
        self.store.add_version("a", "# second version", {}, author="test")
        self.store.update_family("a", best_version=2)
        def answer(job):
            row = {**R.strong(job), "gym_image": self.image}
            row["summary"]["median_max_loss_per_structure"] = 125.0
            return row
        self.answer = answer
        self.tournament.validate(self.store.families(alive=True))
        self.assertEqual(self.store.family("a")["state"]["typical_by_version"], {"1": 60.0, "2": 125.0})


class HoldoutIdentityTests(R.RoundCase):
    def setUp(self):
        super().setUp()
        self.images = {"gym": "sbcp_gym_v1", "gate": "sbcp_gate_v1"}
        self.pool.image = lambda kind: self.images[kind]
        self.pool.bundle = lambda: "engine-v1"
        self.answer = lambda job: {**R.strong(job), "gym_image": self.images["gym"], "gym_bundle": "engine-v1"}
        self.family("a")
        Tournament(self.store, self.pool, self.settings, clock=self.clock).validate(self.store.families(alive=True))
        self.pool.slow.add("a")
        self.replies = [{"text": '{"verdict":"pass"}'}] * 2
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.gate.run()
        self.job, self.late = self.pool.landing[0]
        self.result = {**R.strong(self.job), "gym_image": "sbcp_gate_v1", "gym_bundle": "engine-v1"}

    def cannot_promote(self):
        trials = self.store.family("a")["trials"]
        self.late(self.result)
        self.assertEqual(self.store.family("a")["band"], "gym")
        self.assertEqual(len(self.store.looks()), 1, "opening old or unidentified sealed data still uses a look")
        self.assertGreater(self.store.family("a")["trials"], trials, "its actual computation still counts")
        self.assertIsNone(self.store.family("a")["state"].get("look_inflight"))

    def test_a_gate_checkpoint_switch_cannot_promote_the_old_result(self):
        self.images["gate"] = "sbcp_gate_v2"
        self.cannot_promote()

    def test_a_disabled_gate_cannot_promote_a_late_result(self):
        self.images["gate"] = None
        self.cannot_promote()

    def test_missing_holdout_checkpoint_identity_cannot_promote(self):
        self.result.pop("gym_image")
        self.cannot_promote()

    def test_a_holdout_result_from_another_engine_cannot_promote(self):
        self.result["gym_bundle"] = "engine-v0"
        self.cannot_promote()

    def test_missing_holdout_engine_identity_cannot_promote(self):
        self.result.pop("gym_bundle")
        self.cannot_promote()

    def test_the_current_holdout_image_and_engine_do_promote(self):
        self.late(self.result)
        self.assertEqual(self.store.family("a")["band"], "candidate")
        self.assertEqual(len(self.store.looks()), 1)


class GateOwnershipTests(R.RoundCase):
    def ready(self):
        self.family("a")
        Tournament(self.store, self.pool, self.settings, clock=self.clock).validate(self.store.families(alive=True))
        self.replies = [{"text": '{"verdict":"pass"}'}] * 6
        return Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)

    def test_an_old_attempt_failure_cannot_clear_a_new_attempt_of_the_same_version(self):
        gate = self.ready()
        self.pool.slow.add("a")
        gate.run()
        old, late = self.pool.landing[0]
        self.clock.advance(2200)
        gate.run()
        newer = copy.deepcopy(self.store.family("a")["state"]["look_inflight"])
        old.late_fail("late failure from the superseded attempt")
        late({"status": "error", "summary": {}, "trials": 0})
        self.assertEqual(self.store.family("a")["state"]["look_inflight"], newer)
        self.assertEqual(self.store.get("look_tries:" + newer["sha"]), 1)

    def test_an_older_late_pass_cannot_replace_a_newer_program_already_on_real_money(self):
        gate = self.ready()
        self.pool.slow.add("a")
        gate.run()
        job, late = self.pool.landing[0]
        self.pool.slow.clear()
        self.store.add_version("a", "# newer synthetic program\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n",
                               {}, author="test")
        self.store.update_family("a", best_version=2)
        Tournament(self.store, self.pool, self.settings, clock=self.clock).validate(self.store.families(alive=True))
        self.clock.advance(2200)
        gate.run()
        self.store.set_band("a", "probe", reason="synthetic live promotion")
        late(R.strong(job))
        fam = self.store.family("a")
        self.assertEqual((fam["band"], fam["state"]["banded_version"]), ("probe", 2))
        self.assertEqual(len(self.store.looks()), 2, "the late look still counts")

    def test_pending_looks_reserve_the_last_lineage_ration(self):
        gate = self.ready()
        for i in range(2):
            self.store.add_look("a", i + 100, "old-" + str(i), passed=False, p_value=0.5, detail={})
        child = self.store.add_family({**R.SPEC, "id": "child"}, origin="fork", parent="a")
        self.store.add_version(child["id"], "# child synthetic program\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n",
                               {}, author="test")
        self.store.update_family(child["id"], best_version=1)
        Tournament(self.store, self.pool, self.settings, clock=self.clock).validate(self.store.families(alive=True))
        self.pool.slow.add("a")
        gate.run()
        self.assertEqual([j.family for j in self.pool.jobs if j.window == "holdout"], ["a"])
        self.assertEqual(self.store.refusals("child"), [], "a pending ration causes waiting, not a permanent refusal")

    def test_simultaneous_duplicate_results_count_one_look_and_one_trial(self):
        gate = self.ready()
        self.pool.slow.add("a")
        gate.run()
        job, late = self.pool.landing[0]
        answer = R.strong(job)
        rendezvous = threading.Barrier(2)
        errors = []
        from league.swarm import evidence
        calculate = evidence.holdout_line
        def slow_line(*a, **kw):
            try:
                rendezvous.wait(0.15)
            except threading.BrokenBarrierError:
                pass
            return calculate(*a, **kw)
        def finish():
            try:
                late(answer)
            except Exception as exc:
                errors.append(exc)
        trials = self.store.family("a")["trials"]
        with patch("league.swarm.gate.evidence.holdout_line", side_effect=slow_line):
            threads = [threading.Thread(target=finish) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(3)
            self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(self.store.looks()), 1)
        self.assertEqual(self.store.family("a")["trials"], trials + 1)


class SharedStateTests(R.RoundCase):
    def test_a_stale_band_change_cannot_overwrite_the_houses_newer_band(self):
        self.family("a")
        self.store.set_band("a", "candidate", reason="test")
        other = SwarmStore(self.root)
        self.addCleanup(other.close)
        original = self.store.family
        injected = False
        def race(fid):
            nonlocal injected
            fam = original(fid)
            if not injected:
                injected = True
                other.set_band(fid, "probe", reason="synthetic House promotion")
            return fam
        with patch.object(self.store, "family", side_effect=race):
            self.assertIsNone(self.store.set_band("a", "gym", reason="stale result"))
        self.assertEqual(self.store.family("a")["band"], "probe")

    def test_replacing_a_forward_record_is_atomic_when_an_import_row_is_invalid(self):
        self.family("a")
        previous = [{"id": "old", "day": "2026-09-28", "pnl": -5, "max_loss": 60}]
        self.store.add_forward("a", "nightly", previous, version=1)
        with self.assertRaises(ValueError):
            self.store.replace_forward("a", "nightly", [{**previous[0], "id": "new", "pnl": "invalid"}], version=1)
        self.assertEqual([r["trade_id"] for r in self.store.forward("a")], ["old"])

    def test_house_state_written_during_a_swarm_update_is_preserved(self):
        self.family("a")
        other = SwarmStore(self.root)
        self.addCleanup(other.close)
        original = self.store._one
        injected = False
        def race(sql, params=()):
            nonlocal injected
            row = original(sql, params)
            if "FROM families WHERE id=?" in sql and not injected:
                injected = True
                other.set_state("a", live_position="must survive")
            return row
        with patch.object(self.store, "_one", side_effect=race):
            self.store.set_state("a", gate_ready=True)
        self.assertEqual(self.store.family("a")["state"], {"live_position": "must survive", "gate_ready": True})

    def test_compare_and_set_rechecks_after_another_connection_changes_the_expected_value(self):
        self.family("a")
        self.store.set_state("a", validation_version=1)
        other = SwarmStore(self.root)
        self.addCleanup(other.close)
        original = self.store._one
        injected = False
        def race(sql, params=()):
            nonlocal injected
            row = original(sql, params)
            if "FROM families WHERE id=?" in sql and not injected:
                injected = True
                other.set_state("a", validation_version=2, gate_ready=False)
            return row
        with patch.object(self.store, "_one", side_effect=race):
            accepted = self.store.compare_and_set_state("a", {"validation_version": 1}, gate_ready=True)
        self.assertFalse(accepted)
        self.assertEqual(self.store.family("a")["state"], {"validation_version": 2, "gate_ready": False})


class LineageTests(R.RoundCase):
    def test_a_child_shares_later_looks_on_its_parents_other_root(self):
        self.family("a")
        self.store.add_family({**R.SPEC, "id": "child", "roots": ["QQQ"]}, origin="fork", parent="a")
        self.clock.advance(10)
        for i in range(3):
            self.store.add_look("a", i, f"later-{i}", passed=False, p_value=0.5, detail={})
        self.assertEqual(self.store.lineage_looks("child"), 3)

    def test_reused_program_code_joins_look_and_trial_counts_even_with_other_parameters(self):
        from league.swarm.sitefeed import site_inputs
        self.family("a")
        self.family("b")
        self.family("unrelated", mechanism="A distinct economic mechanism using a different synthetic program.")
        self.store.bump("a", trials=7)
        self.store.bump("b", trials=11)
        self.store.add_look("a", 1, "spent-look", passed=False, p_value=0.5, detail={})
        self.store.add_version("b", self.store.version("a", 1)["code"], {"synthetic": 2}, author="test")
        self.assertEqual(self.store.lineage_looks("b"), 1)
        self.assertEqual(self.store.lineage_trials("a"), 18)
        self.assertEqual(self.store.lineage_trials("b"), 18)
        self.assertEqual(self.store.lineage_looks("unrelated"), 0)
        rows = {f["id"]: f for f in site_inputs(self.root)["agents"]}
        self.assertEqual(rows["b"]["record"]["trials"], 18)

    def test_existing_program_reuse_is_migrated_without_editing_look_records(self):
        self.family("a")
        self.family("b")
        self.store.add_version("b", self.store.version("a", 1)["code"], {}, author="test")
        self.store.add_look("a", 1, "spent-look", passed=False, p_value=0.5, detail={})
        looks = self.store.looks()
        self.store._exec("DELETE FROM lineage_links")
        self.store.put("program_lineages_indexed", False)
        upgraded = SwarmStore(self.root)
        self.addCleanup(upgraded.close)
        self.assertEqual(upgraded.lineage_looks("b"), 1)
        self.assertEqual(upgraded.looks(), looks)

    def test_explicit_resurrection_or_retired_id_reuse_never_resets_the_ration(self):
        self.family("a")
        self.store.add_look("a", 1, "spent-look", passed=False, p_value=0.5, detail={})
        self.store.retire("a", "synthetic retirement")
        arch = Architect(self.store, self.router, self.settings, clock=self.clock)
        row = {**R.SPEC, "slug": "a", "mechanism": "Completely reworded description of the retired trading hypothesis."}
        [resurrected] = arch.admit([row])
        [declared] = arch.admit([{**row, "slug": "declared", "parent": "a", "mechanism": "A revised explanation explicitly linked to its prior hypothesis."}])
        self.assertEqual(self.store.lineage_looks(resurrected), 1)
        self.assertEqual(self.store.lineage_looks(declared), 1)


class AccountingTests(unittest.TestCase):
    setUp = M.Holds.setUp
    ask = M.Holds.ask
    cost = M.Holds.cost

    def test_reaper_then_retry_never_books_the_same_settled_response_twice(self):
        from ltcm.provider import ProviderError
        with self.assertRaises(ProviderError):
            self.ask()
        self.done = True
        self.prov.reconcile_stale(now=time.time() + 3600)
        self.router.settle_holds()
        for _ in range(3):
            self.ask()
        self.assertAlmostEqual(self.store.spent(["sail_model"]), self.cost(), places=6)

    def test_a_released_request_can_reserve_again_when_retried(self):
        from ltcm.provider import ProviderError
        self.fail_code = "provider_transport_timeout"
        with self.assertRaises(ProviderError):
            self.ask()
        self.prov.reconcile_stale(now=time.time() + 3600)
        self.router.settle_holds()
        self.fail_code = None
        with self.assertRaises(ProviderError):
            self.ask()
        self.assertGreater(self.store.spent(["sail_model"]), 0)
        self.done = True
        self.ask()
        self.assertAlmostEqual(self.store.spent(["sail_model"]), self.cost(), places=6)


class PoolInventoryTests(P.PoolCase):
    def test_a_young_stray_counts_toward_capacity_before_reconciliation_may_end_it(self):
        pool = self.pool(start_boxes=1, max_boxes=1)
        self.sail.extra.append({"sailbox_id": "sb_abc00001", "name": pool.name_prefix("gym") + str(int(self.clock())) + "-9",
                                "created_at": self.clock(), "status": "running"})
        pool.submit(P.job("a"))
        out = pool.manage()
        self.assertEqual(out["started"], 0)
        self.assertEqual(self.sail.terminated, [])
        self.clock.advance(601)
        self.assertEqual(pool.manage()["started"], 1)

    def test_an_unreadable_inventory_permits_no_fork(self):
        pool = self.pool(start_boxes=1, max_boxes=1)
        self.sail.list_boxes = lambda **kw: (_ for _ in ()).throw(RuntimeError("unreadable"))
        pool.submit(P.job("a"))
        self.assertEqual(pool.manage()["started"], 0)

    def test_stopped_cleanup_keeps_unknown_submissions_and_terminates_only_owned_boxes(self):
        from league.swarm.pool import cleanup_stopped
        pool = self.pool()
        pending = pool.name_prefix("gym") + str(int(self.clock())) + "-99"
        self.store.put("forking", {pending: self.clock()})
        self.sail.names["sb_abc00002"] = pending
        self.sail.names["sb_abc00003"] = "ltcm-swarm-othertoken-gym-1-1"
        late = pool.name_prefix("gate") + str(int(self.clock())) + "-100"
        self.store.put("forking", {pending: self.clock(), late: self.clock()})
        out = cleanup_stopped(self.store.root, self.sail)
        self.assertEqual(self.sail.terminated, ["sb_abc00002"])
        self.assertEqual(out["confirmed"], 1)
        self.assertEqual(self.store.get("forking"), {late: self.clock()})
        self.sail.names["sb_abc00004"] = late
        cleanup_stopped(self.store.root, self.sail)
        self.assertEqual(self.sail.terminated, ["sb_abc00002", "sb_abc00004"])
        self.assertEqual(self.store.get("forking"), {})

    def test_stopped_cleanup_refuses_to_touch_a_running_swarm(self):
        import fcntl
        from league.swarm.pool import cleanup_stopped
        pool = self.pool()
        self.sail.names["sb_abc00002"] = pool.name_prefix("gym") + "1-1"
        with (self.store.root / "swarm.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertTrue(cleanup_stopped(self.store.root, self.sail)["active"])
        self.assertEqual(self.sail.terminated, [])


class RefillTests(R.RoundCase):
    def test_refill_one_empty_seat_does_not_expand_past_the_start(self):
        self.family("a")
        self.settings["population"]["start"] = 2
        arch = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertEqual(arch.want(), 1)

    def test_repeated_identical_proposals_cannot_create_duplicate_families_in_one_pass(self):
        row = R.ArchitectTests.PROPOSAL["families"][0]
        arch = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertEqual(len(arch.admit([row, row, row])), 1)

    def test_verifier_uses_the_population_floor_start_and_ceiling(self):
        from pathlib import Path
        spec = importlib.util.spec_from_file_location("stage3_verify", Path(__file__).resolve().parents[2] / "scripts/verify_swarm.py")
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        # The lines in effect (swarm.json over the release's policy.json): pinned here, whatever the policy holds.
        # With the floor counting every living family (`population.floor_researching` false, as before F1), fewer alive
        # than the floor is a FAIL; counting research (F1, the default) it is a WAIT while the architect bears (dead slots
        # left, and a family was born within `--birth-hours`), and a FAIL once none was: the population collapsed and
        # nothing refills it.
        lines = {"start": 48, "ceiling": 96, "floor": 16}
        for i in range(97):
            self.store.add_family({**R.SPEC, "id": f"f{i}"}, origin="seed")
        born = self.clock()  # the families' births, on the store's clock: the verifier reads the copy at its own time

        def population(*args):
            stream = io.StringIO()
            # The configured lines alone: the budget's tighten-only ceiling is league/tests/test_ops_budget.py's.
            with contextlib.redirect_stdout(stream), patch.object(S, "budget_overlay", lambda out, root: out):
                verify.main(["--root", str(self.root), *args])
            return json.loads(stream.getvalue())["checks"]["population"]

        for researching, count, hours, expected in (
                (False, 44, 1, "WAIT"), (False, 48, 1, "PASS"), (False, 16, 1, "WAIT"), (False, 15, 1, "FAIL"),
                (False, 97, 1, "FAIL"), (True, 15, 1, "WAIT"), (True, 0, 1, "WAIT"), (True, 48, 1, "PASS"), (True, 97, 1, "FAIL"),
                (True, 15, 5.9, "WAIT"), (True, 15, 6.1, "FAIL"), (True, 0, 72, "FAIL"), (True, 16, 72, "WAIT"),
                (True, 48, 72, "PASS")):
            (Path(self.root) / "swarm.json").write_text(json.dumps({"population": {**lines, "floor_researching": researching}}))
            self.store._exec("UPDATE families SET retired_at='retired', band='retired'")
            for i in range(count):
                self.store.update_family(f"f{i}", retired_at=None, band="gym")
            check = population("--now", str(born + hours * 3600))
            self.assertEqual(check["result"], expected, (researching, count, hours))
            self.assertEqual("why" in check, researching and count < 16 and hours > 6, (researching, count, hours))
        # A collapse says why, and names the architect's last passes: the reader sees what stopped the births.
        self.store._exec("UPDATE families SET retired_at='retired', band='retired'")
        self.store.event("swarm.architect", None, {"born": [], "skipped": "no_cell", "why": "no cell"})
        self.store.event("swarm.architect", None, {"born": ["f1", "f2"], "proposed": 6})
        check = population("--now", str(born + 72 * 3600))
        self.assertEqual(check["why"], "0 alive, under the floor of 16, and no family was born in the last 6 hours: the "
                                       "architect is not refilling it")
        self.assertEqual([(x["born"], x["skipped"]) for x in check["architect_passes"]], [(2, None), (0, "no_cell")])
        self.assertEqual(check["hours_since_a_birth_or_the_start"], 72.0)
        self.assertEqual(population("--now", str(born + 72 * 3600), "--birth-hours", "100")["result"], "WAIT")
        # A swarm that has just started is given the same time to bear (its heartbeat says when it started).
        (Path(self.root) / "swarm.heartbeat").write_text(json.dumps({"at": born + 71 * 3600, "pid": 1, "started_at": born + 70 * 3600}))
        self.assertEqual(population("--now", str(born + 72 * 3600))["result"], "WAIT")
        (Path(self.root) / "swarm.heartbeat").unlink()
        # No key at all (the box's swarm.json holds only the owner's switches): the default counts research.
        (Path(self.root) / "swarm.json").write_text(json.dumps({"population": lines}))
        self.assertEqual(population("--now", str(born + 3600))["result"], "WAIT")


class ReadyForwardTests(R.RoundCase):
    def target(self, day="2026-09-28", checkpoint="sbcp_ready1"):
        self.settings["gym"]["gate_checkpoint"] = checkpoint
        self.settings["forward"]["ready"] = {"schema": 1, "day": day, "gate_checkpoint": checkpoint,
                                                "roots": ["SPY"], "ready_at": "2026-09-29T06:00:00Z"}
        return {"day": day, "checkpoint": checkpoint}

    def banded(self, fid="a"):
        from league.tests.evaluator_fakes import band_proof

        self.family(fid)
        self.store.set_band(fid, "candidate", reason="synthetic test")
        self.store.set_state(fid, banded_version=1, banded_evaluator=band_proof(self.store.version(fid, 1)))

    def good(self, job):
        target = self.gate.forward_target()
        return {**R.strong(job), "gym_image": target["checkpoint"], "gym_bundle": target.get("bundle"),
                "daily": [[target["day"], 0, 10000]], "trades": []}

    def test_an_engine_bundle_change_requires_a_fresh_forward_replay(self):
        self.banded()
        self.target()
        self.bundle = "engine-v1"
        self.pool.bundle = lambda: self.bundle
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.answer = self.good
        self.gate.forward()
        self.assertFalse(self.gate.forward_due())
        self.bundle = "engine-v2"
        self.assertTrue(self.gate.forward_due())
        self.gate.forward()
        self.assertEqual(self.store.family("a")["state"]["forward_replay"]["target"]["bundle"], self.bundle)

    def test_ready_checkpoint_after_a_clock_only_run_replays_immediately_and_retries_failure(self):
        self.banded()
        self.store.put("forward_day", "2026-09-29")
        self.target()
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.assertTrue(self.gate.forward_due())
        self.answer = lambda job: {"status": "no_data", "trials": 0}
        self.gate.forward()
        self.assertEqual(self.store.get("forward_day"), "2026-09-29", "failed replay cannot claim completion")
        self.assertIsNone(self.store.family("a")["state"].get("forward_replay"))
        self.clock.advance(3600)
        self.assertTrue(self.gate.forward_due())
        self.answer = self.good
        self.gate.forward()
        self.assertFalse(self.gate.forward_due())
        self.assertEqual(self.store.get("forward_day"), "2026-09-28")

    def test_partial_failure_retries_only_the_missing_family_and_new_checkpoint_invalidates_completion(self):
        self.banded("a")
        self.banded("b")
        self.target()
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.answer = self.good
        self.pool.fail.add("b")
        self.gate.forward()
        self.clock.advance(3600)
        self.pool.fail.clear()
        self.gate.forward()
        self.assertEqual([j.family for j in self.pool.jobs], ["a", "b", "b"])
        self.target(checkpoint="sbcp_ready2")
        self.assertTrue(self.gate.forward_due())

    def test_wrong_checkpoint_or_missing_ready_day_preserves_the_existing_forward_record(self):
        self.banded()
        self.target()
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.store.add_forward("a", "nightly", [{"id": "previous", "day": "2026-09-28", "pnl": -5, "max_loss": 60}], version=1)
        self.answer = lambda job: {**self.good(job), "gym_image": "sbcp_old"}
        self.gate.forward()
        self.assertEqual(len(self.store.forward("a")), 1)
        self.answer = lambda job: {**self.good(job), "daily": []}
        self.gate.forward()
        self.assertEqual(len(self.store.forward("a")), 1)
        self.assertIsNone(self.store.family("a")["state"].get("forward_replay"))

    def test_a_late_old_checkpoint_result_cannot_replace_a_newer_forward_record(self):
        self.banded()
        self.target()
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.pool.slow.add("a")
        self.gate.forward()
        job, late = self.pool.landing[0]
        old = self.good(job)
        self.target(day="2026-09-29", checkpoint="sbcp_ready2")
        self.store.add_forward("a", "nightly", [{"id": "newer", "day": "2026-09-29", "pnl": -5, "max_loss": 60}], version=1)
        late(old)
        self.assertEqual(self.store.forward("a")[0]["trade_id"], "newer")

    def test_settings_accept_a_ready_manifest_only_while_the_operator_enabled_the_gate(self):
        self.target()
        # THE CHAIN'S RULE (Oct 1, 2026; league/tests/test_swarm_gate_chain.py): the chain must extend the gate swarm.json
        # names (its base) and hold every root of the swarm.
        (self.root / "gym-forward.json").write_text(json.dumps({**self.settings["forward"]["ready"], "base_checkpoint": "sbcp_old",
                                                                "holdout_roots": list(S.DEFAULTS["gym"]["roots"])}))
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"gate_checkpoint": "sbcp_old"}}))
        loaded = S.load(self.root, config={})
        self.assertEqual(loaded["gym"]["gate_checkpoint"], "sbcp_ready1")
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"gate_checkpoint": None}}))
        self.assertIsNone(S.load(self.root, config={})["gym"]["gate_checkpoint"])


if __name__ == "__main__":
    unittest.main()

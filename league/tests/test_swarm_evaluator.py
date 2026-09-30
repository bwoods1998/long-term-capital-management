"""An engine upgrade never reuses qualification, erases search costs, or strands a stale band."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from league.gym import ENGINE_VERSION
from league.swarm import bands, evidence
from league.swarm.evaluator import KEY, adopt, execution_fingerprint, identity, row_matches
from league.swarm.gate import Gate, run_sha
from league.swarm.researcher import migrate_objective, version_drift
from league.swarm.tournament import Tournament
from league.tests.evaluator_fakes import band_proof, seed_current_run
from league.tests.swarm_fakes import result
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase
from league.tests.test_swarm_search import yearly
from league.tests.test_swarm_store import StoreCase, SPEC

CODE = "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"


class Adoption(StoreCase):
    def setUp(self):
        super().setUp()
        self.root = self.store.root

    def family(self, fid="a"):
        self.store.add_family({**SPEC, "id": fid}, origin="test")
        return self.store.add_version(fid, CODE, {}, author="test")

    def test_upgrade_clears_selection_once_without_refunding_trials_or_holdout_looks(self):
        version = self.family()
        run = result("old")
        run.update(gym_image="old-image", gym_bundle="gym-engine-3-old", trials=41)
        row = self.store.add_run("a", 1, run, window="train", stress=1, purpose="train")
        sha = run_sha(version)
        self.store.add_look("a", 1, sha, passed=False, p_value=0.4, detail={"synthetic": True})
        self.store.refuse("a", 1, "audit", "a historical refusal")
        self.store.update_family("a", best_train=9, best_version=1, best_validation=4, validated_version=1)
        self.store.set_state("a", best_train_run=row["run_id"], best_train_version=1, robustness={"1": {"mid": {"pnl": 8}}},
                             robust_failed=[2], drift_failed={"3": "weak"}, validation_version=1,
                             validation_bundle="gym-engine-3-old", review={"verdict": "pass"}, gate_ready=True,
                             gated_sha=sha, banded_version=1, look_inflight={"sha": "pending-look", "n": 2})
        totals, looks = self.store.totals(), self.store.looks()
        reserved_looks = self.store.lineage_looks("a", include_inflight=True)
        current = identity("new-image", bands._bundle())
        self.assertEqual(adopt(self.store, current)["families"], 1)
        fam = self.store.family("a")
        self.assertIsNone(fam["best_train"])
        self.assertIsNone(fam["best_version"])
        self.assertIsNone(fam["state"]["validation_version"])
        self.assertEqual(fam["state"]["robustness"], {})
        self.assertEqual(fam["state"]["span_trials"], 41)
        self.assertEqual(fam["state"]["previous_evaluator_selection"]["best_train"], 9)
        self.assertEqual(self.store.totals(), totals)
        self.assertEqual(self.store.looks(), looks)
        self.assertEqual(self.store.lineage_looks("a", include_inflight=True), reserved_looks)
        self.assertTrue(self.store.looked(sha), "identical code+parameters never get another sealed look")
        self.assertEqual(len(self.store.refusals("a")), 1)
        self.assertEqual(self.store.family("a")["trials"], 41)
        self.store.update_family("a", best_train=2)
        self.assertFalse(adopt(self.store, current)["adopted"])
        self.assertEqual(self.store.family("a")["best_train"], 2, "a restart preserves newly earned evidence")

    def test_old_contract_refusal_is_archived_not_a_permanent_veto_on_fresh_review(self):
        version = self.family()
        sha = run_sha(version)
        self.store.refuse("a", 1, "audit", "old contract claimed cross-run module state leakage")
        self.store.set_state("a", gated_sha=sha, gate_outcome={"sha": sha, "result": "refused"},
                             review={"sha": sha, "verdict": "fail", "contract_sha": "old-contract"})
        adopt(self.store, identity("image", bands._bundle()))
        state = self.store.family("a")["state"]
        self.assertIsNone(state["gated_sha"])
        self.assertIsNone(state["gate_outcome"])
        self.assertIsNone(state["review"])
        self.assertEqual(state["previous_evaluator_selection"]["gate_outcome"]["result"], "refused")
        self.assertEqual(len(self.store.refusals("a")), 1)
        self.assertFalse(self.store.looked(sha), "no sealed data was opened by the old refusal")
        self.assertFalse(state["gate_ready"], "fresh Train, validation and both reviews are still owed")

    def test_stale_money_bands_return_to_research_and_keep_forward_and_banded_history(self):
        for band in bands.LIVE_BANDS:
            self.family(band)
            self.store.set_band(band, band, reason="historical qualification")
            self.store.set_state(band, banded_version=1, banded_evaluator={"engine": "gym-engine-3"},
                                 forward={"pnl_usd": 123}, typical_by_version={"1": 50})
            self.store.add_forward(band, "real", [{"id": "old", "pnl": 3, "max_loss": 50}], version=1)
        adopt(self.store, identity("image", bands._bundle()))
        for band in bands.LIVE_BANDS:
            fam = self.store.family(band)
            self.assertEqual(fam["band"], "gym", "the researcher can now revise/rerun the family")
            self.assertEqual(fam["state"]["banded_version"], 1)
            self.assertEqual(fam["state"]["forward"], {"pnl_usd": 123})
            self.assertEqual(len(self.store.forward(band)), 1)
        self.assertEqual(bands.read(self.root), [])

    def test_docs_only_bundle_adoption_preserves_a_current_executable_band_and_sizing(self):
        version = self.family()
        self.store.set_band("a", "probe", reason="qualified")
        self.store.set_state("a", banded_version=1, banded_evaluator=band_proof(version), typical_by_version={"1": 50})
        adopt(self.store, identity("image", ENGINE_VERSION + "-new-doc-bundle"))
        self.assertEqual(self.store.family("a")["band"], "probe")
        self.assertEqual(bands.read(self.root)[0]["typical_max_loss_usd"], 50)

    def test_execution_fingerprint_changes_for_runtime_fill_or_live_code_without_a_version_bump(self):
        from league.gym.driver import LEAGUE_FILES

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for name in (*LEAGUE_FILES, "league/gym/runtime.py", "league/gym/fills.py", "league/live/shadow.py"):
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("VALUE = 1\n")
            original = execution_fingerprint(repo)
            (repo / "league/gym/PROGRAM.md").write_text("new documentation")
            execution_fingerprint.cache_clear()
            self.assertEqual(execution_fingerprint(repo), original)
            for name in ("gym/runtime.py", "gym/fills.py", "live/shadow.py"):
                path = repo / "league" / name
                path.write_text("VALUE = 2\n")
                execution_fingerprint.cache_clear()
                self.assertNotEqual(execution_fingerprint(repo), original)
                path.write_text("VALUE = 1\n")
        execution_fingerprint.cache_clear()

    def test_same_engine_string_with_old_execution_hash_never_admits_or_confirms_money(self):
        from league.live.families import SwarmFamilies

        version = self.family()
        proof = band_proof(version)
        self.store.set_state("a", banded_version=1, banded_evaluator=proof)
        self.store.set_band("a", "probe", reason="qualified")
        [entry] = bands.read(self.root)
        self.store.set_state("a", banded_evaluator={**proof, "execution_sha256": "old-runtime-and-fills"})
        self.assertEqual(bands.read(self.root), [])
        families = SwarmFamilies(self.root)
        self.addCleanup(lambda: families._store.close() if families._store else None)
        self.assertFalse(families.confirm_band(entry, "sized", "stale proof", forward=[]))
        with families.admit_open(entry, real=True) as allowed:
            self.assertFalse(allowed)

    def test_row_identity_survives_result_pruning_and_old_results_cannot_match(self):
        self.family()
        current = identity("image", bands._bundle())
        self.store.put(KEY, current)
        run = result("new")
        run.update(gym_image=current["image"], gym_bundle=current["bundle"])
        row = self.store.add_run("a", 1, run, window="train", stress=1, purpose="train")
        (self.root / row["path"]).unlink()
        self.assertTrue(row_matches(self.store, self.store.run(row["run_id"])))
        old = result("old")
        old.update(gym_image="image", gym_bundle="gym-engine-3-old")
        old_row = self.store.add_run("a", 1, old, window="train", stress=1, purpose="train")
        self.assertFalse(row_matches(self.store, self.store.run(old_row["run_id"])))

    def test_colliding_worker_ids_keep_separate_results_and_metrics_for_each_evaluator(self):
        self.family()
        old = result("collision", pnl=600)
        old.update(gym_image="image", gym_bundle=ENGINE_VERSION + "-old-source")
        older = self.store.add_run("a", 1, old, window="train", stress=1, purpose="train", key="old-evaluation")
        current = {**old, "gym_bundle": bands._bundle(), "summary": {**old["summary"], "pnl": -600}, "status": "disqualified"}
        newer = self.store.add_run("a", 1, current, window="train", stress=1, purpose="train", key="new-evaluation")
        self.assertNotEqual(older["run_id"], newer["run_id"])
        self.assertEqual(self.store.run(older["run_id"])["summary"]["pnl"], 600)
        self.assertEqual(self.store.run(newer["run_id"])["summary"]["pnl"], -600)
        self.assertEqual(self.store.run(newer["run_id"])["status"], "disqualified")
        self.assertEqual(self.store.run_result(newer["run_id"])["gym_bundle"], current["gym_bundle"])
        repeated = self.store.add_run("a", 1, current, window="train", stress=1, purpose="train", key="new-evaluation")
        self.assertEqual(repeated["run_id"], newer["run_id"])
        self.assertEqual(self.store.run(older["run_id"])["trials"], 1)
        self.assertEqual(self.store.run(newer["run_id"])["trials"], 2)
        self.assertEqual(self.store.family("a")["trials"], 3, "every actual evaluation still counts")

    def test_new_practice_requires_current_actual_evidence_not_cached_labels_or_profit(self):
        self.family()
        self.store.set_state("a", best_train_version=1)
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": "synthetic-image"}}))
        self.assertEqual(bands.observe(self.root), [])
        stale = result("old")
        stale.update(gym_image="synthetic-image", gym_bundle="gym-engine-3-old")
        stale["summary"]["train_eligible"] = True
        self.store.add_run("a", 1, stale, window="train", stress=1, purpose="train")
        self.assertEqual(bands.observe(self.root), [])
        seed_current_run(self.store, "a", 1, window="train")
        self.assertEqual(bands.observe(self.root)[0]["tier"], "train")
        self.store.set_state("a", validation_version=1, validation_line={"passed": False})
        self.assertEqual(bands.observe(self.root), [], "a current Train result cannot pose as a Validation result")
        val = result("current-zero-trade", window="validation", trades=0, pnl=0)
        val.update(gym_image="synthetic-image", gym_bundle=bands._bundle())
        self.store.add_run("a", 1, val, window="validation", stress=1, purpose="validation")
        self.assertEqual(bands.observe(self.root)[0]["tier"], "validated", "practice evidence need not be a profitable strategy")


class LateResearch(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.current = identity("current-image", bands._bundle())
        self.pool.image = lambda kind="gym": self.current["image"]
        self.pool.bundle = lambda: self.current["bundle"]
        self.version = self.store.add_version(self.fam["id"], self.code, {}, author="test")
        self.settings["tournament"]["drift_screen"] = False
        self.store.put(KEY, self.current)

    def answer(self, bundle=None, **kw):
        row = yearly(**kw)
        row.update(gym_image=self.current["image"], gym_bundle=bundle or self.current["bundle"])
        return row

    def test_late_train_is_counted_but_never_selected_or_submitted_and_current_run_can_be(self):
        researcher = self.researcher()
        fid = self.fam["id"]
        for bundle, expected in (("gym-engine-3-old", False), (self.current["bundle"], True)):
            answer = self.answer(bundle)
            score = evidence.train_score(answer)
            answer["summary"].update(train_eligible=True, train_score=score["score"])
            row = self.store.add_run(fid, 1, answer, window="train", stress=1, purpose="train")
            fam = self.store.family(fid)
            view = {}
            value = researcher._scored(fam, 1, row["run_id"], score, view, {}, code=self.code, params={})
            self.assertEqual(value is not None, expected)
            self.assertEqual(view["train_score"]["eligible"], expected)
            self.assertEqual(researcher.eligible_run(fam, self.store.run(row["run_id"]))[0], expected)
        self.assertEqual(self.store.family(fid)["trials"], 2)
        self.assertEqual(self.store.family(fid)["state"]["best_train_run"], row["run_id"])

    def test_late_stress_drift_and_failure_never_demote_or_refill_current_views(self):
        researcher = self.researcher()
        fid = self.fam["id"]
        self.store.update_family(fid, best_train=2, best_version=1)
        for label, stress in (("stress_1.5", 1.5), ("drift", 1.0)):
            researcher.robust_landed(fid, 1, label, stress, self.answer("gym-engine-3-old", pnl=-100))
        researcher.robust_landed(fid, 1, "stress_1.5", None,
                                 {"status": "failed", "reason": "old job failed", "gym_image": "current-image", "gym_bundle": "old"})
        fam = self.store.family(fid)
        self.assertEqual(fam["trials"], 2)
        self.assertEqual(fam["best_train"], 2)
        self.assertFalse(fam["state"].get("robustness"))
        self.assertIsNone(version_drift(self.store, fam, 1))
        researcher.robust_landed(fid, 1, "drift", 1, self.answer())
        self.assertIsNotNone(version_drift(self.store, self.store.family(fid), 1))

    def test_objective_rescoring_cannot_restore_old_engine_best(self):
        fid = self.fam["id"]
        self.store.add_run(fid, 1, self.answer("gym-engine-3-old"), window="train", stress=1, purpose="train")
        migrate_objective(self.store, settings=self.settings)
        self.assertIsNone(self.store.family(fid)["best_train"])


class LateRounds(RoundCase):
    def test_only_current_holdout_results_create_executable_band_proof(self):
        current_bundle = bands._bundle()
        self.pool.bundle = lambda: current_bundle
        self.pool.image = lambda kind="gym": "gate-image" if kind == "gate" else "train-image"
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        for fid, bundle in (("old", "gym-engine-3-old"), ("current", current_bundle)):
            self.family(fid)
            version = self.store.version(fid, 1)
            self.store.set_state(fid, validation_version=1)
            answer = result(fid, window="holdout")
            answer.update(gym_image="gate-image", gym_bundle=bundle)
            self.assertTrue(gate.finish(fid, version, run_sha(version), answer, validation_sharpe=0.2,
                                        validation_image="train-image", validation_bundle=current_bundle))
            fam = self.store.family(fid)
            self.assertEqual(fam["band"], "candidate" if fid == "current" else "gym")
            self.assertEqual(bands.current_banded_evaluator(fam["state"], run_sha(version)), fid == "current")
        self.assertEqual(len(self.store.looks()), 2, "the old result used sealed evidence and still consumes its look")

    def test_a_stale_submission_cannot_buy_validation_even_if_its_best_label_survives(self):
        self.family("a")
        current = identity("image", bands._bundle())
        self.store.put(KEY, current)
        old = result("old")
        old.update(gym_image="image", gym_bundle="gym-engine-3-old")
        row = self.store.add_run("a", 1, old, window="train", stress=1, purpose="train")
        self.store.set_state("a", submitted_run=row["run_id"])
        tournament = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        self.assertEqual(tournament.validate(self.store.families(alive=True))["queued"], 0)
        self.assertEqual(self.pool.jobs, [])

    def test_old_forward_result_is_a_trial_but_cannot_replace_current_record(self):
        self.family("a")
        version = self.store.version("a", 1)
        self.store.set_state("a", banded_version=1, banded_evaluator=band_proof(version))
        self.store.set_band("a", "candidate", reason="qualified")
        self.pool.bundle = lambda: bands._bundle()
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.store.add_forward("a", "nightly", [{"id": "retained", "pnl": 5, "max_loss": 50}], version=1)
        old = result("old-forward", window="forward")
        old["gym_bundle"] = "gym-engine-3-old"
        self.assertIsNone(gate.record_forward("a", 1, old))
        self.assertEqual(self.store.family("a")["trials"], 1)
        self.assertEqual(len(self.store.forward("a")), 1)
        self.assertEqual(self.store.forward("a")[0]["trade_id"], "retained")

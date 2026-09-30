"""An engine upgrade never reuses qualification, erases search costs, or strands a stale band."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from league.gym import ENGINE_VERSION
from league.swarm import bands, evidence
from league.swarm.evaluator import KEY, adopt, execution_fingerprint, gym_changed, identity, row_matches
from league.swarm.gate import Gate, run_sha
from league.swarm.researcher import (extension_held, idle_dead, idle_evaluations, judge_extension, mark_extension,
                                     migrate_objective, version_drift)
from league.swarm.tournament import Tournament
from league.tests.evaluator_fakes import band_proof, seed_current_run
from league.tests.swarm_fakes import result
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase, strong, weak
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
        self.assertEqual(fam["state"]["evaluator_trials"], 41)
        self.assertNotIn("span_trials", fam["state"], "Train's span did not change")
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


class AdoptionAndTheExtensionHold(RoundCase):
    """The review of release A: an extension hold earned on one Gym never exempts its family on the next, and a
    validation of the held version below the checks ends the hold. The review of PR #453: an adoption that changes only
    the execution fingerprint (league/live) keeps the hold's records, so a hold the operator cleared stays cleared."""

    def setUp(self):
        super().setUp()
        self.settings["researcher"]["dormant_cycles"] = 12
        self.tournament = Tournament(self.store, self.pool, self.settings, clock=self.clock)

    @staticmethod
    def line(met, total=8):
        return {"passed": met == total, "checks": {f"c{i}": i < met for i in range(total)}}

    def dormant(self, fid="a", cycles=99):
        self.store.set_state(fid, dormant_cycles=cycles)
        return idle_dead(self.store.family(fid), self.settings)

    def test_the_reviewed_scenario_a_7_of_8_hold_does_not_survive_adoption(self):
        """Hold at 7/8; adopt; the same version re-validates at 2/8 under the new evaluator (the tournament's writes)."""
        self.family("a")
        self.store.set_state("a", validation_version=1, validation_line=self.line(7))
        self.assertTrue(mark_extension(self.store, "a", 1, self.line(7), self.settings))
        hold = self.store.family("a")["state"]["extension_hold"]
        self.assertTrue(extension_held(self.store.family("a")))
        self.assertTrue(adopt(self.store, identity("new-image", bands._bundle()))["adopted"])
        state = self.store.family("a")["state"]
        self.assertIsNone(state["extension_hold"])
        self.assertEqual(state["extension_versions"], [])
        self.assertEqual(state["previous_evaluator_selection"]["extension_hold"], hold, "archived, not erased")
        self.assertEqual(state["previous_evaluator_selection"]["extension_versions"], [1])
        self.store.set_state("a", validation_version=1, validation_line=self.line(2))
        self.assertFalse(mark_extension(self.store, "a", 1, self.line(2), self.settings))
        self.assertFalse(extension_held(self.store.family("a")), "the old hold does not come back with its version")
        self.assertIn("made no new Gym evaluation in its last 99 cycles", self.dormant())
        self.store.set_state("a", validation_line=self.line(7))
        self.assertTrue(mark_extension(self.store, "a", 1, self.line(7), self.settings),
                        "the current evaluator can hold a version the old one held")
        self.assertTrue(extension_held(self.store.family("a")))
        self.assertIsNone(self.dormant())
        self.assertFalse(adopt(self.store, identity("new-image", bands._bundle()))["adopted"])
        self.assertTrue(extension_held(self.store.family("a")), "a restart keeps a hold earned under the current evaluator")

    def test_through_the_tournament_the_current_evaluator_must_earn_the_hold_again(self):
        self.family("a")
        self.tournament.validate(self.store.families(alive=True))
        job = self.pool.jobs[0]
        self.assertTrue(extension_held(self.store.family("a")))
        adopt(self.store, identity("new-image", bands._bundle()))
        self.store.update_family("a", best_version=1)  # the researcher earns version 1 back as its best
        self.assertIsNotNone(self.tournament.judge("a", 1, weak(job), record=False))
        self.assertFalse(extension_held(self.store.family("a")))
        self.assertIn("made no new Gym evaluation in its last 99 cycles", self.dormant())
        out = self.tournament.judge("a", 1, strong(job), record=False)
        self.assertTrue(out["extension_hold"])
        self.assertTrue(extension_held(self.store.family("a")))

    def test_a_validation_of_the_held_version_below_the_checks_ends_its_hold(self):
        self.family("a")
        self.tournament.validate(self.store.families(alive=True))
        job = self.pool.jobs[0]
        self.assertTrue(extension_held(self.store.family("a")))
        out = self.tournament.judge("a", 1, weak(job), record=False)
        self.assertNotIn("extension_hold", out)
        self.assertTrue(out["extension_lapsed"], "the verdict row, which the round's event carries, says it lapsed")
        state = self.store.family("a")["state"]
        self.assertIsNone(state["extension_hold"])
        self.assertEqual(state["extension_versions"], [])
        self.assertEqual((state["extension_lapsed"]["version"], state["extension_lapsed"]["checks"]), (1, "8/8"))
        self.assertLess(int(state["extension_lapsed"]["checks_then"].split("/")[0]), 6)
        self.assertIn("made no new Gym evaluation in its last 99 cycles", self.dormant())
        self.assertNotIn("extension_lapsed", self.tournament.judge("a", 1, weak(job), record=False), "nothing left to lapse")
        out = self.tournament.judge("a", 1, strong(job), record=False)
        self.assertTrue(out["extension_hold"], "the hold stands for the version's latest validation: it meets them again")
        self.assertTrue(extension_held(self.store.family("a")))
        self.assertEqual(self.store.family("a")["state"]["extension_versions"], [1])

    def test_the_switch_and_back_holds_the_version_its_latest_validation_judged(self):
        """The review of PR #453: v1 held at 7/8, v2 validated, v1 re-judged below the checks, then at 7/8 again."""
        self.family("a")
        self.store.set_state("a", validation_version=1)
        self.assertTrue(mark_extension(self.store, "a", 1, self.line(7), self.settings))
        self.store.set_state("a", validation_version=2)
        self.assertFalse(mark_extension(self.store, "a", 2, self.line(3), self.settings))
        self.store.set_state("a", validation_version=1)
        self.assertEqual(judge_extension(self.store, "a", 1, self.line(5), self.settings), "lapsed")
        self.assertFalse(extension_held(self.store.family("a")))
        self.assertEqual(judge_extension(self.store, "a", 1, self.line(7), self.settings), "held")
        self.assertTrue(extension_held(self.store.family("a")))

    def test_a_validation_of_another_version_leaves_the_hold_on_its_own_version(self):
        self.family("a")
        self.store.set_state("a", validation_version=1)
        self.assertTrue(mark_extension(self.store, "a", 1, self.line(7), self.settings))
        self.store.add_version("a", CODE + "# 2\n", {}, author="test")
        self.store.set_state("a", validation_version=2)
        self.assertFalse(mark_extension(self.store, "a", 2, self.line(3), self.settings))
        self.assertFalse(extension_held(self.store.family("a")), "its latest validation judged another version")
        self.assertEqual(self.store.family("a")["state"]["extension_hold"]["version"], 1)
        self.assertNotIn("extension_lapsed", self.store.family("a")["state"])
        self.settings["researcher"]["extension_hold_checks"] = 0
        self.store.set_state("a", validation_version=1)
        self.assertIsNone(judge_extension(self.store, "a", 1, self.line(2), self.settings))
        state = self.store.family("a")["state"]
        self.assertEqual((state["extension_hold"]["version"], state["extension_versions"]), (1, [1]),
                         "with the rule off a validation writes nothing")
        self.assertNotIn("extension_lapsed", state)

    def operator_cleared(self, fid="a"):
        """Version 1 held at 7/8, then cleared the way `scripts/extension_hold.py --clear` clears it."""
        self.family(fid)
        self.store.set_state(fid, validation_version=1, validation_line=self.line(7))
        self.assertTrue(mark_extension(self.store, fid, 1, self.line(7), self.settings))
        hold = self.store.family(fid)["state"]["extension_hold"]
        self.store.set_state(fid, extension_hold=None, extension_cleared={**hold, "cleared_at": "x"})
        self.assertFalse(mark_extension(self.store, fid, 1, self.line(7), self.settings), "not again on the same Gym")
        return hold

    def revalidated(self, fid, met):
        self.store.set_state(fid, validation_version=1, validation_line=self.line(met))
        return judge_extension(self.store, fid, 1, self.line(met), self.settings)

    def test_an_adoption_of_league_live_alone_keeps_an_operator_clear_and_a_standing_hold(self):
        """The review of PR #453: a live-only adoption moves the execution fingerprint, not the Gym's image or bundle, so
        the recorded validation is re-judged as it was and the extension verdict the operator acted on still stands."""
        before = identity("gym-image", bands._bundle())
        adopt(self.store, before)
        self.operator_cleared("a")
        self.family("b")
        self.store.set_state("b", validation_version=1, validation_line=self.line(7))
        self.assertTrue(mark_extension(self.store, "b", 1, self.line(7), self.settings))
        live_only = {**before, "execution": "a league/live change"}
        self.assertFalse(gym_changed(before, live_only))
        self.assertTrue(adopt(self.store, live_only)["adopted"])
        a, b = (self.store.family(fid)["state"] for fid in ("a", "b"))
        self.assertEqual((a["extension_versions"], a["extension_cleared"]["version"]), ([1], 1))
        self.assertEqual((b["extension_hold"]["version"], b["extension_versions"]), (1, [1]))
        self.assertNotIn("extension_versions", a["previous_evaluator_selection"])
        self.assertIsNone(a["validation_version"], "the selection is still owed again")
        self.assertIsNone(self.revalidated("a", 7))
        self.assertFalse(extension_held(self.store.family("a")), "cleared stays cleared")
        self.assertIn("made no new Gym evaluation in its last 99 cycles", self.dormant("a"))
        self.assertFalse(extension_held(self.store.family("b")), "inert until its version is validated again")
        self.assertIsNone(self.revalidated("b", 7))
        self.assertTrue(extension_held(self.store.family("b")), "a standing hold stands")
        self.assertIsNone(self.dormant("b"))
        self.assertEqual(self.revalidated("b", 2), "lapsed", "and still lapses below the checks")

    def test_an_adoption_of_a_new_gym_archives_every_hold_record_and_re_arms_a_cleared_version(self):
        before = identity("gym-image", bands._bundle())
        adopt(self.store, before)
        hold = self.operator_cleared("a")
        self.family("b")
        self.store.set_state("b", validation_version=1)
        self.assertTrue(mark_extension(self.store, "b", 1, self.line(7), self.settings))
        self.assertEqual(judge_extension(self.store, "b", 1, self.line(3), self.settings), "lapsed")
        new_gym = identity("new-image", bands._bundle())
        self.assertTrue(gym_changed(before, new_gym))
        adopt(self.store, new_gym)
        a, b = (self.store.family(fid)["state"] for fid in ("a", "b"))
        for state in (a, b):
            self.assertEqual((state["extension_hold"], state["extension_versions"], state["extension_cleared"],
                              state["extension_lapsed"]), (None, [], None, None), "no old record beside a new hold")
        self.assertEqual(a["previous_evaluator_selection"]["extension_cleared"], {**hold, "cleared_at": "x"})
        self.assertEqual(a["previous_evaluator_selection"]["extension_versions"], [1])
        self.assertEqual(b["previous_evaluator_selection"]["extension_lapsed"]["checks_then"], "3/8")
        self.assertEqual(self.revalidated("a", 7), "held", "its extension verdict is owed again under the new Gym")
        self.assertTrue(extension_held(self.store.family("a")))

    def test_what_changes_the_gym(self):
        before = identity("gym-image", "gym-bundle")
        self.assertTrue(gym_changed(None, before), "the first adoption: no Gym before it is known")
        self.assertTrue(gym_changed({"execution": before["execution"]}, before))
        self.assertTrue(gym_changed(before, {**before, "image": "another"}))
        self.assertTrue(gym_changed(before, {**before, "bundle": "another"}))
        self.assertFalse(gym_changed(before, {**before, "execution": "another"}))
        self.assertFalse(gym_changed(before, dict(before)))


class AdoptionAndTheIdleRule(RoundCase):
    """The review of release A: after an adoption the idle rule's clause says the evaluator changed, not Train's span."""

    def test_idle_retirements_after_adoption_say_the_evaluator_changed(self):
        self.settings["tournament"].update(retire_revisions=10 ** 6, retire_evaluations=10 ** 6)
        self.settings["population"].update(start=2, floor=0)
        for fid in ("a", "b"):
            self.family(fid)
            self.store.update_family(fid, trials=400, since_val_trials=400)
        adopt(self.store, identity("new-image", bands._bundle()))
        self.assertEqual([idle_evaluations(f) for f in self.store.families(alive=True)], [0, 0])
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [])
        self.store.update_family("a", trials=550, since_val_trials=550)
        self.store.update_family("b", trials=549, since_val_trials=549)
        [row] = Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True))
        self.assertEqual(row["family"], "a")
        self.assertIn("150 Gym evaluations since the evaluator changed", row["why"])
        self.assertNotIn("span", row["why"])

    def test_the_clause_names_the_latest_restart(self):
        def since(state, validations=1):
            fam = {"band": "gym", "trials": 700, "since_val_trials": 700, "validations": validations, "best_train": None,
                   "state": state}
            return idle_dead(fam, self.settings)

        cases = [
            ({"span_trials": 400, "evaluator_trials": 400}, "300 Gym evaluations since the evaluator changed"),
            ({"span_trials": 500, "evaluator_trials": 400}, "200 Gym evaluations since Train's span changed"),
            ({"span_trials": 400}, "300 Gym evaluations since Train's span changed"),
            ({"evaluator_trials": 400, "validated_trials": 450}, "250 Gym evaluations since its last validation"),
            ({"evaluator_trials": 400, "validated_trials": 400}, "300 Gym evaluations since the evaluator changed"),
            ({"evaluator_trials": True}, "700 Gym evaluations since its last validation"),
        ]
        for state, words in cases:
            with self.subTest(state=state):
                self.assertIn(words, since(state))
        self.assertIn("700 Gym evaluations since its birth", since({}, validations=0))


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

"""An engine upgrade never reuses qualification, erases search costs, or strands a stale band. A league/live-only release
keeps the Gym's selection (the practice league keeps its programs), moves no money (no real-order route carries across
it: the gate's passing review is the live route's fact, owed again), gives no program a second reading (a review that
did not pass is kept as it is), and gives back, once, what the release before this rule archived."""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from league.gym import ENGINE_VERSION
from league.swarm import bands, evidence
from league.swarm.evaluator import (ARCHIVE_KEY, BEST_COLUMNS, GYM_KEYS, HOLD_KEYS, KEY, LIVE_KEYS, SELECTION_KEYS, adopt,
                                    adoption_words, execution_fingerprint, gym_changed, identity, on_gym_in_force, restorable,
                                    review_stands, row_matches)
from league.swarm.gate import Gate, run_sha
from league.swarm.researcher import (DRIFT_FAILED_KEPT, awaiting_validation, extension_held, guard_words, idle_dead,
                                     idle_evaluations, judge_extension, mark_extension, migrate_objective, retire_guard,
                                     robust_at_stress, version_drift)
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.evaluator_fakes import adopt_as_v3a, band_proof, passed_look, reviewed, seed_current_run
from league.tests.swarm_fakes import Clock, result
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RetiredTuition, RoundCase, review_failure, strong, weak
from league.tests.test_swarm_search import QueueingPool, yearly
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

    def test_old_contract_refusal_is_archived_and_its_row_still_bars_the_program_from_a_second_reading(self):
        """THE PROGRAM BAR ON THE LOOK ROUTE (release F1, Oct 3, 2026). An adoption of a new Gym still archives and clears
        what the gate holds of the program (its mark, its outcome, its review). Before F1 that made the refusal no
        permanent veto: validated again, the program got a fresh review and a look. Now its refusal row, kept for good,
        bars the program on the look route: never made gate-ready again, never read again, in any family."""
        from league.swarm import incubator

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
        self.assertFalse(state["gate_ready"], "fresh Train and validation are still owed")
        self.assertEqual(incubator.look_route_bar(self.store, "a", 1, sha), "the gate refused it in a@1 (the audit)")
        self.assertTrue(Tournament(self.store, None, {}).gate_spent("a", 1, state),
                        "validated again on the new Gym, it is not made gate-ready: no second reading, no look")
        # The same code and parameters in another family (a revive, a twin): its program's row bars it there too.
        self.store.add_family({**SPEC, "id": "twin"}, origin="test")
        self.store.add_version("twin", CODE, {}, author="test")
        self.assertEqual(incubator.look_route_bar(self.store, "twin", 1, sha), "the gate refused it in a@1 (the audit)")

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
        self.assertEqual(bands.read(self.root), [], "a band and a current proof, and no look on record: no row (release F1)")
        passed_look(self.store, "a", version)
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
        passed_look(self.store, "a", version)
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
        self.store.update_family(fid, validated_version=1)  # as the tournament's verdict writes it (`_verdict`)
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
        the recorded validation is re-judged as it was and the extension verdict the operator acted on still stands.
        Since Oct 3, 2026 the selection stands with it (PR #453 had it owed again): a standing hold applies at once."""
        before = identity("gym-image", bands._bundle())
        adopt(self.store, before)
        self.operator_cleared("a")
        self.family("b")
        # Validated, as the tournament's verdict writes it: its best is kept now, and a best not yet validated would be
        # exempt from the dormancy clause by itself (`awaiting_validation`), whatever the hold did.
        self.store.update_family("b", validated_version=1)
        self.store.set_state("b", validation_version=1, validation_line=self.line(7))
        self.assertTrue(mark_extension(self.store, "b", 1, self.line(7), self.settings))
        live_only = {**before, "execution": "a league/live change"}
        self.assertFalse(gym_changed(before, live_only))
        self.assertTrue(adopt(self.store, live_only)["adopted"])
        a, b = (self.store.family(fid)["state"] for fid in ("a", "b"))
        self.assertEqual((a["extension_versions"], a["extension_cleared"]["version"]), ([1], 1))
        self.assertEqual((b["extension_hold"]["version"], b["extension_versions"]), (1, [1]))
        self.assertNotIn(ARCHIVE_KEY, a, "a league/live-only adoption archives no research selection")
        self.assertEqual(a["validation_version"], 1, "the selection stands: its Gym rows are all still current")
        self.assertIsNone(self.revalidated("a", 7))
        self.assertFalse(extension_held(self.store.family("a")), "cleared stays cleared")
        self.assertIn("made no new Gym evaluation in its last 99 cycles", self.dormant("a"))
        self.assertTrue(extension_held(self.store.family("b")), "its validation stands, and so does its hold")
        self.assertIsNone(self.revalidated("b", 7))
        self.assertTrue(extension_held(self.store.family("b")), "a standing hold stands")
        self.assertFalse(awaiting_validation(self.store.family("b")), "its best is validated: only the hold can exempt it")
        self.assertIsNone(self.dormant("b"))
        self.assertEqual(self.revalidated("b", 2), "lapsed", "and still lapses below the checks")
        self.assertIn("made no new Gym evaluation in its last 99 cycles", self.dormant("b"),
                      "so it was the hold that exempted it")

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

    def test_a_verdict_is_on_the_gym_in_force_under_any_execution_fingerprint(self):
        current = identity("gym-image", "gym-bundle")
        self.assertTrue(on_gym_in_force(dict(current), current))
        self.assertTrue(on_gym_in_force({**current, "execution": "an earlier league/live"}, current))
        self.assertFalse(on_gym_in_force({**current, "image": "another"}, current))
        self.assertFalse(on_gym_in_force({**current, "bundle": "another"}, current))
        self.assertFalse(on_gym_in_force(None, current), "judged before any identity was adopted")
        self.assertTrue(on_gym_in_force(None, None), "a store that never adopted one: every verdict is its only Gym's")
        self.assertFalse(on_gym_in_force(current, None))


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


#: What a league/live-only adoption keeps of the selection, name by name (`evaluator.GYM_KEYS`), beside the family's bests
#: (`BEST_COLUMNS`) and the extension hold's records (`HOLD_KEYS`): a change here is a change of the rule. The gate's
#: `review` is not among them (Oct 3, 2026): a passing one is what a tuition row is granted on, so it is a live route's
#: fact. (One that did not pass is kept as it is, by its own rule: `evaluator.review_stands`.)
KEPT = ("best_train_version", "best_train_run", "train_candidates", "submitted_run", "submitted_note", "robustness",
        "robust_failed", "robust_why", "drift_failed", "validation_version", "validation_image", "validation_bundle",
        "validation_line", "validation_view", "validation_numbers", "typical_max_loss_usd", "typical_by_version",
        "gate_ready", "gated_sha", "gate_outcome")
#: What it clears, for every family (`evaluator.LIVE_KEYS`): the incubator's marks and reviews, and the gate's review
#: when it passed.
GONE = ("train_passed", "incubator_reviews", "review")
#: What an adoption that clears leaves under a key (None where not named).
CLEARED = {"train_candidates": [], "robustness": {}, "robust_failed": [], "robust_why": {}, "drift_failed": {},
           "train_passed": {}, "incubator_reviews": {}, "gate_ready": False, "extension_versions": []}
#: The keys of every `evaluator_adopted` event (`at` is its row's time, added by `adoptions`).
EVENT_KEYS = {"action", "from", "to", "gym_changed", "kept", "restored", "_previous_selection", "incubator_barred", "at"}


def adoptions(store, fid=None):
    """The `evaluator_adopted` events' payloads (one family's, or all), oldest first, each with its event's time as `at`."""
    return [{**e["payload"], "at": e["at"]} for e in store.events_after(0, limit=5000)
            if e["payload"].get("action") == "evaluator_adopted" and (fid is None or e["family"] == fid)]


class TheTwoKindsOfAdoption(StoreCase):
    """THE RULE (Oct 3, 2026), key by key. A new Gym image or bundle archives and clears everything, as before. A
    league/live-only adoption keeps the bests, the Gym's selection, the hold's records and the counts, and clears the live
    route's facts alone: the incubator's marks and reviews, and the gate's review when it passed. A review that did not
    pass is kept as it is."""

    BEFORE = {"image": "gym-image", "bundle": "gym-bundle", "execution": "release A's league/live"}
    #: Something under every key an adoption could touch; the gate's review is one that passed, with its audit.
    HELD = {**{key: {"1": key} for key in (*SELECTION_KEYS, *HOLD_KEYS)}, "review": reviewed("a" * 64)}

    def holding(self, store, previous=BEFORE, fid="a"):
        """A family that holds something under every key an adoption could touch, on a store adopted under `previous`."""
        store.add_family({**SPEC, "id": fid}, origin="test")
        store.add_version(fid, CODE, {}, author="test")
        store.set_state(fid, **self.HELD, dormant_cycles=6, evaluator_trials=11)
        store.update_family(fid, best_train=1.5, best_version=1, best_validation=0.2, validated_version=1, stall=3,
                            since_val_revisions=4, since_val_trials=5, trials=41)
        if previous is not None:
            store.put(KEY, previous)
        return store.family(fid)

    def test_a_league_live_only_adoption_keeps_the_gyms_selection_and_clears_the_live_routes_facts_alone(self):
        self.assertEqual((GYM_KEYS, LIVE_KEYS), (KEPT, GONE))
        self.assertNotIn("review", GYM_KEYS, "the gate's review is never kept, and never given back (`restorable` reads these)")
        self.assertEqual(sorted((*GYM_KEYS, *LIVE_KEYS)), sorted(SELECTION_KEYS), "every selection key is one or the other")
        before = self.holding(self.store)
        new = {**self.BEFORE, "execution": "release B's league/live"}
        out = adopt(self.store, new)
        fam = self.store.family("a")
        state = fam["state"]
        for key in (*KEPT, *HOLD_KEYS):
            with self.subTest(kept=key):
                self.assertEqual(state[key], {"1": key})
        self.assertFalse(review_stands(self.HELD["review"]), "the review it held had passed")
        for key in GONE:
            with self.subTest(cleared=key):
                self.assertEqual(state[key], CLEARED.get(key), "as an adoption of a new Gym leaves it")
        for column in (*BEST_COLUMNS, "stall", "since_val_revisions", "since_val_trials", "trials", "band"):
            with self.subTest(column=column):
                self.assertEqual(fam[column], before[column])
        self.assertEqual((state["dormant_cycles"], state["evaluator_trials"]), (6, 11), "the dormancy and idle counts go on")
        self.assertNotIn(ARCHIVE_KEY, state, "no research selection is archived: none is cleared")
        self.assertEqual(state["evaluator"], new)
        self.assertEqual(self.store.get(KEY), new)
        self.assertEqual(self.store.notebook("a"), [], "no note says anything is owed again")
        self.assertEqual({k: v for k, v in out.items() if k not in ("previous", "current")},
                         {"adopted": True, "families": 1, "gym_changed": False, "kept": [*BEST_COLUMNS, *KEPT, *HOLD_KEYS],
                          "bests": 1, "restored": {}, "returned": []})
        [event] = adoptions(self.store)
        self.assertEqual(set(event), EVENT_KEYS)
        self.assertEqual((event["from"], event["to"], event["gym_changed"], event["restored"], event["incubator_barred"]),
                         (self.BEFORE, new, False, None, []))
        self.assertEqual(event["kept"], sorted((*BEST_COLUMNS, *KEPT, *HOLD_KEYS)), "the names of what the family still holds")
        self.assertEqual(event["_previous_selection"], {key: self.HELD[key] for key in GONE}, "what it cleared, and no more")
        self.assertNotIn("review", event["kept"])
        self.assertFalse(adopt(self.store, new)["adopted"], "a restart under the same identity adopts nothing")

    #: The gate's review records that are NOT a pass, each as a writer or a damaged store can leave it: a failed review,
    #: a failed audit (the gate's own shape: the review's verdict "fail", stage "audit"), a review the gate revoked, a
    #: verdict that is neither word or is missing, an audit that is there but is no readable passed audit, and a record
    #: that is no mapping at all.
    SHA = "b" * 64
    NOT_A_PASS = (
        {"sha": SHA, "verdict": "fail", "reasons": ["unsafe"]},
        {"sha": SHA, "verdict": "fail", "stage": "audit", "audit": {"verdict": "fail"}, "reasons": ["unsafe"]},
        {"sha": SHA, "verdict": "fail", "stage": "gate"},
        {"sha": SHA, "verdict": "unclear"},
        {"sha": SHA},
        {"sha": SHA, "verdict": "pass", "audit": {"verdict": "fail"}},
        {"sha": SHA, "verdict": "pass", "audit": {"verdict": "unclear"}},
        {"sha": SHA, "verdict": "pass", "audit": "passed"},
        {"sha": SHA, "verdict": "pass", "audit": None},
        "a review that is no mapping", ["pass"], 7,
    )
    #: Those that are a pass (its audit passed, or still owed), and no review at all.
    A_PASS = ({"sha": SHA, "verdict": "pass"}, {"sha": SHA, "verdict": "pass", "audit": {"verdict": "pass"}},
              reviewed(SHA), {"verdict": "pass"})
    NO_REVIEW = (None, {}, "", [], False)

    def test_a_review_stands_exactly_when_it_is_there_and_is_not_a_pass(self):
        """`review_stands`, record by record, and held to the incubator's own reading of the gate's review: a review is
        kept exactly when it bars its program (`gate_review_bar`), or cannot be read at all (`family_bar`)."""
        from league.swarm import incubator

        for review in self.NOT_A_PASS:
            with self.subTest(stands=review):
                self.assertIs(review_stands(review), True)
                barred = incubator.gate_review_bar(review, self.SHA) or incubator.family_bar({"review": review})
                self.assertIsNotNone(barred, "and the incubator's reader bars on it")
        for review in (*self.A_PASS, *self.NO_REVIEW):
            with self.subTest(goes=review):
                self.assertIs(review_stands(review), False)
                self.assertIsNone(incubator.gate_review_bar(review, self.SHA), "no verdict against its program")
        for review in self.A_PASS[:3]:
            self.assertIsNone(incubator.family_bar({"review": review}))

    def test_a_league_live_only_adoption_keeps_a_review_that_did_not_pass_as_it_is(self):
        """THE RULING OF OCT 3, 2026: clearing a review that failed its program would let the gate read that program
        again. Each record that is not a pass is left under `review` exactly as it was, named in the event's `kept` and
        not in what the event says was cleared; a pass (audited or not) is cleared and archived there. A new Gym still
        clears every review, as before."""
        new = {**self.BEFORE, "execution": "release B's league/live"}
        cases = [(review, True) for review in self.NOT_A_PASS] + [(review, False) for review in self.A_PASS]
        for review, stands in cases:
            with self.subTest(review=review, stands=stands), tempfile.TemporaryDirectory() as tmp:
                store = SwarmStore(Path(tmp), clock=Clock())
                try:
                    self.holding(store)
                    store.set_state("a", review=review)
                    adopt(store, new)
                    state = store.family("a")["state"]
                    [event] = adoptions(store)
                    self.assertEqual(state["review"], review if stands else None)
                    self.assertEqual("review" in event["kept"], stands)
                    self.assertEqual(event["_previous_selection"],
                                     {key: (review if key == "review" else self.HELD[key]) for key in GONE
                                      if not (stands and key == "review")}, "the event archives what was cleared, no more")
                    self.assertEqual((state["train_passed"], state["incubator_reviews"]), ({}, {}),
                                     "the incubator's marks and reviews go either way")
                    for key in KEPT:
                        self.assertEqual(state[key], {"1": key}, key)
                    adopt(store, {**new, "image": "another image"})
                    self.assertIsNone(store.family("a")["state"]["review"], "a new Gym reads every program anew")
                finally:
                    store.close()

    def test_an_adoption_of_a_new_gym_archives_and_clears_everything_as_before(self):
        archive = {**self.HELD, "best_train": 1.5, "best_version": 1, "best_validation": 0.2, "validated_version": 1}
        for name, previous, new in (("a new image", self.BEFORE, {**self.BEFORE, "image": "another image"}),
                                    ("a new bundle", self.BEFORE, {**self.BEFORE, "bundle": "another bundle"}),
                                    ("both, and the fingerprint", self.BEFORE, {"image": "i", "bundle": "b", "execution": "x"}),
                                    ("no identity before", None, self.BEFORE)):
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                store = SwarmStore(Path(tmp), clock=Clock())
                try:
                    self.holding(store, previous)
                    out = adopt(store, new)
                    fam = store.family("a")
                    state = fam["state"]
                    for key in (*SELECTION_KEYS, *HOLD_KEYS):
                        self.assertEqual(state[key], CLEARED.get(key), key)
                    self.assertEqual([fam[column] for column in BEST_COLUMNS], [None] * 4)
                    self.assertEqual((fam["stall"], fam["since_val_revisions"], fam["since_val_trials"], fam["trials"],
                                      state["dormant_cycles"], state["evaluator_trials"]), (0, 0, 0, 41, 0, 41),
                                     "the counts restart; no trial is refunded")
                    self.assertEqual(state[ARCHIVE_KEY], archive)
                    self.assertEqual(state["evaluator"], new)
                    [note] = store.notebook("a")
                    self.assertIn("The evaluator changed.", note["text"])
                    [event] = adoptions(store)
                    self.assertEqual(set(event), EVENT_KEYS)
                    self.assertEqual((event["gym_changed"], event["kept"], event["restored"], event["_previous_selection"]),
                                     (True, [], None, archive))
                    self.assertEqual({k: v for k, v in out.items() if k not in ("previous", "current")},
                                     {"adopted": True, "families": 1, "gym_changed": True, "kept": [], "bests": 0,
                                      "restored": {}, "returned": []})
                finally:
                    store.close()

    def test_the_swarms_start_line_says_which_kind_it_was(self):
        self.assertEqual(adoption_words({"adopted": True, "families": 13, "gym_changed": True, "kept": [], "bests": 0,
                                         "restored": {}, "returned": ["p"]}),
                         "evaluator adopted: 13 families owe fresh evidence")
        self.assertEqual(adoption_words({"adopted": True, "families": 13}), "evaluator adopted: 13 families owe fresh evidence",
                         "a result that does not say is read as the kind that owes")
        live = {"adopted": True, "families": 13, "gym_changed": False, "bests": 9, "restored": {}, "returned": []}
        self.assertEqual(adoption_words(live), "evaluator adopted (league/live only, the Gym did not change): 13 families keep "
                                               "their research selection, 9 with a best")
        at = "2026-10-03T08:50:34Z"
        self.assertEqual(adoption_words({**live, "restored": {"a": at, "b": at}, "returned": ["p"]}),
                         "evaluator adopted (league/live only, the Gym did not change): 13 families keep their research "
                         f"selection, 9 with a best; 2 given back the selection the league/live-only adoption of {at} "
                         "archived; 1 stale money band(s) returned to the Gym")
        self.holding(self.store)
        out = adopt(self.store, {**self.BEFORE, "execution": "release B's league/live"})
        self.assertEqual(adoption_words(out), "evaluator adopted (league/live only, the Gym did not change): 1 families keep "
                                              "their research selection, 1 with a best")


class IdentifiedPool(QueueingPool):
    """The researcher's queueing pool that names the Gym it runs (`Researcher._gym_identity`)."""

    def __init__(self, image, bundle):
        super().__init__()
        self._image, self._bundle = image, bundle

    def image(self, kind="gym"):
        return self._image

    def bundle(self):
        return self._bundle


class LeagueLiveAdoption(ResearcherCase):
    """RELEASE B'S STALL (Oct 1, 2026) AND V3-A's (Oct 3). Each changed league/live alone: the execution fingerprint
    moved, the Gym image and bundle did not. Their adoptions still cleared every family's Train best, robustness views
    and validation, although every row they rested on stayed current (`matches`), so robustness, validation and
    Train-tier practice had nothing to start from. A league/live-only adoption now keeps the research selection; a new
    Gym image or bundle still clears it."""

    IMAGE = "synthetic-image"

    def setUp(self):
        super().setUp()
        self.bundle = bands._bundle()
        self.pool = IdentifiedPool(self.IMAGE, self.bundle)
        self.settings["tournament"]["drift_screen"] = False
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": self.IMAGE}}))
        self.release_a = {"image": self.IMAGE, "bundle": self.bundle, "execution": "release A's league/live"}
        self.store.put(KEY, self.release_a)
        self.fid = self.fam["id"]
        self.store.add_version(self.fid, self.code, {}, author="test")

    def answer(self, *, stress=1.0, pnl=500.0):
        row = yearly(stress=stress, pnl=pnl)
        row.update(gym_image=self.IMAGE, gym_bundle=self.bundle)
        return row

    def best_with_robustness(self, researcher):
        """Version 1's eligible Train run makes it the best, which queues its robustness runs; both land with a profit."""
        answer = self.answer()
        score = evidence.train_score(answer)
        answer["summary"].update(train_eligible=True, train_score=score["score"])
        row = self.store.add_run(self.fid, 1, answer, window="train", stress=1, purpose="train")
        researcher._scored(self.store.family(self.fid), 1, row["run_id"], score, {}, {}, code=self.code, params={})
        self.assertEqual(sorted(job.stress for job in self.pool.queued), [0.0, 1.5], "the best's robustness runs")
        for job in list(self.pool.queued):
            self.pool.land(job, self.answer(stress=job.stress, pnl=300.0))
        self.pool.queued.clear()
        return score["score"]

    def test_a_league_live_only_adoption_keeps_the_best_its_robustness_and_its_practice_row(self):
        researcher = self.researcher()
        score = self.best_with_robustness(researcher)
        self.store.set_state(self.fid, drift_failed={"7": "a weaker version's mark"}, robust_failed=[7],
                             train_passed={"1": {"evaluator": self.release_a}})
        before = self.store.family(self.fid)
        self.assertTrue(robust_at_stress(before["state"], 1))
        rows = bands.observe(self.root)
        self.assertEqual([(r["family"], r["tier"], r["version"]) for r in rows], [(self.fid, "train", 1)])

        release_b = {**self.release_a, "execution": "release B's league/live"}
        out = adopt(self.store, release_b)
        fam = self.store.family(self.fid)
        state = fam["state"]
        self.assertEqual(fam["best_train"], score, "the Train best stands: its run is on the same image and bundle")
        self.assertEqual((out["adopted"], out["families"], out["gym_changed"], out["bests"]), (True, 1, False, 1))
        self.assertEqual((state["best_train_version"], state["best_train_run"]),
                         (before["state"]["best_train_version"], before["state"]["best_train_run"]))
        self.assertEqual(state["train_candidates"], before["state"]["train_candidates"])
        self.assertEqual(state["robustness"], before["state"]["robustness"], "its robustness figures stand")
        self.assertTrue(robust_at_stress(state, 1), "so the tournament can validate it")
        self.assertEqual((state["drift_failed"], state["robust_failed"]), ({"7": "a weaker version's mark"}, [7]),
                         "a demotion stands too")
        self.assertEqual(state["train_passed"], {}, "the live route's mark is made again under the new fingerprint")
        self.assertEqual(state["evaluator"], release_b)
        self.assertNotIn("evaluator_trials", state, "nothing is owed again, so the idle count goes on")
        self.assertNotIn(ARCHIVE_KEY, state)
        researcher.ensure_robustness(fam)
        self.assertEqual(self.pool.queued, [], "nothing is owed again: no robustness run is bought twice")
        self.assertEqual(bands.observe(self.root), rows, "the practice league still has its Train-tier row at the next open")
        self.assertEqual(self.store.notebook(self.fid, limit=20), [], "no note tells the researcher its work is void")
        [event] = adoptions(self.store)
        self.assertEqual((event["gym_changed"], event["restored"], event["_previous_selection"]),
                         (False, None, {"train_passed": {"1": {"evaluator": self.release_a}}}))
        self.assertEqual(event["kept"], ["best_train", "best_train_run", "best_train_version", "drift_failed", "robust_failed",
                                         "robustness", "train_candidates"])

        # A new Gym image still clears the selection: its rows are no longer current.
        out = adopt(self.store, {**release_b, "image": "a new image"})
        self.assertTrue(out["gym_changed"])
        fam = self.store.family(self.fid)
        self.assertIsNone(fam["best_train"])
        self.assertEqual(fam["state"]["robustness"], {})
        self.assertEqual(fam["state"][ARCHIVE_KEY]["best_train"], score)
        self.assertEqual(bands.observe(self.root), [])

    def test_after_a_league_live_only_adoption_a_new_best_still_queues_its_robustness_runs(self):
        researcher = self.researcher()
        adopt(self.store, {**self.release_a, "execution": "release B's league/live"})
        self.best_with_robustness(researcher)
        self.assertTrue(robust_at_stress(self.store.family(self.fid)["state"], 1))


class LiveOnlyCase(RoundCase):
    """A swarm on a named Gym (its image and bundle), adopted under release A's league/live. Releases B, C and D each
    change league/live alone."""

    IMAGE = "synthetic-image"

    def setUp(self):
        super().setUp()
        self.bundle = bands._bundle()
        self.pool.image = lambda kind="gym": self.IMAGE
        self.pool.bundle = lambda: self.bundle
        stamped = self.answer
        self.answer = lambda job: {**stamped(job), "gym_image": self.IMAGE, "gym_bundle": self.bundle}
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": self.IMAGE}}))
        self.release_a = {"image": self.IMAGE, "bundle": self.bundle, "execution": "release A's league/live"}
        self.release_b, self.release_c, self.release_d = (
            {**self.release_a, "execution": f"release {name}'s league/live"} for name in "BCD")
        self.store.put(KEY, self.release_a)
        self.tournament = Tournament(self.store, self.pool, self.settings, clock=self.clock)

    def with_train_best(self, fid, score=1.2):
        """A family whose version 1 is its best by Train score, on an eligible Train run of the Gym in force."""
        self.family(fid)
        row = seed_current_run(self.store, fid, 1, window="train")
        self.store.update_family(fid, best_train=score)
        self.store.set_state(fid, best_train_run=row["run_id"], best_train_version=1)
        return row

    def validated(self, fid):
        """A family the tournament validated (the line met), whose version the gate's review and audit passed: its run sha."""
        self.with_train_best(fid)
        judged = self.tournament.validate([self.store.family(fid)])["judged"]
        self.assertTrue(judged[fid]["passed"])
        sha = run_sha(self.store.version(fid, 1))
        self.store.set_state(fid, review=reviewed(sha))
        return sha

    def practice(self):
        return bands.observe(self.root)

    def tuition_rows(self):
        """The retired execution tuition's Gym-band rows (`bands.read(tuition=True)`, that route's own read). As shipped
        `bands.read` gives none (`bands.TUITION_ROWS` False)."""
        return [r for r in bands.read(self.root, tuition=True) if r["band"] == "gym"]


class ThePracticeLeagueAcrossAnAdoption(LiveOnlyCase):
    """WHAT THE RULE IS FOR. On Oct 3, 2026 a league/live-only release cleared every alive family's best: the swarm offered
    the practice league no program (`bands.observe` returned nothing) until each researcher happened to run its old best
    again. Now the swarm offers the same programs after such an adoption as before it, with no researcher cycle between."""

    def test_practice_is_offered_the_same_programs_and_a_recorded_validation_is_still_current(self):
        self.validated("v")
        self.with_train_best("t")
        rows = self.practice()
        self.assertEqual([(r["family"], r["tier"], r["version"]) for r in rows], [("v", "validated", 1), ("t", "train", 1)])
        self.assertEqual(([r["family"] for r in self.tuition_rows()], bands.read(self.root)), (["v"], []),
                         "validated and reviewed: a row on the retired tuition read before it; none as shipped")
        before = {fid: self.store.family(fid) for fid in ("v", "t")}
        jobs = len(self.pool.jobs)

        out = adopt(self.store, self.release_b)
        self.assertEqual((out["gym_changed"], out["families"], out["bests"]), (False, 2, 2))
        self.assertEqual(self.practice(), rows, "the same programs in the same order, with no researcher cycle between")
        self.assertEqual({r["family"]: bands.observe(self.root, family=r["family"], version=r["version"]) for r in rows},
                         {r["family"]: [r] for r in rows}, "and each pinned version is still admitted")
        v = self.store.family("v")
        for key in ("validation_version", "validation_line", "validation_view", "validation_image", "validation_bundle",
                    "validation_numbers", "gate_ready", "typical_max_loss_usd", "typical_by_version"):
            with self.subTest(key=key):
                self.assertIsNotNone(before["v"]["state"][key])
                self.assertEqual(v["state"][key], before["v"]["state"][key])
        # Practice is shadow only. The gate's review is not practice's: it is what real orders are granted on, and it went.
        self.assertIsNotNone(before["v"]["state"]["review"])
        self.assertEqual((v["state"]["review"], bands.read(self.root), self.tuition_rows()), (None, [], []),
                         "practice keeps its rows; no real order does, on either read")
        self.assertEqual((v["validated_version"], v["best_validation"]), (1, before["v"]["best_validation"]))
        self.assertIsNotNone(self.tournament.recorded_validation("v", 1), "its recorded validation is on the Gym in force")

        round_ = self.tournament.validate(self.store.families(alive=True))
        self.assertEqual(round_["waiting_robustness"], [], "no best is left waiting for evidence it already had")
        self.assertEqual(sorted(round_["judged"]), ["t"], "the validated family is current: it is not validated again")
        self.assertEqual([job.family for job in self.pool.jobs[jobs:]], ["t"], "one job: the best that was not validated yet")
        v = self.store.family("v")
        self.assertEqual((v["trials"], v["validations"]), (before["v"]["trials"], before["v"]["validations"]), "no new trial")
        self.assertTrue(v["state"]["gate_ready"], "its gate place stands")
        guard = retire_guard(self.store, v, self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, False), "its pass is its own line's, not an archive's")

    def test_a_recorded_pass_from_before_it_is_a_standing_pass_and_asks_for_no_run(self):
        """THE VALIDATED-FAMILY GUARD's words (`retire_guard`, `guard_words`). Version 1 passed the line, then version 2's
        failure replaced the family's line, then a league/live-only adoption. The record of version 1's pass names the
        earlier execution fingerprint, on the Gym still in force: nothing archived it and nothing is owed again, so the
        researcher is not told to run it again (the note that made validated families retire themselves, in other words).
        A new Gym does archive it."""
        self.validated("v")
        self.store.add_version("v", CODE + "# 2\n", {}, author="test")
        row = seed_current_run(self.store, "v", 2, window="train")
        self.store.update_family("v", best_version=2)
        self.store.set_state("v", submitted_run=row["run_id"])
        self.answer = lambda job: {**weak(job), "gym_image": self.IMAGE, "gym_bundle": self.bundle}
        self.assertEqual(self.tournament.validate([self.store.family("v")])["judged"]["v"]["passed"], False)
        state = self.store.family("v")["state"]
        self.assertEqual((state["validation_version"], state["validation_line"]["passed"]), (2, False))

        adopt(self.store, self.release_b)
        guard = retire_guard(self.store, self.store.family("v"), self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, False))
        words = guard_words(guard)
        self.assertIn("Your family holds version 1, which passed the validation line.", words)
        self.assertIn("Keep researching beside it", words)
        for told in ("before the evaluator changed", "archived", "Re-run"):
            self.assertNotIn(told, words)

        adopt(self.store, {**self.release_b, "image": "a new image"})
        guard = retire_guard(self.store, self.store.family("v"), self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, True), "judged on another Gym: owed again")
        self.assertIn("Re-run version 1 unchanged on Train", guard_words(guard))

    def test_a_gate_record_that_cannot_be_read_costs_its_own_family_its_row_and_no_other(self):
        """A `review` (or a `gate_outcome`) that is there and is no mapping: a damaged store, or a hand edit. A
        league/live-only adoption KEEPS such a review as it is (`review_stands`, fail-closed: it cannot be read as a
        pass), so no adoption repairs it any more. The practice read must not fall over it: `bands.observe` gives that
        family no row (fail-closed: its program's verdict cannot be read) and every other family its own. Raising
        instead, the House would read "the observe band could not be read" for as long as the record stays, and freeze
        no new cohort for any family."""
        self.validated("v")
        self.with_train_best("t")
        self.validated("w")
        rows = self.practice()
        self.assertEqual([r["family"] for r in rows], ["v", "w", "t"])
        for key in ("review", "gate_outcome"):
            for damaged in (7, "a text", ["a", "list"], True):
                with self.subTest(key=key, damaged=damaged):
                    was = self.store.family("v")["state"].get(key)
                    self.store.set_state("v", **{key: damaged})
                    self.assertEqual(self.practice(), [r for r in rows if r["family"] != "v"],
                                     "no row for the family whose record cannot be read; the others' rows stand")
                    self.assertEqual(bands.observe(self.root, family="v"), [])
                    self.assertEqual(bands.observe(self.root, family="v", version=1), [], "nor for its pinned version")
                    self.assertEqual(bands.observe(self.root, family="w"), [r for r in rows if r["family"] == "w"])
                    self.store.set_state("v", **{key: was})
                    self.assertEqual(self.practice(), rows, "the record put right: its row is back")
        # The adoption keeps the damaged review (it is no pass), and the read still stands for the others after it.
        self.store.set_state("v", review=7)
        adopt(self.store, self.release_b)
        self.assertEqual(self.store.family("v")["state"]["review"], 7)
        self.assertIn("review", adoptions(self.store, "v")[-1]["kept"])
        self.assertEqual([r["family"] for r in self.practice()], ["w", "t"])
        # A record that is merely absent or empty is no verdict: the family has its row, as before.
        for empty in (None, {}):
            self.store.set_state("v", review=empty, gate_outcome=empty)
            self.assertEqual([r["family"] for r in self.practice()], ["v", "w", "t"])

    def test_a_new_gym_still_leaves_practice_with_nothing_until_research_selects_again(self):
        self.validated("v")
        self.with_train_best("t")
        self.assertEqual(len(self.practice()), 2)
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": "a new image"}}))
        out = adopt(self.store, {**self.release_a, "image": "a new image"})
        self.assertEqual((out["gym_changed"], out["bests"]), (True, 0))
        self.assertEqual(self.practice(), [])
        self.assertEqual([self.store.family(fid)["best_version"] for fid in ("v", "t")], [None, None])


class Restoration(LiveOnlyCase):
    """THE ONE-TIME RESTORATION. Release V3-A part 1 (Oct 3, 2026 08:50Z) changed league/live alone and, by the rule then,
    archived and cleared every alive family's selection (`adopt_as_v3a` is that release's `adopt`, so each fixture holds
    exactly the state and the events it left). The next league/live-only adoption gives an alive family that holds no
    best, and nothing it selected since, that archive back: exactly what was archived, once."""

    def setUp(self):
        super().setUp()
        self.sha = self.validated("v")
        self.store.set_state("v", incubator_reviews={self.sha: reviewed(self.sha)}, robust_failed=[7],
                             train_passed={"1": {"evaluator": self.release_a}}, robust_why={"7": "lost at 1.5x"},
                             drift_failed={"6": "an older version's mark"}, dormant_cycles=6)
        self.store.update_family("v", stall=3, since_val_revisions=4, since_val_trials=5)
        self.with_train_best("t")
        self.rows = self.practice()
        self.tuition = self.tuition_rows()  # the retired route's own read (as shipped, `bands.read` gives no Gym-band row)
        self.before = {fid: self.store.family(fid) for fid in ("v", "t")}

    def cleared_by_v3a(self, previous="release A"):
        """That release's adoption of release B's league/live; `previous` replaces the identity it adopts from. Its time."""
        if previous != "release A":
            self.store.put(KEY, previous)
        self.clock.advance(3600)
        at = self.store.now()
        self.assertEqual(adopt_as_v3a(self.store, self.release_b)["families"], 2)
        self.assertEqual((self.practice(), bands.read(self.root), self.tuition_rows()), ([], [], []),
                         "the practice league was offered nothing")
        self.assertEqual([self.store.family(fid)["best_version"] for fid in ("v", "t")], [None, None])
        self.clock.advance(3600)
        return at

    def test_the_selection_it_cleared_is_given_back_and_practice_has_its_programs_again(self):
        self.assertEqual([(r["family"], r["tier"]) for r in self.rows], [("v", "validated"), ("t", "train")])
        at = self.cleared_by_v3a()
        wiped = {fid: self.store.family(fid) for fid in ("v", "t")}
        guard = retire_guard(self.store, wiped["v"], self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, False),
                         "guarded meanwhile by its recorded pass, which was judged on the Gym in force: no re-run is asked")

        out = adopt(self.store, self.release_c)
        self.assertEqual((out["gym_changed"], out["restored"], out["bests"], out["families"]),
                         (False, {"v": at, "t": at}, 2, 2))
        self.assertEqual(self.practice(), self.rows, "the practice league has the programs it had, with no researcher cycle")
        for fid in ("v", "t"):
            fam, was = self.store.family(fid), self.before[fid]
            for column in BEST_COLUMNS:
                with self.subTest(family=fid, column=column):
                    self.assertEqual(fam[column], was[column])
            for key in GYM_KEYS:
                with self.subTest(family=fid, key=key):
                    self.assertEqual(fam["state"][key], was["state"].get(key, CLEARED.get(key)))
        v = self.store.family("v")
        self.assertEqual((v["state"]["train_passed"], v["state"]["incubator_reviews"], v["state"]["review"]), ({}, {}, None),
                         "the live route's facts stay cleared, the gate's review too: they are owed under the new fingerprint")
        self.assertIsNotNone(v["state"][ARCHIVE_KEY]["review"], "that release archived a review, and it is not given back")
        self.assertEqual((v["stall"], v["since_val_revisions"], v["since_val_trials"], v["state"]["dormant_cycles"],
                          v["state"]["evaluator_trials"]), (0, 0, 0, 0, wiped["v"]["state"]["evaluator_trials"]),
                         "the counts that adoption restarted were never archived: they go on from its restart")
        self.assertEqual(v["trials"], self.before["v"]["trials"], "no trial is refunded or added")
        self.assertEqual(v["state"]["evaluator"], self.release_c)
        self.assertEqual(v["state"][ARCHIVE_KEY], wiped["v"]["state"][ARCHIVE_KEY], "the archive stays where it was")

        event = adoptions(self.store, "v")[-1]
        self.assertEqual(set(event), EVENT_KEYS)
        self.assertEqual((event["gym_changed"], event["restored"]["adopted_at"], event["_previous_selection"]),
                         (False, at, {"train_passed": {}, "incubator_reviews": {}, "review": None}))
        self.assertEqual(event["restored"]["keys"], ["best_train", "best_train_run", "best_train_version", "best_validation",
                                                     "best_version", "drift_failed", "gate_ready", "robust_failed",
                                                     "robust_why", "typical_by_version", "typical_max_loss_usd",
                                                     "validated_version", "validation_bundle", "validation_image",
                                                     "validation_line", "validation_numbers", "validation_version",
                                                     "validation_view"], "never the gate's review")
        self.assertEqual(event["kept"], sorted([*event["restored"]["keys"], "extension_hold", "extension_versions"]),
                         "it holds what it was given back, and the hold that release's adoption never cleared")
        self.assertTrue(extension_held(v), "which applies again with the validation it was earned on")
        self.assertEqual(adoptions(self.store, "t")[-1]["restored"],
                         {"adopted_at": at, "keys": ["best_train", "best_train_run", "best_train_version", "best_version"]})
        notes = [n["text"] for n in self.store.notebook("v", limit=20)]
        self.assertIn("The evaluator changed.", notes[-2])
        self.assertIn(f"The evaluator adoption of {at} changed only the live executor", notes[-1])
        self.assertIn("nothing is owed again", notes[-1])

        # The tournament reads the restored validation as current. D2's route is NOT given back with it: the family had a
        # tuition row before that release, and has none until the gate has reviewed its program again.
        jobs = len(self.pool.jobs)
        round_ = self.tournament.validate(self.store.families(alive=True))
        self.assertEqual((sorted(round_["judged"]), [job.family for job in self.pool.jobs[jobs:]]), (["t"], ["t"]))
        self.assertEqual(self.store.family("v")["trials"], self.before["v"]["trials"])
        guard = retire_guard(self.store, self.store.family("v"), self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, False))
        self.assertEqual([(r["family"], r["band"]) for r in self.tuition], [("v", "gym")], "a validated, reviewed Gym family")
        self.assertEqual((bands.read(self.root), self.tuition_rows()), ([], []),
                         "no real-order row is given back: the gate's review is owed again")
        # The gate takes it up by its own rule (its place was given back) and reads the program again; no look can be
        # made here (the gate image is not ready), so the round is the reviews and audits, and only then is the row back.
        # (The round above validated t as well, so the gate reads two programs: a review and an audit each.)
        self.settings["gym"]["gate_checkpoint"] = None
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 4
        out = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertEqual((sorted(out["waiting"]), len(self.sail.bodies)), (["t", "v"], 4))
        self.assertEqual([r for r in self.tuition_rows() if r["family"] == "v"], self.tuition,
                         "reviewed and audited again, the retired tuition read gives the row it gave before that release")
        self.assertEqual(bands.read(self.root), [], "and as shipped there is no row before the look: tuition is retired")

    def test_a_family_that_set_a_best_of_its_own_since_keeps_it(self):
        self.cleared_by_v3a()
        self.store.add_version("t", CODE + "# 2\n", {}, author="test")
        row = seed_current_run(self.store, "t", 2, window="train")
        self.store.update_family("t", best_train=0.7)  # a new best by Train score
        self.store.set_state("t", best_train_run=row["run_id"], best_train_version=2,
                             train_candidates=[[0.7, 2, row["run_id"]]])
        self.store.update_family("v", best_version=1)  # a best submitted again
        out = adopt(self.store, self.release_c)
        self.assertEqual((out["restored"], out["bests"]), ({}, 2))
        t, v = self.store.family("t"), self.store.family("v")
        self.assertEqual((t["best_train"], t["best_version"], t["state"]["best_train_version"]), (0.7, None, 2))
        self.assertEqual((v["best_train"], v["best_version"], v["state"]["validation_version"]), (None, 1, None))
        for fid in ("t", "v"):
            event = adoptions(self.store, fid)[-1]
            self.assertEqual((event["restored"], event["not_restored"]),
                             (None, "it holds a best or a validation of its own since"))
        self.assertEqual([(r["family"], r["tier"], r["version"]) for r in self.practice()],
                         [("t", "train", 2), ("v", "train", 1)], "each practises the best it chose since")

    def test_a_family_that_selected_and_lost_a_best_since_keeps_what_it_made(self):
        at = self.cleared_by_v3a()
        self.store.set_state("t", robust_failed=[2], robust_why={"2": "lost money on Train at 1.5x the half-spread"},
                             robustness={"2": {"stress_1.5": {"status": "ok", "pnl": -5.0}}})
        out = adopt(self.store, self.release_c)
        self.assertEqual(out["restored"], {"v": at})
        t = self.store.family("t")
        self.assertEqual((t["best_train"], t["best_version"], t["state"]["robust_failed"]), (None, None, [2]))
        event = adoptions(self.store, "t")[-1]
        self.assertEqual((event["restored"], event["not_restored"]),
                         (None, "it selected on its own since (robust_failed, robust_why, robustness)"))

    def test_drift_marks_made_since_stay_beside_the_archived_ones(self):
        """A failing run marks its version without the family ever holding a best (`Researcher.drift_blocks`). Marks on
        versions the archive does not select are the family's own newer evidence about other programs: they stay."""
        at = self.cleared_by_v3a()
        self.store.set_state("v", drift_failed={"9": "a failing run since"})
        self.store.set_state("t", drift_failed={str(n): "since" for n in range(2, DRIFT_FAILED_KEPT + 4)})
        out = adopt(self.store, self.release_c)
        self.assertEqual(out["restored"], {"v": at, "t": at})
        self.assertEqual(self.store.family("v")["state"]["drift_failed"],
                         {"6": "an older version's mark", "9": "a failing run since"})
        self.assertEqual(self.store.family("v")["best_version"], 1)
        t = self.store.family("t")
        self.assertEqual(sorted(t["state"]["drift_failed"], key=int), [str(n) for n in range(2, DRIFT_FAILED_KEPT + 4)],
                         "a family whose archive held no mark keeps its own, untouched")
        self.assertEqual(t["best_train"], 1.2)

    def test_the_marks_given_back_and_those_made_since_keep_to_the_newest_versions(self):
        """`DRIFT_FAILED_KEPT`, as every writer of the marks keeps them: the newest versions' only."""
        at = self.cleared_by_v3a()
        since = range(100, 100 + DRIFT_FAILED_KEPT + 3)
        self.store.set_state("v", drift_failed={str(n): "since" for n in since})
        self.assertEqual(adopt(self.store, self.release_c)["restored"], {"v": at, "t": at})
        marks = self.store.family("v")["state"]["drift_failed"]
        self.assertEqual(sorted(marks, key=int), [str(n) for n in sorted([6, *since])[-DRIFT_FAILED_KEPT:]])
        self.assertEqual((len(marks), "6" in marks), (DRIFT_FAILED_KEPT, False), "the archive's older mark made room")

    def test_a_drift_mark_made_since_on_a_version_it_archived_keeps_the_archive_back(self):
        """The family ran a version of its archive again and the drift screen failed it: its own newer evidence about that
        very version. No writer leaves a failed version as the best (a demotion clears it), so none is raised again: not
        the validated best (v), not a selection with a failed candidate in it (t), and not a validation whose version
        failed while a newer best stood beside it (x)."""
        self.store.add_version("t", CODE + "# 2\n", {}, author="test")
        second = seed_current_run(self.store, "t", 2, window="train")
        first = self.store.family("t")["state"]["best_train_run"]
        self.store.set_state("t", train_candidates=[[1.2, 1, first], [0.9, 2, second["run_id"]]])
        self.validated("x")  # version 1 validated; then version 2 became its best, not validated yet
        self.store.add_version("x", CODE + "# 2\n", {}, author="test")
        newer = seed_current_run(self.store, "x", 2, window="train")
        self.store.update_family("x", best_version=2, best_train=1.4)
        self.store.set_state("x", best_train_version=2, best_train_run=newer["run_id"])
        self.clock.advance(3600)
        self.assertEqual(adopt_as_v3a(self.store, self.release_b)["families"], 3)
        archive = self.store.family("x")["state"][ARCHIVE_KEY]
        selects = ("best_version", "best_train_version", "validated_version", "validation_version")
        self.assertEqual([archive[key] for key in selects], [2, 2, 1, 1])
        self.clock.advance(3600)
        self.store.set_state("v", drift_failed={"1": "its validated best, run again", "9": "another version's"})
        self.store.set_state("t", drift_failed={"2": "a candidate of its archive, run again"})
        self.store.set_state("x", drift_failed={"1": "its validated version, run again"})
        out = adopt(self.store, self.release_c)
        self.assertEqual((out["restored"], out["bests"]), ({}, 0))
        for fid, n in (("v", 1), ("t", 2), ("x", 1)):
            fam = self.store.family(fid)
            self.assertEqual([fam[column] for column in BEST_COLUMNS], [None] * 4)
            self.assertEqual((fam["state"]["validation_version"], fam["state"]["best_train_version"]), (None, None))
            event = adoptions(self.store, fid)[-1]
            self.assertEqual((event["restored"], event["not_restored"]),
                             (None, f"the drift screen failed, since, a version it archived ({n})"))
        self.assertEqual(self.store.family("v")["state"]["drift_failed"],
                         {"1": "its validated best, run again", "9": "another version's"}, "its marks are its own")
        self.assertEqual((self.practice(), bands.read(self.root)), ([], []), "no practice row and no real order follows")

    def test_trains_objective_chosen_anew_since_keeps_the_archive_back(self):
        """`migrate_objective` runs before `adopt` at every swarm start. A span switch since that adoption emptied every
        best the new span has no run for; the archive's bests were scored over the old span, and an old span's score never
        stands beside a new span's. Nothing is given back, and practice is offered no old-span program."""
        self.cleared_by_v3a()
        settings = json.loads(json.dumps(self.settings))
        settings["gym"]["train_from"] = "2020-01-02"
        self.assertEqual(migrate_objective(self.store, settings=settings), {"migrated": 2, "with_best": 0, "failed": 0})
        objective = self.store.get("train_objective")
        self.assertEqual(objective, "worst-train-year-v1@2020-01-02")
        out = adopt(self.store, self.release_c)
        self.assertEqual((out["restored"], out["bests"]), ({}, 0))
        for fid in ("v", "t"):
            fam = self.store.family(fid)
            self.assertEqual([fam[column] for column in BEST_COLUMNS], [None] * 4)
            self.assertEqual((fam["state"]["best_train_version"], fam["state"]["objective_migrated"]), (None, objective))
            event = adoptions(self.store, fid)[-1]
            self.assertEqual((event["restored"], event["not_restored"]),
                             (None, "Train's objective was chosen anew since, and its archive is the earlier one's selection"))
        self.assertEqual((self.practice(), bands.read(self.root)), ([], []))
        self.assertEqual(self.tournament.validate(self.store.families(alive=True))["judged"], {}, "nothing to validate")

    def test_a_span_switch_before_that_adoption_is_the_archives_own_span(self):
        """The same start migrates, then adopts: the pass before that adoption (the same second, an earlier event) chose
        what it archived. The validation is no Train score: the migration left it, so it was archived and is given back."""
        self.clock.advance(3600)
        settings = json.loads(json.dumps(self.settings))
        settings["gym"]["train_from"] = "2020-01-02"
        self.assertEqual(migrate_objective(self.store, settings=settings)["with_best"], 0)
        at = self.store.now()
        adopt_as_v3a(self.store, self.release_b)  # no clock tick between: one swarm start
        self.clock.advance(3600)
        out = adopt(self.store, self.release_c)
        self.assertEqual((out["restored"], out["bests"]), ({"v": at}, 0),
                         "t's archive held nothing: its best was emptied before")
        v = self.store.family("v")
        self.assertEqual((v["best_train"], v["best_version"], v["validated_version"], v["state"]["validation_version"]),
                         (None, None, 1, 1))
        self.assertNotIn("not_restored", adoptions(self.store, "t")[-1])
        self.assertEqual([(r["family"], r["tier"]) for r in self.practice()], [("v", "validated")])

    def test_a_migration_that_an_error_cut_short_keeps_the_archive_back_from_the_families_it_reached(self):
        """It wrote no event and left the store's objective as it was; the family it reached says so itself."""
        at = self.cleared_by_v3a()
        self.store.set_state("t", objective_migrated="worst-train-year-v1@2020-01-02")
        out = adopt(self.store, self.release_c)
        self.assertEqual(out["restored"], {"v": at})
        self.assertEqual(adoptions(self.store, "t")[-1]["not_restored"],
                         "Train's objective was chosen anew since, and its archive is the earlier one's selection")
        self.assertIsNone(self.store.family("t")["best_train"])

    def test_a_validation_of_its_own_since_alone_keeps_the_archive_back(self):
        """Any of the four (`BEST_COLUMNS`), not only a best: a family validated since, whose best then went, holds its own."""
        for column, value in (("validated_version", 2), ("best_validation", 0.3)):
            with self.subTest(column):
                self.setUp()  # a fresh store for each
                at = self.cleared_by_v3a()
                self.store.update_family("t", **{column: value})
                out = adopt(self.store, self.release_c)
                self.assertEqual(out["restored"], {"v": at})
                t = self.store.family("t")
                self.assertEqual((t["best_train"], t["best_version"], t[column]), (None, None, value))
                self.assertEqual(adoptions(self.store, "t")[-1]["not_restored"],
                                 "it holds a best or a validation of its own since")

    def test_each_side_of_the_gym_check_keeps_another_gyms_archive_back(self):
        """A family that was retired through adoptions and revived reads an older adoption's archive than the store's newest
        one, so the two sides are not one check: the Gym that adoption archived FROM must be the one it adopted, and the
        one in force now."""
        older = {**self.release_a, "image": "an older image"}
        self.cleared_by_v3a(previous=older)
        fam = self.store.family("t")
        self.assertFalse(gym_changed(older, {**older, "execution": "now"}))
        self.assertIsNone(restorable(self.store, fam, {**older, "execution": "now"}),
                          "that adoption changed the Gym, though the Gym in force is the one it archived from")
        self.setUp()
        at = self.cleared_by_v3a()
        fam = self.store.family("t")
        self.assertEqual(restorable(self.store, fam, self.release_c)["adopted_at"], at,
                         "league/live only, and the same Gym now")
        self.assertIsNone(restorable(self.store, fam, {**self.release_c, "bundle": "gym-engine-4-newer"}),
                          "that adoption was league/live only, and the Gym changed since")

    def test_an_archive_from_an_adoption_that_changed_the_gym_is_never_given_back(self):
        for name, earlier in (("its image", {**self.release_a, "image": "an older image"}),
                              ("its bundle", {**self.release_a, "bundle": "gym-engine-4-older"}),
                              ("no identity before", None)):
            with self.subTest(name):
                self.assertTrue(gym_changed(earlier, self.release_b))
                self.setUp()  # a fresh store for each
                self.cleared_by_v3a(previous=earlier)
                out = adopt(self.store, self.release_c)
                self.assertEqual((out["gym_changed"], out["restored"], out["bests"]), (False, {}, 0))
                for fid in ("v", "t"):
                    fam = self.store.family(fid)
                    self.assertEqual([fam[column] for column in BEST_COLUMNS], [None] * 4)
                    self.assertIsNone(fam["state"]["validation_version"])
                    event = adoptions(self.store, fid)[-1]
                    self.assertIsNone(event["restored"])
                    self.assertNotIn("not_restored", event, "another Gym's evidence: there is nothing to speak of")
                self.assertEqual((self.practice(), bands.read(self.root)), ([], []))

    def test_a_retired_family_is_never_given_anything_back(self):
        at = self.cleared_by_v3a()
        wiped = self.store.family("v")
        self.assertTrue(self.store.retire("v", "its researcher retired it"))
        out = adopt(self.store, self.release_c)
        self.assertEqual((out["restored"], out["families"]), ({"t": at}, 1))
        v = self.store.family("v")
        self.assertEqual([v[column] for column in BEST_COLUMNS], [None] * 4)
        self.assertEqual({k: v["state"][k] for k in GYM_KEYS}, {k: wiped["state"][k] for k in GYM_KEYS})
        self.assertEqual(len(adoptions(self.store, "v")), 1, "an adoption writes nothing for a retired family")
        self.assertEqual([r["family"] for r in self.practice()], ["t"])

    def test_it_happens_once(self):
        from league.swarm.researcher import demote_version

        at = self.cleared_by_v3a()
        self.assertEqual(adopt(self.store, self.release_c)["restored"], {"v": at, "t": at})
        self.assertFalse(adopt(self.store, self.release_c)["adopted"], "a restart under the same identity adopts nothing")
        self.assertEqual(len(adoptions(self.store, "t")), 2)
        # Its restored best then loses at 1.5x: the family holds no best again, and the archive is still in its state.
        demote_version(self.store, self.store.family("t"), 1)
        t = self.store.family("t")
        self.assertEqual((t["best_train"], t["best_version"], t["state"]["best_train_version"]), (None, None, None))
        self.assertEqual(t["state"][ARCHIVE_KEY]["best_train"], 1.2)
        out = adopt(self.store, self.release_d)
        self.assertEqual((out["restored"], out["bests"]), ({}, 1))
        t = self.store.family("t")
        self.assertEqual((t["best_train"], t["best_version"], t["state"]["robust_failed"]), (None, None, [1]),
                         "the next adoption never raises a demoted best again")
        event = adoptions(self.store, "t")[-1]
        self.assertIsNone(event["restored"])
        self.assertNotIn("not_restored", event)
        self.assertIsNone(restorable(self.store, t, self.release_d))
        self.assertEqual(self.store.family("v")["best_version"], 1, "and what was given back stands")

    def test_a_family_with_nothing_archived_is_given_nothing(self):
        self.family("n")
        self.store.update_family("n", best_version=None)  # alive, and never selected anything
        self.clock.advance(60)
        adopt_as_v3a(self.store, self.release_b)
        out = adopt(self.store, self.release_c)
        self.assertEqual(sorted(out["restored"]), ["t", "v"])
        event = adoptions(self.store, "n")[-1]
        self.assertEqual((event["restored"], event["kept"]), (None, []))
        self.assertNotIn("not_restored", event)

    def test_an_archive_that_cannot_be_read_never_keeps_the_swarm_from_starting(self):
        at = self.cleared_by_v3a()
        with patch("league.swarm.evaluator.restorable", side_effect=sqlite3.OperationalError("database is locked")):
            out = adopt(self.store, self.release_c)
        self.assertEqual((out["adopted"], out["restored"], out["families"]), (True, {}, 2))
        event = adoptions(self.store, "v")[-1]
        self.assertEqual((event["restored"], event["not_restored"]), (None, "its archive could not be read (OperationalError)"))
        self.assertEqual(self.store.get(KEY), self.release_c)
        self.assertIsNotNone(at)


class LeagueLiveAdoptionAndMoney(RetiredTuition, LiveOnlyCase):
    """(The tuition tests' own class: `RetiredTuition` switches the retired Gym-band rows on, so each test below reads
    what a kept or cleared review would have granted on that route. `league/tests/test_live_ladder_adoption.py` holds
    the same adoptions under the shipped switches, where the look is the only route.)

    THE MONEY SIDE DOES NOT MOVE: NO REAL-ORDER ROUTE CARRIES ACROSS A LEAGUE/LIVE CHANGE. A band is entry authority only
    under the execution fingerprint that granted it, so a league/live-only adoption still returns it to the Gym, and no
    real order follows from its program; the incubator's marks and reviews are owed again; bars, refusals and looks are
    untouched. And the gate's passing review is the live route's fact (the module's docstring, pinned here): it is
    cleared for every family and never given back, so no validated family has a tuition row (`bands.read`) after such an
    adoption, or after the restoration, until the gate has reviewed its program again, which it does by its own rule
    wherever it still owes the program a look. A review that did NOT pass is the gate's memory that it failed a program:
    it is kept as it is, and given back by the restoration, so no program the gate failed is read a second time."""

    def look_in_flight(self, fid="v"):
        """A validated, reviewed family whose holdout look is out, as `Gate.look` leaves it while the gate box runs:
        its gate place cleared, the look in its marker. (Its run sha, the marker.)"""
        sha = self.validated(fid)
        marker = {"sha": sha, "n": 1, "at": self.clock(), "token": "0123456789abcdef"}
        self.store.set_state(fid, gate_ready=False, look_inflight=marker)
        return sha, marker

    def tuition(self):
        return [(r["family"], r["version"]) for r in bands.read(self.root) if r["band"] == "gym"]

    def readers_pass(self, programs=1):
        """The gate's two readers (the review, then the audit) pass the next `programs` programs they read."""
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * (2 * programs)

    def reads(self):
        """The model reads made so far, on Sail and through the gateway."""
        return len(self.sail.bodies) + len(self.asked)

    def review_of(self, fid):
        """(the program, the verdict, the audit's verdict) of the gate's review in the family's state, or None."""
        review = self.store.family(fid)["state"].get("review")
        return (review["sha"], review["verdict"], (review.get("audit") or {}).get("verdict")) if review else None

    def banded(self, fid="p", band="probe"):
        """A family that passed its holdout look and holds a money band whose proof names release A's executor."""
        sha = self.validated(fid)
        version = self.store.version(fid, 1)
        self.store.add_look(fid, 1, sha, passed=True, p_value=0.01, detail={"synthetic": True})
        self.store.set_state(fid, gate_ready=False, gated_sha=sha,
                             gate_outcome={"sha": sha, "result": "passed", "at": self.clock()},
                             banded_version=1, banded_sha=version["sha"], banded_at=self.clock(),
                             banded_evaluator={**band_proof(version), "execution_sha256": "release A's league/live"})
        self.store.set_band(fid, band, reason="passed its holdout look")
        return sha

    def gate(self):
        return Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)

    def test_a_stale_band_still_returns_to_the_gym_and_no_real_order_follows_from_its_program(self):
        sha = self.banded("p")
        ahead = self.store.family("p")
        self.assertFalse(bands.current_banded_evaluator(ahead["state"], sha), "the proof pins the execution fingerprint")
        self.assertEqual(bands.read(self.root), [], "so the band admits nothing already")

        out = adopt(self.store, self.release_b)
        fam = self.store.family("p")
        state = fam["state"]
        self.assertEqual((fam["band"], out["returned"], out["bests"]), ("gym", ["p"], 1))
        [move] = [e["payload"] for e in self.store.events_after(0)
                  if e["kind"] == "swarm.band" and e["payload"]["band_to"] == "gym"]
        self.assertEqual((move["band_from"], move["reason"]),
                         ("probe", "execution semantics changed; fresh qualification is required"))
        self.assertFalse(bands.current_banded_evaluator(state, sha))
        self.assertEqual((state["banded_version"], state["banded_evaluator"]), (1, ahead["state"]["banded_evaluator"]),
                         "the banded identity remains an historical claim")
        # Its Gym evidence stands, so the practice league has its program again (shadow only) ...
        for key in ("validation_version", "validation_line", "validation_image", "validation_bundle", "validation_numbers",
                    "typical_max_loss_usd", "typical_by_version", "gated_sha", "gate_outcome", "best_train_version"):
            with self.subTest(key=key):
                self.assertEqual(state[key], ahead["state"][key])
        self.assertEqual((fam["best_train"], fam["best_version"], fam["validated_version"]), (1.2, 1, 1))
        self.assertEqual([(r["family"], r["tier"], r["observe"]) for r in self.practice()], [("p", "validated", True)])
        # ... and the gate's review of the banded program went, as every family's does: beside the kept validation it is
        # what a tuition row is granted on, and the gate never reads a program again once its look was made.
        self.assertIsNone(state["review"])
        self.assertEqual(bands.read(self.root), [], "neither a band row nor a tuition row")
        self.assertEqual(bands.incubator(self.root, family="p", version=1), [], "nor the incubator's")
        event = adoptions(self.store, "p")[-1]
        self.assertEqual((event["gym_changed"], event["_previous_selection"]), (False, {"review": ahead["state"]["review"]}))
        self.assertNotIn("review", event["kept"])
        self.assertIn("validation_line", event["kept"])
        asked = len(self.sail.bodies) + len(self.asked)
        self.assertEqual(self.gate().run()["looked"], [])
        self.assertEqual((len(self.sail.bodies) + len(self.asked), bands.read(self.root)), (asked, []),
                         "the gate is done with it: no review is bought again, and no look")
        self.assertTrue(self.store.looked(sha), "its look stays spent")
        [note] = [n["text"] for n in self.store.notebook("p", limit=20)]
        self.assertIn("this family's money band returned to the Gym", note)
        self.assertNotIn("The evaluator changed.", note)

    def test_a_band_returned_by_the_earlier_adoption_gets_its_selection_back_without_the_gates_review(self):
        sha = self.banded("p", band="candidate")
        ahead = self.store.family("p")
        self.clock.advance(3600)
        at = self.store.now()
        adopt_as_v3a(self.store, self.release_b)  # that release returned the band and cleared the selection
        self.assertEqual((self.store.family("p")["band"], self.practice(), bands.read(self.root)), ("gym", [], []))
        out = adopt(self.store, self.release_c)
        self.assertEqual((out["restored"], out["returned"]), ({"p": at}, []))
        fam = self.store.family("p")
        self.assertEqual((fam["band"], fam["validated_version"], fam["state"]["validation_line"]),
                         ("gym", 1, ahead["state"]["validation_line"]))
        self.assertEqual((fam["state"]["gated_sha"], fam["state"]["gate_outcome"]["result"]), (sha, "passed"))
        self.assertIsNone(fam["state"]["review"], "the gate's review is never given back, to a family that held a band or not")
        restored = adoptions(self.store, "p")[-1]["restored"]
        self.assertNotIn("review", restored["keys"])
        self.assertEqual((fam["state"]["gate_ready"], "look_owed" in restored), (False, False),
                         "its look was made: the gate is done with it, and no place is given to it")
        self.assertEqual([(r["family"], r["tier"]) for r in self.practice()], [("p", "validated")])
        self.assertEqual(bands.read(self.root), [], "its practice restarts; no real order follows")

    def test_a_gym_family_on_d2s_route_has_no_row_until_the_gate_reviews_it_again(self):
        """NO REAL-ORDER ROUTE CARRIES (the module's THE MONEY SIDE DOES NOT MOVE). `bands.read`'s tuition rule is
        untouched and names no fingerprint: a validated version that met the line on the Gym in force, whose review and
        audit passed, and that the gate has not failed, refused, demoted or held. The validation is Gym evidence and is
        kept; the gate's review is the live route's fact and is cleared, so the row ends at the adoption, for a family
        that never held a band too. The family is left in exactly the state the gate's round takes up (validated, its
        place kept, the gate not done with it, no review), so the next round reviews and audits the program again, and
        only then is the row back. It still ends as it always did."""
        sha = self.validated("v")
        [row] = bands.read(self.root)
        self.assertEqual((row["family"], row["band"], row["holdout_passed"], row["validation_passed"]),
                         ("v", "gym", False, True))
        ahead = self.store.family("v")["state"]
        adopt(self.store, self.release_b)
        state = self.store.family("v")["state"]
        self.assertEqual((state["review"], bands.read(self.root)), (None, []), "no tuition row carries across the change")
        self.assertEqual(bands.incubator(self.root, family="v", version=1), [], "nor is the incubator's route open to it")
        event = adoptions(self.store, "v")[-1]
        self.assertEqual(event["_previous_selection"], {"review": ahead["review"]}, "the review is archived in the event")
        self.assertNotIn("review", event["kept"])
        self.assertEqual((state["gate_ready"], state["validation_version"], state["validation_line"], state.get("gated_sha"),
                          state.get("look_inflight"), state.get("gate_hold")), (True, 1, ahead["validation_line"], None, None, None),
                         "what the gate's round takes up: the line met, its place kept, the gate not done with the program")
        self.assertEqual(self.store.notebook("v", limit=20), [], "and no note tells the researcher anything is owed")

        # The gate's next round. No look can be made here (the gate image is not ready), so the round is its review and
        # its audit alone: the program is read again, by both readers, before any real order.
        self.settings["gym"]["gate_checkpoint"] = None
        reads = self.reads()
        self.readers_pass()
        self.assertEqual(self.gate().run()["waiting"], ["v"])
        self.assertEqual((self.reads() - reads, self.review_of("v")), (2, (sha, "pass", "pass")), "a review and an audit, asked")
        self.assertEqual(bands.read(self.root), [row], "the row is back once the gate reviewed it again: `bands.read`'s own rule")
        self.assertEqual(self.gate().run()["waiting"], ["v"])
        self.assertEqual(self.reads() - reads, 2, "and that review is kept until the next league/live change: not asked twice")
        for result in bands.BAD_OUTCOMES:
            with self.subTest(result):
                self.store.set_state("v", gate_outcome={"sha": sha, "result": result, "at": self.clock()})
                self.assertEqual(bands.read(self.root), [], "a gate outcome against it ends the row, as before")
        self.store.set_state("v", gate_outcome=None)
        self.assertEqual(bands.read(self.root), [row])
        adopt(self.store, self.release_c)
        self.assertEqual((self.review_of("v"), bands.read(self.root)), (None, []), "the next league/live change ends it again")
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": "a new image"}}))
        adopt(self.store, {**self.release_c, "image": "a new image"})
        self.assertEqual(bands.read(self.root), [], "and so does a new Gym")

    def test_the_second_review_is_a_real_one_a_program_it_fails_is_refused_and_never_has_a_row(self):
        """The review owed again is the gate's own, with its own consequence: a reviewer that fails the program now ends
        it (a refusal, its bar, its gate place closed), though the review before the adoption had passed it."""
        sha = self.validated("v")
        self.assertEqual(self.tuition(), [("v", 1)])
        adopt(self.store, self.release_b)
        self.replies = [{"text": json.dumps(review_failure("counts sessions to known events"))}]
        out = self.gate().run()
        state = self.store.family("v")["state"]
        self.assertEqual((out["refused"], out["looked"], [r["stage"] for r in self.store.refusals("v")]), (["v"], [], ["review"]))
        self.assertEqual((self.review_of("v"), state["gated_sha"], state["gate_ready"], state["gate_outcome"]["result"]),
                         ((sha, "fail", None), sha, False, "refused"))
        self.assertIn(sha, state["incubator_barred"])
        self.assertEqual((self.tuition(), self.store.looks()), ([], []), "no real order, and no look spent on it")

    def test_only_a_family_the_gate_reviews_again_has_a_row_after_the_adoption(self):
        """Every place a validated, reviewed Gym family can stand at the gate when league/live changes. Each had a tuition
        row; none has one after the adoption. Whether it gets one again is the gate's own rule, with nothing reset by
        the adoption: a family at the gate is reviewed again at the next round; a look the restart cut off is owed again
        (`Gate.owe`), behind the same review; a family the operator holds is not read while it is held; and a program
        the gate is done with (`gated_sha`: parked here, as three failed tries leave it) is never read again, so it has
        no row again. In no state is there a row without a review."""
        shas = {fid: self.validated(fid) for fid in ("at-the-gate", "held", "parked")}
        shas["in-flight"], _ = self.look_in_flight("in-flight")
        self.store.hold_gate("held", reason="the operator's")
        self.store.set_state("parked", gate_ready=False, gated_sha=shas["parked"])
        self.assertEqual(sorted(self.tuition()), sorted((fid, 1) for fid in shas), "each is on D2's route before it")
        ahead = {fid: self.store.family(fid)["state"] for fid in shas}

        adopt(self.store, self.release_b)
        self.assertEqual(bands.read(self.root), [], "no tuition row carries across the change, wherever the family stood")
        for fid in shas:
            with self.subTest(fid):
                state = self.store.family(fid)["state"]
                self.assertIsNone(state["review"])
                self.assertEqual(adoptions(self.store, fid)[-1]["_previous_selection"], {"review": ahead[fid]["review"]})
                for key in ("gate_ready", "gated_sha", "look_inflight", "gate_hold", "validation_line", "validation_version"):
                    self.assertEqual(state.get(key), ahead[fid].get(key), f"{key}: nothing of its gate place is reset")

        self.settings["gym"]["gate_checkpoint"] = None  # no look can be made: each round is the reviews and audits alone
        self.clock.advance(60)
        reads = self.reads()
        self.readers_pass(2)
        out = self.gate().run()  # the new process's gate: the look in flight died with the old one
        self.assertEqual((sorted(out["waiting"]), out["held"], out["looked"]), (["at-the-gate", "in-flight"], ["held"], []))
        self.assertEqual(self.reads() - reads, 4, "two programs, each reviewed and audited again; the other two are not read")
        self.assertEqual(sorted(self.tuition()), [("at-the-gate", 1), ("in-flight", 1)])
        self.assertEqual({fid: self.review_of(fid) for fid in shas},
                         {"at-the-gate": (shas["at-the-gate"], "pass", "pass"), "in-flight": (shas["in-flight"], "pass", "pass"),
                          "held": None, "parked": None}, "a row only where there is a review again")
        state = self.store.family("in-flight")["state"]
        self.assertEqual((state["look_inflight"], state["gate_ready"], self.store.get(f"look_tries:{shas['in-flight']}")),
                         (None, True, 1), "the look the restart cut off is owed again, by the gate's own rule")

        self.store.hold_gate("held", False, reason="released")
        self.readers_pass()
        self.assertEqual(sorted(self.gate().run()["waiting"]), ["at-the-gate", "held", "in-flight"])
        self.assertEqual((self.reads() - reads, self.review_of("held")), (6, (shas["held"], "pass", "pass")),
                         "released, it is reviewed again too; the two reviewed before are not asked twice")
        self.assertEqual(sorted(self.tuition()), [("at-the-gate", 1), ("held", 1), ("in-flight", 1)])
        self.assertEqual((self.review_of("parked"), self.store.family("parked")["state"]["gate_ready"]), (None, False),
                         "the gate is done with the parked program: never read again, and never a row again")

    def failed_between_the_gates_stages(self, fid="v"):
        """A validated family whose program the gate's audit FAILED, with no refusal on record yet: the operator's hold
        landed between the gate's stages, so the failed review was written and the refusal was not. It is still at the
        gate. (Its run sha, the failed review as the gate writes it.)"""
        sha = self.validated(fid)
        failed = {**reviewed(sha), "verdict": "fail", "stage": "audit", "reasons": ["unsafe"]}
        failed["audit"] = {**failed["audit"], "verdict": "fail"}
        self.store.set_state(fid, review=failed)
        self.store.hold_gate(fid, reason="the operator's")
        self.assertEqual(((fid, 1) in self.tuition(), self.store.refusals(fid), self.store.family(fid)["state"]["gate_ready"]),
                         (False, [], True))
        return sha, failed

    def refused_without_a_second_reading(self, fid, sha):
        """The hold released: the gate's next round refuses the program on the review it already made, and asks no
        reader anything."""
        self.store.hold_gate(fid, False, reason="released")
        reads = self.reads()
        self.readers_pass()  # a second reading would pass it: none is made
        out = self.gate().run()
        state = self.store.family(fid)["state"]
        self.assertEqual((out["refused"], out["looked"], self.reads() - reads), ([fid], [], 0),
                         "refused on the verdict it holds; no reader is asked again")
        self.assertEqual(([r["stage"] for r in self.store.refusals(fid)], state["gated_sha"], state["gate_ready"],
                          state["gate_outcome"]["result"]), (["audit"], sha, False, "refused"))
        self.assertEqual((self.tuition(), self.store.looks()), ([], []), "no real order, and no look spent on it")

    def test_a_review_that_did_not_pass_is_kept_and_its_program_is_never_read_a_second_time(self):
        """THE RULING OF OCT 3, 2026. The gate's review can hold a verdict against a program that no refusal holds yet.
        Cleared at a league/live-only adoption, the family would be left validated, at the gate and unreviewed: the
        gate's next round would read the program again, and a second reader could pass what the first one failed. So
        the review that did not pass is kept as it is. Its verdict is the program's bar all the same
        (`incubator.adoption_bars`), kept for good; practice is offered no row for it; and the gate refuses it on the
        review it holds."""
        sha, failed = self.failed_between_the_gates_stages()
        self.with_train_best("t")
        adopt(self.store, self.release_b)
        state = self.store.family("v")["state"]
        event = adoptions(self.store, "v")[-1]
        self.assertEqual((state["review"], event["_previous_selection"], event["incubator_barred"]),
                         (failed, {}, [sha[:12]]), "kept as it is: nothing of it is cleared, and its bar is recorded")
        self.assertIn("review", event["kept"])
        self.assertEqual(state["incubator_barred"][sha]["why"], "the gate's audit failed it")
        self.assertEqual((self.tuition(), bands.incubator(self.root, family="v", version=1)), ([], []))
        self.assertEqual([r["family"] for r in self.practice()], ["t"], "a program whose review failed has no practice row")
        self.assertEqual(state["gate_ready"], True, "still at the gate, where the review it holds decides")
        self.refused_without_a_second_reading("v", sha)
        # The next league/live change keeps it again; a new Gym clears it with everything else, its bar standing.
        adopt(self.store, self.release_c)
        self.assertEqual(self.store.family("v")["state"]["review"], failed)
        adopt(self.store, {**self.release_c, "image": "a new image"})
        state = self.store.family("v")["state"]
        self.assertEqual((state["review"], sha in state["incubator_barred"]), (None, True))

    def test_a_review_that_passed_is_read_again_and_one_that_failed_is_not(self):
        """The two halves of the rule side by side, at one adoption: the passing review is cleared, so the gate reads
        that program again (a review and an audit) before any order; the failing one stands, so the gate reads that
        program never again."""
        passed = self.validated("passed")
        sha, failed = self.failed_between_the_gates_stages("failed")
        adopt(self.store, self.release_b)
        self.assertEqual((self.review_of("passed"), self.store.family("failed")["state"]["review"]), (None, failed))
        self.store.hold_gate("failed", False, reason="released")
        self.settings["gym"]["gate_checkpoint"] = None  # no look can be made: the round is the reviews and audits alone
        reads = self.reads()
        self.readers_pass(2)  # both programs would pass a reading now
        out = self.gate().run()
        self.assertEqual((out["waiting"], out["refused"], self.reads() - reads), (["passed"], ["failed"], 2),
                         "one program is read again, by both readers; the other is refused unread")
        self.assertEqual((self.review_of("passed"), self.review_of("failed")),
                         ((passed, "pass", "pass"), (sha, "fail", "fail")))
        self.assertEqual(self.tuition(), [("passed", 1)])

    def test_the_restoration_gives_back_a_review_that_did_not_pass_and_never_one_that_passed(self):
        """The release before this rule archived and cleared every review, the failed ones too. The restoration gives
        the failed one back with the selection, as it was archived: the family is again validated, at the gate and
        FAILED, not validated, at the gate and unread. The passing one stays cleared (no tuition row comes back)."""
        sha, failed = self.failed_between_the_gates_stages("failed")
        passed = self.validated("passed")
        row = self.tuition()
        self.assertEqual(row, [("passed", 1)])
        self.clock.advance(3600)
        at = self.store.now()
        adopt_as_v3a(self.store, self.release_b)
        wiped = {fid: self.store.family(fid)["state"] for fid in ("failed", "passed")}
        self.assertEqual([(s["review"], s[ARCHIVE_KEY]["review"]["verdict"]) for s in wiped.values()],
                         [(None, "fail"), (None, "pass")], "that release cleared both, and archived both")
        self.assertIn(sha, wiped["failed"]["incubator_barred"], "and recorded the failed one's bar first")
        self.clock.advance(3600)

        out = adopt(self.store, self.release_c)
        self.assertEqual(out["restored"], {"failed": at, "passed": at})
        state = self.store.family("failed")["state"]
        event = adoptions(self.store, "failed")[-1]
        self.assertEqual((state["review"], state["validation_version"], state["gate_ready"]), (failed, 1, True),
                         "given back as it was archived, with the selection")
        self.assertIn("review", event["restored"]["keys"])
        self.assertIn("review", event["kept"])
        self.assertEqual(event["_previous_selection"], {"train_passed": {}, "incubator_reviews": {}, "review": None},
                         "what this adoption cleared: nothing the family held")
        self.assertEqual([r["family"] for r in self.practice()], ["passed"], "no practice row for the program it failed")
        other = adoptions(self.store, "passed")[-1]
        self.assertEqual((self.review_of("passed"), "review" in other["restored"]["keys"], "review" in other["kept"]),
                         (None, False, False), "a review that passed is never given back")
        self.assertEqual(self.tuition(), [], "and no tuition row comes back with either")
        self.store.hold_gate("passed", reason="the operator's")  # so the round below reads the failed family alone
        self.refused_without_a_second_reading("failed", sha)
        # The family whose review had passed is read again by the gate before any order, as after any such adoption.
        self.store.hold_gate("passed", False, reason="released")
        self.settings["gym"]["gate_checkpoint"] = None
        reads = self.reads()
        self.readers_pass()
        self.assertEqual((self.gate().run()["waiting"], self.reads() - reads, self.review_of("passed")),
                         (["passed"], 2, (passed, "pass", "pass")))
        self.assertEqual(self.tuition(), row)

    def test_the_restoration_never_replaces_a_review_that_stands_with_the_archived_one(self):
        """A family that holds a review of its own that did not pass keeps it: the archived one is not written over it
        (the newer verdict is the family's standing), and the selection is given back all the same."""
        sha, failed = self.failed_between_the_gates_stages()
        self.clock.advance(3600)
        at = self.store.now()
        adopt_as_v3a(self.store, self.release_b)
        newer = {"sha": "c" * 64, "version": 2, "verdict": "fail", "reasons": ["a later reading"]}
        self.store.set_state("v", review=newer)
        self.clock.advance(3600)
        self.assertEqual(adopt(self.store, self.release_c)["restored"], {"v": at})
        state = self.store.family("v")["state"]
        event = adoptions(self.store, "v")[-1]
        self.assertEqual((state["review"], state["validation_version"]), (newer, 1))
        self.assertNotIn("review", event["restored"]["keys"])
        self.assertIn("review", event["kept"])
        self.assertNotIn("review", event["_previous_selection"], "it was not cleared")
        self.assertEqual(sorted(state["incubator_barred"]), sorted([sha, "c" * 64]), "both verdicts are bars, for good")

    def test_a_look_that_adoption_cut_off_is_owed_again_so_nothing_given_back_waits_on_a_look_that_never_comes(self):
        """The look's marker is no selection key: that release archived `gate_ready` as the look had cleared it, kept the
        marker, and its gate then dropped the marker without owing the look (the validation it was sent for was gone).
        Given back as archived, the family would hold a validated version that no gate round takes up and no tournament
        round readies: it would wait for good. Its gate place is given back by the tournament's own rule instead, which
        is where the gate leaves a look a restart cut off; its review is not given back, so the gate reviews and audits
        the program again before it makes that look, and no tuition row waits meanwhile."""
        sha, marker = self.look_in_flight()
        self.clock.advance(3600)
        at = self.store.now()
        adopt_as_v3a(self.store, self.release_b)
        self.assertEqual(self.store.family("v")["state"]["look_inflight"], marker, "that release kept the marker")
        self.clock.advance(60)
        self.assertEqual(self.gate().run()["looked"], [])  # that release's gate, at its restart
        state = self.store.family("v")["state"]
        self.assertEqual((state["look_inflight"], state["gate_ready"], state[ARCHIVE_KEY]["gate_ready"]), (None, False, False),
                         "it dropped the marker and owed nothing")
        self.assertEqual((self.store.get(f"look_tries:{sha}", 0), self.store.looked(sha)), (0, False), "no look was made")

        self.clock.advance(3600)
        self.assertEqual(adopt(self.store, self.release_c)["restored"], {"v": at})
        state = self.store.family("v")["state"]
        self.assertEqual((state["validation_version"], state["gate_ready"], state["gated_sha"]), (1, True, None))
        restored = adoptions(self.store, "v")[-1]["restored"]
        self.assertEqual((restored["look_owed"], "gate_ready" in restored["keys"], "review" in restored["keys"]),
                         (True, True, False))
        self.assertEqual((self.review_of("v"), self.tuition()), (None, []), "no review and no row come back with its place")
        self.answer = lambda job: {**weak(job), "gym_image": self.IMAGE, "gym_bundle": self.bundle}  # its holdout fails
        reads = self.reads()
        self.readers_pass()
        self.assertEqual(self.gate().run()["looked"], [{"family": "v", "passed": False}],
                         "and the gate makes the look it owed")
        self.assertEqual((self.reads() - reads, self.review_of("v")), (2, (sha, "pass", "pass")),
                         "behind a review and an audit of the program, asked again first")
        state = self.store.family("v")["state"]
        self.assertEqual((self.store.looked(sha), state["gated_sha"], state["gate_ready"], state["look_inflight"],
                          state["gate_outcome"]["result"]), (True, sha, False, None, "failed"))
        self.assertEqual(bands.read(self.root), [], "a failed look ends the tuition row, as it always did")

    def test_a_marker_that_release_left_in_the_state_is_the_gates_to_owe(self):
        """No gate round ran between the two adoptions: the marker is still there. The selection is given back as it was
        archived, bar the review, and the gate owes the look again itself (`Gate.owe`: its version is the one validated
        again), behind a review and an audit of the program."""
        sha, marker = self.look_in_flight()
        self.clock.advance(3600)
        at = self.store.now()
        adopt_as_v3a(self.store, self.release_b)
        self.clock.advance(3600)
        self.assertEqual(adopt(self.store, self.release_c)["restored"], {"v": at})
        state = self.store.family("v")["state"]
        self.assertEqual((state["gate_ready"], state["look_inflight"]), (False, marker))
        self.assertNotIn("look_owed", adoptions(self.store, "v")[-1]["restored"])
        self.assertEqual((self.review_of("v"), self.tuition()), (None, []), "no review is given back, so no row waits on the look")
        self.clock.advance(60)
        reads = self.reads()
        self.readers_pass()
        self.assertEqual(self.gate().run()["looked"], [{"family": "v", "passed": True}])
        self.assertEqual(self.reads() - reads, 2, "reviewed and audited again before the look")
        self.assertEqual((self.store.get(f"look_tries:{sha}"), self.store.looked(sha), self.tuition()), (1, True, []),
                         "one try counted, the look made, and a passed look's row is its band's, not tuition's")
        self.assertEqual(self.store.family("v")["band"], "candidate")

    def test_no_gate_place_is_given_where_the_tournaments_own_rule_gives_none(self):
        """Only a look that was cut off is owed. Each of these held no place when that adoption archived it, for a reason
        that still stands, and is given none: the gate is done with its program (a look row; `gated_sha`, as three failed
        tries park it; a refusal row on a verdict, whose mark a new Gym cleared: `incubator.refused_version`, as
        `Tournament.gate_spent` reads it), a gate outcome ended it, it was demoted, it did not meet the line, or its
        validation is another image's (the tournament owes that one first)."""
        from league.swarm.researcher import demote_version

        shas = {fid: self.validated(fid)
                for fid in ("demoted", "looked", "parked", "refused", "ended", "marked", "elsewhere")}
        demote_version(self.store, self.store.family("demoted"), 1, clock=self.clock)  # the real writer: mark and outcome
        self.store.add_look("looked", 1, shas["looked"], passed=False, p_value=0.4, detail={"synthetic": True})
        self.store.set_state("looked", gate_ready=False)
        self.store.set_state("parked", gate_ready=False, gated_sha=shas["parked"])
        self.store.refuse("refused", 1, "review", "a synthetic refusal")  # the row alone: no mark, no outcome, no bar
        self.store.set_state("refused", gate_ready=False)
        self.store.set_state("ended", gate_ready=False,
                             gate_outcome={"sha": shas["ended"], "result": "held", "at": self.clock()})
        self.store.set_state("marked", gate_ready=False, robust_failed=[1])
        self.store.set_state("elsewhere", gate_ready=False, validation_image="an older image")
        self.with_train_best("below")
        self.answer = lambda job: {**weak(job), "gym_image": self.IMAGE, "gym_bundle": self.bundle}
        self.assertFalse(self.tournament.validate([self.store.family("below")])["judged"]["below"]["passed"])
        fids = (*shas, "below")
        self.assertEqual([self.store.family(fid)["state"]["gate_ready"] for fid in fids], [False] * len(fids))
        self.clock.advance(3600)
        at = self.store.now()
        adopt_as_v3a(self.store, self.release_b)
        self.clock.advance(3600)
        self.assertEqual(adopt(self.store, self.release_c)["restored"], {fid: at for fid in fids})
        for fid in fids:
            with self.subTest(fid):
                state = self.store.family(fid)["state"]
                self.assertEqual((state["validation_version"], state["gate_ready"]), (1, False))
                self.assertNotIn("look_owed", adoptions(self.store, fid)[-1]["restored"])
        self.assertEqual(self.store.family("demoted")["state"]["gate_outcome"]["result"], "demoted")
        self.assertEqual(self.gate().run()["looked"], [], "and the gate takes none of them up")

    def test_the_incubators_marks_and_reviews_go_and_bars_refusals_and_looks_stay(self):
        sha = self.validated("v")
        failed, older = "f" * 64, "e" * 64
        self.store.set_state("v", train_passed={"1": {"evaluator": self.release_a, "objective": "robust"}},
                             incubator_reviews={sha: reviewed(sha), failed: {"sha": failed, "version": 2, "verdict": "fail",
                                                                              "reasons": ["unsafe"]}},
                             incubator_barred={older: {"why": "an older verdict", "at": 1.0}},
                             look_inflight={"sha": "pending-look", "n": 2})
        self.store.refuse("v", 1, "audit", "a historical refusal")
        self.store.add_look("v", 1, "a-looked-sha", passed=False, p_value=0.4, detail={"synthetic": True})
        ahead = self.store.family("v")
        kept = (self.store.totals(), self.store.looks(), self.store.refusals("v"),
                self.store.lineage_looks("v", include_inflight=True))

        adopt(self.store, self.release_b)
        state = self.store.family("v")["state"]
        self.assertEqual((state["train_passed"], state["incubator_reviews"]), ({}, {}), "owed again under the new fingerprint")
        self.assertEqual(state["incubator_barred"][older], {"why": "an older verdict", "at": 1.0}, "a bar is kept for good")
        self.assertEqual(sorted(state["incubator_barred"]), [older, failed],
                         "and a verdict only the cleared reviews held is its program's bar first")
        self.assertEqual((self.store.totals(), self.store.looks(), self.store.refusals("v"),
                          self.store.lineage_looks("v", include_inflight=True)), kept, "no trial, look or refusal moves")
        self.assertTrue(self.store.looked("a-looked-sha"))
        self.assertEqual(state["look_inflight"], {"sha": "pending-look", "n": 2})
        self.assertIsNotNone(ahead["state"]["review"])
        self.assertIsNone(state["review"], "the gate's own review goes with them: it is the live route's fact too")
        event = adoptions(self.store, "v")[-1]
        self.assertEqual((event["incubator_barred"], event["_previous_selection"]),
                         ([failed[:12]], {key: ahead["state"][key] for key in GONE}))


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
